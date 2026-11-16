package app.kimlikmerkezi.toplayici

import android.Manifest
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.ContextWrapper
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import androidx.exifinterface.media.ExifInterface
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.rule.GrantPermissionRule
import app.kimlikmerkezi.toplayici.giden.CihazBilgisi
import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.giden.KeystoreAnahtar
import app.kimlikmerkezi.toplayici.gunluk.Gunluk
import app.kimlikmerkezi.toplayici.topla.AndroidKonumOkuyucu
import app.kimlikmerkezi.toplayici.topla.AndroidKullanimKaynagi
import app.kimlikmerkezi.toplayici.topla.AndroidMedyaKaynagi
import app.kimlikmerkezi.toplayici.topla.BellekDepolama
import app.kimlikmerkezi.toplayici.topla.Izinler
import app.kimlikmerkezi.toplayici.topla.KullanimToplayici
import app.kimlikmerkezi.toplayici.topla.MedyaToplayici
import app.kimlikmerkezi.toplayici.topla.ToplayiciAyarlari
import app.kimlikmerkezi.toplayici.topla.ToplayiciYonetici
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonPrimitive
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.nio.file.Files

@RunWith(AndroidJUnit4::class)
class MedyaToplayiciTest {
    @get:Rule
    val izin: GrantPermissionRule = GrantPermissionRule.grant(*(app.kimlikmerkezi.toplayici.topla.Izinler.medyaIzinleri().filter {
        it != Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED
    } + Manifest.permission.ACCESS_MEDIA_LOCATION).toTypedArray())

    private val ctx: Context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val eklenen = ArrayList<Uri>()
    private val dizinler = ArrayList<File>()

    private fun kutu(): GidenKutusu {
        val d = Files.createTempDirectory(ctx.cacheDir.toPath(), "giden").toFile().also { dizinler.add(it) }
        return GidenKutusu(d, KeystoreAnahtar.sifreleyici(), CihazBilgisi("3f2b8c1e-5a47-4d9e-8b36-1c7e0a9d4f52", "0.2.0", 31, "TEST"), Gunluk(null))
    }

    @After
    fun temizle() {
        eklenen.forEach { runCatching { ctx.contentResolver.delete(it, null, null) } }
        dizinler.forEach { it.deleteRecursively() }
    }

