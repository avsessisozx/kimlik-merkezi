"""Ortak türler: sözleşme (INTERFACES §4), biçim raporu, arşiv soyutlaması.

Arşiv = zip dosyası, açılmış klasör ya da tek dosya. Zip içinden diske açmadan,
akışla okunur (zipfile.ZipFile.open). Hiçbir yerde girdi dosyasına yazılmaz.
"""
from __future__ import annotations

import codecs
import csv
import hashlib
import io
import os
import re
import unicodedata
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Protocol

from kimlikcore import EventIn, FormatError

CHUNK = 1024 * 1024
PEEK_BYTES = 8192

# Çok büyük CSV alanları (uzun gönderi/yorum metni) için; varsayılan 128 KiB yetmez.
csv.field_size_limit(32 * 1024 * 1024)


# --------------------------------------------------------------------------- sonuç türleri
@dataclass(frozen=True, slots=True)
class DetectResult:
    matches: bool
    confidence: float  # 0..1
    reason: str


@dataclass(slots=True)
class FormatReport:
    """Biçim denetim raporu. İçerik YOK: yalnız dosya ve alan adları, sayılar."""

    importer: str
    ok: bool
    found_files: list[str] = field(default_factory=list)  # işlenecek dosyalar (arşiv içi yol)
    missing: list[str] = field(default_factory=list)
    unexpected_fields: list[str] = field(default_factory=list)  # "dosya: alan" biçiminde
    unsupported: list[str] = field(default_factory=list)  # tanındı ama bu sürümde işlenmiyor
    notes: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        """Kopyalanabilir düz metin (kural 4.6). Kayıt içeriği taşımaz."""
        L = [f"Biçim raporu: {self.importer}", f"Sonuç: {'UYGUN' if self.ok else 'UYGUN DEĞİL'}"]

        def block(title: str, items: list[str]) -> None:
            L.append(f"{title} ({len(items)}):")
            L.extend(f"  - {i}" for i in items) if items else L.append("  (yok)")

        block("Bulunan dosyalar", self.found_files)
        block("Eksik / beklenen ama bulunamayan", self.missing)
        block("Beklenmeyen alanlar", self.unexpected_fields)
        block("Tanındı ama bu sürümde desteklenmiyor (atlandı)", self.unsupported)
        block("Notlar", self.notes)
        return "\n".join(L)


class ImportFormatError(FormatError):
    """Biçim uygun değil; `report` kopyalanabilir ayrıntıyı taşır, iletisi de odur."""

    def __init__(self, report: FormatReport):
        super().__init__(
            "Bu dosya beklenen biçimde değil.\n" + report.to_text()
        )
        self.report = report


class Importer(Protocol):
    name: str
    version: str

    def detect(self, path: Path) -> DetectResult: ...
    def verify_format(self, path: Path) -> FormatReport: ...
    def parse(self, path: Path) -> Iterator[EventIn]: ...

    # Çalıştırıcının kullandığı isteğe bağlı ek yöntemler (bkz. run.py):
    def input_files(self, path: Path) -> list[Origin]: ...
    def skipped_counts(self) -> dict[str, int]: ...


# --------------------------------------------------------------------------- arşiv
@dataclass(frozen=True, slots=True)
class Origin:
    """Diskteki fiziksel dosya (zip ya da gevşek dosya) ve ham arşivde kullanılacak adı."""

    path: Path
    label: str  # kök girdiye göre '/' ayraçlı göreli ad (klasör girdisinde yol düzleştirilir)
    is_zip: bool


@dataclass(slots=True)
class Entry:
    """Arşivdeki bir dosya. `open()` akışla ikili okuyucu verir."""

    name: str  # arşiv içi yol, '/' ayraçlı, NFC normalleştirilmiş
    size: int
    mtime: datetime  # UTC; zip girdisinin ya da dosyanın değiştirilme zamanı
    origin: Origin
    _zip_name: str | None = None  # zip içindeki özgün ad

    @property
    def basename(self) -> str:
        return self.name.rsplit("/", 1)[-1]

    def open(self) -> IO[bytes]:
        if self._zip_name is not None:
            return _ZipMember(self.origin.path, self._zip_name)
        return open(self.origin.path, "rb")


class _ZipMember(io.RawIOBase):
    """Zip üyesini akışla okur; kapanınca zip'i de kapatır. Diske açmaz."""

    def __init__(self, zip_path: Path, member: str):
        self._zf = zipfile.ZipFile(zip_path)
        try:
            self._f = self._zf.open(member)
        except Exception:
            self._zf.close()
            raise

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        data = self._f.read(len(b))
        n = len(data)
        b[:n] = data
        return n

    def read(self, size: int = -1) -> bytes:
        return self._f.read(size)

    def close(self) -> None:
        try:
            self._f.close()
            self._zf.close()
        finally:
            super().close()


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s.replace("\\", "/"))


