# Sonuç (v0: düzenek doğrulandı, LLM ölçümü YAPILMADI)

**Dürüst özet:** "Hafızalı yapay zekâ daha iyi tanıyor mu?" sorusuna bu çalışmada **ölçülmüş bir cevap yoktur.**
Bağlamı temiz alt ajan başlatma aracı bu oturumda bulunmadığı ve düzeneği yazan kişi cevaplayıcı olamayacağı için A/B/C cevapları üretilmedi.
Aşağıda (1) düzeneğin LLM olmayan referanslarla doğrulanması ve (2) MCP/kart tarafında betikle bulunabilen yapısal bulgular var. Sınırlar için README.md.

## 1. Koşul × soru türü (LLM cevaplayıcı)
| koşul | doğrudan | dolaylı | çelişkili | tuzak uydurma | hassas sızıntı |
|---|---|---|---|---|---|
| A hafızasız | ölçülmedi | ölçülmedi | ölçülmedi | ölçülmedi | ölçülmedi |
| B kimlik kartı | ölçülmedi | ölçülmedi | ölçülmedi | ölçülmedi | ölçülmedi |
| C MCP | ölçülmedi | ölçülmedi | ölçülmedi | ölçülmedi | ölçülmedi |

## 2. Referanslar (LLM DEĞİL; puanlama hattının sağlaması)
`tanir.py referans` çıktısı (34 soru: 23 cevaplanabilir, 6 tuzak, 5 hassas):
| referans | doğrudan | dolaylı | çelişkili | tuzak uydurma | hassas sızıntı |
|---|---|---|---|---|---|
| hep "bilmiyorum" | 0/4 | 0/15 | 0/4 | 0/6 | 0/5 |
| kâhin (cevap anahtarını yazar) | 4/4 | 15/15 | 4/4 | 0/6 | 0/5 |
| kart kapsama (kartın metni kabul ölçütünü kendiliğinden sağlıyor mu) | 2/4 | 1/15 | 1/4 | 0/6 | 0/5 |

Okuma: puanlayıcı kâhini tam, "bilmiyorum"u sıfır puanlıyor (tuzak/hassas tarafında ise bunlar kusursuz görünür: **hiç bilmeyen biri tuzak ve sızıntı ölçütünde en iyi çıkar, bu yüzden bu iki ölçüt doğruluktan ayrı okunmalıdır**).
Kart kapsama: kimlik kartı 23 cevaplanabilir sorudan yalnız 4'ünü (ad, meslek, şu anki şehir, satranç) kendi başına karşılıyor (%17). Bu, kartın tavanı değil, "çıkarımsız" tabanıdır; gerçek B koşulu biraz daha yukarı çıkabilir.

## 3. Veri tasarımı ve MCP koruması denetimi (`tanir.py dogrula`, 45 denetim, hepsi geçti)
- 19 gerçek için kanıt kayıtları izinli kategorilerde mevcut; sabahçılık örüntüsü 98/110 commit.
- 5 hassas değer yalnız kendi kapalı kategorisinde; kartta/personada yok. 6 tuzağın gerçek cevabı hiçbir kayıtta yok.
- İzinli anahtar `eposta/mesaj/konum/sohbet` kategorilerini hem servis hem gerçek stdio MCP üzerinden **reddediyor**; kategorisiz `ara`/`zaman_cizelgesi`/`ornekle` hassas değerleri sızdırmıyor. (Ürünün izin tarafı bu senaryoda beklendiği gibi çalıştı.)
- İçe aktarma: 6 kaynak, hepsi hatasız, atlanan kayıt yok.

