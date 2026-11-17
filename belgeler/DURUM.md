# DURUM

## YENİ OTURUM BURADAN BAŞLAR (son güncelleme: 17 Kasım 2026)
**TEK DEPO:** Bu dosya artık kod deposundadır: `avsessisozx/kimlik-merkezi`, `belgeler/` klasörü. Eski `avsessisozx/kimlik-merkezi-belgeler` deposu TAŞINDI (yalnız işaret notu içerir) ve silinebilir; yeni oturum yalnız `kimlik-merkezi` deposunu bağlamalıdır. Aşağıdaki "iki depo" ve "belgeler deposu" ifadeleri eskidir.

Önce bu bölümü, sonra GOREV.md'yi oku. Yalnız `avsessisozx/kimlik-merkezi` deposu bağlı olmalı (kod ve `belgeler/` klasörü). Aynı anda en fazla 2 ajan (kota). Ajanlara yaz: çıktıları `tail` ile kısalt, arka planda izleyici bırakma.

**v0.2.0 YAYINLANDI (ön sürüm, 17 Kasım 2026), TÜM VARLIKLARIYLA:** Windows kurulum dosyası, imzalı Android APK (`KimlikMerkezi-v0.2.0.apk` + `.sha256`), SHA256SUMS, SBOM. Doğrulama: `tam` koşusu 44113096571 yeşil (Windows 3.12, 3.13, büyük dosya); paket koşusu 44123528152 yeşil; imzalı APK koşusu 44134430421 yeşil (`surum-apk`, `surum-dogrula` = imzalı APK emülatörde kuruldu ve AÇILDI, `surum-yayinla`, `uctan-uca`).
**İmza anahtarı kullanıcı kararıyla HERKESE AÇIK DEPODA:** `android/imza/kimlikmerkezi-imza.p12`, parolası `android.yml` içinde (GOREV'deki "anahtarı asla depoya koyma" kuralı kullanıcı tarafından bilerek kaldırıldı: tek kullanıcılı araç, yalnız kendi Releases sayfasından kurulur). Sertifika SHA-256: 3D:5C:62:A6:0E:99:F3:7E:CF:B7:AC:A4:75:2E:05:1D:87:FA:CF:FF:32:98:31:41:7A:48:6D:9E:8E:7A:D8:36. `surum-apk` işi anahtarı depodan alır ve bu parmak izini doğrular (başka anahtarla imzalı APK yayınlanamaz). GitHub Secrets artık GEREKMİYOR. Yeni APK sürümü: `gh workflow run android.yml --ref main -f imzali=true -f yayinla=true` (önce paket.yml Release'i oluşturur; sürüm `build.gradle.kts` versionName = `windows/src/kimlikwin/__init__.py` olmalı; versionCode artırılmalı).
**Küçük tutarsızlık:** v0.2.0 Release sayfasının gövdesi (yayın notu) "imzalı APK'nın emülatörde açılması DOĞRULANMADI" diyor; artık doğrulandı. Oturum Release gövdesini düzenleyemedi (403); depodaki `windows/paket/surum-notu.md` bir sonraki sürümde yeniden yazılır. Zararsız, muhafazakâr yönde.

**Kullanıcıdan bekleyen:** (1) v0.1.3 ve v0.2.0'ı gerçek veriyle ve telefonla deneme (KULLANICI_ADIMLARI H–O ve P–Z); (2) APK'yı Releases'ten telefona kurup denemek; (3) Android uygulaması 'sade' sorusuna yanıt (aşağıda); (4) Redmi Note 10 Pro ve Galaxy Tab A9 Plus Android sürümü, DeepSeek uygulama adı. GitHub Secrets'a hiçbir şey eklenmesi GEREKMİYOR (imza anahtarı depoda). Anahtar dosyasının (p12) bir kopyası kullanıcıda, asıl kopya depoda `android/imza/`.

