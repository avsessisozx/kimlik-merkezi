package app.kimlikmerkezi.toplayici.ui

import android.content.Intent
import android.net.Uri
import android.provider.Settings
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import app.kimlikmerkezi.toplayici.Depo
import app.kimlikmerkezi.toplayici.R
import app.kimlikmerkezi.toplayici.aktarim.ElleAktarim
import app.kimlikmerkezi.toplayici.arkaplan.ArkaPlan
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalDate

/** Ayarlar içinde: arka plan anahtarı, eşleştirme, dosyaya aktar, pil yardımı. */
@Composable
fun AktarimBolumu(depo: Depo, eslestir: () -> Unit, pil: () -> Unit) {
    val ctx = LocalContext.current
    @Suppress("UNUSED_VARIABLE") val yenile = depo.ayarSayaci
    val kapsam = rememberCoroutineScope()
    var uyari by remember { mutableStateOf(false) }
    var silinecek by remember { mutableStateOf<List<String>?>(null) }
    val olustur = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        kapsam.launch {
            val idler = withContext(Dispatchers.IO) {
                try {
                    ctx.contentResolver.openOutputStream(uri, "w")!!.use { ElleAktarim.zipYaz(depo.kutu, it) }
                } catch (e: Exception) {
                    depo.gunluk.hata("elle_aktarim", e); null
                }
            }
            if (idler == null) Toast.makeText(ctx, R.string.ay_dosya_hata, Toast.LENGTH_SHORT).show()
            else {
                Toast.makeText(ctx, ctx.getString(R.string.ay_dosya_yazildi, idler.size), Toast.LENGTH_SHORT).show()
                if (idler.isNotEmpty()) silinecek = idler
            }
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
            Text(stringResource(R.string.ay_arka_plan), modifier = Modifier.weight(1f))
            Switch(
                checked = depo.arkaPlanAcik,
                onCheckedChange = { depo.arkaPlanAcik = it; ArkaPlan.planla(ctx.applicationContext, it && depo.eslesme.eslesmis()) },
                modifier = Modifier.testTag("anahtar_arka_plan"),
            )
        }
        Text(stringResource(R.string.ay_arka_plan_bilgi), style = MaterialTheme.typography.bodySmall)
        OutlinedButton(onClick = eslestir, modifier = Modifier.fillMaxWidth().testTag("eslestir_btn")) { Text(stringResource(R.string.ay_eslesme)) }
        OutlinedButton(onClick = { uyari = true }, modifier = Modifier.fillMaxWidth().testTag("dosyaya_aktar_btn")) { Text(stringResource(R.string.ay_dosyaya_aktar)) }
        TextButton(onClick = pil, modifier = Modifier.testTag("pil_btn")) { Text(stringResource(R.string.ay_pil)) }
    }

    if (uyari) {
        AlertDialog(
            onDismissRequest = { uyari = false },
            title = { Text(stringResource(R.string.ay_dosyaya_aktar)) },
            text = { Text(stringResource(R.string.ay_dosya_uyari), modifier = Modifier.testTag("sifresiz_uyari")) },
            confirmButton = {
                TextButton(onClick = { uyari = false; olustur.launch("kimlik-merkezi-giden-${LocalDate.now()}.zip") }) { Text(stringResource(R.string.ay_devam)) }
            },
            dismissButton = { TextButton(onClick = { uyari = false }) { Text(stringResource(R.string.es_vazgec)) } },
        )
    }
    silinecek?.let { idler ->
        AlertDialog(
            onDismissRequest = { silinecek = null },
            title = { Text(stringResource(R.string.ay_silme_baslik)) },
            text = { Text(stringResource(R.string.ay_silme_metin)) },
            confirmButton = {
                TextButton(onClick = {
                    kapsam.launch(Dispatchers.IO) { ElleAktarim.sil(depo.kutu, idler) }
                    silinecek = null
                }, modifier = Modifier.testTag("pc_alindi_sil_btn")) { Text(stringResource(R.string.ay_sil)) }
            },
            dismissButton = { TextButton(onClick = { silinecek = null }) { Text(stringResource(R.string.ay_silme)) } },
        )
    }
}

@Composable
fun PilEkrani(geri: () -> Unit) {
    val ctx = LocalContext.current
    Cerceve(stringResource(R.string.pil_baslik), geri) { mod ->
        Column(mod.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.pil_metin))
            Text(stringResource(R.string.pil_adim), style = MaterialTheme.typography.titleMedium)
            Button(
                onClick = { ac(ctx, Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) },
                modifier = Modifier.fillMaxWidth().testTag("pil_ayari_btn"),
            ) { Text(stringResource(R.string.pil_pil_ayari)) }
            OutlinedButton(
                onClick = { ac(ctx, Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", ctx.packageName, null))) },
                modifier = Modifier.fillMaxWidth().testTag("uygulama_ayari_btn"),
            ) { Text(stringResource(R.string.pil_uygulama_ayari)) }
            Text(stringResource(R.string.pil_garanti))
        }
    }
}

private fun ac(ctx: android.content.Context, i: Intent) {
    try {
        ctx.startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    } catch (e: Exception) {
        Toast.makeText(ctx, R.string.tp_ekran_acilamadi, Toast.LENGTH_SHORT).show()
    }
}
