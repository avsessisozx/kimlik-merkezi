# Veri şifreleme (Kimlik Merkezi)

Durum: ilk sürüm (dal `tur/i1-sifre`). Bu belge neyin yapıldığını, neyin YAPILMADIĞINI ve neyin
doğrulanamadığını açıkça yazar. Kod: `core/src/kimlikcore/sifreleme.py` (anahtarlar, biçim, kurallar),
`donusum.py` (şifrele / şifreyi kaldır), `hub.py` (şifreli açma), `cli.py` (komutlar).

## 1. Ne korunuyor, neye karşı

Korunan (diskte şifreli, AES-256-GCM): `kimlik.db` içindeki HER ŞEY (olaylar, metinler, FTS arama
dizini, persona, anahtar özetleri, izinler, kaynak üst verisi, zaman damgaları) ve `arsiv/` altındaki ham
dışa aktarma dosyaları.

Karşı konulan tehdit: diskin/yedeğin/klasörün kopyalanması, bilgisayarın çalınması, başka bir Windows
kullanıcısının dosyaları okuması. Parola katmanı ek olarak: aynı Windows hesabına erişen biri.

Karşı KONULMAYAN tehditler (dürüst liste): aynı Windows hesabında çalışan kötü amaçlı yazılım (DPAPI'nin
doğası: aynı hesaptaki her program anahtarı açtırabilir; yalnız parola katmanı bunu aşar); çalışan
sürecin belleği, takas dosyası/hazırda bekletme dosyası; kullanıcının kendi ürettiği düz metin çıktılar
(`disa-aktar` JSONL dosyası ve `cikti/` klasörü); ekran/pano; fiziksel silme garantisi (bkz. §9).

## 2. Mimari seçim: karşılaştırma

