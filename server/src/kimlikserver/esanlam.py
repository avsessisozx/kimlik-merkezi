"""`ara` için eşanlamlı / ilişkili terim genişletmesi.

- Veri: `veri/esanlamlilar.json` (paket içi) + isteğe bağlı kullanıcı dosyası
  `<veri klasörü>/esanlamlilar.json` ya da `KIMLIK_ESANLAM` ortam değişkenindeki yol. Biçim:
  `esanlamlilar`: [[a, b, c], ...] (iki yönlü gruplar), `alt_kavramlar`: {genel: [özel, ...]}
  (tek yönlü: "linux" -> dağıtım adları; "fedora" aramak "linux"u getirmez).
- Anahtarlar Türkçe katlanmış (`kimlikcore.turkish.fold`) karşılaştırılır.
- Genişletme tek adımdır (zincir yok), terim başına en çok `TERIM_BASINA` ilişkili terim ve
  sorgu başına en çok `VARYANT_UST` değişken üretilir. Orijinal sorgu her zaman önce ve ayrıca aranır.
- Ne olduğu kullanıcıya/yapay zekâya görünür: `ara` çıktısında `genisletilen_terimler` ve
  her kayıtta `eslesen_terim`.
- Bu bir dil modeli ya da kök bulucu değildir; listede olmayan sözcük genişletilmez.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from kimlikcore.turkish import _QUERY_PART, tokens

log = logging.getLogger("kimlikserver")

TERIM_BASINA = 12
VARYANT_UST = 16
MAX_DOSYA = 256 * 1024
KULLANICI_DOSYASI = "esanlamlilar.json"


def _anahtar(terim: str) -> str:
    return " ".join(tokens(terim))


@dataclass(frozen=True)
class Sozluk:
    esanlam: dict[str, tuple[str, ...]]   # katlanmış anahtar -> gruptaki DİĞER terimler (özgün yazım)
    alt: dict[str, tuple[str, ...]]       # katlanmış anahtar -> özel terimler

    @classmethod
    def kur(cls, veri: dict) -> "Sozluk":
        es: dict[str, list[str]] = {}
        for grup in veri.get("esanlamlilar", []):
            uyeler = [str(t).strip() for t in grup if isinstance(t, str) and _anahtar(t)]
            for t in uyeler:
                k = _anahtar(t)
                es.setdefault(k, [])
                es[k] += [u for u in uyeler if _anahtar(u) != k and u not in es[k]]
        alt: dict[str, list[str]] = {}
        for genel, ozeller in (veri.get("alt_kavramlar") or {}).items():
            k = _anahtar(str(genel))
            if k and isinstance(ozeller, list):
                alt.setdefault(k, [])
                alt[k] += [str(o).strip() for o in ozeller
                           if isinstance(o, str) and _anahtar(o) and str(o).strip() not in alt[k]]
        return cls({k: tuple(v) for k, v in es.items()}, {k: tuple(v) for k, v in alt.items()})

    def genislet(self, terim: str) -> list[str]:
        """`terim` için ilişkili terimler (kendisi hariç, sıralı, tekrarsız, katlanmış karşılaştırma)."""
        k = _anahtar(terim)
        if not k:
            return []
        out: list[str] = []
        goruldu = {k}

        def ekle(adaylar):
            for a in adaylar:
                ak = _anahtar(a)
                if ak and ak not in goruldu:
                    goruldu.add(ak)
                    out.append(a)
        es = self.esanlam.get(k, ())
        ekle(es)
        ekle(self.alt.get(k, ()))
        for e in es:  # eşanlamlının özel terimleri de (tek adım: eşanlamlı -> alt kavram)
            ekle(self.alt.get(_anahtar(e), ()))
        return out[:TERIM_BASINA]

    def bos_mu(self) -> bool:
        return not self.esanlam and not self.alt


def _oku(yol) -> dict:
    try:
        if isinstance(yol, Path) and yol.stat().st_size > MAX_DOSYA:
            log.warning("esanlam: dosya çok büyük, atlandı")
            return {}
        d = json.loads(yol.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def varsayilan_veri() -> dict:
    return _oku(resources.files("kimlikserver").joinpath("veri", "esanlamlilar.json"))


def yukle(veri_klasoru: Path | str | None = None, ortam: dict[str, str] | None = None) -> Sozluk:
    """Paket içi sözlük + (varsa) kullanıcı dosyaları, birleştirilmiş. Bozuk/eksik dosya atlanır."""
    ortam = os.environ if ortam is None else ortam
    temel = varsayilan_veri()
    es = list(temel.get("esanlamlilar", []))
    alt = {k: list(v) for k, v in (temel.get("alt_kavramlar") or {}).items()}
    ekler = []
    if veri_klasoru is not None:
        ekler.append(Path(veri_klasoru) / KULLANICI_DOSYASI)
    if ortam.get("KIMLIK_ESANLAM"):
        ekler.append(Path(ortam["KIMLIK_ESANLAM"]))
    for yol in ekler:
        if not yol.is_file():
            continue
        d = _oku(yol)
        es += d.get("esanlamlilar", []) if isinstance(d.get("esanlamlilar"), list) else []
        for k, v in (d.get("alt_kavramlar") or {}).items() if isinstance(d.get("alt_kavramlar"), dict) else []:
            if isinstance(v, list):
                alt.setdefault(k, [])
                alt[k] += v
    return Sozluk.kur({"esanlamlilar": es, "alt_kavramlar": alt})


# ---------------------------------------------------------------------- sorgu değişkenleri
@dataclass(frozen=True)
class Varyant:
    sorgu: str              # FTS için (build_fts_query'ye verilir)
    eslesen_terim: str      # kayda yazılacak: bulunan ilişkili terim
    asil_terim: str         # sorgudaki hangi terimden türedi


def _parcalar(sorgu: str) -> list[tuple[str, bool]]:
    """(ham metin, tırnaklı mı). Önek yıldızlı terimler genişletilmez ("kel*")."""
    out = []
    for m in _QUERY_PART.finditer(sorgu):
        if m.group(1) is not None:
            if tokens(m.group(1)):
                out.append((m.group(1), True))
        elif tokens(m.group(2)):
            out.append((m.group(2), False))
    return out


def _tirnakla(metin: str) -> str:
    return '"' + " ".join(tokens(metin)) + '"'


def varyantlar(sorgu: str, sozluk: Sozluk) -> list[Varyant]:
    """Orijinal sorgu HARİÇ: bir seferde TEK terimi ilişkili terimle değiştirilmiş sorgular.
    Tüm sorgu (ör. `yarı maraton`) sözlükte bir anahtarsa o tek terim sayılır."""
    parcalar = _parcalar(sorgu)
    if not parcalar or sozluk.bos_mu():
        return []
    tum = " ".join(tokens(sorgu))
    birimler: list[tuple[str, list[str] | None]]
    if len(parcalar) > 1 and (tum in sozluk.esanlam or tum in sozluk.alt):
        birimler = [(sorgu.strip().strip('"'), None)]
    else:
        birimler = [(p[0], None) for p in parcalar]
    out: list[Varyant] = []
    goruldu: set[str] = set()
    for i, (ham_terim, _) in enumerate(birimler):
        if ham_terim.rstrip().endswith("*"):
            continue
        for r in sozluk.genislet(ham_terim):
            if len(birimler) == 1:
                q = _tirnakla(r)
            else:
                q = " ".join(_tirnakla(r) if j == i else (
                    '"' + " ".join(tokens(p[0])) + '"' if p[1] else p[0])
                    for j, p in enumerate(parcalar))
            if q in goruldu:
                continue
            goruldu.add(q)
            out.append(Varyant(q, r, ham_terim.strip()))
            if len(out) >= VARYANT_UST:
                return out
    return out
