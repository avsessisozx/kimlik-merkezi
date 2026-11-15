"""Sohbet kayıtlarındaki kopyaları bulur ve (isteğe bağlı) gizler.

K1 "tam kopya": aynı platform + rol + ts + metin (kırpılmış) olan sohbet mesajları; en küçük
`seq` kalır. K2 "dal dışı": `gecerli_anahtarlar` ({konusma_id: güncel dalın event_key kümesi})
verilirse, o konuşmalarda kümede olmayan mesajlar. Sözlükte olmayan konuşmalara ve sohbet
dışı kayıtlara dokunulmaz. Rapor yalnız sayı içerir (metin, başlık, konuşma kimliği yok).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from .errors import HubReadOnlyError
from .hub import Hub

NEDEN_TAM = "kopya:tam"
NEDEN_DAL = "kopya:dal_disi"

_SQL = (
    "SELECT seq, event_id, event_key, ts, text, "
    "json_extract(payload, '$.platform'), json_extract(payload, '$.rol'), "
    "json_extract(payload, '$.konusma_id'), json_extract(payload, '$.ts') "
    "FROM events WHERE kind = 'sohbet.mesaj' AND hidden = 0 ORDER BY seq"
)


def _sec(hub: Hub, gecerli: Mapping[str, set[str]] | None) -> dict[str, Any]:
    rows = hub.query(_SQL)
    dal: list[tuple[str, str, str]] = []  # (event_id, platform, rol)
    kume: dict[tuple, list[tuple[str, str, str]]] = defaultdict(list)
    for _seq, eid, ekey, ts, text, plat, rol, kid, pts in rows:
        plat = "" if plat is None else str(plat)
        rol = "" if rol is None else str(rol)
        if gecerli is not None and kid in gecerli and ekey not in gecerli[kid]:
            dal.append((eid, plat, rol))
            continue
        if not ts or not pts:  # zamanı olmayan mesaj (içe aktarıcı üst zamanı yedek verir): eşleştirilmez
            continue
        kume[(plat, rol, ts, (text or "").strip())].append((eid, plat, rol))
    tam: list[tuple[str, str, str]] = []
    kume_sayisi = 0
    for uyeler in kume.values():
        if len(uyeler) > 1:
            kume_sayisi += 1
            tam.extend(uyeler[1:])  # satırlar seq sırasıyla geldi: ilki (en küçük seq) kalır
    return {"incelenen": len(rows), "tam": tam, "dal": dal, "kume": kume_sayisi}


def _rapor(s: dict[str, Any], uygulandi: bool) -> dict[str, Any]:
    plat: dict[str, dict[str, int]] = {}
    rol: dict[str, dict[str, int]] = {}
    for anahtar, liste in (("tam_kopya", s["tam"]), ("dal_disi", s["dal"])):
        for _eid, p, r in liste:
            plat.setdefault(p, {"tam_kopya": 0, "dal_disi": 0})[anahtar] += 1
            rol.setdefault(r, {"tam_kopya": 0, "dal_disi": 0})[anahtar] += 1
    return {
        "incelenen": s["incelenen"],
        "tam_kopya": len(s["tam"]),
        "tam_kopya_kume": s["kume"],
        "dal_disi": len(s["dal"]),
        "kalacak": s["incelenen"] - len(s["tam"]) - len(s["dal"]),
        "platforma_gore": plat,
        "role_gore": rol,
        "uygulandi": uygulandi,
    }


def kopya_raporu(hub: Hub, *, gecerli_anahtarlar: Mapping[str, set[str]] | None = None) -> dict[str, Any]:
    """Salt okur: hiçbir şey değiştirmez."""
    return _rapor(_sec(hub, gecerli_anahtarlar), False)


def kopya_temizle(hub: Hub, *, gecerli_anahtarlar: Mapping[str, set[str]] | None = None) -> dict[str, Any]:
    """Aynı kuralla seçilen kayıtları gizler (her biri için tombstone). Yazan Hub ister."""
    if not hub.writable:
        raise HubReadOnlyError("Hub salt okunur açıldı; yazma işlemi yapılamaz.")
    s = _sec(hub, gecerli_anahtarlar)
    if s["dal"]:
        hub.hide_events([e for e, _p, _r in s["dal"]], NEDEN_DAL)
    if s["tam"]:
        hub.hide_events([e for e, _p, _r in s["tam"]], NEDEN_TAM)
    return _rapor(s, True)
