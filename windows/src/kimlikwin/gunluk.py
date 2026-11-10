"""Günlük: ayar klasöründe döner dosya. Kayıt (veri) içeriği ASLA günlüğe yazılmaz."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from .yollar import ayar_dizini

AD = "kimlikwin"
_log = logging.getLogger(AD)


def kur(dizin: Path | None = None) -> Path:
    d = Path(dizin) if dizin else ayar_dizini()
    d.mkdir(parents=True, exist_ok=True)
    yol = d / "gunluk.log"
    for h in list(_log.handlers):
        _log.removeHandler(h)
        h.close()
    h = logging.handlers.RotatingFileHandler(yol, maxBytes=512_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _log.addHandler(h)
    _log.setLevel(logging.INFO)
    _log.propagate = False
    return yol


def son_satirlar(n: int = 50, dizin: Path | None = None) -> list[str]:
    yol = (Path(dizin) if dizin else ayar_dizini()) / "gunluk.log"
    try:
        return yol.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def log() -> logging.Logger:
    return _log
