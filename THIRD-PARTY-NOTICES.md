# Üçüncü taraf bileşenler

Kimlik Merkezi kendi kodunu MIT lisansıyla sunar (bkz. `LICENSE`). Aşağıdaki bileşenler kendi
lisanslarıyla gelir. Bu belge hukuki danışmanlık değildir.

**Doğrulama durumu (2026-11-10):** lisans türleri, temiz bir sanal ortamda
`pip install ./core ./server ./importers "./windows[tepsi]"` ile kurulan paketlerin üst verisinden
(`License-Expression`, `License ::` sınıflandırıcıları, `License` alanı) `windows/paket/sbom_uret.py`
ile okundu. Bu ortam **Linux**'tur; Windows paketine ek giren tek platforma özgü bağımlılık `pywin32`
(`mcp` ister) ayrıca incelendi (Windows tekerleği üst verisi). Sürümler kısıtlı değildir (yalnız `mcp`,
`pystray`, PyInstaller sabit); her yayında **o yayının SBOM'u** (`*.sbom.cdx.json`) gerçekte pakete giren
sürümleri ve lisansları gösterir ve bu tablodan üstündür. Üst veride lisansı belirtilmeyen paket çıkmadı.

## Doğrudan kullanılan ve pakete giren ana bileşenler

| Bileşen | Kullanım | Lisans |
|---|---|---|
| Apache ECharts 6.1.0 | Grafikler (yerelde paketli, CDN yok) | Apache-2.0 (`windows/src/kimlikwin/statik/ECHARTS-LICENSE.txt`, `ECHARTS-NOTICE.txt`) |
| mcp (Python SDK) 2.3.0 | MCP sunucusu | MIT |
| ijson | Akışlı JSON ayrıştırma | BSD-3-Clause AND ISC |
| pypdf | PDF metni | BSD-3-Clause |
| python-docx | DOCX metni | MIT |
| Pillow | Görsel üst verisi, tepsi simgesi | MIT-CMU (HPND benzeri) |
| pystray 0.19.5 (tepsi için, pakete dahil) | Windows tepsi simgesi | **LGPL-3.0** (üst veride "LGPLv3"), aşağıdaki nota bakın |
| CPython 3.13 | Paketle gömülen çalışma zamanı | Python-2.0 (PSF) |
| PyInstaller 6.22.3 | Paket oluşturma (yalnız derleme aracı; önyükleyicisi pakete girer) | GPL-2.0-or-later + paketlenen programa bulaşmayan özel istisna (üst veride yazılı) |
| Inno Setup | Kurulum programı oluşturma (derleme aracı) | Inno Setup Lisansı (serbest) |

## Dolaylı bağımlılıklar (pip üst verisinden)

Pakete giren Python bağımlılıklarının kapanışı (Linux ortamı; `pystray` için `python-xlib` aşağıda ayrıca):

| Paket | Sürüm | Lisans |
|---|---|---|
| annotated-types | 0.8.0 | MIT |
| anyio | 4.16.0 | MIT |
| attrs | 26.1.0 | MIT |
| cffi | 2.1.1 | MIT-0 |
| click | 8.5.1 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| h11 | 0.16.0 | MIT License |
| httpcore2 | 2.16.0 | BSD-3-Clause |
| httpx2 | 2.16.0 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| ijson | 3.6.0 | BSD-3-Clause AND ISC |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| lxml | 6.1.3 | BSD-3-Clause |
| mcp | 2.3.0 | MIT License |
| mcp-types | 2.3.0 | MIT License |
| opentelemetry-api | 1.45.2 | Apache-2.0 |
| pillow | 13.0.0 | MIT-CMU |
| pycparser | 3.12 | BSD-3-Clause |
| pydantic | 2.14.3 | MIT |
| pydantic_core | 2.50.4 | MIT |
| PyJWT | 2.15.1 | MIT |
| pypdf | 7.0.0 | BSD-3-Clause |
| pystray | 0.19.5 | GNU Lesser General Public License v3 (LGPLv3) |
| python-docx | 1.2.0 | MIT License |
| python-multipart | 0.0.33 | Apache-2.0 |
| referencing | 0.37.0 | MIT |
| rpds-py | 2026.9.1 | MIT |
| six | 1.17.0 | MIT License |
| sse-starlette | 3.7.0 | BSD-3-Clause |
| starlette | 1.10.0 | BSD-3-Clause |
| truststore | 0.10.5 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.5 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| pywin32 (yalnız Windows; `mcp` ister) | 312 | PSF (üst veri; ayrıca `adodbapi`, Scintilla, MAPI stub kitaplığı gibi bölümlerin kendi lisans dosyaları var) |

Notlar:
- `python-xlib` 0.33 (LGPL-2.1-or-later; üst veride "LGPLv2+"): `pystray` onu yalnızca **Linux**'ta ister
  (`sys_platform == "linux"`); Windows paketine **girmez**.
