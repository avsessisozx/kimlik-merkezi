from datetime import datetime, timedelta, timezone

import pytest

from kimlikcore import Category, EventIn, FormatError, Hub, HubReadOnlyError, NotFoundError, norm_ts

from util import known_events


def test_bilinen_20_kayit_aramada_bulunur(hub):
    sid = hub.add_source("sentetik", "1", None)
    res = hub.add_events(sid, known_events(20))
    assert (res.added, res.duplicate) == (20, 0)
    for i in range(20):
        found = hub.search(f"bulgu{i:03d}zz")
        assert [e.event_key for e in found] == [f"bilinen-{i}"], i
    assert len(hub.timeline(limit=100)) == 20


def test_ayni_olay_anahtari_iki_kez_eklenmez(hub):
    sid = hub.add_source("sentetik", "1", None)
    assert hub.add_events(sid, known_events(20)).added == 20
    r = hub.add_events(sid, known_events(20))
    assert (r.added, r.duplicate) == (0, 20)
    assert hub.summary()["counts"]["event"] == 20


def test_ayni_dosya_iki_kez_alininca_sayi_degismez(hub, tmp_path):
    from kimlikcore import sha256_file
    from kimlikcore.streaming import iter_event_jsonl
    import json

    f = tmp_path / "gir.jsonl"
    f.write_text("\n".join(json.dumps({
        "ts": "2026-02-01T00:00:00Z", "kind": "s.k", "category": "notlar",
        "payload": {"i": i}, "text": f"satır {i} ışık"} , ensure_ascii=False) for i in range(50)) + "\n",
        encoding="utf-8")
    sha = sha256_file(f)
    counts = []
    for _ in range(2):
        sid = hub.add_source("jsonl", "1", sha)
        hub.store_raw(sid, f)
        hub.add_events(sid, iter_event_jsonl(f))
        s = hub.summary()["counts"]
        counts.append((s["source"], s["raw_file"], s["event"], sid))
    assert counts[0] == counts[1]  # aynı kaynak kimliği dahil
    assert counts[0][:3] == (1, 1, 50)
    assert len(hub.search("ışık", limit=100)) == 50


def test_varsayilan_anahtar_icerikten(hub):
    sid = hub.add_source("s", "1", None)
    e = EventIn(ts="2026-01-01T00:00:00Z", kind="k", category="notlar", payload={"a": 1}, text="x")
    assert hub.add_events(sid, [e, e]).added == 1
    e2 = EventIn(ts="2026-01-01T00:00:01Z", kind="k", category="notlar", payload={"a": 1}, text="x")
    assert hub.add_events(sid, [e2]).added == 1


def test_dogrulama(hub):
    sid = hub.add_source("s", "1", None)
    ok = dict(ts="2026-01-01T00:00:00Z", kind="k", category="notlar")
    for bad in [dict(ok, category="yok"), dict(ok, ts="2026-01-01T00:00:00"), dict(ok, ts="dün"),
                dict(ok, kind=""), dict(ok, payload={"x": float("nan")}), dict(ok, event_key="")]:
        with pytest.raises(FormatError):
            hub.add_events(sid, [EventIn(**bad)])
    with pytest.raises(NotFoundError):
        hub.add_events("yok", [EventIn(**ok)])
    with pytest.raises(FormatError):
        hub.add_source("s", "1", "ABC")


def test_ts_normalizasyonu():
    assert norm_ts("2026-11-09T15:00:00+03:00") == "2026-11-09T12:00:00Z"
    assert norm_ts(datetime(2026, 11, 9, 12, 0, 0, 999, tzinfo=timezone.utc)) == "2026-11-09T12:00:00Z"
    assert norm_ts("2026-11-09", assume_utc=True) == "2026-11-09T00:00:00Z"
    tr = timezone(timedelta(hours=3))
    assert norm_ts(datetime(2026, 11, 9, 3, 0, tzinfo=tr)) == "2026-11-09T00:00:00Z"


def test_zaman_cizelgesi(hub):
    sid = hub.add_source("s", "1", None)
    hub.add_events(sid, known_events(20))
    t = hub.timeline(limit=5)
    assert [e.ts for e in t] == sorted([e.ts for e in t], reverse=True)
    asc = hub.timeline(limit=5, ascending=True)
    assert [e.ts for e in asc] == sorted(e.ts for e in asc)
    win = hub.timeline(since="2026-03-05", until="2026-03-07T23:59:59Z", limit=100)
    assert win and all("2026-03-05" <= e.ts[:10] <= "2026-03-07" for e in win)
    assert len(hub.timeline(limit=7, offset=5)) == 7
    assert hub.timeline(categories=["video"]) == []
    assert all(e.category == Category.NOTLAR for e in hub.timeline(categories=["notlar"], limit=100))


def test_salt_okunur_hub_yazamaz(root):
    with Hub.open(root, write=True) as h:
        sid = h.add_source("s", "1", None)
    with Hub.open(root, write=False) as r:
        with pytest.raises(HubReadOnlyError):
            r.add_source("s", "1", None)
        assert r.timeline() == []
