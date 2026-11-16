package app.kimlikmerkezi.toplayici

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.work.WorkInfo
import androidx.work.WorkManager
import app.kimlikmerkezi.toplayici.aktarim.AdresSuzgeci
import app.kimlikmerkezi.toplayici.aktarim.AktarimDurumu
import app.kimlikmerkezi.toplayici.aktarim.BaglantiUretici
import app.kimlikmerkezi.toplayici.aktarim.ElleAktarim
import app.kimlikmerkezi.toplayici.aktarim.EslesmeDeposu
import app.kimlikmerkezi.toplayici.aktarim.EslesmeKodu
import app.kimlikmerkezi.toplayici.aktarim.Gonderici
import app.kimlikmerkezi.toplayici.aktarim.HttpsBaglanti
import app.kimlikmerkezi.toplayici.aktarim.sha256Hex
import app.kimlikmerkezi.toplayici.arkaplan.ArkaPlan
import app.kimlikmerkezi.toplayici.giden.AesGcmSifreleyici
import app.kimlikmerkezi.toplayici.giden.CihazBilgisi
import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.giden.KeystoreAnahtar
import app.kimlikmerkezi.toplayici.gunluk.Gunluk
import app.kimlikmerkezi.toplayici.topla.BellekDepolama
import app.kimlikmerkezi.toplayici.ui.MainActivity
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.nio.file.Files
import java.util.Base64
import java.util.zip.ZipInputStream

private const val CIHAZ = "3f2b8c1e-5a47-4d9e-8b36-1c7e0a9d4f52"

/** Emülatör İÇİNDE çalışan sahte PC (127.0.0.1, gerçek TLS; testte yerel sayılır). */
@RunWith(AndroidJUnit4::class)
class AktarimUcTanUcaTest {
    @get:Rule
    val kural = createAndroidComposeRule<MainActivity>()
    private val ctx: Context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val sunucu = SahteSunucu()

    @Before fun ac() { AdresSuzgeci.testLoopback = true; ctx.depo.eslesme.kaldir() }
    @After fun kapat() { ctx.depo.eslesme.kaldir(); AdresSuzgeci.testLoopback = false; sunucu.close() }

    private fun bekle(sn: Long = 30, k: () -> Boolean) = kural.waitUntil(sn * 1000) { k() }

    @Test
    fun kodYapistirEslesGonderBekleyen0() {
        val depo = ctx.depo
        val json = """{"a":["127.0.0.1"],"p":${sunucu.port},"f":"${sunucu.parmakIzi}","k":"${sunucu.mantik.eslesmeKodu}","n":"TEST-PC"}"""
        val kod = "km1:" + Base64.getUrlEncoder().withoutPadding().encodeToString(json.toByteArray())

        kural.onNodeWithTag("ayarlar_btn").performClick()
        kural.onNodeWithTag("eslestir_btn").performScrollTo().performClick()
        kural.onNodeWithTag("kod_alani").performTextInput(kod)
        kural.onNodeWithTag("kod_devam_btn").performClick()
        kural.onNodeWithTag("onay_metni").assertIsDisplayed()
        kural.onNodeWithText("TEST-PC adlı bilgisayarla eşleştirilsin mi?").assertIsDisplayed()
        kural.onNodeWithTag("onayla_btn").performClick()
        bekle { kural.onAllNodesWithTag("eslesme_durumu").fetchSemanticsNodes().isNotEmpty() }
        assertTrue(depo.eslesme.eslesmis())
        assertEquals(sunucu.mantik.anahtar, depo.eslesme.anahtar())

        kural.onNodeWithTag("geri").performClick() // Ayarlar
        kural.onNodeWithTag("geri").performClick() // Ana
        val metin = "uctan uca not ${System.nanoTime()}"
        depo.kutu.kayitEkle("not.hizli", "notlar", metin)
        kural.onNodeWithTag("pc_gonder_btn").performClick()
        bekle { depo.kutu.bekleyenKayitSayisi() == 0 && sunucu.mantik.tamamlanan.isNotEmpty() }
        assertEquals(0, depo.kutu.bekleyenKayitSayisi())
        val alinan = sunucu.mantik.tamamlanan.values.map { String(it, Charsets.UTF_8) }
        assertTrue(alinan.any { it.contains(metin) })
        alinan.forEach { assertTrue(it.trimEnd().endsWith("}") && it.lines().filter { l -> l.isNotEmpty() }.last().startsWith("{\"kapanis\":true")) }
        // ikinci kez: gönderilecek dosya yok, sunucuya yeni PUT gitmez
        val put = sunucu.mantik.putSayisi.get()
        kural.onNodeWithTag("pc_gonder_btn").performClick()
        Thread.sleep(3000)
        assertEquals(put, sunucu.mantik.putSayisi.get())
    }
}

