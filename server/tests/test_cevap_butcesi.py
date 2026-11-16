"""Madde 4-8: cevap boyutu bütçeleri (token tasarrufu) ve yeni cevap biçimi.
Sınırlar `olcum_cevap_boyutu.py`daki sentetik örnek dünya üzerindedir."""
from __future__ import annotations

import json

import pytest
from kimlikcore import Hub

from helpers import INJECTION, ev
from kimlikserver.alinti import ALINTI_UZUNLUGU, alinti
from kimlikserver.kart import KISA_KART_UST_SINIR
from kimlikserver.service import ServiceError
import olcum_cevap_boyutu as O


@pytest.fixture
def d(veri):
    return O.dunya_kur(veri)


def test_butceler(d):
    o = O.olc(d)
    print("\n" + O.tablo(o))
    assert o["ara"] <= 4000
    assert o["ornekle"] <= 7000
    assert o["zaman_cizelgesi"] <= 7000
    assert o["say_ay"] <= 2500
    assert o["say_yil"] <= 500
    assert o["kimlik_karti"] <= 3300
    assert o["kategorileri_listele"] <= 1500
    assert o["persona_getir"] <= 5000
    assert o["kayit_getir"] <= 4600


def test_kayit_bicimi_ve_tekrar_eden_bloklar_yok(d):
    s = O.servis(d)
    r = s.ara("konuşma")
    assert set(r) == {"sd", "kayitlar"} and r["sd"] == "+03:00"
    k = r["kayitlar"][0]
    assert set(k) == {"id", "zaman", "tur", "kategori", "veri", "rol", "kisaltildi", "uzunluk"}
    assert k["kisaltildi"] is True and k["uzunluk"] == 3000 and len(k["veri"]) <= ALINTI_UZUNLUGU
    assert k["zaman"].endswith("+03:00")
    assert len(r["kayitlar"]) == 10 and len(s.zaman_cizelgesi()["kayitlar"]) == 20
    for cevap in (s.zaman_cizelgesi(), s.say("ay"), s.kimlik_karti(), s.persona_getir(),
                  s.ornekle("tarama", 3)):
        assert "veri_uyarisi" not in cevap and "saat_dilimi" not in cevap
    assert "saat_dilimi" in s.kategorileri_listele() and "kayit_getir" in s.kategorileri_listele()["kullanim"]


def test_alinti_terim_cevresi_ve_sinirlar():
    metin = "baş " * 100 + "KAHVE makinesi " + "son " * 100
    a = alinti(metin, ["kahve"])
    assert "KAHVE" in a and len(a) <= 200 and a.startswith("…") and a.endswith("…")
    b = alinti(metin)
    assert b.startswith("baş") and b.endswith("…") and len(b) <= 200
    assert alinti("kısa", ["x"]) == "kısa"
    assert "IŞIK" in alinti("a " * 150 + "IŞIK burada " + "b " * 150, ["isik"])  # Türkçe katlama


def test_kayit_getir_parca_parca_ve_tek_ret(d):
    s = O.servis(d)
    eid = s.ara("konuşma", kategori="sohbet", limit=1)["kayitlar"][0]["id"]
    p1 = s.kayit_getir(eid, 0, 1000)
    assert len(p1["veri"]) == 1000 and p1["uzunluk"] == 3000 and p1["devam"] == 1000
    p3 = s.kayit_getir(eid, 2000, 5000)
    assert len(p3["veri"]) == 1000 and "devam" not in p3
    assert len(s.kayit_getir(eid, 0, 10**6)["veri"]) == 3000          # üst sınır 20000
    iletiler = set()
    with Hub.open(d["root"], write=True) as hub:
        gizli = ev("gizli", "tarama", key="g1")
        hub.add_events(hub.add_source("x", "1", None), [gizli])
        gid = hub.query("SELECT event_id FROM events WHERE event_key='g1'")[0][0]
        hub.hide_event(gid, "t")
        hub.add_events(hub.add_source("y", "1", None), [ev("e", "eposta", key="e1")])
        eposta = hub.query("SELECT event_id FROM events WHERE event_key='e1'")[0][0]
    for kimlik in ("yok-yok", gid, eposta):
        with pytest.raises(ServiceError) as e:
            s.kayit_getir(kimlik)
        iletiler.add(str(e.value))
    assert len(iletiler) == 1 and str(iletiler.pop()).startswith("reddedildi")


def test_kisa_kart_siniri_ve_tam_kart(d):
    s = O.servis(d)
    k = s.kimlik_karti()["veri"]
    assert len(k) <= KISA_KART_UST_SINIR and "beyan daha (tam kart: kisa=false)" in k
    assert "Süresi dolan beyan: 3" in k and "Bilinmeyen konu:" in k
    assert len(k.split("Veriden özet")[1].split("\n\n")[0].splitlines()) <= 6
    assert len(s.kimlik_karti(kisa=False)["veri"]) > len(k)


def test_say_yil_satir_bicimi(d):
    r = O.servis(d).say("yil", kategori="tarama")
    assert all(isinstance(x, list) and len(x) == 2 and x[1] > 0 for x in r["satirlar"])
    assert sum(x[1] for x in r["satirlar"]) == 2000 and r["satirlar"][0][0] == "2018"


def test_enjeksiyon_yalniz_veri_alaninda(d):
    with Hub.open(d["root"], write=True) as hub:
        hub.add_events(hub.add_source("z", "1", None), [ev(INJECTION, "notlar", key="inj")])
    r = O.servis(d).ara("talimatları")
    assert [k["veri"] for k in r["kayitlar"]] == [INJECTION]
    r["kayitlar"][0]["veri"] = ""
    assert INJECTION not in json.dumps(r, ensure_ascii=False)
