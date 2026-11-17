"""Galaksi görünümü: küme sayıları, yıl dökümü, sahip/kısıtlı kip, kayıt listesi."""
from __future__ import annotations

import pytest
from kimlikcore import EventIn, Hub

from kimlikserver.galaksi import galaksi, kayitlar


def E(kind, cat, ts, text="", payload=None, key=None):
    return EventIn(ts=ts, kind=kind, category=cat, text=text, payload=payload or {},
                   event_key=key or f"{kind}:{ts}:{text}")


@pytest.fixture
def hub(tmp_path):
    h = Hub.open(tmp_path / "Galaksi Kisi", write=True)
    sid = h.add_source("elle", "1", None)
    ev = [
        E("instagram.gonderi", "sosyal", "2023-05-01T10:00:00Z", "ig"),
        E("facebook.yorum", "sosyal", "2024-05-01T10:00:00Z", "fb"),
        E("sohbet.mesaj", "sohbet", "2024-06-01T10:00:00Z", "merhaba", {"platform": "ChatGPT"}),
        E("sohbet.mesaj", "sohbet", "2024-06-02T10:00:00Z", "selam", {"platform": "chatgpt"}),
        E("android.konum", "konum", "2025-01-01T10:00:00Z", "yer"),
        E("dosya.kayit", "dosyalar", "2025-02-01T10:00:00Z", "belge", {"zaman_kaynagi": "dosya_tarihi"}),
    ]
    h.add_events(sid, ev)
    yield h
    h.close()


def test_sahip_tum_kumeleri_gorur(hub):
    g = galaksi(hub, sahip=True)
    sayi = {k["ad"]: k["sayi"] for k in g["gruplar"]}
    assert sayi == {"ChatGPT": 2, "Meta": 2, "Telefon": 1, "Bilgisayar": 1}
    assert g["toplam"] == 6
    # dosya tarihli kayıt sayıma girer, yıldız/yıl dökümüne girmez
    assert len(g["yildizlar"]["t"]) == 5 and g["tarihsiz"] == 1
    assert g["yillar"]["2024"] == {"Meta": 1, "ChatGPT": 2}


def test_kisitli_kip_hassas_kategorileri_disarida_tutar(hub):
    g = galaksi(hub, sahip=False)
    ad = {k["ad"] for k in g["gruplar"]}
    assert ad == {"Meta", "Bilgisayar"}


def test_seyreltme_sayimi_bozmaz(hub):
    g = galaksi(hub, sahip=True, sinir=2)
    assert g["toplam"] == 6 and g["seyreltme"] >= 3 and len(g["yildizlar"]["t"]) <= 2


def test_kayit_listesi_kume_ve_aralik(hub):
    r = kayitlar(hub, "Meta", sahip=True)
    assert r["toplam"] == 2 and [x["kind"] for x in r["kayitlar"]] == ["facebook.yorum", "instagram.gonderi"]
    ep = 1714521600   # 2024-05-01T00:00:00Z
    assert kayitlar(hub, "Meta", bas=ep, sahip=True)["toplam"] == 1
    assert kayitlar(hub, "ChatGPT", sahip=False)["toplam"] == 0   # kısıtlı kipte sohbet yok
    assert kayitlar(hub, "ChatGPT", sahip=True, arama="selam")["toplam"] == 1


def test_kimlik_ozeti_yalniz_sayim(hub):
    from kimlikserver.galaksi import ozet
    o = ozet(hub, sahip=True, kayma=3)
    kimlik = {m["id"]: m["metin"] for m in o["maddeler"]}
    assert "5 kayıt" in kimlik["toplam"]            # dosya tarihli kayıt zamana girmez
    assert "2023-05-01" in kimlik["aralik"] and "2025-01-01" in kimlik["aralik"]
    assert "2024" in kimlik["yil"] and "13:00" in kimlik["saat"]      # 10:00 UTC = 13:00 TSİ
    assert {k["ad"] for k in o["kaynaklar"]} == {"Meta", "ChatGPT", "Telefon"}
    assert {k["ad"] for k in ozet(hub, sahip=False)["kaynaklar"]} == {"Meta"}


def test_kayit_listesi_tur_suzgeci(hub):
    r = kayitlar(hub, "Meta", sahip=True, tur="facebook.yorum")
    assert r["toplam"] == 1 and r["kayitlar"][0]["kind"] == "facebook.yorum"
