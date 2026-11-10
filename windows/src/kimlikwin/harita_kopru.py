"""Persona Haritası köprüsü (INTERFACES §12 + genişletilmiş sözleşme: filtre, aralık, kayıtlar, ayrıntı).

- Gerçek işlevler `kimlikserver.harita` modülündedir. Modül yoksa açık bir hata döner; sahte veriye
  DÜŞÜLMEZ. Testler `saglayici` değişkenine sahte bir sağlayıcı atar.
- Gerçek modül `filtre`/`aralik` parametrelerini ya da `kayitlar`/`ayrinti` işlevlerini henüz sunmuyorsa
  köprü bunu bildirir (`filtre_destegi: False`, `ozellik_yok` hatası); arayüz bunu zarifçe gösterir.
- Savunma: kilitli hassas bölgenin hiçbir sayısı/içeriği arayüze gitmez; açık hassas bölgede yalnız sayılar kalır
  (en_cok/gruplar/örnek atılır); hassas kategorili kaydın içeriği (başlık, metin, alanlar) HİÇBİR koşulda iletilmez.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, NamedTuple

from kimlikcore import Category

HASSAS = frozenset({"kalp", "karin", "ayak", "zihin"})   # zihin: yapay zekâ sohbetleri (baş çevresi, §13)
KATEGORI_BOLGE = {"mesaj": "kalp", "eposta": "karin", "konum": "ayak", "sohbet": "zihin"}


class Saglayici(NamedTuple):
    harita: Callable[..., dict]
    bolge: Callable[..., dict]
    kayitlar: Callable[..., dict] | None = None
    ayrinti: Callable[..., dict] | None = None


# Testlerde atanır. Üretimde None kalır.
saglayici: Saglayici | tuple | None = None


class HaritaYok(Exception):
    pass


class OzellikYok(Exception):
    pass


def _s() -> Saglayici:
    if saglayici is not None:
        return saglayici if isinstance(saglayici, Saglayici) else Saglayici(*saglayici)
    try:
        import kimlikserver.harita as m  # type: ignore[import-not-found]
        return Saglayici(m.harita, m.bolge, getattr(m, "kayitlar", None), getattr(m, "ayrinti", None))
    except (ImportError, AttributeError) as e:
        raise HaritaYok("Persona haritası modülü (kimlikserver.harita) bu sürümde yok.") from e


def _uygun(fn: Callable[..., Any], kw: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """Fonksiyonun kabul etmediği isteğe bağlı parametreleri ayıklar; ayıklananları döner."""
    try:
        ps = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return kw, set()
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in ps.values()):
        return kw, set()
    ok = {k: v for k, v in kw.items() if k in ps}
    return ok, set(kw) - set(ok)


def harita(hub, ac_hassas: set[str], aralik: dict | None = None) -> dict[str, Any]:
    fn = _s().harita
    kw, _ = _uygun(fn, {"ac_hassas": frozenset(ac_hassas), "aralik": aralik})
    veri = fn(hub, **kw)
    for b in veri.get("bolgeler", []):
        if b.get("id") in HASSAS and b["id"] not in ac_hassas:
            b.update(kilitli=True, olay_sayisi=None, ilk=None, son=None, ozet="")
        else:
            b.setdefault("kilitli", False)
    return veri


def bolge(hub, bolge_id: str, ac_hassas: set[str], filtre: dict | None = None, aralik: dict | None = None) -> dict[str, Any]:
    if bolge_id in HASSAS and bolge_id not in ac_hassas:
        return {"id": bolge_id, "kilitli": True, "grafikler": [], "en_cok": [], "gruplar": [], "notlar": []}
    fn = _s().bolge
    istek = {"ac_hassas": frozenset(ac_hassas)}
    if filtre:
        istek["filtre"] = filtre
    if aralik:
        istek["aralik"] = aralik
    kw, yok = _uygun(fn, istek)
    veri = fn(hub, bolge_id, **kw)
    veri["filtre_destegi"] = not ({"filtre", "aralik"} & yok)
    if bolge_id in HASSAS:
        veri["en_cok"], veri["gruplar"] = [], []   # hassas bölgede içerik/örnek yok, yalnız sayı ve dağılım
        for g in veri.get("grafikler", []):
            g.pop("ornek", None)
    veri["kilitli"] = False
    return veri


_GIZLI = "(içerik gizli)"


def kayitlar(hub, bolge_id: str, ac_hassas: set[str], filtre: dict | None = None, aralik: dict | None = None,
             limit: int = 20, offset: int = 0) -> dict[str, Any]:
    if bolge_id in HASSAS and bolge_id not in ac_hassas:
        return {"kilitli": True, "toplam": 0, "kayitlar": []}
    fn = _s().kayitlar
    if fn is None:
        raise OzellikYok("Kayıt listesi bu sürümde yok.")
    kw, _ = _uygun(fn, {"ac_hassas": frozenset(ac_hassas), "filtre": filtre, "aralik": aralik,
                        "limit": max(1, min(int(limit), 100)), "offset": max(0, int(offset))})
    veri = fn(hub, bolge_id, **kw)
    veri["kilitli"] = False
    if bolge_id in HASSAS:                     # açık hassas bölge: yalnız tarih/tür, içerik asla
        for r in veri.get("kayitlar", []):
            r["baslik"], r["alt"] = f"{r.get('kategori', 'kayıt')} kaydı {_GIZLI}", ""
    return veri


def ayrinti(hub, event_id: str, ac_hassas: set[str]) -> dict[str, Any]:
    fn = _s().ayrinti
    if fn is None:
        raise OzellikYok("Kayıt ayrıntısı bu sürümde yok.")
    kategori = hub.get_event(event_id).category        # bulunamazsa NotFoundError yükselir
    hassas = kategori in Category.SENSITIVE
    if hassas and KATEGORI_BOLGE.get(kategori) not in ac_hassas:
        return {"id": event_id, "kilitli": True}
    veri = fn(hub, event_id)
    veri["kilitli"] = False
    if hassas:                                    # kaynak, ham tarih ve kaynak dosya kalır; içerik gider
        veri["metin"] = ""
        veri["alanlar"] = []
        veri["icerik_gizli"] = True
    return veri
