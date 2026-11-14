"""İçe aktar ekranı: "Bilgisayarımdaki dosyalar ve klasörler" için GERÇEK TARAYICI testi (Playwright + Chromium).
Kurulum/atlama kuralları test_tarayici.py ile aynı (KIMLIK_TARAYICI_ZORUNLU=1 ise atlamak yerine KIRMIZI olur).
Dosya seçme penceresi (tkinter) yerine sahte seçici kullanılır: pencerenin kendisi bu testte AÇILMAZ."""
from __future__ import annotations

import json
import os
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
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "importers" / "tests"))
from karisik_klasor import BOZUK, ICERIKLI, YALNIZ_KAYIT, uret  # noqa: E402
from test_tarayici import _atla, _node_ortami  # noqa: E402

BETIK = Path(__file__).parent / "tarayici" / "dosya_ice.js"


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
    kok = tmp_path_factory.mktemp("dosya_tarayici")
    os.environ["KIMLIK_AYAR_DIZINI"] = str(kok / "ayar")
    klasor = uret(kok / "karisik")
    cok = [klasor / "kilavuz.pdf", klasor / "bozuk.pdf", klasor / "muzik.mp3", klasor / "tablo.xlsx"]

    def secici(tur):
        return str(klasor) if tur == "klasor" else "\n".join(str(p) for p in cok) if tur == "dosyalar" else None

    y = Yonetici(Ayarlar(kok / "ayar"), Otomatik(_AU()), secici=secici, claude_yolu=lambda: None)
    y.api("sihirbaz_tamamla", {"yol": str(kok / "veri"), "otomatik_baslat": False})
    s = Sunucu(y, 0)
    s.baslat()
    ayar = kok / "ayar.json"
    ayar.write_text(json.dumps({"url": s.url}), encoding="utf-8")
    try:
        p = subprocess.run([node, str(BETIK), str(ayar)], capture_output=True, text=True, timeout=300, env=_node_ortami())
    finally:
        s.durdur()
        y.kapat()
    if p.returncode == 77:
        _atla("Playwright/Chromium yok: " + p.stderr.strip()[:200])
    assert p.returncode == 0, p.stderr[-2500:]
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_secenek_gorunur_ve_acik_adlandirilmis(sonuc):
    assert sonuc["baslik"].startswith("Bilgisayarımdaki dosyalar ve klasörler")
    assert sonuc["baslangic_secim"] == "Henüz bir şey seçilmedi."


def test_klasor_secilip_computer_files_ile_calisir(sonuc):
    assert sonuc["tur_kutusu"] == ""                      # kullanıcı tür seçmedi; arayüz computer_files'ı kendisi seçti
    assert "karisik" in sonuc["klasor_secim"]
    assert sonuc["bildirim1"] == []
    assert f"{len(ICERIKLI)} dosya içeriğiyle, {len(YALNIZ_KAYIT)} dosya yalnız kayıt olarak (içerik okunamadı), {len(BOZUK)} dosya bozuk/okunamadığı için atlandı." in sonuc["ozet_metin"]
    assert "1 PDF'de okunabilir metin yok (taranmış olabilir)" in sonuc["metinsiz"]


def test_bozuk_dosyalar_nedeniyle_listelenir(sonuc):
    for ad in BOZUK:
        assert ad in sonuc["ayrintilar"], ad
    assert "bozuk ya da açılamadı" in sonuc["ayrintilar"] and "taranmis.pdf" in sonuc["ayrintilar"]


def test_cok_dosya_secimi(sonuc):
    assert "4 öğe seçildi" in sonuc["cok_secim"]
    assert "2 dosya içeriğiyle, 1 dosya yalnız kayıt olarak" in sonuc["cok_ozet"] and "1 dosya bozuk" in sonuc["cok_ozet"]


def test_ilerleme_islenen_toplam_gorunur(sonuc):
    assert "3 / 12 dosya" in sonuc["ilerleme_metin"]
    assert sonuc["ilerleme_cubuk"] == [3, 12]


def test_hata_ve_mobil_temiz(sonuc):
    assert sonuc["konsol_hatalari"] == []
    assert sonuc["mobil_tasma"] <= 0
