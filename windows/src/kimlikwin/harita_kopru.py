"""Persona Haritası köprüsü (INTERFACES §12): `kimlikserver.harita.harita/bolge` çağrılarını sarar.

- Gerçek işlevler `kimlikserver.harita` modülündedir. Modül yoksa (henüz birleşmediyse) açık bir hata
  döner; sahte veriye DÜŞÜLMEZ. Testler `saglayici` değişkenine sahte bir sağlayıcı atar.
- Savunma: kilitli hassas bölgenin hiçbir sayısı/içeriği arayüze gitmez; açık hassas bölgede de
  yalnız sayılar kalır (`en_cok`/örnek kayıtlar atılır). Sağlayıcı hata yapsa bile arayüz sızdırmaz.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

HASSAS = frozenset({"kalp", "karin", "ayak"})

# Testlerde atanır: (harita_fn, bolge_fn). Üretimde None kalır.
saglayici: tuple[Callable[..., dict], Callable[..., dict]] | None = None


class HaritaYok(Exception):
    pass


def _islevler() -> tuple[Callable[..., dict], Callable[..., dict]]:
    if saglayici is not None:
        return saglayici
    try:
        from kimlikserver.harita import bolge, harita  # type: ignore[attr-defined]
    except ImportError as e:
        raise HaritaYok("Persona haritası modülü (kimlikserver.harita) bu sürümde yok.") from e
    return harita, bolge


def harita(hub, ac_hassas: set[str]) -> dict[str, Any]:
    fn, _ = _islevler()
    veri = fn(hub, ac_hassas=frozenset(ac_hassas))
    for b in veri.get("bolgeler", []):
        if b.get("id") in HASSAS and b["id"] not in ac_hassas:
            b.update(kilitli=True, olay_sayisi=None, ilk=None, son=None, ozet="")
        else:
            b.setdefault("kilitli", False)
    return veri


def bolge(hub, bolge_id: str, ac_hassas: set[str]) -> dict[str, Any]:
    if bolge_id in HASSAS and bolge_id not in ac_hassas:
        # sağlayıcıyı hiç çağırma: kilitliyken veri okunmaz
        return {"id": bolge_id, "kilitli": True, "grafikler": [], "en_cok": [], "notlar": []}
    _, fn = _islevler()
    veri = fn(hub, bolge_id, ac_hassas=frozenset(ac_hassas))
    if bolge_id in HASSAS:
        veri["en_cok"] = []      # hassas bölgede içerik/örnek yok, yalnız sayı ve dağılım
        for g in veri.get("grafikler", []):
            g.pop("ornek", None)
    veri["kilitli"] = False
    return veri
