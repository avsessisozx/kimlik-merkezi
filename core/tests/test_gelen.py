"""Gelen kutusu (çok süreçli kayıtsız yazım), erişim günlüğü/öneri tabloları ve eski oneri.db /
erisim.db göçü. Şifreli klasörde hiçbir dosyada bilinen metin bulunmamalı."""
import json
import os
import sqlite3
import subprocess
import sys

import pytest
from kimlikcore import Hub, SCHEMA_VERSION, donusum, sifreleme as sif
from kimlikcore.gelen import GelenKutusu

GIZLI = "gizlioneriifadesikaplan"


@pytest.fixture(autouse=True)
def sahte(monkeypatch):
    monkeypatch.setattr(sif, "KDF_N", 1 << 4)
    monkeypatch.setenv(sif.ENV_SAHTE, "gelen-testi")
    monkeypatch.delenv(sif.ENV_PAROLA, raising=False)
    sif.saglayici_ayarla(None)


@pytest.fixture
def env_alt(child_env):
    e = dict(child_env)
    e[sif.ENV_SAHTE] = "gelen-testi"
    return e


def dosyalar(root):
    for dp, _d, fs in os.walk(root):
        for f in fs:
            yield os.path.join(dp, f)


def kayit_erisim(i, ts="2026-01-01T00:00:00Z"):
    return {"ts": ts, "app_id": f"app{i}", "tool": "ara", "category": "notlar", "result_count": 1,
            "outcome": "ok"}


def kayit_oneri(n, ifade=GIZLI, h=None):
    return {"oneri_id": f"id-{n}", "ts": f"2026-01-01T00:00:{n:02d}Z", "app_id": "app", "statement": ifade,
            "category": "diger", "fact_key": None, "kanit_event_ids": ["e1"], "guven": 0.5,
            "ifade_hash": h or f"hash-{n}"}


@pytest.mark.parametrize("sifreli", [False, True])
def test_cok_surecli_gelen_yazim_kayip_yok_ve_birlestirme(root, env_alt, sifreli):
    with Hub.open(root, write=True, sifreli=True if sifreli else None) as h:
        assert h.sifreli == sifreli
    kod = r"""
import sys
from kimlikcore.gelen import GelenKutusu
k = GelenKutusu.ac(sys.argv[1])
for i in range(60):
    k.yaz("erisim", {"ts": "2026-01-01T00:00:00Z", "app_id": sys.argv[2], "tool": "ara",
                     "category": "notlar", "result_count": i, "outcome": "ok"})
"""
    ps = [subprocess.Popen([sys.executable, "-c", kod, str(root), f"app{i}"], env=env_alt) for i in range(6)]
    assert all(p.wait(timeout=120) == 0 for p in ps)
    kutu = GelenKutusu.ac(root)
    kayitlar, bozuk = kutu.listele("erisim")
    assert len(kayitlar) == 360 and not bozuk
    if sifreli:  # dosyaların hiçbirinde düz JSON yok
        for _ad, yol in ((a, root / "gelen" / a) for a, _ in kayitlar):
            assert sif.sifreli_mi(yol) and b"app0" not in yol.read_bytes()
    with Hub.open(root, write=True) as h:
        assert h.query("SELECT COUNT(*) FROM access_log")[0][0] == 360
        assert h.gelen.adlar() == []
        assert h.goc_uyarilari == []
        assert {r[0] for r in h.query("SELECT DISTINCT app_id FROM access_log")} == {f"app{i}" for i in range(6)}


