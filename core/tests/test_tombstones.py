import pytest

from kimlikcore import EventIn, Hub, NotFoundError, sha256_file

from util import known_events


def mk(hub, tmp_path, n=20, key_prefix="b"):
    f = tmp_path / "veri.jsonl"
    f.write_text("ham veri\n", encoding="utf-8")
    sha = sha256_file(f)
    sid = hub.add_source("sentetik", "1", sha)
    hub.store_raw(sid, f)
    hub.add_events(sid, known_events(n))
    return sid, f, sha


def test_kaynak_kaldirinca_aramada_gorunmez(hub, tmp_path):
    sid, _f, _ = mk(hub, tmp_path)
    assert len(hub.search("bulgu005zz")) == 1
    assert hub.remove_source(sid, "yanlış dosya") == 20
    assert hub.search("bulgu005zz") == []
    assert hub.search("gezisi", limit=100) == []
    assert hub.timeline(limit=100) == []
    assert hub.remove_source(sid, "tekrar") == 0  # zararsız tekrar
    # satırlar fiziksel silinmedi
    assert hub._conn.execute("SELECT count(*) FROM events").fetchone()[0] == 20
    assert hub._conn.execute("SELECT count(*) FROM events WHERE hidden = 0").fetchone()[0] == 0
    t = hub._conn.execute("SELECT kind, count, reason FROM tombstones").fetchall()
    assert t == [("source_removed", 20, "yanlış dosya")]
    with pytest.raises(NotFoundError):
        hub.add_events(sid, known_events(1))


def test_kayit_gizle(hub, tmp_path):
    mk(hub, tmp_path)
    e = hub.search("bulgu007zz")[0]
    hub.hide_event(e.event_id, "özel")
    hub.hide_event(e.event_id, "özel")  # zararsız tekrar
    assert hub.search("bulgu007zz") == []
    assert len(hub.timeline(limit=100)) == 19
    assert hub.get_event(e.event_id).hidden is True
    assert hub._conn.execute("SELECT count(*) FROM tombstones").fetchone()[0] == 1
    with pytest.raises(NotFoundError):
        hub.hide_event("yok", "x")


def test_kaldirilan_kaynak_yeniden_alininca_gorunur_ama_tek_tek_gizli_kalir(hub, tmp_path):
    sid, f, sha = mk(hub, tmp_path)
    e = hub.search("bulgu007zz")[0]
    hub.hide_event(e.event_id, "özel")
    hub.remove_source(sid, "yanlış")
    sid2 = hub.add_source("sentetik", "1", sha)
    assert sid2 != sid
    r = hub.add_events(sid2, known_events(20))
    assert r.added == 19 and r.duplicate == 1
    assert len(hub.search("gezisi", limit=100)) == 19
    assert hub.search("bulgu007zz") == []
    assert hub._conn.execute("SELECT count(*) FROM events").fetchone()[0] == 20


def test_kalici_silme(hub, tmp_path):
    sid, f, sha = mk(hub, tmp_path)
    keep = hub.add_source("baska", "1", None)
    hub.add_events(keep, [EventIn(event_key="kalan", ts="2026-01-01T00:00:00Z", kind="x",
                                  category="notlar", text="kalan kayıt gezisi")])
    hub.hide_event(hub.search("bulgu002zz")[0].event_id, "özel")
    hub._conn.execute("INSERT INTO facts(fact_id, statement, source_id, date, status, category) "
                      "VALUES ('f1','Bilgi',?,'2026-01-01','dosyadan_alinan','kimlik')", (sid,))
    raw_path = hub.root / hub.raw_files(sid)[0].path
    assert raw_path.exists() and hub.previously_purged(sha) is None

    res = hub.purge_source(sid)
    assert (res.events_deleted, res.raw_files_deleted, res.facts_demoted) == (20, 1, 1)
    assert sha in res.hashes
    assert not raw_path.exists() and not raw_path.parent.exists()
    c = hub._conn
    assert c.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    assert c.execute("SELECT count(*) FROM events_fts").fetchone()[0] == 1  # FTS de temizlendi
    assert hub.search("bulgu002zz") == [] and len(hub.search("gezisi")) == 1
    assert c.execute("SELECT count(*) FROM sources WHERE source_id = ?", (sid,)).fetchone()[0] == 0
    assert c.execute("SELECT count(*) FROM raw_files").fetchone()[0] == 0
    # yalnız içeriksiz "silindi" kaydı kaldı
    rows = c.execute("SELECT kind, source_kind, file_sha256, count, reason FROM tombstones").fetchall()
    assert rows == [("source_purged", "sentetik", sha, 20, None)]
    # persona bilgisi silinmedi, bağı koptu
    assert c.execute("SELECT status, source_id FROM facts").fetchone() == ("eskimis", None)
    # hash'ten tanıma
    info = hub.previously_purged(sha)
    assert info and info.count == 20 and info.source_kind == "sentetik"
    assert hub.previously_purged("0" * 64) is None
    # dosya yeniden alınabilir (karar çağıranda): yeni kaynak açılır, kayıtlar yine görünür
    sid2 = hub.add_source("sentetik", "1", sha)
    assert hub.add_events(sid2, known_events(20)).added == 20
    # veritabanı dosyasında silinen içerik izi kalmadı (secure_delete + checkpoint)
    hub.compact()
    hub.close()
    blob = (hub.root / "kimlik.db").read_bytes()
    assert b"Sentetik not 5" in blob  # yeniden alınan kopya var
    with Hub.open(hub.root, write=True) as h:
        sid3 = h.add_source("x", "1", None)
        h.add_events(sid3, [EventIn(event_key="gizli-iz", ts="2026-01-01T00:00:00Z", kind="x",
                                    category="notlar", text="benzersizizsozcuk")])
        h.purge_source(sid3)
        h.compact()
    blob = (hub.root / "kimlik.db").read_bytes()
    wal = hub.root / "kimlik.db-wal"
    if wal.exists():
        blob += wal.read_bytes()
    assert b"benzersizizsozcuk" not in blob


def test_kalici_silme_baska_kaynak_ayni_arsiv_dosyasini_korur(hub, tmp_path):
    sid, f, sha = mk(hub, tmp_path)
    hub.remove_source(sid, "x")
    sid2 = hub.add_source("sentetik", "1", sha)
    hub.store_raw(sid2, f)
    p = hub.root / hub.raw_files(sid2)[0].path
    hub.purge_source(sid)
    assert p.exists()  # sid2 hâlâ kullanıyor
