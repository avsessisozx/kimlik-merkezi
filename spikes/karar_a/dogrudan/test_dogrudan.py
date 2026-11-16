"""Aday 1: doğrudan HTTPS. Senaryolar (a)-(h)."""
from __future__ import annotations

import http.client
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

import alici as alici_mod
import sertifika
from alici import Alici, yerel_adres_mi
from istemci import Istemci, ParmakIziUyusmadi, Yetkisiz, _SabitBaglanti, parmak_izi
from ortak import dogrula, dosya_yaz, olc, satir_uuidleri, sha256_dosya, uret_giden_kutusu

ANAHTAR = "ortak-gizli-anahtar-test"
CIHAZ = "telefon-1"
KLASOR = Path(__file__).parent
ADAY = "dogrudan"


def bos_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def sert(tmp_path_factory):
    d = tmp_path_factory.mktemp("sert")
    a = sertifika.uret(d, "a")
    b = sertifika.uret(d, "b")
    return {"a": a, "b": b, "pin_a": parmak_izi(a[0]), "pin_b": parmak_izi(b[0])}


@pytest.fixture
def alici(tmp_path, sert):
    a = Alici(tmp_path / "pc", ANAHTAR, *sert["a"]).baslat()
    yield a
    a.durdur()


def istemci(port, sert, **kw):
    return Istemci("127.0.0.1", port, kw.pop("anahtar", ANAHTAR), kw.pop("pin", sert["pin_a"]), **kw)


class AliciSurec:
    def __init__(self, kok, port, sert):
        self.kok, self.port, self.sert, self.p = kok, port, sert, None

    def baslat(self):
        self.p = subprocess.Popen([sys.executable, str(KLASOR / "alici.py"), str(self.kok), str(self.port),
                                   ANAHTAR, *self.sert["a"]], stdout=subprocess.PIPE, text=True)
        assert self.p.stdout.readline().startswith("HAZIR")

    def oldur(self):
        self.p.kill()
        self.p.wait()
        self.p.stdout.close()

    def bitir(self):
        if self.p and self.p.poll() is None:
            self.oldur()


def bekle(kosul, sure=60):
    bitis = time.time() + sure
    while time.time() < bitis:
        if kosul():
            return True
        time.sleep(0.01)
    return False


def part_boyut(kok: Path) -> int:
    return sum(p.stat().st_size for p in (kok / "gecici").rglob("*.part"))


def surdur(c, yol, cihaz, sure=90):
    """Hata olursa bekleyip yeniden dener; sonuçları/hataları sıralı döndürür."""
    kayit, bitis = [], time.time() + sure
    while time.time() < bitis:
        try:
            kayit.append(c.dosya_gonder(yol, cihaz))
            return kayit
        except Exception as e:  # noqa: BLE001
            kayit.append(type(e).__name__)
            c.kapat()
            time.sleep(0.2)
    return kayit


def buyuk_dosya(yol: Path, mb: int, cihaz=CIHAZ) -> list[str]:
    return dosya_yaz(yol, cihaz, mb * 1024, doldur=900)  # ~1 KB satır


# (a) alıcı kapalıyken birikir, açılınca hepsi gider
def test_a_alici_kapaliyken_birikir_acilinca_gider(tmp_path, sert):
    giden = tmp_path / "telefon"
    port = bos_port()
    gonderilen = uret_giden_kutusu(giden, CIHAZ, 20, 100)
    c = istemci(port, sert)
    r = c.klasor_gonder(giden, CIHAZ)
    assert r["bekleyen"] == 20 and r["tamam"] == 0 and r["hata"]
    gonderilen.update(uret_giden_kutusu(giden, CIHAZ, 10, 100))  # "ikinci gün"
    # açık (yazılıyor) dosya aktarılmamalı
    (giden / CIHAZ / f"{uuid.uuid4()}.jsonl.acik").write_bytes(b'{"id": "x"')
    sur = AliciSurec(tmp_path / "pc", port, sert)
    try:
        sur.baslat()
        t0 = time.perf_counter()
        r = c.tekrarla(giden, CIHAZ, 60)
        sure = time.perf_counter() - t0
    finally:
        sur.bitir()
    assert r["bitti"] and r["tamam"] == 30
    dogrula(gonderilen, satir_uuidleri(tmp_path / "pc" / "gelen"))
    assert not list((tmp_path / "pc" / "gelen").rglob("*.acik"))
    olc(ADAY, "a_birikim", dosya=30, satir=3000, sure_s=f"{sure:.2f}")


