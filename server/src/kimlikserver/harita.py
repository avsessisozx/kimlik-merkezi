"""Persona Haritası (INTERFACES §12): insan figürü bölgeleri için YALNIZ veriden sayım.

- Tüm sayımlar SQL ile (`Hub.query`); yapay zekâ ya da çıkarım yok.
- `hidden=1` (tombstone / kaldırılmış kaynak) kayıtlar hiçbir sayıma girmez.
- Hassas bölgeler (kalp, karin, ayak) varsayılan kilitlidir. Kilitliyken yalnız "kilitli" döner
  (sayı, tarih, özet dahil hiçbir şey yok). Açıkken de yalnız sayı ve zaman dağılımı döner:
  kayıt metni, URL, yer adı ve koordinat hiçbir koşulda dönmez.
- Alan adları `importers` çıktısından alınmıştır (kimlikimport.google_takeout / reddit);
  bir bölge için gereken alan yoksa o grafik üretilmez ve `notlar`a "bu alan yok" yazılır.
  Dayanılan alanlar:
    tarama : kind chrome.ziyaret (payload.url, payload.baslik), google.arama (payload.baslik,
             "Searched for " önekiyle; başka dil önekleri tanınmaz, başlık olduğu gibi sayılır)
    video  : youtube.izleme (payload.alt_baslik[0] = kanal adı, payload.baslik),
             youtube.arama, youtube.abonelik (payload.kanal_adi)
    sosyal : reddit.gonderi / reddit.yorum (payload.subreddit), reddit.oy, reddit.kaydedilen,
             reddit.abone
    uygulama: payload.urun (Takeout "header")
    muzik  : spotify.dinleme (payload.sanatci, payload.sarki, payload.sure_ms), spotify.podcast
             (payload.program); kutuphane/liste kayıtları anlık görüntüdür
    kod    : github.* (payload.depo ya da payload.ad, payload.dil)
    dosyalar: dosya.kayit (payload.uzanti, payload.boyut)
    sohbet : sohbet.mesaj / sohbet.konusma (payload.platform, payload.konusma_id, payload.rol);
             hassas, içerik hiç dönmez
  Tarihi olmayan kayıtlar (payload.zaman_kaynagi = dosya_tarihi) zaman grafiklerine girmez.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from kimlikcore import Category, FormatError, Hub, NotFoundError, norm_ts

from ._db import iso, utc_now
from .persona import PersonaReader

HASSAS_BOLGELER = frozenset({"kalp", "karin", "ayak", "zihin"})
EN_COK_LIMIT = 10
MAX_AY = 36
GUNLER = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
VERI_YOK = "Henüz veri yok"
SAYIM_NOTU = "Veriden sayım; yorum ya da çıkarım içermez."

# id -> (ad, kategoriler)
VARSAYILAN_BOLGELER: dict[str, tuple[str, tuple[str, ...]]] = {
    "bas": ("Baş: ilgi ve merak", ("tarama",)),
    "zihin": ("Zihin: yapay zekâ sohbetleri", ("sohbet",)),
    "goz": ("Gözler: izledikleri", ("video",)),
    "kulak": ("Kulaklar: dinledikleri", ("muzik",)),
    "agiz": ("Ağız: yazdıkları/söyledikleri", ("sosyal",)),
    "el": ("Eller: üretim ve iş", ("kod", "dosyalar", "notlar")),
    "kalp": ("Kalp: kişisel (hassas)", ("mesaj",)),
    "karin": ("Karın: e-posta (hassas)", ("eposta",)),
    "ayak": ("Ayaklar: konum (hassas)", ("konum", "medya_meta")),
    "ic": ("Merkez: uygulama kullanımı", ("uygulama",)),
}

_GERCEK_ZAMAN = "COALESCE(json_extract(payload, '$.zaman_kaynagi'), '') <> 'dosya_tarihi'"
_U = "json_extract(payload, '$.url')"
_R = f"lower(substr({_U}, instr({_U}, '//') + 2))"
_H = f"substr({_R}, 1, instr({_R} || '/', '/') - 1)"
_HOST = (f"CASE WHEN {_U} LIKE 'http%://%' THEN "
         f"CASE WHEN {_H} LIKE 'www.%' THEN substr({_H}, 5) ELSE {_H} END END")


_TERIM = ("lower(CASE WHEN json_extract(payload, '$.baslik') LIKE 'Searched for %' "
          "THEN substr(json_extract(payload, '$.baslik'), 14) "
          "ELSE json_extract(payload, '$.baslik') END)")
_KANAL = "json_extract(payload, '$.alt_baslik[0]')"
_SANATCI = "json_extract(payload, '$.sanatci')"
_SARKI = "json_extract(payload, '$.sarki')"
_PROGRAM = "json_extract(payload, '$.program')"
_SUB = "json_extract(payload, '$.subreddit')"
_DEPO = "COALESCE(json_extract(payload, '$.depo'), json_extract(payload, '$.ad'))"
_DIL = "json_extract(payload, '$.dil')"
_UZ = "json_extract(payload, '$.uzanti')"
_URUN = "json_extract(payload, '$.urun')"
_PLAT = "COALESCE(json_extract(payload, '$.platform'), 'bilinmeyen')"

# Filtre alanı -> (SQL ifadesi, geçerli kayıt koşulu). Grafik/en_cok hesaplarıyla AYNI ifade ve
# koşul kullanılır; böylece bir noktanın `anahtar`ıyla süzülen toplam, o noktanın değerine eşittir.
ALAN_IFADE = {
    "terim": (_TERIM, "kind = 'google.arama'"), "site": (_HOST, "kind = 'chrome.ziyaret'"),
    "kanal": (_KANAL, "kind LIKE '%.izleme'"), "sanatci": (_SANATCI, "kind = 'spotify.dinleme'"),
    "parca": (_SARKI, "kind = 'spotify.dinleme'"), "podcast": (_PROGRAM, "kind = 'spotify.podcast'"),
    "subreddit": (_SUB, "kind IN ('reddit.gonderi', 'reddit.yorum')"), "depo": (_DEPO, "1"),
    "dil": (_DIL, "1"), "uzanti": (_UZ, "1"), "uygulama": (_URUN, "1"), "platform": (_PLAT, "1"),
    "tur": ("kind", "1"), "kategori": ("category", "1"),
}
ZAMAN_ALANLARI = ("ay", "saat", "gun")
ORTAK_ALANLAR = ("ay", "saat", "gun", "tur", "kategori")
BOLGE_ALANLARI = {
    "bas": ("terim", "site"), "goz": ("kanal",), "kulak": ("sanatci", "parca", "podcast"),
    "agiz": ("subreddit",), "el": ("depo", "dil", "uzanti"), "ic": ("uygulama",),
    "zihin": ("platform",), "kalp": (), "karin": (), "ayak": (),
}
KUCUK_HARF_ALANLAR = ("terim", "site")


def _now_dt(now: str | datetime | None) -> datetime:
    if now is None:
        return utc_now()
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(norm_ts(now, assume_utc=True).replace("Z", "+00:00"))


def _kilitli(bolge_id: str, kategoriler: Iterable[str], ac_hassas: Iterable[str]) -> bool:
    if bolge_id not in HASSAS_BOLGELER:
        return False
    acik = set(ac_hassas)
    return not (bolge_id in acik or acik & set(kategoriler))


class _Q:
    """Bir bölge için ortak WHERE parçası: gizli değil + kategoriler + zaman aralığı."""

    def __init__(self, hub: Hub, kategoriler: tuple[str, ...], aralik,
                 filtre: list[tuple[str, list]] | None = None):
        self.hub = hub
        self.aralik = aralik
        self.filtre = filtre or []
        self.where = "hidden = 0 AND category IN (%s)" % ",".join("?" * len(kategoriler))
        self.args: list[Any] = list(kategoriler)
        if aralik:
            since, until = aralik
            if since is not None:
                self.where += " AND ts >= ?"
                self.args.append(norm_ts(since, assume_utc=True))
            if until is not None:
                self.where += " AND ts <= ?"
                self.args.append(norm_ts(until, assume_utc=True))
        for frag, fargs in self.filtre:
            self.where += f" AND ({frag})"
            self.args += fargs

    def alt(self, kategoriler: tuple[str, ...]) -> "_Q":
        return _Q(self.hub, kategoriler, self.aralik, self.filtre)

    def rows(self, select: str, extra: str = "", tail: str = "", args: Iterable = ()) -> list[tuple]:
        # NOT INDEXED: 1M olayda dizinle tek tek satıra gitmekten tam tarama 3-5 kat hızlı ölçüldü
        sql = f"SELECT {select} FROM events NOT INDEXED WHERE {self.where}"
        if extra:
            sql += f" AND ({extra})"
        return self.hub.query(sql + " " + tail, [*self.args, *args])

    def one(self, select: str, extra: str = "") -> tuple:
        return self.rows(select, extra)[0]


def _aylar(ilk: str, son: str) -> list[str]:
    y, m = int(ilk[:4]), int(ilk[5:7])
    y2, m2 = int(son[:4]), int(son[5:7])
    out = []
    while (y, m) <= (y2, m2):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out[-MAX_AY:]


def _grafik(tur: str, baslik: str, etiketler: list, degerler: list, alan: str | None = None,
            anahtar_degerleri: list | None = None) -> dict[str, Any]:
    """`anahtarlar`: etiketlerle paralel; her nokta istemcinin `filtre` olarak geri
    gönderebileceği {"alan", "deger"} taşır (filtrelenemeyen noktada None)."""
    g = {"tur": tur, "baslik": baslik, "etiketler": etiketler, "degerler": degerler}
    if alan is not None:
        deg = etiketler if anahtar_degerleri is None else anahtar_degerleri
        g["anahtarlar"] = [{"alan": alan, "deger": v} for v in deg]
    else:
        g["anahtarlar"] = [None] * len(etiketler)
    return g


def _zaman(q: _Q, kayma: int, notlar: list[str]) -> list[dict[str, Any]]:
    """Aylık etkinlik, saat ve haftanın günü dağılımı (gerçek zamanı olan kayıtlardan).
    Tek tarama: (ay, saat, gün, gerçek-zaman mı) gruplarıyla sayılır."""
    shift = f", '{kayma:+d} hours'" if kayma else ""
    d = f"strftime('%Y-%m-%d %H:%M:%S', ts{shift})"
    rows = q.rows(f"substr({d}, 1, 7), substr({d}, 12, 2), strftime('%w', ts{shift}), "
                  f"({_GERCEK_ZAMAN}), COUNT(*)", "", "GROUP BY 1, 2, 3, 4")
    toplam = sum(r[4] for r in rows)
    gercek = [r for r in rows if r[3]]
    sayilan = sum(r[4] for r in gercek)
    if toplam - sayilan:
        notlar.append(f"{toplam - sayilan} kayıtta gerçek zaman yok (dosya tarihi); "
                      "zaman grafiklerine alınmadı.")
    if not sayilan:
        return []
    aylik: dict[str, int] = {}
    saat: dict[str, int] = {}
    gun: dict[str, int] = {}
    for ay, sa, gu, _, n in gercek:
        aylik[ay] = aylik.get(ay, 0) + n
        saat[sa] = saat.get(sa, 0) + n
        gun[gu] = gun.get(gu, 0) + n
    aylar = _aylar(min(aylik), max(aylik))
    etiket_saat = "UTC" if not kayma else f"UTC{kayma:+d}"
    return [
        _grafik("zaman", "Aylık etkinlik", aylar, [aylik.get(a, 0) for a in aylar], "ay"),
        _grafik("saat", f"Günün saati ({etiket_saat})", [f"{h:02d}" for h in range(24)],
                [saat.get(f"{h:02d}", 0) for h in range(24)], "saat", list(range(24))),
        _grafik("hafta", f"Haftanın günü ({etiket_saat})", GUNLER,
                [gun.get(str(g), 0) for g in (1, 2, 3, 4, 5, 6, 0)], "gun"),
    ]


def _kind_pasta(q: _Q, baslik: str = "Kayıt türleri") -> list[dict[str, Any]]:
    rows = q.rows("kind, COUNT(*)", "", "GROUP BY kind ORDER BY 2 DESC, kind")
    return [_grafik("pasta", baslik, [r[0] for r in rows], [r[1] for r in rows], "tur")] if rows else []


def _top(q: _Q, ifade: str, extra: str, grup: str, alan: str, *, ornek: str | None = None
         ) -> tuple[list[dict[str, Any]], int]:
    """(en_cok satırları, ifade değeri boş olan kayıt sayısı). `ifade` SQL ifadesi."""
    sel = f"{ifade} AS v, COUNT(*), {ornek or 'NULL'}"
    rows = q.rows(sel, f"({extra}) AND {ifade} IS NOT NULL AND {ifade} <> ''",
                  f"GROUP BY v ORDER BY 2 DESC, v LIMIT {EN_COK_LIMIT}")
    bos = q.one("COUNT(*)", f"({extra}) AND ({ifade} IS NULL OR {ifade} = '')")[0]
    out = []
    for v, n, o in rows:
        d: dict[str, Any] = {"ad": v, "sayi": n, "grup": grup,
                             "anahtar": {"alan": alan, "deger": v}}
        if o:
            d["ornek"] = o
        out.append(d)
    return out, bos


def _cubuk(basl: str, top: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not top:
        return []
    g = _grafik("cubuk", basl, [t["ad"] for t in top], [t["sayi"] for t in top])
    g["anahtarlar"] = [t["anahtar"] for t in top]
    return g and [g]


# ------------------------------------------------------------------ bölge hesaplayıcıları
def _bas(q, kayma, notlar):
    gr, top = _zaman(q, kayma, notlar), []
    t, bos = _top(q, _TERIM, "kind = 'google.arama'", "arama terimi", "terim")
    top += t
    gr += _cubuk("En çok aranan terimler", t)
    if not t:
        notlar.append("Arama terimi: google.arama kaydı ya da başlık alanı yok.")
    s, bos_url = _top(q, _HOST, "kind = 'chrome.ziyaret'", "site", "site")
    top += s
    gr += _cubuk("En çok gidilen siteler", s)
    if not s:
        notlar.append("Site dağılımı: chrome.ziyaret kaydı ya da url alanı yok.")
    elif bos_url:
        notlar.append(f"{bos_url} ziyarette url alanı yok (ör. konum içerdiği için ayrılmış); "
                      "site sayımına girmedi.")
    gr += _kind_pasta(q)
    return gr, top


def _goz(q, kayma, notlar):
    gr, top = _zaman(q, kayma, notlar), []
    t, bos = _top(q, _KANAL, "kind LIKE '%.izleme'", "kanal", "kanal",
                  ornek="MAX(json_extract(payload,'$.baslik'))")
    top += t
    gr += _cubuk("En çok izlenen kanallar", t)
    if not t and q.one("COUNT(*)", "kind LIKE '%.izleme'")[0]:
        notlar.append("Kanal adı: izleme kayıtlarında kanal alanı (alt_baslik) yok.")
    elif bos:
        notlar.append(f"{bos} izleme kaydında kanal adı yok; kanal sayımına girmedi.")
    gr += _kind_pasta(q)
    return gr, top


def _top_sure(q: _Q, ifade: str, extra: str, baslik: str, alan: str) -> list[dict[str, Any]]:
    """Süreye (sure_ms, dakika) göre ilk 10: tek çubuk grafik. Süre alanı yoksa boş."""
    sure = "json_extract(payload, '$.sure_ms')"
    rows = q.rows(f"{ifade} AS v, SUM({sure})", f"({extra}) AND {ifade} IS NOT NULL AND "
                  f"{ifade} <> '' AND {sure} IS NOT NULL",
                  f"GROUP BY v ORDER BY 2 DESC, v LIMIT {EN_COK_LIMIT}")
    if not rows:
        return []
    return [_grafik("cubuk", baslik, [r[0] for r in rows], [round(r[1] / 60000) for r in rows],
                    alan)]


def _kulak(q, kayma, notlar):
    gr, top = _zaman(q, kayma, notlar), []
    dinleme = "kind = 'spotify.dinleme'"
    sanatci = _SANATCI
    t, bos = _top(q, sanatci, dinleme, "sanatçı", "sanatci")
    top += t
    gr += _cubuk("En çok dinlenen sanatçı (dinleme sayısı)", t)
    gr += _top_sure(q, sanatci, dinleme, "En çok dinlenen sanatçı (dakika)", "sanatci")
    if not t:
        notlar.append("Sanatçı: bu alan yok (spotify.dinleme kaydı ya da sanatci alanı yok).")
    elif bos:
        notlar.append(f"{bos} dinleme kaydında sanatçı yok; sayıma girmedi.")
    s, _ = _top(q, _SARKI, dinleme, "parça", "parca",
                ornek="MAX(json_extract(payload, '$.sanatci'))")
    top += s
    gr += _cubuk("En çok dinlenen parça", s)
    if not s:
        notlar.append("Parça: bu alan yok (sarki alanı yok).")
    p, _ = _top(q, _PROGRAM, "kind = 'spotify.podcast'", "podcast", "podcast")
    top += p
    gr += _cubuk("En çok dinlenen podcast programı", p)
    gr += _kind_pasta(q)
    return gr, top


def _agiz(q, kayma, notlar):
    gr, top = _zaman(q, kayma, notlar), []
    t, bos = _top(q, _SUB, "kind IN ('reddit.gonderi', 'reddit.yorum')", "subreddit", "subreddit")
    top += t
    gr += _cubuk("En çok yazılan subreddit", t)
    if not t:
        notlar.append("Subreddit: gönderi/yorum kaydı ya da subreddit alanı yok.")
    elif bos:
        notlar.append(f"{bos} gönderi/yorumda subreddit alanı yok; sayıma girmedi.")
    gr += _kind_pasta(q, "Gönderi / yorum / oy / kaydedilen")
    return gr, top


def _el(q, kayma, notlar):
    gr: list[dict[str, Any]] = []
    top: list[dict[str, Any]] = []
    rows = q.rows("category, COUNT(*)", "", "GROUP BY category ORDER BY 2 DESC, category")
    gr.append(_grafik("pasta", "Kategoriler", [r[0] for r in rows], [r[1] for r in rows],
                      "kategori"))
    # kod (GitHub)
    qk = q.alt(("kod",))
    if qk.one("COUNT(*)")[0]:
        gr += _kind_pasta(qk, "GitHub kayıt türleri")
        depo, bos = _top(qk, _DEPO, "1", "depo", "depo")
        top += depo
        gr += _cubuk("En çok etkinlik olan depo", depo)
        if not depo:
            notlar.append("Depo: bu alan yok (kod kayıtlarında depo/ad alanı yok).")
        dil, _ = _top(qk, _DIL, "1", "dil", "dil")
        gr += _cubuk("Programlama dilleri", dil)
        if not dil:
            notlar.append("Dil: bu alan yok (kod kayıtlarında dil alanı yok).")
    else:
        notlar.append("Depo/dil: bu alan yok (kod kategorisinde kayıt yok).")
    # dosyalar
    qd = q.alt(("dosyalar",))
    if qd.one("COUNT(*)")[0]:
        uz = _UZ
        tur, _ = _top(qd, uz, "1", "dosya türü", "uzanti")
        top += tur
        gr += _cubuk("Dosya türleri (uzantı)", tur)
        if not tur:
            notlar.append("Dosya türü: bu alan yok (dosya kayıtlarında uzanti alanı yok).")
        boy = qd.rows(f"{uz} AS v, SUM(json_extract(payload, '$.boyut'))",
                      f"{uz} IS NOT NULL AND {uz} <> '' AND json_extract(payload, '$.boyut') "
                      "IS NOT NULL", f"GROUP BY v ORDER BY 2 DESC, v LIMIT {EN_COK_LIMIT}")
        if boy:
            gr.append(_grafik("cubuk", "Türe göre toplam boyut (MB)", [r[0] for r in boy],
                              [round(r[1] / 1_048_576, 1) for r in boy], "uzanti"))
    else:
        notlar.append("Dosya türü: bu alan yok (dosyalar kategorisinde kayıt yok).")
    if not q.alt(("notlar",)).one("COUNT(*)")[0]:
        notlar.append("Notlar: bu alan yok (notlar kategorisinde kayıt yok).")
    return gr + _zaman(q, kayma, notlar), top


def _ic(q, kayma, notlar):
    gr = _zaman(q, kayma, notlar)
    t, bos = _top(q, _URUN, "1", "uygulama", "uygulama")
    gr += _cubuk("En çok kullanılan uygulama/ürün", t)
    if not t:
        notlar.append("Uygulama adı: urun alanı yok.")
    notlar.append("Günlük kullanım süresi: bu alan yok (kayıtlarda süre bilgisi yok); "
                  "yalnız kayıt sayısı gösterilir.")
    return gr, t


def _hassas(q, kayma, notlar, *, yer: bool = False):
    gr = _zaman(q, kayma, notlar)
    gr += _kind_pasta(q)
    if yer:
        kay, yerler = q.one("COUNT(*), COUNT(DISTINCT CASE WHEN category = 'konum' THEN text END)")
        gr.append(_grafik("cubuk", "Sayılar", ["Kayıt", "Farklı yer"], [kay, yerler]))
        notlar.append("Yer adları ve koordinatlar gösterilmez; yalnız sayılar.")
    else:
        notlar.append("İçerik gösterilmez; yalnız sayı ve zaman dağılımı.")
    return gr, []


def _zihin(q, kayma, notlar):
    """Yapay zekâ sohbetleri: yalnız sayı, zaman dağılımı, platform ve konuşma sayısı."""
    gr = _zaman(q, kayma, notlar)
    plat = q.rows(f"{_PLAT}, COUNT(*)", "", "GROUP BY 1 ORDER BY 2 DESC, 1")
    gr.append(_grafik("pasta", "Kaynak (platform)", [r[0] for r in plat], [r[1] for r in plat],
                      "platform"))
    mesaj, konusma, kul, asist = q.one(
        "SUM(kind = 'sohbet.mesaj'), COUNT(DISTINCT json_extract(payload, '$.konusma_id')), "
        "SUM(json_extract(payload, '$.rol') = 'kullanici'), "
        "SUM(json_extract(payload, '$.rol') = 'asistan')")
    gr.append(_grafik("cubuk", "Sayılar", ["Mesaj", "Konuşma", "Kullanıcı mesajı",
                                            "Asistan mesajı"],
                      [mesaj or 0, konusma or 0, kul or 0, asist or 0]))
    if not konusma:
        notlar.append("Konuşma sayısı: bu alan yok (konusma_id alanı yok).")
    notlar.append("İçerik gösterilmez; yalnız sayı ve zaman dağılımı.")
    return gr, []


_YOK_ALAN = {
    "kulak": ("Sanatçı/şarkı: bu alan yok (müzik kaydı yok; Spotify arşivi alınmadı).",),
    "el": ("Depo/dil ve dosya türü: bu alan yok (kod/dosya/not kaydı yok).",),
    "ic": ("Günlük kullanım süresi: bu alan yok.",),
}

_HESAP = {
    "bas": _bas, "goz": _goz, "kulak": _kulak, "agiz": _agiz, "el": _el, "ic": _ic,
    "zihin": _zihin,
    "kalp": lambda q, k, n: _hassas(q, k, n),
    "karin": lambda q, k, n: _hassas(q, k, n),
    "ayak": lambda q, k, n: _hassas(q, k, n, yer=True),
}


# ------------------------------------------------------------------ genel API
def harita(hub: Hub, *, ac_hassas: Iterable[str] = frozenset(), now: str | datetime | None = None,
           bolgeler: dict[str, tuple[str, tuple[str, ...]]] | None = None) -> dict[str, Any]:
    """Tüm figürün özeti. `ac_hassas`: açılan hassas bölge kimlikleri (ya da kategorileri).
    `now`: kalıcı olmayan süre filtresi için saat (persona süre dolumu)."""
    reg = bolgeler or VARSAYILAN_BOLGELER
    ac = set(ac_hassas)
    stats = {c: (n, a, b) for c, n, a, b in hub.query(
        "SELECT category, COUNT(*), MIN(CASE WHEN " + _GERCEK_ZAMAN + " THEN ts END), "
        "MAX(CASE WHEN " + _GERCEK_ZAMAN + " THEN ts END) FROM events NOT INDEXED WHERE hidden = 0 "
        "GROUP BY category")}
    out_bolgeler = []
    for bid, (ad, kats) in reg.items():
        if _kilitli(bid, kats, ac):
            out_bolgeler.append({"id": bid, "ad": ad, "kategoriler": list(kats),
                                 "olay_sayisi": None, "ilk": None, "son": None,
                                 "kilitli": True, "ozet": "Kilitli"})
            continue
        n = sum(stats.get(c, (0, None, None))[0] for c in kats)
        ilkler = [stats[c][1] for c in kats if c in stats and stats[c][1]]
        sonlar = [stats[c][2] for c in kats if c in stats and stats[c][2]]
        ilk, son = (min(ilkler), max(sonlar)) if ilkler else (None, None)
        ozet = VERI_YOK if not n else (
            f"{n} kayıt, {ilk[:10]} ile {son[:10]} arası (veriden sayım)" if ilk
            else f"{n} kayıt, tarihsiz (veriden sayım)")
        out_bolgeler.append({"id": bid, "ad": ad, "kategoriler": list(kats), "olay_sayisi": n,
                             "ilk": ilk, "son": son, "kilitli": False, "ozet": ozet})
    kilitli_kats = {c for bid, (_, kats) in reg.items() if _kilitli(bid, kats, ac) for c in kats}
    # Profil toplamı kilitli bölgelerin kategorilerini içermez (sayı bile sızmasın).
    sayilan = [v for c, v in stats.items() if c not in kilitli_kats]
    pr = PersonaReader(hub, clock=lambda: _now_dt(now))
    ad = next((f.statement for f in pr.list_facts(["kimlik"]) if f.fact_key == "ad"),
              hub.root.name)
    beyan = [{"kategori": f.category, "durum": f.status,
              "kaynak": pr.source_label(f.source_id) if f.status == "dosyadan_alinan" else None,
              "veri": f.statement} for f in pr.list_facts()]
    return {
        "profil": {"ad": ad, "olay": sum(v[0] for v in sayilan),
                   "ilk": min((v[1] for v in sayilan if v[1]), default=None),
                   "son": max((v[2] for v in sayilan if v[2]), default=None)},
        "bolgeler": out_bolgeler,
        "beyan": beyan,
        "not": SAYIM_NOTU,
    }


# ------------------------------------------------------------------ filtre (çapraz filtreleme)
Filtre = dict[str, Any]


def izinli_alanlar(bolge_id: str) -> tuple[str, ...]:
    return (*ORTAK_ALANLAR, *BOLGE_ALANLARI.get(bolge_id, ()))


def _degerler(alan: str, v: Any) -> list[Any]:
    vs = list(v) if isinstance(v, (list, tuple, set, frozenset)) else [v]
    if not vs:
        raise FormatError(f"Filtre '{alan}' için değer boş.")
    out: list[Any] = []
    for x in vs:
        if alan == "ay":
            if not (isinstance(x, str) and len(x) == 7 and x[4] == "-" and x[:4].isdigit()
                    and x[5:].isdigit() and 1 <= int(x[5:]) <= 12):
                raise FormatError("Filtre 'ay' YYYY-AA biçiminde olmalı.")
            out.append(x)
        elif alan == "saat":
            try:
                h = int(x)
            except (TypeError, ValueError):
                raise FormatError("Filtre 'saat' 0-23 arası tamsayı olmalı.") from None
            if not 0 <= h <= 23 or isinstance(x, bool):
                raise FormatError("Filtre 'saat' 0-23 arası olmalı.")
            out.append(f"{h:02d}")
        elif alan == "gun":
            if isinstance(x, str) and x in GUNLER:
                i = GUNLER.index(x)
            else:
                try:
                    i = int(x)
                except (TypeError, ValueError):
                    raise FormatError("Filtre 'gun' Pzt..Paz ya da 0-6 olmalı.") from None
                if not 0 <= i <= 6 or isinstance(x, bool):
                    raise FormatError("Filtre 'gun' Pzt..Paz ya da 0-6 olmalı.")
            out.append(str((i + 1) % 7))  # SQLite %w: Pazar=0
        else:
            if not isinstance(x, str) or not x:
                raise FormatError(f"Filtre '{alan}' için değer metin olmalı.")
            out.append(x.lower() if alan in KUCUK_HARF_ALANLAR else x)
    return out


def _filtre_parcalari(bolge_id: str, filtre: Filtre | None, kayma: int
                      ) -> list[tuple[str, list]]:
    """Filtreyi (SQL parçası, parametreler) listesine çevirir; alanlar VE ile birleşir,
    bir alanın birden çok değeri VEYA'dır. Bu bölgede tanımsız alan FormatError."""
    if not filtre:
        return []
    izinli = izinli_alanlar(bolge_id)
    shift = f", '{kayma:+d} hours'" if kayma else ""
    d = f"strftime('%Y-%m-%d %H:%M:%S', ts{shift})"
    out: list[tuple[str, list]] = []
    for alan, v in filtre.items():
        if alan not in izinli:
            raise FormatError(f"'{bolge_id}' bölgesinde '{alan}' filtre alanı yok "
                              f"(geçerli: {', '.join(izinli)}).")
        vals = _degerler(alan, v)
        ph = ",".join("?" * len(vals))
        if alan == "ay":
            ifade = f"substr({d}, 1, 7)"
        elif alan == "saat":
            ifade = f"substr({d}, 12, 2)"
        elif alan == "gun":
            ifade = f"strftime('%w', ts{shift})"
        else:
            ifade = f"({ALAN_IFADE[alan][0]})"
        frag = f"{ifade} IN ({ph})"
        if alan in ALAN_IFADE and ALAN_IFADE[alan][1] != "1":
            frag = f"({ALAN_IFADE[alan][1]}) AND {frag}"  # grafikteki sayımla aynı kayıt kümesi
        if alan in ZAMAN_ALANLARI:
            frag = f"({_GERCEK_ZAMAN}) AND {frag}"  # tarihi olmayan kayıt zaman filtresine girmez
        out.append((frag, vals))
    return out


