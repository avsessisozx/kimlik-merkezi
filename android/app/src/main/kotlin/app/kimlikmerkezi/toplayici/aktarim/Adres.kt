package app.kimlikmerkezi.toplayici.aktarim

import java.net.InetAddress

/** Yalnız yerel ağ adresleri: RFC1918 ve link-local (IPv4 sayısal adres). Ana makine adı ve IPv6 kabul edilmez. */
object AdresSuzgeci {
    /** YALNIZ testler için: 127.0.0.0/8 yerel sayılır. Üretimde false kalır. */
    @Volatile
    var testLoopback: Boolean = false

    private val IPV4 = Regex("""(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}""")

    fun yerelMi(adres: String): Boolean {
        if (!IPV4.matches(adres)) return false
        val b = InetAddress.getByName(adres).address.map { it.toInt() and 0xff }
        return when {
            b[0] == 10 -> true
            b[0] == 172 && b[1] in 16..31 -> true
            b[0] == 192 && b[1] == 168 -> true
            b[0] == 169 && b[1] == 254 -> true
            b[0] == 127 -> testLoopback
            else -> false
        }
    }
}

/** UDP bulma iletileri (AKTARIM §3). */
object Bulma {
    const val PORT = 47822

    fun istek(parmakIzi: String): ByteArray = "KM1?${parmakIzi.lowercase().take(16)}".toByteArray(Charsets.US_ASCII)

    /** `KM1!<port>` yanıtından port; biçim bozuksa null. */
    fun yanit(veri: ByteArray, uzunluk: Int = veri.size): Int? {
        val s = String(veri, 0, uzunluk, Charsets.US_ASCII).trim()
        if (!s.startsWith("KM1!")) return null
        return s.substring(4).takeIf { it.length in 1..5 && it.all(Char::isDigit) }?.toInt()?.takeIf { it in 1..65535 }
    }
}
