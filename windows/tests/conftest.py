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


@pytest.fixture(autouse=True)
def ayar_ortami(tmp_path, monkeypatch):
    monkeypatch.setenv("KIMLIK_AYAR_DIZINI", str(tmp_path / "ayar"))
    monkeypatch.delenv("KIMLIK_VERI", raising=False)


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
