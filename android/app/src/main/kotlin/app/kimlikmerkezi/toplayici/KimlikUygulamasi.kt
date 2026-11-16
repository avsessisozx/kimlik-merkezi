package app.kimlikmerkezi.toplayici

import android.app.Application
import android.content.Context
import android.os.Build
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import app.kimlikmerkezi.toplayici.giden.CihazBilgisi
import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.giden.KeystoreAnahtar
import app.kimlikmerkezi.toplayici.gunluk.Gunluk
import app.kimlikmerkezi.toplayici.gunluk.HataRaporu
import java.io.File
import java.util.UUID

/** Uygulama genelindeki tekil nesneler. */
class Depo(ctx: Context) {
    private val tercihler = ctx.getSharedPreferences("tercihler", Context.MODE_PRIVATE)

    val gunluk = Gunluk(ctx.filesDir).also { it.cokmeYakala() }

    /** İlk açılışta üretilen UUID4; yeniden kurulumda değişir. */
    val cihazId: String = tercihler.getString("cihaz_id", null) ?: UUID.randomUUID().toString().also {
        tercihler.edit().putString("cihaz_id", it).apply()
    }

    val kutu: GidenKutusu = try {
        GidenKutusu(
            File(ctx.filesDir, "giden"),
            KeystoreAnahtar.sifreleyici(),
            CihazBilgisi(cihazId, BuildConfig.VERSION_NAME, Build.VERSION.SDK_INT, Build.MODEL),
            gunluk,
        )
    } catch (e: Exception) {
        gunluk.hata("baslangic", e)
        throw e
    }

    /** Arayüzü yenilemek için artan sayaç. */
    var degisim by mutableIntStateOf(0)
        private set

    /** "sistem" | "koyu" | "acik" */
    var tema by mutableStateOf(tercihler.getString("tema", "sistem") ?: "sistem")
        private set

    init {
        kutu.dinleyici = { degisim++ }
        gunluk.bilgi("uygulama", "basladi")
    }

    fun temaSec(t: String) {
        tema = t
        tercihler.edit().putString("tema", t).apply()
    }

    fun hataRaporu(): String = HataRaporu.olustur(
        HataRaporu.Girdi(
            uygulamaSurumu = BuildConfig.VERSION_NAME,
            androidSurumu = Build.VERSION.RELEASE,
            api = Build.VERSION.SDK_INT,
            uretici = Build.MANUFACTURER,
            model = Build.MODEL,
            sonAdim = gunluk.sonAdim(),
            sonHata = gunluk.sonHata(),
            gunlukSatirlari = gunluk.sonSatirlar(50),
            bekleyenKayit = kutu.bekleyenKayitSayisi(),
            bekleyenDosya = kutu.bekleyenDosyaSayisi(),
            bozukDosya = kutu.bozukDosyaSayisi(),
        ),
    )
}

class KimlikUygulamasi : Application() {
    lateinit var depo: Depo
        private set

    override fun onCreate() {
        super.onCreate()
        depo = Depo(this)
    }
}

val Context.depo: Depo get() = (applicationContext as KimlikUygulamasi).depo
