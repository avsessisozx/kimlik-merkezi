"""Türkçe katlama (normalizasyon) ve FTS sorgu üretimi.

Varsayılan FTS5 ayarına güvenilmez: metin FTS'e girmeden ve sorgu verilmeden önce
aynı `fold` işleminden geçer. Katlama: İ/I/ı -> i, aksanlar atılır (ç->c, ğ->g,
ş->s, ö->o, ü->u, â->a ...), küçük harfe çevrilir. Böylece "ışık", "ISIK", "Işık"
ve "isik" aynı belirtece (isik) iner; "İstanbul" ve "istanbul" aynı olur.
Bedeli: ASCII ile yazılmış "isik" da "ışık"ı bulur (aksan duyarsız arama).
"""
from __future__ import annotations

import re
import unicodedata

_TR = str.maketrans({"İ": "i", "I": "i", "ı": "i"})
_TOKEN = re.compile(r"[^\W_]+")
_QUERY_PART = re.compile(r'"([^"]*)"|(\S+)')


def fold(text: str) -> str:
    s = text.translate(_TR)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.casefold()


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(fold(text))


def build_fts_query(query: str, *, prefix: bool = False) -> str | None:
    """Kullanıcı sorgusunu güvenli FTS5 ifadesine çevirir (hepsi VE).

    - `kelime`        -> "kelime"
    - `"iki kelime"`  -> "iki kelime" (tümce)
    - `kel*`          -> "kel"* (önek)
    - `e-posta`       -> "e posta" (FTS5'in böldüğü gibi tümce)
    FTS5 işleçleri (AND/OR/NEAR/sütun:) kullanıcıdan alınmaz; hepsi metin sayılır.
    Terim çıkmazsa None döner.
    """
    parts: list[str] = []
    for m in _QUERY_PART.finditer(query):
        phrase, bare = m.group(1), m.group(2)
        if phrase is not None:
            toks = tokens(phrase)
            if toks:
                parts.append('"' + " ".join(toks) + '"' + ("*" if prefix else ""))
            continue
        toks = tokens(bare)
        if not toks:
            continue
        star = prefix or bare.endswith("*")
        parts.append('"' + " ".join(toks) + '"' + ("*" if star else ""))
    return " ".join(parts) if parts else None
