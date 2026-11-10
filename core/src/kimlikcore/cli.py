"""Komut satırı: `kimlikmerkezi`. Çıktı Türkçe; `--json` ile makine okur."""
from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import __version__
from .errors import (
    FormatError,
    HubLockedError,
    HubNotEmptyError,
    HubNotFoundError,
    KimlikError,
    NotFoundError,
    SchemaTooNew,
    SchemaTooOld,
)
from .hub import Hub
from .models import Category, Event
from .schema import SCHEMA_VERSION
from .streaming import iter_event_jsonl, sha256_file

EXIT_OK, EXIT_ERROR, EXIT_LOCKED = 0, 1, 3


def default_root() -> Path:
    env = os.environ.get("KIMLIK_VERI")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "KimlikMerkezi"
    return Path.home() / ".local" / "share" / "kimlikmerkezi"


def _out(args: argparse.Namespace, data: Any, text: str) -> None:
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(text)


def _event_line(e: Event) -> str:
    return f"{e.ts}  [{e.category}] {e.kind}  {e.text[:100]}  ({e.event_id})"


def cmd_baslat(args):
    with Hub.open(args.veri, write=True) as hub:
        _out(args, {"veri": str(args.veri), "sema_surumu": hub.schema_version},
             f"Veri klasörü hazır: {args.veri}\nŞema sürümü: {hub.schema_version}")


