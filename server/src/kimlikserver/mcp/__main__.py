"""Başlatma girişi: `python -m kimlikserver.mcp` (stdio).

Ortam: KIMLIK_ANAHTAR (uygulamanın anahtarı), KIMLIK_VERI (veri klasörü).
stdout yalnızca MCP iletişimine ayrılmıştır; günlük stderr'e gider, kayıt içeriği taşımaz.
"""
from __future__ import annotations

import logging
import os
import sys

from ..service import QueryService
from .server import build_server


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING,
                        format="kimlikserver %(levelname)s %(message)s")
    veri = os.environ.get("KIMLIK_VERI", "").strip()
    if not veri:
        print("KIMLIK_VERI (veri klasörü) tanımlı değil.", file=sys.stderr)
        return 2
    # Anahtar yoksa süreç yine başlar; her araç çağrısı 'reddedildi' ile döner ve kayda girer.
    service = QueryService(veri, os.environ.get("KIMLIK_ANAHTAR") or None)
    build_server(service).run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
