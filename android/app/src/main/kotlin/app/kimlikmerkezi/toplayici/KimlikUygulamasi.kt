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
import app.kimlikmerkezi.toplayici.aktarim.AdresSuzgeci
import app.kimlikmerkezi.toplayici.aktarim.BaglantiUretici
import app.kimlikmerkezi.toplayici.aktarim.EslesmeDeposu
import app.kimlikmerkezi.toplayici.aktarim.Eslestirici
import app.kimlikmerkezi.toplayici.aktarim.Gonderici
import app.kimlikmerkezi.toplayici.aktarim.HttpsBaglanti
import app.kimlikmerkezi.toplayici.arkaplan.ArkaPlan
import app.kimlikmerkezi.toplayici.giden.AesGcmSifreleyici
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

    val eslesme = EslesmeDeposu(depolama, AesGcmSifreleyici(KeystoreAnahtar.al("km_eslesme_v1")))

    init {
        eslesme.kaldirinca = { ArkaPlan.planla(ctx.applicationContext, false) }
    }

    val gonderici = Gonderici(
        kutu, eslesme, depolama, gunluk,
        BaglantiUretici { a, p -> HttpsBaglanti(a, p, eslesme.parmakIzi() ?: error("eslesme yok")) },
        { cihazId },
    )

    val eslestirici = Eslestirici({ pin -> BaglantiUretici { a, p -> HttpsBaglanti(a, p, pin) } }, eslesme)

    /** Arka plan gönderimi (varsayılan açık). */
    var arkaPlanAcik: Boolean
        get() = depolama.mantik("arka_plan_kapali", false).not()
        set(v) { depolama.yazMantik("arka_plan_kapali", !v); ayarDegisti() }

    /** "PC'ye gönder": arka iş parçacığında, tek seferde bir gönderim. */
    fun gonder() {
        Thread {
            try { gonderici.gonder() } catch (e: Exception) { gunluk.hata("gonder", e) }
            ayarDegisti()
        }.start()
    }

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
            eslesme = eslesme.eslesmis(),
            yerelAdres = eslesme.adresler().any { AdresSuzgeci.yerelMi(it) },
            sonGonderimKodu = gonderici.sonKod(),
            reddedilenDosya = gonderici.reddedilenSayisi(),
            sonBasariMs = gonderici.sonBasariMs(),
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
