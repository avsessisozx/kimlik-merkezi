package app.kimlikmerkezi.toplayici

import app.kimlikmerkezi.toplayici.aktarim.sha256Hex
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import java.io.ByteArrayOutputStream
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

/**
 * PC alıcısının (AKTARIM §3, §7) test için sahte MANTIĞI: ağdan bağımsız. Hem bellek içi istemci
 * hem de gerçek TLS soket sunucusu bunu çağırır. YALNIZ TEST.
 */
class PcMantik(val anahtar: String = "ab".repeat(32), val eslesmeKodu: String = "TEK-KULLANIMLIK-KOD") {
    class Istek(val metot: String, val yol: String, val baslik: Map<String, String>, val govde: ByteArray)
    class Cevap(val kod: Int, val baslik: Map<String, String> = emptyMap(), val govde: ByteArray = ByteArray(0))

    @Volatile var zorla401 = false
    @Volatile var zorla422 = false
    /** Sonraki bu kadar PUT için bağlantı kesilir (yanıt yok; parça kaydedilmez). */
    val kesilecekPut = AtomicInteger(0)
    /** putSayisi bunu aşınca (her PUT) bağlantı kesilir. */
    @Volatile var izinVerilenPut = Int.MAX_VALUE
    /** Kimlik denetiminden sonra /giden/ altındaki her isteğe bu kod döner (PC meşgul/yer yok benzetimi). */
    @Volatile var zorlaKod: Int? = null
    /** İlk PUT geldikten sonra HEAD bu kodu döner. */
    @Volatile var putSonrasiHeadKodu: Int? = null
    /** Son parçada bu kadar kez `422 X-Durum: yok` (toplam değişti) döner ve kısmi dosyayı siler. */
    val yok422 = AtomicInteger(0)
    /** Eşleştirmede 400 dön. */
    @Volatile var eslestir400 = false
    @Volatile var sonEslestirGovde: String? = null
    val istekSayisi = AtomicInteger()
    val putSayisi = AtomicInteger()
    val putBoyutlari = java.util.Collections.synchronizedList(ArrayList<Int>())
    val tamamlanan = ConcurrentHashMap<String, ByteArray>()
    val kismi = ConcurrentHashMap<String, ByteArrayOutputStream>()
    private var kodKullanildi = false

    /** null: bağlantı kesilmeli. */
    fun isle(i: Istek): Cevap? {
        istekSayisi.incrementAndGet()
        if (i.metot == "GET" && i.yol == "/durum") return json(200, """{"protokol":1}""")
        if (i.metot == "POST" && i.yol == "/eslestir") return eslestir(i)
        val m = Regex("/giden/([0-9a-f-]{36})/([0-9a-f-]{36})\\.jsonl").matchEntire(i.yol) ?: return Cevap(400)
        if (zorla401 || i.baslik["authorization"] != "Bearer $anahtar" || i.baslik["x-cihaz"].isNullOrEmpty()) return Cevap(401)
        if (i.baslik["x-cihaz"] != m.groupValues[1]) return Cevap(403)
        zorlaKod?.let { return Cevap(it) }
        if (i.metot == "HEAD" && putSayisi.get() > 0) putSonrasiHeadKodu?.let { return Cevap(it) }
        val dosya = m.groupValues[2]
        val alinan = kismi[dosya]?.size()?.toLong() ?: 0L
        return when (i.metot) {
            "HEAD" -> when {
                tamamlanan.containsKey(dosya) -> Cevap(200, mapOf("X-Durum" to "var", "X-Alinan" to "0"))
                alinan > 0 -> Cevap(200, mapOf("X-Durum" to "kismi", "X-Alinan" to alinan.toString()))
                else -> Cevap(200, mapOf("X-Durum" to "yok", "X-Alinan" to "0"))
            }
            "PUT" -> put(i, dosya, alinan)
            else -> Cevap(405)
        }
    }

    private fun json(kod: Int, s: String) = Cevap(kod, mapOf("Content-Type" to "application/json"), s.toByteArray())

    private fun eslestir(i: Istek): Cevap {
        sonEslestirGovde = String(i.govde)
        if (eslestir400) return Cevap(400)
        val o = try { Json.parseToJsonElement(String(i.govde)) as JsonObject } catch (e: Exception) { return Cevap(400) }
        val gecerli = o["kod"]?.jsonPrimitive?.content == eslesmeKodu && !kodKullanildi &&
            o["platform"]?.jsonPrimitive?.content == "android" && !o["cihaz_id"]?.jsonPrimitive?.content.isNullOrEmpty()
        if (!gecerli) return Cevap(401)
        kodKullanildi = true
        return json(200, """{"cihaz_anahtari":"$anahtar"}""")
    }

    private fun put(i: Istek, dosya: String, alinan: Long): Cevap? {
        putSayisi.incrementAndGet()
        if (tamamlanan.containsKey(dosya)) return Cevap(200, mapOf("X-Durum" to "var"))
        if (putSayisi.get() > izinVerilenPut) return null
        if (kesilecekPut.get() > 0) {
            kesilecekPut.decrementAndGet()
            return null
        }
        val r = Regex("bytes (\\d+)-(\\d+)/(\\d+)").matchEntire(i.baslik["content-range"] ?: "") ?: return Cevap(400)
        val (bas, son, toplam) = r.destructured.toList().map { it.toLong() }
        if (son - bas + 1 != i.govde.size.toLong()) return Cevap(400)
        if (bas != alinan) return Cevap(409, mapOf("X-Alinan" to alinan.toString()))
        putBoyutlari.add(i.govde.size)
        val k = kismi.getOrPut(dosya) { ByteArrayOutputStream() }
        k.write(i.govde)
        if (k.size().toLong() < toplam) return Cevap(200, mapOf("X-Durum" to "kismi", "X-Alinan" to k.size().toString()))
        val tum = k.toByteArray()
        kismi.remove(dosya)
        if (yok422.get() > 0) { yok422.decrementAndGet(); return Cevap(422, mapOf("X-Durum" to "yok")) }
        if (zorla422 || tum.sha256Hex() != i.baslik["x-sha256"] || !gecerliDosya(tum)) return Cevap(422)
        tamamlanan[dosya] = tum
        return Cevap(201, mapOf("X-Durum" to "var"))
    }

    private fun gecerliDosya(b: ByteArray): Boolean = try {
        val s = String(b, Charsets.UTF_8)
        val satirlar = s.dropLast(1).split("\n").map { Json.parseToJsonElement(it) as JsonObject }
        val son = satirlar.last()
        s.endsWith("\n") && son["kapanis"]?.jsonPrimitive?.booleanOrNull == true &&
            son["kayit_sayisi"]?.jsonPrimitive?.intOrNull == satirlar.size - 2
    } catch (e: Exception) {
        false
    }
}
