"""Madde 10 ve 12 (sunucu): hassas konu izni, olay önemi; kayit_getir sınırları, enjeksiyon.
Tüm veri sentetiktir. İşareti çekirdek hesaplar (ör. "doktor randevusu" -> saglik)."""
from __future__ import annotations

import json

import pytest
from kimlikcore import Hub

from helpers import FakeClock, INJECTION, T0, ev
from kimlikserver.access import (AccessLog, KeyManager, SensitiveConfirmationRequired,
                                 UnknownTopic, konu_kosulu, list_topics)
from kimlikserver.__main__ import main as yonetim
from kimlikserver.service import QueryService, ServiceError

SAGLIK = "doktor randevusu"
FINANS = "kredi borcu"
KATEGORILER = ("notlar", "dosyalar", "sosyal", "persona")


def _ids(root):
    with Hub.open(root, write=False) as hub:
        return {r[0]: r[1] for r in hub.query("SELECT event_key, event_id FROM events")}


@pytest.fixture
def w(veri):
    clock = FakeClock()
    with Hub.open(veri, write=True) as hub:
        sid = hub.add_source("test", "1", None)
        olaylar = [
            ev(f"kahve {SAGLIK} notu", "notlar", key="n_s"),
            ev(f"kahve {FINANS} notu", "notlar", key="n_f"),
            ev(f"kahve {SAGLIK} {FINANS} notu", "notlar", key="n_sf"),
            ev("kahve sade notu", "notlar", key="n_0"),
            ev(f"kahve {SAGLIK} zamansiz", "notlar", key="n_z",
               payload={"zaman_kaynagi": "dosya_tarihi"}),
            ev(f"kahve {SAGLIK} sohbeti", "sohbet", kind="sohbet.mesaj", key="s_s",
               payload={"rol": "kullanici"}),
            ev("kahve sade sohbet", "sohbet", kind="sohbet.mesaj", key="s_0",
               payload={"rol": "kullanici"}),
            ev(f"{SAGLIK} raporu", "dosyalar", key="d_s", payload={"uzanti": "xyz"}),
            ev("sade rapor bir", "dosyalar", key="d_0", payload={"uzanti": "pdf"}),
            ev("sade rapor iki", "dosyalar", key="d_1", payload={"uzanti": "pdf"}),
        ]
        hub.add_events(sid, olaylar)
        km = KeyManager(hub, clock=clock)
        app, key = km.create_key("Konulu")
        for k in ("notlar", "dosyalar", "persona", "tarama"):
            km.grant(app, k)
        km.grant(app, "sohbet", confirmed_sensitive=True)
        app2, key2 = km.create_key("Ikinci")
        km.grant(app2, "notlar")
    return {"root": veri, "app": app, "key": key, "app2": app2, "key2": key2, "clock": clock,
            "ids": _ids(veri)}


def servis(w, key=None):
    return QueryService(w["root"], key or w["key"], clock=w["clock"])


def yonet(w):
    return Hub.open(w["root"], write=True)


def konu_ver(w, *konular, app=None, **kw):
    with yonet(w) as hub:
        for k in konular:
            KeyManager(hub, clock=w["clock"]).grant_topic(app or w["app"], k, confirmed=True, **kw)


def metinler(cevap):
    return sorted(r["veri"] for r in cevap["kayitlar"])


def id_listesi(cevap):
    return {r["id"] for r in cevap["kayitlar"]}


# ------------------------------------------------------------------ access.py
def test_grant_topic_onay_bayragi_ve_bilinmeyen_konu(w):
    with yonet(w) as hub:
        km = KeyManager(hub)
        with pytest.raises(SensitiveConfirmationRequired):
            km.grant_topic(w["app"], "saglik", confirmed=False)
        with pytest.raises(UnknownTopic):
            km.grant_topic(w["app"], "yok_boyle", confirmed=True)
        assert hub.query("SELECT COUNT(*) FROM konu_izinleri")[0][0] == 0
    assert {"saglik", "finans", "hukuk", "din_siyaset", "cinsellik"} <= set(list_topics())


def test_grant_all_non_sensitive_konu_izni_vermez(w):
    with yonet(w) as hub:
        KeyManager(hub).grant_all_non_sensitive(w["app2"])
        assert hub.query("SELECT COUNT(*) FROM konu_izinleri")[0][0] == 0