def _bolge_kaydi(reg, bolge_id: str):
    if bolge_id not in reg:
        raise NotFoundError(f"Bilinmeyen bölge: {bolge_id}")
    return reg[bolge_id]


def bolge(hub: Hub, bolge_id: str, *, ac_hassas: Iterable[str] = frozenset(),
          aralik: tuple[Any, Any] | None = None, filtre: Filtre | None = None,
          utc_kaydirma: int = 0,
          bolgeler: dict[str, tuple[str, tuple[str, ...]]] | None = None) -> dict[str, Any]:
    """Bir bölgenin ayrıntılı grafikleri. `aralik=(baslangic, bitis)` (UTC, ISO; None serbest).
    `filtre={alan: değer | [değerler]}`: bütün grafikler ve en_cok listeleri filtreye göre
    yeniden hesaplanır (çapraz filtre); alan adları grafik/en_cok `anahtar`larından gelir.
    `utc_kaydirma`: saat/gün grafikleri için UTC'ye eklenecek saat (İstanbul: 3)."""
    reg = bolgeler or VARSAYILAN_BOLGELER
    ad, kats = _bolge_kaydi(reg, bolge_id)
    if _kilitli(bolge_id, kats, ac_hassas):
        return {"id": bolge_id, "ad": ad, "kilitli": True, "grafikler": [], "en_cok": [],
                "notlar": ["Kilitli"]}
    kayma = int(utc_kaydirma)
    q = _Q(hub, kats, aralik, _filtre_parcalari(bolge_id, filtre, kayma))
    notlar: list[str] = []
    toplam = q.one("COUNT(*)")[0]
    if toplam == 0:
        yok = ["Filtreye uyan kayıt yok." if filtre else VERI_YOK]
        if not filtre:
            yok += _YOK_ALAN.get(bolge_id, ())
        return {"id": bolge_id, "ad": ad, "kilitli": False, "toplam": 0, "filtre": filtre or {},
                "grafikler": [], "en_cok": [], "notlar": yok}
    gr, top = _HESAP[bolge_id](q, kayma, notlar)
    notlar.append(SAYIM_NOTU)
    return {"id": bolge_id, "ad": ad, "kilitli": False, "toplam": toplam, "filtre": filtre or {},
            "grafikler": gr, "en_cok": top, "notlar": notlar}


