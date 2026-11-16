package app.kimlikmerkezi.toplayici.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Acik = lightColorScheme(
    primary = Color(0xFF0F5F66),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFBFEBEF),
    onPrimaryContainer = Color(0xFF002023),
    secondary = Color(0xFF4A6366),
    background = Color(0xFFFBFCFC),
    surface = Color(0xFFFBFCFC),
    error = Color(0xFFBA1A1A),
)

private val Koyu = darkColorScheme(
    primary = Color(0xFF7FD3DB),
    onPrimary = Color(0xFF00363B),
    primaryContainer = Color(0xFF004F55),
    onPrimaryContainer = Color(0xFFBFEBEF),
    secondary = Color(0xFFB1CBCE),
    background = Color(0xFF101415),
    surface = Color(0xFF101415),
    error = Color(0xFFFFB4AB),
)

/** [tema]: "sistem", "koyu" ya da "acik". Dinamik renk kapalı. */
@Composable
fun KimlikTemasi(tema: String, icerik: @Composable () -> Unit) {
    val koyu = when (tema) {
        "koyu" -> true
        "acik" -> false
        else -> isSystemInDarkTheme()
    }
    MaterialTheme(colorScheme = if (koyu) Koyu else Acik, content = icerik)
}