def test_allowed_topics_sure_ve_iptal_yeniden_okunur(w):
    from kimlikserver.access import Authorizer
    konu_ver(w, "saglik", expires_at="2026-11-09T13:00:00Z")
    konu_ver(w, "finans")
    with Hub.open(w["root"], write=False) as hub:
        a = Authorizer(hub, clock=w["clock"])
        assert a.allowed_topics(w["app"]) == {"saglik", "finans"}
        assert a.allowed_topics(w["app"], "2026-11-09T14:00:00Z") == {"finans"}
    with yonet(w) as hub:
        KeyManager(hub).revoke_topic(w["app"], "finans")
    with Hub.open(w["root"], write=False) as hub:
        assert Authorizer(hub, clock=w["clock"]).allowed_topics(w["app"]) == {"saglik"}


def test_konu_kosulu_buyuk_kume_dogru(veri):
    with Hub.open(veri, write=True) as hub:
        hub.add_events(hub.add_source("t", "1", None), [
            ev(f"a {SAGLIK} {FINANS}", "notlar", key="x"), ev("b sade", "notlar", key="y")])
        konular = [f"k{i}" for i in range(10)]
        sql, a = konu_kosulu(konular)
        assert hub.query(f"SELECT COUNT(*) FROM events WHERE {sql}", a)[0][0] == 1
        sql, a = konu_kosulu(["finans", "saglik", *konular])
        assert hub.query(f"SELECT COUNT(*) FROM events WHERE {sql}", a)[0][0] == 2


# ------------------------------------------------------------------ her yolda: izinsiz yok, izinle var
def test_ara_izinsiz_donmez_izinle_doner(w):
    s = servis(w)
    assert metinler(s.ara("kahve", kategori="notlar", limit=50)) == ["kahve sade notu"]
    assert metinler(s.ara("kahve", kategori="notlar", genislet=False, rol=None, limit=50)) == \
        ["kahve sade notu"]
    assert metinler(s.ara("kahve", kategori="sohbet", rol="kullanici")) == ["kahve sade sohbet"]
    konu_ver(w, "saglik")
    assert len(s.ara("kahve", kategori="notlar", limit=50)["kayitlar"]) == 3   # n_s, n_z, n_0
    assert len(s.ara("kahve", kategori="sohbet", rol="kullanici")["kayitlar"]) == 2


def test_iki_konulu_kayit_icin_tek_izin_yetmez(w):
    s = servis(w)
    konu_ver(w, "saglik")
    assert w["ids"]["n_sf"] not in id_listesi(s.ara("kahve", kategori="notlar", limit=50))
    with pytest.raises(ServiceError):
        s.kayit_getir(w["ids"]["n_sf"])
    konu_ver(w, "finans")
    assert w["ids"]["n_sf"] in id_listesi(s.ara("kahve", kategori="notlar", limit=50))
    assert s.kayit_getir(w["ids"]["n_sf"])["id"] == w["ids"]["n_sf"]


def test_ornekle_ve_zaman_cizelgesi_ve_kayit_getir(w):
    s = servis(w)
    n_s, n_z = w["ids"]["n_s"], w["ids"]["n_z"]
    for _ in range(3):
        assert id_listesi(s.ornekle("notlar", 50)) == {w["ids"]["n_0"]}
        assert id_listesi(s.ornekle("notlar", 50, sorgu="kahve")) == {w["ids"]["n_0"]}
    z = s.zaman_cizelgesi(kategori="notlar", limit=50)
    assert id_listesi(z) == {w["ids"]["n_0"]} and z["zamansiz_kayitlar"] == [] \
        and z["zamansiz_toplam"] == 0
    iletiler = set()
    for kimlik in (n_s, n_z, "yok-yok"):
        with pytest.raises(ServiceError) as e:
            s.kayit_getir(kimlik)
        iletiler.add(str(e.value))
    assert len(iletiler) == 1
    konu_ver(w, "saglik")
    assert {w["ids"]["n_0"], n_s} <= id_listesi(s.ornekle("notlar", 50))
    z = s.zaman_cizelgesi(kategori="notlar", limit=50)
    assert n_s in id_listesi(z) and z["zamansiz_toplam"] == 1
    assert [r["id"] for r in z["zamansiz_kayitlar"]] == [n_z]
    assert s.kayit_getir(n_s)["id"] == n_s


