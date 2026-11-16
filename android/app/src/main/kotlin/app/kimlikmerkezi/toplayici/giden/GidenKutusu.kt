package app.kimlikmerkezi.toplayici.giden

import app.kimlikmerkezi.toplayici.gunluk.Gunluk
import app.kimlikmerkezi.toplayici.gunluk.SabitIletili
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import java.io.ByteArrayInputStream
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.RandomAccessFile
import java.time.Instant
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.UUID
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/** Başlık satırındaki cihaz alanları. */
data class CihazBilgisi(val cihazId: String, val uygulamaSurumu: String, val androidApi: Int, val model: String)

/** Listeleme için kısa kayıt özeti (metnin yalnız ilk 80 karakteri bellekte tutulur). */
data class KayitOzeti(val id: String, val ts: String, val tur: String, val ozet: String, val onceki: String?)

data class Kayit(
    val id: String,
    val ts: String,
    val tur: String,
    val kategori: String,
    val metin: String,
    val yuk: JsonObject,
    val onceki: String?,
)

/** Toplu ekleme girdisi. */
class YeniKayit(val tur: String, val kategori: String, val metin: String, val yuk: JsonObject = JsonObject(emptyMap()), val onceki: String? = null)

data class DosyaBilgisi(val dosyaId: String, val kayitSayisi: Int, val boyutBayt: Long, val acilis: String)

/** İletisi içerik taşımaz. */
class GidenKutusuHatasi(ileti: String, neden: Throwable? = null) : Exception(ileti, neden), SabitIletili

/**
 * Şifreli giden kutusu. Biçim: docs/AKTARIM.md §1; disk çerçevesi: android/BICIM.md.
 * Tek yazar kilidi: bütün genel işlevler aynı kilidi alır.
 */
