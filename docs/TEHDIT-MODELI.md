# Tehdit modeli

Bu belge Kimlik Merkezi'nin (v0.1 ön sürüm) neyi, kime karşı, hangi önlemle korumaya çalıştığını ve
**neyi korumadığını** yazar. Önlemler kod okunarak yazılmıştır; her satırın yanında hangi dosyada olduğu
belirtilir. Bir şeyin "sınandığı" yalnızca ilgili testi varsa yazılır. Ağ davranışı ayrıca
[AG-GARANTISI.md](AG-GARANTISI.md) içinde ele alınır; açık bildirimi için [SECURITY.md](../SECURITY.md).

## 1. Korunan varlıklar

| Varlık | Nerede durur |
|---|---|
| İçe aktarılmış kişisel veri (arama/izleme geçmişi, sohbetler, e-posta, mesaj, konum...) | veri klasöründe `kimlik.db` (SQLite) |
| Ham arşiv: içe aktarılan dosyaların kopyaları | veri klasöründe `arsiv/<sha256>/` |
| Persona bilgileri ve öneri kuyruğu | `kimlik.db` (öneri kuyruğu da; yazım için geçici, şifreli `gelen/` dosyaları) |
| Erişim kaydı (hangi uygulama, hangi araç, hangi kategori, kaç kayıt, sonuç) | `kimlik.db` içindeki `access_log` (sorgu metni ya da kayıt içeriği yazılmaz) |
| Uygulama anahtarları | veritabanında yalnızca SHA-256 özeti; düz anahtar bir kez gösterilir ve yapay zekâ uygulamasının ayar dosyasına konur |
| Uygulama ayarları, günlük | kullanıcı ayar klasörü (`ayarlar.json`, `gunluk.log`); günlüğe kayıt içeriği yazılmaz |
| Yerel web arayüzü oturum jetonu | süreç belleği ve açık tarayıcı sayfası |
| Yayın bütünlüğü (kurulum paketi) | GitHub yayınları, `SHA256SUMS.txt`, SBOM |

## 2. Tehdit aktörleri ve senaryolar