def _utc_from_ts(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=UTC)


class Archive:
    """Girdi yolunu girdilere (Entry) açar: zip, klasör (içinde zip parçaları da olabilir) ya da dosya."""

    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.exists():
            raise FormatError(f"Girdi yok: {self.path}")
        self.entries: list[Entry] = []
        self.bad_zips: list[str] = []
        if self.path.is_dir():
            self._scan_dir()
        elif zipfile.is_zipfile(self.path):
            self._scan_zip(Origin(self.path, self.path.name, True), prefix="")
        else:
            st = self.path.stat()
            name = _nfc(self.path.name)
            self.entries.append(
                Entry(name, st.st_size, _utc_from_ts(st.st_mtime), Origin(self.path, name, False))
            )

    def _scan_zip(self, origin: Origin, prefix: str) -> None:
        try:
            with zipfile.ZipFile(origin.path) as zf:
                for zi in zf.infolist():
                    if zi.is_dir():
                        continue
                    name = _nfc(prefix + zi.filename)
                    try:
                        mt = datetime(*zi.date_time, tzinfo=UTC)
                        if mt.year < 1990:
                            raise ValueError
                    except ValueError:
                        mt = _utc_from_ts(origin.path.stat().st_mtime)
                    self.entries.append(Entry(name, zi.file_size, mt, origin, zi.filename))
        except zipfile.BadZipFile:
            self.bad_zips.append(origin.label)

    def _scan_dir(self) -> None:
        root = self.path
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for fn in sorted(filenames):
                p = Path(dirpath) / fn
                if p.is_symlink() and not p.exists():
                    continue
                rel = _nfc(p.relative_to(root).as_posix())
                if fn.lower().endswith(".zip") and zipfile.is_zipfile(p):
                    self._scan_zip(Origin(p, rel, True), prefix="")
                    continue
                st = p.stat()
                self.entries.append(
                    Entry(rel, st.st_size, _utc_from_ts(st.st_mtime), Origin(p, rel, False))
                )


_ARCHIVE_CACHE: dict[str, Archive] = {}


def open_archive(path: Path) -> Archive:
    """Aynı çalıştırma içinde (tanıma sırasında birden çok içe aktarıcı) arşiv listesi bir kez çıkarılır.
    Önbellek `run()` başında temizlenir."""
    key = str(Path(path).resolve())
    if key not in _ARCHIVE_CACHE:
        if len(_ARCHIVE_CACHE) >= 2:
            _ARCHIVE_CACHE.clear()
        _ARCHIVE_CACHE[key] = Archive(Path(path))
    return _ARCHIVE_CACHE[key]


def clear_archive_cache() -> None:
    _ARCHIVE_CACHE.clear()


# --------------------------------------------------------------------------- yardımcılar
def strip_bom(f: IO[bytes]) -> IO[bytes]:
    """UTF-8 BOM varsa atlar; akışı CESU-8 (ayrı kodlanmış vekil yarımları) onarımıyla sarar.

    Bazı dışa aktarmalar emojiyi UTF-16 vekil yarımları olarak ayrı ayrı UTF-8'e kodlar (CESU-8);
    katı UTF-8 çözücü bunda patlar. Burada yarımlar birleştirilir, eşleşmeyen yarım U+FFFD olur.
    Geçersiz UTF-8 baytları (ör. latin-1 dosya) yine UnicodeDecodeError verir: sessizce bozulmaz."""
    head = f.read(3)
    return _Utf8Repair(f, b"" if head == b"\xef\xbb\xbf" else head)


class _Utf8Repair(io.RawIOBase):
    def __init__(self, f: IO[bytes], head: bytes = b""):
        self._f = f
        self._pending = head
        self._dec = codecs.getincrementaldecoder("utf-8")("surrogatepass")
        self._carry = ""  # parça sonundaki yüksek vekil yarım
        self._out = b""
        self._pos = 0
        self._eof = False

    def readable(self) -> bool:
        return True

    def _fill(self) -> None:
        chunk, self._pending = self._pending, b""
        if not chunk:
            chunk = self._f.read(256 * 1024)
        final = not chunk
        s = self._carry + self._dec.decode(chunk, final)
        self._carry = ""
        if not s.isascii():
            if not final and s and "\ud800" <= s[-1] <= "\udbff":
                self._carry, s = s[-1], s[:-1]
            try:
                s.encode("utf-8")
            except UnicodeEncodeError:
                s = s.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")
        if final:
            self._eof = True
        self._out = self._out[self._pos:] + s.encode("utf-8")
        self._pos = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            while not self._eof:
                self._fill()
            data, self._out, self._pos = self._out[self._pos:], b"", 0
            return data
        while len(self._out) - self._pos < size and not self._eof:
            self._fill()
        data = self._out[self._pos:self._pos + size]
        self._pos += len(data)
        return data

    def readinto(self, b) -> int:
        d = self.read(len(b))
        b[: len(d)] = d
        return len(d)

    def close(self) -> None:
        try:
            self._f.close()
        finally:
            super().close()


