package app.kimlikmerkezi.toplayici.topla

import android.app.usage.UsageStatsManager
import android.content.ContentResolver
import android.content.ContentUris
import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.provider.DocumentsContract
import android.provider.MediaStore
import androidx.exifinterface.media.ExifInterface

/** MediaStore'dan yalnız metadata sütunları okunur; dosya açılmaz. */
class AndroidMedyaKaynagi(private val ctx: Context) : MedyaKaynagi {
    override fun sonrasi(tur: MedyaTuru, eklenmeSn: Long, id: Long, sinir: Int): List<MedyaOge> {
        val video = tur == MedyaTuru.VIDEO
        val taban = if (video) MediaStore.Video.Media.EXTERNAL_CONTENT_URI else MediaStore.Images.Media.EXTERNAL_CONTENT_URI
        val sutunlar = arrayOf(
            MediaStore.MediaColumns._ID, MediaStore.MediaColumns.DISPLAY_NAME, MediaStore.MediaColumns.SIZE,
            MediaStore.MediaColumns.MIME_TYPE, MediaStore.MediaColumns.WIDTH, MediaStore.MediaColumns.HEIGHT,
            MediaStore.MediaColumns.DATE_ADDED, MediaStore.MediaColumns.DATE_TAKEN, MediaStore.MediaColumns.DURATION,
        )
        val args = Bundle().apply {
            putString(ContentResolver.QUERY_ARG_SQL_SELECTION, "(date_added > ?) OR (date_added = ? AND _id > ?)")
            putStringArray(
                ContentResolver.QUERY_ARG_SQL_SELECTION_ARGS,
                arrayOf(eklenmeSn.toString(), eklenmeSn.toString(), id.toString()),
            )
            putString(ContentResolver.QUERY_ARG_SQL_SORT_ORDER, "date_added ASC, _id ASC")
            putInt(ContentResolver.QUERY_ARG_LIMIT, sinir)
        }
        val sonuc = ArrayList<MedyaOge>()
        ctx.contentResolver.query(taban, sutunlar, args, null)?.use { c ->
            while (c.moveToNext()) {
                fun uz(i: Int) = if (c.isNull(i)) null else c.getLong(i)
                sonuc.add(
                    MedyaOge(
                        tur = tur,
                        id = c.getLong(0),
                        ad = c.getString(1) ?: "",
                        boyut = c.getLong(2),
                        mime = c.getString(3) ?: "",
                        genislik = uz(4)?.toInt()?.takeIf { it > 0 },
                        yukseklik = uz(5)?.toInt()?.takeIf { it > 0 },
                        sureMs = if (video) uz(8) else null,
                        cekimMs = uz(7)?.takeIf { it > 0 },
                        eklenmeSn = c.getLong(6),
                    ),
                )
            }
        }
        return sonuc
    }
}

/** ACCESS_MEDIA_LOCATION ile özgün dosyanın EXIF başlığından konum. Okunamazsa null. */
class AndroidKonumOkuyucu(private val ctx: Context) : KonumOkuyucu {
    override fun oku(oge: MedyaOge): Pair<Double, Double>? {
        if (oge.tur != MedyaTuru.FOTO) return null
        return try {
            val uri = MediaStore.setRequireOriginal(ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, oge.id))
            ctx.contentResolver.openInputStream(uri)?.use { s ->
                ExifInterface(s).latLong?.let { it[0] to it[1] }
            }
        } catch (e: Exception) {
            null
        }
    }
}

class AndroidKullanimKaynagi(private val ctx: Context) : KullanimKaynagi {
    private val usm = ctx.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager

    override fun gunKullanimi(basMs: Long, sonMs: Long): Map<String, Long> =
        usm.queryAndAggregateUsageStats(basMs, sonMs).mapValues { it.value.totalTimeInForeground }

    override fun ad(paket: String): String? = try {
        ctx.packageManager.getApplicationLabel(ctx.packageManager.getApplicationInfo(paket, 0)).toString()
    } catch (e: Exception) {
        null
    }
}

/** SAF klasör seçicisinden gelen ağacın altını gezer (alt klasörler dahil); yalnız ad/boyut/mime/değişim. */
class SafIndirilenKaynagi(private val ctx: Context, private val agac: Uri, private val azamiDerinlik: Int = 6) : IndirilenKaynagi {
    override fun listele(): Sequence<IndirilenOge> = sequence {
        val kok = DocumentsContract.getTreeDocumentId(agac)
        yield_(kok, "", 0)
    }

    private suspend fun SequenceScope<IndirilenOge>.yield_(belge: String, yol: String, derinlik: Int) {
        if (derinlik > azamiDerinlik) return
        val cocuklar = DocumentsContract.buildChildDocumentsUriUsingTree(agac, belge)
        val sutunlar = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_SIZE, DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_LAST_MODIFIED,
        )
        val satirlar = ArrayList<Array<Any?>>()
        ctx.contentResolver.query(cocuklar, sutunlar, null, null, null)?.use { c ->
            while (c.moveToNext()) {
                satirlar.add(arrayOf(c.getString(0), c.getString(1), if (c.isNull(2)) 0L else c.getLong(2), c.getString(3), if (c.isNull(4)) 0L else c.getLong(4)))
            }
        }
        for (s in satirlar) {
            val ad = s[1] as? String ?: continue
            val mime = s[3] as? String ?: ""
            if (mime == DocumentsContract.Document.MIME_TYPE_DIR) {
                yield_(s[0] as String, "$yol/$ad", derinlik + 1)
            } else {
                yield(IndirilenOge("$yol/$ad", ad, s[2] as Long, mime, s[4] as Long))
            }
        }
    }
}
