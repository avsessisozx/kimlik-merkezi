"""Yerel web sunucusu: YALNIZ 127.0.0.1. Dış ağa açılmaz.

Savunmalar: (1) 127.0.0.1'e bağlanır; (2) Host başlığı 127.0.0.1/localhost:<port> olmalı
(DNS yeniden bağlama); (3) /api çağrıları her oturum için rastgele üretilen jetonu ister ve
Origin varsa aynı kaynak olmalı (başka sitenin sayfasından istek atılamaz)."""
from __future__ import annotations

import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any

from kimlikcore import FormatError, HubLockedError, KimlikError

from . import gunluk
from .cekirdek import IslemHatasi
from .yonetici import Yonetici

ADRES = "127.0.0.1"
MAKS_GOVDE = 1_000_000


def _statik(ad: str) -> bytes:
    return resources.files("kimlikwin").joinpath("statik", ad).read_bytes()


class Sunucu:
    def __init__(self, yonetici: Yonetici, port: int = 0):
        self.yonetici = yonetici
        self.jeton = secrets.token_urlsafe(32)
        self.httpd = self._bagla(port)
        self.port = self.httpd.server_address[1]
        self.httpd.sunucu = self  # type: ignore[attr-defined]
        self._is_parcacigi: threading.Thread | None = None

    @staticmethod
    def _bagla(port: int) -> ThreadingHTTPServer:
        for p in ([port] if port else []) + [0]:
            try:
                return ThreadingHTTPServer((ADRES, p), _Isleyici)
            except OSError:
                continue
        raise OSError("Yerel bir port açılamadı.")

    @property
    def url(self) -> str:
        return f"http://{ADRES}:{self.port}/"

    def baslat(self) -> None:
        self._is_parcacigi = threading.Thread(target=self.httpd.serve_forever, daemon=True, name="web")
        self._is_parcacigi.start()

    def durdur(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class _Isleyici(BaseHTTPRequestHandler):
    server_version = "KimlikMerkezi"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # erişim günlüğü yok (yol/içerik sızmasın)
        pass

    @property
    def sunucu(self) -> Sunucu:
        return self.server.sunucu  # type: ignore[attr-defined]

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host in (f"{ADRES}:{self.sunucu.port}", f"localhost:{self.sunucu.port}")

    def _yanit(self, kod: int, govde: bytes, tur: str = "application/json; charset=utf-8") -> None:
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(govde)

    def _json(self, kod: int, nesne: Any) -> None:
        self._yanit(kod, json.dumps(nesne, ensure_ascii=False).encode("utf-8"))

    def do_GET(self) -> None:
        if not self._host_ok():
            return self._json(403, {"hata": "Geçersiz Host."})
        if self.path == "/saglik":
            return self._json(200, {"ok": True, "uygulama": "kimlik-merkezi"})
        if self.path in ("/", "/index.html"):
            html = _statik("index.html").decode("utf-8").replace("__JETON__", self.sunucu.jeton)
            return self._yanit(200, html.encode("utf-8"), "text/html; charset=utf-8")
        self._json(404, {"hata": "Bulunamadı."})

    def do_POST(self) -> None:
        if not self._host_ok():
            return self._json(403, {"hata": "Geçersiz Host."})
        if not self.path.startswith("/api/"):
            return self._json(404, {"hata": "Bulunamadı."})
        if not secrets.compare_digest(self.headers.get("X-Kimlik-Jeton", ""), self.sunucu.jeton):
            return self._json(403, {"hata": "Yetkisiz istek."})
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://{ADRES}:{self.sunucu.port}", f"http://localhost:{self.sunucu.port}"):
            return self._json(403, {"hata": "Yetkisiz kaynak."})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0 or n > MAKS_GOVDE:
            return self._json(413, {"hata": "İstek çok büyük."})
        try:
            girdi = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(girdi, dict):
                raise ValueError
        except ValueError:
            return self._json(400, {"hata": "Geçersiz JSON."})
        ad = self.path[5:]
        try:
            self._json(200, self.sunucu.yonetici.api(ad, girdi))
        except IslemHatasi as e:
            self._json(409 if e.kod in ("sihirbaz_gerekli", "mesgul") else 400,
                       {"hata": str(e), "kod": e.kod, "ek": e.ek})
        except HubLockedError as e:
            self._json(409, {"hata": str(e), "kod": "kilitli"})
        except (KimlikError, FormatError, ValueError, TypeError) as e:
            self._json(400, {"hata": f"{e}" if isinstance(e, (KimlikError, ValueError)) else "Geçersiz istek.",
                             "kod": type(e).__name__})
        except Exception as e:
            gunluk.log().error("api/%s beklenmeyen hata: %s", ad, type(e).__name__)
            self._json(500, {"hata": f"Beklenmeyen hata: {type(e).__name__}", "kod": "beklenmeyen"})


def port_bos_mu(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind((ADRES, port))
            return True
        except OSError:
            return False
