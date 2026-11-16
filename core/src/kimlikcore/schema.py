"""Sürümlü şema ve göç (migration). Ayrıntı: docs/SEMA.md.

Sürüm `PRAGMA user_version` içinde tutulur. Her göç tek işlemde (BEGIN IMMEDIATE)
uygulanır; hata olursa geri alınır ve sürüm değişmez. Göçler yalnız eklemelidir
(geri uyumlu); eski sürümde yazılmış veri yeni sürümde açılır.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone

from .errors import SchemaTooNew

Statements = Sequence[str]

_V1: Statements = [
    """CREATE TABLE schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    )""",
    """CREATE TABLE meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",
    """CREATE TABLE sources (
        source_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        version TEXT NOT NULL,
        file_sha256 TEXT,
        imported_at TEXT NOT NULL,
        removed_at TEXT,
        removed_reason TEXT
    )""",
    "CREATE INDEX idx_sources_sha ON sources(file_sha256)",
    """CREATE TABLE raw_files (
        raw_id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL REFERENCES sources(source_id),
        name TEXT NOT NULL,
        path TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size INTEGER NOT NULL,
        stored_at TEXT NOT NULL,
        UNIQUE (source_id, sha256, name)
    )""",
    "CREATE INDEX idx_raw_sha ON raw_files(sha256)",
    """CREATE TABLE events (
        seq INTEGER PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        event_key TEXT NOT NULL UNIQUE,
        source_id TEXT NOT NULL REFERENCES sources(source_id),
        device_id TEXT,
        ts TEXT NOT NULL,
        kind TEXT NOT NULL,
        category TEXT NOT NULL,
        payload TEXT NOT NULL,
        text TEXT NOT NULL,
        schema_version INTEGER NOT NULL,
        hidden INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)),
        ingested_at TEXT NOT NULL
    )""",
    "CREATE INDEX idx_events_ts ON events(ts)",
    "CREATE INDEX idx_events_cat_ts ON events(category, ts)",
    "CREATE INDEX idx_events_source ON events(source_id)",
    # Türkçe katlama uygulama tarafında yapılır (turkish.fold); unicode61 yalnız
    # ayırıcıdır, kendi aksan/harf dönüşümü kapalı.
    """CREATE VIRTUAL TABLE events_fts USING fts5(
        text, tokenize = 'unicode61 remove_diacritics 0'
    )""",
    """CREATE TABLE tombstones (
        tombstone_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('event_hidden', 'source_removed', 'source_purged')),
        event_id TEXT,
        source_id TEXT,
        source_kind TEXT,
        file_sha256 TEXT,
        count INTEGER,
        reason TEXT,
        created TEXT NOT NULL
    )""",
    "CREATE INDEX idx_tomb_event ON tombstones(event_id)",
    "CREATE INDEX idx_tomb_source ON tombstones(source_id)",
    """CREATE TABLE tombstone_hashes (
        tombstone_id TEXT NOT NULL REFERENCES tombstones(tombstone_id),
        sha256 TEXT NOT NULL,
        PRIMARY KEY (tombstone_id, sha256)
    )""",
    "CREATE INDEX idx_tomb_hash ON tombstone_hashes(sha256)",
]

# v2: persona, anahtar/izin ve cihaz tabloları (yazan taraf İ2). `confidence`,
# `review_queue`, `suppressed` Aşama 9'da göçle gelir; burada YOKTUR.
_V2: Statements = [
    """CREATE TABLE devices (
        device_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        platform TEXT,
        created TEXT NOT NULL,
        last_seen TEXT
    )""",
    """CREATE TABLE facts (
        fact_id TEXT PRIMARY KEY,
        statement TEXT NOT NULL,
        source_id TEXT REFERENCES sources(source_id),
        date TEXT NOT NULL,
        status TEXT NOT NULL CHECK (
            status IN ('beyan_edilen', 'dosyadan_alinan', 'cikarilan', 'eskimis')),
        valid_from TEXT,
        valid_until TEXT,
        category TEXT NOT NULL CHECK (
            category IN ('kimlik', 'tercihler', 'ilgi', 'diger', 'cihazlar', 'projeler', 'is')),
        fact_key TEXT,
        hidden INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)),
        updated TEXT
    )""",
    "CREATE INDEX idx_facts_cat_key ON facts(category, fact_key)",
    "CREATE INDEX idx_facts_source ON facts(source_id)",
    """CREATE TABLE contradictions (
        contradiction_id TEXT PRIMARY KEY,
        old_fact_id TEXT NOT NULL REFERENCES facts(fact_id),
        new_fact_id TEXT NOT NULL REFERENCES facts(fact_id),
        category TEXT NOT NULL,
        fact_key TEXT,
        opened TEXT NOT NULL,
        resolved_at TEXT,
        chosen_fact_id TEXT REFERENCES facts(fact_id)
    )""",
    """CREATE TABLE app_keys (
        app_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        key_hash TEXT NOT NULL UNIQUE,
        created TEXT NOT NULL,
        revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1))
    )""",
    """CREATE TABLE permissions (
        app_id TEXT NOT NULL REFERENCES app_keys(app_id),
        category TEXT NOT NULL,
        granted_at TEXT NOT NULL,
        expires_at TEXT,
        confirmed_sensitive INTEGER NOT NULL DEFAULT 0 CHECK (confirmed_sensitive IN (0, 1)),
        PRIMARY KEY (app_id, category),
        CHECK (category NOT IN ('eposta', 'mesaj', 'konum') OR confirmed_sensitive = 1)
    )""",
]

