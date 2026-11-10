"""Arayüzün tek giriş noktası: ayarlar, sihirbaz, Uygulama (iş mantığı) ve yardımcılar.
Web katmanı yalnızca `api(ad, girdi)` çağırır; kabuk değişirse bu sınıf aynen kalır."""
from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from kimlikcore import KimlikError

from . import APP_AD, __version__, claude_ayar, gunluk, hata_raporu, saglik, veri_klasoru
from .ayarlar import Ayarlar
from .baslangic import Otomatik, veri_yolunu_kaydet
from .cekirdek import IslemHatasi, Uygulama

# Uygulama'nın dışarıya açılan yöntemleri (ad -> yöntem). Başka hiçbir şey çağrılamaz.
UYGULAMA_API = frozenset({
    "durum", "ara", "zaman", "kayit_gizle", "kaynaklar", "kaynak_kaldir", "kaynak_sil", "turler",
    "ice_aktar_baslat", "ice_aktar_durum", "persona_liste", "persona_ekle", "persona_guncelle",
    "persona_sil", "persona_sure_kontrol", "celiskiler", "celiski_coz", "kimlik_karti", "erisim",
    "anahtar_uret", "anahtar_iptal", "izin_ver", "izin_kaldir", "izin_toplu", "erisim_kaydi",
    "baglanti_bilgisi", "claude_ekle",
})


def sec_dialog(tur: str) -> str | None:
    """Dosya/klasör seçme penceresi, AYRI süreçte (tkinter ana iş parçacığı sorunu olmasın).
    Sonuç geçici dosyayla döner (pencereli exe'de stdout güvenilir değildir)."""
    import os
    import tempfile
    fd, cikti = tempfile.mkstemp(prefix="kimlik-sec-", suffix=".txt")
    os.close(fd)
    taban = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "kimlikwin"]
    try:
        subprocess.run([*taban, "--sec", tur, "--cikti", cikti], timeout=600)
        yol = Path(cikti).read_text(encoding="utf-8").strip()
    except (OSError, subprocess.SubprocessError):
        yol = ""
    finally:
        try:
            os.unlink(cikti)
        except OSError:
            pass
    return yol or None


