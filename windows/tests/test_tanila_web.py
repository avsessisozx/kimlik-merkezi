"""'Dosyayı denetle (içerik göstermez)': web ucu, sızıntı yok, veritabanına yazmaz, büyük/bozuk dosya,
zaman aşımı, rapor sınırı ve konsol komutu (kimlikmerkezi-mcp.exe tanila ... ile aynı kod yolu).

Sentinel mantığı windows/paket/tanila_dene.py'de; Windows CI'daki kurulu_dene.py aynı yardımcıyı gerçek
exe üstünde kullanır. Burada (Linux) aynı mantık Python süreci üstünde kanıtlanır."""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from kimlikwin.tanila_is import TanilaIsi, kisalt
from kimlikwin.web import Sunucu

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "paket"))
import tanila_dene as TD  # noqa: E402
from test_web import Istemci  # noqa: E402


@pytest.fixture
def sunucu(yonetici):
    s = Sunucu(yonetici, 0)
    s.baslat()
    yield s
    s.durdur()


@pytest.fixture
def ist(sunucu, yonetici, veri):
    c = Istemci(sunucu)
    c.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False})
    return c


def bekle(ist, sn=60):
    t = time.time()
    while time.time() - t < sn:
        d = ist.api("tanila_durum")
        if d["durum"] != "calisiyor":
            return d
        time.sleep(0.1)
    raise AssertionError("denetim bitmedi")


def dosya_listesi(veri: Path):
    return sorted((str(p.relative_to(veri)), p.stat().st_size) for p in veri.rglob("*") if p.is_file())


# ------------------------------------------------------------------ web ucu güvenliği
def test_uc_jeton_host_origin_ve_yalniz_post(ist, sunucu, tmp_path):
    z = str(TD.sahte_zip(tmp_path / "a.zip"))
    for ad in ("tanila_baslat", "tanila_durum", "tanila_temizle"):
        assert ist.post(ad, {"yol": z}, jeton=None)[0] == 403
        assert ist.post(ad, {"yol": z}, jeton="yanlis")[0] == 403
        assert ist.post(ad, {"yol": z}, host="evil.example:80")[0] == 403
        assert ist.post(ad, {"yol": z}, origin="http://evil.example")[0] == 403
        # GET ile çağrılamaz
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{sunucu.port}/api/{ad}")
        assert e.value.code == 404
    assert ist.api("tanila_durum") == {"durum": "yok"}      # reddedilen çağrılar iş başlatmadı


def test_uc_girdi_dogrulama(ist, tmp_path):
    assert ist.post("tanila_baslat", {"yol": ""})[0] == 400
    assert ist.post("tanila_baslat", {"yol": 5})[0] == 400
    assert ist.post("tanila_baslat", {"yol": str(tmp_path / "yok.zip")})[0] == 400
    assert ist.post("tanila_baslat", {"yol": str(tmp_path), "olmayan": 1})[0] == 400


# ------------------------------------------------------------------ sızıntı yok, DB'ye yazmaz
def test_rapor_sizdirmaz_ve_veritabanina_yazmaz(ist, veri, tmp_path):
    z = TD.sahte_zip(tmp_path / "örnek.zip")
    once = dosya_listesi(veri)
    say = ist.api("durum")["ozet"]["counts"]
    for goster, ayrinti in ((False, False), (False, True), (True, False)):
        d = ist.api("tanila_baslat", {"yol": str(z), "adlari_goster": goster, "ayrinti": ayrinti})
        assert d["durum"] in ("calisiyor", "bitti")
        d = bekle(ist)
        assert d["durum"] == "bitti" and d["hata"] is None, d
        assert TD.sizinti_var_mi(d["rapor"], adlar_acik=goster) is None
        assert str(tmp_path) not in json.dumps(d)       # yol durum nesnesinde yok
        if goster:
            assert TD.SN.lower() in d["rapor"].lower()  # adlar bilerek açıldı, değerler yine yok
    assert dosya_listesi(veri) == once                  # veri klasörüne hiçbir şey yazılmadı
    assert ist.api("durum")["ozet"]["counts"] == say
    assert ist.api("kaynaklar")["kaynaklar"] == []      # kaynak da eklenmedi
    assert ist.api("tanila_temizle") == {"ok": True}
    assert ist.api("tanila_durum") == {"durum": "yok"}


def test_ayni_anda_iki_denetim_ve_ice_aktar_cakismasi(ist, yonetici, tmp_path, monkeypatch):
    z = str(TD.sahte_zip(tmp_path / "a.zip"))
    olay, basladi = threading.Event(), threading.Event()

    def yavas(yol, a, b):
        basladi.set()
        olay.wait(20)
        return "TANILAMA RAPORU"
    monkeypatch.setattr("kimlikwin.tanila_is._varsayilan_fn", yavas)
    ist.api("tanila_baslat", {"yol": z})
    assert basladi.wait(10)
    assert ist.post("tanila_baslat", {"yol": z})[0] == 409          # ikinci denetim
    kod, g = ist.post("ice_aktar_baslat", {"yol": z})
    assert kod == 409 and g["kod"] == "mesgul"          # denetim sürerken içe aktarma yok
    olay.set()
    assert bekle(ist)["durum"] == "bitti"
    # içe aktarma sürerken denetim reddedilir
    ist.api("ice_aktar_baslat", {"yol": z})
    yonetici.uygulama.is_.durum = "calisiyor"
    assert ist.post("tanila_baslat", {"yol": z})[0] == 409
    yonetici.uygulama.is_.durum = "bitti"


