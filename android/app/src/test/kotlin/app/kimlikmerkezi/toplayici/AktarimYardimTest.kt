package app.kimlikmerkezi.toplayici

import app.kimlikmerkezi.toplayici.aktarim.AdresSuzgeci
import app.kimlikmerkezi.toplayici.aktarim.Bulma
import app.kimlikmerkezi.toplayici.aktarim.ElleAktarim
import app.kimlikmerkezi.toplayici.aktarim.EslesmeDeposu
import app.kimlikmerkezi.toplayici.aktarim.EslesmeKodu
import app.kimlikmerkezi.toplayici.aktarim.QrCozucu
import app.kimlikmerkezi.toplayici.aktarim.SabitGuvenYoneticisi
import app.kimlikmerkezi.toplayici.aktarim.SertifikaUyusmadi
import app.kimlikmerkezi.toplayici.aktarim.sha256Hex
import app.kimlikmerkezi.toplayici.giden.AesGcmSifreleyici
import app.kimlikmerkezi.toplayici.topla.BellekDepolama
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.security.KeyStore
import java.security.cert.X509Certificate
import java.util.Base64
import java.util.zip.ZipInputStream
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class AktarimYardimTest {
    private val pin = "ab".repeat(32)

    private fun kod(json: String, dolgulu: Boolean = false): String {
        val e = if (dolgulu) Base64.getUrlEncoder() else Base64.getUrlEncoder().withoutPadding()
        return "km1:" + e.encodeToString(json.toByteArray())
    }

    private val gecerli = """{"a":["192.168.1.20","8.8.8.8","pc.local"],"p":47821,"f":"$pin","k":"gizli","n":"EV-PC"}"""

    @Test
    fun kodCozmeDolguluVeDolgusuz() {
        for (d in listOf(false, true)) {
            val k = EslesmeKodu.coz(kod(gecerli, d))!!
            assertEquals(listOf("192.168.1.20"), k.adresler) // yerel olmayanlar atılır
            assertEquals(47821, k.port); assertEquals(pin, k.parmakIzi); assertEquals("gizli", k.gizli); assertEquals("EV-PC", k.pcAdi)
        }
        assertNotNull(EslesmeKodu.coz("  KM1:" + kod(gecerli).drop(4).chunked(10).joinToString("\n") + "  "))
    }

    @Test
    fun bozukKodlarReddedilir() {
        assertNull(EslesmeKodu.coz(""))
        assertNull(EslesmeKodu.coz("km2:abc"))
        assertNull(EslesmeKodu.coz("km1:!!!bozuk!!!"))
        assertNull(EslesmeKodu.coz(kod("{}")))
        assertNull(EslesmeKodu.coz(kod("""{"a":["8.8.8.8"],"p":1,"f":"$pin","k":"x","n":"p"}"""))) // yerel adres yok
        assertNull(EslesmeKodu.coz(kod("""{"a":["10.0.0.1"],"p":70000,"f":"$pin","k":"x","n":"p"}""")))
        assertNull(EslesmeKodu.coz(kod("""{"a":["10.0.0.1"],"p":1,"f":"abc","k":"x","n":"p"}""")))
        assertNull(EslesmeKodu.coz(kod("""{"a":["10.0.0.1"],"p":1,"f":"$pin","k":"","n":"p"}""")))
        assertNull(EslesmeKodu.coz(kod("[1,2]")))
    }

    @Test
    fun adresSuzgeci() {
        for (a in listOf("10.0.0.1", "10.255.255.255", "172.16.0.1", "172.31.255.255", "192.168.0.1", "169.254.10.10")) assertTrue(AdresSuzgeci.yerelMi(a), a)
        for (a in listOf("8.8.8.8", "172.15.0.1", "172.32.0.1", "192.169.0.1", "11.0.0.1", "pc.local", "fe80::1", "256.1.1.1", "192.168.1", "", "192.168.1.1:80", "127.0.0.1", "0.0.0.0")) assertFalse(AdresSuzgeci.yerelMi(a), a)
        AdresSuzgeci.testLoopback = true
        try { assertTrue(AdresSuzgeci.yerelMi("127.0.0.1")) } finally { AdresSuzgeci.testLoopback = false }
        assertFalse(AdresSuzgeci.yerelMi("127.0.0.1"))
    }

    @Test
    fun udpIletisi() {
        assertEquals("KM1?abababababababab", String(Bulma.istek(pin.uppercase())))
        assertEquals(47821, Bulma.yanit("KM1!47821".toByteArray()))
        assertEquals(47821, Bulma.yanit("KM1!47821\n".toByteArray()))
        assertNull(Bulma.yanit("KM1!".toByteArray())); assertNull(Bulma.yanit("KM1!0".toByteArray()))
        assertNull(Bulma.yanit("KM1!99999".toByteArray())); assertNull(Bulma.yanit("KM1?abab".toByteArray())); assertNull(Bulma.yanit("x".toByteArray()))
        assertEquals(47822, Bulma.PORT)
    }

    @Test
    fun parmakIziKarsilastirma() {
        val ks = KeyStore.getInstance("PKCS12").apply { AktarimYardimTest::class.java.getResourceAsStream("/test_sunucu_YALNIZ_TEST.p12")!!.use { load(it, "test1234".toCharArray()) } }
        val c = ks.getCertificate("test") as X509Certificate
        val gercek = c.encoded.sha256Hex()
        SabitGuvenYoneticisi(gercek).checkServerTrusted(arrayOf(c), "RSA")
        SabitGuvenYoneticisi(gercek.uppercase()).checkServerTrusted(arrayOf(c), "RSA")
        val yanlis = (if (gercek[0] == '0') "1" else "0") + gercek.drop(1)
        assertFailsWith<SertifikaUyusmadi> { SabitGuvenYoneticisi(yanlis).checkServerTrusted(arrayOf(c), "RSA") }
        assertFailsWith<SertifikaUyusmadi> { SabitGuvenYoneticisi(gercek).checkServerTrusted(emptyArray(), "RSA") }
        assertEquals(0, SabitGuvenYoneticisi(gercek).acceptedIssuers.size)
    }

    private fun qrParlaklik(metin: String, boyut: Int, adim: Int): ByteArray {
        val m = QRCodeWriter().encode(metin, BarcodeFormat.QR_CODE, boyut, boyut)
        val y = ByteArray(adim * boyut) { 255.toByte() }
        for (r in 0 until boyut) for (c in 0 until boyut) y[r * adim + c] = if (m.get(c, r)) 0 else 255.toByte()
        return y
    }

    @Test
    fun qrCozucu() {
        val metin = kod(gecerli)
        assertEquals(metin, QrCozucu.coz(qrParlaklik(metin, 400, 400), 400, 400))
        assertEquals(metin, QrCozucu.coz(qrParlaklik(metin, 400, 416), 400, 400, 416)) // satır dolgusu (rowStride)
        assertNull(QrCozucu.coz(ByteArray(200 * 200) { 255.toByte() }, 200, 200))
    }

    @Test
    fun eslesmeDeposuAnahtariSifreliTutar() {
        val d = BellekDepolama()
        val e = EslesmeDeposu(d, AesGcmSifreleyici(TestYardim.ANAHTAR))
        assertFalse(e.eslesmis())
        val anahtar = "cd".repeat(32)
        e.kaydet(EslesmeKodu.coz(kod(gecerli))!!, anahtar)
        assertTrue(e.eslesmis())
        assertEquals(anahtar, e.anahtar())
        assertFalse(d.metin(EslesmeDeposu.ANAHTAR)!!.contains(anahtar))
        assertEquals(listOf("192.168.1.20"), e.adresler())
        e.adresKaydet("10.0.0.5")
        assertEquals(listOf("10.0.0.5", "192.168.1.20"), e.adresler())
        e.kaldir()
        assertFalse(e.eslesmis()); assertNull(e.anahtar()); assertNull(e.parmakIzi())
    }

    @Test
    fun elleAktarimZipVeSilme() {
        val ku = TestYardim.Kurulum()
        val k = ku.ac()
        k.kayitEkle("not.hizli", "notlar", "bir"); k.acikDosyayiKapat()
        k.kayitEkle("not.hizli", "notlar", "iki")
        val cikti = ByteArrayOutputStream()
        val idler = ElleAktarim.zipYaz(k, cikti)
        assertEquals(2, idler.size)
        assertEquals(2, k.bekleyenDosyaSayisi()) // yazmak silmez
        val girdiler = HashMap<String, String>()
        ZipInputStream(ByteArrayInputStream(cikti.toByteArray())).use { z ->
            while (true) { val e = z.nextEntry ?: break; girdiler[e.name] = z.readBytes().toString(Charsets.UTF_8) }
        }
        assertEquals(idler.map { "$it.jsonl" }.toSet(), girdiler.keys)
        girdiler.values.forEach { TestYardim.bicimiDogrula(it) }
        assertContentEquals(k.dosyayiOku(idler[0]).readBytes(), girdiler["${idler[0]}.jsonl"]!!.toByteArray())
        ElleAktarim.sil(k, idler)
        assertEquals(0, k.bekleyenKayitSayisi())
    }
}
