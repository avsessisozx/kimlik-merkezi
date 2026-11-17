package app.kimlikmerkezi.toplayici.ui

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Intent
import android.provider.Settings
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import app.kimlikmerkezi.toplayici.Depo
import app.kimlikmerkezi.toplayici.R
import app.kimlikmerkezi.toplayici.topla.Izinler
import app.kimlikmerkezi.toplayici.topla.MedyaIzni
import app.kimlikmerkezi.toplayici.topla.ToplayiciAyarlari.Ad
import app.kimlikmerkezi.toplayici.topla.ToplayiciYonetici

/** Altı isteğe bağlı toplayıcı: ayrı aç/kapat, tek cümle açıklama, izin durumu. İzin reddi anahtarı kapatır. */
@Composable
fun ToplayiciBolumu(depo: Depo) {
    val ctx = LocalContext.current
    val ayar = depo.yonetici.ayarlar
    @Suppress("UNUSED_VARIABLE") val yenile = depo.ayarSayaci // değişince yeniden çizilir
    var mesaj by remember { mutableStateOf<Int?>(null) }

    fun sonuc(a: Ad, ok: Boolean) {
        ayar.izinSonucu(a, ok)
        mesaj = if (ok) null else R.string.tp_izin_reddedildi
        depo.ayarDegisti()
    }

    val medyaIstek = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        sonuc(Ad.MEDYA, Izinler.medya(ctx) != MedyaIzni.YOK)
    }
    val konumIstek = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        sonuc(Ad.KONUM, Izinler.medya(ctx) != MedyaIzni.YOK && Izinler.konum(ctx))
    }
    val agacIstek = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        var ok = false
        if (uri != null) {
            try {
                ctx.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
                depo.depolama.yazMetin(ToplayiciYonetici.AGAC, uri.toString())
                ok = true
            } catch (e: Exception) {
                depo.gunluk.hata("agac", e)
            }
        }
        sonuc(Ad.INDIRILEN, ok)
    }

    val adimIstek = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        sonuc(Ad.ADIM, ok)
    }

    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) {
        if (depo.depolama.mantik(EKRAN_BEKLIYOR)) {
            depo.depolama.yazMantik(EKRAN_BEKLIYOR, false)
            sonuc(Ad.EKRAN, Izinler.ekranServisiAcik(ctx))
        }
        if (depo.depolama.mantik(ToplayiciYonetici.KULLANIM_BEKLIYOR)) {
            depo.depolama.yazMantik(ToplayiciYonetici.KULLANIM_BEKLIYOR, false)
            sonuc(Ad.KULLANIM, Izinler.kullanimErisimi(ctx))
        }
        depo.ayarDegisti()
    }

    val medyaIzni = Izinler.medya(ctx)
    val izinVar = stringResource(R.string.tp_izin_verildi)
    val izinYok = stringResource(R.string.tp_izin_verilmedi)
    val agacVar = Izinler.indirilenAgaci(ctx, depo.depolama.metin(ToplayiciYonetici.AGAC)) != null

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(stringResource(R.string.tp_baslik), style = MaterialTheme.typography.titleMedium)
        Text(stringResource(R.string.tp_bilgi), color = MaterialTheme.colorScheme.secondary)
        mesaj?.let { Text(stringResource(it), color = MaterialTheme.colorScheme.error, modifier = Modifier.testTag("izin_mesaji")) }

        Toplayici(
            "medya", R.string.tp_medya_baslik, R.string.tp_medya_aciklama,
            if (medyaIzni == MedyaIzni.YOK) izinYok else izinVar,
            ayar.acik(Ad.MEDYA),
        ) { ac ->
            if (!ac) { ayar.ayarla(Ad.MEDYA, false); depo.ayarDegisti() } else medyaIstek.launch(Izinler.medyaIzinleri())
        }
        if (ayar.acik(Ad.MEDYA) && medyaIzni == MedyaIzni.KISMI) {
            Text(stringResource(R.string.tp_medya_kismi), color = MaterialTheme.colorScheme.secondary, modifier = Modifier.testTag("kismi_erisim"))
        }
        Toplayici(
            "konum", R.string.tp_konum_baslik, R.string.tp_konum_aciklama,
            if (Izinler.konum(ctx)) izinVar else izinYok,
            ayar.acik(Ad.KONUM),
        ) { ac ->
            if (!ac) {
                ayar.ayarla(Ad.KONUM, false); depo.ayarDegisti()
            } else {
                konumIstek.launch(Izinler.medyaIzinleri() + Manifest.permission.ACCESS_MEDIA_LOCATION)
            }
        }
        Toplayici(
            "indirilen", R.string.tp_indirilen_baslik, R.string.tp_indirilen_aciklama,
            if (agacVar) izinVar else izinYok,
            ayar.acik(Ad.INDIRILEN),
        ) { ac ->
            if (!ac) {
                ayar.ayarla(Ad.INDIRILEN, false); depo.ayarDegisti()
            } else {
                Toast.makeText(ctx, R.string.tp_indirilen_ipucu, Toast.LENGTH_LONG).show()
                agacIstek.launch(null)
            }
        }
        Toplayici(
            "kullanim", R.string.tp_kullanim_baslik, R.string.tp_kullanim_aciklama,
            if (Izinler.kullanimErisimi(ctx)) izinVar else izinYok,
            ayar.acik(Ad.KULLANIM),
        ) { ac ->
            if (!ac) {
                ayar.ayarla(Ad.KULLANIM, false); depo.ayarDegisti()
            } else if (Izinler.kullanimErisimi(ctx)) {
                sonuc(Ad.KULLANIM, true)
            } else {
                try {
                    depo.depolama.yazMantik(ToplayiciYonetici.KULLANIM_BEKLIYOR, true)
                    Toast.makeText(ctx, R.string.tp_kullanim_yonlendirme, Toast.LENGTH_LONG).show()
                    ctx.startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                } catch (e: ActivityNotFoundException) {
                    depo.depolama.yazMantik(ToplayiciYonetici.KULLANIM_BEKLIYOR, false)
                    Toast.makeText(ctx, R.string.tp_ekran_acilamadi, Toast.LENGTH_SHORT).show()
                }
            }
        }

        Toplayici(
            "adim", R.string.tp_adim_baslik, R.string.tp_adim_aciklama,
            if (Izinler.adim(ctx)) izinVar else izinYok,
            ayar.acik(Ad.ADIM),
        ) { ac ->
            if (!ac) {
                ayar.ayarla(Ad.ADIM, false); depo.ayarDegisti()
            } else if (Izinler.adim(ctx)) {
                sonuc(Ad.ADIM, true)
            } else {
                adimIstek.launch(Manifest.permission.ACTIVITY_RECOGNITION)
            }
        }
        Toplayici(
            "ekran", R.string.tp_ekran_baslik, R.string.tp_ekran_aciklama,
            if (Izinler.ekranServisiAcik(ctx)) izinVar else izinYok,
            ayar.acik(Ad.EKRAN),
        ) { ac ->
            if (!ac) {
                ayar.ayarla(Ad.EKRAN, false); depo.ayarDegisti()
            } else if (Izinler.ekranServisiAcik(ctx)) {
                sonuc(Ad.EKRAN, true)
            } else {
                try {
                    depo.depolama.yazMantik(EKRAN_BEKLIYOR, true)
                    Toast.makeText(ctx, R.string.tp_ekran_yonlendirme, Toast.LENGTH_LONG).show()
                    ctx.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                } catch (e: ActivityNotFoundException) {
                    depo.depolama.yazMantik(EKRAN_BEKLIYOR, false)
                    Toast.makeText(ctx, R.string.tp_ekran_acilamadi, Toast.LENGTH_SHORT).show()
                }
            }
        }
        Text(stringResource(R.string.tp_ses_yok), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.secondary)

        OutlinedButton(
            onClick = { depo.tara() },
            modifier = Modifier.fillMaxWidth().testTag("simdi_tara_btn"),
        ) { Text(stringResource(R.string.tp_simdi_tara)) }
        if (depo.taramaDurumu.isNotEmpty()) {
            Text(stringResource(R.string.tp_tarama_durumu, depo.taramaDurumu), modifier = Modifier.testTag("tarama_durumu"))
        }
    }
}

private const val EKRAN_BEKLIYOR = "ekran_bekliyor"

@Composable
private fun Toplayici(
    etiket: String,
    baslik: Int,
    aciklama: Int,
    durum: String,
    acik: Boolean,
    degis: (Boolean) -> Unit,
) {
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
            Text(stringResource(baslik), style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
            Switch(checked = acik, onCheckedChange = degis, modifier = Modifier.testTag("anahtar_$etiket"))
        }
        Text(stringResource(aciklama), style = MaterialTheme.typography.bodySmall)
        Text(durum, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.secondary, modifier = Modifier.padding(top = 2.dp).testTag("durum_$etiket"))
    }
}
