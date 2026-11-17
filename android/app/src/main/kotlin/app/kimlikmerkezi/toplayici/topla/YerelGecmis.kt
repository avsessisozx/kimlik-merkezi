package app.kimlikmerkezi.toplayici.topla

import app.kimlikmerkezi.toplayici.giden.KayitOzeti
import java.io.File

/**
 * Telefonda yazılan kayıtların kısa özet geçmişi. Giden kutusu PC'ye gönderilince boşalır; ana ekrandaki
 * "Son kayıtlar" ve "Toplanan veriler" bu geçmişten okunur. Yalnız özet tutulur (en çok [limit] satır).
 * Ekran metni özeti içerik taşımaz: yalnız karakter sayısı yazılır.
 */
class YerelGecmis(private val dosya: File, private val limit: Int = 500) {
    private val kilit = Any()
    private var satirlar: MutableList<String>? = null

    private fun yukle(): MutableList<String> {
        satirlar?.let { return it }
        val l = try { if (dosya.exists()) dosya.readLines().toMutableList() else mutableListOf() } catch (e: Exception) { mutableListOf() }
        satirlar = l
        return l
    }

    fun ekle(liste: List<KayitOzeti>) {
        if (liste.isEmpty()) return
        synchronized(kilit) {
            val l = yukle()
            for (k in liste) l.add(satir(k))
            while (l.size > limit) l.removeAt(0)
            try { dosya.writeText(l.joinToString("\n") + "\n") } catch (_: Exception) { /* geçmiş en iyi çaba */ }
        }
    }

    /** En yeni başta; düzenleme ile yerine geçen kayıtlar çıkarılır. */
    fun son(n: Int): List<KayitOzeti> = synchronized(kilit) {
        val hepsi = yukle().mapNotNull(::ayril)
        val degisen = hepsi.mapNotNull { it.onceki }.toSet()
        hepsi.filter { it.id !in degisen }.takeLast(n).reversed()
    }

    /** Tür başına toplam kayıt sayısı (geçmişte kalanlar). */
    fun turSayilari(): Map<String, Int> = synchronized(kilit) {
        yukle().mapNotNull(::ayril).groupingBy { it.tur }.eachCount()
    }

    companion object {
        private fun temiz(s: String) = s.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')

        fun satir(k: KayitOzeti): String {
            val ozet = if (k.tur == "ekran.metin") "(içerik gösterilmez)" else temiz(k.ozet)
            return listOf(k.id, k.ts, k.tur, k.onceki ?: "-", ozet).joinToString("\t")
        }

        fun ayril(s: String): KayitOzeti? {
            val p = s.split('\t', limit = 5)
            if (p.size < 5) return null
            return KayitOzeti(p[0], p[1], p[2], p[4], p[3].takeIf { it != "-" })
        }
    }
}
