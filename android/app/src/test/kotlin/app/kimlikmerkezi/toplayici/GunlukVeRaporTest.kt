package app.kimlikmerkezi.toplayici

import app.kimlikmerkezi.toplayici.gunluk.Gunluk
import app.kimlikmerkezi.toplayici.gunluk.HataRaporu
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class GunlukVeRaporTest {
    @Test
    fun halkaTamponSinirliVeKalici() {
        val d = TestYardim.gecici()
        val g = Gunluk(d, bellekSiniri = 10)
        repeat(50) { g.bilgi("t", "satir $it") }
        assertEquals(10, g.sonSatirlar(50).size)
        assertTrue(g.sonSatirlar(1)[0].endsWith("satir 49"))
        val g2 = Gunluk(d, bellekSiniri = 10) // yeniden açılış: dosyadan
        assertTrue(g2.sonSatirlar(1)[0].endsWith("satir 49"))
        assertTrue(java.io.File(d, "gunluk.txt").readLines().size <= 20)
    }

    @Test
    fun sonAdimVeSonHataKaliciDir() {
        val d = TestYardim.gecici()
        val g = Gunluk(d)
        g.adim("hızlı not")
        g.hata("x", IllegalStateException("bozuk\nsatir"), cokme = true)
        val g2 = Gunluk(d)
        assertEquals("hızlı not", g2.sonAdim())
        val h = g2.sonHata()!!
        assertEquals("java.lang.IllegalStateException", h.tur)
        assertEquals("-", h.kod)
        assertTrue(h.cokme)
    }

    @Test
    fun raporKayitMetniIcermez() {
        val ku = TestYardim.Kurulum(gunluk = Gunluk(TestYardim.gecici()))
        val k = ku.ac()
        val gizli = "BU-NOT-GIZLIDIR-4711"
        k.kayitEkle("not.hizli", "notlar", gizli)
        k.kayitEkle("paylasim.link", "notlar", "https://gizli.test/$gizli")
        runCatching { k.kayitEkle("yok", "notlar", gizli) }.onFailure { ku.gunluk.hata("not", it) }
        ku.ac() // açılış günlüğü
        val r = HataRaporu.olustur(
            HataRaporu.Girdi(
                "0.2.0", "12", 31, "Uretici", "Model", ku.gunluk.sonAdim(), ku.gunluk.sonHata(),
                ku.gunluk.sonSatirlar(50), k.bekleyenKayitSayisi(), k.bekleyenDosyaSayisi(),
            ),
        )
        assertFalse(r.contains(gizli))
        assertFalse(r.contains("gizli.test"))
        assertTrue(r.contains("Uygulama sürümü: 0.2.0"))
        assertTrue(r.contains("API 31"))
        assertTrue(r.contains("Uretici Model"))
        assertTrue(r.contains("2 kayıt, 1 dosya"))
        assertNotNull(ku.gunluk.sonHata())
    }

    @Test
    fun hataIletisiRaporaGirmez() {
        val d = TestYardim.gecici()
        val g = Gunluk(d)
        g.hata("x", IllegalStateException("ICERIK-SIZINTISI-77"))
        g.hata("y", RuntimeException("ICERIK-SIZINTISI-78"), cokme = true)
        val sabit = app.kimlikmerkezi.toplayici.giden.GidenKutusuHatasi("yazilamadi")
        g.hata("z", sabit)
        for (gunluk in listOf(g, Gunluk(d))) {
            val r = HataRaporu.olustur(
                HataRaporu.Girdi("0.2.0", "12", 31, "U", "M", null, gunluk.sonHata(), gunluk.sonSatirlar(50), 0, 0),
            )
            assertFalse(r.contains("ICERIK-SIZINTISI"))
            assertTrue(r.contains("GidenKutusuHatasi [kod: yazilamadi]"))
        }
        assertFalse(java.io.File(d, "gunluk.txt").readText().contains("ICERIK-SIZINTISI"))
        assertFalse(java.io.File(d, "son_hata.txt").readText().contains("ICERIK-SIZINTISI"))
        assertTrue(g.sonSatirlar(50).any { it.contains("java.lang.IllegalStateException -") })
    }

    @Test
    fun raporSonElliSatirlaSinirli() {
        val g = Gunluk(null)
        repeat(120) { g.bilgi("t", "s$it") }
        val r = HataRaporu.olustur(HataRaporu.Girdi("0.2.0", "12", 31, "U", "M", null, null, g.sonSatirlar(80), 0, 0))
        assertEquals(50, r.lines().count { it.contains(" BILGI t s") })
        assertTrue(r.contains("Son hata: yok"))
    }

    @Test
    fun raporDogrulamaDurumuSatiriVar() {
        val r = HataRaporu.olustur(
            HataRaporu.Girdi("0.2.0", "12", 31, "U", "M", null, null, emptyList(), 5, 2, bozukDosya = 1, eslesme = true, sonBasariMs = 1_700_000_000_000),
        )
        assertTrue(r.contains("Doğrulama durumu: giden kutusu 2 dosya, 1 bozuk; son başarılı gönderim: 2023-11-14T22:13:20Z; eşleşme: var"))
        assertTrue(HataRaporu.olustur(HataRaporu.Girdi("0.2.0", "12", 31, "U", "M", null, null, emptyList(), 0, 0)).contains("son başarılı gönderim: yok"))
    }
}
