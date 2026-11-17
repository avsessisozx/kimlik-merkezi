package app.kimlikmerkezi.toplayici

import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.topla.AdimKaynagi
import app.kimlikmerkezi.toplayici.topla.AdimToplayici
import app.kimlikmerkezi.toplayici.topla.BellekDepolama
import app.kimlikmerkezi.toplayici.topla.EkranMetniSuzgeci
import app.kimlikmerkezi.toplayici.topla.YerelGecmis
import app.kimlikmerkezi.toplayici.topla.BellekGorulen
import app.kimlikmerkezi.toplayici.topla.IndirilenKaynagi
import app.kimlikmerkezi.toplayici.topla.IndirilenOge
import app.kimlikmerkezi.toplayici.topla.IndirilenToplayici
import app.kimlikmerkezi.toplayici.topla.KonumOkuyucu
import app.kimlikmerkezi.toplayici.topla.KullanimKaynagi
import app.kimlikmerkezi.toplayici.topla.KullanimToplayici
import app.kimlikmerkezi.toplayici.topla.MedyaKaynagi
import app.kimlikmerkezi.toplayici.topla.MedyaOge
import app.kimlikmerkezi.toplayici.topla.MedyaToplayici
import app.kimlikmerkezi.toplayici.topla.MedyaTuru
import app.kimlikmerkezi.toplayici.topla.ToplayiciAyarlari
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.time.LocalDate
import java.time.ZoneId
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

class ToplayicilarTest {
    /** Kutudaki bütün kayıtlar (açık dosya kapatılır). */
    private fun GidenKutusu.tum(): List<JsonObject> {
        acikDosyayiKapat()
        return kapatilmisDosyalar().flatMap { TestYardim.bicimiDogrula(dosyayiOku(it.dosyaId).readBytes().toString(Charsets.UTF_8)) }
    }

    private fun foto(id: Long, eklenme: Long, ad: String = "IMG_$id.jpg", boyut: Long = 1000) =
        MedyaOge(MedyaTuru.FOTO, id, ad, boyut, "image/jpeg", 4000, 3000, null, 1_700_000_000_000, eklenme)

    private fun video(id: Long, eklenme: Long) =
        MedyaOge(MedyaTuru.VIDEO, id, "VID_$id.mp4", 5000, "video/mp4", 1920, 1080, 15_000, null, eklenme)

    /** MediaStore sorgusunun sahte karşılığı: aynı (date_added, _id) imleç anlamı. */
    class SahteMedya(val ogeler: MutableList<MedyaOge>) : MedyaKaynagi {
        override fun sonrasi(tur: MedyaTuru, eklenmeSn: Long, id: Long, sinir: Int) =
            ogeler.filter { it.tur == tur && (it.eklenmeSn > eklenmeSn || (it.eklenmeSn == eklenmeSn && it.id > id)) }
                .sortedWith(compareBy({ it.eklenmeSn }, { it.id })).take(sinir)
    }

    class SahteKonum(val harita: Map<Long, Pair<Double, Double>>) : KonumOkuyucu {
        var cagri = 0
        override fun oku(oge: MedyaOge): Pair<Double, Double>? { cagri++; return harita[oge.id] }
    }

    private val izinliAnahtarlar = setOf("ad", "boyut", "mime", "genislik", "yukseklik", "sure_ms", "cekim_zamani", "medya_id")

    @Test
    fun turKategoriEslemesiAktarimTablosuylaBirebir() {
        val beklenen = mapOf(
            "paylasim.link" to "notlar", "paylasim.metin" to "notlar", "not.hizli" to "notlar",
            "medya.foto" to "medya_meta", "medya.video" to "medya_meta", "medya.konum" to "konum",
            "indirilen.dosya" to "dosyalar", "uygulama.kullanim" to "uygulama",
            "sensor.adim" to "uygulama", "ekran.metin" to "mesaj",
        )
        assertEquals(beklenen, GidenKutusu.KATEGORI)
        assertEquals("medya.foto", MedyaTuru.FOTO.kayitTuru)
        assertEquals("medya.video", MedyaTuru.VIDEO.kayitTuru)
    }

