package app.kimlikmerkezi.toplayici

import app.kimlikmerkezi.toplayici.aktarim.BaglantiUretici
import app.kimlikmerkezi.toplayici.aktarim.PcBaglanti
import app.kimlikmerkezi.toplayici.aktarim.Yanit
import app.kimlikmerkezi.toplayici.aktarim.sha256Hex
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.InetAddress
import java.net.Socket
import java.security.KeyStore
import javax.net.ssl.KeyManagerFactory
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLServerSocket

/** Bellek içi istemci: [PcMantik]'e doğrudan bağlanır (ağ yok). YALNIZ TEST. */
class BellekBaglanti(private val m: PcMantik) : PcBaglanti {
    private fun cagir(metot: String, yol: String, b: Map<String, String>, govde: ByteArray = ByteArray(0)): Yanit {
        val c = m.isle(PcMantik.Istek(metot, yol, b.mapKeys { it.key.lowercase() }, govde)) ?: throw IOException("baglanti kesildi")
        return Yanit(c.kod, c.baslik.mapKeys { it.key.lowercase() }, c.govde)
    }

    private fun kim(c: String, a: String) = mapOf("Authorization" to "Bearer $a", "X-Cihaz" to c)
    override fun durum() = cagir("GET", "/durum", emptyMap())
    override fun eslestir(govde: ByteArray) = cagir("POST", "/eslestir", emptyMap(), govde)
    override fun head(cihazId: String, dosyaId: String, anahtar: String) = cagir("HEAD", "/giden/$cihazId/$dosyaId.jsonl", kim(cihazId, anahtar))
    override fun put(cihazId: String, dosyaId: String, anahtar: String, bas: Long, toplam: Long, sha: String, parca: ByteArray) =
        cagir("PUT", "/giden/$cihazId/$dosyaId.jsonl", kim(cihazId, anahtar) + mapOf("Content-Range" to "bytes $bas-${bas + parca.size - 1}/$toplam", "X-Sha256" to sha), parca)

    companion object {
        fun uretici(m: PcMantik) = BaglantiUretici { _, _ -> BellekBaglanti(m) }
    }
}

/**
 * Gerçek TLS (SSLServerSocket) ile [PcMantik]'i sunan, 127.0.0.1'e bağlı test sunucusu.
 * Sertifika: depodaki YALNIZ-TEST anahtar deposu (test_sunucu_YALNIZ_TEST.p12). Hem JVM hem emülatörde çalışır.
 */
class SahteSunucu(val mantik: PcMantik = PcMantik()) : AutoCloseable {
    private val ks = KeyStore.getInstance("PKCS12").apply {
        SahteSunucu::class.java.getResourceAsStream("/test_sunucu_YALNIZ_TEST.p12")!!.use { load(it, "test1234".toCharArray()) }
    }
    val parmakIzi: String = ks.getCertificate("test").encoded.sha256Hex()
    private val sunucu: SSLServerSocket = run {
        val kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm()).apply { init(ks, "test1234".toCharArray()) }
        val ctx = SSLContext.getInstance("TLS").apply { init(kmf.keyManagers, null, null) }
        ctx.serverSocketFactory.createServerSocket(0, 50, InetAddress.getByName("127.0.0.1")) as SSLServerSocket
    }
    val port: Int get() = sunucu.localPort
    @Volatile private var kapali = false

    init {
        Thread {
            while (!kapali) {
                val s = try { sunucu.accept() } catch (e: Exception) { break }
                Thread { try { isle(s) } catch (_: Exception) { } finally { runCatching { s.close() } } }.start()
            }
        }.also { it.isDaemon = true }.start()
    }

    private fun isle(s: Socket) {
        s.soTimeout = 15_000
        val g = BufferedInputStream(s.getInputStream())
        val baslikBayt = ByteArrayOutputStream()
        var son4 = 0
        while (true) {
            val b = g.read()
            if (b < 0) return
            baslikBayt.write(b)
            son4 = (son4 shl 8) or b
            if (son4 == 0x0d0a0d0a) break
            if (baslikBayt.size() > 16384) return
        }
        val satirlar = String(baslikBayt.toByteArray(), Charsets.ISO_8859_1).split("\r\n").filter { it.isNotEmpty() }
        val (metot, yol) = satirlar[0].split(" ")
        val basliklar = satirlar.drop(1).associate { it.substringBefore(":").trim().lowercase() to it.substringAfter(":").trim() }
        val uzun = basliklar["content-length"]?.toInt() ?: 0
        val govde = ByteArray(uzun)
        var okunan = 0
        while (okunan < uzun) {
            val n = g.read(govde, okunan, uzun - okunan)
            if (n < 0) return
            okunan += n
        }
        val c = mantik.isle(PcMantik.Istek(metot, yol, basliklar, govde)) ?: return // bağlantıyı yanıtsız kes
        val o = s.getOutputStream()
        val durum = mapOf(200 to "OK", 201 to "Created", 400 to "Bad Request", 401 to "Unauthorized", 403 to "Forbidden", 409 to "Conflict", 422 to "Unprocessable Entity")[c.kod] ?: "X"
        val h = StringBuilder("HTTP/1.1 ${c.kod} $durum\r\nConnection: close\r\nContent-Length: ${c.govde.size}\r\n")
        c.baslik.forEach { (k, v) -> h.append("$k: $v\r\n") }
        h.append("\r\n")
        o.write(h.toString().toByteArray(Charsets.ISO_8859_1))
        o.write(c.govde)
        o.flush()
    }

    override fun close() {
        kapali = true
        runCatching { sunucu.close() }
    }
}
