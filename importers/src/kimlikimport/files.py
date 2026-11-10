"""Bilgisayar dosyaları: kullanıcının seçtiği klasör taranır; dosyalar YERİNDE kalır (kopyalanmaz).

- Belgeler (PDF, DOCX, ODT, düz metin türleri): metin çıkarılır, `dosyalar` kategorisi. Metin katmanı
  olmayan (taranmış) PDF için OCR YOK: `metin = "yok"` işaretlenir.
- Fotoğraf / video: yalnız üst veri (`medya_meta`); GPS varsa AYRI `konum` olayı, ana olaya girmez.
  Fotoğraf: Pillow ile EXIF. Video: MP4/MOV `©xyz` atomu (varsa). Piksel/kare içeriği okunmaz.
- Diğer dosyalar: ad, boyut, tarih.
Kütüphaneler (lisanslar paket meta verisinden okundu): pypdf (BSD-3-Clause), python-docx (MIT),
Pillow (MIT-CMU/HPND). Hiçbiri AGPL değil.

Kaynak özeti (source_sha) dosya adı+boyut+tarih listesinin özetidir: klasör değişmediyse aynı kaynak.
Otomatik tanımada SEÇİLMEZ (her klasöre uyar); `ice-al --tur computer_files` ya da arayüzden seçilir.
"""
from __future__ import annotations

import hashlib
import os
import re
import struct
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from kimlikcore import Category, EventIn, FormatError

from .base import DetectResult, FormatReport, Origin, ScanImporter, stable_key

NAME = "computer_files"
MAX_TEXT_CHARS = 100_000
MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_DOCX_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_PLAIN_BYTES = 2 * 1024 * 1024
MOOV_MAX = 32 * 1024 * 1024

SKIP_DIRS = {"node_modules", "__pycache__", "$recycle.bin", "system volume information", ".git", ".svn"}
SKIP_FILES = {"thumbs.db", "desktop.ini", ".ds_store"}
PLAIN = {".txt", ".md", ".csv", ".tsv", ".log", ".json", ".xml", ".html", ".htm", ".ini", ".yaml", ".yml",
         ".py", ".js", ".ts", ".java", ".c", ".h", ".cpp", ".cs", ".go", ".rs", ".sh", ".bat", ".sql", ".tex"}
IMAGES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".gif", ".bmp", ".heic", ".heif"}
VIDEOS = {".mp4", ".mov", ".m4v", ".3gp", ".mkv", ".avi", ".webm", ".wmv"}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _walk(root: Path, on_error=None) -> Iterator[tuple[Path, str, os.stat_result]]:
    """(tam yol, kökten göreli '/' yol, stat) — gizli/atlanan klasörler dışarıda, sıralı."""
    if root.is_file():
        yield root, root.name, root.stat()
        return
    for dp, dns, fns in os.walk(root, followlinks=False, onerror=on_error):
        dns[:] = sorted(d for d in dns if not d.startswith(".") and d.lower() not in SKIP_DIRS)
        for fn in sorted(fns):
            if fn.startswith(("~$", ".")) or fn.lower() in SKIP_FILES:
                continue
            p = Path(dp) / fn
            try:
                if p.is_symlink():
                    continue
                st = p.stat()
            except OSError:
                if on_error:
                    on_error(None)
                continue
            yield p, p.relative_to(root).as_posix(), st


class _Scan:
    def __init__(self) -> None:
        self.files = self.size = 0
        self.by_class = {"belge": 0, "foto": 0, "video": 0, "diger": 0}
        self.unreadable = 0
        self.sha = ""


def _class_of(ext: str) -> str:
    if ext in IMAGES:
        return "foto"
    if ext in VIDEOS:
        return "video"
    if ext in PLAIN or ext in {".pdf", ".docx", ".odt"}:
        return "belge"
    return "diger"


# ----------------------------------------------------------------------- metin çıkarma
def extract_text(path: Path, ext: str, size: int) -> tuple[str, str, dict]:
    """(metin, durum, ek). durum: var | yok | hata | buyuk | sifreli | desteklenmiyor | bos"""
    try:
        if ext == ".pdf":
            if size > MAX_PDF_BYTES:
                return "", "buyuk", {}
            return _pdf(path)
        if ext == ".docx":
            if size > MAX_DOCX_BYTES:
                return "", "buyuk", {}
            return _docx(path)
        if ext == ".odt":
            return _odt(path)
        if ext in PLAIN:
            with open(path, "rb") as f:
                raw = f.read(MAX_PLAIN_BYTES)
            if b"\x00" in raw[:4096]:
                return "", "desteklenmiyor", {"neden": "ikili içerik"}
            t = raw.decode("utf-8", "replace")
            if ext in (".html", ".htm"):
                from .mbox import html_to_text
                t = html_to_text(t)
            t = t.strip()
            return (t[:MAX_TEXT_CHARS], "var", {}) if t else ("", "bos", {})
    except Exception as e:  # bozuk belge: içerik sızdırmadan sınıf adı
        return "", "hata", {"hata": type(e).__name__}
    return "", "desteklenmiyor", {}