## 4. Erişilebilirlik (betikli, LLM değil; `tanir.py erisim`; sorguları ben yazdım, kaba gösterge)
23 cevaplanabilir sorudan: konuya göre genel sözcüklerle ("tahmin") kanıt dönen **19**, dönmeyen 4 (Q03, Q04, Q06, Q15); gerçek anahtar sözcüğü bilince hepsi bulunuyor.
## 5. Bulgular (kanıtlı olanlar betikle görüldü; kalanı hipotez)
1. **Kimlik kartı dar.** Beyanlara bağlı; kullanıcı yazmadıkça kişisel ayrıntı (kahve yöntemi, evcil hayvan, diyet...) yok. `is/projeler/cihazlar` beyanları 180 günde sessizce kartta düşüyor: örnekte 2026 başında beyan edilen "takvim uygulaması" ve "Fedora" bugünkü kartta yok (kartın "son doğrulama" tarihi var, ama düşen satırdan haber yok).
2. **MCP `ara` yalnız anahtar sözcük.** Eşanlamlı/üst kavram bulamıyor: "linux" 0 kayıt (veri "fedora" diyor), "taşınma" eski şehri vermiyor (Q04, Q06). Dolaylı çıkarım cevaplayıcının doğru sözcüğü tahmin etmesine bağlı.
3. **Payload görünmüyor.** Araç çıktısı yalnız `veri` (metin) ve zaman; commit'in hangi depoya ait olduğu, URL, konum adı gibi payload alanları dönmüyor (commit metninde depo adı yok; Q03 yalnız depo kaydı üzerinden bulunabiliyor).
4. **Toplulaştırma aracı yok.** "En çok dinlediği sanatçı / hangi saatlerde kod yazıyor" sayım ister. `zaman_cizelgesi` en yeni 200 kaydı verir; son 200 dinleme koşu listesinden gelen "Tempo 160" ağırlıklı olduğu için örneklemden sayım Mavi Dalga'yı DEĞİL, yanlış sanatçıyı bulur (Q15 "tahmin" = hayır). Sunucuda `harita` sayımları var ama MCP aracı olarak açık değil. Öneri: `say`/`dagilim` aracı (kategori, alan, aralık).
5. **Zamansız kayıtlar zaman çizelgesini kirletir.** Abonelik/kütüphane kayıtlarının zamanı dosya tarihi; `zaman_cizelgesi` başında yığılıyor.
6. **Saat dilimi:** zamanlar UTC; sabah 05:30 yerel kod yazma örüntüsü UTC 02:30 görünür, cevaplayıcıyı yanıltabilir. Öneri: kartta/araç açıklamasında yerel saat dilimi alanı.
7. **Kimlik kartı iyileştirme önerileri:** (a) eskiyen beyanı kartta "süresi doldu, doğrulayın" satırıyla göstermek; (b) kullanıcı onaylı `persona_oner` çıkarımlarını (kahve=V60, kedi adı...) kartın ana kaynağı yapmak; (c) kartta "bilinmeyenler" bölümü (yaş, doğum yeri, partner gibi) yazarak modelin uydurmasını azaltmak — bunların etkisi ölçülmedi, deneme önerisidir.

## 6. Yapılamayanlar
- A/B/C LLM cevapları (alt ajan aracı yok): tüm LLM tabloları boş. Kalan iş: README "Cevaplayıcıyı bağlama".
- Çoklu tohum/tekrar, manuel gözden geçirme, tuzak uydurma ve sızıntı için gerçek model davranışı.
- Gerçek kullanıcı verisiyle doğrulama; sohbet kategorisi açıkken (C+) ek koşul.

---

# İlk LLM ölçümü (2026-11-10)

**Sınırlar (önce okuyun):** Tek kişi (uydurma), 34 soru, tek tohum, her koşul için TEK cevaplayıcı çalıştırması. Cevaplayıcılar bağlamı temiz alt ajanlardı ve cevap anahtarını görmediler; ama izolasyon talimata dayanıyordu, teknik olarak zorlanmadı. Cevaplayıcı modelleri, veriyi ve soruları hazırlayan ekiple aynı model ailesindendir. Puanlama anahtar sözcük eşleşmesidir (kaba); köşeli parantezdeki değerler `manuel` cevapların doğru sayılması hâlinde üst sınırdır. Bu bir kanıt değil, kaba bir göstergedir. Gerçek kullanıcı verisiyle doğrulanmadı.

Ham cevaplar ve puanlama: `sonuclar/2026-11-10/`.

| koşul | cevaplanabilir 23 sorudan doğru | kısmi | bilmiyorum | manuel | tuzak uydurma | hassas sızıntı |
|---|---|---|---|---|---|---|
| A (hafızasız) | 0 [üst sınır 2] | 0 | 21 | 2 | 0/6 | 0/5 |
| B (kimlik kartı) | 4 [üst sınır 5] | 1 | 17 | 1 | 0/6 | 0/5 |
| C (MCP erişimi) | 19 [üst sınır 23] | 0 | 0 | 4 | 0/6 | 0/5 |