# ------------------------------------------------------------------ kayıt listesi, ayrıntı, karşılaştırma
MAX_SAYFA = 200


def _kaynak_adi(kind: str | None, dosya: str | None) -> str | None:
    if kind is None:
        return None
    return f"{kind}: {dosya}" if dosya else kind


def kayitlar(hub: Hub, bolge_id: str, *, filtre: Filtre | None = None,
             aralik: tuple[Any, Any] | None = None, limit: int = 50, offset: int = 0,
             ac_hassas: Iterable[str] = frozenset(), utc_kaydirma: int = 0,
             bolgeler: dict[str, tuple[str, tuple[str, ...]]] | None = None) -> dict[str, Any]:
    """Filtreye uyan kayıtların sayfası (yeniden eskiye). Hassas bölgede içerik YOK: yalnız
    event_id, ts, kind, kaynak adı. Kilitliyken {"kilitli": True, "toplam": None}."""
    reg = bolgeler or VARSAYILAN_BOLGELER
    ad, kats = _bolge_kaydi(reg, bolge_id)
    if _kilitli(bolge_id, kats, ac_hassas):
        return {"id": bolge_id, "kilitli": True, "toplam": None, "kayitlar": []}
    limit = max(1, min(int(limit), MAX_SAYFA))
    offset = max(0, int(offset))
    q = _Q(hub, kats, aralik, _filtre_parcalari(bolge_id, filtre, int(utc_kaydirma)))
    toplam = q.one("COUNT(*)")[0]
    ids = [r[0] for r in q.rows("event_id", "", "ORDER BY ts DESC, seq DESC LIMIT ? OFFSET ?",
                                [limit, offset])]
    hassas = bolge_id in HASSAS_BOLGELER
    out: list[dict[str, Any]] = []
    if ids:
        ph = ",".join("?" * len(ids))
        rows = {r[0]: r for r in hub.query(
            "SELECT event_id, ts, kind, category, "
            + ("NULL, NULL" if hassas else
               "COALESCE(json_extract(payload, '$.baslik'), substr(text, 1, 120)), "
               "substr(text, 1, 200)")
            + ", (SELECT kind FROM sources WHERE source_id = events.source_id), "
            "(SELECT name FROM raw_files WHERE raw_files.source_id = events.source_id "
            f"ORDER BY stored_at, raw_id LIMIT 1) FROM events WHERE event_id IN ({ph})", ids)}
        for i in ids:
            r = rows[i]
            out.append({"event_id": r[0], "ts": r[1], "kind": r[2], "kategori": r[3],
                        "baslik": r[4], "ozet": r[5], "kaynak_adi": _kaynak_adi(r[6], r[7])})
    return {"id": bolge_id, "kilitli": False, "toplam": toplam, "limit": limit, "offset": offset,
            "kayitlar": out}


