from __future__ import annotations

import json
from collections import Counter

import pytest
from conftest import FIX, count_events
from kimlikcore import FormatError
from kimlikimport import registry
from kimlikimport.base import ImportFormatError, fix_mojibake
from kimlikimport.meta import Meta
from kimlikimport.run import run


def test_mojibake_duzeltme():
    bad = "Örnek şık İ 😀".encode().decode("latin-1")
    assert bad != "Örnek şık İ 😀" and fix_mojibake(bad) == "Örnek şık İ 😀"
    assert fix_mojibake("Zaten doğru şık") == "Zaten doğru şık"  # >0xFF karakter: dokunma
    assert fix_mojibake("düz ascii") == "düz ascii"
    assert fix_mojibake("café") == "café"  # latin-1'de geçerli ama UTF-8 değil: olduğu gibi


def test_instagram_kayit_sayisi_ve_kategoriler(hub, zipper):
    r = run(hub, zipper("meta_instagram"))
    assert r.importer == "meta" and (r.parsed, r.added, r.duplicate) == (16, 16, 0)
    ev = hub.timeline(limit=100)
    cats = Counter(e.category for e in ev)
    assert cats == {"sosyal": 12, "mesaj": 3, "konum": 1}
    kinds = Counter(e.kind for e in ev)
    assert kinds["instagram.begeni"] == 3 and kinds["instagram.takip"] == 3 and kinds["instagram.takipci"] == 2
    assert kinds["instagram.yorum"] == 2 and kinds["instagram.gonderi"] == 2 and kinds["instagram.mesaj"] == 3
    assert r.skipped == {"messages: timestamp_ms yok": 1}


def test_mojibake_olaylarda_duzeltilir(hub):
    run(hub, FIX / "meta_instagram")
    assert hub.search("Güzel şık yorum bir")
    assert hub.search("Merhaba şık mesaj", categories=["mesaj"])
    assert any(e.payload["baslik"] == "Örnek açıklama şık" for e in hub.timeline(limit=100) if e.kind.endswith("gonderi"))


def test_mesajlar_yalniz_mesaj_kategorisinde_ve_gps_ayri(hub):
    run(hub, FIX / "meta_instagram")
    assert not hub.search("Merhaba şık mesaj", categories=["sosyal"])
    for e in hub.timeline(limit=100):
        if e.category != "konum":
            assert "41.0123" not in json.dumps(e.payload), e.kind
    loc = hub.timeline(categories=["konum"], limit=10)
    assert len(loc) == 1 and loc[0].payload["koordinatlar"] == [{"enlem": 41.0123, "boylam": 28.9765}]


def test_facebook(hub, zipper):
    r = run(hub, zipper("meta_facebook"))
    assert (r.parsed, r.added) == (11, 11)
    kinds = Counter(e.kind for e in hub.timeline(limit=100))
    assert kinds["facebook.gonderi"] == 2 and kinds["facebook.yorum"] == 2 and kinds["facebook.tepki"] == 2
    assert kinds["facebook.arkadas"] == 2 and kinds["facebook.mesaj"] == 2 and kinds["meta.konum"] == 1
    assert hub.search("Şık yorum") and hub.search("Ornek Arkadaş İki")
    loc = hub.timeline(categories=["konum"], limit=5)[0]
    assert loc.payload["koordinatlar"][0]["ad"] == "Ornek Yer"


def test_iki_kez_tekrarsiz(hub, zipper):
    z = zipper("meta_instagram")
    a = run(hub, z)
    b = run(hub, z, "instagram")  # takma ad
    assert b.source_id == a.source_id and b.added == 0 and b.duplicate == 16
    assert count_events(hub) == 16


def test_otomatik_tanima(zipper):
    imp, _ = registry.detect_best(zipper("meta_facebook"))
    assert imp.name == "meta"


def test_html_ve_bozuk(hub, tmp_path):
    with pytest.raises(ImportFormatError) as ei:
        run(hub, FIX / "meta_html", "meta")
    assert "HTML" in str(ei.value) and "JSON" in str(ei.value)
    d = tmp_path / "x" / "instagram"
    d.mkdir(parents=True)
    (d / "liked_posts.json").write_text('{"likes_media_likes": [{"title": "a", "string_list_data": [{"timestamp": 1}')
    with pytest.raises(FormatError):
        run(hub, tmp_path / "x", "meta")
    assert count_events(hub) == 0


def test_rapor_icerik_icermez():
    txt = Meta().verify_format(FIX / "meta_instagram").to_text()
    for secret in ("ornekkullanici", "Güzel", "Merhaba", "41.0123", "takip1"):
        assert secret not in txt
