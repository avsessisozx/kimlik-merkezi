"""erisim.db: erişim kaydı (`access_log`) için ayrı SQLite dosyası.

Yazan taraf İ2'dir (MCP süreçleri); çekirdek yalnız boş şemayı hazırlar.
Çok sayıda süreç aynı anda yazabilmelidir: WAL + busy_timeout >= 5000 ms.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ERISIM_SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 5000

_DDL = [
    """CREATE TABLE IF NOT EXISTS access_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        app_id TEXT NOT NULL,
        tool TEXT NOT NULL,
        category TEXT,
        result_count INTEGER NOT NULL DEFAULT 0,
        outcome TEXT NOT NULL CHECK (outcome IN ('ok', 'reddedildi', 'hata'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_access_ts ON access_log(ts)",
    "CREATE INDEX IF NOT EXISTS idx_access_app ON access_log(app_id, ts)",
]


def connect_erisim(root: Path | str) -> sqlite3.Connection:
    """erisim.db'ye yazılabilir bağlantı (WAL, busy_timeout 5000 ms)."""
    conn = sqlite3.connect(
        Path(root) / "erisim.db", timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None
    )
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_erisim_db(root: Path | str) -> Path:
    """erisim.db yoksa boş şemayı oluşturur (varsa dokunmaz). Dosya yolunu döner."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    conn = connect_erisim(root)
    try:
        if conn.execute("PRAGMA user_version").fetchone()[0] < ERISIM_SCHEMA_VERSION:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for stmt in _DDL:
                    conn.execute(stmt)
                conn.execute(f"PRAGMA user_version = {ERISIM_SCHEMA_VERSION}")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()
    return root / "erisim.db"
