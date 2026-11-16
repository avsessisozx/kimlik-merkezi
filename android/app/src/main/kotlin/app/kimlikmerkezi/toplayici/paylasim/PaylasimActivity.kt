package app.kimlikmerkezi.toplayici.paylasim

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import app.kimlikmerkezi.toplayici.R
import app.kimlikmerkezi.toplayici.depo
import app.kimlikmerkezi.toplayici.giden.GidenKutusu

/** Paylaş menüsü hedefi: ayrı ekran yok; kaydeder, kısa bildirim gösterir, kapanır. */
class PaylasimActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val depo = applicationContext.depo
        depo.gunluk.adim("paylasim hedefi")
        val metin = intent?.takeIf { it.action == Intent.ACTION_SEND }?.getCharSequenceExtra(Intent.EXTRA_TEXT)?.toString()
        if (metin.isNullOrBlank()) {
            Toast.makeText(this, R.string.paylasim_bos, Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        val baslik = intent.getStringExtra(Intent.EXTRA_SUBJECT)
        val kaynak = arayanPaket()
        Thread {
            var kisaltildi = false
            val ok = try {
                val s = PaylasimAyristir.ayristir(metin, baslik, kaynak)
                kisaltildi = GidenKutusu.kisalt(s.metin, GidenKutusu.METIN_UST).second
                depo.kutu.kayitEkle(s.tur, "notlar", s.metin, s.yuk)
                true
            } catch (e: Exception) {
                depo.gunluk.hata("paylasim", e)
                false
            }
            runOnUiThread {
                Toast.makeText(this, if (ok && kisaltildi) R.string.paylasim_kisaltildi else if (ok) R.string.paylasim_kaydedildi else R.string.paylasim_hata, Toast.LENGTH_SHORT).show()
                finish()
            }
        }.start()
    }

    /** Arayan uygulamanın paket adı (referrer); alınamazsa null. Kendi paketimiz sayılmaz. */
    private fun arayanPaket(): String? {
        val host = referrer?.takeIf { it.scheme == "android-app" }?.host
        return host?.takeIf { it.isNotBlank() && it != packageName }
    }
}
