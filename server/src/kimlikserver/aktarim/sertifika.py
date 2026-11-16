"""Alıcı sertifikası: kendinden imzalı, EC P-256, 10 yıl (docs/AKTARIM.md §3).

Veri klasöründe `aktarim/` altında durur: `sertifika.pem`, `anahtar.pem` (dosya izinleri yalnız sahibine).
Özel anahtar PEM'i rastgele bir parolayla şifrelenir ve parola işletim sistemi sağlayıcısıyla (Windows'ta DPAPI,
`kimlikcore.sifreleme.AnahtarSaglayici`) sarılır: `anahtar.parola.sarili`. Sağlayıcı yoksa (ör. Linux/CI)
özel anahtar veri klasöründe DÜZ durur; bu durum `Sertifika.anahtar_sarili == False` ile bildirilir.
Sağlayıcı sarılı parolayı açamazsa (veri klasörü başka hesaba taşındı) sertifika yeniden üretilir; telefonlar
yeni parmak izini görür ve yeniden eşleşmelidir.
"""
from __future__ import annotations

import datetime
import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

_log = logging.getLogger("kimlikserver.aktarim")
OTOMATIK = "otomatik"
GECERLILIK_YIL = 10


@dataclass(frozen=True, slots=True)
class Sertifika:
    sertifika_yolu: Path
    anahtar_yolu: Path
    parmak_izi: str          # sertifika DER'inin SHA-256'sı, küçük harf onaltılık
    anahtar_sarili: bool     # özel anahtar parolası sağlayıcıyla sarılı mı
    parola: bytes | None = field(repr=False)   # TLS bağlamını kurmak için (None: anahtar düz); günlüğe/repr'e girmez
    yeniden_uretildi: bool = False   # eski çift açılamadı/eşleşmedi: yenisi üretildi, telefonlar yeniden eşleşmeli


def parmak_izi_pem(pem: bytes) -> str:
    c = x509.load_pem_x509_certificate(pem)
    return hashlib.sha256(c.public_bytes(serialization.Encoding.DER)).hexdigest()


def _yaz_ozel(yol: Path, veri: bytes) -> None:
    gecici = yol.with_name(yol.name + ".yeni")
    fd = os.open(gecici, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(veri)
        f.flush()
        os.fsync(f.fileno())
    os.replace(gecici, yol)
    try:
        os.chmod(yol, 0o600)
    except OSError:  # pragma: no cover - dosya sistemi izin vermiyor
        pass


def uret(sertifika_yolu: Path, anahtar_yolu: Path, parola: bytes | None, *,
         ad: str = "Kimlik Merkezi", san_ip: list[str] | None = None) -> str:
    """Yeni anahtar + sertifika üretir ve çifti ATOMİK yazar: ikisi de önce geçici dosyaya, sonra replace
    (yarıda kalırsa eşleşmeyen çift açılışta `hazirla` tarafından yakalanır). Parmak izini döner."""
    import ipaddress

    anahtar = ec.generate_private_key(ec.SECP256R1())
    isim = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ad)])
    simdi = datetime.datetime.now(datetime.timezone.utc)
    yap = (
        x509.CertificateBuilder().subject_name(isim).issuer_name(isim).public_key(anahtar.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(simdi - datetime.timedelta(days=1))
        .not_valid_after(simdi + datetime.timedelta(days=365 * GECERLILIK_YIL + 3))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    )
    if san_ip:
        yap = yap.add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(a)) for a in san_ip]), critical=False)
    cert = yap.sign(anahtar, hashes.SHA256())
    sifre = (serialization.BestAvailableEncryption(parola) if parola else serialization.NoEncryption())
    anahtar_pem = anahtar.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, sifre)
    pem = cert.public_bytes(serialization.Encoding.PEM)
    g_anahtar, g_sert = anahtar_yolu.with_name(anahtar_yolu.name + ".yeni"), sertifika_yolu.with_name(sertifika_yolu.name + ".yeni")
    _yaz_gecici(g_anahtar, anahtar_pem)
    _yaz_gecici(g_sert, pem)
    os.replace(g_anahtar, anahtar_yolu)
    os.replace(g_sert, sertifika_yolu)
    return parmak_izi_pem(pem)


def _yaz_gecici(gecici: Path, veri: bytes) -> None:
    fd = os.open(gecici, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(veri)
        f.flush()
        os.fsync(f.fileno())


def _cift_gecerli(sert: Path, anahtar: Path, sarili: Path, saglayici):
    """Sertifika + anahtar eşleşiyor ve anahtar açılabiliyorsa parolayı (ya da None) döner; değilse istisna."""
    if sarili.is_file():
        if saglayici is None:
            raise ValueError("sağlayıcı yok")
        parola = saglayici.ac(sarili.read_bytes())
    else:
        parola = None
    ozel = serialization.load_pem_private_key(anahtar.read_bytes(), parola)
    c = x509.load_pem_x509_certificate(sert.read_bytes())
    ac = serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    if c.public_key().public_bytes(*ac) != ozel.public_key().public_bytes(*ac):
        raise ValueError("sertifika ile anahtar eşleşmiyor")
    return parola


def hazirla(veri_klasoru: Path | str, saglayici=OTOMATIK, *, ad: str = "Kimlik Merkezi",
            san_ip: list[str] | None = None) -> Sertifika:
    """`<veri>/aktarim/` altındaki sertifikayı döner; yoksa (ya da anahtarı açılamıyorsa) üretir.

    saglayici: OTOMATIK (kimlikcore.sifreleme.varsayilan_saglayici), None (düz) ya da AnahtarSaglayici.
    """
    dizin = Path(veri_klasoru) / "aktarim"
    dizin.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(dizin, 0o700)
    except OSError:  # pragma: no cover
        pass
    if saglayici == OTOMATIK:
        from kimlikcore import sifreleme

        saglayici = sifreleme.varsayilan_saglayici()
    sert, anahtar, sarili = dizin / "sertifika.pem", dizin / "anahtar.pem", dizin / "anahtar.parola.sarili"

    yeniden = False
    if sert.exists() or anahtar.exists() or sarili.exists():
        try:
            parola = _cift_gecerli(sert, anahtar, sarili, saglayici)
            return Sertifika(sert, anahtar, parmak_izi_pem(sert.read_bytes()), parola is not None, parola)
        except Exception:  # noqa: BLE001 - açılamayan/eşleşmeyen çift: SESSİZCE değil, eskiyi saklayıp yenile
            damga = time.strftime("%Y%m%dT%H%M%S")
            for d in (sert, anahtar, sarili):
                if d.exists():
                    os.replace(d, d.with_name(f"{d.name}.eski-{damga}"))
            yeniden = True
            _log.warning("aktarım sertifikası açılamadı ya da anahtarıyla eşleşmiyor; eski dosyalar "
                         "'.eski-%s' olarak saklandı, yenisi üretildi (telefonlar yeniden eşleşmeli)", damga)

    parola = secrets.token_bytes(24).hex().encode() if saglayici is not None else None
    pi = uret(sert, anahtar, parola, ad=ad, san_ip=san_ip)
    if parola is not None:
        g = sarili.with_name(sarili.name + ".yeni")
        _yaz_gecici(g, saglayici.sar(parola))
        os.replace(g, sarili)
    return Sertifika(sert, anahtar, pi, parola is not None, parola, yeniden)
