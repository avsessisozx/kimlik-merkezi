"""Zengin SENTETİK demo verisi (gerçek veri değildir; depoya veri konmaz, her çalıştırmada üretilir).

2-3 yıllık, mevsimsel ve haftalık desenli, on binlerce olay: YouTube kanalları, aramalar, siteler,
Reddit, Spotify, GitHub, uygulama kullanımı, dosyalar, notlar + hassas kategoriler (yalnız sayı: içerik üretilmez).

Kullanım:  python demo_veri.py <veri_klasoru> [--tohum N] [--olcek 1.0] [--profil ayse|deniz]
Ekran görüntüsü ve tasarım denemeleri için; testlerde küçük ölçekle (olcek=0.02) kullanılabilir."""
from __future__ import annotations

import argparse
import math
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from kimlikcore import EventIn, Hub

BASLANGIC = date(2024, 1, 1)
BITIS = date(2026, 11, 9)

KANALLAR = {   # kanal: (ağırlık, [video başlığı şablonları], tür, bitiş/başlangıç tarihi)
    "Kod Mutfağı": (10, ["Python ile {} nasıl yapılır", "SQLite iç yapısı: {}", "Rust öğreniyorum: {}", "Veritabanı tasarımı {}"], "Eğitim", None),
    "Bilim Atölyesi": (8, ["Kuantum fiziği {}", "Evrenin {} sırrı", "Beyin ve {}", "Kara delikler {}"], "Belgesel", None),
    "Gezgin Deniz": (7, ["{} şehir turu", "Karadeniz'de {} günü", "Kapadokya {}", "Lizbon'da {} saat"], "Seyahat", None),
    "Pratik Yemek": (6, ["{} tarifi", "15 dakikada {}", "Anne usulü {}", "Fırında {}"], "Yemek", None),
    "Tarih Sohbetleri": (6, ["Osmanlı'da {}", "Roma imparatorluğu {}", "{} savaşı", "Anadolu uygarlıkları {}"], "Belgesel", None),
    "Mini Belgesel": (5, ["Okyanusların {}", "Kutup {}", "Orman {}"], "Belgesel", None),
    "Gece Müziği": (5, ["Lo-fi {} mix", "Caz gecesi {}", "Odaklanma müziği {}"], "Müzik", None),
    "Oyun Günlüğü": (4, ["{} inceleme", "{} bölüm 1", "Bağımsız oyunlar {}"], "Eğlence", None),
    "Fotoğraf Rehberi": (3, ["Işık ve {}", "Portre {}", "Gece çekimi {}"], "Eğitim", None),
    "Yapay Zeka Notları": (6, ["Dil modelleri {}", "Embedding nedir {}", "Ajanlar {}"], "Eğitim", date(2025, 1, 1)),
    "Futbol Analiz": (3, ["Haftanın analizi {}", "Taktik {}"], "Spor", None),
    "Eski Tarih Kanalı": (4, ["Arşivden {}", "Nostalji {}"], "Belgesel", (date(2024, 1, 1), date(2025, 3, 1))),
    "Mutfak Sırları": (2, ["Şef ile {}"], "Yemek", None),
}
ARAMA = ["hava durumu", "python sqlite", "tatil otelleri", "kahve makinesi", "uçak bileti", "film önerileri", "ev kirası",
         "maç sonucu", "dolar kuru", "yürüyüş rotaları", "fts5 türkçe", "pyinstaller hata", "inno setup", "bisiklet bakımı",
         "kitap önerisi", "recete tavuk", "istanbul etkinlik", "vize randevusu", "gitar akorları", "laptop karşılaştırma",
         "elektrik faturası", "sağlık sigortası", "mcp sdk", "sqlite wal", "yapay zeka haberleri", "ders notları"]
SITELER = [("wikipedia.org", 9), ("github.com", 9), ("stackoverflow.com", 7), ("youtube.com", 10), ("eksisozluk.com", 5),
           ("hurriyet.com.tr", 3), ("reddit.com", 6), ("docs.python.org", 5), ("sahibinden.com", 3), ("google.com", 8),
           ("medium.com", 3), ("trendyol.com", 3), ("sqlite.org", 3), ("tdk.gov.tr", 2)]
SUBREDDIT = [("r/Turkey", 8), ("r/python", 7), ("r/AskReddit", 5), ("r/istanbul", 4), ("r/selfhosted", 4), ("r/sqlite", 2),
             ("r/kitap", 3), ("r/Turkce", 3), ("r/ProgrammerHumor", 4), ("r/yemek", 2)]
