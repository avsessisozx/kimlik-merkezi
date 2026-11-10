"""§12 + genişletilmiş (filtre / aralık / kayıtlar / ayrıntı) SAHTE sağlayıcı.

Yalnız testlerde ve ekran görüntüsü demosunda kullanılır; üretim kodu bunu içe aktarmaz. Gerçek işlevler
`kimlikserver.harita` içindedir. Bu modül hub'daki GERÇEK olaylardan (demo_veri.py ile üretilmiş ya da
içe aktarılmış) SQL ile sayım yapar; sözleşme İ2'ye böyle gösterilir:

    bolge(hub, bolge_id, *, ac_hassas, aralik=None, filtre=None) -> dict
    kayitlar(hub, bolge_id, *, ac_hassas, filtre=None, aralik=None, limit=20, offset=0) -> dict
    ayrinti(hub, event_id) -> dict
    harita(hub, *, ac_hassas, now=None, aralik=None) -> dict

`aralik = {"baslangic": ts|None, "bitis": ts|None}`; `filtre = {boyut: deger}` (VE ile birleşir).
Boyutlar: ay (YYYY-MM), gun (0=Pzt..6=Paz), saat (0-23) + bölgeye özgü (kanal, terim, site, sanatci, ...).
Çapraz filtreleme: bir grafik kendi boyutunun filtresini UYGULAMAZ (bağlam kalsın), `secili` ile vurgulanır.
"""
from __future__ import annotations

import json

from kimlikserver.persona import PersonaReader

GUNLER = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
AY_AD = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
PAYLOAD = lambda a: f"json_extract(payload, '$.{a}')"  # noqa: E731

# bolge_id -> (ad, kategoriler, hassas, boyutlar{ad: (etiket, ifade, kind_kosulu|None)}, birincil)
BOLGELER = {
    "bas": ("Baş: ilgi ve merak", ["tarama"], False,
            {"terim": ("Arama terimleri", PAYLOAD("terim"), "chrome.arama"),
             "site": ("Siteler", PAYLOAD("site"), "chrome.ziyaret")}, "terim"),
    "zihin": ("Zihin: yapay zekâ sohbetleri (hassas)", ["sohbet"], True,
              {"platform": ("Platformlar", PAYLOAD("platform"), None)}, "platform"),
    "goz": ("Gözler: izledikleri", ["video"], False,
            {"kanal": ("Kanallar", PAYLOAD("kanal"), None), "video": ("Videolar", PAYLOAD("video"), None),
             "tur": ("Türler", PAYLOAD("tur"), None)}, "kanal"),
    "kulak": ("Kulaklar: dinledikleri", ["muzik"], False,
              {"sanatci": ("Sanatçılar", PAYLOAD("sanatci"), None), "parca": ("Parçalar", PAYLOAD("parca"), None),
               "tur": ("Türler", PAYLOAD("tur"), None)}, "sanatci"),
    "agiz": ("Ağız: yazdıkları/söyledikleri", ["sosyal"], False,
             {"subreddit": ("Subreddit'ler", PAYLOAD("subreddit"), None), "tur": ("Gönderi türü", PAYLOAD("tur"), None)}, "subreddit"),
    "el": ("Eller: üretim ve iş", ["kod", "dosyalar", "notlar"], False,
           {"depo": ("Depolar", PAYLOAD("depo"), "github.commit"), "dosya_turu": ("Dosya türleri", PAYLOAD("dosya_turu"), None),
            "kategori": ("Kategori", "category", None)}, "depo"),
    "kalp": ("Kalp: kişisel (hassas)", ["mesaj"], True, {}, None),
    "karin": ("Karın: e-posta (hassas)", ["eposta"], True, {}, None),
    "ayak": ("Ayaklar: konum (hassas)", ["konum", "medya_meta"], True,
             {"yer": ("Yerler", PAYLOAD("yer"), None)}, "yer"),
    "ic": ("Merkez: uygulama kullanımı", ["uygulama"], False,
           {"uygulama": ("Uygulamalar", PAYLOAD("uygulama"), None)}, "uygulama"),
}
ZAMAN_IFADE = {"ay": "substr(ts, 1, 7)", "gun": "((CAST(strftime('%w', ts) AS INTEGER) + 6) % 7)",
               "saat": "CAST(substr(ts, 12, 2) AS INTEGER)"}


