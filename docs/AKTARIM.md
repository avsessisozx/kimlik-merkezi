# AKTARIM — Giden kutusu biçimi ve telefon → PC protokolü (sahibi: müdür)

Sürüm 1.2 (v0.2.0; 1.1: §7 kesinleştirmeler; 1.2: `medya_id` alanı, §8 telefon istemcisi kuralları. Protokol değişmedi). Karar A sonucu: telefon uygulaması PC'ye yerel ağda doğrudan HTTPS gönderir; yedek yol elle aktarımdır. Bu belge `docs/INTERFACES.md` §10 "Bekleyenler"deki giden kutusu ve aktarım maddesini kapatır. Değişiklik yalnız müdür tarafından, sürüm artırılarak yapılır.

## 1. Giden kutusu dosyası (telefon)
- Telefonda uygulamaya özel alanda, Android Keystore anahtarıyla (AES-256-GCM) şifreli durur. Aşağıdaki biçim ÇÖZÜLMÜŞ içeriktir; PC'ye bu içerik TLS içinde gider.
- Dosya adı `<dosya_id>.jsonl` (`dosya_id` UUID4). UTF-8, satır sonu `\n`, her satır tek JSON nesnesi.
- Açık dosyaya yalnız eklenir. Aktarım başlarken, gün değişince (yerel) ya da 1000 kayıtta dosya KAPATILIR; kapatılan dosya bir daha değişmez. Yalnız kapatılmış dosyalar aktarılır.

Satırlar sırayla:
1. Başlık (ilk satır): `{"baslik":true,"bicim":1,"cihaz_id":"<uuid>","dosya_id":"<uuid>","acilis":"<UTC ISO>","uygulama":"0.2.0","android_api":31,"model":"RMX2170"}`
2. Kayıt (0..N): `{"id":"<uuid4>","ts":"<UTC ISO, Z>","tur":"<tür>","kategori":"<kategori>","metin":"<aranabilir düz metin>","yuk":{...},"onceki":"<uuid>|null"}`
   - `onceki`: düzenleme bir "yeni sürüm" kaydıdır ve düzenlenen kaydın `id`'sini taşır.
3. Kapanış (son satır): `{"kapanis":true,"kayit_sayisi":N}`. Kapanışı olmayan ya da `kayit_sayisi` tutmayan dosya eksiktir: PC bekletir, içe almaz.

Türler ve kategoriler (kategori kimlikleri INTERFACES §2):
| tür | kategori | yuk |
|---|---|---|
| `paylasim.link` | `notlar` | `url`, `baslik?`, `kaynak_uygulama?` |
| `paylasim.metin` | `notlar` | `kaynak_uygulama?` |
| `not.hizli` | `notlar` | – |
| `medya.foto`, `medya.video` | `medya_meta` | `ad`, `boyut`, `mime`, `genislik?`, `yukseklik?`, `sure_ms?`, `cekim_zamani?` (GPS YOK) |
| `medya.konum` | `konum` | `enlem`, `boylam`, `medya_id` (yalnız kullanıcı konum iznini ayrıca açtıysa yazılır) |
| `indirilen.dosya` | `dosyalar` | `ad`, `boyut`, `mime` |
| `uygulama.kullanim` | `uygulama` | `paket`, `ad?`, `gun` (yerel tarih), `sure_ms` |

PC tarafında olay anahtarı: `event_key = stable_key("android", cihaz_id, kayit.id)`; `kind = "android." + tür`; `device_id = cihaz_id`. Rol, önem ve hassas konu işareti çekirdekte (şema v5) içe alma anında hesaplanır; telefon bunları hesaplamaz. `not.hizli` ve `paylasim.*` kullanıcının kendi içeriğidir (kategori `notlar` → önem 2).

## 2. Eşleştirme
- PC (Windows uygulaması, "Telefon ekle"): 10 dakika geçerli tek kullanımlık kod üretir ve hem metin hem QR olarak gösterir: `km1:` + base64url(JSON `{"a":["192.168.1.20"],"p":47823,"f":"<sertifika SHA-256 hex>","k":"<tek kullanımlık gizli>","n":"<PC adı>"}`).
- Telefon kodu okur/yapıştırır, sertifika parmak izini SABİTLER (başka sertifikaya bağlanmaz) ve `POST /eslestir` gönderir: `{"cihaz_id","ad","platform":"android","model","kod":"<k>"}`.
- PC kodu doğrular (tek kullanım, süre), 32 baytlık `cihaz_anahtari` üretir, yalnız SHA-256 özetini saklar (`devices` tablosu, şema v6: `key_hash`, `paired_at`, `revoked`) ve anahtarı bir kez döner. Telefon anahtarı Keystore ile şifreli saklar.
- Cihaz iptali PC'den yapılır; iptal edilen anahtar 401 alır.