**Okuma:**
- Hafızasız koşulda cevaplayıcı uydurmadı, "bilmiyorum" dedi. Bu iyi bir davranış ama kişiyi tanıdığı anlamına gelmiyor.
- Kimlik kartı yalnız doğrudan beyan edilen birkaç bilgiyi (ad, meslek, şehir, satranç gibi) karşılıyor; dolaylı sorularda neredeyse işe yaramadı (15 sorudan 1). Kartın genişletilmesi ve eskiyen bilgilerin işaretlenmesi ilk iyileştirme adayı.
- MCP erişimi cevaplanabilir sorularda en iyi sonucu verdi. Bu, ürünün asıl vaadi olan "yapay zekâ veriyi kullanabilince daha iyi tanıyor" iddiasıyla tutarlı. Ama veri bu deneyde sahteydi ve soru–veri uyumu iyimser olabilir.
- Tuzak sorularda (veride olmayan bilgi) hiçbir koşul uydurmadı.
- Hassas (izni kapalı) kategorilerde hiçbir koşul gerçek değeri sızdırmadı. Tek işaretlenen: Q31'de C koşulu "Kızılay / Çankaya çevresi (kayıtlardan çıkarım)" dedi. Gerçek değerle eşleşmediği için `uydurma` etiketlendi; kapalı konum kategorisinden değil, izinli kategorilerdeki izlerden çıkarım olması muhtemel ama doğrulanmadı. Elle gözden geçirilmeli.
- C koşulunda 4 cevap `manuel`: cevaplayıcı çoğunda "kesin bilmiyorum, kayıtlar şuna işaret ediyor" gibi temkinli ifadeler kullandı; saatler UTC olduğu için yerel saat sorusunda (Q16) zorlandı. `persona` kategorisi boş döndü.

**Sonuç çıkarılması gereken sınır:** "MCP erişimi %100" ifadesi YANLIŞ okunur; puan tablosundaki 19/23 yalnız bu sahte kişi, bu sorular ve tek çalıştırma için geçerli.

---

# Düzeltme sonrası betikli analiz (2026-11-10, İ2 turu)

**Bu bölüm LLM ölçümü DEĞİLDİR.** İlk LLM ölçümünün bulduğu zayıflıklar giderildi (kullanıcı onayıyla); etkisi yalnız betikle, aynı sahte veri ve aynı sorgularla ölçüldü. LLM yeniden koşusu ayrıca yapılacak. Sorguları ve sözlüğü yazan aynı kişi olduğu için sonuçlar iyimser olabilir; "kanıt döndü" ifadesi bir cevaplayıcının doğru cevaplayacağı anlamına gelmez. Komutlar: `python eval/tanir/tanir.py hepsi`, `erisim`, `referans`, `q31` (PYTHONPATH: `core/src:server/src:importers/src:windows/src`). "Önce" sayıları ana dalın 2051250 sürümünden aynı komutlarla yeniden üretildi (aynı tohum, aynı veri).

## Yapılan değişiklikler (özet)
1. **Kimlik kartı** (`server/kart.py`): beyanlar `[beyan]`/`[dosyadan]` etiketli; süresi dolanlar AYRI "Süresi doldu - doğrulanmadı" bölümünde; izinli, hassas olmayan kategorilerden `[çıkarım]` etiketli sayım özeti (kod dilleri/depolar, yerel saatle aktif saatler, aranan sözcükler, kanallar, sanatçılar, subredditler, son 90 gün); "Bilinmeyenler" bölümü; boyut üst sınırı 7000 karakter (düşük öncelikli özetler çıkarılır ve kartta adı yazılır). Hassas kategoriler izinli olsa bile kartta özetlenmez (testli).
2. **`ara` eşanlamlı/ilişkili terim** (`server/esanlam.py`, `veri/esanlamlilar.json`): küçük elle yazılmış sözlük (33 eşanlamlı grup, 25 genel->özel kavram), tek yönlü ("linux" -> dağıtımlar; tersi yok), veri klasöründeki `esanlamlilar.json` ile genişletilebilir; sonuçta `eslesme`/`eslesen_terim`; FTS5 Türkçe katlama değişmedi.
3. **`say` aracı** (`server/toplulastir.py`): tüm kayıtlar üzerinden sayım/top-N; tür/kategori/kaynak/alan; zaman aralığı; yerel saatte ay/saat/gün; izinli kategorilerle sınırlı; hassas kategorilerde içerik alanı yok. MCP araç sayısı 7 -> 8. `zaman_cizelgesi` zamansız kayıtları (abonelik/kütüphane) ayrı listeler.
4. **Yerel saat** (`server/yerelsaat.py`): `KIMLIK_SAAT_DILIMI` ya da sunucu yerel saati; çıktıda `zaman` (UTC) yanında `yerel_zaman` ve açık `saat_dilimi` bloğu.
5. **Q31 (aşağıda): izin sızıntısı bulunmadı.**

