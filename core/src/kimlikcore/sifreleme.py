"""Veri şifreleme: anahtar yönetimi (iki katman) ve şifreli dosya biçimi. Ayrıntı: docs/SIFRELEME.md.

Özet:
- Tek bir rastgele VERİ ANAHTARI (DEK, 32 bayt) tüm veriyi şifreler (AES-256-GCM, parçalı biçim).
- DEK, `anahtar.json` içinde "yuvalar" halinde SARILI saklanır; yuvanın düz hâli diskte yoktur:
    * `os`       : işletim sistemi hesabına bağlı sarma (Windows DPAPI). Parolasız varsayılan katman.
    * `parola`   : kullanıcı parolasından scrypt ile türetilen anahtarla sarma (isteğe bağlı).
    * `kurtarma` : kullanıcının seçtiği uzun kurtarma ifadesinden scrypt ile türetilen anahtarla sarma.
- Parola eklenince `os` yuvası KALDIRILIR (yoksa parola, hesaba girebilen biri için anlamsız olurdu).
- Parola, kurtarma ifadesi kurulmadan eklenemez.

Bu modül Hub'ı içe aktarmaz. Şifreleme için `cryptography` (Apache-2.0 / BSD-3) gerekir; yalnız
şifreleme kullanıldığında yüklenir (şifresiz veri klasörleri onsuz da açılır).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO, Protocol

from .errors import (
    AnahtarGerekli,
    KuralHatasi,
    SaglayiciYok,
    SifrelemeHatasi,
    SifreliDosyaBozuk,
    YanlisParola,
)
from .turkish import fold

ANAHTAR_DOSYASI = "anahtar.json"
ENV_PAROLA = "KIMLIK_PAROLA"
ENV_SAHTE = "KIMLIK_SAHTE_SAGLAYICI"   # YALNIZ test: sahte sağlayıcıyı seçer (güvenlik sağlamaz)
MAGIC = b"KMSIFRE1"
PARCA = 1 << 20           # 1 MiB düz metin / parça
_ETIKET = 16              # GCM etiketi
_BASLIK = len(MAGIC) + 16  # MAGIC + dosya tuzu
KDF_N = 1 << 15           # scrypt maliyeti (testler düşürebilir; değer yuvada saklanır)
KDF_R = 8
KDF_P = 1
_KDF_N_UST = 1 << 20      # yuvadan okunan değerlerde sınır (hizmet reddi / bozuk dosya)

UYARI_KURTARMA = (
    "ÖNEMLİ: Parola VE kurtarma ifadesi ikisi de unutulursa verileriniz KİMSE tarafından "
    "kurtarılamaz (biz dahil; sunucu yok, arka kapı yok). Kurtarma ifadesini kâğıda yazıp güvenli "
    "bir yerde saklayın; bilgisayarda düz metin olarak tutmayın."
)


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:  # pragma: no cover - ortam sorunu
        raise SifrelemeHatasi(
            "Şifreleme için 'cryptography' paketi gerekir (pip install cryptography)."
        ) from e
    return AESGCM


# ---------------------------------------------------------------------------- sağlayıcılar
class AnahtarSaglayici(Protocol):
    """Veri anahtarını işletim sistemi/hesap düzeyinde saran arayüz."""

    ad: str

    def sar(self, veri: bytes) -> bytes: ...

    def ac(self, sarili: bytes) -> bytes:
        """Açılamazsa AnahtarGerekli fırlatır."""


class DpapiSaglayici:
    """Windows DPAPI (CryptProtectData), stdlib ctypes ile; kullanıcı hesabına bağlı.

    Başka bir Windows kullanıcısı ya da başka bir bilgisayar sarılı anahtarı AÇAMAZ.
    Aynı hesapta çalışan herhangi bir program açabilir (DPAPI'nin doğası); bu yüzden bu katman
    "diske çalınma / başka hesap" karşısında koruma sağlar, aynı hesaptaki kötü yazılıma karşı değil.
    """

    ad = "dpapi"
    _ENTROPI = b"kimlik-merkezi/anahtar/v1"
    _UI_YOK = 0x1  # CRYPTPROTECT_UI_FORBIDDEN

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise SaglayiciYok("Windows DPAPI yalnız Windows'ta vardır.")

    def _cagir(self, islev: str, veri: bytes) -> bytes:
        import ctypes
        from ctypes import wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        def blob(b: bytes):
            buf = ctypes.create_string_buffer(b, len(b))
            return BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        fn = getattr(crypt32, islev)
        fn.restype = wintypes.BOOL
        if islev == "CryptProtectData":
            fn.argtypes = [ctypes.POINTER(BLOB), wintypes.LPCWSTR, ctypes.POINTER(BLOB),
                           ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(BLOB)]
        else:
            fn.argtypes = [ctypes.POINTER(BLOB), ctypes.c_void_p, ctypes.POINTER(BLOB),
                           ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(BLOB)]
        girdi, _k1 = blob(veri)
        entropi, _k2 = blob(self._ENTROPI)
        cikti = BLOB()
        if islev == "CryptProtectData":
            ok = fn(ctypes.byref(girdi), "KimlikMerkezi", ctypes.byref(entropi), None, None,
                    self._UI_YOK, ctypes.byref(cikti))
        else:
            ok = fn(ctypes.byref(girdi), None, ctypes.byref(entropi), None, None,
                    self._UI_YOK, ctypes.byref(cikti))
        if not ok:
            hata = ctypes.get_last_error()
            if islev == "CryptUnprotectData":
                raise AnahtarGerekli(
                    "Veri anahtarı bu Windows hesabıyla açılamadı (başka hesap/bilgisayar olabilir). "
                    "Kurtarma ifadeniz varsa 'kimlikmerkezi kurtar' ile yeniden bağlayın "
                    f"(Windows hata kodu {hata})."
                )
            raise SifrelemeHatasi(f"Windows DPAPI anahtarı saramadı (hata kodu {hata}).")
        try:
            return ctypes.string_at(cikti.pbData, cikti.cbData)
        finally:
            kernel32.LocalFree(ctypes.cast(cikti.pbData, ctypes.c_void_p))

    def sar(self, veri: bytes) -> bytes:
        return self._cagir("CryptProtectData", veri)

    def ac(self, sarili: bytes) -> bytes:
        return self._cagir("CryptUnprotectData", sarili)


class SahteSaglayici:
    """TEST amaçlı sağlayıcı: anahtarı verilen gizli metinden türetilen anahtarla sarar.

    Linux/CI'da DPAPI'nin yerini tutar; gerçek bir güvenlik sağlamaz (gizli metin süreç ortamındadır).
    """

    ad = "sahte"

    def __init__(self, gizli: str = "test") -> None:
        self._anahtar = hashlib.sha256(b"kimlik-sahte-saglayici/" + gizli.encode("utf-8")).digest()

    def sar(self, veri: bytes) -> bytes:
        nonce = secrets.token_bytes(12)
        return nonce + _aesgcm()(self._anahtar).encrypt(nonce, veri, b"sahte")

    def ac(self, sarili: bytes) -> bytes:
        try:
            return _aesgcm()(self._anahtar).decrypt(sarili[:12], sarili[12:], b"sahte")
        except Exception as e:
            raise AnahtarGerekli("Sahte sağlayıcı anahtarı açamadı (farklı gizli metin).") from e


_ozel_saglayici: AnahtarSaglayici | None = None


def saglayici_ayarla(s: AnahtarSaglayici | None) -> None:
    """Süreç genelinde sağlayıcıyı değiştirir (testler/uygulama gömme). None = varsayılana dön."""
    global _ozel_saglayici
    _ozel_saglayici = s


def varsayilan_saglayici() -> AnahtarSaglayici | None:
    """Sıra: saglayici_ayarla ile verilen, KIMLIK_SAHTE_SAGLAYICI (test), Windows'ta DPAPI, yoksa None."""
    if _ozel_saglayici is not None:
        return _ozel_saglayici
    gizli = os.environ.get(ENV_SAHTE)
    if gizli:
        return SahteSaglayici(gizli)
    if sys.platform == "win32":
        return DpapiSaglayici()
    return None


def varsayilan_acik_mi() -> bool:
    """Yeni veri klasörü şifreli oluşturulabilir mi (bu sistemde anahtar sağlayıcı var mı)?"""
    return varsayilan_saglayici() is not None


# ---------------------------------------------------------------------------- kurallar
_ZAYIF_IFADE = (
    "password", "parola", "sifre", "gizli", "kurtarma", "kurtarma ifadesi", "qwerty", "qwertyuiop",
    "asdfgh", "azerty", "123456", "1234567890", "0123456789", "abcdef", "abcdefgh", "iloveyou",
    "letmein", "admin", "kimlik merkezi", "kimlikmerkezi", "bir iki uc dort bes",
    "one two three four five", "the quick brown fox jumps over the lazy dog",
    "correct horse battery staple", "lorem ipsum dolor sit amet", "test test test test",
    "ali veli kirk dokuz elli", "turkiye cumhuriyeti", "istanbul ankara izmir bursa",
    "galatasaray fenerbahce besiktas", "seni seviyorum", "canim benim", "ben kimim",
    "annemin kizlik soyadi", "ilk evcil hayvanim", "dogdugum sehir",
)
_GUVENLI_SESSIZ = re.compile(r"[\W_]+")


def _sade(s: str) -> str:
    """Zayıf-liste karşılaştırması: katla, noktalama/boşluk at."""
    return _GUVENLI_SESSIZ.sub("", fold(s))


def _zayif_listede(s: str) -> str | None:
    sade = _sade(s)
    if not sade:
        return "boş"
    for z in _ZAYIF_IFADE:
        zs = _sade(z)
        if zs and zs in sade and len(zs) * 2 >= len(sade):  # ifadenin yarısından çoğunu kapsıyorsa
            return z
    return None


def _sirali_mi(sade: str) -> bool:
    """aaaa..., abcdef..., 123456... gibi tek kalıplı diziler."""
    if len(sade) < 6:
        return False
    if len(set(sade)) <= 2:
        return True
    farklar = {ord(b) - ord(a) for a, b in zip(sade, sade[1:])}
    return farklar <= {1} or farklar <= {-1}


def ifade_normallestir(ifade: str) -> str:
    """Kurtarma ifadesi: NFKC, boşluklar tek, Türkçe katlama (büyük/küçük harf ve aksan farkı yok)."""
    s = unicodedata.normalize("NFKC", ifade)
    return " ".join(fold(s).split())


def ifade_degerlendir(ifade: str) -> dict[str, Any]:
    """Kurtarma ifadesi kurallarını denetler. {"uygun": bool, "sorunlar": [...], "guc": str}.

    Kural: en az 4 kelime YA DA en az 20 karakter; çok kısa/tahmin edilebilir (gizli soru yanıtı gibi)
    ifadeler, bilinen zayıf ifadeler ve tek kalıplı diziler reddedilir. Güç göstergesi sezgiseldir
    (gerçek entropi ölçümü değildir).
    """
    sorunlar: list[str] = []
    norm = ifade_normallestir(ifade or "")
    kelimeler = norm.split()
    n_kelime, n_kar = len(kelimeler), len(norm)
    if n_kelime < 4 and n_kar < 20:
        sorunlar.append("En az 4 kelime ya da en az 20 karakter olmalı.")
    sade = _sade(norm)
    if len(sade) < 12:
        sorunlar.append("Harf/rakam sayısı çok az (en az 12).")
    if len(set(sade)) < 8:
        sorunlar.append("Çok az farklı karakter var (en az 8).")
    if n_kelime >= 2 and len(set(kelimeler)) < max(2, n_kelime // 2):
        sorunlar.append("Aynı kelimeler tekrar ediyor.")
    if _sirali_mi(sade):
        sorunlar.append("Tek kalıplı dizi (aaaa, abcdef, 123456 gibi) olamaz.")
    z = _zayif_listede(norm)
    if z:
        sorunlar.append("Bilinen/tahmin edilebilir bir ifade ('" + z + "' gibi).")
    if sorunlar:
        guc = "zayıf"
    elif n_kar >= 35 or n_kelime >= 6:
        guc = "güçlü"
    elif n_kar >= 25 or n_kelime >= 5:
        guc = "iyi"
    else:
        guc = "orta"
    return {"uygun": not sorunlar, "sorunlar": sorunlar, "guc": guc,
            "kelime": n_kelime, "karakter": n_kar}


def parola_degerlendir(parola: str, ifade: str | None = None) -> dict[str, Any]:
    """Parola kuralları: en az 10 karakter, en az 5 farklı karakter, zayıf listede olmamalı,
    kurtarma ifadesiyle aynı olmamalı."""
    sorunlar: list[str] = []
    p = unicodedata.normalize("NFKC", parola or "")
    if len(p) < 10:
        sorunlar.append("Parola en az 10 karakter olmalı.")
    if len(set(p)) < 5:
        sorunlar.append("Çok az farklı karakter var (en az 5).")
    if _sirali_mi(_sade(p)):
        sorunlar.append("Tek kalıplı dizi olamaz.")
    if p and _zayif_listede(p):
        sorunlar.append("Bilinen/tahmin edilebilir bir parola.")
    if ifade is not None and p and _sade(p) == _sade(ifade):
        sorunlar.append("Parola kurtarma ifadesiyle aynı olamaz (ikisi ayrı koruma katmanıdır).")
    return {"uygun": not sorunlar, "sorunlar": sorunlar}


def _kural_denetle(d: dict[str, Any], ne: str) -> None:
    if not d["uygun"]:
        raise KuralHatasi(f"{ne} kurallara uymuyor: " + " ".join(d["sorunlar"]))


# ---------------------------------------------------------------------------- yuva (zarf) işleri
def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"), validate=True)


def _kdf(gizli: str, tuz: bytes, n: int, r: int, p: int) -> bytes:
    if not (2 <= n <= _KDF_N_UST and n & (n - 1) == 0 and 1 <= r <= 16 and 1 <= p <= 4):
        raise SifreliDosyaBozuk("Anahtar dosyasındaki KDF ayarları geçersiz.")
    return hashlib.scrypt(gizli.encode("utf-8"), salt=tuz, n=n, r=r, p=p, dklen=32,
                          maxmem=256 * 1024 * 1024)


def _aad(kid: str, yuva: str) -> bytes:
    return f"kimlik-anahtar/1/{kid}/{yuva}".encode("ascii")


def _gizli_yuva(yuva: str, gizli: str, dek: bytes, kid: str) -> dict[str, Any]:
    tuz = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    kek = _kdf(gizli, tuz, KDF_N, KDF_R, KDF_P)
    sarili = _aesgcm()(kek).encrypt(nonce, dek, _aad(kid, yuva))
    return {"kdf": "scrypt", "n": KDF_N, "r": KDF_R, "p": KDF_P, "tuz": _b64(tuz),
            "nonce": _b64(nonce), "sarili": _b64(sarili)}


def _gizli_yuva_ac(yuva: str, y: dict[str, Any], gizli: str, kid: str) -> bytes:
    try:
        kek = _kdf(gizli, _unb64(y["tuz"]), int(y["n"]), int(y["r"]), int(y["p"]))
        return _aesgcm()(kek).decrypt(_unb64(y["nonce"]), _unb64(y["sarili"]), _aad(kid, yuva))
    except SifreliDosyaBozuk:
        raise
    except (KeyError, ValueError, TypeError) as e:
        raise SifreliDosyaBozuk("Anahtar dosyası bozuk.") from e
    except Exception as e:  # InvalidTag
        raise YanlisParola(
            "Parola yanlış." if yuva == "parola" else "Kurtarma ifadesi yanlış."
        ) from e


def anahtar_yolu(root: Path | str) -> Path:
    return Path(root) / ANAHTAR_DOSYASI


def zarf_oku(root: Path | str) -> dict[str, Any] | None:
    p = anahtar_yolu(root)
    if not p.is_file():
        return None
    try:
        z = json.loads(p.read_text(encoding="utf-8"))
        if z.get("surum") != 1 or not isinstance(z.get("kimlik"), str):
            raise ValueError
        return z
    except (ValueError, OSError) as e:
        raise SifreliDosyaBozuk(f"{ANAHTAR_DOSYASI} okunamadı ya da biçimi geçersiz.") from e


def _zarf_yaz(root: Path | str, z: dict[str, Any]) -> None:
    p = anahtar_yolu(root)
    tmp = p.with_name(p.name + f".gecici-{secrets.token_hex(4)}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(z, f, indent=1)
            f.flush()
            os.fsync(f.fileno())
        yerine_koy(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)


def yerine_koy(kaynak: Path, hedef: Path, deneme: int = 20) -> None:
    """os.replace; Windows'ta hedef başka süreçte açıkken kısa süre yeniden dener."""
    import time

    for i in range(deneme):
        try:
            os.replace(kaynak, hedef)
            return
        except PermissionError:
            if i == deneme - 1:
                raise
            time.sleep(0.05)


def _os_yuva(saglayici: AnahtarSaglayici, dek: bytes, kid: str) -> dict[str, Any]:
    return {"saglayici": saglayici.ad, "sarili": _b64(saglayici.sar(dek + kid.encode("ascii")))}


def _os_yuva_ac(y: dict[str, Any], saglayici: AnahtarSaglayici | None, kid: str) -> bytes:
    if saglayici is None:
        raise SaglayiciYok("Bu sistemde anahtar koruma sağlayıcısı yok (Windows DPAPI).")
    if y.get("saglayici") != saglayici.ad:
        raise AnahtarGerekli(
            f"Anahtar '{y.get('saglayici')}' ile sarılmış, bu sistemde '{saglayici.ad}' var. "
            "Kurtarma ifadeniz varsa 'kimlikmerkezi kurtar' kullanın."
        )
    try:
        ham = saglayici.ac(_unb64(y["sarili"]))
    except AnahtarGerekli:
        raise
    except (KeyError, ValueError) as e:
        raise SifreliDosyaBozuk("Anahtar dosyası bozuk.") from e
    if len(ham) != 32 + len(kid) or ham[32:] != kid.encode("ascii"):
        raise SifreliDosyaBozuk("Sarılı anahtar bu veri klasörüne ait değil.")
    return ham[:32]


# ---------------------------------------------------------------------------- anahtar yaşam döngüsü
def anahtar_kur(root: Path | str, saglayici: AnahtarSaglayici | None = None,
                dek: bytes | None = None) -> bytes:
    """Yeni veri anahtarı üretir, OS yuvasıyla sarıp `anahtar.json` yazar. Anahtarı döner.
    Var olan anahtar dosyasının üzerine YAZMAZ."""
    saglayici = saglayici or varsayilan_saglayici()
    if saglayici is None:
        raise SaglayiciYok(
            "Bu sistemde anahtar koruma sağlayıcısı yok; şifreleme yalnız Windows'ta (DPAPI) açılabilir."
        )
    if zarf_oku(root) is not None:
        raise SifrelemeHatasi("Bu veri klasöründe zaten bir anahtar dosyası var.")
    Path(root).mkdir(parents=True, exist_ok=True)
    dek = dek or secrets.token_bytes(32)
    kid = secrets.token_hex(8)
    _zarf_yaz(root, {"surum": 1, "algo": "aes-256-gcm", "kimlik": kid,
                     "os": _os_yuva(saglayici, dek, kid), "parola": None, "kurtarma": None})
    return dek


def anahtari_coz(root: Path | str, *, parola: str | None = None, kurtarma: str | None = None,
                 saglayici: AnahtarSaglayici | None = None) -> bytes:
    """Veri anahtarını açar. Sıra: verilen kurtarma ifadesi, verilen parola, OS yuvası,
    KIMLIK_PAROLA ortam değişkeni. Hiçbiri olmazsa AnahtarGerekli."""
    z = zarf_oku(root)
    if z is None:
        raise SifrelemeHatasi(f"{ANAHTAR_DOSYASI} yok; bu klasörün anahtarı bulunamıyor.")
    kid = z["kimlik"]
    if kurtarma is not None:
        if not z.get("kurtarma"):
            raise AnahtarGerekli("Bu klasörde kurtarma ifadesi kurulmamış.")
        return _gizli_yuva_ac("kurtarma", z["kurtarma"], ifade_normallestir(kurtarma), kid)
    if parola is None and z.get("os"):
        return _os_yuva_ac(z["os"], saglayici or varsayilan_saglayici(), kid)
    if parola is None:
        parola = os.environ.get(ENV_PAROLA)
    if parola is not None:
        if not z.get("parola"):
            raise AnahtarGerekli("Bu klasörde parola kurulmamış.")
        return _gizli_yuva_ac("parola", z["parola"], unicodedata.normalize("NFKC", parola), kid)
    raise AnahtarGerekli(
        "Veri parolayla korunuyor. Parolayı girin (komut satırında sorulur; MCP/arka plan "
        f"süreçleri için {ENV_PAROLA} ortam değişkeni)."
    )


def kurtarma_kur(root: Path | str, dek: bytes, ifade: str, ifade_tekrar: str) -> None:
    """Kurtarma ifadesi yuvasını kurar/değiştirir. İki giriş aynı olmalı, kurallara uymalı."""
    z = _zarf_gerekli(root)
    if ifade_normallestir(ifade) != ifade_normallestir(ifade_tekrar):
        raise KuralHatasi("Kurtarma ifadesi iki girişte aynı değil.")
    _kural_denetle(ifade_degerlendir(ifade), "Kurtarma ifadesi")
    z["kurtarma"] = _gizli_yuva("kurtarma", ifade_normallestir(ifade), dek, z["kimlik"])
    _zarf_yaz(root, z)


def parola_ekle(root: Path | str, dek: bytes, parola: str, parola_tekrar: str) -> None:
    """Parola katmanı ekler. Kurtarma ifadesi KURULU DEĞİLSE reddedilir. OS yuvası kaldırılır."""
    z = _zarf_gerekli(root)
    if not z.get("kurtarma"):
        raise KuralHatasi("Parola eklemeden önce kurtarma ifadesi kurulmalı.")
    if unicodedata.normalize("NFKC", parola) != unicodedata.normalize("NFKC", parola_tekrar):
        raise KuralHatasi("Parola iki girişte aynı değil.")
    _kural_denetle(parola_degerlendir(parola), "Parola")
    # Aynı ifade parola olarak kullanılamasın: ifadeyle yuva açılıyorsa aynı demektir.
    try:
        _gizli_yuva_ac("kurtarma", z["kurtarma"], ifade_normallestir(parola), z["kimlik"])
    except YanlisParola:
        pass
    else:
        raise KuralHatasi("Parola kurtarma ifadesiyle aynı olamaz (ikisi ayrı koruma katmanıdır).")
    z["parola"] = _gizli_yuva("parola", unicodedata.normalize("NFKC", parola), dek, z["kimlik"])
    z["os"] = None
    _zarf_yaz(root, z)


def parola_kaldir(root: Path | str, dek: bytes, saglayici: AnahtarSaglayici | None = None) -> None:
    """Parolayı kaldırır; OS yuvasını geri koyar (sağlayıcı gerekir). Kurtarma ifadesi kalır."""
    z = _zarf_gerekli(root)
    saglayici = saglayici or varsayilan_saglayici()
    if saglayici is None:
        raise SaglayiciYok("Parolayı kaldırmak için bu sistemde anahtar sağlayıcısı (DPAPI) gerekir.")
    z["os"] = _os_yuva(saglayici, dek, z["kimlik"])
    z["parola"] = None
    _zarf_yaz(root, z)


def kurtar(root: Path | str, ifade: str, yeni_parola: str | None = None,
           yeni_parola_tekrar: str | None = None,
           saglayici: AnahtarSaglayici | None = None) -> str:
    """Kurtarma ifadesiyle erişimi yeniden kurar.

    `yeni_parola` verilirse: yeni parola yuvası kurulur (OS yuvası kaldırılır) -> "parola".
    Verilmezse: bu bilgisayar/hesap için OS yuvası yeniden kurulur, parola yuvası silinir -> "os".
    """
    dek = anahtari_coz(root, kurtarma=ifade)
    z = _zarf_gerekli(root)
    if yeni_parola is not None:
        if unicodedata.normalize("NFKC", yeni_parola) != unicodedata.normalize(
                "NFKC", yeni_parola_tekrar or ""):
            raise KuralHatasi("Parola iki girişte aynı değil.")
        _kural_denetle(parola_degerlendir(yeni_parola, ifade), "Parola")
        z["parola"] = _gizli_yuva("parola", unicodedata.normalize("NFKC", yeni_parola), dek, z["kimlik"])
        z["os"] = None
        _zarf_yaz(root, z)
        return "parola"
    saglayici = saglayici or varsayilan_saglayici()
    if saglayici is None:
        raise SaglayiciYok("Bu sistemde anahtar sağlayıcısı yok; yalnız yeni parola belirleyebilirsiniz.")
    z["os"] = _os_yuva(saglayici, dek, z["kimlik"])
    z["parola"] = None
    _zarf_yaz(root, z)
    return "os"


def anahtari_sil(root: Path | str) -> None:
    """Anahtar dosyasını siler (şifre kaldırma sonunda)."""
    p = anahtar_yolu(root)
    if p.exists():
        guvenli_sil(p)


def _zarf_gerekli(root: Path | str) -> dict[str, Any]:
    z = zarf_oku(root)
    if z is None:
        raise SifrelemeHatasi("Bu veri klasörü şifreli değil (anahtar dosyası yok).")
    return z


# ---------------------------------------------------------------------------- şifreli dosya biçimi
# Dosya: MAGIC(8) | tuz(16) | parça* ; parça = AES-256-GCM(düz<=1MiB) + etiket(16).
# Alt anahtar = HMAC-SHA256(DEK, "kimlik-dosya/1" || tuz): her yazımda taze tuz -> nonce çakışması yok.
# Nonce = sayaç(8, BE) || 3 sıfır || son-parça bayrağı(1). AAD = başlık. Son parça bayrağı ve
# sayaç: parça sırası değiştirme / kırpma / ekleme saldırılarını yakalar (okuyucu EOF'u da doğrular).
def _alt_anahtar(dek: bytes, tuz: bytes) -> bytes:
    return hmac.new(dek, b"kimlik-dosya/1" + tuz, hashlib.sha256).digest()


def _nonce(i: int, son: bool) -> bytes:
    return i.to_bytes(8, "big") + b"\0\0\0" + (b"\1" if son else b"\0")


class SifreYazici:
    """Yazılan düz veriyi parça parça şifreleyip `f`ye yazar. `bitir()` son parçayı yazar."""

    def __init__(self, f: BinaryIO, dek: bytes):
        if len(dek) != 32:
            raise SifrelemeHatasi("Veri anahtarı 32 bayt olmalı.")
        self._f = f
        tuz = secrets.token_bytes(16)
        self._baslik = MAGIC + tuz
        self._g = _aesgcm()(_alt_anahtar(dek, tuz))
        self._tampon = bytearray()
        self._i = 0
        self._bitti = False
        f.write(self._baslik)

    def _parca(self, veri: bytes | bytearray | memoryview, son: bool) -> None:
        self._f.write(self._g.encrypt(_nonce(self._i, son), bytes(veri), self._baslik))
        self._i += 1

    def yaz(self, veri: bytes | memoryview) -> None:
        self._tampon += veri
        # Tamponda PARCA'dan FAZLA varsa en az 1 bayt sonraya kalır -> son parça belirlenebilir.
        while len(self._tampon) > PARCA:
            self._parca(self._tampon[:PARCA], False)
            del self._tampon[:PARCA]

    def bitir(self) -> None:
        if self._bitti:
            return
        self._bitti = True
        self._parca(self._tampon, True)
        self._tampon.clear()


class SifreOkuyucu:
    """Şifreli dosyayı parça parça çözer; `parcalar()` düz veri üretir. Bozulmada SifreliDosyaBozuk."""

    def __init__(self, f: BinaryIO, dek: bytes):
        self._f = f
        baslik = f.read(_BASLIK)
        if len(baslik) != _BASLIK or baslik[:8] != MAGIC:
            raise SifreliDosyaBozuk("Şifreli dosya başlığı geçersiz.")
        self._baslik = baslik
        self._g = _aesgcm()(_alt_anahtar(dek, baslik[8:]))

    def parcalar(self) -> Iterator[bytes]:
        boyut = PARCA + _ETIKET
        cur = self._f.read(boyut)
        i = 0
        if not cur:
            raise SifreliDosyaBozuk("Şifreli dosya kırpılmış (parça yok).")
        while True:
            sonraki = self._f.read(boyut)
            son = not sonraki
            try:
                yield self._g.decrypt(_nonce(i, son), cur, self._baslik)
            except Exception as e:
                raise SifreliDosyaBozuk(
                    "Şifreli dosya doğrulanamadı (bozulma, kırpılma ya da yanlış anahtar)."
                ) from e
            if son:
                return
            cur, i = sonraki, i + 1


def sifreli_mi(yol: Path | str) -> bool:
    try:
        with open(yol, "rb") as f:
            return f.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def acik_boyut(yol: Path | str) -> int:
    """Şifreli dosyanın düz boyutu (dosya boyutundan hesaplanır; çözmeden)."""
    n = os.path.getsize(yol) - _BASLIK
    if n < _ETIKET:
        raise SifreliDosyaBozuk("Şifreli dosya çok kısa.")
    parca = max(1, -(-n // (PARCA + _ETIKET)))
    return n - _ETIKET * parca


def bayt_sifrele_yaz(dek: bytes, veri: bytes | memoryview, hedef: Path | str) -> None:
    """`veri`yi şifreleyip `hedef`e atomik yazar (geçici dosya + fsync + os.replace)."""
    hedef = Path(hedef)
    tmp = hedef.with_name(hedef.name + f".gecici-{secrets.token_hex(4)}")
    try:
        with open(tmp, "wb") as f:
            y = SifreYazici(f, dek)
            mv = memoryview(veri)
            for k in range(0, len(mv), 4 * PARCA):
                y.yaz(mv[k:k + 4 * PARCA])
            y.bitir()
            f.flush()
            os.fsync(f.fileno())
        yerine_koy(tmp, hedef)
    finally:
        tmp.unlink(missing_ok=True)


def bayt_coz_oku(dek: bytes, yol: Path | str) -> bytes:
    with open(yol, "rb") as f:
        return b"".join(SifreOkuyucu(f, dek).parcalar())


def dosya_sifrele(dek: bytes, kaynak: Path | str, hedef: Path | str) -> tuple[str, int]:
    """Düz dosyayı şifreleyip hedefe yazar (hedef atomik değişir). (düz sha256, düz boyut) döner."""
    hedef = Path(hedef)
    tmp = hedef.with_name(hedef.name + f".gecici-{secrets.token_hex(4)}")
    h = hashlib.sha256()
    boyut = 0
    try:
        with open(kaynak, "rb") as fi, open(tmp, "wb") as fo:
            y = SifreYazici(fo, dek)
            while parca := fi.read(PARCA):
                h.update(parca)
                boyut += len(parca)
                y.yaz(parca)
            y.bitir()
            fo.flush()
            os.fsync(fo.fileno())
        yerine_koy(tmp, hedef)
    finally:
        tmp.unlink(missing_ok=True)
    return h.hexdigest(), boyut


def sifreli_sha256(dek: bytes, yol: Path | str) -> tuple[str, int]:
    """Şifreli dosyanın düz içeriğinin (sha256, boyut)'u."""
    h = hashlib.sha256()
    n = 0
    with open(yol, "rb") as f:
        for p in SifreOkuyucu(f, dek).parcalar():
            h.update(p)
            n += len(p)
    return h.hexdigest(), n


def guvenli_sil(yol: Path | str) -> None:
    """Dosyanın içeriğini sıfırla üzerine yazıp siler. En iyi çaba: SSD aşınma dağıtımı,
    günlüklü dosya sistemleri ve yedekler nedeniyle fiziksel silme GARANTİ EDİLMEZ."""
    p = Path(yol)
    try:
        os.chmod(p, 0o600)
        boyut = p.stat().st_size
        with open(p, "r+b") as f:
            sifir = bytes(PARCA)
            kalan = boyut
            while kalan > 0:
                f.write(sifir[:min(kalan, PARCA)])
                kalan -= min(kalan, PARCA)
            f.flush()
            os.fsync(f.fileno())
    except FileNotFoundError:
        return
    except OSError:
        pass
    p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------- durum
def db_durumu(db: Path | str) -> str:
    """'yok' | 'duz' (SQLite) | 'sifreli'."""
    try:
        with open(db, "rb") as f:
            bas = f.read(16)
    except FileNotFoundError:
        return "yok"
    if bas[:8] == MAGIC:
        return "sifreli"
    return "duz"


def durum(root: Path | str, db_adi: str = "kimlik.db") -> dict[str, Any]:
    """Şifreleme durumu (anahtar açılmadan okunabilen bilgiler)."""
    root = Path(root)
    db = db_durumu(root / db_adi)
    z = zarf_oku(root)
    sag = varsayilan_saglayici()
    arsiv = root / "arsiv"
    duz_ham = sifreli_ham = 0
    if arsiv.is_dir():
        for d in arsiv.iterdir():
            if d.is_dir():
                for f in d.iterdir():
                    if f.is_file() and not f.name.startswith("."):
                        if sifreli_mi(f):
                            sifreli_ham += 1
                        else:
                            duz_ham += 1
    kalintilar = sorted(x.name for x in root.glob("kimlik.db.duz-eski*"))
    return {
        "veritabani": db,
        "sifreli": db == "sifreli",
        "anahtar_dosyasi": z is not None,
        "os_korumasi": bool(z and z.get("os")),
        "saglayici": (z["os"].get("saglayici") if z and z.get("os") else None),
        "bu_sistemde_saglayici": sag.ad if sag else None,
        "parola_var": bool(z and z.get("parola")),
        "kurtarma_var": bool(z and z.get("kurtarma")),
        "ham_dosya_sifreli": sifreli_ham,
        "ham_dosya_duz": duz_ham,
        "duz_kalintilar": kalintilar,
    }
