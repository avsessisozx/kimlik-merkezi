"""app.ico üretir (Pillow). Derlemeden önce çalıştırılır."""
from pathlib import Path

import sys as _sys
for _akis in (_sys.stdout, _sys.stderr):    # Windows konsolu (cp1252) Türkçe harfte çökmesin
    try:
        _akis.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


from kimlikwin.tepsi import simge_olustur

hedef = Path(__file__).with_name("app.ico")
simge_olustur(256).save(hedef, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("yazıldı:", hedef, hedef.stat().st_size, "bayt")
