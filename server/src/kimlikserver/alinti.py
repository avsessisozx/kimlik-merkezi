"""Kısa alıntı: uzun kayıt metnini en çok `n` karaktere indirir (token tasarrufu).

`terimler` verilirse (katlanmış sözcükler) alıntı ilk eşleşen terimin çevresinden alınır
(Türkçe katlamalı eşleşme; bulunamazsa baştan). Sözcük ortasından kesmemeye çalışılır; kesilen
uca "…" konur. Sonuç (üç nokta dahil) `n` karakteri aşmaz.
"""
from __future__ import annotations

from kimlikcore.turkish import fold

ALINTI_UZUNLUGU = 200
_ONCE = 60           # eşleşmeden önce göstermeye çalışılan bağlam (karakter)
_SOZCUK_PAYI = 20    # sözcük sınırı aranırken en çok bu kadar geri/ileri gidilir


def _katla_haritali(metin: str) -> tuple[str, list[int]]:
    """Katlanmış metin ve her katlanmış karakterin özgün metindeki konumu."""
    ks: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(metin):
        f = fold(ch) if not ch.isascii() else ch.lower()
        for c in f:
            ks.append(c)
            idx.append(i)
    return "".join(ks), idx


def ilk_eslesme(metin: str, terimler: list[str]) -> int | None:
    """Terimlerden herhangi birinin ilk geçtiği yer (özgün metindeki karakter konumu)."""
    terimler = [t for t in terimler if t]
    if not terimler:
        return None
    ks, idx = _katla_haritali(metin)
    en: int | None = None
    for t in terimler:
        p = ks.find(fold(t))
        if p >= 0 and (en is None or p < en):
            en = p
    return None if en is None else idx[en]


def alinti(metin: str, terimler: list[str] | None = None, n: int = ALINTI_UZUNLUGU) -> str:
    if len(metin) <= n:
        return metin
    bas = 0
    p = ilk_eslesme(metin, terimler) if terimler else None
    if p is not None:
        bas = max(0, p - _ONCE)
        if bas > 0 and not metin[bas - 1].isspace():     # sözcük ortasından başlama
            for j in range(bas, min(len(metin), bas + _SOZCUK_PAYI)):
                if metin[j].isspace():
                    if j + 1 <= p:
                        bas = j + 1
                    break
    on = "…" if bas > 0 else ""
    kalan = metin[bas:]
    if len(on) + len(kalan) <= n:
        return on + kalan
    butce = n - len(on) - 1                  # sondaki "…" için 1
    parca = metin[bas:bas + butce]
    if not metin[bas + butce].isspace():     # sözcük ortasından bitirme
        k = max(parca.rfind(" "), parca.rfind("\n"), parca.rfind("\t"))
        if k >= len(parca) - _SOZCUK_PAYI and k > 0:
            parca = parca[:k]
    return on + parca.rstrip() + "…"
