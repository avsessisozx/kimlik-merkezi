# GOREV-2: Güven ve Gerçeklik Turu (v0.1.1)

Bu dosya, sohbet sıfırlandığında yeni oturumun kaldığı yerden devam etmesi içindir.
Önce `GOREV.md` (ana görev ve kurallar) ve `DURUM.md` okunur, sonra bu dosya.

## 0. EN ÖNEMLİ KURAL (kullanıcının son talimatı)
Kullanıcı bir özellik, hata ya da soru söylediğinde **kodlamaya, dosya değişikliğine
ya da ajan başlatmaya başlama.** Önce ne yapacağını yaz, onay iste (gerekirse iki kez),
onay gelince başla. Soru komut değildir. Gerekmedikçe boşta ajan çalıştırma (token).

## 1. Amaç
Üç şeyi kanıtlamak:
1. Ürün gerçek biçimli dosyalarla çalışıyor.
2. Yabancı biri kurup kullanabiliyor.
3. Verisini kimseye sızdırmadığına güvenilebiliyor.

## 2. Verilen kararlar
| Konu | Karar |
|---|---|
| Uygulama kodu | Açık kaynak, mevcut depo (`avsessisozx/kimlik-merkezi`) public yapılacak. Public yapma işlemini kullanıcı kendisi yapar. |
| Lisans | **MIT** |
| Belgeler | Kapalı kalır, bu private depoda (`kimlik-merkezi-belgeler`). `durum` dalı kod deposundan taşınır; silme ayrıca onaylanır. |
| Gerçek veri testi | Kullanıcı eve gidince kendi bilgisayarında yapacak. Şimdilik ajanlar sahte ama gerçeğe yakın veri üretip test eder. |
| Tanılama aracı | Yazılacak. Kullanıcı dışa aktarma dosyasında çalıştırır, içeriksiz yapı raporu çıkar, rapor ajana yapıştırılır. (Telefon sayfası yok.) |
| Şifreleme | Varsayılan **açık**, parolasız katman: anahtar Windows hesabına bağlı. İsteğe bağlı parola: kurtarma yolu kurulmadan eklenemez. Kapatılabilir. |
| Kurtarma yolu | **B: kullanıcının seçtiği uzun kurtarma ifadesi** (kullanıcı kararı). Kurallar: en az 4 kelime ya da 20 karakter; kısa/gizli soru tarzı cevap yok; güç göstergesi ve bilinen zayıf ifadelerin reddi; ikinci kez yazarak doğrulama; ekranda açık uyarı: parola ve ifade ikisi de unutulursa veri kimse tarafından kurtarılamaz. |

### Karar bekleyenler
- Şifreleme iki katmanlı yapısını kullanıcı "doğru" diye net onaylamadı (son mesajı bunu ima ediyor ama doğrulanmalı).
- Kod deposu public yapılmadan önce git geçmişi taraması sonucu sunulacak. Geçmiş temizliği gerekirse ayrıca onay.

## 3. İş bölümü (aynı anda en fazla 2 ajan)
| Ajan | Görev |
|---|---|
| İ3 İçe aktarıcılar | Her kaynağın resmî biçimini araştır, içe aktarıcıyı sertleştir. Bozuk/büyük/yarım dosya testleri. Tanılama aracı. |
| İ1 Çekirdek | Şifreleme (iki katman), "ağa hiç bağlanmıyor" koruması, silme/dışa aktarma garantileri. |
| İ2 Sunucu / MCP | "Beni tanıyor mu?" ölçüm düzeneği: sahte ama zengin kişi, hafızasız/hafızalı aynı sorular, puanlama. MCP'nin şifreli veriyle çalışması. |
| İ5 Windows / güven | Sağlama toplamı (SHA-256), yazılım malzeme listesi, imza seçenekleri, MIT lisans ve bağımlılık lisansı doğrulama, SECURITY.md, tehdit modeli belgesi. |
| İ6 CI / kalite | "Ağa çıkış yok" testi (kurulum, içe aktarma, MCP sırasında dış bağlantı olursa CI kırmızı). Büyük dosya/performans testleri. |
| İ4 Yabancı kullanıcı | Sadece test eder, kod yazmaz. Yalnızca `KULLANICI_ADIMLARI.md`'yi izler, takıldığı yerleri raporlar. |
| Yönetmen | Kod yazmaz. Koordine eder, dürüst rapor verir. |

## 4. Aşamalar
0. Kararlar (kullanıcı). 1. Gerçeklik: biçim denetimi, sertleştirme, ağ çıkışı testi.
2. Güven: şifreleme, ağ koruması, lisans, sağlama toplamı, belgeler.
3. Kör test: yabancı kullanıcı turu, "tanıyor mu?" ölçümü.
4. Düzeltme: bulguların onaylanan kısmı.
5. v0.1.1 ön sürüm (Harita, öneri kuyruğu, sohbet içe aktarıcıları dahil) ve "doğrulandı / doğrulanmadı" tablosu.

## 5. Başarı ölçütü
- Her içe aktarıcıda "gerçek biçime uygun dosyayla geçti" ya da "doğrulanmadı" açık işareti.
- CI'da dış bağlantı denemesi sıfır.
- Kör kullanıcı testindeki takılmalar kapanmış.
- "Tanıyor mu?" skoru: hafızalı cevaplar hafızasızdan ölçülebilir iyi.

## 6. Dürüstlük notları
- Sahte veriyle geçen test "kısmen doğrulandı"dır; gerçek veriyle geçince "doğrulandı".
- Ajanın "yabancı kullanıcı" testi gerçek insan testinin yerini tutmaz.
- Kod imzası ücretli/başvurulu olabilir, hemen çözülmeyebilir.
- Android toplayıcı bu turda yok.
- Public depoda her commit herkese görünür: sohbet bağlantısı, kişisel veri, anahtar yazma.

## 7. Kod deposu public yapılmadan önce (sırayla, her adım onaylı)
1. Tüm dallarda ve geçmişte tarama (sohbet bağlantısı, e-posta, anahtar, kişisel veri). Sadece okuma.
2. Bulgu varsa geçmiş temizliği için ayrı onay.
3. `LICENSE` MIT yapılır (onaylı). Bağımlılık lisansları doğrulanır.
4. Belgeler bu depoda; kod deposundaki `durum` dalının silinmesi ayrıca onaylanır.
5. Kullanıcı GitHub ayarlarından görünürlüğü kendisi değiştirir.
