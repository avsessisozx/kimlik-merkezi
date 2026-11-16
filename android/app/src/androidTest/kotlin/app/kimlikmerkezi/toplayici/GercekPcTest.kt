package app.kimlikmerkezi.toplayici

import android.content.Context
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.kimlikmerkezi.toplayici.aktarim.AktarimDurumu
import app.kimlikmerkezi.toplayici.aktarim.BaglantiUretici
import app.kimlikmerkezi.toplayici.aktarim.EslesmeKodu
import app.kimlikmerkezi.toplayici.aktarim.EslesmeSonucu
import app.kimlikmerkezi.toplayici.aktarim.Gonderici
import app.kimlikmerkezi.toplayici.aktarim.HttpsBaglanti
import app.kimlikmerkezi.toplayici.aktarim.PcBaglanti
import app.kimlikmerkezi.toplayici.aktarim.Yanit
import app.kimlikmerkezi.toplayici.aktarim.sha256Hex
import app.kimlikmerkezi.toplayici.giden.YeniKayit
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID

/** Yalnız GERÇEK PC alıcısına karşı uçtan uca koşuda (`-e gercek_pc 1`) çalışır; olağan koşuda atlanır. */
@Retention(AnnotationRetention.RUNTIME)
@Target(AnnotationTarget.CLASS, AnnotationTarget.FUNCTION)
annotation class GercekPc

/**
 * Aşamalar ana makine betiğiyle (android/ci/uctan_uca.sh) sıralanır: alıcıyı açıp kapatan ana makinedir.
 * Aşamalar arasında uygulama verisi silinmez; giden kutusu, eşleşme ve beklenen-kayıt dosyası kalıcıdır.
 * Her aşama `olcum=` satırı yayımlar (`am instrument -r` çıktısında INSTRUMENTATION_STATUS).
 */
private val HATALAR = java.util.Collections.synchronizedList(ArrayList<String>())

@GercekPc
@RunWith(AndroidJUnit4::class)
class GercekPcTest {
    private val ins get() = InstrumentationRegistry.getInstrumentation()
    private val ctx: Context get() = ins.targetContext
    private val args get() = InstrumentationRegistry.getArguments()
    private val dizin: File get() = File(ctx.filesDir, "uctan_uca").also { it.mkdirs() }
    private val beklenenDosya: File get() = File(dizin, "beklenen.jsonl")

    @Before
    fun kapi() {
        assumeTrue("gercek_pc=1 verilmedi; bu test yalniz uctan uca betikte kosar", args.getString("gercek_pc") == "1")
    }

    private fun olcum(s: String) {
        Log.i("UCTANUCA", s)
        ins.sendStatus(0, Bundle().apply { putString("olcum", s) })
    }

    private fun kod(): EslesmeKodu =
        requireNotNull(EslesmeKodu.coz(requireNotNull(args.getString("km1")) { "km1 argumani yok" })) { "km1 cozulemedi" }

    // ---- kayıt üretimi ----------------------------------------------------------------------------------------
    private fun kayitlar(n: Int): List<YeniKayit> = (0 until n).map { i ->
        when (i % 6) {
            0 -> YeniKayit("not.hizli", "notlar", "Not $i: çalışma özeti — ığüşöç İĞÜŞÖÇ")
            1 -> YeniKayit("not.hizli", "notlar", "Emoji notu $i \uD83D\uDE00 \uD83C\uDDF9\uD83C\uDDF7 \uD83D\uDC68\u200D\uD83D\uDCBB sonu")
            2 -> YeniKayit("not.hizli", "notlar", "Satır $i:\u2028ikinci parça\nüçüncü satır\r\ndördüncü\tsekme")
            3 -> YeniKayit("paylasim.metin", "notlar", "Paylaşılan metin $i\n\"tırnak\" ve \\ ters bölü", buildJsonObject { put("kaynak_uygulama", "com.ornek.mesaj") })
            4 -> YeniKayit(
                "paylasim.link", "notlar", "Başlık $i\nhttps://ornek.test/yazi/$i",
                buildJsonObject { put("url", "https://ornek.test/yazi/$i"); put("baslik", "Başlık $i"); put("kaynak_uygulama", "com.ornek.tarayici") },
            )
            else -> YeniKayit("not.hizli", "notlar", "Uzun not $i " + "şğüçöı ".repeat(500))
        }
    }

