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
import app.kimlikmerkezi.toplayici.topla.TercihDepolama
import app.kimlikmerkezi.toplayici.topla.ToplayiciYonetici
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

    val depolama = TercihDepolama(tercihler)
    val yonetici = ToplayiciYonetici(ctx, kutu, gunluk, depolama)

    /** Ayarlar ekranını yenilemek için (izin sonuçları, anahtarlar). */
    var ayarSayaci by mutableIntStateOf(0)
        private set

    /** Son tarama sonucu metni; boşsa gösterilmez. */
    var taramaDurumu by mutableStateOf("")
        private set

    fun ayarDegisti() { ayarSayaci++ }

    /** Açık toplayıcıları arka planda çalıştırır. Aynı anda tek tarama. */
    fun tara() {
        taramaDurumu = "taranıyor"
        Thread {
            val n = try { yonetici.tara() } catch (e: Exception) { gunluk.hata("tara", e); -1 }
            taramaDurumu = when {
                n == null -> "taranıyor"
                n < 0 -> "tarama başarısız"
                else -> "$n yeni kayıt"
            }
        }.start()
    }

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
