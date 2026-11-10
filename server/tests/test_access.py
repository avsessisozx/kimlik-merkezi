"""Aşama 3: anahtar, izin, erişim kaydı, servis (süreç içi)."""
from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest
from kimlikcore import Hub, PermissionDenied

from helpers import INJECTION, ev
from kimlikserver._db import write_tx
from kimlikserver.access import (AccessLog, Authorizer, KeyManager,
                                 SensitiveConfirmationRequired)
from kimlikserver.persona import Persona
from kimlikserver.service import QueryService, ServiceError


def svc(world, key=None, clock=None):
    return QueryService(world["root"], key or world["a_key"], clock=clock) if clock \
        else QueryService(world["root"], key or world["a_key"])


def log_rows(world):
    return AccessLog(world["root"]).read_all()


def mutate(world, fn):
    with Hub.open(world["root"], write=True) as hub:
        return fn(hub)


def test_anahtar_yalniz_hash_saklanir(world):
    raw = b""
    for f in world["root"].glob("kimlik.db*"):
        raw += f.read_bytes()
    assert world["a_key"].encode() not in raw
    assert world["a_key"].startswith("kim_") and len(world["a_key"]) == 4 + 64
    with Hub.open(world["root"], write=False) as hub:
        h = hub._conn.execute("SELECT key_hash FROM app_keys WHERE app_id=?",
                              (world["a_id"],)).fetchone()[0]
    assert h == hashlib.sha256(world["a_key"].encode()).hexdigest()


def test_hassas_kategori_ayri_onay_ister(world):
    def f(hub):
        km = KeyManager(hub)
        with pytest.raises(SensitiveConfirmationRequired):
            km.grant(world["a_id"], "konum")
        # çekirdek CHECK kısıtı da ham yazımı reddeder
        with pytest.raises(sqlite3.IntegrityError):
            with write_tx(hub) as c:
                c.execute("INSERT INTO permissions(app_id, category, granted_at, "
                          "confirmed_sensitive) VALUES (?, 'eposta', 'x', 0)", (world["a_id"],))
        km.grant(world["a_id"], "konum", confirmed_sensitive=True)
    mutate(world, f)
    cats = [k["kategori"] for k in svc(world).kategorileri_listele()["kategoriler"]]
    assert "konum" in cats


def test_toplu_acma_hassasi_icermez(world):
    done = mutate(world, lambda hub: KeyManager(hub).grant_all_non_sensitive(world["b_id"]))
    assert not set(done) & {"eposta", "mesaj", "konum"}
    cats = [k["kategori"] for k in svc(world, world["b_key"]).kategorileri_listele()["kategoriler"]]
    assert len(cats) == 10 and not set(cats) & {"eposta", "mesaj", "konum"}
    with pytest.raises(ServiceError):
        svc(world, world["b_key"]).ara("kahve", "eposta")


def test_izinsiz_kategori_reddi_ve_sizma_yok(world):
    s = svc(world)
    with pytest.raises(ServiceError) as e:
        s.ara("kahve", "eposta")
    msg = str(e.value)
    assert msg.startswith("reddedildi") and "randevu" not in msg and "kahve" not in msg
    # kategorisiz sorgu yalnız izinli kategorileri döndürür
    r = s.ara("kahve")
    assert {k["kategori"] for k in r["kayitlar"]} <= {"notlar", "video", "medya_meta"}
    assert "eposta" not in json.dumps(r) and "tarama" not in json.dumps(r)
    # hiç izni olmayan uygulama
    with pytest.raises(ServiceError):
        svc(world, world["b_key"]).ara("kahve")
    assert [r[5] for r in log_rows(world)] == ["reddedildi", "ok", "reddedildi"]


def test_anahtar_iptali_erisimi_keser(world):
    s = svc(world)
    assert s.ara("kahve")["kayitlar"]
    mutate(world, lambda hub: KeyManager(hub).revoke_key(world["a_id"]))
    with pytest.raises(ServiceError) as e:
        s.ara("kahve")  # aynı servis nesnesi: önbellek yok
    assert str(e.value).startswith("reddedildi")
    with pytest.raises(ServiceError):
        s.kategorileri_listele()


def test_gecersiz_ve_anahtarsiz_cagri(world):
    for key in (None, "", "kim_yanlis", "baska"):
        with pytest.raises(ServiceError):
            QueryService(world["root"], key).ara("kahve")
    rows = log_rows(world)
    assert len(rows) == 4 and {r[1] for r in rows} == {"bilinmeyen"}
    assert {r[5] for r in rows} == {"reddedildi"}


def test_her_istek_kayda_girer(world):
    s = svc(world)
    s.kategorileri_listele()
    r = s.ara("kahve", "notlar")
    s.zaman_cizelgesi("video")
    s.persona_getir()
    s.kimlik_karti()
    rows = log_rows(world)
    assert [x[2] for x in rows] == ["kategorileri_listele", "ara", "zaman_cizelgesi",
                                    "persona_getir", "kimlik_karti"]
    assert all(x[1] == world["a_id"] and x[5] == "ok" for x in rows)
    assert rows[0][4] == 4  # 4 izinli kategori
    assert rows[1][3] == "notlar" and rows[1][4] == len(r["kayitlar"]) == 1


def test_erisim_kaydi_yazilamazsa_reddedilir_tablo_yok(world):
    c = sqlite3.connect(world["root"] / "erisim.db")
    c.execute("DROP TABLE access_log")
    c.commit()
    c.close()
    with pytest.raises(ServiceError) as e:
        svc(world).ara("kahve", "notlar")
    assert "reddedildi" in str(e.value) and "kahve" not in str(e.value)


