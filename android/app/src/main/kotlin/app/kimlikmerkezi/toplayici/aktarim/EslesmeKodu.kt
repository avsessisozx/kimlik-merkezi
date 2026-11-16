package app.kimlikmerkezi.toplayici.aktarim

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import java.util.Base64

/** `km1:` eşleştirme kodunun içeriği (AKTARIM §2, §7). */
data class EslesmeKodu(
    val adresler: List<String>,
    val port: Int,
    /** SHA-256(DER) küçük harf hex, 64 karakter. */
    val parmakIzi: String,
    val gizli: String,
    val pcAdi: String,
) {
    /** Gizli ve parmak izi YAZILMAZ. */
    override fun toString() = "EslesmeKodu(adres=${adresler.size}, port=$port, pcAdi=$pcAdi)"

    companion object {
        /** Bozuksa null. Dolgulu ve dolgusuz base64url kabul edilir. Yerel olmayan adresler atılır. */
        fun coz(metin: String): EslesmeKodu? {
            val m = metin.filter { !it.isWhitespace() }
            if (!m.startsWith("km1:", ignoreCase = true)) return null
            return try {
                val json = String(Base64.getUrlDecoder().decode(m.substring(4)), Charsets.UTF_8)
                val o = Json.parseToJsonElement(json) as JsonObject
                val adresler = (o["a"] as JsonArray).map { it.jsonPrimitive.content }.filter { AdresSuzgeci.yerelMi(it) }
                val port = o["p"]!!.jsonPrimitive.intOrNull!!
                val f = o["f"]!!.jsonPrimitive.content.lowercase()
                val k = o["k"]!!.jsonPrimitive.content
                val n = o["n"]!!.jsonPrimitive.content
                if (adresler.isEmpty() || port !in 1..65535 || !Regex("[0-9a-f]{64}").matches(f) || k.isEmpty()) return null
                EslesmeKodu(adresler, port, f, k, n.take(80))
            } catch (e: Exception) {
                null
            }
        }
    }
}
