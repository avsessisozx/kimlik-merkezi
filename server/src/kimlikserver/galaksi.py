"""Galaksi görünümü (v0.3.0): verinin sahibinin kendi arayüzü için "yıldız haritası".

Her kayıt bir yıldızdır; kaynak ailesine (Meta, ChatGPT, Telefon, Bilgisayar, ...) göre kümelenir.
- YALNIZ veriden sayım ve zaman; yorum/çıkarım yok.
- `sahip=True`: hassas kategoriler dahil (yerel arayüz). `sahip=False`: hassas kategoriler dışarıda
  (yapay zekâ yolu bu modülü kullanmaz; testler kısıtlı kipi sınar).
- `hidden=1` kayıtlar hiçbir yerde görünmez. Tarihi dosya tarihinden gelen kayıtlar zamana girmez.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from kimlikcore import Hub

HASSAS_KATEGORILER = ("mesaj", "eposta", "konum", "sohbet")
SINIR_YILDIZ = 30000          # çizilecek en çok yıldız; fazlası düzgün aralıkla seyreltilir (sayımlar tam kalır)
_GERCEK_ZAMAN = "COALESCE(json_extract(payload, '$.zaman_kaynagi'), '') <> 'dosya_tarihi'"

# Kaynak ailesi kodu: sohbet kayıtları platforma göre (sohbet:chatgpt), diğerleri tür önekine göre.
GRUP_SQL = ("CASE WHEN kind LIKE 'sohbet.%' THEN 'sohbet:' || lower(COALESCE(json_extract(payload, '$.platform'), 'bilinmeyen')) "
            "ELSE substr(kind, 1, instr(kind || '.', '.') - 1) END")

GRUP_AD = {
    "meta": "Meta", "instagram": "Meta", "facebook": "Meta",
    "sohbet:chatgpt": "ChatGPT", "sohbet:claude": "Claude", "sohbet:gemini": "Gemini",
    "sohbet:deepseek": "DeepSeek", "sohbet:bilinmeyen": "Yapay zekâ sohbetleri",
    "android": "Telefon", "dosya": "Bilgisayar", "pc": "Bilgisayar", "bilgisayar": "Bilgisayar",
    "google": "Google", "youtube": "YouTube", "chrome": "Chrome", "firefox": "Firefox", "edge": "Edge",
    "spotify": "Spotify", "reddit": "Reddit", "github": "GitHub", "gmail": "E-posta",
}
# Aynı adı paylaşan aileler tek yıldız kümesi olur (Meta = instagram + facebook + meta).
KUME_ADI_SIRA = ("Meta", "ChatGPT", "Claude", "Gemini", "DeepSeek", "Telefon", "Bilgisayar")


def grup_adi(kod: str) -> str:
    if kod in GRUP_AD:
        return GRUP_AD[kod]
    if kod.startswith("sohbet:"):
        return kod.split(":", 1)[1].capitalize()
    return kod.capitalize() or "Diğer"


def _kategori_kosulu(sahip: bool) -> tuple[str, list[Any]]:
    if sahip:
        return "1", []
    return "category NOT IN (%s)" % ",".join("?" * len(HASSAS_KATEGORILER)), list(HASSAS_KATEGORILER)


def _kume_kodlari(ad: str, kodlar: Iterable[str]) -> list[str]:
    return [k for k in kodlar if grup_adi(k) == ad]


def galaksi(hub: Hub, *, sahip: bool = False, sinir: int = SINIR_YILDIZ) -> dict[str, Any]:
    kos, args = _kategori_kosulu(sahip)
    temel = f"FROM events NOT INDEXED WHERE hidden = 0 AND {kos}"
    sayim = hub.query(f"SELECT {GRUP_SQL}, COUNT(*), "
                      f"MIN(CASE WHEN {_GERCEK_ZAMAN} THEN ts END), MAX(CASE WHEN {_GERCEK_ZAMAN} THEN ts END) "
                      f"{temel} GROUP BY 1", args)
    kumeler: dict[str, dict[str, Any]] = {}
    for kod, n, ilk, son in sayim:
        ad = grup_adi(kod)
        k = kumeler.setdefault(ad, {"id": ad, "ad": ad, "kodlar": [], "sayi": 0, "ilk": None, "son": None})
        k["kodlar"].append(kod)
        k["sayi"] += n
        if ilk and (k["ilk"] is None or ilk < k["ilk"]):
            k["ilk"] = ilk
        if son and (k["son"] is None or son > k["son"]):
            k["son"] = son
    sirali = sorted(kumeler.values(), key=lambda k: (-k["sayi"], k["ad"]))
    idx = {k["ad"]: i for i, k in enumerate(sirali)}
    toplam = sum(k["sayi"] for k in sirali)
    adim = max(1, -(-toplam // max(1, int(sinir))))      # tavan bölme: yıldız sayısı sinir'i geçmesin
    # Yıldızlar: (zaman, küme, tür). Dosya tarihli (gerçek zamanı olmayan) kayıtlar çizilmez, sayıma girer.
    satirlar = hub.query(f"SELECT CAST(strftime('%s', ts) AS INTEGER), {GRUP_SQL}, kind {temel} AND {_GERCEK_ZAMAN} "
                         f"AND (seq % ?) = 0 ORDER BY ts", [*args, adim])
    turler: list[str] = []
    tur_idx: dict[str, int] = {}
    t, g, k = [], [], []
    for epoch, kod, kind in satirlar:
        if epoch is None:
            continue
        if kind not in tur_idx:
            tur_idx[kind] = len(turler)
            turler.append(kind)
        t.append(epoch)
        g.append(idx[grup_adi(kod)])
        k.append(tur_idx[kind])
    yillar: dict[str, dict[str, int]] = {}
    for yil, kod, n in hub.query(f"SELECT strftime('%Y', ts), {GRUP_SQL}, COUNT(*) {temel} AND {_GERCEK_ZAMAN} "
                                 f"GROUP BY 1, 2", args):
        if yil:
            d = yillar.setdefault(yil, {})
            ad = grup_adi(kod)
            d[ad] = d.get(ad, 0) + n
    return {
        "toplam": toplam,
        "gruplar": [{"id": k["id"], "ad": k["ad"], "sayi": k["sayi"], "ilk": k["ilk"], "son": k["son"]} for k in sirali],
        "yildizlar": {"t": t, "g": g, "k": k},
        "turler": turler,
        "yillar": yillar,
        "seyreltme": adim,
        "tarihsiz": sum(kumeler[a]["sayi"] for a in kumeler) - sum(sum(d.values()) for d in yillar.values()),
        "not": "Veriden sayım; yorum ya da çıkarım içermez.",
    }


def _grup_kodlari(hub: Hub, ad: str, kos: str, args: list[Any]) -> list[str]:
    kodlar = [r[0] for r in hub.query(f"SELECT DISTINCT {GRUP_SQL} FROM events NOT INDEXED WHERE hidden = 0 AND {kos}", args)]
    return _kume_kodlari(ad, kodlar)


def kayitlar(hub: Hub, grup: str, *, bas: int | None = None, bit: int | None = None, sahip: bool = False,
             limit: int = 50, offset: int = 0, arama: str | None = None, tur: str | None = None) -> dict[str, Any]:
    """Bir kaynak kümesindeki kayıtlar (yeniden eskiye). `bas`/`bit`: epoch saniye (bit hariç)."""
    kos, args = _kategori_kosulu(sahip)
    kodlar = _grup_kodlari(hub, grup, kos, args)
    if not kodlar:
        return {"grup": grup, "toplam": 0, "kayitlar": []}
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    where = f"hidden = 0 AND {kos} AND ({GRUP_SQL}) IN ({','.join('?' * len(kodlar))})"
    a: list[Any] = [*args, *kodlar]
    if bas is not None:
        where += " AND ts >= strftime('%Y-%m-%dT%H:%M:%SZ', ?, 'unixepoch')"
        a.append(int(bas))
    if bit is not None:
        where += " AND ts < strftime('%Y-%m-%dT%H:%M:%SZ', ?, 'unixepoch')"
        a.append(int(bit))
    if tur:
        where += " AND kind = ?"
        a.append(str(tur))
    if arama:
        where += " AND text LIKE ? ESCAPE '\\'"
        a.append("%" + arama.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    toplam = hub.query(f"SELECT COUNT(*) FROM events NOT INDEXED WHERE {where}", a)[0][0]
    rows = hub.query(
        "SELECT event_id, ts, kind, category, COALESCE(json_extract(payload, '$.baslik'), substr(text, 1, 120)), "
        f"substr(text, 1, 240) FROM events NOT INDEXED WHERE {where} ORDER BY ts DESC, seq DESC LIMIT ? OFFSET ?",
        [*a, limit, offset])
    return {"grup": grup, "toplam": toplam, "limit": limit, "offset": offset,
            "kayitlar": [{"event_id": r[0], "ts": r[1], "kind": r[2], "kategori": r[3], "baslik": r[4], "ozet": r[5]}
                         for r in rows]}


GUN_AD = ["Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"]   # strftime('%w'): 0 = Pazar


def ozet(hub: Hub, *, sahip: bool = False, kayma: int = 0) -> dict[str, Any]:
    """"Sen kimsin" sayfasının VERİDEN çıkan gerçekleri. Yorum yok: her madde bir sayım ya da tarih.
    `kayma`: UTC'ye eklenecek tam saat (Türkiye +3) — saat ve gün dağılımı yerel saate göre."""
    kos, args = _kategori_kosulu(sahip)
    temel = f"FROM events NOT INDEXED WHERE hidden = 0 AND {kos} AND {_GERCEK_ZAMAN}"
    toplam, ilk, son = hub.query(f"SELECT COUNT(*), MIN(ts), MAX(ts) {temel}", args)[0]
    if not toplam:
        return {"toplam": 0, "maddeler": [], "kaynaklar": [], "not": "Henüz veri yok."}
    kd = f"{int(kayma):+d} hours"
    yillar = hub.query(f"SELECT strftime('%Y', ts, ?), COUNT(*) {temel} GROUP BY 1 ORDER BY 2 DESC, 1", [kd, *args])
    saatler = hub.query(f"SELECT CAST(strftime('%H', ts, ?) AS INTEGER), COUNT(*) {temel} GROUP BY 1 ORDER BY 2 DESC, 1", [kd, *args])
    gunler = hub.query(f"SELECT CAST(strftime('%w', ts, ?) AS INTEGER), COUNT(*) {temel} GROUP BY 1 ORDER BY 2 DESC, 1", [kd, *args])
    kay = hub.query(f"SELECT {GRUP_SQL}, COUNT(*) {temel} GROUP BY 1", args)
    kume: dict[str, int] = {}
    for kod, n in kay:
        kume[grup_adi(kod)] = kume.get(grup_adi(kod), 0) + n
    kaynaklar = [{"ad": a, "sayi": n} for a, n in sorted(kume.items(), key=lambda x: (-x[1], x[0]))]
    gece = sum(n for h, n in saatler if h >= 23 or h < 5)
    maddeler = [
        {"id": "toplam", "metin": f"{toplam:,} kayıt".replace(",", "."), "kanit": "kayıt sayısı"},
        {"id": "aralik", "metin": f"En eski kayıt {ilk[:10]}, en yeni {son[:10]}.", "kanit": "ilk ve son tarih"},
        {"id": "yil", "metin": f"En çok kayıt {yillar[0][0]} yılında ({yillar[0][1]:,}).".replace(",", "."), "kanit": "yıllara göre sayım"},
        {"id": "saat", "metin": f"En yoğun saat {saatler[0][0]:02d}:00–{saatler[0][0]:02d}:59 (Türkiye saati).", "kanit": "saatlere göre sayım"},
        {"id": "gun", "metin": f"En yoğun gün {GUN_AD[gunler[0][0]]}.", "kanit": "haftanın gününe göre sayım"},
        {"id": "gece", "metin": f"Kayıtların %{round(100 * gece / toplam)}'i 23:00–05:00 arasında.", "kanit": "saatlere göre sayım"},
        {"id": "kaynak", "metin": f"En çok kaydı olan kaynak {kaynaklar[0]['ad']} ({kaynaklar[0]['sayi']:,}).".replace(",", "."), "kanit": "kaynağa göre sayım"},
    ]
    return {"toplam": toplam, "ilk": ilk, "son": son, "maddeler": maddeler, "kaynaklar": kaynaklar,
            "not": "Her madde veriden bir sayımdır; yorum ya da çıkarım içermez."}
