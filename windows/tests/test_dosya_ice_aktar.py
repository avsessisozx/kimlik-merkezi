"""İçe aktar ekranının çağırdığı GERÇEK API (Yonetici.api) ile bilgisayar dosyaları: karışık sahte klasör,
birden çok dosya seçimi, ilerleme (işlenen/toplam), dosya özeti ve seçici (sec) davranışı."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "importers" / "tests"))
from karisik_klasor import BOZUK, ICERIKLI, YALNIZ_KAYIT, uret  # noqa: E402

from kimlikwin.yonetici import IslemHatasi  # noqa: E402


def _bekle(y, sn=60):
    bas = time.time()
    while time.time() - bas < sn:
        s = y.api("ice_aktar_durum", {})
        if s["durum"] != "calisiyor":
            return s
        time.sleep(0.05)
    raise AssertionError("içe aktarma bitmedi")


@pytest.fixture
def karisik(tmp_path):
    return uret(tmp_path / "karisik")


def test_pdf_klasoru_otomatik_tanimaz_ama_ipucu_verir(kurulu, karisik):
    """Kullanıcı raporu: tür seçilmezse klasör 'tanıyamadım' hatası verir (hatanın yeniden üretimi)."""
    kurulu.api("ice_aktar_baslat", {"yol": str(karisik), "tur": None})
    s = _bekle(kurulu)
    assert s["durum"] == "hata" and s["hata"].startswith("Bu dosyayı tanıyamadım")
    assert "Bilgisayarımdaki dosyalar" in s["hata"]          # artık çıkış yolu gösteriliyor


def test_karisik_klasor_gercek_api(kurulu, karisik):
    kurulu.api("ice_aktar_baslat", {"yol": str(karisik), "tur": "computer_files"})
    s = _bekle(kurulu)
    assert s["durum"] == "bitti", s
    o = s["dosya_ozeti"]
    assert (o["icerikli"], o["yalniz_kayit"], o["bozuk"]) == (len(ICERIKLI), len(YALNIZ_KAYIT), len(BOZUK))
    top = o["toplam"]
    assert (s["dosya_islenen"], s["dosya_toplam"]) == (top, top)       # ilerleme sayaçları sonda dolu
    assert o["metinsiz_pdf"] == 1 and "taranmış olabilir" in s["sonuc"]
    assert {d["yol"] for d in o["bozuk_dosyalari"]} == set(BOZUK)
    # içerik gerçekten aranabilir (arayüzdeki Arama ekranının API'si)
    for anahtar in ("anahtpdf", "anahtxlsx", "anahtcp1254", "anahtrtf"):
        assert kurulu.api("ara", {"sorgu": anahtar})["kayitlar"], anahtar
    assert kurulu.api("durum", {})["ozet"]["counts"]["event"] == len(ICERIKLI) + len(YALNIZ_KAYIT)   # bozuklar için kayıt yok


def test_birden_cok_dosya_secimi(kurulu, karisik):
    sec = [karisik / "kilavuz.pdf", karisik / "mektup.docx", karisik / "bozuk.pdf", karisik / "muzik.mp3"]
    kurulu.api("ice_aktar_baslat", {"yol": "", "yollar": [str(p) for p in sec], "tur": "computer_files"})
    s = _bekle(kurulu)
    assert s["durum"] == "bitti" and s["yollar"] == [str(p) for p in sec]
    o = s["dosya_ozeti"]
    assert (o["icerikli"], o["yalniz_kayit"], o["bozuk"]) == (2, 1, 1) and s["dosya_toplam"] == 4


def test_cok_dosya_tur_olmadan_reddedilir(kurulu, karisik):
    with pytest.raises(IslemHatasi, match="Bilgisayarımdaki dosyalar"):
        kurulu.api("ice_aktar_baslat", {"yol": "", "yollar": [str(karisik / "a.txt"), str(karisik / "b.txt")], "tur": None})


def test_sec_dosyalar_cok_yol_doner(yonetici):
    yonetici.secici = lambda tur: "C:\\a\\x.pdf\nC:\\a\\y.docx" if tur == "dosyalar" else "C:\\klasor"
    r = yonetici.api("sec", {"tur": "dosyalar"})
    assert r["yollar"] == ["C:\\a\\x.pdf", "C:\\a\\y.docx"] and r["yol"] == "C:\\a\\x.pdf"
    assert yonetici.api("sec", {"tur": "klasor"}) == {"yol": "C:\\klasor", "yollar": []}
    with pytest.raises(IslemHatasi):
        yonetici.api("sec", {"tur": "baska"})


def test_yarim_kalan_is_cok_dosyayi_saklar(kurulu, karisik):
    kurulu.api("ice_aktar_baslat", {"yol": "", "yollar": [str(karisik / "kilavuz.pdf"), str(karisik / "not.md")], "tur": "computer_files"})
    _bekle(kurulu)
    import json
    d = json.loads((kurulu.uygulama.ayar_dizin / "ice_aktar_durum.json").read_text(encoding="utf-8"))
    assert d["yollar"] == [str(karisik / "kilavuz.pdf"), str(karisik / "not.md")] and d["durum"] == "bitti"
