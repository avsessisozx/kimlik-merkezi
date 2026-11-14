# Ağ garantisi

Bu belge, "Kimlik Merkezi dışarıya yalnız kullanıcının kapatabildiği tek bir yoldan (GitHub sürüm denetimi)
bağlanabilir" iddiasının tam olarak ne anlama geldiğini, nasıl sınandığını ve nelerin bu iddianın DIŞINDA
kaldığını açıkça yazar. Sınanmamış bir şeyi "garanti" diye yazmıyoruz.

> **Değişiklik notu:** Önceki sürümlerde bu belge "uygulama hiç ağa bağlanmaz" diyordu. Uygulama içi güncelleme
> eklendiği için bu artık DOĞRU DEĞİLDİR: Windows uygulaması varsayılan olarak (kullanıcı Ayarlar'dan kapatmadıkça)
> açılışta GitHub'ın herkese açık sürüm listesine bağlanır. İndirme ve kurulum yalnız kullanıcı onayıyla yapılır.

## Ne garanti ediliyor

1. Kimlik Merkezi'nin kendi kodu (`core/`, `server/`, `importers/`, `windows/`), **güncelleme modülü hariç**,
   internete bağlanmaz: bulut servisi, telemetri, hata raporu gönderimi ve CDN'den yükleme yoktur.
2. **Tek istisna: `windows/src/kimlikwin/guncelleme.py`** (aşağıda "Güncelleme istisnası"). Uygulamanın ağa çıkan
   TEK yoludur; başka hiçbir modül ağ açamaz (statik denetim testle kilitler).
3. Güncelleme denetimi **varsayılan olarak AÇIKTIR**; ilk açılış sihirbazında ve Ayarlar'da açıkça yazılıdır ve
   kapatılabilir. Kapalıyken (ve "Güncellemeleri denetle" düğmesine basılmadıkça) uygulama internete bağlanmaz.
   0.1.1 ve öncesinden gelen kullanıcılara, otomatik denetim başlamadan önce bir kez bilgi gösterilir.
4. Denetim yalnız sürüm listesini sorar: genel kullanıcı ajanı `KimlikMerkezi-guncelleme`; sürüm numaranız, adınız,
   verileriniz, makine adınız gönderilmez (IP adresiniz GitHub tarafından görülür; bunu engelleyemeyiz).
5. **İndirme ve kurulum yalnız kullanıcı onayıyla:** "Yeni sürüm X var, indirmek ister misin?" onayı olmadan
   hiçbir dosya indirilmez; indirme bitip SHA-256 doğrulanınca "Şimdi kurmak ister misin?" diye İKİNCİ kez sorulur.
   Kod düzeyinde `indir(onay=True)` / `kur(onay=True)` anahtar sözcüğü ister; testler onaysız çağrıların hiçbir
   dosya/istek üretmediğini sınar.
6. Bunun dışındaki tek ağ kullanımı yerel web arayüzüdür: yalnız `127.0.0.1` üzerinde dinler (başka bilgisayarlar
   erişemez) ve kurulu uygulama yalnız kendi `http://127.0.0.1:<port>/` adresiyle konuşur.
7. Web arayüzü dosyaları (HTML/JS/CSS/grafik kütüphanesi) pakete gömülüdür; internetsiz çalışır.
8. MCP sunucusu ağ değil standart girdi/çıktı (stdio) kullanır; ağa açılmaz.

Bu maddeler "testlerde ve CI'de bir ihlal görülmedi" demektir; aşağıdaki sınırlarla birlikte okunmalıdır.

## Güncelleme istisnası (`guncelleme.py`)

| Konu | Kural | Nerede kilitli |
|---|---|---|
| Ana makineler | yalnız `api.github.com` (sürüm listesi), `github.com` (release dosyası adresi) ve GitHub'ın release depolaması (`objects.githubusercontent.com`, `release-assets.githubusercontent.com`; `github.com` bunlara yönlendirir) | `IZINLI_ANA_MAKINELER`; `test_guncelleme_istisnasi_dar` kümenin aynen bu olduğunu denetler |
| Protokol | yalnız https, adreste kullanıcı bilgisi ya da başka port yok | `adres_denetle`; test_guncelleme.py |
| Yönlendirme | her yönlendirme aynı beyaz listeden geçer; http/file/ftp ya da başka ana makineye yönlendirme işlemi durdurur | `_YonlendirmeDenetci`; test_guncelleme.py |
| Adres | indirme adresi yalnız bu deponun `releases/download/<etiket>/<dosya>` yolu olabilir | `en_yeni_aday`; test_guncelleme.py |
| Dosya adı | `KimlikMerkezi-Kurulum-v….exe` katı kalıbı, yol ayracı/`..` yok; yalnız ayar dizinindeki `guncelleme/` klasörüne yazılır | `EXE_KALIBI`, `_yollar` |
| Tek çıkış | modülde tek ağ çağrısı vardır (`self._opener.open`); kapatma anahtarı ve adres denetimi ondan önce çalışır | `test_guncelleme_istisnasi_dar` (AST) |
| Başka modül | `urllib.request`, `socket`, `ssl`, `http.client` vb. içe aktaran başka modül testi kırmızı yapar; istisna yalnız bu dosya + `urllib.request` içindir | `IZINLI_ISTISNALAR`, `test_baska_modul_ag_acarsa_test_kirmizi` |
| Test politikası | https zorunluluğunu/ana makine listesini gevşeten `AgPolitikasi` yalnız testlerde kurucuya verilir; uygulama kaynağında hiçbir yerde kullanılmaz | `test_guncelleme_istisnasi_dar` (5) |
| Kapatma | Ayarlar'daki seçenek; ayrıca `KIMLIK_GUNCELLEME=kapali` ortam değişkeni her ağ erişimini keser (CI ve testler) | `Guncelleme._ac` |
| Doğrulama | SHA-256, yalnız aynı sürüm sayfasındaki `SHA256SUMS.txt` ile. Uyuşmazsa dosya silinir. **Kurulum paketi imzasızdır**; GitHub hesabı/yayını ele geçirilirse paket ve toplam birlikte değişebilir, bu doğrulama onu yakalamaz | SECURITY.md, TEHDIT-MODELI.md 2.6 |
| Kurulum | uygulama veri klasörünü bıraktıktan SONRA Inno Setup sessiz bayraklarıyla başlatılır; veri klasörüne dokunulmaz; kurulum sonrası uygulama yeniden açılır | `kurulum_komutu`, `KimlikMerkezi.iss`, Windows CI "üstüne kurulum" adımı |

**Testlerde ağ koruması:** `ag_koruma.py` çalışma zamanı koruması bu istisna için GEVŞETİLMEDİ. Testler gerçek
GitHub'a çıkmaz: güncelleme testleri sahte yerel sunucuya (`127.0.0.1`) bağlanır ve üretim politikasıyla yapılan
bir istek testte `AgIhlali` ile engellenir (`test_testler_gercek_github_a_cikamaz`). Yani ağ koruması, bu modülün
GitHub'a gerçekten bağlanabildiğini değil, adres/politika mantığının doğru olduğunu sınar.

**Windows CI'da denetim kapalıdır** (`ci_paket.ps1` `KIMLIK_GUNCELLEME=kapali` verir; kurulu uygulama ve
kurulum programının yeniden açtığı kopya bunu devralır). `ag_izle.ps1` bu yüzden hiçbir GitHub istisnası TANIMAZ:
CI'da 127.0.0.1 dışındaki her bağlantı ihlaldir. `kurulu_dene.py` ayrıca donmuş exe içinde bu anahtarın denetimi
gerçekten kapattığını ve onaysız indirmenin reddedildiğini sınar.

