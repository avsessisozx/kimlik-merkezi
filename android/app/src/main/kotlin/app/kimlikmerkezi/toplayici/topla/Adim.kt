package app.kimlikmerkezi.toplayici.topla

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

interface AdimKaynagi {
    /** Telefonun açılışından beri toplam adım; sensör yok/okunamadıysa null. */
    fun sayac(): Long?
}

/** Her taramada son taramadan bu yana atılan adım farkını yazar. İlk tarama yalnız başlangıç değerini kaydeder. */
class AdimToplayici(
    private val kutu: GidenKutusu,
    private val kaynak: AdimKaynagi,
    private val d: Depolama,
) {
    fun tara(): Int {
        val simdi = kaynak.sayac() ?: return 0
        val onceki = d.uzun(SON, Long.MIN_VALUE)
        d.yazUzun(SON, simdi)
        if (onceki == Long.MIN_VALUE) return 0
        // Sayaç yeniden başlatmada sıfırlanır: düşüş varsa yeni değerin kendisi fark sayılır.
        val fark = if (simdi >= onceki) simdi - onceki else simdi
        if (fark <= 0) return 0
        kutu.kayitEkle(
            "sensor.adim", "uygulama", "$fark adım",
            buildJsonObject {
                put("fark", fark)
                put("sayac", simdi)
            },
        )
        return 1
    }

    companion object {
        const val SON = "adim_son_sayac"
    }
}

class AndroidAdimKaynagi(private val ctx: Context) : AdimKaynagi {
    override fun sayac(): Long? {
        val sm = ctx.getSystemService(Context.SENSOR_SERVICE) as? SensorManager ?: return null
        val sensor = sm.getDefaultSensor(Sensor.TYPE_STEP_COUNTER) ?: return null
        val kilit = CountDownLatch(1)
        var deger: Long? = null
        val dinle = object : SensorEventListener {
            override fun onSensorChanged(e: SensorEvent) {
                if (deger == null) { deger = e.values[0].toLong(); kilit.countDown() }
            }
            override fun onAccuracyChanged(s: Sensor?, a: Int) {}
        }
        return try {
            sm.registerListener(dinle, sensor, SensorManager.SENSOR_DELAY_NORMAL)
            kilit.await(3, TimeUnit.SECONDS)
            deger
        } finally {
            sm.unregisterListener(dinle)
        }
    }
}
