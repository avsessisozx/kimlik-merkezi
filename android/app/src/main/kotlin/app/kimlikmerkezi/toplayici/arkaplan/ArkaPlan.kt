package app.kimlikmerkezi.toplayici.arkaplan

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import app.kimlikmerkezi.toplayici.R
import app.kimlikmerkezi.toplayici.aktarim.AktarimDurumu
import app.kimlikmerkezi.toplayici.depo
import java.util.concurrent.TimeUnit

/** Arka plan gönderimi en iyi çabadır (üretici pil kısıtlamaları garanti vermez). */
object ArkaPlan {
    const val IS_ADI = "km_periyodik_gonderim"
    const val KANAL = "gonderim"

    /** Açıksa periyodik iş (en sık aralık 15 dk, sınırsız ağ, pil düşük değil); kapalıysa iptal. */
    fun planla(ctx: Context, ac: Boolean) {
        val wm = WorkManager.getInstance(ctx)
        if (!ac) { wm.cancelUniqueWork(IS_ADI); return }
        val kisit = Constraints.Builder().setRequiredNetworkType(NetworkType.UNMETERED).setRequiresBatteryNotLow(true).build()
        wm.enqueueUniquePeriodicWork(
            IS_ADI, ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<GonderimIsi>(15, TimeUnit.MINUTES).setConstraints(kisit).build(),
        )
    }

    /** Tek, sessiz, düşük öncelikli bildirim. Bildirim izni/ayarı kapalıysa atlanır (izin İSTENMEZ). */
    fun bildir(ctx: Context, dosya: Int) {
        if (Build.VERSION.SDK_INT >= 33 && ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val nm = NotificationManagerCompat.from(ctx)
        if (!nm.areNotificationsEnabled()) return
        (ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(
            NotificationChannel(KANAL, ctx.getString(R.string.bildirim_kanal), NotificationManager.IMPORTANCE_LOW).apply { setSound(null, null) },
        )
        val b = NotificationCompat.Builder(ctx, KANAL)
            .setSmallIcon(R.drawable.ic_bildirim)
            .setContentTitle(ctx.getString(R.string.bildirim_baslik))
            .setContentText(ctx.getString(R.string.bildirim_metin, dosya))
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setSilent(true)
            .setAutoCancel(true)
            .build()
        @Suppress("MissingPermission")
        nm.notify(1, b)
    }
}

class GonderimIsi(ctx: Context, p: WorkerParameters) : Worker(ctx, p) {
    override fun doWork(): Result {
        val depo = applicationContext.depo
        if (!depo.eslesme.eslesmis() || !depo.arkaPlanAcik) return Result.success()
        val s = depo.gonderici.gonder()
        if (s is AktarimDurumu.Tamam && s.dosya > 0) ArkaPlan.bildir(applicationContext, s.dosya)
        return Result.success()
    }
}