## 3. Aktarım (HTTPS, yalnız yerel ağ)
- PC alıcısı YALNIZ Windows uygulaması açıkken ve "Telefon aktarımı" açıkken dinler. Varsayılan TCP 47823. Kendinden imzalı sertifika ilk açılışta üretilir (`cryptography`), veri klasöründe durur. Kaynak adresi RFC1918, link-local ya da loopback olmayan bağlantı kabul edilmez. İnternete açılmaz, yönlendirme yapılmaz.
- Kimlik: `Authorization: Bearer <cihaz_anahtari>` ve `X-Cihaz: <cihaz_id>`. Yanlış/eksik/iptal → 401, hiçbir bayt yazılmaz.
- `GET /durum` → `{"surum","pc_adi","protokol":1}`.
- `HEAD /giden/<cihaz_id>/<dosya_id>.jsonl` → `X-Durum: yok|kismi|var`, `X-Alinan: <bayt>`.
- `PUT /giden/<cihaz_id>/<dosya_id>.jsonl`, `Content-Range: bytes <bas>-<son>/<toplam>`, `X-Sha256: <tüm dosyanın SHA-256'sı>`. `bas` alıcıdaki bayta eşit değilse 409 + `X-Alinan`. Son parçada SHA-256 ve kapanış kaydı doğrulanır; tutarsa dosya atomik olarak tamamlanır ve `201 X-Durum: var` döner; tutmazsa geçici dosya silinir, 422.
- Daha önce tam alınmış dosya (içe alınıp taşınmış olsa da) her zaman `X-Durum: var` alır: alınan dosyalar `aktarim_dosyalari(device_id, dosya_id, sha256, kayit_sayisi, alindi)` tablosunda tutulur (şema v6).
- Telefon bir dosyayı ANCAK `var` yanıtını aldıktan sonra siler. Telefondaki silme PC'yi etkilemez.
- Bulma: telefon eşleştirmedeki adresi dener; ulaşamazsa yerel ağa UDP 47822 yayını `KM1?<parmak izinin ilk 16 hex'i>` gönderir, PC `KM1!<port>` ile yanıtlar. Elle adres girme her zaman mümkündür.

## 4. PC'de içe alma
Tamamlanan dosya `gelen_aktarim/<cihaz_id>/` altına düşer; yazan Hub (Windows uygulaması) `android_giden` içe aktarıcısıyla (`importers/`) alır: ham arşive SHA-256 ile kopyalanır, kayıtlar `Hub.add_events` ile eklenir (tekrarsız), dosya klasörden kaldırılır. Aynı dosya ya da aynı kayıt ikinci kez gelirse 0 yeni kayıt.

## 5. Elle aktarım (yedek)
Telefon "Dosyaya aktar": kapatılmış dosyaları tek `.zip` olarak kullanıcının seçtiği yere yazar (kullanıcının açık eylemi; zip şifresizdir, ekranda yazar). PC "Telefon dosyası al" aynı içe aktarıcıyı kullanır. Telefon, kullanıcı "PC'ye alındı" diye onaylamadan dosyaları silmez.

## 6. Android yapı sabitleri
Kotlin + Jetpack Compose. `minSdk 30`, `targetSdk 35`, `compileSdk 35`. Birincil hedef API 31 (Realme 7 Pro, Mi 10T Pro). minSdk 30 seçildi çünkü Redmi Note 10 Pro ve Galaxy Tab A9 Plus'ın sürümü bilinmiyor; Redmi Note 10 Pro Android 11 ile çıktı. Paket adı `app.kimlikmerkezi.toplayici`. Arayüz Türkçe, koyu/açık tema.