class Yonetici:
    def __init__(self, ayarlar: Ayarlar | None = None, otomatik: Otomatik | None = None,
                 secici: Callable[[str], str | None] = sec_dialog,
                 claude_yolu: Callable[[], Path | None] = claude_ayar.bul):
        self.ayarlar = ayarlar or Ayarlar()
        self.otomatik = otomatik or Otomatik()
        self.secici = secici
        self.claude_yolu = claude_yolu
        self.uygulama: Uygulama | None = None
        self.son_dogrulama: str | None = None
        self.baslangic_hatasi: str | None = None
        self.cikis_istegi = False

    # ------------------------------------------------------------------ yaşam döngüsü
    def baslat(self) -> None:
        """Kurulum tamamlanmışsa Hub'ı yazan olarak açar. Kilitliyse hata verir (çağıran ele alır)."""
        if self.ayarlar["ilk_acilis_tamam"] and self.ayarlar["veri_klasoru"]:
            self.uygulama = Uygulama(self.ayarlar["veri_klasoru"], ayar_dizin=self.ayarlar.dizin,
                                     claude_yolu=self.claude_yolu)

    def kapat(self) -> None:
        if self.uygulama:
            self.uygulama.kapat()
            self.uygulama = None

    # ------------------------------------------------------------------ API
    def api(self, ad: str, girdi: dict[str, Any]) -> Any:
        yerel = getattr(self, "api_" + ad, None)
        if yerel is not None:
            return yerel(**girdi)
        if ad in UYGULAMA_API:
            if self.uygulama is None:
                raise IslemHatasi("Önce ilk açılış sihirbazını tamamlayın.", "sihirbaz_gerekli")
            return getattr(self.uygulama, ad)(**girdi)
        raise IslemHatasi("Bilinmeyen işlem.", "yok")

    def api_acilis(self) -> dict:
        return {"sihirbaz": self.uygulama is None, "tema": self.ayarlar["tema"], "surum": __version__,
                "ad": APP_AD, "varsayilan_klasor": veri_klasoru.varsayilan_oner(),
                "otomatik_baslat": self.ayarlar["otomatik_baslat"],
                "yarim_is": self.uygulama.yarim_kalan_is() if self.uygulama else None,
                "eskiyen": self.uygulama.eskiyen if self.uygulama else 0,
                "baslangic_hatasi": self.baslangic_hatasi}

    def api_sec(self, tur: str) -> dict:
        if tur not in ("dosya", "klasor"):
            raise IslemHatasi("Geçersiz seçim türü.")
        return {"yol": self.secici(tur)}

    def api_sihirbaz_denetle(self, yol: str) -> dict:
        return veri_klasoru.denetle(yol).to_dict()

    def api_sihirbaz_tamamla(self, yol: str, otomatik_baslat: bool = True) -> dict:
        if self.uygulama is not None:
            raise IslemHatasi("Kurulum zaten tamamlanmış.")
        bilgi = veri_klasoru.olustur(yol)
        self.ayarlar.guncelle(veri_klasoru=bilgi["yol"], ilk_acilis_tamam=True, otomatik_baslat=bool(otomatik_baslat))
        self._otomatik_uygula(bool(otomatik_baslat))
        veri_yolunu_kaydet(bilgi["yol"])
        self.baslat()
        gunluk.log().info("ilk açılış tamamlandı (şema %s)", bilgi["sema"])
        return {**bilgi, "baglanti": self.uygulama.baglanti_bilgisi() if self.uygulama else None}

    def _otomatik_uygula(self, acik: bool) -> str | None:
        if not self.otomatik.desteklenir:
            return "Bu sistemde girişte başlatma desteklenmiyor."
        try:
            self.otomatik.ayarla(acik)
        except OSError as e:
            return f"Girişte başlatma ayarlanamadı: {e.strerror or e}"
        return None

    def api_ayarlar(self) -> dict:
        return {"tema": self.ayarlar["tema"], "otomatik_baslat": self.otomatik.etkin_mi(),
                "otomatik_destek": self.otomatik.desteklenir, "veri_klasoru": self.ayarlar["veri_klasoru"],
                "port": self.ayarlar["port"]}

    def api_ayar_yaz(self, tema: str | None = None, otomatik_baslat: bool | None = None) -> dict:
        uyari = None
        if tema is not None:
            try:
                self.ayarlar.guncelle(tema=tema)
            except ValueError as e:
                raise IslemHatasi(str(e)) from None
        if otomatik_baslat is not None:
            uyari = self._otomatik_uygula(bool(otomatik_baslat))
            if uyari is None:
                self.ayarlar.guncelle(otomatik_baslat=bool(otomatik_baslat))
        return {**self.api_ayarlar(), "uyari": uyari}

    def api_saglik(self) -> dict:
        veri = self.ayarlar["veri_klasoru"]
        if not veri:
            return {"ok": False, "kontroller": [{"ad": "veri klasörü seçildi", "ok": False, "ayrinti": ""}], "metin": ""}
        s = saglik.denetle(veri)
        self.son_dogrulama = ("tüm kontroller geçti" if s["ok"] else "BAŞARISIZ kontroller var") + " (sağlık denetimi)"
        return {**s, "metin": saglik.metin(s)}

    def api_hata_raporu(self, adim: str = "", mesaj: str = "", ek: str = "") -> dict:
        h = RuntimeError(mesaj) if mesaj else None
        return {"metin": hata_raporu.olustur(adim, h, self.son_dogrulama, ek or None, self.ayarlar.dizin)}

    def api_hakkinda(self) -> dict:
        import kimlikcore
        return {"ad": APP_AD, "surum": __version__, "cekirdek": kimlikcore.__version__,
                "python": sys.version.split()[0],
                "veri_klasoru": self.ayarlar["veri_klasoru"],
                "lisanslar": ["Python (PSF)", "SQLite (kamu malı)", "mcp SDK (MIT)", "ijson (BSD-3-Clause)",
                              "PyInstaller (GPLv2+, paketlenen uygulama için istisnalı)",
                              "pystray (LGPL-3.0)", "Pillow (HPND)", "Inno Setup (kendi lisansı)"],
                "sifreleme_notu": "Uygulama verileri şifrelemez. Veri klasörünü BitLocker/VeraCrypt gibi "
                                  "şifreli bir birimde tutmanız önerilir.",
                "smartscreen_notu": "Uygulama imzasızdır: Windows SmartScreen 'Windows bilgisayarınızı "
                                    "korudu' uyarısı gösterebilir ve bazı antivirüsler yanlış alarm "
                                    "verebilir. Kurulum dosyasının bütünlüğünü SHA256SUMS ile doğrulayın."}

    def api_cikis(self) -> dict:
        self.cikis_istegi = True
        return {"ok": True}


__all__ = ["Yonetici", "KimlikError", "UYGULAMA_API"]
