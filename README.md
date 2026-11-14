# Kimlik Merkezi

Kendi dijital izlerinizi (arama ve izleme geçmişi, sohbetler, müzik, kod, notlar...) **kendi bilgisayarınızda**
tek bir yerde toplayan, aramanıza ve zaman çizelgesinde görmenize izin veren, isterseniz yapay zekâ
uygulamalarına **yalnızca sizin seçtiğiniz kategorilerden ve salt okunur** erişim veren açık kaynaklı bir
Windows uygulaması.

> **Durum: v0.1.1 ön sürüm.** Henüz gerçek kullanıcı verisiyle doğrulanmamış parçalar var (aşağıda
> "Kısıtlar"). Önemli verilerinizin tek kopyasıyla denemeyin; kaynak dosyalarınıza zaten dokunulmaz,
> ama yine de yedeğiniz olsun.

## Ne yapar

- **İçe aktarır:** Google Takeout (arama, YouTube, Chrome, konum, Gmail MBOX, Gemini), Instagram/Facebook,
  Reddit, Spotify, GitHub hesap verisi, tarayıcı geçmişi dosyaları, ChatGPT ve Claude sohbet dışa aktarmaları,
  elle hazırlanmış sohbet dosyaları, yerel klasör taraması. Kaynak arşivler diske açılmadan akışla okunur.
- **Yerelde saklar:** veriler seçtiğiniz klasörde durur; Windows'ta yeni klasör varsayılan olarak **şifrelenir** (aşağıda "Şifreleme").
- **Arama, zaman çizelgesi, "persona", harita:** yerel web arayüzünde (yalnızca bu bilgisayardan açılır).
- **Yapay zekâ uygulamalarına izinli erişim (MCP):** her uygulama için ayrı anahtar; hangi kategorilerin
  okunabileceğini siz seçersiniz; hassas kategoriler (e-posta, özel mesajlar, konum, yapay zekâ sohbetleri) ayrı onay ister;
  her erişim kaydedilir ve uygulamada görebilirsiniz; erişim salt okunurdur.
- **Persona önerileri:** yapay zekâ istemcisi sizin hakkınızda bir şey öneriyorsa öneri yalnızca bir kuyruğa
  düşer; siz onaylamadan hiçbir şey değişmez.

## Ne OLMADIĞI

- Bir bulut hizmeti, hesap ya da senkronizasyon aracı **değildir**. Sunucumuz yok; telemetri ve hata raporu
  gönderimi yok. Tek istisna, GitHub'daki herkese açık yayın listesine bakan **güncelleme denetimidir** (aşağıda
  "Gizlilik ve yerel çalışma sözü"); kapatabilirsiniz, indirme/kurulum yalnız onayınızla yapılır.
- Her şeyi şifrelemez ve kötü amaçlı yazılıma karşı koruma değildir: aşağıdaki "Şifreleme" bölümü neyin
  şifrelendiğini ve neyin ŞİFRELENMEDİĞİNİ açıkça yazar. Ek önlem olarak veri klasörünü BitLocker/VeraCrypt gibi
  şifreli bir birimde tutmanız önerilir. Ayrıntı: [docs/TEHDIT-MODELI.md](docs/TEHDIT-MODELI.md).
- Bir yapay zekâ istemcisine verdiğiniz izin sonrasında o istemcinin veriyle ne yaptığını **denetleyemez**.
  İzin verdiğiniz kategorideki metin, o uygulamanın (ve onun modelinin sağlayıcısının) eline geçer.
- Bir antivirüs, parola yöneticisi ya da yedekleme çözümü değildir.
- Henüz **kod imzalı değildir** (bkz. Kısıtlar).

## Şifreleme

Teknik ayrıntı ve sınırlar: [docs/SIFRELEME.md](docs/SIFRELEME.md).

- **Varsayılan açık (yeni klasörlerde).** Windows uygulamasıyla oluşturulan yeni veri klasörü AES-256-GCM ile
  şifrelenir; anahtar Windows hesabınıza bağlıdır (DPAPI), ayrı parola sormaz.