    private fun satir(id: String, k: YeniKayit, metin: String) =
        buildJsonObject { put("id", id); put("tur", k.tur); put("kategori", k.kategori); put("metin", metin) }.toString()

    /** Eklenen kayıtları (kutunun GERÇEKTE sakladığı metinle) beklenen dosyasına yazar. */
    private fun ekle(liste: List<YeniKayit>, ekleModu: Boolean) {
        val kutu = ctx.depo.kutu
        val idler = kutu.kayitlariEkle(liste)
        val satirlar = ArrayList<String>()
        if (!ekleModu) satirlar += buildJsonObject { put("cihaz_id", ctx.depo.cihazId) }.toString()
        idler.forEachIndexed { i, id ->
            val saklanan = requireNotNull(kutu.kayitBul(id)) { "kayit bulunamadi" }
            assertEquals("kutu metni degistirdi (kayit $i, tur ${liste[i].tur})", liste[i].metin, saklanan.metin)
            satirlar += satir(id, liste[i], saklanan.metin)
        }
        val metin = satirlar.joinToString("\n", postfix = "\n")
        if (ekleModu) beklenenDosya.appendText(metin, Charsets.UTF_8) else beklenenDosya.writeText(metin, Charsets.UTF_8)
    }

    /** Test için ölçen/yavaşlatan bağlantı sarmalayıcısı. */
    private class Olcumlu(private val ic: PcBaglanti, private val bekleMs: Long, private val kayit: MutableList<LongArray>) : PcBaglanti {
        private fun <T> izle(ad: String, f: () -> T): T = try { f() } catch (e: Exception) {
            HATALAR += "$ad ${System.currentTimeMillis() % 100000}: ${e.javaClass.name}: ${e.message} <- ${e.cause?.javaClass?.name}: ${e.cause?.message}"
            throw e
        }
        override fun durum() = izle("durum") { ic.durum() }
        override fun eslestir(govde: ByteArray) = izle("eslestir") { ic.eslestir(govde) }
        override fun head(cihazId: String, dosyaId: String, anahtar: String) = izle("head") { ic.head(cihazId, dosyaId, anahtar) }
        override fun put(cihazId: String, dosyaId: String, anahtar: String, bas: Long, toplam: Long, sha: String, parca: ByteArray): Yanit {
            if (bekleMs > 0) Thread.sleep(bekleMs)
            val y = izle("put") { ic.put(cihazId, dosyaId, anahtar, bas, toplam, sha, parca) } // hata atarsa kayıt yazılmaz
            kayit += longArrayOf(bas, parca.size.toLong(), toplam, y.kod.toLong())
            return y
        }
    }

    private fun olcumluGonderici(bekleMs: Long, kayit: MutableList<LongArray>): Gonderici {
        val d = ctx.depo
        return Gonderici(
            d.kutu, d.eslesme, d.depolama, d.gunluk,
            BaglantiUretici { a, p -> Olcumlu(HttpsBaglanti(a, p, d.eslesme.parmakIzi() ?: error("eslesme yok")), bekleMs, kayit) },
            { d.cihazId },
            bulucu = { null },
        )
    }