## Nasıl test ediliyor

| Katman | Ne yapar | Nerede |
|---|---|---|
| Çalışma zamanı koruması | Testler sürerken `socket.connect/connect_ex/sendto`, `socket.create_connection`, `getaddrinfo`, `gethostbyname*` sarılır. Hedef yerel değilse (127.0.0.0/8, `::1`, `localhost`, Unix soketi, makinenin kendi adı/adresleri dışında) çağrı yapılmaz, ihlal kaydedilir ve istisna yutulsa bile o test BAŞARISIZ olur. Yeni bağımlılık yok. | `ag_koruma.py` (kök), kök ve paket `conftest.py` dosyaları; `core`, `server`, `importers`, `windows`, `entegrasyon` ve `buyuk` testlerinde varsayılan açık |
| Korumanın kendi testi | Dış hedefin engellendiği, yerelin serbest olduğu, yutulan ihlalin yine de testi bozduğu denenir. | `entegrasyon/test_ag_garantisi.py` (A) |
| Statik denetim (Python) | AST ile `requests`, `urllib.request`, `http.client`, `socket`, `ssl`, `ftplib`, `smtplib`, `webbrowser`, telemetri kütüphaneleri vb. içe aktarımı aranır; kaynakta `http(s)://` adresleri ve CDN/telemetri adları (cdn., googleapis, jsdelivr, unpkg ...) aranır. İzinli istisnalar dosya + gerekçeyle listelidir; listede olup kullanılmayan istisna da hata verir. | `entegrasyon/test_ag_garantisi.py` (B) |
| Statik denetim (arayüz) | `windows/src/kimlikwin/statik` içinde harici URL, uzak `src/href`, `@import`, `url(http...)`, uzak `fetch`, `XMLHttpRequest`, `WebSocket`, `sendBeacon` yok. | aynı dosya (C) |
| Paket CI'si (Windows) | Güncelleme denetimi KAPALI (`KIMLIK_GUNCELLEME=kapali`). Kurulu uygulama başlatılıp sihirbaz, içe aktarma ve gerçek MCP stdio akışı yürütülürken `Get-NetTCPConnection` ile `KimlikMerkezi` ve `kimlikmerkezi-mcp` süreçleri (ve alt süreçleri) yoklanır; 127.0.0.1/::1 dışında uzak adres ya da dış arayüzde dinleme görülürse paket işi kırılır. Sonuç `ag_sonuc.json` olarak yüklenir. | `windows/paket/ag_izle.ps1`, `windows/paket/ci_paket.ps1`, `.github/workflows/paket.yml` |

