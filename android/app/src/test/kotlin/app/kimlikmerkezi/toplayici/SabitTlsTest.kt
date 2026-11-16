package app.kimlikmerkezi.toplayici

import app.kimlikmerkezi.toplayici.aktarim.AktarimDurumu
import app.kimlikmerkezi.toplayici.aktarim.AdresSuzgeci
import app.kimlikmerkezi.toplayici.aktarim.BaglantiUretici
import app.kimlikmerkezi.toplayici.aktarim.EslesmeDeposu
import app.kimlikmerkezi.toplayici.aktarim.EslesmeKodu
import app.kimlikmerkezi.toplayici.aktarim.Eslestirici
import app.kimlikmerkezi.toplayici.aktarim.EslesmeSonucu
import app.kimlikmerkezi.toplayici.aktarim.Gonderici
import app.kimlikmerkezi.toplayici.aktarim.HttpsBaglanti
import app.kimlikmerkezi.toplayici.aktarim.sertifikaHatasiMi
import app.kimlikmerkezi.toplayici.aktarim.sha256Hex
import app.kimlikmerkezi.toplayici.giden.AesGcmSifreleyici
import app.kimlikmerkezi.toplayici.topla.BellekDepolama
import org.junit.After
import org.junit.Before
import java.net.ServerSocket
import java.util.concurrent.atomic.AtomicReference
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** GERÇEK TLS: JDK TLS yığını + depodaki YALNIZ-TEST sertifikası (127.0.0.1, ağ dışına çıkmaz). */
class SabitTlsTest {
    private val sunucu = SahteSunucu()

    @Before fun ac() { AdresSuzgeci.testLoopback = true }
    @After fun kapat() { AdresSuzgeci.testLoopback = false; sunucu.close() }

    private fun kod(pin: String = sunucu.parmakIzi) = EslesmeKodu(listOf("127.0.0.1"), sunucu.port, pin, sunucu.mantik.eslesmeKodu, "TEST-PC")

    @Test
    fun dogruParmakIziylePasifTamAkis() {
        val b = HttpsBaglanti("127.0.0.1", sunucu.port, sunucu.parmakIzi)
        val y = b.durum()
        assertEquals(200, y.kod)
        assertEquals("""{"protokol":1}""", String(y.govde))
        // eşleştirme
        val d = BellekDepolama()
        val e = EslesmeDeposu(d, AesGcmSifreleyici(TestYardim.ANAHTAR))
        assertEquals(EslesmeSonucu.Tamam, Eslestirici({ pin -> BaglantiUretici { a, p -> HttpsBaglanti(a, p, pin) } }, e).eslestir(kod(), TestYardim.CIHAZ.cihazId, "SENTETIK"))
        assertEquals(sunucu.mantik.anahtar, e.anahtar())
        // aynı kod ikinci kez kullanılamaz
        assertEquals(EslesmeSonucu.KodGecersiz, Eslestirici({ pin -> BaglantiUretici { a, p -> HttpsBaglanti(a, p, pin) } }, EslesmeDeposu(BellekDepolama(), AesGcmSifreleyici(TestYardim.ANAHTAR))).eslestir(kod(), TestYardim.CIHAZ.cihazId, "x"))
        // gönderim (1 MiB üstü, çok parçalı) gerçek TLS üzerinden
        val ku = TestYardim.Kurulum()
        val kutu = ku.ac()
        repeat(30) { kutu.kayitEkle("not.hizli", "notlar", "t".repeat(60_000)) }
        val g = Gonderici(kutu, e, d, ku.gunluk, BaglantiUretici { a, p -> HttpsBaglanti(a, p, e.parmakIzi()!!) }, { TestYardim.CIHAZ.cihazId }, bekle = {}, bulucu = { null })
        assertEquals(AktarimDurumu.Tamam(1, 30), g.gonder())
        assertEquals(0, kutu.bekleyenKayitSayisi())
        assertEquals(1, sunucu.mantik.tamamlanan.size)
        assertTrue(sunucu.mantik.putBoyutlari.size >= 2 && sunucu.mantik.putBoyutlari.all { it <= 1024 * 1024 })
    }

