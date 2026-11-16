"""Telefonu taklit eden istemci (stdlib). Durumsuz: her dosya için alıcıya "kaç baytım var" diye sorar."""
from __future__ import annotations

import hashlib
import http.client
import re
import socket
import ssl
import sys
import time
from pathlib import Path

UUID_DOSYA = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.jsonl$")


class Yetkisiz(Exception):
    pass


class ParmakIziUyusmadi(Exception):
    """Sertifika parmak izi sabitlemesi tutmadı; hiçbir istek gönderilmedi."""


class _SabitBaglanti(http.client.HTTPSConnection):
    def __init__(self, host, port, pin, timeout):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # güven kökü yok; yerine parmak izi sabitleme
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        super().__init__(host, port, timeout=timeout, context=ctx)
        self._pin = pin.lower().replace(":", "")

    def connect(self):
        super().connect()
        der = self.sock.getpeercert(binary_form=True)
        if hashlib.sha256(der).hexdigest() != self._pin:
            self.sock.close()
            self.sock = None
            raise ParmakIziUyusmadi("sertifika parmak izi uyuşmuyor")


def parmak_izi(pem_yolu) -> str:
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(Path(pem_yolu).read_text())).hexdigest()


class Istemci:
    def __init__(self, host, port, anahtar, pin, parca_bayt=256 * 1024, parca_arasi_s=0.0, zaman_asimi=15):
        self.host, self.port, self.anahtar, self.pin = host, port, anahtar, pin
        self.parca_bayt, self.parca_arasi_s, self.zaman_asimi = parca_bayt, parca_arasi_s, zaman_asimi
        self._bag: _SabitBaglanti | None = None
        self.istek_sayisi = 0

    def _istek(self, yontem, yol, basliklar=None, govde=None):
        basliklar = dict(basliklar or {})
        if self.anahtar is not None:
            basliklar["Authorization"] = f"Bearer {self.anahtar}"
        for deneme in (0, 1):  # keep-alive bağlantı kopmuşsa bir kez yeniden bağlan
            if self._bag is None:
                self._bag = _SabitBaglanti(self.host, self.port, self.pin, self.zaman_asimi)
            try:
                self.istek_sayisi += 1
                self._bag.request(yontem, yol, body=govde, headers=basliklar)
                yanit = self._bag.getresponse()
                yanit.read()
                if yanit.status == 401:
                    self.kapat()
                    raise Yetkisiz("401")
                return yanit
            except (http.client.HTTPException, ConnectionError, ssl.SSLError, socket.timeout, OSError) as e:
                self.kapat()
                if isinstance(e, (Yetkisiz, ParmakIziUyusmadi)) or deneme == 1:
                    raise
        raise AssertionError("ulaşılmaz")

    def kapat(self):
        if self._bag is not None:
            try:
                self._bag.close()
            finally:
                self._bag = None

    def durum(self, cihaz, ad):
        y = self._istek("HEAD", f"/{cihaz}/{ad}")
        return y.getheader("X-Durum"), int(y.getheader("X-Alinan") or 0)

    def dosya_gonder(self, yol: Path, cihaz: str) -> dict:
        """Tek dosyayı gönderir/sürdürür. {'sonuc','baslangic_ofset','gonderilen_bayt'} döner."""
        yol = Path(yol)
        ad = yol.name
        toplam = yol.stat().st_size
        h = hashlib.sha256()
        with open(yol, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        sha = h.hexdigest()
        durum, ofset = self.durum(cihaz, ad)
        if durum == "var":
            return {"sonuc": "var", "baslangic_ofset": ofset, "gonderilen_bayt": 0, "ilk_durum": durum}
        bas0, gonderilen = ofset, 0
        with open(yol, "rb") as f:
            while True:
                f.seek(ofset)
                parca = f.read(self.parca_bayt)
                son = ofset + len(parca) - 1
                y = self._istek("PUT", f"/{cihaz}/{ad}", {
                    "Content-Range": f"bytes {ofset}-{son}/{toplam}" if parca else f"bytes */{toplam}",
                    "X-Sha256": sha, "Content-Length": str(len(parca)),
                    "Content-Type": "application/octet-stream"}, parca)
                if y.status in (200, 201):
                    gonderilen += len(parca)
                    if y.getheader("X-Durum") == "var":
                        return {"sonuc": "var", "baslangic_ofset": bas0, "gonderilen_bayt": gonderilen, "ilk_durum": durum}
                    ofset += len(parca)
                    if y.status == 201:
                        return {"sonuc": "tamam", "baslangic_ofset": bas0, "gonderilen_bayt": gonderilen, "ilk_durum": durum}
                    if self.parca_arasi_s:
                        time.sleep(self.parca_arasi_s)
                elif y.status == 409:
                    ofset = int(y.getheader("X-Alinan"))
                elif y.status == 422:
                    return {"sonuc": "sha_hatasi", "baslangic_ofset": bas0, "gonderilen_bayt": gonderilen, "ilk_durum": durum}
                else:
                    raise RuntimeError(f"beklenmeyen durum {y.status}")

    def klasor_gonder(self, kok: Path, cihaz: str) -> dict:
        """Giden kutusundaki KAPALI (*.jsonl, UUID adlı) dosyaları gönderir. Bağlantı yoksa bekleyenleri sayar."""
        sonuc = {"tamam": 0, "var": 0, "bekleyen": 0, "hata": None, "gonderilen_bayt": 0}
        dosyalar = sorted(p for p in (Path(kok) / cihaz).glob("*.jsonl") if UUID_DOSYA.match(p.name))
        for i, p in enumerate(dosyalar):
            try:
                r = self.dosya_gonder(p, cihaz)
            except (ConnectionError, OSError, http.client.HTTPException, ssl.SSLError) as e:
                sonuc["bekleyen"] = len(dosyalar) - i
                sonuc["hata"] = type(e).__name__
                self.kapat()
                return sonuc
            if r["sonuc"] in ("tamam", "var"):
                sonuc[r["sonuc"]] += 1
            else:
                sonuc["hata"] = r["sonuc"]
            sonuc["gonderilen_bayt"] += r["gonderilen_bayt"]
        self.kapat()
        return sonuc

    def tekrarla(self, kok: Path, cihaz: str, sure_s: float, bekleme_s: float = 0.2) -> dict:
        """Bekleyen kalmayana (ya da süre dolana) dek klasor_gonder'i yineler."""
        bitis = time.time() + sure_s
        toplam = {"tamam": 0, "var": 0, "gonderilen_bayt": 0, "tur": 0}
        while time.time() < bitis:
            r = self.klasor_gonder(kok, cihaz)
            toplam["tur"] += 1
            toplam["tamam"] += r["tamam"]
            toplam["var"] += r["var"]
            toplam["gonderilen_bayt"] += r["gonderilen_bayt"]
            if r["bekleyen"] == 0 and r["hata"] is None:
                toplam["bitti"] = True
                return toplam
            time.sleep(bekleme_s)
        toplam["bitti"] = False
        return toplam


if __name__ == "__main__":  # istemci.py kok cihaz port anahtar pin parca_bayt parca_arasi_s
    kok, cihaz, port, anahtar, pin, pb, pa = sys.argv[1:8]
    c = Istemci("127.0.0.1", int(port), anahtar, pin, int(pb), float(pa))
    print("BASLADI", flush=True)
    print(c.tekrarla(Path(kok), cihaz, 120), flush=True)
