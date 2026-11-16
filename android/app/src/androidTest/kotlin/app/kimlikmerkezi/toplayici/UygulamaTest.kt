package app.kimlikmerkezi.toplayici

import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.onNodeWithText
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.kimlikmerkezi.toplayici.giden.CihazBilgisi
import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.giden.KeystoreAnahtar
import app.kimlikmerkezi.toplayici.gunluk.Gunluk
import app.kimlikmerkezi.toplayici.paylasim.PaylasimActivity
import app.kimlikmerkezi.toplayici.ui.MainActivity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.nio.file.Files

@RunWith(AndroidJUnit4::class)
class UygulamaTest {
    @get:Rule
    val kural = createAndroidComposeRule<MainActivity>()

    private val ctx: Context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val depo get() = ctx.depo

    private fun bekle(kosul: () -> Boolean) {
        kural.waitUntil(10_000) { kosul() }
    }

    @Test
    fun uygulamaAcilir() {
        kural.onNodeWithTag("bekleyen_sayac").assertIsDisplayed()
        kural.onNodeWithTag("hizli_not_btn").assertIsDisplayed()
        kural.onNodeWithTag("pc_gonder_btn").assertIsDisplayed()
        kural.onNodeWithText("Önce PC ile eşleştir").assertIsDisplayed()
    }

    @Test
    fun hizliNotEklenirSayacArtar() {
        val once = depo.kutu.bekleyenKayitSayisi()
        kural.onNodeWithTag("hizli_not_btn").performClick()
        kural.onNodeWithTag("not_alani").performTextInput("Deneme notu ${System.nanoTime()}")
        kural.onNodeWithTag("kaydet_btn").performClick()
        bekle { depo.kutu.bekleyenKayitSayisi() == once + 1 }
        kural.onNodeWithTag("bekleyen_sayac").assertIsDisplayed()
        assertEquals("not.hizli", depo.kutu.sonKayitlar(1)[0].tur)
    }

    @Test
    fun paylasimKayitEkler() {
        val once = depo.kutu.bekleyenKayitSayisi()
        val i = Intent(ctx, PaylasimActivity::class.java).apply {
            action = Intent.ACTION_SEND
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, "Bak: https://ornek.test/yazi")
            putExtra(Intent.EXTRA_SUBJECT, "Örnek")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        ActivityScenario.launch<PaylasimActivity>(i).use {
            bekle { depo.kutu.bekleyenKayitSayisi() == once + 1 }
        }
        assertEquals("paylasim.link", depo.kutu.sonKayitlar(1)[0].tur)
    }

    @Test
    fun hataRaporuPanoyaKopyalanirNotMetniYok() {
        val gizli = "PANO-GIZLI-${System.nanoTime()}"
        depo.kutu.kayitEkle("not.hizli", "notlar", gizli)
        kural.onNodeWithTag("ayarlar_btn").performClick()
        kural.onNodeWithTag("hata_raporu_btn").performScrollTo().performClick()
        var metin = ""
        bekle {
            kural.runOnUiThread {
                val pano = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                metin = pano.primaryClip?.getItemAt(0)?.text?.toString() ?: ""
            }
            metin.contains("Uygulama sürümü")
        }
        assertTrue(metin.contains("Android:"))
        assertFalse(metin.contains(gizli))
    }

    @Test
    fun temalarCokmez() {
        kural.onNodeWithTag("ayarlar_btn").performClick()
        for (t in listOf("tema_koyu", "tema_acik", "tema_sistem")) {
            kural.onNodeWithTag(t).performClick()
            kural.waitForIdle()
            kural.onNodeWithTag("hata_raporu_btn").performScrollTo().assertIsDisplayed()
        }
        kural.onNodeWithTag("hakkinda_btn").performScrollTo().performClick()
        kural.onNodeWithTag("surum").assertIsDisplayed()
    }
}

@RunWith(AndroidJUnit4::class)
class KeystoreGidenKutusuTest {
    private val ctx: Context get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun ac(dizin: File) = GidenKutusu(
        dizin, KeystoreAnahtar.sifreleyici(),
        CihazBilgisi("3f2b8c1e-5a47-4d9e-8b36-1c7e0a9d4f52", "0.2.0", 31, "TEST"), Gunluk(null),
    )

    @Test
    fun sifreliYazilirOkunurDiskteDuzMetinYoktur() {
        val dizin = Files.createTempDirectory(ctx.cacheDir.toPath(), "giden").toFile()
        val gizli = "KEYSTORE-GIZLI-NOT-98765"
        val k = ac(dizin)
        k.kayitEkle("not.hizli", "notlar", gizli)
        val id = k.acikDosyayiKapat()!!
        val ham = String(dizin.listFiles()!!.single().readBytes(), Charsets.ISO_8859_1)
        assertFalse(ham.contains(gizli))
        assertFalse(ham.contains("not.hizli"))
        val duz = k.dosyayiOku(id).readBytes().toString(Charsets.UTF_8)
        assertTrue(duz.contains(gizli))
        assertTrue(duz.trimEnd().endsWith("\"kayit_sayisi\":1}"))
        dizin.deleteRecursively()
    }

    @Test
    fun yenidenAcilincaKayitlarDurur() {
        val dizin = Files.createTempDirectory(ctx.cacheDir.toPath(), "giden").toFile()
        val k = ac(dizin)
        k.kayitEkle("not.hizli", "notlar", "bir")
        k.kayitEkle("not.hizli", "notlar", "iki")
        val k2 = ac(dizin) // süreç yeniden başlaması: yeni nesne, aynı dosyalar, aynı Keystore anahtarı
        assertEquals(2, k2.bekleyenKayitSayisi())
        assertEquals("iki", k2.sonKayitlar(5)[0].ozet)
        dizin.deleteRecursively()
    }
}