**Kullanıcının beklentisi ve çalışma kuralları (önemli):** Kullanıcı bu oturumda "çok token harcandı, somut ürün yok" diye haklı olarak şikâyet etti. Kural: önce somut, kullanılabilir sonuç; gereksiz inceleme/ajan turu açma; yeni özellik ekleme; kota kısıtlı. Fikir konuşurken araç çalıştırma, kodlamadan önce yazılı plan çıkarıp onay al (GOREV-2 §0). Kullanıcı her şeyi Türkçe, sade, numaralı adımlarla ister; programcı değildir. "Bitir" dediğinde onay sormadan bitir.

**Android uygulaması sade (kullanıcı sordu, YANITLANMADI):** Kullanıcı "Android uygulaması neden bu kadar sade?" diye sordu. Cevap verildi: bilerek toplayıcı (arama/persona/erişim yalnız Windows'ta) + görünüm hiç tasarlanmadı (hazır Material 3 bileşenleri, ekran görüntüsüne kimse bakmadı). Kullanıcıdan hangisini kastettiği istendi: (1) çirkin/dağınık, (2) eksik özellik (telefonda arama vb.: büyük iş, yeni tasarım), (3) ne yaptığı anlaşılmıyor. Yanıt/ekran görüntüsü gelirse oradan devam; gelmeden başlama.

**Depo durumu (17 Kasım):** kod deposu `main` = uzak `main`; yerel/uzak aynı; tüm özellik dalları main'e birleşmiş; `spike/karar-a` (Karar A ölçümü) bilerek main'de değil, uzakta yedekli. Belgeler deposu aynı. Kullanıcı (ya da başka oturum) iki depoya da `README: Türkçe, düzenli yapı ve doğrudan indirme bağlantısı` commit'i ekledi: ÜZERİNE YAZMA. Yeni oturumda ilk iş `git pull` (iki depoda da).

**Son doğrulamalar (main d3961f2):** `ci` ve `android` (birim + emülatör + uçtan uca gerçek PC alıcısı + imzalı APK emülatörde açılışı) yeşil. `tam` (Windows 3.12 + 3.13 + büyük dosya) main'in 5d1dd84 commit'inde YEŞİL (koşu 44113096571). Yerel (Linux): core 393, server 339, importers 257, entegrasyon 40, eval 34, windows 373+.

**Bu oturumda Windows koşusunun yakaladığı ürün hataları (hepsi düzeldi):** tzdata eksikliği; CRLF'li sohbet dosyaları; alıcıda kimliksiz istekte yanıtın kaybolması; kesilen bağlantının sayacının düşmemesi. Ders: `tam` (Windows) her yayından önce koşmalı; Linux yeşili yetmez.

**Ölçülen, DÜZELTİLMEYEN başarım bulgusu:** şifreli veri klasöründe 40 kayıtlık yazım 2.000 kayıtta 6,7 ms, 20.000 kayıtta 27,5 ms (şifresiz 2,0 → 4,4 ms). Süre veriyle büyüyor (her işlemde veritabanı yeniden yazılıyor olabilir; doğrulanmadı). Kullanıcının 22.000 kaydında sorun değil; yüz binlerce kayıtta olabilir. İş açılmadı.

**ERTELENDİ (kullanıcıya önerildi, itiraz etmedi; açık onay da vermedi):** Bölüm 3'ün tamamı (ses/görüntü içe aktarma, izlenen klasörler, "Sen kimsin" sayfası, belge parçalama, anlamsal arama). Şefin önerisi: v0.2.0'dan sonra sıradaki iş Bölüm 3 değil, persona ve bilgi katmanı (kullanıcının kendi teşhisindeki 3. madde: persona boş); önce kullanıcı gerçek veriyle denesin. Kullanıcı sormadan Bölüm 3'e BAŞLAMA.

**Bilinen küçük açıklar:** içerik taşımayan sayımlar hassas işaretli kayıtları da sayar; uygulama yeniden kurulunca aynı medya yeniden kayıt üretir; hassas konu sözcük listesi insan gözüyle gözden geçirilmedi; kamera ile QR ve gerçek ağda UDP bulma hiç sınanmadı; `tam.yml` tarayıcı testlerinin çoğunu Windows'ta atlıyor (61 skip).

---

# ARŞİV (tarihsel kayıt; GÜNCEL durum yukarıdadır, aşağıdakiler eski olabilir)

## Devam noktası
YOL-HARITASI.md sırası geçerli. main'de: çekirdek (sohbet kategorisi, şema v3), 12 içe aktarıcı (sohbet dahil, hepsi doğrulanmadı), Harita veri katmanı + drill-down API + persona öneri kuyruğu (İ2 bitti). Kırmızı (main): entegrasyon test_icealdan_kimlik_kartina ve windows test_mcp_stdio...(7 araç) → İ5'e verildi. Çalışan: İ5 (1) 2 test düzeltme + Öneri inceleme ekranı, (2) Harita görsel tasarım yenilemesi (HUD, ECharts, zengin demo veri, drill-down/çapraz filtre). Sıradaki: İ2/İ3 boşta → ses/görüntü içe aktarıcıları (yerel whisper+OCR), izlenen klasörler (sürekli güncel), Claude gerçek bağlantı adımları KULLANICI_ADIMLARI'na, sohbet dışa aktarma adımları (ChatGPT/Claude/DeepSeek/Gemini), v0.1.1 ön sürüm, Karar A + Android.

## Yapıldı
- Özel depo avsessisozx/kimlik-merkezi bağlandı; main'e kök dosyalar ve INTERFACES.md v1 itildi.

## Kaldı
Aşama 1-8 (v0.1.0), sonra Karar A + v0.2.0.

## Bilinen hatalar / notlar
- LICENSE: kişisel kullanım için "tüm hakları saklıdır" metni konuldu (kullanıcı değiştirebilir).
- `gh auth status` GH_TOKEN'ı geçersiz gösteriyor, ama REST (gh api) çalışıyor. Repo oluşturma otomatik izin denetiminde reddedildi; kullanıcı depoyu elle açtı.

## Doğrulandı / doğrulanmadı
Doğrulandı (CI, 2026-11-10): ci (ubuntu, py3.12/3.13), tam (windows-latest + 2 GiB büyük test), paket (PyInstaller+Inno sessiz kurulum, açılış, sağlık, MCP stdio, kaldırma, Claude'a ekle sahte ayarla). Yerel: core 60, server 41, importers 35, entegrasyon 3, windows 23.
Doğrulanmadı: gerçek Takeout/Reddit dosyaları; Türkçe Takeout adları; Reddit sütunları; Claude Desktop gerçek ayar yolu; DeepSeek MCP; Windows 10 (runner Server 2025); SmartScreen; tepsi simgesinin ekranda görünmesi; gerçek tarayıcıda görsel kontrol; modelin enjeksiyona kanmaması.

## Müdüre istekler
(yok)

## Kullanıcıdan bekleyen cevaplar
DeepSeek uygulama adı; Redmi Note 10 Pro ve Galaxy Tab A9 Plus Android sürümü; Claude Code otomatik onay adımları.

## 2026-11-14 devam notu (kullanıcı limiti %93; yalnız mevcut işler bitirilecek)
- Yapıldı ve push edildi: Harita aralık hatası düzeltmesi (073dc51).
- Sürüyor: (1) uygulama içi güncelleme (GitHub sürümleri, indirme ve kurma için ayrı onay, ilerleme çubuğu); (2) her dosya/klasör türünü içe aktarma (okunabilen eklenir, bozuk atlanır, ikili dosyalar yalnız kayıt).
- Sonra: iki işi main'e birleştir, testler, push, paket.yml ile v0.1.2 ön sürümü.
- HAFTALIK LİMİT SIFIRLANINCA (ertelendi): uzun belgeleri parçalayıp tamamını alma + anlam bazlı arama; "Sen kimsin" özet sayfası; mirasa bırakma güvenliği; "Claude'a ekle" izin varsayılanı; tema.
- Kullanıcıdan bekleyen: depoyu public yapması, Ford PDF klasöründeki hata metni.

## 2026-11-15 oturumu: v0.1.3 → Android (v0.2.0) → yol haritası (ORKESTRA DÜZENİ)
Görev metni: kullanıcının 15 Kasım mesajı (Bölüm 1: madde 1-13, Bölüm 2: madde 14, Bölüm 3: madde 15). Şef kod yazmaz; işi ajanlara dağıtır, birleştirir, bu dosyayı günceller. Onay beklenmez.

### Devam noktası (yeni oturum buradan sürer)
- Ajan tanımları `kimlik-merkezi/.claude/agents/` altında main'de (b6a8117): kasif, kodcu, android-kodcu, testci, gozden-gecirici (hepsi sonnet).
- **BÖLÜM 1 BİTTİ: v0.1.3 ön sürüm olarak YAYINLANDI** (16 Kasım 2026; paket koşusu 43879176891 yeşil; varlıklar: KimlikMerkezi-Kurulum-v0.1.3.exe, SHA256SUMS.txt, SBOM). Yayın commit'i b6efdb4, CI yeşil (43839815613). Madde 1-13'ün hepsi main'de. Yerelde denenecekler: KULLANICI_ADIMLARI.md "v0.1.3" bölümü (H-O).
- `tam` iş akışı (büyük dosya testleri) elle başlatıldı: koşu 43880188087; SONUCUNA BAKILMADI (importers büyük testi yerelde 10 dk'da bitmedi, sonucu bilinmiyor).
- BÖLÜM 2 (v0.2.0) sürüyor:
  - PC alıcısı (şema v6, `android_giden` içe aktarıcı, `server/aktarim/`, güvenlik incelemesi 13 düzeltme) YEREL main'e birleşti ama HENÜZ İTİLMEDİ: windows/tests/test_v4_goc.py şema sürümünü 5 bekliyor (artık 6), 1 kırmızı. Düzeltme `android/windows-alici` dalındaki işin A maddesi. Dal `android/pc-alici` uzakta yedek.
  - `android/windows-alici` (worktree wt-win2): Windows'ta alıcıyı başlat/durdur, "Telefon ekle" (kod + QR), cihaz listesi, tepsi; ÇALIŞIYOR.
  - GÜNCEL (14:50 UTC): main fb83d30 itildi (PC alıcısı 3 küçük düzeltme dahil). main CI KIRMIZI: windows/tests/test_kopya.py 2 test, neden: açılıştaki telefon alımı sürerken kopya/içe aktarma isteği reddediliyor (gerçek kullanım hatası). Düzeltme dalı `duzeltme/telefon-alim-yarisi` (worktree wt-yaris) ÇALIŞIYOR. İkinci çalışan: `android/uctan-uca` (worktree wt-android): emülatör → gerçek PC alıcısı uçtan uca CI işi (Aşama 6). Kota: 5 saatlik sınır %94 (21:40 UTC sıfırlanır), haftalık %53, Fable %59. Bu iki iş bitince v0.2.0 kalanları: sürüm 0.2.0 + yayın notu, bütünlük denetimi, KULLANICI_ADIMLARI (ADB, pil, Güvenlik Duvarı), imzalı APK (secret bekliyor). BÖLÜM 3'E BAŞLANMADI; kullanıcıya kota nedeniyle sorulacak.
  - (önceki) (14:25 UTC): Android (A1-A4, inceleme düzeltmeleri dahil) ve Windows telefon aktarımı main'e BİRLEŞTİ ve itildi (cc478dc). Çalışan: `android/pc-alici-duzeltme` (PC alıcısında 3 küçük düzeltme). Sırada: gerçek PC alıcısına karşı emülatör uçtan uca testi (CI), sürüm 0.2.0, yayın notu, bütünlük denetimi, imzalı APK (kullanıcının secret eklemesini bekler).
  - (eski) `android/iskelet` (worktree wt-android): A1 (iskelet, şifreli giden kutusu, not, paylaşım) ve A2 (medya, konum, indirilenler, kullanım) BİTTİ, CI yeşil (emülatör API 31). A3 (eşleştirme + gönderim + elle aktarım) YARIM, sürüyor. Android henüz main'de DEĞİL.
  - SONRA: Android dalını incele + main'e al; gerçek PC alıcısına karşı emülatör uçtan uca testi (Aşama 6, CI); imza anahtarı üret, GitHub Secrets'a yaz, anahtar dosyasını kullanıcıya teslim et; imzalı APK; iki platform ortaklıkları (hata raporu, tema, eşleştirme) denetimi; bütünlük denetimi; v0.2.0 yayını; KULLANICI_ADIMLARI (ADB kurulumu, Realme/MIUI pil, Güvenlik Duvarı, gerçek telefon aktarımı).
- BÖLÜM 3 başlanmadı.
- KOTA: 16 Kasım 13:50 UTC itibarıyla haftalık sınır tüm modeller %46, Fable %52 (sıfırlanma Pazar 19:00). 5 saatlik sınır bu oturumda 3 kez doldu. Bundan sonra aynı anda en fazla 2 ajan.
- Sıra: A (1,2,3) → B (4-8) → C (9) → D (10,11) → E (12) → F (13). server/ ile importers/ işleri paralel; aynı dosyaya dokunanlar sırayla.

### Ajan düzeni günlüğü
| Bölüm/madde | Ajan | Deneme | Sonuç / takılan nokta |
|---|---|---|---|
| Keşif (Bölüm 1) | kasif ×2 | 1 | server+windows ve importers+core raporları; ikisi de ilk seferde yeterli. |
| Temel ölçüm | testci | 1 | main yeşil: core 149, server 115, importers 212, windows 277, entegrasyon 34(+1 yaml atlaması). |
| M2/M3 içe aktarıcı | kodcu → gozden-gecirici → kodcu | 2 | İnceleme: kod hatası yok, 3 test boşluğu + kimliksiz mesaj anahtarı; 2. turda kapandı. importers 225. |
| M2 kopya-temizle (core) | kodcu → gozden-gecirici → kodcu | 2 | İnceleme 4 önemli bulgu (iki çalıştırmada geçerli mesajın kaybı, yedek zaman, K2 güvenlik sınırı, bellek); 2. turda kapandı. core 168. İkinci inceleme yapılmadı (sürüm öncesi bütünlük denetimine bırakıldı). |
| M1 rol (server) | kodcu → testci + gozden-gecirici → kodcu | 2 | İnceleme gerçek hata buldu: rol süzgeci asistan cevapları çokken kullanıcı mesajını kaçırıyordu. Kodcunun ilk test sayıları yanlıştı (nokta saymış); testçi doğrusunu verdi. server 127. |
| Şema v5 (core) | kodcu → gozden-gecirici → kodcu | 2 | Göç güvenli bulundu; sözcük listesinde gizlilik boşlukları (Kur'an, kliniğe, intihar, polis, vergi...) 2. turda kapandı. core 385. Terim listesi insan gözüyle gözden geçirilmeli. |
| B bölümü M4-8 (server) | kodcu | 1 (kota kesintisiyle) | Önce/sonra: ara 118149→3990, zaman_cizelgesi 112126→4671, ornekle 58389→6830, say ay 7319→1719, kimlik_karti 6182→3028 karakter. İncelemede. |
| M10/12 sunucu | kodcu → gozden-gecirici → kodcu | 2 | İnceleme BİRLEŞTİR + 5 küçük (konu kimliğinde tırnak → sorgu hatası, kartta önem 0 beslemesi, test boşlukları); kapandı. server 163. Sorgu envanteri: süzgeçsiz yol yok. |
| Karar A ölçümü (spikes) | kodcu | 1 (3 CI turu) | 41/41 ubuntu+windows. Sorun: ajan bıraktığı arka plan izleyicisi yüzünden aynı raporu 4 kez yeniden gönderdi; şef durdurdu. Ders: ajanlara 'arka planda izleyici bırakma' yazılıyor. |
| Windows M9/M11/kopya/paket | kodcu | 1 | 4 commit, windows 322. İncelemede. |
| Windows M9/M11/kopya + konu izni | kodcu → gozden-gecirici → kodcu | 2 | İnceleme 2 ENGELLEYİCİ buldu (CLAUDE.md bloğunda işaretçi enjeksiyonu; kullanıcı metninde işaretçi örneği varken metin kaybı) + 10 bulgu; 2. turda kapandı. windows 347. |
| Bütünlük denetimi 0.1.3 | gozden-gecirici + testci | 1 | Denetim: sürüm 0.1.2 kalmış, yayın notu bayat, tehdit modeli yönetilen bloğu anlatmıyor. Testçi: main CI kırmızı (2 tarayıcı testi; test düzeneğinde HOME yönlendirmesi Playwright yolunu bozmuş). Yerelde görünmüyordu; testçi yakaladı. |
| Yayın hazırlığı + CI düzeltmesi | kodcu ×2 | 1+1 | 0.1.3 yayınlandı. Not: bir kodcu yine arka planda iş bırakıp 'bekliyor' durumunda kaldı; şef durdurdu. |
| PC alıcısı (v6, içe aktarıcı, alıcı) | kodcu → gozden-gecirici → kodcu | 2 | Güvenlik incelemesi 1 ENGELLEYİCİ (yavaş bağlantıyla 32 bağlantıyı kilitleme) + disk kotası, derin JSON, sessiz sertifika yenileme, alıcı/içe aktarıcı tutarsızlığı; 13 madde kapandı. server 324. İkinci inceleme yapılmadı. |
| Android A1, A2 | android-kodcu | 1+1 (her biri 2-3 CI turu) | CI birim + emülatör yeşil. İnceleme henüz yapılmadı (A3 ile birlikte yapılacak). |
| Kurulum | şef | 1 | Ajan tanımları yazıldı. Not: oturum başladıktan sonra eklenen `.claude/agents` türleri bu oturumda `subagent_type` olarak tanınmadı ("Agent type 'kasif' not found"); ajanlar genel amaçlı alt ajan + model sonnet ile başlatılıp ilk iş olarak kendi rol dosyasını okuyor. Yeni oturumda doğrudan ajan adıyla çağrılabilmeli (doğrulanmadı). |

### Şefin verdiği kararlar (itiraz edilebilir)
- Kopya kuralı: aynı platform+rol+zaman+metin = kopya (konuşma kimliği farklı olsa da); zamanı konuşma zamanına eşit olan mesajlar "zamanı belirsiz" sayılır ve temizliğe girmez (yanlış gizlemeyi önlemek için). Gizleme geri alınabilir tombstone'dur, silme değildir.
- Dal dışı (yeniden üretilmiş) cevaplar veritabanından ayırt edilemiyor (dal bilgisi saklanmamış); bu yüzden `kopya-temizle --paket <zip>` paketi yeniden okuyup güncel dalı çıkarır. Bir konuşmanın tüm mesajları dal dışı çıkarsa o konuşma atlanır.
- `ornekle` sohbette varsayılan olarak yalnız kullanıcının kendi mesajlarını verir; `persona_oner` asistan mesajını kanıt kabul etmez.
- Şema v5: `events.onem` (0/1/2) ve `events.hassas_konu` içe alma anında çekirdekte hesaplanır (Android dahil her kaynak için tek yer); mevcut kayıtlar göçle işaretlenir; konu izni ayrı tablo `konu_izinleri`.
- Karar A: doğrudan HTTPS (gerekçe ve elenenler KARAR-SENKRON.md). Android minSdk 30, targetSdk 35, paket adı `app.kimlikmerkezi.toplayici`.
- Hassas konu: içerik taşımayan sayımlar (tür, ay, saat...) işaretli kayıtları saymaya devam eder (içerik sızmaz, varlık çıkarılabilir); kimlik kartı konu izni olsa bile işaretli kaydı kullanmaz.
- Yönetilen blok hedefleri: `~/.claude/CLAUDE.md` ve yalnız `~/.codex` varsa `~/.codex/AGENTS.md`; içerik yalnız onaylı persona; 3000 karakter.
- Token: kayıt sözlüğü sadeleşti (tek yerel `zaman`, kayıt başına etiket yok), `kimlik_karti` MCP varsayılanı kısa mod, say satırları `[deger, sayi]`.

### Kullanıcıdan bekleyen cevaplar (bu oturum; beklenmeden devam ediliyor)
- **Android imza anahtarı (v0.2.0'ı TUTAN tek şey):** anahtar bu oturumda üretildi (sertifika SHA-256 3D:5C:62:A6:0E:99:F3:7E:CF:B7:AC:A4:75:2E:05:1D:87:FA:CF:FF:32:98:31:41:7A:48:6D:9E:8E:7A:D8:36), üç dosya kullanıcıya sohbetten gönderildi. Oturum GitHub Secrets'a yazamıyor (proxy 403). Kullanıcı dört secret'ı (KM_KEYSTORE_B64, KM_KEYSTORE_PAROLA, KM_ANAHTAR_AD, KM_ANAHTAR_PAROLA) eklemeli: adımlar KULLANICI_ADIMLARI.md sonunda. Eklendikten sonra: `gh workflow run android.yml -f imzali=true` (işler `surum-apk` + `surum-dogrula`; hiç koşmadılar, ilk koşuda hata çıkabilir). ANAHTAR DOSYASI YALNIZ KULLANICIDA VE BU OTURUMUN GEÇİCİ KLASÖRÜNDE; oturum kapanırsa buradaki kopya gider.
- Redmi Note 10 Pro ve Galaxy Tab A9 Plus Android sürümü (minSdk için; şimdilik 31 değil daha düşük makul bir değer seçilecek, karar Bölüm 2'de yazılır).

### v0.3.0 (17 Kasım 2026, dal `v0.3.0`) — Devam noktası (yeni oturum buradan sürer)
- **A (Windows düzeltmeleri) yapıldı, ci yeşil**: Takeout klasörü içe aktarma (sembolik bağ yok, yerinde okuma, Windows'a uygun dosya adı, okunamayan dosyada gerçek ad+neden), sahip görünümü (hassas dahil tam; yapay zekâ/MCP yolu kısıtlı), saatler Türkiye saatiyle (TSİ). Doğrulandı: ci (ubuntu, tarayıcı testleri dahil). DOĞRULANMADI: Errno 22'nin gerçek kök nedeni (Windows `tam` koşusu 44160292262 sonucu bekleniyor), kullanıcının PC'sinde klasör içe aktarma.
- Sırada: B galaksi arayüzü (prototip: scratch Main.dc.html → gerçek veri), "Sen kimsin" sayfası, sadeleştirilmiş menü, hâl katmanı; C sesli arama (Whisper medium, kural tabanlı süzgeç); D PC alıcısı yeni veri türleri; E Android (toplayıcı anahtarları, izin akışı, pil rehberi, ana ekran, temel karşılaştırma); F sürüm 0.3.0, yayın notu ≤10 satır, kullanıcı test listesi, ci yeşilse main'e yayın.
- Yerelde ijson yok: importers testleri ve `konsol tanila` testleri yalnızca CI'da doğrulanır.

- **(güncelleme) B, C, D, E yapıldı ve dala itildi; F sürüm hazırlığı sürüyor.** B galaksi + Sen kimsin + menü + hâl; C yazı/ses arama (Whisper ayrı süreç, kurulum onaylı); D PC alıcısı `sensor.adim` ve `ekran.metin` (yalnız `mesaj` kategorisiyle); E Android adım/ekran metni anahtarları, yerel geçmiş (ana ekran artık gönderilmiş kayıtları gösterir), pil rehberi, `KARAR-ANDROID-TEMEL.md` (kendi kod önerilir, seçim kullanıcıda). Sürüm 0.3.0 işlendi.
- DOĞRULANMADI (v0.3.0): gerçek telefonda adım sayacı ve erişilebilirlik hizmeti; mikrofon + Whisper kurulumu kullanıcının PC'sinde; Errno 22 kök nedeni; realme pil menü yolları; galaksi gerçek 5 kaynakla (yalnız demo veriyle görüldü).
