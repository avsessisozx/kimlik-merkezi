"""GERÇEK TARAYICI: Kaynaklar sayfasındaki kopya denetimi kartı. Çalışma koşulu test_tarayici.py ile aynı."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from kimlikcore import EventIn, Hub

from kimlikwin.ayarlar import Ayarlar
from kimlikwin.baslangic import Otomatik
from kimlikwin.web import Sunucu
from kimlikwin.yonetici import Yonetici

sys.path.insert(0, str(Path(__file__).parent))
from test_tarayici import _atla, _node_ortami  # noqa: E402

BETIK = Path(__file__).parent / "tarayici" / "kopya.js"


class _AU:
    d = None

    def oku(self): return self.d
    def yaz(self, k): self.d = k
    def sil(self): self.d = None


def _m(key, text="selam dünya"):
    ts = "2026-05-01T10:00:00Z"
    return EventIn(ts=ts, kind="sohbet.mesaj", category="sohbet", text=text, event_key=key,
                   payload={"platform": "chatgpt", "konusma_id": "k1", "baslik": "B", "rol": "user", "mesaj_id": key, "ts": ts})


@pytest.fixture(scope="module")
def sonuc(tmp_path_factory):
    node = shutil.which("node")
    if not node:
        _atla("node kurulu değil")
    kok = tmp_path_factory.mktemp("kopya_tarayici")
    y = Yonetici(Ayarlar(kok / "ayar"), Otomatik(_AU()), secici=lambda t: None, claude_yolu=lambda: None)
    y.api("sihirbaz_tamamla", {"yol": str(kok / "veri"), "otomatik_baslat": False})
    y.kapat()
    with Hub.open(kok / "veri", write=True) as hub:
        sid = hub.add_source("sentetik", "1", None)
        hub.add_events(sid, [_m("a1"), _m("a2"), _m("a3", "öteki")])
    y = Yonetici(Ayarlar(kok / "ayar"), Otomatik(_AU()), secici=lambda t: None, claude_yolu=lambda: None)
    y.baslat()
    s = Sunucu(y, 0)
    s.baslat()
    ayar = kok / "ayar.json"
    ayar.write_text(json.dumps({"url": s.url}), encoding="utf-8")
    try:
        p = subprocess.run([node, str(BETIK), str(ayar)], capture_output=True, text=True, timeout=240, env=_node_ortami())
        gorunur = y.uygulama.hub.query_one("SELECT count(*) FROM events WHERE kind='sohbet.mesaj' AND hidden=0")[0]
    finally:
        s.durdur()
        y.kapat()
    if p.returncode == 77:
        _atla("Playwright/Chromium yok: " + p.stderr.strip()[:200])
    assert p.returncode == 0, p.stderr[-2500:]
    r = json.loads(p.stdout.strip().splitlines()[-1])
    r["gorunur_sonra"] = gorunur
    return r


def test_hata_yok(sonuc):
    assert sonuc["hatalar"] == [] and sonuc["bildirim_hatalari"] == []


def test_denetle_sayilari_gosterir_degistirmez(sonuc):
    assert "1 kopya mesaj ve 0 yeniden üretilmiş cevap bulundu. 2 mesaj kalacak. Henüz hiçbir şey değiştirilmedi." in sonuc["denetim"]
    assert "ChatGPT dışa aktarma dosyası" in sonuc["kart"] and sonuc["gizle_var"] is True


def test_gizle_onay_ister_ve_sonuc_gosterir(sonuc):
    assert "Kayıtlar silinmez, gizlenir." in sonuc["onay"]
    assert "1 kopya mesaj ve 0 yeniden üretilmiş cevap gizlendi" in sonuc["sonuc"]
    assert sonuc["gorunur_sonra"] == 2 and sonuc["gizle_sonra"] is False and sonuc["rapor_dugmesi"] is True
