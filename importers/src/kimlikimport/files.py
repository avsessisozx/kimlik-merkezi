"""Bilgisayar dosyaları: kullanıcının seçtiği klasör ya da dosyalar taranır; dosyalar YERİNDE kalır (kopyalanmaz).

Kural: okunabilen her şey eklenir; yalnız gerçekten bozuk (açılamayan) dosya atlanır ve nedeniyle raporlanır.
Her dosya üç sonuçtan birine girer:
- İÇERİKLİ: metni/üst verisi okundu. Düz metin (kodlama otomatik: UTF-8/UTF-16/cp1254), kod, günlük, JSON/CSV/XML/HTML,
  e-posta (.eml), PDF, DOCX, XLSX, PPTX, ODT/ODS/ODP, RTF. Fotoğraf/video: yalnız üst veri (`medya_meta`); GPS varsa AYRI `konum` olayı.
- YALNIZ KAYIT: sağlam görünür ama içeriği okunamaz (ses, program, arşiv, eski ikili Office, bilinmeyen ikili, taranmış PDF,
  parolalı, çok büyük, boş). Ad, tür, boyut, tarih kaydedilir; `icerik_durumu = "yalnız kayıt"` ve `kayit_notu` işaretlenir.
- BOZUK: açılamayan/kesik belge ya da zip. KAYIT EKLENMEZ; neden raporda listelenir. Tek bozuk dosya içe aktarmayı düşürmez.
Metin katmanı olmayan (taranmış) PDF için OCR YOK. Gizli (nokta ile başlayan), `~$` geçici ve sistem dosyaları taranmaz.
Yeni bağımlılık YOK: PDF için pypdf (BSD-3-Clause), DOCX için python-docx (MIT), görsel için Pillow (MIT-CMU); XLSX/PPTX/ODF/RTF/EML
yalnız standart kütüphane (zipfile, re, email) ile okunur. Hiçbiri AGPL değil.

Kaynak özeti (source_sha) dosya adı+boyut+tarih listesinin özetidir: klasör değişmediyse aynı kaynak.
Otomatik tanımada SEÇİLMEZ (her klasöre uyar); `ice-al --tur computer_files` ya da arayüzde "Bilgisayarımdaki dosyalar" ile seçilir.
Yol bir liste de olabilir (birden çok dosya/klasör seçimi).
"""
from __future__ import annotations

import codecs
import email
import email.policy
import hashlib
import html
import os
import re
import struct
import zipfile
from collections.abc import Iterator, Sequence
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
MAX_ZIP_MEMBER = 50 * 1024 * 1024      # zip içindeki tek parçadan en çok bu kadar okunur (zip bombası sınırı)
MOOV_MAX = 32 * 1024 * 1024
LISTE_SINIRI = 50                      # raporda adıyla sayılan atlanan/yalnız-kayıt dosya sayısı üst sınırı

SKIP_DIRS = {"node_modules", "__pycache__", "$recycle.bin", "system volume information", ".git", ".svn"}
SKIP_FILES = {"thumbs.db", "desktop.ini", ".ds_store"}
PLAIN = {".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".log", ".json", ".jsonl", ".ndjson", ".geojson", ".xml",
         ".html", ".htm", ".xhtml", ".ini", ".cfg", ".conf", ".toml", ".yaml", ".yml", ".env", ".properties", ".srt", ".vtt",
         ".ics", ".vcf", ".gpx", ".kml", ".svg", ".css", ".scss", ".less", ".tex", ".bib", ".sql",
         ".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".vue", ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".go",
         ".rs", ".rb", ".php", ".pl", ".lua", ".r", ".swift", ".scala", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd", ".vbs"}
HTML = {".html", ".htm", ".xhtml"}
IMAGES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".gif", ".bmp", ".heic", ".heif"}
VIDEOS = {".mp4", ".mov", ".m4v", ".3gp", ".mkv", ".avi", ".webm", ".wmv"}
AUDIO = {".mp3", ".wav", ".flac", ".ogg", ".oga", ".m4a", ".aac", ".wma", ".opus", ".aiff", ".mid", ".midi"}
OOXML = {".docx", ".xlsx", ".pptx"}
ODF = {".odt", ".ods", ".odp"}
OLD_OFFICE = {".doc", ".xls", ".ppt"}
ARCHIVES = {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".cab"}
BINARY = {".exe", ".dll", ".msi", ".bin", ".iso", ".dmg", ".apk", ".so", ".dylib", ".class", ".jar", ".o", ".obj", ".pyc",
          ".sys", ".db", ".sqlite", ".sqlite3", ".dat", ".psd", ".ttf", ".otf", ".woff", ".woff2"}
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

