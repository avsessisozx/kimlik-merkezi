"""Syncthing ölçümü için yardımcılar: iki örnek ("telefon", "pc"), REST istemcisi, kill/yeniden başlatma."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


def bos_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def ikili() -> str | None:
    yol = os.environ.get("SYNCTHING_BIN")
    return yol if yol and os.path.exists(yol) else None


def bekle(kosul, sure=60.0, aralik=0.2):
    bitis = time.time() + sure
    son = None
    while time.time() < bitis:
        try:
            son = kosul()
        except Exception:  # noqa: BLE001
            son = None
        if son:
            return son
        time.sleep(aralik)
    return None


class Ornek:
    def __init__(self, ad: str, kok: Path, bin_yolu: str):
        self.ad, self.kok, self.bin = ad, Path(kok), bin_yolu
        self.home = self.kok / "home"
        self.klasor = self.kok / "veri"
        self.gui_port, self.dinle_port = bos_port(), bos_port()
        self.apikey = f"anahtar-{ad}-{self.gui_port}"
        self.p: subprocess.Popen | None = None
        self.log = None
        self.id = None
        self.baslangic_s = None

    # --- yapılandırma dosyası (başlamadan önce)
    def uret(self, secenekler: dict | None = None):
        self.klasor.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([self.bin, "generate", "--home", str(self.home)], capture_output=True, text=True,
                           timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        self.xml_duzenle(secenekler)

    def xml_duzenle(self, secenekler: dict | None = None):
        yol = self.home / "config.xml"
        agac = ET.parse(yol)
        kok = agac.getroot()
        for f in kok.findall("folder"):
            kok.remove(f)
        gui = kok.find("gui")
        for ad, deger in (("address", f"127.0.0.1:{self.gui_port}"), ("apikey", self.apikey)):
            e = gui.find(ad)
            if e is None:
                e = ET.SubElement(gui, ad)
            e.text = deger
        gui.set("tls", "false")
        o = kok.find("options")
        for e in o.findall("listenAddress"):
            o.remove(e)
        ET.SubElement(o, "listenAddress").text = f"tcp://127.0.0.1:{self.dinle_port}"
        varsayilan = {"globalAnnounceEnabled": "false", "localAnnounceEnabled": "false", "relaysEnabled": "false",
                      "natEnabled": "false", "urAccepted": "-1", "startBrowser": "false",
                      "autoUpgradeIntervalH": "0", "crashReportingEnabled": "false"}
        varsayilan.update({k: str(v) for k, v in (secenekler or {}).items()})
        for k, v in varsayilan.items():
            e = o.find(k)
            if e is None:
                e = ET.SubElement(o, k)
            e.text = v
        agac.write(yol, encoding="utf-8", xml_declaration=True)

    # --- süreç
    def baslat(self):
        env = dict(os.environ, STNORESTART="1", STNOUPGRADE="1", STNODEFAULTFOLDER="1", STHASHING="standard")
        self.log = open(self.kok / f"{self.ad}.log", "ab")
        self.p = subprocess.Popen([self.bin, "serve", "--home", str(self.home), "--no-browser", "--no-upgrade"],
                                  stdout=self.log, stderr=subprocess.STDOUT, env=env)
        t0 = time.perf_counter()
        assert bekle(lambda: self.rest("GET", "/rest/system/ping"), 90), self.gunluk_son()
        self.baslangic_s = time.perf_counter() - t0
        self.id = self.rest("GET", "/rest/system/status")["myID"]

    def gunluk_son(self, n=2000):
        try:
            return (self.kok / f"{self.ad}.log").read_text(errors="replace")[-n:]
        except OSError:
            return ""

    def ping(self) -> bool:
        try:
            self.rest("GET", "/rest/system/ping")
            return True
        except Exception:  # noqa: BLE001
            return False

    def oldur(self):
        if self.p and self.p.poll() is None:
            if os.name == "nt":  # süreç ağacı: izleyici/çocuk süreç hayatta kalmasın
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.p.pid)], capture_output=True)
            self.p.kill()
            self.p.wait()
            bekle(lambda: not self.ping(), 15, 0.2)
        if self.log:
            self.log.close()
            self.log = None

    def calisiyor(self):
        return self.p is not None and self.p.poll() is None

    # --- REST
    def rest(self, yontem, yol, govde=None):
        veri = None if govde is None else json.dumps(govde).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.gui_port}{yol}", data=veri, method=yontem,
                                     headers={"X-API-Key": self.apikey, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as y:
            b = y.read()
        return json.loads(b) if b.strip().startswith((b"{", b"[")) else (b.decode() or True)

    def cihaz_ekle(self, diger: "Ornek", **ek):
        try:
            sablon = self.rest("GET", "/rest/config/defaults/device")
        except Exception:  # noqa: BLE001
            sablon = {}
        sablon.update({"deviceID": diger.id, "name": diger.ad, "addresses": [f"tcp://127.0.0.1:{diger.dinle_port}"],
                       "autoAcceptFolders": False, "paused": False})
        sablon.update(ek)
        self.rest("PUT", f"/rest/config/devices/{diger.id}", sablon)

    def klasor_ekle(self, kimlik: str, tur: str, diger: "Ornek", yol: Path | None = None, **ek):
        try:
            sablon = self.rest("GET", "/rest/config/defaults/folder")
        except Exception:  # noqa: BLE001
            sablon = {}
        sablon.update({"id": kimlik, "label": kimlik, "path": str(yol or self.klasor), "type": tur,
                       "devices": [{"deviceID": self.id}, {"deviceID": diger.id}],
                       "fsWatcherEnabled": False, "rescanIntervalS": 3600})
        sablon.update(ek)
        self.rest("PUT", f"/rest/config/folders/{kimlik}", sablon)

    def tara(self, kimlik: str):
        self.rest("POST", f"/rest/db/scan?folder={kimlik}")

    def db(self, kimlik: str) -> dict:
        return self.rest("GET", f"/rest/db/status?folder={kimlik}")

    def gelen_bayt(self) -> int:
        c = self.rest("GET", "/rest/system/connections")
        return sum(v.get("inBytesTotal", 0) for v in c["connections"].values())

    def bagli(self) -> bool:
        c = self.rest("GET", "/rest/system/connections")["connections"]
        return any(v.get("connected") for v in c.values())


class Cift:
    """telefon (sendonly) + pc (receiveonly) örnekleri."""

    def __init__(self, kok: Path, bin_yolu: str, klasor_id="giden-kutusu", pc_secenek=None, pc_klasor_ek=None):
        self.kok = Path(kok)
        self.kid = klasor_id
        self.tel = Ornek("telefon", self.kok / "telefon", bin_yolu)
        self.pc = Ornek("pc", self.kok / "pc", bin_yolu)
        self.pc_secenek = pc_secenek
        self.pc_klasor_ek = pc_klasor_ek or {}

    def hazirla(self):
        self.tel.uret()
        self.pc.uret(self.pc_secenek)
        for o in (self.tel, self.pc):
            o.klasor.mkdir(parents=True, exist_ok=True)
            (o.klasor / ".stfolder").mkdir(exist_ok=True)
            o.baslat()
        self.tel.cihaz_ekle(self.pc)
        self.pc.cihaz_ekle(self.tel)
        self.tel.klasor_ekle(self.kid, "sendonly", self.pc)
        self.pc.klasor_ekle(self.kid, "receiveonly", self.tel, **self.pc_klasor_ek)
        return self

    def bagla(self, sure=60):
        assert bekle(lambda: self.tel.bagli() and self.pc.bagli(), sure), "cihazlar bağlanmadı\n" + \
            self.tel.gunluk_son(800) + self.pc.gunluk_son(800)

    def bitir(self):
        self.tel.oldur()
        self.pc.oldur()


def esitlendi(pc: Ornek, kimlik: str, beklenen_dosya: int, sure=120):
    def k():
        d = pc.db(kimlik)
        return d["state"] == "idle" and d["localFiles"] >= beklenen_dosya and d["needFiles"] == 0 and d
    return bekle(k, sure, 0.3)
