"""Aday 3: elle aktarım (USB/paylaş ile klasöre kopyalama) + "klasörü tara ve al"."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from elle_alici import ac, klasoru_tara_ve_al, tum_kimlikler
from ortak import dogrula, dosya_yaz, olc, uret_giden_kutusu

ADAY = "elle"
CIHAZ = "telefon-1"


@pytest.fixture
def db(tmp_path):
    d = ac(tmp_path / "pc.db")
    yield d
    d.close()


def kes(kaynak: Path, hedef: Path, bayt: int):
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_bytes(kaynak.read_bytes()[:bayt])


def test_kesik_son_satir_reddedilir_sonra_tam_kopya_gelir(tmp_path, db):
    giden = tmp_path / "giden"
    g = uret_giden_kutusu(giden, CIHAZ, 1, 100)
    ad = next(iter(g))
    usb = tmp_path / "usb"
    veri = (giden / CIHAZ / ad).read_bytes()
    kes(giden / CIHAZ / ad, usb / ad, len(veri) - 15)  # son satırın ortasında kesik
    r = klasoru_tara_ve_al(usb, db)
    assert r["ayrinti"][ad] == "kesik" and r["bekletilen"] == 1 and r["yeni"] == 0
    assert tum_kimlikler(db) == []  # kesik dosyadan hiçbir satır alınmadı
    shutil.copy(giden / CIHAZ / ad, usb / ad)  # kopya tamamlandı (üzerine yazıldı)
    r = klasoru_tara_ve_al(usb, db)
    assert r["yeni"] == 100 and r["tamam"] == 1
    dogrula(g, tum_kimlikler(db))
    olc(ADAY, "kesik_son_satir", ilk_tur="kesik/bekletildi", alinan_satir_kesikten=0, tam_kopyadan=100)


def test_ayni_dosya_iki_kez_ve_farkli_adla_kopya(tmp_path, db):
    giden = tmp_path / "giden"
    g = uret_giden_kutusu(giden, CIHAZ, 3, 40)
    usb = tmp_path / "usb"
    usb.mkdir()
    for ad in g:
        shutil.copy(giden / CIHAZ / ad, usb / ad)
    r1 = klasoru_tara_ve_al(usb, db)
    assert r1["yeni"] == 120 and r1["tekrar"] == 0
    r2 = klasoru_tara_ve_al(usb, db)  # aynı klasör tekrar taranır (iki kez kopyalama sonucu)
    assert r2["yeni"] == 0 and r2["tekrar"] == 120
    ad0 = next(iter(g))
    shutil.copy(giden / CIHAZ / ad0, usb / f"kopya ({1}) - {ad0}")  # farklı adla kopya
    (usb / "yedek").mkdir()
    shutil.copy(giden / CIHAZ / ad0, usb / "yedek" / "yeni_ad.jsonl")
    r3 = klasoru_tara_ve_al(usb, db)
    assert r3["yeni"] == 0 and r3["tekrar"] == 120 + 80  # 3 dosya + 2 yeni kopya
    ids = tum_kimlikler(db)
    dogrula(g, ids)
    olc(ADAY, "cift_kopya_farkli_ad", tur1_yeni=r1["yeni"], tur2_yeni=r2["yeni"], tur3_yeni=r3["yeni"],
        tur3_tekrar_satir=r3["tekrar"], toplam_tekil=len(ids))


def test_bozuk_ve_yabanci_dosyalar(tmp_path, db):
    usb = tmp_path / "usb"
    usb.mkdir()
    (usb / "a.jsonl.tmp").write_bytes(b'{"id": "x"}\n')
    (usb / "not.txt").write_bytes(b'{"id": "y"}\n')
    (usb / "bozuk.jsonl").write_bytes(b'{"id": "a1", "x": 1}\nBOZUK SATIR\n{"id": "a2"}\n')
    (usb / "bos.jsonl").write_bytes(b"")
    r = klasoru_tara_ve_al(usb, db)
    assert r["reddedilen"] == 1 and r["bekletilen"] == 1 and r["yeni"] == 0 and r["dosya"] == 2
    assert tum_kimlikler(db) == []  # bozuk dosyadan da kısmi satır alınmaz


def test_satir_siniri_kesilmesi_kapanissiz_tespit_edilemez_kapanisla_edilir(tmp_path, db):
    # Kopya tam bir satır sınırında kesilirse '\n' ile biter: kesik görünmez.
    g1 = tmp_path / "g1"
    kim = dosya_yaz(g1 / f"{uuid.uuid4()}.jsonl", CIHAZ, 100)
    yol = next(g1.glob("*.jsonl"))
    satirlar = yol.read_bytes().split(b"\n")[:-1]
    usb = tmp_path / "usb"
    usb.mkdir()
    (usb / yol.name).write_bytes(b"\n".join(satirlar[:60]) + b"\n")  # 60/100 satır, '\n' ile bitiyor
    r = klasoru_tara_ve_al(usb, db)
    kapanissiz_alinan = r["yeni"]
    assert r["tamam"] == 1 and kapanissiz_alinan == 60  # BULGU: eksik kopya sessizce kabul edilir
    # tam kopya sonradan gelirse UUID tekilleştirmesiyle tamamlanır
    shutil.copy(yol, usb / yol.name)
    r = klasoru_tara_ve_al(usb, db)
    assert r["yeni"] == 40 and r["tekrar"] == 60
    dogrula(kim, tum_kimlikler(db))

    # kapanış kaydıyla (son satır satir_sayisi): aynı kesilme tespit edilir
    db2 = ac(tmp_path / "pc2.db")
    g2 = tmp_path / "g2"
    kim2 = dosya_yaz(g2 / f"{uuid.uuid4()}.jsonl", CIHAZ, 100, kapanis=True)
    y2 = next(g2.glob("*.jsonl"))
    s2 = y2.read_bytes().split(b"\n")[:-1]
    usb2 = tmp_path / "usb2"
    usb2.mkdir()
    (usb2 / y2.name).write_bytes(b"\n".join(s2[:60]) + b"\n")  # kapanış satırı yok
    r = klasoru_tara_ve_al(usb2, db2, kapanis_zorunlu=True)
    assert r["bekletilen"] == 1 and r["yeni"] == 0
    (usb2 / y2.name).write_bytes(b"\n".join(s2[:60] + [s2[-1]]) + b"\n")  # kapanış var ama sayı tutmuyor
    r = klasoru_tara_ve_al(usb2, db2, kapanis_zorunlu=True)
    assert r["bekletilen"] == 1 and r["yeni"] == 0
    shutil.copy(y2, usb2 / y2.name)
    r = klasoru_tara_ve_al(usb2, db2, kapanis_zorunlu=True)
    assert r["yeni"] == 100
    dogrula(kim2, tum_kimlikler(db2))
    db2.close()
    olc(ADAY, "satir_sinirinda_kesilme", kapanissiz_kabul_edilen_eksik_kopya_satir=kapanissiz_alinan,
        kapanisli_tespit=True)


def test_karisik_senaryo_bir_gunluk_birikim(tmp_path, db):
    giden = tmp_path / "giden"
    g = uret_giden_kutusu(giden, CIHAZ, 40, 200, kapanis=True)
    usb = tmp_path / "usb"
    usb.mkdir()
    adlar = list(g)
    for i, ad in enumerate(adlar):
        kaynak = giden / CIHAZ / ad
        if i % 5 == 0:
            kes(kaynak, usb / ad, kaynak.stat().st_size // 2)  # yarım kopya
        else:
            shutil.copy(kaynak, usb / ad)
        if i % 7 == 0:
            shutil.copy(kaynak, usb / f"Kopya - {ad}")  # aynı içerik, başka ad (tam)
    r1 = klasoru_tara_ve_al(usb, db, kapanis_zorunlu=True)
    for i, ad in enumerate(adlar):  # kullanıcı yarım olanları yeniden kopyalar
        shutil.copy(giden / CIHAZ / ad, usb / ad)
    r2 = klasoru_tara_ve_al(usb, db, kapanis_zorunlu=True)
    ids = tum_kimlikler(db)
    dogrula(g, ids)
    assert r2["bekletilen"] == 0
    olc(ADAY, "karisik_40dosya", tur1_bekletilen=r1["bekletilen"], tur1_yeni=r1["yeni"], tur2_yeni=r2["yeni"],
        toplam_tekil=len(ids), beklenen=40 * 200)