def _pdf(path: Path):
    from pypdf import PdfReader

    r = PdfReader(str(path))
    if r.is_encrypted and not r.decrypt(""):
        return "", "sifreli", {}
    n = len(r.pages)
    parts: list[str] = []
    total = 0
    for i, page in enumerate(r.pages):
        if i >= MAX_PDF_PAGES or total >= MAX_TEXT_CHARS:
            break
        t = (page.extract_text() or "").strip()
        if t:
            parts.append(t)
            total += len(t)
    text = "\n".join(parts)[:MAX_TEXT_CHARS]
    return (text, "var", {"sayfa": n}) if text.strip() else ("", "yok", {"sayfa": n})


def _docx(path: Path):
    from docx import Document

    d = Document(str(path))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for row in t.rows:
            parts.append(" ".join(c.text for c in row.cells if c.text.strip()))
    text = "\n".join(x for x in parts if x.strip())[:MAX_TEXT_CHARS]
    return (text, "var", {}) if text.strip() else ("", "yok", {})


def _odt(path: Path):
    with zipfile.ZipFile(path) as z:
        info = z.getinfo("content.xml")
        if info.file_size > 50 * 1024 * 1024:
            return "", "buyuk", {}
        xml = z.read("content.xml").decode("utf-8", "replace")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()[:MAX_TEXT_CHARS]
    return (text, "var", {}) if text else ("", "yok", {})


# ----------------------------------------------------------------------- medya üst verisi
def _ratio(v) -> float:
    return float(v)


def _dms(vals, ref) -> float | None:
    try:
        d, m, s = (_ratio(x) for x in vals)
        deg = d + m / 60 + s / 3600
        return -deg if str(ref).upper() in ("S", "W") else deg
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def photo_meta(path: Path) -> tuple[dict, dict | None, str]:
    """(üst veri, gps|None, durum). GPS ana üst veriye KONMAZ."""
    try:
        from PIL import Image
    except ImportError:
        return {}, None, "desteklenmiyor"
    try:
        with Image.open(path) as im:
            meta: dict = {"genislik": im.width, "yukseklik": im.height, "bicim": im.format}
            ex = im.getexif()
            if ex.get(0x010F):
                meta["marka"] = str(ex[0x010F]).strip("\x00 ")
            if ex.get(0x0110):
                meta["model"] = str(ex[0x0110]).strip("\x00 ")
            try:
                sub = ex.get_ifd(0x8769)
                if sub.get(0x9003):
                    meta["cekim_zamani_yerel"] = str(sub[0x9003])
                gps_ifd = ex.get_ifd(0x8825)
            except Exception:
                gps_ifd = {}
            gps = None
            if gps_ifd and gps_ifd.get(2) and gps_ifd.get(4):
                lat, lon = _dms(gps_ifd[2], gps_ifd.get(1)), _dms(gps_ifd[4], gps_ifd.get(3))
                if lat is not None and lon is not None:
                    gps = {"enlem": round(lat, 6), "boylam": round(lon, 6)}
                    if gps_ifd.get(6) is not None:
                        try:
                            gps["yukseklik_m"] = round(_ratio(gps_ifd[6]), 1)
                        except (TypeError, ValueError):
                            pass
            return meta, gps, "var"
    except Exception as e:
        return {"hata": type(e).__name__}, None, "hata"


_ISO6709 = re.compile(rb"([+-]\d{1,3}(?:\.\d+)?)([+-]\d{1,3}(?:\.\d+)?)([+-]\d+(?:\.\d+)?)?/")


def video_meta(path: Path) -> tuple[dict, dict | None, str]:
    """MP4/MOV: moov/mvhd oluşturma zamanı ve udta/©xyz GPS (yoksa boş). Diğer kapsayıcılar: yok."""
    meta: dict = {}
    try:
        with open(path, "rb") as f:
            pos, end = 0, os.fstat(f.fileno()).st_size
            while pos + 8 <= end:
                f.seek(pos)
                size, typ = struct.unpack(">I4s", f.read(8))
                hdr = 8
                if size == 1:
                    size = struct.unpack(">Q", f.read(8))[0]
                    hdr = 16
                elif size == 0:
                    size = end - pos
                if size < hdr:
                    break
                if typ == b"moov":
                    if size > MOOV_MAX:
                        return meta, None, "var"
                    f.seek(pos + hdr)
                    moov = f.read(size - hdr)
                    i = moov.find(b"mvhd")
                    if i >= 0 and i + 12 <= len(moov):
                        ver = moov[i + 4]
                        ct = struct.unpack(">Q", moov[i + 8:i + 16])[0] if ver == 1 else struct.unpack(">I", moov[i + 8:i + 12])[0]
                        if ct > 2082844800:
                            meta["olusturma"] = _iso(ct - 2082844800)
                    j = moov.find(b"\xa9xyz")
                    if j >= 0:
                        m = _ISO6709.search(moov[j + 4:j + 64])
                        if m:
                            gps = {"enlem": float(m.group(1)), "boylam": float(m.group(2))}
                            if m.group(3):
                                gps["yukseklik_m"] = float(m.group(3))
                            return meta, gps, "var"
                    return meta, None, "var"
                pos += size
        return meta, None, "var"
    except (OSError, struct.error):
        return meta, None, "hata"


