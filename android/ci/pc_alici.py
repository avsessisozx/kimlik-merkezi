#!/usr/bin/env python3
"""Uçtan uca CI için gerçek PC alıcısı (yalnız depodaki paketler: kimlikcore, kimlikserver, kimlikimport).

Komutlar:
  baslat   --calisma D [--port 47923]   arka planda başlatır (PID dosyası), hazır olunca döner
  durdur   --calisma D                  SIGTERM: alıcıyı durdurur, kalanı içe alır, Hub'ı kapatır
  oldur    --calisma D                  SIGKILL (kesinti senaryosu)
  kod      --calisma D                  yeni eşleştirme kodu üretir ve basar
  dogrula  --calisma D --beklenen F     veritabanındaki android.* olaylarını beklenenle karşılaştırır
  bekle-kismi --calisma D --en-az B     geçici .part en az B bayt olunca boyutu basar

Emülatör ana makineye 10.0.2.2 ile ulaşır; ana makinede bağlantı 127.0.0.1'den gelir.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

PORT = 47923
EMULATOR_ANA_MAKINE = "10.0.2.2"


def yollar(calisma: Path) -> dict[str, Path]:
    return {
        "veri": calisma / "veri", "pid": calisma / "alici.pid", "kod": calisma / "eslestirme_kodu.txt",
        "gunluk": calisma / "alici.log", "hazir": calisma / "alici.hazir", "ice_alma": calisma / "ice_alma.log",
    }


def _yaz(y: dict, ileti: str) -> None:
    with open(y["ice_alma"], "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {ileti}\n")


# --- çalışan süreç -----------------------------------------------------------------------------------------------
def calis(calisma: Path, port: int) -> int:
    from kimlikcore import Hub
    from kimlikserver.aktarim import AktarimAlici, DogrudanKopru, gelenleri_ice_al

    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", stream=sys.stdout)
    import traceback

    from kimlikserver.aktarim import alici as _al

    _ham_hata, _ham_islem = _al._Sunucu.handle_error, _al._Sunucu.process_request

    def _hata(self, request, client_address):      # tanilama: sunucu hatasini yutma, yaz
        print("SUNUCU HATA", client_address, traceback.format_exc().strip().splitlines()[-1], flush=True)

    def _islem(self, request, client_address):
        n = self._ip_sayac.get(client_address[0], 0)
        print(f"BAGLANTI {client_address} acik_ip={n} sem_acik={len(self._acik)}", flush=True)
        return _ham_islem(self, request, client_address)

    _al._Sunucu.handle_error, _al._Sunucu.process_request = _hata, _islem
    y = yollar(calisma)
    y["veri"].mkdir(parents=True, exist_ok=True)
    hub = Hub.open(y["veri"], write=True)
    kuyruk: queue.Queue = queue.Queue()
    alici = AktarimAlici(DogrudanKopru(hub, tamamlandi=kuyruk.put), y["veri"], port=port, adres="127.0.0.1",
                         saglayici=None, bulma_port=None)
    alici.baslat()
    dur = threading.Event()
    yeni_kod = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: dur.set())
    signal.signal(signal.SIGINT, lambda *_: dur.set())
    signal.signal(signal.SIGUSR1, lambda *_: yeni_kod.set())

    def kod_yaz() -> None:
        km1 = alici.eslestirme_kodu_uret(adresler=[EMULATOR_ANA_MAKINE])
        gecici = y["kod"].with_suffix(".tmp")
        gecici.write_text(km1, encoding="utf-8")
        os.replace(gecici, y["kod"])

    def ice_al(neden: str) -> None:
        s = gelenleri_ice_al(hub)
        if s["dosya"] or s["eksik"]:
            _yaz(y, f"ice_al({neden}): {s}")

    kod_yaz()
    ice_al("acilis")                 # önceki ömürden kalan tamamlanmış dosyalar
    y["hazir"].write_text(str(alici.port), encoding="utf-8")
    print(f"alici hazir port={alici.port} parmak_izi={alici.parmak_izi[:16]}", flush=True)
    while not dur.is_set():
        geldi = False
        try:
            kuyruk.get(timeout=0.3)
            geldi = True
            while True:              # birikenleri tek turda al
                kuyruk.get_nowait()
        except queue.Empty:
            pass
        if geldi:
            ice_al("tamamlandi")
        if yeni_kod.is_set():
            yeni_kod.clear()
            kod_yaz()
    alici.durdur()
    ice_al("kapanis")
    hub.close()
    print("alici kapandi", flush=True)
    return 0


# --- kabuk komutları ---------------------------------------------------------------------------------------------
def _pid(y: dict) -> int | None:
    try:
        return int(y["pid"].read_text())
    except (OSError, ValueError):
        return None


def _yasiyor(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"
    except OSError:
        return True


def baslat(calisma: Path, port: int) -> int:
    calisma.mkdir(parents=True, exist_ok=True)
    y = yollar(calisma)
    if _yasiyor(_pid(y)):
        print("HATA: alici zaten calisiyor", file=sys.stderr)
        return 1
    y["hazir"].unlink(missing_ok=True)
    gunluk = open(y["gunluk"], "ab")
    p = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "calis", "--calisma", str(calisma),
                          "--port", str(port)], stdout=gunluk, stderr=subprocess.STDOUT, start_new_session=True)
    y["pid"].write_text(str(p.pid))
    son = time.time() + 60
    while time.time() < son:
        if y["hazir"].exists():
            print(f"alici basladi pid={p.pid} port={y['hazir'].read_text()}")
            return 0
        if p.poll() is not None:
            break
        time.sleep(0.1)
    print("HATA: alici baslamadi", file=sys.stderr)
    print(y["gunluk"].read_text(errors="replace")[-2000:], file=sys.stderr)
    return 1


def _bitis_bekle(pid: int, sn: float) -> bool:
    son = time.time() + sn
    while time.time() < son:
        if not _yasiyor(pid):
            return True
        time.sleep(0.1)
    return False


def durdur(calisma: Path, sinyal: int = signal.SIGTERM) -> int:
    y = yollar(calisma)
    pid = _pid(y)
    if not _yasiyor(pid):
        print("alici zaten kapali")
        return 0
    os.kill(pid, sinyal)
    if not _bitis_bekle(pid, 60):
        print("HATA: alici kapanmadi", file=sys.stderr)
        return 1
    y["hazir"].unlink(missing_ok=True)
    print(f"alici {'durduruldu' if sinyal == signal.SIGTERM else 'olduruldu'} pid={pid}")
    return 0


def kod(calisma: Path) -> int:
    y = yollar(calisma)
    pid = _pid(y)
    if not _yasiyor(pid):
        print("HATA: alici calismiyor", file=sys.stderr)
        return 1
    onceki = y["kod"].stat().st_mtime_ns if y["kod"].exists() else 0
    os.kill(pid, signal.SIGUSR1)
    son = time.time() + 20
    while time.time() < son:
        if y["kod"].exists() and y["kod"].stat().st_mtime_ns != onceki:
            print(y["kod"].read_text().strip())
            return 0
        time.sleep(0.1)
    print("HATA: yeni kod uretilmedi", file=sys.stderr)
    return 1


def bekle_kismi(calisma: Path, en_az: int, sn: float) -> int:
    """Geçici .part dosyasının boyutu en_az'a ulaşınca (boyut hâlâ yazılırken) boyutu basar. Dosya hiç görünmezse 2."""
    gecici = yollar(calisma)["veri"] / "aktarim" / "gecici"
    son = time.time() + sn
    while time.time() < son:
        parcalar = list(gecici.rglob("*.part")) if gecici.exists() else []
        if parcalar:
            boy = max(p.stat().st_size for p in parcalar)
            if boy >= en_az:
                print(boy)
                return 0
        time.sleep(0.02)
    print("HATA: yukleme beklenen boyuta ulasmadi", file=sys.stderr)
    return 2