# v3: hassas kategori `sohbet`. CHECK kısıtı değiştirilemediği için `permissions` tablosu
# yeniden oluşturulur (aynı işlemde: kopyala, eskiyi at, yeniyi adlandır); satırlar aynen kalır.
# `events.category` üzerinde CHECK yoktur (kategori doğrulaması kodda), o tabloya dokunulmaz.
_V3: Statements = [
    """CREATE TABLE permissions_yeni (
        app_id TEXT NOT NULL REFERENCES app_keys(app_id),
        category TEXT NOT NULL,
        granted_at TEXT NOT NULL,
        expires_at TEXT,
        confirmed_sensitive INTEGER NOT NULL DEFAULT 0 CHECK (confirmed_sensitive IN (0, 1)),
        PRIMARY KEY (app_id, category),
        CHECK (category NOT IN ('eposta', 'mesaj', 'konum', 'sohbet') OR confirmed_sensitive = 1)
    )""",
    """INSERT INTO permissions_yeni(app_id, category, granted_at, expires_at, confirmed_sensitive)
        SELECT app_id, category, granted_at, expires_at, confirmed_sensitive FROM permissions""",
    "DROP TABLE permissions",
    "ALTER TABLE permissions_yeni RENAME TO permissions",
]

# v4: erişim günlüğü (`access_log`) ve persona öneri kuyruğu (`oneriler`, `bastirilan`) ana veritabanına
# taşındı. Eskiden ayrı `erisim.db` / `oneri.db` dosyalarıydı ve ŞİFRELENMİYORDU. Eski dosyaların
# içeriği yazan Hub açılırken göç ettirilir (hub.py, `_eski_dosyalari_goc`); burada yalnız tablolar var.
_V4: Statements = [
    """CREATE TABLE access_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        app_id TEXT NOT NULL,
        tool TEXT NOT NULL,
        category TEXT,
        result_count INTEGER NOT NULL DEFAULT 0,
        outcome TEXT NOT NULL CHECK (outcome IN ('ok', 'reddedildi', 'hata'))
    )""",
    "CREATE INDEX idx_access_ts ON access_log(ts)",
    "CREATE INDEX idx_access_app ON access_log(app_id, ts)",
    """CREATE TABLE oneriler (
        oneri_id TEXT PRIMARY KEY,
        ts TEXT NOT NULL,
        app_id TEXT NOT NULL,
        statement TEXT NOT NULL,
        category TEXT NOT NULL,
        fact_key TEXT,
        kanit_event_ids TEXT NOT NULL,
        guven REAL NOT NULL CHECK (guven >= 0 AND guven <= 1),
        durum TEXT NOT NULL DEFAULT 'bekliyor' CHECK (
            durum IN ('bekliyor', 'onaylandi', 'duzeltildi', 'reddedildi', 'hic_dogru_degil')),
        ifade_hash TEXT NOT NULL,
        karar_ts TEXT,
        duzeltilmis_ifade TEXT,
        fact_id TEXT
    )""",
    "CREATE INDEX idx_oneri_durum ON oneriler(durum, ts)",
    "CREATE INDEX idx_oneri_hash ON oneriler(ifade_hash)",
    """CREATE TABLE bastirilan (
        ifade_hash TEXT PRIMARY KEY,
        ts TEXT NOT NULL,
        category TEXT
    )""",
]

_GERI_DOLDURMA_GRUP = 5000


