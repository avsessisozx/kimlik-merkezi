"""Madde 1: sohbet mesajı rolü (kullanici/asistan) — kayıtta, süzgeçlerde, say, persona_oner, kart."""
from __future__ import annotations

import json

import pytest
from kimlikcore import Hub, PermissionDenied

from helpers import ev
from kimlikserver.access import KeyManager
from kimlikserver.persona import Persona
from kimlikserver.service import QueryService, ServiceError

KULLANICI_METNI = "KULLANICI-METNI-ZX9"
ASISTAN_METNI = "ASISTAN-METNI-ZX9"


def _msg(i: int, rol: str, ts_gun: int):
    metin = KULLANICI_METNI if rol == "kullanici" else ASISTAN_METNI
    return ev(f"{metin} kahve {i}", "sohbet", kind="sohbet.mesaj", ts=f"2026-10-{ts_gun:02d}T10:00:00Z",
              payload={"platform": "chatgpt", "rol": rol}, key=f"sh{i}")


@pytest.fixture
def d(veri):
    with Hub.open(veri, write=True) as hub:
        sid = hub.add_source("test", "1", None)
        olaylar = [_msg(i, "asistan", 1 + i % 20) for i in range(30)]
        olaylar += [_msg(100 + i, "kullanici", 21 + i) for i in range(3)]
        olaylar.append(ev("kahve notu rolsuz", "notlar"))
        hub.add_events(sid, olaylar)
        km = KeyManager(hub)
        app, key = km.create_key("Sohbetli")
        for k in ("sohbet",):
            km.grant(app, k, confirmed_sensitive=True)
        km.grant(app, "notlar")
        km.grant(app, "persona")
        app2, key2 = km.create_key("Sohbetsiz")
        km.grant(app2, "notlar")
        km.grant(app2, "persona")
        km.grant(app2, "tarama")
        Persona(hub).add_fact("Adı Deneme", "kimlik")
        ids = {r: [x[0] for x in hub.query(
            "SELECT event_id FROM events WHERE category='sohbet' AND "
            "json_extract(payload,'$.rol')=?", (r,))] for r in ("kullanici", "asistan")}
    return {"root": veri, "key": key, "key2": key2, "ids": ids}


def s(d, key=None):
    return QueryService(d["root"], key or d["key"])


def test_kayitta_rol_alani_yalniz_sohbette(d):
    k = s(d).ara("kahve", limit=200)["kayitlar"]
    assert {r["rol"] for r in k if r["kategori"] == "sohbet"} == {"kullanici", "asistan"}
    assert all("rol" not in r for r in k if r["kategori"] == "notlar")
    assert any(r["kategori"] == "notlar" for r in k)


def test_ara_rol_suzgeci_limiti_doldurur(d):
    r = s(d).ara("kahve", rol="kullanici", limit=3, genislet=False)["kayitlar"]
    assert len(r) == 3 and {x["rol"] for x in r} == {"kullanici"}
    # rolsüz kayıt (notlar) süzgeçle dönmez
    assert all(x["kategori"] == "sohbet" for x in s(d).ara("kahve", rol="asistan", limit=50)["kayitlar"])


def test_zaman_cizelgesi_rol_suzgeci(d):
    r = s(d).zaman_cizelgesi(rol="kullanici", limit=10)["kayitlar"]
    assert len(r) == 3 and {x["rol"] for x in r} == {"kullanici"}
    assert len(s(d).zaman_cizelgesi(rol="asistan", limit=100)["kayitlar"]) == 30


def test_ornekle_varsayilan_asistani_dislar(d):
    r = s(d).ornekle("sohbet", n=50)["kayitlar"]
    assert len(r) == 3 and {x["rol"] for x in r} == {"kullanici"}
    r = s(d).ornekle("sohbet", n=50, sorgu="kahve")["kayitlar"]
    assert len(r) == 3 and {x["rol"] for x in r} == {"kullanici"}
    a = s(d).ornekle("sohbet", n=50, rol="asistan")["kayitlar"]
    assert len(a) == 30 and {x["rol"] for x in a} == {"asistan"}
    assert len(s(d).ornekle("sohbet", n=5, sorgu="kahve", rol="asistan")["kayitlar"]) == 5
    # sohbet dışı kategori etkilenmez
    assert len(s(d).ornekle("notlar")["kayitlar"]) == 1


def test_say_alan_rol_ve_suzgec(d):
    r = s(d).say("rol", kategori="sohbet")
    assert {(x["veri"], x["sayi"]) for x in r["satirlar"]} == {("asistan", 30), ("kullanici", 3)}
    r = s(d).say("platform", kategori="sohbet", rol="kullanici")
    assert r["satirlar"][0]["sayi"] == 3 and r["toplam_kayit"] == 3


def test_gecersiz_rol_anlasilir_hata(d):
    for cagri in (lambda: s(d).ara("kahve", rol="robot"), lambda: s(d).say("tur", rol="x"),
                  lambda: s(d).zaman_cizelgesi(rol="x"), lambda: s(d).ornekle("sohbet", rol="x")):
        with pytest.raises(ServiceError, match="Geçersiz rol"):
            cagri()


def test_sohbet_izni_olmayan_anahtar_rol_suzgeciyle_de_goremez(d):
    sv = s(d, d["key2"])
    assert sv.ara("kahve", rol="kullanici", limit=50)["kayitlar"] == []
    assert sv.zaman_cizelgesi(rol="asistan")["kayitlar"] == []
    with pytest.raises(ServiceError, match="reddedildi"):
        sv.ara("kahve", "sohbet", rol="kullanici")
    with pytest.raises(ServiceError, match="reddedildi"):
        sv.ornekle("sohbet", rol="asistan")
    with pytest.raises(ServiceError, match="reddedildi"):
        sv.say("rol", kategori="sohbet")


def test_persona_oner_asistan_kanitini_reddeder(d):
    sv = s(d)
    with pytest.raises(ServiceError, match="yapay zekânın cevabı"):
        sv.persona_oner([{"ifade": "Kahve sever", "kategori": "ilgi",
                          "kanit": [d["ids"]["asistan"][0]], "guven": 0.5}])
    # karışık kanıtta da hiçbiri eklenmez
    with pytest.raises(ServiceError, match="yapay zekânın cevabı"):
        sv.persona_oner([{"ifade": "Kahve sever", "kategori": "ilgi",
                          "kanit": [d["ids"]["kullanici"][0], d["ids"]["asistan"][0]], "guven": 0.5}])
    ok = sv.persona_oner([{"ifade": "Kahve sever", "kategori": "ilgi",
                           "kanit": [d["ids"]["kullanici"][0]], "guven": 0.5}])
    assert ok["eklenen"] == 1


def test_kimlik_karti_sohbet_metni_tasimaz(d):
    r = s(d).kimlik_karti()
    govde = json.dumps(r, ensure_ascii=False)
    assert KULLANICI_METNI not in govde and ASISTAN_METNI not in govde
    assert "sohbet" not in r["ozet_kategorileri"]
