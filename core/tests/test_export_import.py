import json
import shutil

import pytest

from kimlikcore import EventIn, FormatError, Hub, HubNotEmptyError

from util import known_events


def populate(hub, tmp_path):
    f = tmp_path / "ornek.txt"
    f.write_text("ham içerik İstanbul", encoding="utf-8")
    s1 = hub.add_source("sentetik", "1", None)
    hub.store_raw(s1, f)
    hub.add_events(s1, known_events(20))
    s2 = hub.add_source("diger", "2", None)
    hub.add_events(s2, [EventIn(event_key=f"d{i}", ts="2026-05-01T00:00:00Z", kind="x", category="video",
                                payload={"iç": {"liste": [1, 2.5, None, True]}, "i": i}, text=f"video {i} şarkı")
                        for i in range(7)])
    hub.hide_event(hub.search("bulgu003zz")[0].event_id, "deneme")
    s3 = hub.add_source("kaldirilacak", "1", None)
    hub.add_events(s3, [EventIn(event_key="k1", ts="2026-05-02T00:00:00Z", kind="x", category="kod", text="gizlenecek")])
    hub.remove_source(s3, "yanlış")
    c = hub._conn
    c.execute("INSERT INTO devices(device_id, name, platform, created) VALUES ('d1','Telefon','android','2026-01-01T00:00:00Z')")
    c.execute("INSERT INTO facts(fact_id, statement, source_id, date, status, category, fact_key) "
              "VALUES ('f1','Merhaba',?, '2026-01-01','dosyadan_alinan','kimlik','ad')", (s1,))
    c.execute("INSERT INTO app_keys(app_id, name, key_hash, created) VALUES ('a1','Claude','abc','2026-01-01T00:00:00Z')")
    c.execute("INSERT INTO permissions(app_id, category, granted_at) VALUES ('a1','notlar','2026-01-01T00:00:00Z')")
    return s1


def test_disa_aktar_ice_aktar_esit(hub, tmp_path):
    populate(hub, tmp_path)
    before = hub.summary()
    out = tmp_path / "yedek.jsonl"
    r = hub.export_jsonl(out)
    assert r.counts["event"] == 28 and r.counts["source"] == 3
    assert not (tmp_path / "yedek.jsonl.part").exists()
    lines = out.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["t"] == "header" and json.loads(lines[-1])["t"] == "footer"

    new_root = tmp_path / "yeni"
    shutil.copytree(hub.root / "arsiv", new_root / "arsiv")
    with Hub.open(new_root, write=True) as h2:
        res = h2.import_jsonl(out)
        assert res.verified and res.raw_missing == 0
        after = h2.summary()
        assert after == before
        assert after["counts"]["event"] == 28
        assert len(h2.search("gezisi", limit=100)) == 19  # biri gizli
        assert h2.search("gizlenecek") == []
        assert h2.verify_archive() == []
        # gizli bayrağı korundu, olay kimlikleri aynı
        hid = [e for e in h2.timeline(limit=100)]
        assert len(hid) == 26
    # yeniden dışa aktarım içerik olarak aynı özet
    with Hub.open(new_root, write=False) as r2:
        out2 = tmp_path / "yedek2.jsonl"
        r2.export_jsonl(out2)
        assert json.loads(out2.read_text(encoding="utf-8").splitlines()[-1]) == json.loads(lines[-1])


def test_ham_dosya_yoksa_uyari_sayisi(hub, tmp_path):
    populate(hub, tmp_path)
    out = tmp_path / "e.jsonl"
    hub.export_jsonl(out)
    with Hub.open(tmp_path / "yeni2", write=True) as h2:
        res = h2.import_jsonl(out)
        assert res.raw_missing == 1 and res.verified


def test_bos_olmayan_hub_reddeder(hub, tmp_path):
    populate(hub, tmp_path)
    out = tmp_path / "e.jsonl"
    hub.export_jsonl(out)
    with pytest.raises(HubNotEmptyError):
        hub.import_jsonl(out)


def test_bozuk_ya_da_kesik_dosya_hicbir_sey_birakmaz(hub, tmp_path):
    populate(hub, tmp_path)
    out = tmp_path / "e.jsonl"
    hub.export_jsonl(out)
    lines = out.read_text(encoding="utf-8").splitlines(keepends=True)
    cases = {
        "kesik": lines[:-1],  # footer yok
        "eksik_satir": lines[:5] + lines[6:],  # özet uyuşmaz
        "bozuk_json": lines[:3] + ["{bozuk\n"] + lines[3:],
        "header_yok": lines[1:],
    }
    for name, content in cases.items():
        bad = tmp_path / f"{name}.jsonl"
        bad.write_text("".join(content), encoding="utf-8")
        with Hub.open(tmp_path / f"h_{name}", write=True) as h2:
            with pytest.raises(FormatError):
                h2.import_jsonl(bad)
            assert h2.summary()["counts"]["event"] == 0 and h2.summary()["counts"]["source"] == 0
            assert h2.search("gezisi") == []


def test_kalici_silinen_disa_aktarilmaz(hub, tmp_path):
    s1 = populate(hub, tmp_path)
    hub.purge_source(s1)
    out = tmp_path / "e.jsonl"
    hub.export_jsonl(out)
    text = out.read_text(encoding="utf-8")
    assert "bulgu" not in text and "ham içerik" not in text
    recs = [json.loads(x) for x in text.splitlines()]
    purged = [r for r in recs if r["t"] == "tombstone" and r["kind"] == "source_purged"]
    assert len(purged) == 1 and purged[0]["count"] == 20 and purged[0]["reason"] is None
    # silindi kaydı geri yüklemeden sonra da hash'i tanır
    with Hub.open(tmp_path / "yeni", write=True) as h2:
        h2.import_jsonl(out)
        assert purged[0]["file_sha256"]
        assert h2.previously_purged(purged[0]["file_sha256"]).count == 20