def dogrula(calisma: Path, beklenen: Path) -> int:
    """Beklenen: ilk satır {"cihaz_id": ...}; sonra satır başına {"id","tur","kategori","metin"}."""
    from kimlikcore import Hub
    from kimlikimport.base import stable_key

    y = yollar(calisma)
    satirlar = [json.loads(s) for s in beklenen.read_text(encoding="utf-8").split("\n") if s.strip()]
    cihaz = satirlar[0]["cihaz_id"]
    kayitlar = satirlar[1:]
    ids = [k["id"] for k in kayitlar]
    hatalar: list[str] = []
    if len(set(ids)) != len(ids):
        hatalar.append("beklenen dosyada yinelenen kimlik")
    beklenen_harita = {stable_key("android", cihaz, k["id"]): k for k in kayitlar}
    hub = Hub.open(y["veri"], write=False)
    try:
        satir = hub.query("SELECT event_key, kind, category, text, device_id, onem, hassas_konu FROM events "
                          "WHERE kind LIKE 'android.%'")
        gelen_say = len(satir)
        tum = hub.query("SELECT COUNT(*) FROM events")[0][0]
    finally:
        hub.close()
    gorulen: dict[str, tuple] = {}
    for s in satir:
        if s[0] in gorulen:
            hatalar.append(f"yinelenen olay anahtari {s[0][:12]}")
        gorulen[s[0]] = s
    eksik = [k for k in beklenen_harita if k not in gorulen]
    fazla = [k for k in gorulen if k not in beklenen_harita]
    if eksik:
        hatalar.append(f"EKSIK olay: {len(eksik)} (ilk: {beklenen_harita[eksik[0]]['id']})")
    if fazla:
        hatalar.append(f"FAZLA olay: {len(fazla)}")
    if gelen_say != len(kayitlar):
        hatalar.append(f"olay sayisi {gelen_say} != beklenen {len(kayitlar)}")
    metin_sapma = tur_sapma = kat_sapma = cihaz_sapma = onem_sapma = 0
    for anahtar, k in beklenen_harita.items():
        s = gorulen.get(anahtar)
        if s is None:
            continue
        _, kind, kategori, metin, device_id, onem, hassas = s
        if metin != k["metin"]:
            metin_sapma += 1
            if metin_sapma == 1:
                hatalar.append(f"METIN farki ornek: id={k['id']} beklenen={k['metin'][:60]!r} gercek={metin[:60]!r}")
        if kind != "android." + k["tur"]:
            tur_sapma += 1
        if kategori != k["kategori"]:
            kat_sapma += 1
        if device_id != cihaz:
            cihaz_sapma += 1
        if onem != (2 if k["kategori"] == "notlar" else 1):
            onem_sapma += 1
    for ad, n in (("metin", metin_sapma), ("tur", tur_sapma), ("kategori", kat_sapma), ("device_id", cihaz_sapma),
                  ("onem", onem_sapma)):
        if n:
            hatalar.append(f"{ad} sapmasi: {n} olay")
    for p in (y["veri"] / "gelen_aktarim").rglob("*.jsonl") if (y["veri"] / "gelen_aktarim").exists() else []:
        hatalar.append(f"gelen_aktarim'da ice alinmamis dosya: {p.name}")
    print(f"DOGRULA beklenen={len(kayitlar)} veritabani_android={gelen_say} veritabani_toplam={tum} "
          f"eksik={len(eksik)} fazla={len(fazla)} metin_sapma={metin_sapma} tur_sapma={tur_sapma} "
          f"kategori_sapma={kat_sapma} device_id_sapma={cihaz_sapma} onem_sapma={onem_sapma}")
    for h in hatalar:
        print("HATA:", h)
    print("DOGRULA " + ("TAMAM" if not hatalar else "BASARISIZ"))
    return 0 if not hatalar else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("komut", choices=["baslat", "durdur", "oldur", "kod", "dogrula", "bekle-kismi", "calis"])
    ap.add_argument("--calisma", required=True, type=Path)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--beklenen", type=Path)
    ap.add_argument("--en-az", type=int, default=1)
    ap.add_argument("--sure", type=float, default=60.0)
    a = ap.parse_args()
    if a.komut == "calis":
        return calis(a.calisma, a.port)
    if a.komut == "baslat":
        return baslat(a.calisma, a.port)
    if a.komut == "durdur":
        return durdur(a.calisma)
    if a.komut == "oldur":
        return durdur(a.calisma, signal.SIGKILL)
    if a.komut == "kod":
        return kod(a.calisma)
    if a.komut == "bekle-kismi":
        return bekle_kismi(a.calisma, a.en_az, a.sure)
    if a.komut == "dogrula":
        return dogrula(a.calisma, a.beklenen)
    return 2


if __name__ == "__main__":
    sys.exit(main())
