# Karar A masa başı notları (kod yok)

Etiketler: **BİLİNEN** = genel yazılım bilgisi, kararı bunun üstüne kurmak için ayrıca doğrulanmalı olsa da
mimari olarak kesin; **ÖLÇÜLDÜ** = bu dalın CI testiyle ölçüldü (sayılar CI günlüğünde / şefin raporunda);
**DOĞRULANAMADI** = bu ortamda (bulut konteyneri, github.com ve api.github.com erişimi 403) bakılamadı ya da
gerçek cihaz gerektiriyor. Tahmin yazılmadı.

## 1. Şifreli giden kutusuyla uyum
| Aday | BİLİNEN | DOĞRULANAMADI |
|---|---|---|
| Doğrudan HTTPS | Uygulama kendi özel alanında şifreli paketi kendisi okur, gövde olarak gönderir; ayrıca ayrı bir paylaşılan klasöre çıkması gerekmez. Aktarım TLS + parmak izi sabitleme; paket zaten şifreli olduğundan çift katman. Anahtarın PC'ye geçişi eşleştirmede olur (ortak gizli anahtar + parmak izi QR/kodla bir kez). | Anahtarın PC'ye ilk geçişinin kullanıcı deneyimi (QR okutma, kod yazma); Android'de kendinden imzalı sertifika + parmak izi sabitlemenin uygulama tarafı kodu (bu spike yalnız PC/Python tarafını taklit etti). |
| Syncthing | Ayrı bir uygulamadır: başka uygulamanın özel alanını (Android uygulama sandbox'ı) OKUYAMAZ. Dosyaların paylaşılan bir klasöre (harici depolama / SAF) çıkarılması şarttır; şifreli paket orada durur, şifre çözme anahtarı ayrı yoldan (örn. eşleştirme sırasında) PC'ye iletilmelidir. Syncthing kendi aktarımını TLS ile şifreler ama klasördeki dosyalar telefonda diske düz haliyle (şifreli paket olarak) yazılır; "güvenilmeyen cihaz şifreli klasör" özelliği 3. cihaz içindir, bu senaryoya uymaz. | Android sürümlerinde (11+) paylaşılan klasörün Syncthing uygulamasınca okunması için gereken izin türü (tüm dosyalar erişimi vs. SAF) ve Play Store politikası etkisi; hangi Android istemcisinin kullanılacağı (bkz. bakım). |
| Elle | Paket zaten şifreli dosya; USB/paylaşımla gider. Anahtar ayrı (PC'de uygulama kurulumunda/ilk eşleşmede) olmalı. | Kullanıcının telefondan dosya yöneticisiyle uygulamanın özel alanına erişemeyeceği (Android 11+ kısıtı) için uygulamanın "dışa aktar" (SAF/paylaş) adımını sunması gerekir; bu adımın kullanılabilirliği gerçek cihazda sınanmadı. |

## 2. Realme UI / MIUI arka plan kısıtlamasına dayanıklılık
Yalnız gerçek cihazda ölçülür; bu spike'ta ölçülmedi. **DOĞRULANAMADI** (hepsi için).
- BİLİNEN: Android'de arka plan işi iki yoldan çalışır: WorkManager (sistem zamanlar, gecikebilir, üreticinin pil
  yönetimi tarafından ertelenebilir) ve ön plan hizmeti (kalıcı bildirim; daha güvenilir ama pil/izin maliyeti).
  Doğrudan HTTPS: uygulamanın kendi kodu olduğundan, PC'nin açık olduğu anı yakalamak için periyodik WorkManager
  işi ya da uygulama açılışında deneme gerekir; PC kapalıyken denemek pil harcar (üstel geri çekilme gerekir).
  Syncthing: ayrı uygulama olduğundan üretici kısıtlamasına kendi başına tabidir; kullanıcı onu "pil optimizasyonundan
  muaf tut / otomatik başlat" ayarına elle almalıdır; çoğu istemci ön plan hizmeti kullanır.
  Elle: arka plan gerekmez.
- DOĞRULANAMADI: Realme UI/MIUI'nin belirli sürümlerinde bu ayarların varsayılanı ve öldürme davranışı; hangisinin
  WorkManager'ı gerçekten geciktirdiği.

## 3. Pil
Gerçek cihaz ölçümü gerektirir. **DOĞRULANAMADI** (üç aday için de yüzde/saat verisi yok). BİLİNEN yalnız yapısal fark:
Syncthing sürekli açık bir süreç (bağlantı, yerel keşif, tarama) tutar; doğrudan HTTPS yalnız denemede ağ kullanır;
elle aktarım hiç kullanmaz. Bu ölçüm spike'ta yok.

## 4. Bakım riski (Syncthing çekirdeği ve Android istemcileri)
- Syncthing çekirdeği: Go, MPL-2.0 (BİLİNEN, hatırlanan). Dalın CI'si SYNCTHING_SURUM sürümünü indirir (bkz. iş akışı);
  son sürüm tarihi **DOĞRULANAMADI** (api.github.com bu ortamdan 403).
- Syncthing-Fork (Catfriend1) ve BasicSync depolarının lisansı ve son sürüm tarihi: **DOĞRULANAMADI** (GitHub API'si
  bu ortamdan 403 verdi). Hatırlanan (doğrulanmadı): resmî Syncthing-Android uygulaması 2024 sonunda emekli edildi,
  Fork onun devamı olarak anılıyor; BasicSync daha küçük, tek geliştiricili bir istemci. Şef bu iki satırı GitHub'da
  elle kontrol etmeli (lisans, son commit/sürüm tarihi, açık sorun sayısı).
- Doğrudan HTTPS: bakım yükü kendi kodumuzda (Android istemci + PC alıcı); üçüncü taraf bağımlılık riski yok ama
  sertifika üretimi için PC tarafında stdlib yetmez (bkz. ölçüm bulgusu).
- Elle: bakım riski yok.

## 5. Windows Güvenlik Duvarı izin penceresi ve "Ortak" ağ profili
Bu spike CI runner'ında (loopback) koştu; gerçek Windows 10/11 kullanıcı makinesinde **DOĞRULANAMADI**.
- BİLİNEN: Bir uygulama ilk kez gelen bağlantı için dinlemeye başlayınca (loopback dışı arayüz) Windows Defender
  Güvenlik Duvarı "izin ver" penceresi çıkarır; "Özel" ağ kutusu varsayılan işaretli, "Ortak" kutusu işaretsiz. Ağ profili
  "Ortak" ise gelen bağlantı varsayılan olarak engellenir; telefonun PC'ye ulaşması için kullanıcı ağı "Özel"e almalı ya da
  Ortak kutusunu işaretlemelidir. Bu hem doğrudan HTTPS alıcıyı (Python süreci dinler) hem Syncthing'i (22000/tcp dinler)
  etkiler. Yönetici izni gerektirebilecek kural eklemenin (netsh) Python uygulamasından otomatikleştirilmesi
  **DOĞRULANAMADI**.
- Elle aktarım: dinleme yok, güvenlik duvarı yok.
- Not: ölçüm alıcısı 127.0.0.1'e bağlandı; gerçek kullanımda 0.0.0.0/yerel arayüze bağlanıp RFC1918 süzgecinden
  geçirmek gerekir (süzgeç birim testiyle ölçüldü, gerçek ağda değil). Telefonun PC adresini nasıl bulacağı (DHCP değişimi,
  mDNS, sabit IP) bu spike'ta ele alınmadı: **DOĞRULANAMADI/ölçülmedi**.

## 6. Kullanıcının atacağı adım sayısı
Sayım ayrıntısı şefin raporunda (CI test_e çıktısı + aşağıdaki liste). Bu satırlar tasarım sayımıdır, kullanıcı testi değildir.
- Doğrudan HTTPS (eşleştirme tek seferlik): (1) PC'de uygulamada "telefon eşleştir" -> kod/QR üret, (2) telefonda
  uygulamada kodu okut/gir, (3) PC güvenlik duvarı izni (ilk dinlemede 1 pencere; profil Ortak ise +ağı Özel yap),
  sonra otomatik. Telefon IP'sini kullanıcı yazmıyorsa adres bulma mekanizması gerekir (kapsam dışı).
- Syncthing (iki ayrı uygulama): (1) iki cihaza Syncthing kur, (2) PC kimliğini telefona ekle, (3) telefon kimliğini
  PC'de onayla, (4) giden kutusu klasörünü paylaş, (5) PC'de klasör yolu + türü receiveonly ayarla (otomatik kabulde tür
  varsayılan sendreceive gelir: CI test_e ölçer), (6) telefonda pil muafiyeti/otomatik başlat, (7) güvenlik duvarı izni.
- Elle: her aktarımda kullanıcı (1) uygulamada "dışa aktar", (2) PC'ye kopyala (USB/paylaş), (3) PC'de "klasörü tara ve al".
  Kurulum yok; her seferinde 3 adım.

## 7. CI'de ölçülen ek bulgular (karar-a-olcum, koşu 43801008257: ubuntu ve windows 41/41 geçti)
- Syncthing v1.30.0, SHA256 yayımlanan `sha256sum.txt.asc` ile eşleşti (linux a2edc833..., windows c8e2713d...). İmza (GPG) doğrulanmadı.
- Syncthing'i öldürme: `serve` varsayılan olarak izleyici + çocuk süreç başlatır; yalnız üst süreci öldürmek çocuğu hayatta bırakır
  (ilk iki CI turunda "kill" bu yüzden etkisizdi). Ölçüm `STMONITORED=1` ile tek süreç çalıştırdı. Gerçek uygulama kullanımında
  PC kapanması = tüm süreç ağacı gider; bu yalnız test düzeneğiyle ilgili.
- Doğrudan HTTPS'te istemci bağlantı kopmasını tek çağrı içinde şeffaf yeniden bağlanmayla atlatabildi (windows b senaryosu); bu iki biçimde de sınandı.
- Sertifika üretimi stdlib ile yapılamadı; testler openssl komut satırını kullandı (Windows runner'da Git for Windows ile geldi). PC uygulamasında
  sertifika üretimi ayrıca çözülmeli (bağımlılık ya da gömülü araç).
- Syncthing satır UUID'sini bilmez: aynı içerikli iki dosya iki kopya olarak gelir (10240 yinelenen satır UUID'si); tekilleştirme içe aktarıcıda yapılmalı.
