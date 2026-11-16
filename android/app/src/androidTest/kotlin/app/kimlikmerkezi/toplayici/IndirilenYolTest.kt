package app.kimlikmerkezi.toplayici

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.MediaStore
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import app.kimlikmerkezi.toplayici.giden.CihazBilgisi
import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.giden.KeystoreAnahtar
import app.kimlikmerkezi.toplayici.gunluk.Gunluk
import app.kimlikmerkezi.toplayici.topla.BellekGorulen
import app.kimlikmerkezi.toplayici.topla.Izinler
import app.kimlikmerkezi.toplayici.topla.IndirilenToplayici
import app.kimlikmerkezi.toplayici.topla.SafIndirilenKaynagi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.nio.file.Files
import java.util.concurrent.atomic.AtomicReference
import java.util.regex.Pattern

private const val GIZLI_ICERIK = "gizli-icerik" // 12 bayt

private fun Context.indirilenDosyaEkle(altYol: String, ad: String): Uri {
    val v = ContentValues().apply {
        put(MediaStore.MediaColumns.DISPLAY_NAME, ad)
        put(MediaStore.MediaColumns.MIME_TYPE, "text/plain")
        put(MediaStore.MediaColumns.RELATIVE_PATH, "Download/$altYol")
    }
    val u = contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v)!!
    contentResolver.openOutputStream(u)!!.use { it.write(GIZLI_ICERIK.toByteArray()) }
    return u
}

/** Seçenek 1: SAF klasör seçicisi (alt klasör seçimi dahil), UiAutomator ile gerçek seçici sürülür. */
@RunWith(AndroidJUnit4::class)
class IndirilenSafTest {
    @get:Rule
    val kural = createAndroidComposeRule<ComponentActivity>()

    private val inst get() = InstrumentationRegistry.getInstrumentation()
    private val ctx: Context get() = inst.targetContext

    @Test
    fun altKlasorSecilirKaliciIzinAlinirDosyalarListelenir() {
        val sonuc = AtomicReference<Uri?>(null)
        val bitti = java.util.concurrent.atomic.AtomicBoolean(false)
        val launcherRef = AtomicReference<androidx.activity.result.ActivityResultLauncher<Uri?>>()
        kural.setContent {
            launcherRef.set(rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { u ->
                sonuc.set(u); bitti.set(true)
            })
        }
        kural.waitForIdle()
        val ekler = listOf(ctx.indirilenDosyaEkle("KMSaf/alt", "kayit-a.txt"), ctx.indirilenDosyaEkle("KMSaf", "ust.txt"))
        try {
            val baslangic = DocumentsContract.buildDocumentUri("com.android.externalstorage.documents", "primary:Download/KMSaf")
            kural.runOnUiThread { launcherRef.get().launch(baslangic) }
            val cihaz = UiDevice.getInstance(inst)
            val kullan = cihaz.wait(Until.findObject(By.text(Pattern.compile("(?i)use this folder"))), 30_000)
            assertNotNull("Klasör seçici 'Use this folder' düğmesi görünmedi", kullan)
            kullan.click()
            val izinVer = cihaz.wait(Until.findObject(By.clazz("android.widget.Button").text(Pattern.compile("(?i)allow"))), 15_000)
            assertNotNull("İzin iletişim kutusu görünmedi", izinVer)
            izinVer.click()
            val t = System.currentTimeMillis()
            while (!bitti.get() && System.currentTimeMillis() - t < 20_000) Thread.sleep(200)
            val agac = sonuc.get()
            assertNotNull("Seçici sonuç döndürmedi", agac)
            ctx.contentResolver.takePersistableUriPermission(agac!!, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            assertNotNull(Izinler.indirilenAgaci(ctx, agac.toString()))

            val dosyalar = SafIndirilenKaynagi(ctx, agac).listele().toList()
            val a = dosyalar.first { it.ad == "kayit-a.txt" }
            assertEquals(GIZLI_ICERIK.length.toLong(), a.boyut)
            assertEquals("text/plain", a.mime)
            assertTrue(dosyalar.any { it.ad == "ust.txt" })

            val d = Files.createTempDirectory(ctx.cacheDir.toPath(), "giden").toFile()
            try {
                val k = GidenKutusu(d, KeystoreAnahtar.sifreleyici(), CihazBilgisi("3f2b8c1e-5a47-4d9e-8b36-1c7e0a9d4f52", "0.2.0", 31, "TEST"), Gunluk(null))
                val t2 = IndirilenToplayici(k, SafIndirilenKaynagi(ctx, agac), BellekGorulen())
                val g = BellekGorulen()
                val tt = IndirilenToplayici(k, SafIndirilenKaynagi(ctx, agac), g)
                assertTrue(tt.tara() >= 2)
                assertEquals(0, tt.tara())
                assertTrue(k.sonKayitlar(100).any { it.tur == "indirilen.dosya" && it.ozet == "kayit-a.txt" })
                assertTrue(k.sonKayitlar(100).none { it.ozet.contains(GIZLI_ICERIK) })
                assertNotNull(t2)
            } finally {
                d.deleteRecursively()
            }
            ctx.contentResolver.releasePersistableUriPermission(agac, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } finally {
            ekler.forEach { runCatching { ctx.contentResolver.delete(it, null, null) } }
        }
    }
}

/** Seçenek 2 deneyi: MANAGE_EXTERNAL_STORAGE. İzin değişimi süreci öldürebilir; ayrı koşulur. */
@Deney
@RunWith(AndroidJUnit4::class)
class IndirilenTumDosyalarDeneyi {
    private val inst get() = InstrumentationRegistry.getInstrumentation()
    private val ctx: Context get() = inst.targetContext

    @Test
    fun tumDosyalarErisimiVerilinceIndirilenlerListelenir() {
        val ui = inst.uiAutomation
        fun kabuk(c: String) = ui.executeShellCommand(c).use { f -> android.os.ParcelFileDescriptor.AutoCloseInputStream(f).readBytes() }
        val ek = ctx.indirilenDosyaEkle("KMTum", "tum-a.txt")
        try {
            kabuk("appops set ${ctx.packageName} MANAGE_EXTERNAL_STORAGE allow")
            assertTrue("isExternalStorageManager false", Environment.isExternalStorageManager())
            val klasor = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "KMTum")
            val ad = klasor.listFiles()?.map { it.name }.orEmpty()
            assertTrue("liste: $ad", "tum-a.txt" in ad)
        } finally {
            kabuk("appops set ${ctx.packageName} MANAGE_EXTERNAL_STORAGE default")
            ctx.contentResolver.delete(ek, null, null)
        }
    }
}