def test_eski_oneri_ve_erisim_db_gocu_sifreli_klasorde(root):
    root.mkdir()
    # --- eski şemayı elle kur (v3 öncesi çalışan sürümlerin dosyaları)
    from kimlikcore import schema
    c = sqlite3.connect(root / "oneri.db", isolation_level=None)
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("""CREATE TABLE oneriler (oneri_id TEXT PRIMARY KEY, ts TEXT NOT NULL, app_id TEXT NOT NULL,
        statement TEXT NOT NULL, category TEXT NOT NULL, fact_key TEXT, kanit_event_ids TEXT NOT NULL,
        guven REAL NOT NULL, durum TEXT NOT NULL DEFAULT 'bekliyor', ifade_hash TEXT NOT NULL,
        karar_ts TEXT, duzeltilmis_ifade TEXT, fact_id TEXT)""")
    c.execute("CREATE TABLE bastirilan (ifade_hash TEXT PRIMARY KEY, ts TEXT NOT NULL, category TEXT)")
    c.execute("INSERT INTO oneriler VALUES ('o1','2026-01-01T00:00:00Z','a',?, 'diger', 'k', '[\"e1\"]', 0.7, "
              "'bekliyor', 'h1', NULL, NULL, NULL)", (GIZLI + " bir",))
    c.execute("INSERT INTO oneriler VALUES ('o2','2026-01-01T00:00:01Z','a',?, 'ilgi', NULL, '[\"e2\"]', 0.2, "
              "'reddedildi', 'h2', '2026-01-02T00:00:00Z', NULL, NULL)", (GIZLI + " iki",))
    c.execute("INSERT INTO bastirilan VALUES ('h3','2026-01-03T00:00:00Z','diger')")
    c.close()
    e = sqlite3.connect(root / "erisim.db", isolation_level=None)
    e.execute("PRAGMA journal_mode = WAL")
    e.execute("""CREATE TABLE access_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
        app_id TEXT NOT NULL, tool TEXT NOT NULL, category TEXT, result_count INTEGER NOT NULL DEFAULT 0,
        outcome TEXT NOT NULL)""")
    for i in range(5):
        e.execute("INSERT INTO access_log(ts, app_id, tool, category, result_count, outcome) VALUES "
                  "('2026-01-01T00:00:0%dZ', 'gizliuygulamaadi', 'ara', 'gizlikategori', %d, 'ok')" % (i, i))
    e.close()
    assert (root / "oneri.db-wal").exists() or (root / "oneri.db").exists()
    with Hub.open(root, write=True, sifreli=True) as h:
        assert h.sifreli and h.goc_uyarilari == []
        assert h.schema_version == SCHEMA_VERSION
        assert h.query("SELECT oneri_id, statement, durum, karar_ts FROM oneriler ORDER BY oneri_id") == [
            ("o1", GIZLI + " bir", "bekliyor", None), ("o2", GIZLI + " iki", "reddedildi", "2026-01-02T00:00:00Z")]
        assert h.query("SELECT ifade_hash FROM bastirilan") == [("h3",)]
        assert [r[0] for r in h.query("SELECT result_count FROM access_log ORDER BY id")] == [0, 1, 2, 3, 4]
    for ad in ("oneri.db", "oneri.db-wal", "oneri.db-shm", "erisim.db", "erisim.db-wal", "erisim.db-shm"):
        assert not (root / ad).exists(), ad
    for yol in dosyalar(root):
        b = open(yol, "rb").read()
        assert GIZLI.encode() not in b and b"gizliuygulamaadi" not in b and b"SQLite format" not in b, yol
    # ikinci açılış: yineleme yok
    with Hub.open(root, write=True) as h:
        assert h.query("SELECT COUNT(*) FROM access_log")[0][0] == 5
        assert h.query("SELECT COUNT(*) FROM oneriler")[0][0] == 2


def test_goc_dogrulamasi_tutmazsa_eski_dosya_silinmez(root, monkeypatch):
    root.mkdir()
    e = sqlite3.connect(root / "erisim.db", isolation_level=None)
    e.execute("""CREATE TABLE access_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
        app_id TEXT NOT NULL, tool TEXT NOT NULL, category TEXT, result_count INTEGER NOT NULL DEFAULT 0,
        outcome TEXT NOT NULL)""")
    e.execute("INSERT INTO access_log(ts, app_id, tool, category, result_count, outcome) VALUES "
              "('2026-01-01T00:00:00Z','a','ara','notlar',1,'ok')")
    e.close()
    monkeypatch.setattr(Hub, "_sifreli_dogrula", lambda self: False)
    with Hub.open(root, write=True) as h:
        assert any("erisim.db" in u and "silinmedi" in u for u in h.goc_uyarilari)
    assert (root / "erisim.db").exists()   # veri kaybı yok; sonraki açılışta yeniden denenir
    monkeypatch.undo()
    monkeypatch.setenv(sif.ENV_SAHTE, "gelen-testi")
    with Hub.open(root, write=True) as h:
        assert h.goc_uyarilari == []
        assert h.query("SELECT COUNT(*) FROM access_log")[0][0] == 1   # ikiye katlanmadı
    assert not (root / "erisim.db").exists()


