package app.kimlikmerkezi.toplayici.aktarim

import app.kimlikmerkezi.toplayici.giden.Sifreleyici
import app.kimlikmerkezi.toplayici.topla.Depolama
import java.util.Base64

/** Eşleştirilen PC: adresler/port/parmak izi tercihlerde, cihaz anahtarı Keystore ile şifreli. */
class EslesmeDeposu(private val d: Depolama, private val sifreleyici: Sifreleyici) {
    private val aad = "km-eslesme-anahtar".toByteArray()

    fun eslesmis(): Boolean = anahtar() != null && parmakIzi() != null && adresler().isNotEmpty()

    fun adresler(): List<String> = d.metin(ADRESLER)?.split(',')?.filter { it.isNotBlank() }.orEmpty()
    fun port(): Int = d.uzun(PORT, 47821).toInt()
    fun parmakIzi(): String? = d.metin(PARMAK)
    fun pcAdi(): String = d.metin(PC_ADI) ?: ""

    fun anahtar(): String? = d.metin(ANAHTAR)?.let {
        try {
            String(sifreleyici.coz(Base64.getDecoder().decode(it), aad), Charsets.UTF_8)
        } catch (e: Exception) {
            null
        }
    }

    fun kaydet(kod: EslesmeKodu, cihazAnahtari: String) {
        d.yazMetin(ADRESLER, kod.adresler.joinToString(","))
        d.yazUzun(PORT, kod.port.toLong())
        d.yazMetin(PARMAK, kod.parmakIzi)
        d.yazMetin(PC_ADI, kod.pcAdi)
        d.yazMetin(ANAHTAR, Base64.getEncoder().encodeToString(sifreleyici.sifrele(cihazAnahtari.toByteArray(Charsets.UTF_8), aad)))
    }

    fun adresKaydet(adres: String, port: Int = port()) {
        d.yazMetin(ADRESLER, (listOf(adres) + adresler().filter { it != adres }).joinToString(","))
        d.yazUzun(PORT, port.toLong())
    }

    /** Anahtar ve adres silinir; giden kutusu kayıtlarına dokunulmaz. */
    fun kaldir() {
        listOf(ADRESLER, PARMAK, PC_ADI, ANAHTAR).forEach { d.yazMetin(it, null) }
    }

    companion object {
        const val ADRESLER = "pc_adresler"
        const val PORT = "pc_port"
        const val PARMAK = "pc_parmak"
        const val PC_ADI = "pc_adi"
        const val ANAHTAR = "pc_anahtar_sifreli"
    }
}

sealed class EslesmeSonucu {
    object Tamam : EslesmeSonucu()
    object KodGecersiz : EslesmeSonucu()
    object SertifikaUyusmadi : EslesmeSonucu()
    object Ulasilamadi : EslesmeSonucu()
    object Beklenmeyen : EslesmeSonucu()
}

/** `POST /eslestir` (AKTARIM §2). */
class Eslestirici(private val ureticiFabrikasi: (parmakIzi: String) -> BaglantiUretici, private val depo: EslesmeDeposu) {
    fun eslestir(kod: EslesmeKodu, cihazId: String, model: String): EslesmeSonucu {
        val govde = kotlinx.serialization.json.buildJsonObject {
            put("cihaz_id", kotlinx.serialization.json.JsonPrimitive(cihazId))
            put("ad", kotlinx.serialization.json.JsonPrimitive(model))
            put("platform", kotlinx.serialization.json.JsonPrimitive("android"))
            put("model", kotlinx.serialization.json.JsonPrimitive(model))
            put("kod", kotlinx.serialization.json.JsonPrimitive(kod.gizli))
        }.toString().toByteArray(Charsets.UTF_8)
        var ulasildi = false
        for (a in kod.adresler) {
            val y = try {
                ureticiFabrikasi(kod.parmakIzi).ac(a, kod.port).eslestir(govde)
            } catch (e: Exception) {
                if (e.sertifikaHatasiMi()) return EslesmeSonucu.SertifikaUyusmadi
                continue
            }
            ulasildi = true
            if (y.kod in 200..201) {
                val anahtar = try {
                    (kotlinx.serialization.json.Json.parseToJsonElement(String(y.govde, Charsets.UTF_8)) as kotlinx.serialization.json.JsonObject)["cihaz_anahtari"]
                        ?.let { (it as kotlinx.serialization.json.JsonPrimitive).content }
                } catch (e: Exception) {
                    null
                }
                if (anahtar == null || !Regex("[0-9a-f]{64}").matches(anahtar)) return EslesmeSonucu.Beklenmeyen
                depo.kaydet(kod, anahtar)
                return EslesmeSonucu.Tamam
            }
            return if (y.kod in 400..499) EslesmeSonucu.KodGecersiz else EslesmeSonucu.Beklenmeyen
        }
        return if (ulasildi) EslesmeSonucu.Beklenmeyen else EslesmeSonucu.Ulasilamadi
    }
}