SANATCI = {"Sezen Aksu": ["Hep Yaşın Olsun", "Gidiyorum", "Kaybolan Yıllar"], "Daft Punk": ["Get Lucky", "Around the World", "One More Time"],
           "Tarkan": ["Şımarık", "Kuzu Kuzu", "Dudu"], "Mor ve Ötesi": ["Bir Derdim Var", "Deli", "Cambaz"],
           "Radiohead": ["Karma Police", "Creep", "Reckoner"], "Duman": ["Her Şeyi Yak", "Bu Akşam", "Köprüaltı"],
           "Norah Jones": ["Don't Know Why", "Come Away With Me"], "Barış Manço": ["Gülpembe", "Dönence", "Can Bedenden Çıkmayınca"],
           "Khruangbin": ["Time (You and I)", "Maria También"], "Ludovico Einaudi": ["Nuvole Bianche", "Experience"],
           "Cem Karaca": ["Resimdeki Gözyaşları", "Tamirci Çırağı"], "Massive Attack": ["Teardrop", "Angel"]}
SANATCI_AGIRLIK = [9, 8, 5, 6, 6, 5, 4, 7, 3, 5, 3, 3]
DEPOLAR = [("kimlik-merkezi", 10), ("blog", 3), ("dotfiles", 2), ("araclar", 4), ("oyun-denemesi", 2), ("ders-notlari", 3)]
UYGULAMALAR = [("Tarayıcı", 10), ("Kod düzenleyici", 8), ("Mesajlaşma", 6), ("Müzik", 5), ("Harita", 2), ("Fotoğraflar", 3),
               ("Notlar", 3), ("Takvim", 2), ("Terminal", 4)]
DOSYA_TURLERI = [("pdf", 6), ("jpg", 8), ("docx", 3), ("py", 5), ("xlsx", 2), ("zip", 1), ("png", 5), ("md", 3)]
YERLER = [("İstanbul", 12), ("Ankara", 3), ("İzmir", 2), ("Bursa", 2), ("Antalya", 1)]
PLATFORMLAR = [("Claude", 9), ("ChatGPT", 5), ("Gemini", 2), ("DeepSeek", 2)]
NOT_BASLIK = ["Alışveriş listesi", "Toplantı notu", "Fikir: harita ekranı", "Kitap alıntısı", "Yapılacaklar"]
KONULAR = ["nasıl çalışır", "ipuçları", "başlangıç", "ileri düzey", "özet", "derinlemesine", "tartışma", "yeni başlayanlar için"]


def _agirlikli(rng, secenekler):
    toplam = sum(a for _, a in secenekler)
    x = rng.random() * toplam
    for ad, a in secenekler:
        x -= a
        if x <= 0:
            return ad
    return secenekler[-1][0]


def _gun_agirligi(d: date, profil: dict) -> float:
    yil_kesri = (d - BASLANGIC).days / max(1, (BITIS - BASLANGIC).days)
    mevsim = 1 + profil["mevsim"] * math.cos((d.timetuple().tm_yday - 15) / 365.25 * 2 * math.pi)   # kışın artar
    buyume = 1 + profil["buyume"] * yil_kesri
    return mevsim * buyume


def _saat_sec(rng, tepeler):
    t, s = rng.choice(tepeler)
    return int(max(0, min(23, rng.gauss(t, s)))) % 24


