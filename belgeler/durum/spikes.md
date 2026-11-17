# durum/spikes.md — işçi durumu ve Müdüre istekler

## Son durum (2026-11-09)
Karar B (Adım 1 + Adım 2) ve Karar C tamam. Rapor: /home/user/kimlik-durum/KARAR-WINDOWS-KABUK.md. Karar A yapılmadı (v0.1.0 sonrası).

## Yapıldı
- Adım 2 ölçümü GitHub Actions `windows-latest` üzerinde, her aday bir kez: win-web #42694798642 (başarılı), win-qt #42695290862 (başarılı). Sonuçlar iş günlüğünden okundu (artifact indirme bu ortamda engelli).
- Karar C: iki kütüphane Linux'ta resmî istemciyle denendi; sürümler `spikes/mcp/requirements-*.txt` içinde sabit.

## Müdüre istekler / dikkat
- Dal `iscilik/spikes` yalnız geçici spike içindir: `.github/workflows/win-*.yml` ve `spikes/` main'e GİRMEZ. Dal silinebilir.
- `workflow_dispatch` main'de dosya yokken kaydolmadığı için iş akışları bu dalda `push` + tek tetik dosyası (`spikes/TETIK-win-web`, `TETIK-win-qt`) ile çalışıyor.
- Raporun asıl açık sorusu kullanıcıya: "zip/klasör sürükle-bırak ve yerel pencere hissi önemli mi?" (önemliyse PySide6, değilse web + tepsi).
- Karar C önerisi: resmî SDK `mcp==2.3.0` sabit. GOREV Aşama 3 metnine uyuyor.
- Ağ: learn.microsoft.com, pyinstaller.org, v2.tauri.app, docs.github.com erişime kapalı; .NET'in Windows 10 desteği ve Python 3.13 Windows 10 desteği belgeden doğrulanamadı.

## Doğrulanmadı
Windows 10'da çalışma, SmartScreen, Defender dışı antivirüsler, .NET ve Tauri ölçümleri, ikinci (önbellekli) çalıştırma süresi.
