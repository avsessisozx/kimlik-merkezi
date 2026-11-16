"""Şema v6: telefon aktarımı (cihaz anahtarı özeti, aktarim_dosyalari), göç, dışa/içe aktarım uyumu."""
import hashlib
import json
import sqlite3

import pytest

from kimlikcore import EventIn, Hub, schema, transfer

from test_migration import make_v1

DEV = "11111111-1111-4111-8111-111111111111"
H1 = hashlib.sha256(b"anahtar-1").hexdigest()
H2 = hashlib.sha256(b"anahtar-2").hexdigest()


def test_v5ten_v6ya_goc(root):
    make_v1(root, upto=2)
    c = sqlite3.connect(root / "kimlik.db", isolation_level=None)
    schema.migrate(c, migrations={k: v for k, v in schema.MIGRATIONS.items() if k <= 5})
    c.execute("INSERT INTO devices(device_id, name, platform, created) VALUES ('eski', 'Eski', 'windows', '2026-01-01T00:00:00Z')")
    assert schema.current_version(c) == 5
    assert "key_hash" not in {r[1] for r in c.execute("PRAGMA table_info(devices)")}
    c.close()
    with Hub.open(root, write=True) as h:
        assert h.schema_version == 6
        cols = {r[1] for r in h._conn.execute("PRAGMA table_info(devices)")}
        assert {"key_hash", "paired_at", "revoked"} <= cols
        assert h.query("SELECT 1 FROM sqlite_master WHERE name = 'aktarim_dosyalari'") == [(1,)]
        # eski cihaz bozulmadan; eşleşmemiş cihaz doğrulanamaz
        (d,) = h.cihazlar()
        assert d["device_id"] == "eski" and d["revoked"] is False and d["eslesmis"] is False
        assert h.cihaz_dogrula("eski", H1) is False
        assert h.summary()["counts"]["event"] == 10


def test_v6_idempotent(tmp_path):
    c = sqlite3.connect(tmp_path / "x.db", isolation_level=None)
    schema.migrate(c)
    schema._v6(c)
    assert schema.current_version(c) == 6


def test_basarisiz_v6_gocu_geri_alinir(tmp_path):
    c = sqlite3.connect(tmp_path / "x.db", isolation_level=None)
    schema.migrate(c, migrations={k: v for k, v in schema.MIGRATIONS.items() if k <= 5})

    def bozuk(conn):
        schema._v6(conn)
        raise RuntimeError("v6 patladı")

    with pytest.raises(RuntimeError):
        schema.migrate(c, migrations={**schema.MIGRATIONS, 6: bozuk})
    assert schema.current_version(c) == 5
    assert "key_hash" not in {r[1] for r in c.execute("PRAGMA table_info(devices)")}
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='aktarim_dosyalari'").fetchone() is None
    schema.migrate(c)
    assert schema.current_version(c) == 6


def test_cihaz_yontemleri(hub):
    hub.cihaz_ekle(DEV, "Telefon", "android", H1)
    assert hub.cihaz_dogrula(DEV, H1) is True
    assert hub.cihaz_dogrula(DEV, H2) is False
    assert hub.cihaz_dogrula("yok", H1) is False
    (d,) = hub.cihazlar()
    assert d["paired_at"] and d["revoked"] is False and "key_hash" not in d
    hub.cihaz_goruldu(DEV, "2026-02-01T00:00:00Z")
    assert hub.cihazlar()[0]["last_seen"] == "2026-02-01T00:00:00Z"
    assert hub.cihaz_iptal(DEV) is True
    assert hub.cihaz_dogrula(DEV, H1) is False and hub.cihazlar()[0]["revoked"] is True
    assert hub.cihaz_iptal("yok") is False
    hub.cihaz_ekle(DEV, "Telefon", "android", H2)   # yeniden eşleşme iptali kaldırır
    assert hub.cihaz_dogrula(DEV, H2) is True and hub.cihaz_dogrula(DEV, H1) is False


def test_aktarim_dosyasi(hub):
    assert hub.aktarim_dosyasi_var(DEV, "f1") is None
    hub.aktarim_dosyasi_kaydet(DEV, "f1", "ab" * 32, 7)
    hub.aktarim_dosyasi_kaydet(DEV, "f1", "cd" * 32, 9)   # ikinci kayıt ilkini değiştirmez
    assert hub.aktarim_dosyasi_var(DEV, "f1") == "ab" * 32
    assert hub.aktarim_dosyasi_var("baska", "f1") is None
    assert hub.query("SELECT kayit_sayisi FROM aktarim_dosyalari") == [(7,)]


def test_dis_ice_aktarim_gidis_donus(root, tmp_path):
    with Hub.open(root, write=True) as h:
        h.cihaz_ekle(DEV, "Telefon", "android", H1)
        h.aktarim_dosyasi_kaydet(DEV, "f1", "ab" * 32, 3)
        out = tmp_path / "d.jsonl"
        h.export_jsonl(out)
        ozet = h.summary()
    with Hub.open(tmp_path / "yeni", write=True) as h2:
        r = h2.import_jsonl(out)
        assert r.verified and r.counts["aktarim_dosyasi"] == 1
        assert h2.summary() == ozet
        assert h2.cihaz_dogrula(DEV, H1) and h2.aktarim_dosyasi_var(DEV, "f1") == "ab" * 32


def _eski_dosya(src, dst):
    """v5 biçimi: devices'ta yeni alan yok, aktarim_dosyasi türü yok; footer buna göre yeniden hesaplanır."""
    acc = transfer._Acc()
    lines = []
    for ln in open(src, encoding="utf-8"):
        rec = json.loads(ln)
        t = rec["t"]
        if t == "aktarim_dosyasi":
            continue
        if t == "header":
            rec["schema_version"] = 5
        if t == "device":
            for k in ("key_hash", "paired_at", "revoked"):
                rec.pop(k)
        if t == "footer":
            res = acc.result()
            rec["counts"] = {k: v for k, v in res["counts"].items() if k != "aktarim_dosyasi"}
            rec["digests"] = {k: v for k, v in res["digests"].items() if k != "aktarim_dosyasi"}
        elif t != "header":
            body = {k: v for k, v in rec.items() if k != "t"}
            acc.add(t, body)
        lines.append(json.dumps(rec, ensure_ascii=False))
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_eski_v5_dosyasi_ice_alinir(root, tmp_path):
    with Hub.open(root, write=True) as h:
        h.cihaz_ekle(DEV, "Telefon", "android", H1)
        h.aktarim_dosyasi_kaydet(DEV, "f1", "ab" * 32, 3)
        h.add_source("t", "1", None)
        out = tmp_path / "d.jsonl"
        h.export_jsonl(out)
    eski = tmp_path / "eski.jsonl"
    _eski_dosya(out, eski)
    with Hub.open(tmp_path / "yeni", write=True) as h2:
        r = h2.import_jsonl(eski)
        assert r.counts["device"] == 1 and r.counts["aktarim_dosyasi"] == 0
        (d,) = h2.cihazlar()
        assert d["revoked"] is False and d["eslesmis"] is False   # eski dosyada anahtar özeti yok