- `Pillow`, `lxml`, `cryptography` gibi paketlerin tekerlekleri yerel (derlenmiş) kitaplıklar içerebilir;
  bunların kendi lisans dosyaları tekerleğin `dist-info` klasöründedir. Windows tekerlekleri için tek tek incelenmedi.
- `cryptography` iki lisanslıdır (Apache-2.0 **veya** BSD-3-Clause).

## Lisans metinleri paketle birlikte geliyor mu? (dürüst kontrol)

PyInstaller spec'i ve Inno Setup betiği okundu; ayrıca aynı PyInstaller sürümüyle (6.22.3), aynı düzende
küçük bir **Linux** deneme derlemesi yapılıp çıktı incelendi. Sonuç:
- Kurulum paketine **`LICENSE`, bu dosya ve LGPL/GPL metinleri konmuyor**. Yalnızca ECharts'ın lisans/bildirim dosyaları
  (`statik/` içinde) ve Python paketlerinin kendi içindekiler geliyor; deneme derlemesinde `pystray`in
  `COPYING.LGPL` dosyası çıktıda yoktu. MIT/BSD/Apache/LGPL lisanslarının çoğu, ikili dağıtımda telif ve lisans
  metninin bulunmasını ister. **Eksik.** Önerilen düzeltme (bu değişiklikte yapılmadı): `kimlikmerkezi.spec`
  `datas` listesine `LICENSE`, `THIRD-PARTY-NOTICES.md` ve `pystray`in `COPYING*` dosyalarını eklemek.

## pystray hakkında not (LGPL-3.0)

pystray ayrı bir kütüphane olarak kullanılır, kodu **değiştirilmemiştir** ve yalnızca tepsi simgesi içindir
(`windows[tepsi]` isteğe bağlı eki; kod, pystray yoksa tepsisiz de çalışır). Kaynağı:
https://github.com/moses-palmer/pystray (üst verideki ana sayfa).

Paket yapısı kontrolü (`windows/paket/kimlikmerkezi.spec`, `KimlikMerkezi.iss`):
- **Klasör tipi (onedir) paket:** evet. Spec `COLLECT` kullanır, Inno Setup `dist\KimlikMerkezi` klasörünü
  olduğu gibi kurar (`recursesubdirs`). Tek dosyalık (onefile) paket değildir.
- **pystray kullanıcı tarafından ayrı dosya olarak değiştirilebilir mi: HAYIR (şu an).** `pystray` saf Python'dur ve
  PyInstaller varsayılanıyla modüller `KimlikMerkezi.exe` içindeki sıkıştırılmış bir arşive (PYZ) gömülür. Aynı
  PyInstaller sürümü ve aynı spec yapısıyla yapılan deneme derlemesinde (Linux) çıktı klasöründe hiç `pystray`
  dosyası yoktu; `archive_viewer` ile modüllerin exe içinde olduğu görüldü. Windows'ta derlenmiş gerçek paket bu
  oturumda incelenmedi ama mekanizma aynıdır. Yani kullanıcı kurulu klasörde kütüphaneyi dosya olarak
  değiştiremez.
- **Önerilen düzeltme (yapılmadı, spec davranışı değişir):** `Analysis(..., noarchive=True)` kullanmak. Aynı deneme
  derlemesinde bu ayarla `_internal/pystray/*.pyc` dosyaları ayrı çıktı; kullanıcı, değiştirilmiş pystray'ı aynı
  Python sürümüyle derleyip bu dosyaların yerine koyabilir. Daha sağlam alternatif, pystray'ı derlemeye hiç
  katmayıp ayrı bir klasörden yüklemektir. Hangisinin LGPL-3.0 §4'ü karşıladığı hukuki değerlendirme ister.

Şu anki dürüst durum ve kullanıcıya sunulan yol:
1. Uygulamanın tüm kaynak kodu (MIT) ve paketleme betikleri herkese açıktır; pystray sürümü `windows/paket/gereksinim.txt`
   içinde sabittir (`pystray==0.19.5`).
2. **Değiştirilmiş pystray ile kendi paketinizi üretmek için:** depoyu indirin; `pip install ./core ./server ./importers`
   ve `pip install "./windows[tepsi]"` sonrasında kendi (değiştirilmiş) pystray'ınızı `pip install` ile kurun
   (`pip install --force-reinstall --no-deps <değiştirilmiş-pystray-klasörü>`); sonra `windows/paket` klasöründe
   `python simge_uret.py` ve `python -m PyInstaller --noconfirm kimlikmerkezi.spec` çalıştırın, Inno Setup ile
   `KimlikMerkezi.iss` derleyin. (Adımlar betik/CI akışından yazılmıştır; bu oturumda Windows'ta uçtan uca
   denenmedi.)
3. Doğrudan kurulu pakette değiştirme (yukarıdaki `noarchive` değişikliğinden sonra) ayrıca belgelenecektir; **şu an
   desteklenmiyor**, bu yüzden "kullanıcı kütüphaneyi kendisi değiştirebilir" iddiasında bulunmuyoruz.
