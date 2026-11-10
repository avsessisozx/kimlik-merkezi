"""Sağlık denetimi: veri klasörü, veritabanı, FTS, erişim kaydı, kilit, boş alan.
Salt okunur açar; çalışan uygulamanın yazan kilidini bozmaz."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from kimlikcore import Hub, KimlikError

from .veri_klasoru import bos_alan, boyut_metni


@dataclass
class Kontrol:
    ad: str
    ok: bool
    ayrinti: str


def denetle(veri: str | Path) -> dict:
    veri = Path(veri)
    kontroller: list[Kontrol] = []

    def ekle(ad: str, ok: bool, ayrinti: str = "") -> None:
        kontroller.append(Kontrol(ad, ok, ayrinti))

    ekle("veri klasörü var", veri.is_dir(), str(veri) if veri.is_dir() else "yok")
    ekle("kimlik.db var", (veri / "kimlik.db").is_file())
    eski = [a for a in ("oneri.db", "erisim.db") if (veri / a).exists()]
    ekle("eski şifresiz dosya yok (oneri.db, erisim.db)", not eski,
         ", ".join(eski) + " duruyor: uygulama açılışında ana veritabanına taşınır, taşınamadıysa silinmez" if eski else "")
    for alt in ("arsiv", "cikti"):
        ekle(f"{alt}/ klasörü var", (veri / alt).is_dir())
    try:
        with Hub.open(veri, write=False) as h:
            ekle("veritabanı açılıyor (salt okunur)", True, f"şema {h.schema_version}")
            ekle("veri şifreleme durumu", True, "şifreli" if h.sifreli else "şifresiz (kimlikmerkezi sifrele ile şifrelenir)")
            ekle("arama dizini (FTS5) çalışıyor", isinstance(h.search("a", limit=1), list))
            ekle("özet okunuyor", isinstance(h.summary(), dict))
    except (KimlikError, OSError) as e:
        ekle("veritabanı açılıyor (salt okunur)", False, f"{type(e).__name__}: {e}")
    try:
        with Hub.open(veri, write=False) as h:
            n = h.query_one("SELECT count(*) FROM access_log")[0]
        bekleyen = len(list((veri / "gelen").glob("*.gelen"))) if (veri / "gelen").is_dir() else 0
        ekle("erişim kaydı okunuyor", True, f"{n} satır" + (f", {bekleyen} kayıt işlenmeyi bekliyor" if bekleyen else ""))
    except Exception as e:  # KimlikError, sqlite3.Error, OSError
        ekle("erişim kaydı okunuyor", False, type(e).__name__)
    try:
        ekle("boş alan", True, boyut_metni(bos_alan(veri)))
    except OSError:
        ekle("boş alan", False, "okunamadı")
    return {"ok": all(k.ok for k in kontroller), "kontroller": [asdict(k) for k in kontroller]}


def metin(sonuc: dict) -> str:
    return "\n".join(f"[{'tamam' if k['ok'] else 'HATA '}] {k['ad']}" + (f": {k['ayrinti']}" if k["ayrinti"] else "")
                     for k in sonuc["kontroller"])


def json_metin(sonuc: dict) -> str:
    return json.dumps(sonuc, ensure_ascii=False, indent=2)