@RunWith(AndroidJUnit4::class)
class GondericiEmulatorTest {
    private val ctx: Context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val sunucu = SahteSunucu()
    private val dizin = Files.createTempDirectory(InstrumentationRegistry.getInstrumentation().targetContext.cacheDir.toPath(), "g").toFile()

    @Before fun ac() { AdresSuzgeci.testLoopback = true }
    @After fun kapat() { AdresSuzgeci.testLoopback = false; sunucu.close(); dizin.deleteRecursively() }

    private fun kur(): Pair<GidenKutusu, Gonderici> {
        val kutu = GidenKutusu(dizin, KeystoreAnahtar.sifreleyici(), CihazBilgisi(CIHAZ, "0.2.0", 31, "TEST"), Gunluk(null))
        val d = BellekDepolama()
        val e = EslesmeDeposu(d, AesGcmSifreleyici(KeystoreAnahtar.al("km_test_eslesme")))
        e.kaydet(EslesmeKodu(listOf("127.0.0.1"), sunucu.port, sunucu.parmakIzi, "k", "TEST-PC"), sunucu.mantik.anahtar)
        return kutu to Gonderici(kutu, e, d, Gunluk(null), BaglantiUretici { a, p -> HttpsBaglanti(a, p, sunucu.parmakIzi) }, { CIHAZ }, bekle = {}, bulucu = { null })
    }

    @Test
    fun ortadaKesilinceYenidenBaslarKaldigiYerdenTamamlanirAyniDosyaIkinciKezGitmez() {
        val (kutu, g) = kur()
        repeat(30) { kutu.kayitEkle("not.hizli", "notlar", "k".repeat(60_000)) }
        kutu.acikDosyayiKapat()
        val id = kutu.kapatilmisDosyalar().single().dosyaId
        val ozet = kutu.dosyayiOku(id).readBytes().sha256Hex()

        sunucu.mantik.izinVerilenPut = 1 // ilk 1 MiB'lik parça gider, sonra bağlantı kopar
        assertEquals(AktarimDurumu.Hata("ulasilamadi"), g.gonder())
        assertEquals(1, kutu.bekleyenDosyaSayisi()) // 'var' görülmedi: silinmedi
        assertEquals(1024 * 1024, sunucu.mantik.kismi[id]!!.size())

        sunucu.mantik.izinVerilenPut = Int.MAX_VALUE
        assertEquals(AktarimDurumu.Tamam(1, 30), g.gonder())
        assertEquals(0, kutu.bekleyenKayitSayisi())
        assertEquals(ozet, sunucu.mantik.tamamlanan[id]!!.sha256Hex())
        assertTrue(sunucu.mantik.putBoyutlari.all { it <= 1024 * 1024 })

        val put = sunucu.mantik.putSayisi.get()
        assertEquals(AktarimDurumu.Tamam(0, 0), g.gonder())
        assertEquals(put, sunucu.mantik.putSayisi.get())
    }

    @Test
    fun yetkisiz401DosyaSilinmez() {
        val (kutu, g) = kur()
        kutu.kayitEkle("not.hizli", "notlar", "a")
        sunucu.mantik.zorla401 = true
        assertEquals(AktarimDurumu.Hata("yetkisiz"), g.gonder())
        assertEquals(1, kutu.bekleyenKayitSayisi())
        assertFalse(sunucu.mantik.tamamlanan.isNotEmpty())
    }

