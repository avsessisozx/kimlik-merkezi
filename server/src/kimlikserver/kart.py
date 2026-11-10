"""Zengin kimlik kartı (INTERFACES Ek 1.6): beyanlar + izinli verilerden özet + bilinmeyenler.

Bölümler (öncelik sırasıyla; boyut sınırı aşılırsa SONDAKİ özet blokları çıkarılır ve kartta
hangilerinin çıkarıldığı yazılır):
  1. Başlık, etiket açıklaması, saat dilimi                       (her zaman)
  2. Bu kişi hakkında bilinenler: beyan_edilen + dosyadan_alinan  (her zaman; en çok MAX_BEYAN satır)
  3. Süresi doldu - doğrulanmadı: eskiyen beyanlar AYRI bölümde  (her zaman; en çok MAX_ESKI satır)
  4. Bilinmeyenler / veride bulunamayanlar                         (her zaman, kısa)
  5. Veriden özet (izinli, hassas olmayan kategoriler): sırayla kod, aktif saatler, aramalar,
     video, müzik, sosyal, dosya/uygulama, son dönem ilgi alanları, veri kapsamı
Etiketler: [beyan] kullanıcının kendi sözü; [dosyadan] bir kaynağa bağlı; [çıkarım] veriden sayımla
çıkarılmış özet (kesin olgu değil). `cikarilan` (onaysız öneri) ve çelişkiyle yerini yenisine
bırakmış bilgi kartta HİÇ yer almaz.

Gizlilik: özet yalnız çağıranın `veri_kategorileri` listesindeki ve hassas OLMAYAN kategorilerden
üretilir; eposta/mesaj/konum/sohbet için izin verilmiş olsa bile kartta içerik/özet bulunmaz
(o veriye araçlarla erişilir). İzin verilmeyen kategoriler kartta adlandırılmaz.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Iterable

from kimlikcore import Category
from kimlikcore.turkish import fold

from .toplulastir import Toplulastirici
from .yerelsaat import UTC, YerelSaat

if TYPE_CHECKING:  # döngüsel içe aktarma olmasın
    from .persona import Fact, PersonaReader

KART_UST_SINIR = 7000          # karakter; ~2000 jeton. Aşılırsa düşük öncelikli özetler çıkarılır.
MAX_BEYAN = 40
MAX_ESKI = 12
MAX_CUMLE = 300
SON_DONEM_GUN = 90
ENAZ_SAAT_KAYDI = 30

OZET_KATEGORILERI = ("kod", "tarama", "video", "muzik", "sosyal", "notlar", "dosyalar",
                     "medya_meta", "uygulama")

_DURAK = frozenset("""
ve ile icin bir bu su o mi mu mı nasil nedir ne nerede nereye en da de ki ya ama veya gibi daha cok az
the a an of to in for and or how what is are on at by with from vs com www http https html php
yeni hakkinda olarak gore kadar sonra once mi mu
""".split())
_KELIME = re.compile(r"[^\W_]+")
# (konu, kartta kanıt desenleri; katlanmış metinde). Beyanlarda geçmeyen konular "bilinmeyen" yazılır.
_BILINMEYEN_KONULAR = (
    ("yaş / doğum yılı", r"dogum yil|yasinda|\byas\b|dogum tarih"),
    ("doğum yeri / memleket", r"dogum yeri|memleket|dogdu|dogma"),
    ("aile / partner / çocuk", r"\besi\b|evli|sevgili|cocuk|kardes|\banne|\bbaba\b|partner"),
    ("evcil hayvan", r"kedi|kopek|evcil|kus\b|balik"),
    ("sağlık / diyet", r"saglik|hastalik|alerji|diyet|vejetaryen|vegan"),
    ("gelir / finans", r"maas|gelir|borc|banka|kredi"),
    ("tuttuğu takım / siyasi ya da dini görüş", r"taraftar|takim|parti|mezhep|dini"),
)


def _satir(s: str) -> str:
    s = re.sub(r"\s*[\r\n]+\s*", " ", s).strip()
    return s if len(s) <= MAX_CUMLE else s[:MAX_CUMLE] + "…"


def _tarih(ts: str | None, tz: YerelSaat) -> str:
    if not ts:
        return "?"
    return tz.yerel_dt(ts).strftime("%Y-%m-%d")


def _kelimeler(satirlar: Iterable[tuple[str, int]]) -> list[tuple[str, int]]:
    """Arama sorgularından sözcük sayımı: katlanmış anahtar, en sık görülen özgün yazımla gösterilir."""
    sayac: dict[str, int] = {}
    yazim: dict[str, dict[str, int]] = {}
    for terim, n in satirlar:
        goruldu = set()
        for w in _KELIME.findall(terim):
            k = fold(w)
            if len(k) < 3 or k.isdigit() or k in _DURAK or k in goruldu:
                continue
            goruldu.add(k)
            sayac[k] = sayac.get(k, 0) + n
            d = yazim.setdefault(k, {})
            d[w.lower()] = d.get(w.lower(), 0) + n
    out = [(max(yazim[k], key=yazim[k].get), n) for k, n in sayac.items()]
    return sorted(out, key=lambda x: (-x[1], x[0]))


def _liste(rows: list[tuple[str, int]], n: int) -> str:
    return ", ".join(f"{v} ({c})" for v, c in rows[:n])


def _pencere(saatler: list[int], genislik: int = 3) -> tuple[int, int, int, int] | None:
    """24 saatlik dağılımda (dairesel) en yoğun `genislik` saatlik aralık; baştaki/sondaki boş
    saatler kırpılır: (başlangıç saati, saat sayısı, aralıktaki kayıt, tüm kayıt)."""
    tum = sum(saatler)
    if tum < ENAZ_SAAT_KAYDI:
        return None
    en = max(range(24), key=lambda s: (sum(saatler[(s + i) % 24] for i in range(genislik)), -s))
    bas, son = en, en + genislik - 1
    while son > bas and saatler[bas % 24] == 0:
        bas += 1
    while son > bas and saatler[son % 24] == 0:
        son -= 1
    return bas % 24, son - bas + 1, sum(saatler[(bas + i) % 24] for i in range(son - bas + 1)), tum


# ---------------------------------------------------------------------- bölümler
def _beyanlar(reader: "PersonaReader", cats: list[str]) -> tuple[list[str], int]:
    from .persona import CATEGORY_TITLES, FACT_CATEGORIES, son_dogrulama
    facts = reader.list_facts(cats)
    by_cat: dict[str, list] = {}
    for f in facts:
        by_cat.setdefault(f.category, []).append(f)
    out: list[str] = []
    labels: dict[str | None, str | None] = {}
    sayi = 0
    for cat in FACT_CATEGORIES:
        items = by_cat.get(cat)
        if not items:
            continue
        out += [f"### {CATEGORY_TITLES[cat]}", ""]
        for f in items:
            if sayi >= MAX_BEYAN:
                break
            sayi += 1
            notlar = ["beyan"] if f.status == "beyan_edilen" else ["dosyadan"]
            if f.status == "dosyadan_alinan":
                if f.source_id not in labels:
                    labels[f.source_id] = reader.source_label(f.source_id)
                notlar.append(f"kaynak: {_satir(labels[f.source_id] or 'bilinmeyen')}")
            dogr = son_dogrulama(f)
            if dogr:
                notlar.append(f"son doğrulama: {dogr}")
            out.append(f"- {_satir(f.statement)} ({', '.join(notlar)})")
        out.append("")
    kalan = len(facts) - sayi
    if kalan > 0:
        out += [f"(Boyut sınırı nedeniyle {kalan} beyan daha gösterilmedi.)", ""]
    return out, len(facts)


def _eskiyenler(reader: "PersonaReader", cats: list[str]) -> list["Fact"]:
    from .persona import _COLS, _fact
    if not cats:
        return []
    cols = ", ".join("f." + c.strip() for c in _COLS.split(","))
    sql = (f"SELECT {cols} FROM facts f LEFT JOIN sources s ON s.source_id = f.source_id "
           "WHERE f.hidden = 0 AND f.status IN ('beyan_edilen', 'dosyadan_alinan', 'eskimis') "
           "AND f.valid_until IS NOT NULL AND f.valid_until <= ? "
           "AND (f.source_id IS NULL OR s.removed_at IS NULL) "
           f"AND f.category IN ({','.join('?' * len(cats))}) "
           # aynı anahtarda daha yeni (çıkarılan hariç) bir bilgi varsa bu çoktan yerini bırakmıştır
           "AND NOT EXISTS (SELECT 1 FROM facts g WHERE g.hidden = 0 AND g.status <> 'cikarilan' "
           "AND g.fact_id <> f.fact_id AND g.category = f.category AND f.fact_key IS NOT NULL "
           "AND g.fact_key = f.fact_key AND (g.date > f.date OR (g.date = f.date AND "
           "g.fact_id > f.fact_id))) "
           "ORDER BY f.valid_until DESC, f.fact_id")
    rows = reader.hub.query(sql, [reader._now(), *cats])
    return [_fact(r) for r in rows]


def _eski_bolum(reader: "PersonaReader", cats: list[str]) -> list[str]:
    from .persona import CATEGORY_TITLES, son_dogrulama
    eski = _eskiyenler(reader, cats)
    if not eski:
        return []
    out = ["### Süresi doldu - doğrulanmadı", "",
           "Aşağıdaki bilgilerin geçerlilik süresi bitti; artık doğru olmayabilir. Güncel diye "
           "sunmayın; sorulursa 'daha önce şöyle beyan edilmişti, doğrulanmadı' deyin.", ""]
    for f in eski[:MAX_ESKI]:
        out.append(f"- [{CATEGORY_TITLES[f.category]}] {_satir(f.statement)} "
                   f"(beyan, son doğrulama: {son_dogrulama(f)}, süresi dolma: "
                   f"{(f.valid_until or '')[:10]})")
    if len(eski) > MAX_ESKI:
        out.append(f"(+{len(eski) - MAX_ESKI} süresi dolmuş bilgi daha gösterilmedi.)")
    out.append("")
    return out


def _bilinmeyenler(canli_metin: str, bos_kategoriler: list[str], bos_beyan: list[str],
                   izinli: list[str]) -> list[str]:
    ft = fold(canli_metin)
    yok = [ad for ad, desen in _BILINMEYEN_KONULAR if not re.search(desen, ft)]
    out = ["## Bilinmeyenler / veride bulunamayanlar", ""]
    if yok:
        out.append("- Beyanlarda yer almıyor ve bu kartta özetlenmedi: " + "; ".join(yok) +
                   ". Bu konularda tahmin yürütmeyin.")
    if bos_beyan:
        out.append("- Hiç beyan yok: " + ", ".join(bos_beyan) + ".")
    if bos_kategoriler:
        out.append("- İzinli ama kaydı olmayan veri kategorileri: " + ", ".join(bos_kategoriler) + ".")
    out.append("- Bu kart tüm verinin özeti DEĞİL; yalnız seçilmiş sayımlar ve beyanlardır. Cevap "
               "kartta yoksa uydurmayın: araçlarla (`ara`, `say`) bakın; bulamazsanız 'bilmiyorum' deyin.")
    out.append("- Bu karta yalnız izinli kategorilerden bilgi girmiştir"
               + (f" ({', '.join(izinli)})" if izinli else "")
               + "; izin verilmeyen alanlardaki bilgi bu kartta yoktur ve yokluğu 'böyle bir şey "
               "yok' anlamına gelmez.")
    out.append("")
    return out


def _kapsam(tz: YerelSaat, hub, cats: list[str]) -> tuple[list[str], list[str]]:
    """Veri kapsamı satırları ve izinli-ama-boş kategoriler."""
    if not cats:
        return [], []
    rows = hub.query(
        "SELECT category, COUNT(*), MIN(CASE WHEN COALESCE(json_extract(payload,'$.zaman_kaynagi'),"
        "'') <> 'dosya_tarihi' THEN ts END), MAX(CASE WHEN COALESCE(json_extract(payload,"
        "'$.zaman_kaynagi'),'') <> 'dosya_tarihi' THEN ts END) FROM events WHERE hidden = 0 AND "
        f"category IN ({','.join('?' * len(cats))}) GROUP BY category ORDER BY 2 DESC", cats)
    var = {r[0] for r in rows}
    satir = [f"{k}: {n} kayıt" + (f", {_tarih(a, tz)} - {_tarih(b, tz)}" if a else "")
             for k, n, a, b in rows]
    return satir, [c for c in cats if c not in var]


def _ozetler(tg: Toplulastirici, tz: YerelSaat, cats: list[str], simdi: datetime
             ) -> list[tuple[str, list[str]]]:
    """(blok adı, satırlar) listesi, ÖNCELİK sırasıyla."""
    L = "[çıkarım] "
    bloklar: list[tuple[str, list[str]]] = []

    def var(c):
        return c in cats

    def ekle(ad, satirlar):
        if satirlar:
            bloklar.append((ad, satirlar))

    # --- kod
    if var("kod"):
        s = []
        diller = tg.ham_top("dil", ["kod"], limit=6)
        depolar = tg.ham_top("depo", ["kod"], limit=6)
        if diller:
            s.append(f"- {L}Kod dilleri (depo sayısına göre): {_liste(diller, 5)}")
        if depolar:
            s.append(f"- {L}Depolar (etkinlik sayısına göre): {_liste(depolar, 5)}")
        ekle("kod", s)
    # --- aktif saatler (yerel)
    s = []
    for ad, kl in (("Kod etkinliği", ["kod"]), ("Genel etkinlik", cats)):
        kl = [c for c in kl if c in cats]
        if not kl:
            continue
        r = tg.say("saat", kategoriler=kl)["satirlar"]
        p = _pencere([x["sayi"] for x in r])
        if p:
            bas, genis, n, tum = p
            s.append(f"- {L}{ad} en çok {bas:02d}:00-{(bas + genis - 1) % 24:02d}:59 arasında "
                     f"(yerel saat, {tz.ad} {tz.bilgi(simdi)['utc_farki']}; {n}/{tum} kayıt)")
    ekle("saatler", s)
    # --- aramalar
    if var("tarama") or var("video"):
        s = []
        kl = [c for c in ("tarama", "video") if var(c)]
        terimler = tg.ham_top("terim", kl, limit=3000)
        kel = _kelimeler(terimler)
        if kel:
            s.append(f"- {L}Aramalarda en çok geçen sözcükler: {_liste(kel, 10)}")
        tekrar = [(t, n) for t, n in terimler if n >= 2][:5]
        if tekrar:
            s.append(f"- {L}Tekrar eden aramalar: {_liste(tekrar, 5)}")
        if var("tarama"):
            siteler = tg.ham_top("site", ["tarama"], limit=6)
            if siteler:
                s.append(f"- {L}En çok gidilen siteler: {_liste(siteler, 5)}")
        ekle("aramalar", s)
    # --- video
    if var("video"):
        s = []
        kanal = tg.ham_top("kanal", ["video"], limit=6)
        if kanal:
            s.append(f"- {L}En çok izlenen kanallar (izleme sayısı): {_liste(kanal, 5)}")
        abone = tg.hub.query("SELECT COUNT(*) FROM events WHERE hidden = 0 AND "
                             "kind = 'youtube.abonelik'")[0][0]
        if abone:
            s.append(f"- {L}Abone olunan kanal sayısı: {abone}")
        ekle("video", s)
    # --- müzik
    if var("muzik"):
        s = []
        sanatci = tg.ham_top("sanatci", ["muzik"], limit=6)
        if sanatci:
            s.append(f"- {L}En çok dinlenen sanatçılar (dinleme sayısı): {_liste(sanatci, 5)}")
        pod = tg.ham_top("podcast", ["muzik"], limit=4)
        if pod:
            s.append(f"- {L}En çok dinlenen podcast programları: {_liste(pod, 3)}")
        ekle("muzik", s)
    # --- sosyal
    if var("sosyal"):
        sub = tg.ham_top("subreddit", ["sosyal"], limit=6)
        ekle("sosyal", [f"- {L}En çok yazılan subredditler: {_liste(sub, 5)}"] if sub else [])
    # --- dosya / uygulama
    s = []
    if var("dosyalar"):
        uz = tg.ham_top("uzanti", ["dosyalar"], limit=5)
        if uz:
            s.append(f"- {L}En çok dosya uzantıları: {_liste(uz, 5)}")
    if var("uygulama"):
        ap = tg.ham_top("uygulama", ["uygulama"], limit=5)
        if ap:
            s.append(f"- {L}En çok kullanılan uygulamalar: {_liste(ap, 5)}")
    ekle("dosya_uygulama", s)
    # --- son dönem ilgi alanları
    since = (simdi - timedelta(days=SON_DONEM_GUN)).astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    s = []
    n_son = tg.hub.query(
        "SELECT COUNT(*) FROM events WHERE hidden = 0 AND ts >= ? AND category IN "
        f"({','.join('?' * len(cats))}) AND COALESCE(json_extract(payload,'$.zaman_kaynagi'),'') "
        "<> 'dosya_tarihi'", [since, *cats])[0][0] if cats else 0
    if n_son >= 5:
        sk = [c for c in ("tarama", "video") if var(c)]
        kel = _kelimeler(tg.ham_top("terim", sk, since=since, limit=2000)) if sk else []
        if kel:
            s.append(f"- {L}Aramalarda öne çıkan sözcükler: {_liste(kel, 8)}")
        for alan, kl, baslik in (("kanal", ["video"], "İzlenen kanallar"),
                                 ("subreddit", ["sosyal"], "Subredditler"),
                                 ("sanatci", ["muzik"], "Dinlenen sanatçılar"),
                                 ("depo", ["kod"], "Kod depoları")):
            kl = [c for c in kl if var(c)]
            r = tg.ham_top(alan, kl, since=since, limit=4) if kl else []
            if r:
                s.append(f"- {L}{baslik}: {_liste(r, 3)}")
        if s:
            s = [f"- Son {SON_DONEM_GUN} gün ({n_son} kayıt) içinde:"] + ["  " + x for x in s]
    elif cats:
        s.append(f"- Son {SON_DONEM_GUN} günde yalnız {n_son} kayıt var; son dönem özeti çıkarılmadı.")
    ekle("son_donem", s)
    return bloklar


# ---------------------------------------------------------------------- ana işlev
def uret(reader: "PersonaReader", categories: Iterable[str] | None = None, *,
         veri_kategorileri: Iterable[str] | None = None, saat_dilimi: YerelSaat | None = None,
         ust_sinir: int = KART_UST_SINIR) -> str:
    from .persona import FACT_CATEGORIES
    tz = saat_dilimi or UTC
    cats = list(FACT_CATEGORIES) if categories is None else list(categories)
    simdi = reader._clock()
    if simdi.tzinfo is None:
        simdi = simdi.replace(tzinfo=timezone.utc)
    ozet_kat = [c for c in OZET_KATEGORILERI
                if veri_kategorileri is not None and c in set(veri_kategorileri)
                and c not in Category.SENSITIVE]

    beyan_satir, n_beyan = _beyanlar(reader, cats)
    eski = _eski_bolum(reader, cats)
    farkli = reader.list_facts(cats)
    from .persona import CATEGORY_TITLES
    dolu = {f.category for f in farkli} | {f.category for f in _eskiyenler(reader, cats)}
    bos_beyan = [CATEGORY_TITLES[k] for k in cats if k not in dolu and k != "diger"]
    kapsam, bos_kat = ([], [])
    tg = None
    hub = reader.hub
    if ozet_kat:
        tg = Toplulastirici(hub, tz)
        kapsam, bos_kat = _kapsam(tz, hub, ozet_kat)
    now_s = reader._now()
    ust = ["# Kimlik Kartı", "",
           f"Oluşturulma: {now_s} (UTC); yerel: {tz.yerel(now_s)} ({tz.ad}). Kart içindeki "
           f"tarih/saatler, aksi yazılmadıkça {tz.ad} saat dilimindedir.",
           "Etiketler: [beyan] kullanıcının kendi sözü; [dosyadan] bir kaynağa bağlı bilgi; "
           "[çıkarım] veriden sayımla çıkarılan özet - kesin olgu değil, yanılabilir.", "",
           "## Bu kişi hakkında bilinenler", "",
           "Kişinin kendi beyanı ya da bir kaynağa bağlı bilgiler; tahmin içermez.", ""]
    govde = list(beyan_satir)
    if not beyan_satir:
        govde += ["Seçilen kategorilerde bilgi yok.", ""]
    govde += eski
    canli_metin = " ".join(f.statement for f in farkli)
    sabit_son = _bilinmeyenler(canli_metin, bos_kat, bos_beyan, ozet_kat)
    parcalar_ust = "\n".join(ust + govde)
    parcalar_son = "\n".join(sabit_son)
    butce = ust_sinir - len(parcalar_ust) - len(parcalar_son) - 200
    ozet_satir: list[str] = []
    atlanan: list[str] = []
    if tg is not None:
        basl = ["## Veriden özet (izinli kategoriler; çıkarım düzeyi: yalnız sayım)", ""]
        if kapsam:
            basl.append("- Veri kapsamı: " + "; ".join(kapsam))
        kullanilan = len("\n".join(basl)) + 2
        govde_ozet: list[str] = []
        for ad, satirlar in _ozetler(tg, tz, ozet_kat, simdi):
            metin = "\n".join(satirlar)
            if kullanilan + len(metin) + 1 <= butce:
                govde_ozet += satirlar
                kullanilan += len(metin) + 1
            else:
                atlanan.append(ad)
        ozet_satir = basl + govde_ozet
        if atlanan:
            ozet_satir.append(f"(Boyut sınırı nedeniyle çıkarılan özetler: {', '.join(atlanan)}.)")
        ozet_satir.append("")
    return "\n".join(ust + govde + ozet_satir + sabit_son).rstrip() + "\n"