    @Test
    fun medyaArtimliTaramaIkinciKezKayitUretmez() {
        val k = TestYardim.Kurulum().ac()
        val kaynak = SahteMedya(mutableListOf(foto(1, 100), foto(2, 100), foto(3, 101), video(1, 100), video(2, 150)))
        val t = MedyaToplayici(k, kaynak, SahteKonum(emptyMap()), BellekDepolama())
        assertEquals(5, t.taraMedya())
        assertEquals(0, t.taraMedya())
        kaynak.ogeler.add(foto(4, 101)) // aynı saniye, daha büyük _id
        kaynak.ogeler.add(foto(5, 200))
        assertEquals(2, t.taraMedya())
        assertEquals(7, k.bekleyenKayitSayisi())
        val kayitlar = k.tum()
        assertEquals(setOf("medya.foto", "medya.video"), kayitlar.map { it["tur"]!!.jsonPrimitive.content }.toSet())
        assertTrue(kayitlar.all { it["kategori"]!!.jsonPrimitive.content == "medya_meta" })
        val adlar = kayitlar.map { (it["yuk"] as JsonObject)["ad"]!!.jsonPrimitive.content }
        assertEquals(adlar.size, adlar.toSet().size)
    }

    @Test
    fun imlecDepolamadaKalirYeniNesneYenidenUretmez() {
        val k = TestYardim.Kurulum().ac()
        val kaynak = SahteMedya(mutableListOf(foto(1, 100), video(1, 100)))
        val d = BellekDepolama()
        assertEquals(2, MedyaToplayici(k, kaynak, SahteKonum(emptyMap()), d).taraMedya())
        assertEquals(0, MedyaToplayici(k, kaynak, SahteKonum(emptyMap()), d).taraMedya())
    }

    @Test
    fun fotoKaydindaGpsYokVeKonumKapaliykenOkuyucuCagrilmaz() {
        val k = TestYardim.Kurulum().ac()
        val konum = SahteKonum(mapOf(1L to (41.01 to 28.97)))
        val t = MedyaToplayici(k, SahteMedya(mutableListOf(foto(1, 100), video(1, 100))), konum, BellekDepolama())
        t.taraMedya() // konum ayarı kapalı: taraKonum hiç çağrılmaz
        assertEquals(0, konum.cagri)
        val kayitlar = k.tum()
        assertTrue(kayitlar.none { it["tur"]!!.jsonPrimitive.content == "medya.konum" })
        for (r in kayitlar) {
            val yuk = r["yuk"] as JsonObject
            assertTrue(izinliAnahtarlar.containsAll(yuk.keys), "izin dışı alan: ${yuk.keys}")
            assertFalse(yuk.keys.any { it in setOf("enlem", "boylam", "lat", "lon", "konum", "gps") })
        }
    }

    @Test
    fun konumAyriKayitAyriImlecAcCincaEskiFotolarIcinDeUretilir() {
        val k = TestYardim.Kurulum().ac()
        val konum = SahteKonum(mapOf(1L to (41.01 to 28.97), 3L to (-33.5 to 151.2)))
        val d = BellekDepolama()
        val t = MedyaToplayici(k, SahteMedya(mutableListOf(foto(1, 100), foto(2, 101), foto(3, 102))), konum, d)
        t.taraMedya()
        assertEquals(2, t.taraKonum()) // foto 2'nin konumu yok: atlanır
        assertEquals(0, t.taraKonum())
        val kayitlar = k.tum()
        val konumlar = kayitlar.filter { it["tur"]!!.jsonPrimitive.content == "medya.konum" }
        assertEquals(2, konumlar.size)
        for (r in konumlar) {
            assertEquals("konum", r["kategori"]!!.jsonPrimitive.content)
            assertEquals(listOf("enlem", "boylam", "medya_id"), (r["yuk"] as JsonObject).keys.toList())
        }
        // medya_id, foto kaydındakiyle aynı
        val fotoIdler = kayitlar.filter { it["tur"]!!.jsonPrimitive.content == "medya.foto" }
            .map { (it["yuk"] as JsonObject)["medya_id"]!!.jsonPrimitive.content }.toSet()
        assertTrue(konumlar.all { (it["yuk"] as JsonObject)["medya_id"]!!.jsonPrimitive.content in fotoIdler })
    }

