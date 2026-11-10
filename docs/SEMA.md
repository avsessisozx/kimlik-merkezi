# SEMA — Veri şeması ve çekirdek davranışları (sahibi: İ1)

Şema sürümü: **4** (`PRAGMA user_version`). Sözleşme: `docs/INTERFACES.md` (sürüm 1). Kod: `core/src/kimlikcore/`.

## 1. Veri klasörü
| Yol | İçerik |
|---|---|
| `kimlik.db` | ana SQLite (WAL; şifreliyse şifreli kapsayıcı). Olaylar, kaynaklar, persona, anahtar/izin, tombstone, `access_log`, `oneriler`, `bastirilan` |
| `gelen/` | MCP süreçlerinin bıraktığı, henüz işlenmemiş erişim/öneri kayıtları (her biri kendi dosyası; şifreliyse şifreli). Yazan Hub işleyip siler. `gelen/bozuk/`: okunamayanlar |
| `erisim.db`, `oneri.db` | **v4 ile kaldırıldı**; eski klasörlerde bulunursa yazan Hub açılırken göç ettirilip silinir (INTERFACES Ek 1.5) |
| `arsiv/<sha256>/<ad>` | ham dosyalar; salt okunur, değiştirilmez |
| `hub.lock` | yazan sürecin kilit dosyası (JSON: pid, bilgisayar, belirteç) |
| `cikti/` | dışa aktarım vb. çıktılar için boş klasör |

Bağlantı ayarları: yazan `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`. Okuyucu `file:...?mode=ro` + `query_only=ON`. Eski `erisim.db` yardımcıları (`connect_erisim`, `init_erisim_db`) yalnız geriye dönük uyumluluk içindir.

## 2. Göç kuralları
- Sürüm, `PRAGMA user_version`'dır; `schema_migrations(version, applied_at)` kaydı tutar.
- Göçler yalnız eklemelidir ve her biri tek `BEGIN IMMEDIATE` işleminde uygulanır; hata olursa geri alınır, sürüm değişmez.
- Yazan açış (`Hub.open(write=True)`) en yeni sürüme göç ettirir. Salt okunur açış göç etmez: eski sürümde `SchemaTooOld`, daha yenide `SchemaTooNew`.
- v1: çekirdek tablolar. v2: persona/anahtar/izin/cihaz tabloları. v3: hassas kategori `sohbet` (`permissions` CHECK kısıtı genişledi; SQLite CHECK değiştiremediği için tablo aynı işlemde yeniden oluşturuldu: yeni tabloya kopya, eskiyi at, yeniden adlandır; satırlar aynen taşınır). v4: `access_log`, `oneriler`, `bastirilan` tabloları (eskiden ayrı, şifresiz `erisim.db`/`oneri.db`). Eski dosyaların içeriği tablolar oluştuktan sonra, yazan Hub açılışında KOD ile taşınır (`Hub._eski_dosyalari_goc`: kopyala, satır satır doğrula, sıfırlayıp sil; yarım kalırsa güvenle tekrarlanır). `facts.confidence`, `review_queue`, `suppressed` Aşama 9'da göçle gelir (şu an YOK).
- Yeni sürüm eklemek: `schema.MIGRATIONS`'a bir sonraki numarayı ekle (ifade listesi ya da `fn(conn)`); eski göçleri DEĞİŞTİRME.

## 3. Tablolar (v2)
Zaman: UTC metin `YYYY-MM-DDTHH:MM:SSZ` (saniye hassasiyeti; saniye altı atılır). Kimlik: UUID4 metin. Hash: SHA-256 küçük hex.

**sources** `source_id` PK, `kind`, `version`, `file_sha256`, `imported_at`, `removed_at`, `removed_reason`.
Aynı `kind` + `file_sha256` ve kaldırılmamış kaynak varsa `add_source` onu döner (aynı dosya ikinci kez yeni kaynak açmaz).

**raw_files** `raw_id` PK, `source_id`, `name`, `path` (`arsiv/<sha256>/<ad>`, `/` ayraçlı), `sha256`, `size`, `stored_at`; `UNIQUE(source_id, sha256, name)`.

