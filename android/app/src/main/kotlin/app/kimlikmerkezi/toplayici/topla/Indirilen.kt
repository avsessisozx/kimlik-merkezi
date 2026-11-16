package app.kimlikmerkezi.toplayici.topla

import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.security.MessageDigest

/** Seçilen klasörden yalnız ad/boyut/mime. İçerik okunmaz. */
data class IndirilenOge(val yol: String, val ad: String, val boyut: Long, val mime: String, val degisimMs: Long)

interface IndirilenKaynagi {
    fun listele(): Sequence<IndirilenOge>
}

class IndirilenToplayici(
    private val kutu: GidenKutusu,
    private val kaynak: IndirilenKaynagi,
    private val gorulen: GorulenKumesi,
    private val ust: Int = 20_000,
) {
    fun tara(): Int {
        var yeni = 0
        for (o in kaynak.listele().take(ust)) {
            val ozet = ozet(o)
            if (gorulen.var_mi(ozet)) continue
            kutu.kayitEkle(
                "indirilen.dosya", "dosyalar", o.ad,
                buildJsonObject { put("ad", o.ad); put("boyut", o.boyut); put("mime", o.mime) },
            )
            gorulen.ekle(ozet)
            yeni++
        }
        return yeni
    }

    companion object {
        fun ozet(o: IndirilenOge): String =
            MessageDigest.getInstance("SHA-256").digest("${o.yol}|${o.boyut}|${o.degisimMs}".toByteArray())
                .take(16).joinToString("") { "%02x".format(it) }
    }
}