    @Test
    fun medyaIdKararliVeAyirt() {
        val a = foto(7, 100, boyut = 1234)
        assertEquals(a.medyaId(), foto(7, 100, ad = "baska-ad.jpg", boyut = 1234).medyaId()) // ad etkilemez
        assertEquals(32, a.medyaId().length)
        assertNotEquals(a.medyaId(), foto(8, 100, boyut = 1234).medyaId())
        assertNotEquals(a.medyaId(), foto(7, 101, boyut = 1234).medyaId())
        assertNotEquals(a.medyaId(), foto(7, 100, boyut = 1235).medyaId())
        assertNotEquals(a.medyaId(), video(7, 100).medyaId())
        assertEquals("a1b2c3d4e5f60718293a4b5c6d7e8f90".length, a.medyaId().length)
    }

    class SahteIndirilen(var liste: List<IndirilenOge>) : IndirilenKaynagi {
        override fun listele() = liste.asSequence()
    }

    @Test
    fun indirilenlerArtimli() {
        val k = TestYardim.Kurulum().ac()
        val kaynak = SahteIndirilen(listOf(IndirilenOge("/a/f.pdf", "f.pdf", 100, "application/pdf", 5), IndirilenOge("/g.zip", "g.zip", 9, "application/zip", 6)))
        val t = IndirilenToplayici(k, kaynak, BellekGorulen())
        assertEquals(2, t.tara())
        assertEquals(0, t.tara())
        kaynak.liste = kaynak.liste + IndirilenOge("/yeni.txt", "yeni.txt", 3, "text/plain", 9)
        assertEquals(1, t.tara())
        val kayitlar = k.tum()
        assertEquals(3, kayitlar.size)
        assertTrue(kayitlar.all { it["tur"]!!.jsonPrimitive.content == "indirilen.dosya" && it["kategori"]!!.jsonPrimitive.content == "dosyalar" })
        assertTrue(kayitlar.all { (it["yuk"] as JsonObject).keys.toList() == listOf("ad", "boyut", "mime") })
    }

    class SahteKullanim(val gunler: MutableList<Pair<Long, Long>> = mutableListOf()) : KullanimKaynagi {
        override fun gunKullanimi(basMs: Long, sonMs: Long): Map<String, Long> {
            gunler.add(basMs to sonMs)
            return mapOf("com.ornek.b" to 2000L, "com.ornek.a" to 1000L, "com.ornek.sifir" to 0L, "app.kimlikmerkezi.toplayici" to 99L)
        }
        override fun ad(paket: String) = if (paket == "com.ornek.a") "Örnek A" else null
    }

    private fun kullanim(k: GidenKutusu, d: BellekDepolama, kaynak: SahteKullanim, bugun: String) = KullanimToplayici(
        k, kaynak, d, bugun = { LocalDate.parse(bugun) }, bolge = { ZoneId.of("Europe/Istanbul") },
        kendiPaket = "app.kimlikmerkezi.toplayici",
    )

    @Test
    fun kullanimYalnizTamamlanmisGunlerIlkAcilista7Gun() {
        val k = TestYardim.Kurulum().ac()
        val d = BellekDepolama()
        val kaynak = SahteKullanim()
        assertEquals(14, kullanim(k, d, kaynak, "2026-11-10").tara()) // 7 gün x 2 paket
        assertEquals(7, kaynak.gunler.size)
        val kayitlar = k.tum()
        val gunler = kayitlar.map { (it["yuk"] as JsonObject)["gun"]!!.jsonPrimitive.content }.toSet()
        assertEquals((3..9).map { "2026-11-%02d".format(it) }.toSet(), gunler)
        assertFalse("2026-11-10" in gunler) // bugün yazılmaz
        val r = kayitlar.first { (it["yuk"] as JsonObject)["paket"]!!.jsonPrimitive.content == "com.ornek.a" }
        assertEquals("uygulama.kullanim", r["tur"]!!.jsonPrimitive.content)
        assertEquals("uygulama", r["kategori"]!!.jsonPrimitive.content)
        assertEquals(listOf("paket", "ad", "gun", "sure_ms"), (r["yuk"] as JsonObject).keys.toList())
        val b = kayitlar.first { (it["yuk"] as JsonObject)["paket"]!!.jsonPrimitive.content == "com.ornek.b" }
        assertEquals(listOf("paket", "gun", "sure_ms"), (b["yuk"] as JsonObject).keys.toList()) // adı bilinmeyen: ad yok
        // gün sınırı yerel gece yarısı (İstanbul UTC+3)
        val (bas, son) = kaynak.gunler[0]
        assertEquals(24 * 3600 * 1000L, son - bas)
        assertEquals("2026-11-02T21:00:00Z", java.time.Instant.ofEpochMilli(bas).toString())
    }