**events** (yalnız eklenir; `category` üzerinde DB CHECK'i yoktur, kategori kodda `Category.ALL` ile doğrulanır, bu yüzden yeni kategori eklemek bu tabloya dokunmaz): `seq` (iç sıra, FTS rowid'i), `event_id` UNIQUE, `event_key` UNIQUE, `source_id`, `device_id`, `ts`, `kind`, `category`, `payload` (kanonik JSON: anahtarlar sıralı), `text`, `schema_version` (satırın yazıldığı şema), `hidden` (0/1), `ingested_at`. İndeksler: `ts`, `(category, ts)`, `source_id`.
- `event_key` evrenseldir (kaynaklar arası). Verilmezse `h:` + SHA-256(kaynak türü, kind, category, ts, device_id, payload, text).
- Gizli kayıt `hidden=1` ile işaretlenir; tek tek gizleme ya da kaynak kaldırma aynı bayrağı kullanır. **Tüm sorgular `hidden=0` süzer.**

**events_fts** FTS5, tek sütun `text`, `tokenize='unicode61 remove_diacritics 0'`; `rowid = events.seq`. İçerik, Türkçe katlamadan geçmiş metindir (bölüm 4).

**tombstones**: `tombstone_id` PK, `kind` ∈ {`event_hidden`, `source_removed`, `source_purged`}, `event_id`, `source_id`, `source_kind`, `file_sha256`, `count`, `reason`, `created`.
**tombstone_hashes**: `(tombstone_id, sha256)`: `source_purged` kaydına bağlı hash'ler (kaynak dosyası + ham arşiv dosyaları). İçerik taşımaz.

**devices** `device_id` PK, `name`, `platform`, `created`, `last_seen`.
**facts** `fact_id` PK, `statement`, `source_id|NULL`, `date`, `status` ∈ {`beyan_edilen`,`dosyadan_alinan`,`cikarilan`,`eskimis`}, `valid_from`, `valid_until`, `category` ∈ {`kimlik`,`tercihler`,`ilgi`,`diger`,`cihazlar`,`projeler`,`is`}, `fact_key`, `hidden`, `updated`.
**contradictions** `contradiction_id` PK, `old_fact_id`, `new_fact_id`, `category`, `fact_key`, `opened`, `resolved_at`, `chosen_fact_id`.
**app_keys** `app_id` PK, `name`, `key_hash` UNIQUE, `created`, `revoked` (0/1).
**permissions** `(app_id, category)` PK, `granted_at`, `expires_at|NULL`, `confirmed_sensitive` (0/1). CHECK: `eposta`/`mesaj`/`konum`/`sohbet` için `confirmed_sensitive=1` olmadan satır yazılamaz.
Not: `fact_key` (çelişki tespitinde "aynı category+anahtar"), `facts.hidden` (`delete_fact` = gizleme) ve `updated` INTERFACES §5'in alan listesine eklenmiş ek sütunlardır (bkz. durum/core.md, Müdüre istekler).

**access_log** (v4) `id` AUTOINCREMENT PK, `ts`, `app_id`, `tool`, `category|NULL`, `result_count`, `outcome` ∈ {`ok`,`reddedildi`,`hata`}. İçerik ve sorgu metni yazılmaz. İndeksler `ts`, `(app_id, ts)`.
**oneriler** (v4) `oneri_id` PK, `ts`, `app_id`, `statement`, `category`, `fact_key`, `kanit_event_ids` (JSON listesi), `guven` (0..1), `durum` ∈ {`bekliyor`,`onaylandi`,`duzeltildi`,`reddedildi`,`hic_dogru_degil`}, `ifade_hash`, `karar_ts`, `duzeltilmis_ifade`, `fact_id`. **bastirilan** `ifade_hash` PK, `ts`, `category`.
Bu tablolara MCP süreçleri doğrudan yazmaz; kayıtlar `gelen/` kutusundan `Hub.gelen_birlestir()` ile gelir (bölüm 12).

**meta**: anahtar-değer. Kullanılan anahtar: `goc_erisim_db` (eski `erisim.db` göçü tamamlandı işareti).