def test_persona_oner_izinsiz_konulu_kanit_yok_gibi(w):
    s = servis(w)
    def oner(kimlik):
        return s.persona_oner([{"ifade": "Kahveyi sever", "kategori": "ilgi", "kanit": [kimlik],
                                "guven": 0.8}])
    with pytest.raises(ServiceError) as yok:
        oner("yok-yok")
    with pytest.raises(ServiceError) as izinsiz:
        oner(w["ids"]["n_s"])
    assert str(yok.value) == str(izinsiz.value)
    konu_ver(w, "saglik")
    assert oner(w["ids"]["n_s"])["eklenen"] == 1


def test_say_icerik_alanlari_isaretlileri_saymaz_diger_alanlar_sayar(w):
    s = servis(w)
    r = s.say("uzanti", kategori="dosyalar")
    assert r["satirlar"] == [["pdf", 2]] and r["toplam_kayit"] == 2
    assert s.say("tur", kategori="dosyalar")["toplam_kayit"] == 3        # içerik olmayan: yalnız sayı
    assert s.say("kategori", kategori="notlar")["toplam_kayit"] == 5
    konu_ver(w, "saglik")
    r = s.say("uzanti", kategori="dosyalar")
    assert sorted(map(tuple, r["satirlar"])) == [("pdf", 2), ("xyz", 1)]


def test_kimlik_karti_isaretli_kayit_konu_izniyle_bile_kullanilmaz(w):
    s = servis(w)
    for kisa in (False, True):
        konu_ver(w, "saglik")
        k = s.kimlik_karti(kisa=kisa)["veri"]
        assert "pdf" in k and "xyz" not in k
    assert "dosyalar: 2 kayıt" in s.kimlik_karti(kisa=False)["veri"]


# ------------------------------------------------------------------ limit, süre, iptal, bilgi
def test_ara_limit_dogru_dolar(veri):
    with Hub.open(veri, write=True) as hub:
        sid = hub.add_source("t", "1", None)
        hub.add_events(sid, [ev(f"zebra {SAGLIK} {i}", "notlar", key=f"i{i}",
                                ts=f"2026-11-02T10:00:{i:02d}Z") for i in range(30)]
                       + [ev(f"zebra sade {i}", "notlar", key=f"u{i}",
                             ts=f"2026-10-02T10:00:{i:02d}Z") for i in range(3)])
        km = KeyManager(hub)
        app, key = km.create_key("L")
        km.grant(app, "notlar")
    s = QueryService(veri, key)
    for kw in ({}, {"genislet": False}):
        assert len(s.ara("zebra", limit=3, **kw)["kayitlar"]) == 3
    assert all("sade" in r["veri"] for r in s.ara("zebra", limit=3)["kayitlar"])
    assert len(s.ornekle("notlar", 3, sorgu="zebra")["kayitlar"]) == 3


def test_suresi_dolan_konu_izni_ve_iptal_edilen_anahtar(w):
    konu_ver(w, "saglik", expires_at="2026-11-09T13:00:00Z")
    s = servis(w)
    assert len(s.ara("kahve", kategori="notlar", limit=50)["kayitlar"]) == 3
    w["clock"].advance(hours=2)
    assert metinler(s.ara("kahve", kategori="notlar", limit=50)) == ["kahve sade notu"]
    w["clock"].advance(hours=-2)
    assert len(s.ara("kahve", kategori="notlar", limit=50)["kayitlar"]) == 3
    with yonet(w) as hub:
        KeyManager(hub).revoke_key(w["app"])
    with pytest.raises(ServiceError, match="reddedildi"):
        s.ara("kahve", kategori="notlar")


def test_kategorileri_listele_hassas_konular(w):
    s = servis(w)
    k = s.kategorileri_listele()["hassas_konular"]
    assert k["acik"] == [] and {"saglik", "finans"} <= set(k["kapali"])
    konu_ver(w, "saglik")
    k = s.kategorileri_listele()["hassas_konular"]
    assert k["acik"] == ["saglik"] and "saglik" not in k["kapali"] and "finans" in k["kapali"]
    assert set(k) == {"acik", "kapali"} and all(isinstance(x, str) for x in k["acik"] + k["kapali"])


