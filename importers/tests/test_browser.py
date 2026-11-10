"""Yerel tarayıcı geçmişi: sentetik SQLite dosyalarıyla (Windows yolları mantık olarak sınanır)."""
from __future__ import annotations

import shutil
import sqlite3
from collections import Counter
from pathlib import Path

import pytest
from conftest import FIX, count_events
from kimlikcore import FormatError
from kimlikimport import registry
from kimlikimport.base import ImportFormatError
from kimlikimport.browser import WEBKIT_OFFSET_US, BrowserHistory, default_locations
from kimlikimport.run import run

U = 1_000_000


def make_chromium(path: Path, *, extra_bad: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript("""
      CREATE TABLE urls(id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INT, typed_count INT,
                        last_visit_time INT, hidden INT);
      CREATE TABLE visits(id INTEGER PRIMARY KEY, url INT, visit_time INT, from_visit INT, transition INT,
                          segment_id INT, visit_duration INT);
    """)
    urls = [(1, "https://example.test/bir", "Ornek Sayfa Bir"), (2, "https://example.test/iki", "Ornek Sayfa Iki"),
            (3, "https://www.google.com/maps/place/Ornek/@40.987654,28.987654,17z", "Ornek Harita"),
            (4, "https://example.test/dort", "Dort")]
    con.executemany("INSERT INTO urls(id,url,title) VALUES (?,?,?)", urls)
    t = lambda unix_us: unix_us + WEBKIT_OFFSET_US
    visits = [(1, 1, t(1709287200 * U), 0), (2, 2, t(1709290800 * U), 1 | 0x20000000),
              (3, 3, t(1709298000 * U), 0), (4, 4, t(1709301600 * U), 8)]
    if extra_bad:
        visits.append((5, 4, 0, 0))
    con.executemany("INSERT INTO visits(url,visit_time,transition) SELECT ?,?,? ", [(a, b, c) for _, a, b, c in visits])
    con.commit()
    con.close()
    return path


def make_firefox(path: Path, *, wal: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA wal_autocheckpoint=0")
    con.executescript("""
      CREATE TABLE moz_places(id INTEGER PRIMARY KEY, url TEXT, title TEXT, description TEXT, visit_count INT);
      CREATE TABLE moz_historyvisits(id INTEGER PRIMARY KEY, from_visit INT, place_id INT, visit_date INT, visit_type INT);
    """)
    con.executemany("INSERT INTO moz_places(id,url,title) VALUES (?,?,?)",
                    [(1, "https://example.test/ff1", "Firefox Bir"), (2, "https://example.test/ff2", "Firefox Iki")])
    con.executemany("INSERT INTO moz_historyvisits(place_id,visit_date,visit_type) VALUES (?,?,1)",
                    [(1, 1709287200 * U), (2, 1709290800 * U), (1, 1709294400 * U)])
    con.commit()
    return con  # WAL testinde bağlantı açık bırakılır


def test_chromium_kayit_sayisi_ve_konum(hub, tmp_path):
    h = make_chromium(tmp_path / "Local/Google/Chrome/User Data/Default/History")
    r = run(hub, h)
    assert r.importer == "browser_history" and (r.parsed, r.added) == (5, 5)
    assert r.skipped == {"chrome: ziyaret zamanı/url geçersiz": 1}
    ev = hub.timeline(limit=50)
    assert Counter(e.kind for e in ev) == {"chrome.ziyaret": 4, "google.konum": 1}
    assert Counter(e.category for e in ev) == {"tarama": 4, "konum": 1}
    assert all("40.987654" not in str(e.payload) for e in ev if e.category == "tarama")
    tr = {e.payload["baslik"]: e.payload["gecis"] for e in ev if e.kind == "chrome.ziyaret"}
    assert tr["Ornek Sayfa Iki"] == "TYPED" and tr["Dort"] == "RELOAD"
    assert next(e for e in ev if e.payload.get("baslik") == "Ornek Sayfa Bir").ts == "2024-03-01T10:00:00Z"
    assert hub.search("Ornek Sayfa Iki", categories=["tarama"])


def test_orijinal_degismez_ve_ham_arsiv(hub, tmp_path):
    h = make_chromium(tmp_path / "History")
    before = h.read_bytes()
    mt = h.stat().st_mtime_ns
    r = run(hub, h)
    assert h.read_bytes() == before and h.stat().st_mtime_ns == mt
    assert not list(tmp_path.glob("History-*"))  # yan dosya bırakılmadı
    assert len(r.raw_files) == 1 and hub.verify_archive() == []
    assert (hub.root / r.raw_files[0].path).read_bytes() == before


def test_iki_kez_alim_tekrarsiz(hub, tmp_path):
    h = make_chromium(tmp_path / "History")
    a = run(hub, h)
    b = run(hub, h)
    assert b.source_id == a.source_id and (b.added, b.duplicate) == (0, 5)
    assert count_events(hub) == 5


def test_takeout_ile_ayni_ziyaret_tekrar_sayilmaz(hub, tmp_path):
    run(hub, make_chromium(tmp_path / "History"))
    r = run(hub, FIX / "takeout_eski_chrome")  # Takeout'ta aynı üç ziyaret (bir, iki, harita) var
    assert r.duplicate == 4  # bir + iki + harita ziyareti + harita konumu
    assert r.added == 1


def test_firefox_wal_dahil(hub, tmp_path):
    p = tmp_path / "Roaming/Mozilla/Firefox/Profiles/abc.default-release/places.sqlite"
    con = make_firefox(p, wal=True)
    try:
        assert Path(str(p) + "-wal").exists() and Path(str(p) + "-wal").stat().st_size > 0
        r = run(hub, p)  # veri henüz yalnız -wal içinde; kopya onu da almalı
    finally:
        con.close()
    assert (r.parsed, r.added) == (3, 3)
    assert {e.kind for e in hub.timeline(limit=10)} == {"firefox.ziyaret"}


def test_profil_klasoru_ve_varsayilan_yollar(hub, tmp_path):
    local, roam = tmp_path / "Local", tmp_path / "Roaming"
    make_chromium(local / "Google/Chrome/User Data/Default/History")
    make_chromium(local / "Microsoft/Edge/User Data/Profile 1/History")
    make_firefox(roam / "Mozilla/Firefox/Profiles/x.default/places.sqlite").close()
    found = default_locations({"LOCALAPPDATA": str(local), "APPDATA": str(roam)})
    assert len(found) == 3 and default_locations({}) == []
    r = run(hub, local / "Microsoft/Edge/User Data")  # User Data klasörü: profilleri bulur
    assert r.added == 5 and {e.kind for e in hub.timeline(limit=20)} == {"edge.ziyaret", "google.konum"}
    rep = BrowserHistory().verify_format(local / "Google/Chrome")
    assert rep.ok and "4 ziyaret" in rep.to_text() or "5 ziyaret" in rep.to_text()


def test_otomatik_tanima(tmp_path):
    h = make_chromium(tmp_path / "History")
    imp, _ = registry.detect_best(h)
    assert imp.name == "browser_history"
    f = make_firefox(tmp_path / "places.sqlite")
    f.close()
    imp, _ = registry.detect_best(tmp_path / "places.sqlite")
    assert imp.name == "browser_history"


def test_kilitli_dosya_anlasilir_hata(hub, tmp_path, monkeypatch):
    h = make_chromium(tmp_path / "History")
    real = shutil.copyfile

    def locked(s, d, *a, **k):
        if Path(s).name == "History":
            raise PermissionError(13, "kilitli")
        return real(s, d, *a, **k)

    monkeypatch.setattr(shutil, "copyfile", locked)
    with pytest.raises(FormatError) as ei:
        run(hub, h, "browser_history")
    assert "kilitli" in str(ei.value) and "Tarayıcıyı" in str(ei.value)
    assert count_events(hub) == 0 and hub.sources() == []


def test_sqlite_degil_ya_da_baska_sema(hub, tmp_path):
    bad = tmp_path / "History"
    bad.write_text("sqlite degil")
    with pytest.raises(FormatError):
        run(hub, bad, "browser_history")
    other = tmp_path / "x" / "History"
    other.parent.mkdir()
    con = sqlite3.connect(other)
    con.execute("CREATE TABLE urls(id INTEGER, url TEXT)")
    con.execute("CREATE TABLE visits(id INTEGER)")
    con.commit()
    con.close()
    with pytest.raises(ImportFormatError) as ei:
        run(hub, other.parent, "browser_history")
    assert "sütunları eksik" in str(ei.value) and "title" in str(ei.value)