def geri_isaretle(conn: sqlite3.Connection, siniflandirici=None, progress=None) -> tuple[int, int]:
    """Tüm olayların `onem` ve `hassas_konu` değerlerini güncel kural/listeyle yeniden hesaplar.

    Satırları `seq` sırasıyla gruplar halinde gezer (bellek sabit; 1 milyon satırda da şişmez),
    yalnız değişen satırları günceller. (incelenen, değişen) döner. Çağıran işlemi yönetir.
    """
    from . import hassas as _hassas
    from .onem import SOHBET_KIND, onem_hesapla

    sn = siniflandirici or _hassas.paket_siniflandirici()
    son = 0
    incelenen = degisen = 0
    while True:
        rows = conn.execute(
            "SELECT seq, kind, category, CASE WHEN kind = ? THEN payload END, text, onem, hassas_konu "
            "FROM events WHERE seq > ? ORDER BY seq LIMIT ?", (SOHBET_KIND, son, _GERI_DOLDURMA_GRUP),
        ).fetchall()
        if not rows:
            return incelenen, degisen
        guncel = []
        for seq, kind, cat, payload, text, onem, hk in rows:
            try:
                pl = json.loads(payload) if payload else {}
            except ValueError:
                pl = {}
            yeni_onem = onem_hesapla(kind, cat, pl)
            yeni_hk = _hassas.isaret(sn.konular(text))
            if yeni_onem != onem or yeni_hk != hk:
                guncel.append((yeni_onem, yeni_hk, seq))
        if guncel:
            conn.executemany("UPDATE events SET onem = ?, hassas_konu = ? WHERE seq = ?", guncel)
        incelenen += len(rows)
        degisen += len(guncel)
        son = rows[-1][0]
        if progress:
            progress(incelenen)


def _v5(conn: sqlite3.Connection, veri_klasoru=None) -> None:
    """v5: `events.onem`, `events.hassas_konu`, `konu_izinleri`; mevcut olaylar geriye dönük işaretlenir."""
    from . import hassas as _hassas

    cols = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
    if "onem" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN onem INTEGER NOT NULL DEFAULT 1 CHECK (onem IN (0, 1, 2))")
    if "hassas_konu" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN hassas_konu TEXT")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS konu_izinleri (
        app_id TEXT NOT NULL REFERENCES app_keys(app_id),
        konu TEXT NOT NULL,
        granted_at TEXT NOT NULL,
        expires_at TEXT,
        PRIMARY KEY (app_id, konu)
    )""")
    sn, _uyari = _hassas.yukle(veri_klasoru)
    geri_isaretle(conn, sn)


def v5_adimi(veri_klasoru=None):
    """Veri klasöründeki ek listeyi de kullanan v5 adımı (Hub açılışı bunu verir)."""
    return lambda conn: _v5(conn, veri_klasoru)


def _v6(conn: sqlite3.Connection) -> None:
    """v6: telefon aktarımı (docs/AKTARIM.md). `devices`e eşleştirme alanları, `aktarim_dosyalari` tablosu.
    Yalnız eklemeli; yeniden çalıştırılırsa bozulmaz."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(devices)")}
    if "key_hash" not in cols:
        conn.execute("ALTER TABLE devices ADD COLUMN key_hash TEXT")
    if "paired_at" not in cols:
        conn.execute("ALTER TABLE devices ADD COLUMN paired_at TEXT")
    if "revoked" not in cols:
        conn.execute("ALTER TABLE devices ADD COLUMN revoked INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS aktarim_dosyalari (
        device_id TEXT NOT NULL,
        dosya_id TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        kayit_sayisi INTEGER NOT NULL,
        alindi TEXT NOT NULL,
        PRIMARY KEY (device_id, dosya_id)
    )""")


MIGRATIONS: dict[int, Statements | Callable[[sqlite3.Connection], None]] = {
    1: _V1, 2: _V2, 3: _V3, 4: _V4, 5: _v5, 6: _v6,
}
SCHEMA_VERSION = max(MIGRATIONS)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(
    conn: sqlite3.Connection,
    *,
    migrations: Mapping[int, Statements | Callable[[sqlite3.Connection], None]] = MIGRATIONS,
) -> tuple[int, int]:
    """Bağlantıyı en yeni sürüme getirir. `conn` isolation_level=None olmalı.

    (eski_sürüm, yeni_sürüm) döner. Veritabanı daha yeniyse SchemaTooNew.
    """
    target = max(migrations)
    old = current_version(conn)
    if old > target:
        raise SchemaTooNew(
            f"Veritabanı şema sürümü {old}, bu program en çok {target} sürümünü bilir. "
            "Programı güncelleyin."
        )
    for version in sorted(v for v in migrations if v > old):
        step = migrations[version]
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Başka süreç bu arada göç ettirmiş olabilir.
            if current_version(conn) >= version:
                conn.execute("ROLLBACK")
                continue
            if callable(step):
                step(conn)
            else:
                for stmt in step:
                    conn.execute(stmt)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, _now()),
            )
            conn.execute(f"PRAGMA user_version = {int(version)}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    return old, current_version(conn)