def uret(hub: Hub, *, tohum: int = 7, olcek: float = 1.0, profil: str = "ayse") -> dict:
    rng = random.Random(tohum)
    P = {"ayse": {"mevsim": 0.28, "buyume": 0.5, "hafta_sonu": 1.5}, "deniz": {"mevsim": 0.15, "buyume": 0.9, "hafta_sonu": 1.1}}[profil]
    gunler = [BASLANGIC + timedelta(days=i) for i in range((BITIS - BASLANGIC).days + 1)]
    agirlik = [_gun_agirligi(d, P) for d in gunler]
    sayac = {"n": 0}
    kaynaklar = {k: hub.add_source(k, "demo", None) for k in
                 ("youtube", "chrome", "reddit", "spotify", "github", "dosya", "notlar", "uygulama", "gmail", "mesaj", "konum", "sohbet", "foto")}

    def olay(kaynak, ts, kind, kategori, text, payload):
        sayac["n"] += 1
        return kaynak, EventIn(ts=ts.strftime("%Y-%m-%dT%H:%M:%SZ"), kind=kind, category=kategori, text=text, payload=payload,
                               event_key=f"demo-{profil}-{kind}-{sayac['n']}")

    def zaman(gun, saat, rng):
        return datetime(gun.year, gun.month, gun.day, saat, rng.randint(0, 59), rng.randint(0, 59), tzinfo=timezone.utc)

    def dagit(adet, hafta_sonu_carpani, saat_tepeleri, uretici):
        """Toplam `adet` olayı günlere (mevsim+büyüme+hafta içi/sonu) ve saatlere dağıtır."""
        adet = int(adet * olcek)
        w = [a * (hafta_sonu_carpani if g.weekday() >= 5 else 1.0) for a, g in zip(agirlik, gunler)]
        for gun in rng.choices(gunler, weights=w, k=adet):
            yield uretici(gun, zaman(gun, _saat_sec(rng, saat_tepeleri), rng))

    olaylar = []
    # --- video (akşam ve hafta sonu)
    kn = [(k, v[0]) for k, v in KANALLAR.items()]
    for ev in dagit(9500, P["hafta_sonu"], [(21, 2.2), (13, 1.5), (23, 1.2)], lambda g, t: (g, t)):
        g, t = ev
        for _ in range(8):
            k = _agirlikli(rng, kn)
            _, sablon, tur, sinir = KANALLAR[k]
            if sinir is None or (isinstance(sinir, date) and g >= sinir) or (isinstance(sinir, tuple) and sinir[0] <= g <= sinir[1]):
                break
        baslik = rng.choice(sablon).format(rng.choice(KONULAR)) + f" #{rng.randint(1, 60)}"
        olaylar.append(olay("youtube", t, "youtube.izleme", "video", f"{baslik} {k}", {"kanal": k, "video": baslik, "tur": tur}))
    # --- tarama: arama + ziyaret (gün içi, iş saatleri)
    for g, t in dagit(5200, 1.1, [(10, 2), (15, 2.5), (21, 2)], lambda g, t: (g, t)):
        terim = rng.choice(ARAMA)
        olaylar.append(olay("chrome", t, "chrome.arama", "tarama", terim, {"terim": terim}))
    for g, t in dagit(7800, 1.1, [(10, 2), (15, 2.5), (21, 2)], lambda g, t: (g, t)):
        site = _agirlikli(rng, SITELER)
        olaylar.append(olay("chrome", t, "chrome.ziyaret", "tarama", site, {"site": site, "url": f"https://{site}/" + str(rng.randint(1, 9999))}))
    # --- sosyal
    for g, t in dagit(2600, 1.3, [(22, 2), (12, 1.5)], lambda g, t: (g, t)):
        sr = _agirlikli(rng, SUBREDDIT)
        tur = rng.choices(["Yorum", "Gönderi", "Beğeni"], [5, 1, 8])[0]
        olaylar.append(olay("reddit", t, "reddit." + tur.lower(), "sosyal", f"{sr} {tur}", {"subreddit": sr, "tur": tur}))
    # --- müzik (yolculuk saatleri ve akşam)
    san = list(SANATCI)
    for g, t in dagit(8200, 1.0, [(8, 1), (18, 1.5), (22, 1.5)], lambda g, t: (g, t)):
        s = rng.choices(san, SANATCI_AGIRLIK)[0]
        parca = rng.choice(SANATCI[s])
        olaylar.append(olay("spotify", t, "spotify.dinleme", "muzik", f"{parca} {s}", {"sanatci": s, "parca": parca,
                                                                                       "tur": "Türkçe" if s in ("Sezen Aksu", "Tarkan", "Mor ve Ötesi", "Duman", "Barış Manço", "Cem Karaca") else "Yabancı"}))
    # --- kod (hafta içi gündüz)
    for g, t in dagit(1900, 0.5, [(11, 2), (15, 2), (22, 1.5)], lambda g, t: (g, t)):
        d = _agirlikli(rng, DEPOLAR)
        olaylar.append(olay("github", t, "github.commit", "kod", f"{d} commit", {"depo": d}))
    # --- dosyalar, notlar, uygulama
    for g, t in dagit(650, 0.8, [(11, 2), (16, 2)], lambda g, t: (g, t)):
        dt = _agirlikli(rng, DOSYA_TURLERI)
        olaylar.append(olay("dosya", t, "dosya.indirme", "dosyalar", f"belge.{dt}", {"dosya_turu": dt, "dosya": f"belge-{rng.randint(1, 999)}.{dt}"}))
    for g, t in dagit(420, 1.0, [(9, 2), (20, 2)], lambda g, t: (g, t)):
        b = rng.choice(NOT_BASLIK)
        olaylar.append(olay("notlar", t, "not.olustur", "notlar", b, {"baslik": b}))
    for g, t in dagit(4200, 0.7, [(10, 2.5), (15, 2.5)], lambda g, t: (g, t)):
        u = _agirlikli(rng, UYGULAMALAR)
        olaylar.append(olay("uygulama", t, "uygulama.kullanim", "uygulama", u, {"uygulama": u, "dakika": rng.randint(1, 90)}))
    for g, t in dagit(900, 1.4, [(13, 3), (17, 2)], lambda g, t: (g, t)):
        olaylar.append(olay("foto", t, "foto.meta", "medya_meta", "fotoğraf", {"tur": rng.choice(["jpg", "heic", "mp4"])}))
    # --- hassas kategoriler: YALNIZ sayı için; içerik üretilmez
    for kaynak, kat, kind, adet, tepe, hs in [("gmail", "eposta", "eposta.alinan", 3200, [(9, 2), (14, 2)], 0.5),
                                              ("mesaj", "mesaj", "mesaj.ozel", 3600, [(13, 2), (21, 2.5)], 1.2),
                                              ("konum", "konum", "konum.ziyaret", 1500, [(9, 1.5), (18, 2)], 1.0),
                                              ("sohbet", "sohbet", "sohbet.mesaj", 900, [(11, 2), (22, 2)], 1.1)]:
        for g, t in dagit(adet, hs, tepe, lambda g, t: (g, t)):
            payload = {}
            if kat == "konum":
                payload = {"yer": _agirlikli(rng, YERLER)}
            if kat == "sohbet":
                payload = {"platform": _agirlikli(rng, PLATFORMLAR)}
            olaylar.append(olay(kaynak, t, kind, kat, "(içerik yok)", payload))
    # toplu ekle (kaynağa göre)
    kume: dict[str, list[EventIn]] = {}
    for kaynak, ev in olaylar:
        kume.setdefault(kaynak, []).append(ev)
    toplam = 0
    for kaynak, evs in kume.items():
        r = hub.add_events(kaynaklar[kaynak], evs)
        toplam += r.added
    return {"olay": toplam, "kaynak": len(kume)}


