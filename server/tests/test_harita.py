"""Persona Haritası testleri (sentetik veri; importers fixtures + elle yazılmış olaylar)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from kimlikcore import EventIn, Hub, NotFoundError
from kimlikimport.run import run as ice_al

from kimlikserver.harita import HASSAS_BOLGELER, VARSAYILAN_BOLGELER, bolge, harita
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
    assert {"ad": "ornek", "sayi": 3, "grup": "subreddit"} in s["en_cok"]
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
    assert agiz["en_cok"] == [{"ad": "ornek", "sayi": 2, "grup": "subreddit"}]  # abone sayılmaz
    assert graf(agiz, "Aylık")["degerler"] == [2]  # dosya tarihli abone grafikte yok
    assert any("gerçek zaman yok" in n for n in agiz["notlar"])
    el = bolge(hub, "el")
    pasta = graf(el, "Kategoriler")
    assert dict(zip(pasta["etiketler"], pasta["degerler"])) == {"notlar": 1, "dosyalar": 1}
    assert any("bu alan yok" in n for n in el["notlar"])
    ic = bolge(hub, "ic")
    assert ic["en_cok"][0] == {"ad": "Maps", "sayi": 2, "grup": "uygulama"}
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
        t0 = time.perf_counter()
        hh = harita(h, ac_hassas={"kalp", "ayak"})
        t_harita = time.perf_counter() - t0
        sure = {}
        for bid in ("bas", "goz", "agiz", "ic", "kalp", "ayak"):
            t0 = time.perf_counter()
            bolge(h, bid, ac_hassas={"kalp", "ayak"})
            sure[bid] = time.perf_counter() - t0
    print(f"\nHARITA 200k olay: harita={t_harita:.3f}s bolge={ {k: round(v, 3) for k, v in sure.items()} }")
    assert hh["profil"]["olay"] == 200_000  # kalp ve ayak açık, eposta üretilmedi
    assert t_harita < 3.0
    assert max(sure.values()) < 3.0


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
