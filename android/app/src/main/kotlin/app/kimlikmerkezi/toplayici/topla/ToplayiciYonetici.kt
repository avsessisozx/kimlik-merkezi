package app.kimlikmerkezi.toplayici.topla

import android.content.Context
import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.gunluk.Gunluk
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

/** Açık toplayıcıları çalıştırır. İzin yoksa o toplayıcı sessizce atlanır (çökmez). */
class ToplayiciYonetici(
    private val ctx: Context,
    private val kutu: GidenKutusu,
    private val gunluk: Gunluk,
    private val depolama: Depolama,
    val ayarlar: ToplayiciAyarlari = ToplayiciAyarlari(depolama),
) {
    private val calisiyor = AtomicBoolean(false)

    /** Çalışan tarama varsa null döner. Dönen sayı: yeni yazılan kayıt. */
    fun tara(): Int? {
        if (!calisiyor.compareAndSet(false, true)) return null
        try {
            var toplam = 0
            fun dene(ad: String, f: () -> Int) {
                try { toplam += f() } catch (e: Exception) { gunluk.hata("tara_$ad", e) }
            }
            val medyaIzni = Izinler.medya(ctx)
            if (ayarlar.acik(ToplayiciAyarlari.Ad.MEDYA) && medyaIzni != MedyaIzni.YOK) {
                val mt = MedyaToplayici(kutu, AndroidMedyaKaynagi(ctx), AndroidKonumOkuyucu(ctx), depolama)
                dene("medya") { mt.taraMedya() }
            }
            if (ayarlar.acik(ToplayiciAyarlari.Ad.KONUM) && medyaIzni != MedyaIzni.YOK && Izinler.konum(ctx)) {
                val mt = MedyaToplayici(kutu, AndroidMedyaKaynagi(ctx), AndroidKonumOkuyucu(ctx), depolama)
                dene("konum") { mt.taraKonum() }
            }
            if (ayarlar.acik(ToplayiciAyarlari.Ad.INDIRILEN)) {
                val agac = Izinler.indirilenAgaci(ctx, depolama.metin(AGAC))
                if (agac != null) {
                    val t = IndirilenToplayici(kutu, SafIndirilenKaynagi(ctx, agac), DosyaGorulen(File(ctx.filesDir, "indirilen_gorulen.txt")))
                    dene("indirilen") { t.tara() }
                }
            }
            if (ayarlar.acik(ToplayiciAyarlari.Ad.KULLANIM) && Izinler.kullanimErisimi(ctx)) {
                val t = KullanimToplayici(kutu, AndroidKullanimKaynagi(ctx), depolama, kendiPaket = ctx.packageName)
                dene("kullanim") { t.tara() }
            }
            gunluk.bilgi("tara", "tamamlandi: $toplam yeni kayit")
            return toplam
        } finally {
            calisiyor.set(false)
        }
    }

    companion object {
        const val AGAC = "indirilen_agac"
        const val KULLANIM_BEKLIYOR = "kullanim_bekliyor"
    }
}
