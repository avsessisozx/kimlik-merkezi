# Doğrulama durumu (içe aktarıcılar)

Güncelleme: 2026-11-10. Kural: sahte veriyle geçen test **"kısmen doğrulandı"**dır; "doğrulandı" yalnız kullanıcının gerçek
dışa aktarmasıyla geçince yazılır. Şu an **hiçbir kaynak için gerçek veriyle doğrulama yok**.

Durum sütunu:
- **Sahte gerçeğe-yakın veriyle geçti**: `fixtures/gercekci/` ve eski `fixtures/` dosyalarıyla; biçim BICIM-DENETIMI.md'deki kaynağa göre kurulmuş.
- **Gerçek veriyle doğrulanmadı**: her satırda geçerli.

Kaynak kalitesi: **K** = açık kaynak ayrıştırıcının kodu/şeması okundu; **A** = yalnız web arama özeti; **H** = hafıza (kaynaksız).

| İçe aktarıcı | Kapsadığı kaynaklar | Durum | Biçim kaynağı | Özellikle doğrulanmayanlar |
|---|---|---|---|---|
| `google_takeout` (etkinlik) | Arama, YouTube izleme/arama geçmişi, My Activity | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | K | Türkçe klasör adları (varsayım); tüm ürün klasörleri |
| `google_takeout` (Chrome) | `History.json` / `BrowserHistory.json` | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | K | hangisinin güncel olduğu |
| `google_takeout` (konum) | `Records.json`, aylık Semantic Location History | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | K (şema) | Türkçe ay adlı dosya adları; çok büyük `Records.json` ölçeği (GB) |
| `google_takeout` (konum, yeni) | cihaz içi `Timeline.json` (`semanticSegments`) | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | A (topluluk) | alan adları topluluk özetinden; Takeout'ta hiç gelmeyebilir |
| `google_takeout` (YouTube) | abonelik CSV'si, `likes.json` | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | K (likes), H (CSV başlıkları) | yerel dildeki CSV başlıkları |
| `google_takeout` (Gemini) | My Activity / Gemini Apps | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | A | Türkçe istem öneki; ekli dosya/görsel alanları |
| `google_takeout` (Gmail) | MBOX | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | H | etiket tırnaklaması; çok büyük (GB) dosya (yalnız sentetik 1 GiB testi, çalıştırılmadı) |
| `meta` | Instagram / Facebook JSON | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | K (Facebook zaman alanları), A/H (Instagram şekilleri) | `saved_*`/yorum şekilleri; gönderi/hikâye dosya adları; mojibake'nin Instagram'da da aynı olduğu |
| `reddit` | hesap veri isteği CSV'leri | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | H (kaynak bulunamadı) | **tüm sütun adları**, `messages_archive.csv`, tarih biçimi |
| `github` | hesap verisi arşivi (tar.gz) | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | H | dosya adları, her kayıtta `type` alanı, iç içe nesne şekilleri |
| `spotify` | standart + genişletilmiş akış geçmişi, liste, kütüphane, arama | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | K (Playlist), A (genişletilmiş), H (diğer) | `ip_addr` / `ip_addr_decrypted`, video dosyası alanları, `searchTime` biçimi |
| `browser_history` | Chrome/Edge/Brave/Vivaldi/Opera, Firefox yerel geçmişi | Sahte gerçeğe-yakın veriyle geçti (sahte SQLite); gerçek veriyle doğrulanmadı | K | Windows'ta kilitli/açık tarayıcı dosyası; gerçek şema sürümleri; Safari desteklenmiyor |
| `computer_files` | yerel klasör taraması | Sahte gerçeğe-yakın veriyle geçti (sentetik klasör); gerçek veriyle doğrulanmadı | (dışa aktarma biçimi yok) | gerçek fotoğraf/video/PDF çeşitliliği; çok büyük klasör ölçeği |
| `chatgpt` | `conversations.json` / `conversations-NNN.json` | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | K | tüm `content_type` çeşitleri; ekler/görseller alınmıyor; resmî alan listesi görülmedi |
| `claude` | claude.ai `conversations.json` | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | K | resmî dışa aktarma sayfası görülmedi; araç/düşünce blokları atlanıyor |
| `chat_file` | elle hazırlanmış / DeepSeek vb. sohbet dosyaları | Sahte gerçeğe-yakın veriyle geçti; gerçek veriyle doğrulanmadı | (kendi biçimimiz; resmî dışa aktarma yok) | gerçek bir DeepSeek dışa aktarması |

## Tanılama aracı (`kimlikmerkezi tanila`)
- Sahte veriyle: iki sentinel testi geçti (değerler hiçbir modda, adlar varsayılan modda sızmıyor); ağ çağrısı yok.
- **Gerçek bir dışa aktarmada denenmedi.** Sızıntı garantisi verilmez; kullanıcı raporu yapıştırmadan önce okumalıdır.

## Bu turda bulunan ve düzeltilen gerçek hatalar (hepsi sahte veriyle)
1. Meta: `string_map_data` taşıyan kayıtlar üst anahtara göre yanlış şekille okunup sessizce atlanıyordu.
2. Takeout: konum dosyaları ve `likes.json` tanınmıyordu / yanlış etiketleniyordu.
3. Genel sohbet: yarım tek-nesne JSON `JSONDecodeError` ile çöküyordu.
4. Tüm JSON içe aktarıcılar: CESU-8 emoji içeren dosya bütün içe aktarmayı düşürürdü.
5. ChatGPT: araç çağrıları ve düşünme ara notları kullanıcı mesajı gibi alınıyor, sesli sohbet dökümü kayboluyordu.

## Sıradaki adım (kullanıcıda)
Gerçek Takeout, Reddit, Instagram/Facebook, Spotify, GitHub, ChatGPT ve Claude dışa aktarmalarında
`kimlikmerkezi tanila <yol>` çalıştırıp çıktıyı yapıştırmak; bu tablodaki "doğrulanmadı" satırlarını gerçek biçime göre kapatır.
