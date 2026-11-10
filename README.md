# Kimlik Merkezi

Kendi dijital izlerinizi (arama ve izleme geçmişi, sohbetler, müzik, kod, notlar...) **kendi bilgisayarınızda**
tek bir yerde toplayan, aramanıza ve zaman çizelgesinde görmenize izin veren, isterseniz yapay zekâ
uygulamalarına **yalnızca sizin seçtiğiniz kategorilerden ve salt okunur** erişim veren açık kaynaklı bir
Windows uygulaması.

> **Durum: v0.1 ön sürüm.** Henüz gerçek kullanıcı verisiyle doğrulanmamış parçalar var (aşağıda
> "Kısıtlar"). Önemli verilerinizin tek kopyasıyla denemeyin; kaynak dosyalarınıza zaten dokunulmaz,
> ama yine de yedeğiniz olsun.

## Ne yapar

- **İçe aktarır:** Google Takeout (arama, YouTube, Chrome, konum, Gmail MBOX, Gemini), Instagram/Facebook,
  Reddit, Spotify, GitHub hesap verisi, tarayıcı geçmişi dosyaları, ChatGPT ve Claude sohbet dışa aktarmaları,
  elle hazırlanmış sohbet dosyaları, yerel klasör taraması. Kaynak arşivler diske açılmadan akışla okunur.
- **Yerelde saklar:** veriler seçtiğiniz klasörde SQLite dosyasında durur.
- **Arama, zaman çizelgesi, "persona", harita:** yerel web arayüzünde (yalnızca bu bilgisayardan açılır).
- **Yapay zekâ uygulamalarına izinli erişim (MCP):** her uygulama için ayrı anahtar; hangi kategorilerin
  okunabileceğini siz seçersiniz; hassas kategoriler (e-posta, özel mesajlar, konum, yapay zekâ sohbetleri) ayrı onay ister;
  her erişim kaydedilir ve uygulamada görebilirsiniz; erişim salt okunurdur.
- **Persona önerileri:** yapay zekâ istemcisi sizin hakkınızda bir şey öneriyorsa öneri yalnızca bir kuyruğa
  düşer; siz onaylamadan hiçbir şey değişmez.

## Ne OLMADIĞI

- Bir bulut hizmeti, hesap ya da senkronizasyon aracı **değildir**. Sunucumuz yok; telemetri, güncelleme
  yoklaması ve hata raporu gönderimi yok.
- Verinizi **şifrelemez** (bu sürümde). Bilgisayarınıza erişen biri dosyalarınızı okuyabilir. Veri klasörünü
  BitLocker/VeraCrypt gibi şifreli bir birimde tutmanız önerilir. Ayrıntı: [docs/TEHDIT-MODELI.md](docs/TEHDIT-MODELI.md).
- Bir yapay zekâ istemcisine verdiğiniz izin sonrasında o istemcinin veriyle ne yaptığını **denetleyemez**.
  İzin verdiğiniz kategorideki metin, o uygulamanın (ve onun modelinin sağlayıcısının) eline geçer.
- Bir antivirüs, parola yöneticisi ya da yedekleme çözümü değildir.
- Henüz **kod imzalı değildir** (bkz. Kısıtlar).

## Gizlilik ve yerel çalışma sözü

Kimlik Merkezi'nin kendi kodu internete bağlanmaz. Tek ağ kullanımı yalnızca `127.0.0.1` üzerinde dinleyen
yerel web arayüzüdür; MCP sunucusu ağ yerine standart girdi/çıktı kullanır. Bu söz otomatik testlerle, kaynak
denetimiyle ve Windows paket CI'sındaki bağlantı izlemesiyle sınanır; sınırları (neleri garanti ETMEDİĞİMİZ
dahil) açıkça yazılıdır: [docs/AG-GARANTISI.md](docs/AG-GARANTISI.md).
Güvenlik varsayımları ve kalan riskler: [docs/TEHDIT-MODELI.md](docs/TEHDIT-MODELI.md).
Güvenlik açığı bildirimi: [SECURITY.md](SECURITY.md).

## Kurulum (Windows)

**Hazır kurulum paketi** (yönetici izni gerekmez, kullanıcı klasörüne kurulur):

1. GitHub'daki "Releases" bölümünden `KimlikMerkezi-Kurulum-v….exe` ve `SHA256SUMS.txt` dosyalarını indirin.
2. Bütünlüğü doğrulayın (PowerShell). Çıkan değer `SHA256SUMS.txt` içindeki satırla aynı olmalıdır:
   `Get-FileHash .\KimlikMerkezi-Kurulum-v0.1.0.exe -Algorithm SHA256`
3. Çalıştırın. Paket **imzasız** olduğu için Windows SmartScreen "Windows bilgisayarınızı korudu" uyarısı
   gösterebilir; yalnızca özeti doğruladıysanız "Ek bilgi > Yine de çalıştır" deyin.
4. Yayınlarda ayrıca yazılım malzeme listesi (SBOM, CycloneDX JSON) bulunur; hangi bileşenlerin ve
   lisansların pakete girdiğini gösterir.

Kaldırırken kişisel verileriniz varsayılan olarak **silinmez**; silmek isteyip istemediğiniz sorulur.

**Kaynaktan** (Python 3.12 veya üstü):

```
pip install ./core ./server ./importers "./windows[tepsi]"
python -m kimlikwin
```

Yapay zekâ uygulaması bağlama adımları: [docs/BAGLANTI.md](docs/BAGLANTI.md) (hangi istemcilerin
doğrulandığı orada işaretlidir; doğrulanmamış adımlar öyle yazılmıştır).

## Kısıtlar (dürüst durum)

- **v0.1 ön sürüm.** Arayüz ve veri biçimleri değişebilir.
- **İçe aktarıcılar gerçek veriyle doğrulanmadı.** Her biri, resmî/yaygın biçime göre hazırlanmış sahte
  ama gerçeğe yakın dosyalarla test edildi; gerçek dışa aktarmalarla doğrulama beklemede. Hangi kaynağın
  hangi varsayımlarla yazıldığı: [importers/DOGRULAMA-DURUMU.md](importers/DOGRULAMA-DURUMU.md).
  Kendi dışa aktarmanızla `kimlikmerkezi tanila <yol>` çalıştırırsanız içeriksiz bir yapı raporu çıkar;
  uyumsuzluk bildirimi için bunu kullanın (önce okuyup içinde kişisel şey kalmadığından emin olun).
- **Kod imzası yok.** Araştırma ve plan: [docs/IMZA.md](docs/IMZA.md).
- **Şifreleme yok** (bu sürümde), yalnızca Windows, yalnızca Türkçe arayüz. Android uygulaması yok.
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
