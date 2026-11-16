package app.kimlikmerkezi.toplayici.topla

import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.giden.YeniKayit
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.security.MessageDigest
import java.time.Instant

enum class MedyaTuru(val anahtar: String, val kayitTuru: String) {
    FOTO("foto", "medya.foto"),
    VIDEO("video", "medya.video"),
}

/** MediaStore satırından yalnız metadata. Dosya içeriği YOKTUR. */
data class MedyaOge(
    val tur: MedyaTuru,
    val id: Long,
    val ad: String,
    val boyut: Long,
    val mime: String,
    val genislik: Int?,
    val yukseklik: Int?,
    val sureMs: Long?,
    val cekimMs: Long?,
    /** MediaStore DATE_ADDED (saniye). */
    val eklenmeSn: Long,
) {
    /** Kararlı kimlik: yeniden kurulumda aynı medya aynı değeri üretir (PC tekilleştirir). */
    fun medyaId(): String {
        val ozet = MessageDigest.getInstance("SHA-256").digest("${tur.anahtar}|$id|$eklenmeSn|$boyut".toByteArray())
        return ozet.take(16).joinToString("") { "%02x".format(it) }
    }
}

interface MedyaKaynagi {
    /** (eklenmeSn, id) sırasına göre, verilen imleçten SONRAKİ en çok [sinir] öğe. */
    fun sonrasi(tur: MedyaTuru, eklenmeSn: Long, id: Long, sinir: Int): List<MedyaOge>
}

interface KonumOkuyucu {
    /** (enlem, boylam) ya da yok/okunamaz ise null. YALNIZ konum ayarı açıkken çağrılır. */
    fun oku(oge: MedyaOge): Pair<Double, Double>?
}

/**
 * Artımlı medya taraması. Her tür için imleç (date_added, _id) tercihlerde durur; aynı öğe iki kez kayıt üretmez.
 * Konum taraması AYRI imleçle yürür: `medya.foto` kaydında GPS alanı hiç olmaz.
 */
class MedyaToplayici(
    private val kutu: GidenKutusu,
    private val kaynak: MedyaKaynagi,
    private val konum: KonumOkuyucu,
    private val d: Depolama,
) {
    /** Yeni foto ve video kaydı sayısı. */
    fun taraMedya(): Int = MedyaTuru.entries.sumOf { t ->
        gez(t, t.anahtar) { o ->
            YeniKayit(
                o.tur.kayitTuru, "medya_meta", o.ad,
                buildJsonObject {
                    put("ad", o.ad)
                    put("boyut", o.boyut)
                    put("mime", o.mime)
                    o.genislik?.let { put("genislik", it) }
                    o.yukseklik?.let { put("yukseklik", it) }
                    if (o.tur == MedyaTuru.VIDEO) o.sureMs?.let { put("sure_ms", it) }
                    o.cekimMs?.let { put("cekim_zamani", ISO(it)) }
                    put("medya_id", o.medyaId())
                },
            )
        }
    }

    /** Yeni `medya.konum` kaydı sayısı (yalnız fotoğraflar). Çağıran ayarı ve izni denetler. */
    fun taraKonum(): Int = gez(MedyaTuru.FOTO, "konum") { o ->
        val k = konum.oku(o) ?: return@gez null
        YeniKayit(
            "medya.konum", "konum", o.ad + " konumu",
            buildJsonObject {
                put("enlem", k.first)
                put("boylam", k.second)
                put("medya_id", o.medyaId())
            },
        )
    }

    /** Her parti (<= 200) tek fsync ile yazılır; imleç YALNIZ parti diske yazıldıktan sonra ilerler. */
    private fun gez(tur: MedyaTuru, anahtar: String, kayitYap: (MedyaOge) -> YeniKayit?): Int {
        var eklenme = d.uzun("${anahtar}_eklenme")
        var id = d.uzun("${anahtar}_id")
        var yazilan = 0
        while (true) {
            val parti = kaynak.sonrasi(tur, eklenme, id, PARTI)
            if (parti.isEmpty()) break
            val kayitlar = parti.mapNotNull(kayitYap)
            if (kayitlar.isNotEmpty()) kutu.kayitlariEkle(kayitlar)
            yazilan += kayitlar.size
            val son = parti.last()
            eklenme = son.eklenmeSn
            id = son.id
            d.yazUzun("${anahtar}_eklenme", eklenme)
            d.yazUzun("${anahtar}_id", id)
        }
        return yazilan
    }

    companion object {
        const val PARTI = 200

        fun ISO(ms: Long): String = GidenKutusu.ISO.format(Instant.ofEpochMilli(ms))
    }
}
