package app.kimlikmerkezi.toplayici.topla

import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.LocalDate
import java.time.ZoneId

interface KullanimKaynagi {
    /** [basMs, sonMs) aralığında paket -> ön planda kalma süresi (ms). */
    fun gunKullanimi(basMs: Long, sonMs: Long): Map<String, Long>
    fun ad(paket: String): String?
}

/** Yalnız TAMAMLANMIŞ günler (bugün yazılmaz); her (gün, paket) bir kez; ilk açılışta en çok son 7 gün. */
class KullanimToplayici(
    private val kutu: GidenKutusu,
    private val kaynak: KullanimKaynagi,
    private val d: Depolama,
    private val bugun: () -> LocalDate = { LocalDate.now() },
    private val bolge: () -> ZoneId = { ZoneId.systemDefault() },
    private val kendiPaket: String? = null,
) {
    fun tara(): Int {
        val b = bugun()
        val son = d.uzun(SON_GUN, Long.MIN_VALUE)
        val ilk = if (son == Long.MIN_VALUE) b.toEpochDay() - 7 else maxOf(son + 1, b.toEpochDay() - 7)
        var yeni = 0
        var gun = ilk
        while (gun < b.toEpochDay()) {
            val tarih = LocalDate.ofEpochDay(gun)
            val z = bolge()
            val bas = tarih.atStartOfDay(z).toInstant().toEpochMilli()
            val bit = tarih.plusDays(1).atStartOfDay(z).toInstant().toEpochMilli()
            for ((paket, sure) in kaynak.gunKullanimi(bas, bit).toSortedMap()) {
                if (sure <= 0 || paket == kendiPaket) continue
                val ad = kaynak.ad(paket)
                kutu.kayitEkle(
                    "uygulama.kullanim", "uygulama", ad ?: paket,
                    buildJsonObject {
                        put("paket", paket)
                        if (ad != null) put("ad", ad)
                        put("gun", tarih.toString())
                        put("sure_ms", sure)
                    },
                )
                yeni++
            }
            d.yazUzun(SON_GUN, gun)
            gun++
        }
        return yeni
    }

    companion object {
        const val SON_GUN = "kullanim_son_gun"
    }
}
