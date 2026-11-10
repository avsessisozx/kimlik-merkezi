"""Şifresiz <-> şifreli dönüşüm (veri yeniden şifreleme). Ayrıntı: docs/SIFRELEME.md.

Her dosya kendini tanıtır (şifreliyse başlığı `KMSIFRE1`), bu yüzden dönüşüm yarıda kesilirse
yeniden çalıştırmak güvenlidir ve karma durumdaki klasör okunabilir. Sıra her zaman:
yeni dosya yaz -> geri okuyup doğrula -> eskiyi (en iyi çabayla sıfırlayıp) sil.
Dönüşüm sırasında yazan süreç kilidi (hub.lock) tutulur.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import sifreleme as sif
from .errors import FormatError, SifrelemeHatasi
from .hub import DB_NAME
from .lock import HubLock


def _ham_dosyalar(root: Path):
    arsiv = root / "arsiv"
    if arsiv.is_dir():
        for d in sorted(arsiv.iterdir()):
            if d.is_dir():
                for f in sorted(d.iterdir()):
                    if f.is_file() and not f.name.startswith("."):
                        yield f


def _duz_db_serilestir(db: Path) -> bytes:
    """Düz veritabanını (WAL'ı birleştirip) tek parça bayt olarak okur."""
    conn = sqlite3.connect(db, timeout=5, isolation_level=None)
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass
        conn.execute("PRAGMA journal_mode = DELETE")
        return conn.serialize()
    finally:
        conn.close()


def sifrele(root: Path | str, saglayici: sif.AnahtarSaglayici | None = None,
            ilerleme: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Şifresiz veri klasörünü şifreler (veritabanı + ham arşiv). Zaten şifreliyse yalnız
    şifresiz kalmış ham dosyaları tamamlar. Düz metin kopyaları en iyi çabayla sıfırlayıp siler."""
    root = Path(root)
    db = root / DB_NAME
    say = ilerleme or (lambda _m: None)
    durum = sif.db_durumu(db)
    if durum == "yok":
        raise FormatError("Veri klasöründe veritabanı yok; önce 'baslat' ile oluşturun.")
    lock = HubLock(root / "hub.lock")
    lock.acquire()
    try:
        if durum == "duz":
            if sif.zarf_oku(root) is not None:
                raise SifrelemeHatasi(
                    "Veritabanı şifresiz ama anahtar.json var (yarım kalmış bir işlem olabilir). "
                    "Güvenli yol: anahtar.json'ı elle silmeyin; önce yedek alın, sonra destek isteyin."
                )
            dek = sif.anahtar_kur(root, saglayici)
            try:
                veri = _duz_db_serilestir(db)
                sha_once = hashlib.sha256(veri).hexdigest()
                say("Veritabanı şifreleniyor...")
                yeni = db.with_name(DB_NAME + ".sifreli-yeni")
                sif.bayt_sifrele_yaz(dek, veri, yeni)
                # Doğrula: geri çöz, aynı mı + SQLite sağlam mı.
                geri = sif.bayt_coz_oku(dek, yeni)
                if hashlib.sha256(geri).hexdigest() != sha_once:
                    raise SifrelemeHatasi("Şifreli kopya doğrulanamadı; hiçbir şey değiştirilmedi.")
                kontrol = sqlite3.connect(":memory:")
                try:
                    kontrol.deserialize(geri)
                    if kontrol.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise SifrelemeHatasi("Veritabanı bütünlük denetimi başarısız; iptal.")
                finally:
                    kontrol.close()
                eski = db.with_name(DB_NAME + ".duz-eski")
                os.replace(db, eski)
                sif.yerine_koy(yeni, db)
            except BaseException:
                # Dönüşüm başlamadan düştü: anahtarı geri al ki klasör eski (şifresiz) halinde kalsın.
                eski_ = db.with_name(DB_NAME + ".duz-eski")
                if sif.db_durumu(db) == "yok" and eski_.exists():
                    os.replace(eski_, db)
                if sif.db_durumu(db) == "duz":
                    sif.anahtari_sil(root)
                    db.with_name(DB_NAME + ".sifreli-yeni").unlink(missing_ok=True)
                raise
            for ek in ("-wal", "-shm", "-journal"):
                p = db.with_name(DB_NAME + ek)
                if p.exists():
                    sif.guvenli_sil(p)
            sif.guvenli_sil(eski)
        else:
            dek = sif.anahtari_coz(root, saglayici=saglayici)
        n = 0
        for f in _ham_dosyalar(root):
            if sif.sifreli_mi(f):
                continue
            say(f"Ham dosya şifreleniyor: {f.name}")
            os.chmod(f, 0o600)
            sha, boyut = sif.dosya_sifrele(dek, f, f.with_name(f.name + ".sifreli-yeni"))
            yeni = f.with_name(f.name + ".sifreli-yeni")
            sha2, boyut2 = sif.sifreli_sha256(dek, yeni)
            if (sha, boyut) != (sha2, boyut2):
                yeni.unlink(missing_ok=True)
                raise SifrelemeHatasi(f"Ham dosya doğrulanamadı, dokunulmadı: {f.name}")
            eski = f.with_name(f.name + ".duz-eski")
            os.replace(f, eski)
            sif.yerine_koy(yeni, f)
            os.chmod(f, 0o444)
            sif.guvenli_sil(eski)
            n += 1
    finally:
        lock.release()
    return {"veritabani_sifrelendi": durum == "duz", "ham_dosya_sifrelendi": n,
            "uyari": "cikti/ klasörü, erisim.db ve oneri.db bu işlemle şifrelenmez (bkz. docs/SIFRELEME.md)."}


def sifreyi_kaldir(root: Path | str, parola: str | None = None,
                   saglayici: sif.AnahtarSaglayici | None = None,
                   ilerleme: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Şifrelemeyi kapatır: veritabanı ve ham arşiv düz hale getirilir, anahtar dosyası silinir.
    Anahtar açılabilmelidir (OS sağlayıcısı ya da parola)."""
    root = Path(root)
    db = root / DB_NAME
    say = ilerleme or (lambda _m: None)
    durum = sif.db_durumu(db)
    if durum == "yok":
        raise FormatError("Veri klasöründe veritabanı yok.")
    dek = sif.anahtari_coz(root, parola=parola, saglayici=saglayici)
    lock = HubLock(root / "hub.lock")
    lock.acquire()
    try:
        if durum == "sifreli":
            say("Veritabanı çözülüyor...")
            veri = sif.bayt_coz_oku(dek, db)
            kontrol = sqlite3.connect(":memory:")
            try:
                kontrol.deserialize(veri)
                if kontrol.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise SifrelemeHatasi("Çözülen veritabanı bütünlük denetimini geçemedi; iptal.")
            finally:
                kontrol.close()
            yeni = db.with_name(DB_NAME + ".duz-yeni")
            try:
                with open(yeni, "wb") as f:
                    f.write(veri)
                    f.flush()
                    os.fsync(f.fileno())
                sif.yerine_koy(yeni, db)
            finally:
                yeni.unlink(missing_ok=True)
        n = 0
        for f in _ham_dosyalar(root):
            if not sif.sifreli_mi(f):
                continue
            say(f"Ham dosya çözülüyor: {f.name}")
            yeni = f.with_name(f.name + ".duz-yeni")
            h = hashlib.sha256()
            try:
                with open(f, "rb") as fi, open(yeni, "wb") as fo:
                    for p in sif.SifreOkuyucu(fi, dek).parcalar():
                        h.update(p)
                        fo.write(p)
                    fo.flush()
                    os.fsync(fo.fileno())
                if len(f.parent.name) == 64 and h.hexdigest() != f.parent.name:
                    raise SifrelemeHatasi(f"Çözülen ham dosyanın özeti klasör adıyla uyuşmuyor: {f.name}")
                os.chmod(f, 0o600)
                sif.yerine_koy(yeni, f)
                os.chmod(f, 0o444)
            finally:
                yeni.unlink(missing_ok=True)
            n += 1
        # Her şey düz olduktan sonra (karma durum kalmadıysa) anahtarı at.
        if not any(sif.sifreli_mi(f) for f in _ham_dosyalar(root)) and sif.db_durumu(db) == "duz":
            sif.anahtari_sil(root)
    finally:
        lock.release()
    return {"veritabani_cozuldu": durum == "sifreli", "ham_dosya_cozuldu": n}
