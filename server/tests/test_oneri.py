"""Persona öneri kuyruğu: persona_oner, ornekle, onay işlemleri."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys

import pytest
from kimlikcore import FormatError, Hub, NotFoundError
from mcp import Client, StdioServerParameters

from helpers import INJECTION, ev
from kimlikserver import oneri as oneri_mod
from kimlikserver.access import AccessLog, KeyManager
from kimlikserver.oneri import OneriKuyrugu, OneriYonetici, ifade_ozeti
from kimlikserver.persona import Persona, PersonaReader
from kimlikserver.service import QueryService, ServiceError


def svc(world, key=None):
    return QueryService(world["root"], key or world["a_key"])


def event_ids(world, sorgu="kahve", kategori="notlar"):
    return [r["id"] for r in svc(world).ara(sorgu, kategori)["kayitlar"]]


def eid_of(world, text, category):
    with Hub.open(world["root"], write=False) as h:
        return h.query_one("SELECT event_id FROM events WHERE text = ? AND category = ?",
                           (text, category))[0]


def onerme(world, ifade="Kahve seviyor", kategori="tercihler", guven=0.8, kanit=None, **kw):
    return {"ifade": ifade, "kategori": kategori, "guven": guven,
            "kanit": kanit or event_ids(world)[:1], **kw}


def oneri_rows(world):
    p = world["root"] / "oneri.db"
    if not p.exists():
        return []
    c = sqlite3.connect(p)
    try:
        return c.execute("SELECT oneri_id, app_id, statement, category, durum, kanit_event_ids "
                         "FROM oneriler ORDER BY ts, oneri_id").fetchall()
    finally:
        c.close()


def fact_count(world):
    with Hub.open(world["root"], write=False) as h:
        return h.query_one("SELECT COUNT(*) FROM facts")[0]


def yonet(world):
    return Hub.open(world["root"], write=True)


# ------------------------------------------------------------------ persona_oner
def test_oneri_yazilir_facts_degismez(world):
    r = svc(world).persona_oner([onerme(world, anahtar="icecek")])
    assert r["eklenen"] == 1 and r["sonuclar"][0]["sonuc"] == "eklendi"
    assert "onaylamadan persona değişmez" in r["bilgi"]
    (satir,) = oneri_rows(world)
    assert satir[1] == world["a_id"] and satir[2] == "Kahve seviyor" and satir[4] == "bekliyor"
    assert json.loads(satir[5]) == event_ids(world)[:1]
    assert fact_count(world) == 0
    log = [x for x in AccessLog(world["root"]).read_all() if x[2] == "persona_oner"]
    assert [(x[1], x[3], x[4], x[5]) for x in log] == [(world["a_id"], "notlar", 1, "ok")]


def test_izinsiz_kategoride_kanit_reddedilir(world):
    eposta = eid_of(world, "kahve randevu e-postası", "eposta")
    gecerli = onerme(world)
    for kotu in (eposta, "yok-boyle-bir-olay"):
        with pytest.raises(ServiceError) as e:
            svc(world).persona_oner([gecerli, onerme(world, "Başka", kanit=[kotu])])
        msg = str(e.value)
        assert msg.startswith("reddedildi") and "randevu" not in msg
    assert oneri_rows(world) == []  # geçerli olan da eklenmedi (tümü ya da hiçbiri)
    assert [r[5] for r in AccessLog(world["root"]).read_all()[-2:]] == ["reddedildi"] * 2
    # iki ret iletisi aynı: olayın varlığı sızmaz
    with pytest.raises(ServiceError) as a:
        svc(world).persona_oner([onerme(world, kanit=[eposta])])
    with pytest.raises(ServiceError) as b:
        svc(world).persona_oner([onerme(world, kanit=["yok-boyle-bir-olay"])])
    assert str(a.value) == str(b.value)


def test_izin_verilince_kanit_kabul_edilir(world):
    eposta = eid_of(world, "kahve randevu e-postası", "eposta")
    with Hub.open(world["root"], write=True) as h:
        KeyManager(h).grant(world["a_id"], "eposta", confirmed_sensitive=True)
    assert svc(world).persona_oner([onerme(world, kanit=[eposta])])["eklenen"] == 1
    assert AccessLog(world["root"]).read_all()[-1][3] == "eposta"


def test_gizli_olay_kanit_olamaz(world):
    kid = event_ids(world)[0]
    with Hub.open(world["root"], write=True) as h:
        h.hide_event(kid, "test")
    with pytest.raises(ServiceError):
        svc(world).persona_oner([onerme(world, kanit=[kid])])


def test_dogrulama_hatalari(world):
    k = event_ids(world)[:1]
    kotu = [
        [], "metin", [{"ifade": "", "kategori": "kimlik", "kanit": k, "guven": 0.5}],
        [{"ifade": "x", "kategori": "yok", "kanit": k, "guven": 0.5}],
        [{"ifade": "x", "kategori": "kimlik", "kanit": [], "guven": 0.5}],
        [{"ifade": "x", "kategori": "kimlik", "kanit": k, "guven": 1.5}],
        [{"ifade": "x", "kategori": "kimlik", "kanit": k, "guven": True}],
        [{"ifade": "x", "kategori": "kimlik", "kanit": k}],
        [onerme(world)] * 21,
    ]
    for o in kotu:
        with pytest.raises(ServiceError):
            svc(world).persona_oner(o)
    assert oneri_rows(world) == []


def test_oneri_db_yazilamazsa_reddedilir(world):
    (world["root"] / "oneri.db").mkdir()  # dosya yerine klasör
    with pytest.raises(ServiceError) as e:
        svc(world).persona_oner([onerme(world)])
    assert "reddedildi" in str(e.value)


def test_erisim_kaydi_yazilamazsa_kuyruga_da_yazilmaz(world):
    c = sqlite3.connect(world["root"] / "erisim.db")
    c.execute("DROP TABLE access_log")
    c.commit()
    c.close()
    with pytest.raises(ServiceError):
        svc(world).persona_oner([onerme(world)])
    assert oneri_rows(world) == []  # kayıt önce yazılır; kayıt yoksa yazma da yok


def test_kuyruk_dolu(world, monkeypatch):
    monkeypatch.setattr(oneri_mod, "MAX_BEKLEYEN", 2)
    r = svc(world).persona_oner([onerme(world, f"Bilgi {i}") for i in range(4)])
    assert [x["sonuc"] for x in r["sonuclar"]] == ["eklendi", "eklendi", "kuyruk_dolu", "kuyruk_dolu"]


# ------------------------------------------------------------------ bastırma / tekrar
def test_tekrar_onerilen_kuyruga_girmez(world):
    s = svc(world)
    s.persona_oner([onerme(world, "Kahve seviyor"), onerme(world, "Çay içmez"),
                    onerme(world, "Satranç oynar"), onerme(world, "Kedisi var")])
    with yonet(world) as h:
        y = OneriYonetici(h)
        ids = {o.statement: o.oneri_id for o in y.kuyruk_listele()}
        y.reddet(ids["Çay içmez"])
        y.hic_dogru_degil(ids["Satranç oynar"])
        y.onayla(ids["Kedisi var"])
    # normalleşme: büyük/küçük harf, noktalama, Türkçe katlama, çoklu boşluk
    r = s.persona_oner([
        onerme(world, "çay  İÇMEZ!"),            # reddedilmiş
        onerme(world, "SATRANÇ oynar."),         # hiç doğru değil
        onerme(world, "kedisi var"),             # onaylı
        onerme(world, "Kahve seviyor"),          # hâlâ bekliyor
        onerme(world, "Yeni bilgi"),
        onerme(world, "Yeni bilgi."),            # aynı çağrıda yineleme
    ])
    assert [x["sonuc"] for x in r["sonuclar"]] == [
        "reddedilmis", "bastirilmis", "zaten_onayli", "zaten_kuyrukta", "eklendi", "zaten_kuyrukta"]
    assert r["eklenen"] == 1
    assert len(oneri_rows(world)) == 5
    # farklı kategoride aynı ifade ayrı öneridir
    assert ifade_ozeti("a b", "kimlik") != ifade_ozeti("a b", "ilgi")
    # bastirilan tablosu dolu
    c = sqlite3.connect(world["root"] / "oneri.db")
    assert c.execute("SELECT COUNT(*) FROM bastirilan").fetchone()[0] == 1
    c.close()


# ------------------------------------------------------------------ onay akışı
def test_onay_akisi_facts_e_duser(world, clock):
    svc(world).persona_oner([onerme(world, "İstanbul'da yaşıyor", "kimlik", anahtar="sehir"),
                             onerme(world, "Yanlış bilgi"[:0] + "Düzeltilecek bilgi", "ilgi"),
                             onerme(world, "Reddedilecek", "diger")])
    with yonet(world) as h:
        y = OneriYonetici(h, clock=clock)
        ids = {o.statement: o.oneri_id for o in y.kuyruk_listele()}
        assert len(ids) == 3 and fact_count_hub(h) == 0
        fid = y.onayla(ids["İstanbul'da yaşıyor"])
        f = Persona(h, clock=clock).get_fact(fid)
        assert (f.statement, f.status, f.category, f.fact_key) == \
            ("İstanbul'da yaşıyor", "beyan_edilen", "kimlik", "sehir")
        assert f.valid_from == "2026-11-09T12:00:00Z" and f.source_id is None
        fid2 = y.duzelt(ids["Düzeltilecek bilgi"], "Satranç ilgisi var")
        assert Persona(h, clock=clock).get_fact(fid2).statement == "Satranç ilgisi var"
        y.reddet(ids["Reddedilecek"])
        d = {o.statement: (o.durum, o.fact_id) for o in y.kuyruk_listele(None)}
        assert d["İstanbul'da yaşıyor"] == ("onaylandi", fid)
        assert d["Düzeltilecek bilgi"] == ("duzeltildi", fid2)
        assert d["Reddedilecek"][0] == "reddedildi"
        assert y.kuyruk_listele() == []
        assert fact_count_hub(h) == 2
        with pytest.raises(FormatError):
            y.onayla(ids["İstanbul'da yaşıyor"])  # ikinci karar yok
        with pytest.raises(NotFoundError):
            y.reddet("yok")
        o = [x for x in y.kuyruk_listele("duzeltildi")][0]
        assert o.duzeltilmis_ifade == "Satranç ilgisi var"
    # onaylanan MCP'den görünür
    r = svc(world).persona_getir()
    assert {x["veri"] for x in r["kayitlar"]} == {"İstanbul'da yaşıyor", "Satranç ilgisi var"}


def fact_count_hub(h):
    return h.query_one("SELECT COUNT(*) FROM facts")[0]


def test_onay_celiski_yonetimini_calistirir(world):
    with yonet(world) as h:
        Persona(h).add_fact("Ankara'da yaşıyor", "kimlik", fact_key="sehir")
    svc(world).persona_oner([onerme(world, "İzmir'de yaşıyor", "kimlik", anahtar="sehir")])
    with yonet(world) as h:
        y = OneriYonetici(h)
        y.onayla(y.kuyruk_listele()[0].oneri_id)
        p = Persona(h)
        (c,) = p.list_contradictions()
        assert c.old_fact.statement == "Ankara'da yaşıyor" and c.new_fact.statement == "İzmir'de yaşıyor"
        assert [f.statement for f in p.list_facts(["kimlik"])] == ["İzmir'de yaşıyor"]


def test_toplu_reddet(world):
    svc(world).persona_oner([onerme(world, f"Bilgi {i}") for i in range(5)])
    with yonet(world) as h:
        y = OneriYonetici(h)
        ids = [o.oneri_id for o in y.kuyruk_listele()]
        assert y.toplu_reddet(ids[:2]) == 2
        assert y.toplu_reddet(ids[:2]) == 0  # zaten karara bağlı
        assert y.toplu_reddet() == 3
        assert y.kuyruk_listele() == [] and len(y.kuyruk_listele("reddedildi")) == 5
        assert fact_count_hub(h) == 0


def test_onaylanmamis_oneri_kartta_ve_persona_getirde_yok(world):
    svc(world).persona_oner([onerme(world, "ONAYSIZ-BILGI-XYZ", "kimlik")])
    s = svc(world)
    assert "ONAYSIZ-BILGI-XYZ" not in json.dumps(s.persona_getir(), ensure_ascii=False)
    assert "ONAYSIZ-BILGI-XYZ" not in s.kimlik_karti()["veri"]
    with Hub.open(world["root"], write=False) as h:
        assert "ONAYSIZ-BILGI-XYZ" not in PersonaReader(h).export_identity_card()
    with yonet(world) as h:
        y = OneriYonetici(h)
        y.onayla(y.kuyruk_listele()[0].oneri_id)
    assert "ONAYSIZ-BILGI-XYZ" in s.kimlik_karti()["veri"]


# ------------------------------------------------------------------ ornekle
def test_ornekle(world):
    s = svc(world)
    r = s.ornekle("notlar", 5)
    assert [k["veri"] for k in r["kayitlar"]] == ["kahve makinesi notu"]
    assert all(k["etiket"] == "veri" for k in r["kayitlar"])
    assert s.ornekle("video", 5, "tarifi")["kayitlar"][0]["veri"] == "kahve tarifi videosu"
    assert s.ornekle("notlar", 5, "olmayan-sozcuk")["kayitlar"] == []
    for kat in ("eposta", "konum", "tarama"):
        with pytest.raises(ServiceError) as e:
            s.ornekle(kat)
        assert str(e.value).startswith("reddedildi") and "kahve" not in str(e.value)
    # GPS'li medya kaydı konum izni yokken örneklenmez
    assert s.ornekle("medya_meta", 10)["kayitlar"] == []
    log = AccessLog(world["root"]).read_all()
    assert [x[2] for x in log] == ["ornekle"] * len(log)
    assert [x[5] for x in log] == ["ok", "ok", "ok", "reddedildi", "reddedildi", "reddedildi", "ok"]


def test_ornekle_rastgele_n_sinirli(world):
    with Hub.open(world["root"], write=True) as h:
        sid = h.add_source("sohbet", "1", None)
        h.add_events(sid, [ev(f"not {i}", "notlar", key=f"o{i}") for i in range(300)])
        KeyManager(h).grant(world["b_id"], "notlar")
    r = svc(world, world["b_key"]).ornekle("notlar", 25)
    assert len(r["kayitlar"]) == 25 and len({k["id"] for k in r["kayitlar"]}) == 25
    assert len(svc(world, world["b_key"]).ornekle("notlar", 9999)["kayitlar"]) == 200  # üst sınır


def test_ornekle_hassas_izin_sarti(world):
    with Hub.open(world["root"], write=True) as h:
        KeyManager(h).grant(world["b_id"], "notlar")
    with pytest.raises(ServiceError):
        svc(world, world["b_key"]).ornekle("eposta")
    with Hub.open(world["root"], write=True) as h:
        KeyManager(h).grant(world["b_id"], "eposta", confirmed_sensitive=True)
    assert svc(world, world["b_key"]).ornekle("eposta")["kayitlar"][0]["veri"].startswith("kahve randevu")


def test_persona_getir_zengin_bicim(world, clock):
    with yonet(world) as h:
        p = Persona(h, clock=clock)
        p.add_fact("Adım Deneme", "kimlik")
        sid = h.add_source("belge", "1", None)
        p.add_fact_from_source("Python bilir", "ilgi", sid)
    r = svc(world).persona_getir()["kayitlar"]
    assert [x["kategori_basligi"] for x in r] == ["Kimlik", "İlgi alanları"]
    assert r[1]["kaynak"] == "belge" and r[1]["durum"] == "dosyadan_alinan"
    assert r[0]["son_dogrulama"] and len(r[0]["son_dogrulama"]) == 10
    kart = svc(world).kimlik_karti()["veri"]
    assert kart.startswith("# Kimlik Kartı") and "## Bu kişi hakkında bilinenler" in kart
    assert "son doğrulama:" in kart and "kaynak: belge" in kart


def test_oneri_metni_talimat_icerse_de_yalniz_veri(world):
    """Kuyruktaki öneri metni de MCP çıktısına girmez (yalnız onaydan sonra facts üzerinden)."""
    svc(world).persona_oner([onerme(world, INJECTION, "diger")])
    assert INJECTION not in json.dumps(svc(world).persona_getir(), ensure_ascii=False)


# ------------------------------------------------------------------ gerçek stdio
def params(world, key):
    return StdioServerParameters(command=sys.executable, args=["-m", "kimlikserver.mcp"],
                                 env={"KIMLIK_VERI": str(world["root"]), "KIMLIK_ANAHTAR": key})


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 90))


def test_stdio_persona_oner_ve_ornekle(world):
    kanit = event_ids(world)[:1]

    async def go():
        async with Client(params(world, world["a_key"])) as c:
            o = await c.call_tool("ornekle", {"kategori": "notlar", "n": 3})
            kid = o.structured_content["kayitlar"][0]["id"]
            r = await c.call_tool("persona_oner", {"onermeler": [
                {"ifade": "Kahve tutkunu", "kategori": "tercihler", "kanit": [kid], "guven": 0.7}]})
            kotu = await c.call_tool("persona_oner", {"onermeler": [
                {"ifade": "Gizli", "kategori": "kimlik",
                 "kanit": [eid_of(world, "kahve randevu e-postası", "eposta")], "guven": 0.7}]})
            bad = await c.call_tool("persona_oner", {"onermeler": [
                {"ifade": "x", "kategori": "kimlik", "kanit": kanit, "guven": 9}]})
            return o, r, kotu, bad
    o, r, kotu, bad = run(go())
    assert not o.is_error and not r.is_error
    assert r.structured_content["eklenen"] == 1
    assert kotu.is_error and "reddedildi" in kotu.content[0].text
    assert bad.is_error
    assert [x[4] for x in oneri_rows(world)] == ["bekliyor"] and len(oneri_rows(world)) == 1
    log = [x for x in AccessLog(world["root"]).read_all() if x[2] != "ara"]
    assert [x[5] for x in log] == ["ok", "ok", "reddedildi", "hata"]


def test_uc_mcp_sureci_ayni_anda_oneri_yazar_kayip_yok(world):
    N = 10

    async def worker(i):
        async with Client(params(world, world["a_key"])) as c:
            kid = (await c.call_tool("ornekle", {"kategori": "notlar", "n": 1})
                   ).structured_content["kayitlar"][0]["id"]
            for j in range(N):
                r = await c.call_tool("persona_oner", {"onermeler": [
                    {"ifade": f"Süreç {i} bilgi {j}", "kategori": "diger", "kanit": [kid],
                     "guven": 0.5}]})
                assert not r.is_error and r.structured_content["eklenen"] == 1, r.content

    async def go():
        await asyncio.gather(*(worker(i) for i in range(3)))
    run(go())
    rows = oneri_rows(world)
    assert len(rows) == 3 * N and len({r[2] for r in rows}) == 3 * N
    log = AccessLog(world["root"]).read_all()
    assert sum(1 for x in log if x[2] == "persona_oner" and x[5] == "ok") == 3 * N