def test_bozuk_gelen_dosyasi_karantinaya_alinir_digerleri_islenir(root):
    with Hub.open(root, write=True):
        pass
    k = GelenKutusu.ac(root)
    k.yaz("erisim", kayit_erisim(1))
    (root / "gelen" / "erisim-00000000000000000001-bozuk.gelen").write_bytes(b"{ bozuk json")
    k.yaz("erisim", {"ts": "t"})  # eksik alan
    with Hub.open(root, write=True) as h:
        assert h.query("SELECT COUNT(*) FROM access_log")[0][0] == 1
    assert sorted(p.name for p in (root / "gelen" / "bozuk").iterdir()).__len__() == 2
    assert GelenKutusu.ac(root).adlar() == []


def test_oneri_birlestirme_yinelenen_hash_ve_bastirilan_atilir(root):
    with Hub.open(root, write=True) as h:
        with h.transaction() as c:
            c.execute("INSERT INTO bastirilan(ifade_hash, ts, category) VALUES ('bastirilmis','t','diger')")
    k = GelenKutusu.ac(root)
    k.yaz("oneri", kayit_oneri(1, h="ayni"))
    k.yaz("oneri", kayit_oneri(2, h="ayni"))      # aynı hash: yinelenen
    k.yaz("oneri", kayit_oneri(3, h="bastirilmis"))
    with Hub.open(root, write=True) as h:
        assert [r[0] for r in h.query("SELECT oneri_id FROM oneriler")] == ["id-1"]
        assert h.gelen.adlar() == []


def test_sifrele_gelen_dosyalari_ve_eski_dbleri_de_sifreler(root):
    with Hub.open(root, write=True, sifreli=False) as h:
        assert not h.sifreli
    GelenKutusu.ac(root).yaz("oneri", kayit_oneri(1))
    e = sqlite3.connect(root / "oneri.db", isolation_level=None)
    e.execute("""CREATE TABLE oneriler (oneri_id TEXT PRIMARY KEY, ts TEXT NOT NULL, app_id TEXT NOT NULL,
        statement TEXT NOT NULL, category TEXT NOT NULL, fact_key TEXT, kanit_event_ids TEXT NOT NULL,
        guven REAL NOT NULL, durum TEXT NOT NULL DEFAULT 'bekliyor', ifade_hash TEXT NOT NULL,
        karar_ts TEXT, duzeltilmis_ifade TEXT, fact_id TEXT)""")
    e.execute("INSERT INTO oneriler VALUES ('eski','2026-01-01T00:00:00Z','a','eskigizliifade','diger',NULL,"
              "'[\"e\"]',0.5,'bekliyor','heski',NULL,NULL,NULL)")
    e.close()
    r = donusum.sifrele(root)
    assert r["gelen_dosya_sifrelendi"] == 1 and r["goc_uyarilari"] == []
    assert not (root / "oneri.db").exists()
    for yol in dosyalar(root):
        b = open(yol, "rb").read()
        assert GIZLI.encode() not in b and b"eskigizliifade" not in b and b"SQLite format" not in b, yol
    with Hub.open(root, write=True) as h:
        assert sorted(r[0] for r in h.query("SELECT oneri_id FROM oneriler")) == ["eski", "id-1"]
    # geri çevirme: gelen dosyaları da çözülür
    GelenKutusu.ac(root).yaz("erisim", kayit_erisim(1))
    donusum.sifreyi_kaldir(root)
    assert GelenKutusu.ac(root).listele("erisim")[0][0][1]["app_id"] == "app1"
