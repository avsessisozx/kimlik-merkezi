from __future__ import annotations

import json
from collections import Counter

import pytest
from conftest import FIX, count_events
from kimlikcore import FormatError
from kimlikimport.base import ImportFormatError
from kimlikimport.reddit import Reddit
from kimlikimport.run import run

# yorum 3 + gönderi 2 + özel mesaj 2 + sohbet 2 + oy 2 + kaydedilen 2 + abonelik 3
EXPECT = 16


def test_kayit_sayisi_ve_kategoriler(hub, zipper):
    r = run(hub, zipper("reddit"), "reddit")
    assert (r.parsed, r.added, r.duplicate) == (EXPECT, EXPECT, 0)
    ev = hub.timeline(limit=1000)
    kinds = Counter(e.kind for e in ev)
    assert kinds["reddit.yorum"] == 3 and kinds["reddit.gonderi"] == 2
    assert kinds["reddit.mesaj"] == 2 and kinds["reddit.sohbet"] == 2
    cats = Counter(e.category for e in ev)
    assert cats["mesaj"] == 4 and cats["sosyal"] == 12


def test_ozel_mesajlar_yalniz_mesaj_kategorisinde(hub, zipper):
    run(hub, zipper("reddit"), "reddit")
    msgs = [e for e in hub.timeline(limit=1000) if e.kind in ("reddit.mesaj", "reddit.sohbet")]
    assert msgs and all(e.category == "mesaj" for e in msgs)
    assert not [e for e in hub.timeline(categories=["sosyal"], limit=1000) if "mesaj" in e.kind]


def test_ip_okunmaz_ve_zaman(hub, zipper):
    run(hub, zipper("reddit"), "reddit")
    for e in hub.timeline(limit=1000):
        assert "1.2.3.4" not in json.dumps(e.payload) + e.text
    c1 = [e for e in hub.timeline(limit=1000) if e.kind == "reddit.yorum" and e.payload["id"] == "c1"][0]
    assert c1.ts == "2023-01-15T12:34:56Z" and "virgullu" in c1.text and "\n" in c1.payload["body"]
    snap = [e for e in hub.timeline(limit=1000) if e.kind == "reddit.abone"][0]
    assert snap.payload["zaman_kaynagi"] == "dosya_tarihi"


def test_iki_kez_tekrarsiz(hub, zipper):
    z = zipper("reddit")
    a = run(hub, z)
    b = run(hub, z)
    assert a.importer == "reddit" and b.source_id == a.source_id
    assert (b.added, b.duplicate) == (0, EXPECT) and count_events(hub) == EXPECT


def test_klasor_girdisi(hub):
    assert run(hub, FIX / "reddit", "reddit").added == EXPECT


def test_atlananlar_raporlanir(hub, zipper):
    rep = Reddit().verify_format(zipper("reddit"))
    txt = rep.to_text()
    assert "ip_logs.csv" in txt and "statistics.csv" in txt and rep.ok
    assert "Ornek yorum" not in txt


def test_eksik_sutun(hub, tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    (d / "comments.csv").write_text("id,permalink,subreddit\nc1,/x,ornek\n")
    with pytest.raises(ImportFormatError) as ei:
        run(hub, d, "reddit")
    assert "zorunlu sütun yok" in str(ei.value) and "body" in str(ei.value) and "date" in str(ei.value)
    assert count_events(hub) == 0


def test_bozuk_tarih_atlanir_sayilir(hub, tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    (d / "comments.csv").write_text(
        "id,permalink,date,subreddit,body\nc1,/x,2023-01-01 00:00:00 UTC,a,iyi\nc2,/y,bozuk,a,kotu\n")
    r = run(hub, d, "reddit")
    assert r.added == 1 and r.skipped == {"comments.csv: date okunamadı": 1}


def test_csv_degil(hub, tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    (d / "comments.csv").write_bytes(b"\xff\xfe\x00bozuk")
    with pytest.raises(FormatError):
        run(hub, d, "reddit")


def test_turu_otomatik_tanir(hub, zipper, tmp_path):
    from kimlikimport import registry
    imp, _ = registry.detect_best(zipper("reddit"))
    assert imp.name == "reddit"
    imp2, _ = registry.detect_best(zipper("takeout_en"))
    assert imp2.name == "google_takeout"
