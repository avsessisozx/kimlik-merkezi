# SEMA — Veri şeması ve çekirdek davranışları (sahibi: İ1)

Şema sürümü: **2** (`PRAGMA user_version`). Sözleşme: `docs/INTERFACES.md` (sürüm 1). Kod: `core/src/kimlikcore/`.

## 1. Veri klasörü
| Yol | İçerik |
|---|---|
| `kimlik.db` | ana SQLite (WAL). Olaylar, kaynaklar, persona, anahtar/izin, tombstone |
| `erisim.db` | yalnız `access_log` (ayrı SQLite, WAL). Boş şemayı çekirdek hazırlar, yazan taraf İ2 |
| `arsiv/<sha256>/<ad>` | ham dosyalar; salt okunur, değiştirilmez |
| `hub.lock` | yazan sürecin kilit dosyası (JSON: pid, bilgisayar, belirteç) |
| `cikti/` | dışa aktarım vb. çıktılar için boş klasör |

Bağlantı ayarları: yazan `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `busy_timeout=5000`. Okuyucu `file:...?mode=ro` + `query_only=ON`. `erisim.db`: WAL, `busy_timeout=5000` (`kimlikcore.connect_erisim`).

## 2. Göç kuralları
- Sürüm, `PRAGMA user_version`'dır; `schema_migrations(version, applied_at)` kaydı tutar.
- Göçler yalnız eklemelidir ve her biri tek `BEGIN IMMEDIATE` işleminde uygulanır; hata olursa geri alınır, sürüm değişmez.
- Yazan açış (`Hub.open(write=True)`) en yeni sürüme göç ettirir. Salt okunur açış göç etmez: eski sürümde `SchemaTooOld`, daha yenide `SchemaTooNew`.
- v1: çekirdek tablolar. v2: persona/anahtar/izin/cihaz tabloları. `facts.confidence`, `review_queue`, `suppressed` Aşama 9'da göçle gelir (şu an YOK).
- Yeni sürüm eklemek: `schema.MIGRATIONS`'a bir sonraki numarayı ekle (ifade listesi ya da `fn(conn)`); eski göçleri DEĞİŞTİRME.

## 3. Tablolar (v2)
Zaman: UTC metin `YYYY-MM-DDTHH:MM:SSZ` (saniye hassasiyeti; saniye altı atılır). Kimlik: UUID4 metin. Hash: SHA-256 küçük hex.

**sources** `source_id` PK, `kind`, `version`, `file_sha256`, `imported_at`, `removed_at`, `removed_reason`.
Aynı `kind` + `file_sha256` ve kaldırılmamış kaynak varsa `add_source` onu döner (aynı dosya ikinci kez yeni kaynak açmaz).

**raw_files** `raw_id` PK, `source_id`, `name`, `path` (`arsiv/<sha256>/<ad>`, `/` ayraçlı), `sha256`, `size`, `stored_at`; `UNIQUE(source_id, sha256, name)`.

**events** (yalnız eklenir): `seq` (iç sıra, FTS rowid'i), `event_id` UNIQUE, `event_key` UNIQUE, `source_id`, `device_id`, `ts`, `kind`, `category`, `payload` (kanonik JSON: anahtarlar sıralı), `text`, `schema_version` (satırın yazıldığı şema), `hidden` (0/1), `ingested_at`. İndeksler: `ts`, `(category, ts)`, `source_id`.
- `event_key` evrenseldir (kaynaklar arası). Verilmezse `h:` + SHA-256(kaynak türü, kind, category, ts, device_id, payload, text).
- Gizli kayıt `hidden=1` ile işaretlenir; tek tek gizleme ya da kaynak kaldırma aynı bayrağı kullanır. **Tüm sorgular `hidden=0` süzer.**

**events_fts** FTS5, tek sütun `text`, `tokenize='unicode61 remove_diacritics 0'`; `rowid = events.seq`. İçerik, Türkçe katlamadan geçmiş metindir (bölüm 4).

**tombstones**: `tombstone_id` PK, `kind` ∈ {`event_hidden`, `source_removed`, `source_purged`}, `event_id`, `source_id`, `source_kind`, `file_sha256`, `count`, `reason`, `created`.
**tombstone_hashes**: `(tombstone_id, sha256)`: `source_purged` kaydına bağlı hash'ler (kaynak dosyası + ham arşiv dosyaları). İçerik taşımaz.

**devices** `device_id` PK, `name`, `platform`, `created`, `last_seen`.
**facts** `fact_id` PK, `statement`, `source_id|NULL`, `date`, `status` ∈ {`beyan_edilen`,`dosyadan_alinan`,`cikarilan`,`eskimis`}, `valid_from`, `valid_until`, `category` ∈ {`kimlik`,`tercihler`,`ilgi`,`diger`,`cihazlar`,`projeler`,`is`}, `fact_key`, `hidden`, `updated`.
**contradictions** `contradiction_id` PK, `old_fact_id`, `new_fact_id`, `category`, `fact_key`, `opened`, `resolved_at`, `chosen_fact_id`.
**app_keys** `app_id` PK, `name`, `key_hash` UNIQUE, `created`, `revoked` (0/1).
**permissions** `(app_id, category)` PK, `granted_at`, `expires_at|NULL`, `confirmed_sensitive` (0/1). CHECK: `eposta`/`mesaj`/`konum` için `confirmed_sensitive=1` olmadan satır yazılamaz.
Not: `fact_key` (çelişki tespitinde "aynı category+anahtar"), `facts.hidden` (`delete_fact` = gizleme) ve `updated` INTERFACES §5'in alan listesine eklenmiş ek sütunlardır (bkz. durum/core.md, Müdüre istekler).

**meta**: anahtar-değer (şimdilik boş, ileride kullanım için ayrıldı).

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