class GidenKutusu(
    private val dizin: File,
    private val sifreleyici: Sifreleyici,
    private val cihaz: CihazBilgisi,
    private val gunluk: Gunluk,
    private val saat: () -> Instant = { Instant.now() },
    private val bolge: () -> ZoneId = { ZoneId.systemDefault() },
    private val kapatmaEsigi: Int = KAPATMA_ESIGI,
    /** Her çerçeveden sonra fsync. Yalnız çok sayıda kayıt yazan testlerde kapatılır. */
    private val zorlaYaz: Boolean = true,
) {
    private class Dosya(
        val id: String,
        val dosya: File,
        val acilis: Instant,
        var kayitSayisi: Int,
        var kapali: Boolean,
        var bayt: Int,
        var sira: Long,
        val ozetler: MutableList<KayitOzeti>,
    )

    private val kilit = ReentrantLock()
    private val dosyalar = LinkedHashMap<String, Dosya>()
    private var acik: Dosya? = null
    private var bozukDosyalar = 0

    /** Her değişiklikten sonra (kilit bırakıldıktan sonra) çağrılır; arayüzü yenilemek içindir. */
    @Volatile
    var dinleyici: (() -> Unit)? = null

    init {
        kilit.withLock {
            dizin.mkdirs()
            var kayip = 0
            val liste = dizin.listFiles { f -> f.name.endsWith(UZANTI) }.orEmpty().sortedBy { it.name }
            for (f in liste) kayip += yukle(f)
            if (kayip > 0) gunluk.bilgi("giden", "acilis onarimi: $kayip yarim cerceve atildi")
            // Birden fazla açık dosya kalmışsa (beklenmez) en yenisi dışındakileri kapat.
            val acikOlanlar = dosyalar.values.filter { !it.kapali }.sortedBy { it.acilis }
            acikOlanlar.dropLast(1).forEach { runCatching { kapat(it) } }
            acik = dosyalar.values.lastOrNull { !it.kapali }
        }
    }

    // ---- Genel API ----

    fun kayitEkle(
        tur: String,
        kategori: String,
        metin: String,
        yuk: JsonObject = JsonObject(emptyMap()),
        onceki: String? = null,
    ): String = kayitlariEkle(listOf(YeniKayit(tur, kategori, metin, yuk, onceki))).single()

    /**
     * Toplu ekleme: dosya başına ve grup başına TEK fsync. Dönen kimlikler girdiyle aynı sırada.
     * `metin` 64 KiB'a, `yuk` içindeki metin alanları 2 KiB'a kısaltılır; satır her durumda <= 1 MiB (aksi halde
     * kayıt reddedilir: [GidenKutusuHatasi] `kayit_cok_buyuk`). Eşik kapatması hata verirse kayıt yine eklenmiş sayılır.
     */
    fun kayitlariEkle(liste: List<YeniKayit>): List<String> {
        for (k in liste) {
            require(KATEGORI[k.tur] == k.kategori) { "bilinmeyen tur ya da kategori uyusmuyor" }
            require(k.onceki == null || UUID_RE.matches(k.onceki)) { "onceki gecerli bir kimlik degil" }
        }
        val idler = ArrayList<String>(liste.size)
        kilit.withLock {
            var i = 0
            while (i < liste.size) {
                val simdi = saat()
                acik?.let { if (it.kayitSayisi >= kapatmaEsigi || gun(it.acilis) != gun(simdi)) kapatDene(it) }
                val d = acik ?: yeniDosya(simdi)
                val kapasite = maxOf(1, kapatmaEsigi - d.kayitSayisi)
                val parti = liste.subList(i, minOf(liste.size, i + kapasite))
                val hazir = parti.map { hazirla(it, simdi) }
                ekle(d, hazir.map { it.satir })
                d.kayitSayisi += hazir.size
                hazir.forEach { d.ozetler.add(KayitOzeti(it.id, it.ts, it.tur, ozet(it.metin), it.onceki)) }
                hazir.forEach { idler.add(it.id) }
                i += parti.size
                if (d.kayitSayisi >= kapatmaEsigi) kapatDene(d)
            }
        }
        dinleyici?.invoke()
        return idler
    }

    private class Hazir(val id: String, val ts: String, val tur: String, val metin: String, val onceki: String?, val satir: String)

    private fun satirYap(id: String, ts: String, k: YeniKayit, metin: String, yuk: JsonObject) = guvenliSatir(
        buildJsonObject {
            put("id", id)
            put("ts", ts)
            put("tur", k.tur)
            put("kategori", k.kategori)
            put("metin", metin)
            put("yuk", yuk)
            put("onceki", if (k.onceki == null) JsonNull else JsonPrimitive(k.onceki))
        }.toString(),
    )

    private fun hazirla(k: YeniKayit, simdi: Instant): Hazir {
        val id = UUID.randomUUID().toString()
        val ts = ISO.format(simdi)
        var metin = kisalt(k.metin, METIN_UST).first
        var satir = satirYap(id, ts, k, metin, kisaltYuk(k.yuk, ALAN_UST) as JsonObject)
        if (satir.toByteArray(Charsets.UTF_8).size + 1 > SATIR_UST) {
            metin = kisalt(metin, 16 * 1024).first
            satir = satirYap(id, ts, k, metin, kisaltYuk(k.yuk, 256) as JsonObject)
            if (satir.toByteArray(Charsets.UTF_8).size + 1 > SATIR_UST) {
                gunluk.bilgi("giden", "kayit reddedildi: kayit_cok_buyuk")
                throw GidenKutusuHatasi("kayit_cok_buyuk")
            }
        }
        return Hazir(id, ts, k.tur, metin, k.onceki, satir)
    }

    /** Kapatma hatası kaydı etkilemez: günlüğe kod yazılır, sonraki eklemede yeniden denenir. */
    private fun kapatDene(d: Dosya) {
        try {
            kapat(d)
        } catch (e: GidenKutusuHatasi) {
            gunluk.bilgi("giden", "kapatma ertelendi: ${e.message}")
        }
    }

    /** Açık dosyayı kapatır; kapatılan dosyanın kimliğini, açık dosya yoksa null döner. */
    fun acikDosyayiKapat(): String? {
        val sonuc = kilit.withLock { acik?.let { val id = it.id; kapat(it); id } }
        dinleyici?.invoke()
        return sonuc
    }

    fun kapatilmisDosyalar(): List<DosyaBilgisi> = kilit.withLock {
        dosyalar.values.filter { it.kapali }.sortedBy { it.acilis }.map {
            DosyaBilgisi(it.id, it.kayitSayisi, it.dosya.length(), ISO.format(it.acilis))
        }
    }

    fun bekleyenKayitSayisi(): Int = kilit.withLock { dosyalar.values.sumOf { it.kayitSayisi } }

    fun bekleyenDosyaSayisi(): Int = kilit.withLock { dosyalar.size }

    fun bozukDosyaSayisi(): Int = kilit.withLock { bozukDosyalar }

    /** Kapatılmış dosyanın ÇÖZÜLMÜŞ içeriği (AKTARIM §1 biçimi, UTF-8). */
    fun dosyayiOku(dosyaId: String): InputStream = kilit.withLock {
        val d = dosyalar[dosyaId]?.takeIf { it.kapali } ?: throw GidenKutusuHatasi("kapatilmis dosya yok")
        ByteArrayInputStream(cozulmusIcerik(d))
    }

    /** Yalnız kapatılmış dosya silinir. Silindiyse true. */
    fun dosyayiSil(dosyaId: String): Boolean {
        val silindi = kilit.withLock {
            val d = dosyalar[dosyaId]?.takeIf { it.kapali } ?: return@withLock false
            if (!d.dosya.delete()) throw GidenKutusuHatasi("dosya silinemedi")
            dosyalar.remove(dosyaId)
            true
        }
        if (silindi) {
            gunluk.bilgi("giden", "dosya silindi")
            dinleyici?.invoke()
        }
        return silindi
    }

    /** En yeni [n] kayıt (yeniden eskiye); yeni sürümü olan eski kayıtlar listelenmez. */
    fun sonKayitlar(n: Int): List<KayitOzeti> = kilit.withLock {
        val hepsi = dosyalar.values.sortedBy { it.acilis }.flatMap { it.ozetler }
        val degisen = hepsi.mapNotNull { it.onceki }.toSet()
        hepsi.filter { it.id !in degisen }.takeLast(n).reversed()
    }

    fun kayitBul(id: String): Kayit? = kilit.withLock {
        for (d in dosyalar.values) {
            if (d.ozetler.none { it.id == id }) continue
            for (s in satirlar(d)) {
                val o = runCatching { JSON.parseToJsonElement(s) as JsonObject }.getOrNull() ?: continue
                if (o["id"]?.jsonPrimitive?.contentOrNull == id) return@withLock kayitOku(o)
            }
        }
        null
    }

    // ---- İç işlevler ----

    private fun gun(t: Instant) = t.atZone(bolge()).toLocalDate()

    private fun dosyaYolu(id: String) = File(dizin, id + UZANTI)

    private fun yeniDosya(simdi: Instant): Dosya {
        val id = UUID.randomUUID().toString()
        val baslik = guvenliSatir(
            buildJsonObject {
                put("baslik", true)
                put("bicim", 1)
                put("cihaz_id", cihaz.cihazId)
                put("dosya_id", id)
                put("acilis", ISO.format(simdi))
                put("uygulama", cihaz.uygulamaSurumu)
                put("android_api", cihaz.androidApi)
                put("model", cihaz.model)
            }.toString(),
        )
        val d = Dosya(id, dosyaYolu(id), milisaniyeye(simdi), 0, false, 0, 0, ArrayList())
        try {
            ekle(d, listOf(baslik))
        } catch (e: GidenKutusuHatasi) {
            d.dosya.delete()
            throw e
        }
        dosyalar[id] = d
        acik = d
        return d
    }

    private fun milisaniyeye(t: Instant): Instant = Instant.ofEpochMilli(t.toEpochMilli())

    /** Çerçeveleri tek yazım + tek fsync ile ekler; hata olursa dosyayı bilinen son iyi boyuta geri keser. */
    private fun ekle(d: Dosya, satirlar: List<String>) {
        try {
            val cerceveler = satirlar.mapIndexed { n, s -> Cerceve.yaz(sifreleyici, d.id, d.sira + n, (s + "\n").toByteArray(Charsets.UTF_8)) }
            val toplam = cerceveler.sumOf { it.size }
            FileOutputStream(d.dosya, true).use { o ->
                cerceveler.forEach { o.write(it) }
                o.flush()
                if (zorlaYaz) o.fd.sync()
            }
            d.bayt += toplam
            d.sira += cerceveler.size
        } catch (e: Exception) {
            runCatching { RandomAccessFile(d.dosya, "rw").use { it.setLength(d.bayt.toLong()) } }
            gunluk.hata("giden", e)
            throw GidenKutusuHatasi("yazilamadi", e)
        }
    }

    private fun kapat(d: Dosya) {
        if (d.kapali) return
        if (d.kayitSayisi == 0) {
            d.dosya.delete()
            dosyalar.remove(d.id)
        } else {
            ekle(d, listOf(guvenliSatir(buildJsonObject { put("kapanis", true); put("kayit_sayisi", d.kayitSayisi) }.toString())))
            d.kapali = true
        }
        if (acik === d) acik = null
    }

    private fun cozulmusIcerik(d: Dosya): ByteArray {
        val o = Cerceve.oku(sifreleyici, d.id, d.dosya.readBytes())
        if (o.bozuk || o.yarimUc) throw GidenKutusuHatasi("dosya bozuk")
        return o.icerikler.fold(ByteArray(0)) { a, b -> a + b }
    }

    private fun satirlar(d: Dosya): List<String> =
        String(cozulmusIcerik(d), Charsets.UTF_8).split('\n').filter { it.isNotEmpty() }

    /** Diskteki bir dosyayı okuyup dizine alır, gerekirse onarır. Atılan yarım çerçeve sayısını döner. */
    private fun yukle(f: File): Int {
        val id = f.name.removeSuffix(UZANTI)
        if (!UUID_RE.matches(id)) return 0
        val veri = f.readBytes()
        val o = Cerceve.oku(sifreleyici, id, veri)
        var kayip = 0
        var bayt = o.gecerliBayt
        if (o.yarimUc) {
            kayip = 1
            runCatching { RandomAccessFile(f, "rw").use { it.setLength(bayt.toLong()) } }
        }
        if (o.icerikler.isEmpty() && !o.bozuk) {
            f.delete()
            return kayip
        }
        fun bozukSay(neden: String): Int {
            bozukDosyalar++
            gunluk.bilgi("giden", "bozuk dosya atlandi: $neden")
            return kayip
        }
        if (o.bozuk || o.icerikler.isEmpty()) return bozukSay("cerceve dogrulanamadi")
        val satirlar = o.icerikler.map { String(it, Charsets.UTF_8).trimEnd('\n') }
        val baslik = runCatching { JSON.parseToJsonElement(satirlar[0]) as JsonObject }.getOrNull()
        if (baslik == null || baslik["baslik"]?.jsonPrimitive?.booleanOrNull != true ||
            baslik["dosya_id"]?.jsonPrimitive?.contentOrNull != id
        ) {
            return bozukSay("baslik gecersiz")
        }
        val acilis = runCatching { Instant.parse(baslik["acilis"]!!.jsonPrimitive.content) }.getOrNull()
            ?: return bozukSay("acilis gecersiz")
        val ozetler = ArrayList<KayitOzeti>()
        var kapali = false
        var beklenen = -1
        for (s in satirlar.drop(1)) {
            val j = runCatching { JSON.parseToJsonElement(s) as JsonObject }.getOrNull()
                ?: return bozukSay("satir gecersiz")
            if (kapali) return bozukSay("kapanistan sonra satir")
            if (j["kapanis"]?.jsonPrimitive?.booleanOrNull == true) {
                kapali = true
                beklenen = j["kayit_sayisi"]?.jsonPrimitive?.intOrNull ?: -1
            } else {
                val k = runCatching { kayitOku(j) }.getOrNull() ?: return bozukSay("kayit gecersiz")
                ozetler.add(KayitOzeti(k.id, k.ts, k.tur, ozet(k.metin), k.onceki))
            }
        }
        if (kapali && beklenen != ozetler.size) return bozukSay("kayit_sayisi tutmuyor")
        dosyalar[id] = Dosya(id, f, acilis, ozetler.size, kapali, bayt, o.icerikler.size.toLong(), ozetler)
        return kayip
    }

    private fun kayitOku(o: JsonObject) = Kayit(
        id = o["id"]!!.jsonPrimitive.content,
        ts = o["ts"]!!.jsonPrimitive.content,
        tur = o["tur"]!!.jsonPrimitive.content,
        kategori = o["kategori"]!!.jsonPrimitive.content,
        metin = o["metin"]!!.jsonPrimitive.content,
        yuk = o["yuk"] as JsonObject,
        onceki = o["onceki"]?.jsonPrimitive?.contentOrNull,
    )

    companion object {
        const val KAPATMA_ESIGI = 1000
        /** `metin` en çok 64 KiB (UTF-8), `yuk` içindeki her metin alanı en çok 2 KiB, serileştirilmiş satır en çok 1 MiB. */
        const val METIN_UST = 64 * 1024
        const val ALAN_UST = 2 * 1024
        const val SATIR_UST = 1024 * 1024
        const val KISALTMA_EKI = "… [kısaltıldı]"

        /** UTF-8 bayt sınırına göre, kod noktası sınırında keser. (sonuç, kısaltıldı mı) */
        fun kisalt(metin: String, azamiBayt: Int): Pair<String, Boolean> {
            val b = metin.toByteArray(Charsets.UTF_8)
            if (b.size <= azamiBayt) return metin to false
            val ek = KISALTMA_EKI.toByteArray(Charsets.UTF_8).size
            var son = maxOf(0, azamiBayt - ek)
            while (son > 0 && (b[son].toInt() and 0xC0) == 0x80) son--
            return String(b, 0, son, Charsets.UTF_8) + KISALTMA_EKI to true
        }

        private fun kisaltYuk(e: JsonElement, sinir: Int): JsonElement = when (e) {
            is JsonObject -> JsonObject(e.mapValues { kisaltYuk(it.value, sinir) })
            is JsonArray -> JsonArray(e.map { kisaltYuk(it, sinir) })
            is JsonPrimitive -> if (e.isString) JsonPrimitive(kisalt(e.content, sinir).first) else e
        }

        const val UZANTI = ".jsonl.kmx"

        /** AKTARIM §1 tür → kategori tablosu. */
        val KATEGORI: Map<String, String> = mapOf(
            "paylasim.link" to "notlar",
            "paylasim.metin" to "notlar",
            "not.hizli" to "notlar",
            "medya.foto" to "medya_meta",
            "medya.video" to "medya_meta",
            "medya.konum" to "konum",
            "indirilen.dosya" to "dosyalar",
            "uygulama.kullanim" to "uygulama",
        )

        val ISO: DateTimeFormatter =
            DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC)

        private val JSON = Json
        private val UUID_RE = Regex("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")

        /** Satır ayırıcı sayılabilecek (Python splitlines vb.) karakterleri kaçışa çevirir; satır tek `\n` ile biter. */
        fun guvenliSatir(json: String): String =
            json.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029").replace("\u0085", "\\u0085")

        fun ozet(metin: String): String {
            val t = metin.replace(Regex("\\s+"), " ").trim()
            return if (t.codePointCount(0, t.length) <= 80) t else t.substring(0, t.offsetByCodePoints(0, 80))
        }
    }
}