def _gps_temizle(obj: Any, depth: int = 0) -> Any:
    if depth > 8:
        return obj
    if isinstance(obj, dict):
        return {k: ("[konum alanı gizlendi]" if str(k).lower() in _GPS_ANAHTARLARI
                    else _gps_temizle(v, depth + 1)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_gps_temizle(v, depth + 1) for v in obj]
    return obj


_GPS_ANAHTARLARI = frozenset({"gps", "lat", "lon", "lng", "latitude", "longitude", "enlem",
                              "boylam", "koordinat", "koordinatlar", "coordinates", "geo",
                              "geolocation", "yerler"})


def ayrinti(hub: Hub, event_id: str, *, ac_hassas: Iterable[str] = frozenset(),
            bolgeler: dict[str, tuple[str, tuple[str, ...]]] | None = None) -> dict[str, Any]:
    """Tek kaydın alanları ve kaynağı. Hassas kategoride (kilitli ya da açık) içerik YOK:
    açıkken yalnız zaman, tür ve kaynak bilgisi; kilitliyken yalnız {"kilitli": True}.
    `tekrar`: aynı tür+metinli kayıtların ilk/son görülmesi ve sayısı (metni olmayan için None)."""
    reg = bolgeler or VARSAYILAN_BOLGELER
    r = hub.query_one("SELECT event_id, ts, kind, category, payload, text, source_id, device_id, "
                      "ingested_at FROM events WHERE event_id = ? AND hidden = 0", (event_id,))
    if r is None:
        raise NotFoundError(f"Kayıt yok: {event_id}")
    eid, ts, kind, cat, payload, text, sid, dev, ing = r
    bid = next((b for b, (_, kats) in reg.items() if cat in kats), None)
    hassas = (bid in HASSAS_BOLGELER) if bid else (cat in Category.SENSITIVE)
    if hassas and (_kilitli(bid, reg[bid][1], ac_hassas) if bid else cat not in set(ac_hassas)):
        return {"event_id": eid, "kilitli": True}
    src = hub.query_one("SELECT kind, version, file_sha256, imported_at, removed_at FROM sources "
                        "WHERE source_id = ?", (sid,))
    dosyalar = [{"ad": n, "sha256": h} for n, h in hub.query(
        "SELECT name, sha256 FROM raw_files WHERE source_id = ? ORDER BY stored_at, raw_id LIMIT 5",
        (sid,))]
    kaynak = None if src is None else {
        "source_id": sid, "tur": src[0], "surum": src[1], "dosya_sha256": src[2],
        "ice_aktarma": src[3], "dosyalar": dosyalar,
        "ad": _kaynak_adi(src[0], dosyalar[0]["ad"] if dosyalar else None)}
    out: dict[str, Any] = {"event_id": eid, "kilitli": False, "bolge": bid, "ts": ts, "kind": kind,
                           "kategori": cat, "cihaz": dev, "ice_aktarma_ts": ing, "kaynak": kaynak,
                           "alanlar": None, "metin": None, "tekrar": None}
    if hassas:
        out["not"] = "Hassas kategori: içerik gösterilmez."
        return out
    out["alanlar"] = _gps_temizle(json.loads(payload))
    out["metin"] = (text or "")[:20000]
    if text:
        ilk, son, n = hub.query_one(
            "SELECT MIN(ts), MAX(ts), COUNT(*) FROM events WHERE hidden = 0 AND category = ? "
            "AND kind = ? AND text = ?", (cat, kind, text))
        out["tekrar"] = {"ilk": ilk, "son": son, "sayi": n}
    return out


def karsilastir(hub: Hub, bolge_id: str, aralik_a: tuple[Any, Any], aralik_b: tuple[Any, Any],
                *, ac_hassas: Iterable[str] = frozenset(), filtre: Filtre | None = None,
                utc_kaydirma: int = 0,
                bolgeler: dict[str, tuple[str, tuple[str, ...]]] | None = None) -> dict[str, Any]:
    """İki dönemin (a, b) yan yana özeti: toplam, grafikler, en_cok ve en çok değişenler."""
    kw = dict(ac_hassas=ac_hassas, filtre=filtre, utc_kaydirma=utc_kaydirma, bolgeler=bolgeler)
    a = bolge(hub, bolge_id, aralik=aralik_a, **kw)
    if a["kilitli"]:
        return {"id": bolge_id, "ad": a["ad"], "kilitli": True, "notlar": ["Kilitli"]}
    b = bolge(hub, bolge_id, aralik=aralik_b, **kw)
    ta, tb = a["toplam"], b["toplam"]

    def yan(x, aralik):
        return {"aralik": list(aralik) if aralik else None, "toplam": x["toplam"],
                "grafikler": x["grafikler"], "en_cok": x["en_cok"], "notlar": x["notlar"]}
    degisim: dict[tuple[str, str], dict[str, Any]] = {}
    for taraf, x in (("a", a), ("b", b)):
        for e in x["en_cok"]:
            d = degisim.setdefault((e["grup"], e["ad"]), {"ad": e["ad"], "grup": e["grup"],
                                                          "anahtar": e["anahtar"], "a": 0, "b": 0})
            d[taraf] = e["sayi"]
    for d in degisim.values():
        d["fark"] = d["b"] - d["a"]
    en_degisen = sorted(degisim.values(), key=lambda d: (-abs(d["fark"]), d["grup"], d["ad"]))
    return {"id": bolge_id, "ad": a["ad"], "kilitli": False,
            "a": yan(a, aralik_a), "b": yan(b, aralik_b),
            "fark": {"toplam": tb - ta,
                     "yuzde": None if ta == 0 else round((tb - ta) * 100 / ta, 1)},
            "en_cok_degisim": en_degisen[:EN_COK_LIMIT],
            "notlar": [SAYIM_NOTU]}
