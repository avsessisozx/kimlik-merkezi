"""Test sertifikası üretimi: stdlib sertifika üretemez; openssl komut satırı aranır.
(Ölçüm bulgusu: gerçek uygulama için PC tarafında sertifika üretimi ayrı bir bağımlılık/araç ister.)"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ADAYLAR = [
    r"C:\Program Files\Git\usr\bin\openssl.exe",
    r"C:\Program Files\Git\mingw64\bin\openssl.exe",
    r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe",
]

CNF = """[req]
distinguished_name=dn
x509_extensions=v3
prompt=no
[dn]
CN=localhost
[v3]
subjectAltName=IP:127.0.0.1,DNS:localhost
"""


def openssl_bul() -> str:
    b = shutil.which("openssl")
    if b:
        return b
    for a in ADAYLAR:
        if os.path.exists(a):
            return a
    raise FileNotFoundError("openssl bulunamadı")


def uret(dizin: Path, ad: str) -> tuple[str, str]:
    dizin = Path(dizin)
    dizin.mkdir(parents=True, exist_ok=True)
    cnf = dizin / f"{ad}.cnf"
    cnf.write_text(CNF)
    sert, anahtar = dizin / f"{ad}.pem", dizin / f"{ad}.key"
    subprocess.run([openssl_bul(), "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
                    "-nodes", "-days", "2", "-config", str(cnf), "-keyout", str(anahtar), "-out", str(sert)],
                   check=True, capture_output=True)
    return str(sert), str(anahtar)
