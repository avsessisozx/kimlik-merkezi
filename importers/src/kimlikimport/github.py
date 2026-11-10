"""GitHub hesap verisi dışa aktarma içe aktarıcısı (tar.gz, açılmış klasör ya da zip).

DOĞRULANMADI: docs.github.com bu ortamdan açılamadı; dosya/alan adları hafızadan. Dışa aktarma,
`<tür>_000001.json` gibi JSON dizileri içeren bir tar.gz'dir ve kayıtlar bir `type` alanı taşır
(varsayım). Bu yüzden dosya adına değil kayıttaki `type` alanına ve zaman/metin alanlarına bakılır.
REST API kullanılmaz, jeton istenmez. Kişisel profil/anahtar/e-posta türleri bilerek ALINMAZ.
Hepsi `kod` kategorisi.
"""
from __future__ import annotations

import re
import tarfile
from collections.abc import Iterator
from pathlib import Path

import ijson
from kimlikcore import Category, EventIn, FormatError

from .base import (
    open_archive,
    DetectResult,
    FormatReport,
    Origin,
    ScanImporter,
    iso_utc,
    stable_key,
    strip_bom,
)

NAME = "github"
_TAR_EXT = (".tar.gz", ".tgz", ".tar")
_TS_FIELDS = ("created_at", "starred_at", "submitted_at", "published_at", "committed_at", "updated_at",
              "pushed_at")
# Bilerek alınmayan türler (kimlik/gizli bilgi): ad parçası eşleşirse atlanır ve raporda yazılır.
_SENSITIVE = re.compile(r"(user|email|key|token|secret|credential|session|ip_|oauth|billing|payment|"
                        r"two_factor|sponsor|organization_invitation)", re.I)
_NAME_RE = re.compile(r"^[a-z][a-z_]*_\d{3,}\.json$")
_TEXT_FIELDS = ("title", "name", "full_name", "body", "message", "description", "tag_name", "label")
_SAMPLE = 50


def _is_tar(path: Path) -> bool:
    return path.is_file() and path.name.lower().endswith(_TAR_EXT)


def _walk(path: Path):
    """(ad, açık_dosya, Origin|None) üretir; açık dosya bir sonraki yinelemeye kadar geçerlidir."""
    if _is_tar(path):
        try:
            with tarfile.open(path, "r|*") as tf:
                for m in tf:
                    if m.isfile() and m.name.lower().endswith(".json"):
                        f = tf.extractfile(m)
                        if f is not None:
                            yield m.name.replace("\\", "/"), f, Origin(path, path.name, True)
        except (tarfile.TarError, EOFError, OSError) as e:
            raise FormatError(f"{path.name}: tar arşivi okunamadı/bozuk ({type(e).__name__}).") from None
        return
    arc = open_archive(path)
    for e in arc.entries:
        if e.name.lower().endswith(".json"):
            with e.open() as f:
                yield e.name, f, e.origin


class _Scan:
    def __init__(self) -> None:
        self.files: list[tuple[str, str, Origin]] = []  # (ad, tür, origin)
        self.skipped_types: dict[str, str] = {}
        self.ignored = 0
        self.corrupt: list[str] = []
        self.types: dict[str, int] = {}


def _first_records(f, n: int):
    out = []
    for rec in ijson.items(strip_bom(f), "item", use_float=True):
        out.append(rec)
        if len(out) >= n:
            break
    return out


