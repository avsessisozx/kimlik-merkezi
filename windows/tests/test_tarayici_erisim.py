"""GERÇEK TARAYICI: Erişim sayfasında izin ekranı (madde 11). Çalışma koşulu test_tarayici.py ile aynı."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kimlikwin.ayarlar import Ayarlar
from kimlikwin.baslangic import Otomatik
from kimlikwin.web import Sunucu
from kimlikwin.yonetici import Yonetici

sys.path.insert(0, str(Path(__file__).parent))
from test_tarayici import _atla, _node_ortami  # noqa: E402

BETIK = Path(__file__).parent / "tarayici" / "erisim_izin.js"
HASSAS = {"eposta", "mesaj", "konum", "sohbet"}


class _AU:
    d = None

    def oku(self): return self.d
    def yaz(self, k): self.d = k
    def sil(self): self.d = None


@pytest.fixture(scope="module")
def sonuc(tmp_path_factory):
    node = shutil.which("node")
    if not node:
        _atla("node kurulu değil")
    kok = tmp_path_factory.mktemp("erisim_tarayici")
    cfg = kok / "claude_desktop_config.json"
    cfg.write_text("{}", encoding="utf-8")
    y = Yonetici(Ayarlar(kok / "ayar"), Otomatik(_AU()), secici=lambda t: None, claude_yolu=lambda: cfg)
    y.api("sihirbaz_tamamla", {"yol": str(kok / "veri"), "otomatik_baslat": False})
    s = Sunucu(y, 0)
    s.baslat()
    ayar = kok / "ayar.json"
    ayar.write_text(json.dumps({"url": s.url}), encoding="utf-8")
    try:
        p = subprocess.run([node, str(BETIK), str(ayar)], capture_output=True, text=True, timeout=240, env=_node_ortami())
    finally:
        s.durdur()
        y.kapat()
    if p.returncode == 77:
        _atla("Playwright/Chromium yok: " + p.stderr.strip()[:200])
    assert p.returncode == 0, p.stderr[-2500:]
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_hata_yok(sonuc):
    assert sonuc["hatalar"] == [] and sonuc["bildirim_hatalari"] == []


def test_claude_ekle_sonrasi_izin_ekrani_gorunur(sonuc):
    c = sonuc["claude"]
    assert "Claude şu an bunları görebilir. İstediğini kapat." in c["metin"]
    assert len(c["acik"]) == 10 and not (HASSAS & set(c["acik"]))
    assert HASSAS <= set(c["hepsi"]) and "kapalı; yalnız ayrı onayla açılır" in c["metin"]
    assert c["api"] == [c["acik"]]
    assert c["kapandi"] is True


def test_yeni_anahtar_onerilenler_isaretli_ama_kaydetmeden_verilmez(sonuc):
    y = sonuc["yeni"]
    assert len(y["secili"]) == 10 and not (HASSAS & set(y["secili"]))
    assert y["api_kaydetmeden"]["izinler"] == [] and y["api_kaydetmeden"]["izinsiz"] is True
    assert "Kaydet" in y["metin"] and "önerilen" in y["metin"]
    assert y["liste_etiketi"] and all(e == "Hiç izni yok" for e in y["liste_etiketi"])


def test_bos_kayitta_uyari_ve_onay_gerekir(sonuc):
    assert sonuc["yeni"]["bos_secili"] == []
    u = sonuc["uyari_vazgec"]
    assert u["diyalog"] == ["Bu anahtar hiçbir şeyi göremez. Yine de izinsiz bırakılsın mı?"] and u["ekran_acik"] is True
    o = sonuc["uyari_onay"]
    assert o["diyalog"] == ["Bu anahtar hiçbir şeyi göremez. Yine de izinsiz bırakılsın mı?"] and o["ekran_kapandi"] is True
    assert "Hiç izni yok" in o["etiket"]


def test_onerilenlerle_kaydet_uyarisiz_10_izin_verir(sonuc):
    o = sonuc["onerili"]
    assert o["diyalog"] == [] and len(o["api"]) == 10 and not (HASSAS & set(o["api"]))


def test_izinsiz_kapatmada_da_uyari(sonuc):
    k = sonuc["kapat_uyari"]
    assert k["diyalog"] == ["Bu anahtar hiçbir şeyi göremez. Yine de izinsiz bırakılsın mı?"] and k["ekran_acik"] is True
