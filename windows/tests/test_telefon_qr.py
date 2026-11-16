"""Eşleştirme QR'ı (statik/qrcode.js, MIT; telefon.js qrMatris): bilinen girdi için beklenen matris özeti ve
(OpenCV varsa) gidiş-dönüş çözümü. Matris node vm ile tarayıcısız üretilir."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from kimlikserver.aktarim.eslestirme import eslestirme_metni

STATIK = Path(__file__).resolve().parents[1] / "src" / "kimlikwin" / "statik"
BETIK = Path(__file__).parent / "tarayici" / "qr_matris.js"

# Bilinen girdiler için matrisin SHA-256'sı (satırlar "\n" ile birleştirilmiş '0'/'1'); değerler OpenCV ile
# çözülerek doğrulandı (HELLO -> sürüm 1, 21x21; "km1:"+"A"*20 -> sürüm 2, 25x25; hata düzeltme M).
BILINEN = {
    "HELLO": ("1fff7fd781f0f59edd796e0f79b20d68de6ecef41b47571460c4bbfbac1afe97", 21),
    "km1:" + "A" * 20: ("1731fdfc49fd3b9c3b816b5f2ab774e9bd1ce167b8cb5a9137cbc2b6bc5b3c57", 25),
}


def _matrisler(metinler):
    node = shutil.which("node")
    if not node:
        pytest.skip("node kurulu değil")
    p = subprocess.run([node, str(BETIK), str(STATIK)], input=json.dumps(metinler), capture_output=True,
                       text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    return json.loads(p.stdout)


def _coz(matris):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    n, mod, sessiz = len(matris), 8, 4
    im = np.full(((n + 2 * sessiz) * mod,) * 2, 255, dtype=np.uint8)
    for r, satir in enumerate(matris):
        for c, v in enumerate(satir):
            if v == "1":
                im[(r + sessiz) * mod:(r + sessiz + 1) * mod, (c + sessiz) * mod:(c + sessiz + 1) * mod] = 0
    metin, _, _ = cv2.QRCodeDetector().detectAndDecode(im)
    return metin


def test_bilinen_girdi_beklenen_matris():
    for metin, m in zip(BILINEN, _matrisler(list(BILINEN))):
        ozet, boyut = BILINEN[metin]
        assert len(m) == boyut and all(len(s) == boyut for s in m)
        assert hashlib.sha256("\n".join(m).encode()).hexdigest() == ozet


def test_gercek_km1_kodu_yeter_ve_geri_cozulur():
    kodlar = [eslestirme_metni(["192.168.1.20"], 47821, "ab" * 32, "k" * 43, "Ev bilgisayarı"),
              eslestirme_metni(["192.168.1.20", "10.0.0.5", "172.16.3.4"], 47821, "cd" * 32, "z" * 43,
                               "Ofis-PC-çok-uzun-bir-ad")]
    assert all(150 <= len(k) <= 400 for k in kodlar)
    for kod, m in zip(kodlar, _matrisler(kodlar)):
        assert len(m) <= 177 and (len(m) - 17) % 4 == 0           # QR sürümü <= 40
        assert _coz(m) == kod


def test_matris_hata_duzeltme_ve_ascii_disi_degil():
    # Eşleştirme kodu base64url (ASCII) olduğundan bayt kipi yeter; boş metin değil, her zaman kare matris
    m = _matrisler(["km1:abc_-"])[0]
    assert len(m) == len(m[0]) and set("".join(m)) <= {"0", "1"}
