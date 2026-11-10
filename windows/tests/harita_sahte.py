"""§12 JSON biçimine uyan SAHTE sağlayıcı: yalnız testlerde ve ekran görüntüsü demosunda kullanılır.
Üretim kodu bunu içe aktarmaz; gerçek işlevler `kimlikserver.harita` içindedir.

Veri yoksa (hub'da olay yok) bütün bölgeler boş döner. Aksi hâlde klasör adından türetilen tohumla
kişiye özgü, tekrarlanabilir sayılar üretilir (başka kişi = başka persona)."""
from __future__ import annotations

import random
from datetime import date

from kimlikserver.persona import PersonaReader

BOLGELER = [
    ("bas", "Baş: ilgi ve merak", ["tarama"], False),
    ("goz", "Gözler: izledikleri", ["video"], False),
    ("kulak", "Kulaklar: dinledikleri", ["muzik"], False),
    ("agiz", "Ağız: yazdıkları/söyledikleri", ["sosyal"], False),
    ("el", "Eller: üretim ve iş", ["kod", "dosyalar", "notlar"], False),
    ("kalp", "Kalp: kişisel (hassas)", ["mesaj"], True),
    ("karin", "Karın: e-posta (hassas)", ["eposta"], True),
    ("ayak", "Ayaklar: konum (hassas)", ["konum", "medya_meta"], True),
    ("ic", "Merkez: uygulama kullanımı", ["uygulama"], False),
]
AYLAR = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13)][:23]
GUNLER = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
KANALLAR = ["Kod Mutfağı", "Gezgin Mehmet", "Bilim Atölyesi", "Pratik Yemek", "Tarih Sohbetleri", "Mini Belgesel",
            "Gece Müziği", "Oyun Günlüğü"]
TERIMLER = ["hava durumu", "python sqlite", "tatil otelleri", "kahve makinesi", "uçak bileti", "film önerileri",
            "ev kirası", "mac sonucu"]
SITELER = ["wikipedia.org", "github.com", "stackoverflow.com", "ekşisözlük", "haber siteleri", "youtube.com"]
SANATCI = ["Sezen Aksu", "Daft Punk", "Tarkan", "Mor ve Ötesi", "Radiohead", "Duman", "Norah Jones"]
SUBREDDIT = ["r/Turkey", "r/python", "r/AskReddit", "r/istanbul", "r/selfhosted", "r/Sqlite"]
UYGULAMALAR = ["Tarayıcı", "Kod düzenleyici", "Mesajlaşma", "Müzik", "Harita", "Fotoğraflar", "Notlar"]
DOSYA_TURLERI = ["pdf", "jpg", "docx", "py", "xlsx", "zip"]


def _olay_sayisi(hub) -> int:
    return int(hub.summary()["counts"]["event"])


def _rng(hub, anahtar: str) -> random.Random:
    return random.Random(f"{hub.root.parent.name}/{hub.root.name}/{anahtar}")


