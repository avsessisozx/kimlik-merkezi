"""Google Takeout içe aktarıcısı (JSON biçimi; HTML değil).

Tanınanlar (dosya adına değil İÇERİĞE bakarak; hesap dili Türkçe olabilir):
- YouTube izleme/arama geçmişi ve My Activity (JSON dizisi; kayıtlarda `time` + `title`/`header`)
- Chrome geçmişi: `{"Browser History": [ ... ]}` (`History.json` ya da eski `BrowserHistory.json`)
- YouTube abonelikleri: CSV (kanal kimliği `UC...` + `youtube.com/channel/...` adresi)
- Gmail MBOX (`.mbox`, "From " ayırıcılı): `eposta` kategorisi (hassas), akışla; ekler alınmaz.
Tanınıp işlenmeyenler rapora yazılır, sessizce atlanmaz: HTML biçimi, eski biçim.

Biçim bilgisinin kaynakları ve doğrulama durumu: durum/importers.md.
"""
from __future__ import annotations

import csv
import io
import re
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import ijson
from kimlikcore import Category, EventIn, FormatError

from .common import chrome_visit_events
from .mbox import iter_raw_messages, message_event
from .base import (
    Archive,
    DetectResult,
    Entry,
    FormatReport,
    Origin,
    csv_rows,
    has_coordinates,
    iso_utc,
    peek,
    stable_key,
    strip_bom,
)

NAME = "google_takeout"
VERSION = "0.1.0"

# İngilizce hesapta bilinen adlar (yalnız not için; tanıma içeriğe göre yapılır).
_KNOWN_NAMES = {
    "watch-history.json", "search-history.json", "myactivity.json",
    "history.json", "browserhistory.json", "subscriptions.csv",
}

_ACTIVITY_KNOWN = {
    "header", "title", "titleUrl", "description", "time", "products", "subtitles",
    "details", "locationInfos", "activityControls",
}
_CHROME_KNOWN = {"favicon_url", "page_transition", "title", "url", "client_id", "time_usec"}
_SAMPLE = 200
_UC = re.compile(r"^UC[\w-]{20,}$")
_CHROME_HEAD = re.compile(rb'^\s*\{\s*"Browser History"\s*:')

# Ürün adı (İngilizce) -> (kind, kategori). URL'den tanınmayanlar için yedek.
_PRODUCT = {
    "search": ("google.arama", Category.TARAMA),
    "image search": ("google.arama", Category.TARAMA),
    "video search": ("google.arama", Category.TARAMA),
    "chrome": ("chrome.etkinlik", Category.TARAMA),
    "discover": ("google.etkinlik", Category.TARAMA),
    "news": ("google.etkinlik", Category.TARAMA),
    "maps": ("google.harita", Category.TARAMA),
    "youtube": ("youtube.etkinlik", Category.VIDEO),
    "youtube music": ("youtube_music.etkinlik", Category.VIDEO),
}


class _Found:
    """Tarama sonucu."""

    def __init__(self) -> None:
        self.files: list[tuple[str, Entry]] = []  # (rol, girdi); rol: activity|chrome|subscriptions
        self.empty: list[Entry] = []
        self.unsupported: list[str] = []
        self.corrupt: list[str] = []
        self.notes: list[str] = []
        self.ignored = 0
        self.bad_zips: list[str] = []

    def supported(self) -> list[tuple[str, Entry]]:
        return self.files


def _first_record(entry: Entry):
    with entry.open() as raw:
        f = strip_bom(raw)
        return next(ijson.items(f, "item", use_float=True), None)


def _classify(entry: Entry, found: _Found) -> None:
    ext = entry.name.lower().rsplit(".", 1)[-1] if "." in entry.basename else ""
    if ext == "json":
        head = peek(entry)
        s = head.lstrip()
        if s.startswith(b"["):
            try:
                rec = _first_record(entry)
            except (ijson.JSONError, UnicodeDecodeError, OSError):
                found.corrupt.append(f"{entry.name} (JSON dizisi okunamadı)")
                return
            if rec is None:
                found.empty.append(entry)
            elif isinstance(rec, dict) and "time" in rec and ("title" in rec or "header" in rec):
                found.files.append(("activity", entry))
            elif isinstance(rec, dict) and "snippet" in rec and "publishedAt" in rec:
                found.unsupported.append(f"{entry.name}: 2017 öncesi eski etkinlik biçimi")
            else:
                found.ignored += 1
        elif _CHROME_HEAD.match(head):
            found.files.append(("chrome", entry))
        else:
            found.ignored += 1
    elif ext == "csv":
        if _looks_like_subscriptions(entry):
            found.files.append(("subscriptions", entry))
        else:
            found.ignored += 1
    elif ext == "mbox":
        if peek(entry, 16).startswith(b"From "):
            found.files.append(("mbox", entry))
        elif entry.size == 0:
            found.empty.append(entry)
        else:
            found.unsupported.append(f"{entry.name}: .mbox uzantılı ama 'From ' ayırıcısıyla başlamıyor")
    elif ext in ("html", "htm"):
        if b"mdl-grid" in peek(entry, 16384):
            found.unsupported.append(
                f"{entry.name}: HTML biçimi (Takeout'u JSON seçerek yeniden indirin)"
            )
        else:
            found.ignored += 1
    else:
        found.ignored += 1


