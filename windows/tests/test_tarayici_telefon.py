"""GERÇEK TARAYICI: Telefon sayfası. Çalışma koşulu test_tarayici.py ile aynı."""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from kimlikwin.ayarlar import Ayarlar
from kimlikwin.baslangic import Otomatik
from kimlikwin.web import Sunucu
from kimlikwin.yonetici import Yonetici

sys.path.insert(0, str(Path(__file__).parent))
from test_tarayici import _atla, _node_ortami  # noqa: E402
from test_telefon import IO, TEL, _AU  # noqa: E402

BETIK = Path(__file__).parent / "tarayici" / "telefon.js"


@pytest.fixture(scope="module")
def sonuc(tmp_path_factory):
    node = shutil.which("node")
    if not node:
        _atla("node kurulu değil")
    kok = tmp_path_factory.mktemp("telefon_tarayici")
    y = Yonetici(Ayarlar(kok / "ayar"), Otomatik(_AU()), secici=lambda t: None, claude_yolu=lambda: None,
                 telefon_ayar=dict(TEL))
    y.api("sihirbaz_tamamla", {"yol": str(kok / "veri"), "otomatik_baslat": False})
    s = Sunucu(y, 0)
    s.baslat()
    ayar = kok / "ayar.json"
    sinyal = kok / "sinyal"
    ayar.write_text(json.dumps({"url": s.url, "sinyal": str(sinyal)}), encoding="utf-8")
    p = subprocess.Popen([node, str(BETIK), str(ayar)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         env=_node_ortami())
    try:
        satir = ""
        for satir in p.stdout:
            if satir.startswith("KOD "):
                break
        else:
            out, err = p.communicate(timeout=60)
            if p.returncode == 77:
                _atla("Playwright/Chromium yok: " + err.strip()[:200])
            pytest.fail("tarayıcı betiği kod üretmeden bitti: " + err[-2000:])
        kod = json.loads(satir[4:])
        i = IO.Istemci.kodla(kod["kod"], str(uuid.uuid4()), host="127.0.0.1", port=y.telefon.alici().port)
        i.eslestir(IO.eslestirme_coz(kod["kod"])["k"], ad="Deneme telefonu")
        sinyal.write_text("1")
        kalan, err = p.communicate(timeout=120)
        assert p.returncode == 0, err[-2500:]
        r = json.loads(kalan.strip().splitlines()[-1])
        r["png"] = kod["png"]
        r["telefon_calisiyor_sonra"] = y.telefon.calisiyor()
        r["cihaz_iptal"] = y.uygulama.hub.cihazlar()[0]["revoked"]
    finally:
        if p.poll() is None:
            p.kill()
        s.durdur()
        y.kapat()
    return r


def test_hata_yok(sonuc):
    assert sonuc["hatalar"] == [] and sonuc["bildirim_hatalari"] == []


def test_ilk_acista_aciklama_ve_ac_kapat(sonuc):
    assert sonuc["baslangic_durum"] == "Kapalı." and sonuc["ekle_pasif"] is True
    assert "yalnız ev ağından, yalnız eşleştirdiğin telefondan dosya kabul eder" in sonuc["aciklama"]
    assert "Özel ağlar" in sonuc["aciklama"] and "Ortak" in sonuc["aciklama"]
    assert sonuc["acik_durum"].startswith("Çalışıyor") and "127.0.0.1:" in sonuc["acik_durum"] and sonuc["acik_isaret"]
    assert sonuc["kapali_durum"] == "Kapalı." and sonuc["ekle_pasif_sonra"] is True
    assert sonuc["telefon_calisiyor_sonra"] is False


def test_telefon_ekle_kod_metin_ve_qr(sonuc):
    assert sonuc["kod"].startswith("km1:") and "Kalan süre: " in sonuc["kalan"]
    assert sonuc["qr"]["w"] > 100 and int(sonuc["qr"]["surum"]) >= 2
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    ham = base64.b64decode(sonuc["png"].split(",", 1)[1])
    im = cv2.imdecode(np.frombuffer(ham, np.uint8), cv2.IMREAD_GRAYSCALE)
    metin, _, _ = cv2.QRCodeDetector().detectAndDecode(im)
    assert metin == sonuc["kod"]                      # tarayıcıda çizilen QR, ekrandaki kodu aynen verir


def test_cihaz_listesi_ve_kaldirma(sonuc):
    assert "Kod kullanıldı" not in sonuc["kod_sonrasi"] and "Telefon eşleşti." in sonuc["kod_sonrasi"]
    assert "Deneme telefonu" in sonuc["cihaz"] and "android" in sonuc["cihaz"] and "Eşleştirmeyi kaldır" in sonuc["cihaz"]
    assert "Eşleştirme kaldırıldı" in sonuc["kaldirilan"] and sonuc["kaldir_dugmesi_kaldi"] is False
    assert sonuc["cihaz_iptal"] is True


def test_elle_aktarim_dugmesi_ice_aktar_sayfasina_gider(sonuc):
    assert sonuc["dosya_al"] is True and sonuc["ice_sayfasi"] is True
