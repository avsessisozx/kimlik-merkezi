"""Ortak yardımcılar: sentetik giden kutusu üretici, doğrulayıcı, ölçüm yazıcı."""
from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path


def olc(aday: str, ad: str, **degerler) -> None:
    """Ölçümü günlüğe yazar (workflow bu satırları özete toplar)."""
    kv = " ".join(f"{k}={v}" for k, v in degerler.items())
    print(f"\nOLCUM|{aday}|{ad}|{kv}", file=sys.stdout, flush=True)


def satir_uret(cihaz_id: str, sira: int, doldur: int = 0) -> tuple[str, bytes]:
    kimlik = str(uuid.uuid4())
    kayit = {"id": kimlik, "cihaz": cihaz_id, "sira": sira, "metin": "ö" * 5}
    if doldur:
        kayit["dolgu"] = "x" * doldur
    return kimlik, (json.dumps(kayit, ensure_ascii=False) + "\n").encode("utf-8")


def dosya_yaz(yol: Path, cihaz_id: str, satir_sayisi: int, doldur: int = 0,
              kapanis: bool = False) -> list[str]:
    """Tek bir kapalı giden kutusu dosyası yazar; satır UUID'lerini döndürür.
    kapanis=True ise son satır {"kapanis":true,"satir_sayisi":N} olur (UUID'siz)."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    kimlikler: list[str] = []
    with open(yol, "wb") as f:
        for i in range(satir_sayisi):
            k, b = satir_uret(cihaz_id, i, doldur)
            kimlikler.append(k)
            f.write(b)
        if kapanis:
            f.write((json.dumps({"kapanis": True, "satir_sayisi": satir_sayisi}) + "\n").encode())
    return kimlikler


def uret_giden_kutusu(kok: Path, cihaz_id: str, dosya_sayisi: int, satir_sayisi: int,
                      doldur: int = 0, kapanis: bool = False) -> dict[str, list[str]]:
    """kok/<cihaz_id>/<dosya_uuid>.jsonl üretir. {dosya_adi: [satır uuid]} döndürür."""
    sonuc: dict[str, list[str]] = {}
    for _ in range(dosya_sayisi):
        ad = f"{uuid.uuid4()}.jsonl"
        sonuc[ad] = dosya_yaz(kok / cihaz_id / ad, cihaz_id, satir_sayisi, doldur, kapanis)
    return sonuc


def satir_uuidleri(dizin: Path) -> list[str]:
    """Dizin altındaki (özyinelemeli) tüm *.jsonl dosyalarındaki kayıt UUID'leri (kapanış satırı hariç)."""
    cikti: list[str] = []
    for p in sorted(Path(dizin).rglob("*.jsonl")):
        for s in p.read_bytes().split(b"\n"):
            if not s.strip():
                continue
            d = json.loads(s)
            if "id" in d:
                cikti.append(d["id"])
    return cikti


def dogrula(gonderilen, alinan) -> None:
    """alınan UUID listesi == gönderilen küme ve tekrarsız."""
    alinan = list(alinan)
    g = set(x for lst in (gonderilen.values() if isinstance(gonderilen, dict) else [gonderilen]) for x in lst)
    assert len(alinan) == len(set(alinan)), f"tekrar var: {len(alinan) - len(set(alinan))}"
    eksik = g - set(alinan)
    fazla = set(alinan) - g
    assert not eksik, f"eksik satır: {len(eksik)}"
    assert not fazla, f"fazla satır: {len(fazla)}"


def sha256_dosya(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()
