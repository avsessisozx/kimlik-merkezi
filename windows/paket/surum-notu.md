Kimlik Merkezi {SURUM} (ön sürüm), Windows
- Yeni: Persona Haritası; persona öneri kuyruğu (siz onaylamadan persona değişmez); ChatGPT, Claude ve elle hazırlanmış sohbet içe aktarıcıları; yeni klasörlerde varsayılan şifreleme ve uygulama içi Güvenlik sayfası; dosya denetimi ("Dosyayı denetle" / `kimlikmerkezi-mcp.exe tanila`, içerik göstermez); daha zengin kimlik kartı, eşanlamlı arama, `say` sayım aracı ve yerel saat; ağa çıkış yok testleri. Lisans: MIT.
- Ağa çıkış yok: telemetri, güncelleme yoklaması ve hata raporu gönderimi yoktur; paket CI'sı süreçlerin yalnız 127.0.0.1 ile konuştuğunu örnekleyerek denetler (kesin kanıt değildir).
- Kurulum: yönetici izni gerekmez. Paket imzasızdır; Windows SmartScreen uyarı verebilir. Önce SHA256SUMS.txt ile özeti doğrulayın, sonra "Ek bilgi > Yine de çalıştır".
- Yayında SHA256SUMS.txt ve yazılım malzeme listesi (SBOM, CycloneDX) bulunur.
- DOĞRULANDI: Windows CI'da kurulum, açılış, sahte veriyle içe aktarma, MCP stdio akışı, dosya denetimi, kaldırma ve ağ izleme. Linux'ta sahte veriyle içe aktarıcı ve şifreleme testleri.
- DOĞRULANMADI: hiçbir içe aktarıcı gerçek bir dışa aktarma dosyasıyla denenmedi; Claude Desktop'un gerçek ayar yolu; Windows 10; SmartScreen davranışı; tepsi simgesi; Edge'de görünüm; gerçek DPAPI ile kullanıcı hesabı değişimi; gerçek Claude ile uzun kullanım.
- Bilinen kısıtlar: parolalı klasörde "Claude'a ekle" kapalıdır (bilinçli); hassas kategoriler için ayrı onay yalnızca arayüz bayrağıdır; aynı Windows hesabındaki kötü amaçlı yazılıma karşı koruma yoktur; izin verdiğiniz kategorideki metin yapay zekâ uygulamasının eline geçer.
- Şifrelenmeyenler: `cikti/` klasörü ve dışa aktardığınız dosyalar. Erişim günlüğü kategori ve kayıt sayısını tutar, içeriği değil.
- Yalnız Windows ve Türkçe arayüz; Android uygulaması ve kod imzası yok. Ayrıntı: README ve docs/TEHDIT-MODELI.md.
