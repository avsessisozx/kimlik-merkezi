# Biçim denetimi: içe aktarıcıların varsaydığı ile gerçek dışa aktarma biçimi

Tarih: 2026-11-10. Kapsam: `importers/` (Aşama 1, biçim denetimi). Bu belge, her kaynağın dışa aktarma
biçimine dair **neyi, nereden, ne kadar güvenilir** öğrendiğimi ve içe aktarıcıda ne değiştirdiğimi yazar.

## 0. Yöntem ve dürüst sınırlar

- Bu ortamda yalnız şu adresler açılabildi: `raw.githubusercontent.com` (açık kaynak depoların dosyaları),
  `pypi.org` ve `files.pythonhosted.org` (paket kaynak arşivleri). **Resmî yardım sayfaları açılamadı**
  (support.google.com, developers.google.com, help.openai.com, support.spotify.com, help.instagram.com,
  docs.github.com, reddit.com, topluluk blogları): ağ izin listesi dışı. Bu yüzden:
  - "Kod okundu" diyen yerler: açık kaynak ayrıştırıcının gerçek kodu/şeması okundu (en güçlü kanıt, ama
    ikinci el: ayrıştırıcıyı yazan kişinin kendi dışa aktarmasına dayanır).
  - "Arama özeti" diyen yerler: web aramasının döndürdüğü özet metin. Resmî belge DEĞİL, sayfanın kendisi
    okunmadı. Bunlara dayanan her şey "doğrulanmadı" sayılır.
  - "Hafıza" diyen yerler: önceki oturumun/benim bilgim; kaynağı gösterilemez. Hepsi "doğrulanmadı".