def test_cevaplarda_isaretli_kayit_sayisi_sizmaz(w):
    s = servis(w)
    cevaplar = [s.ara("kahve"), s.zaman_cizelgesi(), s.ornekle("notlar", 50), s.say("tur"),
                s.say("uzanti", kategori="dosyalar"), s.kategorileri_listele(),
                s.kimlik_karti(), s.kimlik_karti(kisa=False)]
    for c in cevaplar:
        j = json.dumps(c, ensure_ascii=False)
        assert SAGLIK not in j and FINANS not in j
    assert s.zaman_cizelgesi(kategori="notlar")["zamansiz_toplam"] == 0
    with pytest.raises(ServiceError) as e:
        s.kayit_getir(w["ids"]["n_s"])
    assert "hassas" not in str(e.value).lower() and "konu" not in str(e.value).lower()


def test_erisim_kaydi_yazilir(w):
    servis(w).ara("kahve", kategori="notlar")
    kayit = [r for r in AccessLog(w["root"]).read_all() if r[2] == "ara"]
    assert kayit and kayit[-1][1] == w["app"] and kayit[-1][5] == "ok" and kayit[-1][4] == 1


# ------------------------------------------------------------------ Madde 12: önem
@pytest.fixture
def sosyal(veri):
    with Hub.open(veri, write=True) as hub:
        sid = hub.add_source("t", "1", None)
        olaylar = ([ev(f"GONDERI {i}", "sosyal", kind="reddit.gonderi", key=f"g{i}") for i in range(3)]
                   + [ev(f"OLAGAN {i}", "sosyal", kind="sosyal.paylasim", key=f"o{i}") for i in range(4)]
                   + [ev(f"BEGENI {i}", "sosyal", kind="instagram.begeni", key=f"b{i}") for i in range(5)]
                   + [ev(f"zzz {i}", "dosyalar", kind="x.begeni", key=f"z{i}", payload={"uzanti": "zzz"})
                      for i in range(3)]
                   + [ev("belge", "dosyalar", key="dp", payload={"uzanti": "pdf"})])
        hub.add_events(sid, olaylar)
        km = KeyManager(hub)
        app, key = km.create_key("S")
        for k in ("sosyal", "dosyalar", "persona"):
            km.grant(app, k)
    return {"root": veri, "key": key, "ids": _ids(veri)}


def _tur(r):
    return r["veri"].split()[0]


def test_ornekle_onem_kovalari(sosyal):
    s = QueryService(sosyal["root"], sosyal["key"])
    for _ in range(5):
        assert {_tur(r) for r in s.ornekle("sosyal", 3)["kayitlar"]} == {"GONDERI"}
        k = s.ornekle("sosyal", 5)["kayitlar"]
        assert sorted(map(_tur, k)) == ["GONDERI"] * 3 + ["OLAGAN"] * 2
        assert all("dusuk" not in r for r in k)
    k = s.ornekle("sosyal", 10)["kayitlar"]
    assert sorted(map(_tur, k)) == ["BEGENI"] * 3 + ["GONDERI"] * 3 + ["OLAGAN"] * 4
    assert all(r.get("dusuk") is True for r in k if _tur(r) == "BEGENI")
    assert all("dusuk" not in r and "onem" not in r for r in k if _tur(r) != "BEGENI")
    goruldu = set()
    for _ in range(6):
        goruldu |= {_tur(r) for r in s.ornekle("sosyal", 7, dusuk_onem=True)["kayitlar"]}
    assert "BEGENI" in goruldu


def test_ara_esit_rankte_onem_sonra_zaman(veri):
    with Hub.open(veri, write=True) as hub:
        hub.add_events(hub.add_source("t", "1", None), [
            ev("esitmetin kelime", "sosyal", kind="instagram.begeni", key="dusuk",
               ts="2026-11-05T10:00:00Z"),
            ev("esitmetin kelime", "sosyal", kind="reddit.gonderi", key="yuksek_eski",
               ts="2026-11-01T10:00:00Z"),
            ev("esitmetin kelime", "sosyal", kind="reddit.gonderi", key="yuksek_yeni",
               ts="2026-11-03T10:00:00Z")])
        km = KeyManager(hub)
        app, key = km.create_key("E")
        km.grant(app, "sosyal")
    ids = _ids(veri)
    r = QueryService(veri, key).ara("esitmetin", genislet=False)["kayitlar"]
    assert [x["id"] for x in r] == [ids["yuksek_yeni"], ids["yuksek_eski"], ids["dusuk"]]