class ComputerFiles(ScanImporter):
    name = NAME

    def _do_scan(self, arc):  # kullanılmaz (Archive açmaz)
        raise NotImplementedError

    def _scan(self, path: Path) -> _Scan:  # type: ignore[override]
        path = Path(path)
        key = str(path.resolve())
        if key in self._cache:
            return self._cache[key]  # type: ignore[return-value]
        if not path.exists():
            raise FormatError(f"Girdi yok: {path}")
        sc = _Scan()
        h = hashlib.sha256()

        def err(_):
            sc.unreadable += 1

        for p, rel, st in _walk(path, err):
            sc.files += 1
            sc.size += st.st_size
            sc.by_class[_class_of(p.suffix.lower())] += 1
            h.update(f"{rel}\x00{st.st_size}\x00{st.st_mtime_ns}\n".encode("utf-8", "replace"))
        sc.sha = h.hexdigest()
        self._cache = {key: sc}  # type: ignore[assignment]
        return sc

    def detect(self, path: Path) -> DetectResult:
        # Her klasöre uyduğu için güven < 0.5: otomatik seçilmez, --tur computer_files gerekir.
        if Path(path).exists():
            return DetectResult(True, 0.1, "klasör/dosya; yalnız --tur computer_files ile seçilir")
        return DetectResult(False, 0.0, "yol yok")

    def verify_format(self, path: Path) -> FormatReport:
        sc = self._scan(Path(path))
        rep = FormatReport(importer=NAME, ok=sc.files > 0)
        c = sc.by_class
        rep.found_files.append(
            f"{sc.files} dosya, {sc.size} bayt: belge {c['belge']}, fotoğraf {c['foto']}, video {c['video']}, diğer {c['diger']}")
        if not sc.files:
            rep.missing.append("klasörde taranacak dosya yok (boş ya da yalnız gizli/atlanan klasörler)")
        if sc.unreadable:
            rep.notes.append(f"{sc.unreadable} klasör/dosya okunamadı (izin) ve atlandı")
        rep.notes.append("Dosyalar yerinde kalır, ham arşive kopyalanmaz; kaynak özeti ad+boyut+tarih listesidir")
        rep.notes.append("OCR yok: metin katmanı olmayan PDF 'metin=yok' işaretlenir")
        rep.notes.append("Video GPS yalnız MP4/MOV ©xyz atomundan; diğer kapsayıcılarda okunmaz")
        return rep

    def source_sha(self, path: Path) -> str:
        return self._scan(Path(path)).sha

    def input_files(self, path: Path) -> list[Origin]:
        return []  # yerinde kalır

    # ------------------------------------------------------------------ ayrıştırma
    def parse(self, path: Path) -> Iterator[EventIn]:
        root = Path(path)
        root_name = root.name
        for p, rel, st in _walk(root):
            ext = p.suffix.lower()
            cls = _class_of(ext)
            ts = _iso(st.st_mtime)
            base = {"ad": p.name, "yol": rel, "kok": root_name, "uzanti": ext, "boyut": st.st_size}
            key = stable_key("fs", root_name, rel, st.st_size, int(st.st_mtime))
            if cls in ("foto", "video"):
                meta, gps, state = (photo_meta if cls == "foto" else video_meta)(p)
                if state == "hata":
                    self._skip(f"{cls}: üst veri okunamadı")
                kind = "medya.foto" if cls == "foto" else "medya.video"
                yield EventIn(ts=ts, kind=kind, category=Category.MEDYA_META, event_key=key,
                              payload={**base, "ust_veri": meta, "ust_veri_durumu": state},
                              text=" ".join(x for x in (p.name, meta.get("marka"), meta.get("model")) if x))
                if gps:
                    yield EventIn(ts=ts, kind="dosya.konum", category=Category.KONUM, event_key=key + ":konum",
                                  payload={"dosya": rel, "kok": root_name, "tur": cls, **gps}, text=p.name)
                continue
            text, state, extra = extract_text(p, ext, st.st_size) if cls == "belge" else ("", "uygulanmaz", {})
            if state in ("hata", "yok", "sifreli", "buyuk"):
                self._skip(f"belge metni {state}")
            yield EventIn(ts=ts, kind="dosya.kayit", category=Category.DOSYALAR, event_key=key,
                          payload={**base, "metin_durumu": state, **extra},
                          text=f"{p.name}\n{text}".strip())


def factory() -> ComputerFiles:
    return ComputerFiles()
