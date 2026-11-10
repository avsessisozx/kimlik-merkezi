"""Genişletilmiş harita sözleşmesi: filtre, aralık, kayıtlar, ayrıntı, karşılaştırma, hassas içerik sızıntısı,
statik dosyalar (yerel ECharts) ve demo veri üreticisi. Sahte sağlayıcı gerçek olaylar üzerinde SQL ile sayar."""
import json
import urllib.request

import pytest
from kimlikcore import Hub

import demo_veri
import harita_sahte
from kimlikwin import harita_kopru
from kimlikwin.cekirdek import IslemHatasi
from kimlikwin.web import Sunucu


@pytest.fixture(autouse=True)
def sahte():
    eski = harita_sahte.kur()
    yield
    harita_kopru.saglayici = eski


@pytest.fixture
def demo(kurulu):
    demo_veri.uret(kurulu.uygulama.hub, olcek=0.04, tohum=3)
    return kurulu


def test_demo_veri_zengin_ve_tekrarlanabilir(kurulu, tmp_path):
    hub = kurulu.uygulama.hub
    r = demo_veri.uret(hub, olcek=0.05, tohum=5)
    assert r["olay"] > 1500 and r["kaynak"] >= 10
    c = hub.query("SELECT category, count(*) FROM events GROUP BY 1")
    assert {k for k, _ in c} >= {"video", "tarama", "sosyal", "muzik", "kod", "uygulama", "eposta", "mesaj", "konum", "sohbet"}
    aylar = hub.query("SELECT count(DISTINCT substr(ts,1,7)) FROM events")[0][0]
    assert aylar >= 30                                         # 2-3 yıl
    # hassas kategorilerde içerik yok
    assert hub.query("SELECT DISTINCT text FROM events WHERE category IN ('eposta','mesaj','konum','sohbet')") == [("(içerik yok)",)]


def test_filtre_capraz_ve_aralik(demo):
    v = demo.api("harita_bolge", {"bolge_id": "goz"})
    kanallar = next(g for g in v["gruplar"] if g["id"] == "kanal")["ogeler"]
    ad, n = kanallar[0]["ad"], kanallar[0]["sayi"]
    f = demo.api("harita_bolge", {"bolge_id": "goz", "filtre": {"kanal": ad}})
    assert f["toplam"] == n and f["filtre"] == {"kanal": ad}
    # çapraz filtre: kanal grafiği kendi filtresini uygulamaz (bağlam kalır), diğerleri uygular
    kg = next(g for g in f["grafikler"] if g.get("boyut") == "kanal")
    assert kg["secili"] == ad and len(kg["etiketler"]) > 1
    assert sum(next(g for g in f["grafikler"] if g["tur"] == "saat")["degerler"]) == n
    # birden çok filtre VE ile birleşir
    f2 = demo.api("harita_bolge", {"bolge_id": "goz", "filtre": {"kanal": ad, "saat": 21}})
    assert f2["toplam"] <= n
    # aralık
    a = demo.api("harita_bolge", {"bolge_id": "goz", "aralik": {"baslangic": "2025-01-01T00:00:00Z", "bitis": "2025-12-31T23:59:59Z"}})
    z = next(g for g in a["grafikler"] if g["tur"] == "zaman")
    assert z["etiketler"][0] >= "2025-01" and z["etiketler"][-1] <= "2025-12"
    assert a["toplam"] < v["toplam"]
    # harita da aralığa uyar
    h = demo.api("harita", {"aralik": {"baslangic": "2025-01-01T00:00:00Z", "bitis": "2025-12-31T23:59:59Z"}})
    assert h["profil"]["ilk"] >= "2025-01-01"


def test_kayitlar_sayfalama_ve_ayrinti(demo):
    k = demo.api("harita_kayitlar", {"bolge_id": "goz", "limit": 5})
    assert len(k["kayitlar"]) == 5 and k["toplam"] > 5
    k2 = demo.api("harita_kayitlar", {"bolge_id": "goz", "limit": 5, "offset": 5})
    assert {r["id"] for r in k["kayitlar"]}.isdisjoint({r["id"] for r in k2["kayitlar"]})
    assert k["kayitlar"][0]["ts"] >= k["kayitlar"][-1]["ts"]
    d = demo.api("harita_ayrinti", {"olay_id": k["kayitlar"][0]["id"]})
    assert d["kategori"] == "video" and d["ham_ts"] == d["ts"] and d["kaynak"]["ad"] == "youtube"
    assert any(a["ad"] == "kanal" for a in d["alanlar"]) and d["metin"]
    with pytest.raises(IslemHatasi):
        demo.api("harita_ayrinti", {"olay_id": "yok-boyle-bir-id"})
    # limit üst sınırı
    assert len(demo.api("harita_kayitlar", {"bolge_id": "goz", "limit": 100000})["kayitlar"]) <= 100