# (b) yükleme ortasında alıcı kill -> kaldığı bayttan devam
def test_b_alici_kill_devam(tmp_path, sert):
    giden = tmp_path / "telefon"
    yol = giden / CIHAZ / f"{uuid.uuid4()}.jsonl"
    kimlikler = buyuk_dosya(yol, 24)
    boyut = yol.stat().st_size
    port = bos_port()
    kok = tmp_path / "pc"
    sur = AliciSurec(kok, port, sert)
    c = istemci(port, sert, parca_bayt=256 * 1024, parca_arasi_s=0.02)
    kayit: list = []
    try:
        sur.baslat()
        it = threading.Thread(target=lambda: kayit.extend(surdur(c, yol, CIHAZ)))
        it.start()
        assert bekle(lambda: part_boyut(kok) >= 3 * 1024 * 1024), "yükleme başlamadı"
        sur.oldur()
        olu = part_boyut(kok)
        assert 0 < olu < boyut
        time.sleep(0.8)
        sur.baslat()
        it.join(90)
        assert not it.is_alive()
    finally:
        sur.bitir()
    son = kayit[-1]
    assert isinstance(son, dict) and son["sonuc"] == "tamam", kayit
    assert son["baslangic_ofset"] >= olu > 0, (son, olu)
    assert son["baslangic_ofset"] + son["gonderilen_bayt"] == boyut
    assert sha256_dosya(kok / "gelen" / CIHAZ / yol.name) == sha256_dosya(yol)
    assert not list((kok / "gecici").rglob("*.part"))
    dogrula(kimlikler, satir_uuidleri(kok / "gelen"))
    olc(ADAY, "b_alici_kill", boyut_bayt=boyut, kill_aninda_alinan=olu, devam_ofseti=son["baslangic_ofset"],
        devamda_gonderilen=son["gonderilen_bayt"], hatalar=len(kayit) - 1, sha_esit=True)


# (c) istemci ortada öldürülür, yeniden başlar
def test_c_istemci_kill_devam(tmp_path, sert, alici):
    giden = tmp_path / "telefon"
    yol = giden / CIHAZ / f"{uuid.uuid4()}.jsonl"
    kimlikler = buyuk_dosya(yol, 24)
    boyut = yol.stat().st_size
    kok = Path(alici.srv.kok)
    p = subprocess.Popen([sys.executable, str(KLASOR / "istemci.py"), str(giden), CIHAZ, str(alici.port),
                          ANAHTAR, sert["pin_a"], str(256 * 1024), "0.02"], stdout=subprocess.PIPE, text=True)
    try:
        assert bekle(lambda: part_boyut(kok) >= 3 * 1024 * 1024), "yükleme başlamadı"
        p.kill()
        p.wait()
    finally:
        p.stdout.close()
    time.sleep(0.8)
    olu = part_boyut(kok)
    assert 0 < olu < boyut
    r = istemci(alici.port, sert).dosya_gonder(yol, CIHAZ)
    assert r["sonuc"] == "tamam" and r["baslangic_ofset"] >= olu
    assert r["baslangic_ofset"] + r["gonderilen_bayt"] == boyut
    assert sha256_dosya(kok / "gelen" / CIHAZ / yol.name) == sha256_dosya(yol)
    dogrula(kimlikler, satir_uuidleri(kok / "gelen"))
    olc(ADAY, "c_istemci_kill", boyut_bayt=boyut, kill_aninda_alinan=olu, devam_ofseti=r["baslangic_ofset"],
        devamda_gonderilen=r["gonderilen_bayt"], sha_esit=True)


