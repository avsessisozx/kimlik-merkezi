"""Girişte otomatik başlama (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run). Kapatılabilir.

Kayıt defteri erişimi bir `Arka uç` ile soyutlanır; testler sahte arka uç kullanır.
Yönetici izni gerekmez (HKCU).
"""
from __future__ import annotations

import sys
from typing import Protocol

ANAHTAR = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEGER_AD = "KimlikMerkezi"


class ArkaUc(Protocol):
    def oku(self) -> str | None: ...
    def yaz(self, komut: str) -> None: ...
    def sil(self) -> None: ...


class WinregArkaUc:
    def __init__(self, deger_ad: str = DEGER_AD, anahtar: str = ANAHTAR):
        import winreg  # yalnız Windows
        self._w = winreg
        self.ad, self.anahtar = deger_ad, anahtar

    def oku(self) -> str | None:
        w = self._w
        try:
            with w.OpenKey(w.HKEY_CURRENT_USER, self.anahtar, 0, w.KEY_READ) as k:
                return str(w.QueryValueEx(k, self.ad)[0])
        except FileNotFoundError:
            return None

    def yaz(self, komut: str) -> None:
        w = self._w
        with w.CreateKeyEx(w.HKEY_CURRENT_USER, self.anahtar, 0, w.KEY_SET_VALUE) as k:
            w.SetValueEx(k, self.ad, 0, w.REG_SZ, komut)

    def sil(self) -> None:
        w = self._w
        try:
            with w.OpenKey(w.HKEY_CURRENT_USER, self.anahtar, 0, w.KEY_SET_VALUE) as k:
                w.DeleteValue(k, self.ad)
        except FileNotFoundError:
            pass


def varsayilan_arka_uc() -> ArkaUc | None:
    return WinregArkaUc() if sys.platform == "win32" else None


def baslatma_komutu() -> str:
    """Girişte çalışacak komut: pencere açmadan tepside başlar."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --arka-plan'
    return f'"{sys.executable}" -m kimlikwin --arka-plan'


class Otomatik:
    def __init__(self, arka_uc: ArkaUc | None = None):
        self.arka_uc = arka_uc if arka_uc is not None else varsayilan_arka_uc()

    @property
    def desteklenir(self) -> bool:
        return self.arka_uc is not None

    def etkin_mi(self) -> bool:
        return bool(self.arka_uc and self.arka_uc.oku())

    def ayarla(self, acik: bool) -> None:
        if not self.arka_uc:
            raise OSError("Bu sistemde girişte başlatma desteklenmiyor.")
        if acik:
            self.arka_uc.yaz(baslatma_komutu())
        else:
            self.arka_uc.sil()


# ---------------------------------------------------------------------- kaldırıcı için veri yolu
UYGULAMA_ANAHTARI = r"Software\KimlikMerkezi"


def veri_yolunu_kaydet(yol: str) -> bool:
    """Kaldırıcının "veriler de silinsin mi" sorusunda hangi klasörü sileceğini bilmesi için
    HKCU\\Software\\KimlikMerkezi\\VeriKlasoru değerini yazar (yönetici izni gerekmez). Windows dışında no-op."""
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UYGULAMA_ANAHTARI, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "VeriKlasoru", 0, winreg.REG_SZ, yol)
        return True
    except OSError:
        return False