# ------------------------------------------------------------------ büyük / bozuk dosya, sınırlar
def test_bozuk_ve_bos_girdilerde_calismaya_devam_eder(ist, tmp_path):
    bozuk = tmp_path / f"bozuk_{TD.SN}.zip"
    bozuk.write_bytes(b"PK\x03\x04" + bytes(range(256)) * 8)
    bos = tmp_path / "bos.json"
    bos.write_bytes(b"")
    yarim = tmp_path / "yarim.json"
    yarim.write_text('[{"a": "' + TD.SV + '", "b": ', encoding="utf-8")
    klasor = tmp_path / "k"
    klasor.mkdir()
    for yol in (bozuk, bos, yarim, klasor):
        ist.api("tanila_baslat", {"yol": str(yol)})
        d = bekle(ist)
        assert d["durum"] in ("bitti", "hata"), d
        if d["durum"] == "bitti":
            assert TD.sizinti_var_mi(d["rapor"]) is None, yol.name
        else:
            assert TD.SN not in d["hata"] and TD.SV not in d["hata"]
    assert ist.api("durum")["ozet"]["counts"]["event"] == 0


def test_buyuk_dosya_makul_surede_biter(ist, tmp_path):
    b = tmp_path / "buyuk.json"
    satir = json.dumps({"title": "x " * 20, "time": "2024-03-05T10:11:12Z", "n": 1709287200123, TD.SN: TD.SV})
    with open(b, "w", encoding="utf-8") as f:
        f.write("[")
        for i in range(120_000):
            f.write(("," if i else "") + satir)
        f.write("]")
    assert b.stat().st_size > 15_000_000
    ist.api("tanila_baslat", {"yol": str(b)})
    t0 = time.time()
    d = bekle(ist, 120)
    assert d["durum"] == "bitti" and time.time() - t0 < 120
    assert TD.sizinti_var_mi(d["rapor"]) is None or "TANILAMA" in d["rapor"]
    assert TD.SV.lower() not in d["rapor"].lower() and "5551" not in d["rapor"]


def test_rapor_boyut_siniri():
    m = "\n".join(f"satir {i} " + "x" * 50 for i in range(10_000))
    k, kesik = kisalt(m, 2000)
    assert kesik and len(k) < 2300 and "gösteriliyor" in k
    assert kisalt("kisa", 2000) == ("kisa", False)
    j = TanilaIsi("x", False, False, fn=lambda *a: m, rapor_siniri=5000)
    j.baslat()
    j._is.join(10)
    d = j.to_dict()
    assert d["durum"] == "bitti" and d["kisaltildi"] and len(d["rapor"]) < 5400


def test_istisna_iletisi_arayuze_sizmaz():
    def patla(*a):
        raise OSError(f"{TD.SV} dosya adı burada")
    j = TanilaIsi("x", False, False, fn=patla)
    j.baslat()
    j._is.join(10)
    d = j.to_dict()
    assert d["durum"] == "hata" and "OSError" in d["hata"] and TD.SV not in json.dumps(d)


def test_zaman_asimi_sonucu_atar():
    olay = threading.Event()
    j = TanilaIsi("x", False, False, zaman_asimi=0.2, fn=lambda *a: (olay.wait(10), "TANILAMA RAPORU")[1])
    j.baslat()
    time.sleep(0.5)
    d = j.to_dict()
    assert d["durum"] == "zaman_asimi" and d["rapor"] is None and "uzun sürdü" in d["hata"]
    assert j.canli                    # iş parçacığı sürüyor: yeni denetim başlatılamaz (yönetici kontrol eder)
    olay.set()
    j._is.join(10)
    assert j.to_dict()["durum"] == "zaman_asimi" and j.to_dict()["rapor"] is None   # geç gelen sonuç atılır


# ------------------------------------------------------------------ konsol komutu (kimlikmerkezi-mcp.exe ile aynı yol)
def konsol(*args, cwd=None):
    kok = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
           "PYTHONPATH": os.pathsep.join(str(kok / d) for d in ("core/src", "server/src", "importers/src", "windows/src")),
           "KIMLIK_AYAR_DIZINI": str(cwd / "ayar")}
    return subprocess.run([sys.executable, "-m", "kimlikwin.konsol", *args], capture_output=True, text=True,
                          encoding="utf-8", timeout=120, env=env, cwd=str(cwd))


def test_konsol_tanila_cikis_0_ve_sizinti_yok(tmp_path):
    z = TD.sahte_zip(tmp_path / "a.zip")
    r = konsol("tanila", str(z), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert TD.sizinti_var_mi(r.stdout) is None
    r = konsol("tanila", str(z), "--adlari-goster", "--ayrinti", cwd=tmp_path)
    assert r.returncode == 0 and TD.sizinti_var_mi(r.stdout, adlar_acik=True) is None
    assert TD.SN.lower() in r.stdout.lower()
    assert not (tmp_path / "veri").exists()                     # veri klasörü açılmadı/oluşturulmadı


def test_konsol_tanila_hatalar_ve_surum(tmp_path):
    assert konsol("tanila", cwd=tmp_path).returncode == 2
    r = konsol("tanila", str(tmp_path / "yok"), cwd=tmp_path)
    assert r.returncode == 1 and "Girdi yok" in r.stderr
    s = konsol("surum", cwd=tmp_path)
    assert s.returncode == 0 and "pypdf: var" in s.stdout and "docx: var" in s.stdout and "ijson arka ucu" in s.stdout