NEDEN = {
    "yok": "okunabilir metin yok (taranmış olabilir)",
    "sifreli": "parola korumalı",
    "buyuk": "çok büyük, içerik okunmadı",
    "desteklenmiyor": "içerik okunamadı",
    "uygulanmaz": "içeriği okunamayan tür (ses, program, arşiv, bilinmeyen ikili)",
    "bos": "boş dosya",
    "hata": "bozuk ya da açılamadı",
}
KAYIT_NOTU = "içerik okunamadı, yalnız kayıt eklendi"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _kokler(path) -> list[Path]:
    if isinstance(path, (list, tuple)):
        return [Path(p) for p in path]
    return [Path(path)]


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


def _walk_all(roots: list[Path], on_error=None) -> Iterator[tuple[Path, str, os.stat_result, str]]:
    """Tüm kökler üzerinde (yol, göreli yol, stat, kök adı). Tek kökte göreli yol kökten başlar; çok kökte
    çakışmasın diye tam yol kullanılır. Aynı dosya iki kez gelmez."""
    gorulen: set[str] = set()
    cok = len(roots) > 1
    for root in roots:
        for p, rel, st in _walk(root, on_error):
            try:
                kimlik = str(p.resolve())
            except OSError:
                kimlik = str(p)
            if kimlik in gorulen:
                continue
            gorulen.add(kimlik)
            if cok:
                yield p, p.as_posix(), st, "seçilen dosyalar"
            else:
                yield p, rel, st, root.name


class _Scan:
    def __init__(self) -> None:
        self.files = self.size = 0
        self.by_class = {"belge": 0, "foto": 0, "video": 0, "ses": 0, "diger": 0}
        self.unreadable = 0
        self.sha = ""


def _class_of(ext: str) -> str:
    if ext in IMAGES:
        return "foto"
    if ext in VIDEOS:
        return "video"
    if ext in AUDIO:
        return "ses"
    if ext in PLAIN or ext in OOXML or ext in ODF or ext in OLD_OFFICE or ext in {".pdf", ".rtf", ".eml"}:
        return "belge"
    return "diger"


# ----------------------------------------------------------------------- metin çıkarma
def _temiz(t: str) -> str:
    """NUL'ları at, eşleşmemiş vekil (surrogate) karakterleri değiştir: veritabanına UTF-8 yazılabilir olsun."""
    return t.replace("\x00", "").encode("utf-8", "replace").decode("utf-8")


