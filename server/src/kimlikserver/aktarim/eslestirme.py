"""Eşleştirme (docs/AKTARIM.md §2): tek kullanımlık kod, `km1:` metni, `POST /eslestir` mantığı.

Bellek içi durum; kod diske yazılmaz. Cihaz anahtarının kendisi saklanmaz (yalnız SHA-256 özeti).
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
import secrets
import socket
import threading
import time
from collections.abc import Callable

KOD_SURESI_S = 600
EN_FAZLA_YANLIS = 5
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")   # her yerde fullmatch

_YEREL_AGLAR = tuple(ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "::1/128", "fe80::/10"))
_OZEL_V4 = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def yerel_adres_mi(adres: str) -> bool:
    """RFC1918 + link-local + loopback (`::ffff:` eşlemeli IPv4 dahil) ise True; bozuk metin False."""
    try:
        ip = ipaddress.ip_address(str(adres).split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip in ag for ag in _YEREL_AGLAR if ag.version == ip.version)


def yerel_ipv4_adresleri() -> list[str]:
    """Bu bilgisayarın RFC1918 IPv4 adresleri (ağ erişimi yapmadan, yalnız kendi adının çözümlemesi)."""
    bulunan: list[str] = []
    try:
        ad = socket.gethostname()
        for _f, _t, _p, _c, sa in socket.getaddrinfo(ad, None, socket.AF_INET):
            a = sa[0]
            if a not in bulunan and any(ipaddress.ip_address(a) in ag for ag in _OZEL_V4):
                bulunan.append(a)
    except OSError:
        pass
    return bulunan


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def b64url_coz(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def eslestirme_metni(adresler: list[str], port: int, parmak_izi: str, kod: str, pc_adi: str) -> str:
    """`km1:` + base64url(JSON {a,p,f,k,n}); dolgu (=) yazılmaz, çözücü her iki biçimi kabul eder."""
    govde = {"a": list(adresler), "p": int(port), "f": parmak_izi, "k": kod, "n": pc_adi}
    return "km1:" + b64url(json.dumps(govde, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def eslestirme_coz(metin: str) -> dict:
    metin = metin.strip()
    if not metin.startswith("km1:"):
        raise ValueError("km1: ile başlamıyor")
    return json.loads(b64url_coz(metin[4:]).decode("utf-8"))


def anahtar_ozeti(cihaz_anahtari: str) -> str:
    """Saklanan özet: Bearer'da gönderilen anahtar METNİNİN SHA-256'sı (küçük harf onaltılık)."""
    return hashlib.sha256(cihaz_anahtari.encode("utf-8")).hexdigest()


class EslestirmeKodlari:
    """Tek kullanımlık kod havuzu. Aynı anda tek geçerli kod; yenisi eskisini geçersiz kılar."""

    def __init__(self, saat: Callable[[], float] = time.monotonic):
        self._saat = saat
        self._kilit = threading.Lock()
        self._kod: str | None = None
        self._bitis = 0.0
        self._yanlis = 0
        self._neden: str | None = "uretilmedi"   # kod geçersizse nedeni (arayüz için)

    def uret(self, sure_s: float = KOD_SURESI_S) -> str:
        with self._kilit:
            self._kod = secrets.token_urlsafe(18)
            self._bitis = self._saat() + sure_s
            self._yanlis = 0
            self._neden = None
            return self._kod

    def gecerli_mi(self) -> bool:
        return self.durum()[0]

    def durum(self) -> tuple[bool, str | None]:
        """(geçerli_mi, neden). neden: None | "sure_doldu" | "cok_yanlis_deneme" | "kullanildi" | "uretilmedi" | "iptal"."""
        with self._kilit:
            if self._kod is not None and self._saat() >= self._bitis:
                self._kod, self._neden = None, "sure_doldu"
            return self._kod is not None, (None if self._kod is not None else self._neden)

    def iptal(self) -> None:
        with self._kilit:
            self._kod, self._neden = None, "iptal"

    def tuket(self, kod: str) -> bool:
        """Doğruysa kodu tüketir (tek kullanım). Yanlışta sayaç artar; 5. yanlışta etkin kod geçersiz olur."""
        with self._kilit:
            if self._kod is not None and self._saat() >= self._bitis:
                self._kod, self._neden = None, "sure_doldu"
            if self._kod is None:
                return False
            if isinstance(kod, str) and secrets.compare_digest(kod.encode("utf-8"), self._kod.encode("utf-8")):
                self._kod, self._neden = None, "kullanildi"
                return True
            self._yanlis += 1
            if self._yanlis >= EN_FAZLA_YANLIS:
                self._kod, self._neden = None, "cok_yanlis_deneme"
            return False


def eslestir(govde: object, kodlar: EslestirmeKodlari, cihaz_ekle: Callable[[str, str, str | None, str], None],
             pc_adi: str) -> tuple[int, dict]:
    """`POST /eslestir` işleyicisi (HTTP'siz). (durum kodu, yanıt gövdesi) döner."""
    if not isinstance(govde, dict):
        return 400, {"hata": "gövde bir JSON nesnesi olmalı"}
    cihaz_id, ad, kod = govde.get("cihaz_id"), govde.get("ad"), govde.get("kod")
    if not isinstance(cihaz_id, str) or not UUID_RE.fullmatch(cihaz_id):
        return 400, {"hata": "cihaz_id UUID olmalı"}
    if not isinstance(ad, str) or not ad.strip() or len(ad) > 100:
        return 400, {"hata": "ad gerekli (en çok 100 karakter)"}
    if not isinstance(kod, str) or not kod or len(kod) > 200:
        return 401, {"hata": "kod geçersiz"}
    platform = govde.get("platform") if isinstance(govde.get("platform"), str) else None
    if platform is not None:
        platform = platform[:50]
    if not kodlar.tuket(kod):
        return 401, {"hata": "kod geçersiz, süresi dolmuş ya da kullanılmış"}
    anahtar = secrets.token_bytes(32).hex()
    cihaz_ekle(cihaz_id, ad.strip(), platform, anahtar_ozeti(anahtar))
    return 200, {"cihaz_anahtari": anahtar, "cihaz_id": cihaz_id, "pc_adi": pc_adi}
