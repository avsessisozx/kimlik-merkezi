package app.kimlikmerkezi.toplayici.topla

import android.content.SharedPreferences
import java.io.File

/** Küçük anahtar-değer deposu (tercihler). Birim testte bellekteki sürüm kullanılır. */
interface Depolama {
    fun uzun(anahtar: String, varsayilan: Long = 0L): Long
    fun yazUzun(anahtar: String, deger: Long)
    fun mantik(anahtar: String, varsayilan: Boolean = false): Boolean
    fun yazMantik(anahtar: String, deger: Boolean)
    fun metin(anahtar: String): String?
    fun yazMetin(anahtar: String, deger: String?)
}

class BellekDepolama : Depolama {
    private val m = java.util.concurrent.ConcurrentHashMap<String, Any>()
    override fun uzun(anahtar: String, varsayilan: Long) = m[anahtar] as? Long ?: varsayilan
    override fun yazUzun(anahtar: String, deger: Long) { m[anahtar] = deger }
    override fun mantik(anahtar: String, varsayilan: Boolean) = m[anahtar] as? Boolean ?: varsayilan
    override fun yazMantik(anahtar: String, deger: Boolean) { m[anahtar] = deger }
    override fun metin(anahtar: String) = m[anahtar] as? String
    override fun yazMetin(anahtar: String, deger: String?) { if (deger == null) m.remove(anahtar) else m[anahtar] = deger }
}

class TercihDepolama(private val t: SharedPreferences) : Depolama {
    override fun uzun(anahtar: String, varsayilan: Long) = t.getLong(anahtar, varsayilan)
    override fun yazUzun(anahtar: String, deger: Long) = t.edit().putLong(anahtar, deger).apply()
    override fun mantik(anahtar: String, varsayilan: Boolean) = t.getBoolean(anahtar, varsayilan)
    override fun yazMantik(anahtar: String, deger: Boolean) = t.edit().putBoolean(anahtar, deger).apply()
    override fun metin(anahtar: String) = t.getString(anahtar, null)
    override fun yazMetin(anahtar: String, deger: String?) = t.edit().putString(anahtar, deger).apply()
}

/** Daha önce kayda geçen öğelerin özetleri (indirilenler için). */
interface GorulenKumesi {
    fun var_mi(ozet: String): Boolean
    fun ekle(ozet: String)
}

class BellekGorulen : GorulenKumesi {
    private val k = HashSet<String>()
    override fun var_mi(ozet: String) = ozet in k
    override fun ekle(ozet: String) { k.add(ozet) }
}

/** Satır başına bir özet; ekleme yalnız sona yazılır. */
class DosyaGorulen(private val dosya: File) : GorulenKumesi {
    private val k = HashSet<String>().also { s -> if (dosya.exists()) dosya.forEachLine { if (it.isNotBlank()) s.add(it) } }
    override fun var_mi(ozet: String) = ozet in k
    override fun ekle(ozet: String) {
        if (k.add(ozet)) dosya.appendText(ozet + "\n")
    }
}

/** Toplayıcı ayar anahtarları ve açma/kapama kuralları. Varsayılan hepsi KAPALI. */
class ToplayiciAyarlari(private val d: Depolama) {
    enum class Ad(val anahtar: String) {
        MEDYA("medya_acik"), KONUM("konum_acik"), INDIRILEN("indirilen_acik"), KULLANIM("kullanim_acik")
    }

    fun acik(a: Ad) = d.mantik(a.anahtar, false)
    fun ayarla(a: Ad, acik: Boolean) = d.yazMantik(a.anahtar, acik)

    /** İzin isteği sonucu: verilmediyse anahtar kapalıya döner. Yeni durumu döner. */
    fun izinSonucu(a: Ad, verildi: Boolean): Boolean {
        ayarla(a, verildi)
        return verildi
    }

    fun herhangiAcik() = Ad.entries.any { acik(it) }
}