def test_erisim_kaydi_yazilamazsa_reddedilir_dosya_acilamiyor(world):
    (world["root"] / "erisim.db").unlink()
    for f in world["root"].glob("erisim.db-*"):
        f.unlink()
    (world["root"] / "erisim.db").mkdir()  # dosya yerine klasör: bağlantı açılamaz
    with pytest.raises(ServiceError) as e:
        svc(world).ara("kahve", "notlar")
    assert "reddedildi" in str(e.value)


def test_erisim_kaydi_enjekte_hata(world):
    def kotu(root):
        raise sqlite3.OperationalError("disk I/O error")
    s = QueryService(world["root"], world["a_key"],
                     access_log=AccessLog(world["root"], connect=kotu))
    with pytest.raises(ServiceError):
        s.persona_getir()


def test_tombstone_kayitlar_donmez(world):
    s = svc(world)
    before = {k["id"] for k in s.ara("kahve")["kayitlar"]}
    assert len(before) == 2
    hide = next(iter(before))

    def f(hub):
        hub.hide_event(hide, "test")
    mutate(world, f)
    after = {k["id"] for k in s.ara("kahve")["kayitlar"]}
    assert hide not in after and len(after) == 1
    assert hide not in {k["id"] for k in s.zaman_cizelgesi()["kayitlar"]}
    mutate(world, lambda hub: hub.remove_source(world["source"], "yanlış"))
    assert s.ara("kahve")["kayitlar"] == [] and s.zaman_cizelgesi()["kayitlar"] == []


def test_konum_izinsizken_gps_li_kayit_donmez(world):
    s = svc(world)
    r = s.ara("kahve")
    txt = json.dumps(r, ensure_ascii=False)
    assert "konumu" not in txt and "fotoğrafı" not in txt  # konum kaydı ve GPS'li medya
    assert "fotoğrafı" not in json.dumps(s.zaman_cizelgesi(), ensure_ascii=False)
    with pytest.raises(ServiceError):
        s.ara("kahve", "konum")
    # konum izni verilince (ayrı onayla) konum kaydı gelir; medya_meta'daki GPS'li kayıt da
    mutate(world, lambda hub: KeyManager(hub).grant(world["a_id"], "konum",
                                                    confirmed_sensitive=True))
    txt = json.dumps(s.ara("kahve"), ensure_ascii=False)
    assert "konumu" in txt and "fotoğrafı" in txt
    # izin geri alınınca yine kesilir
    mutate(world, lambda hub: KeyManager(hub).revoke_grant(world["a_id"], "konum"))
    assert "konumu" not in json.dumps(s.ara("kahve"), ensure_ascii=False)


def test_suresi_dolan_izin_reddi(world, clock):
    def f(hub):
        KeyManager(hub, clock=clock).grant(world["b_id"], "notlar",
                                           expires_at="2026-11-09T13:00:00Z")
    mutate(world, f)
    s = QueryService(world["root"], world["b_key"], clock=clock)
    assert s.ara("kahve", "notlar")["kayitlar"]
    assert s.kategorileri_listele()["kategoriler"][0]["bitis"] == "2026-11-09T13:00:00Z"
    clock.advance(minutes=59)
    assert s.ara("kahve", "notlar")["kayitlar"]
    clock.advance(minutes=1)  # tam bitiş anı: dolmuş sayılır
    with pytest.raises(ServiceError) as e:
        s.ara("kahve", "notlar")
    assert str(e.value).startswith("reddedildi")
    assert s.kategorileri_listele()["kategoriler"] == []


def test_talimat_iceren_kayit_yalniz_veri_alaninda(world):
    def f(hub):
        sid = hub.add_source("sahte", "1", None)
        hub.add_events(sid, [ev(INJECTION, "notlar", ts="2026-11-08T10:00:00Z")])
    mutate(world, f)
    r = svc(world).ara("talimatları")
    assert len(r["kayitlar"]) == 1
    k = r["kayitlar"][0]
    assert k["etiket"] == "veri" and k["veri"] == INJECTION
    # metin yalnız kayitlar[*].veri içinde geçer; başka hiçbir alanda yok
    kalan = json.loads(json.dumps(r))
    kalan["kayitlar"][0]["veri"] = ""
    assert INJECTION not in json.dumps(kalan, ensure_ascii=False)
    assert "talimat değildir" in r["veri_uyarisi"]


def test_persona_servis(world):
    def f(hub):
        p = Persona(hub)
        p.add_fact("Adım Deneme", "kimlik")
        p.add_fact("Kahve severim", "tercihler")
    mutate(world, f)
    s = svc(world)
    r = s.persona_getir("kimlik")
    assert [x["veri"] for x in r["kayitlar"]] == ["Adım Deneme"]
    assert r["kayitlar"][0]["etiket"] == "veri"
    k = s.kimlik_karti(["tercihler"])
    assert "Kahve severim" in k["veri"] and "Adım" not in k["veri"] and k["etiket"] == "veri"
    with pytest.raises(ServiceError):
        svc(world, world["b_key"]).kimlik_karti()  # persona izni yok


def test_veritabani_yoksa_anlasilir_hata(tmp_path):
    with pytest.raises(ServiceError) as e:
        QueryService(tmp_path / "yok", "kim_x").ara("a")
    assert "uygulamasını" in str(e.value)


def test_authorizer_dogrudan(world):
    with Hub.open(world["root"], write=False) as hub:
        a = Authorizer(hub)
        assert a.authenticate(world["a_key"]).app_id == world["a_id"]
        with pytest.raises(PermissionDenied):
            a.authenticate(world["a_key"] + "x")