def peek(entry: Entry, n: int = PEEK_BYTES) -> bytes:
    with entry.open() as f:
        data = f.read(n)
    return data[3:] if data.startswith(b"\xef\xbb\xbf") else data


def iso_utc(value) -> str | None:
    """ISO-8601 metni ya da datetime'ı `YYYY-MM-DDTHH:MM:SSZ` yapar; çözülemezse None."""
    try:
        if isinstance(value, datetime):
            dt = value
        else:
            txt = re.sub(r"\[[^\]]*\]$", "", str(value).strip())  # Java ZonedDateTime eki: ...Z[UTC]
            dt = datetime.fromisoformat(txt.replace(" UTC", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OverflowError, TypeError):
        return None


def stable_key(prefix: str, *parts: object) -> str:
    """Kararlı olay anahtarı: dosya yoluna/kaynağa bağlı değil (yeniden indirilen arşivle çakışır)."""
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8", "replace"))
        h.update(b"\x1f")
    return f"{prefix}:{h.hexdigest()[:40]}"


_COORD_RES = (
    re.compile(r"@-?\d{1,3}\.\d+,-?\d{1,3}\.\d+"),
    re.compile(r"!3d-?\d{1,3}\.\d+!4d-?\d{1,3}\.\d+"),
    re.compile(r"[?&](?:q|ll|center|query|daddr|saddr)=-?\d{1,3}\.\d+(?:,|%2C)-?\d{1,3}\.\d+"),
)


def has_coordinates(url: str | None) -> bool:
    return bool(url) and any(r.search(url) for r in _COORD_RES)


def csv_rows(entry: Entry) -> Iterator[dict[str, str]]:
    """CSV'yi satır satır okur (UTF-8, BOM'lu olabilir)."""
    with entry.open() as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        yield from csv.DictReader(text)


def csv_header(entry: Entry) -> list[str] | None:
    try:
        with entry.open() as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            row = next(csv.reader(text), None)
            return [c.strip() for c in row] if row else None
    except (UnicodeDecodeError, csv.Error, OSError):
        return None


ProgressFn = Callable[[str, int], None]


# --------------------------------------------------------------------------- ortak iskelet
def fix_mojibake(s: str) -> str:
    """Meta'nın bilinen sorunu: UTF-8 baytları latin-1 sanılıp \\uXXXX kaçışlanmış. Düzeltilebiliyorsa
    düzeltir, değilse metni olduğu gibi bırakır (gerçek Türkçe/Unicode metne dokunmaz)."""
    if not s or s.isascii() or max(s) > "ÿ":
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def fix_tree(o):
    if isinstance(o, str):
        return fix_mojibake(o)
    if isinstance(o, list):
        return [fix_tree(x) for x in o]
    if isinstance(o, dict):
        return {fix_mojibake(k): fix_tree(v) for k, v in o.items()}
    return o


def epoch_to_iso(v) -> str | None:
    """Saniye ya da milisaniye cinsinden Unix zamanı -> ISO UTC; olmazsa None."""
    try:
        x = float(v)
        if x > 1e11:  # milisaniye
            x /= 1000.0
        if x < 0 or x > 4e9:
            return None
        return datetime.fromtimestamp(x, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


class ScanImporter:
    """Alt sınıflar `_do_scan(arc)` ile tarama sonucunu üretir; sonuç yola göre önbelleğe alınır."""

    name = ""
    version = "0.1.0"

    def __init__(self) -> None:
        self._cache: dict[str, tuple[Archive, object]] = {}
        self._skipped: dict[str, int] = {}

    def _skip(self, why: str, n: int = 1) -> None:
        self._skipped[why] = self._skipped.get(why, 0) + n

    def skipped_counts(self) -> dict[str, int]:
        return dict(self._skipped)

    def _scan(self, path: Path):
        key = str(Path(path).resolve())
        if key not in self._cache:
            arc = open_archive(Path(path))
            self._cache = {key: (arc, self._do_scan(arc))}
        return self._cache[key]

    def _do_scan(self, arc: Archive):  # pragma: no cover - alt sınıf doldurur
        raise NotImplementedError

    def close(self) -> None:
        self._cache.clear()
