# durum/server.md — İ2 (Persona ve Erişim), 2026-11-10

Dal: iscilik/server (push edildi). Paket: server/src/kimlikserver. Testler: 41 geçti (genel Hub API'sine geçişten sonra da: `cd server && pytest tests` ve repo kökünden `pytest server`)
(`cd server && python -m pytest tests`, 3 ardışık çalıştırmada aynı, ~7,5 sn; Linux, Python 3.13.18, mcp 2.3.0).

## Yapıldı
- persona.py: add_fact, add_fact_from_source, update/delete, check_expiry (saat enjekte, varsayılan 180 gün, kategori bazında), çelişki (ikisi saklanır), resolve_contradiction, export_identity_card.
- access.py: KeyManager (anahtar üretimi: `kim_`+32 bayt hex, yalnız hash; iptal; izin, süreli; hassas için confirmed_sensitive; grant_all_non_sensitive hassasları atlar), Authorizer (her çağrıda yeniden okur), AccessLog (erisim.db, `connect_erisim`; yazılamazsa AccessLogError).
- service.py: MCP'den bağımsız iş mantığı; ret/hata da kayda girer, ok kaydı yazılamazsa veri dönmez.
- mcp/: ince adaptör (`mcp.server.mcpserver.MCPServer`, 5 araç, salt okunur); giriş `python -m kimlikserver.mcp`.
- `python -m kimlikserver --veri DIR anahtar-uret|anahtar-iptal|liste` (kabuk gelene kadar anahtar üretmek için; yazan süreç olarak çalışır).
- docs/BAGLANTI.md.

## Kararlar / varsayımlar (Müdür onaylasın)
- Çelişkide eski bilgi `eskimis` olur (yapay zekâya verilmez), yeni canlı kalır; yalnız `fact_key` verilirse çelişki aranır. Aynı metin yeniden eklenirse yeni satır açılmaz, süre tazelenir.
- Kaynağı `remove_source` ile kaldırılmış `dosyadan_alinan` bilgi kartta/MCP'de görünmez.
- MCP kayıtlarında yalnız `text` döner, `payload` dönmez (GPS/serbest metin sızmasın). Savunma: konum izni yokken payload'ında gps/lat/lon vb. anahtar olan, konum olmayan kategorideki kayıt da dönmez (sezgisel).
- `kimlik_karti` çıktısı düz metin yerine `{etiket:"veri", veri_uyarisi, veri:<markdown>}` sarmalı.
- `persona_getir` ve `kimlik_karti` için `persona` kategorisi izni gerekir.
- Hub her çağrıda `mode=ro` açılıp kapanır (önbellek yok).

## Test çıktı özeti (hepsi çalıştırıldı)
persona 14, access/service 17, gerçek stdio (resmî `mcp.Client` ile süreç başlatarak) 10. Kapsam: izinsiz kategori reddi; anahtar iptali sonrası kesilme (süreç içi ve çalışan MCP sürecinde); her istek kayıtta; erisim.db yazılamazsa ret (tablo yok / dosya yerine klasör / enjekte hata); tombstone ve kaynak kaldırma; konum izinsizken konum ve GPS'li kayıt yok; WAL yan dosyaları yokken yanıt; yazan süreç açılıp 30 kayıt yazarken ve kapanırken MCP sorgusu; 3 ayrı MCP süreci x 25 çağrı = 75 kayıt eksiksiz, ayrıca 6 süreç x 100 doğrudan yazım = 600; süresi dolan izin (bitiş anı dahil); araç listesi/şema/açıklamalar; anahtarsız çağrı.
- "Önceki talimatları unut" testi: sahte kaydın yalnız `kayitlar[*].veri` içinde ve `etiket:"veri"` ile döndüğünü, başka hiçbir alanda geçmediğini doğrular. Bu YALNIZ çıktı biçimini doğrular; modelin talimata kanmayacağını KANITLAMAZ.

## Doğrulandı / doğrulanmadı
- Doğrulandı: mcp 2.3.0 PyPI'daki en yeni sürüm (pip index, 2026-11-10); 2.x API (`MCPServer`, `ToolError`, `Client`, `StdioServerParameters`) kurulu paketin kaynağından okundu ve test edildi. Claude Code `claude mcp add` sözdizimi code.claude.com/docs/en/mcp'den.
- Doğrulanmadı: Claude Desktop ayar dosyası yolu ve menü adı (modelcontextprotocol.io bu oturumda erişilemedi, support.claude.com sayfası dosyayı anmıyor); DeepSeek masaüstü uygulaması (ad bilinmiyor, resmî belge bulunamadı); gerçek Claude Desktop/Claude Code/DeepSeek ile bağlantı; Windows'ta çalışma (testler yalnız Linux'ta); Windows'ta WAL yan dosyası davranışı.
- Test edilmeyen: ro bağlantının WAL yan dosyası bırakıp bırakmadığı garanti edilmedi (testte yan dosya yokken açıldığı gösterildi).

