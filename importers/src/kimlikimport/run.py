"""Çalıştırıcı (INTERFACES §4 ve §11 Ek 1.1).

Sıra: detect -> verify_format -> previously_purged -> add_source -> store_raw -> parse -> add_events.
Girdi dosyalarına hiç yazılmaz. Biçim uygun değilse `ImportFormatError` (iletisi kopyalanabilir
rapordur) ve hiçbir şey eklenmez.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from kimlikcore import EventIn, FormatError, Hub, RawFile, sha256_file

from . import registry
from .base import FormatReport, ImportFormatError, Origin, clear_archive_cache

ProgressFn = Callable[[str, int], None]


@dataclass(slots=True)
class RunResult:
    importer: str
    source_id: str
    parsed: int  # ayrıştırılıp çekirdeğe verilen olay sayısı
    added: int
    duplicate: int
    raw_files: list[RawFile]
    report: FormatReport
    skipped: dict[str, int] = field(default_factory=dict)  # neden -> sayı (içerik yok)

    def __str__(self) -> str:
        L = [
            f"Kaynak: {self.importer} ({self.source_id})",
            f"Ayrıştırılan: {self.parsed}  Eklenen: {self.added}  Zaten vardı: {self.duplicate}",
            "Ham arşiv: " + (", ".join(r.path for r in self.raw_files) or "-"),
        ]
        if self.skipped:
            L.append("Atlanan kayıtlar: " + "; ".join(f"{k}: {v}" for k, v in sorted(self.skipped.items())))
        if self.report.unsupported:
            L.append("Desteklenmediği için atlanan:")
            L += [f"  - {u}" for u in self.report.unsupported]
        return "\n".join(L)


def _combined_sha(path: Path, origins: list[Origin], hashes: dict[Path, str]) -> str:
    """Tek zip/dosya girdisinde dosyanın kendi SHA-256'sı; çok parçalıda (etiket, hash) özeti."""
    if len(origins) == 1 and origins[0].path == path:
        return hashes[origins[0].path]
    h = hashlib.sha256()
    for o in sorted(origins, key=lambda o: o.label):
        h.update(o.label.encode("utf-8") + b"\x00" + hashes[o.path].encode() + b"\n")
    return h.hexdigest()


def _counting(it: Iterator[EventIn], counter: list[int], progress: ProgressFn | None, every: int = 5000):
    for ev in it:
        counter[0] += 1
        if progress and counter[0] % every == 0:
            progress("isle", counter[0])
        yield ev


def _flat_link(tmp: Path, origin: Origin) -> Path:
    """Gevşek dosya için ham arşivde benzersiz ad: klasör yolu '__' ile düzleştirilir.
    Önce sembolik bağ (kopya yok); olmazsa kopya."""
    link = tmp / origin.label.replace("/", "__")[:200]
    try:
        os.symlink(origin.path.resolve(), link)
    except (OSError, NotImplementedError):
        shutil.copy2(origin.path, link)
    return link


def _taninmama_mesaji(path: Path) -> str:
    """Hiçbir içe aktarıcı dosyayı tanımadığında kullanıcıya gösterilen ilk satır: bozuk dosya ile
    tanınmayan dosya ayrı söylenir (zip ise açılabiliyor mu diye bakılır)."""
    import zipfile

    if path.is_file():
        try:
            with open(path, "rb") as f:
                zip_gibi = f.read(2) == b"PK" or path.suffix.lower() == ".zip"
        except OSError:
            zip_gibi = False
        if zip_gibi and not zipfile.is_zipfile(path):
            return ("Bu dosya bozuk görünüyor: zip olarak açılamadı. İndirme yarım kalmış olabilir; "
                    "dışa aktarma dosyasını yeniden indirip tekrar deneyin.")
        if zip_gibi:
            try:
                with zipfile.ZipFile(path) as z:
                    if z.testzip() is not None:
                        return ("Bu dosya bozuk görünüyor: zip içindeki bir dosya okunamadı. "
                                "İndirme yarım kalmış olabilir; yeniden indirip tekrar deneyin.")
            except (zipfile.BadZipFile, OSError, NotImplementedError, RuntimeError):
                return ("Bu dosya bozuk görünüyor: zip olarak açılamadı. İndirme yarım kalmış olabilir; "
                        "dışa aktarma dosyasını yeniden indirip tekrar deneyin.")
    return ("Bu dosyayı tanıyamadım. Google Takeout, Reddit, ChatGPT, Claude, Spotify, Instagram/Facebook "
            "ya da GitHub dışa aktarma dosyası mı? Dosya sağlam ama tanınmıyorsa aşağıdaki teknik ayrıntıyı "
            "geliştiriciyle paylaşın.")


