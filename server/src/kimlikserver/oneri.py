"""Persona öneri kuyruğu (`oneri.db`) ve onay işlemleri.

Yapay zekâ (MCP `persona_oner`) YALNIZ bu dosyaya öneri yazar; `facts` tablosuna dokunamaz.
Kullanıcı onaylayınca (Windows uygulaması `OneriYonetici` çağırır) öneri `facts`'e
`beyan_edilen` olarak düşer. Onaylanmamış öneri hiçbir çıktıda (persona_getir, kimlik kartı)
görünmez, çünkü o çıktılar yalnız `facts` okur.

`oneri.db` ayrı bir SQLite dosyasıdır (WAL, busy_timeout 5000 ms), `erisim.db` gibi: MCP süreçleri
ana veritabanına yazamaz. Dosya ilk yazımda oluşturulur.

Bastırma: ifade; Türkçe katlama + noktalama/boşluk normalleşmesinden sonra (kategoriyle birlikte)
SHA-256 ile özetlenir. Aynı özetli bir öneri kuyrukta bekliyorsa, daha önce onaylandı/düzeltildi/
reddedildiyse ya da `bastirilan`daysa ("hiç doğru değil") yeniden kuyruğa girmez. Sınır: yalnız
normalleşmiş AYNI ifade yakalanır; anlamca benzer ama farklı sözcüklü ifade yakalanmaz.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kimlikcore import FormatError, Hub, KimlikError, NotFoundError
from kimlikcore.turkish import tokens

from ._db import Clock, iso, utc_now
from .persona import FACT_CATEGORIES, MAX_STATEMENT, Persona

ONERI_DB = "oneri.db"
BUSY_TIMEOUT_MS = 5000
ONERI_SCHEMA_VERSION = 1
MAX_BEKLEYEN = 500          # kuyruk dolarsa yeni öneri alınmaz (taşırma/spam koruması)
MAX_ONERI_CAGRI = 20        # bir çağrıdaki öneri sayısı
MAX_KANIT = 20              # bir önerideki kanıt sayısı
DURUMLAR = ("bekliyor", "onaylandi", "duzeltildi", "reddedildi", "hic_dogru_degil")

_DDL = [
    """CREATE TABLE IF NOT EXISTS oneriler (
        oneri_id TEXT PRIMARY KEY,
        ts TEXT NOT NULL,
        app_id TEXT NOT NULL,
        statement TEXT NOT NULL,
        category TEXT NOT NULL,
        fact_key TEXT,
        kanit_event_ids TEXT NOT NULL,
        guven REAL NOT NULL CHECK (guven >= 0 AND guven <= 1),
        durum TEXT NOT NULL DEFAULT 'bekliyor' CHECK (
            durum IN ('bekliyor', 'onaylandi', 'duzeltildi', 'reddedildi', 'hic_dogru_degil')),
        ifade_hash TEXT NOT NULL,
        karar_ts TEXT,
        duzeltilmis_ifade TEXT,
        fact_id TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_oneri_durum ON oneriler(durum, ts)",
    "CREATE INDEX IF NOT EXISTS idx_oneri_hash ON oneriler(ifade_hash)",
    """CREATE TABLE IF NOT EXISTS bastirilan (
        ifade_hash TEXT PRIMARY KEY,
        ts TEXT NOT NULL,
        category TEXT
    )""",
]


class OneriYazilamadi(KimlikError):
    """oneri.db yazılamadı."""


def ifade_ozeti(statement: str, category: str) -> str:
    norm = " ".join(tokens(statement))  # Türkçe katlama, noktalama atılır, boşluklar tekleşir
    return hashlib.sha256(f"{category}\n{norm}".encode("utf-8")).hexdigest()


def connect_oneri(root: Path | str) -> sqlite3.Connection:
    """oneri.db'ye yazılabilir bağlantı; şema yoksa kurar (idempotent, çok süreçli güvenli)."""
    conn = sqlite3.connect(Path(root) / ONERI_DB, timeout=BUSY_TIMEOUT_MS / 1000,
                           isolation_level=None)
    try:
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        if conn.execute("PRAGMA user_version").fetchone()[0] < ONERI_SCHEMA_VERSION:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for stmt in _DDL:
                    conn.execute(stmt)
                conn.execute(f"PRAGMA user_version = {ONERI_SCHEMA_VERSION}")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
    except BaseException:
        conn.close()
        raise
    return conn