## Müdüre istekler
1. Karar C onayı (mcp==2.3.0 sabit; server/pyproject.toml'da).
2. (Kapandı, 2026-11-10) Özel `Hub._conn/_tx/_mutex` kullanımı kaldırıldı; server artık main'deki `Hub.transaction()/query()/query_one()` kullanıyor (main birleştirildi). `_db.py` yalnız zaman yardımcılarını içerir.
3. Claude Desktop yapılandırma yolu/menüsünün resmî belgeden doğrulanması (ağ izni: modelcontextprotocol.io) ve DeepSeek uygulama adının kullanıcıdan alınması; GOREV 13'e "DeepSeek'te MCP bağlantısını kendi cihazında doğrula" eklenmeli.
4. Kök pyproject testpaths `server` içeriyor; CI'de `pip install -e core -e server` gerekir.
5. Başlatma girişi kabuk kararından sonra güncellenecek (BAGLANTI.md ve INTERFACES §10).

## Kalan / v0.2.0
Aktarım (server/aktarim) ve REST yazılmadı. Windows "Claude'a ekle" düğmesi İ5.

## Devam noktası
v0.1.0 İ2 kapsamı tamam; sıradaki: Müdür incelemesi, Claude Desktop yolunun doğrulanması.

## Persona Haritası (INTERFACES §12) — 2026-11-10, dal iscilik/harita
- Modül: server/src/kimlikserver/harita.py (`harita()`, `bolge()`), testler server/tests/test_harita.py (13 test; tüm server paketi 54 test geçti). Örnek çıktı: durum/harita-ornek.json (importers fixtures + elle persona; hassas kilitli ve açık varyantlar).
- Alan eşlemesi importers kodundan okundu: tarama (chrome.ziyaret payload.url -> alan adı; google.arama payload.baslik, yalnız İngilizce "Searched for " öneki atılır, Türkçe önek varsayımı yok), video (youtube.izleme payload.alt_baslik[0] = kanal), sosyal (payload.subreddit; yalnız gönderi/yorum), uygulama (payload.urun). Muzik, kod, dosyalar, notlar için içe aktarıcı yok: o bölgeler yalnız sayı/zaman gösterir, notlar'a "bu alan yok" yazılır. Uygulama için süre alanı yok, yazıldı.
- Tarihi olmayan kayıtlar (payload.zaman_kaynagi=dosya_tarihi) zaman grafiklerine ve ilk/son tarihe girmez (notlar'da belirtilir).
- Hassas bölge kilitliyken yalnız `kilitli:true`, `ozet:"Kilitli"`, sayı/tarih None; profil.olay kilitli kategorileri içermez. Açıkken yalnız sayı ve zaman/tür dağılımı; yer adı, URL, metin, koordinat dönmez (testle doğrulandı). `ac_hassas` hem bölge id (kalp/karin/ayak) hem kategori adı (mesaj/eposta/konum/medya_meta) kabul eder.
- Sözleşmeye eklenen küçük ekler (Müdür onaylasın): en_cok satırında `grup` alanı (arama terimi/site/kanal/subreddit/uygulama); harita çıktısında `not`; `bolge(..., utc_kaydirma=3)` (İstanbul için saat/gün grafikleri; varsayılan 0 = UTC); `harita/bolge(..., bolgeler=...)` bölge eşlemesini değiştirmek için; `profil.ad` = kimlik kategorisinde fact_key="ad" olan beyan, yoksa veri klasörü adı.
- Ölçüm (Linux, sentetik, salt okunur hub, tek deneme): 200k olay: harita 0,38 sn, bölgeler 0,5-0,9 sn. 1 milyon olay: harita ~1,0 sn (sözleşme <3 sn sağlandı), bölgeler 0,8-2,9 sn (en yavaş `bas`: 1M farklı URL'li en kötü durum). Hız için sorgular `NOT INDEXED` (tam tarama dizinli satır-satır erişimden 3-5 kat hızlı ölçüldü); 1M ölçümü test paketinde değil elle yapıldı. Önbellek tablosu yazılmadı (gerekmedi).
- Doğrulanmadı: gerçek Takeout/Reddit verisinde alan adları (yalnız sentetik fixture), Türkçe arama öneki, Windows'ta süre.

## Persona öneri kuyruğu + sohbet + yeni harita alanları (dal iscilik/harita, 2026-11-10)
- Kuyruk: server/src/kimlikserver/oneri.py. `oneri.db` (WAL, busy_timeout 5000, ilk yazımda şema kurulur): `oneriler` (oneri_id, ts, app_id, statement, category, fact_key, kanit_event_ids JSON, guven 0-1, durum bekliyor|onaylandi|duzeltildi|reddedildi|hic_dogru_degil, ifade_hash, karar_ts, duzeltilmis_ifade, fact_id) ve `bastirilan(ifade_hash)`. Bastırma özeti: kategori + Türkçe katlanmış/noktalamasız ifade; yalnız AYNI normalleşmiş ifade yakalanır, anlamca benzer ama farklı sözcüklü öneri yakalanmaz (sınır).
- MCP: `persona_oner(onermeler:[{ifade, kategori, kanit:[event_id], guven, anahtar?}])` yalnız oneri.db'ye yazar; her kanıt olayı var, gizli değil ve kategorisine okuma izni olmalı, aksi halde TÜM çağrı reddedilir (yok/gizli/izinsiz aynı iletiyle, varlık sızmaz). Erişim kaydı ÖNCE yazılır, sonra kuyruğa ekleme yapılır; kayıt yazılamazsa kuyruğa hiçbir şey yazılmaz. Kuyruk üst sınırı 500 bekleyen, çağrı başına 20 öneri, öneri başına 20 kanıt. Açıklama: "Bu araç yalnız öneri kuyruğuna ekler; kullanıcı onaylamadan persona değişmez."
- MCP `ornekle(kategori, n?, sorgu?)`: izinli tek kategoriden örnek (sorguysa FTS, değilse rastgele; üst sınır 200). Hassas kategoriler aynı izin şartı. `persona_oner` için `persona` izni şart koşulmadı (yalnız kanıt kategorileri); onay olmadan facts değişmediğinden bu bilinçli bir karardır, Müdür itiraz ederse tek satır.
- Onay (Windows uygulaması çağırır, yazan Hub gerekir): `OneriYonetici(hub).kuyruk_listele/onayla/duzelt/reddet/hic_dogru_degil/toplu_reddet`. Onay `Persona.add_fact` ile `beyan_edilen` yazar (valid_from=şimdi; fact_key varsa çelişki yönetimi çalışır, test edildi). Önce fact, sonra oneri.db durumu yazılır (iki ayrı dosya, tek işlem değil; yarım kalan onay güvenle tekrarlanabilir). Onaylanmamış öneri persona_getir/kimlik kartında yoktur (testle).
- `persona_getir` kayıtlarına `kategori_basligi` ve `son_dogrulama` (valid_from) eklendi; `kimlik_karti` başlığı "# Kimlik Kartı / ## Bu kişi hakkında bilinenler", kategori başlıkları `###`, her satırda "(kaynak: ..., son doğrulama: GG)". Eski kart biçimine bağımlı tüketici varsa uyarılmalı.
- `sohbet` kategorisi: Category.ALL/SENSITIVE zaten kapsıyor; izin için hassas onay, toplu açmaya dahil değil, kanıt olarak kullanmak izne bağlı (testlerle). NOT: görevde "sohbet" kategorisi geçiyordu; main'e girene kadar yoktu, şimdi var.
- Harita: bölge `zihin` (hassas, kilitli; açıkken yalnız sayı, zaman, platform dağılımı, mesaj/konuşma/rol sayısı; chat fixture metin ve başlıklarının çıktıda geçmediği testle doğrulandı; profil toplamına da sızmaz). kulak: Spotify sanatçı/parça/podcast/süre(dakika); el: GitHub depo/dil ve dosya türü/boyut; alan yoksa "bu alan yok" notu.
- Testler: server paketi toplam 79 geçti (oneri 20, ek harita 3, sohbet izin 2). 200k olayda harita 0,20 sn, bölgeler 0,17-0,67 sn.
- Doğrulanmadı: gerçek Claude/DeepSeek ile persona_oner akışı; modelin çıkarım kalitesi ve kayıt metnine kanıp kanmayacağı. docs/BAGLANTI.md'ye örnek komut eklendi (denenmedi).

## Harita drill-down (dal iscilik/harita, 2026-11-10; INTERFACES §14 için)
- `bolge(hub, id, *, ac_hassas, aralik=None, filtre=None, utc_kaydirma=0)`: `filtre={alan: değer | [değerler]}`; alanlar VE, bir alanın çoklu değeri VEYA. Tüm grafikler ve en_cok yeniden hesaplanır (kendi alanının grafiği de süzülür). Çıktıya `toplam` ve `filtre` eklendi (kilitli çıktı değişmedi). Filtreye uyan kayıt yoksa `grafikler:[]`, notlar `["Filtreye uyan kayıt yok."]`.
- Filtre alanları: ortak `ay` (YYYY-AA), `saat` (0-23, utc_kaydirma'ya göre), `gun` (Pzt..Paz ya da 0-6), `tur` (kind), `kategori`; bölgeye özel: bas `terim`,`site` (küçük harfe çevrilir); goz `kanal`; kulak `sanatci`,`parca`,`podcast`; agiz `subreddit`; el `depo`,`dil`,`uzanti`; ic `uygulama`; zihin `platform`. Hassas bölgelerde yalnız ortak alanlar (+ zihin `platform`); içerik alanıyla filtre FormatError. Geçersiz alan/değer FormatError (bölge için geçerli alan listesi iletide). Zaman filtreleri tarihsiz (dosya tarihi) kayıtları dışlar.
- `anahtar`: her `en_cok` satırında `anahtar:{alan, deger}`; her grafikte etiketlerle paralel `anahtarlar` listesi (filtrelenemeyen noktada None; saat noktasında deger tamsayı, hafta noktasında "Pzt".."Paz"). Gidiş-dönüş testi: grafik/en_cok noktasının anahtarı filtre olarak gönderilince `toplam` o noktanın sayısına eşit (fixture'larla ~60+ nokta; "dakika", "boyut" ve "Sayılar" grafikleri sayım olmadığı için hariç).
- `kayitlar(hub, id, *, filtre, aralik, limit=50 (1-200), offset, ac_hassas, utc_kaydirma)` -> `{id, kilitli, toplam, limit, offset, kayitlar:[{event_id, ts, kind, kategori, baslik, ozet, kaynak_adi}]}` yeniden eskiye. Hassas bölge: baslik/ozet None; kilitliyken `{kilitli:True, toplam:None, kayitlar:[]}`. `kaynak_adi` = "tür: ham dosya adı" (dosya yoksa tür).
- `ayrinti(hub, event_id, *, ac_hassas)`: `{event_id, kilitli, bolge, ts, kind, kategori, cihaz, ice_aktarma_ts, kaynak:{source_id, tur, surum, dosya_sha256, ice_aktarma, dosyalar:[{ad,sha256}], ad}, alanlar (payload; GPS/yerler benzeri anahtarlar "[konum alanı gizlendi]"), metin, tekrar:{ilk,son,sayi}}`. `tekrar` = aynı kategori+tür+metne sahip kayıtların ilk/son görülmesi (ilk/son görülme için yaptığım yorum; metni olmayan kayıtta None). Hassas kategoride içerik yok (açıkken alanlar/metin/tekrar None, kilitliyken yalnız `{event_id, kilitli:True}`). Gizli kayıt NotFoundError.
- `karsilastir(hub, id, aralik_a, aralik_b, *, ac_hassas, filtre, utc_kaydirma)` -> `{a:{aralik,toplam,grafikler,en_cok,notlar}, b:{...}, fark:{toplam, yuzde (a=0 ise None)}, en_cok_degisim:[{ad,grup,anahtar,a,b,fark}] (mutlak farka göre ilk 10)}`; kilitliyse `{kilitli:True,notlar:["Kilitli"]}`. Aralıklar iki ucu dahil (ts>=baslangic, ts<=bitis).
- Testler: server paketi 96 test geçti (yeni 13: elle sayılmış filtre, geçersiz filtre, gidiş-dönüş, sayfalama, kaynak adı/sha, ayrıntı/tekrar/GPS, hassas içerik sızıntısı yok, tombstone/kaynak kaldırma, karşılaştırma).
- Ölçüm (200k olay, Linux, sentetik): harita 0,19 sn; bolge bas 0,64 / goz 0,31 / agiz 0,28 / ic 0,25; filtreli bolge 0,07-0,10; kayitlar (offset 20000) 0,10; ayrinti 0,05; karsilastir bas (iki dönem) 0,72. Hepsi testte < 1,5 sn olarak doğrulanıyor. 1M olayda drill-down ölçülmedi.
- Örnek çıktı: durum/harita-ornek.json yenilendi (anahtarlar, filtre/kayitlar/ayrinti/karsilastir örnekleri dahil).