- Hiçbir kaynaktan kod kopyalanmadı; yalnız alan/dosya adları ve biçim bilgisi alındı. Okunan depoların
  lisansları: google_takeout_parser MIT, LocationHistoryFormat MIT, HPI MIT, browserexport MIT, convoviz MIT,
  claude-export MIT, chatgpt-to-markdown MIT, browser-history Apache-2.0. (Önceki oturumdan kalan
  now2ai-claude-export-processor GPLv3'tür: yalnız alan adları için bakılmıştı; bu turda kullanılmadı.)
- **Gerçek bir kullanıcı dışa aktarması hiçbir kaynak için görülmedi.** Test dosyaları (`fixtures/gercekci/`)
  bu araştırmaya göre elle kurulmuş uydurma verilerdir. "Testten geçti" = "bizim varsayımımızla tutarlı".
- Takeout klasör adlarının Türkçesi hiçbir kaynakta bulunamadı. Türkçe klasör adlı test verisi VARSAYIMDIR;
  içe aktarıcı zaten dosyayı adından değil içeriğinden tanır.

## 1. Özet: bulunan farklar ve yapılan düzeltmeler

| Kaynak | Fark (varsayılan ↔ bulunan) | Kanıt düzeyi | Düzeltme |
|---|---|---|---|
| Takeout konum | `Records.json`, "Semantic Location History" aylık dosyaları, yeni `Timeline.json` hiç tanınmıyordu ("Takeout içeriği bulunamadı") | kod+şema okundu (ilk ikisi); Timeline.json arama özeti | `konum` kategorisinde üç biçim eklendi |
| Takeout YouTube | `playlists/likes.json` "2017 öncesi eski etkinlik" diye yanlış etiketlenip atlanıyordu | kod okundu | `youtube.begeni` olayı olarak alınıyor |
| Takeout Gemini | `safeHtmlItem` "beklenmeyen alan" çıkıyordu; "Prompted " öneki yalnız İngilizce; "Bard" başlığı | arama özeti | alan bilinen sayıldı; yerelleştirilmiş "<Önek>: " (≤4 kelime) atılıyor; Türkçe önek DOĞRULANMADI |
| Her JSON | UTF-8 BOM'a ek olarak CESU-8 (ayrı kodlanmış vekil yarımları, emoji) dosyalar `UnicodeDecodeError` ile bütün içe aktarmayı düşürürdü | kod okundu (convoviz uyarısı) | `strip_bom` akışı onarıyor; geçersiz UTF-8 yine hata veriyor |
| ChatGPT | sesli sohbet parçası (`audio_transcription`, `parts` içinde nesne) düşüyordu; araç çağrıları (`recipient != all`) ve düşünme ara notları kullanıcıya görünür mesaj gibi alınıyordu | kod okundu (convoviz) | döküm alınıyor; araç çağrısı/ara not atlanıp sayılıyor |
| Claude | `content` düz metin (str) gelirse boş okunurdu | kod okundu (claude-export) | str de kabul |
| Meta | Üst anahtar adına göre şekil varsayımı: `saved_saved_media` / `comments_media_comments` kaydı `string_map_data` taşırsa olaylar **sessizce hiç üretilmiyordu** (hata da sayaç da yok) | fixture ile yeniden üretildi; gerçek dosya şekli HAFIZA | şekil kayıt başına seçiliyor (`string_list_data` ya da `string_map_data`); href/başlık alınıyor |
| Spotify | `searchTime` sonunda Java eki `...Z[UTC]` olursa tarih okunamazdı | HAFIZA | `iso_utc` köşeli ek'i atıyor |
| Tarayıcı | Firefox `visit_date` çok eski sürümlerde ms; Opera/Vivaldi yolları yok; Safari `History.db` "tanınmadı" | kod okundu (browserexport, browser-history) | ms→µs normalizasyonu, yollar, Safari için anlaşılır "desteklenmiyor" |
| Gmail MBOX | `X-Gmail-Labels` düz virgülle bölünüyordu | HAFIZA/savunmacı | tırnak duyarlı bölme |
| Reddit | `messages_archive.csv` bilinmiyordu | HAFIZA | `messages.csv` ile aynı şemayla eklendi |
| Genel sohbet | yarım (kesik) tek-nesne JSON `json.JSONDecodeError` ile **çöküyordu** (yeni dayanıklılık testi buldu) | test | yakalanıp anlaşılır hata |

Kalan her şey (Reddit sütunları, GitHub dosya adları, Instagram/Facebook gerçek şekilleri, Spotify tam
alan listesi) için **gerçek kaynak bulunamadı**; aşağıda ayrıntı.

## 2. Kaynak kaynak

### Google Takeout (arama, YouTube, Chrome, My Activity)
- Kod okundu: purarue/google_takeout_parser (MIT) `README.md`, `locales/en.py`, `parse_json.py`
  <https://github.com/purarue/google_takeout_parser>. PyPI sdist 0.1.13 de açıldı.
  - Yollar: `Chrome/BrowserHistory.json` ve `Chrome/History.json` (ikisi de var), `My Activity/<ürün>/…MyActivity.json`,
    `YouTube( and YouTube Music)?/history/*.json`, `…/playlists/likes.json`, `Location History( \(Timeline\))?/Records.json`,
    `…/Semantic Location History/<yıl>/<dosya>.json`.
  - "Klasör adları hesabın ana diline göre değişir"; ayrıştırıcı yalnız EN ve DE'yi bilir. "JSON seçin, HTML değil."
  - Etkinlik: `header`, `title`, `time` zorunlu; `titleUrl`, `description`, `details[].name`, `locationInfos`, `products`,
    `subtitles[].name/url` isteğe bağlı; eski biçim `snippet.publishedAt` taşır. Chrome: `{"Browser History": [{time_usec, title, url,
    page_transition}]}`.
- Mevcut içe aktarıcıyla uyum: etkinlik, Chrome, abonelik CSV'si, dosyayı içeriğinden tanıma, `History.json`/`BrowserHistory.json`
  ikisi de doğru varsayılmıştı. Tarih biçimi (`2024-03-05T10:11:12.123Z`, kesirli saniyeli/kesirsiz) `fromisoformat` ile okunuyor.
- Türkçe/yerel adlar: kaynak bulunamadı. Mevcut yaklaşım (içerikten tanıma) zaten bunu karşılıyor; abonelik CSV başlığı yerel olsa bile
  satırlar `UC…` kimliğinden tanınıyor.

### Google konum geçmişi (Records.json, Semantic Location History, Timeline.json)
- Şema okundu: CarlosBergillos/LocationHistoryFormat (MIT) `schemas/Records.schema.json`, `Semantic.schema.json`
  <https://github.com/CarlosBergillos/LocationHistoryFormat>. Yazarlar "Google resmî belge vermedi, biçim yıllar içinde değişti" diyor.
  - `Records.json`: `{"locations": [{latitudeE7, longitudeE7, accuracy, source (WIFI/CELL/GPS...), deviceTag, timestamp (ISO) ve/veya
    timestampMs (metin), platformType, formFactor, activity[], …}]}`.
  - Aylık: `{"timelineObjects": [{"placeVisit": {location{latitudeE7,longitudeE7,placeId,address,name,semanticType}, duration{startTimestamp,
    endTimestamp}, placeConfidence…}} | {"activitySegment": {startLocation,endLocation,duration,distance,activityType,…}}]}`; eski dosyalarda
    `…TimestampMs`.
- Yeni cihaz içi `Timeline.json` (`semanticSegments`, `rawSignals`, `userLocationProfile`; `visit.topCandidate.placeLocation.latLng`
  `"41.0°, 29.0°"`, `activity.start/end.latLng`, `timelinePath[]`): **yalnız arama özeti** (topluluk araçları). Takeout'un artık bu
  biçimi vermeyebileceği, telefondan "Zaman çizelgesini dışa aktar" ile alındığı belirtiliyor. DOĞRULANMADI.
- Değişiklik: üç biçim `konum` (hassas) kategorisinde alınıyor. `Records.json` kaydı başına bir olay (büyük dosya akışla), aylık dosyada yer ziyareti
  ve hareket parçası, yeni biçimde ziyaret/hareket (yol noktaları atlanıp sayılıyor). Koordinat aralık dışı kayıtlar atlanıp sayılıyor.

### Google Gemini (Takeout "My Activity")
- Yalnız arama özetleri: dosya `My Activity/Gemini Apps/MyActivity.json` (bazı kaynaklarda `Gemini`), kayıt anahtarları `activityControls, header,
  products, safeHtmlItem, time, title`; yanıt HTML `safeHtmlItem[].html`; başlık önekü yerelleşiyor (Almanca "Eingegebener Prompt: ").
- Değişiklik: önek atma genelleştirildi; `Bard` başlığı da Gemini sayılıyor. Türkçe önek bilinmiyor (DOĞRULANMADI).

### Gmail MBOX
- Kod okundu: google_takeout_parser `Mail/` yolunu bilerek yok sayar (içerik ayrıştırmaz). Biçim bilgisi: standart mbox/mboxrd ("From " ayırıcı),
  Gmail'in `X-Gmail-Labels`, `X-GM-THRID` başlıkları (önceki oturumda hafızadan). Etiketlerde virgül/tırnak davranışı kaynaksız (HAFIZA).
- Değişiklik: etiket bölme tırnak duyarlı (zararsız savunma). RFC 2047 kodlu başlıklar (`=?UTF-8?B?…?=`) test verisinde var ve doğru çözülüyor.

### ChatGPT
- Kod okundu: mohamed-chs/convoviz 1.0.1 (MIT) `chatgpt/files.py`, `chatgpt/parse.py`, PyPI
  <https://pypi.org/project/convoviz/>. Bulguları:
  - Düzen: `conversations.json` ya da büyük hesaplarda `conversations-000.json …` parçaları, `export_manifest.json` (`logical_files` ya da
    `export_files:[{path,size_bytes}]`); ekler kökte `file_<hex>.dat`, `conversation_asset_file_names.json`, `library_files.json`.
  - "Yayımlanmış şema yok; anahtarlar sürümler arasında gelip gidiyor."
  - İçerik türleri: `text`, `multimodal_text` (parts: metin + `image_asset_pointer`/`audio_asset_pointer`/`audio_transcription` nesneleri),
    `code`, `execution_output`, `tether_quote`, `tether_browsing_display`, `thoughts`, `reasoning_recap`, `user_editable_context`.
    Araç çağrıları `author.role="assistant"` ve `recipient != "all"`; gizli mesajlar `metadata.is_visually_hidden_from_conversation`;
    düşünme ara notu `metadata.is_thinking_preamble_message`.
  - Bazı dışa aktarmalarda emoji ayrı vekil yarımları (CESU-8) olarak kodlu: katı çözücü düşer.
- Önceki dayanak: pionxzh/chatgpt-exporter `src/api.ts` (MIT).
- Mevcut içe aktarıcıyla uyum: `mapping` ağacı + `current_node`, çok parçalı `conversations-NNN.json` (içerikten tanıma), `user.json`/`message_feedback.json`
  yok sayma zaten doğruydu.
- Değişiklik: `audio_transcription` alınıyor; araç çağrısı ve ara not atlanıp sayılıyor; CESU-8 onarımı.
- Açık: görseller/ekler/canvas içeriği alınmıyor; resmî alan listesi (OpenAI yardım sayfası) görülmedi.

### Claude (claude.ai)
- Kod okundu: claude-export 0.1.0 (MIT) `models.py` <https://pypi.org/project/claude-export/>;
  claude-json-to-markdown 0.2.0 (MIT). Alanlar: `uuid, name, created_at, updated_at, project_uuid`, `chat_messages[]` (`uuid, created_at,
  sender: human|assistant, text, content: [{type:"text",text}…] (ya da düz metin), attachments[{file_name,…}], files`).
- Değişiklik: `content` düz metin biçimi eklendi. Resmî dışa aktarma sayfası görülmedi; `users.json`/`projects.json` zaten okunmuyor.

### Instagram / Facebook (Meta)
- Kod okundu: purarue/HPI `my/facebook/gdpr.py` (MIT): zaman damgaları saniye (`timestamp`, `created_timestamp`), mesajlarda `timestamp_ms`;
  konuşmalar `messages/inbox/<konuşma>/message_N.json`, kök `participants` + `messages`. HPI mojibake düzeltmesi yapmıyor.
- Arama özeti (resmî değil): Instagram listeleri `string_list_data: [{href, value, timestamp}]` taşır (takipçi/beğeni); Facebook/Instagram JSON'u
  UTF-8 baytlarını latin-1 sanıp `\u00XX` kaçışlıyor; düzeltme "latin-1 ile kodla, UTF-8 ile çöz". Instagram için kesin kaynak yok.
- Fark: şekil üst anahtara bağlı varsayılıyordu. Gerçek sürümler aynı anahtarı farklı şekillerle verebilir (kaydedilen/yorum için
  `string_map_data` bilgisi HAFIZA); eski kod bu durumda hiçbir şey üretmeden geçiyordu. Artık kayıt başına şekil seçiliyor.
- Açık: gönderi/hikâye/reels dosya adları ve Facebook'un yeni `your_facebook_activity` düzeni için gerçek örnek yok.

### Reddit (hesap veri isteği)
- **Kaynak bulunamadı.** Arama özeti yalnız "ZIP içinde CSV'ler (posts, comments, saved_posts, messages…)" diyor; sütunlar için kod/şema bulunamadı
  (bulunan açık kaynak araçlar API kullanıyor). Mevcut sütun listesi (`id, permalink, date, ip, subreddit, gildings, link, parent, body, media` vb.)
  hafızadan; **hiç doğrulanmadı**. Kayıt zamanı `2024-03-05 10:11:12 UTC` biçimi `iso_utc` ile okunuyor.
- Değişiklik: `messages_archive.csv` eklendi (HAFIZA). Tanınmayan CSV'ler rapora "desteklenmiyor" olarak yazılıyor (sessiz değil).

### GitHub hesap verisi
- Arama özeti: tar.gz, JSON + Git; 7 gün geçerli bağlantı. Dosya adları (`repositories_000001.json`…) ve her kayıtta `type` alanı: HAFIZA.
  **Doğrulanamadı.** Değişiklik yok; dayanıklılık testleri eklendi.

### Spotify
- Kod okundu: purarue/HPI `my/spotify/gdpr.py` (MIT): `Playlist*.json` = `{"playlists":[{name, lastModifiedDate "YYYY-MM-DD", numberOfFollowers,
  items:[{track:{trackName,artistName,albumName}}]}]}`; dosya önekleri `Follow, Inferences, Payments, Playlist, StreamingHistory, Userdata, YourLibrary`.
- Arama özeti: genişletilmiş geçmiş dosyaları `Streaming_History_Audio_*.json` (bitiş zamanı UTC, kullanıcı adı, platform, ms çalma, ülke, IP,
  kullanıcı aracısı, parça/sanatçı/albüm/URI alanları). Tam anahtar adları (`ip_addr` ya da `ip_addr_decrypted`) resmî yardım sayfasından
  doğrulanamadı; ikisi de bilinen sayılıyor, IP hiçbirinde alınmıyor.
- `SearchQueries.json` `searchTime` sonunda `Z[UTC]` biçimi HAFIZA.

### Tarayıcı geçmişi
- Kod okundu: purarue/browserexport (MIT) `chrome.py`, `firefox.py`, `safari.py`; browser-history (Apache-2.0) `browsers.py`.
  - Chromium: `urls`+`visits`, `visit_time` 1601'den µs; Firefox: `moz_places`+`moz_historyvisits`, `visit_date` µs (çok eski: ms); Safari:
    `history_items`+`history_visits`, `visit_time` 2001'den saniye.
  - Windows profil yolları: Chrome `AppData/Local/Google/Chrome/User Data`, Edge `Microsoft/Edge/User Data`, Brave, Vivaldi
    `Local/Vivaldi/User Data`, Opera `AppData/Roaming/Opera Software/Opera Stable` (History doğrudan), Opera GX, Firefox
    `AppData/Roaming/Mozilla/Firefox/Profiles`.
- Değişiklik: Firefox ms/µs ayrımı, Vivaldi ve Opera yolları, Safari için anlaşılır ret. Edge/Chrome şeması aynı olduğundan ek iş yok.
- Açık: Windows'ta açık tarayıcının kilitli dosyası gerçek makinede denenmedi (`copy_snapshot` yalnız sahte kilitle sınandı).

### Bilgisayar dosyaları
- Bir dışa aktarma biçimi yok (kullanıcının klasörü taranır). Kaynak gerekmedi. Bozuk/boş PDF, DOCX, JPEG ve ikili metin dosyalarıyla
  çökmediği test edildi.

### Genel sohbet dosyası (DeepSeek vb.)
- Resmî dışa aktarma bulunamadı (önceki oturum notu geçerli). Kendi biçimimiz; değişiklik: yarım JSON çökmesi giderildi.

## 3. Genel teknik bulgular
- UTF-8 BOM: tüm JSON akışlarında `strip_bom` (artık CESU-8 onarımlı), CSV'de `utf-8-sig`, `peek` BOM'u atıyor. Test: `test_takeout.py`,
  `test_gercekci.py`.
- Meta mojibake: `fix_tree` yalnız latin-1 aralığındaki ve geri çevrilebilen metne dokunuyor; gerçek Türkçe/emoji metin bozulmuyor (test).
- Tarih: ISO (kesirli/kesirsiz, `Z`, `+03:00`), Unix s/ms/µs, Chrome 1601 µs, Reddit `… UTC`, Spotify `YYYY-MM-DD HH:MM`, Java `Z[UTC]`.
- Büyük dosya: akışla okuma `test_dayaniklilik.py` içinde bellek tepe değerinin dosya büyüklüğüyle büyümediği ölçülerek sınandı
  (JSON ~15 MB'a kadar, CSV, MBOX); GB ölçeği için `pytest -m buyuk` testleri duruyor, bu turda çalıştırılmadı.

## 4. Tanılama aracı: `kimlikmerkezi tanila <yol>`
Kullanıcı dışa aktarma dosyasında/klasöründe çalıştırır, çıkan kısa metni geliştiriciye yapıştırır. İçerik yazmaz; ağa bağlanmaz.
- Çıktı: hangi içe aktarıcının tanıdığı (ad, güven), biçim denetimi sonucu, dosya yapısı (uzantı sayıları), her dosya grubu için kayıt sayısı, alan
  ağacı (tür, uzunluk aralığı, sayıların hane sayısı: saniye/ms/µs benzeri, tarih ÖRÜNTÜSÜ `9999-99-99T99:99:99Z`), beklenen şekil bulundu/eksik alan.
- Gizlilik kuralları: değerler hiç yazılmaz; dosya/klasör adları ve bilinmeyen alan adları varsayılan olarak yalnız şekle (a/A/9) indirgenir,
  yalnız bilinen dışa aktarma adları açık kalır. Yeni ya da yerelleşmiş adlar gerekirse `--adlari-goster` (adlar kişi adı/veri taşıyabilir;
  kullanıcı bilerek seçer, paylaşmadan önce bakmalı). `--ayrinti` daha uzun çıktı verir.
- Sınama: `tests/test_tanila.py` iki sentinelle (yalnız değerlerde, yalnız adlarda) JSON, JSONL, CSV, MBOX, SQLite, düz metin, zip, tar.gz üzerinde
  sızıntı olmadığını gösterir; ağ çağrıları engellenip çalıştırılır; kaynakta ağ modülü bulunmadığı denetlenir. **Bu sahte veriyle yapılan
  bir kanıttır**; gerçek bir dışa aktarmada veri taşıyan olağandışı bir yapının sızmayacağına dair garanti değildir.
- Kurulu Windows paketinde iki yol: (1) arayüzde İçe aktar > "Dosyayı denetle (içerik göstermez)" düğmesi (rapor ekranda, "Kopyala" ile); (2) konsolda
  `kimlikmerkezi-mcp.exe tanila <yol> [--adlari-goster] [--ayrinti]`. İkisi de aynı `tanila` kodunu çağırır, veritabanına yazmaz.
  Paket CI'sı (`windows/paket/kurulu_dene.py`) kurulu exe'de sahte örnekle sentinel sızıntısını ve çıkış kodunu sınar; ilk gerçek Windows CI koşusuna kadar bu adım ÇALIŞTIRILMAMIŞTIR.