def kisi_bilgileri(persona, profil: str) -> None:
    """Persona: örnek beyan edilen bilgiler (sentetik)."""
    veri = {"ayse": [("Adım Ayşe Yılmaz", "kimlik", "ad"), ("İstanbul'da yaşıyorum", "kimlik", "sehir"), ("Kahveyi sütsüz içerim", "tercihler", "kahve"),
                     ("Yazılım geliştiriciyim", "is", "meslek"), ("Windows 11 dizüstü bilgisayar kullanıyorum", "cihazlar", "pc"),
                     ("Bilim ve belgesel videoları izlerim", "ilgi", "video"), ("kimlik-merkezi projesini geliştiriyorum", "projeler", "proje")],
            "deniz": [("Adım Deniz Aydın", "kimlik", "ad"), ("Ankara'da yaşıyorum", "kimlik", "sehir"), ("Gitar çalarım", "ilgi", "gitar"),
                       ("Çayı şekersiz içerim", "tercihler", "cay"), ("Mühendisim", "is", "meslek")]}[profil]
    for stmt, kat, key in veri:
        persona.add_fact(stmt, kat, fact_key=key)


def main(argv=None) -> int:
    from kimlikserver.persona import Persona
    p = argparse.ArgumentParser()
    p.add_argument("klasor", type=Path)
    p.add_argument("--tohum", type=int, default=7)
    p.add_argument("--olcek", type=float, default=1.0)
    p.add_argument("--profil", choices=["ayse", "deniz"], default="ayse")
    a = p.parse_args(argv)
    with Hub.open(a.klasor, write=True) as hub:
        r = uret(hub, tohum=a.tohum, olcek=a.olcek, profil=a.profil)
        kisi_bilgileri(Persona(hub), a.profil)
    print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
