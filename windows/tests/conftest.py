import os
import sys as _sys
from pathlib import Path as _Path

import pytest

from kimlikwin.ayarlar import Ayarlar
from kimlikwin.yonetici import Yonetici


class SahteArkaUc:
    def __init__(self):
        self.deger = None

    def oku(self):
        return self.deger

    def yaz(self, komut):
        self.deger = komut

    def sil(self):
        self.deger = None


def _gercek_playwright_yolu():
    """HOME yönlendirilmeden ÖNCE gerçek ev klasöründeki Playwright tarayıcı klasörü (yoksa None)."""
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return None                               # zaten ayarlı: dokunma
    ev = _Path.home()
    if _sys.platform == "win32":
        yerel = os.environ.get("LOCALAPPDATA")
        aday = _Path(yerel) / "ms-playwright" if yerel else ev / "AppData" / "Local" / "ms-playwright"
    elif _sys.platform == "darwin":
        aday = ev / "Library" / "Caches" / "ms-playwright"
    else:
        aday = ev / ".cache" / "ms-playwright"
    return str(aday) if aday.is_dir() else None


@pytest.fixture(autouse=True)
def ayar_ortami(tmp_path, monkeypatch):
    monkeypatch.setenv("KIMLIK_AYAR_DIZINI", str(tmp_path / "ayar"))
    monkeypatch.delenv("KIMLIK_VERI", raising=False)
    pw = _gercek_playwright_yolu()                # HOME değişmeden önce çöz; node tarayıcıyı yine bulsun
    if pw:
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", pw)
    ev =tmp_path / "ev"                      # gerçek ev klasörüne (CLAUDE.md/AGENTS.md) hiçbir test yazmasın
    ev.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setenv("USERPROFILE", str(ev))


@pytest.fixture(autouse=True)
def eski_kilitli_gorunum(request, monkeypatch):
    """Üretimde sahip görünümü açıktır (harita_kopru.SAHIP=True). Eski kilit/gizleme sınamaları
    `SAHIP=False` ile (savunma katmanı hâlâ çalışıyor mu diye) sürer; sahip görünümü test_sahip_gorunum.py'de."""
    if request.module.__name__.endswith("test_sahip_gorunum"):
        return
    from kimlikwin import harita_kopru
    monkeypatch.setattr(harita_kopru, "SAHIP", False)


@pytest.fixture
def veri(tmp_path):
    return tmp_path / "veri"


@pytest.fixture
def arka_uc():
    return SahteArkaUc()


@pytest.fixture
def yonetici(tmp_path, arka_uc):
    from kimlikwin.baslangic import Otomatik
    y = Yonetici(Ayarlar(tmp_path / "ayar"), Otomatik(arka_uc), secici=lambda tur: None,
                 claude_yolu=lambda: None)
    yield y
    y.kapat()


@pytest.fixture
def kurulu(yonetici, veri):
    yonetici.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": True})
    return yonetici


# Ağ koruması (kök ag_koruma.py): paket klasöründen tek başına koşulsa da devrede olsun.
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
from ag_koruma import ag_korumasi, pytest_configure, pytest_unconfigure, sifreleme_saglayici_yalitimi, girisde_baslatma_yalitimi  # noqa: E402,F401
