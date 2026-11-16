"""importers/fixtures/android_giden/ fixture'larını üretir (sentetik; gerçek veri yok).
Kullanım: python uret_android.py  (bu dosyanın yanındaki android_giden/ klasörüne yazar)"""
import json
import zipfile
from pathlib import Path

KOK = Path(__file__).resolve().parent / "android_giden"
CIHAZ = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
F = {
    "saglam": "11111111-1111-4111-8111-111111111111",
    "kapanissiz": "22222222-2222-4222-8222-222222222222",
    "sayi_tutmaz": "33333333-3333-4333-8333-333333333333",
    "yarim": "44444444-4444-4444-8444-444444444444",
    "bozuk": "55555555-5555-4555-8555-555555555555",
    "bicim2": "66666666-6666-4666-8666-666666666666",
    "bilinmeyen": "77777777-7777-4777-8777-777777777777",
    "yedek": "88888888-8888-4888-8888-888888888888",
}


def baslik(dosya, bicim=1):
    return {"baslik": True, "bicim": bicim, "cihaz_id": CIHAZ, "dosya_id": dosya, "acilis": "2026-03-01T08:00:00Z",
            "uygulama": "0.2.0", "android_api": 31, "model": "RMX2170"}


def kayit(n, tur, kat, metin, yuk=None, onceki=None, ts=None):
    return {"id": f"aaaaaaaa-0000-4000-8000-{n:012d}", "ts": ts or f"2026-03-01T09:{n % 60:02d}:00Z", "tur": tur,
            "kategori": kat, "metin": metin, "yuk": yuk or {}, "onceki": onceki}


SAGLAM = [
    kayit(1, "paylasim.link", "notlar", "Örnek makale bağlantısı", {"url": "https://ornek.test/makale", "baslik": "Örnek makale", "kaynak_uygulama": "tarayici"}),
    kayit(2, "paylasim.metin", "notlar", "Paylaşılan kısa metin", {"kaynak_uygulama": "mesajlar"}),
    kayit(3, "not.hizli", "notlar", "Süt ve ekmek al"),
    kayit(4, "not.hizli", "notlar", "Süt, ekmek ve yumurta al", onceki="aaaaaaaa-0000-4000-8000-000000000003"),
    kayit(5, "not.hizli", "notlar", "Yarın doktor randevusu var"),
    kayit(6, "medya.foto", "medya_meta", "IMG_0001.jpg", {"ad": "IMG_0001.jpg", "boyut": 2048000, "mime": "image/jpeg", "genislik": 4000, "yukseklik": 3000, "cekim_zamani": "2026-03-01T08:30:00Z"}),
    kayit(7, "medya.video", "medya_meta", "VID_0001.mp4", {"ad": "VID_0001.mp4", "boyut": 9048000, "mime": "video/mp4", "sure_ms": 15000}),
    kayit(8, "medya.konum", "konum", "IMG_0001.jpg konumu", {"enlem": 41.0082, "boylam": 28.9784, "medya_id": "aaaaaaaa-0000-4000-8000-000000000006"}),
    kayit(9, "indirilen.dosya", "dosyalar", "rapor.pdf", {"ad": "rapor.pdf", "boyut": 120000, "mime": "application/pdf"}),
    kayit(10, "uygulama.kullanim", "uygulama", "Örnek Uygulama kullanımı", {"paket": "test.ornek.uygulama", "ad": "Örnek Uygulama", "gun": "2026-03-01", "sure_ms": 600000}),
]


def yaz(ad, ust, kayitlar, kapanis="dogru", bicim=1, son_ek="\n"):
    dosya = ad if isinstance(ad, str) else ad
    sat = [json.dumps(ust, ensure_ascii=False)] + [json.dumps(k, ensure_ascii=False) for k in kayitlar]
    if kapanis == "dogru":
        sat.append(json.dumps({"kapanis": True, "kayit_sayisi": len(kayitlar)}))
    elif kapanis == "yanlis":
        sat.append(json.dumps({"kapanis": True, "kayit_sayisi": len(kayitlar) + 2}))
    return "\n".join(sat) + son_ek


def uret():
    KOK.mkdir(parents=True, exist_ok=True)
    d = {}
    d["saglam"] = yaz("s", baslik(F["saglam"]), SAGLAM)
    d["kapanissiz"] = yaz("k", baslik(F["kapanissiz"]), [kayit(20, "not.hizli", "notlar", "kapanışsız not")], kapanis=None)
    d["sayi_tutmaz"] = yaz("t", baslik(F["sayi_tutmaz"]), [kayit(30, "not.hizli", "notlar", "sayısı tutmaz")], kapanis="yanlis")
    yarim = yaz("y", baslik(F["yarim"]), [kayit(40, "not.hizli", "notlar", "yarım dosya"), kayit(41, "not.hizli", "notlar", "ikinci")], kapanis=None, son_ek="")
    d["yarim"] = yarim[: len(yarim) - 25]  # son satır ortadan kesik
    bozuk = yaz("b", baslik(F["bozuk"]), [kayit(50, "not.hizli", "notlar", "bozuk dosya"), kayit(51, "not.hizli", "notlar", "x")])
    sat = bozuk.split("\n")
    sat[2] = sat[2][:20] + "}{ bozuk"
    d["bozuk"] = "\n".join(sat)
    d["bicim2"] = yaz("2", baslik(F["bicim2"], 2), [kayit(60, "not.hizli", "notlar", "gelecek biçim")])
    d["bilinmeyen"] = yaz("u", baslik(F["bilinmeyen"]), [
        kayit(70, "ses.kayit", "notlar", "yeni tür, geçerli kategori", {"sure_ms": 1000}),
        kayit(71, "not.hizli", "notlar", "bilinen tür")])
    d["yedek"] = yaz("e", baslik(F["yedek"]), [
        SAGLAM[2],  # aynı kayıt farklı dosyada yeniden gelir
        kayit(80, "not.hizli", "notlar", "yalnız bu dosyada")])
    for ad, icerik in d.items():
        (KOK / f"{F[ad]}.jsonl").write_text(icerik, encoding="utf-8")
    # karışık zip: sağlam + eksik + sayısı tutmayan
    with zipfile.ZipFile(KOK / "karisik.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for ad in ("saglam", "kapanissiz", "sayi_tutmaz", "bilinmeyen"):
            z.writestr(f"{F[ad]}.jsonl", d[ad])


if __name__ == "__main__":
    uret()
