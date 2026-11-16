package app.kimlikmerkezi.toplayici.gunluk

import java.io.File
import java.time.Instant
import java.time.temporal.ChronoUnit

/** Son hatanın özeti. [cokme]: yakalanmamış hata ile süreç öldü. */
data class SonHata(val tur: String, val ileti: String, val zaman: String, val cokme: Boolean)

/**
 * Uygulama içi günlük: halka tampon (bellek) + küçük dosya. KAYIT İÇERİĞİ YAZILMAZ:
 * çağıranlar yalnız sabit ifade ve sayı verir. Hata iletileri kısaltılır, satır sonu temizlenir.
 */
class Gunluk(
    private val dizin: File?,
    private val simdi: () -> Instant = { Instant.now() },
    private val bellekSiniri: Int = 200,
) {
    private val kilit = Any()
    private val satirlar = ArrayDeque<String>()
    private var dosyadakiSatir = 0
    private val gunlukDosyasi get() = dizin?.let { File(it, "gunluk.txt") }
    private val hataDosyasi get() = dizin?.let { File(it, "son_hata.txt") }

    init {
        synchronized(kilit) {
            val f = gunlukDosyasi
            if (f != null && f.exists()) {
                val tum = f.readLines(Charsets.UTF_8)
                tum.takeLast(bellekSiniri).forEach { satirlar.addLast(it) }
                dosyadakiSatir = tum.size
            }
        }
    }

    fun bilgi(etiket: String, ileti: String) = yaz("BILGI", etiket, ileti)

    /** Kullanıcının bulunduğu adım ("ana ekran", "hızlı not kaydet" gibi sabit adlar). */
    fun adim(ad: String) = yaz("ADIM", "adim", ad)

    fun hata(etiket: String, t: Throwable, cokme: Boolean = false) {
        val tur = t.javaClass.name
        val ileti = temizle(t.message ?: "")
        yaz(if (cokme) "COKME" else "HATA", etiket, "$tur $ileti".trim())
        val z = zaman()
        hataDosyasi?.let { f ->
            runCatching { f.writeText("$tur\n$ileti\n$z\n${if (cokme) "cokme" else "hata"}\n", Charsets.UTF_8) }
        }
        synchronized(kilit) { bellekHata = SonHata(tur, ileti, z, cokme) }
    }

    @Volatile
    private var bellekHata: SonHata? = null

    fun sonHata(): SonHata? {
        bellekHata?.let { return it }
        val f = hataDosyasi ?: return null
        if (!f.exists()) return null
        return runCatching {
            val s = f.readLines(Charsets.UTF_8)
            SonHata(s[0], s[1], s[2], s[3] == "cokme")
        }.getOrNull()
    }

    fun sonSatirlar(n: Int = 50): List<String> = synchronized(kilit) { satirlar.toList().takeLast(n) }

    /** Son kaydedilen adım adı, yoksa null. */
    fun sonAdim(): String? = synchronized(kilit) {
        satirlar.lastOrNull { it.contains(" ADIM adim ") }?.substringAfter(" ADIM adim ")
    }

    /** Yakalanmamış hata olursa günlüğe ve son_hata.txt dosyasına yazıp varsayılan işleyiciye devreder. */
    fun cokmeYakala() {
        val eski = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { th, t ->
            runCatching { hata("cokme", t, cokme = true) }
            eski?.uncaughtException(th, t)
        }
    }

    private fun zaman() = simdi().truncatedTo(ChronoUnit.SECONDS).toString()

    private fun temizle(s: String): String = s.replace(Regex("[\\r\\n\\t]+"), " ").take(200)

    private fun yaz(duzey: String, etiket: String, ileti: String) {
        val satir = "${zaman()} $duzey ${temizle(etiket)} ${temizle(ileti)}"
        synchronized(kilit) {
            satirlar.addLast(satir)
            while (satirlar.size > bellekSiniri) satirlar.removeFirst()
            val f = gunlukDosyasi ?: return
            runCatching {
                if (dosyadakiSatir >= bellekSiniri * 2) {
                    f.writeText(satirlar.joinToString("\n", postfix = "\n"), Charsets.UTF_8)
                    dosyadakiSatir = satirlar.size
                } else {
                    f.appendText(satir + "\n", Charsets.UTF_8)
                    dosyadakiSatir++
                }
            }
        }
    }
}
