"""UDP bulma yanıtlayıcısı (docs/AKTARIM.md §3): `KM1?<parmak izi ilk 16 hex>` -> `KM1!<port>`.

Yanlış parmak izine ve yerel olmayan kaynak adreslere yanıt verilmez. Alıcıyla birlikte başlar/durur.
"""
from __future__ import annotations

import logging
import socket
import threading

from .eslestirme import yerel_adres_mi

BULMA_PORTU = 47822
_log = logging.getLogger("kimlikserver.aktarim")


class Bulma:
    def __init__(self, parmak_izi: str, tcp_port_al, port: int = BULMA_PORTU, adres: str = "0.0.0.0",
                 yalniz_yerel: bool = True):
        self._beklenen = b"KM1?" + parmak_izi[:16].lower().encode("ascii")
        self._tcp_port_al = tcp_port_al
        self._adres, self._port, self._yalniz_yerel = adres, port, yalniz_yerel
        self._soket: socket.socket | None = None
        self._iplik: threading.Thread | None = None
        self._dur = threading.Event()
        self.port = 0

    def baslat(self) -> bool:
        """Dinlemeye başlar; port kullanımdaysa False (alıcı yine de çalışır)."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind((self._adres, self._port))
        except OSError as e:
            s.close()
            _log.warning("bulma yanıtlayıcısı başlatılamadı (%s)", type(e).__name__)
            return False
        s.settimeout(0.3)
        self._soket, self.port = s, s.getsockname()[1]
        self._dur.clear()
        self._iplik = threading.Thread(target=self._dongu, name="aktarim-bulma", daemon=True)
        self._iplik.start()
        return True

    def _dongu(self) -> None:
        s = self._soket
        while not self._dur.is_set():
            try:
                veri, kaynak = s.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                return
            if veri.strip() != self._beklenen:
                continue
            if self._yalniz_yerel and not yerel_adres_mi(kaynak[0]):
                continue
            try:
                s.sendto(b"KM1!" + str(self._tcp_port_al()).encode("ascii"), kaynak)
            except OSError:
                pass

    def durdur(self) -> None:
        self._dur.set()
        if self._soket is not None:
            try:
                self._soket.close()
            except OSError:
                pass
        if self._iplik is not None:
            self._iplik.join(timeout=2)
        self._soket = self._iplik = None