    // ---- aşamalar ---------------------------------------------------------------------------------------------
    /** Alıcı KAPALI: 120 kayıt, 3 kapatılmış dosya; gönder -> ulasilamadi, hiçbir dosya silinmez. */
    @Test
    fun a1_biriktir() {
        val d = ctx.depo
        assertEquals("temiz kurulum bekleniyordu", 0, d.kutu.bekleyenKayitSayisi())
        // Eşleşme kaydı yalnız adres/parmak izi için kullanılır (alıcı kapalı); sahte anahtar a2'de gerçek eşleştirmeyle değişir.
        d.eslesme.kaydet(kod(), "0".repeat(64))
        val t0 = System.currentTimeMillis()
        val hepsi = kayitlar(120)
        for (grup in 0 until 3) {
            ekle(hepsi.subList(grup * 40, grup * 40 + 40), ekleModu = grup > 0)
            d.kutu.acikDosyayiKapat()
        }
        assertEquals(120, d.kutu.bekleyenKayitSayisi())
        assertEquals(3, d.kutu.bekleyenDosyaSayisi())
        val sonuc = d.gonderici.gonder()
        assertEquals("alici kapaliyken gonder", AktarimDurumu.Hata("ulasilamadi"), sonuc)
        assertEquals("hicbir dosya silinmemeli", 3, d.kutu.bekleyenDosyaSayisi())
        assertEquals(120, d.kutu.bekleyenKayitSayisi())
        olcum("a1_biriktir kayit=120 dosya=3 gonder=${(sonuc as AktarimDurumu.Hata).kod} bekleyen_dosya=${d.kutu.bekleyenDosyaSayisi()} sure_ms=${System.currentTimeMillis() - t0}")
    }

    /** Alıcı AÇIK: gerçek POST /eslestir, sonra gönder; tüm dosyalar `var`, bekleyen 0. */
    @Test
    fun a2_eslesGonder() {
        val d = ctx.depo
        assertEquals(3, d.kutu.bekleyenDosyaSayisi())
        val kopya = File(dizin, "kopya").also { it.mkdirs() }
        for (f in d.kutu.kapatilmisDosyalar()) File(kopya, "${f.dosyaId}.jsonl").writeBytes(d.kutu.dosyayiOku(f.dosyaId).use { it.readBytes() })
        val k = kod()
        val t0 = System.currentTimeMillis()
        val es = d.eslestirici.eslestir(k, d.cihazId, Build.MODEL)
        assertEquals("gercek /eslestir", EslesmeSonucu.Tamam, es)
        assertTrue(d.eslesme.eslesmis())
        val t1 = System.currentTimeMillis()
        val bayt = d.kutu.kapatilmisDosyalar().sumOf { it.boyutBayt }
        val sonuc = olcumluGonderici(0, ArrayList()).gonder()
        val sure = System.currentTimeMillis() - t1
        assertEquals("ag hatalari: ${HATALAR.joinToString(" | ")}", AktarimDurumu.Tamam(3, 120), sonuc)
        assertEquals(0, d.kutu.bekleyenKayitSayisi())
        assertEquals(0, d.kutu.bekleyenDosyaSayisi())
        olcum("a2_esles_gonder eslestirme_ms=${t1 - t0} dosya=3 kayit=120 bayt~=$bayt gonder_ms=$sure bekleyen=0")
    }

    /** Büyük dosya, ana makine alıcıyı öldürürken: hata, dosya silinmez. */
    @Test
    fun a3_kesinti1() {
        val d = ctx.depo
        assertEquals(0, d.kutu.bekleyenDosyaSayisi())
        val buyuk = (0 until 110).map { i ->
            YeniKayit("not.hizli", "notlar", "Büyük kayıt $i ığüşöç " + "k${i % 10}".repeat(29_000))
        }
        d.kutu.acikDosyayiKapat()
        ekle(buyuk, ekleModu = true)
        d.kutu.acikDosyayiKapat()
        assertEquals(1, d.kutu.bekleyenDosyaSayisi())
        val kayit = ArrayList<LongArray>()
        val g = olcumluGonderici(700, kayit)
        olcum("a3_kesinti1 basladi")                  // betik bunu görünce .part'ı izler
        val t0 = System.currentTimeMillis()
        val sonuc = g.gonder()
        assertTrue("kesintide hata bekleniyordu, sonuc=$sonuc", sonuc is AktarimDurumu.Hata)
        assertEquals("dosya silinmemeli", 1, d.kutu.bekleyenDosyaSayisi())
        val tamam = kayit.filter { it[3] in 200L..299L }
        val gonderilen = tamam.sumOf { it[1] }
        val toplam = kayit.firstOrNull()?.get(2) ?: 0L
        assertTrue("kesinti aktarim ortasinda olmali: gonderilen=$gonderilen toplam=$toplam", gonderilen in 1 until toplam)
        olcum("a3_kesinti1 sonuc=${(sonuc as AktarimDurumu.Hata).kod} toplam=$toplam kabul_edilen_bayt=$gonderilen parca=${tamam.size} sure_ms=${System.currentTimeMillis() - t0} bekleyen_dosya=1")
    }

