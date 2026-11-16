"""Sohbet kopyalarını denetle/gizle (madde 2'nin arayüz ucu): salt okuma, uygulama, ikinci uygulama, paketli yol."""
import time
from pathlib import Path

import pytest
from kimlikcore import EventIn

from kimlikwin.cekirdek import IslemHatasi

FIX = Path(__file__).resolve().parents[2] / "importers" / "fixtures"


def bekle(y, ad="kopya_durum"):
    for _ in range(200):
        d = y.api(ad, {})
        if d["durum"] != "calisiyor":
            return d
        time.sleep(0.05)
    raise AssertionError("iş bitmedi")


def mesaj(key, ts="2026-05-01T10:00:00Z", text="selam dünya", kid="k1", rol="user"):
    return EventIn(ts=ts, kind="sohbet.mesaj", category="sohbet", text=text, event_key=key,
                   payload={"platform": "chatgpt", "konusma_id": kid, "baslik": "B", "rol": rol, "mesaj_id": key, "ts": ts})


def sohbet_ekle(kurulu, olaylar):
    h = kurulu.uygulama.hub
    sid = h.add_source("sentetik", "1", None)
    h.add_events(sid, olaylar)


def gorunur(kurulu):
    return kurulu.uygulama.hub.query_one("SELECT count(*) FROM events WHERE kind='sohbet.mesaj' AND hidden=0")[0]


def test_denetle_degistirmez_uygula_gizler_ikinci_uygula_sifir(kurulu):
    sohbet_ekle(kurulu, [mesaj("a1"), mesaj("a2"), mesaj("a3", text="öteki")])
    assert kurulu.api("kopya_durum", {}) == {"durum": "yok"}
    kurulu.api("kopya_baslat", {})
    d = bekle(kurulu)
    assert d["durum"] == "bitti" and d["rapor"]["tam_kopya"] == 1 and d["rapor"]["uygulandi"] is False
    assert "1 kopya mesaj ve 0 yeniden üretilmiş cevap bulundu. 2 mesaj kalacak. Henüz hiçbir şey değiştirilmedi." in d["ozet"]
    assert "yalnız ChatGPT dışa aktarma dosyası da seçilirse" in d["ozet"]
    assert gorunur(kurulu) == 3                                    # salt okuma: hiçbir şey değişmedi
    kurulu.api("kopya_baslat", {"uygula": True})
    d = bekle(kurulu)
    assert d["rapor"]["uygulandi"] is True and "gizlendi" in d["ozet"] and "silinmedi" in d["ozet"]
    assert gorunur(kurulu) == 2
    kurulu.api("kopya_baslat", {"uygula": True})
    assert bekle(kurulu)["rapor"]["tam_kopya"] == 0
    assert gorunur(kurulu) == 2
    assert "Kopya mesaj: 0" in bekle(kurulu)["metin"]


def test_rapor_yalniz_sayi_icerir(kurulu):
    sohbet_ekle(kurulu, [mesaj("a1", text="GIZLI-SENTINEL"), mesaj("a2", text="GIZLI-SENTINEL")])
    kurulu.api("kopya_baslat", {})
    d = bekle(kurulu)
    assert "GIZLI-SENTINEL" not in repr(d) and "k1" not in repr(d["rapor"])


def test_paketli_yol_yeniden_uretilmis_cevaplar(kurulu):
    kurulu.api("ice_aktar_baslat", {"yol": str(FIX / "chat_chatgpt")})
    assert bekle(kurulu, "ice_aktar_durum")["durum"] == "bitti"
    h = kurulu.uygulama.hub
    kid = h.query("SELECT json_extract(payload, '$.konusma_id') FROM events WHERE kind = 'sohbet.mesaj' LIMIT 1")[0][0]
    sohbet_ekle(kurulu, [mesaj("dal-disi-1", text="yeniden üretilen dal", kid=kid, rol="assistant")])
    once = gorunur(kurulu)
    kurulu.api("kopya_baslat", {"paket": str(FIX / "chat_chatgpt")})
    d = bekle(kurulu)
    assert d["durum"] == "bitti" and d["rapor"]["dal_disi"] == 1 and d["rapor"]["tam_kopya"] == 0
    assert "1 yeniden üretilmiş cevap bulundu" in d["ozet"] and "yalnız ChatGPT" not in d["ozet"]
    assert gorunur(kurulu) == once
    kurulu.api("kopya_baslat", {"paket": str(FIX / "chat_chatgpt"), "uygula": True})
    assert bekle(kurulu)["rapor"]["uygulandi"] is True
    assert gorunur(kurulu) == once - 1
    kurulu.api("kopya_baslat", {"paket": str(FIX / "chat_chatgpt"), "uygula": True})
    assert bekle(kurulu)["rapor"]["dal_disi"] == 0


def test_hatali_paket_anlasilir_hata_ve_yol_sizmaz(kurulu, tmp_path):
    with pytest.raises(IslemHatasi):
        kurulu.api("kopya_baslat", {"paket": str(tmp_path / "yok")})
    kurulu.api("kopya_baslat", {"paket": str(FIX / "reddit")})
    d = bekle(kurulu)
    assert d["durum"] == "hata" and "sohbet" in d["hata"] and str(FIX) not in d["hata"]


def test_ice_aktarma_surerken_reddedilir(kurulu):
    from kimlikwin.cekirdek import IceAktarmaIsi
    kurulu.uygulama.is_ = IceAktarmaIsi("x", None, False)
    with pytest.raises(IslemHatasi):
        kurulu.api("kopya_baslat", {})
