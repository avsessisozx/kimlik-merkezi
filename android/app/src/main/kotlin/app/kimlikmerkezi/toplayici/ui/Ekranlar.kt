package app.kimlikmerkezi.toplayici.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import app.kimlikmerkezi.toplayici.BuildConfig
import app.kimlikmerkezi.toplayici.Depo
import app.kimlikmerkezi.toplayici.R
import app.kimlikmerkezi.toplayici.aktarim.AktarimDurumu
import app.kimlikmerkezi.toplayici.giden.GidenKutusu
import app.kimlikmerkezi.toplayici.giden.KayitOzeti
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private const val ANA = "ana"
private const val NOT = "not"
private const val AYARLAR = "ayarlar"
private const val HAKKINDA = "hakkinda"
private const val ESLES = "esles"
private const val PIL = "pil"

@Composable
fun Uygulama(depo: Depo) {
    var ekran by rememberSaveable { mutableStateOf(ANA) }
    var duzenlenen by rememberSaveable { mutableStateOf<String?>(null) }
    var oncekiAyar by rememberSaveable { mutableStateOf(false) }
    LaunchedEffectAdim(depo, ekran)
    BackHandler(enabled = ekran != ANA) {
        ekran = if (ekran == HAKKINDA || ekran == PIL || ekran == ESLES) AYARLAR.takeIf { oncekiAyar } ?: ANA else ANA
    }
    when (ekran) {
        NOT -> NotEkrani(depo, duzenlenen, geri = { ekran = ANA })
        AYARLAR -> AyarlarEkrani(
            depo, geri = { ekran = ANA }, hakkinda = { oncekiAyar = true; ekran = HAKKINDA },
            eslestir = { oncekiAyar = true; ekran = ESLES }, pil = { oncekiAyar = true; ekran = PIL },
        )
        ESLES -> EslesmeEkrani(depo, geri = { ekran = if (oncekiAyar) AYARLAR else ANA })
        PIL -> PilEkrani(geri = { ekran = AYARLAR })
        HAKKINDA -> HakkindaEkrani(depo, geri = { ekran = AYARLAR })
        else -> AnaEkran(
            depo,
            yeniNot = { duzenlenen = null; ekran = NOT },
            notuDuzenle = { duzenlenen = it; ekran = NOT },
            ayarlar = { oncekiAyar = false; ekran = AYARLAR },
            eslestir = { oncekiAyar = false; ekran = ESLES },
        )
    }
}

@Composable
private fun LaunchedEffectAdim(depo: Depo, ekran: String) {
    androidx.compose.runtime.LaunchedEffect(ekran) { depo.gunluk.adim("ekran $ekran") }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun Cerceve(baslik: String, geri: (() -> Unit)?, eylem: @Composable () -> Unit = {}, icerik: @Composable (Modifier) -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(baslik) },
                navigationIcon = {
                    if (geri != null) TextButton(onClick = geri, modifier = Modifier.testTag("geri")) { Text(stringResource(R.string.geri)) }
                },
                actions = { eylem() },
            )
        },
    ) { ic -> icerik(Modifier.padding(ic).fillMaxSize()) }
}

private val YEREL_SAAT: DateTimeFormatter = DateTimeFormatter.ofPattern("dd.MM HH:mm")

private fun yerelZaman(ts: String): String =
    runCatching { YEREL_SAAT.format(Instant.parse(ts).atZone(ZoneId.systemDefault())) }.getOrDefault("")

@Composable
private fun turAdi(tur: String): String = when (tur) {
    "not.hizli" -> stringResource(R.string.tur_not)
    "paylasim.link" -> stringResource(R.string.tur_link)
    "paylasim.metin" -> stringResource(R.string.tur_metin)
    "medya.foto" -> stringResource(R.string.tur_foto)
    "medya.video" -> stringResource(R.string.tur_video)
    "medya.konum" -> stringResource(R.string.tur_konum)
    "indirilen.dosya" -> stringResource(R.string.tur_indirilen)
    "uygulama.kullanim" -> stringResource(R.string.tur_kullanim)
    else -> stringResource(R.string.tur_diger)
}

