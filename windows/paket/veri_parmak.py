"""Veri klasörü parmak izi (CI, üstüne kurulum denetimi). Kullanım:
  python veri_parmak.py yaz <cikti.json> <klasor-ya-da-dosya>...   dosya adı + boyut + SHA-256 kaydı alır
  python veri_parmak.py denetle <cikti.json>                       aynı yolları yeniden tarar, FARK varsa çıkış 1
Neden: Inno Setup'ın üstüne kurulumu (uygulama içi güncelleme) kullanıcı verisine dokunmamalı; bunu 'dosya var' ile değil
içerik özetiyle denetleriz. Boş/küçük parmak izi 'geçti' sayılmaz (kimlik.db en az bir dosya olmalı)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def ozet(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def tara(yollar: list[str]) -> dict[str, dict]:
    sonuc: dict[str, dict] = {}
    for y in map(Path, yollar):
        dosyalar = sorted(p for p in y.rglob("*") if p.is_file()) if y.is_dir() else ([y] if y.is_file() else [])
        for p in dosyalar:
            sonuc[f"{y.name}/{p.relative_to(y).as_posix()}" if y.is_dir() else y.name] = {"boyut": p.stat().st_size, "sha256": ozet(p)}
    return sonuc


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "yaz":
        cikti, yollar = Path(argv[1]), argv[2:]
        iz = tara(yollar)
        if not any(k.endswith("kimlik.db") and v["boyut"] > 0 for k, v in iz.items()):
            print("HATA: parmak izinde dolu bir kimlik.db yok (veri klasörü yanlış ya da boş)", file=sys.stderr)
            return 1
        cikti.write_text(json.dumps({"yollar": yollar, "dosyalar": iz}, indent=1), encoding="utf-8")
        print(f"parmak izi alındı: {len(iz)} dosya")
        return 0
    if len(argv) == 2 and argv[0] == "denetle":
        kayit = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        simdi = tara(kayit["yollar"])
        onceki = kayit["dosyalar"]
        fark = [f"silinmiş: {k}" for k in onceki if k not in simdi] + [f"eklenmiş: {k}" for k in simdi if k not in onceki] + \
               [f"DEĞİŞMİŞ: {k}" for k in onceki if k in simdi and onceki[k] != simdi[k]]
        if fark:
            print("VERİ KLASÖRÜ DEĞİŞTİ:\n  " + "\n  ".join(fark), file=sys.stderr)
            return 1
        print(f"veri klasörü aynen korundu ({len(simdi)} dosya)")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
