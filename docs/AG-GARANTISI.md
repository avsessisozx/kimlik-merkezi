# Ağ garantisi

Bu belge, "Kimlik Merkezi dışarıya hiç bağlantı denemiyor" iddiasının tam olarak ne anlama geldiğini,
nasıl sınandığını ve nelerin bu iddianın DIŞINDA kaldığını açıkça yazar. Sınanmamış bir şeyi
"garanti" diye yazmıyoruz.

## Ne garanti ediliyor

1. Kimlik Merkezi'nin kendi kodu (`core/`, `server/`, `importers/`, `windows/`) internete bağlanmaz:
   bulut servisi, telemetri, güncelleme yoklaması, hata raporu gönderimi ve CDN'den yükleme yoktur.
2. Tek ağ kullanımı yerel web arayüzüdür: yalnız `127.0.0.1` üzerinde dinler (başka bilgisayarlar
   erişemez) ve kurulu uygulama yalnız kendi `http://127.0.0.1:<port>/` adresiyle konuşur.
3. Web arayüzü dosyaları (HTML/JS/CSS/grafik kütüphanesi) pakete gömülüdür; internetsiz çalışır.
4. MCP sunucusu ağ değil standart girdi/çıktı (stdio) kullanır; ağa açılmaz.

Bu maddeler "testlerde ve CI'de bir ihlal görülmedi" demektir; aşağıdaki sınırlarla birlikte okunmalıdır.

## Nasıl test ediliyor

| Katman | Ne yapar | Nerede |
|---|---|---|
| Çalışma zamanı koruması | Testler sürerken `socket.connect/connect_ex/sendto`, `socket.create_connection`, `getaddrinfo`, `gethostbyname*` sarılır. Hedef yerel değilse (127.0.0.0/8, `::1`, `localhost`, Unix soketi, makinenin kendi adı/adresleri dışında) çağrı yapılmaz, ihlal kaydedilir ve istisna yutulsa bile o test BAŞARISIZ olur. Yeni bağımlılık yok. | `ag_koruma.py` (kök), kök ve paket `conftest.py` dosyaları; `core`, `server`, `importers`, `windows`, `entegrasyon` ve `buyuk` testlerinde varsayılan açık |
| Korumanın kendi testi | Dış hedefin engellendiği, yerelin serbest olduğu, yutulan ihlalin yine de testi bozduğu denenir. | `entegrasyon/test_ag_garantisi.py` (A) |
| Statik denetim (Python) | AST ile `requests`, `urllib.request`, `http.client`, `socket`, `ssl`, `ftplib`, `smtplib`, `webbrowser`, telemetri kütüphaneleri vb. içe aktarımı aranır; kaynakta `http(s)://` adresleri ve CDN/telemetri adları (cdn., googleapis, jsdelivr, unpkg ...) aranır. İzinli istisnalar dosya + gerekçeyle listelidir; listede olup kullanılmayan istisna da hata verir. | `entegrasyon/test_ag_garantisi.py` (B) |
| Statik denetim (arayüz) | `windows/src/kimlikwin/statik` içinde harici URL, uzak `src/href`, `@import`, `url(http...)`, uzak `fetch`, `XMLHttpRequest`, `WebSocket`, `sendBeacon` yok. | aynı dosya (C) |
| Paket CI'si (Windows) | Kurulu uygulama başlatılıp sihirbaz, içe aktarma ve gerçek MCP stdio akışı yürütülürken `Get-NetTCPConnection` ile `KimlikMerkezi` ve `kimlikmerkezi-mcp` süreçleri (ve alt süreçleri) yoklanır; 127.0.0.1/::1 dışında uzak adres ya da dış arayüzde dinleme görülürse paket işi kırılır. Sonuç `ag_sonuc.json` olarak yüklenir. | `windows/paket/ag_izle.ps1`, `windows/paket/ci_paket.ps1`, `.github/workflows/paket.yml` |

Kuraldan sapmak gerekirse (ör. yeni bir kütüphane) istisna bilerek, gerekçesiyle `IZINLI_ISTISNALAR`
listesine eklenir; sessizce geçmez.

### Mevcut izinli istisnalar (Python kaynağı)