    @Test
    fun kullanimAyniGunIkiKezYazilmazErtesiGunSadeceDun() {
        val k = TestYardim.Kurulum().ac()
        val d = BellekDepolama()
        val kaynak = SahteKullanim()
        kullanim(k, d, kaynak, "2026-11-10").tara()
        assertEquals(0, kullanim(k, d, kaynak, "2026-11-10").tara())
        assertEquals(2, kullanim(k, d, kaynak, "2026-11-11").tara()) // yalnız 10 Kasım
        assertEquals(16, k.bekleyenKayitSayisi())
        // uzun ara: en çok 7 gün
        val kaynak2 = SahteKullanim()
        assertEquals(14, kullanim(k, d, kaynak2, "2026-12-30").tara())
        assertEquals(7, kaynak2.gunler.size)
    }

    @Test
    fun toplayicilarVarsayilanKapaliIzinRedKapatir() {
        val d = BellekDepolama()
        val a = ToplayiciAyarlari(d)
        assertTrue(ToplayiciAyarlari.Ad.entries.none { a.acik(it) })
        assertFalse(a.herhangiAcik())
        a.ayarla(ToplayiciAyarlari.Ad.MEDYA, true)
        assertTrue(a.herhangiAcik())
        assertFalse(a.izinSonucu(ToplayiciAyarlari.Ad.MEDYA, false))
        assertFalse(a.acik(ToplayiciAyarlari.Ad.MEDYA))
        assertTrue(a.izinSonucu(ToplayiciAyarlari.Ad.KONUM, true))
        assertTrue(a.acik(ToplayiciAyarlari.Ad.KONUM))
    }

    @Test
    fun otuzBinMedyaKaydiToplu_ekleme_performansi() {
        val ku = TestYardim.Kurulum(zorla = true) // gerçek fsync
        val k = ku.ac()
        val kaynak = SahteMedya(MutableList(30_000) { foto(it + 1L, 1000L + it / 50) })
        val t = MedyaToplayici(k, kaynak, SahteKonum(emptyMap()), BellekDepolama())
        val bas = System.nanoTime()
        assertEquals(30_000, t.taraMedya())
        val ms = (System.nanoTime() - bas) / 1_000_000
        println("OLCUM 30000 kayit toplu tarama: $ms ms (grup 200, gercek fsync)")
        assertEquals(30_000, k.bekleyenKayitSayisi())
        assertEquals(30, k.kapatilmisDosyalar().size)
        assertEquals(0, t.taraMedya())
        assertTrue(ms < 120_000, "çok yavaş: $ms ms")
    }

    @Test
    fun imlecYalnizGrupYazildiktanSonraIlerler() {
        val ku = TestYardim.Kurulum()
        val k = ku.ac()
        val d = BellekDepolama()
        val kaynak = SahteMedya(MutableList(450) { foto(it + 1L, 100L + it) })
        // 2. grupta yazım hatası: kutu klasörü kaldırılır
        val t = MedyaToplayici(k, kaynak, SahteKonum(emptyMap()), d)
        var cagri = 0
        val bozucu = object : MedyaKaynagi {
            override fun sonrasi(tur: MedyaTuru, eklenmeSn: Long, id: Long, sinir: Int): List<MedyaOge> {
                if (tur == MedyaTuru.FOTO && ++cagri == 2) throw java.io.IOException("kopya")
                return kaynak.sonrasi(tur, eklenmeSn, id, sinir)
            }
        }
        val t2 = MedyaToplayici(k, bozucu, SahteKonum(emptyMap()), d)
        runCatching { t2.taraMedya() }
        assertEquals(200, k.bekleyenKayitSayisi()) // ilk grup yazıldı, imleç onun sonunda
        assertEquals(250, t.taraMedya()) // kalan 250, tekrarsız
        assertEquals(450, k.bekleyenKayitSayisi())
    }

