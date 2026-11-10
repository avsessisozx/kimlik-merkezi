"""Hub: bir veri klasörünü temsil eden çekirdek API (INTERFACES §3)."""
from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import schema as _schema
from . import sifreleme as _sif
from .gelen import GelenKutusu
from .errors import (
    FormatError,
    HubNotFoundError,
    HubReadOnlyError,
    NotFoundError,
    SchemaTooNew,
    SchemaTooOld,
)
from .lock import HubLock
from .models import (
    AddResult,
    Category,
    Event,
    EventIn,
    ExportResult,
    ImportResult,
    PurgedInfo,
    PurgeResult,
    RawFile,
    Source,
)
from .streaming import CHUNK
from .turkish import build_fts_query, fold

DB_NAME = "kimlik.db"
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_EVENT_COLS = (
    "event_id, event_key, source_id, device_id, ts, kind, category, payload, text, "
    "schema_version, hidden"
)
_BATCH = 5000


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime(_TS_FORMAT)


def norm_ts(value: str | datetime, *, assume_utc: bool = False) -> str:
    """Zamanı `2026-11-09T12:00:00Z` biçimine (UTC, saniye) çevirir.

    Saat dilimi yoksa `assume_utc` kapalıyken FormatError (belirsiz zaman alınmaz).
    Saniyenin altı atılır; gerekirse `payload` içinde saklanmalıdır.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.strip())
        except ValueError as e:
            raise FormatError("Zaman ISO-8601 biçiminde değil.") from e
    else:
        raise FormatError("Zaman metin ya da datetime olmalı.")
    if dt.tzinfo is None:
        if not assume_utc:
            raise FormatError("Zamanın saat dilimi yok (UTC 'Z' ya da +hh:mm gerekir).")
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(_TS_FORMAT)


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _clean_text(s: str) -> str:
    try:
        s.encode("utf-8")
        return s
    except UnicodeEncodeError:
        return s.encode("utf-8", "replace").decode("utf-8")


def _safe_name(name: str) -> str:
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(name).name).strip()
    if not base or set(base) == {"."}:
        base = "dosya"
    return base[:200]


def _write_only(fn):
    @functools.wraps(fn)
    def wrapper(self: "Hub", *a, **kw):
        if not self._write:
            raise HubReadOnlyError("Hub salt okunur açıldı; yazma işlemi yapılamaz.")
        with self._mutex:
            return fn(self, *a, **kw)

    return wrapper


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(self: "Hub", *a, **kw):
        with self._mutex:
            return fn(self, *a, **kw)

    return wrapper


class Hub:
    """Tek bir veri klasörü. `write=True` tek yazan süreçtir (hub.lock)."""

    schema_version: int

    def __init__(self, root: Path, conn: sqlite3.Connection, write: bool, lock: HubLock | None,
                 dek: bytes | None = None):
        self.root = root
        self._conn = conn
        self._write = write
        self._lock = lock
        # Şifreli veri klasörü: veritabanı bellekte çalışır, diske şifreli kapsayıcı olarak yazılır
        # (docs/SIFRELEME.md). `_dek` yoksa klasör şifresizdir.
        self._dek = dek
        self._yazilan_degisim = conn.total_changes
        self._son_yazim = time.monotonic()
        self._ertele = False
        self._mutex = threading.RLock()
        self._closed = False
        self.schema_version = _schema.current_version(conn)
        self.goc_uyarilari: list[str] = []   # açılışta eski dosya göçü / gelen kutusu uyarıları

    # ------------------------------------------------------------------ açma/kapama
    @classmethod
    def open(cls, root: Path | str, *, write: bool, parola: str | None = None,
             saglayici: "_sif.AnahtarSaglayici | None" = None,
             sifreli: bool | None = None) -> "Hub":
        """Veri klasörünü açar.

        Şifreli klasör (kimlik.db şifreli kapsayıcı) otomatik algılanır; anahtar sırayla OS
        sağlayıcısından (Windows DPAPI), `parola` argümanından ya da KIMLIK_PAROLA ortam
        değişkeninden alınır; alınamazsa `AnahtarGerekli`. `sifreli=True` yalnız YENİ (kimlik.db
        olmayan) klasörde anlamlıdır: şifreli oluşturur; mevcut şifresiz klasör `donusum.sifrele`
        ile dönüştürülür, burada otomatik dönüştürülmez.
        """
        root = Path(root)
        db = root / DB_NAME
        durum = _sif.db_durumu(db)
        if sifreli and durum == "duz":
            raise FormatError("Bu klasör şifresiz; 'kimlikmerkezi sifrele' ile dönüştürün.")
        dek: bytes | None = None
        if durum == "sifreli":
            dek = _sif.anahtari_coz(root, parola=parola, saglayici=saglayici)
        if write:
            root.mkdir(parents=True, exist_ok=True)
            lock = HubLock(root / "hub.lock")
            lock.acquire()
            try:
                (root / "arsiv").mkdir(exist_ok=True)
                (root / "cikti").mkdir(exist_ok=True)
                if durum == "yok" and sifreli:
                    dek = _sif.anahtar_kur(root, saglayici)
                if dek is not None:
                    conn = cls._bellek_baglanti(db, dek, durum == "sifreli")
                else:
                    conn = sqlite3.connect(db, timeout=5, isolation_level=None, check_same_thread=False)
                try:
                    conn.execute("PRAGMA busy_timeout = 5000")
                    if dek is None:
                        conn.execute("PRAGMA journal_mode = WAL")
                        conn.execute("PRAGMA synchronous = NORMAL")
                    else:
                        conn.execute("PRAGMA temp_store = MEMORY")
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute("PRAGMA cache_size = -65536")
                    _schema.migrate(conn)
                    if dek is not None and (durum != "sifreli" or conn.total_changes > 0):
                        _sif.bayt_sifrele_yaz(dek, conn.serialize(), db)   # yeni klasör ya da göç yapıldı
                except BaseException:
                    conn.close()
                    raise
            except BaseException:
                lock.release()
                raise
            hub = cls(root, conn, True, lock, dek)
            hub._acilista_isle()
            return hub
        if durum == "yok":
            raise HubNotFoundError(f"Veri klasöründe {DB_NAME} yok: {root}")
        if dek is not None:
            conn = cls._bellek_baglanti(db, dek, True)
            conn.execute("PRAGMA query_only = ON")
        else:
            uri = db.resolve().as_uri() + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5, isolation_level=None, check_same_thread=False)
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA query_only = ON")
            conn.execute("PRAGMA foreign_keys = ON")
            ver = _schema.current_version(conn)
            if ver > _schema.SCHEMA_VERSION:
                raise SchemaTooNew(
                    f"Veritabanı şema sürümü {ver}, bu program en çok {_schema.SCHEMA_VERSION} bilir."
                )
            if ver < _schema.SCHEMA_VERSION:
                raise SchemaTooOld(
                    f"Veritabanı şema sürümü {ver} (güncel {_schema.SCHEMA_VERSION}). "
                    "Önce yazan süreçle (ör. 'kimlikmerkezi baslat') açıp güncelleyin."
                )
        except BaseException:
            conn.close()
            raise
        return cls(root, conn, False, None, dek)

    @staticmethod
    def _bellek_baglanti(db: Path, dek: bytes, mevcut: bool) -> sqlite3.Connection:
        """Şifreli kapsayıcıyı çözüp bellek içi SQLite bağlantısı kurar (düz metin diske yazılmaz)."""
        conn = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False)
        if mevcut:
            try:
                veri = _sif.bayt_coz_oku(dek, db)
                conn.deserialize(veri)
            except BaseException:
                conn.close()
                raise
        return conn

    @property
    def sifreli(self) -> bool:
        return self._dek is not None

    # ------------------------------------------------------------------ gelen kutusu / eski dosyalar
    @property
    def gelen(self) -> GelenKutusu:
        """Bu veri klasörünün gelen kutusu (okuyucu Hub'dan da yazılabilir; bkz. gelen.py)."""
        return GelenKutusu(self.root, self._dek)

    def _acilista_isle(self) -> None:
        """Yazan Hub açılırken: eski `oneri.db`/`erisim.db`yi göç ettirir, gelen kutusunu işler.
        Başarısızlık Hub'ın açılmasını engellemez; `goc_uyarilari`na yazılır (veri silinmez)."""
        for ad, islev in (("eski dosyalar", self._eski_dosyalari_goc),
                          ("gelen kutusu", self.gelen_birlestir)):
            try:
                islev()
            except Exception as e:  # noqa: BLE001 - açılışı engelleme; neden uyarıda
                self.goc_uyarilari.append(f"{ad} işlenemedi ({type(e).__name__}); veri silinmedi.")

    @_write_only
    def gelen_birlestir(self) -> dict[str, int]:
        """`gelen/` altındaki erişim günlüğü ve öneri kayıtlarını veritabanına işler, sonra dosyaları
        siler (önce kalıcı yazım). Yinelenen öneri atılır (aynı `oneri_id` ya da aynı `ifade_hash`
        kuyrukta/bastırılmış/karara bağlanmışsa). Okunamayan dosyalar `gelen/bozuk/`a alınır."""
        kutu = self.gelen
        kayitlar, bozuk = kutu.listele()
        sonuc = {"erisim": 0, "oneri": 0, "yinelenen": 0, "bozuk": 0}
        for ad in bozuk:
            kutu.karantina(ad)
            sonuc["bozuk"] += 1
        if not kayitlar:
            return sonuc
        islenen: list[str] = []
        gecersiz: list[str] = []
        c = self._conn
        c.execute("PRAGMA synchronous = FULL")  # dosyalar silinmeden önce işlem diske insin
        try:
            with self._tx():
                for ad, k in kayitlar:
                    tur = ad.split("-", 1)[0]
                    try:
                        if tur == "erisim":
                            c.execute(
                                "INSERT INTO access_log(ts, app_id, tool, category, result_count, "
                                "outcome) VALUES (?, ?, ?, ?, ?, ?)",
                                (k["ts"], k["app_id"], k["tool"], k.get("category"),
                                 int(k["result_count"]), k["outcome"]))
                            sonuc["erisim"] += 1
                        else:
                            h = k["ifade_hash"]
                            var = (c.execute("SELECT 1 FROM oneriler WHERE oneri_id = ? OR "
                                             "ifade_hash = ?", (k["oneri_id"], h)).fetchone()
                                   or c.execute("SELECT 1 FROM bastirilan WHERE ifade_hash = ?",
                                                (h,)).fetchone())
                            if var:
                                sonuc["yinelenen"] += 1
                            else:
                                c.execute(
                                    "INSERT INTO oneriler(oneri_id, ts, app_id, statement, category, "
                                    "fact_key, kanit_event_ids, guven, durum, ifade_hash) "
                                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'bekliyor', ?)",
                                    (k["oneri_id"], k["ts"], k["app_id"], k["statement"],
                                     k["category"], k.get("fact_key"),
                                     json.dumps(k["kanit_event_ids"]), float(k["guven"]), h))
                                sonuc["oneri"] += 1
                    except (KeyError, TypeError, ValueError, sqlite3.IntegrityError):
                        # Biçimi bozuk kayıt diğerlerini engellemesin: atla, dosyayı karantinaya al.
                        gecersiz.append(ad)
                        continue
                    islenen.append(ad)
        finally:
            c.execute("PRAGMA synchronous = NORMAL")
        self._kalici_yaz()
        for ad in islenen:
            kutu.sil(ad)
        for ad in gecersiz:
            kutu.karantina(ad)
            sonuc["bozuk"] += 1
        return sonuc

    def _eski_dosyalari_goc(self) -> None:
        """Eski ayrı `oneri.db` ve `erisim.db` içeriğini ana veritabanına taşır, DOĞRULAR, sonra
        eski dosyayı (-wal/-shm dahil) sıfırlayıp siler. Doğrulama tutmazsa dosya SİLİNMEZ."""
        for ad, islev in (("oneri.db", self._oneri_db_goc), ("erisim.db", self._erisim_db_goc)):
            yol = self.root / ad
            if not yol.is_file():
                continue
            try:
                ok = islev(yol)
            except (sqlite3.Error, OSError) as e:
                self.goc_uyarilari.append(f"{ad} göç ettirilemedi ({type(e).__name__}); dosya duruyor.")
                continue
            if not ok:
                self.goc_uyarilari.append(f"{ad} göç doğrulaması tutmadı; dosya silinmedi.")
                continue
            for ek in ("", "-wal", "-shm", "-journal"):
                p = self.root / (ad + ek)
                if p.exists():
                    _sif.guvenli_sil(p)

    @staticmethod
    def _eski_ac(yol: Path) -> sqlite3.Connection:
        c = sqlite3.connect(yol, timeout=5, isolation_level=None)
        c.execute("PRAGMA busy_timeout = 5000")
        try:
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass
        return c

    def _sifreli_dogrula(self) -> bool:
        """Şifreli klasörde diske yazılanı geri çözüp açılabildiğini denetler."""
        if self._dek is None:
            return True
        self._kalici_yaz()
        k = sqlite3.connect(":memory:")
        try:
            k.deserialize(_sif.bayt_coz_oku(self._dek, self.root / DB_NAME))
            return k.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        finally:
            k.close()

    def _oneri_db_goc(self, yol: Path) -> bool:
        eski = self._eski_ac(yol)
        try:
            if not eski.execute("SELECT 1 FROM sqlite_master WHERE name = 'oneriler'").fetchone():
                return True  # boş/şemasız dosya: taşınacak bir şey yok
            sutun = ("oneri_id, ts, app_id, statement, category, fact_key, kanit_event_ids, guven, "
                     "durum, ifade_hash, karar_ts, duzeltilmis_ifade, fact_id")
            satirlar = eski.execute(f"SELECT {sutun} FROM oneriler ORDER BY ts, oneri_id").fetchall()
            bastirilan = (eski.execute("SELECT ifade_hash, ts, category FROM bastirilan").fetchall()
                          if eski.execute("SELECT 1 FROM sqlite_master WHERE name = 'bastirilan'"
                                          ).fetchone() else [])
        finally:
            eski.close()
        with self.transaction() as c:
            c.executemany(f"INSERT OR IGNORE INTO oneriler({sutun}) VALUES ({','.join('?' * 13)})",
                          satirlar)
            c.executemany("INSERT OR IGNORE INTO bastirilan(ifade_hash, ts, category) VALUES (?,?,?)",
                          bastirilan)
        c = self._conn
        for r in satirlar:
            if c.execute(f"SELECT {sutun} FROM oneriler WHERE oneri_id = ?", (r[0],)
                         ).fetchone() != r:
                return False
        for r in bastirilan:
            if c.execute("SELECT ifade_hash, ts, category FROM bastirilan WHERE ifade_hash = ?",
                         (r[0],)).fetchone() != r:
                return False
        return self._sifreli_dogrula()

    def _erisim_db_goc(self, yol: Path) -> bool:
        eski = self._eski_ac(yol)
        try:
            if not eski.execute("SELECT 1 FROM sqlite_master WHERE name = 'access_log'").fetchone():
                return True
            satirlar = eski.execute("SELECT ts, app_id, tool, category, result_count, outcome "
                                    "FROM access_log ORDER BY id").fetchall()
        finally:
            eski.close()
        isaret = "goc_erisim_db"  # tek seferlik işaret: yarım kalan göç satırları ikiye katlamasın
        with self.transaction() as c:
            if c.execute("SELECT 1 FROM meta WHERE key = ?", (isaret,)).fetchone() is None:
                c.executemany("INSERT INTO access_log(ts, app_id, tool, category, result_count, "
                              "outcome) VALUES (?,?,?,?,?,?)", satirlar)
                c.execute("INSERT INTO meta(key, value) VALUES (?, ?)", (isaret, str(len(satirlar))))
        # Doğrulama: her eski satır yeni tabloda var mı (çoklu küme karşılaştırması).
        c = self._conn
        yeni = c.execute("SELECT ts, app_id, tool, category, result_count, outcome FROM access_log"
                         ).fetchall()
        from collections import Counter
        eksik = Counter(satirlar) - Counter(yeni)
        if eksik:
            return False
        return self._sifreli_dogrula()

    def _kalici_yaz(self, *, zamanli: bool = False) -> None:
        """Şifreli klasörde değişiklik varsa veritabanını şifreli kapsayıcıya atomik yazar.
        `zamanli`: toplu içe almada en çok ~20 sn'de bir yazar (her grupta tüm dosyayı yazmamak için)."""
        if self._dek is None or not self._write:
            return
        if self._conn.total_changes == self._yazilan_degisim:
            return
        if zamanli and time.monotonic() - self._son_yazim < 20:
            return
        _sif.bayt_sifrele_yaz(self._dek, self._conn.serialize(), self.root / DB_NAME)
        self._yazilan_degisim = self._conn.total_changes
        self._son_yazim = time.monotonic()

    def raw_parcalari(self, yol: str):
        """Arşivdeki ham dosyanın DÜZ içeriğini parça parça üretir (şifreliyse çözerek)."""
        p = self.root / yol
        if _sif.sifreli_mi(p):
            dek = self._dek or _sif.anahtari_coz(self.root)
            with open(p, "rb") as f:
                yield from _sif.SifreOkuyucu(f, dek).parcalar()
        else:
            with open(p, "rb") as f:
                while chunk := f.read(CHUNK):
                    yield chunk

    def close(self) -> None:
        with self._mutex:
            if self._closed:
                return
            self._closed = True
            try:
                self._kalici_yaz()
            finally:
                try:
                    self._conn.close()
                finally:
                    if self._lock:
                        self._lock.release()

    def __enter__(self) -> "Hub":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def writable(self) -> bool:
        return self._write

    @contextmanager
    def _tx(self):
        c = self._conn
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
        except BaseException:
            c.execute("ROLLBACK")
            raise
        else:
            c.execute("COMMIT")
            self._kalici_yaz(zamanli=self._ertele)

    # ------------------------------------------------------------------ genel SQL erişimi
    @contextmanager
    def transaction(self):
        """Yazma işlemi: `BEGIN IMMEDIATE` ... `COMMIT` (istisnada `ROLLBACK`).

        Bağlam içinde `sqlite3.Connection` döner; yalnız `execute`/`executemany` kullanın,
        `commit`/`rollback`/`close` çağırmayın. İç içe `transaction()` desteklenmez.
        Salt okunur hub'da `HubReadOnlyError`. İşlem boyunca hub'ın iç kilidi tutulur
        (diğer iş parçacıkları bekler). Persona/anahtar/izin tabloları (server) bunu kullanır;
        `Hub._conn/_tx/_mutex` özel üyeleri yerine geçer.
        """
        if not self._write:
            raise HubReadOnlyError("Hub salt okunur açıldı; yazma işlemi yapılamaz.")
        with self._mutex:
            with self._tx() as c:
                yield c

    def query(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> list[tuple]:
        """Salt okunur SQL (tek ifade); satırları `tuple` listesi olarak döner.

        Yazan hub'da bağlantı çağrı süresince `query_only` yapılır: INSERT/UPDATE/DDL
        `sqlite3.OperationalError` verir. Açık bir `transaction()` içinden çağrılırsa
        o işlemin yazdıklarını da görür. `?` ya da `:ad` parametreleri kullanın.
        """
        with self._mutex:
            c = self._conn
            if self._write:
                c.execute("PRAGMA query_only = ON")
            try:
                return c.execute(sql, params).fetchall()
            finally:
                if self._write:
                    c.execute("PRAGMA query_only = OFF")

    def query_one(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> tuple | None:
        """`query` ile aynı; ilk satırı ya da `None` döner."""
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # ------------------------------------------------------------------ kaynak, ham arşiv
    @_write_only
    def add_source(self, kind: str, version: str, file_sha256: str | None) -> str:
        """Kaynak ekler. Aynı tür + aynı dosya hash'i ve kaldırılmamış bir kaynak varsa
        onun kimliğini döner (aynı dosyayı ikinci kez almak yeni kaynak açmaz)."""
        if not kind or not version:
            raise FormatError("Kaynak türü ve sürümü boş olamaz.")
        if file_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", file_sha256):
            raise FormatError("file_sha256 küçük harfli 64 karakterlik hex olmalı.")
        with self._tx() as c:
            if file_sha256:
                row = c.execute(
                    "SELECT source_id FROM sources WHERE kind = ? AND file_sha256 = ? "
                    "AND removed_at IS NULL",
                    (kind, file_sha256),
                ).fetchone()
                if row:
                    return row[0]
            sid = str(uuid.uuid4())
            c.execute(
                "INSERT INTO sources(source_id, kind, version, file_sha256, imported_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (sid, kind, version, file_sha256, now_iso()),
            )
            return sid

    def _source_row(self, source_id: str) -> sqlite3.Row | tuple:
        row = self._conn.execute(
            "SELECT source_id, kind, version, file_sha256, imported_at, removed_at, removed_reason "
            "FROM sources WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Kaynak yok: {source_id}")
        return row

    @_write_only
    def store_raw(self, source_id: str, src_path: Path | str) -> RawFile:
        """Dosyayı akışla `arsiv/<sha256>/<ad>` altına kopyalar; kaynak dosyaya dokunmaz,
        arşivdeki kopya salt okunur yapılır ve bir daha değiştirilmez."""
        self._source_row(source_id)
        src = Path(src_path)
        arsiv = self.root / "arsiv"
        arsiv.mkdir(exist_ok=True)
        tmp = arsiv / f".gecici-{uuid.uuid4().hex}"
        h = hashlib.sha256()
        size = 0
        try:
            with open(src, "rb") as fi, open(tmp, "wb") as fo:
                yazici = _sif.SifreYazici(fo, self._dek) if self._dek else None
                while chunk := fi.read(CHUNK):
                    h.update(chunk)
                    if yazici:
                        yazici.yaz(chunk)
                    else:
                        fo.write(chunk)
                    size += len(chunk)
                if yazici:
                    yazici.bitir()
                fo.flush()
                os.fsync(fo.fileno())
            sha = h.hexdigest()
            name = _safe_name(src.name)
            d = arsiv / sha
            d.mkdir(exist_ok=True)
            dest = d / name
            if dest.exists():
                mevcut = _sif.acik_boyut(dest) if _sif.sifreli_mi(dest) else dest.stat().st_size
                if mevcut != size:
                    raise FormatError("Arşivdeki aynı adlı dosyanın boyutu uyuşmuyor (bozulma?).")
                tmp.unlink()
            else:
                os.replace(tmp, dest)
                os.chmod(dest, 0o444)
        finally:
            tmp.unlink(missing_ok=True)
        rel = f"arsiv/{sha}/{name}"
        with self._tx() as c:
            row = c.execute(
                "SELECT raw_id FROM raw_files WHERE source_id = ? AND sha256 = ? AND name = ?",
                (source_id, sha, name),
            ).fetchone()
            if row:
                raw_id = row[0]
            else:
                raw_id = str(uuid.uuid4())
                c.execute(
                    "INSERT INTO raw_files(raw_id, source_id, name, path, sha256, size, stored_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (raw_id, source_id, name, rel, sha, size, now_iso()),
                )
            c.execute(
                "UPDATE sources SET file_sha256 = ? WHERE source_id = ? AND file_sha256 IS NULL",
                (sha, source_id),
            )
        return RawFile(raw_id, source_id, name, rel, sha, size)

    @_locked
    def raw_files(self, source_id: str | None = None) -> list[RawFile]:
        sql = "SELECT raw_id, source_id, name, path, sha256, size FROM raw_files"
        args: tuple = ()
        if source_id:
            sql += " WHERE source_id = ?"
            args = (source_id,)
        return [RawFile(*r) for r in self._conn.execute(sql + " ORDER BY stored_at, raw_id", args)]

    @_locked
    def verify_archive(self) -> list[str]:
        """Arşivdeki her dosyanın SHA-256'sını yeniden hesaplar; sorunların listesini döner
        (boş liste = tümü sağlam). Tam okuma yapar, büyük arşivde yavaştır."""
        problems: list[str] = []
        seen: set[str] = set()
        for path, sha in self._conn.execute("SELECT path, sha256 FROM raw_files"):
            if path in seen:
                continue
            seen.add(path)
            p = self.root / path
            if not p.is_file():
                problems.append(f"eksik: {path}")
                continue
            h = hashlib.sha256()
            try:
                for chunk in self.raw_parcalari(path):
                    h.update(chunk)
            except _sif.SifrelemeHatasi:
                problems.append(f"şifre çözülemedi/bozuk: {path}")
                continue
            if h.hexdigest() != sha:
                problems.append(f"hash uyuşmuyor: {path}")
        return problems

    @_locked
    def sources(self, *, include_removed: bool = True) -> list[Source]:
        sql = (
            "SELECT s.source_id, s.kind, s.version, s.file_sha256, s.imported_at, s.removed_at, "
            "s.removed_reason, (SELECT count(*) FROM events e WHERE e.source_id = s.source_id) "
            "FROM sources s"
        )
        if not include_removed:
            sql += " WHERE s.removed_at IS NULL"
        return [Source(*r) for r in self._conn.execute(sql + " ORDER BY s.imported_at, s.source_id")]

    # ------------------------------------------------------------------ olaylar
    @staticmethod
    def _prepare(ev: EventIn, source_kind: str) -> tuple[str, str, str, str, str, str | None, str]:
        if ev.category not in Category.ALL:
            raise FormatError(f"Bilinmeyen kategori: {ev.category!r}")
        if not isinstance(ev.kind, str) or not ev.kind:
            raise FormatError("Olay türü (kind) boş olamaz.")
        if not isinstance(ev.payload, dict):
            raise FormatError("payload bir sözlük olmalı.")
        if ev.text is None or not isinstance(ev.text, str):
            raise FormatError("text metin olmalı.")
        ts = norm_ts(ev.ts)
        try:
            payload = canonical_json(ev.payload)
        except (TypeError, ValueError) as e:
            raise FormatError("payload JSON'a çevrilemiyor (NaN/tür).") from e
        payload = _clean_text(payload)
        text = _clean_text(ev.text)
        key = ev.event_key
        if key is None:
            digest = hashlib.sha256(
                canonical_json([source_kind, ev.kind, ev.category, ts, ev.device_id, payload, text]).encode(
                    "utf-8", "replace"
                )
            ).hexdigest()
            key = "h:" + digest
        elif not isinstance(key, str) or not key or len(key) > 1000:
            raise FormatError("event_key boş olmayan, en çok 1000 karakterlik metin olmalı.")
        return key, ts, ev.kind, ev.category, payload, ev.device_id, text

    @_write_only
    def add_events(
        self, source_id: str, events: Iterable[EventIn], *, batch_size: int = _BATCH
    ) -> AddResult:
        """Olayları ekler; aynı `event_key` ikinci kez eklenmez (duplicate sayılır).

        Akışla çalışır: `events` üreteç olabilir, `batch_size` kayıtta bir işlem kesinleşir.
        Hata ortasında olursa önceki gruplar kalır (yeniden çalıştırmak güvenlidir).
        Kaldırılmış (gizli) bir kaynağın olayları aynı anahtarla yeniden gelirse
        görünür olur ve yeni kaynağa bağlanır ("added" sayılır); tek tek gizlenmiş
        olaylar gizli kalır.
        """
        src = self._source_row(source_id)
        if src[5] is not None:
            raise NotFoundError("Kaldırılmış kaynağa olay eklenemez.")
        kind = src[1]
        added = dup = 0
        batch: list[tuple] = []
        self._ertele = True   # şifreli klasörde her grupta tüm dosyayı yeniden yazma (zamanlı yaz)
        try:
            for ev in events:
                batch.append(self._prepare(ev, kind))
                if len(batch) >= batch_size:
                    a, d = self._flush(source_id, batch)
                    added += a
                    dup += d
                    batch.clear()
            if batch:
                a, d = self._flush(source_id, batch)
                added += a
                dup += d
        finally:
            self._ertele = False
            self._kalici_yaz()
        return AddResult(added=added, duplicate=dup)

    def _flush(self, source_id: str, batch: list[tuple]) -> tuple[int, int]:
        added = dup = 0
        now = now_iso()
        ver = self.schema_version
        with self._tx() as c:
            for key, ts, kind, cat, payload, device, text in batch:
                cur = c.execute(
                    "INSERT OR IGNORE INTO events(event_id, event_key, source_id, device_id, ts, "
                    "kind, category, payload, text, schema_version, hidden, ingested_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                    (str(uuid.uuid4()), key, source_id, device, ts, kind, cat, payload, text, ver, now),
                )
                if cur.rowcount == 1:
                    folded = fold(text)
                    if folded.strip():
                        c.execute(
                            "INSERT INTO events_fts(rowid, text) VALUES (?, ?)", (cur.lastrowid, folded)
                        )
                    added += 1
                    continue
                revive = c.execute(
                    "UPDATE events SET source_id = ?, hidden = 0 WHERE event_key = ? AND hidden = 1 "
                    "AND source_id IN (SELECT source_id FROM sources WHERE removed_at IS NOT NULL) "
                    "AND NOT EXISTS (SELECT 1 FROM tombstones t WHERE t.kind = 'event_hidden' "
                    "AND t.event_id = events.event_id)",
                    (source_id, key),
                )
                if revive.rowcount == 1:
                    added += 1
                else:
                    dup += 1
        return added, dup

    @staticmethod
    def _row_event(r: tuple) -> Event:
        return Event(
            event_id=r[0], event_key=r[1], source_id=r[2], device_id=r[3], ts=r[4], kind=r[5],
            category=r[6], payload=json.loads(r[7]), text=r[8], schema_version=r[9], hidden=bool(r[10]),
        )

    @staticmethod
    def _cat_clause(categories: Iterable[str] | None, col: str = "e.category") -> tuple[str, list]:
        if categories is None:
            return "", []
        cats = list(categories)
        if not cats:
            return " AND 0", []
        return f" AND {col} IN ({','.join('?' * len(cats))})", cats

    @_locked
    def timeline(
        self,
        *,
        categories: Iterable[str] | None = None,
        since: str | datetime | None = None,
        until: str | datetime | None = None,
        limit: int = 100,
        offset: int = 0,
        ascending: bool = False,
    ) -> list[Event]:
        """Zaman çizelgesi (gizli kayıtlar ve kaldırılmış kaynaklar hariç).

        `since` <= ts <= `until` (UTC; saat dilimsiz değer UTC sayılır). Varsayılan sıra yeniden eskiye.
        """
        where = "e.hidden = 0"
        args: list = []
        if since is not None:
            where += " AND e.ts >= ?"
            args.append(norm_ts(since, assume_utc=True))
        if until is not None:
            where += " AND e.ts <= ?"
            args.append(norm_ts(until, assume_utc=True))
        clause, cargs = self._cat_clause(categories)
        order = "ASC" if ascending else "DESC"
        rows = self._conn.execute(
            f"SELECT {', '.join('e.' + c.strip() for c in _EVENT_COLS.split(','))} FROM events e "
            f"WHERE {where}{clause} ORDER BY e.ts {order}, e.seq {order} LIMIT ? OFFSET ?",
            [*args, *cargs, int(limit), int(offset)],
        ).fetchall()
        return [self._row_event(r) for r in rows]

    @_locked
    def search(
        self,
        query: str,
        *,
        categories: Iterable[str] | None = None,
        limit: int = 50,
        prefix: bool = False,
    ) -> list[Event]:
        """Türkçe katlamalı FTS5 araması; tüm terimler birlikte (VE) aranır."""
        match = build_fts_query(query, prefix=prefix)
        if match is None:
            return []
        clause, cargs = self._cat_clause(categories)
        cols = ", ".join("e." + c.strip() for c in _EVENT_COLS.split(","))
        rows = self._conn.execute(
            f"SELECT {cols} FROM events_fts f JOIN events e ON e.seq = f.rowid "
            f"WHERE events_fts MATCH ? AND e.hidden = 0{clause} "
            "ORDER BY f.rank, e.ts DESC, e.seq DESC LIMIT ?",
            [match, *cargs, int(limit)],
        ).fetchall()
        return [self._row_event(r) for r in rows]

    @_locked
    def get_event(self, event_id: str) -> Event:
        r = self._conn.execute(f"SELECT {_EVENT_COLS} FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if r is None:
            raise NotFoundError(f"Olay yok: {event_id}")
        return self._row_event(r)

    # ------------------------------------------------------------------ silme yolu
    @_write_only
    def hide_event(self, event_id: str, reason: str) -> None:
        """Tek kaydı gizler (fiziksel silinmez; aramada ve erişimde görünmez). Tekrar çağrı zararsız."""
        with self._tx() as c:
            if c.execute("SELECT 1 FROM events WHERE event_id = ?", (event_id,)).fetchone() is None:
                raise NotFoundError(f"Olay yok: {event_id}")
            if c.execute(
                "SELECT 1 FROM tombstones WHERE kind = 'event_hidden' AND event_id = ?", (event_id,)
            ).fetchone():
                return
            c.execute("UPDATE events SET hidden = 1 WHERE event_id = ?", (event_id,))
            c.execute(
                "INSERT INTO tombstones(tombstone_id, kind, event_id, reason, created) "
                "VALUES (?, 'event_hidden', ?, ?, ?)",
                (str(uuid.uuid4()), event_id, reason, now_iso()),
            )

    @_write_only
    def remove_source(self, source_id: str, reason: str) -> int:
        """Kaynağı kaldırır: olayları gizlenir (silinmez). Yeni gizlenen kayıt sayısını döner."""
        with self._tx() as c:
            src = self._source_row(source_id)
            if src[5] is not None:
                return 0
            n = c.execute("UPDATE events SET hidden = 1 WHERE source_id = ? AND hidden = 0", (source_id,)).rowcount
            ts = now_iso()
            c.execute(
                "UPDATE sources SET removed_at = ?, removed_reason = ? WHERE source_id = ?",
                (ts, reason, source_id),
            )
            c.execute(
                "INSERT INTO tombstones(tombstone_id, kind, source_id, source_kind, file_sha256, "
                "count, reason, created) VALUES (?, 'source_removed', ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), source_id, src[1], src[3], n, reason, ts),
            )
            return n

    @_write_only
    def purge_source(self, source_id: str) -> PurgeResult:
        """KALICI silme (kaynak düzeyinde): olaylar, FTS kayıtları, ham arşiv dosyaları.

        Geri alınamaz; onay isteme sorumluluğu çağıran katmandadır (CLI: --onayla).
        Geriye yalnız içeriksiz bir "silindi" tombstone'u kalır (tür, tarih, sayı, hash'ler).
        Bu kaynaktan türeyen persona bilgileri (`facts`) silinmez; kaynak bağı kopar ve
        durumları 'eskimis' olur (yapay zekâya verilmezler).
        """
        src = self._source_row(source_id)
        c = self._conn
        c.execute("PRAGMA secure_delete = ON")
        try:
            raws = c.execute("SELECT path, sha256 FROM raw_files WHERE source_id = ?", (source_id,)).fetchall()
            hashes = sorted({r[1] for r in raws} | ({src[3]} if src[3] else set()))
            with self._tx():
                n = c.execute("SELECT count(*) FROM events WHERE source_id = ?", (source_id,)).fetchone()[0]
                c.execute("DELETE FROM events_fts WHERE rowid IN (SELECT seq FROM events WHERE source_id = ?)", (source_id,))
                c.execute(
                    "DELETE FROM tombstones WHERE kind = 'event_hidden' AND event_id IN "
                    "(SELECT event_id FROM events WHERE source_id = ?)",
                    (source_id,),
                )
                c.execute("DELETE FROM events WHERE source_id = ?", (source_id,))
                demoted = c.execute(
                    "UPDATE facts SET source_id = NULL, status = 'eskimis', updated = ? WHERE source_id = ?",
                    (now_iso(), source_id),
                ).rowcount
                old = c.execute("SELECT tombstone_id FROM tombstones WHERE source_id = ?", (source_id,)).fetchall()
                for (tid,) in old:
                    c.execute("DELETE FROM tombstone_hashes WHERE tombstone_id = ?", (tid,))
                c.execute("DELETE FROM tombstones WHERE source_id = ?", (source_id,))
                c.execute("DELETE FROM raw_files WHERE source_id = ?", (source_id,))
                c.execute("DELETE FROM sources WHERE source_id = ?", (source_id,))
                tid = str(uuid.uuid4())
                c.execute(
                    "INSERT INTO tombstones(tombstone_id, kind, source_id, source_kind, file_sha256, "
                    "count, reason, created) VALUES (?, 'source_purged', ?, ?, ?, ?, NULL, ?)",
                    (tid, source_id, src[1], src[3], n, now_iso()),
                )
                for h in hashes:
                    c.execute("INSERT INTO tombstone_hashes(tombstone_id, sha256) VALUES (?, ?)", (tid, h))
            # FTS5 silinen satırların terimlerini eski bölümlerde tutar; birleştirerek at.
            c.execute("INSERT INTO events_fts(events_fts) VALUES ('optimize')")
            deleted_files = 0
            for path, _sha in raws:
                still = c.execute("SELECT 1 FROM raw_files WHERE path = ? LIMIT 1", (path,)).fetchone()
                if still:
                    continue  # başka bir kaynak aynı arşiv dosyasını kullanıyor
                p = self.root / path
                try:
                    os.chmod(p, 0o666)
                    p.unlink()
                    deleted_files += 1
                except FileNotFoundError:
                    pass
                try:
                    p.parent.rmdir()
                except OSError:
                    pass
            try:
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.OperationalError:
                pass
        finally:
            c.execute("PRAGMA secure_delete = OFF")
        self._kalici_yaz()
        return PurgeResult(source_id, src[1], n, deleted_files, tuple(hashes), demoted)

    @_locked
    def previously_purged(self, sha256: str) -> PurgedInfo | None:
        """Bu hash daha önce kalıcı silinmiş bir kaynağa (dosyasına) aitse bilgisini döner."""
        r = self._conn.execute(
            "SELECT t.tombstone_id, t.source_kind, t.created, t.count, t.file_sha256 FROM tombstones t "
            "JOIN tombstone_hashes h ON h.tombstone_id = t.tombstone_id "
            "WHERE h.sha256 = ? AND t.kind = 'source_purged' ORDER BY t.created DESC LIMIT 1",
            (sha256,),
        ).fetchone()
        return PurgedInfo(*r) if r else None

    @_write_only
    def compact(self) -> None:
        """VACUUM + WAL kesme: silinmiş içerik sayfalarını dosyadan atar. Boş disk gerektirir."""
        self._conn.execute("VACUUM")
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass
        self._kalici_yaz()

    # ------------------------------------------------------------------ dışa/içe aktarım
    @_locked
    def summary(self) -> dict[str, Any]:
        """Kayıt türü başına sayı ve içerik özeti (sıradan bağımsız SHA-256 toplamı)."""
        from . import transfer

        return transfer.summarize(self._conn)

    @_locked
    def export_jsonl(self, out: Path | str) -> ExportResult:
        from . import transfer

        return transfer.export_jsonl(self._conn, Path(out), self.schema_version)

    @_write_only
    def import_jsonl(
        self, src: Path | str, *, progress: Callable[[int], None] | None = None
    ) -> ImportResult:
        """Dışa aktarılan JSON Lines'ı BOŞ hub'a geri yükler (tek işlem; hata olursa hiçbir şey kalmaz)."""
        from . import transfer

        return transfer.import_jsonl(self, Path(src), progress)