Kuraldan sapmak gerekirse (ör. yeni bir kütüphane) istisna bilerek, gerekçesiyle `IZINLI_ISTISNALAR`
listesine eklenir; sessizce geçmez. Güncelleme istisnası da böyle eklenmiştir ve yukarıdaki testlerle kilitlidir.

### Mevcut izinli istisnalar (Python kaynağı)

- `core/src/kimlikcore/lock.py`: `socket.gethostname()` (kilit dosyasına makine adı); bağlantı yok.
- `windows/src/kimlikwin/web.py`: `127.0.0.1`'e bağlanarak boş port bulma ve yerel sunucu.
- `windows/src/kimlikwin/guncelleme.py`: `urllib.request` ile GitHub sürüm denetimi/indirme (yukarıdaki "Güncelleme
  istisnası" tablosu); kullanıcı kapatabilir, indirme/kurulum onaylıdır. Python kaynağında yalnız `https://api.github.com`
  ve `https://github.com` sabitleri bulunur.
- `windows/src/kimlikwin/uygulama.py`: `urllib.request` ile yalnız `http://127.0.0.1:<port>/saglik`;
  `webbrowser` ile yalnız kendi yerel adresini kullanıcının tarayıcısında açma.
- Arayüz dosyalarında yalnız ağa gitmeyen metinler: SVG/XML ad alanı tanımlayıcıları (`www.w3.org`),
  lisans metinleri (`www.apache.org`, `github.com`).

## Neler garanti EDİLMİYOR (dürüst sınırlar)

- **GitHub ve ağ yolundaki taraflar.** Güncelleme denetimi/indirmesinde GitHub (ve sistem vekil sunucusu, ağ yöneticisi,
  internet sağlayıcınız) IP adresinizi ve bir sürüm sorgusu yaptığınızı görür. Denetimi kapatarak bundan kaçınırsınız.
  Gerçek GitHub'a karşı uçtan uca indirme (özellikle `github.com` -> depolama yönlendirmesinin güncel ana makine adları)
  bu depoda otomatik denenmez; sahte sunucuyla sınanan davranış gerçek GitHub'ın belgelenmiş davranışına dayanır.
- **İmzasız paket.** Güncelleme doğrulaması yalnız `SHA256SUMS.txt` iledir (bkz. SECURITY.md).
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
  sihirbazı (Inno Setup) ve kaldırma izlenmez (güncelleme akışında kurulum programı da izlenmez); izlenen kısım kurulu uygulamanın başlatma, sihirbaz,
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