def test_kart_dusuk_onem_ozet_uretmez_tek_satir_sayi(sosyal):
    s = QueryService(sosyal["root"], sosyal["key"])
    for kisa in (True, False):
        k = s.kimlik_karti(kisa=kisa)["veri"]
        assert "5 beğeni/takip kaydı (düşük önem, özetlenmedi)" in k
        assert "BEGENI" not in k
        assert "pdf" in k and "zzz" not in k            # ham_top önem 0'ı dışlar


def test_persona_oner_tum_kanit_dusukse_reddedilir(sosyal):
    s = QueryService(sosyal["root"], sosyal["key"])
    ids = sosyal["ids"]
    def oner(*kanit):
        return s.persona_oner([{"ifade": "Gezmeyi sever", "kategori": "ilgi",
                                "kanit": list(kanit), "guven": 0.7}])
    with pytest.raises(ServiceError, match="düşük önemli"):
        oner(ids["b0"], ids["b1"])
    assert oner(ids["b0"], ids["g0"])["eklenen"] == 1


# ------------------------------------------------------------------ Madde C: kayit_getir sınırları
def test_kayit_getir_sinirlari(w):
    s = servis(w)
    n0 = w["ids"]["n_0"]
    with Hub.open(w["root"], write=True) as hub:
        hub.add_events(hub.add_source("u", "1", None), [
            ev("0123456789" * 5, "notlar", key="uzun"),
            ev("gps kaydi", "notlar", key="gpsli", payload={"gps": {"lat": 1.0, "lon": 2.0}})])
    ids = _ids(w["root"])
    uz = ids["uzun"]
    assert s.kayit_getir(uz, -5, 10)["veri"] == "0123456789"         # negatif başlangıç -> 0
    r = s.kayit_getir(uz, 45, 100)
    assert r["veri"] == "56789" and r["uzunluk"] == 50 and "devam" not in r
    r = s.kayit_getir(uz, 500, 10)                                    # metin sonunu aşan
    assert r["veri"] == "" and r["uzunluk"] == 50 and "devam" not in r
    for u in (0, -3):
        r = s.kayit_getir(uz, 0, u)
        assert r["veri"] == "0" and r["devam"] == 1
    assert s.kayit_getir(n0)["veri"] == "kahve sade notu"
    with pytest.raises(ServiceError, match="reddedildi"):            # GPS savunması (konum izni yok)
        s.kayit_getir(ids["gpsli"])


def test_kayit_getir_suresi_dolmus_kategori_izni(veri):
    clock = FakeClock()
    with Hub.open(veri, write=True) as hub:
        hub.add_events(hub.add_source("t", "1", None), [ev("not metni", "notlar", key="n")])
        km = KeyManager(hub, clock=clock)
        app, key = km.create_key("Sureli")
        km.grant(app, "notlar", expires_at="2026-11-09T13:00:00Z")
    kimlik = _ids(veri)["n"]
    s = QueryService(veri, key, clock=clock)
    assert s.kayit_getir(kimlik)["veri"] == "not metni"
    clock.advance(hours=2)
    with pytest.raises(ServiceError, match="reddedildi"):
        s.kayit_getir(kimlik)


# ------------------------------------------------------------------ Madde C: enjeksiyon
def test_enjeksiyon_yalniz_veri_alaninda_diger_yollar(veri):
    with Hub.open(veri, write=True) as hub:
        hub.add_events(hub.add_source("z", "1", None), [ev(INJECTION, "notlar", key="inj")])
        km = KeyManager(hub)
        app, key = km.create_key("Enj")
        km.grant(app, "notlar")
    s = QueryService(veri, key)
    kimlik = _ids(veri)["inj"]
    for cevap in (s.ornekle("notlar", 5), s.zaman_cizelgesi(kategori="notlar"),
                  s.ornekle("notlar", 5, sorgu="talimatları")):
        assert [k["veri"] for k in cevap["kayitlar"]] == [INJECTION]
        cevap["kayitlar"][0]["veri"] = ""
        assert INJECTION not in json.dumps(cevap, ensure_ascii=False)
    r = s.kayit_getir(kimlik)
    assert r["veri"] == INJECTION
    r["veri"] = ""
    assert INJECTION not in json.dumps(r, ensure_ascii=False)


