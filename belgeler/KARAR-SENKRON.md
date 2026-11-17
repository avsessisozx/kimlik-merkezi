# KARAR A — Telefondan PC'ye aktarım yöntemi

Tarih: 16 Kasım 2026. Ölçüm dalı: `spike/karar-a` (main'e girmez). Yeşil ölçüm koşusu: GitHub Actions `karar-a-olcum` #43801008257 (ubuntu-latest 41/41, windows-latest 41/41). Önceki iki koşu test düzeneği hataları yüzünden kırmızıydı (ayrıntı: `spikes/karar_a/NOTLAR.md`).

**Seçim (şef, kullanıcının "kendin seç ve devam et" talimatıyla): Aday 2, uygulamanın PC'ye doğrudan HTTPS göndermesi. Yedek yol: Aday 3, elle aktarım (dosyayı dışa aktar, PC'de klasörden al).** İtiraz edilebilir; aşağıda elenenlerin nedeni yazılı.

**Dürüst sınır:** GOREV 7.1'e göre bu karar gerçek telefonda (Realme 7 Pro, 1 gün arka plan) ölçülmeden kesinleşmez. O ölçüm yapılmadı, yapılamaz (cihaz kullanıcıda). Emülatörde uçtan uca test de bu ölçümde yok; gerçek uygulamanın istemcisiyle Aşama 6'da CI'de koşacak ve geçmeden APK yayınlanmayacak. Adımlar KULLANICI_ADIMLARI.md'de.

## En zor senaryo ve sonuçlar
PC bir gün kapalı; telefonda kayıt birikir; PC açılınca eksiksiz ve tekrarsız gelir; aktarım ortasında kesilirse bozulmadan devam eder.

| Senaryo | Doğrudan HTTPS | Syncthing 1.30.0 (iki örnek) | Elle kopya |
|---|---|---|---|
| PC kapalıyken birikme, açılınca eksiksiz | GEÇTİ (30 dosya, 3000 satır: ubuntu 1,32 sn, windows 0,27 sn) | GEÇTİ (200 dosya: 1,81 / 2,85 sn) | GEÇTİ (kullanıcı kopyalayınca) |
| Alıcı ortada öldürülür, devam | GEÇTİ (25 MB; kaldığı bayttan devam, SHA-256 eşit) | GEÇTİ (104 MB; ~27 MB yeniden kullanıldı, SHA eşit) | Uygulanmaz |
| Gönderen ortada öldürülür, devam | GEÇTİ | ölçülmedi | Uygulanmaz |
| Aynı dosya iki kez, tekrarsız | GEÇTİ (2. turda 0 bayt, tek kopya) | Aynı adla tek kopya; FARKLI adla iki dosya (satır tekilliğini yine PC sağlamalı) | GEÇTİ (satır UUID'siyle) |
| Yanlış eşleştirme anahtarı | 401, 0 bayt yazıldı | Syncthing cihaz kimliği | Yok |
| Yanlış sertifika parmak izi | İstemci hiç göndermedi | Yok | Yok |
| Yalnız yerel ağ adresleri | Birim testi geçti (gerçek ağda ölçülmedi) | Ölçülmedi | Yok |
| Telefonda silme PC kopyasını siler mi | Hayır (tasarım gereği) | **Varsayılan ayarda EVET, siler**; `ignoreDelete` açılırsa silmez | Hayır |
| Hız | 200 MB: 9,1 sn ubuntu, 2,4 sn windows | benzer | Kopyalama hızı |

Elle kopyada bulgu: kopya tam satır sınırında kesilirse yarım dosya fark edilmiyor. Çözüm ölçüldü: her kapatılmış dosyanın sonuna kapanış kaydı (`{"kapanis":true,"satir_sayisi":N}`) yazılınca kesik kopya yakalanıyor. Giden kutusu biçimine bu kayıt eklenecek.

## Diğer ölçütler
| Ölçüt | Doğrudan HTTPS | Syncthing | Elle |
|---|---|---|---|
| Şifreli, uygulamaya özel giden kutusu | Uyumlu: dosya özel alandan doğrudan gider | **Çelişir:** Syncthing ayrı uygulama, özel alanı okuyamaz; dosyalar paylaşılan klasöre çıkmak zorunda, ayrıca şifreli paket ve anahtar aktarımı tasarlanmalı | Dışa aktarma adımı gerekir |
| Kullanıcının kurulum adımı (tasarım sayımı, kullanıcı testi değil) | 3 + Güvenlik Duvarı izni | 7 (ikinci uygulama kurulumu, cihaz kimliği değişimi, klasör türü ve yolu elle; otomatik kabul edilen klasör yanlış türde geldi) | Her seferinde 3 |
| Bakım riski | Kendi kodumuz, küçük | Android sarmalayıcıları (Syncthing-Fork, BasicSync) üçüncü taraf; lisans ve son sürüm tarihi bu ortamdan DOĞRULANAMADI | Yok |
| CI'de test edilebilirlik | Tam (protokol; emülatör Aşama 6'da) | Çekirdek evet, Android sarmalayıcı hayır | Tam |
| Realme UI / MIUI arka plan dayanıklılığı, pil | ÖLÇÜLMEDİ (yalnız gerçek cihaz) | ÖLÇÜLMEDİ | Etkilenmez (kullanıcı elle yapar) |
| Windows Güvenlik Duvarı / "Ortak" ağ | PC dinler: izin penceresi çıkar; DOĞRULANAMADI | Aynı | Etkilenmez |