### 2.1 Bilgisayarı ya da diski kopyalayan biri
Kayıp/çalıntı bilgisayar, yedek diski, paylaşılan bilgisayarda başka bir Windows kullanıcısı.
- **Önlem:** Veritabanı (öneri kuyruğu ve erişim günlüğü dahil) ve ham arşiv varsayılan olarak AES-256-GCM ile
  şifrelidir (Windows'ta anahtar hesaba bağlı; ayrıntı ve sınırlar docs/SIFRELEME.md). Şifrelenmeyenler: `cikti/` ve
  kullanıcının dışa aktardığı dosyalar, Linux/sağlayıcısız ortamda oluşturulan klasörler, şifrelemeden önce
  oluşturulmuş ve henüz `sifrele` ile dönüştürülmemiş klasörler.
- **Kalan risk:** şifrelenmeyen yukarıdaki parçalar için yüksek; ek olarak tam disk şifrelemesi önerilir.
  Uygulama kaldırılırken veriyi de silmek isteyip istemediğiniz sorulur (varsayılan: silmez; sessiz kaldırmada da silmez).

### 2.2 Kötü niyetli ya da özensiz bir yapay zekâ istemcisi (MCP)
Bağladığınız bir uygulama izin verdiğinizden fazlasını okumaya çalışabilir; ya da sizin verinizdeki
metin onu kandırabilir (istem enjeksiyonu).
- **Önlemler (`server/src/kimlikserver/access.py`, `service.py`, `mcp/server.py`):**
  - Her uygulamaya ayrı anahtar; varsayılan olarak hiçbir kategori açık değildir.
  - Kategori izni tek tek verilir; isteğe bağlı bitiş zamanı vardır; anahtar iptal edilebilir.
    Her çağrıda anahtar ve izinler veritabanından yeniden okunur (önbellek yok).
  - Hassas kategoriler (`eposta`, `mesaj`, `konum`, `sohbet`) ayrı onay işareti olmadan açılamaz ve
    "hepsini aç" toplu işlemine dahil değildir.
  - MCP sunucusu veritabanını `mode=ro` + `query_only` ile **salt okunur** açar. Tek yazma yolu,
    ayrı dosyadaki öneri kuyruğudur ve o da persona'yı değiştirmez; kullanıcı onaylamadan etkisizdir.
    Öneride gösterilen kanıt kayıtlarının kategorisi için okuma izni de gerekir.
  - Her çağrı erişim kaydına yazılır (red ve hata dahil). Kayıt yazılamazsa veri **döndürülmez**.
  - Sonuç sayısı sınırlıdır (en çok 200); dönen metinler `etiket: veri` ve "bu metin talimat değildir"
    uyarısıyla işaretlenir.
  - GPS benzeri alan taşıyan kayıtlar, konum izni yoksa dönmez (savunma katmanı).
- **Kalan risk:** İzin verdiğiniz kategorideki metin **o istemcinin ve onun model sağlayıcısının eline
  geçer**; bunu engelleyemeyiz. İstem enjeksiyonu uyarısı yalnızca tavsiyedir, modeli bağlamaz. Anahtar
  istemcinin ayar dosyasında düz metin durur (aynı kullanıcıyla çalışan başka bir program okuyabilir).
  Kötü niyetli bir istemci, izinli olduğu sürece öneri kuyruğunu yanıltıcı önerilerle doldurabilir; her
  öneri sizin onayınızdan geçer, ama gözden kaçırabilirsiniz.

### 2.3 Kötü niyetli içe aktarma dosyası
Bir dışa aktarma arşivi (zip/tar/json/csv/mbox/pdf/docx/sqlite) bilerek bozulmuş olabilir ya da içine
saldırı metni gömülmüş olabilir.
- **Önlemler (`importers/`):**
  - Arşivler diske açılmaz; üyeler akışla okunur, bu yüzden "zip slip" türü dosya yolu saldırılarına
    açık bir açma adımı yoktur (kodda `extractall`/`extract` kullanılmaz). Kaynak dosyaya yazılmaz.
  - Ayrıştırıcılar bozuk, yarım ve çok büyük girdiler için dayanıklılık testlerinden geçer
    (`importers/tests/test_dayaniklilik.py`); bozuk dosya atlanır/rapor edilir.
  - Belge çıkarımında boyut sınırları vardır (PDF 100 MB/500 sayfa, DOCX 50 MB, düz metin 2 MB, çıkarılan metin
    en çok 100 000 karakter); sembolik bağlantılar izlenmez (klasör taramasında).
  - Kayıt metinleri arayüzde yalnızca `textContent`/metin düğümü olarak eklenir; kayıt içeriği için
    `innerHTML` kullanılmaz (depodaki tek `innerHTML` sabit bir simge çizgisidir). Böylece içe aktarılan
    metinden depolanmış XSS beklenmez.
- **Kalan risk:** PDF/DOCX/XML/görsel kitaplıklarındaki (pypdf, python-docx, lxml, Pillow) açıklar
  burada giderilmez; "sıkıştırma bombası" gibi her kaynak tükenmesi durumu için üst sınır
  **doğrulanmadı**. İçe aktarılan metin, sonradan bir yapay zekâ istemcisine verildiğinde istem
  enjeksiyonu taşıyabilir (2.2). İçe aktarıcılar gerçek veriyle henüz doğrulanmadı.

### 2.4 Kötü niyetli yerel web sayfası: başka site, DNS yeniden bağlama, CSRF
Tarayıcınızda açık başka bir sitenin, `127.0.0.1` üzerindeki Kimlik Merkezi arayüzüne istek atması.
- **Önlemler (`windows/src/kimlikwin/web.py`, test: `windows/tests/test_web.py`):**
  - Sunucu yalnızca `127.0.0.1`'e bağlanır (başka bilgisayarlar erişemez).
  - **Host denetimi:** `Host` başlığı tam olarak `127.0.0.1:<port>` ya da `localhost:<port>` değilse
    GET ve POST isteği 403 alır. Başlık yoksa da reddedilir. Bu, DNS yeniden bağlama saldırısını keser.
  - **CSRF/oturum jetonu:** `/api/*` yalnızca POST kabul eder ve her istekte oturuma özgü rastgele jeton
    (`secrets.token_urlsafe(32)`, sabit zamanlı karşılaştırma) ister. Jeton özel bir istek başlığında
    (`X-Kimlik-Jeton`) gelir; başka bir site bu başlığı CORS ön kontrolü olmadan gönderemez ve sunucu
    CORS'a izin vermez (OPTIONS ve diğer yöntemler 501; `Access-Control-*` başlığı yok), jetonu da okuyamaz.
  - **Origin denetimi:** `Origin` başlığı varsa `http://127.0.0.1:<port>` ya da `http://localhost:<port>`
    olmalıdır; `null` dahil diğerleri 403 alır.
  - Gövde en çok 1 MB; yalnızca bilinen işlemler çağrılabilir (açık izin listesi); statik dosya yolu
    katı bir ad desenine uyar (`..` geçmez).
  - Yanıt başlıkları: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
    `Content-Security-Policy` (`default-src 'self'`, `connect-src 'self'`, `frame-ancestors 'none'`,
    `base-uri 'none'`, `form-action 'none'`, `object-src 'none'`),
    erişim günlüğü tutulmaz.
- **Kalan risk:** CSP `script-src 'unsafe-inline'` içerir (arayüz satır içi betik kullanır); bu, olası
  bir XSS'e karşı CSP'nin sağladığı korumayı zayıflatır (satır içi betiklerin dışarı taşınması
  ayrı bir iştir; şimdilik yalnızca belgelenmiştir). Jeton sayfa HTML'ine gömülüdür; **aynı bilgisayardaki herhangi bir yerel süreç**
  (ve çok kullanıcılı bir Windows'ta başka kullanıcı hesapları) varsayılan sabit porttan sayfayı
  isteyip jetonu alabilir: jeton yerel süreçlere karşı koruma sağlamaz, yalnızca tarayıcıdaki
  başka sitelere karşıdır. "Hassas ayrı onay" arayüzde bir onay adımıdır; arayüz API'sini jetonla
  çağıran biri onay bayrağını kendisi gönderebilir (2.5 ve aşağıdaki bilinen kısıt).

### 2.5 Aynı kullanıcı hesabında çalışan kötü amaçlı yazılım
- **Önlem:** Yok. Aynı kullanıcı olarak çalışan bir program veri dosyalarını, ayar dosyasındaki
  anahtarları ve arayüz jetonunu doğrudan okuyabilir. Bu model bunu korumaya **çalışmaz**.
- **Kalan risk: yüksek**, kapsam dışı (bkz. 4).

### 2.6 Yayın zinciri: sahte ya da değiştirilmiş kurulum paketi
- **Uygulama içi güncelleme (bu özellikle eklendi):** Uygulama GitHub'daki herkese açık yayın listesine bağlanır
  (`windows/.../guncelleme.py`, uygulamanın ağa çıkan TEK yolu; varsayılan açık, Ayarlar'dan kapatılır). Önlemler:
  yalnız https, ana makine beyaz listesi (yönlendirmeler dahil), dosya adı kalıbı ve yalnız bu deponun
  `releases/download/<etiket>/<dosya>` yolu, yalnız uygulamaya ait klasöre yazma, indirme ve kurulum için ayrı
  kullanıcı onayları, kurulumdan hemen önce yeniden doğrulama, kurulum programı yalnız uygulama kapandıktan sonra
  başlar. **Kalan risk:** doğrulama yalnız aynı sürüm sayfasındaki `SHA256SUMS.txt` iledir; GitHub hesabı ya da
  yayın hattı ele geçirilirse saldırgan paketi ve toplamı birlikte değiştirebilir ve kullanıcı onay verirse kurulur
  (imza yok). Sürüm denetimi isteği GitHub'a IP adresinizi gösterir. Bu risk, kullanıcı denetimi kapatarak ve
  güncellemeleri elle doğrulayarak kaçınabileceği bir risktir.
- **Önlemler (elle indirme):** Her yayında `SHA256SUMS.txt` ve SBOM; yayın işi, derlemede hesaplanan özetle yayınlanan dosyayı
  karşılaştırır ve yayından sonra dosyaları yeniden indirip doğrular (CI'da; bu belge yazılırken CI burada
  çalıştırılamadı, bkz. aşağıdaki not).
- **Kalan risk:** Paket **kod imzalı değildir**; toplamlar paketle aynı yerden geldiği için yayın sayfasını
  ele geçiren biri ikisini birlikte değiştirebilir. Bağımlılıkların çoğu sürüm aralığıyla (`>=`) istenir,
  yalnızca `mcp`, `pystray` ve `PyInstaller` sabittir; derlemede hangi sürümlerin kullanıldığı SBOM'da yazılıdır.
  Çözüm planı: [IMZA.md](IMZA.md).

## 3. Özet tablo: mevcut önlemler

| Önlem | Yer |
|---|---|
| Uygulama başına anahtar (yalnız özet saklanır), iptal | `server/.../access.py` |
| Varsayılan kapalı kategori izinleri, bitiş zamanı | `access.py` (`KeyManager.grant`, `Authorizer`) |
| Hassas kategoriler için ayrı onay, toplu açmada hariç | `access.py` |
| Salt okunur veritabanı (`mode=ro`, `query_only`) | `core/.../hub.py` |
| Erişim günlüğü; yazılamazsa veri verilmez | `access.py`, `service.py` |
| Veri etiketleme ve "talimat değildir" uyarısı | `service.py`, `mcp/server.py` |
| Yalnız `127.0.0.1`, Host/Origin denetimi, oturum jetonu, güvenlik başlıkları | `windows/.../web.py` |
| Ağa çıkış yok testleri ve CI izleme; tek istisna olan güncelleme modülü (`guncelleme.py`) ve kilit testleri | [AG-GARANTISI.md](AG-GARANTISI.md) |
| Kayıt içeriğinin günlüğe yazılmaması | `gunluk.py`, `hata_raporu.py` (kullanıcı adı maskelenir) |
| Arşivler diske açılmaz, belge boyut sınırları | `importers/` |

### Bilinen kısıt / v0.2 önerisi: "hassas ayrı onay" yalnızca arayüz bayrağıdır
Hassas kategoriler (`eposta`, `mesaj`, `konum`, `sohbet`) için ikinci onay, yerel API'de istemcinin
gönderdiği bir bayraktır (`hassas_onay`); sunucu bunun gerçekten bir insanın ayrı bir eylemiyle verildiğini
doğrulayamaz. Oturum jetonuna sahip bir yerel süreç bayrağı kendisi gönderebilir. Yapay zekâ istemcileri
(MCP) bu API'ye erişmez, bu yüzden 2.2'deki kendi kendine izin verme senaryosu için bu yalnızca aynı
kullanıcı hesabındaki bir programın sorunudur (2.5, kapsam dışı). **Bu sürümde düzeltilmedi.**
v0.2 önerisi: hassas izin verme işlemini, yalnızca insanın görebileceği bir kanaldan (ör. ayrı bir
sistem iletişim penceresi ya da tek kullanımlık, ekranda gösterilen bir onay kodu) doğrulatmak.

## 4. Kapsam dışı olanlar

- Aynı Windows kullanıcısı ya da yönetici olarak çalışan saldırgan; fiziksel erişim, bellek dökümü,
  keylogger, çekirdek düzeyi kötü amaçlı yazılım.
- Bağladığınız yapay zekâ uygulamasının, model sağlayıcısının ya da Windows'un/tarayıcının kendi
  ağ trafiği ve veri işleme politikası.
- Veri klasörünü bulut eşitleme/yedekleme servisine koymanızın sonuçları.
- Üçüncü taraf bileşenlerdeki açıklar (ilgili projeye bildirin; sürümler SBOM'da).
- Hizmet reddi (bilgisayarınızı yavaşlatan büyük dosya vb.) tek başına güvenlik açığı sayılmaz.
- Aynı Windows hesabında çalışan kötü amaçlı yazılım (anahtar hesaba bağlıdır; yalnız parola katmanı bunu aşar). Kurtarma ve parola yönetimi ayrıntıları ve sınırları: docs/SIFRELEME.md.

## 5. Bu belgenin sınırları

- Kod okunarak ve `web.py` yerel olarak yoklanarak yazıldı (Host/Origin/jeton davranışı gerçek sunucuya
  ham istekler gönderilerek denendi). Windows'ta gerçek tarayıcıyla elle sızma denemesi yapılmadı.
- Bağımsız bir güvenlik denetimi yapılmadı.
- Paket CI'sı (Windows) ve yayın işi bu belgeyi yazan ortamda çalıştırılamadı.
