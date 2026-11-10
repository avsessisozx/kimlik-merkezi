"""Persona Haritası testleri (sentetik veri; importers fixtures + elle yazılmış olaylar)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from kimlikcore import EventIn, FormatError, Hub, NotFoundError
from kimlikimport.run import run as ice_al

from kimlikserver.harita import (HASSAS_BOLGELER, VARSAYILAN_BOLGELER, ayrinti, bolge, harita,
                                 karsilastir, kayitlar)
from kimlikserver.persona import Persona

FIX = Path(__file__).resolve().parents[2] / "importers" / "fixtures"
SIR_METIN = "GIZLI-ICERIK-ASLA-DONMEMELI"
SIR_URL = "https://gizli.example/yol?q=sir"


def E(kind, cat, ts, text="", payload=None, key=None):
    return EventIn(ts=ts, kind=kind, category=cat, text=text, payload=payload or {},
                   event_key=key or f"{kind}:{ts}:{text}")


@pytest.fixture
def hub(tmp_path):
    h = Hub.open(tmp_path / "Deneme Kisi", write=True)
    yield h
    h.close()


@pytest.fixture
def fixture_hub(hub):
    ice_al(hub, FIX / "takeout_en")
    ice_al(hub, FIX / "reddit")
    return hub


def elle_veri(hub):
    sid = hub.add_source("elle", "1", None)
    ev = [
        E("chrome.ziyaret", "tarama", "2026-01-05T08:00:00Z", "a", {"url": "https://www.Siteler.example/x?y=1"}, "t1"),
        E("chrome.ziyaret", "tarama", "2026-01-06T09:00:00Z", "b", {"url": "https://siteler.example/z"}, "t2"),
        E("chrome.ziyaret", "tarama", "2026-02-06T23:30:00Z", "c", {"url": "https://baska.example:8080/"}, "t3"),
        E("google.arama", "tarama", "2026-02-07T10:00:00Z", "k", {"baslik": "Searched for Kahve Makinesi"}, "t4"),
        E("google.arama", "tarama", "2026-02-08T10:00:00Z", "k", {"baslik": "Searched for kahve makinesi"}, "t5"),
        E("youtube.izleme", "video", "2026-03-01T12:00:00Z", "v", {"baslik": "Watched V1", "alt_baslik": ["Kanal X"]}, "v1"),
        E("youtube.izleme", "video", "2026-03-02T12:00:00Z", "v", {"baslik": "Watched V2", "alt_baslik": ["Kanal X"]}, "v2"),
        E("youtube.izleme", "video", "2026-03-03T12:00:00Z", "v", {"baslik": "Watched V3"}, "v3"),
        E("muzik.dinleme", "muzik", "2026-04-01T12:00:00Z", "m", {}, "m1"),
        E("reddit.gonderi", "sosyal", "2026-05-01T12:00:00Z", "g", {"subreddit": "ornek"}, "s1"),
        E("reddit.yorum", "sosyal", "2026-05-02T12:00:00Z", "g", {"subreddit": "ornek"}, "s2"),
        E("reddit.abone", "sosyal", "2026-11-10T00:00:00Z", "g", {"subreddit": "ornek", "zaman_kaynagi": "dosya_tarihi"}, "s3"),
        E("not.kayit", "notlar", "2026-06-01T12:00:00Z", "n", {}, "n1"),
        E("dosya.kayit", "dosyalar", "2026-06-02T12:00:00Z", "d", {}, "n2"),
        E("google.etkinlik", "uygulama", "2026-07-01T12:00:00Z", "u", {"urun": "Maps"}, "u1"),
        E("google.etkinlik", "uygulama", "2026-07-02T12:00:00Z", "u", {"urun": "Maps"}, "u2"),
        E("google.etkinlik", "uygulama", "2026-07-03T12:00:00Z", "u", {"urun": "Gmail"}, "u3"),
        # hassas
        E("reddit.mesaj", "mesaj", "2026-08-01T12:00:00Z", SIR_METIN, {"from": SIR_METIN}, "h1"),
        E("reddit.mesaj", "mesaj", "2026-08-02T12:00:00Z", SIR_METIN + " 2", {}, "h2"),
        E("eposta.ileti", "eposta", "2026-08-03T12:00:00Z", SIR_METIN + " e", {"konu": SIR_METIN}, "h3"),
        E("google.konum", "konum", "2026-08-04T12:00:00Z", "Gizli Mahalle", {"url": SIR_URL, "lat": 41.0123456, "lon": 28.9876543}, "h4"),
        E("google.konum", "konum", "2026-08-05T12:00:00Z", "Baska Gizli Yer", {"yerler": [{"name": "Baska Gizli Yer"}]}, "h5"),
        E("foto.meta", "medya_meta", "2026-08-06T12:00:00Z", "FOTO-GIZLI-METIN", {"gps": {"lat": 41.5, "lon": 29.5}}, "h6"),
    ]
    hub.add_events(sid, ev)
    return sid


def sec(h, bolge_id):
    return next(b for b in h["bolgeler"] if b["id"] == bolge_id)


def graf(b, baslik_parca):
    return next((g for g in b["grafikler"] if baslik_parca in g["baslik"]), None)


# ---------------------------------------------------------------- fixtures (gerçek importer çıktısı)
def test_importer_fixture_sayilari(fixture_hub):
    h = harita(fixture_hub, now="2026-11-10T00:00:00Z")
    assert h["profil"]["ad"] == "Deneme Kisi"  # kimlik fact'i yok: klasör adı
    assert [b["id"] for b in h["bolgeler"]] == list(VARSAYILAN_BOLGELER)
    assert (sec(h, "bas")["olay_sayisi"], sec(h, "goz")["olay_sayisi"],
            sec(h, "agiz")["olay_sayisi"]) == (6, 10, 12)
    assert sec(h, "kulak")["ozet"] == "Henüz veri yok" and sec(h, "el")["olay_sayisi"] == 0
    # tarihi olmayan (dosya tarihi) kayıtlar ilk/son ve zaman grafiklerini kirletmez
    assert sec(h, "agiz")["son"] < "2024"
    assert sec(h, "goz")["son"] < "2025"
    b = bolge(fixture_hub, "goz")
    assert any("kanal" in e["grup"] for e in b["en_cok"])
    assert {e["ad"] for e in b["en_cok"]} >= {"Kanal A", "Kanal B"}
    assert any("gerçek zaman yok" in n for n in b["notlar"])
    s = bolge(fixture_hub, "agiz")
    assert {"ad": "ornek", "sayi": 3, "grup": "subreddit",
            "anahtar": {"alan": "subreddit", "deger": "ornek"}} in s["en_cok"]
    t = bolge(fixture_hub, "bas")
    assert {e["ad"] for e in t["en_cok"] if e["grup"] == "site"} == {"example.test"}
    assert {e["ad"] for e in t["en_cok"] if e["grup"] == "arama terimi"} == \
        {"ornek google arama", "ornek yer"}  # "Searched for " öneki atıldı


def test_fixture_konum_ayrildi_ayak_kilitli(fixture_hub):
    h = harita(fixture_hub)
    ayak = sec(h, "ayak")
    assert ayak["kilitli"] and ayak["olay_sayisi"] is None and ayak["ozet"] == "Kilitli"
    a = harita(fixture_hub, ac_hassas={"ayak"})
    assert sec(a, "ayak")["olay_sayisi"] == 2 and not sec(a, "ayak")["kilitli"]
    assert sec(a, "kalp")["kilitli"]  # yalnız istenen açılır
    assert sec(a, "kalp")["olay_sayisi"] is None


# ---------------------------------------------------------------- elle yazılmış veri, her bölge
def test_her_bolgenin_ciktisi(hub):
    elle_veri(hub)
    h = harita(hub)
    assert [sec(h, i)["olay_sayisi"] for i in ("bas", "goz", "kulak", "agiz", "el", "ic")] == \
        [5, 3, 1, 3, 2, 3]
    bas = bolge(hub, "bas")
    siteler = graf(bas, "siteler")
    assert dict(zip(siteler["etiketler"], siteler["degerler"])) == \
        {"siteler.example": 2, "baska.example:8080": 1}  # www. atılır, küçük harf
    terim = graf(bas, "aranan")
    assert dict(zip(terim["etiketler"], terim["degerler"])) == {"kahve makinesi": 2}
    aylik = graf(bas, "Aylık")
    assert aylik["etiketler"] == ["2026-01", "2026-02"] and aylik["degerler"] == [2, 3]
    saat = graf(bas, "saat")
    assert saat["degerler"][8] == 1 and saat["degerler"][23] == 1 and sum(saat["degerler"]) == 5
    assert graf(bas, "Haftanın")["etiketler"][0] == "Pzt"
    goz = bolge(hub, "goz")
    assert goz["en_cok"][0]["ad"] == "Kanal X" and goz["en_cok"][0]["sayi"] == 2
    assert any("kanal adı yok" in n for n in goz["notlar"])  # 1 kayıtta kanal yok
    kulak = bolge(hub, "kulak")
    assert any("bu alan yok" in n for n in kulak["notlar"]) and graf(kulak, "Aylık")
    assert graf(kulak, "sanat") is None and kulak["en_cok"] == []
    agiz = bolge(hub, "agiz")
    assert agiz["en_cok"] == [{"ad": "ornek", "sayi": 2, "grup": "subreddit",
                               "anahtar": {"alan": "subreddit", "deger": "ornek"}}]  # abone sayılmaz
    assert graf(agiz, "Aylık")["degerler"] == [2]  # dosya tarihli abone grafikte yok
    assert any("gerçek zaman yok" in n for n in agiz["notlar"])
    el = bolge(hub, "el")
    pasta = graf(el, "Kategoriler")
    assert dict(zip(pasta["etiketler"], pasta["degerler"])) == {"notlar": 1, "dosyalar": 1}
    assert any("bu alan yok" in n for n in el["notlar"])
    ic = bolge(hub, "ic")
    assert ic["en_cok"][0] == {"ad": "Maps", "sayi": 2, "grup": "uygulama",
                               "anahtar": {"alan": "uygulama", "deger": "Maps"}}
    assert any("süresi: bu alan yok" in n for n in ic["notlar"])


def test_aralik_ve_saat_kaydirma(hub):
    elle_veri(hub)
    b = bolge(hub, "bas", aralik=("2026-02-01T00:00:00Z", None))
    assert graf(b, "Aylık")["etiketler"] == ["2026-02"]
    b3 = bolge(hub, "bas", utc_kaydirma=3)
    saat = graf(b3, "saat")
    assert "UTC+3" in saat["baslik"] and saat["degerler"][11] == 1 and saat["degerler"][2] == 1 \
        and saat["degerler"][13] == 2
    # 6 Şubat Cuma 23:30 UTC -> +3 ile 7 Şubat Cumartesi 02:30; 7 Şubat 10:00 -> Cmt 13:00; 8 Şubat -> Pazar
    assert graf(b3, "Haftanın")["degerler"] == [1, 1, 0, 0, 0, 2, 1]


# ---------------------------------------------------------------- hassas bölgeler
def test_hassas_kilitli_yalniz_kilitli_ve_sizinti_yok(hub):
    elle_veri(hub)
    h = harita(hub)
    for bid in HASSAS_BOLGELER:
        b = sec(h, bid)
        assert b["kilitli"] and b["olay_sayisi"] is None and b["ilk"] is None and b["son"] is None
        assert b["ozet"] == "Kilitli"
        d = bolge(hub, bid)
        assert d == {"id": bid, "ad": d["ad"], "kilitli": True, "grafikler": [], "en_cok": [],
                     "notlar": ["Kilitli"]}
    # profil toplamı da kilitli kategorilerin sayısını içermez: 5+3+1+3+2+3 = 17
    assert h["profil"]["olay"] == 17
    txt = json.dumps(h, ensure_ascii=False)
    for yasak in (SIR_METIN, SIR_URL, "Gizli Mahalle", "41.01", "28.98"):
        assert yasak not in txt


def test_hassas_acik_yalniz_sayi_ve_zaman(hub):
    elle_veri(hub)
    acik = {"kalp", "karin", "ayak"}
    h = harita(hub, ac_hassas=acik)
    assert (sec(h, "kalp")["olay_sayisi"], sec(h, "karin")["olay_sayisi"],
            sec(h, "ayak")["olay_sayisi"]) == (2, 1, 3)
    assert h["profil"]["olay"] == 23
    parcalar = [json.dumps(h, ensure_ascii=False)]
    for bid in acik:
        d = bolge(hub, bid, ac_hassas=acik)
        assert not d["kilitli"] and d["en_cok"] == [] and graf(d, "Aylık")
        parcalar.append(json.dumps(d, ensure_ascii=False))
    ayak = bolge(hub, "ayak", ac_hassas=acik)
    sayilar = graf(ayak, "Sayılar")
    assert sayilar["degerler"] == [3, 2]  # 3 kayıt, 2 farklı konum adı (yalnız sayı)
    tum = "\n".join(parcalar)
    for yasak in (SIR_METIN, SIR_URL, "Gizli Mahalle", "Baska Gizli", "41.01", "28.98", "41.5",
                  "gizli.example", "FOTO-GIZLI-METIN"):
        assert yasak not in tum, yasak


def test_kategori_adiyla_acma(hub):
    elle_veri(hub)
    assert not sec(harita(hub, ac_hassas={"mesaj"}), "kalp")["kilitli"]
    assert not bolge(hub, "kalp", ac_hassas={"mesaj"})["kilitli"]
    assert bolge(hub, "karin", ac_hassas={"mesaj"})["kilitli"]


# ---------------------------------------------------------------- gizli kayıt, boş hub, hata
def test_tombstone_sayilmaz(hub):
    sid = elle_veri(hub)
    onceki = harita(hub, ac_hassas={"kalp"})
    ev = hub.timeline(categories=["tarama"], limit=1)[0]
    hub.hide_event(ev.event_id, "test")
    h = harita(hub, ac_hassas={"kalp"})
    assert sec(h, "bas")["olay_sayisi"] == sec(onceki, "bas")["olay_sayisi"] - 1
    assert h["profil"]["olay"] == onceki["profil"]["olay"] - 1
    hub.remove_source(sid, "yanlış")
    h = harita(hub, ac_hassas={"kalp", "karin", "ayak", "zihin"})
    assert h["profil"]["olay"] == 0
    assert all(b["olay_sayisi"] == 0 for b in h["bolgeler"])
    assert bolge(hub, "goz")["notlar"][0] == "Henüz veri yok"


def test_bos_hub(hub):
    h = harita(hub, ac_hassas={"ayak"})
    assert h["profil"] == {"ad": "Deneme Kisi", "olay": 0, "ilk": None, "son": None}
    assert h["beyan"] == []
    for b in h["bolgeler"]:
        if not b["kilitli"]:
            assert b["olay_sayisi"] == 0 and b["ozet"] == "Henüz veri yok"
    d = bolge(hub, "bas")
    assert d["grafikler"] == [] and d["notlar"] == ["Henüz veri yok"]
    assert "bu alan yok" in " ".join(bolge(hub, "kulak")["notlar"])


def test_bilinmeyen_bolge(hub):
    with pytest.raises(NotFoundError):
        bolge(hub, "yok")


def test_beyan_ve_profil_adi(hub, tmp_path):
    p = Persona(hub)
    p.add_fact("Ayşe Deneme", "kimlik", fact_key="ad")
    p.add_fact("Kahve severim", "tercihler")
    sid = hub.add_source("belge", "1", None)
    p.add_fact_from_source("Python bilir", "ilgi", sid)
    h = harita(hub)
    assert h["profil"]["ad"] == "Ayşe Deneme"
    assert {(b["durum"], b["veri"]) for b in h["beyan"]} == {
        ("beyan_edilen", "Ayşe Deneme"), ("beyan_edilen", "Kahve severim"),
        ("dosyadan_alinan", "Python bilir")}
    assert next(b for b in h["beyan"] if b["durum"] == "dosyadan_alinan")["kaynak"] == "belge"


def test_salt_okunur_hub_ile(hub):
    elle_veri(hub)
    hub.close()
    with Hub.open(hub.root, write=False) as ro:
        assert sec(harita(ro), "bas")["olay_sayisi"] == 5
        assert bolge(ro, "goz")["en_cok"]


# ---------------------------------------------------------------- performans
def test_200bin_olayda_sure(tmp_path):
    import random
    rnd = random.Random(1)
    kinds = [("chrome.ziyaret", "tarama"), ("youtube.izleme", "video"), ("reddit.gonderi", "sosyal"),
             ("google.etkinlik", "uygulama"), ("reddit.mesaj", "mesaj"), ("google.konum", "konum")]
    with Hub.open(tmp_path / "buyuk", write=True) as h:
        sid = h.add_source("sentetik", "1", None)

        def gen():
            for i in range(200_000):
                kind, cat = kinds[i % len(kinds)]
                ts = f"{2023 + i % 3}-{1 + i % 12:02d}-{1 + i % 28:02d}T{i % 24:02d}:{i % 60:02d}:00Z"
                pay = {"url": f"https://site{rnd.randrange(500)}.example/x/{i}",
                       "alt_baslik": [f"Kanal {rnd.randrange(300)}"],
                       "subreddit": f"sub{rnd.randrange(100)}", "urun": f"Uygulama{rnd.randrange(30)}",
                       "baslik": f"Searched for terim {rnd.randrange(1000)}"}
                yield EventIn(ts=ts, kind=kind, category=cat, payload=pay, text=f"kayit {i}",
                              event_key=f"b{i}")
        h.add_events(sid, gen())
        ac = {"kalp", "ayak", "zihin"}
        t0 = time.perf_counter()
        hh = harita(h, ac_hassas=ac)
        t_harita = time.perf_counter() - t0
        sure = {}

        def olc(ad, fn):
            t = time.perf_counter()
            r = fn()
            sure[ad] = time.perf_counter() - t
            return r
        for bid in ("bas", "goz", "agiz", "ic", "kalp", "ayak"):
            olc(bid, lambda bid=bid: bolge(h, bid, ac_hassas=ac))
        olc("filtre:site", lambda: bolge(h, "bas", filtre={"site": "site7.example", "ay": ["2024-03", "2024-04"]}))
        olc("filtre:saat", lambda: bolge(h, "goz", filtre={"saat": 5}, utc_kaydirma=3))
        sayfa = olc("kayitlar", lambda: kayitlar(h, "bas", limit=50, offset=20_000))
        olc("kayitlar:filtre", lambda: kayitlar(h, "goz", filtre={"kanal": "Kanal 7"}, limit=50))
        olc("kayitlar:hassas", lambda: kayitlar(h, "ayak", ac_hassas=ac, limit=50))
        olc("ayrinti", lambda: ayrinti(h, sayfa["kayitlar"][0]["event_id"]))
        olc("karsilastir", lambda: karsilastir(h, "bas", ("2023-01-01T00:00:00Z", "2023-12-31T23:59:59Z"),
                                               ("2024-01-01T00:00:00Z", "2024-12-31T23:59:59Z")))
        olc("karsilastir:goz", lambda: karsilastir(h, "goz", ("2023-01-01T00:00:00Z", "2023-12-31T23:59:59Z"),
                                                   ("2025-01-01T00:00:00Z", "2025-12-31T23:59:59Z")))
    print(f"\nHARITA 200k olay: harita={t_harita:.3f}s {({k: round(v, 3) for k, v in sure.items()})}")
    assert hh["profil"]["olay"] == 200_000  # kalp ve ayak açık, eposta üretilmedi
    assert t_harita < 1.5
    assert max(sure.values()) < 1.5, sure


# ---------------------------------------------------------------- sohbet (Zihin) ve yeni içe aktarıcılar
def _ice_al(hub, *adlar):
    for a in adlar:
        ice_al(hub, FIX / a)


def test_zihin_kilitli_icerik_yok(hub):
    _ice_al(hub, "chat_chatgpt", "chat_claude", "takeout_gemini")
    metinler = [r[0] for r in hub.query("SELECT text FROM events WHERE category = 'sohbet'") if r[0]]
    basliklar = [r[0] for r in hub.query(
        "SELECT json_extract(payload, '$.baslik') FROM events WHERE category = 'sohbet'") if r[0]]
    assert len(metinler) >= 15 and basliklar
    h = harita(hub)
    z = sec(h, "zihin")
    assert z["kilitli"] and z["olay_sayisi"] is None and z["ozet"] == "Kilitli"
    assert z["kategoriler"] == ["sohbet"]
    assert h["profil"]["olay"] == 0  # sohbet sayısı profil toplamına bile sızmaz
    assert bolge(hub, "zihin") == {"id": "zihin", "ad": "Zihin: yapay zekâ sohbetleri",
                                   "kilitli": True, "grafikler": [], "en_cok": [],
                                   "notlar": ["Kilitli"]}
    # başka bir hassas bölgeyi (ya da kategori adını) açmak zihni açmaz
    assert sec(harita(hub, ac_hassas={"kalp", "karin", "ayak", "mesaj"}), "zihin")["kilitli"]
    # açık: yalnız sayı, zaman, platform; içerik asla
    acik = harita(hub, ac_hassas={"zihin"})
    assert sec(acik, "zihin")["olay_sayisi"] == 19 and acik["profil"]["olay"] == 19
    d = bolge(hub, "zihin", ac_hassas={"sohbet"})  # kategori adıyla da açılır
    assert not d["kilitli"] and d["en_cok"] == []
    sayilar = graf(d, "Sayılar")
    assert sayilar["etiketler"] == ["Mesaj", "Konuşma", "Kullanıcı mesajı", "Asistan mesajı"]
    assert sayilar["degerler"][0] == 15 and sayilar["degerler"][1] == 7
    plat = graf(d, "platform")
    assert dict(zip(plat["etiketler"], plat["degerler"])) == {"chatgpt": 8, "claude": 6, "gemini": 5}
    assert graf(d, "Aylık") and graf(d, "saat") and graf(d, "Haftanın")
    tum = json.dumps([acik, d], ensure_ascii=False)
    for parca in metinler + basliklar:
        assert parca not in tum, parca[:30]


def test_kulak_spotify_alanlari(hub):
    _ice_al(hub, "spotify_standart", "spotify_genisletilmis")
    k = bolge(hub, "kulak")
    san = graf(k, "sanatçı (dinleme sayısı)")
    assert san["etiketler"] == sorted(san["etiketler"], key=lambda e: (-san["degerler"][san["etiketler"].index(e)], e))
    assert "Ornek Sanatci" in san["etiketler"]
    assert graf(k, "(dakika)")["degerler"][0] > 0  # sure_ms toplamı dakikaya çevrildi
    assert {e["grup"] for e in k["en_cok"]} >= {"sanatçı", "parça", "podcast"}
    assert any(e["grup"] == "podcast" and e["ad"] == "Ornek Podcast" for e in k["en_cok"])
    assert graf(k, "Aylık")
    assert any("gerçek zaman yok" in n for n in k["notlar"])  # kütüphane anlık görüntüsü


def test_el_github_ve_dosya_turleri(hub):
    _ice_al(hub, "github")
    sid = hub.add_source("dosya", "1", None)
    hub.add_events(sid, [
        E("dosya.kayit", "dosyalar", "2026-01-01T10:00:00Z", "a.pdf", {"uzanti": ".pdf", "boyut": 2_097_152}, "d1"),
        E("dosya.kayit", "dosyalar", "2026-01-02T10:00:00Z", "b.pdf", {"uzanti": ".pdf", "boyut": 1_048_576}, "d2"),
        E("dosya.kayit", "dosyalar", "2026-01-03T10:00:00Z", "c.txt", {"uzanti": ".txt", "boyut": 1024}, "d3"),
    ])
    el = bolge(hub, "el")
    assert any(e["grup"] == "depo" for e in el["en_cok"])
    assert graf(el, "Programlama dilleri")["etiketler"] == ["Python"]
    tur = graf(el, "Dosya türleri")
    assert dict(zip(tur["etiketler"], tur["degerler"])) == {".pdf": 2, ".txt": 1}
    boy = graf(el, "boyut")
    assert dict(zip(boy["etiketler"], boy["degerler"]))[".pdf"] == 3.0
    assert any("Notlar: bu alan yok" in n for n in el["notlar"])
    assert not any("Depo" in n and "bu alan yok" in n for n in el["notlar"])


# ---------------------------------------------------------------- drill-down: filtre, kayıtlar, ayrıntı, karşılaştırma
def etiketli(b, parca):
    return graf(b, parca)


def test_filtre_elle_sayilmis(hub):
    elle_veri(hub)
    # bas: t1 01-05 08:00 siteler/a, t2 01-06 09:00 siteler/b, t3 02-06 23:30 baska, t4 02-07 10:00 arama,
    #      t5 02-08 10:00 arama (UTC)
    def sayi(b, baslik):
        g = graf(b, baslik)
        return dict(zip(g["etiketler"], g["degerler"])) if g else {}
    b = bolge(hub, "bas", filtre={"site": "siteler.example"})
    assert b["toplam"] == 2 and b["filtre"] == {"site": "siteler.example"}
    assert sayi(b, "Aylık") == {"2026-01": 2}
    assert sayi(b, "siteler") == {"siteler.example": 2} and sayi(b, "aranan") == {}
    assert {k: v for k, v in sayi(b, "saat").items() if v} == {"08": 1, "09": 1}
    b = bolge(hub, "bas", filtre={"ay": "2026-02"})
    assert b["toplam"] == 3 and sayi(b, "siteler") == {"baska.example:8080": 1}
    assert sayi(b, "aranan") == {"kahve makinesi": 2}
    assert bolge(hub, "bas", filtre={"saat": 10})["toplam"] == 2          # UTC 10:00
    b3 = bolge(hub, "bas", filtre={"saat": 13}, utc_kaydirma=3)           # +3: 10:00 -> 13:00
    assert b3["toplam"] == 2
    assert bolge(hub, "bas", filtre={"saat": 2}, utc_kaydirma=3)["toplam"] == 1  # 23:30 -> 02:30
    assert bolge(hub, "bas", filtre={"ay": ["2026-01", "2026-02"]})["toplam"] == 5
    assert bolge(hub, "bas", filtre={"terim": "KAHVE Makinesi"})["toplam"] == 2  # küçük harfe çevrilir
    assert bolge(hub, "bas", filtre={"gun": "Cum"})["toplam"] == 1        # 2026-02-06 Cuma
    assert bolge(hub, "bas", filtre={"gun": 5})["toplam"] == 1            # 5 = Cmt (07 Şubat)
    # çoklu alan VE; boş sonuç
    assert bolge(hub, "bas", filtre={"site": "siteler.example", "ay": "2026-01"})["toplam"] == 2
    bos = bolge(hub, "bas", filtre={"site": "siteler.example", "ay": "2026-02"})
    assert bos["toplam"] == 0 and bos["grafikler"] == [] and bos["notlar"] == ["Filtreye uyan kayıt yok."]
    # video: kanal filtresi
    g = bolge(hub, "goz", filtre={"kanal": "Kanal X"})
    assert g["toplam"] == 2 and sayi(g, "Aylık") == {"2026-03": 2}
    # tür/kategori filtresi
    assert bolge(hub, "bas", filtre={"tur": "google.arama"})["toplam"] == 2
    assert bolge(hub, "el", filtre={"kategori": "notlar"})["toplam"] == 1


def test_filtre_gecersiz_alan_ve_deger(hub):
    elle_veri(hub)
    for f in ({"kanal": "x"}, {"saat": 24}, {"saat": "ab"}, {"ay": "2026-13"}, {"ay": "26-01"},
              {"gun": "Xyz"}, {"gun": 7}, {"site": ""}, {"site": []}, {"nokta": 1}):
        with pytest.raises(FormatError):
            bolge(hub, "bas", filtre=f)
    with pytest.raises(FormatError):
        kayitlar(hub, "bas", filtre={"kanal": "x"})
    with pytest.raises(FormatError):  # hassas bölgede içerik alanıyla filtre yok
        bolge(hub, "kalp", ac_hassas={"kalp"}, filtre={"site": "x"})


def test_anahtar_gidis_donus(fixture_hub):
    """Her grafik noktasının ve en_cok satırının `anahtar`ı filtre olarak geri gönderilince
    süzülen toplam o noktanın sayısına eşit olmalı (cubuk/pasta/zaman/saat/hafta)."""
    _ice_al(fixture_hub, "spotify_standart", "github", "chat_chatgpt", "chat_claude")
    kontrol = 0
    ac = {"zihin"}
    for bid in ("bas", "goz", "kulak", "agiz", "el", "zihin"):
        b = bolge(fixture_hub, bid, ac_hassas=ac)
        assert b["grafikler"], bid
        for g in b["grafikler"]:
            assert len(g["anahtarlar"]) == len(g["etiketler"]) == len(g["degerler"])
            if any(x in g["baslik"] for x in ("dakika", "boyut", "Sayılar")):
                continue
            for a, n in zip(g["anahtarlar"], g["degerler"]):
                if a is None or n == 0:
                    continue
                f = bolge(fixture_hub, bid, ac_hassas=ac, filtre={a["alan"]: a["deger"]})
                assert f["toplam"] == n, (bid, g["baslik"], a, n, f["toplam"])
                kontrol += 1
        for e in b["en_cok"]:
            f = bolge(fixture_hub, bid, ac_hassas=ac, filtre={e["anahtar"]["alan"]: e["anahtar"]["deger"]})
            assert f["toplam"] == e["sayi"], (bid, e)
            kontrol += 1
    assert kontrol > 60
    b = bolge(fixture_hub, "bas")
    aylik = graf(b, "Aylık")
    assert aylik["anahtarlar"][0] == {"alan": "ay", "deger": aylik["etiketler"][0]}
    assert graf(b, "saat")["anahtarlar"][8] == {"alan": "saat", "deger": 8}
    assert graf(b, "Haftanın")["anahtarlar"][0] == {"alan": "gun", "deger": "Pzt"}


def test_kayitlar_sayfalama(hub):
    elle_veri(hub)
    k = kayitlar(hub, "bas", limit=2)
    assert k["toplam"] == 5 and len(k["kayitlar"]) == 2 and k["limit"] == 2 and k["offset"] == 0
    tum = []
    for off in (0, 2, 4):
        tum += kayitlar(hub, "bas", limit=2, offset=off)["kayitlar"]
    assert len(tum) == 5 and len({x["event_id"] for x in tum}) == 5
    assert [x["ts"] for x in tum] == sorted((x["ts"] for x in tum), reverse=True)  # yeniden eskiye
    assert tum[0]["ts"] == "2026-02-08T10:00:00Z" and tum[0]["kind"] == "google.arama"
    assert tum[0]["kaynak_adi"] == "elle" and tum[0]["ozet"] and tum[0]["baslik"]
    assert kayitlar(hub, "bas", limit=2, offset=5)["kayitlar"] == []
    assert kayitlar(hub, "bas", limit=0)["limit"] == 1 and kayitlar(hub, "bas", limit=10**6)["limit"] == 200
    assert kayitlar(hub, "bas", offset=-3)["offset"] == 0
    f = kayitlar(hub, "bas", filtre={"ay": "2026-01"}, limit=10)
    assert f["toplam"] == 2 and {x["ts"][:7] for x in f["kayitlar"]} == {"2026-01"}
    r = kayitlar(hub, "bas", aralik=("2026-02-07T00:00:00Z", None))
    assert r["toplam"] == 2
    with pytest.raises(NotFoundError):
        kayitlar(hub, "yok")


def test_kayitlar_ve_ayrinti_kaynak_adi(fixture_hub):
    k = kayitlar(fixture_hub, "goz", limit=3)
    assert all(x["kaynak_adi"].startswith("google_takeout") for x in k["kayitlar"])
    d = ayrinti(fixture_hub, k["kayitlar"][0]["event_id"])
    assert d["kaynak"]["tur"] == "google_takeout" and len(d["kaynak"]["dosya_sha256"]) == 64
    assert d["kaynak"]["dosyalar"] and d["kaynak"]["dosyalar"][0]["sha256"]
    assert d["kaynak"]["ad"].startswith("google_takeout: ")
    assert d["bolge"] == "goz" and d["alanlar"] and d["metin"] and d["kilitli"] is False


def test_ayrinti_icerik_ve_tekrar(hub):
    sid = elle_veri(hub)
    hub.add_events(sid, [E("chrome.ziyaret", "tarama", "2026-03-01T10:00:00Z", "konumlu sayfa",
                           {"baslik": "x", "lat": 41.5, "url": "https://a.example"}, "g1")])
    k = {x["kind"] + x["ts"]: x for x in kayitlar(hub, "bas", limit=50)["kayitlar"]}
    d = ayrinti(hub, k["google.arama2026-02-08T10:00:00Z"]["event_id"])
    assert d["tekrar"] == {"ilk": "2026-02-07T10:00:00Z", "son": "2026-02-08T10:00:00Z", "sayi": 2}
    assert d["ts"] == "2026-02-08T10:00:00Z" and d["kaynak"]["tur"] == "elle"
    g = ayrinti(hub, k["chrome.ziyaret2026-03-01T10:00:00Z"]["event_id"])
    assert g["alanlar"]["lat"] == "[konum alanı gizlendi]" and g["alanlar"]["baslik"] == "x"
    with pytest.raises(NotFoundError):
        ayrinti(hub, "yok")


def test_hassas_kayitlar_ve_ayrinti_icerik_yok(hub):
    elle_veri(hub)
    # kilitli
    for bid in ("kalp", "karin", "ayak", "zihin"):
        assert kayitlar(hub, bid) == {"id": bid, "kilitli": True, "toplam": None, "kayitlar": []}
    ids = {r[0]: r[1] for r in hub.query("SELECT event_id, category FROM events")}
    for eid, cat in ids.items():
        if cat in ("mesaj", "eposta", "konum", "medya_meta"):
            assert ayrinti(hub, eid) == {"event_id": eid, "kilitli": True}
    # açık: içerik asla
    ac = {"kalp", "karin", "ayak"}
    parcalar = []
    for bid, n in (("kalp", 2), ("karin", 1), ("ayak", 3)):
        k = kayitlar(hub, bid, ac_hassas=ac)
        assert k["toplam"] == n and len(k["kayitlar"]) == n
        for x in k["kayitlar"]:
            assert x["baslik"] is None and x["ozet"] is None and x["kaynak_adi"] == "elle"
            assert set(x) == {"event_id", "ts", "kind", "kategori", "baslik", "ozet", "kaynak_adi"}
            d = ayrinti(hub, x["event_id"], ac_hassas=ac)
            assert d["alanlar"] is None and d["metin"] is None and d["tekrar"] is None
            parcalar += [json.dumps(x, ensure_ascii=False), json.dumps(d, ensure_ascii=False)]
    tum = "\n".join(parcalar)
    for yasak in (SIR_METIN, SIR_URL, "Gizli Mahalle", "Baska Gizli", "41.01", "28.98", "41.5",
                  "gizli.example", "FOTO-GIZLI-METIN"):
        assert yasak not in tum, yasak
    # yalnız kategori adıyla açılan bölge de aynı
    assert kayitlar(hub, "ayak", ac_hassas={"konum"})["toplam"] == 3


def test_tombstone_drilldown(hub):
    sid = elle_veri(hub)
    onceki = kayitlar(hub, "bas", limit=50)
    gizle = onceki["kayitlar"][0]["event_id"]
    hub.hide_event(gizle, "test")
    sonra = kayitlar(hub, "bas", limit=50)
    assert sonra["toplam"] == onceki["toplam"] - 1
    assert gizle not in {x["event_id"] for x in sonra["kayitlar"]}
    assert bolge(hub, "bas")["toplam"] == onceki["toplam"] - 1
    assert bolge(hub, "bas", filtre={"ay": "2026-02"})["toplam"] == 2
    with pytest.raises(NotFoundError):
        ayrinti(hub, gizle)
    hub.remove_source(sid, "yanlış")
    assert kayitlar(hub, "bas")["toplam"] == 0 and bolge(hub, "bas", filtre={"ay": "2026-01"})["toplam"] == 0
    k = karsilastir(hub, "bas", ("2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z"),
                    ("2026-02-01T00:00:00Z", "2026-02-28T23:59:59Z"))
    assert k["a"]["toplam"] == 0 and k["b"]["toplam"] == 0 and k["fark"]["yuzde"] is None


def test_karsilastir(hub):
    elle_veri(hub)
    ocak = ("2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z")
    subat = ("2026-02-01T00:00:00Z", "2026-02-28T23:59:59Z")
    k = karsilastir(hub, "bas", ocak, subat)
    assert k["kilitli"] is False and k["a"]["toplam"] == 2 and k["b"]["toplam"] == 3
    assert k["fark"] == {"toplam": 1, "yuzde": 50.0}
    assert k["a"]["aralik"] == list(ocak)
    d = {(e["grup"], e["ad"]): e for e in k["en_cok_degisim"]}
    assert d[("site", "siteler.example")]["a"] == 2 and d[("site", "siteler.example")]["b"] == 0
    assert d[("site", "siteler.example")]["fark"] == -2
    assert d[("arama terimi", "kahve makinesi")]["b"] == 2
    assert [e["fark"] for e in k["en_cok_degisim"]] == sorted((e["fark"] for e in k["en_cok_degisim"]),
                                                              key=abs, reverse=True)
    # filtreyle birlikte
    kf = karsilastir(hub, "bas", ocak, subat, filtre={"saat": 9})
    assert kf["a"]["toplam"] == 1 and kf["b"]["toplam"] == 0
    # kilitli hassas bölge
    assert karsilastir(hub, "kalp", ocak, subat) == {"id": "kalp", "ad": "Kalp: kişisel (hassas)",
                                                     "kilitli": True, "notlar": ["Kilitli"]}
    ac = karsilastir(hub, "kalp", ("2026-07-01T00:00:00Z", "2026-07-31T23:59:59Z"),
                     ("2026-08-01T00:00:00Z", "2026-08-31T23:59:59Z"), ac_hassas={"kalp"})
    assert ac["a"]["toplam"] == 0 and ac["b"]["toplam"] == 2 and ac["fark"]["yuzde"] is None
    assert SIR_METIN not in json.dumps(ac, ensure_ascii=False)
