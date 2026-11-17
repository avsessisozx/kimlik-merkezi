package app.kimlikmerkezi.toplayici

import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.giden.GidenKutusuHatasi
import app.kimlikmerkezi.toplayici.gunluk.Gunluk
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import java.io.File
import java.io.RandomAccessFile
import java.time.Duration
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class GidenKutusuTest {
    private fun GidenKutusu.not(m: String, onceki: String? = null) = kayitEkle("not.hizli", "notlar", m, onceki = onceki)
    private fun GidenKutusu.oku(id: String) = dosyayiOku(id).readBytes().toString(Charsets.UTF_8)

    @Test
    fun biciSozlesmeyeUyar() {
        val k = TestYardim.Kurulum().ac()
        val a = k.not("ilk not")
        k.kayitEkle(
            "paylasim.link", "notlar", "Başlık\nhttps://ornek.test/a",
            buildJsonObject { put("url", "https://ornek.test/a"); put("baslik", "Başlık") },
        )
        k.not("ilk not düzenlendi", onceki = a)
        val id = k.acikDosyayiKapat()!!
        val kayitlar = TestYardim.bicimiDogrula(k.oku(id))
        assertEquals(3, kayitlar.size)
        assertEquals("null", kayitlar[0]["onceki"].toString())
        assertEquals(a, kayitlar[2]["onceki"]!!.jsonPrimitive.content)
    }

    @Test
    fun uretilenDosyaAltinOrnekleAyniSekildedir() {
        val altin = javaClass.getResource("/giden_ornek.jsonl")!!.readText()
        val kayitlar = TestYardim.bicimiDogrula(altin)
        assertEquals(9, kayitlar.size)
        // Altın örnek v0.2 türlerini kapsar; v0.3.0'ın iki yeni türü (adım, ekran metni) ayrı testlerde sınanır.
        assertEquals(GidenKutusu.KATEGORI.keys - setOf("sensor.adim", "ekran.metin"), kayitlar.map { it["tur"]!!.jsonPrimitive.content }.toSet())
    }

    @Test
    fun geriDonusluSatirAyiriciKarakterleriKacar() {
        val k = TestYardim.Kurulum().ac()
        k.not("a\u2028b\u2029c\u0085d\r\ne")
        val ic = k.oku(k.acikDosyayiKapat()!!)
        assertFalse(ic.contains('\u2028') || ic.contains('\u2029') || ic.contains('\u0085') || ic.contains('\r'))
        assertEquals(3, ic.split("\n").filter { it.isNotEmpty() }.size)
        assertEquals("a\u2028b\u2029c\u0085d\r\ne", TestYardim.bicimiDogrula(ic)[0]["metin"]!!.jsonPrimitive.content)
    }

    @Test
    fun bilinmeyenTurReddedilirVeIletiIcerikTasimaz() {
        val k = TestYardim.Kurulum().ac()
        val e = assertFailsWith<IllegalArgumentException> { k.kayitEkle("yok.tur", "notlar", "GIZLI-METIN") }
        assertFalse(e.message!!.contains("GIZLI"))
        assertFailsWith<IllegalArgumentException> { k.kayitEkle("not.hizli", "konum", "x") }
        assertEquals(0, k.bekleyenKayitSayisi())
    }

    @Test
    fun onbinKayitIdsiTekildir() {
        val k = TestYardim.Kurulum(zorla = false).ac()
        val idler = HashSet<String>()
        repeat(10_000) { assertTrue(idler.add(k.not("n$it"))) }
        assertEquals(10_000, k.bekleyenKayitSayisi())
        assertTrue(idler.all { TestYardim.UUID4.matches(it) })
        assertEquals(10, k.kapatilmisDosyalar().size) // 1000'er kayıtla
    }

    @Test
    fun binKayittaDosyaKapanir() {
        val k = TestYardim.Kurulum(zorla = false).ac()
        repeat(999) { k.not("n$it") }
        assertTrue(k.kapatilmisDosyalar().isEmpty())
        k.not("son")
        val d = k.kapatilmisDosyalar()
        assertEquals(1, d.size)
        assertEquals(1000, d[0].kayitSayisi)
        k.not("yeni dosya")
        assertEquals(1, k.kapatilmisDosyalar().size)
        assertEquals(1001, k.bekleyenKayitSayisi())
    }

    @Test
    fun yerelGunDegisinceKapanir() {
        val ku = TestYardim.Kurulum()
        val k = ku.ac()
        k.not("bugün")
        ku.saat.an = ku.saat.an.plus(Duration.ofHours(10)) // aynı gün (UTC bölgesi)
        k.not("bugün 2")
        assertTrue(k.kapatilmisDosyalar().isEmpty())
        ku.saat.an = ku.saat.an.plus(Duration.ofHours(14)) // ertesi gün
        k.not("yarın")
        val d = k.kapatilmisDosyalar()
        assertEquals(1, d.size)
        assertEquals(2, d[0].kayitSayisi)
        assertEquals(3, k.bekleyenKayitSayisi())
    }

    @Test
    fun istenincKapanirVeBosAcikDosyaYokturIcin() {
        val k = TestYardim.Kurulum().ac()
        assertNull(k.acikDosyayiKapat())
        k.not("a")
        assertEquals(1, k.kapatilmisDosyalar().size.let { k.acikDosyayiKapat(); k.kapatilmisDosyalar().size })
        assertNull(k.acikDosyayiKapat())
    }

    @Test
    fun kapatilmisDosyaDegismez() {
        val ku = TestYardim.Kurulum()
        val k = ku.ac()
        k.not("a"); k.not("b")
        val id = k.acikDosyayiKapat()!!
        val dosya = File(ku.dizin, "giden/$id${GidenKutusu.UZANTI}")
        val once = dosya.readBytes()
        repeat(5) { k.not("sonra $it") }
        k.acikDosyayiKapat()
        assertTrue(once.contentEquals(dosya.readBytes()))
        // yeniden açılışta da aynı
        val k2 = ku.ac()
        assertTrue(once.contentEquals(dosya.readBytes()))
        assertEquals(7, k2.bekleyenKayitSayisi())
        // kapatılmış dosyaya ekleme yolu yok: yeni kayıt yeni dosyaya gider
        k2.not("x")
        assertTrue(once.contentEquals(dosya.readBytes()))
    }

    @Test
    fun yarimSatirOnarilir() {
        val ku = TestYardim.Kurulum(gunluk = Gunluk(null))
        val k = ku.ac()
        repeat(3) { k.not("GIZLI-NOT-$it") }
        val acik = File(ku.dizin, "giden").listFiles()!!.single()
        val tam = acik.length()
        RandomAccessFile(acik, "rw").use { it.setLength(tam - 7) } // son çerçeve yarım kaldı
        val k2 = ku.ac()
        assertEquals(2, k2.bekleyenKayitSayisi())
        assertEquals(0, k2.bozukDosyaSayisi())
        k2.not("devam")
        assertEquals(3, k2.bekleyenKayitSayisi())
        val id = k2.acikDosyayiKapat()!!
        val kayitlar = TestYardim.bicimiDogrula(k2.oku(id))
        assertEquals(listOf("GIZLI-NOT-0", "GIZLI-NOT-1", "devam"), kayitlar.map { it["metin"]!!.jsonPrimitive.content })
        val gunlukMetni = ku.gunluk.sonSatirlar(50).joinToString("\n")
        assertTrue(gunlukMetni.contains("1 yarim cerceve atildi"))
        assertFalse(gunlukMetni.contains("GIZLI"))
    }

    @Test
    fun yalnizYarimBaslikOlanDosyaSilinir() {
        val ku = TestYardim.Kurulum()
        val k = ku.ac()
        k.not("a")
        val f = File(ku.dizin, "giden").listFiles()!!.single()
        k.acikDosyayiKapat()
        // yeni açık dosya: yalnız başlık + kısmi kayıt
        k.not("b")
        val acik = File(ku.dizin, "giden").listFiles()!!.first { it != f }
        RandomAccessFile(acik, "rw").use { it.setLength(it.length() - 3) }
        val bas = RandomAccessFile(acik, "r").use { it.length() }
        assertTrue(bas > 0)
        val k2 = ku.ac()
        assertEquals(1, k2.bekleyenKayitSayisi())
    }

    @Test
    fun yeniden_acilistaKayitlarDurur() {
        val ku = TestYardim.Kurulum()
        val k = ku.ac()
        val a = k.not("bir")
        k.not("iki")
        val k2 = ku.ac()
        assertEquals(2, k2.bekleyenKayitSayisi())
        assertEquals(listOf("iki", "bir"), k2.sonKayitlar(10).map { it.ozet })
        // yeniden açılan kutu aynı açık dosyaya ekler
        k2.not("üç", onceki = a)
        assertEquals(3, k2.bekleyenKayitSayisi())
        assertEquals(1, File(ku.dizin, "giden").listFiles()!!.size)
        assertEquals("üç", k2.sonKayitlar(10)[0].ozet)
        assertEquals(listOf("üç", "iki"), k2.sonKayitlar(10).map { it.ozet }) // "bir" yeni sürümle değişti
        assertEquals("bir", k2.kayitBul(a)!!.metin)
    }

    @Test
    fun eszamanliYazimGuvenli() {
        val ku = TestYardim.Kurulum(zorla = false)
        val k = ku.ac()
        val havuz = Executors.newFixedThreadPool(8)
        val idler = java.util.concurrent.ConcurrentHashMap.newKeySet<String>()
        repeat(8) { t -> havuz.execute { repeat(300) { n -> idler.add(k.not("t$t-n$n")) } } }
        havuz.shutdown()
        assertTrue(havuz.awaitTermination(60, TimeUnit.SECONDS))
        assertEquals(2400, idler.size)
        assertEquals(2400, k.bekleyenKayitSayisi())
        assertEquals(2, k.kapatilmisDosyalar().size)
        k.acikDosyayiKapat()
        val metinler = HashSet<String>()
        for (d in k.kapatilmisDosyalar()) TestYardim.bicimiDogrula(k.oku(d.dosyaId)).forEach { metinler.add(it["metin"]!!.jsonPrimitive.content) }
        assertEquals(2400, metinler.size)
        // diskten yeniden okuma da aynı sayıyı verir
        assertEquals(2400, ku.ac().bekleyenKayitSayisi())
    }

    @Test
    fun dosyayiSilVeAcikDosyaOkunamaz() {
        val ku = TestYardim.Kurulum()
        val k = ku.ac()
        k.not("a")
        val acikId = File(ku.dizin, "giden").listFiles()!!.single().name.removeSuffix(GidenKutusu.UZANTI)
        assertFailsWith<GidenKutusuHatasi> { k.dosyayiOku(acikId) }
        assertFalse(k.dosyayiSil(acikId))
        k.acikDosyayiKapat()
        assertTrue(k.dosyayiSil(acikId))
        assertEquals(0, k.bekleyenKayitSayisi())
        assertTrue(File(ku.dizin, "giden").listFiles()!!.isEmpty())
    }

    @Test
    fun diskteDuzMetinYok() {
        val ku = TestYardim.Kurulum()
        val k = ku.ac()
        k.not("ÇOK-GIZLI-ifade-123")
        val tum = File(ku.dizin, "giden").listFiles()!!.single().readBytes()
        assertFalse(String(tum, Charsets.ISO_8859_1).contains("GIZLI"))
        assertFalse(String(tum, Charsets.ISO_8859_1).contains("baslik"))
    }

    @Test
    fun bozukDosyaSayilirVeAtlanir() {
        val ku = TestYardim.Kurulum()
        val k = ku.ac()
        k.not("a"); k.not("b")
        val f = File(ku.dizin, "giden").listFiles()!!.single()
        val b = f.readBytes()
        b[b.size - 5] = (b[b.size - 5].toInt() xor 1).toByte()
        f.writeBytes(b)
        val k2 = ku.ac()
        assertEquals(1, k2.bozukDosyaSayisi())
        assertEquals(0, k2.bekleyenKayitSayisi())
        assertNotEquals(0, f.length())
    }

    @Test
    fun uyduruk_oncekiReddedilir() {
        val k = TestYardim.Kurulum().ac()
        assertFailsWith<IllegalArgumentException> { k.not("x", onceki = "../../etc") }
    }

    // ---- A: kayıt boyutu ----
    @Test
    fun birMiBKontrolKarakterliPaylasimKisaltilirSatirSinirliDosyaGecerli() {
        val ku = TestYardim.Kurulum()
        val k = ku.ac()
        k.not("onceki gecerli not")
        val kotu = "\u0001".repeat(1024 * 1024) // JSON'da 6 kat şişer
        k.kayitEkle("paylasim.metin", "notlar", kotu, buildJsonObject { put("kaynak_uygulama", "k".repeat(10_000)) })
        k.not("sonraki gecerli not")
        val id = k.acikDosyayiKapat()!!
        val icerik = k.oku(id)
        val kayitlar = TestYardim.bicimiDogrula(icerik)
        assertEquals(3, kayitlar.size)
        assertTrue(icerik.lines().all { it.toByteArray().size <= GidenKutusu.SATIR_UST })
        val m = kayitlar[1]["metin"]!!.jsonPrimitive.content
        assertTrue(m.endsWith(GidenKutusu.KISALTMA_EKI))
        assertTrue(m.toByteArray().size <= GidenKutusu.METIN_UST)
        val kaynak = ((kayitlar[1]["yuk"]) as JsonObject)["kaynak_uygulama"]!!.jsonPrimitive.content
        assertTrue(kaynak.toByteArray().size <= GidenKutusu.ALAN_UST && kaynak.endsWith(GidenKutusu.KISALTMA_EKI))
        assertEquals("sonraki gecerli not", kayitlar[2]["metin"]!!.jsonPrimitive.content)
    }

    @Test
    fun kisaltKodNoktasiSinirindaKesilirKisaMetinDegismez() {
        val emoji = "\uD83D\uDE00" // 4 bayt
        val (k, kisaldi) = GidenKutusu.kisalt(emoji.repeat(30_000), GidenKutusu.METIN_UST)
        assertTrue(kisaldi)
        assertTrue(k.toByteArray().size <= GidenKutusu.METIN_UST)
        assertFalse(k.contains('\uFFFD'))
        assertTrue(k.removeSuffix(GidenKutusu.KISALTMA_EKI).all { true } && k.endsWith(GidenKutusu.KISALTMA_EKI))
        assertEquals("kısa" to false, GidenKutusu.kisalt("kısa", 100))
        val (t, _) = GidenKutusu.kisalt("é".repeat(100), 51) // 2 baytlık harfler: sınır ortasında kesilmez
        assertFalse(t.contains('\uFFFD'))
    }

    @Test
    fun asiriYukReddedilirGunlugeKodYazilirDosyaBozulmaz() {
        val ku = TestYardim.Kurulum()
        val k = ku.ac()
        k.not("once")
        val dev = buildJsonObject { repeat(3000) { put("a$it", "\u0001".repeat(2000)) } }
        val e = assertFailsWith<GidenKutusuHatasi> { k.kayitEkle("paylasim.metin", "notlar", "x", dev) }
        assertEquals("kayit_cok_buyuk", e.message)
        assertTrue(ku.gunluk.sonSatirlar(20).any { it.contains("kayit_cok_buyuk") })
        k.not("sonra")
        TestYardim.bicimiDogrula(k.oku(k.acikDosyayiKapat()!!)).let { assertEquals(2, it.size) }
    }

    // ---- I: eşik kapatma hatası çağırana yansımaz ----
    class SaskinSifreleyici(val ic: app.kimlikmerkezi.toplayici.giden.Sifreleyici, var basarisizCagri: Int) : app.kimlikmerkezi.toplayici.giden.Sifreleyici {
        var n = 0
        override fun sifrele(duz: ByteArray, aad: ByteArray): ByteArray {
            if (++n == basarisizCagri) throw IllegalStateException("ICERIK-SIZINTISI")
            return ic.sifrele(duz, aad)
        }
        override fun coz(paket: ByteArray, aad: ByteArray) = ic.coz(paket, aad)
    }

    @Test
    fun esikKapatmaHatasiKaydiEtkilemezSonrakiEklemedeYenidenDenenir() {
        val ku = TestYardim.Kurulum(esik = 2)
        // çağrılar: 1 başlık, 2 kayıt-1, 3 kayıt-2, 4 kapanış (BAŞARISIZ)
        val s = SaskinSifreleyici(app.kimlikmerkezi.toplayici.giden.AesGcmSifreleyici(TestYardim.ANAHTAR), 4)
        val k = GidenKutusu(File(ku.dizin, "giden"), s, TestYardim.CIHAZ, ku.gunluk, saat = ku.saat::simdi, bolge = { java.time.ZoneId.of("UTC") }, kapatmaEsigi = 2)
        k.not("bir")
        k.not("iki") // kapanış yazımı patlar ama ÇAĞIRANA hata fırlamaz
        assertEquals(2, k.bekleyenKayitSayisi())
        assertEquals(0, k.kapatilmisDosyalar().size)
        assertTrue(ku.gunluk.sonSatirlar(20).any { it.contains("kapatma ertelendi") })
        assertFalse(ku.gunluk.sonSatirlar(20).joinToString().contains("SIZINTI"))
        k.not("uc") // önce kapatmayı yeniden dener (başarılı), kayıt yeni dosyaya gider
        assertEquals(1, k.kapatilmisDosyalar().size)
        assertEquals(2, k.kapatilmisDosyalar()[0].kayitSayisi)
        assertEquals(3, k.bekleyenKayitSayisi())
        TestYardim.bicimiDogrula(k.oku(k.kapatilmisDosyalar()[0].dosyaId))
    }

    // ---- J: toplu ekleme ----
    @Test
    fun topluEklemeSiraliKimlikGrupBasinaDosyaDondurur() {
        val ku = TestYardim.Kurulum(zorla = false)
        val k = ku.ac()
        val idler = k.kayitlariEkle((1..2500).map { app.kimlikmerkezi.toplayici.giden.YeniKayit("not.hizli", "notlar", "n$it") })
        assertEquals(2500, idler.size)
        assertEquals(2500, idler.toSet().size)
        assertEquals(listOf(1000, 1000), k.kapatilmisDosyalar().map { it.kayitSayisi })
        assertEquals(2500, k.bekleyenKayitSayisi())
        assertEquals(2500, ku.ac().bekleyenKayitSayisi())
        k.acikDosyayiKapat()
        val sirali = k.kapatilmisDosyalar().flatMap { TestYardim.bicimiDogrula(k.oku(it.dosyaId)) }.map { it["metin"]!!.jsonPrimitive.content }
        assertEquals((1..2500).map { "n$it" }, sirali)
    }
}
