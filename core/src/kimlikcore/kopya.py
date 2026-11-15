"""Sohbet kayıtlarındaki kopyaları bulur ve (isteğe bağlı) gizler.

K1 "tam kopya": aynı platform + rol + ts + metin (kırpılmış) olan sohbet mesajları. Kalan:
`gecerli_anahtarlar` verildiyse geçerli dalda olan, yoksa en küçük `seq`. Zamanı konuşmanın
başlık olayının zamanına eşit mesajlar (içe aktarıcı yedek zaman yazmış olabilir) K1'e girmez.
K2 "dal dışı": `gecerli_anahtarlar` ({konusma_id: güncel dalın event_key kümesi}) verilirse, o
konuşmalarda kümede olmayan mesajlar. Görünür mesajlarının TAMAMI dal dışı çıkan konuşma
atlanır (paket başka sürümden olabilir). Sözlükte olmayan konuşmalara ve sohbet dışı kayıtlara
dokunulmaz. Daha önce `kopya:` nedeniyle gizlenmiş ama geçerli dalda olan kayıt, kümesinde görünür
geçerli kayıt yoksa geri açılır. Rapor yalnız sayı içerir (metin, başlık, konuşma kimliği yok).
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from .errors import HubReadOnlyError
from .hub import Hub

NEDEN_TAM = "kopya:tam"
NEDEN_DAL = "kopya:dal_disi"

_ALANLAR = (
    "e.event_id, e.event_key, e.ts, e.text, "
    "json_extract(e.payload, '$.platform'), json_extract(e.payload, '$.rol'), "
    "json_extract(e.payload, '$.konusma_id'), json_extract(e.payload, '$.ts')"
)
_SQL_GORUNUR = f"SELECT {_ALANLAR} FROM events e WHERE e.kind = 'sohbet.mesaj' AND e.hidden = 0 ORDER BY e.seq"
_SQL_BASLIK = (
    "SELECT json_extract(payload, '$.platform'), json_extract(payload, '$.konusma_id'), ts "
    "FROM events WHERE kind = 'sohbet.konusma'"
)
# kopya olarak gizlenmiş, kaynağı kaldırılmamış mesajlar (geri açma adayı)
_SQL_ADAY = (
    f"SELECT {_ALANLAR} FROM events e JOIN sources s ON s.source_id = e.source_id "
    "WHERE e.kind = 'sohbet.mesaj' AND e.hidden = 1 AND s.removed_at IS NULL AND EXISTS ("
    "SELECT 1 FROM tombstones t WHERE t.kind = 'event_hidden' AND t.event_id = e.event_id "
    "AND t.reason LIKE 'kopya:%') ORDER BY e.seq"
)


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _sec(hub: Hub, gecerli: Mapping[str, set[str]] | None) -> dict[str, Any]:
    baslik_ts: dict[tuple[str, str], str] = {}
    hub.query_each(_SQL_BASLIK, (), lambda r: baslik_ts.__setitem__((_s(r[0]), _s(r[1])), r[2]))

    # gorunur: (eid, plat, rol, kid, gecerli_mi, k1anahtar | None)
    gorunur: list[tuple] = []
    adaylar: list[tuple] = []
    belirsiz = 0

    def satir(r: tuple, aday: bool) -> tuple | None:
        nonlocal belirsiz
        eid, ekey, ts, text, plat, rol, kid, pts = r
        plat, rol = _s(plat), _s(rol)
        flag = None if gecerli is None or kid not in gecerli else (ekey in gecerli[kid])
        k1 = None
        if ts and pts:
            if baslik_ts.get((plat, _s(kid))) == ts:
                if not aday:
                    belirsiz += 1
            else:
                k1 = (plat, rol, ts, hashlib.sha1((text or "").strip().encode("utf-8", "surrogatepass")).digest())
        return (eid, plat, rol, _s(kid), flag, k1)

    hub.query_each(_SQL_GORUNUR, (), lambda r: gorunur.append(satir(r, False)))
    if gecerli is not None:
        def _aday(r):
            t = satir(r, True)
            if t[4] is True and t[5] is not None:
                adaylar.append(t)
        hub.query_each(_SQL_ADAY, (), _aday)

    # konuşma başına sayımlar (K2 güvenlik sınırı)
    gor, dal_n, aday_n = defaultdict(int), defaultdict(int), defaultdict(int)
    for t in gorunur:
        gor[t[3]] += 1
        if t[4] is False:
            dal_n[t[3]] += 1
    for t in adaylar:
        aday_n[t[3]] += 1
    atlanan = {k for k, n in dal_n.items() if n == gor[k] and aday_n[k] == 0}

    dal = [t for t in gorunur if t[4] is False and t[3] not in atlanan]
    dal_kimlik = {t[0] for t in dal}

    gruplar: dict[tuple, list[list[tuple]]] = {}  # anahtar -> [görünür üyeler, adaylar]
    for t in gorunur:
        if t[0] in dal_kimlik or t[5] is None:
            continue
        gruplar.setdefault(t[5], [[], []])[0].append(t)
    for t in adaylar:
        if t[3] in atlanan:
            continue
        gruplar.setdefault(t[5], [[], []])[1].append(t)

    tam: list[tuple] = []
    geri: list[str] = []
    kume = 0
    for gor_u, adayl in gruplar.values():
        gecerli_gor = next((t for t in gor_u if t[4] is True), None)
        if gecerli_gor is not None:
            kalan = gecerli_gor
            digerleri = [t for t in gor_u if t is not kalan]
        elif adayl:
            geri.append(adayl[0][0])
            digerleri = gor_u
        else:
            digerleri = gor_u[1:]
        if digerleri:
            kume += 1
            tam.extend(digerleri)
    etkilenen = sum(1 for n in dal_n.values() if n)
    return {"incelenen": len(gorunur), "tam": tam, "dal": dal, "kume": kume, "geri": geri,
            "belirsiz": belirsiz, "etkilenen": etkilenen, "atlanan": len(atlanan)}


def _rapor(s: dict[str, Any], uygulandi: bool) -> dict[str, Any]:
    plat: dict[str, dict[str, int]] = {}
    rol: dict[str, dict[str, int]] = {}
    for anahtar, liste in (("tam_kopya", s["tam"]), ("dal_disi", s["dal"])):
        for t in liste:
            plat.setdefault(t[1], {"tam_kopya": 0, "dal_disi": 0})[anahtar] += 1
            rol.setdefault(t[2], {"tam_kopya": 0, "dal_disi": 0})[anahtar] += 1
    return {
        "incelenen": s["incelenen"],
        "tam_kopya": len(s["tam"]),
        "tam_kopya_kume": s["kume"],
        "dal_disi": len(s["dal"]),
        "geri_acilan": len(s["geri"]),
        "zamani_belirsiz": s["belirsiz"],
        "etkilenen_konusma": s["etkilenen"],
        "tumu_dal_disi_konusma": s["atlanan"],
        "atlanan_konusma": s["atlanan"],
        "kalacak": s["incelenen"] - len(s["tam"]) - len(s["dal"]) + len(s["geri"]),
        "platforma_gore": plat,
        "role_gore": rol,
        "uygulandi": uygulandi,
    }


def kopya_raporu(hub: Hub, *, gecerli_anahtarlar: Mapping[str, set[str]] | None = None) -> dict[str, Any]:
    """Salt okur: hiçbir şey değiştirmez."""
    return _rapor(_sec(hub, gecerli_anahtarlar), False)


def kopya_temizle(hub: Hub, *, gecerli_anahtarlar: Mapping[str, set[str]] | None = None) -> dict[str, Any]:
    """Aynı kuralla seçilenleri tek işlemde gizler/geri açar (her gizleme için tombstone). Yazan Hub ister."""
    if not hub.writable:
        raise HubReadOnlyError("Hub salt okunur açıldı; yazma işlemi yapılamaz.")
    s = _sec(hub, gecerli_anahtarlar)
    hub._kopya_uygula(
        [((t[0] for t in s["dal"]), NEDEN_DAL), ((t[0] for t in s["tam"]), NEDEN_TAM)], s["geri"])
    return _rapor(s, True)
