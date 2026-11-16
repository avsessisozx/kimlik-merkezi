"""Telefon aktarımının Windows tarafı: alıcının (kimlikserver.aktarim) yaşam döngüsü ve içe alma.

Kurallar (docs/AKTARIM.md §3):
  * Alıcı YALNIZ ayar `telefon_aktarimi` açıkken VE yazan Hub (uygulama) açıkken dinler. Uygulama kapanınca,
    kişi değişince, klasör kilitlenince ya da dönüşüm sürerken durur; uygulama kapalıyken ASLA dinlemez.
  * `tamamlandi` geri çağrısı yalnız bir işaret bırakır. İçe alma ayrı bir iş parçacığında, uygulamanın yazma
    sırasına uyarak (`Uygulama.telefon_ice_al`) yapılır: içe aktarma/kopya işi sürerken bekler.
  * Dinleme adresi ve port arayüzden/API'den ALINMAZ; yalnız kurucuya (test) enjekte edilir.
  * Eşleştirme kodu ve cihaz anahtarı günlüğe yazılmaz."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__, gunluk
from .cekirdek import IslemHatasi

ALICI_PORTU = 47823          # docs/AKTARIM.md varsayılanı (47821 web arayüzünün yerel portu)
YENIDEN_DENEME_S = 0.3
KOD_SURESI_S = 600
GECERSIZLIK_METINLERI = {
    "sure_doldu": "Kodun süresi doldu.",
    "cok_yanlis_deneme": "Çok fazla yanlış deneme yapıldı.",
    "kullanildi": "Kod kullanıldı.",
    "iptal": "Kod iptal edildi.",
    "uretilmedi": None,
}


def _simdi() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_OTOMATIK = object()      # saglayici verilmediyse alıcının kendi varsayılanı (platform anahtar sağlayıcısı)


class _Ekli:
    """Bir uygulamaya (Hub) bağlı durum: içe alma iş parçacığı ve (açıksa) alıcı."""

    def __init__(self, uygulama):
        self.uygulama = uygulama
        self.alici = None
        self.dur = threading.Event()
        self.bekleyen = threading.Event()
        self.is_ = threading.Thread(target=self._calis, daemon=True, name="telefon-ice-al")
        self.yonetim: "TelefonAktarimi | None" = None

    def _calis(self) -> None:
        while not self.dur.is_set():
            if not self.bekleyen.wait(0.2):
                continue
            self.bekleyen.clear()
            while not self.dur.is_set():
                try:
                    r = self.uygulama.telefon_ice_al()
                except Exception as e:      # noqa: BLE001 - içerik/yol günlüğe yazılmaz
                    gunluk.log().error("telefon: içe alma hatası: %s", type(e).__name__)
                    break
                if r is None:               # içe aktarma/kopya sürüyor: bekle, yeniden dene
                    self.dur.wait(YENIDEN_DENEME_S)
                    continue
                self.yonetim._alim_kaydet(r)
                break


class TelefonAktarimi:
    def __init__(self, yonetici, *, port: int | None = None, adres: str = "0.0.0.0", yalniz_yerel: bool = True,
                 bulma_port: int | None = 47822, saglayici: Any = _OTOMATIK, adresler=None):
        self.y = yonetici
        self._port, self._adres, self._yalniz_yerel = port, adres, yalniz_yerel
        self._bulma_port, self._saglayici = bulma_port, saglayici
        self._adresler = adresler                      # test: yerel adres listesini sabitler
        self._kilit = threading.RLock()
        self._alim_kilit = threading.Lock()            # son_alim (içe alma iş parçacığı _kilit'i beklemesin: join kilitlenmesi)
        self._ekli: _Ekli | None = None
        self.hata: str | None = None
        self.son_alim: dict | None = None              # {"zaman", "dosya", "yeni", "yinelenen", "eksik"}
        self.toplam_yeni = 0
        self.kod_bitis: float | None = None            # time.monotonic()

    # ------------------------------------------------------------------ yaşam döngüsü
    def uyumlandir(self) -> None:
        """İstenen duruma getirir: ayar açık + uygulama açık => alıcı çalışır; aksi halde durur."""
        with self._kilit:
            u = self.y.uygulama if not self.y.mesgul else None
            if self._ekli is not None and self._ekli.uygulama is not u:
                self._ayril()
            if u is None:
                return
            if self._ekli is None:
                self._ekli = _Ekli(u)
                self._ekli.yonetim = self
                self._ekli.is_.start()
                self._ekli.bekleyen.set()              # önceki oturumdan kalanlar
            istenen = bool(self.y.ayarlar["telefon_aktarimi"])
            if istenen and self._ekli.alici is None:
                self._alici_baslat(self._ekli)
            elif not istenen and self._ekli.alici is not None:
                self._alici_durdur(self._ekli)
                self.hata = None

    def durdur(self) -> None:
        with self._kilit:
            self._ayril()

    def _ayril(self) -> None:
        e, self._ekli = self._ekli, None
        if e is None:
            return
        self._alici_durdur(e)
        e.dur.set()
        if e.is_.is_alive() and e.is_ is not threading.current_thread():
            e.is_.join(timeout=30)

    def _alici_baslat(self, e: _Ekli) -> None:
        from kimlikserver.aktarim import AktarimAlici, DogrudanKopru
        ayar = self.y.ayarlar
        tercih = self._port
        if tercih is None:
            tercih = ALICI_PORTU
        if tercih == int(ayar["port"]):      # web arayüz portuyla aynıysa işletim sistemi boş port versin
            tercih = 0
        kopru = DogrudanKopru(e.uygulama.hub, lambda yol: e.bekleyen.set())
        son: Exception | None = None
        for port in (tercih, 0) if tercih else (0,):
            alici = AktarimAlici(kopru, Path(e.uygulama.veri), port, self._adres, self._yalniz_yerel,
                                 surum=__version__, bulma_port=self._bulma_port,
                                 **({} if self._saglayici is _OTOMATIK else {"saglayici": self._saglayici}))
            try:
                alici.baslat()
            except OSError as ex:
                son = ex
                getattr(alici, "_dur", threading.Event()).set()   # başarısız başlatmada temizlik iş parçacığı kalmasın
                continue
            except Exception as ex:   # noqa: BLE001 - sertifika vb.; ayrıntı içermez
                son = ex
                break
            e.alici = alici
            self.hata = None
            e.bekleyen.set()                            # alıcı başlarken bir kez
            gunluk.log().info("telefon aktarımı açıldı (port %d)", alici.port)
            return
        self.hata = f"Telefon aktarımı başlatılamadı ({type(son).__name__}). Port başka bir program tarafından kullanılıyor olabilir."
        gunluk.log().error("telefon aktarımı başlatılamadı: %s", type(son).__name__)

    def _alici_durdur(self, e: _Ekli) -> None:
        a, e.alici = e.alici, None
        self.kod_bitis = None
        if a is not None:
            try:
                a.durdur()
            except Exception as ex:   # noqa: BLE001
                gunluk.log().error("telefon aktarımı durdurulamadı: %s", type(ex).__name__)
            gunluk.log().info("telefon aktarımı kapandı")

    def _alim_kaydet(self, r: dict) -> None:
        with self._alim_kilit:
            if r.get("dosya") or r.get("eksik"):
                self.son_alim = {"zaman": _simdi(), "dosya": int(r.get("dosya", 0)), "yeni": int(r.get("yeni", 0)),
                                 "yinelenen": int(r.get("yinelenen", 0)), "eksik": int(r.get("eksik", 0))}
                self.toplam_yeni += int(r.get("yeni", 0))
                gunluk.log().info("telefondan alım: dosya=%s yeni=%s yinelenen=%s eksik=%s",
                                  r.get("dosya"), r.get("yeni"), r.get("yinelenen"), r.get("eksik"))

    # ------------------------------------------------------------------ API'nin kullandığı işlemler
    def calisiyor(self) -> bool:
        e = self._ekli
        return bool(e and e.alici is not None and e.alici.calisiyor())

    def alici(self):
        e = self._ekli
        return e.alici if e else None

    def ayarla(self, acik: bool) -> dict:
        self.y.ayarlar.guncelle(telefon_aktarimi=bool(acik))
        self.uyumlandir()
        return self.durum()

    def kod_uret(self) -> dict:
        with self._kilit:
            a = self.alici()
            if a is None:
                raise IslemHatasi("Önce telefondan aktarımı açın (uygulama açık olmalı).", "telefon_kapali")
            adresler = self._adresler() if callable(self._adresler) else self._adresler
            kod = a.eslestirme_kodu_uret(KOD_SURESI_S, adresler)
            self.kod_bitis = time.monotonic() + KOD_SURESI_S
            return {"kod": kod, "sure_s": KOD_SURESI_S}

    def cihazlar(self) -> list[dict]:
        u = self.y.uygulama
        if u is None:
            return []
        return [{"id": c["device_id"], "ad": c["name"], "platform": c["platform"], "eslesme": c["paired_at"],
                 "son_gorulme": c["last_seen"], "iptal": c["revoked"]} for c in u.hub.cihazlar() if c["eslesmis"]]

    def cihaz_kaldir(self, device_id: str) -> dict:
        u = self.y.uygulama
        if u is None:
            raise IslemHatasi("Önce ilk açılış sihirbazını tamamlayın.", "sihirbaz_gerekli")
        if not isinstance(device_id, str) or not u.hub.cihaz_iptal(device_id):
            raise IslemHatasi("Böyle bir eşleşmiş cihaz yok.", "yok")
        gunluk.log().info("telefon eşleştirmesi kaldırıldı")
        return self.durum()

    def _adres_listesi(self) -> list[str]:
        if self._adresler is not None:
            return list(self._adresler() if callable(self._adresler) else self._adresler)
        try:
            from kimlikserver.aktarim import yerel_ipv4_adresleri
            return list(yerel_ipv4_adresleri())
        except Exception:   # noqa: BLE001
            return []

    def durum(self) -> dict:
        with self._kilit:
            a = self.alici()
            d = a.durum() if a is not None else None
            neden = d["eslestirme_kodu_gecersizlik_nedeni"] if d else None
            kalan = None
            if d and d["eslestirme_kodu_gecerli"] and self.kod_bitis is not None:
                kalan = max(0, int(self.kod_bitis - time.monotonic()))
            cihazlar = self.cihazlar()
            with self._alim_kilit:
                son_alim, toplam_yeni = (dict(self.son_alim) if self.son_alim else None), self.toplam_yeni
            return {
                "acik": bool(self.y.ayarlar["telefon_aktarimi"]), "calisiyor": bool(d and d["calisiyor"]),
                "uygulama_acik": self.y.uygulama is not None,
                "port": d["port"] if d else None, "adresler": self._adres_listesi() if d else [],
                "pc_adi": d["pc_adi"] if d else None, "parmak_izi": d["parmak_izi"] if d else None,
                "sertifika_yenilendi": bool(d and d["sertifika_yenilendi"]), "uyari": d["uyari"] if d else None,
                "kod_gecerli": bool(d and d["eslestirme_kodu_gecerli"]), "kod_kalan_s": kalan,
                "kod_gecersizlik_nedeni": neden, "kod_gecersizlik_metni": GECERSIZLIK_METINLERI.get(neden or "", None),
                "alinan_dosya": d["alinan_dosya"] if d else 0,
                "son_alim": son_alim, "toplam_yeni": toplam_yeni, "hata": self.hata,
                "cihazlar": cihazlar,
            }

    def rapor_satiri(self) -> str:
        """Hata raporu için YALNIZ sayılar/durum (kod, anahtar, adres yok)."""
        with self._alim_kilit:
            s = dict(self.son_alim) if self.son_alim else None
        son = f"dosya={s['dosya']} yeni={s['yeni']} yinelenen={s['yinelenen']} eksik={s['eksik']}" if s else "yok"
        n = sum(1 for c in self.cihazlar() if not c["iptal"])
        return f"Telefon aktarımı: {'açık' if self.y.ayarlar['telefon_aktarimi'] else 'kapalı'}; " \
               f"eşleşmiş cihaz: {n}; son alım: {son}"