def _tum_ifadeler(bolge_id):
    d = dict(ZAMAN_IFADE)
    for k, (_, ifade, _kind) in BOLGELER[bolge_id][3].items():
        d[k] = ifade
    return d


def _kosul(bolge_id, aralik, filtre, haric=()):
    kats = BOLGELER[bolge_id][1]
    w = [f"hidden = 0 AND category IN ({','.join('?' * len(kats))})"]
    a = list(kats)
    aralik = aralik or {}
    if aralik.get("baslangic"):
        w.append("ts >= ?")
        a.append(aralik["baslangic"])
    if aralik.get("bitis"):
        w.append("ts <= ?")
        a.append(aralik["bitis"])
    ifadeler = _tum_ifadeler(bolge_id)
    for k, v in (filtre or {}).items():
        if k in haric or k not in ifadeler:
            continue
        w.append(f"{ifadeler[k]} = ?")
        a.append(v)
    for k, (_, _ifade, kind) in BOLGELER[bolge_id][3].items():   # boyut yalnız belli türde geçerliyse
        if kind and k in (filtre or {}) and k not in haric:
            w.append("kind = ?")
            a.append(kind)
    return " AND ".join(w), a


def _say(hub, bolge_id, aralik, filtre, ifade, haric=(), limit=None, kind=None, sirala="cnt DESC"):
    w, a = _kosul(bolge_id, aralik, filtre, haric)
    if kind:
        w += " AND kind = ?"
        a.append(kind)
    sql = f"SELECT {ifade} AS k, count(*) AS cnt FROM events WHERE {w} AND {ifade} IS NOT NULL GROUP BY k ORDER BY {sirala}"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return hub.query(sql, a)


def _toplam(hub, bolge_id, aralik, filtre):
    w, a = _kosul(bolge_id, aralik, filtre)
    r = hub.query_one(f"SELECT count(*), min(ts), max(ts) FROM events WHERE {w}", a)
    return r[0], r[1], r[2]


def _ay_listesi(ilk, son):
    if not ilk:
        return []
    y, m = int(ilk[:4]), int(ilk[5:7])
    ys, ms = int(son[:4]), int(son[5:7])
    out = []
    while (y, m) <= (ys, ms):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _grafik(tur, baslik, etiketler, degerler, boyut=None, secili=None, **ek):
    g = {"tur": tur, "baslik": baslik, "etiketler": etiketler, "degerler": degerler}
    if boyut:
        g["boyut"] = boyut
    if secili is not None:
        g["secili"] = secili
    g.update(ek)
    return g


def _zaman(hub, bid, aralik, filtre):
    gl = _say(hub, bid, aralik, filtre, ZAMAN_IFADE["ay"], haric=("ay",), sirala="k ASC")
    if not gl:
        return None
    ilk, son = gl[0][0], gl[-1][0]
    d = {k: c for k, c in gl}
    aylar = _ay_listesi(ilk, son)
    return _grafik("zaman", "Aylık etkinlik", aylar, [d.get(a, 0) for a in aylar], "ay", (filtre or {}).get("ay"))


def _saat(hub, bid, aralik, filtre):
    d = dict(_say(hub, bid, aralik, filtre, ZAMAN_IFADE["saat"], haric=("saat", "gun")))
    return _grafik("saat", "Günün saatleri", [f"{h:02d}" for h in range(24)], [d.get(h, 0) for h in range(24)], "saat",
                   (filtre or {}).get("saat"))


def _hafta(hub, bid, aralik, filtre):
    w, a = _kosul(bid, aralik, filtre, haric=("gun", "saat"))
    rows = hub.query(f"SELECT {ZAMAN_IFADE['gun']} g, {ZAMAN_IFADE['saat']} h, count(*) FROM events WHERE {w} GROUP BY g, h", a)
    m = [[0] * 24 for _ in range(7)]
    for g, h, c in rows:
        m[g][h] = c
    f = filtre or {}
    return _grafik("hafta", "Hafta × saat yoğunluğu", GUNLER, m, ["gun", "saat"],
                   {"gun": f.get("gun"), "saat": f.get("saat")} if ("gun" in f or "saat" in f) else None)


def _gunluk_dagilim(hub, bid, aralik, filtre):
    d = dict(_say(hub, bid, aralik, filtre, ZAMAN_IFADE["gun"], haric=("gun", "saat")))
    return _grafik("cubuk", "Haftanın günleri", GUNLER, [d.get(i, 0) for i in range(7)], "gun", (filtre or {}).get("gun"), sirali=True)


