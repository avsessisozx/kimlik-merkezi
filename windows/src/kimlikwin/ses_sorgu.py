"""Sesli/yazılı aramayı kurallarla çözer (yapay zekâ yok): "geçen yaz Chrome'da kahve aramaları" ->
{tarih aralığı, kaynak, anahtar sözcük}. Çözemediğini UYDURMAZ: tanınmayan her şey anahtar sözcük olur ve
`anlasilan` listesi kullanıcıya ne anlaşıldığını açıkça gösterir. Saat dilimi: Türkiye (UTC+3, `kayma`)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

AYLAR = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
         "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}
AY_ADI = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
MEVSIMLER = {"yaz": ((6, 0), (9, 0), "yaz"), "bahar": ((3, 0), (6, 0), "ilkbahar"), "ilkbahar": ((3, 0), (6, 0), "ilkbahar"),
             "sonbahar": ((9, 0), (12, 0), "sonbahar"), "güz": ((9, 0), (12, 0), "sonbahar"), "kış": ((12, 0), (3, 1), "kış")}
KAYNAK_TAKMA = {"instagram": "Meta", "insta": "Meta", "facebook": "Meta", "meta": "Meta", "chatgpt": "ChatGPT", "gpt": "ChatGPT",
                "telefon": "Telefon", "telefondan": "Telefon", "bilgisayar": "Bilgisayar", "bilgisayardan": "Bilgisayar"}
DOLGU = {"bana", "göster", "gösterir", "misin", "mısın", "ara", "bul", "getir", "listele", "ne", "neler", "nelerdi", "vardı", "yaptım",
         "baktım", "olan", "ile", "ilgili", "hakkında", "için", "bir", "ve", "da", "de", "ki", "şu", "bu", "o", "zaman", "içinde", "ayında",
         "ayı", "yılında", "yılı", "kayıtları", "kayıtlar", "kayıt", "arama", "aramaları", "aramalar", "lütfen", "bakalım", "mı", "mi", "mu", "mü"}


def _kucult(s: str) -> str:
    return s.replace("İ", "i").lower()      # "I" -> "i" (Whisper büyük harfi Türkçe sözcükte nadiren kullanır; marka adları bozulmasın)


def _epoch(d: datetime, kayma: int) -> int:
    """Yerel (UTC+kayma) duvar saati -> epoch saniye."""
    return int((d - timedelta(hours=kayma)).replace(tzinfo=timezone.utc).timestamp())


def _gun(y: int, m: int, g: int) -> datetime:
    return datetime(y, m, g)


def _mevsim_araligi(ad: str, yil: int) -> tuple[datetime, datetime]:
    (bm, _), (em, ey), _ = MEVSIMLER[ad]
    if ad == "kış":                       # "2023 kışı": Aralık 2023 – Şubat 2024
        return _gun(yil, 12, 1), _gun(yil + 1, 3, 1)
    return _gun(yil, bm, 1), _gun(yil, em, 1)


def _son_biten_mevsim(ad: str, simdi: datetime) -> int:
    """Bitişi `simdi`'den önce olan en yakın mevsimin yılı."""
    for y in range(simdi.year, simdi.year - 4, -1):
        if _mevsim_araligi(ad, y)[1] <= simdi:
            return y
    return simdi.year - 1


