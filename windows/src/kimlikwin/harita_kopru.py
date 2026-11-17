"""Persona Haritası köprüsü (INTERFACES §12 + genişletilmiş sözleşme: filtre, aralık, kayıtlar, ayrıntı).

- Gerçek işlevler `kimlikserver.harita` modülündedir. Modül yoksa açık bir hata döner; sahte veriye
  DÜŞÜLMEZ. Testler `saglayici` değişkenine sahte bir sağlayıcı atar.
- Gerçek modül `filtre`/`aralik` parametrelerini ya da `kayitlar`/`ayrinti` işlevlerini henüz sunmuyorsa
  köprü bunu bildirir (`filtre_destegi: False`, `ozellik_yok` hatası); arayüz bunu zarifçe gösterir.
- SAHİP GÖRÜNÜMÜ (v0.3.0): bu köprü yalnız verinin sahibinin kendi bilgisayarındaki arayüzüne hizmet eder
  (parola/oturum jetonu ile korunan yerel web). Sahip kendi verisini, hassas kategoriler dahil, TAM görür:
  kilit ve "içerik gizli" yok. Yapay zekâ (MCP) yolu bu köprüyü HİÇ kullanmaz; orada kategori izni, ayrı
  hassas onayı ve içerik kısıtı aynen sürer (server/access.py). `SAHIP = False` yapılırsa eski kilitli
  görünüm döner (testler bunu sınar).
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import datetime
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

# Sahip görünümü: açık (True) = hassas bölgeler kilitsiz ve içerikli. Yapay zekâ yolunu ETKİLEMEZ.
SAHIP = True

# Yerel saat farkı (saat) testlerde sabitlenebilir; None = bilgisayarın saat dilimi (Türkiye: +3).
YEREL_KAYMA: int | None = None


def yerel_kayma() -> int:
    """Grafiklerdeki saat/gün dilimleri için UTC'ye eklenecek tam saat (Türkiye +3). Kayıtlar UTC saklanır."""
    if YEREL_KAYMA is not None:
        return int(YEREL_KAYMA)
    try:
        fark = datetime.now().astimezone().utcoffset()
        return int(round(fark.total_seconds() / 3600)) if fark is not None else 0
    except (OSError, ValueError, OverflowError):
        return 0


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


def _aralik(aralik: Any) -> tuple[Any, Any] | None:
    """Arayüzün `{"baslangic", "bitis"}` aralığını sunucunun `(baslangic, bitis)` çiftine çevirir.
    Boş/None değerler None kalır; zaten çift/liste ise olduğu gibi (çifte) döner."""
    if not aralik:
        return None
    if isinstance(aralik, dict):
        a, b = aralik.get("baslangic") or None, aralik.get("bitis") or None
        return (a, b) if (a, b) != (None, None) else None
    return tuple(aralik)


def _acik(ac_hassas: set[str]) -> set[str]:
    return set(ac_hassas) | (set(HASSAS) if SAHIP else set())


def harita(hub, ac_hassas: set[str], aralik: dict | None = None) -> dict[str, Any]:
    ac_hassas = _acik(ac_hassas)
    fn = _s().harita
    kw, _ = _uygun(fn, {"ac_hassas": frozenset(ac_hassas), "aralik": _aralik(aralik)})
    veri = fn(hub, **kw)
    for b in veri.get("bolgeler", []):
        if b.get("id") in HASSAS and b["id"] not in ac_hassas:
            b.update(kilitli=True, olay_sayisi=None, ilk=None, son=None, ozet="")
        else:
            b.setdefault("kilitli", False)
    return veri