def _looks_like_subscriptions(entry: Entry) -> bool:
    try:
        with entry.open() as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            rd = csv.reader(text)
            for i, row in enumerate(rd):
                if i > 2:
                    break
                if len(row) >= 3 and _UC.match(row[0].strip()) and "youtube.com/channel/" in row[1]:
                    return True
    except (UnicodeDecodeError, csv.Error, OSError):
        return False
    return False


class GoogleTakeout:
    name = NAME
    version = VERSION

    def __init__(self) -> None:
        self._cache: dict[str, tuple[Archive, _Found]] = {}
        self._skipped: Counter[str] = Counter()

    # ----------------------------------------------------------------- tarama
    def _scan(self, path: Path) -> tuple[Archive, _Found]:
        key = str(Path(path).resolve())
        if key not in self._cache:
            arc = Archive(Path(path))
            found = _Found()
            found.bad_zips = arc.bad_zips
            for e in arc.entries:
                _classify(e, found)
            self._cache = {key: (arc, found)}
        return self._cache[key]

    def detect(self, path: Path) -> DetectResult:
        try:
            _, f = self._scan(path)
        except FormatError as e:
            return DetectResult(False, 0.0, str(e))
        if f.files:
            kinds = sorted({r for r, _ in f.files})
            return DetectResult(True, 0.95, "Takeout JSON/CSV içeriği bulundu: " + ", ".join(kinds))
        if f.unsupported:
            return DetectResult(True, 0.6, "Takeout'a benzer ama işlenebilir dosya yok (desteklenmeyen biçimler)")
        return DetectResult(False, 0.0, "Takeout etkinlik/Chrome/abonelik içeriği bulunamadı")

    # ----------------------------------------------------------------- doğrulama
    def verify_format(self, path: Path) -> FormatReport:
        arc, f = self._scan(path)
        rep = FormatReport(importer=NAME, ok=True)
        rep.unsupported = list(f.unsupported)
        for role, e in f.files:
            rep.found_files.append(f"{role}: {e.name} ({e.size} bayt)")
            if e.basename.lower() not in _KNOWN_NAMES:
                rep.notes.append(
                    f"{e.name}: ad bilinen İngilizce adlarla eşleşmedi, içeriğinden tanındı "
                    "(hesap dili farklı olabilir)"
                )
        for e in f.empty:
            rep.notes.append(f"{e.name}: boş JSON dizisi (kayıt yok)")
        for b in f.bad_zips:
            rep.missing.append(f"{b}: zip dosyası okunamadı (bozuk ya da eksik indirme)")
            rep.ok = False
        for c in f.corrupt:
            rep.missing.append(f"{c}: bozuk")
            rep.ok = False
        if not f.files:
            rep.ok = False
            rep.missing.append(
                "Takeout JSON içeriği: YouTube izleme/arama geçmişi, My Activity, "
                "Chrome geçmişi, abonelik CSV'si ya da Gmail MBOX (hiçbiri bulunamadı)"
            )
        if f.ignored:
            rep.notes.append(f"{f.ignored} dosya tanınan Takeout içeriği olmadığı için yok sayıldı")
        for role, e in f.files:
            self._verify_sample(role, e, rep)
        return rep

    def _verify_sample(self, role: str, e: Entry, rep: FormatReport) -> None:
        extra: set[str] = set()
        total = bad = 0
        try:
            if role == "activity":
                for rec in self._iter_json(e, "item", _SAMPLE):
                    total += 1
                    if not isinstance(rec, dict) or iso_utc(rec.get("time")) is None:
                        bad += 1
                        continue
                    extra |= set(rec) - _ACTIVITY_KNOWN
            elif role == "chrome":
                for rec in self._iter_json(e, "Browser History.item", _SAMPLE):
                    total += 1
                    if (
                        not isinstance(rec, dict)
                        or not isinstance(rec.get("time_usec"), (int, float))
                        or not rec.get("url")
                    ):
                        bad += 1
                        continue
                    extra |= set(rec) - _CHROME_KNOWN
            elif role == "mbox":
                self._verify_mbox(e, rep)
                return
            else:
                return
        except (ijson.JSONError, UnicodeDecodeError):
            rep.ok = False
            rep.missing.append(f"{e.name}: JSON baştan okunamadı (bozuk)")
            return
        rep.unexpected_fields += [f"{e.name}: {k}" for k in sorted(extra)]
        if total and bad == total:
            rep.ok = False
            rep.missing.append(
                f"{e.name}: ilk {total} kaydın hiçbirinde beklenen alanlar yok "
                f"({'time' if role == 'activity' else 'time_usec, url'})"
            )
        elif bad:
            rep.notes.append(f"{e.name}: ilk {total} kayıttan {bad} tanesi eksik/bozuk alanlı")

    @staticmethod
    def _verify_mbox(e: Entry, rep: FormatReport) -> None:
        with e.open() as f:
            first = next(iter_raw_messages(f), None)
        if first is None or not first[1].strip():
            rep.ok = False
            rep.missing.append(f"{e.name}: MBOX'ta okunabilir ileti yok")
            return
        try:
            ev = message_event(*first)
        except Exception:
            ev = None
        if ev is None:
            rep.ok = False
            rep.missing.append(f"{e.name}: ilk iletide Date başlığı okunamadı")
        else:
            rep.notes.append(f"{e.name}: Gmail MBOX akışla okunur, ekler içe alınmaz (yalnız ad/boyut)")

    @staticmethod
    def _iter_json(e: Entry, prefix: str, limit: int | None = None):
        with e.open() as raw:
            f = strip_bom(raw)
            for n, rec in enumerate(ijson.items(f, prefix, use_float=True)):
                if limit is not None and n >= limit:
                    return
                yield rec

    # ----------------------------------------------------------------- çalıştırıcı yardımcıları
    def input_files(self, path: Path) -> list[Origin]:
        _, f = self._scan(path)
        seen: dict[Path, Origin] = {}
        for _, e in f.files:
            seen.setdefault(e.origin.path, e.origin)
        return list(seen.values())

    def skipped_counts(self) -> dict[str, int]:
        return dict(self._skipped)

    # ----------------------------------------------------------------- ayrıştırma
    def parse(self, path: Path) -> Iterator[EventIn]:
        _, f = self._scan(path)
        for role, e in f.files:
            if role == "activity":
                yield from self._parse_activity(e)
            elif role == "chrome":
                yield from self._parse_chrome(e)
            elif role == "subscriptions":
                yield from self._parse_subscriptions(e)
            elif role == "mbox":
                yield from self._parse_mbox(e)

    def _stream(self, e: Entry, prefix: str):
        n = 0
        try:
            for rec in self._iter_json(e, prefix):
                n += 1
                yield rec
        except (ijson.JSONError, UnicodeDecodeError) as exc:
            raise FormatError(
                f"{e.name}: JSON {n}. kayıttan sonra bozuk ({type(exc).__name__}). "
                "Önceki kayıtlar eklendi; dosya düzeldikten sonra yeniden alın."
            ) from None

    # --- etkinlik
    def _parse_activity(self, e: Entry) -> Iterator[EventIn]:
        for rec in self._stream(e, "item"):
            if not isinstance(rec, dict):
                self._skipped["etkinlik: kayıt nesne değil"] += 1
                continue
            ts = iso_utc(rec.get("time"))
            if ts is None:
                self._skipped["etkinlik: time yok/okunamadı"] += 1
                continue
            yield from _activity_events(rec, ts)

    # --- chrome
    def _parse_chrome(self, e: Entry) -> Iterator[EventIn]:
        for rec in self._stream(e, "Browser History.item"):
            if not isinstance(rec, dict):
                self._skipped["chrome: kayıt nesne değil"] += 1
                continue
            usec, url = rec.get("time_usec"), rec.get("url")
            if not isinstance(usec, (int, float)) or not url:
                self._skipped["chrome: time_usec/url yok"] += 1
                continue
            try:
                ts = datetime.fromtimestamp(usec / 1_000_000, tz=UTC).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
            except (OverflowError, OSError, ValueError):
                self._skipped["chrome: time_usec aralık dışı"] += 1
                continue
            yield from chrome_visit_events(
                kind="chrome.ziyaret", ts=ts, unix_usec=int(usec), url=url,
                title=rec.get("title") or "", transition=rec.get("page_transition"),
            )

    # --- Gmail MBOX
    def _parse_mbox(self, e: Entry) -> Iterator[EventIn]:
        with e.open() as f:
            for from_line, raw, trunc in iter_raw_messages(f):
                if not from_line and not raw.strip():
                    continue
                try:
                    ev = message_event(from_line, raw, trunc)
                except Exception:
                    self._skipped["eposta: ileti ayrıştırılamadı"] += 1
                    continue
                if ev is None:
                    self._skipped["eposta: tarih yok/okunamadı"] += 1
                    continue
                if trunc:
                    self._skipped["eposta: ileti boyut sınırında kesildi (metin kısmi)"] += 1
                yield ev

    # --- abonelikler
    def _parse_subscriptions(self, e: Entry) -> Iterator[EventIn]:
        ts = iso_utc(e.mtime)
        for row in csv_rows(e):
            vals = [v for v in row.values() if isinstance(v, str)]
            if len(vals) < 3 or not _UC.match(vals[0].strip()):
                continue  # başlık satırı ya da tanınmayan satır (başlık DictReader'a gider)
            cid, url, title = vals[0].strip(), vals[1].strip(), vals[2].strip()
            yield EventIn(
                ts=ts, kind="youtube.abonelik", category=Category.VIDEO,
                event_key=stable_key("gt", "abone", cid),
                payload={"kanal_id": cid, "kanal_url": url, "kanal_adi": title,
                         "zaman_kaynagi": "dosya_tarihi"},
                text=title,
            )


