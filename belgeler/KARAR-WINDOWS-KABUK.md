# Karar B (Windows kabuğu) ve Karar C (MCP kütüphanesi) — İ6 raporu

Tarih: 2026-11-09. Seçimi kullanıcı yapar; aşağısı yalnızca öneridir. Deneme kodu: dal `iscilik/spikes`, `spikes/win/` ve `spikes/mcp/`. CI çalıştırmaları: `win-web` #42694798642, `win-qt` #42695290862 (her biri bir kez).

## Karar B

### Adım 1: masa başı eleme (dört aday)

| Ölçüt | 1. PyInstaller + yerel web + tepsi | 2. Python + PySide6 | 3. .NET self-contained | 4. Tauri (Rust) |
|---|---|---|---|---|
| Çekirdek Python kalır, ek maliyet | Yok, tek yapı | Yok, tek yapı | Python çekirdek ayrıca PyInstaller ile paketlenip yan süreç olur: iki araç zinciri, iki bakım. MCP girişi zaten Python exe olmak zorunda. | Aynısı. Tauri belgesi de Python'u PyInstaller ile "sidecar" paketlemeyi öneriyor. Üstüne Rust araç zinciri. |
| Kurulum paketi CI'de | Ölçüldü: evet (PyInstaller + Inno Setup) | Ölçüldü: evet | Mümkün görünüyor, ölçülmedi | NSIS (Linux'ta da) / MSI (yalnız Windows'ta), belgede var; ölçülmedi |
| Kullanıcı bazlı kurulum | Inno `PrivilegesRequired=lowest`, ölçüldü | Aynı | Paketleyici ayrıca seçilir (ör. Inno) | Varsayılan: yalnız bu kullanıcı, yönetici gerekmez (belge) |
| SQLite FTS5 | Ölçüldü: var | Ölçüldü: var | Python tarafında aynı; .NET tarafında ayrıca denenmeli | Python tarafında aynı |
| Tepsi + girişte başlama | pystray 0.19.5 (son sürüm 2023-09, LGPLv3) + HKCU Run: ölçüldü | QSystemTrayIcon + HKCU Run: ölçüldü | Hazır sınıf var (NotifyIcon, WinForms), ölçülmedi | Resmî eklenti (autostart) ve tepsi var, ölçülmedi |
| Boyut | 23,2 MB paket (ölçüldü) | 36,9 MB paket (ölçüldü) | Bilinmiyor + Python çekirdek paketi eklenir | Bilinmiyor + Python çekirdek paketi eklenir; WebView2 Windows 10/11'de işletim sisteminde hazır (belge) |
| stdio MCP | Ayrı konsol exe, ölçüldü | Aynı | Python MCP exe şart | Python MCP exe şart |
| Claude'un güvenilir yazabildiği dil | Python + HTML/JS | Python (Qt API geniş, daha çok hata payı) | C# iyi, ama çekirdekle iki dil | Rust + Python + JS: üç dil |
| Antivirüs yanlış alarmı | Defender taraması temiz (tek motor) | Aynı | Ölçülmedi | Ölçülmedi |
| Lisans (doğrulanan) | PyInstaller GPLv2+ ama paketlenen uygulamaya (ticari dahil) izin veren özel istisnayla | PySide6 LGPL-3.0 / GPL | .NET çalışma zamanı MIT | Tauri Apache-2.0 veya MIT |

**Elenenler:** .NET ve Tauri. Gerekçe tek: çekirdek Python kalacağı için ikisi de Python'u yine paketler (yan süreç), yani iki yapı, iki dil (Tauri'de üç), iki bakım yükü; kazandırdıkları (daha küçük arayüz kabuğu, yerel görünüm) bu maliyeti karşılamıyor ve bu proje için ölçmeye değer bulunmadı. Kullanıcı isterse ölçtürülür. Bunlarda boyut, antivirüs ve Windows 10 desteği hiç ölçülmedi/okunmadı.

### Adım 2: CI ölçümü (`windows-latest` = Windows Server 2025, build 26100; Python 3.13.17, PyInstaller 6.22.3, Inno Setup 6.7.1 hazır kurulu geliyor)

Her iki adayda aynı örnek: FTS5 sorgusu, tepsi simgesi, ayrı konsol exe ile stdio MCP (resmî SDK mcp 2.3.0), PyInstaller + Inno Setup, sessiz kurulum, kaldırma.

| Ölçüt | Web + tepsi | PySide6 |
|---|---|---|
| PyInstaller derleme | 55,8 sn | 87,9 sn |
| Klasör boyutu (kurulu) | 65,3 MB | 124,6 MB |
| Kurulum paketi | 23,2 MB | 36,9 MB |
| Inno derleme | 17,6 sn | 40,0 sn |
| Sessiz kurulum / kaldırma | 4,2 sn / 1,2 sn, çıkış 0 | 6,7 sn / 1,2 sn, çıkış 0 |
| Yönetici izni | gerekmedi (`%LOCALAPPDATA%\Programs`) | gerekmedi |
| FTS5 (SQLite 3.50.4) | var, sorgu doğru | var, sorgu doğru |
| Tepsi simgesi | `visible=true` | `isSystemTrayAvailable` ve `isVisible` true |
| Pencere / yerel HTTP | `/saglik` ok, ana sayfa sorgu sonucu gösteriyor | pencere görünür |
| Girişte başlama (HKCU Run) | kurucu yazdı, uygulama aç/kapat çalıştı, kaldırma sildi | aynı |
| stdio MCP el sıkışması + araç çağrısı | geçti, 1,26 sn | geçti, 1,21 sn |
| Kaldırınca veri | silinmedi (istenen davranış) | silinmedi |
| Defender taraması (kurulum paketi) | tehdit yok | tehdit yok |
| Toplam iş süresi (ilk çalıştırma, önbelleksiz) | ~2 dk 29 sn | ~3 dk 20 sn |

