"""Madde 13: v4 şemalı veri klasörü Windows uygulaması çekirdeğiyle açılınca v5'e göç eder."""
import sqlite3

from kimlikcore import schema
from kimlikwin.cekirdek import Uygulama


def _v4_kur(root):
    root.mkdir(parents=True)
    c = sqlite3.connect(root / "kimlik.db", isolation_level=None)
    c.execute("PRAGMA journal_mode = WAL")
    schema.migrate(c, migrations={v: m for v, m in schema.MIGRATIONS.items() if v <= 4})
    assert c.execute("PRAGMA user_version").fetchone()[0] == 4
    assert "onem" not in {r[1] for r in c.execute("PRAGMA table_info(events)")}
    c.execute("INSERT INTO sources VALUES ('s1', 'eski', '1', NULL, '2026-01-01T00:00:00Z', NULL, NULL)")
    for i, metin in enumerate(["doktor randevusu yarin", "sade not"]):
        c.execute(
            "INSERT INTO events(event_id, event_key, source_id, ts, kind, category, payload, text, "
            "schema_version, hidden, ingested_at) VALUES (?, ?, 's1', '2026-01-01T00:00:00Z', 'k', "
            "'notlar', '{}', ?, 4, 0, '2026-01-01T00:00:00Z')", (f"id{i}", f"key{i}", metin))
    c.close()


def test_v4_klasor_uygulamada_v5e_goc_eder(tmp_path):
    veri = tmp_path / "veri"
    _v4_kur(veri)
    uyg = Uygulama(veri, ayar_dizin=tmp_path / "ayar", claude_yolu=lambda: None)
    try:
        c = uyg.hub._conn
        assert c.execute("PRAGMA user_version").fetchone()[0] == schema.SCHEMA_VERSION == 5
        satirlar = {r[0]: r[1:] for r in c.execute("SELECT event_id, onem, hassas_konu FROM events")}
        assert "saglik" in (satirlar["id0"][1] or "")
        assert not satirlar["id1"][1]
        assert satirlar["id0"][0] in (0, 1, 2)
    finally:
        uyg.kapat()
