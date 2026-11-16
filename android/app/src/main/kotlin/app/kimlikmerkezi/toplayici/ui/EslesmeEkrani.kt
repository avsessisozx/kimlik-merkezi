package app.kimlikmerkezi.toplayici.ui

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import app.kimlikmerkezi.toplayici.Depo
import app.kimlikmerkezi.toplayici.R
import app.kimlikmerkezi.toplayici.aktarim.AdresSuzgeci
import app.kimlikmerkezi.toplayici.aktarim.EslesmeKodu
import app.kimlikmerkezi.toplayici.aktarim.EslesmeSonucu
import app.kimlikmerkezi.toplayici.aktarim.QrCozucu
import app.kimlikmerkezi.toplayici.arkaplan.ArkaPlan
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

@Composable
fun EslesmeEkrani(depo: Depo, geri: () -> Unit) {
    val ctx = LocalContext.current
    @Suppress("UNUSED_VARIABLE") val yenile = depo.ayarSayaci
    var kodMetni by rememberSaveable { mutableStateOf("") }
    var bekleyen by remember { mutableStateOf<EslesmeKodu?>(null) }
    var mesaj by remember { mutableStateOf<Int?>(null) }
    var calisiyor by remember { mutableStateOf(false) }
    var kameraAcik by remember { mutableStateOf(false) }
    var adres by rememberSaveable { mutableStateOf("") }
    val kapsam = rememberCoroutineScope()

    fun kodDene(m: String) {
        val k = EslesmeKodu.coz(m)
        if (k == null) mesaj = R.string.es_kod_bozuk else { mesaj = null; bekleyen = k }
    }

    val kameraIzni = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        kameraAcik = ok
        if (!ok) mesaj = R.string.es_kamera_yok
    }

    Cerceve(stringResource(R.string.es_baslik), geri) { mod ->
        Column(mod.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (depo.eslesme.eslesmis()) {
                Text(stringResource(R.string.es_eslesmis, depo.eslesme.pcAdi()), style = MaterialTheme.typography.titleMedium, modifier = Modifier.testTag("eslesme_durumu"))
                OutlinedTextField(
                    value = adres, onValueChange = { adres = it }, singleLine = true,
                    label = { Text(stringResource(R.string.es_adres_alani)) },
                    modifier = Modifier.fillMaxWidth().testTag("adres_alani"),
                )
                OutlinedButton(
                    onClick = {
                        if (AdresSuzgeci.yerelMi(adres.trim())) { depo.eslesme.adresKaydet(adres.trim()); mesaj = null; adres = "" } else mesaj = R.string.es_adres_gecersiz
                    },
                    modifier = Modifier.fillMaxWidth().testTag("adres_kaydet_btn"),
                ) { Text(stringResource(R.string.es_adres_kaydet)) }
                Text(stringResource(R.string.es_kaldir_bilgi), color = MaterialTheme.colorScheme.secondary)
                Button(
                    onClick = { depo.eslesme.kaldir(); depo.ayarDegisti() },
                    modifier = Modifier.fillMaxWidth().testTag("eslesme_kaldir_btn"),
                ) { Text(stringResource(R.string.es_kaldir)) }
            } else {
                Text(stringResource(R.string.es_aciklama))
                OutlinedButton(
                    onClick = {
                        if (ctx.checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) kameraAcik = true
                        else kameraIzni.launch(Manifest.permission.CAMERA)
                    },
                    modifier = Modifier.fillMaxWidth().testTag("qr_tara_btn"),
                ) { Text(stringResource(R.string.es_qr_tara)) }
                if (kameraAcik) {
                    QrOkuyucu(Modifier.fillMaxWidth().height(280.dp)) { m ->
                        kameraAcik = false
                        kodMetni = m
                        kodDene(m)
                    }
                }
                OutlinedTextField(
                    value = kodMetni, onValueChange = { kodMetni = it },
                    label = { Text(stringResource(R.string.es_kod_alani)) },
                    modifier = Modifier.fillMaxWidth().testTag("kod_alani"),
                )
                Button(onClick = { kodDene(kodMetni) }, modifier = Modifier.fillMaxWidth().testTag("kod_devam_btn")) {
                    Text(stringResource(R.string.es_devam))
                }
            }
            if (calisiyor) Text(stringResource(R.string.es_calisiyor))
            mesaj?.let { Text(stringResource(it), color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("eslesme_mesaji")) }
        }
    }

    bekleyen?.let { k ->
        AlertDialog(
            onDismissRequest = { bekleyen = null },
            title = { Text(stringResource(R.string.es_onay_baslik)) },
            text = { Text(stringResource(R.string.es_onay_metin, k.pcAdi), modifier = Modifier.testTag("onay_metni")) },
            confirmButton = {
                TextButton(
                    onClick = {
                        bekleyen = null
                        calisiyor = true
                        kapsam.launch {
                            val s = withContext(Dispatchers.IO) {
                                try {
                                    depo.eslestirici.eslestir(k, depo.cihazId, android.os.Build.MODEL ?: "")
                                } catch (e: Exception) {
                                    depo.gunluk.hata("eslestir", e); EslesmeSonucu.Beklenmeyen
                                }
                            }
                            calisiyor = false
                            mesaj = when (s) {
                                EslesmeSonucu.Tamam -> {
                                    kodMetni = ""
                                    ArkaPlan.planla(ctx.applicationContext, depo.arkaPlanAcik)
                                    null
                                }
                                EslesmeSonucu.KodGecersiz -> R.string.es_kod_gecersiz
                                EslesmeSonucu.IstekHatali -> R.string.es_istek_hatali
                                EslesmeSonucu.SertifikaUyusmadi -> R.string.es_sertifika
                                EslesmeSonucu.Ulasilamadi -> R.string.es_ulasilamadi
                                EslesmeSonucu.Beklenmeyen -> R.string.es_beklenmeyen
                            }
                            depo.ayarDegisti()
                        }
                    },
                    modifier = Modifier.testTag("onayla_btn"),
                ) { Text(stringResource(R.string.es_onayla)) }
            },
            dismissButton = { TextButton(onClick = { bekleyen = null }) { Text(stringResource(R.string.es_vazgec)) } },
        )
    }
}

