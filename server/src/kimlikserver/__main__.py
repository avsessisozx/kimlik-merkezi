"""Yönetim komutu (Windows uygulaması gelene kadar): `python -m kimlikserver ...`.

Anahtar üretir/iptal eder, izin verir. Yazan süreç olarak çalışır (hub.lock alır); Windows
uygulaması açıkken `HubLockedError` verir. Düz anahtar yalnızca `anahtar-uret` çıktısında görünür.
"""
from __future__ import annotations

import argparse
import sys

from kimlikcore import Category, Hub, KimlikError

from .access import KeyManager


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m kimlikserver")
    p.add_argument("--veri", required=True, help="veri klasörü")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("anahtar-uret", help="uygulama için yeni anahtar üretir (bir kez gösterilir)")
    a.add_argument("--ad", required=True)
    a.add_argument("--izin", action="append", default=[], metavar="KATEGORI",
                   help="kategori izni (tekrarlanabilir); hassaslar için ayrıca --hassas-onay")
    a.add_argument("--hassas-onay", action="store_true",
                   help="--izin ile verilen hassas kategoriler (eposta, mesaj, konum) için onay")
    a.add_argument("--bitis", help="izin bitişi, ISO-8601 (ör. 2026-12-01T00:00:00Z)")
    i = sub.add_parser("anahtar-iptal")
    i.add_argument("--app-id", required=True)
    sub.add_parser("liste")
    args = p.parse_args(argv)
    try:
        with Hub.open(args.veri, write=True) as hub:
            km = KeyManager(hub)
            if args.cmd == "anahtar-uret":
                app_id, plain = km.create_key(args.ad)
                for cat in args.izin:
                    km.grant(app_id, cat, expires_at=args.bitis,
                             confirmed_sensitive=args.hassas_onay and cat in Category.SENSITIVE)
                print(f"app_id: {app_id}")
                print(f"anahtar: {plain}")
                print("Bu anahtar bir daha gösterilmez.", file=sys.stderr)
            elif args.cmd == "anahtar-iptal":
                km.revoke_key(args.app_id)
                print("İptal edildi.")
            else:
                for app_id, name, created, revoked in km.list_keys():
                    cats = ",".join(g.category for g in km.list_grants(app_id)) or "-"
                    print(f"{app_id}\t{name}\t{created}\t{'IPTAL' if revoked else 'aktif'}\t{cats}")
    except KimlikError as e:
        print(f"Hata: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
