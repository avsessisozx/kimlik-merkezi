"""Tepsi simgesi (pystray; isteğe bağlı bağımlılık). Menü: Aç, Girişte başlat, Çıkış."""
from __future__ import annotations

from collections.abc import Callable

from . import APP_AD


def simge_olustur(boyut: int = 64):
    """Pillow ile basit simge: koyu daire içinde 'K'. (Dosya gerekmez.)"""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (boyut, boyut), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((2, 2, boyut - 2, boyut - 2), fill=(33, 76, 140, 255))
    k = boyut // 4
    d.rectangle((k + 2, k, k + 8, boyut - k), fill="white")
    d.polygon([(k + 8, boyut // 2), (boyut - k, k), (boyut - k - 10, k), (k + 8, boyut // 2 - 2)], fill="white")
    d.polygon([(k + 8, boyut // 2), (boyut - k, boyut - k), (boyut - k - 10, boyut - k)], fill="white")
    return im


class Tepsi:
    def __init__(self, ac: Callable[[], None], cik: Callable[[], None],
                 oto_oku: Callable[[], bool], oto_yaz: Callable[[bool], None]):
        import pystray
        self._pystray = pystray
        m = pystray.MenuItem
        menu = pystray.Menu(
            m("Aç", lambda *_: ac(), default=True),
            m("Girişte otomatik başlat", lambda *_: oto_yaz(not oto_oku()), checked=lambda *_: oto_oku()),
            m("Çıkış", lambda *_: cik()),
        )
        self.simge = pystray.Icon("KimlikMerkezi", simge_olustur(), APP_AD, menu)

    def calistir(self) -> None:
        self.simge.run()          # ana iş parçacığını tutar

    def durdur(self) -> None:
        self.simge.stop()