- `core/src/kimlikcore/lock.py`: `socket.gethostname()` (kilit dosyasına makine adı); bağlantı yok.
- `windows/src/kimlikwin/web.py`: `127.0.0.1`'e bağlanarak boş port bulma ve yerel sunucu.
- `windows/src/kimlikwin/uygulama.py`: `urllib.request` ile yalnız `http://127.0.0.1:<port>/saglik`;
  `webbrowser` ile yalnız kendi yerel adresini kullanıcının tarayıcısında açma.
- Arayüz dosyalarında yalnız ağa gitmeyen metinler: SVG/XML ad alanı tanımlayıcıları (`www.w3.org`),
  lisans metinleri (`www.apache.org`, `github.com`).

## Neler garanti EDİLMİYOR (dürüst sınırlar)

- **Kullanıcının bağladığı yapay zekâ istemcisi.** Claude, DeepSeek ya da başka bir istemci MCP ile
  bağlanırsa, o uygulamanın kendi ağ davranışı (aldığı veriyi kendi sunucusuna/modeline göndermesi
  dahil) bizim kontrolümüz dışındadır. Kimlik Merkezi yalnız izin verilen kategoriyi, salt okunur
  sunar; sunulan verinin istemcide ne olduğunu denetleyemez.
- **Windows'un ve diğer yazılımların kendi trafiği:** Windows telemetrisi, Windows Update, Defender,
  tarayıcı (arayüzü açtığınız tarayıcının eklentileri, senkronizasyonu, güvenli gezinti sorguları),
  kurulum sırasında Inno Setup ya da antivirüs. Bunlar uygulamanın kodu değildir.
- **Alt süreçler ve üçüncü taraf kod:** Python düzeyi koruma yalnız testi koşan süreci ve
  iş parçacıklarını kapsar; testlerin başlattığı alt süreçler (ör. MCP stdio çocuk süreci) bu korumanın
  dışındadır, onlar statik denetim ve paket CI'sindeki izlemeyle ele alınır. `ctypes`/yerel uzantılar
  (C kodu) Python `socket` işlevlerini atlayabilir; statik denetim bunları yakalamaz.
- **Paket CI'sindeki izleme örneklemedir.** Yoklama aralığından (~150 ms) kısa ömürlü bir TCP bağlantısı
  kaçabilir. UDP ve DNS sorguları (Windows'ta DNS'i `svchost` yapar) süreçle eşlenemez. Kurulum
  sihirbazı (Inno Setup) ve kaldırma izlenmez; izlenen kısım kurulu uygulamanın başlatma, sihirbaz,
  içe aktarma ve MCP stdio akışıdır. Bu adım kanıtı güçlendirir, tek başına mutlak kanıt değildir.
  Mutlak kanıt isteyen kullanıcı kendi güvenlik duvarında bu iki programın giden bağlantısını engelleyebilir.
- **Testlerin kapsadığı yollar.** Test edilmeyen bir kod yolu (ör. nadir bir hata dalı) ağa çıkıyorsa
  çalışma zamanı koruması bunu ancak o yol koşulursa görür; statik denetim yalnız bilinen kalıpları arar.
- **Ağ koruması testlerde varsayılan açıktır** ama `KIMLIK_AG_KORUMASI=kapali` ortam değişkeniyle kapatılabilir
  (hata ayıklama içindir; CI bunu kullanmaz).
- **Makinenin kendi adresi yerel sayılır.** Yerel sunucunun dış arayüze bağlı olmadığını sınayan
  mevcut test için, makinenin kendi adı ve arayüz IP'leri izinlidir (paketler makineden çıkmaz).
- Ağ güvenliği dışındaki konular (şifreleme, disk güvenliği, kötü amaçlı yazılım) bu belgenin kapsamında değil.

## Kendi makinenizde denemek

1. Python düzeyi: `python -m pytest entegrasyon` ve paket klasörleri (`core`, `server`, `importers`, `windows`) ayrı ayrı.
2. Yan denetim (isteğe bağlı): Windows'ta `Kaynak İzleyicisi > Ağ` ya da güvenlik duvarında
   `KimlikMerkezi.exe` ve `kimlikmerkezi-mcp.exe` için giden bağlantıyı engelleyip uygulamanın yine de çalıştığına bakın.