class GitHub(ScanImporter):
    name = NAME

    def _do_scan(self, arc):  # kullanılmaz: tar için Archive açılamaz
        raise NotImplementedError

    def _scan(self, path: Path) -> _Scan:  # type: ignore[override]
        key = str(Path(path).resolve())
        if key in self._cache:
            return self._cache[key]  # type: ignore[return-value]
        if not Path(path).exists():
            raise FormatError(f"Girdi yok: {path}")
        sc = _Scan()
        try:
            for name, f, origin in _walk(Path(path)):
                try:
                    recs = _first_records(f, _SAMPLE)
                except (ijson.JSONError, UnicodeDecodeError):
                    sc.corrupt.append(name)
                    continue
                typed = [r for r in recs if isinstance(r, dict) and isinstance(r.get("type"), str)]
                if not typed:
                    sc.ignored += 1
                    continue
                t = typed[0]["type"]
                if _SENSITIVE.search(t) or _SENSITIVE.search(name.rsplit("/", 1)[-1]):
                    sc.skipped_types[name] = t
                    continue
                sc.files.append((name, t, origin))
                sc.types[t] = sc.types.get(t, 0) + 1
        except FormatError:
            if not sc.files:
                raise
            sc.corrupt.append(f"{Path(path).name} (arşivin sonu okunamadı)")
        self._cache = {key: sc}  # type: ignore[assignment]
        return sc

    def detect(self, path: Path) -> DetectResult:
        try:
            sc = self._scan(Path(path))
        except FormatError as e:
            return DetectResult(False, 0.0, str(e))
        if sc.files:
            named = sum(1 for n, _, _ in sc.files if _NAME_RE.match(n.rsplit("/", 1)[-1]))
            return DetectResult(True, 0.9 if named else 0.55,
                                f"{len(sc.files)} GitHub `type` alanlı JSON dosyası ({', '.join(sorted(sc.types))})")
        return DetectResult(False, 0.0, "GitHub dışa aktarma JSON'u (type alanlı kayıtlar) bulunamadı")

    def verify_format(self, path: Path) -> FormatReport:
        sc = self._scan(Path(path))
        rep = FormatReport(importer=NAME, ok=bool(sc.files) and not sc.corrupt)
        for name, t, _ in sc.files:
            rep.found_files.append(f"{t}: {name}")
        for name, t in sc.skipped_types.items():
            rep.unsupported.append(f"{name}: tür '{t}' kişisel/gizli bilgi olabilir, bilerek alınmıyor")
        for c in sc.corrupt:
            rep.missing.append(f"{c}: bozuk")
        if not sc.files:
            rep.missing.append("`type` alanlı kayıt dizileri içeren GitHub dışa aktarma JSON dosyaları")
        if sc.ignored:
            rep.notes.append(f"{sc.ignored} JSON dosyası `type` alanı taşımadığı için yok sayıldı")
        rep.notes.append("Zaman alanı olmayan kayıtlar atlanır ve sayılır (RunResult.skipped)")
        return rep

    def input_files(self, path: Path) -> list[Origin]:
        sc = self._scan(Path(path))
        seen: dict[Path, Origin] = {}
        for _, _, o in sc.files:
            seen.setdefault(o.path, o)
        return list(seen.values())

    def parse(self, path: Path) -> Iterator[EventIn]:
        sc = self._scan(Path(path))
        want = {n for n, _, _ in sc.files}
        for name, f, _ in _walk(Path(path)):
            if name not in want:
                continue
            n = 0
            try:
                for rec in ijson.items(strip_bom(f), "item", use_float=True):
                    n += 1
                    ev = self._event(rec)
                    if ev is not None:
                        yield ev
            except (ijson.JSONError, UnicodeDecodeError) as exc:
                raise FormatError(
                    f"{name}: JSON {n}. kayıttan sonra bozuk ({type(exc).__name__}). "
                    "Önceki kayıtlar eklendi; dosya düzeldikten sonra yeniden alın."
                ) from None

    def _event(self, rec) -> EventIn | None:
        if not isinstance(rec, dict) or not isinstance(rec.get("type"), str):
            self._skip("github: kayıt nesne değil / type yok")
            return None
        t = rec["type"]
        ts = next((iso_utc(rec[k]) for k in _TS_FIELDS if rec.get(k) and iso_utc(rec[k])), None)
        if ts is None:
            self._skip(f"github {t}: zaman alanı yok")
            return None
        text_parts = [str(rec[k]) for k in _TEXT_FIELDS if isinstance(rec.get(k), (str, int)) and rec.get(k)]
        url = rec.get("url") if isinstance(rec.get("url"), str) else ""
        payload = {
            "tur": t, "url": url or None, "depo": _s(rec.get("repository")), "durum": rec.get("state"),
            "ad": rec.get("name") or rec.get("full_name"), "baslik": rec.get("title"),
            "govde": rec.get("body"), "aciklama": rec.get("description"), "gizli": rec.get("private"),
            "dil": rec.get("language"), "etiket": rec.get("tag_name"),
        }
        payload = {k: v for k, v in payload.items() if v not in (None, "")}
        kind = {"star": "github.yildiz", "watcher": "github.izleme", "repository": "github.depo",
                "issue": "github.issue", "pull_request": "github.pr"}.get(t, f"github.{t}")
        key = stable_key("gh", t, url or " ".join(text_parts)[:200], ts)
        return EventIn(ts=ts, kind=kind, category=Category.KOD, payload=payload,
                       text=" ".join(text_parts), event_key=key)


def _s(v):
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return v.get("url") or v.get("full_name") or v.get("name")
    return None


def factory() -> GitHub:
    return GitHub()
