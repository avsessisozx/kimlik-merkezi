"""GERÇEK TARAYICI: Ayarlar'daki yönetilen blok kartı. Çalışma koşulu test_tarayici.py ile aynı."""
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

BETIK = Path(__file__).parent / "tarayici" / "yonetilen_blok.js"


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
    kok = tmp_path_factory.mktemp("blok_tarayici")
    ev = kok / "ev"
    ev.mkdir()
    y = Yonetici(Ayarlar(kok / "ayar"), Otomatik(_AU()), secici=lambda t: None, claude_yolu=lambda: None, ev_klasoru=lambda: ev)
    y.api("sihirbaz_tamamla", {"yol": str(kok / "veri"), "otomatik_baslat": False})
    y.api("persona_ekle", {"metin": "Adım Deneme, yazılımcıyım", "kategori": "kimlik"})
    s = Sunucu(y, 0)
    s.baslat()
    ayar = kok / "ayar.json"
    ayar.write_text(json.dumps({"url": s.url, "claude": str(ev / ".claude" / "CLAUDE.md")}), encoding="utf-8")
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


def test_kart_aciklamasi_ve_varsayilan_kapali(sonuc):
    assert "Onayladığın bilgiler Claude Code ve Codex'in her oturumda okuduğu dosyalara kısa bir bölüm olarak yazılır. Kendi yazdıklarına dokunulmaz, önce yedek alınır." in sonuc["kart"]
    assert sonuc["baslangic_acik"] is False


def test_onizleme_metni_gosterir_ama_yazmaz(sonuc):
    assert "Adım Deneme, yazılımcıyım" in sonuc["onizleme"] and "KIMLIK-MERKEZI:BASLA" in sonuc["onizleme"]
    assert sonuc["onizleme_sonrasi_dosya"] is False


def test_acinca_dosya_olusur_kapatinca_bolum_kalkar(sonuc):
    assert "Adım Deneme, yazılımcıyım" in sonuc["acik_dosya"] and sonuc["ayar_acik"] is True
    assert "CLAUDE.md" in sonuc["acik_liste"] and "yazıldı" in sonuc["acik_liste"] and "Codex" in sonuc["acik_liste"] and "atlandı" in sonuc["acik_liste"]
    assert "KIMLIK-MERKEZI" not in sonuc["kapali_dosya"]