# --------------------------------------------------------------------------- etkinlik eşleme
def _host(url: str) -> tuple[str, str]:
    try:
        u = urlparse(url)
        return (u.hostname or "").lower(), u.path or ""
    except ValueError:
        return "", ""


def _kind_for(rec: dict) -> tuple[str, str]:
    url = rec.get("titleUrl") or ""
    host, path = _host(url)
    if host == "youtu.be" or host.endswith("youtube.com"):
        music = host.startswith("music.")
        base = "youtube_music" if music else "youtube"
        if path.startswith("/watch") or host == "youtu.be":
            return f"{base}.izleme", Category.VIDEO
        if path.startswith("/results"):
            return f"{base}.arama", Category.VIDEO
        return f"{base}.etkinlik", Category.VIDEO
    if host.startswith(("www.google.", "google.")) and path.startswith("/search"):
        return "google.arama", Category.TARAMA
    if host.startswith("maps.google.") or (
        host.startswith(("www.google.", "google.")) and path.startswith("/maps")
    ):
        return "google.harita", Category.TARAMA
    names = [str(rec.get("header") or "")] + [str(p) for p in (rec.get("products") or [])]
    for n in names:
        hit = _PRODUCT.get(n.strip().lower())
        if hit:
            return hit
    return "google.etkinlik", Category.UYGULAMA


