package app.kimlikmerkezi.toplayici

import app.kimlikmerkezi.toplayici.giden.AesGcmSifreleyici
import app.kimlikmerkezi.toplayici.giden.CihazBilgisi
import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.gunluk.Gunluk
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import java.nio.file.Files
import java.time.Instant
import java.time.ZoneId
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Ayarlanabilir saat. */
class SahteSaat(var an: Instant = Instant.parse("2026-11-10T08:15:00Z")) {
    fun simdi(): Instant = an
}

object TestYardim {
    val ANAHTAR: SecretKey = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()
    val CIHAZ = CihazBilgisi("3f2b8c1e-5a47-4d9e-8b36-1c7e0a9d4f52", "0.2.0", 31, "SENTETIK-1")

    fun gecici(): File = Files.createTempDirectory("km_test").toFile().also { it.deleteOnExit() }

    class Kurulum(
        val dizin: File = gecici(),
        val saat: SahteSaat = SahteSaat(),
        val gunluk: Gunluk = Gunluk(null),
        val esik: Int = GidenKutusu.KAPATMA_ESIGI,
        val zorla: Boolean = true,
    ) {
        fun ac() = GidenKutusu(
            File(dizin, "giden"), AesGcmSifreleyici(ANAHTAR), CIHAZ, gunluk,
            saat = saat::simdi, bolge = { ZoneId.of("UTC") }, kapatmaEsigi = esik, zorlaYaz = zorla,
        )
    }

    val UUID4 = Regex("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
    val TS = Regex("\\d{4}-\\d\\d-\\d\\dT\\d\\d:\\d\\d:\\d\\d(\\.\\d+)?Z")

    val BASLIK_ANAHTARLARI = listOf("baslik", "bicim", "cihaz_id", "dosya_id", "acilis", "uygulama", "android_api", "model")
    val KAYIT_ANAHTARLARI = listOf("id", "ts", "tur", "kategori", "metin", "yuk", "onceki")

    /** AKTARIM §1 biçimini doğrular; kayıt satırlarını döner. */
    fun bicimiDogrula(icerik: String): List<JsonObject> {
        assertTrue(icerik.endsWith("\n"), "son satir \\n ile bitmeli")
        val satirlar = icerik.dropLast(1).split("\n")
        val o = satirlar.map { Json.parseToJsonElement(it) as JsonObject }
        val b = o.first()
        assertEquals(BASLIK_ANAHTARLARI, b.keys.toList())
        assertEquals(true, b["baslik"]!!.jsonPrimitive.booleanOrNull)
        assertEquals(1, b["bicim"]!!.jsonPrimitive.intOrNull)
        assertTrue(UUID4.matches(b["cihaz_id"]!!.jsonPrimitive.content))
        assertTrue(UUID4.matches(b["dosya_id"]!!.jsonPrimitive.content))
        assertTrue(TS.matches(b["acilis"]!!.jsonPrimitive.content))
        val k = o.last()
        assertEquals(listOf("kapanis", "kayit_sayisi"), k.keys.toList())
        assertEquals(true, k["kapanis"]!!.jsonPrimitive.booleanOrNull)
        val kayitlar = o.subList(1, o.size - 1)
        assertEquals(kayitlar.size, k["kayit_sayisi"]!!.jsonPrimitive.intOrNull)
        for (r in kayitlar) {
            assertEquals(KAYIT_ANAHTARLARI, r.keys.toList())
            assertTrue(UUID4.matches(r["id"]!!.jsonPrimitive.content))
            assertTrue(TS.matches(r["ts"]!!.jsonPrimitive.content))
            val tur = r["tur"]!!.jsonPrimitive.content
            assertEquals(GidenKutusu.KATEGORI[tur], r["kategori"]!!.jsonPrimitive.content, "kategori $tur")
            assertTrue(r["yuk"] is JsonObject)
            val on = r["onceki"]!!
            assertTrue(on.jsonPrimitive.content == "null" && on.toString() == "null" || UUID4.matches(on.jsonPrimitive.content))
        }
        return kayitlar
    }
}
