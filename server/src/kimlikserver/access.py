"""Anahtarlar, izinler, erişim kaydı (INTERFACES §6).

- `KeyManager` (yazan Hub): anahtar üretme/iptal, kategori izni verme/kaldırma.
- `Authorizer` (salt okunur Hub yeter): anahtarı doğrular, izinleri çözer. Önbellek YOK;
  her çağrıda veritabanından yeniden okunur.
- `AccessLog`: `erisim.db`'ye ekleme. Her çağrıda yeni bağlantı (çok süreçli yazım için
  `kimlikcore.connect_erisim`: WAL + busy_timeout 5000 ms). Yazılamazsa `AccessLogError`.
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kimlikcore import Category, FormatError, Hub, KimlikError, NotFoundError, PermissionDenied
from kimlikcore import connect_erisim, norm_ts

from ._db import Clock, iso, utc_now

KEY_PREFIX = "kim_"


class SensitiveConfirmationRequired(KimlikError):
    """Hassas kategori (eposta/mesaj/konum) ayrı onay işareti olmadan açılamaz."""


class AccessLogError(KimlikError):
    """Erişim kaydı (erisim.db) yazılamadı; sorgu reddedilmelidir."""


def hash_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AppIdentity:
    app_id: str
    name: str


@dataclass(frozen=True, slots=True)
class Grant:
    app_id: str
    category: str
    granted_at: str
    expires_at: str | None
    confirmed_sensitive: bool


def _check_category(category: str) -> str:
    if category not in Category.ALL:
        raise FormatError(f"Bilinmeyen kategori: {category!r}")
    return category


class KeyManager:
    """Yazan Hub ile anahtar ve izin yönetimi (Windows uygulaması ya da yönetim komutu çağırır)."""

    def __init__(self, hub: Hub, *, clock: Clock = utc_now):
        self.hub = hub
        self._clock = clock

    def create_key(self, name: str) -> tuple[str, str]:
        """Yeni anahtar üretir: (app_id, düz_anahtar). Düz anahtar yalnız burada döner,
        veritabanına yalnızca SHA-256 hash'i yazılır."""
        name = (name or "").strip()
        if not name:
            raise FormatError("Uygulama adı boş olamaz.")
        plain = KEY_PREFIX + secrets.token_hex(32)  # 32 bayt rastgele
        app_id = str(uuid.uuid4())
        with self.hub.transaction() as c:
            c.execute("INSERT INTO app_keys(app_id, name, key_hash, created, revoked) "
                      "VALUES (?, ?, ?, ?, 0)", (app_id, name, hash_key(plain), iso(self._clock())))
        return app_id, plain

    def revoke_key(self, app_id: str) -> None:
        with self.hub.transaction() as c:
            cur = c.execute("UPDATE app_keys SET revoked = 1 WHERE app_id = ?", (app_id,))
            if cur.rowcount == 0:
                raise NotFoundError(f"Uygulama yok: {app_id}")

    def list_keys(self) -> list[tuple[str, str, str, bool]]:
        """(app_id, ad, oluşturulma, iptal_edildi). Anahtarın kendisi/hash'i dönmez."""
        return [(r[0], r[1], r[2], bool(r[3])) for r in self.hub.query(
            "SELECT app_id, name, created, revoked FROM app_keys ORDER BY created, app_id")]

    def grant(self, app_id: str, category: str, *, expires_at: str | datetime | None = None,
              confirmed_sensitive: bool = False) -> None:
        """Tek kategori izni (varsa günceller). Hassas kategori için `confirmed_sensitive=True`
        (ikinci onay) zorunludur. `expires_at` verilirse izin o ana kadar geçerlidir."""
        _check_category(category)
        sensitive = category in Category.SENSITIVE
        if sensitive and not confirmed_sensitive:
            raise SensitiveConfirmationRequired(
                f"'{category}' hassas bir kategoridir; ayrı onay olmadan açılamaz.")
        exp = None if expires_at is None else norm_ts(expires_at, assume_utc=True)
        now = iso(self._clock())
        with self.hub.transaction() as c:
            row = c.execute("SELECT revoked FROM app_keys WHERE app_id = ?", (app_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"Uygulama yok: {app_id}")
            if row[0]:
                raise FormatError("İptal edilmiş anahtara izin verilemez.")
            c.execute(
                "INSERT INTO permissions(app_id, category, granted_at, expires_at, "
                "confirmed_sensitive) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(app_id, category) DO UPDATE SET granted_at = excluded.granted_at, "
                "expires_at = excluded.expires_at, confirmed_sensitive = excluded.confirmed_sensitive",
                (app_id, category, now, exp, 1 if sensitive else 0))

    def grant_all_non_sensitive(self, app_id: str, *,
                                expires_at: str | datetime | None = None) -> list[str]:
        """Toplu açma ("hepsini aç"): YALNIZ hassas olmayan kategoriler. Hassaslar dahil değildir;
        onlar tek tek `grant(..., confirmed_sensitive=True)` ile açılır."""
        cats = sorted(Category.ALL - Category.SENSITIVE)
        for cat in cats:
            self.grant(app_id, cat, expires_at=expires_at)
        return cats

    def revoke_grant(self, app_id: str, category: str) -> None:
        with self.hub.transaction() as c:
            c.execute("DELETE FROM permissions WHERE app_id = ? AND category = ?",
                      (app_id, category))

    def list_grants(self, app_id: str | None = None) -> list[Grant]:
        sql = "SELECT app_id, category, granted_at, expires_at, confirmed_sensitive FROM permissions"
        args: tuple = ()
        if app_id:
            sql += " WHERE app_id = ?"
            args = (app_id,)
        return [Grant(r[0], r[1], r[2], r[3], bool(r[4]))
                for r in self.hub.query(sql + " ORDER BY app_id, category", args)]


class Authorizer:
    """Her çağrıda anahtar + izin kontrolü (önbelleksiz)."""

    def __init__(self, hub: Hub, *, clock: Clock = utc_now):
        self.hub = hub
        self._clock = clock

    def authenticate(self, plain_key: str | None) -> AppIdentity:
        if not plain_key or not plain_key.startswith(KEY_PREFIX):
            raise PermissionDenied("Anahtar yok ya da geçersiz.")
        r = self.hub.query_one("SELECT app_id, name, revoked FROM app_keys WHERE key_hash = ?",
                               (hash_key(plain_key),))
        if r is None or r[2]:
            raise PermissionDenied("Anahtar yok, geçersiz ya da iptal edilmiş.")
        return AppIdentity(r[0], r[1])

    def allowed_categories(self, app_id: str) -> dict[str, str | None]:
        """İzinli ve süresi dolmamış kategoriler -> bitiş zamanı (süresizse None).
        Hassas kategori yalnız `confirmed_sensitive=1` ise sayılır."""
        now = iso(self._clock())
        out: dict[str, str | None] = {}
        rows = self.hub.query("SELECT category, expires_at, confirmed_sensitive FROM permissions "
                              "WHERE app_id = ?", (app_id,))
        for cat, exp, conf in rows:
            if cat not in Category.ALL:
                continue
            if exp is not None and exp <= now:
                continue
            if cat in Category.SENSITIVE and conf != 1:
                continue
            out[cat] = exp
        return out


class AccessLog:
    """`erisim.db` / `access_log`. Yazma başarısızsa `AccessLogError`."""

    def __init__(self, root: Path | str, *, clock: Clock = utc_now,
                 connect: Callable[[Path | str], sqlite3.Connection] = connect_erisim):
        self.root = Path(root)
        self._clock = clock
        self._connect = connect

    def record(self, app_id: str, tool: str, category: str | None, result_count: int,
               outcome: str) -> None:
        try:
            conn = self._connect(self.root)
            try:
                conn.execute(
                    "INSERT INTO access_log(ts, app_id, tool, category, result_count, outcome) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (iso(self._clock()), app_id, tool, category, int(result_count), outcome))
            finally:
                conn.close()
        except (sqlite3.Error, OSError) as e:
            raise AccessLogError("Erişim kaydı yazılamadı.") from e

    def read_all(self) -> list[tuple]:
        """Yönetim/test için: (ts, app_id, tool, category, result_count, outcome)."""
        conn = self._connect(self.root)
        try:
            return conn.execute("SELECT ts, app_id, tool, category, result_count, outcome "
                                "FROM access_log ORDER BY id").fetchall()
        finally:
            conn.close()


def categories_label(cats: Iterable[str]) -> str | None:
    """`access_log.category` için: kategorilerin virgülle birleşimi (boşsa None)."""
    cs = sorted(set(cats))
    return ",".join(cs) if cs else None
