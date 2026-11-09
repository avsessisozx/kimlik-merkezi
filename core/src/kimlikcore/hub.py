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
import uuid
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import schema as _schema
from .erisim import init_erisim_db
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

    def __init__(self, root: Path, conn: sqlite3.Connection, write: bool, lock: HubLock | None):
        self.root = root
        self._conn = conn
        self._write = write
        self._lock = lock
        self._mutex = threading.RLock()
        self._closed = False
        self.schema_version = _schema.current_version(conn)

    # ------------------------------------------------------------------ açma/kapama
    @classmethod
    def open(cls, root: Path | str, *, write: bool) -> "Hub":
        root = Path(root)
        db = root / DB_NAME
        if write:
            root.mkdir(parents=True, exist_ok=True)
            lock = HubLock(root / "hub.lock")
            lock.acquire()
            try:
                (root / "arsiv").mkdir(exist_ok=True)
                (root / "cikti").mkdir(exist_ok=True)
                conn = sqlite3.connect(db, timeout=5, isolation_level=None, check_same_thread=False)
                try:
                    conn.execute("PRAGMA busy_timeout = 5000")
                    conn.execute("PRAGMA journal_mode = WAL")
                    conn.execute("PRAGMA synchronous = NORMAL")
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.execute("PRAGMA cache_size = -65536")
                    _schema.migrate(conn)
                    init_erisim_db(root)
                except BaseException:
                    conn.close()
                    raise
            except BaseException:
                lock.release()
                raise
            return cls(root, conn, True, lock)
        if not db.is_file():
            raise HubNotFoundError(f"Veri klasöründe {DB_NAME} yok: {root}")
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
        return cls(root, conn, False, None)

    def close(self) -> None:
        with self._mutex:
            if self._closed:
                return
            self._closed = True
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
                while chunk := fi.read(CHUNK):
                    h.update(chunk)
                    fo.write(chunk)
                    size += len(chunk)
                fo.flush()
                os.fsync(fo.fileno())
            sha = h.hexdigest()
            name = _safe_name(src.name)
            d = arsiv / sha
            d.mkdir(exist_ok=True)
            dest = d / name
            if dest.exists():
                if dest.stat().st_size != size:
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
            with open(p, "rb") as f:
                while chunk := f.read(CHUNK):
                    h.update(chunk)
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