def _tx(conn: sqlite3.Connection):
    from contextlib import contextmanager

    @contextmanager
    def cm():
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
    return cm()


@dataclass(frozen=True, slots=True)
class Oneri:
    oneri_id: str
    ts: str
    app_id: str
    statement: str
    category: str
    fact_key: str | None
    kanit_event_ids: list[str]
    guven: float
    durum: str
    karar_ts: str | None
    duzeltilmis_ifade: str | None
    fact_id: str | None


_COLS = ("oneri_id, ts, app_id, statement, category, fact_key, kanit_event_ids, guven, durum, "
         "karar_ts, duzeltilmis_ifade, fact_id")


def _oneri(r: tuple) -> Oneri:
    return Oneri(r[0], r[1], r[2], r[3], r[4], r[5], json.loads(r[6]), r[7], r[8], r[9], r[10], r[11])


def dogrula_onerme(o: Any) -> dict[str, Any]:
    """Tek öneriyi doğrular/normalleştirir: {ifade, kategori, kanit, guven, anahtar}."""
    if not isinstance(o, dict):
        raise FormatError("Her öneri nesne olmalı.")
    ifade = o.get("ifade")
    if not isinstance(ifade, str) or not ifade.strip():
        raise FormatError("Önerinin 'ifade' alanı boş olamaz.")
    ifade = ifade.strip()
    if len(ifade) > MAX_STATEMENT:
        raise FormatError(f"'ifade' en çok {MAX_STATEMENT} karakter olabilir.")
    kat = o.get("kategori")
    if kat not in FACT_CATEGORIES:
        raise FormatError("Geçersiz persona kategorisi: " + ", ".join(FACT_CATEGORIES)
                          + " değerlerinden biri olmalı.")
    kanit = o.get("kanit")
    if not isinstance(kanit, list) or not kanit or not all(isinstance(k, str) and k for k in kanit):
        raise FormatError("'kanit' en az bir olay kimliği (metin) içeren liste olmalı.")
    if len(kanit) > MAX_KANIT:
        raise FormatError(f"'kanit' en çok {MAX_KANIT} olay kimliği içerebilir.")
    guven = o.get("guven")
    if isinstance(guven, bool) or not isinstance(guven, (int, float)) or not 0 <= guven <= 1:
        raise FormatError("'guven' 0 ile 1 arasında sayı olmalı.")
    anahtar = o.get("anahtar")
    if anahtar is not None and not isinstance(anahtar, str):
        raise FormatError("'anahtar' metin olmalı.")
    return {"ifade": ifade, "kategori": kat, "kanit": list(dict.fromkeys(kanit)),
            "guven": float(guven), "anahtar": (anahtar or "").strip() or None}