    /** Alıcı yeniden açıldı: kaldığı yerden tamamlar (`kismi` = ana makinenin .part boyutu). */
    @Test
    fun a3_kesinti2() {
        val d = ctx.depo
        assertEquals(1, d.kutu.bekleyenDosyaSayisi())
        val kismi = args.getString("kismi")!!.toLong()
        val kayit = ArrayList<LongArray>()
        val t0 = System.currentTimeMillis()
        val sonuc = olcumluGonderici(0, kayit).gonder()
        assertEquals(AktarimDurumu.Tamam(1, 110), sonuc)
        assertEquals(0, d.kutu.bekleyenDosyaSayisi())
        val ilk = kayit.first()
        val toplam = ilk[2]
        val gonderilen = kayit.filter { it[3] in 200L..299L }.sumOf { it[1] }
        assertTrue("devam sifirdan baslamamali (ilk bas=${ilk[0]})", ilk[0] > 0)
        assertTrue("devam ofseti PC'deki .part boyutundan kucuk: ${ilk[0]} < $kismi", ilk[0] >= kismi)
        assertEquals("gonderilen bayt = toplam - ofset", toplam - ilk[0], gonderilen)
        assertTrue(gonderilen < toplam)
        olcum("a3_kesinti2 devam_ofseti=${ilk[0]} pc_part=$kismi toplam=$toplam bu_turda_gonderilen=$gonderilen tekrar_gonderilmeyen=${ilk[0]} sure_ms=${System.currentTimeMillis() - t0} bekleyen=0")
    }

    /** İkinci "gönder": 0 dosya. Ayrıca aynı dosya ve aynı kayıtlar PC'ye yeniden verilir: yeni olay doğmamalı. */
    @Test
    fun a4_tekrar() {
        val d = ctx.depo
        val sonuc = d.gonderici.gonder()
        assertEquals("ikinci gonder", AktarimDurumu.Tamam(0, 0), sonuc)
        assertEquals(0, d.kutu.bekleyenDosyaSayisi())

        val anahtar = requireNotNull(d.eslesme.anahtar())
        val b = HttpsBaglanti(d.eslesme.adresler().first(), d.eslesme.port(), requireNotNull(d.eslesme.parmakIzi()))
        val kopyalar = File(dizin, "kopya").listFiles { f -> f.name.endsWith(".jsonl") }!!.sortedBy { it.name }
        assertEquals(3, kopyalar.size)
        // (a) aynı dosya: HEAD `var`, PUT 200 `var` (alıcı baytı yeniden yazmaz)
        for (f in kopyalar) {
            val id = f.name.removeSuffix(".jsonl")
            val h = b.head(d.cihazId, id, anahtar)
            assertEquals("HEAD $id", "var", h.baslik("x-durum"))
            val icerik = f.readBytes()
            val y = b.put(d.cihazId, id, anahtar, 0, icerik.size.toLong(), icerik.sha256Hex(), icerik)
            assertEquals("PUT $id", 200, y.kod)
            assertEquals("var", y.baslik("x-durum"))
        }
        // (b) aynı KAYITLAR başka dosya kimliğiyle: PC kabul eder, içe alma 0 yeni olay üretmeli (host dogrula denetler)
        val ilk = kopyalar.first()
        val eskiId = ilk.name.removeSuffix(".jsonl")
        val yeniId = UUID.randomUUID().toString()
        val yeni = String(ilk.readBytes(), Charsets.UTF_8).replace(eskiId, yeniId).toByteArray(Charsets.UTF_8)
        val y = b.put(d.cihazId, yeniId, anahtar, 0, yeni.size.toLong(), yeni.sha256Hex(), yeni)
        assertEquals("ayni kayitlar yeni dosya olarak", 201, y.kod)
        olcum("a4_tekrar ikinci_gonder_dosya=0 ayni_dosya_put=200/var x3 ayni_kayitlar_yeni_dosya_kod=${y.kod} yeni_dosya=$yeniId")
    }
}