def coz(metin: str, *, simdi: datetime | None = None, kaynaklar: list[str] | None = None, kayma: int = 3) -> dict[str, Any]:
    """`simdi`: yerel duvar saati (testler sabitler). `kaynaklar`: veride bulunan küme adları."""
    simdi = simdi or (datetime.now(timezone.utc) + timedelta(hours=kayma)).replace(tzinfo=None, microsecond=0)
    ham = _kucult(metin)
    t = re.sub(r"[^\w\s']", " ", ham).replace("'", " ")
    sozler = t.split()
    anlasilan: list[str] = []
    kullanilan: set[int] = set()
    aralik: tuple[datetime, datetime] | None = None
    bugun = _gun(simdi.year, simdi.month, simdi.day)

    def al(i: int, j: int | None = None) -> None:
        kullanilan.update(range(i, (j if j is not None else i) + 1))

    def ara(*kelimeler: str) -> int | None:
        for i, w in enumerate(sozler):
            if w in kelimeler and i not in kullanilan:
                return i
        return None

    def ayar(bas: datetime, bit: datetime, ad: str) -> None:
        nonlocal aralik
        if aralik is None:
            aralik = (bas, bit)
            anlasilan.append(ad)

    # göreli günler
    for kel, gor in (("bugün", (0, 1)), ("dün", (-1, 0)), ("evvelsi", (-2, -1)), ("önceki", None)):
        i = ara(kel)
        if i is not None and gor:
            ayar(bugun + timedelta(days=gor[0]), bugun + timedelta(days=gor[1]), kel if kel != "evvelsi" else "evvelsi gün")
            al(i)
            if i + 1 < len(sozler) and sozler[i + 1] == "gün":
                al(i + 1)
    # hafta / ay / yıl (bu, geçen)
    for i, w in enumerate(sozler[:-1]):
        o = sozler[i + 1]
        if w not in ("bu", "geçen", "önceki", "gelecek") or i in kullanilan or w == "gelecek":
            continue
        geri = 0 if w == "bu" else 1
        if o == "hafta":
            pazartesi = bugun - timedelta(days=bugun.weekday())
            ayar(pazartesi - timedelta(weeks=geri), pazartesi - timedelta(weeks=geri) + timedelta(weeks=1), f"{w} hafta")
            al(i, i + 1)
        elif o in ("ay", "ayın"):
            y, m = simdi.year, simdi.month - geri
            if m < 1:
                y, m = y - 1, 12
            bit = _gun(y + (m == 12), 1 if m == 12 else m + 1, 1)
            ayar(_gun(y, m, 1), bit, f"{w} ay ({AY_ADI[m]} {y})")
            al(i, i + 1)
        elif o in ("yıl", "sene", "yılın"):
            y = simdi.year - geri
            ayar(_gun(y, 1, 1), _gun(y + 1, 1, 1), f"{w} yıl ({y})")
            al(i, i + 1)
        elif o in MEVSIMLER:
            if w == "bu":
                y = simdi.year if _mevsim_araligi(o, simdi.year)[0] <= simdi else simdi.year - 1
            else:
                y = _son_biten_mevsim(o, simdi)
            b, e = _mevsim_araligi(o, y)
            ayar(b, e, f"{w} {MEVSIMLER[o][2]} ({b.year})")
            al(i, i + 1)
    # açık yıl (2000-2100) + mevsim / ay
    yil = None
    for i, w in enumerate(sozler):
        w2 = re.sub(r"(yılında|yılı|yılının|da|de|ta|te)$", "", w)
        if re.fullmatch(r"20\d\d", w2) and i not in kullanilan:
            yil = int(w2)
            yi = i
            break
    mevsim_i = next((i for i, w in enumerate(sozler) if i not in kullanilan and re.sub(r"(ı|i|u|ü|nda|nde|da|de|ta|te)$", "", w) in MEVSIMLER), None)
    ay_i = next((i for i, w in enumerate(sozler) if i not in kullanilan and re.sub(r"(ında|inde|unda|ünde|da|de|ta|te|ı|i|u|ü)$", "", w) in AYLAR), None)
    if ay_i is None:      # "mart" gibi çıplak ad
        ay_i = next((i for i, w in enumerate(sozler) if i not in kullanilan and w in AYLAR), None)
    if mevsim_i is not None:
        ad = re.sub(r"(ı|i|u|ü|nda|nde|da|de|ta|te)$", "", sozler[mevsim_i])
        y = yil if yil is not None else _son_biten_mevsim(ad, simdi)
        b, e = _mevsim_araligi(ad, y)
        ayar(b, e, f"{MEVSIMLER[ad][2]} {y}")
        al(mevsim_i)
        if yil is not None:
            al(yi)
    elif ay_i is not None:
        w = sozler[ay_i]
        ad = w if w in AYLAR else re.sub(r"(ında|inde|unda|ünde|da|de|ta|te|ı|i|u|ü)$", "", w)
        m = AYLAR[ad]
        if yil is not None:
            y = yil
        else:
            y = simdi.year if _gun(simdi.year, m, 1) <= simdi else simdi.year - 1
        bit = _gun(y + (m == 12), 1 if m == 12 else m + 1, 1)
        ayar(_gun(y, m, 1), bit, f"{AY_ADI[m]} {y}")
        al(ay_i)
        if yil is not None:
            al(yi)
    elif yil is not None:
        ayar(_gun(yil, 1, 1), _gun(yil + 1, 1, 1), str(yil))
        al(yi)
    # kaynak
    kaynak = None
    bilinen = {_kucult(k): k for k in (kaynaklar or [])}
    for i, w in enumerate(sozler):
        if i in kullanilan:
            continue
        kok = re.sub(r"(da|de|ta|te|dan|den|tan|ten|ın|in|un|ün|daki|deki)$", "", w)
        aday = KAYNAK_TAKMA.get(w) or KAYNAK_TAKMA.get(kok) or bilinen.get(w) or bilinen.get(kok)
        if aday and (kaynaklar is None or aday in (kaynaklar or [])):
            kaynak = aday
            anlasilan.append(f"kaynak: {aday}")
            al(i)
            break
    kalan = [w for i, w in enumerate(sozler) if i not in kullanilan and w not in DOLGU and len(w) > 1]
    arama = " ".join(kalan) or None
    if arama:
        anlasilan.append(f"içinde geçen: «{arama}»")
    return {"metin": metin.strip(), "bas": _epoch(aralik[0], kayma) if aralik else None, "bit": _epoch(aralik[1], kayma) if aralik else None,
            "kaynak": kaynak, "arama": arama, "anlasilan": anlasilan, "bos": not (aralik or kaynak or arama)}