    @Test
    fun yanlisParmakIziBaglantiKurulmazIstekUlasmaz() {
        val yanlis = "0".repeat(64)
        val b = HttpsBaglanti("127.0.0.1", sunucu.port, yanlis)
        val hata = assertFailsWith<Exception> { b.durum() }
        assertTrue(hata.sertifikaHatasiMi(), "sertifika hatası beklenirdi: $hata")
        assertEquals(0, sunucu.mantik.istekSayisi.get())
        // Eşleştirme de reddedilir, anahtar yazılmaz
        val e = EslesmeDeposu(BellekDepolama(), AesGcmSifreleyici(TestYardim.ANAHTAR))
        assertEquals(EslesmeSonucu.SertifikaUyusmadi, Eslestirici({ pin -> BaglantiUretici { a, p -> HttpsBaglanti(a, p, pin) } }, e).eslestir(kod(yanlis), TestYardim.CIHAZ.cihazId, "x"))
        assertFalse(e.eslesmis())
        // Gönderici: "sertifika" hatası, dosya durur
        val ku = TestYardim.Kurulum(); val kutu = ku.ac(); kutu.kayitEkle("not.hizli", "notlar", "a")
        val d = BellekDepolama(); val e2 = EslesmeDeposu(d, AesGcmSifreleyici(TestYardim.ANAHTAR))
        e2.kaydet(kod(yanlis), sunucu.mantik.anahtar)
        val g = Gonderici(kutu, e2, d, ku.gunluk, BaglantiUretici { a, p -> HttpsBaglanti(a, p, e2.parmakIzi()!!) }, { TestYardim.CIHAZ.cihazId }, bekle = {}, bulucu = { null })
        assertEquals(AktarimDurumu.Hata("sertifika"), g.gonder())
        assertEquals(1, kutu.bekleyenDosyaSayisi())
        assertEquals(0, sunucu.mantik.istekSayisi.get())
    }

    @Test
    fun duzHttpyeGidilmezVeYerelOlmayanAdresReddedilir() {
        val gelen = AtomicReference(ByteArray(0))
        ServerSocket(0, 5, java.net.InetAddress.getByName("127.0.0.1")).use { duz ->
            val t = Thread {
                try {
                    duz.accept().use { s ->
                        s.soTimeout = 1500
                        val tampon = ByteArray(4096)
                        val n = try { s.getInputStream().read(tampon) } catch (e: Exception) { -1 }
                        if (n > 0) gelen.set(tampon.copyOf(n))
                    }
                } catch (_: Exception) { }
            }.also { it.start() }
            assertFailsWith<Exception> { HttpsBaglanti("127.0.0.1", duz.localPort, sunucu.parmakIzi).durum() }
            t.join(5000)
        }
        val s = String(gelen.get(), Charsets.ISO_8859_1)
        assertFalse(s.contains("/durum") || s.contains("HTTP/1"), "düz HTTP isteği sızdı")
        // Yalnız TLS ClientHello (0x16) gitmiş olabilir
        assertTrue(gelen.get().isEmpty() || gelen.get()[0] == 0x16.toByte())
        AdresSuzgeci.testLoopback = false
        assertFailsWith<IllegalArgumentException> { HttpsBaglanti("127.0.0.1", sunucu.port, sunucu.parmakIzi) }
        assertFailsWith<IllegalArgumentException> { HttpsBaglanti("example.com", 443, sunucu.parmakIzi) }
    }

    private fun gonderici(kayit: Int): Triple<app.kimlikmerkezi.toplayici.giden.GidenKutusu, Gonderici, EslesmeDeposu> {
        val ku = TestYardim.Kurulum(); val kutu = ku.ac()
        repeat(kayit) { kutu.kayitEkle("not.hizli", "notlar", "c".repeat(60_000)) }
        val d = BellekDepolama(); val e = EslesmeDeposu(d, AesGcmSifreleyici(TestYardim.ANAHTAR))
        e.kaydet(kod(), sunucu.mantik.anahtar)
        return Triple(kutu, Gonderici(kutu, e, d, ku.gunluk, BaglantiUretici { a, p -> HttpsBaglanti(a, p, e.parmakIzi()!!) }, { TestYardim.CIHAZ.cihazId }, bekle = {}, bulucu = { null }), e)
    }

    /** C: PC gövdeyi okumadan 409 dönüp kapatır; istemci ya yanıtı okur ya HEAD ile durumu sorar; sonuçta tamamlanır. */
    @Test
    fun gövdeOkunmadanKapanan409DaTamamlanir() {
        val (kutu, g, _) = gonderici(26)
        sunucu.govdeOkumadanKod = 409
        sunucu.govdeOkumadanKapat.set(2)
        assertEquals(AktarimDurumu.Tamam(1, 26), g.gonder())
        assertEquals(0, kutu.bekleyenDosyaSayisi())
        assertEquals(1, sunucu.mantik.tamamlanan.size)
        assertEquals(0, sunucu.govdeOkumadanKapat.get())
    }

    /** C: PC yer yok (507) der ve gövdeyi okumadan kapatır: "ulaşılamadı" değil "bekle"; dosya silinmez. */
    @Test
    fun govdeOkunmadanKapananYerYok507BekleOlarakGorunur() {
        val (kutu, g, _) = gonderici(26)
        sunucu.govdeOkumadanKod = 507
        sunucu.govdeOkumadanKapat.set(100)
        sunucu.mantik.putSonrasiHeadKodu = 507 // PC bu durumda HEAD'e de aynı yanıtı verir
        assertEquals(AktarimDurumu.Hata("bekle"), g.gonder())
        assertEquals(1, kutu.bekleyenDosyaSayisi())
        assertEquals(0, sunucu.mantik.tamamlanan.size)
    }
}
