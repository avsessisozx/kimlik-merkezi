# Güvenlik politikası

## Güvenlik açığı bildirme

Bir güvenlik açığı bulduğunuzu düşünüyorsanız lütfen **herkese açık bir kayıt (issue) ya da çekme isteği
açmayın**. Bunun yerine GitHub'ın özel bildirim özelliğini kullanın:

1. Bu deponun GitHub sayfasında **Security** (Güvenlik) sekmesine gidin.
2. **Report a vulnerability** (Güvenlik açığı bildir) düğmesine basın ve formu doldurun.

Bildirim yalnızca depo bakımcılarına görünür. (Düğmeyi göremiyorsanız depoda özel bildirim henüz
açılmamış olabilir; bu durumda lütfen ayrıntı yazmadan, yalnızca "özel bildirim yolu açık değil" diyen
bir kayıt açın, size özel bir yol açılacaktır.)

Bildirimde şunlar işimizi çok kolaylaştırır:

- Etkilenen sürüm ve nasıl kurduğunuz (kurulum paketi mi, kaynaktan mı).
- Adım adım yeniden üretme. **Gerçek kişisel veri, anahtar ya da özel sohbet bağlantısı eklemeyin**;
  sahte örnek veri kullanın.
- Etkiyi nasıl değerlendirdiğiniz (hangi veri, kimin, hangi koşulda).

Bu proje gönüllülerce sürdürülür; yanıt süresi için **söz veremeyiz**, ancak her bildirimi okuyup dönüş
yapmaya çalışırız. Düzeltme yayımlanana kadar ayrıntıyı gizli tutmanızı rica ederiz; isterseniz
düzeltme notunda adınızla anılırsınız.

## Desteklenen sürümler

Yalnızca en son yayımlanan sürüm (şu an v0.1 ön sürüm serisi) için düzeltme yapılır.

## Kapsam

Kapsam içinde: Kimlik Merkezi'nin kendi kodu ve kurulum paketi (`core/`, `server/`, `importers/`, `windows/`),
yerel web arayüzü, MCP sunucusu, izin ve anahtar mekanizması, içe aktarıcıların kötü niyetli dosyalarla
davranışı, yayın dosyalarının bütünlüğü.

Kapsam dışı olan ve beklenen durumlar [docs/TEHDIT-MODELI.md](docs/TEHDIT-MODELI.md) içinde yazılıdır
(ör. bilgisayarınıza yönetici ya da aynı kullanıcı olarak erişmiş bir saldırgan; bağladığınız yapay zekâ
uygulamasının kendi davranışı; üçüncü taraf bağımlılıklardaki açıklar, bunları ilgili projeye bildirin).
Kapsam dışı sayılan bir şeyin yine de gerçek bir risk olduğunu düşünüyorsanız bildirin; birlikte değerlendiririz.

## Yayın bütünlüğü

Her yayında kurulum paketinin SHA-256 toplamı (`SHA256SUMS.txt`) ve yazılım malzeme listesi (SBOM,
CycloneDX JSON) bulunur. Paket **henüz kod imzalı değildir** ([docs/IMZA.md](docs/IMZA.md)); bu yüzden
indirdiğiniz dosyanın toplamını `SHA256SUMS.txt` ile karşılaştırmanız önemlidir. `SHA256SUMS.txt`
paketle aynı yerden geldiği için, indirme sayfasının kendisi ele geçirilmişse tek başına kanıt değildir;
bu sınır imzalama yapılana kadar sürer.