    /** Test görseli: küçük JPEG, istenirse EXIF GPS ile; MediaStore'a eklenir. */
    private fun gorselEkle(ad: String, enlem: Double? = null, boylam: Double? = null): Long {
        val dosya = File(ctx.cacheDir, ad)
        dosya.outputStream().use { Bitmap.createBitmap(8, 6, Bitmap.Config.ARGB_8888).compress(Bitmap.CompressFormat.JPEG, 80, it) }
        if (enlem != null && boylam != null) {
            val e = ExifInterface(dosya.absolutePath)
            e.setLatLong(enlem, boylam)
            e.saveAttributes()
        }
        val v = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, ad)
            put(MediaStore.MediaColumns.MIME_TYPE, "image/jpeg")
            put(MediaStore.MediaColumns.RELATIVE_PATH, "Pictures/KMTest")
        }
        val uri = ctx.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, v)!!
        ctx.contentResolver.openOutputStream(uri)!!.use { o -> dosya.inputStream().use { it.copyTo(o) } }
        dosya.delete()
        eklenen.add(uri)
        return ContentUris.parseId(uri)
    }

    private fun GidenKutusu.sayi(tur: String, ozet: String) = sonKayitlar(100_000).count { it.tur == tur && it.ozet == ozet }

    @Test
    fun taramaKayitUretirIkinciTaramaUretmez() {
        val k = kutu()
        val ad = "km_test_${System.nanoTime()}.jpg"
        gorselEkle(ad)
        val t = MedyaToplayici(k, AndroidMedyaKaynagi(ctx), AndroidKonumOkuyucu(ctx), BellekDepolama())
        assertTrue(t.taraMedya() >= 1)
        assertEquals(1, k.sayi("medya.foto", ad))
        val once = k.bekleyenKayitSayisi()
        assertEquals(0, t.taraMedya())
        assertEquals(once, k.bekleyenKayitSayisi())
        val id = k.sonKayitlar(100_000).first { it.ozet == ad }.id
        val yuk = k.kayitBul(id)!!.yuk
        assertEquals("image/jpeg", yuk["mime"]!!.jsonPrimitive.content)
        assertTrue(yuk.containsKey("medya_id"))
        assertFalse(yuk.containsKey("enlem"))
    }

    @Test
    fun konumKapaliykenKayitYokAcikkenVar() {
        val k = kutu()
        val ad = "km_gps_${System.nanoTime()}.jpg"
        gorselEkle(ad, 41.0105, 28.9784)
        val t = MedyaToplayici(k, AndroidMedyaKaynagi(ctx), AndroidKonumOkuyucu(ctx), BellekDepolama())
        t.taraMedya() // ayar kapalı: konum taraması çağrılmaz
        assertEquals(1, k.sayi("medya.foto", ad))
        assertEquals(0, k.sayi("medya.konum", "$ad konumu"))
        val fotoYuk = k.kayitBul(k.sonKayitlar(100_000).first { it.tur == "medya.foto" && it.ozet == ad }.id)!!.yuk
        assertFalse(fotoYuk.containsKey("enlem") || fotoYuk.containsKey("boylam"))
        // ayar açıldı + izin var
        assertTrue(t.taraKonum() >= 1)
        assertEquals(1, k.sayi("medya.konum", "$ad konumu"))
        val konum: JsonObject = k.kayitBul(k.sonKayitlar(100_000).first { it.tur == "medya.konum" && it.ozet == "$ad konumu" }.id)!!.yuk
        assertEquals(41.0105, konum["enlem"]!!.jsonPrimitive.doubleOrNull!!, 0.01)
        assertEquals(28.9784, konum["boylam"]!!.jsonPrimitive.doubleOrNull!!, 0.01)
        assertEquals(0, t.taraKonum())
    }

    @Test
    fun izinReddindeTaramaCokmezKayitUretmez() {
        val k = kutu()
        gorselEkle("km_red_${System.nanoTime()}.jpg", 1.0, 2.0)
        val red = object : ContextWrapper(ctx) {
            override fun checkSelfPermission(permission: String) = android.content.pm.PackageManager.PERMISSION_DENIED
            override fun getApplicationContext(): Context = this
        }
        val d = BellekDepolama()
        val y = ToplayiciYonetici(red, k, Gunluk(null), d)
        ToplayiciAyarlari.Ad.entries.forEach { y.ayarlar.ayarla(it, true) }
        assertEquals(0, y.tara())
        assertEquals(0, k.bekleyenKayitSayisi())
        assertNotNull(Build.VERSION.SDK_INT)
    }

    @Test
    fun kullanimErisimiVerilinceTaramaCalisir() {
        val ui = InstrumentationRegistry.getInstrumentation().uiAutomation
        fun kabuk(c: String) = ui.executeShellCommand(c).use { f -> android.os.ParcelFileDescriptor.AutoCloseInputStream(f).readBytes() }
        try {
            kabuk("appops set ${ctx.packageName} android:get_usage_stats allow")
            assertTrue(Izinler.kullanimErisimi(ctx))
            val k = kutu()
            val kaynak = AndroidKullanimKaynagi(ctx)
            val d = BellekDepolama()
            val n = KullanimToplayici(k, kaynak, d, kendiPaket = ctx.packageName).tara()
            assertTrue(n >= 0)
            assertEquals(0, KullanimToplayici(k, kaynak, d, kendiPaket = ctx.packageName).tara())
        } finally {
            kabuk("appops set ${ctx.packageName} android:get_usage_stats default")
        }
    }
}