def cmd_surum(args):
    info = {"kimlikcore": __version__, "sema_surumu": SCHEMA_VERSION, "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version, "sistem": platform.platform()}
    _out(args, info, "\n".join(f"{k}: {v}" for k, v in info.items()))


def _run_importer(hub: Hub, args: argparse.Namespace, path: Path) -> None:
    """kimlikimport çalıştırıcısı: tanıma, doğrulama, daha önce silinmiş mi sorgusu ve içe alma
    orada yapılır (burada ikinci kez kontrol edilmez)."""
    try:
        from kimlikimport.run import run
    except ImportError as e:
        raise FormatError(
            f"İçe aktarıcı paketi (kimlikimport) yüklenemedi ({e.name}). "
            "Dahili 'jsonl' türü için --tur jsonl kullanın."
        ) from e
    tur = None if args.tur in (None, "auto") else args.tur
    result = run(hub, path, tur=tur, yine_de=args.yine_de)
    data: dict[str, Any] = {"sonuc": str(result)}
    for name in ("importer", "source_id", "parsed", "added", "duplicate", "skipped"):
        if hasattr(result, name):
            data[name] = getattr(result, name)
    if hasattr(result, "raw_files"):
        data["raw_files"] = [r.path for r in result.raw_files]
    _out(args, data, f"İçe alındı:\n{result}")


def _run_jsonl(hub: Hub, args: argparse.Namespace, path: Path) -> None:
    if not path.is_file():
        raise FormatError(f"'jsonl' türü bir dosya ister: {path}")
    sha = sha256_file(path)
    prev = hub.previously_purged(sha)
    if prev and not args.yine_de:
        raise FormatError(
            f"Bu girdiyi {prev.purged_at} tarihinde kalıcı sildiniz ({prev.count} kayıt). "
            "Yine de almak için --yine-de ekleyin."
        )
    sid = hub.add_source("jsonl", "1", sha)
    raw = hub.store_raw(sid, path)
    res = hub.add_events(sid, iter_event_jsonl(path))
    _out(args, {"kaynak": sid, "eklenen": res.added, "tekrar": res.duplicate, "arsiv": raw.path},
         f"Kaynak: {sid}\nEklenen: {res.added}  Zaten vardı: {res.duplicate}\nHam arşiv: {raw.path}")


def cmd_ice_al(args):
    path = Path(args.yol)
    if not path.exists():
        raise FormatError(f"Girdi yok: {path}")
    with Hub.open(args.veri, write=True) as hub:
        if args.tur == "jsonl":
            _run_jsonl(hub, args, path)
        else:
            _run_importer(hub, args, path)


def cmd_tanila(args):
    """Dışa aktarma dosyasının yapısını (içeriksiz) raporlar; ağa bağlanmaz."""
    path = Path(args.yol)
    if not path.exists():
        raise FormatError(f"Girdi yok: {path}")
    try:
        from kimlikimport.tanila import tanila
    except ImportError as e:
        raise FormatError(f"İçe aktarıcı paketi (kimlikimport) yüklenemedi ({e.name}).") from e
    text = tanila(path, adlari_goster=args.adlari_goster, ayrinti=args.ayrinti)
    _out(args, {"rapor": text}, text)


def cmd_ara(args):
    with Hub.open(args.veri, write=False) as hub:
        found = hub.search(args.sorgu, categories=args.kategori, limit=args.limit, prefix=args.onek)
    _out(args, [e.to_dict() for e in found],
         "\n".join(_event_line(e) for e in found) or "Sonuç yok.")


def cmd_zaman(args):
    with Hub.open(args.veri, write=False) as hub:
        found = hub.timeline(categories=args.kategori, since=args.baslangic, until=args.bitis,
                             limit=args.limit, offset=args.atla)
    _out(args, [e.to_dict() for e in found],
         "\n".join(_event_line(e) for e in found) or "Kayıt yok.")


def cmd_kaynaklar(args):
    with Hub.open(args.veri, write=False) as hub:
        srcs = hub.sources()
    rows = [asdict(s) for s in srcs]
    lines = [f"{s.source_id}  {s.kind}  {s.imported_at}  kayıt={s.event_count}"
             + ("  KALDIRILDI" if s.removed_at else "") for s in srcs]
    _out(args, rows, "\n".join(lines) or "Kaynak yok.")


def cmd_ozet(args):
    with Hub.open(args.veri, write=False) as hub:
        s = hub.summary()
    _out(args, s, "\n".join(f"{t}: {n}" for t, n in s["counts"].items()))


def cmd_disa_aktar(args):
    with Hub.open(args.veri, write=False) as hub:
        r = hub.export_jsonl(args.dosya)
    _out(args, {"dosya": r.path, "kayitlar": r.counts, "bayt": r.bytes, "sha256": r.sha256},
         f"Dışa aktarıldı: {r.path}\nOlay: {r.counts['event']}  Kaynak: {r.counts['source']}\nSHA-256: {r.sha256}")


def cmd_ice_aktar(args):
    with Hub.open(args.veri, write=True) as hub:
        r = hub.import_jsonl(args.dosya)
    msg = f"Geri yüklendi. Olay: {r.counts['event']}  Kaynak: {r.counts['source']}\nDoğrulama: " + (
        "tamam" if r.verified else "yapılamadı (şema sürümü farklı)")
    if r.raw_missing:
        msg += f"\nUyarı: {r.raw_missing} ham dosya bu klasörde yok; 'arsiv' klasörünü de kopyalayın."
    _out(args, {"kayitlar": r.counts, "ham_eksik": r.raw_missing, "dogrulandi": r.verified}, msg)


def cmd_kaynak_kaldir(args):
    with Hub.open(args.veri, write=True) as hub:
        n = hub.remove_source(args.kaynak, args.neden)
    _out(args, {"gizlenen": n}, f"Kaynak kaldırıldı; {n} kayıt gizlendi.")


def cmd_kaynak_sil(args):
    if not args.onayla:
        if sys.stdin.isatty():
            print("Bu işlem GERİ ALINAMAZ: kaynağın kayıtları ve ham dosyası kalıcı silinir.")
            try:
                yanit = input("Devam için SIL yazın: ").strip()
            except (EOFError, OSError):
                raise FormatError(
                    "Onay okunamadı (girdi kapalı); hiçbir şey silinmedi. Kalıcı silme için --onayla kullanın."
                ) from None
            if yanit != "SIL":
                raise FormatError("Onaylanmadı; hiçbir şey silinmedi.")
        else:
            raise FormatError("Kalıcı silme için --onayla gerekir.")
    with Hub.open(args.veri, write=True) as hub:
        r = hub.purge_source(args.kaynak)
        hub.compact()
    _out(args, {"silinen_kayit": r.events_deleted, "silinen_dosya": r.raw_files_deleted,
                "persona_eskimis": r.facts_demoted},
         f"Kalıcı silindi: {r.events_deleted} kayıt, {r.raw_files_deleted} ham dosya.")


def cmd_kayit_gizle(args):
    with Hub.open(args.veri, write=True) as hub:
        hub.hide_event(args.kayit, args.neden)
    _out(args, {"gizlendi": args.kayit}, "Kayıt gizlendi.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kimlikmerkezi", description="Kimlik Merkezi komut satırı")
    p.add_argument("--veri", type=Path, default=None, help="veri klasörü (varsayılan: KIMLIK_VERI ya da kullanıcı klasörü)")
    p.add_argument("--json", action="store_true", help="çıktıyı JSON olarak ver")
    sub = p.add_subparsers(dest="komut", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    add("baslat", cmd_baslat, "veri klasörünü (hub) oluşturur/günceller")
    add("surum", cmd_surum, "sürüm bilgisi")
    sp = add("ice-al", cmd_ice_al, "dosyayı içe alır")
    sp.add_argument("yol")
    sp.add_argument("--tur", default="auto", help="auto (varsayılan: otomatik tanıma), jsonl (dahili) ya da içe aktarıcı adı")
    sp.add_argument("--yine-de", action="store_true", help="daha önce kalıcı silinmiş dosyayı yine de al")
    sp = add("tanila", cmd_tanila, "dışa aktarma dosyasının yapı raporu (içerik yazmaz; ağa bağlanmaz)")
    sp.add_argument("yol", help="dışa aktarma dosyası ya da klasörü (zip, tar.gz, json, csv, mbox, sqlite...)")
    sp.add_argument("--adlari-goster", action="store_true",
                    help="dosya/klasör adlarını maskelemeden yaz (kişi adı içerebilir; bilerek seç)")
    sp.add_argument("--ayrinti", action="store_true", help="tüm alan ağacını ve daha çok dosyayı yaz (uzun çıktı)")
    sp = add("ara", cmd_ara, "ara")
    sp.add_argument("sorgu")
    sp.add_argument("--kategori", action="append", choices=sorted(Category.ALL))
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--onek", action="store_true", help="her terimi önek olarak ara")
    sp = add("zaman", cmd_zaman, "zaman çizelgesi (yeniden eskiye)")
    sp.add_argument("--kategori", action="append", choices=sorted(Category.ALL))
    sp.add_argument("--baslangic")
    sp.add_argument("--bitis")
    sp.add_argument("--limit", type=int, default=100)
    sp.add_argument("--atla", type=int, default=0)
    add("kaynaklar", cmd_kaynaklar, "kaynakları listeler")
    add("ozet", cmd_ozet, "kayıt sayıları (dışa/içe aktarım karşılaştırması için)")
    sp = add("disa-aktar", cmd_disa_aktar, "JSON Lines olarak dışa aktarır")
    sp.add_argument("dosya", type=Path)
    sp = add("ice-aktar", cmd_ice_aktar, "dışa aktarılan dosyayı BOŞ veri klasörüne geri yükler")
    sp.add_argument("dosya", type=Path)
    sp = add("kaynak-kaldir", cmd_kaynak_kaldir, "kaynağın kayıtlarını gizler")
    sp.add_argument("kaynak")
    sp.add_argument("--neden", default="")
    sp = add("kaynak-sil", cmd_kaynak_sil, "kaynağı KALICI siler (geri alınamaz)")
    sp.add_argument("kaynak")
    sp.add_argument("--onayla", action="store_true")
    sp = add("kayit-gizle", cmd_kayit_gizle, "tek kaydı gizler")
    sp.add_argument("kayit")
    sp.add_argument("--neden", default="")
    return p


def _utf8_streams() -> None:
    """Borulanmış/yönlendirilmiş çıktı yerel kodlamaya (Windows'ta cp1252) bağlı kalmasın.
    Etkileşimli konsola dokunulmaz."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if not stream.isatty():
                stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _utf8_streams()
    args = build_parser().parse_args(argv)
    if args.veri is None:
        args.veri = default_root()
    try:
        args.fn(args)
        return EXIT_OK
    except HubLockedError as e:
        print(f"Hata: {e}", file=sys.stderr)
        return EXIT_LOCKED
    except HubNotFoundError:
        print(f"Hata: veri klasörü bulunamadı ({args.veri}). Önce 'kimlikmerkezi baslat' çalıştırın.", file=sys.stderr)
        return EXIT_ERROR
    except (SchemaTooNew, SchemaTooOld, FormatError, HubNotEmptyError, NotFoundError, KimlikError) as e:
        print(f"Hata: {e}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as e:
        print(f"Hata (dosya): {e.strerror or e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