def run(
    hub: Hub,
    path: Path | str,
    tur: str | None = None,
    *,
    yine_de: bool = False,
    progress: ProgressFn | None = None,
) -> RunResult:
    """Dosyayı/klasörü içe aktarır. `progress(asama, sayi)`: asama 'dogrula'|'kopyala'|'isle'."""
    path = Path(path)
    if not path.exists():
        raise FormatError(f"Girdi yok: {path}")
    notify = progress or (lambda *_: None)
    clear_archive_cache()

    # 1) detect
    notify("dogrula", 0)
    if tur:
        try:
            imp = registry.create(tur)
        except KeyError:
            raise FormatError(
                f"Bilinmeyen içe aktarıcı türü: {tur}. Kullanılabilir: {', '.join(registry.names())}"
            ) from None
    else:
        imp, results = registry.detect_best(path)
        if imp is None:
            lines = "\n".join(f"  - {n}: {d.reason}" for n, d in results)
            raise FormatError(f"{_taninmama_mesaji(path)}\n\nTeknik ayrıntı (dosya hiçbir içe aktarıcıyla tanınmadı; her birinin nedeni):\n{lines}")

    try:
        return _run_with(hub, path, imp, yine_de, notify, progress)
    finally:
        close = getattr(imp, "close", None)
        if close:
            close()


def _run_with(hub, path, imp, yine_de, notify, progress) -> RunResult:
    # 2) verify_format (ok değilse durur, hiçbir şey yazılmaz)
    report = imp.verify_format(path)
    if not report.ok:
        raise ImportFormatError(report)

    # 3) previously_purged
    origins = imp.input_files(path)
    hashes = {o.path: sha256_file(o.path) for o in origins}
    # Ham arşive kopyalanmayan kaynaklar (ör. yerinde kalan bilgisayar dosyaları) kendi özetini verir.
    own_sha = getattr(imp, "source_sha", None)
    total_sha = own_sha(path) if own_sha else _combined_sha(path, origins, hashes)
    if not yine_de:
        for sha in [total_sha, *hashes.values()]:
            prev = hub.previously_purged(sha)
            if prev:
                raise FormatError(
                    f"Bu girdiyi {prev.purged_at} tarihinde kalıcı sildiniz ({prev.count} kayıt). "
                    "Yine de almak için --yine-de ekleyin."
                )

    # 4) add_source, 5) store_raw
    source_id = hub.add_source(imp.name, imp.version, total_sha)
    notify("kopyala", 0)
    raws: list[RawFile] = []
    with tempfile.TemporaryDirectory(prefix="kimlikimport-") as td:
        for o in origins:
            src = o.path if o.is_zip or o.path == path else _flat_link(Path(td), o)
            raws.append(hub.store_raw(source_id, src))

    # 6) parse -> 7) add_events
    counter = [0]
    res = hub.add_events(source_id, _counting(imp.parse(path), counter, progress))
    notify("isle", counter[0])
    return RunResult(
        importer=imp.name, source_id=source_id, parsed=counter[0], added=res.added,
        duplicate=res.duplicate, raw_files=raws, report=report, skipped=imp.skipped_counts(),
    )
