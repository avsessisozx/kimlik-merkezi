from __future__ import annotations

import json
from collections import Counter

from conftest import FIX, count_events
from kimlikimport import registry
from kimlikimport.run import run
from kimlikimport.spotify import Spotify

# standart: müzik 3 + podcast 1 + liste 2 + kütüphane 4 + arama 2 = 12
# genişletilmiş: 3 geçerli (biri standartla aynı dakika/şarkı) + 1 adsız atlanır


def test_standart_paket(hub, zipper):
    r = run(hub, zipper("spotify_standart"))
    assert r.importer == "spotify" and (r.parsed, r.added, r.duplicate) == (12, 12, 0)
    ev = hub.timeline(limit=100)
    assert {e.category for e in ev} == {"muzik"}
    kinds = Counter(e.kind for e in ev)
    assert kinds["spotify.dinleme"] == 3 and kinds["spotify.podcast"] == 1 and kinds["spotify.liste_ogesi"] == 2
    assert kinds["spotify.arama"] == 2 and sum(v for k, v in kinds.items() if k.startswith("spotify.kutuphane")) == 4
    assert hub.search("Turkce Sarkı Şık", categories=["muzik"])
    t = [e for e in ev if e.kind == "spotify.dinleme" and e.payload["sarki"] == "Ornek Sarki Bir"][0]
    assert t.ts == "2023-05-01T10:01:00Z"


def test_kimlik_dosyasi_okunmaz(hub):
    rep = Spotify().verify_format(FIX / "spotify_standart")
    assert rep.ok and "Userdata" not in "".join(rep.found_files)
    run(hub, FIX / "spotify_standart")
    blob = json.dumps([e.payload for e in hub.timeline(limit=100)])
    assert "gizli@example.test" not in blob and "1990-01-01" not in blob


def test_genisletilmis_ip_ve_kullanici_alinmaz(hub):
    r = run(hub, FIX / "spotify_genisletilmis")
    assert (r.parsed, r.added) == (3, 3) and r.skipped == {"genişletilmiş: parça/bölüm/kitap adı yok": 1}
    blob = json.dumps([e.payload for e in hub.timeline(limit=100)])
    for secret in ("1.2.3.4", "ornekkullanici", "\"TR\"", "user_agent"):
        assert secret not in blob
    ev = [e for e in hub.timeline(limit=100) if e.payload.get("sarki") == "Genisletilmis Sarki"][0]
    assert ev.payload["atlandi"] is True and ev.ts == "2023-05-05T12:00:10Z"


def test_iki_paket_birlikte_tekrarsiz(hub, zipper):
    run(hub, zipper("spotify_standart"))
    r = run(hub, zipper("spotify_genisletilmis"))
    assert (r.added, r.duplicate) == (2, 1)  # "Ornek Sarki Bir" aynı dakika/şarkı
    assert count_events(hub) == 14
    r2 = run(hub, zipper("spotify_genisletilmis"))
    assert (r2.added, r2.duplicate) == (0, 3)


def test_otomatik_tanima(zipper):
    for n in ("spotify_standart", "spotify_genisletilmis"):
        imp, _ = registry.detect_best(zipper(n))
        assert imp.name == "spotify", n
