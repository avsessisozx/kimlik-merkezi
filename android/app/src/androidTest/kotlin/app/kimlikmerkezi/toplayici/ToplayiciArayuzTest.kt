package app.kimlikmerkezi.toplayici

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import app.kimlikmerkezi.toplayici.topla.ToplayiciAyarlari
import app.kimlikmerkezi.toplayici.ui.MainActivity
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ToplayiciArayuzTest {
    @get:Rule
    val kural = createAndroidComposeRule<MainActivity>()

    private val ctx: Context get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun ayarlar() {
        kural.onNodeWithTag("ayarlar_btn").performClick()
    }

    @Test
    fun dortToplayiciVarsayilanKapali() {
        ayarlar()
        for (t in listOf("medya", "konum", "indirilen", "kullanim")) {
            kural.onNodeWithTag("anahtar_$t").performScrollTo().assertIsDisplayed().assertIsOff()
            kural.onNodeWithTag("durum_$t").performScrollTo().assertIsDisplayed()
        }
        kural.onNodeWithTag("simdi_tara_btn").performScrollTo().assertIsDisplayed()
    }

    @Test
    fun kullanimErisimiYonlendirmesiCokmezVeIzinsizseKapaliKalir() {
        ayarlar()
        kural.onNodeWithTag("anahtar_kullanim").performScrollTo().performClick()
        val cihaz = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        // Sistem ekranı açıldı; geri dönene kadar geri tuşu
        Thread.sleep(2000)
        var deneme = 0
        while (cihaz.currentPackageName != ctx.packageName && deneme++ < 5) {
            cihaz.pressBack()
            Thread.sleep(1000)
        }
        kural.waitForIdle()
        kural.onNodeWithTag("anahtar_kullanim").performScrollTo().assertIsOff()
        assertFalse(ToplayiciAyarlari(ctx.depo.depolama).acik(ToplayiciAyarlari.Ad.KULLANIM))
    }
}