## Neden doğrudan HTTPS
1. En zor senaryonun dört parçası da iki işletim sisteminde geçti.
2. Şifreli ve uygulamaya özel giden kutusu kuralını bozmadan çalışan tek otomatik yol.
3. Kullanıcı ikinci bir uygulama kurmaz; eşleştirme tek seferlik.
4. Silme yayılımı riski yok: telefon dosyayı ancak PC "aldım" dedikten sonra siler, PC'deki kopya telefondan bağımsızdır.

## Elenenler
- **Syncthing:** teknik olarak geçti, ama (a) şifreli özel giden kutusuyla çelişiyor, (b) varsayılan ayarda telefondaki silme PC'deki kopyayı siliyor, doğru ayar kullanıcıya bırakılırsa veri kaybı riski var, (c) 7 adımlı kurulum ve ikinci uygulama, (d) Android sarmalayıcısının bakımı doğrulanamadı. Arka plan dayanıklılığı gerçek cihazda bizim yöntemden iyi çıkarsa yeniden değerlendirilebilir.
- **Elle aktarım:** her durumda çalışır ama her seferinde kullanıcı emeği ister. Elenmedi; yedek yol olarak uygulamada kalıyor (ağ ya da Güvenlik Duvarı sorununda).

## Seçimin getirdiği açık işler
- Sertifika: Python standart kütüphanesi sertifika üretemiyor; PC tarafı kendinden imzalı sertifikayı projede zaten bulunan şifreleme kütüphanesiyle üretecek (ölçümde `openssl` komutu kullanıldı).
- Telefonun PC'yi bulması: eşleştirmede adres verilir; adres değişirse yerel ağda yayın (UDP) ile bulma. Gerçek ağda ölçülmedi.
- Realme/MIUI arka plan kısıtlaması: uygulama, kullanıcı açtığında ve "şimdi gönder" dendiğinde her zaman gönderir; arka planda otomatik gönderim en iyi çaba olarak eklenir. Gerçek cihaz sonucu olmadan "arka planda kendiliğinden gider" denmeyecek.

## Bilinmeyenler
Gerçek telefon, pil, gerçek Wi-Fi, Güvenlik Duvarı penceresi, Windows 10; Syncthing imza doğrulaması ve sürümün güncelliği; ubuntu/windows hız farkının nedeni.
