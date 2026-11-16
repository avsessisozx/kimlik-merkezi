import pytest

from helpers import FakeClock, build_world


@pytest.fixture
def veri(tmp_path):
    root = tmp_path / "veri"
    root.mkdir()
    return root


@pytest.fixture
def world(veri):
    w = build_world(veri)
    w["root"] = veri
    return w


@pytest.fixture
def clock():
    return FakeClock()


# Ağ koruması (kök ag_koruma.py): paket klasöründen tek başına koşulsa da devrede olsun.
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
from ag_koruma import ag_korumasi, pytest_configure, pytest_unconfigure, sifreleme_saglayici_yalitimi, girisde_baslatma_yalitimi  # noqa: E402,F401


# --- telefon aktarımı (test_aktarim_*.py) ------------------------------------------------------------
import uuid as _uuid


class AktarimDunyasi:
    """Gerçek Hub + gerçek soketli alıcı (127.0.0.1, rastgele port) + eşleşmiş örnek istemci."""

    def __init__(self, kok, **alici_kw):
        from kimlikcore import Hub
        from kimlikserver.aktarim import AktarimAlici, DogrudanKopru

        self.kok = kok
        self.veri = kok / "veri"
        self.hub = Hub.open(self.veri, write=True)
        self.tamamlananlar: list = []
        self.kopru = DogrudanKopru(self.hub, self.tamamlananlar.append)
        self._alici_kw = {"adres": "127.0.0.1", "port": 0, "bulma_port": 0, "saglayici": None, **alici_kw}
        self.alici = AktarimAlici(self.kopru, self.veri, **self._alici_kw)
        self.alici.baslat()
        self.cihaz = str(_uuid.uuid4())
        self.cikis = kok / "telefon"
        self.cikis.mkdir()

    def yeni_alici(self, **kw):
        """Aynı veri klasörü ve aynı portla yeni alıcı (öncekini durdurmuş olmalısınız)."""
        from kimlikserver.aktarim import AktarimAlici

        self.alici = AktarimAlici(self.kopru, self.veri, **{**self._alici_kw, "port": self.alici.port, **kw})
        self.alici.baslat()
        return self.alici

    def istemci(self, **kw):
        from istemci_ornek import Istemci

        return Istemci("127.0.0.1", self.alici.port, self.alici.parmak_izi, self.cihaz, **kw)

    def eslesmis(self, **kw):
        km1 = self.alici.eslestirme_kodu_uret()
        i = self.istemci(**kw)
        from kimlikserver.aktarim import eslestirme_coz

        i.eslestir(eslestirme_coz(km1)["k"])
        return i

    def dosya_yaz(self, dosya_id=None, kayit=5, **kw):
        from istemci_ornek import kutu_dosyasi

        dosya_id = dosya_id or str(_uuid.uuid4())
        yol = self.cikis / f"{dosya_id}.jsonl"
        yol.write_bytes(kutu_dosyasi(self.cihaz, dosya_id, kayit, **kw))
        return yol

    def dosyalar(self, klasor):
        return sorted(p for p in (self.veri / klasor).rglob("*") if p.is_file()) if (self.veri / klasor).exists() else []

    def kapat(self):
        self.alici.durdur()
        self.hub.close()


@pytest.fixture
def aktarim(tmp_path):
    d = AktarimDunyasi(tmp_path)
    yield d
    d.kapat()