def _dim_say(hub, bid, aralik, filtre, dim, limit):
    _, ifade, kind = BOLGELER[bid][3][dim]
    return _say(hub, bid, aralik, filtre, ifade, haric=(dim,), limit=limit, kind=kind)


def harita(hub, *, ac_hassas=frozenset(), now=None, aralik=None) -> dict:
    pr = PersonaReader(hub)
    beyan = [{"kategori": f.category, "durum": f.status, "kaynak": None, "veri": f.statement} for f in pr.list_facts()]
    bolgeler, toplam, ilk, son = [], 0, None, None
    for bid, (ad, kat, hassas, _dims, _p) in BOLGELER.items():
        n, i, s = _toplam(hub, bid, aralik, None)
        kilitli = hassas and bid not in ac_hassas
        bolgeler.append({"id": bid, "ad": ad, "kategoriler": kat, "olay_sayisi": n, "kilitli": kilitli, "ilk": i, "son": s,
                         "ozet": f"{n} kayıt." if n else ""})
        if not hassas:
            toplam += n
            ilk = min([x for x in (ilk, i) if x], default=None)
            son = max([x for x in (son, s) if x], default=None)
    ad = next((f.statement for f in pr.list_facts(["kimlik"]) if f.fact_key == "ad"), hub.root.name)
    return {"profil": {"ad": ad, "olay": toplam, "ilk": ilk, "son": son}, "bolgeler": bolgeler, "beyan": beyan}


def bolge(hub, bolge_id, *, ac_hassas=frozenset(), aralik=None, filtre=None) -> dict:
    if bolge_id not in BOLGELER:
        raise ValueError("Bilinmeyen bölge.")
    ad, _kat, hassas, dims, birincil = BOLGELER[bolge_id]
    if hassas and bolge_id not in ac_hassas:
        return {"id": bolge_id, "ad": ad, "kilitli": True, "grafikler": [], "en_cok": [], "notlar": []}
    filtre = {k: v for k, v in (filtre or {}).items() if v not in (None, "")}
    n, ilk, son = _toplam(hub, bolge_id, aralik, filtre)
    n0, ilk0, son0 = _toplam(hub, bolge_id, None, None)
    if n0 == 0:
        return {"id": bolge_id, "ad": ad, "kilitli": False, "grafikler": [], "en_cok": [], "gruplar": [], "kpi": [],
                "notlar": ["Henüz veri yok."], "toplam": 0}
    g, gruplar = [], []
    z = _zaman(hub, bolge_id, aralik, filtre)
    if z:
        g.append(z)
    g.append(_saat(hub, bolge_id, aralik, filtre))
    g.append(_hafta(hub, bolge_id, aralik, filtre))
    g.append(_gunluk_dagilim(hub, bolge_id, aralik, filtre))
    kpi = [{"ad": "Kayıt", "deger": n}]
    if ilk:
        gun_sayisi = max(1, (int(son[:4]) - int(ilk[:4])) * 365 + (int(son[5:7]) - int(ilk[5:7])) * 30 + (int(son[8:10]) - int(ilk[8:10])) + 1)
        kpi.append({"ad": "Günlük ortalama", "deger": round(n / gun_sayisi, 1)})
        kpi.append({"ad": "İlk kayıt", "deger": ilk[:10], "metin": True})
        kpi.append({"ad": "Son kayıt", "deger": son[:10], "metin": True})
    if not hassas:
        for dim, (etiket, _i, _k) in dims.items():
            rows = _dim_say(hub, bolge_id, aralik, filtre, dim, 14)
            if not rows:
                continue
            ogeler = [{"ad": str(k), "sayi": c} for k, c in rows]
            gruplar.append({"id": dim, "ad": etiket, "eylem": "ara" if dim == "terim" else "ac", "ogeler": ogeler})
            sec = filtre.get(dim)
            if dim == "terim":
                g.append(_grafik("agac", "Aranan terimler", [o["ad"] for o in ogeler], [o["sayi"] for o in ogeler], dim, sec))
            elif len(rows) <= 6 and dim in ("tur", "platform", "kategori"):
                g.append(_grafik("pasta", etiket, [o["ad"] for o in ogeler], [o["sayi"] for o in ogeler], dim, sec))
            else:
                g.append(_grafik("cubuk", f"En çok: {etiket.lower()}", [o["ad"] for o in ogeler[:10]], [o["sayi"] for o in ogeler[:10]], dim, sec))
            tekil = hub.query_one(f"SELECT count(DISTINCT {_i}) FROM events WHERE {_kosul(bolge_id, aralik, filtre, haric=(dim,))[0]}",
                                  _kosul(bolge_id, aralik, filtre, haric=(dim,))[1])[0]
            kpi.append({"ad": f"Tekil {etiket.lower()}", "deger": tekil})
    else:
        for dim, (etiket, _i, _k) in dims.items():
            rows = _dim_say(hub, bolge_id, aralik, filtre, dim, 8)
            if rows:   # yalnız sayı ve dağılım (yer adı/platform), içerik yok
                g.append(_grafik("pasta", etiket, [str(k) for k, _ in rows], [c for _, c in rows], dim, filtre.get(dim)))
    en_cok = gruplar[0]["ogeler"] if gruplar else []
    notlar = ["Veriden sayım: yorum ya da çıkarım içermez."]
    if hassas:
        notlar.append("Yalnız sayı ve zaman dağılımı; içerik gösterilmez.")
    return {"id": bolge_id, "ad": ad, "kilitli": False, "grafikler": g, "en_cok": en_cok, "gruplar": gruplar, "kpi": kpi,
            "notlar": notlar, "toplam": n, "filtre": filtre, "birincil": birincil}