def _sayilar(rng: random.Random, n: int, buyuk: int) -> list[int]:
    return sorted((rng.randint(buyuk // 8, buyuk) for _ in range(n)), reverse=True)


def _zaman(rng, baslik="Aylık etkinlik", taban=200):
    return {"tur": "zaman", "baslik": baslik, "etiketler": AYLAR,
            "degerler": [int(taban * (0.4 + rng.random() * 1.2) * (1 + i / 30)) for i in range(len(AYLAR))]}


def _saat(rng, baslik="Günün saatleri"):
    egri = [int(40 + 120 * max(0.0, 1 - abs(h - rng.choice([14, 21])) / 7) + rng.randint(0, 25)) for h in range(24)]
    return {"tur": "saat", "baslik": baslik, "etiketler": [f"{h:02d}" for h in range(24)], "degerler": egri}


def _hafta(rng, baslik="Hafta ısı haritası"):
    return {"tur": "hafta", "baslik": baslik, "etiketler": GUNLER,
            "degerler": [[max(0, int(rng.gauss(30, 18) * (1.6 if g >= 5 else 1) * (0.2 if h < 7 else 1)))
                          for h in range(24)] for g in range(7)]}


def _cubuk(rng, baslik, adlar, buyuk=900):
    return {"tur": "cubuk", "baslik": baslik, "etiketler": adlar, "degerler": _sayilar(rng, len(adlar), buyuk)}


def _pasta(rng, baslik, adlar):
    return {"tur": "pasta", "baslik": baslik, "etiketler": adlar, "degerler": [rng.randint(5, 90) for _ in adlar]}


def _en_cok(rng, adlar, buyuk=900, ornek=None):
    return [{"ad": a, "sayi": s, **({"ornek": ornek} if ornek else {})} for a, s in zip(adlar, _sayilar(rng, len(adlar), buyuk))]


def harita(hub, *, ac_hassas=frozenset(), now=None) -> dict:
    n = _olay_sayisi(hub)
    pr = PersonaReader(hub)
    beyan = [{"statement": f.statement, "category": f.category, "status": f.status} for f in pr.list_facts()]
    bolgeler = []
    for i, (bid, ad, kat, hassas) in enumerate(BOLGELER):
        kilitli = hassas and bid not in ac_hassas
        rng = _rng(hub, bid)
        sayi = 0 if n == 0 else rng.randint(40, 6000) // (3 if hassas else 1)
        b = {"id": bid, "ad": ad, "kategoriler": kat, "olay_sayisi": sayi, "kilitli": kilitli,
             "ilk": "2019-03-14T08:00:00Z" if sayi else None, "son": "2026-11-09T21:40:00Z" if sayi else None,
             "ozet": (f"{sayi} kayıt, en çok {kat[0]} kategorisinde." if sayi else "")}
        bolgeler.append(b)
    toplam = sum(b["olay_sayisi"] for b in bolgeler)
    return {"profil": {"ad": hub.root.parent.name, "olay": toplam if n else 0,
                       "ilk": "2019-03-14T08:00:00Z" if n else None, "son": "2026-11-09T21:40:00Z" if n else None},
            "bolgeler": bolgeler, "beyan": beyan}


def bolge(hub, bolge_id, *, ac_hassas=frozenset(), aralik=None) -> dict:
    ad = next((b[1] for b in BOLGELER if b[0] == bolge_id), None)
    if ad is None:
        raise ValueError("Bilinmeyen bölge.")
    hassas = next(b[3] for b in BOLGELER if b[0] == bolge_id)
    if hassas and bolge_id not in ac_hassas:
        return {"id": bolge_id, "ad": ad, "kilitli": True, "grafikler": [], "en_cok": [], "notlar": []}
    if _olay_sayisi(hub) == 0:
        return {"id": bolge_id, "ad": ad, "kilitli": False, "grafikler": [], "en_cok": [], "notlar": ["Henüz veri yok."]}
    r = _rng(hub, "b" + bolge_id)
    g: list[dict] = []
    e: list[dict] = []
    notlar = ["Veriden sayım: yorum ya da çıkarım içermez."]
    if bolge_id == "bas":
        g = [_zaman(r, "Aylık arama ve ziyaret"), _saat(r, "Günün saatleri"), _cubuk(r, "En çok gidilen siteler", SITELER)]
        e = _en_cok(r, TERIMLER, 420)
    elif bolge_id == "goz":
        g = [_zaman(r, "Aylık izleme"), _hafta(r, "Hafta ısı haritası: izleme"), _pasta(r, "Video türü", ["Eğitim", "Müzik", "Belgesel", "Eğlence"])]
        e = _en_cok(r, KANALLAR, 310)
    elif bolge_id == "kulak":
        g = [_zaman(r, "Aylık dinleme"), _cubuk(r, "En çok dinlenen sanatçılar", SANATCI, 700), _saat(r, "Dinleme saatleri")]
        e = _en_cok(r, SANATCI, 500)
    elif bolge_id == "agiz":
        g = [_zaman(r, "Aylık gönderi ve yorum", 60), _pasta(r, "Gönderi / yorum", ["Yorum", "Gönderi", "Beğeni"]), _cubuk(r, "En çok subreddit", SUBREDDIT, 300)]
        e = _en_cok(r, SUBREDDIT, 300)
    elif bolge_id == "el":
        g = [_pasta(r, "Dosya türleri", DOSYA_TURLERI), _zaman(r, "Aylık üretim", 40), _cubuk(r, "Depo etkinliği", ["kimlik-merkezi", "blog", "dotfiles", "araclar"], 200)]
        e = _en_cok(r, DOSYA_TURLERI, 150)
    elif bolge_id in ("kalp", "karin"):
        g = [_zaman(r, "Aylık sayı", 30), _hafta(r, "Hafta ısı haritası")]
        notlar.append("Yalnız sayı ve zaman dağılımı; içerik gösterilmez.")
    elif bolge_id == "ayak":
        g = [_zaman(r, "Aylık yer sayısı", 12), _cubuk(r, "Yer sayıları (ham koordinat yok)", ["İstanbul", "Ankara", "İzmir", "Diğer"], 120)]
        notlar.append("Ham koordinat gösterilmez.")
    else:  # ic
        g = [_cubuk(r, "En çok kullanılan uygulamalar", UYGULAMALAR, 800), _saat(r, "Kullanım saatleri"), _zaman(r, "Aylık kullanım", 150)]
        e = _en_cok(r, UYGULAMALAR, 800)
    return {"id": bolge_id, "ad": ad, "kilitli": False, "grafikler": g, "en_cok": e, "notlar": notlar}


def kur():
    """Köprüye sahte sağlayıcıyı bağlar; eski değeri döner (testte geri konur)."""
    from kimlikwin import harita_kopru
    eski = harita_kopru.saglayici
    harita_kopru.saglayici = (harita, bolge)
    return eski
