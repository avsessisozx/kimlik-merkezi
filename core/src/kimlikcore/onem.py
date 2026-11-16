"""Olay önem ağırlığı (şema v5, `events.onem`). Ayrıntı: docs/SEMA.md.

0 = düşük, 1 = olağan, 2 = yüksek (kullanıcının kendi yazdığı içerik). Kural tablosu veri
olarak tek yerdedir; `onem_hesapla` onu uygular.
"""
from __future__ import annotations

from typing import Any

DUSUK, OLAGAN, YUKSEK = 0, 1, 2

# kind'ın SON parçası (nokta ile ayrılmış) bunlardan biriyse kullanıcının kendi yazdığıdır.
YUKSEK_SON_PARCALAR = frozenset({"gonderi", "yorum"})
YUKSEK_KATEGORILER = frozenset({"notlar"})
YUKSEK_KINDLAR = frozenset({"github.depo", "github.issue", "github.pr"})

# Etkileşim izi (kullanıcı bir şey yazmadı): düşük önem.
DUSUK_SON_PARCALAR = frozenset({
    "begeni", "takip", "takipci", "tepki", "oy", "abone", "abonelik", "arkadas", "kaydedilen",
    "yildiz",
})
# Yalnız tam kind eşleşmesi: `youtube.izleme` DÜŞÜK DEĞİLDİR (1 kalır).
DUSUK_KINDLAR = frozenset({"github.izleme"})

# sohbet.mesaj: payload.rol'e göre.
SOHBET_KIND = "sohbet.mesaj"
SOHBET_ROL_ONEM = {"kullanici": YUKSEK, "asistan": DUSUK}


def onem_hesapla(kind: str, category: str, payload: dict[str, Any]) -> int:
    kind = (kind or "").lower()
    if kind == SOHBET_KIND:
        rol = payload.get("rol") if isinstance(payload, dict) else None
        return SOHBET_ROL_ONEM.get(rol, OLAGAN) if isinstance(rol, str) else OLAGAN
    son = kind.rsplit(".", 1)[-1]
    if son in YUKSEK_SON_PARCALAR or category in YUKSEK_KATEGORILER or kind in YUKSEK_KINDLAR:
        return YUKSEK
    if son in DUSUK_SON_PARCALAR or kind in DUSUK_KINDLAR:
        return DUSUK
    return OLAGAN
