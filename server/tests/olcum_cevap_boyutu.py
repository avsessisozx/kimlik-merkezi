"""Cevap boyutu ölçümü (Madde 4-8): sentetik "örnek dünya" üzerinde her MCP aracının JSON
cevabının karakter sayısı. `test_cevap_butcesi.py` bütçe sınırlarını buradan denetler.

Tablo üretmek için: `.venv/bin/python server/tests/olcum_cevap_boyutu.py`
(ONCE değerleri değişiklikten ÖNCEKİ hâlin ölçümüdür; sabit yazılıdır.)
Tüm veri uydurmadır.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kimlikcore import EventIn, Hub  # noqa: E402

from helpers import FakeClock  # noqa: E402
from kimlikserver.access import KeyManager  # noqa: E402
from kimlikserver.persona import Persona  # noqa: E402
from kimlikserver.service import QueryService  # noqa: E402
from kimlikserver.yerelsaat import YerelSaat  # noqa: E402

IST = YerelSaat.cozumle("Europe/Istanbul")
SIMDI = datetime(2026, 11, 10, 9, 0, 0, tzinfo=timezone.utc)
YETKILI = ["tarama", "video", "muzik", "kod", "notlar", "persona"]

# Değişiklikten ÖNCE (main f60d0bb) ölçülen karakter sayıları (aynı dünya, aynı çağrılar).
ONCE: dict[str, int | None] = {
    "kategorileri_listele": 559,
    "ara": 118149,
    "ornekle": 58389,          # rastgele örnek; çalıştırmaya göre birkaç yüz karakter oynar
    "zaman_cizelgesi": 112126,
    "say_ay": 7319,
    "say_yil": None,          # alan=yil yoktu
    "kimlik_karti": 6182,
    "persona_getir": 5353,
    "kayit_getir": None,      # araç yoktu
}

_KONULAR = ("fedora kurulumu", "kahve tarifi", "ubuntu usb", "müzik listesi", "bisiklet bakımı")


def _uzun_mesaj(i: int) -> str:
    cumle = (f"Mesaj {i}: fedora kurulumu ve kahve makinesi üzerine uzun bir konuşma; "
             "ayrıntılar, adımlar, denemeler ve sonuçlar burada tek tek anlatılıyor. ")
    return (cumle * 30)[:3000]


def olaylar() -> list[EventIn]:
    out: list[EventIn] = []
    for i in range(36):                         # uzun sohbet mesajları (~3000 karakter), 18+18 rol
        out.append(EventIn(
            ts=f"2026-10-{1 + i % 28:02d}T{8 + i % 10:02d}:00:00Z", kind="sohbet.mesaj",
            category="sohbet", payload={"platform": "chatgpt",
                                        "rol": "kullanici" if i % 2 == 0 else "asistan"},
            text=_uzun_mesaj(i), event_key=f"sh{i}"))
    for i in range(2000):                        # 96 aya yayılmış tarama kayıtları
        ay = i % 96
        yil, a = 2018 + (ay + 10) // 12, (ay + 10) % 12 + 1
        t = f"{_KONULAR[i % 5]} {i}"
        out.append(EventIn(ts=f"{yil}-{a:02d}-{1 + i % 27:02d}T{(i * 7) % 24:02d}:15:00Z",
                           kind="google.arama", category="tarama", payload={"baslik": t},
                           text="Searched for " + t, event_key=f"ar{i}"))
    for i in range(300):                         # müzik
        sanatci = "Gece Vardiyası" if i >= 240 else "Mavi Dalga"
        out.append(EventIn(ts=f"2026-0{1 + i % 9}-{1 + i % 27:02d}T{i % 24:02d}:10:00Z",
                           kind="spotify.dinleme", category="muzik",
                           payload={"sanatci": sanatci, "sarki": f"Şarkı {i % 7}"},
                           text=f"Şarkı {i % 7} {sanatci}", event_key=f"mz{i}"))
    for i in range(60):                          # kod
        out.append(EventIn(ts=f"2026-10-{1 + i % 27:02d}T0{2 + i % 2}:{30 + i % 20}:00Z",
                           kind="github.commit", category="kod",
                           payload={"depo": "https://github.com/ornek/mahalle-takvimi",
                                    "dil": "Python"},
                           text=f"düzeltme {i}", event_key=f"kd{i}"))
    out.append(EventIn(ts="2026-03-03T12:00:00Z", kind="github.depo", category="kod",
                       payload={"ad": "mahalle-takvimi", "dil": "Python"},
                       text="mahalle-takvimi", event_key="depo1"))
    return out


def dunya_kur(root: Path) -> dict:
    """Örnek dünyayı `root`a yazar; döner: {"root", "key"}."""
    with Hub.open(root, write=True) as hub:
        sid = hub.add_source("test", "1", None)
        hub.add_events(sid, olaylar())
        km = KeyManager(hub)
        app, key = km.create_key("Olcum")
        for k in YETKILI:
            km.grant(app, k)
        km.grant(app, "sohbet", confirmed_sensitive=True)
        p = Persona(hub, clock=lambda: datetime(2026, 8, 1, 12, tzinfo=timezone.utc))
        kategoriler = ["kimlik", "tercihler", "ilgi", "cihazlar", "projeler", "is"]
        for i in range(20):
            p.add_fact(f"Deneme beyanı {i}: " + "ayrıntılı bir bilgi cümlesi " * 3,
                       kategoriler[i % 6])
        for i in range(3):                       # süresi dolmuş
            p.add_fact(f"Eski beyan {i}", "kimlik", valid_until="2026-01-01T00:00:00Z")
    return {"root": root, "key": key}


def servis(d: dict) -> QueryService:
    return QueryService(d["root"], d["key"], clock=FakeClock(SIMDI), saat_dilimi=IST)


def boyut(cevap) -> int:
    return len(json.dumps(cevap, ensure_ascii=False))


def olc(d: dict) -> dict[str, int | None]:
    """Her araç için varsayılan çağrının cevap karakter sayısı."""
    s = servis(d)
    sonuc: dict[str, int | None] = {}
    sonuc["kategorileri_listele"] = boyut(s.kategorileri_listele())
    sonuc["ara"] = boyut(s.ara("konuşma"))
    sonuc["ornekle"] = boyut(s.ornekle("sohbet", 20))
    sonuc["zaman_cizelgesi"] = boyut(s.zaman_cizelgesi())
    sonuc["say_ay"] = boyut(s.say("ay"))
    try:
        sonuc["say_yil"] = boyut(s.say("yil"))
    except Exception:
        sonuc["say_yil"] = None
    sonuc["kimlik_karti"] = boyut(s.kimlik_karti())
    sonuc["persona_getir"] = boyut(s.persona_getir())
    if hasattr(s, "kayit_getir"):
        eid = s.ara("konuşma", kategori="sohbet", limit=1)["kayitlar"][0]["id"]
        sonuc["kayit_getir"] = boyut(s.kayit_getir(eid))
    else:
        sonuc["kayit_getir"] = None
    return sonuc


def tablo(sonra: dict[str, int | None]) -> str:
    satir = ["| Araç (varsayılan çağrı) | Önce | Sonra |", "|---|---:|---:|"]
    for k, once in ONCE.items():
        o = "-" if once is None else str(once)
        n = "-" if sonra.get(k) is None else str(sonra[k])
        satir.append(f"| {k} | {o} | {n} |")
    return "\n".join(satir)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        kok = Path(t) / "veri"
        kok.mkdir()
        olculen = olc(dunya_kur(kok))
    print(json.dumps(olculen, ensure_ascii=False, indent=1))
    print(tablo(olculen))
