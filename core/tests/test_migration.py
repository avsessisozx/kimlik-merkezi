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


# v2'de eklenen tabloların donmuş kopyası (göç kodundan bağımsız); permissions eski CHECK ile.
V2_DDL = [
    "CREATE TABLE devices (device_id TEXT PRIMARY KEY, name TEXT NOT NULL, platform TEXT, created TEXT NOT NULL, last_seen TEXT)",
    """CREATE TABLE facts (fact_id TEXT PRIMARY KEY, statement TEXT NOT NULL, source_id TEXT REFERENCES sources(source_id),
        date TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('beyan_edilen','dosyadan_alinan','cikarilan','eskimis')),
        valid_from TEXT, valid_until TEXT, category TEXT NOT NULL CHECK (
        category IN ('kimlik','tercihler','ilgi','diger','cihazlar','projeler','is')),
        fact_key TEXT, hidden INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)), updated TEXT)""",
    "CREATE INDEX idx_facts_cat_key ON facts(category, fact_key)",
    "CREATE INDEX idx_facts_source ON facts(source_id)",
    """CREATE TABLE contradictions (contradiction_id TEXT PRIMARY KEY, old_fact_id TEXT NOT NULL REFERENCES facts(fact_id),
        new_fact_id TEXT NOT NULL REFERENCES facts(fact_id), category TEXT NOT NULL, fact_key TEXT, opened TEXT NOT NULL,
        resolved_at TEXT, chosen_fact_id TEXT REFERENCES facts(fact_id))""",
    """CREATE TABLE app_keys (app_id TEXT PRIMARY KEY, name TEXT NOT NULL, key_hash TEXT NOT NULL UNIQUE,
        created TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0 CHECK (revoked IN (0, 1)))""",
    """CREATE TABLE permissions (app_id TEXT NOT NULL REFERENCES app_keys(app_id), category TEXT NOT NULL,
        granted_at TEXT NOT NULL, expires_at TEXT,
        confirmed_sensitive INTEGER NOT NULL DEFAULT 0 CHECK (confirmed_sensitive IN (0, 1)),
        PRIMARY KEY (app_id, category),
        CHECK (category NOT IN ('eposta', 'mesaj', 'konum') OR confirmed_sensitive = 1))""",
]


def make_v1(root, n=10, upto=1):
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
    if upto >= 2:
        for stmt in V2_DDL:
            c.execute(stmt)
        c.execute("INSERT INTO schema_migrations VALUES (2, '2026-01-02T00:00:00Z')")
        c.execute("INSERT INTO app_keys VALUES ('a1', 'Claude', 'h1', '2026-01-02T00:00:00Z', 0)")
        c.execute("INSERT INTO permissions VALUES ('a1', 'notlar', '2026-01-02T00:00:00Z', NULL, 0)")
        c.execute("INSERT INTO permissions VALUES ('a1', 'eposta', '2026-01-02T00:00:00Z', '2027-01-01T00:00:00Z', 1)")
        c.execute("INSERT INTO facts(fact_id, statement, date, status, category) VALUES ('f1','Bilgi','2026-01-02','beyan_edilen','kimlik')")
        c.execute("PRAGMA user_version = 2")
    c.close()


def test_eski_semadan_yeniye_goc(root):
    make_v1(root)
    # Salt okunur açış, eski sürümü açıkça reddeder.
    with pytest.raises(SchemaTooOld):
        Hub.open(root, write=False)
    with Hub.open(root, write=True) as h:
        assert h.schema_version == SCHEMA_VERSION == 3
        names = {r[0] for r in h._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"facts", "contradictions", "app_keys", "permissions", "devices"} <= names
        assert not {"review_queue", "suppressed"} & names
        facts_cols = {r[1] for r in h._conn.execute("PRAGMA table_info(facts)")}
        assert "confidence" not in facts_cols
        assert [r[0] for r in h._conn.execute("SELECT version FROM schema_migrations ORDER BY 1")] == [1, 2, 3]
        # eski veri bozulmadan açılır ve aranır
        assert h.summary()["counts"]["event"] == 10
        assert len(h.search("ISIK", limit=50)) == 10
        assert h.get_event("id3").schema_version == 1
        # yeni tablolar kullanılabilir
        h._conn.execute(
            "INSERT INTO facts(fact_id, statement, date, status, category) VALUES ('f1','x','2026-01-01','cikarilan','is')"
        )
    with Hub.open(root, write=False) as r:  # artık salt okunur da açılır
        assert r.schema_version == 3


