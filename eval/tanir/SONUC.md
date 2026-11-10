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
