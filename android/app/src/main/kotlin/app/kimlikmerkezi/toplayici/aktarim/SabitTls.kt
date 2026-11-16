package app.kimlikmerkezi.toplayici.aktarim

import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.Proxy
import java.net.URL
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocketFactory
import javax.net.ssl.X509TrustManager

/** Sunucu sertifikası sabitlenen parmak izine uymuyor. */
class SertifikaUyusmadi : CertificateException("sertifika parmak izi uyusmadi")

fun ByteArray.sha256Hex(): String = MessageDigest.getInstance("SHA-256").digest(this).joinToString("") { "%02x".format(it) }

/**
 * Yalnız [parmakIzi] (SHA-256 DER, hex) ile aynı sertifikayı kabul eder; sistem deposuna ve ana makine adına bakmaz.
 * El sıkışma sırasında doğrulanır: uymazsa hiçbir uygulama verisi gönderilmez.
 */
class SabitGuvenYoneticisi(parmakIzi: String) : X509TrustManager {
    private val beklenen = parmakIzi.lowercase()

    override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
        val yaprak = chain?.firstOrNull() ?: throw SertifikaUyusmadi()
        val h = yaprak.encoded.sha256Hex()
        if (!MessageDigest.isEqual(h.toByteArray(), beklenen.toByteArray())) throw SertifikaUyusmadi()
    }

    override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) = throw CertificateException("istemci sertifikasi beklenmiyor")
    override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
}

class Yanit(val kod: Int, val baslik: Map<String, String>, val govde: ByteArray = ByteArray(0)) {
    fun baslik(ad: String): String? = baslik[ad.lowercase()]
}

/** Bir PC adresine bağlı (sabit parmak izli) istemci. Yalnız https, yalnız sayısal yerel adres. */
interface PcBaglanti {
    fun durum(): Yanit
    fun eslestir(govde: ByteArray): Yanit
    fun head(cihazId: String, dosyaId: String, anahtar: String): Yanit
    fun put(cihazId: String, dosyaId: String, anahtar: String, bas: Long, toplam: Long, sha: String, parca: ByteArray): Yanit
}

fun interface BaglantiUretici {
    fun ac(adres: String, port: Int): PcBaglanti
}

class HttpsBaglanti(private val adres: String, private val port: Int, parmakIzi: String) : PcBaglanti {
    private val fabrika: SSLSocketFactory = SSLContext.getInstance("TLS").apply {
        init(null, arrayOf(SabitGuvenYoneticisi(parmakIzi)), SecureRandom())
    }.socketFactory

    init {
        require(AdresSuzgeci.yerelMi(adres)) { "yerel olmayan adres" }
    }

    private fun istek(metot: String, yol: String, basliklar: Map<String, String>, govde: ByteArray?): Yanit {
        val c = URL("https", adres, port, yol).openConnection(Proxy.NO_PROXY) as HttpsURLConnection
        try {
            c.sslSocketFactory = fabrika
            // Parmak izi el sıkışmada doğrulandı; bu doğrulayıcı yalnız BU bağlantı içindir.
            c.hostnameVerifier = javax.net.ssl.HostnameVerifier { _, _ -> true }
            c.connectTimeout = 5_000
            c.readTimeout = 30_000
            c.instanceFollowRedirects = false
            c.useCaches = false
            // Her istek ayrı bağlantı ve açıkça kapatılır: Android'in bağlantı havuzu boşta bağlantıları açık tutar ve PC'nin
            // IP başına 4 bağlantı sınırına takılır (gerçek PC alıcısına karşı CI'de görüldü).
            c.setRequestProperty("Connection", "close")
            c.requestMethod = metot
            basliklar.forEach { (k, v) -> c.setRequestProperty(k, v) }
            var yazmaHatasi: IOException? = null
            if (govde != null) {
                c.doOutput = true
                c.setFixedLengthStreamingMode(govde.size)
                try {
                    c.outputStream.use { it.write(govde) }
                } catch (e: IOException) {
                    // PC gövdeyi okumadan yanıt verip kapatmış olabilir: yanıt okunabiliyorsa onu kullan.
                    if (e.sertifikaHatasiMi()) throw e
                    yazmaHatasi = e
                }
            }
            val kod = try {
                c.responseCode
            } catch (e: IOException) {
                throw yazmaHatasi ?: e
            }
            val b = HashMap<String, String>()
            c.headerFields.forEach { (k, v) -> if (k != null && v.isNotEmpty()) b[k.lowercase()] = v.last() }
            val ac = if (metot == "HEAD") ByteArray(0) else okuSinirli(if (kod >= 400) c.errorStream else c.inputStream)
            return Yanit(kod, b, ac)
        } finally {
            c.disconnect()
        }
    }

    private fun okuSinirli(s: java.io.InputStream?): ByteArray {
        if (s == null) return ByteArray(0)
        s.use {
            val o = ByteArrayOutputStream()
            val tampon = ByteArray(4096)
            while (o.size() < 65536) {
                val n = it.read(tampon)
                if (n < 0) break
                o.write(tampon, 0, n)
            }
            return o.toByteArray()
        }
    }

    override fun durum() = istek("GET", "/durum", emptyMap(), null)

    override fun eslestir(govde: ByteArray) =
        istek("POST", "/eslestir", mapOf("Content-Type" to "application/json"), govde)

    private fun kimlik(cihazId: String, anahtar: String) = mapOf("Authorization" to "Bearer $anahtar", "X-Cihaz" to cihazId)

    override fun head(cihazId: String, dosyaId: String, anahtar: String) =
        istek("HEAD", "/giden/$cihazId/$dosyaId.jsonl", kimlik(cihazId, anahtar), null)

    override fun put(cihazId: String, dosyaId: String, anahtar: String, bas: Long, toplam: Long, sha: String, parca: ByteArray): Yanit {
        val son = bas + parca.size - 1
        return istek(
            "PUT", "/giden/$cihazId/$dosyaId.jsonl",
            kimlik(cihazId, anahtar) + mapOf(
                "Content-Range" to "bytes $bas-$son/$toplam",
                "X-Sha256" to sha,
                "Content-Type" to "application/octet-stream",
            ),
            parca,
        )
    }
}

/** İstisna zincirinde sertifika uyuşmazlığı var mı? */
fun Throwable.sertifikaHatasiMi(): Boolean = generateSequence(this) { it.cause }.any { it is SertifikaUyusmadi }