## 7. Kesinleştirmeler (sürüm 1.1; PC alıcısı yazılırken netleşenler, bağlayıcı)
- `km1:` metnindeki base64url DOLGUSUZDUR (`=` yazılmaz); çözücüler dolgulu ve dolgusuz iki biçimi de kabul eder.
- `cihaz_anahtari` 64 karakterlik küçük harf hex metindir. `Authorization: Bearer <bu metin>`. PC'de saklanan özet, bu metnin UTF-8 baytlarının SHA-256'sıdır.
- Yeniden eşleştirme: aynı `cihaz_id` geçerli bir tek kullanımlık kodla yeniden eşleşirse anahtar yenilenir, eski anahtar geçersiz olur, iptal kalkar. Kod olmadan yeniden eşleştirme yoktur.
- Telefondan yalnız şu kategoriler kabul edilir: `notlar`, `medya_meta`, `konum`, `dosyalar`, `uygulama`; tek istisna: `ekran.metin` türü yalnız `mesaj` kategorisiyle gelir (v0.3.0; yapay zekâ/MCP yolundan okunamayan hassas kategori). Yeni türler: `sensor.adim` (kategori `uygulama`). Başka kategori taşıyan dosya reddedilir (telefon `persona`, `eposta`, `mesaj`, `sohbet` kaydı yazamaz).
- Alıcı tamamlanan dosyada her satırın JSON nesnesi olduğunu da doğrular; değilse 422. Kategori ve alan denetimi içe aktarıcıdadır.
- Yanıt kodları: tamamlanma `201 X-Durum: var`; zaten alınmış dosyaya PUT `200 X-Durum: var`; yanlış ofset ya da aynı dosyaya eşzamanlı ikinci PUT `409 + X-Alinan`; doğrulama hatası `422`; kimlik `401`; başka cihazın yolu `403`; geçersiz yol `400`; boyut `413`; başlık `431`; `Content-Length` yok `411`.
- Daha önce alınmış ama içe alınıp klasörden kaldırılmış dosya için `HEAD` yanıtı `X-Durum: var`, `X-Alinan: 0` olabilir; telefon `var` gördüğünde bayt sayısına bakmaz.
- Devam, son TAMAMLANAN parça sınırından olur (yarım kalan parça diske yazılmaz). Telefon parça boyutunu en fazla 1 MiB tutar.
- `GET /durum` kimliksizdir ve YALNIZ `{"protokol": 1}` döner (PC adı ve sürüm yerel ağa gösterilmez; §3'teki `surum`/`pc_adi` alanları kaldırıldı, PC adı eşleştirme kodundadır). `/giden/` altında kimliksiz her istek aynı 401'i alır.
- Sınırlar: başlıklar için toplam 10 sn; aynı adresten en çok 4, toplam 32 eşzamanlı bağlantı; cihaz başına en çok 8 yarım yükleme ve 1 GiB geçici alan; 7 günden eski yarım yüklemeler silinir. Aynı ağdaki bir cihaz 5 yanlış denemeyle bekleyen eşleştirme kodunu geçersiz kılabilir (yenisi üretilir; güvenlik kaybı yok).
- PC sertifikası yenilenirse (açılamayan anahtar) parmak izi değişir; PC kullanıcıyı uyarır ve telefonlar yeniden eşleştirilir.
- `medya.foto` ve `medya.video` yükünde ayrıca `medya_id` bulunur: SHA-256(`tür|MediaStore _id|date_added|boyut`) ilk 32 hex (aynı kurulumda kararlı). `medya.konum` kaydının `yuk.medya_id` değeri ilgili fotoğraf kaydının `medya_id`'sidir.
- Tekrarsızlık kayıt `id`'si üzerindendir. Uygulama kaldırılıp yeniden kurulursa `cihaz_id` ve tarama imleçleri sıfırlanır; aynı fotoğraf/indirilen dosya/kullanım günü yeniden kayıt üretir ve PC bunları ayrı kayıt sayar. Bilinen sınır.

## 8. Telefon istemcisi kuralları (sürüm 1.2)
- Ağ: yalnız eşleştirilen PC ile konuşur. Düz HTTP yoktur. TLS'te yalnız eşleştirmede sabitlenen sertifika parmak izi (SHA-256, DER) kabul edilir; sistem sertifika deposuna ve ana makine adına güvenilmez. Parmak izi tutmazsa hiçbir istek gönderilmez ve kullanıcıya "PC'nin güvenlik sertifikası değişmiş; yeniden eşleştir" denir.
- Sıra: `HEAD` → `yok/kismi` ise `X-Alinan`'dan itibaren en fazla 1 MiB'lik `PUT` parçaları → `var` görülünce dosya telefondan silinir. `409` gelirse `X-Alinan`'a göre devam. `401` gelirse gönderim durur, "eşleştirme iptal edilmiş" denir, dosyalar SİLİNMEZ. `422` gelirse o dosya "PC reddetti" olarak işaretlenir, silinmez, hata raporunda sayılır. `507/429` gelirse beklenir.
- Aktarım başlarken açık giden kutusu dosyası kapatılır (§1). Dosyalar eskiden yeniye gönderilir.
- Ne zaman: kullanıcı "PC'ye gönder"e basınca her zaman; ayrıca uygulama açılışında ve arka planda en iyi çabayla (sınırsız/Wi-Fi ağda, periyodik). Arka plan gönderimi garanti DEĞİLDİR (üretici pil kısıtlamaları); ekranda "son başarılı gönderim" zamanı gösterilir.
- Adres: eşleştirmedeki adresler sırayla denenir; hiçbiri yanıt vermezse UDP bulma (§3), o da olmazsa kullanıcı adresi elle girebilir. Yalnız yerel ağ adreslerine (RFC1918, link-local) bağlanılır.
- Alıcının varsayılan TCP portu 47823'tür (47821 Windows uygulamasının kendi yerel arayüz portuyla çakıştığı için §2 ve §3'teki 47821 örnekleri geçersizdir). Port doluysa işletim sisteminin verdiği boş port kullanılır; geçerli port her zaman eşleştirme kodundaki `p` alanında ve UDP bulma yanıtındadır. UDP bulma portu 47822 olarak kalır.
