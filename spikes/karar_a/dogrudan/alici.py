"""Doğrudan HTTPS alıcı prototipi (yalnız stdlib).

Protokol:
  HEAD|GET /<cihaz_id>/<dosya_uuid>.jsonl      -> X-Durum: yok|kismi|var, X-Alinan: <bayt>
  PUT      /<cihaz_id>/<dosya_uuid>.jsonl      Content-Range: bytes <bas>-<son>/<toplam>
                                               X-Sha256: <tüm dosyanın sha256'sı>
      bas != alıcıdaki bayt  -> 409 (+X-Alinan)
      son parça + sha uyuşmaz-> 422, geçici dosya silinir
      son parça + sha uyar   -> fsync + os.replace ile gelen/ altına atomik taşıma, 201
      dosya zaten gelen/'de  -> 200 X-Durum: var (yazma yok)
Kimlik: Authorization: Bearer <ortak gizli anahtar> (sabit zamanlı karşılaştırma); yoksa/yanlışsa 401, bayt yazılmaz.
Ağ: yalnız RFC1918 + loopback istemci adresleri kabul edilir (yerel_adres_mi).
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import ssl
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

YOL_RE = re.compile(r"^/([A-Za-z0-9_-]{1,64})/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$")
RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
YEREL_AGLAR = [ipaddress.ip_network(n) for n in
               ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128")]


def yerel_adres_mi(adres: str) -> bool:
    try:
        ip = ipaddress.ip_address(adres.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip in ag for ag in YEREL_AGLAR if ag.version == ip.version)


class _Sunucu(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64

    def __init__(self, adres, kok: Path, anahtar: str, sertifika: str, ozel_anahtar: str,
                 yalniz_yerel: bool = True):
        self.kok = Path(kok)
        self.gelen = self.kok / "gelen"
        self.gecici = self.kok / "gecici"
        self.gelen.mkdir(parents=True, exist_ok=True)
        self.gecici.mkdir(parents=True, exist_ok=True)
        self.anahtar = anahtar.encode()
        self.yalniz_yerel = yalniz_yerel
        self.istek_sayisi = 0
        self.kilitler: dict[str, threading.Lock] = {}
        self.kilit_kilidi = threading.Lock()
        self.bag = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.bag.minimum_version = ssl.TLSVersion.TLSv1_2
        self.bag.load_cert_chain(sertifika, ozel_anahtar)
        super().__init__(adres, _Isleyici)

    def get_request(self):
        ham, adres = self.socket.accept()
        # el sıkışma iş parçacığında yapılır: yavaş/bozuk istemci kabul döngüsünü tutmaz
        return self.bag.wrap_socket(ham, server_side=True, do_handshake_on_connect=False), adres

    def verify_request(self, request, client_address):
        if self.yalniz_yerel and not yerel_adres_mi(client_address[0]):
            return False
        return True

    def handle_error(self, request, client_address):
        pass  # bozuk bağlantılar (kill, sertifika reddi) gürültü yapmasın

    def dosya_kilidi(self, anahtar: str) -> threading.Lock:
        with self.kilit_kilidi:
            return self.kilitler.setdefault(anahtar, threading.Lock())


class _Isleyici(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 60

    def setup(self):
        self.request.settimeout(30)
        self.request.do_handshake()
        super().setup()

    def log_message(self, *a):
        pass

    # --- yardımcılar
    def _cevap(self, kod, durum=None, alinan=None, govde=None, **ek):
        data = json.dumps(govde if govde is not None else {"durum": durum, "alinan": alinan}).encode()
        self.send_response(kod)
        if durum is not None:
            self.send_header("X-Durum", durum)
        if alinan is not None:
            self.send_header("X-Alinan", str(alinan))
        for k, v in ek.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _govdeyi_at(self):
        n = int(self.headers.get("Content-Length") or 0)
        while n > 0:
            n -= len(self.rfile.read(min(n, 1 << 20)))

    def _yetkili(self) -> bool:
        ver = self.headers.get("Authorization", "")
        if not ver.startswith("Bearer "):
            return False
        return hmac.compare_digest(ver[7:].encode(), self.server.anahtar)

    def _on_kontrol(self):
        self.server.istek_sayisi += 1
        if not self._yetkili():
            self.close_connection = True
            self._cevap(401, govde={"hata": "yetkisiz"}, Connection="close")
            return None
        m = YOL_RE.match(self.path)
        if not m:
            self._govdeyi_at()
            self._cevap(400, govde={"hata": "gecersiz yol"})
            return None
        return m.group(1), m.group(2)

    def _durum(self, cihaz, kimlik):
        son = self.server.gelen / cihaz / f"{kimlik}.jsonl"
        if son.exists():
            return "var", son.stat().st_size
        part = self.server.gecici / cihaz / f"{kimlik}.part"
        if part.exists():
            return "kismi", part.stat().st_size
        return "yok", 0

    # --- yöntemler
    def do_HEAD(self):
        k = self._on_kontrol()
        if k:
            d, n = self._durum(*k)
            self._cevap(200, d, n)

    do_GET = do_HEAD

    def do_PUT(self):
        # 401'de gövde okunmaz ve bağlantı kapatılır: hiçbir bayt diske gitmez
        if not self._yetkili():
            self.server.istek_sayisi += 1
            self.close_connection = True
            self._cevap(401, govde={"hata": "yetkisiz"}, Connection="close")
            return
        k = self._on_kontrol()
        if not k:
            return
        cihaz, kimlik = k
        srv = self.server
        with srv.dosya_kilidi(f"{cihaz}/{kimlik}"):
            m = RANGE_RE.match(self.headers.get("Content-Range", ""))
            uzunluk = int(self.headers.get("Content-Length") or 0)
            if not m:
                self._govdeyi_at()
                return self._cevap(400, govde={"hata": "Content-Range yok"})
            bas, son, toplam = map(int, m.groups())
            if son - bas + 1 != uzunluk or son >= toplam:
                self._govdeyi_at()
                return self._cevap(400, govde={"hata": "aralik tutarsiz"})
            durum, mevcut = self._durum(cihaz, kimlik)
            if durum == "var":
                self._govdeyi_at()
                return self._cevap(200, "var", mevcut)
            if bas != mevcut:
                self._govdeyi_at()
                return self._cevap(409, durum, mevcut)
            veri = self.rfile.read(uzunluk)  # yarım gövde = hiçbir şey yazılmaz
            if len(veri) != uzunluk:
                self.close_connection = True
                return
            (srv.gecici / cihaz).mkdir(parents=True, exist_ok=True)
            part = srv.gecici / cihaz / f"{kimlik}.part"
            with open(part, "ab") as f:
                f.write(veri)
                f.flush()
                os.fsync(f.fileno())
            yeni = bas + uzunluk
            if yeni < toplam:
                return self._cevap(200, "kismi", yeni)
            # tamamlandı: sha doğrula, atomik taşı
            h = hashlib.sha256()
            with open(part, "rb") as f:
                for b in iter(lambda: f.read(1 << 20), b""):
                    h.update(b)
            beklenen = self.headers.get("X-Sha256", "")
            if not hmac.compare_digest(h.hexdigest(), beklenen.lower()):
                part.unlink()
                return self._cevap(422, govde={"hata": "sha256 uyusmuyor", "alinan": 0})
            (srv.gelen / cihaz).mkdir(parents=True, exist_ok=True)
            os.replace(part, srv.gelen / cihaz / f"{kimlik}.jsonl")
            return self._cevap(201, "tamam", yeni)


class Alici:
    """Test/prototip için iş parçacığında çalışan alıcı."""

    def __init__(self, kok, anahtar, sertifika, ozel_anahtar, port=0, adres="127.0.0.1", yalniz_yerel=True):
        self.srv = _Sunucu((adres, port), kok, anahtar, sertifika, ozel_anahtar, yalniz_yerel)
        self.port = self.srv.server_address[1]
        self.iplik = threading.Thread(target=self.srv.serve_forever, daemon=True)

    def baslat(self):
        self.iplik.start()
        return self

    def durdur(self):
        self.srv.shutdown()
        self.srv.server_close()


if __name__ == "__main__":  # alt süreç olarak: alici.py kok port anahtar sertifika ozel_anahtar
    kok, port, anahtar, sert, ozel = sys.argv[1:6]
    a = Alici(kok, anahtar, sert, ozel, port=int(port))
    print(f"HAZIR {a.port}", flush=True)
    a.srv.serve_forever()
