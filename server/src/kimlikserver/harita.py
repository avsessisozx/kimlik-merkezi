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

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from kimlikcore import Hub, NotFoundError, norm_ts

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

    def __init__(self, hub: Hub, kategoriler: tuple[str, ...], aralik):
        self.hub = hub
        self.aralik = aralik
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

    def alt(self, kategoriler: tuple[str, ...]) -> "_Q":
        return _Q(self.hub, kategoriler, self.aralik)

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


def _grafik(tur: str, baslik: str, etiketler: list, degerler: list) -> dict[str, Any]:
    return {"tur": tur, "baslik": baslik, "etiketler": etiketler, "degerler": degerler}


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
        _grafik("zaman", "Aylık etkinlik", aylar, [aylik.get(a, 0) for a in aylar]),
        _grafik("saat", f"Günün saati ({etiket_saat})", [f"{h:02d}" for h in range(24)],
                [saat.get(f"{h:02d}", 0) for h in range(24)]),
        _grafik("hafta", f"Haftanın günü ({etiket_saat})", GUNLER,
                [gun.get(str(g), 0) for g in (1, 2, 3, 4, 5, 6, 0)]),
    ]


def _kind_pasta(q: _Q, baslik: str = "Kayıt türleri") -> list[dict[str, Any]]:
    rows = q.rows("kind, COUNT(*)", "", "GROUP BY kind ORDER BY 2 DESC, kind")
    return [_grafik("pasta", baslik, [r[0] for r in rows], [r[1] for r in rows])] if rows else []


def _top(q: _Q, ifade: str, extra: str, grup: str, *, ornek: str | None = None
         ) -> tuple[list[dict[str, Any]], int]:
    """(en_cok satırları, ifade değeri boş olan kayıt sayısı). `ifade` SQL ifadesi."""
    sel = f"{ifade} AS v, COUNT(*), {ornek or 'NULL'}"
    rows = q.rows(sel, f"({extra}) AND {ifade} IS NOT NULL AND {ifade} <> ''",
                  f"GROUP BY v ORDER BY 2 DESC, v LIMIT {EN_COK_LIMIT}")
    bos = q.one("COUNT(*)", f"({extra}) AND ({ifade} IS NULL OR {ifade} = '')")[0]
    out = []
    for v, n, o in rows:
        d: dict[str, Any] = {"ad": v, "sayi": n, "grup": grup}
        if o:
            d["ornek"] = o
        out.append(d)
    return out, bos


def _cubuk(basl: str, top: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_grafik("cubuk", basl, [t["ad"] for t in top], [t["sayi"] for t in top])] if top else []


# ------------------------------------------------------------------ bölge hesaplayıcıları
def _bas(q, kayma, notlar):
    gr, top = _zaman(q, kayma, notlar), []
    terim = ("lower(CASE WHEN json_extract(payload,'$.baslik') LIKE 'Searched for %' "
             "THEN substr(json_extract(payload,'$.baslik'), 14) "
             "ELSE json_extract(payload,'$.baslik') END)")
    t, bos = _top(q, terim, "kind = 'google.arama'", "arama terimi")
    top += t
    gr += _cubuk("En çok aranan terimler", t)
    if not t:
        notlar.append("Arama terimi: google.arama kaydı ya da başlık alanı yok.")
    host_ifade = _HOST
    s, bos_url = _top(q, host_ifade, "kind = 'chrome.ziyaret'", "site")
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
    kanal = "json_extract(payload, '$.alt_baslik[0]')"
    t, bos = _top(q, kanal, "kind LIKE '%.izleme'", "kanal",
                  ornek="MAX(json_extract(payload,'$.baslik'))")
    top += t
    gr += _cubuk("En çok izlenen kanallar", t)
    if not t and q.one("COUNT(*)", "kind LIKE '%.izleme'")[0]:
        notlar.append("Kanal adı: izleme kayıtlarında kanal alanı (alt_baslik) yok.")
    elif bos:
        notlar.append(f"{bos} izleme kaydında kanal adı yok; kanal sayımına girmedi.")
    gr += _kind_pasta(q)
    return gr, top


def _top_sure(q: _Q, ifade: str, extra: str, baslik: str) -> list[dict[str, Any]]:
    """Süreye (sure_ms, dakika) göre ilk 10: tek çubuk grafik. Süre alanı yoksa boş."""
    sure = "json_extract(payload, '$.sure_ms')"
    rows = q.rows(f"{ifade} AS v, SUM({sure})", f"({extra}) AND {ifade} IS NOT NULL AND "
                  f"{ifade} <> '' AND {sure} IS NOT NULL",
                  f"GROUP BY v ORDER BY 2 DESC, v LIMIT {EN_COK_LIMIT}")
    if not rows:
        return []
    return [_grafik("cubuk", baslik, [r[0] for r in rows], [round(r[1] / 60000) for r in rows])]


