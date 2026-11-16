"""PC'de içe alma (docs/AKTARIM.md §4): `gelen_aktarim/` altındaki tamamlanmış dosyaları `android_giden`
içe aktarıcısıyla alır. YAZAN Hub'ın sahibi (Windows uygulaması) kendi iş parçacığında çağırır; alıcı iş
parçacığı bunu çağırmaz (alıcı yalnız `tamamlandi(yol)` geri çağrısıyla haber verir).
"""
from __future__ import annotations

import logging
from pathlib import Path

from .alici import GELEN_KLASOR, UUID_DOSYA_RE

_log = logging.getLogger("kimlikserver.aktarim")


def gelenleri_ice_al(hub, klasor: Path | str | None = None) -> dict[str, int]:
    """{"dosya": içe alınıp kaldırılan dosya, "yeni": eklenen olay, "yinelenen": zaten var olan olay,
    "eksik": alınamayıp yerinde bırakılan dosya}. Hata olan dosya silinmez; sonraki çağrıda yeniden denenir."""
    from kimlikimport.run import run   # içe aktarıcılar paketi yalnız burada gerekir

    kok = Path(klasor) if klasor is not None else Path(hub.root) / GELEN_KLASOR
    sonuc = {"dosya": 0, "yeni": 0, "yinelenen": 0, "eksik": 0}
    if not kok.is_dir():
        return sonuc
    for cihaz_dizin in sorted(p for p in kok.iterdir() if p.is_dir()):
        for yol in sorted(cihaz_dizin.glob("*.jsonl")):
            if not UUID_DOSYA_RE.fullmatch(yol.name):
                continue
            try:
                r = run(hub, yol, "android_giden")
            except Exception as e:  # noqa: BLE001 - dosya yerinde kalır, sayılır
                sonuc["eksik"] += 1
                _log.warning("içe alınamadı: %s/%s (%s)", cihaz_dizin.name, yol.name, type(e).__name__)
                continue
            try:
                yol.unlink()
            except OSError:
                sonuc["eksik"] += 1
                continue
            sonuc["dosya"] += 1
            sonuc["yeni"] += r.added
            sonuc["yinelenen"] += r.duplicate
        try:
            cihaz_dizin.rmdir()     # boşsa kaldır
        except OSError:
            pass
    return sonuc
