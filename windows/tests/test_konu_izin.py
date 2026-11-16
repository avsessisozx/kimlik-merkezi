"""Hassas KONU izinleri (madde 10, Windows kısmı): API ve toplu/önerilen seçimlerin konu izni vermemesi."""
import json

import pytest
from kimlikserver.access import SensitiveConfirmationRequired, UnknownTopic

from kimlikwin.cekirdek import KONU_ADLARI


def app_(kurulu, ad="Deneme"):
    return kurulu.api("anahtar_uret", {"ad": ad})["id"]


def u_(kurulu, app):
    return next(u for u in kurulu.api("erisim", {})["uygulamalar"] if u["id"] == app)


def test_erisim_cikti_tum_konular_ve_varsayilan_bos(kurulu):
    app = app_(kurulu)
    e = kurulu.api("erisim", {})
    assert {k["kimlik"] for k in e["tum_konular"]} >= {"saglik", "hukuk", "finans", "din_siyaset", "cinsellik"}
    ad = {k["kimlik"]: k["ad"] for k in e["tum_konular"]}
    assert ad["saglik"] == "Sağlık" and ad["finans"] == "Para ve finans" and ad["din_siyaset"] == "Din ve siyaset" and ad["cinsellik"] == "Cinsellik"
    assert u_(kurulu, app)["konular"] == []


def test_onaysiz_reddedilir_onayli_acilir_kaldirilir(kurulu):
    app = app_(kurulu)
    with pytest.raises(SensitiveConfirmationRequired):
        kurulu.api("konu_izin_ver", {"app_id": app, "konu": "saglik"})
    with pytest.raises(SensitiveConfirmationRequired):
        kurulu.api("konu_izin_ver", {"app_id": app, "konu": "saglik", "hassas_onay": "evet"})   # yalnız gerçek True
    assert u_(kurulu, app)["konular"] == []
    kurulu.api("konu_izin_ver", {"app_id": app, "konu": "saglik", "bitis": "2099-01-01T00:00:00Z", "hassas_onay": True})
    assert u_(kurulu, app)["konular"] == [{"konu": "saglik", "bitis": "2099-01-01T00:00:00Z"}]
    kurulu.api("konu_izin_kaldir", {"app_id": app, "konu": "saglik"})
    assert u_(kurulu, app)["konular"] == []


def test_bilinmeyen_konu_hatasi(kurulu):
    app = app_(kurulu)
    with pytest.raises(UnknownTopic):
        kurulu.api("konu_izin_ver", {"app_id": app, "konu": "uydurma", "hassas_onay": True})


def test_suresi_dolmus_konu_izni_listelenmez(kurulu):
    app = app_(kurulu)
    kurulu.api("konu_izin_ver", {"app_id": app, "konu": "hukuk", "hassas_onay": True})
    with kurulu.uygulama.hub.transaction() as c:
        c.execute("UPDATE konu_izinleri SET expires_at='2020-01-01T00:00:00Z' WHERE app_id=?", (app,))
    assert u_(kurulu, app)["konular"] == []


def test_toplu_ve_claude_ekle_konu_izni_vermez(kurulu, tmp_path):
    app = app_(kurulu)
    kurulu.api("izin_toplu", {"app_id": app})
    assert u_(kurulu, app)["konular"] == []
    f = tmp_path / "c.json"
    f.write_text("{}", encoding="utf-8")
    kurulu.uygulama._claude_yolu = lambda: f
    cid = kurulu.api("claude_ekle", {})["app_id"]
    assert u_(kurulu, cid)["konular"] == [] and len(u_(kurulu, cid)["izinler"]) == 10
    assert kurulu.uygulama.anahtarlar.list_topic_grants() == []


def test_bilinmeyen_konu_kimligi_oldugu_gibi_gosterilir():
    assert KONU_ADLARI.get("ozel_konu", "ozel_konu") == "ozel_konu"