def _baslik(kind, payload, text):
    p = payload or {}
    for a in ("video", "terim", "parca", "uygulama", "depo", "dosya", "baslik"):
        if p.get(a):
            if a == "parca":
                return f"{p['parca']} · {p.get('sanatci', '')}"
            if a == "video":
                return f"{p['video']} · {p.get('kanal', '')}"
            return str(p[a])
    return text[:80] if text else kind


def kayitlar(hub, bolge_id, *, ac_hassas=frozenset(), filtre=None, aralik=None, limit=20, offset=0) -> dict:
    ad, _k, hassas, _d, _p = BOLGELER[bolge_id]
    if hassas and bolge_id not in ac_hassas:
        return {"kilitli": True, "toplam": 0, "kayitlar": []}
    filtre = {k: v for k, v in (filtre or {}).items() if v not in (None, "")}
    w, a = _kosul(bolge_id, aralik, filtre)
    toplam = hub.query_one(f"SELECT count(*) FROM events WHERE {w}", a)[0]
    rows = hub.query(f"SELECT event_id, ts, kind, category, payload, text FROM events WHERE {w} "
                     "ORDER BY ts DESC, seq DESC LIMIT ? OFFSET ?", [*a, int(limit), int(offset)])
    out = [{"id": r[0], "ts": r[1], "tur": r[2], "kategori": r[3], "baslik": _baslik(r[2], json.loads(r[4] or "{}"), r[5]),
            "alt": r[2]} for r in rows]
    return {"kilitli": False, "toplam": toplam, "kayitlar": out}


def _duz(p, onek=""):
    for k, v in (p or {}).items():
        if isinstance(v, dict):
            yield from _duz(v, f"{onek}{k}.")
        else:
            yield f"{onek}{k}", v


def ayrinti(hub, event_id) -> dict:
    e = hub.get_event(event_id)
    kaynak = next((s for s in hub.sources() if s.source_id == e.source_id), None)
    dosyalar = [r.name for r in hub.raw_files(e.source_id)]
    return {"id": e.event_id, "ts": e.ts, "ham_ts": e.ts, "kategori": e.category, "tur": e.kind, "metin": e.text,
            "kaynak": {"id": e.source_id, "ad": kaynak.kind if kaynak else None, "surum": kaynak.version if kaynak else None,
                       "alindi": kaynak.imported_at if kaynak else None},
            "kaynak_dosya": dosyalar,
            "alanlar": [{"ad": k, "deger": v} for k, v in _duz(e.payload)]}


def kur():
    """Köprüye sahte sağlayıcıyı bağlar; eski değeri döner (testte geri konur)."""
    from kimlikwin import harita_kopru
    eski = harita_kopru.saglayici
    harita_kopru.saglayici = harita_kopru.Saglayici(harita=harita, bolge=bolge, kayitlar=kayitlar, ayrinti=ayrinti)
    return eski