# ------------------------------------------------------------------ Madde E: CLI uyarısı
def test_anahtar_uret_izinsiz_uyarir(veri, capsys):
    with Hub.open(veri, write=True):
        pass
    assert yonetim(["--veri", str(veri), "anahtar-uret", "--ad", "Bos"]) == 0
    c = capsys.readouterr()
    assert "Bu anahtarın hiçbir kategori izni yok; hiçbir şeyi göremez." in c.err
    assert "anahtar: kim_" in c.out
    assert yonetim(["--veri", str(veri), "anahtar-uret", "--ad", "Dolu", "--izin", "notlar"]) == 0
    assert "hiçbir kategori izni yok" not in capsys.readouterr().err


# ------------------------------------------------------------------ inceleme küçükleri
def _kur(veri, olaylar, kategoriler=("notlar",), hassas=()):
    with Hub.open(veri, write=True) as hub:
        hub.add_events(hub.add_source("t", "1", None), olaylar)
        km = KeyManager(hub)
        app, key = km.create_key("K")
        for k in kategoriler:
            km.grant(app, k, confirmed_sensitive=k in hassas)
    return app, key


def test_esanlam_genislemesinde_isaretli_kayit_donmez_sayilar_degismez(veri):
    (veri / "esanlamlilar.json").write_text(json.dumps(
        {"alt_kavramlar": {"linux": ["fedora"]}}), encoding="utf-8")
    app, key = _kur(veri, [ev("linux notu bir", "notlar", key="a"),
                           ev("fedora kurulumu sade", "notlar", key="b"),
                           ev(f"fedora kurulumu {SAGLIK}", "notlar", key="c")])
    s = QueryService(veri, key)
    r = s.ara("linux", genislet=True)
    assert metinler(r) == ["fedora kurulumu sade", "linux notu bir"]
    def fedora(c):
        return [i for t in c["genisletilen_terimler"] for i in t["iliskili"]
                if i["terim"] == "fedora"]
    onceki = fedora(r)
    assert onceki == [{"terim": "fedora", "kayit": 1}]
    with Hub.open(veri, write=True) as hub:
        hub.add_events(hub.add_source("u", "1", None), [
            ev(f"fedora ayrıca {SAGLIK} {i}", "notlar", key=f"x{i}") for i in range(5)])
    assert fedora(s.ara("linux")) == onceki
    with Hub.open(veri, write=True) as hub:
        KeyManager(hub).grant_topic(app, "saglik", confirmed=True)
    r = s.ara("linux", limit=50)
    assert any(SAGLIK in k["veri"] for k in r["kayitlar"])
    assert fedora(r) == [{"terim": "fedora", "kayit": 7}]


def test_konu_kimliginde_tirnak_ve_ters_bolu_sorgulari_bozmaz(veri):
    app, key = _kur(veri, [ev("alfa sade", "notlar", key="s"), ev("alfa tirnakli", "notlar", key="q"),
                           ev("alfa tersbolu", "notlar", key="b"), ev("alfa ikili", "notlar", key="i")])
    ids = _ids(veri)
    with Hub.open(veri, write=True) as hub:
        with hub.transaction() as c:
            c.execute("UPDATE events SET hassas_konu = ? WHERE event_id = ?", ('x"y', ids["q"]))
            c.execute("UPDATE events SET hassas_konu = ? WHERE event_id = ?", ("x\\y", ids["b"]))
            c.execute("UPDATE events SET hassas_konu = ? WHERE event_id = ?", ('saglik,x"y', ids["i"]))
        km = KeyManager(hub)
    s = QueryService(veri, key)
    assert metinler(s.ara("alfa", kategori="notlar", limit=50)) == ["alfa sade"]
    assert metinler(s.ornekle("notlar", 50)) == ["alfa sade"]
    assert metinler(s.zaman_cizelgesi(kategori="notlar", limit=50)) == ["alfa sade"]
    assert s.say("uzanti")["toplam_kayit"] >= 0
    with Hub.open(veri, write=True) as hub:
        KeyManager(hub).grant_topic(app, "saglik", confirmed=True)
    assert metinler(s.ara("alfa", kategori="notlar", limit=50)) == ["alfa sade"]   # x"y hâlâ yok
    with Hub.open(veri, write=True) as hub:           # izin tablosuna doğrudan yaz (geçersiz kimlik)
        with hub.transaction() as c:
            for k in ('x"y', "x\\y"):
                c.execute("INSERT INTO konu_izinleri(app_id, konu, granted_at) VALUES (?, ?, 'x')",
                          (app, k))
    assert metinler(s.ara("alfa", kategori="notlar", limit=50)) == \
        ["alfa ikili", "alfa sade", "alfa tersbolu", "alfa tirnakli"]