def _ikili_gorunur(ornek: bytes) -> bool:
    if b"\x00" in ornek:
        return True
    kontrol = sum(1 for b in ornek if b < 32 and b not in (9, 10, 12, 13, 27))
    return kontrol > max(2, len(ornek) // 50)


def decode_text(raw: bytes) -> tuple[str, str] | None:
    """(metin, kodlama) ya da None (ikili). Sıra: BOM -> BOM'suz UTF-16 -> UTF-8 -> cp1254 (Türkçe Windows)."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "replace"), "utf-8"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", "replace"), "utf-16"
    head = raw[:4096]
    if len(head) >= 4 and b"\x00" in head:
        yarim = len(head) // 2
        cift, tek = head[0::2].count(0), head[1::2].count(0)
        if tek > 0.3 * yarim and cift < 0.05 * yarim:
            return raw.decode("utf-16-le", "replace"), "utf-16"
        if cift > 0.3 * yarim and tek < 0.05 * yarim:
            return raw.decode("utf-16-be", "replace"), "utf-16"
        return None
    if _ikili_gorunur(head):
        return None
    try:   # okuma sınırında kesilen çok baytlı karakter hata sayılmasın
        return codecs.getincrementaldecoder("utf-8")("strict").decode(raw, final=False), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1254"), "cp1254"
    except UnicodeDecodeError:
        return raw.decode("cp1254", "replace"), "cp1254"


def extract_text(path: Path, ext: str, size: int) -> tuple[str, str, dict]:
    """(metin, durum, ek). durum: var | yok | hata | buyuk | sifreli | desteklenmiyor | bos | uygulanmaz.
    `hata` = bozuk (atlanır); `ek["neden"]` insan-okur nedeni, `ek["hata"]` yalnız istisna sınıf adı (içerik yok)."""
    try:
        if ext == ".pdf":
            if size > MAX_PDF_BYTES:
                return "", "buyuk", {}
            return _pdf(path)
        if ext in OOXML or ext in ODF:
            if size > MAX_DOCX_BYTES:
                return "", "buyuk", {}
            return _zip_belge(path, ext)
        if ext == ".rtf":
            return _rtf(path)
        if ext == ".eml":
            return _eml(path)
        if ext in OLD_OFFICE:
            return "", "desteklenmiyor", {"neden": "eski ikili Office biçimi (.doc/.xls/.ppt)"}
        if ext == ".zip":
            with zipfile.ZipFile(path) as z:
                z.namelist()
            return "", "uygulanmaz", {"neden": "zip arşivi (içindekiler okunmaz)"}
        if ext in AUDIO or ext in ARCHIVES or ext in BINARY:
            return "", "uygulanmaz", {}
        return _duz_metin(path, ext)
    except Exception as e:  # bozuk belge: içerik sızdırmadan sınıf adı
        return "", "hata", {"hata": type(e).__name__}


def _duz_metin(path: Path, ext: str):
    bilinen = ext in PLAIN
    with open(path, "rb") as f:
        raw = f.read(8192)
        if not raw:
            return "", "bos", {}
        if not bilinen and decode_text(raw) is None:
            return "", "uygulanmaz", {}
        raw += f.read(MAX_PLAIN_BYTES - len(raw))
    if not raw:
        return "", "bos", {}
    d = decode_text(raw)
    if d is None:
        return ("", "desteklenmiyor", {"neden": "ikili içerik"}) if bilinen else ("", "uygulanmaz", {})
    t, enc = d
    if ext in HTML:
        from .mbox import html_to_text
        t = html_to_text(t)
    t = _temiz(t).strip()
    return (t[:MAX_TEXT_CHARS], "var", {"kodlama": enc}) if t else ("", "bos", {})


def _pdf(path: Path):
    from pypdf import PdfReader

    with open(path, "rb") as f:
        if b"%PDF" not in f.read(1024):
            return "", "hata", {"neden": "PDF başlığı yok"}
    r = PdfReader(str(path))
    try:
        if r.is_encrypted and not r.decrypt(""):
            return "", "sifreli", {}
    except Exception as e:
        if type(e).__name__ == "DependencyError":   # AES için ek bileşen yok: bozuk değil, okunamıyor
            return "", "sifreli", {"neden": "parola korumalı (çözmek için ek bileşen gerekir)"}
        raise
    n = len(r.pages)
    parts: list[str] = []
    total = 0
    for i, page in enumerate(r.pages):
        if i >= MAX_PDF_PAGES or total >= MAX_TEXT_CHARS:
            break
        try:
            t = _temiz(page.extract_text() or "").strip()
        except Exception:   # tek bozuk sayfa belgeyi düşürmesin
            continue
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
    text = _temiz("\n".join(x for x in parts if x.strip()))[:MAX_TEXT_CHARS]
    return (text, "var", {}) if text.strip() else ("", "yok", {})


def _zread(z: zipfile.ZipFile, ad: str, sinir: int = MAX_ZIP_MEMBER) -> str:
    with z.open(ad) as f:
        return f.read(sinir).decode("utf-8", "replace")


def _xml_metin(xml: str) -> str:
    return html.unescape(re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"<[^>]+>", " ", xml)))


def _zip_belge(path: Path, ext: str):
    with open(path, "rb") as f:
        if f.read(8) == OLE_MAGIC:   # parolalı OOXML bir OLE kabında durur
            return "", "sifreli", {"neden": "parola korumalı"}
    if ext == ".docx":
        return _docx(path)
    with zipfile.ZipFile(path) as z:
        adlar = z.namelist()
        if ext in ODF:
            if "content.xml" not in adlar:
                raise KeyError("content.xml")
            xml = _zread(z, "content.xml")
            xml = re.sub(r"</text:(?:p|h)>|</table:table-row>", "\n", xml)
            text = re.sub(r"[ \t]*\n[ \t\n]*", "\n", _xml_metin(xml)).strip()
        elif ext == ".xlsx":
            text = _xlsx(z, adlar)
        else:
            text = _pptx(z, adlar)
    text = _temiz(text)[:MAX_TEXT_CHARS]
    return (text, "var", {}) if text.strip() else ("", "yok", {})


def _xlsx(z: zipfile.ZipFile, adlar: list[str]) -> str:
    if "xl/workbook.xml" not in adlar:
        raise KeyError("workbook.xml")
    ortak: list[str] = []
    if "xl/sharedStrings.xml" in adlar:
        for si in re.findall(r"<si\b[^>]*>(.*?)</si>", _zread(z, "xl/sharedStrings.xml"), re.S):
            ortak.append(html.unescape("".join(re.findall(r"<t\b[^>]*>(.*?)</t>", si, re.S))))
    sayfalar = sorted((a for a in adlar if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", a)),
                      key=lambda a: int(re.findall(r"\d+", a)[-1]))
    out: list[str] = []
    toplam = 0
    for ad in sayfalar:
        for satir in re.findall(r"<row\b[^>]*>(.*?)</row>", _zread(z, ad), re.S):
            hucre: list[str] = []
            for nitelik, ic in re.findall(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", satir, re.S):
                v = re.search(r"<v>(.*?)</v>", ic or "", re.S)
                tur = re.search(r'\bt="(\w+)"', nitelik)
                tur = tur.group(1) if tur else "n"
                if tur == "s" and v:
                    try:
                        hucre.append(ortak[int(v.group(1))])
                    except (ValueError, IndexError):
                        pass
                elif tur == "inlineStr":
                    hucre.append(html.unescape("".join(re.findall(r"<t\b[^>]*>(.*?)</t>", ic or "", re.S))))
                elif v:
                    hucre.append(html.unescape(v.group(1)))
            if hucre:
                s = " ".join(x for x in hucre if x.strip())
                out.append(s)
                toplam += len(s)
            if toplam >= MAX_TEXT_CHARS:
                return "\n".join(out)
    return "\n".join(out)


def _pptx(z: zipfile.ZipFile, adlar: list[str]) -> str:
    slaytlar = sorted((a for a in adlar if re.fullmatch(r"ppt/(?:slides|notesSlides)/\w+\.xml", a)),
                      key=lambda a: (a.split("/")[1] != "slides", [int(x) for x in re.findall(r"\d+", a)] or [0]))
    if not slaytlar and "ppt/presentation.xml" not in adlar:
        raise KeyError("presentation.xml")
    out: list[str] = []
    for ad in slaytlar:
        xml = _zread(z, ad)
        for par in re.findall(r"<a:p\b[^>]*>(.*?)</a:p>", xml, re.S):
            t = html.unescape("".join(re.findall(r"<a:t\b[^>]*>(.*?)</a:t>", par, re.S)))
            if t.strip():
                out.append(t)
        if sum(len(x) for x in out) >= MAX_TEXT_CHARS:
            break
    return "\n".join(out)


_RTF_ATLA = re.compile(r"\\\*|\\(?:fonttbl|colortbl|stylesheet|info|pict|header|footer|object|themedata|datastore|latentstyles)\b")


def _rtf(path: Path):
    with open(path, "rb") as f:
        s = f.read(MAX_PLAIN_BYTES).decode("latin-1")
    if not s.lstrip().startswith("{\\rtf"):
        return "", "hata", {"neden": "RTF başlığı yok"}
    out: list[str] = []
    derin, atla, i, n = 0, None, 0, len(s)
    while i < n:
        c = s[i]
        if c == "{":
            derin += 1
            if atla is None and _RTF_ATLA.match(s, i + 1):
                atla = derin
            i += 1
        elif c == "}":
            if atla == derin:
                atla = None
            derin -= 1
            i += 1
        elif c == "\\":
            m = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\(.)", re.S).match(s, i)
            if not m:
                i += 1
                continue
            i = m.end()
            if atla is not None:
                continue
            ad, sayi, hexb, tek = m.groups()
            if hexb:
                out.append(bytes([int(hexb, 16)]).decode("cp1254", "replace"))
            elif ad == "u" and sayi:
                out.append(chr(int(sayi) & 0xFFFF))
                i += 1   # yedek karakteri atla
            elif ad in ("par", "line", "row"):
                out.append("\n")
            elif ad in ("tab", "cell"):
                out.append("\t")
            elif tek in ("\\", "{", "}"):
                out.append(tek)
        else:
            if atla is None and c not in "\r\n":
                out.append(c)
            i += 1
    t = _temiz("".join(out))
    t = re.sub(r"[ \t]*\n[ \t\n]*", "\n", t).strip()[:MAX_TEXT_CHARS]
    return (t, "var", {}) if t else ("", "yok", {})


def _eml(path: Path):
    from .mbox import _body_and_attachments

    with open(path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=email.policy.default)
    govde, _ekler = _body_and_attachments(msg)
    basliklar = []
    for ad, et in (("subject", "Konu"), ("from", "Kimden"), ("to", "Kime"), ("date", "Tarih")):
        try:
            v = str(msg.get(ad) or "").strip()
        except Exception:
            v = ""
        if v:
            basliklar.append(f"{et}: {v}")
    t = _temiz("\n".join(basliklar) + "\n\n" + govde).strip()[:MAX_TEXT_CHARS]
    return (t, "var", {}) if govde.strip() or basliklar else ("", "bos", {})


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

    def __init__(self) -> None:
        super().__init__()
        self.file_progress = None   # (islenen, toplam) -> None; çalıştırıcı bağlar
        self.ozet: dict = {}

    def _do_scan(self, arc):  # kullanılmaz (Archive açmaz)
        raise NotImplementedError

    def _scan(self, path) -> _Scan:  # type: ignore[override]
        roots = _kokler(path)
        key = "\x00".join(str(r.resolve()) for r in roots)
        if key in self._cache:
            return self._cache[key]  # type: ignore[return-value]
        for r in roots:
            if not r.exists():
                raise FormatError(f"Girdi yok: {r}")
        sc = _Scan()
        h = hashlib.sha256()

        def err(_):
            sc.unreadable += 1

        for p, rel, st, _kok in _walk_all(roots, err):
            sc.files += 1
            sc.size += st.st_size
            sc.by_class[_class_of(p.suffix.lower())] += 1
            h.update(f"{rel}\x00{st.st_size}\x00{st.st_mtime_ns}\n".encode("utf-8", "replace"))
        sc.sha = h.hexdigest()
        self._cache = {key: sc}  # type: ignore[assignment]
        return sc

    def detect(self, path) -> DetectResult:
        # Her klasöre uyduğu için güven < 0.5: otomatik seçilmez, --tur computer_files gerekir.
        if all(r.exists() for r in _kokler(path)):
            return DetectResult(True, 0.1, "klasör/dosya; yalnız --tur computer_files ile seçilir")
        return DetectResult(False, 0.0, "yol yok")

    def verify_format(self, path) -> FormatReport:
        sc = self._scan(path)
        rep = FormatReport(importer=NAME, ok=sc.files > 0)
        c = sc.by_class
        rep.found_files.append(
            f"{sc.files} dosya, {sc.size} bayt: belge {c['belge']}, fotoğraf {c['foto']}, video {c['video']}, "
            f"ses {c['ses']}, diğer {c['diger']}")
        if not sc.files:
            rep.missing.append("klasörde taranacak dosya yok (boş ya da yalnız gizli/atlanan klasörler)")
        if sc.unreadable:
            rep.notes.append(f"{sc.unreadable} klasör/dosya okunamadı (izin) ve atlandı")
        rep.notes.append("Dosyalar yerinde kalır, ham arşive kopyalanmaz; kaynak özeti ad+boyut+tarih listesidir")
        rep.notes.append("Okunabilen her şey içeriğiyle, okunamayan sağlam dosyalar yalnız kayıt olarak eklenir; bozuk dosya atlanır ve raporlanır")
        rep.notes.append("OCR yok: metin katmanı olmayan PDF yalnız kayıt olarak eklenir")
        rep.notes.append("Gizli (nokta ile başlayan), ~$ geçici ve sistem dosyaları taranmaz")
        rep.notes.append("Video GPS yalnız MP4/MOV ©xyz atomundan; diğer kapsayıcılarda okunmaz")
        return rep

    def source_sha(self, path) -> str:
        return self._scan(path).sha

    def input_files(self, path) -> list[Origin]:
        return []  # yerinde kalır

    # ------------------------------------------------------------------ rapor
    def _ozet_sifirla(self) -> None:
        self.ozet = {"toplam": 0, "icerikli": 0, "yalniz_kayit": 0, "bozuk": 0, "metinsiz_pdf": 0,
                     "yalniz_kayit_nedenleri": {}, "bozuk_nedenleri": {}, "yalniz_kayit_dosyalari": [],
                     "bozuk_dosyalari": []}

    def _say(self, sinif: str, rel: str, neden: str = "", teknik: str = "") -> None:
        o = self.ozet
        o["toplam"] += 1
        o[sinif] += 1
        if sinif == "icerikli":
            return
        nd = o["bozuk_nedenleri" if sinif == "bozuk" else "yalniz_kayit_nedenleri"]
        nd[neden] = nd.get(neden, 0) + 1
        lst = o["bozuk_dosyalari" if sinif == "bozuk" else "yalniz_kayit_dosyalari"]
        if len(lst) < LISTE_SINIRI:
            lst.append({"yol": rel, "neden": neden + (f" ({teknik})" if teknik else "")})

    def ozet_metni(self) -> str:
        o = self.ozet
        if not o or not o.get("toplam"):
            return ""
        L = [f"{o['toplam']} dosya işlendi: {o['icerikli']} dosya içeriğiyle, {o['yalniz_kayit']} dosya yalnız kayıt olarak "
             f"(içerik okunamadı), {o['bozuk']} dosya bozuk/okunamadığı için atlandı."]
        if o["metinsiz_pdf"]:
            L.append(f"{o['metinsiz_pdf']} PDF'de okunabilir metin yok (taranmış olabilir); yalnız kayıt eklendi.")
        for baslik, nd in (("Yalnız kayıt", o["yalniz_kayit_nedenleri"]), ("Atlanan (bozuk)", o["bozuk_nedenleri"])):
            if nd:
                L.append(f"{baslik}: " + "; ".join(f"{k}: {v}" for k, v in sorted(nd.items())))
        return "\n".join(L)

    # ------------------------------------------------------------------ ayrıştırma
    def parse(self, path) -> Iterator[EventIn]:
        roots = _kokler(path)
        toplam = self._scan(path).files
        self._ozet_sifirla()
        islenen = 0
        for p, rel, st, root_name in _walk_all(roots):
            ext = p.suffix.lower()
            cls = _class_of(ext)
            try:
                yield from self._dosya(p, rel, st, root_name, ext, cls)
            except Exception as e:   # beklenmeyen tek dosya hatası içe aktarmayı düşürmez
                if isinstance(e, GeneratorExit):
                    raise
                self._skip("dosya okunamadı (beklenmeyen)")
                self._say("bozuk", rel, "beklenmeyen hata", type(e).__name__)
            islenen += 1
            if self.file_progress:
                self.file_progress(islenen, max(toplam, islenen))

    def _dosya(self, p: Path, rel: str, st, root_name: str, ext: str, cls: str) -> Iterator[EventIn]:
        ts = _iso(st.st_mtime)
        base = {"ad": p.name, "yol": rel, "kok": root_name, "uzanti": ext, "boyut": st.st_size, "tur": cls, "tarih": ts}
        key = stable_key("fs", root_name, rel, st.st_size, int(st.st_mtime))
        if cls in ("foto", "video"):
            meta, gps, state = (photo_meta if cls == "foto" else video_meta)(p)
            kind = "medya.foto" if cls == "foto" else "medya.video"
            if state == "var":
                self._say("icerikli", rel)
                extra = {"icerik_durumu": "okundu"}
            else:   # HEIC gibi Pillow'un açamadığı sağlam dosya: yalnız kayıt
                self._skip(f"{cls}: üst veri okunamadı")
                self._say("yalniz_kayit", rel, "fotoğraf/video üst verisi okunamadı")
                extra = {"icerik_durumu": "yalnız kayıt", "kayit_notu": KAYIT_NOTU}
            yield EventIn(ts=ts, kind=kind, category=Category.MEDYA_META, event_key=key,
                          payload={**base, **extra, "ust_veri": meta, "ust_veri_durumu": state},
                          text=" ".join(x for x in (p.name, meta.get("marka"), meta.get("model")) if x))
            if gps:
                yield EventIn(ts=ts, kind="dosya.konum", category=Category.KONUM, event_key=key + ":konum",
                              payload={"dosya": rel, "kok": root_name, "tur": cls, **gps}, text=p.name)
            return
        text, state, extra = extract_text(p, ext, st.st_size)
        neden = extra.get("neden") or NEDEN.get(state, state)
        if state == "hata":
            self._skip("belge metni hata")
            self._say("bozuk", rel, neden, extra.get("hata", ""))
            return   # bozuk dosya: kayıt eklenmez
        if state == "var":
            self._say("icerikli", rel)
            durum = {"icerik_durumu": "okundu"}
        else:
            if state in ("yok", "sifreli", "buyuk"):
                self._skip(f"belge metni {state}")
            if state == "yok" and ext == ".pdf":
                self.ozet["metinsiz_pdf"] += 1
            self._say("yalniz_kayit", rel, neden)
            durum = {"icerik_durumu": "yalnız kayıt", "kayit_notu": f"{KAYIT_NOTU} ({neden})"}
        yield EventIn(ts=ts, kind="dosya.kayit", category=Category.DOSYALAR, event_key=key,
                      payload={**base, **durum, "metin_durumu": state,
                               **{k: v for k, v in extra.items() if k != "hata"}},
                      text=f"{p.name}\n{text}".strip())


def factory() -> ComputerFiles:
    return ComputerFiles()
