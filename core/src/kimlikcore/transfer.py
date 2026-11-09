"""Dışa aktarma (JSON Lines), geri yükleme ve içerik özeti.

Dosya biçimi (her satır bir JSON nesnesi, `t` alanı kayıt türüdür):
  header -> source -> raw_file -> tombstone -> tombstone_hash -> device -> app_key ->
  permission -> fact -> contradiction -> event ... -> footer
`footer` kayıt türü başına sayı ve içerik özetini taşır; ice-aktar bunları doğrular.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .errors import FormatError, HubNotEmptyError, SchemaTooNew
from .models import ExportResult, ImportResult
from .streaming import iter_lines
from .turkish import fold

if TYPE_CHECKING:  # pragma: no cover
    from .hub import Hub

FORMAT = "kimlikmerkezi-jsonl"
FORMAT_VERSION = 1
_MOD = 1 << 256

# (kayıt türü, tablo) — sıra dış anahtar bağımlılığına uygundur.
TYPES: list[tuple[str, str]] = [
    ("source", "sources"),
    ("raw_file", "raw_files"),
    ("tombstone", "tombstones"),
    ("tombstone_hash", "tombstone_hashes"),
    ("device", "devices"),
    ("app_key", "app_keys"),
    ("permission", "permissions"),
    ("fact", "facts"),
    ("contradiction", "contradictions"),
    ("event", "events"),
]
_TABLE_OF = dict(TYPES)
_EVENT_FIELDS = (
    "event_id", "event_key", "source_id", "device_id", "ts", "kind", "category", "payload",
    "text", "schema_version", "hidden", "ingested_at",
)


def _canon(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class _Acc:
    def __init__(self) -> None:
        self.counts = {t: 0 for t, _ in TYPES}
        self.sums = {t: 0 for t, _ in TYPES}

    def add(self, t: str, rec: dict[str, Any]) -> None:
        h = hashlib.sha256(_canon(rec).encode("utf-8", "replace")).digest()
        self.counts[t] += 1
        self.sums[t] = (self.sums[t] + int.from_bytes(h, "big")) % _MOD

    def result(self) -> dict[str, Any]:
        return {
            "counts": dict(self.counts),
            "digests": {t: format(v, "064x") for t, v in self.sums.items()},
        }


@contextmanager
def _snapshot(conn: sqlite3.Connection):
    """Tutarlı okuma için (WAL'de yazanı engellemeyen) okuma işlemi."""
    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN")
    try:
        yield
    finally:
        conn.execute("COMMIT")


def iter_records(conn: sqlite3.Connection) -> Iterator[tuple[str, dict[str, Any]]]:
    for t, table in TYPES:
        if t == "event":
            cur = conn.execute(f"SELECT {', '.join(_EVENT_FIELDS)} FROM events ORDER BY seq")
        else:
            cur = conn.execute(f"SELECT * FROM {table} ORDER BY rowid")
        cols = [d[0] for d in cur.description]
        for row in cur:
            rec = dict(zip(cols, row))
            if t == "event":
                rec["payload"] = json.loads(rec["payload"])
            yield t, rec


def summarize(conn: sqlite3.Connection) -> dict[str, Any]:
    acc = _Acc()
    with _snapshot(conn):
        for t, rec in iter_records(conn):
            acc.add(t, rec)
    return acc.result()


def export_jsonl(conn: sqlite3.Connection, out: Path, schema_version: int) -> ExportResult:
    from .hub import now_iso

    out = Path(out)
    part = out.with_name(out.name + ".part")
    h = hashlib.sha256()
    nbytes = 0
    acc = _Acc()
    try:
        with _snapshot(conn), open(part, "wb") as f:

            def w(rec: dict[str, Any]) -> None:
                nonlocal nbytes
                line = (json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                f.write(line)
                h.update(line)
                nbytes += len(line)

            w({
                "t": "header", "format": FORMAT, "format_version": FORMAT_VERSION,
                "schema_version": schema_version, "exported_at": now_iso(),
            })
            for t, rec in iter_records(conn):
                acc.add(t, rec)
                w({"t": t, **rec})
            w({"t": "footer", **acc.result()})
            f.flush()
            os.fsync(f.fileno())
        os.replace(part, out)
    finally:
        part.unlink(missing_ok=True)
    return ExportResult(str(out), dict(acc.counts), nbytes, h.hexdigest())


def import_jsonl(hub: "Hub", src: Path, progress: Callable[[int], None] | None) -> ImportResult:
    from .hub import canonical_json

    conn = hub._conn
    cols_of: dict[str, set[str]] = {}
    for _t, table in TYPES:
        cols_of[table] = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    acc = _Acc()
    header: dict[str, Any] | None = None
    footer: dict[str, Any] | None = None
    verified = False
    with hub._tx() as c:
        for table in ("sources", "events", "facts", "devices", "app_keys", "tombstones"):
            if c.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise HubNotEmptyError("ice-aktar yalnız boş bir veri klasörüne yapılır.")
        for n, line in iter_lines(src):
            try:
                rec = json.loads(line)
                t = rec.pop("t")
            except (ValueError, KeyError, AttributeError) as e:
                raise FormatError(f"{n}. satır geçerli bir kayıt değil.") from e
            if footer is not None:
                raise FormatError(f"{n}. satır: 'footer' kaydından sonra kayıt var.")
            if header is None:
                if t != "header" or rec.get("format") != FORMAT:
                    raise FormatError("Dosya bir kimlikmerkezi dışa aktarımı değil (header yok).")
                if rec.get("format_version", 0) > FORMAT_VERSION:
                    raise FormatError("Dosya daha yeni bir biçimde; programı güncelleyin.")
                if rec.get("schema_version", 0) > hub.schema_version:
                    raise SchemaTooNew("Dışa aktarım daha yeni bir şema sürümünden.")
                header = rec
                continue
            if t == "footer":
                footer = rec
                continue
            table = _TABLE_OF.get(t)
            if table is None:
                raise FormatError(f"{n}. satır: bilinmeyen kayıt türü.")
            unknown = set(rec) - cols_of[table]
            if unknown:
                raise FormatError(f"{n}. satır: bilinmeyen alanlar: {', '.join(sorted(unknown))}")
            acc.add(t, rec)
            try:
                if t == "event":
                    vals = dict(rec)
                    vals["payload"] = canonical_json(rec["payload"])
                    vals["hidden"] = int(bool(rec["hidden"]))
                    names = list(vals)
                    cur = c.execute(
                        f"INSERT INTO events({', '.join(names)}) VALUES ({','.join('?' * len(names))})",
                        [vals[k] for k in names],
                    )
                    folded = fold(vals["text"])
                    if folded.strip():
                        c.execute("INSERT INTO events_fts(rowid, text) VALUES (?, ?)", (cur.lastrowid, folded))
                else:
                    names = list(rec)
                    c.execute(
                        f"INSERT INTO {table}({', '.join(names)}) VALUES ({','.join('?' * len(names))})",
                        [rec[k] for k in names],
                    )
            except (sqlite3.IntegrityError, KeyError, TypeError) as e:
                raise FormatError(f"{n}. satır: kayıt şemaya uymuyor.") from e
            if progress and n % 10000 == 0:
                progress(n)
        if header is None or footer is None:
            raise FormatError("Dosya eksik ya da kesik (header/footer yok).")
        got = acc.result()
        if got != {"counts": footer.get("counts"), "digests": footer.get("digests")}:
            raise FormatError("Dosyanın içerik özeti footer ile uyuşmuyor (bozuk ya da kesik dosya).")
        if header["schema_version"] == hub.schema_version:
            if summarize(c) != got:
                raise FormatError("Geri yüklenen veri özeti dosyadakiyle uyuşmuyor.")
            verified = True
    missing = sum(
        1 for (p,) in conn.execute("SELECT DISTINCT path FROM raw_files") if not (hub.root / p).is_file()
    )
    return ImportResult(counts=dict(acc.counts), raw_missing=missing, verified=verified)
