"""Elle aktarım yedeği: "klasörü tara ve al" mantığı (stdlib + sqlite3).

Kurallar:
  - yalnız *.jsonl (ad serbest: kullanıcı kopyayı yeniden adlandırmış olabilir); .tmp/.acik/vb. yok sayılır
  - dosya '\\n' ile bitmiyorsa -> 'kesik' (hiçbir satırı içe alınmaz, dosya olduğu gibi bekletilir)
  - geçersiz JSON satırı -> 'bozuk' (dosya reddedilir)
  - son satır kapanış kaydıysa ({"kapanis":true,"satir_sayisi":N}) N tutmuyorsa -> 'kesik'
  - kapanis_zorunlu=True iken kapanış kaydı yoksa -> 'kapanissiz' (bekletilir)
  - tekrarsızlık: satır UUID'si PRIMARY KEY; INSERT OR IGNORE; dosya başına tek işlem (ya hep ya hiç)
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def ac(db_yolu) -> sqlite3.Connection:
    db = sqlite3.connect(str(db_yolu))
    db.execute("CREATE TABLE IF NOT EXISTS kayit (id TEXT PRIMARY KEY, satir TEXT NOT NULL)")
    db.commit()
    return db


def dosyayi_incele(veri: bytes, kapanis_zorunlu: bool):
    if not veri:
        return "bos", []
    if not veri.endswith(b"\n"):
        return "kesik", []
    kayitlar, kapanis = [], None
    for ham in veri.split(b"\n")[:-1]:
        if not ham.strip():
            continue
        try:
            d = json.loads(ham)
        except ValueError:
            return "bozuk", []
        if not isinstance(d, dict):
            return "bozuk", []
        if d.get("kapanis") is True:
            kapanis = d
        elif isinstance(d.get("id"), str):
            kayitlar.append((d["id"], ham.decode("utf-8")))
        else:
            return "bozuk", []
    if kapanis is not None and kapanis.get("satir_sayisi") != len(kayitlar):
        return "kesik", []
    if kapanis is None and kapanis_zorunlu:
        return "kapanissiz", []
    return "tamam", kayitlar


def klasoru_tara_ve_al(kaynak, db: sqlite3.Connection, kapanis_zorunlu: bool = False) -> dict:
    rapor = {"dosya": 0, "tamam": 0, "bekletilen": 0, "reddedilen": 0, "yeni": 0, "tekrar": 0, "ayrinti": {}}
    for p in sorted(Path(kaynak).rglob("*.jsonl")):
        if not p.is_file():
            continue
        rapor["dosya"] += 1
        durum, kayitlar = dosyayi_incele(p.read_bytes(), kapanis_zorunlu)
        rapor["ayrinti"][p.name] = durum
        if durum in ("kesik", "kapanissiz", "bos"):
            rapor["bekletilen"] += 1
            continue
        if durum == "bozuk":
            rapor["reddedilen"] += 1
            continue
        with db:  # tek işlem
            for kimlik, satir in kayitlar:
                c = db.execute("INSERT OR IGNORE INTO kayit(id, satir) VALUES (?, ?)", (kimlik, satir))
                rapor["yeni" if c.rowcount else "tekrar"] += 1
        rapor["tamam"] += 1
    return rapor


def tum_kimlikler(db) -> list[str]:
    return [r[0] for r in db.execute("SELECT id FROM kayit")]
