# Kod imzası araştırması (öneri belgesi, uygulama kurulmadı)

Tarih: 2026-11-10. Amaç: Windows kurulum paketinin (`KimlikMerkezi-Kurulum-v….exe`, içinde iki exe) açık kaynak
bir proje için ücretsiz ya da ucuz yoldan imzalanması. Şu an paket **imzasızdır**; bütünlük için yalnızca
`SHA256SUMS.txt` ve SBOM vardır.

## Kaynak durumu (dürüstlük notu)

Bu araştırma bir bulut oturumunda yapıldı. `signpath.org` ve `learn.microsoft.com` adresleri bu oturumun ağ
kısıtı nedeniyle **doğrudan açılamadı** ("doğrulanamadı"). Aşağıdaki bilgiler web arama özetlerine ve
üçüncü taraf sayfalara dayanır; her satırın yanında kaynağı ve durumu yazılıdır. **Başvurmadan önce birincil
sayfaları kendiniz okuyun.** Fiyatlar bu oturumda bulunamadı; hiçbiri uydurulmadı.

## Seçenekler

### 1. SignPath Foundation (açık kaynak için ücretsiz imzalama)
- **Koşullar** (arama özetinden; birincil sayfa `https://signpath.org/terms` **doğrulanamadı**):
  OSI onaylı açık kaynak lisansı (MIT uygundur) ve herkese açık depo; projede tescilli/kapalı bileşen olmaması;
  bir önceki yayının bulunması (bir rehber bunu ön koşul olarak sayıyor); ekip üyelerinde hem SignPath'te hem
  depoda çok faktörlü kimlik doğrulama; imzanın depo, dal, işlem (commit) ve CI derleme işine bağlanması
  ("origin verification": derleme betikleri de gözden geçirilmiş kaynakta olmalı); proje sayfasında bir
  "kod imzalama politikası" yayımlanması.
- **Sertifika sahibi:** sertifika SignPath Foundation adına verilir; yayıncı olarak o görünür, sizin adınız
  değil. Foundation sertifikadan doğan zararlar için sorumluluk kabul etmez.
- **Maliyet:** nitelikli projeler için ücretsiz (kaynak: üçüncü taraf rehberler; birincil sayfa doğrulanamadı).
- **Bizim için uygunluk:** MIT, GitHub Actions'ta derleme, PyInstaller + Inno Setup çıktısı. Depo herkese
  açık yapıldıktan ve en az bir sürüm yayımlandıktan sonra başvurulabilir görünüyor. Tüm bağımlılıkların
  açık kaynak olması gerekliliği ile ilgili not: `pystray` LGPL, `PyInstaller` GPL+istisna; ikisi de açık kaynak,
  sorun beklenmiyor ama "tescilli bileşen yok" koşulu birincil sayfadan teyit edilmeli.
- **Ne zamana yetişir:** başvuru onay süresi **doğrulanamadı** (bulunamadı). Kendi tarafımızda gereken: depo
  public, ilk yayın, MFA, imzalama politikası metni, derleme işinin SignPath'e bağlanması (bir iki gün iş).
- **SmartScreen etkisi:** imza tek başına uyarıyı hemen kaldırmaz (aşağıya bakın). Foundation sertifikasının
  birçok projede ortak kullanılmasının itibarı hızlandırıp hızlandırmadığı **doğrulanamadı**.