| | A. SQLCipher (tüm SQLite dosyası) | B. Sütun düzeyinde yük şifreleme | **C. Şifreli kapsayıcı + bellek içi çalışma (seçilen)** |
|---|---|---|---|
| Kapsam | Tüm sayfalar, FTS dizini dahil | Yalnız seçilen sütunlar | Tüm veritabanı (FTS dizini dahil) |
| FTS5 Türkçe arama | Çalışır (şifre çözme sayfa düzeyinde) | **Bozulur ya da sızdırır**: FTS5 dizini belirteçleri düz metin tutar (`events_fts_data`). Çözüm "kör indeks" (belirteç HMAC'i) önek aramasını (`--onek`) ve ilgili sorguları kaybettirir, eşitlik örüntüsü sızar | Çalışır (düz metin yalnız bellekte), testle kanıtlı |
| Mevcut okuyucular (harita, persona, server SQL'leri `events.payload/text` okur) | Değişmez | Hepsinin yeniden yazılması gerekir | Değişmez (`Hub.open` anahtarı kendisi bulur) |
| Yeni bağımlılık | Bir SQLCipher Python bağlayıcısı (bkz. aşağı) | `cryptography` | `cryptography` (Apache-2.0 OR BSD-3) |
| Bellek / hız | Düşük ek yük | Düşük | DB boyutunun ~2-3 katı bellek; her yazımda dosyanın tamamı yeniden yazılır |
| Bu sürümde güvenle yapılabilir mi | **Hayır** (aşağıya bakın) | Yarım koruma verir (yanıltıcı) | Evet |

### Neden SQLCipher seçilmedi (araştırma, 2026-11)
- PyPI'deki `sqlcipher3-binary` (MIT) yalnız Linux/macOS tekerlekleri yayımlıyor; `pip download --platform
  win_amd64 --python-version 3.12` ile Windows tekerleği BULUNAMADI.
- Windows tekerleği olan `sqlcipher3-wheels` 0.5.7 (win_amd64 / cp312 var) paket üst verisinde lisansı
  **zlib/libpng** diyor; bu, kararınızdaki "yalnız MIT/BSD/Apache" kuralının dışında (içindeki SQLCipher
  BSD tarzı, OpenSSL Apache-2.0 olabilir, ama tekerleğin kendi lisansı ve içeriği ayrıca denetlenmedi).
  Ayrıca topluluk tarafından derlenmiş ikili bir paket: tedarik zinciri güveni ayrı bir karar.
- Windows'ta PyInstaller ile paketlenip çalıştığı burada DENENEMEDİ (Linux makinedeyiz).
- Sonuç: kuralınıza uyan ve doğrulanabilen yol C. SQLCipher, lisans/ikili güven kararı verilip Windows
  CI'da paketlenerek denendikten sonra ileride eklenebilir; kapsayıcı biçimi sürümlü olduğundan geçiş
  `sifrele`/`sifreyi-kaldir` ile yapılabilir. C'nin dezavantajı: büyük veride bellek/yazma maliyeti.

### Neden sütun şifreleme (B) seçilmedi
Arama dizini düz metin kalırsa "şifreli" iddiası yanıltıcı olur; kör indeks özellik kaybettirir ve
`server`/`windows` içindeki doğrudan SQL okuyucularının tamamını değiştirmeyi gerektirir. Yarım ve
yanıltıcı şifreleme göndermemek için elendi.

### C nasıl çalışır
- Diskteki `kimlik.db`, `KMSIFRE1` başlıklı şifreli kapsayıcıdır (düz SQLite başlığı yoktur). Açılışta
  çözülür, `sqlite3.Connection.deserialize` ile BELLEKTEKİ veritabanına yüklenir; düz metin diske yazılmaz
  (`temp_store=MEMORY`, WAL yok).
- Her yazma işlemi (commit) sonrası `serialize()` ile şifrelenip geçici dosya + `fsync` + `os.replace`
  ile atomik yazılır; yarım yazma eski sağlam dosyayı bozmaz. Toplu içe almada (`add_events`) her 5000
  kayıtta değil en çok ~20 sn'de bir ve çağrı sonunda yazılır (aksi halde ikinci dereceden maliyet);
  çökmede son ~20 sn'lik içe alma kaybolabilir, yeniden çalıştırmak güvenlidir (yinelenenler atlanır).
- Dosya biçimi: `KMSIFRE1 | tuz(16) | parçalar`; her parça 1 MiB düz metin + 16 bayt GCM etiketi. Alt anahtar
  = HMAC-SHA256(veri anahtarı, tuz): her yazımda taze tuz, dolayısıyla nonce yeniden kullanımı yok. Nonce
  = sayaç + son-parça bayrağı; başlık AAD'dir. Bit bozma, parça sırası değiştirme, kırpma, sona ekleme
  testlerle yakalanıyor. Aynı biçim ham arşiv dosyaları için de kullanılır (akışla, bellek şişmez).
- Tek yazan süreç kuralı (hub.lock) aynen sürer. Okuyucular (`write=False`) açılışta tutarlı bir anlık
  görüntü alır: açıkken sonradan yazılanı görmez (server her istekte yeniden açtığı için sorun değil).
- Şema sürümü DEĞİŞMEDİ (kapsayıcı şemanın dışındadır). Eski şemalı şifreli klasör: salt okunur açılışta
  `SchemaTooOld`, yazan süreç açınca göç eder ve şifreli yazar (testli).

Ölçüm (bu ortam, 200 000 olay, 116 MB veritabanı; kendi makinenizde değişir): toplu yazma şifreli 5,3 sn /
düz 6,1 sn; salt okunur açma + özet şifreli 1,9 sn / düz 1,8 sn; tek kayıt ekleyip kapatma ≈0,9 sn (dosyayı
okuyup yeniden yazar). Çok daha büyük verilerde (GB) bellek ve gecikme belirgin artar; bu sınırlama bilinen
bir bedeldir.

## 3. Anahtar katmanları

Tek rastgele 32 baytlık VERİ ANAHTARI (DEK) her şeyi şifreler. DEK, `anahtar.json` içinde "yuvalar"
halinde yalnız SARILI saklanır (düz hâli hiçbir yerde yok; testle denetlenir):

| Yuva | Nasıl sarılır | Ne zaman var |
|---|---|---|
| `os` | Windows DPAPI (`CryptProtectData`, stdlib `ctypes`, UI yok, uygulamaya özgü entropi) | Varsayılan (parolasız katman) |
| `parola` | scrypt (n=2^15, r=8, p=1, 16 bayt tuz) → AES-GCM | Kullanıcı parola eklediyse |
| `kurtarma` | scrypt → AES-GCM; ifade NFKC + Türkçe katlama + boşluk düzeltme ile normalleştirilir | Kullanıcı kurduysa (parola için ZORUNLU) |

- Yuva adı ve veri klasörü kimliği AES-GCM AAD'sindedir: yuvaları birbirine kopyalama saldırısı testle
  yakalanıyor. KDF ayarları yuvada saklanır, okunurken üst sınır denetlenir.
- Sağlayıcı bir arayüzdür (`AnahtarSaglayici.sar/ac`): `DpapiSaglayici` (Windows), `SahteSaglayici`
  (testler; `KIMLIK_SAHTE_SAGLAYICI` ortam değişkeni ya da `saglayici_ayarla` ile seçilir, gerçek koruma
  sağlamaz, `durum` çıktısı uyarır).
- **Parola eklenince `os` yuvası kaldırılır.** Aksi halde hesaba girebilen biri parolayı atlardı. Bedeli:
  veri her açılışta parola ister (aşağıda MCP).
- Yeni veri klasörü, sağlayıcı varsa (Windows) varsayılan ŞİFRELİ oluşturulur (`baslat`, Windows
  uygulamasının klasör sihirbazı). Sağlayıcı yoksa (Linux) şifresiz oluşturulur VE bu açıkça uyarılır.
  Mevcut şifresiz klasörler otomatik dönüştürülmez; `kimlikmerkezi sifrele` ister.

## 4. Kurtarma ifadesi ve parola kuralları

Kurtarma yolu seçimi (kullanıcı kararı B): kullanıcının seçtiği uzun ifade. Kurallar (`ifade_degerlendir`):
- En az 4 kelime YA DA en az 20 karakter; ayrıca en az 12 harf/rakam, en az 8 farklı karakter.
- Kısa / "gizli soru" tarzı yanıtlar, tekrar eden kelimeler, tek kalıplı diziler (aaaa, abcdef, 123456) ve
  kısa gömülü zayıf listedeki ifadeler (örn. "correct horse battery staple", "bir iki üç dört beş")
  reddedilir. Güç göstergesi (zayıf/orta/iyi/güçlü) SEZGİSELDİR, gerçek entropi ölçümü değildir; gömülü
  liste kısadır, bu bir kuraldışı-parola listesi değildir.
- İkinci kez yazarak doğrulama zorunlu; eşleşmezse ya da kural çiğnenirse hiçbir şey kurulmaz.
- Parola: en az 10 karakter, en az 5 farklı karakter, zayıf listede olmamalı, kurtarma ifadesiyle aynı
  olamaz. Parola eklemek için kurtarma ifadesi KURULU olmalı (`KuralHatasi`; CLI önce kurdurur).
- Açık uyarı (CLI ve `sifreleme.UYARI_KURTARMA`): parola VE ifade ikisi de unutulursa veri KİMSE
  tarafından kurtarılamaz. Parola ekleme ayrıca `ANLADIM` yazılarak onaylanır (`--anladim` ile atlanır).

## 5. Komutlar

| Komut | İş |
|---|---|
| `kimlikmerkezi baslat [--sifresiz]` | Yeni klasör varsayılan şifreli (sağlayıcı varsa) |
| `durum` | Şifreli mi, hesap koruması, parola, kurtarma, ham dosya sayıları, kalıntı uyarıları |
| `sifrele` | Şifresiz klasörü şifreler (veritabanı + ham arşiv); yarım kalırsa yeniden çalıştırılabilir |
| `sifreyi-kaldir [--onayla]` | Şifrelemeyi kapatır, veri düz metin olur, anahtar dosyası silinir |
| `kurtarma-kur` | Kurtarma ifadesini kurar/değiştirir |
| `parola-ekle [--anladim]` | Parola ekler (ifade yoksa önce kurdurur) |
| `parola-kaldir` | Parolayı kaldırır, anahtarı Windows hesabına geri bağlar |
| `kurtar [--yeni-parola]` | İfadeyle: yeni parola kurar ya da (parola yoksa) anahtarı bu hesaba yeniden bağlar |

Kapatma/açma = veri yeniden şifreleme: `sifrele` yeni dosyayı yazar, geri çözüp doğrular (özet + SQLite
`quick_check`; ham dosyalar için SHA-256), sonra düz kopyayı sıfırlayıp siler. Hata olursa eski hâl
korunur ve anahtar dosyası geri alınır (testli). Her dosya kendini tanıtır; karma durum okunabilir.

## 6. MCP / okuyucular için anahtar erişimi

Tüm okuyucular (`server` MCP süreci, harita, `windows` uygulaması) veriyi `Hub.open` ile açar; `Hub.open`
şifreli klasörü algılayıp anahtarı sırayla (1) `saglayici` (DPAPI), (2) `parola=` argümanı, (3)
`KIMLIK_PAROLA` ortam değişkeninden alır. Tasarım:
- **Parolasız (varsayılan):** MCP süreci Claude Desktop tarafından kullanıcının Windows hesabıyla başlar,
  DPAPI ile anahtarı kendisi açar. Ek sır, yapılandırma değişikliği yok.
- **Parolalı:** MCP süreci kendiliğinden açamaz (DPAPI yuvası kaldırıldı). Seçenekler: (a) MCP girdisine
  `KIMLIK_PAROLA` vermek — parola yapılandırma dosyasında düz metin olur ve parolanın değeri azalır;
  (b) MCP kullanılacaksa parolasız katmanda kalmak. Bu bir ödünleşimdir, gizlenmemelidir.
- Anahtar açılamazsa MCP, sır sızdırmadan şu hatayı döner: "Veri şifreli ve anahtar açılamadı…" (erişim
  kaydına `hata` yazılır). Windows uygulaması açıkken (yazan) MCP salt okur; kapsayıcı atomik değiştiği
  için tutarlı sürüm görür.
- Her MCP isteği veriyi yeniden çözer (116 MB için ≈1 sn). Büyük verilerde önbellek/uzun ömürlü okuyucu
  ileride gerekebilir; yapılmadı.

## 7. Testler

`core/tests/test_sifreleme.py` (biçim, kurallar, yaşam döngüsü, Hub, dönüşüm), `test_sifreleme_cli.py`
(komutlar, alt süreç), `server/tests/test_sifreli.py` (QueryService, MCP stdio), `windows/tests/test_mantik.py`.
Kapsananlar: yanlış parola reddi; kurtarma akışları; ifade/parola kuralları; parola-önce-ifade zorunluluğu;
anahtarın diskte düz metin olmaması; veritabanı ve ham arşiv dosyalarında bilinen metin aranınca (Türkçe
karakterli, düz ve katlanmış hâliyle) bulunmaması; şifreliyken Türkçe katlamalı FTS5 (ISIK/ışık/İstanbul,
önek) çalışması; şifrele↔şifreyi kaldır gidiş-dönüş özet eşitliği; yarım kalan dönüşümün tamamlanması;
hata durumunda geri alma; bozuk/kırpılmış dosya; eski şemadan göç; başka hesapta açılamama.

## 8. Yapılmadı / doğrulanmadı

- **`oneri.db` (persona öneri kuyruğu) ve `erisim.db` (erişim kaydı) ŞİFRELENMİYOR.** İkisi ayrı SQLite
  dosyalarıdır ve birden çok süreç WAL ile aynı anda yazar; bellek içi kapsayıcı modeline uymaz. `oneri.db`
  kişi hakkında öneri cümleleri taşıyabilir: bu, bu sürümün GERÇEK bir açığıdır. Çözüm önerisi: öneri
  kuyruğunu `kimlik.db` içine taşımak (INTERFACES kararı gerekir) ya da sütun düzeyinde şifrelemek.
- `cikti/` klasörü ve `disa-aktar` çıktısı düz kalır (kullanıcı istedi / kullanıcı verisi).
- Anahtar döndürme (yeni DEK ile yeniden şifreleme) yok. `sifreyi-kaldir` + `sifrele` bunu dolaylı yapar.
- Windows uygulamasında parola sorma arayüzü, kurtarma ifadesi sihirbazı ve şifreleme ayar sayfası YOK;
  yalnız CLI. Uygulamada klasör oluşturma varsayılan şifreli olur, parolalı klasör uygulamadan açılamaz.
- **Gerçek Windows DPAPI burada denenemedi** (Linux). `DpapiSaglayici` ctypes kodu yazıldı ve Windows'ta
  koşacak bir test eklendi (`test_dpapi_gercek_gidis_donus`, Linux'ta atlanır) ama hiç çalıştırılmadı.
  Windows CI'da ve elle doğrulanmalı. `windows/paket` PyInstaller derlemesi de Windows'ta denenmedi.
- PyInstaller + `cryptography`: Linux'ta tek dosyalı bir deneme programı (PyInstaller 6.22.3, cryptography
  50.x) AESGCM ile çalıştı; hook kendiliğinden geldi. Windows'ta aynısı beklenir ama doğrulanmadı.
  Spec'e açık `hiddenimport` eklendi.
- Harita (`kimlikserver/harita.py`) şifreli klasörle ayrıca denenmedi; `Hub.query` yolunu kullandığı için
  çalışması beklenir (doğrulanmadı). Tanılama aracı (`tanila`) şifreli klasörü değil dış dosyayı okur.
- Silinen veri: şifreli modda `purge_source` yeni kapsayıcıda içeriği taşımaz, ama dosya sistemindeki
  ESKİ şifreli kopyalar (SSD/yedek) silinmiş içeriğin şifreli hâlini barındırabilir; anahtar aynı olduğu
  için anahtar sızarsa açılırlar. Düz metin kopyalar sıfırlanarak silinir; SSD/günlüklü dosya sistemlerinde
  bu da fiziksel silmeyi GARANTİ ETMEZ.
- Çökme: toplu içe almada ~20 sn'lik pencere (bkz. §2). Windows'ta kapsayıcı değişimi başka süreç dosyayı
  açıkken `PermissionError` verebilir; 1 sn'ye kadar yeniden denenir, sürekli açık tutan bir program
  (antivirüs) varsa yazma hata verebilir (veri kaybı olmaz, eski dosya kalır). Doğrulanmadı.
- Kurtarma ifadesi gücü sezgiseldir; kısa zayıf listesi yeterli bir kara liste değildir.

## 9. INTERFACES için öneri (müdür karar verir; bu dal INTERFACES.md'yi değiştirmedi)

`Hub.open(root, *, write, parola=None, saglayici=None, sifreli=None)`; `Hub.sifreli`; `Hub.raw_parcalari(yol)`
(ham dosyayı düz okumak için; arşiv dosyasını doğrudan `open` ile okumak şifreli klasörde ÇALIŞMAZ);
hatalar: `SifrelemeHatasi` ⊃ `AnahtarGerekli` ⊃ `YanlisParola`, `KuralHatasi`, `SaglayiciYok`,
`SifreliDosyaBozuk`; yeni dosya `anahtar.json` (veri klasörü kökünde, yedeklenmeli: kurtarma ifadesiyle
birlikte tek başına veri açamaz, ama onsuz kurtarma da yapılamaz). Yedek alırken `anahtar.json` DA alın.

## 10. Bağımlılık

`cryptography>=42` (Apache-2.0 OR BSD-3-Clause; tekerlekler OpenSSL içerir, Apache-2.0). Gerekçe: Python
standart kütüphanesinde AEAD yok; kendi şifre yapımımızı yazmak güvensiz olurdu. Yalnız şifreleme
kullanılırken içe aktarılır. `THIRD-PARTY-NOTICES.md` güncellendi.
