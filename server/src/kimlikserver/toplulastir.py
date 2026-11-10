"""Toplulaştırma: sayım ve "en çok" (top-N). MCP `say` aracı ile kimlik kartı bunu kullanır.

- YALNIZ veriden sayım; yorum yok. SQL ile (Python'da kayıt döngüsü yok; saat/gün/ay dağılımı
  saat dilimi dönüşümü için dakika/saat grupları üzerinden Python'da toplanır).
- İzin: çağıran `kategoriler` listesini (izinli ve istenen kesişimi) verir; burada başka kategori
  eklenmez. Gizli (hidden=1) kayıtlar hiçbir sayıma girmez.
- İçerik taşıyan alanlar (terim, site, kanal, sanatçı, depo...) hassas kategorilerde (eposta,
  mesaj, konum, sohbet) HİÇ hesaplanmaz, izin verilmiş olsa bile: o kategorilerde yalnız
  `tur`, `kategori`, `kaynak`, `platform` ve zaman dağılımı sayılır. (Konum izni açık olsa da yer
  adları bu araçtan dönmez.)
- Zamansız kayıtlar (payload.zaman_kaynagi = dosya_tarihi: abonelik/kütüphane gibi): zaman
  aralığı verilirse ve zaman alanlarında (ay/saat/gun) sayıma girmez; kaç tane dışlandığı yazılır.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from kimlikcore import Category, FormatError

from .harita import (_DIL, _HOST, _KANAL, _PROGRAM, _SANATCI, _SARKI, _SUB, _TERIM, _UZ,
                     _URUN, GUNLER)
from .yerelsaat import YerelSaat

VARSAYILAN_EN_COK = 10
UST_EN_COK = 50
MAX_AY = 120
DEGER_UZUNLUK = 200
_GERCEK_ZAMAN = "COALESCE(json_extract(payload, '$.zaman_kaynagi'), '') <> 'dosya_tarihi'"
_PLATFORM = "json_extract(payload, '$.platform')"
# Depo adı: URL biçimindeki ("<ana makine>/kullanici/depo") ve yalın "depo" aynı depo sayılsın -> son yol parçası
_DEPO_HAM = "COALESCE(json_extract(payload, '$.depo'), json_extract(payload, '$.ad'))"
_DEPO = f"replace({_DEPO_HAM}, rtrim({_DEPO_HAM}, replace({_DEPO_HAM}, '/', '')), '')"
_KAYNAK = "(SELECT s.kind FROM sources s WHERE s.source_id = events.source_id)"

# alan -> (SQL ifadesi, kayıt koşulu, içerik mi)
ALANLAR: dict[str, tuple[str, str, bool]] = {
    "tur": ("kind", "1", False),
    "kategori": ("category", "1", False),
    "kaynak": (_KAYNAK, "1", False),
    "platform": (_PLATFORM, f"{_PLATFORM} IS NOT NULL", False),
    "terim": (_TERIM, "kind IN ('google.arama', 'youtube.arama')", True),
    "site": (_HOST, "kind = 'chrome.ziyaret'", True),
    "kanal": (_KANAL, "kind = 'youtube.izleme'", True),
    "sanatci": (_SANATCI, "kind = 'spotify.dinleme'", True),
    "parca": (_SARKI, "kind = 'spotify.dinleme'", True),
    "podcast": (_PROGRAM, "kind = 'spotify.podcast'", True),
    "subreddit": (_SUB, "kind IN ('reddit.gonderi', 'reddit.yorum')", True),
    "depo": (_DEPO, "kind LIKE 'github.%'", True),
    "dil": (_DIL, "kind LIKE 'github.%'", True),
    "uzanti": (_UZ, "1", True),
    "uygulama": (_URUN, "1", True),
}
ZAMAN_ALANLARI = ("ay", "saat", "gun")
TUM_ALANLAR = tuple(ALANLAR) + ZAMAN_ALANLARI
_KUCUK_HARF = ("terim", "site")  # SQL tarafında zaten küçük harf


def _kaçir(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class Toplulastirici:
    def __init__(self, hub, tz: YerelSaat):
        self.hub = hub
        self.tz = tz

    # ------------------------------------------------------------------ yardımcılar
    def _kosul(self, kategoriler: list[str], tur: str | None, kaynak: str | None,
               since: str | None, until: str | None, gercek_zaman: bool
               ) -> tuple[str, list[Any]]:
        if not kategoriler:
            return "0", []
        w = "hidden = 0 AND category IN (%s)" % ",".join("?" * len(kategoriler))
        a: list[Any] = list(kategoriler)
        if tur:
            if tur.endswith("*"):
                w += " AND kind LIKE ? ESCAPE '\\'"
                a.append(_kaçir(tur[:-1]) + "%")
            else:
                w += " AND kind = ?"
                a.append(tur)
        if kaynak:
            w += " AND source_id IN (SELECT source_id FROM sources WHERE kind = ?)"
            a.append(kaynak)
        if since is not None:
            w += " AND ts >= ?"
            a.append(since)
        if until is not None:
            w += " AND ts <= ?"
            a.append(until)
        if gercek_zaman:
            w += f" AND ({_GERCEK_ZAMAN})"
        return w, a

    @staticmethod
    def _kes(v: Any) -> Any:
        if isinstance(v, str) and len(v) > DEGER_UZUNLUK:
            return v[:DEGER_UZUNLUK] + "…"
        return v

    # ------------------------------------------------------------------ ana işlev
    def say(self, alan: str, *, kategoriler: list[str], tur: str | None = None,
            kaynak: str | None = None, since: str | None = None, until: str | None = None,
            en_cok: int | None = None) -> dict[str, Any]:
        """`since`/`until` UTC ISO (çağıran normalleştirir). `kategoriler` izin süzülmüş liste."""
        if alan not in TUM_ALANLAR:
            raise FormatError(f"Bilinmeyen alan '{alan}'. Geçerli alanlar: {', '.join(TUM_ALANLAR)}.")
        try:
            n = VARSAYILAN_EN_COK if en_cok is None else int(en_cok)
        except (TypeError, ValueError):
            raise FormatError("en_cok sayı olmalı.") from None
        n = max(1, min(n, UST_EN_COK))
        zaman_alani = alan in ZAMAN_ALANLARI
        aralikli = since is not None or until is not None
        notlar: list[str] = []
        cats = list(kategoriler)
        if alan in ALANLAR and ALANLAR[alan][2]:  # içerik alanı: hassas kategoriler dışlanır
            kalan = [c for c in cats if c not in Category.SENSITIVE]
            if len(kalan) != len(cats):
                notlar.append(f"'{alan}' içerik alanıdır; hassas kategorilerde hesaplanmaz.")
            cats = kalan
        # Aynı filtrenin toplamı ve zamansız dışlanan sayısı
        w_hepsi, a_hepsi = self._kosul(cats, tur, kaynak, since, until, False)
        toplam = self.hub.query(f"SELECT COUNT(*) FROM events WHERE {w_hepsi}", a_hepsi)[0][0]
        w, a = self._kosul(cats, tur, kaynak, since, until, zaman_alani or aralikli)
        if zaman_alani or aralikli:
            sayilan = self.hub.query(f"SELECT COUNT(*) FROM events WHERE {w}", a)[0][0]
            zamansiz = toplam - sayilan
            if zamansiz:
                notlar.append(f"{zamansiz} kayıt gerçek zamansız (dosya tarihi; abonelik/kütüphane "
                              "gibi), zaman süzgecine/dağılımına alınmadı.")
        else:
            zamansiz = self.hub.query(
                f"SELECT COUNT(*) FROM events WHERE {w_hepsi} AND NOT ({_GERCEK_ZAMAN})",
                a_hepsi)[0][0]
            if zamansiz:
                notlar.append(f"{zamansiz} kayıt zamansız (dosya tarihi); sayıma dahil, zamana göre "
                              "yorumlamayın.")
        out: dict[str, Any] = {"alan": alan, "toplam_kayit": toplam, "zamansiz_kayit": zamansiz}
        if zaman_alani:
            satirlar, alansiz = self._zaman(alan, w, a)
            out["sira"] = "deger"
            farkli = len(satirlar)
            diger = 0
            sayilan_toplam = sum(s["sayi"] for s in satirlar)
        else:
            ifade, kosul, _ = ALANLAR[alan]
            ek = f"({kosul}) AND {ifade} IS NOT NULL AND {ifade} <> ''"
            rows = self.hub.query(
                f"SELECT {ifade} AS v, COUNT(*) FROM events WHERE {w} AND {ek} "
                "GROUP BY v ORDER BY 2 DESC, v LIMIT ?", [*a, n])
            farkli = self.hub.query(
                f"SELECT COUNT(*) FROM (SELECT 1 FROM events WHERE {w} AND {ek} GROUP BY {ifade})",
                a)[0][0]
            sayilan_toplam = self.hub.query(
                f"SELECT COUNT(*) FROM events WHERE {w} AND {ek}", a)[0][0]
            alansiz = self.hub.query(
                f"SELECT COUNT(*) FROM events WHERE {w} AND ({kosul}) AND "
                f"({ifade} IS NULL OR {ifade} = '')", a)[0][0]
            satirlar = [{"etiket": "veri", "veri": self._kes(v), "sayi": c} for v, c in rows]
            diger = sayilan_toplam - sum(s["sayi"] for s in satirlar)
            out["sira"] = "sayiya_gore_azalan"
            if not sayilan_toplam:
                notlar.append(f"Bu süzgeçle '{alan}' alanı olan kayıt yok (alan yalnız belirli "
                              "kayıt türlerinde bulunur).")
        for s in satirlar:
            s["oran"] = round(s["sayi"] / sayilan_toplam, 4) if sayilan_toplam else 0.0
        out.update({"alanli_kayit": sayilan_toplam, "alansiz_kayit": alansiz,
                    "farkli_deger": farkli, "satirlar": satirlar, "diger_sayi": diger})
        if notlar:
            out["notlar"] = notlar
        return out

    def ham_top(self, alan: str, kategoriler: list[str], *, since: str | None = None,
                until: str | None = None, tur: str | None = None, limit: int = 2000
                ) -> list[tuple[str, int]]:
        """(değer, sayı) satırları, sayıya göre azalan; `limit` iç kullanım içindir (kart:
        sözcük sayımı). İçerik alanları hassas kategorilerde hesaplanmaz. Zaman alanı verilemez."""
        if alan not in ALANLAR:
            raise FormatError(f"Bilinmeyen alan '{alan}'.")
        ifade, kosul, icerik = ALANLAR[alan]
        cats = [c for c in kategoriler if not (icerik and c in Category.SENSITIVE)]
        w, a = self._kosul(cats, tur, None, since, until, since is not None or until is not None)
        rows = self.hub.query(
            f"SELECT {ifade} AS v, COUNT(*) FROM events WHERE {w} AND ({kosul}) AND "
            f"{ifade} IS NOT NULL AND {ifade} <> '' GROUP BY v ORDER BY 2 DESC, v LIMIT ?",
            [*a, int(limit)])
        return [(self._kes(v), c) for v, c in rows]

    # ------------------------------------------------------------------ zaman alanları
    def _zaman(self, alan: str, w: str, a: list[Any]) -> tuple[list[dict[str, Any]], int]:
        """ay/saat/gun: yerel saat diliminde. UTC saat (ya da dakika) gruplarını yerel zamana
        çevirip toplar (yaz saati değişimlerini doğru yakalar)."""
        simdi = datetime.now(timezone.utc)
        tam_saat = self.tz.farki(simdi).total_seconds() % 3600 == 0
        uz = 13 if tam_saat else 16
        rows = self.hub.query(f"SELECT substr(ts, 1, {uz}), COUNT(*) FROM events WHERE {w} "
                              f"GROUP BY 1", a)
        sayac: Counter[str] = Counter()
        for g, c in rows:
            ts = g + (":00" if uz == 13 else "") + ":00Z"
            yerel = self.tz.yerel_dt(ts)
            if alan == "saat":
                sayac[f"{yerel.hour:02d}"] += c
            elif alan == "gun":
                sayac[str(yerel.weekday())] += c
            else:
                sayac[f"{yerel.year:04d}-{yerel.month:02d}"] += c
        if alan == "saat":
            satirlar = [{"etiket": "veri", "veri": f"{h:02d}:00-{h:02d}:59", "sayi": sayac.get(f"{h:02d}", 0)}
                        for h in range(24)]
        elif alan == "gun":
            satirlar = [{"etiket": "veri", "veri": GUNLER[g], "sayi": sayac.get(str(g), 0)}
                        for g in range(7)]
        else:
            ay_listesi = sorted(sayac)[-MAX_AY:]
            satirlar = [{"etiket": "veri", "veri": ay, "sayi": sayac[ay]} for ay in ay_listesi]
        return satirlar, 0


def aralik_pencere(simdi: datetime, gun: int) -> str:
    return (simdi - timedelta(days=gun)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
