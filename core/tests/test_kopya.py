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


# ------------------------------------------------------------------ düzeltme turu
def baslik(kid="k1", ts="2026-05-01T09:00:00Z", plat="chatgpt"):
    return EventIn(ts=ts, kind="sohbet.konusma", category="sohbet", text="B", event_key=f"baslik-{kid}",
                   payload={"platform": plat, "konusma_id": kid, "baslik": "B", "ts": ts})


def gorunur(hub):
    return {x[0] for x in hub.query("SELECT event_key FROM events WHERE hidden = 0 AND kind = 'sohbet.mesaj'")}


def test_zamani_belirsiz_k1e_girmez(hub):
    yedek = "2026-05-01T09:00:00Z"
    doldur(hub, [baslik(), msg("a1", ts=yedek), msg("a2", ts=yedek), msg("b1"), msg("b2")])
    r = kopya_raporu(hub)
    assert r["zamani_belirsiz"] == 2 and r["tam_kopya"] == 1 and r["incelenen"] == 4
    kopya_temizle(hub)
    assert gorunur(hub) == {"a1", "a2", "b1"}


def test_k1_k2_cakismasi_ve_gecerli_olan_kalir(hub):
    # küme: a1 (küçük seq, dal dışı), a2 ve a3 (geçerli, aynı içerik); a4 farklı içerik geçerli
    doldur(hub, [msg("a1"), msg("a2"), msg("a3"), msg("a4", text="başka", ts="2026-05-01T10:05:00Z")])
    g = {"k1": {"a2", "a3", "a4"}}
    r = kopya_raporu(hub, gecerli_anahtarlar=g)
    assert r["dal_disi"] == 1 and r["tam_kopya"] == 1 and r["kalacak"] == 2
    kopya_temizle(hub, gecerli_anahtarlar=g)
    assert gorunur(hub) == {"a2", "a4"}  # dal dışı a1 K1'e girmedi; geçerli kümede en küçük seq kaldı
    # farklı konuşmalarda aynı içerik: geçerli dalda olan kalır (en küçük seq değil)
    doldur(hub, [msg("p1", text="y", kid="k4"), msg("p2", text="y", kid="k5")])
    kopya_temizle(hub, gecerli_anahtarlar={"k5": {"p2"}})
    assert "p2" in gorunur(hub) and "p1" not in gorunur(hub)


def test_iki_calistirma_senaryosu_gecerli_mesaj_gorunur(hub):
    doldur(hub, [msg("A"), msg("B")])
    kopya_temizle(hub)  # paketsiz: A kalır, B gizlenir
    assert gorunur(hub) == {"A"}
    g = {"k1": {"B"}}  # güncel dalda yalnız B
    r = kopya_raporu(hub, gecerli_anahtarlar=g)
    assert r["geri_acilan"] == 1 and r["dal_disi"] == 1 and r["tumu_dal_disi_konusma"] == 0
    assert gorunur(hub) == {"A"}  # kuru çalıştırma dokunmadı
    r = kopya_temizle(hub, gecerli_anahtarlar=g)
    assert gorunur(hub) == {"B"}
    assert hub.query("SELECT event_key, reason FROM tombstones t JOIN events e USING(event_id)") == [("A", "kopya:dal_disi")]
    assert kopya_temizle(hub, gecerli_anahtarlar=g)["geri_acilan"] == 0


def test_geri_acma_sinirlari_kaynak_kaldirma_ve_elle_gizleme(hub):
    s1 = doldur(hub, [msg("A"), msg("B")])
    kopya_temizle(hub)  # B kopya olarak gizli
    g = {"k1": {"B"}}
    # B'nin kaynağı kaldırılmış: geri açılmaz
    hub.remove_source(s1, "x")
    assert kopya_raporu(hub, gecerli_anahtarlar=g)["geri_acilan"] == 0
    assert hub.query("SELECT count(*) FROM events WHERE hidden = 0")[0][0] == 0
    # elle gizlenen geçerli kayıt geri açılmaz ve kümeye girmez
    ev_id = None
    s2 = doldur(hub, [msg("C", text="z", kid="k9"), msg("D", text="z", kid="k9")])
    ev_id = hub.query("SELECT event_id FROM events WHERE event_key = 'D'")[0][0]
    hub.hide_event(ev_id, "elle")
    r = kopya_temizle(hub, gecerli_anahtarlar={"k9": {"D", "C"}})
    assert r["geri_acilan"] == 0 and hub.query("SELECT hidden FROM events WHERE event_key = 'D'") == [(1,)]
    assert hub.query("SELECT reason FROM tombstones WHERE event_id = ?", (ev_id,)) == [("elle",)]
    # kaldırılmış kaynağın kayıtları kümeye girmez
    assert kopya_raporu(hub)["incelenen"] == 1


def test_kopya_gizli_yeniden_iceaktarmada_gizli_kalir(hub):
    s = doldur(hub, [msg("a1"), msg("a2")])
    kopya_temizle(hub)
    hub.add_events(s, [msg("a1"), msg("a2")])
    assert gorunur(hub) == {"a1"}


def test_tumu_dal_disi_konusma_atlanir(hub):
    doldur(hub, [msg("a1", text="1"), msg("a2", text="2", ts="2026-05-01T10:01:00Z"),
                 msg("b1", kid="k2", text="3"), msg("b2", kid="k2", text="4", ts="2026-05-01T10:01:00Z")])
    g = {"k1": {"eski-anahtar"}, "k2": {"b1"}}
    r = kopya_temizle(hub, gecerli_anahtarlar=g)
    assert r["etkilenen_konusma"] == 2 and r["tumu_dal_disi_konusma"] == 1 and r["atlanan_konusma"] == 1
    assert r["dal_disi"] == 1
    assert gorunur(hub) == {"a1", "a2", "b1"}


def test_bellek_akisla(hub):
    import tracemalloc
    doldur(hub, [msg(f"m{i}", kid=f"k{i}", text=("x" * 2000) + str(i % 20000)) for i in range(25000)])
    tracemalloc.start()
    r = kopya_raporu(hub)
    _, tepe = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"\nTEPE BELLEK {tepe / 1e6:.1f} MB")
    assert r["tam_kopya"] == 5000 and tepe < 25e6


def test_sifreli_hub_kopya_temizle(root, monkeypatch):
    from kimlikcore import sifreleme as sif
    monkeypatch.setattr(sif, "KDF_N", 1 << 4)
    sif.saglayici_ayarla(sif.SahteSaglayici("birinci"))
    with Hub.open(root, write=True, sifreli=True) as h:
        doldur(h, [msg("a1"), msg("a2"), msg("a3", text="başka")])
        assert kopya_temizle(h)["tam_kopya"] == 1
    with Hub.open(root, write=False) as h:
        assert h.sifreli and len(h.timeline(limit=10)) == 2
        assert kopya_raporu(h)["tam_kopya"] == 0
    sif.saglayici_ayarla(None)
