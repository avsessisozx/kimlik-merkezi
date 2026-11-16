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
        repeat(40) { z.not("p".repeat(60_000)) }
        val toplam = z.dosyalar().single().let { z.icerik(it.dosyaId).size }
        assertEquals(AktarimDurumu.Tamam(1, 40), z.g.gonder())
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

    // ---- B ----
    @Test
    fun tamBoyutluAmaTamamlanmamisSunucuDosyasiSonsuzDongudenKacinir() {
        val z = Duzen()
        z.not("a".repeat(500))
        val id = z.dosyalar().single().dosyaId
        val tum = z.icerik(id)
        z.m.kismi[id] = java.io.ByteArrayOutputStream().also { it.write(tum) } // HEAD: kismi, X-Alinan == toplam
        assertEquals(AktarimDurumu.Hata("pc_tamamlayamadi"), z.g.gonder())
        assertEquals(1, z.kutu.bekleyenDosyaSayisi()) // silinmedi
        assertEquals(0, z.g.reddedilenSayisi()) // kalıcı ret işaretlenmedi
        assertEquals(0, z.m.putSayisi.get())
    }

    // ---- D ----
    @Test
    fun kayitliAdresteSertifikaUyusmazligiOnceUdpSonraSertifika() {
        val uyusmaz = BaglantiUretici { a, _ -> if (a == "192.168.1.2") throw SSLHandshakeException("x").initCause(SertifikaUyusmadi()) as SSLHandshakeException else throw IOException() }
        val z = Duzen(uretici = { uyusmaz }, bulucu = { null })
        z.not("a")
        assertEquals(AktarimDurumu.Hata("sertifika"), z.g.gonder()) // uyuşmazlık görüldü, doğru PC bulunamadı
        // UDP doğru PC'yi bulursa başarılı olur
        val z2 = Duzen(
            uretici = { m -> BaglantiUretici { a, _ -> if (a == "192.168.1.2") throw SSLHandshakeException("x").initCause(SertifikaUyusmadi()) as SSLHandshakeException else BellekBaglanti(m) } },
            bulucu = { "192.168.1.9" to 47821 },
        )
        z2.not("a")
        assertEquals(AktarimDurumu.Tamam(1, 1), z2.g.gonder())
        // yalnızca ulaşılamayan adres: sertifika DEĞİL ulasilamadi
        val z3 = Duzen(uretici = { BaglantiUretici { _, _ -> throw IOException() } })
        z3.not("a")
        assertEquals(AktarimDurumu.Hata("ulasilamadi"), z3.g.gonder())
    }

    // ---- E ----
    @Test
    fun yokDurumluYirmiIkiYuzYirmiIkiBirKezBastanDenenir() {
        val z = Duzen(parca = 200)
        z.not("e".repeat(700))
        val id = z.dosyalar().single().dosyaId
        z.m.yok422.set(1)
        assertEquals(AktarimDurumu.Tamam(1, 1), z.g.gonder())
        assertEquals(0, z.g.reddedilenSayisi())
        assertTrue(z.m.tamamlanan.containsKey(id))
        // ikinci kez de 422/yok gelirse kalıcı ret
        val z2 = Duzen(parca = 200)
        z2.not("e".repeat(700))
        z2.m.yok422.set(2)
        assertEquals(AktarimDurumu.Hata("reddedildi"), z2.g.gonder())
        assertEquals(1, z2.g.reddedilenSayisi())
        assertEquals(1, z2.kutu.bekleyenDosyaSayisi())
    }

    // ---- F ----
    @Test
    fun eslesmeKalkincaRetlerTemizlenirVeGeriCagriCalisir() {
        val z = Duzen()
        z.not("a")
        z.m.zorla422 = true
        z.g.gonder()
        assertEquals(1, z.g.reddedilenSayisi())
        var iptal = 0
        z.eslesme.kaldirinca = { iptal++ }
        z.eslesme.kaldir()
        assertEquals(0, z.g.reddedilenSayisi())
        assertEquals(1, iptal)
    }

    // ---- H ----
    @Test
    fun durdurulunca_temizCikis_dosyaSilinmez() {
        val z = Duzen(parca = 100)
        z.not("d".repeat(1000))
        var kontrol = 0
        assertEquals(AktarimDurumu.Hata("durduruldu"), z.g.gonder { ++kontrol > 4 })
        assertEquals(1, z.kutu.bekleyenDosyaSayisi())
        assertTrue(z.m.putSayisi.get() in 1..4)
        // sonra devam eder
        assertEquals(AktarimDurumu.Tamam(1, 1), z.g.gonder())
    }

    // ---- K, L ----
    @Test
    fun toStringGizliAlanYazmazVeEslestirmeAdiBosModeldeVarsayilan() {
        val k = EslesmeKodu(listOf("192.168.1.2"), 47821, pin, "COK-GIZLI-KOD", "EV-PC")
        assertTrue(!k.toString().contains("COK-GIZLI-KOD") && !k.toString().contains(pin))
        val z = Duzen()
        val e = app.kimlikmerkezi.toplayici.aktarim.Eslestirici({ BellekBaglanti.uretici(z.m) }, EslesmeDeposu(BellekDepolama(), AesGcmSifreleyici(TestYardim.ANAHTAR)))
        assertEquals(app.kimlikmerkezi.toplayici.aktarim.EslesmeSonucu.Tamam, e.eslestir(EslesmeKodu(listOf("192.168.1.2"), 1, pin, z.m.eslesmeKodu, "PC"), TestYardim.CIHAZ.cihazId, "  "))
        assertTrue(z.m.sonEslestirGovde!!.contains("\"ad\":\"Android cihaz\""))
        val z2 = Duzen(); z2.m.eslestir400 = true
        val e2 = app.kimlikmerkezi.toplayici.aktarim.Eslestirici({ BellekBaglanti.uretici(z2.m) }, EslesmeDeposu(BellekDepolama(), AesGcmSifreleyici(TestYardim.ANAHTAR)))
        assertEquals(app.kimlikmerkezi.toplayici.aktarim.EslesmeSonucu.IstekHatali, e2.eslestir(EslesmeKodu(listOf("192.168.1.2"), 1, pin, "x", "PC"), TestYardim.CIHAZ.cihazId, "M"))
    }
}