- **Şifrelenenler:** veritabanının tamamı (olaylar, arama dizini, persona, **persona öneri kuyruğu**, anahtar
  özetleri, izinler, **erişim günlüğü**) ve `arsiv/` altındaki ham içe aktarma dosyaları.
- **ŞİFRELENMEYENLER:** `cikti/` klasörü ve dışa aktardığınız her dosya (JSONL, kimlik kartı, vb.); Linux'ta ya da
  anahtar sağlayıcısı olmayan ortamlarda oluşturulan klasörler (varsayılan şifresiz, uyarı verilir); şifreleme
  gelmeden önce oluşturduğunuz klasörler (otomatik dönüştürülmez, `kimlikmerkezi sifrele` gerekir); dosya adları,
  boyutları ve zamanları gibi dosya sistemi üst verisi. Aynı Windows hesabında çalışan bir program anahtarı
  açtırabilir: yalnız isteğe bağlı parola katmanı buna karşı korur.
- **Parola ve kurtarma ifadesi:** isteğe bağlı parola eklenebilir, ama önce bir **kurtarma ifadesi** kurmak ZORUNLUDUR
  (en az 4 kelime ya da 20 karakter; kısa, "gizli soru" tarzı, tekrar eden ya da bilinen zayıf ifadeler reddedilir; iki
  kez yazarak doğrulanır). **Parolayı ve kurtarma ifadesini ikisini birden unutursanız verinizi KİMSE kurtaramaz**
  (biz de, kimse de). Kurtarma ifadesi gücü sezgiseldir, gerçek bir entropi ölçümü değildir.
- **Uygulamadaki "Güvenlik" sayfası.** Şifreleme durumu (açık/kapalı, parola var mı, kurtarma ifadesi kuruldu mu),
  kurtarma ifadesi kurma, parola ekleme/kaldırma, parolayı kurtarma ifadesiyle sıfırlama ve şifrelemeyi açıp kapatma
  uygulamanın içinden yapılır; komut satırı gerekmez (komutlar `kimlikmerkezi ...` hâlâ vardır). Parola eklerken sıra
  zorunludur: önce kurtarma ifadesi (kural göstergesi, güç göstergesi, iki kez yazma), sonra "kurtarılamaz" uyarısı ve
  onay kutusu, sonra parola. Şifrelemeyi kapatmak için `KALDIR` yazılır; işlem veriyi yeniden yazar ve uzun sürebilir.
  İlk açılış sihirbazı şifrelemenin varsayılan açık olduğunu söyler.
- **Parolalı klasör açılışta parola sorar.** Parola yalnız bellekte tutulur, diske yazılmaz. Yanlış denemeler
  yavaşlatılır (2 hata bedava, sonra 5, 10, 20... sn, en çok 5 dk; sayaç uygulama yeniden başlayınca sıfırlanır:
  kaba kuvveti durdurmaz, yalnız yavaşlatır). Parolayı unuttuysanız kilit ekranından kurtarma ifadesiyle açabilirsiniz.
- **Parola ve Claude (MCP) birlikte çalışmaz, bu bilinçli bir karardır.** Claude'un MCP süreci parola giremez;
  parolayı Claude'un ayar dosyasına (`KIMLIK_PAROLA`) yazmak, aynı Windows hesabındaki her programa parolayı vermek
  demektir ve parolanın tüm amacını boşa çıkarır. Bu yüzden parolalı klasörde "Claude Desktop'a ekle" kapalıdır ve
  parola eklemeden önce bu açıkça gösterilir. Claude erişimi istiyorsanız parolasız (Windows hesabına bağlı şifreli)
  kalın. Gerekçe: [docs/SIFRELEME.md §6](docs/SIFRELEME.md).
- **Hazır kurulum paketindeki `kimlikmerkezi` komut satırı aracı** (sifrele, parola-ekle...) pakette olmayabilir;
  artık gerekmez, çünkü hepsi Güvenlik sayfasında. Ancak Güvenlik sayfası gerçek Windows'ta (DPAPI, Inno Setup
  kurulumu) **denenmedi**; Linux'ta sahte anahtar sağlayıcısıyla sınandı.
