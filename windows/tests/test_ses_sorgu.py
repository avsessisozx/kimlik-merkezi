"""Sesli arama kuralları: tarih, kaynak, anahtar sözcük. Türkiye saati (UTC+3)."""
from datetime import datetime, timezone

import pytest

from kimlikwin.ses_sorgu import coz

SIMDI = datetime(2026, 11, 17, 15, 30)      # Salı
K = ["Meta", "ChatGPT", "Telefon", "Bilgisayar"]


def tr(epoch: int) -> str:
    return datetime.fromtimestamp(epoch + 3 * 3600, timezone.utc).strftime("%Y-%m-%d %H:%M")


def aralik(metin, **kw):
    r = coz(metin, simdi=SIMDI, kaynaklar=K, **kw)
    return tr(r["bas"]), tr(r["bit"]), r


def test_gecen_yaz_kasimda_bu_yilin_yazi():
    b, e, _ = aralik("geçen yaz neler yaptım")
    assert (b, e) == ("2026-06-01 00:00", "2026-09-01 00:00")


def test_gecen_yaz_nisanda_onceki_yil():
    r = coz("geçen yaz", simdi=datetime(2026, 4, 2, 10, 0), kaynaklar=K)
    assert tr(r["bas"]) == "2025-06-01 00:00"


def test_bu_hafta_geçen_hafta_bugun_dun():
    assert aralik("bu hafta")[:2] == ("2026-11-16 00:00", "2026-11-23 00:00")
    assert aralik("geçen hafta")[:2] == ("2026-11-09 00:00", "2026-11-16 00:00")
    assert aralik("bugün")[:2] == ("2026-11-17 00:00", "2026-11-18 00:00")
    assert aralik("dün")[:2] == ("2026-11-16 00:00", "2026-11-17 00:00")


def test_gecen_ay_yil_basinda_aralik_ayi():
    r = coz("geçen ay", simdi=datetime(2026, 1, 5, 9, 0), kaynaklar=K)
    assert (tr(r["bas"]), tr(r["bit"])) == ("2025-12-01 00:00", "2026-01-01 00:00")


def test_ay_ve_yil_ve_mevsim():
    assert aralik("mart ayında ne yaptım")[:2] == ("2026-03-01 00:00", "2026-04-01 00:00")
    assert aralik("aralık 2024")[:2] == ("2024-12-01 00:00", "2025-01-01 00:00")
    assert aralik("2023 yazı")[:2] == ("2023-06-01 00:00", "2023-09-01 00:00")
    assert aralik("2023 kışı")[:2] == ("2023-12-01 00:00", "2024-03-01 00:00")
    assert aralik("2022")[:2] == ("2022-01-01 00:00", "2023-01-01 00:00")
    assert aralik("bu yıl")[:2] == ("2026-01-01 00:00", "2027-01-01 00:00")


def test_kaynak_ve_anahtar_sozcuk():
    r = coz("geçen yaz Instagram'da kahve makinesi", simdi=SIMDI, kaynaklar=K)
    assert r["kaynak"] == "Meta" and r["arama"] == "kahve makinesi"
    assert any("kaynak: Meta" in a for a in r["anlasilan"]) and any("kahve makinesi" in a for a in r["anlasilan"])


def test_olmayan_kaynak_uydurulmaz_ve_bos_sorgu():
    r = coz("tiktok", simdi=SIMDI, kaynaklar=K)
    assert r["kaynak"] is None and r["arama"] == "tiktok"           # tanınmayan şey anahtar sözcük olur
    assert coz("bana göster", simdi=SIMDI, kaynaklar=K)["bos"]


@pytest.mark.parametrize("metin", ["Geçen Yaz ChatGPT", "GEÇEN YAZ chatgpt ile", "İstanbul geçen yaz"])
def test_buyuk_kucuk_harf_ve_turkce_i(metin):
    r = coz(metin, simdi=SIMDI, kaynaklar=K)
    assert r["bas"] is not None
