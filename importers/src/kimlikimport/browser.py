"""Yerel tarayıcı geçmişi: Chrome / Edge / Brave (Chromium `History`) ve Firefox (`places.sqlite`).

Dosyanın KOPYASI alınır (yanındaki -wal/-shm/-journal ile birlikte) ve kopya salt okunur açılır;
orijinale hiç yazılmaz. Tarayıcı açıkken Windows dosyayı kilitleyebilir: kopya önce normal, olmazsa
(yalnız Windows) paylaşımlı açma ile denenir, o da olmazsa anlaşılır hata verilir ("tarayıcıyı kapatın").

Şema bilgisi: browserexport (MIT, purarue) kaynağı okundu: Chromium `urls`+`visits`, `visit_time` =
1601'den beri mikrosaniye; Firefox `moz_places`+`moz_historyvisits`, `visit_date` = Unix mikrosaniye.
Kod kopyalanmadı, bağımlılık yapılmadı (kendi küçük okuyucumuz). Windows profil yolları
(`%LOCALAPPDATA%\\Google\\Chrome\\User Data\\<Profil>\\History`, Edge: `Microsoft\\Edge`, Firefox:
`%APPDATA%\\Mozilla\\Firefox\\Profiles\\<profil>\\places.sqlite`) DOĞRULANMADI (hafıza + kısmi kaynak).
Chrome kayıtları Takeout'un Chrome kaydıyla aynı olay anahtarını üretir (aynı ziyaret tekrar sayılmaz).
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path

from kimlikcore import Category, EventIn, FormatError

from .base import DetectResult, FormatReport, Origin, ScanImporter, stable_key
from .common import chrome_visit_events

NAME = "browser_history"
WEBKIT_OFFSET_US = 11_644_473_600 * 1_000_000
SQLITE_MAGIC = b"SQLite format 3\x00"
_SIDE = ("-wal", "-shm", "-journal")
_CHROMIUM_NAMES = ("History",)
_TRANSITION = {0: "LINK", 1: "TYPED", 2: "AUTO_BOOKMARK", 3: "AUTO_SUBFRAME", 4: "MANUAL_SUBFRAME",
               5: "GENERATED", 6: "START_PAGE", 7: "FORM_SUBMIT", 8: "RELOAD", 9: "KEYWORD",
               10: "KEYWORD_GENERATED"}
_BATCH = 5000


def default_locations(env: Mapping[str, str] | None = None) -> list[Path]:
    """Windows'ta bilinen tarayıcı geçmiş dosyaları (var olanlar). `env` testte sahte verilebilir."""
    env = os.environ if env is None else env
    out: list[Path] = []
    local, roam = env.get("LOCALAPPDATA"), env.get("APPDATA")
    chromium = (("Google/Chrome", "chrome"), ("Microsoft/Edge", "edge"),
                ("BraveSoftware/Brave-Browser", "brave"), ("Chromium", "chromium"))
    if local:
        for sub, _ in chromium:
            root = Path(local) / sub / "User Data"
            if root.is_dir():
                for prof in sorted(root.iterdir()):
                    h = prof / "History"
                    if prof.is_dir() and h.is_file():
                        out.append(h)
    if roam:
        prof_root = Path(roam) / "Mozilla" / "Firefox" / "Profiles"
        if prof_root.is_dir():
            for prof in sorted(prof_root.iterdir()):
                p = prof / "places.sqlite"
                if p.is_file():
                    out.append(p)
    return out