/** CameraX önizleme + zxing çözücü; çevrimdışı, Google Play Hizmetleri gerekmez. */
@Composable
private fun QrOkuyucu(mod: Modifier, bulundu: (String) -> Unit) {
    val ctx = LocalContext.current
    val sahip = LocalLifecycleOwner.current
    val yurutucu = remember { Executors.newSingleThreadExecutor() }
    val tamam = remember { AtomicBoolean(false) }
    AndroidView(
        modifier = mod,
        factory = { c ->
            PreviewView(c).also { pv ->
                val f = ProcessCameraProvider.getInstance(c)
                f.addListener({
                    val onizleme = Preview.Builder().build().also { it.surfaceProvider = pv.surfaceProvider }
                    val analiz = ImageAnalysis.Builder().setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build()
                    analiz.setAnalyzer(yurutucu) { img ->
                        try {
                            val p = img.planes[0]
                            val arabellek = p.buffer
                            val y = ByteArray(arabellek.remaining()).also { arabellek.get(it) }
                            val m = QrCozucu.coz(y, img.width, img.height, p.rowStride)
                            if (m != null && m.startsWith("km1:", ignoreCase = true) && tamam.compareAndSet(false, true)) {
                                ContextCompat.getMainExecutor(c).execute { bulundu(m) }
                            }
                        } catch (_: Exception) {
                        } finally {
                            img.close()
                        }
                    }
                    try {
                        val prov = f.get()
                        prov.unbindAll()
                        prov.bindToLifecycle(sahip, CameraSelector.DEFAULT_BACK_CAMERA, onizleme, analiz)
                    } catch (_: Exception) {
                    }
                }, ContextCompat.getMainExecutor(ctx))
            }
        },
    )
}