def _kulak(q, kayma, notlar):
    gr, top = _zaman(q, kayma, notlar), []
    dinleme = "kind = 'spotify.dinleme'"
    sanatci = "json_extract(payload, '$.sanatci')"
    t, bos = _top(q, sanatci, dinleme, "sanatçı")
    top += t
    gr += _cubuk("En çok dinlenen sanatçı (dinleme sayısı)", t)
    gr += _top_sure(q, sanatci, dinleme, "En çok dinlenen sanatçı (dakika)")
    if not t:
        notlar.append("Sanatçı: bu alan yok (spotify.dinleme kaydı ya da sanatci alanı yok).")
    elif bos:
        notlar.append(f"{bos} dinleme kaydında sanatçı yok; sayıma girmedi.")
    s, _ = _top(q, "json_extract(payload, '$.sarki')", dinleme, "parça",
                ornek="MAX(json_extract(payload, '$.sanatci'))")
    top += s
    gr += _cubuk("En çok dinlenen parça", s)
    if not s:
        notlar.append("Parça: bu alan yok (sarki alanı yok).")
    p, _ = _top(q, "json_extract(payload, '$.program')", "kind = 'spotify.podcast'", "podcast")
    top += p
    gr += _cubuk("En çok dinlenen podcast programı", p)
    gr += _kind_pasta(q)
    return gr, top


def _agiz(q, kayma, notlar):
    gr, top = _zaman(q, kayma, notlar), []
    t, bos = _top(q, "json_extract(payload, '$.subreddit')",
                  "kind IN ('reddit.gonderi', 'reddit.yorum')", "subreddit")
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
    gr.append(_grafik("pasta", "Kategoriler", [r[0] for r in rows], [r[1] for r in rows]))
    # kod (GitHub)
    qk = q.alt(("kod",))
    if qk.one("COUNT(*)")[0]:
        gr += _kind_pasta(qk, "GitHub kayıt türleri")
        depo, bos = _top(qk, "COALESCE(json_extract(payload, '$.depo'), json_extract(payload, '$.ad'))",
                         "1", "depo")
        top += depo
        gr += _cubuk("En çok etkinlik olan depo", depo)
        if not depo:
            notlar.append("Depo: bu alan yok (kod kayıtlarında depo/ad alanı yok).")
        dil, _ = _top(qk, "json_extract(payload, '$.dil')", "1", "dil")
        gr += _cubuk("Programlama dilleri", dil)
        if not dil:
            notlar.append("Dil: bu alan yok (kod kayıtlarında dil alanı yok).")
    else:
        notlar.append("Depo/dil: bu alan yok (kod kategorisinde kayıt yok).")
    # dosyalar
    qd = q.alt(("dosyalar",))
    if qd.one("COUNT(*)")[0]:
        uz = "json_extract(payload, '$.uzanti')"
        tur, _ = _top(qd, uz, "1", "dosya türü")
        top += tur
        gr += _cubuk("Dosya türleri (uzantı)", tur)
        if not tur:
            notlar.append("Dosya türü: bu alan yok (dosya kayıtlarında uzanti alanı yok).")
        boy = qd.rows(f"{uz} AS v, SUM(json_extract(payload, '$.boyut'))",
                      f"{uz} IS NOT NULL AND {uz} <> '' AND json_extract(payload, '$.boyut') "
                      "IS NOT NULL", f"GROUP BY v ORDER BY 2 DESC, v LIMIT {EN_COK_LIMIT}")
        if boy:
            gr.append(_grafik("cubuk", "Türe göre toplam boyut (MB)", [r[0] for r in boy],
                              [round(r[1] / 1_048_576, 1) for r in boy]))
    else:
        notlar.append("Dosya türü: bu alan yok (dosyalar kategorisinde kayıt yok).")
    if not q.alt(("notlar",)).one("COUNT(*)")[0]:
        notlar.append("Notlar: bu alan yok (notlar kategorisinde kayıt yok).")
    return gr + _zaman(q, kayma, notlar), top


def _ic(q, kayma, notlar):
    gr = _zaman(q, kayma, notlar)
    t, bos = _top(q, "json_extract(payload, '$.urun')", "1", "uygulama")
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
    plat = q.rows("COALESCE(json_extract(payload, '$.platform'), 'bilinmeyen'), COUNT(*)", "",
                  "GROUP BY 1 ORDER BY 2 DESC, 1")
    gr.append(_grafik("pasta", "Kaynak (platform)", [r[0] for r in plat], [r[1] for r in plat]))
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


def bolge(hub: Hub, bolge_id: str, *, ac_hassas: Iterable[str] = frozenset(),
          aralik: tuple[Any, Any] | None = None, utc_kaydirma: int = 0,
          bolgeler: dict[str, tuple[str, tuple[str, ...]]] | None = None) -> dict[str, Any]:
    """Bir bölgenin ayrıntılı grafikleri. `aralik=(baslangic, bitis)` (UTC, ISO; None serbest).
    `utc_kaydirma`: saat/gün grafikleri için UTC'ye eklenecek saat (İstanbul: 3)."""
    reg = bolgeler or VARSAYILAN_BOLGELER
    if bolge_id not in reg:
        raise NotFoundError(f"Bilinmeyen bölge: {bolge_id}")
    ad, kats = reg[bolge_id]
    if _kilitli(bolge_id, kats, ac_hassas):
        return {"id": bolge_id, "ad": ad, "kilitli": True, "grafikler": [], "en_cok": [],
                "notlar": ["Kilitli"]}
    q = _Q(hub, kats, aralik)
    notlar: list[str] = []
    if q.one("COUNT(*)")[0] == 0:
        return {"id": bolge_id, "ad": ad, "kilitli": False, "grafikler": [], "en_cok": [],
                "notlar": [VERI_YOK, *_YOK_ALAN.get(bolge_id, ())]}
    gr, top = _HESAP[bolge_id](q, int(utc_kaydirma), notlar)
    notlar.append(SAYIM_NOTU)
    return {"id": bolge_id, "ad": ad, "kilitli": False, "grafikler": gr, "en_cok": top,
            "notlar": notlar}