    @Test
    fun yanlisParmakIziIstekGonderilmez() {
        val (kutu, _) = kur()
        kutu.kayitEkle("not.hizli", "notlar", "a")
        val d = BellekDepolama()
        val e = EslesmeDeposu(d, AesGcmSifreleyici(KeystoreAnahtar.al("km_test_eslesme")))
        e.kaydet(EslesmeKodu(listOf("127.0.0.1"), sunucu.port, "1".repeat(64), "k", "x"), sunucu.mantik.anahtar)
        val g = Gonderici(kutu, e, d, Gunluk(null), BaglantiUretici { a, p -> HttpsBaglanti(a, p, e.parmakIzi()!!) }, { CIHAZ }, bekle = {}, bulucu = { null })
        assertEquals(AktarimDurumu.Hata("sertifika"), g.gonder())
        assertEquals(0, sunucu.mantik.istekSayisi.get())
    }

    @Test
    fun dosyayaAktarZipSozlesmeyeUyar() {
        val (kutu, _) = kur()
        kutu.kayitEkle("not.hizli", "notlar", "elle aktarim notu")
        val o = ByteArrayOutputStream()
        val idler = ElleAktarim.zipYaz(kutu, o)
        assertEquals(1, idler.size)
        ZipInputStream(ByteArrayInputStream(o.toByteArray())).use { z ->
            val e = z.nextEntry!!
            assertEquals("${idler[0]}.jsonl", e.name)
            val satirlar = String(z.readBytes(), Charsets.UTF_8).trimEnd('\n').split("\n")
            assertTrue(satirlar.first().startsWith("{\"baslik\":true,\"bicim\":1,\"cihaz_id\":\"$CIHAZ\""))
            assertTrue(satirlar[1].contains("elle aktarim notu"))
            assertEquals("{\"kapanis\":true,\"kayit_sayisi\":1}", satirlar.last())
        }
        assertEquals(1, kutu.bekleyenKayitSayisi()) // onay olmadan silinmez
    }
}

@RunWith(AndroidJUnit4::class)
class AktarimArayuzTest {
    @get:Rule
    val kural = createAndroidComposeRule<MainActivity>()
    private val ctx: Context get() = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun eslesmeYokkenGonderEslesmeEkraninaGiderVeAyarlarOgeleriVar() {
        ctx.depo.eslesme.kaldir()
        kural.onNodeWithTag("pc_gonder_btn").performClick()
        kural.onNodeWithTag("kod_alani").assertIsDisplayed()
        kural.onNodeWithTag("qr_tara_btn").assertIsDisplayed()
        kural.onNodeWithTag("geri").performClick()
        kural.onNodeWithTag("ayarlar_btn").performClick()
        kural.onNodeWithTag("anahtar_arka_plan").performScrollTo().assertIsDisplayed()
        kural.onNodeWithTag("dosyaya_aktar_btn").performScrollTo().performClick()
        kural.onNodeWithTag("sifresiz_uyari").assertIsDisplayed()
        kural.onNodeWithText("Vazgeç").performClick()
        kural.onNodeWithTag("pil_btn").performScrollTo().performClick()
        kural.onNodeWithTag("pil_ayari_btn").assertIsDisplayed()
    }

    @Test
    fun arkaPlanIsiPlanlanirVeIptalEdilir() {
        ArkaPlan.planla(ctx, true)
        val wm = WorkManager.getInstance(ctx)
        val bilgi = wm.getWorkInfosForUniqueWork(ArkaPlan.IS_ADI).get()
        assertTrue(bilgi.isNotEmpty() && bilgi.all { it.state == WorkInfo.State.ENQUEUED || it.state == WorkInfo.State.RUNNING })
        ArkaPlan.planla(ctx, false)
        assertTrue(wm.getWorkInfosForUniqueWork(ArkaPlan.IS_ADI).get().all { it.state == WorkInfo.State.CANCELLED })
    }
}
