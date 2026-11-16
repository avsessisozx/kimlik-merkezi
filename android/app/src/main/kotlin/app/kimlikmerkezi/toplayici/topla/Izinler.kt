package app.kimlikmerkezi.toplayici.topla

import android.Manifest
import android.app.AppOpsManager
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Process

enum class MedyaIzni { YOK, KISMI, TAM }

object Izinler {
    fun medyaIzinleri(): Array<String> = when {
        Build.VERSION.SDK_INT >= 34 -> arrayOf(
            Manifest.permission.READ_MEDIA_IMAGES, Manifest.permission.READ_MEDIA_VIDEO,
            Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED,
        )
        Build.VERSION.SDK_INT >= 33 -> arrayOf(Manifest.permission.READ_MEDIA_IMAGES, Manifest.permission.READ_MEDIA_VIDEO)
        else -> arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
    }

    private fun var_mi(ctx: Context, izin: String) =
        ctx.checkSelfPermission(izin) == PackageManager.PERMISSION_GRANTED

    fun medya(ctx: Context): MedyaIzni = when {
        Build.VERSION.SDK_INT >= 34 -> when {
            var_mi(ctx, Manifest.permission.READ_MEDIA_IMAGES) && var_mi(ctx, Manifest.permission.READ_MEDIA_VIDEO) -> MedyaIzni.TAM
            var_mi(ctx, Manifest.permission.READ_MEDIA_IMAGES) || var_mi(ctx, Manifest.permission.READ_MEDIA_VIDEO) ||
                var_mi(ctx, Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED) -> MedyaIzni.KISMI
            else -> MedyaIzni.YOK
        }
        Build.VERSION.SDK_INT >= 33 ->
            if (var_mi(ctx, Manifest.permission.READ_MEDIA_IMAGES) || var_mi(ctx, Manifest.permission.READ_MEDIA_VIDEO)) MedyaIzni.TAM else MedyaIzni.YOK
        else -> if (var_mi(ctx, Manifest.permission.READ_EXTERNAL_STORAGE)) MedyaIzni.TAM else MedyaIzni.YOK
    }

    fun konum(ctx: Context) = var_mi(ctx, Manifest.permission.ACCESS_MEDIA_LOCATION)

    fun kullanimErisimi(ctx: Context): Boolean {
        val ops = ctx.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        @Suppress("DEPRECATION")
        val m = ops.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), ctx.packageName)
        return m == AppOpsManager.MODE_ALLOWED
    }

    /** Kalıcı okuma izni verilmiş kayıtlı klasör ağacı, yoksa null. */
    fun indirilenAgaci(ctx: Context, kayitli: String?): Uri? {
        if (kayitli == null) return null
        val u = Uri.parse(kayitli)
        return u.takeIf { x -> ctx.contentResolver.persistedUriPermissions.any { it.uri == x && it.isReadPermission } }
    }
}
