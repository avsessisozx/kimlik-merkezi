package app.kimlikmerkezi.toplayici.topla

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import app.kimlikmerkezi.toplayici.depo
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.concurrent.Executors

/**
 * Hangi ekran metinleri yazılsın: kendi uygulamamız yok, aynı uygulamadan en çok [aralikMs]'de bir,
 * aynı metin tekrar yok, en çok [azami] karakter. Saf mantık; JVM'de test edilir.
 */
class EkranMetniSuzgeci(
    private val kendiPaket: String,
    private val aralikMs: Long = 5_000,
    private val azami: Int = 2_000,
) {
    private val sonZaman = HashMap<String, Long>()
    private val sonMetin = HashMap<String, Int>()

    fun kabul(paket: String?, metin: String, simdiMs: Long): String? {
        if (paket == null || paket == kendiPaket) return null
        val t = metin.replace(Regex("\\s+"), " ").trim()
        if (t.length < 3) return null
        val kes = if (t.length > azami) t.substring(0, azami) else t
        val onceki = sonZaman[paket]
        if (onceki != null && simdiMs - onceki < aralikMs) return null
        val h = kes.hashCode()
        if (sonMetin[paket] == h) return null
        sonZaman[paket] = simdiMs
        sonMetin[paket] = h
        return kes
    }
}

/**
 * Ekrandaki yazıları okur (erişilebilirlik hizmeti). Kullanıcı sistem ekranından hizmeti açmadıkça ve uygulamada
 * "Ekran metni" anahtarını açmadıkça hiçbir şey yazılmaz. Parola alanları ve kendi uygulamamız atlanır.
 */
class EkranMetniServisi : AccessibilityService() {
    private val yazici = Executors.newSingleThreadExecutor()
    private var suzgec: EkranMetniSuzgeci? = null

    override fun onAccessibilityEvent(e: AccessibilityEvent?) {
        if (e == null) return
        val depo = try { applicationContext.depo } catch (_: Exception) { return }
        if (!depo.yonetici.ayarlar.acik(ToplayiciAyarlari.Ad.EKRAN)) return
        val s = suzgec ?: EkranMetniSuzgeci(packageName).also { suzgec = it }
        val paket = e.packageName?.toString()
        if (paket == packageName) return
        val kok = rootInActiveWindow ?: return
        val toplam = StringBuilder()
        try { topla(kok, toplam, 0) } finally { kok.recycle() }
        val metin = s.kabul(paket, toplam.toString(), System.currentTimeMillis()) ?: return
        yazici.execute {
            try {
                depo.kutu.kayitEkle(
                    "ekran.metin", "mesaj", metin,
                    buildJsonObject { put("paket", paket ?: "") },
                )
            } catch (ex: Exception) {
                depo.gunluk.hata("ekran_metni", ex)
            }
        }
    }

    private fun topla(n: AccessibilityNodeInfo, sb: StringBuilder, derinlik: Int) {
        if (derinlik > 30 || sb.length > 6_000) return
        if (!n.isPassword && n.isVisibleToUser) {
            val t = n.text?.toString()
            if (!t.isNullOrBlank()) sb.append(t).append(' ')
        }
        for (i in 0 until n.childCount) {
            val c = n.getChild(i) ?: continue
            try { topla(c, sb, derinlik + 1) } finally { c.recycle() }
        }
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        yazici.shutdown()
        super.onDestroy()
    }
}
