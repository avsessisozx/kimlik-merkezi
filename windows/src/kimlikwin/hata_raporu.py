"""Kopyalanabilir hata raporu (GOREV 4.6): sürüm, sistem, adım, hata, son 50 günlük satırı,
doğrulama durumu. Kayıt (veri) içeriği içermez; kullanıcı klasör adı %KULLANICI% ile maskelenir."""
from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import kimlikcore

from . import __version__, gunluk


def _maske(s: str) -> str:
    ev = str(Path.home())
    s = s.replace(ev, "%KULLANICI%")
    return s.replace(ev.replace("\\", "/"), "%KULLANICI%")


def olustur(adim: str = "", hata: BaseException | None = None, dogrulama: str | None = None,
            ek: str | None = None, ayar_dizin: Path | None = None) -> str:
    L = [
        "Kimlik Merkezi hata raporu",
        f"Zaman: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"Sürüm: kimlikwin {__version__}, kimlikcore {kimlikcore.__version__}",
        f"Python: {platform.python_version()} ({'paketlenmiş' if getattr(sys, 'frozen', False) else 'kaynak'})",
        f"Sistem: {platform.system()} {platform.release()} {platform.version()} {platform.machine()}",
        f"Adım: {adim or '(belirtilmedi)'}",
    ]
    if hata is not None:
        L.append(f"Hata: {type(hata).__name__}: {hata}")
    else:
        L.append("Hata: (yok)")
    L.append(f"Doğrulama: {dogrulama or 'çalıştırılmadı'}")
    if ek:
        L += ["Ek bilgi:", ek]
    satirlar = gunluk.son_satirlar(50, ayar_dizin)
    L.append(f"Son {len(satirlar)} günlük satırı:")
    L += [f"  {s}" for s in satirlar] or ["  (günlük boş)"]
    return _maske("\n".join(L))
