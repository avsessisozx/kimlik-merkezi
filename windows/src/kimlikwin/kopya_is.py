"""'Sohbet kopyalarını denetle' işi: çekirdekteki kopya raporu/temizleme, arka planda.

Rapor yalnız SAYI içerir (metin, başlık, konuşma kimliği, dosya yolu taşımaz). Denetleme salt okurdur;
yalnız `uygula=True` ile kayıtlar GİZLENİR (silinmez, tombstone'lu; çekirdeğin kuralı)."""
from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from kimlikcore import KimlikError


def ozet_metni(r: dict[str, Any], paket_verildi: bool) -> str:
    """Sade Türkçe özet (yalnız sayılar)."""
    if r["uygulandi"]:
        s = (f"{r['tam_kopya']} kopya mesaj ve {r['dal_disi']} yeniden üretilmiş cevap gizlendi. "
             f"{r['kalacak']} mesaj kalıyor. Kayıtlar silinmedi, yalnız gizlendi.")
    else:
        s = (f"{r['tam_kopya']} kopya mesaj ve {r['dal_disi']} yeniden üretilmiş cevap bulundu. "
             f"{r['kalacak']} mesaj kalacak. Henüz hiçbir şey değiştirilmedi.")
    if r["geri_acilan"]:
        s += (f" Yanlışlıkla kopya sayılıp gizlenmiş {r['geri_acilan']} kayıt geri açıldı." if r["uygulandi"]
              else f" Yanlışlıkla kopya sayılıp gizlenmiş {r['geri_acilan']} kayıt geri açılacak.")
    if r["zamani_belirsiz"]:
        s += f" Zamanı belirsiz {r['zamani_belirsiz']} mesaj kopya denetimine alınmadı."
    if r["atlanan_konusma"]:
        s += (f" {r['atlanan_konusma']} konuşmanın tüm mesajları yeniden üretilmiş görünüyordu; dışa aktarma "
              "dosyası başka bir sürümden olabileceği için bu konuşmalara dokunulmadı.")
    if not paket_verildi:
        s += " Yeniden üretilmiş cevaplar yalnız ChatGPT dışa aktarma dosyası da seçilirse bulunur."
    return s


def rapor_metni(r: dict[str, Any]) -> str:
    """'Raporu kopyala' için düz metin (yalnız sayılar)."""
    satirlar = [f"İncelenen mesaj: {r['incelenen']}", f"Kopya mesaj: {r['tam_kopya']}",
                f"Yeniden üretilmiş cevap: {r['dal_disi']}", f"Kalacak mesaj: {r['kalacak']}",
                f"Zamanı belirsiz: {r['zamani_belirsiz']}", f"Geri açılan: {r['geri_acilan']}",
                f"Etkilenen konuşma: {r['etkilenen_konusma']}", f"Dokunulmayan konuşma: {r['atlanan_konusma']}",
                "Uygulandı (kayıtlar gizlendi): " + ("evet" if r["uygulandi"] else "hayır")]
    for ad, d in sorted(r["platforma_gore"].items()):
        satirlar.append(f"Platform {ad}: kopya {d['tam_kopya']}, yeniden üretilmiş {d['dal_disi']}")
    for ad, d in sorted(r["role_gore"].items()):
        satirlar.append(f"Rol {ad}: kopya {d['tam_kopya']}, yeniden üretilmiş {d['dal_disi']}")
    return "\n".join(satirlar)


class KopyaIsi:
    def __init__(self, hub, uygula: bool, paket: str | None):
        self.hub, self.uygula, self.paket = hub, uygula, paket
        self.durum = "calisiyor"        # calisiyor | bitti | hata
        self.rapor: dict[str, Any] | None = None
        self.ozet: str | None = None
        self.metin: str | None = None
        self.hata: str | None = None
        self._kilit = threading.Lock()
        self._is = threading.Thread(target=self._calis, daemon=True, name="kopya")

    def baslat(self) -> None:
        self._is.start()

    def _calis(self) -> None:
        from kimlikcore.cli import _paketten_anahtarlar
        from kimlikcore.kopya import kopya_raporu, kopya_temizle
        try:
            gecerli = _paketten_anahtarlar(Path(self.paket)) if self.paket else None
            r = (kopya_temizle if self.uygula else kopya_raporu)(self.hub, gecerli_anahtarlar=gecerli)
            with self._kilit:
                self.rapor, self.ozet, self.metin, self.durum = r, ozet_metni(r, bool(self.paket)), rapor_metni(r), "bitti"
        except KimlikError as e:        # çekirdeğin Türkçe, yol içermeyen iletileri (Paket tanınmadı vb.)
            with self._kilit:
                self.hata, self.durum = str(e), "hata"
        except BaseException as e:      # iletiyi koyma: yol/dosya adı içerebilir
            with self._kilit:
                self.hata, self.durum = f"Denetim tamamlanamadı ({type(e).__name__}).", "hata"

    @property
    def canli(self) -> bool:
        return self._is.is_alive()

    def to_dict(self) -> dict[str, Any]:
        with self._kilit:
            return {"durum": self.durum, "uygula": self.uygula, "paket_verildi": bool(self.paket),
                    "rapor": self.rapor, "ozet": self.ozet, "metin": self.metin, "hata": self.hata}