- **Doğrulanmadı:** gerçek Windows DPAPI bu geliştirme ortamında (Linux) denenmedi; Windows'ta paketlenmiş uygulamayla
  şifreleme elle sınanmadı. Güvenli silme (eski düz dosyaları sıfırlayıp silme) SSD ve yedekler yüzünden fiziksel
  silmeyi garanti etmez.

## Gizlilik ve yerel çalışma sözü

Kimlik Merkezi'nin kendi kodu, **tek bir istisna dışında**, internete bağlanmaz: Windows uygulaması
**güncelleme denetimi** için GitHub'a (`api.github.com`; indirme olursa `github.com` ve GitHub'ın dosya depolama
adresleri) bağlanabilir. Bu denetim **varsayılan olarak AÇIKTIR** (uygulama açılırken "yeni sürüm var mı?" diye
sorar; ilk açılış sihirbazında ve Ayarlar'da açıkça yazılıdır) ve Ayarlar'dan **kapatılabilir**; kapalıyken ve
"Güncellemeleri denetle" düğmesine basmadıkça uygulama internete hiç bağlanmaz. Gönderilen tek şey sürüm listesi
isteğidir: genel bir kullanıcı ajanı (`KimlikMerkezi-guncelleme`), sürümünüz, adınız ya da verileriniz yok (IP
adresiniz GitHub tarafından görülür). Yeni sürüm bulunursa **önce sorulur**; indirme yalnız onaylarsanız
başlar (ilerleme çubuğu, duraklat/devam, iptal; SHA-256 ile doğrulanır) ve kurulum için **ikinci bir onay**
istenir. Paket imzasız olduğundan doğrulama yalnız aynı sürüm sayfasındaki `SHA256SUMS.txt` ile yapılır
(ayrıntı ve sınırı: [SECURITY.md](SECURITY.md)). Bunun dışında tek ağ kullanımı `127.0.0.1` üzerinde dinleyen
yerel web arayüzüdür; MCP sunucusu ağ yerine standart girdi/çıktı kullanır. Bu söz otomatik testlerle, kaynak
denetimiyle (istisna tek dosyaya ve sabit ana makine listesine kilitlidir) ve Windows paket CI'sındaki
bağlantı izlemesiyle sınanır; sınırları (neleri garanti ETMEDİĞİMİZ dahil) açıkça yazılıdır:
[docs/AG-GARANTISI.md](docs/AG-GARANTISI.md).
Güvenlik varsayımları ve kalan riskler: [docs/TEHDIT-MODELI.md](docs/TEHDIT-MODELI.md).
Güvenlik açığı bildirimi: [SECURITY.md](SECURITY.md).

## Kurulum (Windows)

**Hazır kurulum paketi** (yönetici izni gerekmez, kullanıcı klasörüne kurulur):

1. GitHub'daki "Releases" bölümünden `KimlikMerkezi-Kurulum-v….exe` ve `SHA256SUMS.txt` dosyalarını indirin.
2. Bütünlüğü doğrulayın (PowerShell). Çıkan değer `SHA256SUMS.txt` içindeki satırla aynı olmalıdır:
   `Get-FileHash .\KimlikMerkezi-Kurulum-v0.1.1.exe -Algorithm SHA256`
3. Çalıştırın. (Uygulama içinden güncelliyorsanız bu adımlar kendiliğinden yapılır: aşağıdaki "Uygulama içi güncelleme".) Paket **imzasız** olduğu için Windows SmartScreen "Windows bilgisayarınızı korudu" uyarısı
   gösterebilir; yalnızca özeti doğruladıysanız "Ek bilgi > Yine de çalıştır" deyin.
4. Yayınlarda ayrıca yazılım malzeme listesi (SBOM, CycloneDX JSON) bulunur; hangi bileşenlerin ve
   lisansların pakete girdiğini gösterir.

Kaldırırken kişisel verileriniz varsayılan olarak **silinmez**; silmek isteyip istemediğiniz sorulur.

**Uygulama içi güncelleme** (Windows): yeni sürüm bulunursa "Yeni sürüm X var, indirmek ister misin?" diye sorulur.
Onaylarsanız kurulum dosyası indirilir (ilerleme, kalan süre, duraklat/devam, iptal), `SHA256SUMS.txt` ile
doğrulanır (uyuşmazsa dosya silinir ve hata gösterilir) ve **"Şimdi kurmak ister misin?"** diye ikinci kez sorulur.
Onaylarsanız uygulama kapanır, kurulum sessizce yapılır ve Kimlik Merkezi yeniden açılır; veri klasörünüze ve
ayarlarınıza dokunulmaz. Denetimi Ayarlar > Güncellemeler bölümünden kapatabilir ya da elle başlatabilirsiniz.
Gerçek Windows üzerinde uçtan uca denenmedi; neyin doğrulandığı için bkz. `windows/paket/surum-notu.md`.

**Kaynaktan** (Python 3.12 veya üstü):

```
pip install ./core ./server ./importers "./windows[tepsi]"
python -m kimlikwin
```

Yapay zekâ uygulaması bağlama adımları: [docs/BAGLANTI.md](docs/BAGLANTI.md) (hangi istemcilerin
doğrulandığı orada işaretlidir; doğrulanmamış adımlar öyle yazılmıştır).

## Kısıtlar (dürüst durum)

- **v0.1.1 ön sürüm.** Arayüz ve veri biçimleri değişebilir.
- **İçe aktarıcılar gerçek veriyle doğrulanmadı.** Her biri, resmî/yaygın biçime göre hazırlanmış sahte
  ama gerçeğe yakın dosyalarla test edildi; gerçek dışa aktarmalarla doğrulama beklemede. Hangi kaynağın
  hangi varsayımlarla yazıldığı: [importers/DOGRULAMA-DURUMU.md](importers/DOGRULAMA-DURUMU.md).
  Dosyanız tanınmazsa kendi dışa aktarmanızın içeriksiz bir yapı raporunu çıkarabilirsiniz: kurulu uygulamada
  **İçe aktar > "Dosyayı denetle (içerik göstermez)"** (rapor ekranda, "Kopyala" düğmesiyle), konsolda
  `kimlikmerkezi-mcp.exe tanila <yol>` (kaynak kodda `kimlikmerkezi tanila <yol>`). Rapor yalnız alan adları, türler
  ve sayılar içerir; hiçbir şey kaydedilmez. Uyumsuzluk bildirimi için bunu kullanın (önce okuyup içinde kişisel
  şey kalmadığından emin olun).
- **Kod imzası yok.** Araştırma ve plan: [docs/IMZA.md](docs/IMZA.md).
- **Şifreleme kısmi ve Windows'ta gerçek DPAPI ile denenmedi** (yukarıdaki "Şifreleme" bölümü), yalnızca Windows, yalnızca Türkçe arayüz. Android uygulaması yok.
- **Test kapsamı:** otomatik testler Linux'ta ve Windows paket CI'sında çalışır; gerçek bir Windows
  masaüstünde elle uçtan uca deneme yapılan bir "doğrulandı" kaydı henüz yoktur.

## Klasörler

`core/` çekirdek (SQLite, ham arşiv, Türkçe arama) · `server/` persona, izinler ve MCP adaptörü ·
`importers/` içe aktarıcılar · `windows/` kabuk, web arayüzü ve kurulum paketi · `entegrasyon/` uçtan uca
ve ağ garantisi testleri · `docs/` belgeler.

Testler: `PYTHONPATH=core/src:server/src:importers/src:windows/src` ayarlayıp `core`, `importers`, `server`,
`windows`, `entegrasyon` klasörlerinde ayrı ayrı `python -m pytest` çalıştırın.

## Lisans

[MIT](LICENSE). Üçüncü taraf bileşenler kendi lisanslarıyla gelir: [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## Katkı

Hata bildirimleri ve çekme istekleri (pull request) memnuniyetle karşılanır; Türkçe ya da İngilizce yazabilirsiniz.
Lütfen **gerçek kişisel veri, anahtar ya da özel sohbet bağlantısı** içeren dosya, günlük, ekran görüntüsü veya
test verisi paylaşmayın; test verileri sahte olmalıdır. Güvenlik açıklarını herkese açık kayıt (issue) olarak
değil, [SECURITY.md](SECURITY.md) içindeki yolla bildirin. Kod değişikliklerinde testlerin geçmesini
bekliyoruz; ağ garantisi testleri bilinçli olarak sıkıdır.