Ek bulgu: pencereli (`console=False`) exe'ye `mcp` argümanı verildiğinde de stdio el sıkışması geçti (iki adayda). Yine de önerim ayrı konsol exe (`kimlikmerkezi-mcp.exe`): Aşama 3'te "pencere göstermez" şartı için daha güvenli; pencereli exe ile bu yalnızca bu denemede çalıştı, başka istemcilerle (Claude Desktop) denenmedi.

### Öneri

**Web + tepsi (aday 1)**, daha küçük, daha hızlı derleniyor, arayüz HTML olduğu için Claude'un yazması ve test etmesi kolay. **Ama bir sorun var, ölçmedim:** Aşama 7 "zip/klasör sürükle-bırak" ister. Tarayıcı, sürüklenen dosyanın disk yolunu uygulamaya vermez; ya çok GB'lık arşiv HTTP ile yüklenir ya da yerel sunucu bir dosya seçme penceresi açar. Bu tasarım riski. PySide6'da sorun yok (yol doğrudan gelir), bedeli +14 MB paket, +1 dk derleme. Ayrıca pystray 2023'ten beri sürüm almamış; çalışıyor ama bakım riski var. Kararı etkileyen tek asıl soru: sürükle-bırak veya yerel pencere hissi önemli mi? Önemliyse PySide6, değilse web + tepsi.

### Bilinmeyenler
- Windows 10 üzerinde çalışma ölçülmedi (runner Server 2025). Belgeler: PyInstaller Windows 8+; Python 3.13 resmî olarak Windows 10+ ister (hafızadan, doğrulanmadı); .NET 10 için Windows 10 desteği okunamadı (learn.microsoft.com erişime kapalı).
- Tepsi simgesinin gerçekten bildirim alanında göründüğü runner'da gözle doğrulanamaz; yalnızca API "görünür" dedi. Gerçek masaüstünde kullanıcı testi gerekir.
- SmartScreen uyarısı ölçülemez; Defender dışı antivirüsler denenmedi. İmzasız exe için uyarı beklenir (GOREV Aşama 7).
- Önbellekli (ikinci) çalıştırma süresi ölçülmedi; tekrar çalıştırılmadı.
- GitHub Actions dakikası: iki iş toplam ~5,8 dk Windows (özel depoda katsayı uygulanır).
- Inno Setup lisans metninin tamamı okunmadı (yalnızca başı: "as-is", telif Jordan Russell/Martijn Laan).
- Rapor için `workflow_dispatch` kullanılamadı: dosya varsayılan dalda (main) yokken GitHub dispatch'i kaydetmiyor (404). Bu yüzden iki iş akışı yalnız bu dalda `push` ile, tek bir tetik dosyasına (`spikes/TETIK-win-*`) bağlı çalışıyor. main'e girmez.

## Karar C: resmî Python SDK ile bağımsız `fastmcp`

| | Resmî SDK (`mcp`) | `fastmcp` |
|---|---|---|
| Güncel sürüm (PyPI) | 2.3.0 (2026-10-02); 2.0.0 2026-07-28; 1.x kolu da sürüm alıyor (1.30.0, 2026-09-07) | 4.1.6 (2026-11-03); 4.2.0 alfa var; 3.4.x kolu da sürüm alıyor |
| Sürüm temposu | Birkaç haftada bir | Haftada birkaç sürüm (20 Eki - 3 Kas arası 5 sürüm) |
| Lisans | MIT | Apache-2.0 |
| Python | PyPI: >=3.10; README: 3.11+ (tutarsız, kurulumda 3.13 ile denendi) | >=3.10 |
| Bağımlılık | Tek paket | `fastmcp-slim` + resmî `mcp` (kurulumda mcp 2.3.0 geldi), httpx2, starlette, uvicorn vb. |
| stdio | Var, denendi | Var, denendi |
| Kurulu boyut (Linux site-packages) | 39 MB | 51 MB |
| Sunucu başlat + el sıkış + çağrı (Linux, 2 deneme) | 0,58-0,71 sn | 1,03-1,16 sn; stderr'e afiş basıyor (`show_banner=False` ile kapanmadı, araştırılmadı) |

Doğrulama: aynı küçük `ara` aracı iki kütüphaneyle yazıldı, resmî SDK istemcisiyle (Linux, mcp 2.3.0) araç listesi `['ara']` döndü ve çağrı sonuç verdi (`spikes/mcp/`). Donmuş exe (PyInstaller) içinde yalnızca resmî SDK denendi ve Windows CI'de geçti; fastmcp donmuş exe'de ve Windows'ta denenmedi.

**Öneri: resmî SDK, `mcp==2.3.0` sabit.** Gerekçe: Aşama 3 yalnızca stdio ve birkaç salt-okunur araç istiyor; fastmcp'nin ek özellikleri (uygulamalar, istemci, sunucu bileşimi) gerekmiyor, bağımlılığı fazla, sürümü çok hızlı değişiyor ve zaten resmî SDK üstünde. fastmcp'nin üstünlüğü: daha az kod (`@mcp.tool`). Bu avantaj bu proje için küçük. Sürüm 1.x/2.x uyumsuzluğu nedeniyle sabitleme şart. Bilinmeyen: fastmcp'nin uzun vadeli yönü ve 4.x kırıcı değişiklik sıklığı ölçülmedi.
