package app.kimlikmerkezi.toplayici

import app.kimlikmerkezi.toplayici.aktarim.AktarimDurumu
import app.kimlikmerkezi.toplayici.aktarim.BaglantiUretici
import app.kimlikmerkezi.toplayici.aktarim.EslesmeDeposu
import app.kimlikmerkezi.toplayici.aktarim.EslesmeKodu
import app.kimlikmerkezi.toplayici.aktarim.Gonderici
import app.kimlikmerkezi.toplayici.aktarim.PcBaglanti
import app.kimlikmerkezi.toplayici.aktarim.SertifikaUyusmadi
import app.kimlikmerkezi.toplayici.aktarim.Yanit
import app.kimlikmerkezi.toplayici.aktarim.sha256Hex
import app.kimlikmerkezi.toplayici.giden.AesGcmSifreleyici
import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.topla.BellekDepolama
import java.io.IOException
import javax.net.ssl.SSLHandshakeException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class GondericiTest {
    private val pin = "ab".repeat(32)

    /** Belirli sayıda PUT'tan sonra bağlantıyı koparan sarmalayıcı; ayrıca eski (bayat) HEAD yanıtı verebilir. */
    class Sarmal(val ic: PcBaglanti, var kesPutSonrasi: Int = Int.MAX_VALUE, var bayatHead: Boolean = false) : PcBaglanti by ic {
        var put = 0
        override fun put(cihazId: String, dosyaId: String, anahtar: String, bas: Long, toplam: Long, sha: String, parca: ByteArray): Yanit {
            if (put++ >= kesPutSonrasi) throw IOException("kesildi")
            return ic.put(cihazId, dosyaId, anahtar, bas, toplam, sha, parca)
        }
        override fun head(cihazId: String, dosyaId: String, anahtar: String): Yanit =
            if (bayatHead) Yanit(200, mapOf("x-durum" to "yok", "x-alinan" to "0")) else ic.head(cihazId, dosyaId, anahtar)
    }

    inner class Duzen(parca: Int = 1024 * 1024, uretici: ((PcMantik) -> BaglantiUretici)? = null, bulucu: (String) -> Pair<String, Int>? = { null }) {
        val ku = TestYardim.Kurulum()
        val kutu = ku.ac()
        val m = PcMantik()
        val d = BellekDepolama()
        val eslesme = EslesmeDeposu(d, AesGcmSifreleyici(TestYardim.ANAHTAR))
        val beklemeler = ArrayList<Long>()
        val g: Gonderici

        init {
            eslesme.kaydet(EslesmeKodu(listOf("192.168.1.2"), 47821, pin, "k", "PC"), m.anahtar)
            g = Gonderici(
                kutu, eslesme, d, ku.gunluk, (uretici ?: { BellekBaglanti.uretici(it) })(m), { TestYardim.CIHAZ.cihazId },
                bekle = { beklemeler.add(it) }, bulucu = bulucu, parcaBayt = parca,
            )
        }

        fun not(metin: String) = kutu.kayitEkle("not.hizli", "notlar", metin)
        fun dosyalar() = kutu.acikDosyayiKapat().let { kutu.kapatilmisDosyalar() }
        fun icerik(id: String) = kutu.dosyayiOku(id).readBytes()
    }

    @Test
    fun iyiYolHeadPutVarSonraSil() {
        val z = Duzen(parca = 200)
        z.not("a".repeat(500)); z.kutu.acikDosyayiKapat(); z.not("b".repeat(300))
        val ilk = z.kutu.let { z.kutu.acikDosyayiKapat(); it.kapatilmisDosyalar() }
        val icerikler = ilk.associate { it.dosyaId to z.icerik(it.dosyaId) }
        val s = z.g.gonder()
        assertEquals(AktarimDurumu.Tamam(2, 2), s)
        assertEquals(0, z.kutu.bekleyenKayitSayisi())
        assertEquals(2, z.m.tamamlanan.size)
        icerikler.forEach { (id, b) -> assertEquals(b.sha256Hex(), z.m.tamamlanan[id]!!.sha256Hex()) }
        assertTrue(z.g.sonBasariMs() > 0); assertEquals("tamam", z.g.sonKod())
        assertEquals(s, z.g.durum.value)
    }

    @Test
    fun kismiVarsaKaldigiYerdenDevamEderVeVarOlmadanSilmez() {
        val z = Duzen(parca = 300)
        z.not("x".repeat(2000))
        val id = z.dosyalar().single().dosyaId
        val toplam = z.icerik(id).size
        val sarmal = Sarmal(BellekBaglanti(z.m), kesPutSonrasi = 2)
        val g1 = Gonderici(z.kutu, z.eslesme, z.d, z.ku.gunluk, { _, _ -> sarmal }, { TestYardim.CIHAZ.cihazId }, bekle = { z.beklemeler.add(it) }, bulucu = { null }, parcaBayt = 300)
        assertEquals(AktarimDurumu.Hata("ulasilamadi"), g1.gonder())
        assertEquals(listOf(1000L, 2000L, 4000L), z.beklemeler) // üstel bekleme, sınırlı deneme
        assertEquals(1, z.kutu.bekleyenDosyaSayisi()) // var görülmedi: silinmedi
        assertEquals(600, z.m.kismi[id]!!.size())
        val once = z.m.putBoyutlari.size
        assertEquals(AktarimDurumu.Tamam(1, 1), z.g.gonder())
        assertEquals(toplam, z.m.putBoyutlari.sum())
        assertEquals(Math.ceil(toplam / 300.0).toInt(), z.m.putBoyutlari.size)
        assertTrue(z.m.putBoyutlari.size > once)
        assertEquals(0, z.kutu.bekleyenDosyaSayisi())
    }

    @Test
    fun ortadaKesilinceAyniGonderimIcindeToparlar() {
        val z = Duzen(parca = 300)
        z.not("y".repeat(1500))
        z.dosyalar().single()
        z.m.kesilecekPut.set(1) // ilk PUT kesilir, sonrası normal
        assertEquals(AktarimDurumu.Tamam(1, 1), z.g.gonder())
        assertEquals(1, z.beklemeler.size)
        assertEquals(1, z.m.tamamlanan.size)
    }

    @Test
    fun hizalamaIcin409() {
        val z = Duzen(parca = 400)
        z.not("z".repeat(1000))
        val id = z.dosyalar().single().dosyaId
        val icerik = z.icerik(id)
        z.m.kismi[id] = java.io.ByteArrayOutputStream().also { it.write(icerik, 0, 400) }
        val sarmal = Sarmal(BellekBaglanti(z.m), bayatHead = true) // HEAD "yok" der, PC aslında 400 bayt almış
        val g = Gonderici(z.kutu, z.eslesme, z.d, z.ku.gunluk, { _, _ -> sarmal }, { TestYardim.CIHAZ.cihazId }, bekle = {}, bulucu = { null }, parcaBayt = 400)
        assertEquals(AktarimDurumu.Tamam(1, 1), g.gonder())
        assertEquals(icerik.sha256Hex(), z.m.tamamlanan[id]!!.sha256Hex())
    }

    @Test
    fun headVarIseGondermeden_siler() {
        val z = Duzen()
        z.not("a")
        val id = z.dosyalar().single().dosyaId
        z.m.tamamlanan[id] = ByteArray(0) // PC bunu daha önce aldı (bayt sayısına bakılmaz)
        assertEquals(AktarimDurumu.Tamam(1, 1), z.g.gonder())
        assertEquals(0, z.m.putSayisi.get())
        assertEquals(0, z.kutu.bekleyenDosyaSayisi())
    }

    @Test
    fun yetkisiz401DosyalariSilmez() {
        val z = Duzen()
        z.not("a"); z.kutu.acikDosyayiKapat(); z.not("b")
        z.m.zorla401 = true
        assertEquals(AktarimDurumu.Hata("yetkisiz"), z.g.gonder())
        assertEquals(2, z.kutu.bekleyenKayitSayisi())
        assertEquals(0, z.m.tamamlanan.size)
        assertEquals("yetkisiz", z.g.sonKod())
        assertEquals(0L, z.g.sonBasariMs())
    }

    @Test
    fun reddedilen422SilinmezIsaretlenirTekrarDenenmez() {
        val z = Duzen()
        z.not("a")
        z.m.zorla422 = true
        assertEquals(AktarimDurumu.Hata("reddedildi"), z.g.gonder())
        assertEquals(1, z.kutu.bekleyenDosyaSayisi())
        assertEquals(1, z.g.reddedilenSayisi())
        val put = z.m.putSayisi.get()
        z.m.zorla422 = false
        assertEquals(AktarimDurumu.Tamam(0, 0), z.g.gonder()) // reddedilen atlanır
        assertEquals(put, z.m.putSayisi.get())
        assertEquals(1, z.kutu.bekleyenDosyaSayisi())
    }

    @Test
    fun parcaBirMiBiGecmez() {
        val z = Duzen()
        repeat(3) { z.not("p".repeat(850_000)) }
        val toplam = z.dosyalar().single().let { z.icerik(it.dosyaId).size }
        assertEquals(AktarimDurumu.Tamam(1, 3), z.g.gonder())
        assertTrue(z.m.putBoyutlari.all { it <= 1024 * 1024 })
        assertEquals(1024 * 1024, z.m.putBoyutlari.first())
        assertEquals(toplam, z.m.putBoyutlari.sum())
        assertTrue(z.m.putBoyutlari.size >= 3)
    }

    @Test
    fun eslesmeYokVeGonderilecekYok() {
        val z = Duzen()
        z.eslesme.kaldir()
        assertEquals(AktarimDurumu.Hata("eslesme_yok"), z.g.gonder())
        z.eslesme.kaydet(EslesmeKodu(listOf("192.168.1.2"), 1, pin, "k", "PC"), z.m.anahtar)
        assertEquals(AktarimDurumu.Tamam(0, 0), z.g.gonder())
        assertEquals(0, z.m.istekSayisi.get()) // ağa hiç çıkılmadı
    }

    @Test
    fun adresBulmaKayitliOnceSonraUdp() {
        val z = Duzen(
            uretici = { m -> BaglantiUretici { a, _ -> if (a == "192.168.1.2") throw IOException("yok") else BellekBaglanti(m) } },
            bulucu = { p -> assertEquals(pin, p); "192.168.1.9" to 50000 },
        )
        z.not("a")
        assertEquals(AktarimDurumu.Tamam(1, 1), z.g.gonder())
        assertEquals("192.168.1.9", z.eslesme.adresler().first())
        assertEquals(50000, z.eslesme.port())
    }

    @Test
    fun yerelOlmayanAdreseBaglanilmaz() {
        var cagri = 0
        val z = Duzen(uretici = { BaglantiUretici { _, _ -> cagri++; throw IOException() } }, bulucu = { "8.8.8.8" to 47821 })
        z.eslesme.kaydet(EslesmeKodu(listOf("192.168.1.2"), 1, pin, "k", "PC"), z.m.anahtar)
        z.d.yazMetin(EslesmeDeposu.ADRESLER, "8.8.8.8,example.com")
        z.not("a")
        assertEquals(AktarimDurumu.Hata("ulasilamadi"), z.g.gonder())
        assertEquals(0, cagri)
    }

    @Test
    fun sertifikaUyusmazligindaHicbirSeyGonderilmez() {
        val z = Duzen(uretici = { BaglantiUretici { _, _ -> throw SSLHandshakeException("x").initCause(SertifikaUyusmadi()) as SSLHandshakeException } })
        z.not("a")
        assertEquals(AktarimDurumu.Hata("sertifika"), z.g.gonder())
        assertEquals(1, z.kutu.bekleyenDosyaSayisi())
        assertNull(z.m.tamamlanan.values.firstOrNull())
    }
}
