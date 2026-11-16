package app.kimlikmerkezi.toplayici.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import app.kimlikmerkezi.toplayici.depo

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val depo = applicationContext.depo
        setContent {
            KimlikTemasi(depo.tema) { Uygulama(depo) }
        }
    }
}