class OneriKuyrugu:
    """oneri.db okuma/ekleme (MCP süreçleri ve Windows uygulaması)."""

    def __init__(self, root: Path | str, *, clock: Clock = utc_now,
                 connect: Callable[[Path | str], sqlite3.Connection] = connect_oneri):
        self.root = Path(root)
        self._clock = clock
        self._connect = connect

    # ---- salt okuma (dosya yoksa oluşturmaz)
    def _read_conn(self) -> sqlite3.Connection | None:
        p = self.root / ONERI_DB
        if not p.is_file():
            return None
        conn = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True,
                               timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        return conn

    def _durum_kontrol(self, conn: sqlite3.Connection | None, h: str) -> str | None:
        """None: eklenebilir; aksi halde neden kodu."""
        if conn is None:
            return None
        if conn.execute("SELECT 1 FROM bastirilan WHERE ifade_hash = ?", (h,)).fetchone():
            return "bastirilmis"
        r = conn.execute("SELECT durum FROM oneriler WHERE ifade_hash = ? ORDER BY ts DESC LIMIT 1",
                         (h,)).fetchone()
        if r is None:
            return None
        return {"bekliyor": "zaten_kuyrukta", "onaylandi": "zaten_onayli",
                "duzeltildi": "zaten_onayli", "reddedildi": "reddedilmis",
                "hic_dogru_degil": "bastirilmis"}[r[0]]

    def on_kontrol(self, onermeler: list[dict[str, Any]]) -> tuple[list[str | None], int]:
        """Her öneri için (eklenebilir ise None | neden kodu) ve kuyruktaki bekleyen sayısı."""
        conn = self._read_conn()
        try:
            sonuc = []
            gorulen: set[str] = set()
            for o in onermeler:
                h = ifade_ozeti(o["ifade"], o["kategori"])
                s = "zaten_kuyrukta" if h in gorulen else self._durum_kontrol(conn, h)
                gorulen.add(h)
                sonuc.append(s)
            bekleyen = 0 if conn is None else conn.execute(
                "SELECT COUNT(*) FROM oneriler WHERE durum = 'bekliyor'").fetchone()[0]
            return sonuc, bekleyen
        finally:
            if conn is not None:
                conn.close()

    # ---- yazma
    def ekle(self, app_id: str, onermeler: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Doğrulanmış önerileri (dogrula_onerme çıktısı) kuyruğa ekler. Her biri için
        {"sonuc": "eklendi"|<neden kodu>, "oneri_id"?}. Tek işlemde; hata olursa hiçbiri eklenmez.
        Bastırma/yineleme kontrolü işlem İÇİNDE yeniden yapılır (yarış güvenli)."""
        now = iso(self._clock())
        try:
            conn = self._connect(self.root)
            try:
                with _tx(conn):
                    bekleyen = conn.execute(
                        "SELECT COUNT(*) FROM oneriler WHERE durum = 'bekliyor'").fetchone()[0]
                    out = []
                    for o in onermeler:
                        h = ifade_ozeti(o["ifade"], o["kategori"])
                        neden = self._durum_kontrol(conn, h)
                        if neden is None and bekleyen >= MAX_BEKLEYEN:
                            neden = "kuyruk_dolu"
                        if neden is not None:
                            out.append({"sonuc": neden})
                            continue
                        oid = str(uuid.uuid4())
                        conn.execute(
                            "INSERT INTO oneriler(oneri_id, ts, app_id, statement, category, "
                            "fact_key, kanit_event_ids, guven, durum, ifade_hash) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'bekliyor', ?)",
                            (oid, now, app_id, o["ifade"], o["kategori"], o["anahtar"],
                             json.dumps(o["kanit"]), o["guven"], h))
                        bekleyen += 1
                        out.append({"sonuc": "eklendi", "oneri_id": oid})
                    return out
            finally:
                conn.close()
        except (sqlite3.Error, OSError) as e:
            raise OneriYazilamadi("Öneri kuyruğu (oneri.db) yazılamadı.") from e

    def listele(self, durum: str | None = "bekliyor", *, limit: int = 500) -> list[Oneri]:
        conn = self._read_conn()
        if conn is None:
            return []
        try:
            sql = f"SELECT {_COLS} FROM oneriler"
            args: list[Any] = []
            if durum is not None:
                if durum not in DURUMLAR:
                    raise FormatError(f"Bilinmeyen durum: {durum}")
                sql += " WHERE durum = ?"
                args.append(durum)
            sql += " ORDER BY ts, oneri_id LIMIT ?"
            return [_oneri(r) for r in conn.execute(sql, [*args, int(limit)])]
        finally:
            conn.close()


class OneriYonetici:
    """Kullanıcı kararları (Windows uygulaması çağırır; yazan Hub gerekir)."""

    def __init__(self, hub: Hub, root: Path | str | None = None, *, clock: Clock = utc_now,
                 persona: Persona | None = None):
        self.hub = hub
        self.root = Path(root) if root is not None else hub.root
        self._clock = clock
        self.persona = persona or Persona(hub, clock=clock)
        self.kuyruk = OneriKuyrugu(self.root, clock=clock)

    def kuyruk_listele(self, durum: str | None = "bekliyor") -> list[Oneri]:
        return self.kuyruk.listele(durum)

    def _bekleyen(self, conn: sqlite3.Connection, oneri_id: str) -> Oneri:
        r = conn.execute(f"SELECT {_COLS} FROM oneriler WHERE oneri_id = ?", (oneri_id,)).fetchone()
        if r is None:
            raise NotFoundError(f"Öneri yok: {oneri_id}")
        o = _oneri(r)
        if o.durum != "bekliyor":
            raise FormatError(f"Öneri zaten karara bağlanmış ({o.durum}).")
        return o

    def _karar(self, oneri_id: str, durum: str, *, fact_id: str | None = None,
               duzeltilmis: str | None = None, bastir: bool = False) -> None:
        now = iso(self._clock())
        conn = connect_oneri(self.root)
        try:
            with _tx(conn):
                o = self._bekleyen(conn, oneri_id)
                conn.execute("UPDATE oneriler SET durum = ?, karar_ts = ?, fact_id = ?, "
                             "duzeltilmis_ifade = ? WHERE oneri_id = ?",
                             (durum, now, fact_id, duzeltilmis, oneri_id))
                if bastir:
                    conn.execute("INSERT OR IGNORE INTO bastirilan(ifade_hash, ts, category) "
                                 "VALUES (?, ?, ?)",
                                 (ifade_ozeti(o.statement, o.category), now, o.category))
        finally:
            conn.close()

    def _bekleyen_oku(self, oneri_id: str) -> Oneri:
        conn = connect_oneri(self.root)
        try:
            return self._bekleyen(conn, oneri_id)
        finally:
            conn.close()

    def onayla(self, oneri_id: str) -> str:
        """Öneriyi `facts`'e `beyan_edilen` olarak ekler (çelişki varsa mevcut çelişki
        yönetimi çalışır). fact_id döner. Önce fact yazılır; aynı metin yeniden eklenirse
        `add_fact` yineleme yapmaz, bu yüzden yarım kalan onay güvenle tekrarlanabilir."""
        o = self._bekleyen_oku(oneri_id)
        fid = self.persona.add_fact(o.statement, o.category, fact_key=o.fact_key)
        self._karar(oneri_id, "onaylandi", fact_id=fid)
        return fid

    def duzelt(self, oneri_id: str, yeni_ifade: str) -> str:
        """Kullanıcı ifadeyi düzeltir; düzeltilmiş metin `beyan_edilen` olarak eklenir."""
        o = self._bekleyen_oku(oneri_id)
        fid = self.persona.add_fact(yeni_ifade, o.category, fact_key=o.fact_key)
        self._karar(oneri_id, "duzeltildi", fact_id=fid, duzeltilmis=yeni_ifade.strip())
        return fid

    def reddet(self, oneri_id: str) -> None:
        self._karar(oneri_id, "reddedildi")

    def hic_dogru_degil(self, oneri_id: str) -> None:
        """Reddeder ve benzer (aynı normalleşmiş ifade) önerinin bir daha kuyruğa girmesini engeller."""
        self._karar(oneri_id, "hic_dogru_degil", bastir=True)

    def toplu_reddet(self, oneri_idleri: Iterable[str] | None = None) -> int:
        """Verilen (ya da `None`: tüm bekleyen) önerileri reddeder; sayıyı döner."""
        now = iso(self._clock())
        conn = connect_oneri(self.root)
        try:
            with _tx(conn):
                if oneri_idleri is None:
                    cur = conn.execute("UPDATE oneriler SET durum = 'reddedildi', karar_ts = ? "
                                       "WHERE durum = 'bekliyor'", (now,))
                    return cur.rowcount
                n = 0
                for oid in dict.fromkeys(oneri_idleri):
                    n += conn.execute("UPDATE oneriler SET durum = 'reddedildi', karar_ts = ? "
                                      "WHERE oneri_id = ? AND durum = 'bekliyor'",
                                      (now, oid)).rowcount
                return n
        finally:
            conn.close()
