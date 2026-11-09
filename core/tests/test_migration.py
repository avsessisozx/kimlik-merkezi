import json
import sqlite3

import pytest

from kimlikcore import Hub, SCHEMA_VERSION, SchemaTooNew, SchemaTooOld, fold
from kimlikcore import schema

# v1 şemasının donmuş, elle yazılmış kopyası (göç kodundan bağımsız). Persona tabloları yok.
V1_DDL = [
    "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)",
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE sources (source_id TEXT PRIMARY KEY, kind TEXT NOT NULL, version TEXT NOT NULL,
        file_sha256 TEXT, imported_at TEXT NOT NULL, removed_at TEXT, removed_reason TEXT)""",
    "CREATE INDEX idx_sources_sha ON sources(file_sha256)",
    """CREATE TABLE raw_files (raw_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
        name TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
        stored_at TEXT NOT NULL, UNIQUE (source_id, sha256, name))""",
    "CREATE INDEX idx_raw_sha ON raw_files(sha256)",
    """CREATE TABLE events (seq INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, event_key TEXT NOT NULL UNIQUE,
        source_id TEXT NOT NULL REFERENCES sources(source_id), device_id TEXT, ts TEXT NOT NULL, kind TEXT NOT NULL,
        category TEXT NOT NULL, payload TEXT NOT NULL, text TEXT NOT NULL, schema_version INTEGER NOT NULL,
        hidden INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)), ingested_at TEXT NOT NULL)""",
    "CREATE INDEX idx_events_ts ON events(ts)",
    "CREATE INDEX idx_events_cat_ts ON events(category, ts)",
    "CREATE INDEX idx_events_source ON events(source_id)",
    "CREATE VIRTUAL TABLE events_fts USING fts5(text, tokenize = 'unicode61 remove_diacritics 0')",
    """CREATE TABLE tombstones (tombstone_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL CHECK (kind IN ('event_hidden', 'source_removed', 'source_purged')),
        event_id TEXT, source_id TEXT, source_kind TEXT, file_sha256 TEXT, count INTEGER, reason TEXT,
        created TEXT NOT NULL)""",
    "CREATE INDEX idx_tomb_event ON tombstones(event_id)",
    "CREATE INDEX idx_tomb_source ON tombstones(source_id)",
    """CREATE TABLE tombstone_hashes (tombstone_id TEXT NOT NULL REFERENCES tombstones(tombstone_id),
        sha256 TEXT NOT NULL, PRIMARY KEY (tombstone_id, sha256))""",
    "CREATE INDEX idx_tomb_hash ON tombstone_hashes(sha256)",
]


def make_v1(root, n=10):
    root.mkdir(parents=True)
    c = sqlite3.connect(root / "kimlik.db", isolation_level=None)
    c.execute("PRAGMA journal_mode = WAL")
    for s in V1_DDL:
        c.execute(s)
    c.execute("INSERT INTO schema_migrations VALUES (1, '2026-01-01T00:00:00Z')")
    c.execute("INSERT INTO sources VALUES ('s1', 'eski', '1', NULL, '2026-01-01T00:00:00Z', NULL, NULL)")
    for i in range(n):
        text = f"eski kayıt {i} Işık"
        c.execute(
            "INSERT INTO events(event_id, event_key, source_id, ts, kind, category, payload, text, "
            "schema_version, hidden, ingested_at) VALUES (?, ?, 's1', ?, 'k', 'notlar', ?, ?, 1, 0, "
            "'2026-01-01T00:00:00Z')",
            (f"id{i}", f"key{i}", f"2026-01-{i + 1:02d}T00:00:00Z", json.dumps({"i": i}), text),
        )
        c.execute("INSERT INTO events_fts(rowid, text) VALUES (?, ?)", (i + 1, fold(text)))
    c.execute("PRAGMA user_version = 1")
    c.close()


def test_eski_semadan_yeniye_goc(root):
    make_v1(root)
    # Salt okunur açış, eski sürümü açıkça reddeder.
    with pytest.raises(SchemaTooOld):
        Hub.open(root, write=False)
    with Hub.open(root, write=True) as h:
        assert h.schema_version == SCHEMA_VERSION == 2
        names = {r[0] for r in h._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"facts", "contradictions", "app_keys", "permissions", "devices"} <= names
        assert not {"review_queue", "suppressed"} & names
        facts_cols = {r[1] for r in h._conn.execute("PRAGMA table_info(facts)")}
        assert "confidence" not in facts_cols
        assert [r[0] for r in h._conn.execute("SELECT version FROM schema_migrations ORDER BY 1")] == [1, 2]
        # eski veri bozulmadan açılır ve aranır
        assert h.summary()["counts"]["event"] == 10
        assert len(h.search("ISIK", limit=50)) == 10
        assert h.get_event("id3").schema_version == 1
        # yeni tablolar kullanılabilir
        h._conn.execute(
            "INSERT INTO facts(fact_id, statement, date, status, category) VALUES ('f1','x','2026-01-01','cikarilan','is')"
        )
    with Hub.open(root, write=False) as r:  # artık salt okunur da açılır
        assert r.schema_version == 2


def test_goc_idempotent_ve_yeniden_acilis(root):
    with Hub.open(root, write=True):
        pass
    with Hub.open(root, write=True) as h:
        assert [r[0] for r in h._conn.execute("SELECT version FROM schema_migrations ORDER BY 1")] == [1, 2]


def test_daha_yeni_sema_reddedilir(root):
    with Hub.open(root, write=True):
        pass
    c = sqlite3.connect(root / "kimlik.db")
    c.execute("PRAGMA user_version = 99")
    c.commit()
    c.close()
    with pytest.raises(SchemaTooNew):
        Hub.open(root, write=False)
    with pytest.raises(SchemaTooNew):
        Hub.open(root, write=True)
    assert not (root / "hub.lock").exists()  # hata sonrası kilit bırakılmadı


def test_basarisiz_goc_geri_alinir(tmp_path):
    c = sqlite3.connect(tmp_path / "x.db", isolation_level=None)
    schema.migrate(c)
    assert schema.current_version(c) == 2

    def bozuk(conn):
        conn.execute("CREATE TABLE yeni_tablo (a INTEGER)")
        raise RuntimeError("göç patladı")

    with pytest.raises(RuntimeError):
        schema.migrate(c, migrations={**schema.MIGRATIONS, 3: bozuk})
    assert schema.current_version(c) == 2
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='yeni_tablo'").fetchone() is None


def test_hassas_izin_onaysiz_yazilamaz(hub):
    c = hub._conn
    c.execute("INSERT INTO app_keys(app_id, name, key_hash, created) VALUES ('a','x','h','2026-01-01T00:00:00Z')")
    c.execute("INSERT INTO permissions(app_id, category, granted_at) VALUES ('a','notlar','2026-01-01T00:00:00Z')")
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO permissions(app_id, category, granted_at) VALUES ('a','eposta','2026-01-01T00:00:00Z')")
    c.execute("INSERT INTO permissions(app_id, category, granted_at, confirmed_sensitive) "
              "VALUES ('a','eposta','2026-01-01T00:00:00Z', 1)")


def test_fact_durumlari(hub):
    c = hub._conn
    for st in ("beyan_edilen", "dosyadan_alinan", "cikarilan", "eskimis"):
        c.execute("INSERT INTO facts(fact_id, statement, date, status, category) VALUES (?, 's', 'd', ?, 'kimlik')", (st, st))
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO facts(fact_id, statement, date, status, category) VALUES ('z','s','d','baska','kimlik')")