def test_kart_onem_sifir_saat_son_donem_ve_kapsami_beslemez(veri):
    olaylar = [ev(f"BEGENI {i}", "sosyal", kind="instagram.begeni", key=f"b{i}",
                  ts=f"2026-11-0{1 + i % 8}T0{i % 9}:00:00Z") for i in range(40)]
    app, key = _kur(veri, olaylar, ("sosyal", "persona"))
    s = QueryService(veri, key, clock=FakeClock())
    for kisa in (False, True):
        k = s.kimlik_karti(kisa=kisa)["veri"]
        assert "etkinlik en çok" not in k
        assert "40 beğeni/takip kaydı (düşük önem, özetlenmedi)" in k
    tam = s.kimlik_karti(kisa=False)["veri"]
    assert "sosyal: 40 kayıt" not in tam and "Son 90 günde yalnız 0 kayıt" in tam


def test_say_sayilari_ve_erisim_sayisi_isaretli_kayitla_degismez(veri):
    app, key = _kur(veri, [ev("sade bir", "dosyalar", key="p1", payload={"uzanti": "pdf"}),
                           ev("sade iki", "dosyalar", key="p2", payload={"uzanti": "pdf"}),
                           ev("sade yok", "dosyalar", key="p3")], ("dosyalar",))
    s = QueryService(veri, key)
    def al():
        r = s.say("uzanti", kategori="dosyalar")
        n = [x for x in AccessLog(veri).read_all() if x[2] == "say"][-1][4]
        return {k: r.get(k) for k in ("toplam_kayit", "alansiz_kayit", "farkli_deger",
                                      "alanli_kayit", "satirlar")}, n
    onceki = al()
    with Hub.open(veri, write=True) as hub:
        hub.add_events(hub.add_source("u", "1", None), (
            [ev(f"{SAGLIK} {i}", "dosyalar", key=f"m{i}", payload={"uzanti": f"e{i}"}) for i in range(4)]
            + [ev(f"{FINANS} yok", "dosyalar", key="m_yok")]))
    assert al() == onceki


def test_hassas_kategori_ve_hassas_konu_birlikte(veri):
    app, key = _kur(veri, [
        ev("sade sohbet bir", "sohbet", kind="sohbet.mesaj", key="a", payload={"rol": "kullanici", "platform": "p"}),
        ev(f"{SAGLIK} sohbeti", "sohbet", kind="sohbet.mesaj", key="b", payload={"rol": "kullanici", "platform": "q"})],
        ("sohbet", "notlar"), hassas=("sohbet",))
    ids = _ids(veri)
    s = QueryService(veri, key)
    # içerik alanları sohbette zaten hesaplanmaz; içerik olmayan alan işaretliyi sayar
    r = s.say("uzanti", kategori="sohbet")
    assert r["satirlar"] == []                       # hassas kategoride içerik alanı hesaplanmaz
    assert s.say("platform", kategori="sohbet")["toplam_kayit"] == 2
    assert s.kayit_getir(ids["a"])["id"] == ids["a"]
    with pytest.raises(ServiceError, match="reddedildi"):
        s.kayit_getir(ids["b"])
    with Hub.open(veri, write=True) as hub:
        KeyManager(hub).grant_topic(app, "saglik", confirmed=True)
        KeyManager(hub).revoke_grant(app, "sohbet")
    with pytest.raises(ServiceError, match="reddedildi"):     # konu izni kategori yerine geçmez
        s.kayit_getir(ids["b"])
