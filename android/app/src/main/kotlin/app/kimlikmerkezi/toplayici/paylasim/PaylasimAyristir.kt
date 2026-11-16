package app.kimlikmerkezi.toplayici.paylasim

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Paylaşılan metinden giden kutusu kaydı için tür, metin ve yük üretir. */
object PaylasimAyristir {
    class Sonuc(val tur: String, val metin: String, val yuk: JsonObject)

    private val URL_RE = Regex("""(?i)\b(?:https?://|www\.)[^\s<>"]+""")
    private val SONDAKI = charArrayOf('.', ',', ';', ':', '!', '?', ')', ']', '}', '\'', '"')

    /** Metindeki ilk bağlantı (http/https ya da www.), yoksa null. */
    fun urlBul(metin: String): String? {
        val m = URL_RE.find(metin) ?: return null
        var u = m.value.trimEnd(*SONDAKI)
        if (u.length <= "www.".length || u.endsWith("://")) return null
        if (u.startsWith("www.", ignoreCase = true)) u = "https://$u"
        return u
    }

    fun ayristir(metin: String, baslik: String?, kaynakUygulama: String?): Sonuc {
        val temiz = metin.trim()
        val b = baslik?.trim()?.takeIf { it.isNotEmpty() }
        val url = urlBul(temiz)
        return if (url != null) {
            Sonuc(
                "paylasim.link",
                if (b != null && !temiz.contains(b)) "$b\n$temiz" else temiz,
                buildJsonObject {
                    put("url", url)
                    if (b != null) put("baslik", b)
                    if (kaynakUygulama != null) put("kaynak_uygulama", kaynakUygulama)
                },
            )
        } else {
            Sonuc(
                "paylasim.metin",
                temiz,
                buildJsonObject { if (kaynakUygulama != null) put("kaynak_uygulama", kaynakUygulama) },
            )
        }
    }
}
