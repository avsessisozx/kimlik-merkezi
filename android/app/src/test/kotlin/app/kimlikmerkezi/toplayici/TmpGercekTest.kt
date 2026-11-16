package app.kimlikmerkezi.toplayici

import app.kimlikmerkezi.toplayici.aktarim.*
import org.junit.Test
import java.io.File

class TmpGercekTest {
    @Test
    fun dene() {
        val yol = System.getenv("KM_KOD") ?: return
        AdresSuzgeci.testLoopback = true
        val k = EslesmeKodu.coz(File(yol).readText())!!
        val b = HttpsBaglanti("127.0.0.1", k.port, k.parmakIzi)
        val cihaz = java.util.UUID.randomUUID().toString()
        val govde = """{"cihaz_id":"$cihaz","ad":"x","platform":"android","model":"x","kod":"${k.gizli}"}""".toByteArray()
        val y = b.eslestir(govde); println("eslestir ${y.kod}")
        val key = Regex("[0-9a-f]{64}").find(String(y.govde))!!.value
        for (i in 1..8) {
            try { println("durum $i ${b.durum().kod}"); println("head $i ${b.head(cihaz, java.util.UUID.randomUUID().toString(), key).kod}") }
            catch (e: Exception) { println("HATA $i ${e.javaClass.name} ${e.message}") }
        }
    }
}