def _is_sqlite(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            return f.read(16) == SQLITE_MAGIC
    except OSError:
        return False


def _win_open_shared(src: Path):
    """Windows: başka süreç açıkken okumak için tam paylaşımlı CreateFile (DOĞRULANMADI)."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    h = k32.CreateFileW(str(src), 0x80000000, 0x1 | 0x2 | 0x4, None, 3, 0x80, None)
    if h in (wintypes.HANDLE(-1).value, None, -1):
        raise PermissionError(ctypes.get_last_error())
    fd = msvcrt.open_osfhandle(h, os.O_RDONLY)
    return os.fdopen(fd, "rb")


def copy_snapshot(src: Path, dst: Path) -> None:
    """src -> dst (ve yan dosyaları). Kilitliyse anlaşılır FormatError."""
    for suffix in ("", *_SIDE):
        s = Path(str(src) + suffix)
        d = Path(str(dst) + suffix)
        if suffix and not s.exists():
            continue
        try:
            shutil.copyfile(s, d)
        except PermissionError:
            try:
                if os.name != "nt":
                    raise
                with _win_open_shared(s) as fi, open(d, "wb") as fo:
                    shutil.copyfileobj(fi, fo, 1024 * 1024)
            except (PermissionError, OSError, ImportError, AttributeError):
                if suffix:
                    continue  # yan dosya alınamadı: ana dosyayla devam
                raise FormatError(
                    f"{src.name}: dosya kilitli (tarayıcı açık olabilir). Tarayıcıyı tamamen kapatıp "
                    "yeniden deneyin."
                ) from None


def _browser_of(path: Path, kind: str) -> str:
    if kind == "firefox":
        return "firefox"
    p = "/".join(path.parts[-5:]).replace("\\", "/").lower()
    for hint, name in (("microsoft/edge", "edge"), ("brave", "brave"), ("opera", "opera"),
                       ("vivaldi", "vivaldi"), ("chromium", "chromium"), ("google/chrome", "chrome")):
        if hint in p:
            return name
    return "chrome"


class _Db:
    def __init__(self, orig: Path, snap: Path, kind: str, browser: str, profile: str):
        self.orig, self.snap, self.kind, self.browser, self.profile = orig, snap, kind, browser, profile


def _kind_of_db(snap: Path) -> tuple[str | None, str]:
    """('chrome'|'firefox'|None, neden). Yalnız tablo/sütun adlarına bakar."""
    try:
        con = sqlite3.connect(f"file:{snap}?mode=ro", uri=True)
    except sqlite3.Error as e:
        return None, f"SQLite açılamadı ({type(e).__name__})"
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        def cols(t):
            return {r[1] for r in con.execute(f"PRAGMA table_info({t})")}

        if {"urls", "visits"} <= tables:
            miss = ({"id", "url", "title"} - cols("urls")) | ({"url", "visit_time"} - cols("visits"))
            return ("chrome", "") if not miss else (None, "Chromium sütunları eksik: " + ", ".join(sorted(miss)))
        if {"moz_places", "moz_historyvisits"} <= tables:
            miss = ({"id", "url", "title"} - cols("moz_places")) | ({"place_id", "visit_date"} - cols("moz_historyvisits"))
            return ("firefox", "") if not miss else (None, "Firefox sütunları eksik: " + ", ".join(sorted(miss)))
        return None, "ne Chromium (urls/visits) ne Firefox (moz_places/moz_historyvisits) tabloları var"
    except sqlite3.Error as e:
        return None, f"şema okunamadı ({type(e).__name__})"
    finally:
        con.close()


class BrowserHistory(ScanImporter):
    name = NAME

    def __init__(self) -> None:
        super().__init__()
        self._tmp: tempfile.TemporaryDirectory | None = None
        self._dbs: dict[str, tuple[list[_Db], list[str], list[str]]] = {}

    def close(self) -> None:
        self._dbs.clear()
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None
        super().close()

    # ---- tarama: aday dosyaları bul, kopyala, türünü anla
    def _candidates(self, path: Path) -> list[Path]:
        if path.is_file():
            return [path] if _is_sqlite(path) else []
        found: list[Path] = []
        base = len(path.parts)
        for dp, dns, fns in os.walk(path):
            if len(Path(dp).parts) - base >= 4:
                dns[:] = []
            for fn in sorted(fns):
                if fn in _CHROMIUM_NAMES or fn == "places.sqlite":
                    p = Path(dp) / fn
                    if _is_sqlite(p):
                        found.append(p)
        return found

    def _prepare(self, path: Path):
        key = str(Path(path).resolve())
        if key in self._dbs:
            return self._dbs[key]
        path = Path(path)
        if not path.exists():
            raise FormatError(f"Girdi yok: {path}")
        if self._tmp is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="kimlikimport-tarayici-")
        dbs: list[_Db] = []
        problems: list[str] = []
        notes: list[str] = []
        for i, orig in enumerate(self._candidates(path)):
            snap = Path(self._tmp.name) / f"{i}_{orig.name}"
            copy_snapshot(orig, snap)
            kind, why = _kind_of_db(snap)
            if kind is None:
                problems.append(f"{orig.name}: {why}")
                continue
            browser = _browser_of(orig, kind)
            dbs.append(_Db(orig, snap, kind, browser, orig.parent.name))
            if any(Path(str(orig) + s).exists() for s in _SIDE):
                notes.append(f"{orig.name}: yan dosyalar (-wal/-journal) da kopyalandı")
        self._dbs = {key: (dbs, problems, notes)}
        return self._dbs[key]

    def detect(self, path: Path) -> DetectResult:
        try:
            dbs, problems, _ = self._prepare(Path(path))
        except FormatError as e:
            return DetectResult(False, 0.0, str(e))
        if dbs:
            return DetectResult(True, 0.9, "tarayıcı geçmişi: " + ", ".join(sorted({d.browser for d in dbs})))
        if problems:
            return DetectResult(True, 0.4, "SQLite var ama tarayıcı geçmişi şemasına uymuyor")
        return DetectResult(False, 0.0, "tarayıcı geçmiş veritabanı (History / places.sqlite) bulunamadı")

    def verify_format(self, path: Path) -> FormatReport:
        dbs, problems, notes = self._prepare(Path(path))
        rep = FormatReport(importer=NAME, ok=bool(dbs))
        for d in dbs:
            n = self._count(d)
            rep.found_files.append(f"{d.browser} ({d.kind}) profil '{d.profile}': {d.orig.name}, {n} ziyaret")
        rep.missing += problems
        if not dbs:
            rep.missing.append("History (Chromium) ya da places.sqlite (Firefox) dosyası bulunamadı")
        rep.notes += notes
        rep.notes.append("Dosyanın kopyası okunur; orijinale yazılmaz")
        return rep

    @staticmethod
    def _count(d: _Db) -> int:
        con = sqlite3.connect(f"file:{d.snap}?mode=ro", uri=True)
        try:
            t = "visits" if d.kind == "chrome" else "moz_historyvisits"
            return con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        finally:
            con.close()

    def input_files(self, path: Path) -> list[Origin]:
        dbs, _, _ = self._prepare(Path(path))
        return [Origin(d.snap, f"{d.browser}_{d.profile}_{d.orig.name}", False) for d in dbs]

    # ---- ayrıştırma
    def parse(self, path: Path) -> Iterator[EventIn]:
        dbs, _, _ = self._prepare(Path(path))
        for d in dbs:
            yield from (self._chrome(d) if d.kind == "chrome" else self._firefox(d))

    def _rows(self, d: _Db, sql: str):
        con = sqlite3.connect(f"file:{d.snap}?mode=ro", uri=True)
        con.text_factory = lambda b: b.decode("utf-8", "replace")
        try:
            cur = con.execute(sql)
            while True:
                rows = cur.fetchmany(_BATCH)
                if not rows:
                    return
                yield from rows
        except sqlite3.Error as e:
            raise FormatError(f"{d.orig.name}: veritabanı okunamadı ({type(e).__name__}).") from None
        finally:
            con.close()

    def _chrome(self, d: _Db) -> Iterator[EventIn]:
        kind = f"{d.browser}.ziyaret"
        keyb = "chrome" if d.browser == "chrome" else d.browser
        for vt, tr, url, title in self._rows(
            d, "SELECT v.visit_time, v.transition, u.url, u.title FROM visits v "
               "JOIN urls u ON v.url = u.id ORDER BY v.id"):
            if not isinstance(vt, int) or vt <= WEBKIT_OFFSET_US or not url:
                self._skip(f"{d.browser}: ziyaret zamanı/url geçersiz")
                continue
            unix_us = vt - WEBKIT_OFFSET_US
            try:
                ts = datetime.fromtimestamp(unix_us / 1_000_000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (OverflowError, OSError, ValueError):
                self._skip(f"{d.browser}: zaman aralık dışı")
                continue
            yield from chrome_visit_events(
                kind=kind, ts=ts, unix_usec=unix_us, url=url, title=title or "",
                transition=_TRANSITION.get((tr or 0) & 0xFF), key_browser=keyb)

    def _firefox(self, d: _Db) -> Iterator[EventIn]:
        from .base import has_coordinates  # yerel: döngüsel içe aktarmayı önler

        for vd, url, title in self._rows(
            d, "SELECT v.visit_date, p.url, p.title FROM moz_historyvisits v "
               "JOIN moz_places p ON v.place_id = p.id ORDER BY v.id"):
            if not isinstance(vd, int) or vd <= 0 or not url:
                self._skip("firefox: ziyaret zamanı/url geçersiz")
                continue
            try:
                ts = datetime.fromtimestamp(vd / 1_000_000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            except (OverflowError, OSError, ValueError):
                self._skip("firefox: zaman aralık dışı")
                continue
            title = title or ""
            key = stable_key("br", "firefox", vd, url)
            if has_coordinates(url):
                yield EventIn(ts=ts, kind="firefox.ziyaret", category=Category.TARAMA, event_key=key,
                              payload={"baslik": title, "url": None, "url_konum_ayrildi": True}, text=title)
                yield EventIn(ts=ts, kind="google.konum", category=Category.KONUM, event_key=key + ":konum",
                              payload={"kaynak": "firefox", "url": url, "baslik": title}, text=title)
            else:
                yield EventIn(ts=ts, kind="firefox.ziyaret", category=Category.TARAMA, event_key=key,
                              payload={"baslik": title, "url": url}, text=f"{title} {url}".strip())


def factory() -> BrowserHistory:
    return BrowserHistory()
