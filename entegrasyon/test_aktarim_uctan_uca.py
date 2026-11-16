"""GOREV Aşama 6, telefon -> PC aktarımının dört senaryosu (örnek istemciyle, gerçek soket, 127.0.0.1):
1) çevrimdışı biriktirme, 2) bağlanınca eksiksiz aktarım, 3) aktarım ortasında kesme ve devam,
4) iki kez aktarım tekrarsız. Her senaryo sonunda veritabanındaki olay kimlik kümesi == gönderilen kayıt kümesi.
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server" / "tests"))
from istemci_ornek import Istemci, kutu_dosyasi  # noqa: E402
from kimlikcore import Hub  # noqa: E402
from kimlikimport.base import stable_key  # noqa: E402
from kimlikserver.aktarim import AktarimAlici, DogrudanKopru, eslestirme_coz, gelenleri_ice_al  # noqa: E402


class Dunya:
    def __init__(self, kok: Path):
        self.veri = kok / "pc"
        self.hub = Hub.open(self.veri, write=True)
        self.cihaz = str(uuid.uuid4())
        self.giden = kok / "telefon" / "giden"
        self.giden.mkdir(parents=True)
        self.gonderilen: set[str] = set()          # telefonda yazılan kayıtların PC'deki olay anahtarları
        self.alici = self._alici(0)
        self.alici.baslat()
        km1 = self.alici.eslestirme_kodu_uret(adresler=["127.0.0.1"])
        self.istemci = Istemci.kodla(km1, self.cihaz, parca_bayt=700)
        self.istemci.eslestir(eslestirme_coz(km1)["k"])

    def _alici(self, port):
        return AktarimAlici(DogrudanKopru(self.hub), self.veri, port=port, adres="127.0.0.1", bulma_port=0,
                            saglayici=None)

    def yeniden_baslat(self):
        port = self.alici.port
        self.alici.durdur()
        self.alici = self._alici(port)
        self.alici.baslat()

    def telefonda_dosya(self, kayit: int) -> Path:
        dosya_id = str(uuid.uuid4())
        veri = kutu_dosyasi(self.cihaz, dosya_id, kayit, on_ek=dosya_id)
        yol = self.giden / f"{dosya_id}.jsonl"
        yol.write_bytes(veri)
        for ln in veri.decode().splitlines()[1:-1]:
            self.gonderilen.add(stable_key("android", self.cihaz, json.loads(ln)["id"]))
        return yol

    def veritabanindaki(self) -> set[str]:
        return {k for (k,) in self.hub.query("SELECT event_key FROM events")}

    def kapat(self):
        self.alici.durdur()
        self.hub.close()


@pytest.fixture
def d(tmp_path):
    w = Dunya(tmp_path)
    yield w
    w.kapat()


def test_senaryo1_cevrimdisi_biriktirme(d):
    d.alici.durdur()                                   # PC kapalı
    for n in (5, 8, 3):
        d.telefonda_dosya(n)
    r = d.istemci.klasor_gonder(d.giden)
    assert r["bekleyen"] == 3 and r["var"] == 0 and r["hata"]
    assert len(list(d.giden.glob("*.jsonl"))) == 3     # telefon hiçbirini silmedi
    assert d.veritabanindaki() == set() and gelenleri_ice_al(d.hub)["dosya"] == 0


def test_senaryo2_baglaninca_eksiksiz_aktarim(d):
    d.alici.durdur()
    for n in (5, 8, 3, 12):
        d.telefonda_dosya(n)
    d.istemci.klasor_gonder(d.giden)                   # başarısız, birikir
    d.yeniden_baslat()                                 # PC açıldı
    r = d.istemci.tekrarla(d.giden, 30)
    assert r["bitti"] and r["var"] == 4
    assert list(d.giden.glob("*.jsonl")) == []         # telefon yalnız `var` sonrası siler
    s = gelenleri_ice_al(d.hub)
    assert s == {"dosya": 4, "yeni": 28, "yinelenen": 0, "eksik": 0}
    assert d.veritabanindaki() == d.gonderilen and len(d.gonderilen) == 28
    assert not list((d.veri / "gelen_aktarim").rglob("*.jsonl"))


def test_senaryo3_aktarim_ortasinda_kesme_ve_devam(d):
    yol = d.telefonda_dosya(400)                        # çok parçalı dosya
    sha = hashlib.sha256(yol.read_bytes()).hexdigest()
    d.istemci.parca_arasi_s = 0.03
    sonuc: dict = {}

    def gonder():
        try:
            sonuc["r"] = d.istemci.klasor_gonder(d.giden, var_olunca_sil=False)
        except Exception as e:  # noqa: BLE001
            sonuc["hata"] = e

    t = threading.Thread(target=gonder)
    t.start()
    gecici = d.veri / "aktarim" / "gecici" / d.cihaz
    bitis = time.time() + 20
    while time.time() < bitis:                          # yarıdan fazlası gelene dek bekle, sonra PC'yi kapat
        parca = gecici / f"{yol.stem}.part"
        if parca.exists() and parca.stat().st_size > yol.stat().st_size // 3:
            break
        time.sleep(0.01)
    alinan_once = (gecici / f"{yol.stem}.part").stat().st_size
    d.alici.durdur()
    t.join(30)
    assert not t.is_alive() and yol.exists()
    assert 0 < alinan_once < yol.stat().st_size
    d.yeniden_baslat()                                  # PC yeniden açıldı
    d.istemci.parca_arasi_s = 0
    ilk, ofset = d.istemci.durum(yol.stem)
    assert ilk == "kismi" and ofset >= alinan_once      # kaldığı bayttan
    r = d.istemci.dosya_gonder(yol)
    assert r["sonuc"] == "var" and r["baslangic_ofset"] == ofset and r["gonderilen_bayt"] == yol.stat().st_size - ofset
    (hedef,) = list((d.veri / "gelen_aktarim").rglob("*.jsonl"))
    assert hashlib.sha256(hedef.read_bytes()).hexdigest() == sha
    assert gelenleri_ice_al(d.hub)["yeni"] == 400
    assert d.veritabanindaki() == d.gonderilen


def test_senaryo4_iki_kez_aktarim_tekrarsiz(d):
    yollar = [d.telefonda_dosya(n) for n in (6, 9)]
    yedek = {p.name: p.read_bytes() for p in yollar}
    assert d.istemci.klasor_gonder(d.giden)["var"] == 2
    assert gelenleri_ice_al(d.hub)["yeni"] == 15
    # telefon (ör. silme başarısız oldu / kullanıcı yedekten geri yükledi) aynı dosyaları yeniden gönderir
    for ad, veri in yedek.items():
        (d.giden / ad).write_bytes(veri)
    r = d.istemci.klasor_gonder(d.giden)
    assert r["var"] == 2 and r["gonderilen_bayt"] == 0     # alıcı `var` dedi, bayt gitmedi
    assert not list((d.veri / "gelen_aktarim").rglob("*.jsonl"))
    assert gelenleri_ice_al(d.hub) == {"dosya": 0, "yeni": 0, "yinelenen": 0, "eksik": 0}
    assert d.veritabanindaki() == d.gonderilen and len(d.gonderilen) == 15
    # aynı içerik yeni dosya kimliğiyle gelse bile (kayıt kimlikleri aynı) 0 yeni olay: elle zip ile ikinci yol
    import zipfile

    z = d.giden.parent / "elle.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for ad, veri in yedek.items():
            zf.writestr(ad, veri)
    from kimlikimport.run import run

    assert run(d.hub, z, "android_giden").added == 0