## 4. Türkçe katlama (arama)
`turkish.fold(metin)`: `İ`,`I`,`ı` → `i`; Unicode ayrıştırma (NFKD) ile aksanlar atılır (ç→c, ğ→g, ş→s, ö→o, ü→u, â→a ...); `casefold`. Hem kayıt metni FTS'e girerken hem sorgu aynı işlemden geçer. Sonuç: "ışık", "Işık", "ISIK", "isik" aynı; "İstanbul" = "istanbul"; "çğşöü" = "CGSOU". Bedel: aksan duyarsız arama (ASCII yazılmış "isik", "ışık"ı da bulur). Ayrıntı: sorgu dili `turkish.build_fts_query`.
Sorgu dili: boşlukla ayrılan terimlerin hepsi aranır (VE); `"iki kelime"` tümce; `kel*` önek (ya da `prefix=True`). FTS5 işleçleri (`OR`, `NEAR`, `sütun:`) kullanıcıdan alınmaz, metin sayılır. Sıralama: `bm25`, sonra yeni → eski. Yalnız `text` aranır (payload aranmaz); içe aktarıcı aranması gereken her şeyi `text`'e yazmalıdır.

## 5. Silme yolu
- **Gizle** (`hide_event`): `hidden=1` + `event_hidden` tombstone. Satır silinmez.
- **Kaynağı kaldır** (`remove_source`): kaynağın kayıtları `hidden=1`, `sources.removed_at` dolar, `source_removed` tombstone yazılır. Kaldırılmış kaynağa olay eklenemez. Aynı dosya yeni kaynak olarak yeniden alınırsa aynı `event_key`'li gizli kayıtlar yeni kaynağa bağlanıp görünür olur (tek tek gizlenmiş olanlar gizli kalır).
- **Kalıcı sil** (`purge_source`, onay çağıranda: CLI `--onayla`): kaynağın olayları, FTS kayıtları, ham arşiv dosyaları ve o kaynağa ait tombstone'lar silinir; yalnız `source_purged` kaydı (tür, tarih, kayıt sayısı, hash'ler) kalır. Başka bir kaynak aynı arşiv dosyasını kullanıyorsa dosya silinmez. Bu kaynağa bağlı `facts` silinmez: `source_id=NULL`, `status='eskimis'` olur. Silinen içeriğin SQLite sayfalarında kalmaması için `secure_delete`, FTS5 `optimize` ve WAL kesme uygulanır; `compact()` (VACUUM) ayrıca dosyayı küçültür (CLI `kaynak-sil` bunu çağırır). Sınır: SQLite/dosya sistemi düzeyinde adli kurtarma garantisi verilmez.
- **Hash'ten tanıma**: `previously_purged(sha256)`; `ice-al` bu durumda `--yine-de` olmadan reddeder.

