"""Konu bazında hassasiyet işareti (şema v5, `events.hassas_konu`). Ayrıntı ve SINIRLAR: docs/SEMA.md.

Yöntem yalnız bir sözcük listesidir: metin `fold()` ile katlanır, sözcüklere ayrılır, listedeki
terimlerle eşleşir. Bağlamı anlamaz; yanlış pozitif ve negatif olur. Yalnız `events.text` bakılır.
Liste paket verisidir (`veri/hassas_konular.json`, importlib.resources); veri klasöründeki
`hassas_konular.json` ona EKLENİR (`"cikar": [...]` ile terim çıkarılır).
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from .turkish import tokens

EK_DOSYA = "hassas_konular.json"
MIN_KOK = 4


class HassasListeHatasi(ValueError):
    """Terim listesi geçersiz (bozuk ek dosya vb.)."""


def _liste(v: Any, ne: str) -> list[str]:
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise HassasListeHatasi(f"{ne} metin listesi olmalı.")
    return v


def _oku_json(data: bytes | str, ne: str) -> dict[str, Any]:
    try:
        d = json.loads(data)
    except ValueError as e:
        raise HassasListeHatasi(f"{ne} geçerli JSON değil.") from e
    if not isinstance(d, dict):
        raise HassasListeHatasi(f"{ne} bir nesne olmalı.")
    return d


def _konular(d: dict[str, Any], ne: str) -> dict[str, tuple[list[str], list[str]]]:
    k = d.get("konular", {})
    if not isinstance(k, dict):
        raise HassasListeHatasi(f"{ne}: 'konular' bir nesne olmalı.")
    out: dict[str, tuple[list[str], list[str]]] = {}
    for kid, v in k.items():
        if not isinstance(v, dict) or not kid or not isinstance(kid, str) or "," in kid:
            raise HassasListeHatasi(f"{ne}: konu {kid!r} geçersiz.")
        out[kid] = (_liste(v.get("terimler", []), f"{ne}: {kid}.terimler"),
                    _liste(v.get("tam", []), f"{ne}: {kid}.tam"))
    return out


def _paket_ham() -> dict[str, Any]:
    return _oku_json(
        resources.files("kimlikcore").joinpath("veri", "hassas_konular.json").read_bytes(), "paket listesi")


class Siniflandirici:
    """Derlenmiş eşleştirici. Bir kez kurulur; `konular(metin)` hızlıdır."""

    def __init__(self, konular: dict[str, tuple[list[str], list[str]]], cikar: set[str] | None = None):
        cikar_kat = {" ".join(tokens(c)) for c in (cikar or ())}
        self._onek: dict[str, list[tuple[str, str]]] = {}      # ilk 4 harf -> [(kök, konu)]
        self._tam: dict[str, set[str]] = {}                    # sözcük -> konular
        self._oz: dict[str, list[tuple[tuple[str, ...], str]]] = {}   # ilk sözcük -> [(devam, konu)]
        self.konu_idleri = sorted(konular)
        for kid in sorted(konular):
            terimler, tam = konular[kid]
            for t in terimler:
                w = tokens(t)
                if not w or " ".join(w) in cikar_kat:
                    continue
                if len(w) == 1:
                    if len(w[0]) < MIN_KOK:
                        raise HassasListeHatasi(
                            f"{kid}: tek sözcüklü terim en az {MIN_KOK} harf olmalı (kısaysa 'tam' listesine): {t!r}")
                    self._onek.setdefault(w[0][:MIN_KOK], []).append((w[0], kid))
                else:
                    self._oz.setdefault(w[0], []).append((tuple(w[1:]), kid))
            for t in tam:
                w = tokens(t)
                if len(w) != 1:
                    raise HassasListeHatasi(f"{kid}: 'tam' terimi tek sözcük olmalı: {t!r}")
                if w[0] in cikar_kat:
                    continue
                self._tam.setdefault(w[0], set()).add(kid)

    def konular(self, metin: str) -> list[str]:
        if not metin or not metin.strip():
            return []
        w = tokens(metin)
        bulunan: set[str] = set()
        onek, tam, oz = self._onek, self._tam, self._oz
        n = len(w)
        for i, s in enumerate(w):
            k = tam.get(s)
            if k:
                bulunan |= k
            if len(s) >= MIN_KOK:
                aday = onek.get(s[:MIN_KOK])
                if aday:
                    for kok, kid in aday:
                        if s.startswith(kok):
                            bulunan.add(kid)
            ph = oz.get(s)
            if ph:
                for devam, kid in ph:
                    m = len(devam)
                    if i + m >= n or kid in bulunan:
                        continue
                    if w[i + 1:i + m] == list(devam[:-1]) and w[i + m].startswith(devam[-1]):
                        bulunan.add(kid)
        return sorted(bulunan)


def _derle(ham: dict[str, Any], ek: dict[str, Any] | None) -> Siniflandirici:
    kon = _konular(ham, "paket listesi")
    cikar: set[str] = set()
    if ek is not None:
        for kid, (ter, tam) in _konular(ek, "ek dosya").items():
            o_ter, o_tam = kon.get(kid, ([], []))
            kon[kid] = (o_ter + ter, o_tam + tam)
        cikar = set(_liste(ek.get("cikar", []), "ek dosya: cikar"))
    return Siniflandirici(kon, cikar)


@lru_cache(maxsize=1)
def paket_siniflandirici() -> Siniflandirici:
    return _derle(_paket_ham(), None)


def yukle(veri_klasoru: Path | str | None) -> tuple[Siniflandirici, str | None]:
    """(sınıflandırıcı, uyarı). Ek dosya yoksa paket listesi; bozuksa paket listesi + uyarı."""
    if veri_klasoru is not None:
        yol = Path(veri_klasoru) / EK_DOSYA
        if yol.is_file():
            try:
                return _derle(_paket_ham(), _oku_json(yol.read_bytes(), f"{EK_DOSYA} (ek liste)")), None
            except (HassasListeHatasi, OSError, UnicodeDecodeError) as e:
                return paket_siniflandirici(), (
                    f"{EK_DOSYA} kullanılamadı ({e}); yalnız paket listesi kullanılıyor.")
    return paket_siniflandirici(), None


def hassas_konulari(text: str) -> list[str]:
    """Paket listesiyle (ek dosya olmadan) konu kimlikleri, alfabetik."""
    return paket_siniflandirici().konular(text)


def isaret(konular: list[str]) -> str | None:
    """`events.hassas_konu` değeri: boşsa NULL, değilse alfabetik virgüllü."""
    return ",".join(konular) if konular else None