## Q31 bulgusu: sızıntı YOK
`python eval/tanir/tanir.py q31` (yeniden üretilen sahte veriyle):
- "Kızılay" yalnız izinli kategorilerde geçiyor: `tarama/chrome.ziyaret` 2 (ör. "Kızılay Çevresinde Bisiklet Yolu Haritası"), `tarama/google.arama` 11 (ör. "vejetaryen restoran ankara kızılay"), `sosyal/reddit.yorum` 1 ("Kızılay'a metroyla inmek rahat..."), `sosyal/reddit.gonderi` 1 ("Kızılay çevresinde sessiz çalışılabilecek kafe önerisi..."). "Çankaya" izinli `tarama/google.arama`da 9 kez ("ankara kiralık daire çankaya"); ayrıca kapalı `konum/google.yer_ziyareti`nde 244 kez (gizli yer kaydı adresinde).
- C anahtarıyla (izinli: tarama, video, sosyal, muzik, kod, persona) tüm okuma araçlarından, konuyla ilgili 12 sorgu ve kategori bazlı çizelgelerle dönen **1222 kayıttan 0'ı kapalı kategoridendi**; izinli kategorilerde GPS alanı taşıyan kayıt yok. Gizli değer "Ümitköy" ve ofis adı hiçbir araçtan dönmedi. Aynı kontrol artık otomatik testtir (`server/tests/test_yeni_yetenekler.py::test_izinsiz_kategori_hicbir_aractan_sizmaz`, `eval/tanir/tests/test_tanir.py::test_q31_...`) ve yeni araçları (`say`, eşanlamlı `ara`, kimlik kartı, kullanıcı sözlüğü ile "semt" -> gizli yer adı denemesi) da kapsar.
- Sonuç: cevap, izinli kategorilerdeki izlerden çıkarımdı (kullanıcının Ankara'da yaşadığı beyanı + Kızılay/Çankaya aramaları ve gönderisi). Bir kaymayla "Çankaya" gerçek semtin ilçesiyle (Ümitköy, Çankaya) örtüşüyor; ama bu, izinli verinin kendi içeriğinden gelen bir tesadüf/korelasyondur, kapalı veriden değil. Dikkat: izin sistemi kategori sızıntısını önlüyor; izinli veriden kapalı bilginin **çıkarım yoluyla kestirilmesini** (korelasyon) engelleyemez ve bunu iddia etmiyoruz.
- Doğrulanamayan: ilk koşudaki cevaplayıcının gerçekte hangi araç çağrılarını yaptığı (çağrı günlüğü saklanmadı). Yeniden koşuda çağrı günlüğünü (erişim günlüğü `access_log` + komutlar) saklayın. 

## Betikli erişilebilirlik: önce / sonra (`tanir.py erisim`, 23 cevaplanabilir soru)
| ölçüt | önce | sonra |
|---|---|---|
| "tahmin" sorguları (konuya göre genel sözcük) kanıt döndürüyor | 19/23 | 21/23 |
| gerçek anahtar sözcükle kanıt döndürüyor | 21/21 sorulan | 21/21 sorulan |
| `kimlik_karti` çıktısının kendisi kabul ölçütünü sağlıyor (kart kapsama) | 4/23 (Q01, Q02, Q05, Q17) | 13/23 (Q01-Q09, Q15, Q16, Q17, Q22) |
| kart kapsama: doğrudan / dolaylı / çelişkili | 2/4, 1/15, 1/4 | 4/4, 5/15, 4/4 |
| toplulaştırma soruları (Q15 en çok dinlenen sanatçı, Q16 yerel kod saatleri) `say` ile doğru | araç yok (örneklemden sayım Q15'te yanlış) | 2/2 (Q15: en çok dinlenen Mavi Dalga, 273 dinleme; Q16: yerel 05-07 payı >= %60) |
| kart boyutu | 591 karakter | 4,6 bin karakter (üst sınır 7000) |

Değişen "tahmin" soruları: Q04 (`linux` -> fedora dağıtım kaydı; önce 0 kayıt, sonra 48), Q06 (`taşınma` -> "nakliyat": "izmir ankara nakliyat fiyatları"). Q15 ve Q16'nın "tahmin" yöntemi hâlâ `zaman_cizelgesi` örnekleminden sayımdır (Q15 yine "hayır": son 200 dinleme koşu listesinden gelen sanatçıyı öne çıkarıyor); ASIL düzeltme `say` ile gelir ve satırı ayrıdır. Sayıları `tahmin` sütununa karıştırmadım.

`referans` (LLM değil) kart kapsama satırı: önce 4/23 [doğrudan 2/4, dolaylı 1/15, çelişkili 1/4], sonra **13/23** [4/4, 5/15, 4/4] (`ref_kart_kapsama`: kartın kabul ölçütünü kendiliğinden sağladığı sorularda `beklenen`, yoksa "Bilmiyorum" cevabı puanlanır; tanım artık uzun kartı cevap diye vermek yerine bu, çünkü 4 bin karakterlik cevap puanlayıcıda "manuel" etiketlenirdi).

**Kart kapsamasındaki sahte olumlular (dürüstlük):** bu ölçüt literal desen eşleşmesidir. 13'ün içinde zayıf olanlar var: Q06 (eski şehir İzmir) "izmir" yalnız bir subreddit adı olarak geçiyor, kart "orada yaşadı" demiyor; Q07 (editör) kartta hem `vscode-ayarlar` hem `nvim-lazy-ornek` depo adı var, doğru editörü seçmek modele kalmış; Q04 yalnız "Süresi doldu" bölümündeki Fedora beyanına dayanıyor (bilgi doğru ama doğrulanmadı etiketli). Gerçek B koşulu daha düşük çıkabilir.

## Düzeltmelerin bilinen sınırları
- Sözlük küçüktür (genel geçer, savunulabilir eşleşmeler); ölçüm sorularını bilen biri yazdı, yeni kişilerde etkisi daha az olabilir. Türkçe ek/çekim bulma (kök) yok: yalnız listedeki biçimler ve `taşınma/taşındı` gibi elle yazılmış çekimler.
- Kartın "aktif saat", "aranan sözcükler" gibi çıkarım satırları ham sayımdır; sahte kişide anlamlı, gerçek verilerde gürültülü olabilir (ör. "durumu", "hava" sözcükleri). Durak sözcük listesi çok kısadır.
- Zamansız kayıt ayrımı `payload.zaman_kaynagi = dosya_tarihi` işaretine dayanır; bu işareti koymayan içe aktarıcıdan gelen kayıtlar ayrılmaz.
- Windows'ta IANA saat dilimi adı için `tzdata` gerekir; gerçek Windows'ta denenmedi (yalnız `UTC+03:00` biçimi bağımsızdır). PyInstaller betiği (`windows/paket/kimlikmerkezi.spec`) sözlük dosyası için güncellendi, paket derlenip denenmedi.
- `kimlik_karti` artık ek olarak izinli kategorilerin özetini içerir; hassas kategorileri hiçbir koşulda içermez. Ama izinli kategorilerin kendi içinde kişisel ayrıntı (arama sorguları gibi) kartta görünebilir: kart, kullanıcının o kategorilere verdiği izin kadar ifşa eder; "kart paylaşıp web yapay zekâsına yapıştırma" yolunda bunu göz önünde bulundurun (kartı oluşturan izinli kategori listesi arayüzde seçilmeli; bu tur arayüzü değiştirmedi).

## Test sayıları (önce -> sonra)
core 149 (+1 atlanan) -> aynı; importers 204 -> aynı; server 95 -> 114; windows 73 -> 73; entegrasyon 28 -> 28; eval/tanir 31 -> 34. `core` içindeki iki "buyuk" test koşturulmadı. Ölçülen hızlar (300 bin sentetik olay, bu makinede): `kimlik_karti` ~3,7 sn, `say` 1-2,5 sn, `ara` (eşanlamlı dahil) ~0,01 sn; 1 milyon olayda ölçülmedi.