# (d) aynı dosya iki kez
def test_d_ayni_dosya_iki_kez(tmp_path, sert, alici):
    giden = tmp_path / "telefon"
    gonderilen = uret_giden_kutusu(giden, CIHAZ, 3, 50)
    c = istemci(alici.port, sert)
    r1 = c.klasor_gonder(giden, CIHAZ)
    r2 = c.klasor_gonder(giden, CIHAZ)
    assert (r1["tamam"], r1["var"]) == (3, 0) and (r2["tamam"], r2["var"]) == (0, 3)
    assert r2["gonderilen_bayt"] == 0
    # yanıtı kaybolan istemci HEAD'siz tüm dosyayı yeniden PUT eder
    ad, kimlik_listesi = next(iter(gonderilen.items()))
    veri = (giden / CIHAZ / ad).read_bytes()
    bag = _SabitBaglanti("127.0.0.1", alici.port, sert["pin_a"], 10)
    bag.request("PUT", f"/{CIHAZ}/{ad}", body=veri, headers={
        "Authorization": f"Bearer {ANAHTAR}", "Content-Range": f"bytes 0-{len(veri)-1}/{len(veri)}",
        "X-Sha256": sha256_dosya(giden / CIHAZ / ad), "Content-Length": str(len(veri))})
    y = bag.getresponse()
    y.read()
    bag.close()
    assert y.status == 200 and y.getheader("X-Durum") == "var"
    gelen = Path(alici.srv.gelen) / CIHAZ
    assert len(list(gelen.glob("*.jsonl"))) == 3
    dogrula(gonderilen, satir_uuidleri(Path(alici.srv.gelen)))
    olc(ADAY, "d_cift_gonderim", dosya=3, ikinci_turda_gonderilen_bayt=r2["gonderilen_bayt"], tek_kopya=True)


# (e) anahtar yanlış/eksik -> 401, bayt yazılmaz
def test_e_yanlis_anahtar_401(tmp_path, sert, alici):
    giden = tmp_path / "telefon"
    uret_giden_kutusu(giden, CIHAZ, 1, 50)
    ad = next((giden / CIHAZ).glob("*.jsonl"))
    for anahtar in ("yanlis", None, ""):
        with pytest.raises(Yetkisiz):
            istemci(alici.port, sert, anahtar=anahtar).dosya_gonder(ad, CIHAZ)
    # doğrudan PUT: gövdeyle birlikte, yanlış anahtar
    veri = ad.read_bytes()
    bag = _SabitBaglanti("127.0.0.1", alici.port, sert["pin_a"], 10)
    bag.request("PUT", f"/{CIHAZ}/{ad.name}", body=veri, headers={
        "Authorization": "Bearer yanlis", "Content-Range": f"bytes 0-{len(veri)-1}/{len(veri)}",
        "X-Sha256": sha256_dosya(ad), "Content-Length": str(len(veri))})
    try:
        y = bag.getresponse()
        kod = y.status
    except (ConnectionError, http.client.HTTPException):
        kod = 401  # sunucu bağlantıyı 401 sonrası kapattı; yanıt okunamadı
    bag.close()
    assert kod == 401
    kok = Path(alici.srv.kok)
    assert not list((kok / "gelen").rglob("*")) and not list((kok / "gecici").rglob("*.part"))
    olc(ADAY, "e_yanlis_anahtar", durum=401, yazilan_bayt=0)