def bolge(hub, bolge_id: str, ac_hassas: set[str], filtre: dict | None = None, aralik: dict | None = None) -> dict[str, Any]:
    ac_hassas = _acik(ac_hassas)
    if bolge_id in HASSAS and bolge_id not in ac_hassas:
        return {"id": bolge_id, "kilitli": True, "grafikler": [], "en_cok": [], "gruplar": [], "notlar": []}
    fn = _s().bolge
    istek: dict[str, Any] = {"ac_hassas": frozenset(ac_hassas), "utc_kaydirma": yerel_kayma(), "sahip": SAHIP}
    if filtre:
        istek["filtre"] = filtre
    if aralik := _aralik(aralik):
        istek["aralik"] = aralik
    kw, yok = _uygun(fn, istek)
    veri = fn(hub, bolge_id, **kw)
    veri["filtre_destegi"] = not ({"filtre", "aralik"} & yok)
    if bolge_id in HASSAS and not SAHIP:
        veri["en_cok"], veri["gruplar"] = [], []   # hassas bölgede içerik/örnek yok, yalnız sayı ve dağılım
        for g in veri.get("grafikler", []):
            g.pop("ornek", None)
    veri["kilitli"] = False
    return veri


_GIZLI = "(içerik gizli)"


def kayitlar(hub, bolge_id: str, ac_hassas: set[str], filtre: dict | None = None, aralik: dict | None = None,
             limit: int = 20, offset: int = 0) -> dict[str, Any]:
    ac_hassas = _acik(ac_hassas)
    if bolge_id in HASSAS and bolge_id not in ac_hassas:
        return {"kilitli": True, "toplam": 0, "kayitlar": []}
    fn = _s().kayitlar
    if fn is None:
        raise OzellikYok("Kayıt listesi bu sürümde yok.")
    kw, _ = _uygun(fn, {"ac_hassas": frozenset(ac_hassas), "filtre": filtre, "aralik": _aralik(aralik),
                        "limit": max(1, min(int(limit), 100)), "offset": max(0, int(offset)),
                        "utc_kaydirma": yerel_kayma(), "sahip": SAHIP})
    veri = fn(hub, bolge_id, **kw)
    veri["kilitli"] = False
    if bolge_id in HASSAS and not SAHIP:       # sahip değilse: yalnız tarih/tür, içerik asla
        for r in veri.get("kayitlar", []):
            r["baslik"], r["alt"] = f"{r.get('kategori', 'kayıt')} kaydı {_GIZLI}", ""
    return veri


def ayrinti(hub, event_id: str, ac_hassas: set[str]) -> dict[str, Any]:
    ac_hassas = _acik(ac_hassas)
    fn = _s().ayrinti
    if fn is None:
        raise OzellikYok("Kayıt ayrıntısı bu sürümde yok.")
    kategori = hub.get_event(event_id).category        # bulunamazsa NotFoundError yükselir
    hassas = kategori in Category.SENSITIVE
    if hassas and KATEGORI_BOLGE.get(kategori) not in ac_hassas:
        return {"id": event_id, "kilitli": True}
    kw, _ = _uygun(fn, {"sahip": SAHIP, "ac_hassas": frozenset(ac_hassas)})
    veri = fn(hub, event_id, **kw)
    veri["kilitli"] = False
    if hassas and not SAHIP:                      # kaynak, ham tarih ve kaynak dosya kalır; içerik gider
        veri["metin"] = ""
        veri["alanlar"] = []
        veri["icerik_gizli"] = True
    return veri


# ------------------------------------------------------------------ galaksi (v0.3.0, yalnız sahibin yerel arayüzü)
def _galaksi_modulu():
    try:
        import kimlikserver.galaksi as m  # type: ignore[import-not-found]
        return m
    except ImportError as e:
        raise HaritaYok("Galaksi modülü (kimlikserver.galaksi) bu sürümde yok.") from e


def galaksi(hub) -> dict[str, Any]:
    return _galaksi_modulu().galaksi(hub, sahip=SAHIP)


def galaksi_kayitlar(hub, grup: str, bas: int | None = None, bit: int | None = None, limit: int = 50,
                     offset: int = 0, arama: str | None = None, tur: str | None = None) -> dict[str, Any]:
    return _galaksi_modulu().kayitlar(hub, str(grup), bas=bas, bit=bit, sahip=SAHIP, limit=limit, offset=offset,
                                      arama=(arama or None), tur=(tur or None))


def kimlik_ozeti(hub) -> dict[str, Any]:
    return _galaksi_modulu().ozet(hub, sahip=SAHIP, kayma=yerel_kayma())


def kaynak_adlari(hub) -> list[str]:
    return _galaksi_modulu().kaynak_adlari(hub, sahip=SAHIP)