def _names(items) -> list[str]:
    out = []
    for it in items or []:
        if isinstance(it, dict) and it.get("name"):
            out.append(str(it["name"]))
    return out


def _activity_events(rec: dict, ts: str) -> Iterator[EventIn]:
    kind, cat = _kind_for(rec)
    title = str(rec.get("title") or "")
    url = rec.get("titleUrl")
    loc = [x for x in (rec.get("locationInfos") or []) if isinstance(x, dict)]
    key = stable_key("gt", kind, rec.get("time"), url, title)
    coord_url = has_coordinates(url)
    payload: dict = {
        "baslik": title,
        "url": None if coord_url else url,
        "urun": rec.get("header"),
        "urunler": rec.get("products") or [],
        "etkinlik_kontrolleri": rec.get("activityControls") or [],
    }
    if coord_url:
        payload["url_konum_ayrildi"] = True
    subs = rec.get("subtitles")
    if subs:
        payload["alt_baslik"] = _names(subs)
        first = subs[0] if isinstance(subs, list) and subs and isinstance(subs[0], dict) else {}
        if first.get("url"):
            payload["kanal_url"] = first["url"]
    det = _names(rec.get("details"))
    if det:
        payload["ayrinti"] = det
    if rec.get("description"):
        payload["aciklama"] = rec["description"]
    if kind.endswith(".izleme") and url:
        q = parse_qs(urlparse(url).query)
        vid = (q.get("v") or [None])[0]
        if vid:
            payload["video_id"] = vid
    text = " ".join([title] + payload.get("alt_baslik", [])).strip()
    yield EventIn(ts=ts, kind=kind, category=cat, payload=payload, text=text, event_key=key)
    if loc or coord_url:
        names = [str(x.get("name")) for x in loc if x.get("name")]
        yield EventIn(
            ts=ts, kind="google.konum", category=Category.KONUM, event_key=key + ":konum",
            payload={"kaynak": kind, "baslik": title,
                     "yerler": [{k: x.get(k) for k in ("name", "url", "source", "sourceUrl")} for x in loc],
                     "url": url if coord_url else None},
            text=" ".join(names) or title,
        )


def factory() -> GoogleTakeout:
    return GoogleTakeout()


__all__ = ["NAME", "VERSION", "GoogleTakeout", "factory"]