@Composable
private fun AnaEkran(depo: Depo, yeniNot: () -> Unit, notuDuzenle: (String) -> Unit, ayarlar: () -> Unit, eslestir: () -> Unit) {
    // degisim okunur: giden kutusu değişince yeniden çizilir.
    val degisim = depo.degisim
    val bekleyen = remember(degisim) { depo.kutu.bekleyenKayitSayisi() }
    val son: List<KayitOzeti> = remember(degisim) { depo.kutu.sonKayitlar(30) }
    Cerceve(
        baslik = stringResource(R.string.app_name),
        geri = null,
        eylem = {
            TextButton(onClick = ayarlar, modifier = Modifier.testTag("ayarlar_btn")) { Text(stringResource(R.string.ayarlar)) }
        },
    ) { mod ->
        Column(mod.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Card(
                Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
            ) {
                Text(
                    if (bekleyen > 0) stringResource(R.string.ana_bekleyen, bekleyen) else stringResource(R.string.ana_bekleyen_yok),
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                    modifier = Modifier.padding(20.dp).testTag("bekleyen_sayac"),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Button(onClick = yeniNot, modifier = Modifier.testTag("hizli_not_btn")) { Text(stringResource(R.string.ana_hizli_not)) }
                val eslesmis = depo.eslesme.eslesmis()
                Button(
                    onClick = { if (eslesmis) depo.gonder() else eslestir() },
                    modifier = Modifier.testTag("pc_gonder_btn"),
                ) { Text(stringResource(if (eslesmis) R.string.ana_pc_gonder_aktif else R.string.ana_pc_gonder)) }
            }
            val ak by depo.gonderici.durum.collectAsState()
            val sonBasari = depo.gonderici.sonBasariMs()
            Text(
                if (sonBasari > 0) stringResource(R.string.ana_son_basari, yerelZaman(java.time.Instant.ofEpochMilli(sonBasari).toString()))
                else stringResource(R.string.ana_son_basari_yok),
                style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("son_basari"),
            )
            val akMetin = aktarimMetni(ak)
            if (akMetin != null) Text(akMetin, modifier = Modifier.testTag("aktarim_durumu"))
            Text(stringResource(R.string.ana_son_kayitlar), style = MaterialTheme.typography.titleMedium)
            if (son.isEmpty()) {
                Text(stringResource(R.string.ana_kayit_yok), color = MaterialTheme.colorScheme.secondary)
            } else {
                LazyColumn(Modifier.testTag("son_kayitlar")) {
                    items(son, key = { it.id }) { k ->
                        val duzenlenebilir = k.tur == "not.hizli"
                        Column(
                            Modifier.fillMaxWidth()
                                .then(if (duzenlenebilir) Modifier.clickable(role = Role.Button) { notuDuzenle(k.id) } else Modifier)
                                .padding(vertical = 8.dp),
                        ) {
                            Text("${turAdi(k.tur)} · ${yerelZaman(k.ts)}", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.secondary)
                            Text(k.ozet, maxLines = 2)
                        }
                        HorizontalDivider()
                    }
                }
            }
        }
    }
}

@Composable
private fun NotEkrani(depo: Depo, duzenlenenId: String?, geri: () -> Unit) {
    val onceki = remember(duzenlenenId) { duzenlenenId?.let { depo.kutu.kayitBul(it) } }
    var metin by rememberSaveable(duzenlenenId) { mutableStateOf(onceki?.metin ?: "") }
    val kapsam = rememberCoroutineScope()
    val ctx = LocalContext.current
    Cerceve(
        baslik = stringResource(if (duzenlenenId == null) R.string.not_baslik else R.string.not_duzenle_baslik),
        geri = geri,
    ) { mod ->
        Column(mod.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedTextField(
                value = metin,
                onValueChange = { metin = it },
                placeholder = { Text(stringResource(R.string.not_ipucu)) },
                modifier = Modifier.fillMaxWidth().weight(1f).testTag("not_alani"),
            )
            Button(
                onClick = {
                    if (metin.isBlank()) {
                        Toast.makeText(ctx, R.string.not_bos, Toast.LENGTH_SHORT).show()
                    } else {
                        val m = metin
                        kapsam.launch {
                            val ok = withContext(Dispatchers.IO) {
                                try {
                                    depo.kutu.kayitEkle("not.hizli", "notlar", m, onceki = duzenlenenId)
                                    true
                                } catch (e: Exception) {
                                    depo.gunluk.hata("not", e)
                                    false
                                }
                            }
                            withContext(Dispatchers.Main) {
                                Toast.makeText(ctx, if (ok && GidenKutusu.kisalt(m, GidenKutusu.METIN_UST).second) R.string.not_kisaltildi else if (ok) R.string.not_kaydedildi else R.string.not_kaydedilemedi, Toast.LENGTH_SHORT).show()
                                if (ok) geri()
                            }
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth().testTag("kaydet_btn"),
            ) { Text(stringResource(R.string.not_kaydet)) }
        }
    }
}

@Composable
private fun AyarlarEkrani(depo: Depo, geri: () -> Unit, hakkinda: () -> Unit, eslestir: () -> Unit, pil: () -> Unit) {
    val bekleyen = remember(depo.degisim) { depo.kutu.bekleyenKayitSayisi() }
    val ctx = LocalContext.current
    Cerceve(stringResource(R.string.ayarlar_baslik), geri) { mod ->
        Column(mod.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (bekleyen > 0) {
                Text(
                    stringResource(R.string.ayarlar_uyari, bekleyen),
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.testTag("kaybolur_uyarisi"),
                )
            }
            Text(stringResource(R.string.ayarlar_tema), style = MaterialTheme.typography.titleMedium)
            listOf(
                Triple("sistem", R.string.tema_sistem, "tema_sistem"),
                Triple("koyu", R.string.tema_koyu, "tema_koyu"),
                Triple("acik", R.string.tema_acik, "tema_acik"),
            ).forEach { (kod, ad, etiket) ->
                Row(
                    Modifier.fillMaxWidth().clickable(role = Role.RadioButton) { depo.temaSec(kod) }.testTag(etiket),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    RadioButton(selected = depo.tema == kod, onClick = null)
                    Text(stringResource(ad), modifier = Modifier.padding(start = 12.dp, top = 8.dp, bottom = 8.dp))
                }
            }
            Spacer(Modifier.height(8.dp))
            Text(stringResource(R.string.ayarlar_toplanan), style = MaterialTheme.typography.titleMedium)
            Text("• " + stringResource(R.string.veri_not))
            Text("• " + stringResource(R.string.veri_paylasim))
            Spacer(Modifier.height(8.dp))
            ToplayiciBolumu(depo)
            Spacer(Modifier.height(8.dp))
            AktarimBolumu(depo, eslestir, pil)
            Spacer(Modifier.height(8.dp))
            Text(stringResource(R.string.ayarlar_hata_raporu_bilgi), color = MaterialTheme.colorScheme.secondary)
            OutlinedButton(
                onClick = { raporuKopyala(ctx, depo) },
                modifier = Modifier.fillMaxWidth().testTag("hata_raporu_btn"),
            ) { Text(stringResource(R.string.ayarlar_hata_raporu)) }
            TextButton(onClick = hakkinda, modifier = Modifier.testTag("hakkinda_btn")) { Text(stringResource(R.string.ayarlar_hakkinda)) }
        }
    }
}

private fun raporuKopyala(ctx: Context, depo: Depo) {
    val pano = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    pano.setPrimaryClip(ClipData.newPlainText("Hata raporu", depo.hataRaporu()))
    depo.gunluk.bilgi("rapor", "hata raporu kopyalandi")
    Toast.makeText(ctx, R.string.hata_raporu_kopyalandi, Toast.LENGTH_SHORT).show()
}

@Composable
private fun HakkindaEkrani(depo: Depo, geri: () -> Unit) {
    Cerceve(stringResource(R.string.hakkinda_baslik), geri) { mod ->
        Column(mod.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.hakkinda_surum, BuildConfig.VERSION_NAME), modifier = Modifier.testTag("surum"))
            Text(stringResource(R.string.hakkinda_cihaz, depo.cihazId.take(8)), modifier = Modifier.testTag("cihaz_kimligi"))
            Text(stringResource(R.string.hakkinda_gizlilik), style = MaterialTheme.typography.titleMedium)
            Text(stringResource(R.string.hakkinda_lisans))
        }
    }
}

@Composable
private fun aktarimMetni(d: AktarimDurumu): String? = when (d) {
    AktarimDurumu.Bosta -> null
    AktarimDurumu.Araniyor -> stringResource(R.string.ak_araniyor)
    is AktarimDurumu.Gonderiliyor -> stringResource(
        R.string.ak_gonderiliyor, d.dosyaNo, d.dosyaSayisi,
        android.text.format.Formatter.formatShortFileSize(LocalContext.current, d.bayt),
        android.text.format.Formatter.formatShortFileSize(LocalContext.current, d.toplamBayt),
    )
    is AktarimDurumu.Tamam -> stringResource(R.string.ak_tamam, d.dosya, d.kayit)
    is AktarimDurumu.Hata -> stringResource(
        when (d.kod) {
            "eslesme_yok" -> R.string.ak_hata_eslesme_yok
            "yetkisiz" -> R.string.ak_hata_yetkisiz
            "sertifika" -> R.string.ak_hata_sertifika
            "ulasilamadi" -> R.string.ak_hata_ulasilamadi
            "reddedildi" -> R.string.ak_hata_reddedildi
            "bekle" -> R.string.ak_hata_bekle
            "pc_tamamlayamadi" -> R.string.ak_hata_pc_tamamlayamadi
            "durduruldu" -> R.string.ak_hata_durduruldu
            "kutu" -> R.string.ak_hata_kutu
            else -> R.string.ak_hata_sunucu
        },
    )
}