# (f) yanlış sertifika parmak izi -> istemci göndermez
def test_f_yanlis_parmak_izi(tmp_path, sert, alici):
    giden = tmp_path / "telefon"
    uret_giden_kutusu(giden, CIHAZ, 2, 50)
    with pytest.raises(ParmakIziUyusmadi):
        istemci(alici.port, sert, pin=sert["pin_b"]).klasor_gonder(giden, CIHAZ)
    assert alici.srv.istek_sayisi == 0
    assert not list((Path(alici.srv.kok) / "gelen").rglob("*.jsonl"))
    olc(ADAY, "f_yanlis_parmak_izi", alicida_gorulen_istek=alici.srv.istek_sayisi)


# (g) yalnız yerel ağ adresleri
@pytest.mark.parametrize("adres,beklenen", [
    ("127.0.0.1", True), ("127.5.5.5", True), ("::1", True), ("10.0.0.1", True), ("10.255.255.255", True),
    ("172.16.0.1", True), ("172.31.255.255", True), ("192.168.1.20", True), ("::ffff:192.168.1.20", True),
    ("172.15.255.255", False), ("172.32.0.1", False), ("8.8.8.8", False), ("100.64.0.1", False),
    ("169.254.1.1", False), ("192.169.0.1", False), ("2001:db8::1", False), ("::ffff:8.8.8.8", False),
    ("fe80::1%eth0", False), ("kotu", False), ("", False),
])
def test_g_adres_suzgeci(adres, beklenen):
    assert yerel_adres_mi(adres) is beklenen


def test_g_sunucu_dis_adresi_reddeder(tmp_path, sert):
    a = Alici(tmp_path / "pc", ANAHTAR, *sert["a"])
    try:
        srv = a.srv
        assert srv.verify_request(None, ("192.168.0.5", 1234)) is True
        assert srv.verify_request(None, ("8.8.8.8", 1234)) is False
        srv.yalniz_yerel = False
        assert srv.verify_request(None, ("8.8.8.8", 1234)) is True
    finally:
        a.srv.server_close()


# (h) süre ölçümü
def test_h1_200_dosya_50kb(tmp_path, sert, alici):
    giden = tmp_path / "telefon"
    gonderilen = uret_giden_kutusu(giden, CIHAZ, 200, 50, doldur=800)  # ~50 KB
    toplam = sum(p.stat().st_size for p in (giden / CIHAZ).glob("*.jsonl"))
    c = istemci(alici.port, sert)
    t0 = time.perf_counter()
    r = c.klasor_gonder(giden, CIHAZ)
    sure = time.perf_counter() - t0
    assert r["tamam"] == 200 and r["bekleyen"] == 0
    t1 = time.perf_counter()
    r2 = istemci(alici.port, sert).klasor_gonder(giden, CIHAZ)
    bos = time.perf_counter() - t1
    assert r2["var"] == 200
    dogrula(gonderilen, satir_uuidleri(Path(alici.srv.gelen)))
    olc(ADAY, "h_200x50KB", dosya=200, toplam_mb=f"{toplam/1e6:.1f}", sure_s=f"{sure:.2f}",
        dosya_basina_ms=f"{sure*1000/200:.1f}", tekrar_tur_sure_s=f"{bos:.2f}")


def test_h2_tek_dosya_200mb(tmp_path, sert, alici):
    yol = tmp_path / "telefon" / CIHAZ / f"{uuid.uuid4()}.jsonl"
    buyuk_dosya(yol, 200)
    boyut = yol.stat().st_size
    c = istemci(alici.port, sert, parca_bayt=1024 * 1024, zaman_asimi=60)
    t0 = time.perf_counter()
    r = c.dosya_gonder(yol, CIHAZ)
    sure = time.perf_counter() - t0
    assert r["sonuc"] == "tamam"
    assert sha256_dosya(Path(alici.srv.gelen) / CIHAZ / yol.name) == sha256_dosya(yol)
    olc(ADAY, "h_1x200MB", bayt=boyut, sure_s=f"{sure:.2f}", mb_s=f"{boyut/1e6/sure:.1f}", sha_esit=True)