## 6. Dışa/içe aktarım (JSON Lines)
`disa-aktar`: tek tutarlı okuma anlık görüntüsünden (yazan engellenmez) UTF-8 JSONL. Satır türleri (`t` alanı): `header`, `source`, `raw_file`, `tombstone`, `tombstone_hash`, `device`, `app_key`, `permission`, `fact`, `contradiction`, `event`, `footer`. `event.payload` gerçek JSON nesnesidir. Gizli kayıtlar `hidden:1` ile gelir; kalıcı silinenlerin içeriği yoktur. `app_keys` yalnız hash taşır. Ham dosyaların kendisi dışa aktarıma girmez (`arsiv/` zaten açık biçimdedir); yalnız `raw_file` üst verisi girer.
`footer`: tür başına `counts` ve `digests` (her kaydın kanonik JSON SHA-256'sının sıradan bağımsız toplamı). `Hub.summary()` aynı değerleri veritabanından üretir; eşitlik "sayı ve özetler eşit" ölçütüdür.
`ice-aktar` yalnız BOŞ hub'a yapılır, **tek işlemde** çalışır; satır bozuk, dosya kesik ya da özet uyuşmuyorsa hiçbir şey kalmaz. `ImportResult.raw_missing`: üst verisi gelen ama `arsiv/` altında bulunmayan ham dosya sayısı (geri yüklerken `arsiv/` klasörünü de kopyalayın). Dışa aktarım şema sürümü hub'dan eskiyse özet doğrulaması atlanır (`verified=False`).

## 7. Eşzamanlılık
- Yazan: `Hub.open(write=True)`; `hub.lock` `O_EXCL` ile alınır. Kilit sahibi öldüyse (aynı bilgisayarda pid yok / zombi / Linux'ta başlangıç zamanı farklı) kilit atomik `rename` ile kenara alınıp devralınır. Başka bilgisayardan yazılmış kilit canlı sayılır (doğrulanamaz).
- Okuyucu: `mode=ro`; kilit almaz. WAL sayesinde yazan okuyucuyu, okuyucu yazanı beklemez. Okuyucu, yazan kapalıyken de açılır.
- `Hub` nesnesi iş parçacığı güvenlidir (iç `RLock`), ama aynı anda tek yazan süreç kuralı değişmez.

## 8. Akışla okuma ve bellek
`streaming.iter_lines` dosyayı satır satır okur (tek satır ≤ 64 MiB, aşılırsa `FormatError`). `store_raw` 1 MiB parçalarla kopyalar ve hash'ler. `add_events` üreteçle çalışır, 5000 kayıtta bir işlemi kesinleştirir. Ölçüm: `core/tests/test_buyuk.py` (sonuç durum/core.md'de).

## 9. Genel SQL erişimi (özel üyeler yerine)
`Hub._conn/_tx/_mutex` özel üyelerdir; sürümler arası korunmaz. Persona/anahtar/izin gibi çekirdeğin dışında yönetilen tablolar için genel API:
- `with hub.transaction() as c:` yazma işlemi (`BEGIN IMMEDIATE`; çıkışta `COMMIT`, istisnada `ROLLBACK`). `c` bir `sqlite3.Connection`'dır: yalnız `execute`/`executemany`; `commit`/`rollback`/`close` çağırmayın; iç içe kullanmayın. Salt okunur hub'da `HubReadOnlyError`. İşlem boyunca hub'ın iç kilidi tutulur.
- `hub.query(sql, params=())` salt okunur tek ifade, `list[tuple]` döner; `hub.query_one(...)` ilk satır ya da `None`. Yazan hub'da çağrı süresince `query_only=ON` olur (yazma girişimi `sqlite3.OperationalError`). Açık `transaction()` içinden çağrılırsa o işlemin yazdıklarını görür. Okumalar arasında tek anlık görüntü gerekiyorsa `transaction()` içinde `c.execute` kullanın.
Gizli kayıt süzmesi bu yöntemlerde otomatik DEĞİLDİR: `events` sorgularında `hidden = 0` ekleyin (ya da `search/timeline` kullanın).

## 10. CLI `ice-al`
`kimlikmerkezi ice-al <yol> [--tur auto|jsonl|<içe aktarıcı adı>] [--yine-de]`. Yol dosya ya da klasör olabilir. Varsayılan `auto`: `kimlikimport.run.run(hub, yol, tur=None)` ile otomatik tanıma. `jsonl`: dahili, yalnız dosya, her satır bir EventIn. "Daha önce kalıcı silindi" sorgusu tek yerde yapılır: içe aktarıcı yolunda çalıştırıcıda, `jsonl` yolunda `_run_jsonl` içinde.

## 11. Şifreli veri klasörü (şema sürümü değişmedi)
`kimlik.db` şifreliyse (başlık `KMSIFRE1`) düz SQLite dosyası değil, şifreli kapsayıcıdır; şema bellekteki kopyada aynen çalışır, göçler aynı yolla uygulanır ve kapsayıcıya yazılır. Salt okunur açılış bellekte anlık görüntü alır (WAL yok). Ayrıntı ve sınırlar: `docs/SIFRELEME.md`. `arsiv/` dosyaları şifreliyse `Hub.raw_parcalari` ile okunmalıdır.

## 12. Gelen kutusu (v4)
Birden çok MCP süreci erişim günlüğüne ve öneri kuyruğuna aynı anda yazmak ister; `kimlik.db` ise tek yazan süreçtir (şifreliyse bellek içi kapsayıcı, her yazımda dosyanın tamamı yeniden yazılır). Süreçlerin kapsayıcıyı kendi aralarında "oku-değiştir-yaz" yapması güncelleme kaybettirir, ayrı SQLite dosyası ise şifrelenemez. Bu yüzden: `GelenKutusu.yaz` her kaydı `gelen/` altında benzersiz adlı kendi dosyasına (geçici dosya + `fsync` + `os.replace`; şifreliyse aynı AES-GCM biçimi) bırakır; hiçbir iki yazar aynı dosyaya dokunmaz, kilit gerekmez. Yazan Hub `gelen_birlestir` ile tek işlemde tabloya işler (`synchronous=FULL`, şifreliyse kapsayıcı yazıldıktan sonra), sonra dosyaları siler; yarıda kalırsa öneri `oneri_id` ile yinelenmez, ama erişim satırı çökme anında bir kez çift yazılabilir (dosya silinmeden önce süreç ölürse). Okuyucular tablo + bekleyen dosyaları birlikte görür. Yazan Hub açık olsa da MCP yazabilir (kilit gerekmez).