    @Test
    fun adimIlkTaramaYalnizBaslangicSonrasiFarkYenidenBaslatmaSayaciSifirlar() {
        val k = TestYardim.Kurulum().ac()
        val d = BellekDepolama()
        var deger: Long? = 1000
        val t = AdimToplayici(k, object : AdimKaynagi { override fun sayac() = deger }, d)
        assertEquals(0, t.tara())
        assertEquals(0, t.tara()) // fark yok
        deger = 1250
        assertEquals(1, t.tara())
        deger = 40 // telefon yeniden başladı
        assertEquals(1, t.tara())
        deger = null // sensör yok
        assertEquals(0, t.tara())
        val kayitlar = k.tum()
        assertEquals(listOf("250", "40"), kayitlar.map { it["yuk"]!!.let { y -> (y as JsonObject)["fark"]!!.jsonPrimitive.content } })
        assertTrue(kayitlar.all { it["tur"]!!.jsonPrimitive.content == "sensor.adim" && it["kategori"]!!.jsonPrimitive.content == "uygulama" })
    }

    @Test
    fun ekranSuzgeciKendiPaketiAralikTekrarVeKisaMetniAtlar() {
        val s = EkranMetniSuzgeci("app.kimlikmerkezi.toplayici", aralikMs = 5000, azami = 20)
        assertEquals(null, s.kabul("app.kimlikmerkezi.toplayici", "kendi ekranım", 0))
        assertEquals(null, s.kabul("x.y", "ab", 0))
        assertEquals("merhaba dünya", s.kabul("x.y", "  merhaba \n dünya ", 0))
        assertEquals(null, s.kabul("x.y", "başka metin burada", 1000)) // aralık dolmadı
        assertEquals(null, s.kabul("x.y", "merhaba dünya", 6000)) // aynı metin
        assertEquals("başka metin burada", s.kabul("x.y", "başka metin burada", 12000))
        assertEquals("a".repeat(20), s.kabul("z.w", "a".repeat(50), 12000)) // en çok 20 karakter
    }

    @Test
    fun yerelGecmisKutuBosalsaDaKalirDuzenlenenYerineGecerEkranMetniGizlenir() {
        val f = java.io.File.createTempFile("gecmis", ".txt")
        try {
            val g = YerelGecmis(f, limit = 3)
            g.ekle(listOf(
                app.kimlikmerkezi.toplayici.giden.KayitOzeti("a", "2026-11-17T10:00:00.000Z", "not.hizli", "ilk\tnot", null),
                app.kimlikmerkezi.toplayici.giden.KayitOzeti("b", "2026-11-17T10:01:00.000Z", "not.hizli", "ilk not düzeltildi", "a"),
                app.kimlikmerkezi.toplayici.giden.KayitOzeti("c", "2026-11-17T10:02:00.000Z", "ekran.metin", "gizli içerik", null),
            ))
            val yeni = YerelGecmis(f, limit = 3) // dosyadan yüklenir
            val son = yeni.son(10)
            assertEquals(listOf("c", "b"), son.map { it.id })
            assertFalse(son.any { it.ozet.contains("gizli") })
            assertEquals(mapOf("not.hizli" to 2, "ekran.metin" to 1), yeni.turSayilari())
            yeni.ekle(listOf(app.kimlikmerkezi.toplayici.giden.KayitOzeti("d", "2026-11-17T10:03:00.000Z", "sensor.adim", "9 adım", null)))
            assertEquals(3, yeni.turSayilari().values.sum()) // en çok 3 satır
        } finally {
            f.delete()
        }
    }
}
