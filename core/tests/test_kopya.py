import importlib.util
import json
import time
from pathlib import Path

import pytest

from kimlikcore import EventIn, Hub
from kimlikcore.kopya import kopya_raporu, kopya_temizle

IMPORTERS = importlib.util.find_spec("kimlikimport") is not None
FIXTURES = Path(__file__).resolve().parents[2] / "importers" / "fixtures"


def msg(key, kid="k1", text="merhaba dünya", ts="2026-05-01T10:00:00Z", rol="user", plat="chatgpt",
        kind="sohbet.mesaj", cat="sohbet"):
    return EventIn(ts=ts, kind=kind, category=cat, text=text, event_key=key,
                   payload={"platform": plat, "konusma_id": kid, "baslik": "GİZLİ BAŞLIK", "rol": rol,
                            "mesaj_id": key, "ts": ts})


def doldur(hub, evs):
    sid = hub.add_source("sentetik", "1", None)
    hub.add_events(sid, evs)
    return sid


def sayilar(hub):
    return (hub.query("SELECT count(*) FROM events WHERE hidden = 1")[0][0],
            hub.query("SELECT count(*) FROM tombstones")[0][0])


def test_k1_ayni_ve_farkli_konusma(hub):
    doldur(hub, [msg("a1"), msg("a2"), msg("a3", kid="k2"),       # üçü tam kopya (konuşma farklı olsa da)
                 msg("b1", rol="assistant"),                      # farklı rol
                 msg("c1", text="başka"),                         # farklı metin
                 msg("d1", plat="claude"),                        # farklı platform
                 msg("e1", ts="2026-05-02T10:00:00Z"),            # farklı zaman
                 msg("f1", text="  boşluklu  "), msg("f2", text="boşluklu")])
    r = kopya_raporu(hub)
    assert r["incelenen"] == 9 and r["tam_kopya"] == 3 and r["tam_kopya_kume"] == 2
    assert r["dal_disi"] == 0 and r["kalacak"] == 6 and r["uygulandi"] is False
    assert r["platforma_gore"] == {"chatgpt": {"tam_kopya": 3, "dal_disi": 0}}
    assert r["role_gore"] == {"user": {"tam_kopya": 3, "dal_disi": 0}}
    kopya_temizle(hub)
    kalan = {x[0] for x in hub.query("SELECT event_key FROM events WHERE hidden = 0")}
    assert {"a1", "f1"} <= kalan and not ({"a2", "a3", "f2"} & kalan)  # en küçük seq kalır


def test_bos_ts_dokunulmaz(hub):
    doldur(hub, [msg("a1"), msg("a2")])
    with hub.transaction() as c:
        c.execute("UPDATE events SET payload = json_set(payload, '$.ts', '')")
    assert kopya_raporu(hub)["tam_kopya"] == 0


def test_sohbet_disi_ve_konusma_basligina_dokunulmaz(hub):
    doldur(hub, [msg("b1", kind="sohbet.konusma", text="x"), msg("b2", kind="sohbet.konusma", text="x"),
                 msg("n1", kind="not", cat="notlar"), msg("n2", kind="not", cat="notlar")])
    r = kopya_raporu(hub)
    assert r["incelenen"] == 0 and r["tam_kopya"] == 0


def test_k2_dal_disi_ve_bilinmeyen_konusma(hub):
    doldur(hub, [msg("a1", text="bir"), msg("a2", text="iki", ts="2026-05-01T10:01:00Z"),
                 msg("a3", text="üç", ts="2026-05-01T10:02:00Z"),
                 msg("z1", kid="baska", text="yabancı")])
    gecerli = {"k1": {"a1", "a2"}}
    r = kopya_raporu(hub, gecerli_anahtarlar=gecerli)
    assert r["dal_disi"] == 1 and r["tam_kopya"] == 0 and r["kalacak"] == 3
    assert kopya_raporu(hub)["dal_disi"] == 0  # sözlük yoksa K2 çalışmaz
    kopya_temizle(hub, gecerli_anahtarlar=gecerli)
    assert [x[0] for x in hub.query("SELECT event_key FROM events WHERE hidden = 1")] == ["a3"]
    neden = hub.query("SELECT reason FROM tombstones WHERE kind = 'event_hidden'")
    assert neden == [("kopya:dal_disi",)]


def test_kuru_calistirma_degistirmez_uygula_gizler_idempotent(hub):
    doldur(hub, [msg("a1"), msg("a2"), msg("a3", text="üç")])
    once = sayilar(hub)
    for _ in range(2):
        r = kopya_raporu(hub)
        assert r["tam_kopya"] == 1
    assert sayilar(hub) == once
    r = kopya_temizle(hub)
    assert r["uygulandi"] is True and sayilar(hub) == (1, 1)
    assert hub.query("SELECT reason FROM tombstones") == [("kopya:tam",)]
    assert len(hub.search("merhaba")) == 1 and len(hub.timeline(limit=10)) == 2
    r2 = kopya_temizle(hub)
    assert r2["tam_kopya"] == 0 and sayilar(hub) == (1, 1)


def test_rapor_icerik_icermez(hub):
    doldur(hub, [msg("a1", text="çok gizli metin"), msg("a2", text="çok gizli metin", kid="KONUSMA-X")])
    s = json.dumps(kopya_raporu(hub), ensure_ascii=False)
    assert "gizli" not in s and "BAŞLIK" not in s and "KONUSMA" not in s and "k1" not in s


def test_salt_okunur_hub_temizleyemez(root):
    from kimlikcore import HubReadOnlyError
    with Hub.open(root, write=True) as h:
        doldur(h, [msg("a1"), msg("a2")])
    with Hub.open(root, write=False) as h:
        assert kopya_raporu(h)["tam_kopya"] == 1
        with pytest.raises(HubReadOnlyError):
            kopya_temizle(h)


def test_buyuk_olcek_sure(hub, capsys):
    evs = []
    for i in range(25000):
        j = i % 20000  # 5000 kopya
        evs.append(msg(f"m{i}", kid=f"k{i}", text=f"metin {j}", ts=f"2026-05-01T10:{j % 60:02d}:{j // 60 % 60:02d}Z"))
    doldur(hub, evs)
    t = time.perf_counter()
    r = kopya_raporu(hub)
    t1 = time.perf_counter() - t
    t = time.perf_counter()
    kopya_temizle(hub)
    t2 = time.perf_counter() - t
    print(f"\nOLCUM rapor={t1:.2f}s temizle={t2:.2f}s tam_kopya={r['tam_kopya']}")
    assert r["tam_kopya"] > 0 and t1 < 15 and t2 < 30
