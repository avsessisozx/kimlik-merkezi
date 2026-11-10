"""Arayüzdeki 'Dosyayı denetle (içerik göstermez)' işi: kimlikimport.tanila ile yapı raporu üretir.

Yalnız OKUR: veritabanına dokunmaz, Hub açmaz, hub.lock gerektirmez. Arka plan iş parçacığında çalışır
(arayüz donmaz). Durum sorgulanır; rapor boyutu sınırlıdır. Durum nesnesi dosya YOLUNU taşımaz ve hata
iletisine istisna metnini koymaz (yalnız tür adı): ikisi de kişi adı/dosya adı sızdırabilir.

Zaman aşımı: bir iş parçacığı dışarıdan öldürülemez. Süre dolunca iş 'zaman_asimi' olur ve sonucu ATILIR;
iş parçacığı kendi kendine bitene kadar yeni denetim başlatılmaz (tanila büyük dosyayı zaten örnekler,
bu yüzden sonsuza kadar sürmez)."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

RAPOR_SINIRI = 200_000          # karakter
ZAMAN_ASIMI_SN = 900.0


def kisalt(metin: str, sinir: int = RAPOR_SINIRI) -> tuple[str, bool]:
    if len(metin) <= sinir:
        return metin, False
    kesik = metin[:sinir].rsplit("\n", 1)[0]
    return kesik + f"\n\n… [rapor {len(metin)} karakterdi; ilk {len(kesik)} karakter gösteriliyor]", True


def _varsayilan_fn(yol: str, adlari_goster: bool, ayrinti: bool) -> str:
    from kimlikimport.tanila import tanila
    return tanila(yol, adlari_goster=adlari_goster, ayrinti=ayrinti)


class TanilaIsi:
    def __init__(self, yol: str, adlari_goster: bool, ayrinti: bool, *, zaman_asimi: float = ZAMAN_ASIMI_SN,
                 fn: Callable[[str, bool, bool], str] | None = None, rapor_siniri: int = RAPOR_SINIRI):
        self.yol, self.adlari_goster, self.ayrinti = yol, adlari_goster, ayrinti
        self.zaman_asimi, self.fn, self.rapor_siniri = zaman_asimi, fn or _varsayilan_fn, rapor_siniri
        self.durum = "calisiyor"        # calisiyor | bitti | hata | zaman_asimi
        self.rapor: str | None = None
        self.kisaltildi = False
        self.hata: str | None = None
        self.basla = time.monotonic()
        self._bitis: float | None = None
        self._kilit = threading.Lock()
        self._is = threading.Thread(target=self._calis, daemon=True, name="tanila")

    def baslat(self) -> None:
        self._is.start()

    @property
    def canli(self) -> bool:
        return self._is.is_alive()

    def _calis(self) -> None:
        try:
            metin = self.fn(self.yol, self.adlari_goster, self.ayrinti)
            rapor, kes = kisalt(metin, self.rapor_siniri)
            with self._kilit:
                if self.durum == "calisiyor":
                    self.rapor, self.kisaltildi, self.durum = rapor, kes, "bitti"
                    self._bitis = time.monotonic()
        except BaseException as e:   # iletiyi koyma: dosya adı içerebilir
            with self._kilit:
                if self.durum == "calisiyor":
                    self.hata = f"Dosya denetlenemedi ({type(e).__name__})."
                    self.durum, self._bitis = "hata", time.monotonic()

    def to_dict(self) -> dict[str, Any]:
        with self._kilit:
            if self.durum == "calisiyor" and time.monotonic() - self.basla > self.zaman_asimi:
                self.durum, self._bitis = "zaman_asimi", time.monotonic()
                self.hata = ("Denetim çok uzun sürdü ve bırakıldı. Dosya çok büyük olabilir; "
                             "başka bir dosya deneyin ya da bu dosyayı bölün.")
            gecen = (self._bitis or time.monotonic()) - self.basla
            return {"durum": self.durum, "gecen_sn": round(gecen, 1), "rapor": self.rapor,
                    "kisaltildi": self.kisaltildi, "hata": self.hata}
