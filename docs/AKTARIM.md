# AKTARIM — Giden kutusu biçimi ve telefon → PC protokolü (sahibi: müdür)

Sürüm 1 (v0.2.0). Karar A sonucu: telefon uygulaması PC'ye yerel ağda doğrudan HTTPS gönderir; yedek yol elle aktarımdır. Bu belge `docs/INTERFACES.md` §10 "Bekleyenler"deki giden kutusu ve aktarım maddesini kapatır. Değişiklik yalnız müdür tarafından, sürüm artırılarak yapılır.

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
- PC (Windows uygulaması, "Telefon ekle"): 10 dakika geçerli tek kullanımlık kod üretir ve hem metin hem QR olarak gösterir: `km1:` + base64url(JSON `{"a":["192.168.1.20"],"p":47821,"f":"<sertifika SHA-256 hex>","k":"<tek kullanımlık gizli>","n":"<PC adı>"}`).
- Telefon kodu okur/yapıştırır, sertifika parmak izini SABİTLER (başka sertifikaya bağlanmaz) ve `POST /eslestir` gönderir: `{"cihaz_id","ad","platform":"android","model","kod":"<k>"}`.
- PC kodu doğrular (tek kullanım, süre), 32 baytlık `cihaz_anahtari` üretir, yalnız SHA-256 özetini saklar (`devices` tablosu, şema v6: `key_hash`, `paired_at`, `revoked`) ve anahtarı bir kez döner. Telefon anahtarı Keystore ile şifreli saklar.
- Cihaz iptali PC'den yapılır; iptal edilen anahtar 401 alır.

## 3. Aktarım (HTTPS, yalnız yerel ağ)
- PC alıcısı YALNIZ Windows uygulaması açıkken ve "Telefon aktarımı" açıkken dinler. Varsayılan TCP 47821. Kendinden imzalı sertifika ilk açılışta üretilir (`cryptography`), veri klasöründe durur. Kaynak adresi RFC1918, link-local ya da loopback olmayan bağlantı kabul edilmez. İnternete açılmaz, yönlendirme yapılmaz.
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
