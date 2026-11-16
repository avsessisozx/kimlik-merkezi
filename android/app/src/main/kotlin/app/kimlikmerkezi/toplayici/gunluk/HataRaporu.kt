package app.kimlikmerkezi.toplayici.gunluk

/** "Hata raporunu kopyala" metni. Kayıt METNİ ASLA girmez; yalnız sayılar ve günlük satırları. */
object HataRaporu {
    class Girdi(
        val uygulamaSurumu: String,
        val androidSurumu: String,
        val api: Int,
        val uretici: String,
        val model: String,
        val sonAdim: String?,
        val sonHata: SonHata?,
        val gunlukSatirlari: List<String>,
        val bekleyenKayit: Int,
        val bekleyenDosya: Int,
        val bozukDosya: Int = 0,
    )

    fun olustur(g: Girdi): String = buildString {
        appendLine("Kimlik Merkezi Toplayıcı - hata raporu")
        appendLine("Uygulama sürümü: ${g.uygulamaSurumu}")
        appendLine("Android: ${g.androidSurumu} (API ${g.api})")
        appendLine("Cihaz: ${g.uretici} ${g.model}")
        appendLine("Son adım: ${g.sonAdim ?: "-"}")
        val h = g.sonHata
        if (h == null) {
            appendLine("Son hata: yok")
        } else {
            appendLine("Son hata: ${h.tur} [kod: ${h.kod}]${if (h.cokme) " (uygulama çöktü)" else ""} [${h.zaman}]")
        }
        appendLine("Giden kutusu: ${g.bekleyenKayit} kayıt, ${g.bekleyenDosya} dosya, ${g.bozukDosya} bozuk dosya")
        appendLine("Son ${g.gunlukSatirlari.size} günlük satırı:")
        g.gunlukSatirlari.takeLast(50).forEach { appendLine(it) }
    }
}
