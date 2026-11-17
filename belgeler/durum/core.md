# durum/core.md — İ1 Çekirdek işçisi (dal iscilik/core)

Tarih: 2026-11-09. Aşama 1 kodlandı, test edildi, push edildi (son commit 0c00ade). Yalnız `core/` ve `docs/SEMA.md` yazıldı.

## Yapılanlar
- Paket `kimlikcore` (core/src/kimlikcore/), `core/pyproject.toml`, komut `kimlikmerkezi` (pip kurulumunda çalıştığı görüldü: `kimlikmerkezi surum`, `baslat`).
- Sürümlü şema + göç (sürüm 2: v1 çekirdek, v2 persona/anahtar/izin/cihaz); göç tek işlemde, hata olursa geri alınır.
- Ham arşiv (`arsiv/<sha256>/<ad>`, akışla kopya + SHA-256, salt okunur), idempotent `add_events` (evrensel `event_key`), Türkçe katlamalı FTS5 (katlamayı kendim uyguluyorum: `turkish.fold`), zaman çizelgesi, tombstone (gizle / kaynak kaldır / onaylı kalıcı sil / hash'ten "daha önce silindi"), `disa-aktar` / `ice-aktar` (tek işlem, özet doğrulamalı), `hub.lock` (bayat kilit devralma), okuyucular `mode=ro` + WAL, `erisim.db` boş şema yardımcısı (`init_erisim_db`, `connect_erisim`), akışla okuma, CLI (INTERFACES komutları + `kaynaklar`, `ozet`).
- Çekirdek yalnız standart kütüphane kullanır (içe aktarma listesi kontrol edildi; `kimlikimport` yalnız `ice-al` içinde isteğe bağlı, try/except).
- `docs/SEMA.md` yazıldı.

## Test sonuçları (gerçekten çalıştırıldı)
- `cd core && pytest tests` (Python 3.13.18, SQLite 3.53.1, Linux): **50 passed, 1 deselected** (buyuk), ~9 sn.
- Aynı komut Python 3.12.3 (SQLite 3.45.1) ile: **50 passed, 1 deselected**.
- Kapsanan Aşama 1 maddeleri: bilinen 20 kaydın aramada bulunması (test_ingest); aynı dosya iki kez alınınca kaynak/ham dosya/olay sayısı ve kaynak kimliği aynı, hem API hem CLI (test_ingest, test_cli); eski şemadan göç (elle yazılmış donmuş v1 DB → v2; veri ve arama korunur; başarısız göç geri alınır; daha yeni şema reddedilir) (test_migration); dışa aktar → boş hub'a ice-aktar → sayı ve içerik özetleri eşit, kesik/bozuk dosya hiçbir şey bırakmaz (test_export_import); WAL + mode=ro gerçek ayrı süreç okuyucu, yazan sürerken 4 sn: 46 okuyucu turu, hata 0, anlık görüntü tutarlı, okuyucu yazamıyor, yazan toplu yazımı en çok 0.043 sn gecikti, integrity_check ok (test_concurrency); Türkçe arama ışık/ISIK, İstanbul/istanbul, çğşöü/CGSOU, sorgu enjeksiyonu zararsız (test_turkce); kaynak kaldırınca aramada/zaman çizelgesinde görünmez, kalıcı silmede satır+FTS+ham dosya gider, silinen sözcük .db dosyasında kalmaz (test_tombstones).
- Ek: ikinci yazan süreç `HubLockedError` (CLI çıkış kodu 3); SIGKILL ile öldürülen gerçek sürecin bayat kilidi devralınır; erisim.db'ye 4 süreç x 300 eşzamanlı yazım = 1200 satır, kayıp yok.
- **Büyük dosya** (`pytest -m buyuk core/tests/test_buyuk.py`, 1 kez çalıştırıldı): 2 147 483 675 bayt (2.00 GiB), 2 190 891 satır sentetik JSONL; sha256+ham arşiv kopyası+tüm olaylar+FTS içe alındı, 2 190 891 eklendi, 0 tekrar, sayım doğru, "hedefkayit777zz" aramada bulundu. **Alt sürecin tepe belleği (ru_maxrss): 99.2 MB** (eşik 300 MB; 64 MB SQLite sayfa önbelleği dahil). Süre: hash 2.2 sn, ham kopya 4.3 sn, olaylar 302.5 sn (~7.2 bin olay/sn, FTS dahil); kimlik.db 3.4 GB. Üretim sırasında oturum başına 1 kez çalıştırıldı; ikinci geçiş (idempotentlik) büyük dosyada denenmedi (küçükte denendi).

## Doğrulandı / doğrulanmadı
Doğrulandı (Linux, Python 3.12/3.13, yerel): yukarıdaki tüm testler.
Doğrulanmadı:
- Windows: `pid_alive` (ctypes OpenProcess), `os.chmod` ile salt okunur arşiv ve silerken yeniden yazılabilir yapma, `os.replace`/`os.link` davranışı, `as_uri` ile `mode=ro` yolu. Windows koduna bu ortamda hiç dokunulmadı. CI'de Windows koşusu gerekir.
- GitHub CI'de çalıştırma (CI yapılandırması müdürde; ben yalnızca yerelde koştum).
- 2 GB'lık dışa aktarım / ice-aktar süresi ve belleği ölçülmedi (ice-aktar tek işlem; WAL dosyası veri boyutu kadar büyür).
- Başka bilgisayardan (ağ paylaşımı) gelen kilit: yalnız "canlı say" kuralı testle (sahte host adı) doğrulandı, gerçek ağ paylaşımı denenmedi.
- Python 3.12 altında büyük test koşulmadı (yalnız 3.13).

## Bilinen sorunlar / sınırlar
- Zaman saniye hassasiyetinde saklanır (saniye altı atılır).
- Arama aksan duyarsızdır ("isik" de "ışık"ı bulur); bu, "ışık"/"ISIK" şartının doğal sonucudur. Önek araması varsayılan kapalı (`kel*` ya da `prefix=True`); Türkçe ekler için içe aktarıcı/arayüz isterse açabilir.
- `payload` aranmaz, yalnız `text` aranır.
- `purge_source` sonrası adli kurtarma garantisi verilmez (secure_delete + FTS optimize + VACUUM yapılır).
- `add_events` toplu işlemleri 5000 kayıtta bir kesinleştirir; ortada hata olursa önceki gruplar kalır (yeniden çalıştırmak güvenli).
- Kaynak kaldırıldıktan sonra aynı dosya yeniden alınırsa eski gizli kayıtlar yeni kaynağa bağlanıp görünür olur (tasarım kararı, SEMA §5).

## Müdüre istekler (INTERFACES'e dokunmadım; en makul yorumla ilerledim)
1. **`facts` ek sütunları:** §5 "aynı category+anahtar" diyor ama alan listesinde anahtar yok; `fact_key` ekledim. Ayrıca `delete_fact` (gizleme) için `facts.hidden` ve `updated`. `app_keys.revoked` 0/1 tamsayı (zaman damgası değil). Sözleşmeye işlenmesini ya da düzeltmeyi isteyin (İ2 bunlara göre yazar).
2. **`purge_source` onayı:** imza onay parametresi taşımıyor. API doğrudan siler; onay CLI'de (`--onayla` ya da etkileşimli "SIL"). Arayüz/Windows kabuğu kendi onay ekranını göstermek zorunda. İsterseniz sözleşmeye `confirm` eklensin.
3. **Hash'ten tanıma çağıranda:** `add_source` kalıcı silinmiş hash'i engellemez; çalıştırıcı (`kimlikimport.run`) `hub.previously_purged(sha256)` ile sorup kullanıcıya "yine de alınsın mı" demeli (CLI `ice-al` bunu `--yine-de` ile yapıyor). §4 çalıştırıcı sırasına eklenmeli.
4. **Kalıcı silinen kaynağın `facts`'i:** silinmez; `source_id=NULL`, `status='eskimis'` olur (yapay zekâya verilmez). Başka davranış isterseniz söyleyin.
5. **Sözleşmeye eklediğim isteğe bağlı parametre/yöntemler** (geri uyumlu): `timeline(ascending=)`, `search(prefix=)`, `add_events(batch_size=)`, `Hub.sources()`, `raw_files()`, `get_event()`, `verify_archive()`, `summary()`, `previously_purged()`, `compact()`; `Hub.import_jsonl(progress=)`; hata sınıfları `SchemaTooOld`, `HubNotFoundError`, `HubReadOnlyError`, `HubNotEmptyError`, `NotFoundError`; `kimlikcore.fold`, `norm_ts`, `init_erisim_db`, `connect_erisim`.
6. **`ice-al` ve içe aktarıcılar:** çekirdekte yalnız dahili `jsonl` türü var (her satır bir EventIn). Diğer `--tur` değerleri için `kimlikimport.run.run(hub, path, tur=...)` çağıracak biçimde tahmin ettim (yoksa anlaşılır hata). Gerçek imzayı İ3 ile netleştirin; test edilmedi.
7. **Salt okunur açış göç etmez:** MCP/okuyucu, veri klasörü eski şemadaysa `SchemaTooOld` alır; önce yazan süreç (uygulama / `kimlikmerkezi baslat`) açılmalı. Sunucu tarafında kullanıcıya "önce uygulamayı açın" iletisi gerekir.
8. **İ2'ye not:** gizli kayıtlar `events.hidden=1` ile işaretli; sunucu `Hub.search/timeline` kullanırsa süzülür, doğrudan SQL yazarsa `hidden=0` koşulunu kendisi eklemeli. `access_log` kategorisi boş (NULL) olabilir (`kategorileri_listele` gibi araçlar için).
9. **Python sürümü:** `requires-python >= 3.12` yazdım (INTERFACES "3.12+"); 3.12.3 ve 3.13.18'de test geçti. Karar B sonrası sabitlenecekse bildirin.

## Güncelleme 2026-11-10 (görev 2)
- `Hub.transaction()` (yazma işlemi bağlam yöneticisi, `sqlite3.Connection` verir) ve `Hub.query(sql, params)` / `Hub.query_one` (salt okunur, yazan hub'da `query_only` ile zorlanır) eklendi; `Hub._conn/_tx/_mutex` yerine geçer (SEMA §9). `server/_db.py` değiştirilmedi; İ2 `read()` yerine `hub.query`, `write_tx()` yerine `hub.transaction()` kullanabilir. Tek anlık görüntülü çoklu okuma için ayrı `read()` eklemedim (istenirse söyleyin).
- CLI `ice-al`: klasör kabul eder; `--tur` varsayılan `auto` -> `kimlikimport.run.run(hub, yol, tur=None, yine_de=...)`; `jsonl` açık kalır (yalnız dosya). DİKKAT: önceden varsayılan `jsonl` idi, artık `--tur jsonl` yazılmalı. Önceki tahminim (`run(hub, path, tur=...)`) gerçek imzayla uyumluymuş; `yine_de` da geçiriliyor. Purge kontrolü tek yerde (çalıştırıcı / jsonl dalı).
- Testler: `cd core && pytest tests`: 59 passed, 1 deselected (Python 3.13.18; PATH'te venv/bin ve `pip install -e core -e importers`). `cd importers && pytest`: 35 passed, 1 deselected. Yeni: test_hub_api.py (8 test), test_cli.py'ye klasör + otomatik tanıma + purge sorgusu + tanınmayan girdi.
- Doğrulanmadı: `server` testleri (test_mcp_stdio toplama hatası verdi, büyük olasılıkla MCP kütüphanesi bu venv'de yok; bu görevle ilgisiz, araştırılmadı). core ve importers testleri aynı pytest çağrısında birlikte çalışmaz (aynı adlı test_cli.py/test_buyuk.py); ayrı ayrı çalıştırın.

## Güncelleme 2026-11-10 (Windows kodlama düzeltmesi)
- Testlerdeki tüm `subprocess` çağrılarında `text=True` yerine `encoding="utf-8"` (conftest.run_child, test_cli, test_concurrency, test_buyuk). CLI `main()` artık tty olmayan stdout/stderr'i UTF-8'e zorlar (`reconfigure`); `PYTHONIOENCODING=cp1252` ile elle denendi, çıktı UTF-8 geldi.
- Linux (Python 3.13): `cd core && pytest tests` 59 passed, 1 deselected. Windows'ta ÇALIŞTIRILMADI; 3 testin Windows CI'de geçtiği doğrulanmadı, CI koşusuyla teyit gerekir.

## Güncelleme 2026-11-10 (kaynak-sil EOFError)
- `kaynak-sil` onay isteminde `EOFError/OSError` yakalanır: "Onay okunamadı ... --onayla kullanın", çıkış kodu 1, traceback yok. Testler: stdin=DEVNULL, boş boru (`input=""`) ve isatty()=True sahte stdin (Windows davranışının benzetimi). Linux: core 60 passed, 1 deselected. Windows'ta çalıştırılmadı; CI ile teyit gerekir.

## Güncelleme 2026-11-10 (sohbet kategorisi, şema sürümü 3)
- `Category.SOHBET`, `Category.ALL` ve `SENSITIVE` (hassas) güncellendi. Göç v3: `permissions` CHECK kısıtı `sohbet` dahil olacak biçimde tablo yeniden oluşturularak değiştirildi (tek işlem; veri, birincil/dış anahtar korunur). `events.category` üzerinde CHECK olmadığı için o tabloya dokunulmadı. SEMA.md güncellendi.
- Testler (Linux, 3.13): `cd core && pytest tests` 63 passed, 1 deselected. Yeni: v2 şemalı (eski CHECK'li, veri dolu) DB v3'e göç eder, veri/arama/dış anahtar sağlam, `sohbet` izni onaysız reddedilir; sohbet olayı eklenir/aranır/zaman çizelgesinde; dışa/içe aktarımda `summary` eşit. `PYTHONPATH=core/src:importers/src python -m pytest importers`: 85 passed, 3 deselected (python-docx kurulunca; ilk denemede 7 hata yalnızca eksik `docx` paketindendi).
- Doğrulanmadı: server'ın `test_mcp_stdio` testi (MCP kütüphanesi yok); server diğer testleri 31 passed. Windows'ta çalıştırılmadı.

### Müdüre istekler (yeni)
- `importers/tests/conftest.py` (satır 9-14) içindeki `sohbet` taklidi artık gereksiz (`if "sohbet" not in Category.ALL` dalı çalışmıyor); importers işçisi kaldırsın. Taklit olmadan testlerin geçmesi beklenir; ben conftest'i değiştirmeden çalıştırdığımda geçti, taklidi silip ayrıca denemedim.
- İ2/server: MCP kategori listesi ve izin ekranı `Category.ALL/SENSITIVE`'ı kullanmıyorsa `sohbet` eklenmeli.