- Kaynaklar: arama sonuçları [SignPath Foundation şartları](https://signpath.org/terms) ve
  [origin verification belgesi](https://docs.signpath.io/origin-verification) (ikisi de bu oturumda doğrudan açılamadı),
  [SignPath açık kaynak ürün sayfası](https://about.signpath.io/product/open-source),
  örnek projelerin imza politikaları: [Ink/Stitch](https://inkstitch.org/code-signing-policy),
  [Super Productivity](https://super-productivity.com/code-signing/).

### 2. Microsoft'un bulut imzalama hizmeti (Trusted Signing; sonradan "Artifact Signing" olarak anılıyor)
- **Uygunluk** (arama özetleri, Microsoft Learn yanıtlarına dayanıyor; birincil sayfalar **doğrulanamadı**):
  bireysel geliştiriciler için yalnızca ABD ve Kanada; kuruluşlar için ABD, Kanada, Avrupa Birliği ve Birleşik
  Krallık. Önizleme sürecinde bireysel kayıtların daha da kısıtlandığına dair soru-cevap kayıtları var.
- **Sonuç:** proje sahibinin bulunduğu ülke bu listede değilse (ör. Türkiye) ve tüzel kişi yoksa bu yol
  **uygun görünmüyor**; sahibin ülkesini ve durumunu siz teyit edin.
- Maliyet: **doğrulanamadı**. Zaman: uygunsa kimlik doğrulaması gerekir, süresi **doğrulanamadı**.
- Kaynaklar: [Microsoft Learn: kod imzalama seçenekleri](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options),
  [Soru-cevap: farklı ülkeler](https://learn.microsoft.com/en-us/answers/questions/2243504/trusted-signing-for-other-countries),
  [Soru-cevap: bireysel kimlik doğrulama](https://learn.microsoft.com/en-us/answers/questions/5810735/cant-create-a-new-trusted-signing-individual-ident),
  [DevClass haberi, 2026-01-14](https://www.devclass.com/security/2026/01/14/code-signing-windows-apps-may-be-easier-and-more-secure-with-new-azure-artifact-service/4079554).
  (Bu kaynakların hiçbiri bu oturumda doğrudan açılıp okunmadı; arama özetidir.)

### 3. Kendi OV (kuruluş doğrulamalı) kod imzalama sertifikası, ticari bir sertifika yetkilisinden
- **Koşullar:** kimlik/kuruluş doğrulaması (bireyler için kabul edilip edilmediği satıcıya göre değişir,
  **doğrulanamadı**). Genel bilgi (bu oturumda doğrulanmadı): özel anahtarın donanım belirtecinde ya da
  bulut HSM'de tutulması zorunlu, bu yüzden CI'dan imzalamak için satıcının bulut imzalama hizmeti gerekebilir.
- **Geçerlilik:** 1 Mart 2026'dan sonra verilen genel güvenilir kod imzalama sertifikaları en çok 460 gün
  geçerli (CA/B Forum CSC-31); yani yılda en az bir yenileme.
  Kaynaklar: [GlobalSign](https://www.globalsign.com/en/blog/code-signing-validity-changes),
  [DigiCert](https://knowledge.digicert.com/alerts/code-signing-certificates-459-day-validity) (arama özetleri).
- **Maliyet:** bu oturumda **bulunamadı/doğrulanamadı**; satıcı fiyat sayfalarından bakılmalı.
- **Ne zamana yetişir:** doğrulama süresi satıcıya bağlı, **doğrulanamadı**.
- **EV sertifika:** önerilmez (aşağıda).

### 4. Kendi kendine imzalı sertifika
- Ücretsiz ve anında, ama Windows ve kullanıcılar bu sertifikaya güvenmez; SmartScreen uyarısını
  **kaldırmaz**. Yalnızca kendi test makinelerinizde, sertifikayı elle güvenilir kök yaparak işe yarar.
  Herkese dağıtılan pakette anlamsızdır.

### 5. Şimdilik imzasız yayın + güçlü bütünlük kanıtı
- Yapılıyor: `SHA256SUMS.txt`, SBOM, açık kaynak derleme betikleri, sürüm notunda SmartScreen uyarısı.
- Eksik kalan: toplamlar ve paket aynı yerden geldiği için yayın sayfası ele geçirilirse güvence vermez.
  Ek olarak sürüm etiketlerini imzalamak (git etiket imzası) ve GitHub'ın yapıt doğrulama (attestation)
  özelliği değerlendirilebilir; ikisi de bu oturumda **araştırılmadı**.

## SmartScreen gerçeği
- Kod imzası yalnızca yayıncıyı doğrulanabilir kılar; SmartScreen uyarısının kalkması için ayrıca itibar
  birikmesi gerekir. Arama sonuçlarına göre EV sertifikanın eskiden verdiği "anında itibar" artık geçerli
  değil, EV ve OV yeni dosyalar için benzer davranıyor ([Microsoft Learn mirror: smartscreen-reputation](https://star-hk2.eastasia.cloudapp.azure.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation) ve
  [Microsoft Q&A, EV/OV tartışması](https://learn.microsoft.com/en-us/answers/questions/417016/reputation-with-ov-certificates-and-are-ev-certifi);
  ikincil kaynak: [ngrok blog, 2026-02-24](https://ngrok.com/blog/windows-ev-certificate)). Resmî
  `learn.microsoft.com` sayfası doğrudan okunamadı; **doğrulanamadı**.
- Beklenti: imzalı olsak bile ilk indirmelerde uyarı görülebilir; itibar indirme sayısıyla zamanla oluşur
  (süre için güvenilir bir rakam bulunamadı).
- Yanlış alarm veren antivirüsler için satıcıların "yanlış pozitif bildirimi" kanalları vardır
  (genel bilgi, bu oturumda araştırılmadı).

## Öneri
1. **Önce SignPath Foundation'a başvurun.** Ücretsiz, MIT'e uygun, CI'da çalışır. Ön koşul: depo public,
   en az bir yayın, MFA, `docs` içinde kısa bir "kod imzalama politikası", derleme betiklerinin depoda olması.
   Başvuru ve onay süresi bilinmiyor; v0.1.x yayınları imzasız çıkmaya devam eder.
2. Azure/Artifact Signing yalnızca sahibin ülkesi/kuruluşu uygunsa; birincil Microsoft sayfasından teyit edin.
3. Ücretli OV sertifikasını yalnızca SignPath reddederse ya da çok gecikirse düşünün; EV'ye para vermeyin
   (SmartScreen'de tek başına avantaj sağlamıyor görünüyor).
4. İmzalama gelene kadar: README ve sürüm notundaki SHA-256 doğrulama yönergeleri kalsın; SBOM ve toplamlar
   her yayında üretilsin (paket işi bunu yapıyor).
5. İmza eklendiğinde `paket.yml` ve Inno Setup (`SignTool`) adımları ayrı bir değişiklik olarak yapılmalı;
   hem iç exe'ler hem kurulum paketi imzalanmalı.