def test_hassas_kayit_ve_ayrinti_icerik_sizdirmaz(demo):
    kilitli = demo.api("harita_kayitlar", {"bolge_id": "kalp"})
    assert kilitli["kilitli"] and kilitli["kayitlar"] == []
    hub = demo.uygulama.hub
    mesaj_id = hub.query_one("SELECT event_id FROM events WHERE category='mesaj' LIMIT 1")[0]
    assert demo.api("harita_ayrinti", {"olay_id": mesaj_id})["kilitli"] is True       # bölge kilitliyken ayrıntı yok
    demo.api("harita_hassas", {"bolge_id": "kalp", "ac": True, "onay": True})
    k = demo.api("harita_kayitlar", {"bolge_id": "kalp", "limit": 3})
    assert all("içerik gizli" in r["baslik"] for r in k["kayitlar"])
    d = demo.api("harita_ayrinti", {"olay_id": k["kayitlar"][0]["id"]})
    assert d["icerik_gizli"] and d["metin"] == "" and d["alanlar"] == [] and d["kaynak"]["ad"] and d["ham_ts"]
    # sağlayıcı içerik dönse bile köprü atar
    s0 = harita_kopru.saglayici
    harita_kopru.saglayici = s0._replace(ayrinti=lambda hub, eid: {"id": eid, "ts": "x", "ham_ts": "x", "metin": "GİZLİ MESAJ", "alanlar": [{"ad": "govde", "deger": "GİZLİ"}], "kaynak": {}})
    d = demo.api("harita_ayrinti", {"olay_id": mesaj_id})
    assert "GİZLİ" not in json.dumps(d, ensure_ascii=False)
    harita_kopru.saglayici = s0._replace(kayitlar=lambda hub, bid, **kw: {"toplam": 1, "kayitlar": [{"id": "1", "ts": "t", "kategori": "mesaj", "baslik": "GİZLİ MESAJ", "alt": "x"}]})
    assert "GİZLİ" not in json.dumps(demo.api("harita_kayitlar", {"bolge_id": "kalp"}), ensure_ascii=False)


def test_gercek_modul_filtreyi_desteklemiyorsa_zarifce_bildirilir(demo):
    s0 = harita_kopru.saglayici
    harita_kopru.saglayici = s0._replace(bolge=lambda hub, bid, ac_hassas=frozenset(): s0.bolge(hub, bid, ac_hassas=ac_hassas), kayitlar=None, ayrinti=None)
    v = demo.api("harita_bolge", {"bolge_id": "goz", "filtre": {"kanal": "x"}})
    assert v["filtre_destegi"] is False
    with pytest.raises(IslemHatasi) as e:
        demo.api("harita_kayitlar", {"bolge_id": "goz"})
    assert e.value.kod == "ozellik_yok"


def test_karsilastirma_baska_kisi_salt_okunur(demo, tmp_path):
    k = demo.api("kisi_ekle", {"ad": "İkinci", "yol": str(tmp_path / "ikinci")})
    ilk = next(x for x in k["kisiler"] if x["ad"] == "Ben")
    demo.api("kisi_sec", {"kisi_id": ilk["id"]})
    ikinci = next(x for x in demo.api("kisiler", {})["kisiler"] if x["ad"] == "İkinci")
    with Hub.open(tmp_path / "ikinci", write=True) as h:
        demo_veri.uret(h, olcek=0.02, tohum=9, profil="deniz")
    b = demo.api("harita_karsilastir", {"kisi_id": ikinci["id"], "bolge_id": "goz"})
    assert b["kisi"] == "İkinci" and b["toplam"] > 0
    a = demo.api("harita_karsilastir", {"kisi_id": ilk["id"], "bolge_id": "goz"})
    assert a["toplam"] > b["toplam"]
    with pytest.raises(IslemHatasi):
        demo.api("harita_karsilastir", {"kisi_id": "yok", "bolge_id": "goz"})


def test_statik_dosyalar_yerel_echarts_ve_cdn_yok(yonetici, veri):
    yonetici.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False})
    s = Sunucu(yonetici, 0)
    s.baslat()
    try:
        def al(yol):
            with urllib.request.urlopen(f"http://127.0.0.1:{s.port}{yol}", timeout=10) as r:
                return r.status, r.headers["Content-Type"], r.read()
        kod, tur, govde = al("/statik/echarts.min.js")
        assert kod == 200 and "javascript" in tur and len(govde) > 500_000 and b"Apache Software Foundation" in govde[:600]
        for ad in ("harita.js", "figur.js", "harita.css", "ECHARTS-LICENSE.txt", "ECHARTS-NOTICE.txt"):
            assert al("/statik/" + ad)[0] == 200
        html = al("/")[2].decode()
        assert "http://" not in html.replace("http://www.w3.org", "") and "https://" not in html      # CDN yok, internetsiz çalışır
        for ad in ("../yonetici.py", "..%2fyonetici.py", "olmayan.js", "index.html.bak"):
            with pytest.raises(urllib.error.HTTPError):
                al("/statik/" + ad)
    finally:
        s.durdur()