def test_goc_idempotent_ve_yeniden_acilis(root):
    with Hub.open(root, write=True):
        pass
    with Hub.open(root, write=True) as h:
        assert [r[0] for r in h._conn.execute("SELECT version FROM schema_migrations ORDER BY 1")] == [1, 2, 3]


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
    assert schema.current_version(c) == 3

    def bozuk(conn):
        conn.execute("CREATE TABLE yeni_tablo (a INTEGER)")
        raise RuntimeError("göç patladı")

    with pytest.raises(RuntimeError):
        schema.migrate(c, migrations={**schema.MIGRATIONS, 4: bozuk})
    assert schema.current_version(c) == 3
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


def test_v2den_v3e_sohbet_gocu(root):
    make_v1(root, upto=2)
    # eski şemada 'sohbet' hassas sayılmaz: onaysız yazılabilirdi (v3 bunu kapatır)
    with Hub.open(root, write=True) as h:
        assert h.schema_version == 3
        assert [r[0] for r in h._conn.execute("SELECT version FROM schema_migrations ORDER BY 1")] == [1, 2, 3]
        # mevcut veri bozulmadan taşındı
        assert h.query("SELECT app_id, category, expires_at, confirmed_sensitive FROM permissions ORDER BY category") == [
            ("a1", "eposta", "2027-01-01T00:00:00Z", 1), ("a1", "notlar", None, 0)]
        assert h.query("SELECT count(*) FROM events") == [(10,)] and h.query("SELECT count(*) FROM facts") == [(1,)]
        assert len(h.search("ISIK", limit=50)) == 10
        assert not h.query("PRAGMA foreign_key_check")
        assert h.query("SELECT 1 FROM sqlite_master WHERE name = 'permissions_yeni'") == []
        # yeni kısıt
        with pytest.raises(sqlite3.IntegrityError):
            with h.transaction() as c:
                c.execute("INSERT INTO permissions(app_id, category, granted_at) VALUES ('a1','sohbet','2026-01-01T00:00:00Z')")
        with h.transaction() as c:
            c.execute("INSERT INTO permissions(app_id, category, granted_at, confirmed_sensitive) "
                      "VALUES ('a1','sohbet','2026-01-01T00:00:00Z', 1)")
        with pytest.raises(sqlite3.IntegrityError):  # eposta kuralı korunuyor
            with h.transaction() as c:
                c.execute("INSERT INTO permissions(app_id, category, granted_at) VALUES ('a1','mesaj','2026-01-01T00:00:00Z')")
        # yeni tabloda dış anahtar işliyor
        with pytest.raises(sqlite3.IntegrityError):
            with h.transaction() as c:
                c.execute("INSERT INTO permissions(app_id, category, granted_at) VALUES ('yok','notlar','2026-01-01T00:00:00Z')")


def test_sohbet_kategorisi_sabitleri():
    from kimlikcore import Category
    assert "sohbet" in Category.ALL and "sohbet" in Category.SENSITIVE and Category.SOHBET == "sohbet"
    assert Category.SENSITIVE == {"eposta", "mesaj", "konum", "sohbet"}


def test_sohbet_olayi_eklenir_aranir_disa_icine_aktarilir(hub, tmp_path):
    from kimlikcore import EventIn
    sid = hub.add_source("sohbet-deneme", "1", None)
    hub.add_events(sid, [EventIn(event_key=f"s{i}", ts="2026-06-01T10:00:00Z", kind="sohbet.mesaj", category="sohbet",
                                 payload={"rol": "kullanici", "i": i}, text=f"Işık hakkında sohbet {i}") for i in range(3)])
    assert len(hub.search("ISIK", categories=["sohbet"])) == 3
    assert len(hub.timeline(categories=["sohbet"])) == 3 and hub.timeline(categories=["notlar"]) == []
    with hub.transaction() as c:
        c.execute("INSERT INTO app_keys(app_id, name, key_hash, created) VALUES ('a','x','h','2026-01-01T00:00:00Z')")
        c.execute("INSERT INTO permissions(app_id, category, granted_at, confirmed_sensitive) VALUES ('a','sohbet','2026-01-01T00:00:00Z',1)")
    before = hub.summary()
    out = tmp_path / "s.jsonl"
    hub.export_jsonl(out)
    with Hub.open(tmp_path / "yeni", write=True) as h2:
        res = h2.import_jsonl(out)
        assert res.verified and h2.summary() == before
        assert len(h2.search("ışık", categories=["sohbet"])) == 3
        assert h2.query("SELECT category FROM permissions") == [("sohbet",)]
