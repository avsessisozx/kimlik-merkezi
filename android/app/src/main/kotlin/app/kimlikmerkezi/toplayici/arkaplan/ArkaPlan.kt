package app.kimlikmerkezi.toplayici.arkaplan

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import app.kimlikmerkezi.toplayici.depo
import java.util.concurrent.TimeUnit

/** Arka plan gönderimi (bildirimsiz) en iyi çabadır (üretici pil kısıtlamaları garanti vermez). */
object ArkaPlan {
    const val IS_ADI = "km_periyodik_gonderim"

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
}

class GonderimIsi(ctx: Context, p: WorkerParameters) : Worker(ctx, p) {
    override fun doWork(): Result {
        val depo = applicationContext.depo
        if (!depo.eslesme.eslesmis() || !depo.arkaPlanAcik) return Result.success()
        depo.gonderici.gonder { isStopped } // durdurulunca dosyalar/parçalar arasında temiz çıkış
        return Result.success()
    }
}
