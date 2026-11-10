"""Reddit hesap veri isteği (zip içinde CSV dosyaları) içe aktarıcısı. Reddit API'si kullanılmaz.

DOĞRULANMADI: Reddit'in resmî yardım sayfasına bu ortamdan erişilemedi (ağ kısıtı); dosya ve sütun
adları ikincil kaynaklardan ve bilgiden alındı, gerçek bir arşivle sınanmadı (durum/importers.md).
Bu yüzden: sütunlar başlık adıyla okunur (sıra önemsiz), eksik zorunlu sütun ya da başlığı
tanınmayan dosya sessizce okunmaz, rapora yazılır.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from kimlikcore import Category, EventIn, FormatError

from .base import (
    Archive,
    open_archive,
    DetectResult,
    Entry,
    FormatReport,
    Origin,
    csv_header,
    csv_rows,
    iso_utc,
    stable_key,
)

NAME = "reddit"
VERSION = "0.1.0"


class _Spec:
    def __init__(self, kind, category, required, known, text_cols, key_cols, ts_col=None, note=""):
        self.kind, self.category = kind, category
        self.required, self.known = set(required), set(known)
        self.text_cols, self.key_cols, self.ts_col, self.note = text_cols, key_cols, ts_col, note


# Dosya adı (küçük harf) -> belirtim. `ip` sütunu bilerek okunmaz (gizlilik).
_SPECS: dict[str, _Spec] = {
    "comments.csv": _Spec(
        "reddit.yorum", Category.SOSYAL, {"id", "permalink", "date", "body"},
        {"id", "permalink", "date", "ip", "subreddit", "gildings", "link", "parent", "body", "media"},
        ["body", "subreddit"], ["id"], "date"),
    "posts.csv": _Spec(
        "reddit.gonderi", Category.SOSYAL, {"id", "permalink", "date", "title"},
        {"id", "permalink", "date", "ip", "subreddit", "gildings", "title", "url", "body"},
        ["title", "body", "subreddit"], ["id"], "date"),
    "messages.csv": _Spec(
        "reddit.mesaj", Category.MESAJ, {"id", "date", "body"},
        {"id", "permalink", "thread_id", "date", "ip", "from", "to", "subject", "body"},
        ["subject", "body", "from", "to"], ["id"], "date"),
    "chat_history.csv": _Spec(
        "reddit.sohbet", Category.MESAJ, {"message_id", "created_at", "message"},
        {"message_id", "created_at", "updated_at", "username", "message", "thread_parent_message_id",
         "channel_url", "subreddit", "channel_name", "conversation_type"},
        ["message", "username", "channel_name"], ["message_id"], "created_at"),
    # Tarihi olmayan anlık durum dosyaları: zaman = arşiv dosyasının tarihi (payload'da işaretli).
    "post_votes.csv": _Spec(
        "reddit.oy", Category.SOSYAL, {"id", "direction"}, {"id", "permalink", "direction"},
        ["permalink", "direction"], ["id", "direction"], None),
    "comment_votes.csv": _Spec(
        "reddit.oy", Category.SOSYAL, {"id", "direction"}, {"id", "permalink", "direction"},
        ["permalink", "direction"], ["id", "direction"], None),
    "saved_posts.csv": _Spec(
        "reddit.kaydedilen", Category.SOSYAL, {"id"}, {"id", "permalink"},
        ["permalink"], ["id"], None),
    "saved_comments.csv": _Spec(
        "reddit.kaydedilen", Category.SOSYAL, {"id"}, {"id", "permalink"},
        ["permalink"], ["id"], None),
    "subscribed_subreddits.csv": _Spec(
        "reddit.abone", Category.SOSYAL, {"subreddit"}, {"subreddit"},
        ["subreddit"], ["subreddit"], None),
}
# messages_archive.csv: eski özel mesajlar, messages.csv ile aynı sütunlar (ikincil bilgi, DOĞRULANMADI)
_SPECS["messages_archive.csv"] = _SPECS["messages.csv"]
# Bilinen ama bilerek işlenmeyenler (gizlilik/anlamsızlık): rapora yazılır.
_SKIPPED_BY_DESIGN = {
    "ip_logs.csv": "IP kayıtları, bilerek alınmıyor (gizlilik)",
    "statistics.csv": "özet istatistik, olay değil",
}


def _spec_for(e: Entry) -> _Spec | None:
    return _SPECS.get(e.basename.lower())


class Reddit:
    name = NAME
    version = VERSION

    def __init__(self) -> None:
        self._cache: dict[str, tuple[Archive, list, list]] = {}
        self._skipped: Counter[str] = Counter()

    def _scan(self, path: Path):
        key = str(Path(path).resolve())
        if key not in self._cache:
            arc = open_archive(Path(path))
            good, bad = [], []  # good: (entry, spec, header); bad: (entry, neden)
            for e in arc.entries:
                spec = _spec_for(e)
                if spec is None:
                    continue
                hdr = csv_header(e)
                if hdr is None:
                    bad.append((e, "başlık satırı okunamadı (boş ya da UTF-8 değil)"))
                    continue
                missing = sorted(spec.required - set(hdr))
                if missing:
                    bad.append((e, "zorunlu sütun yok: " + ", ".join(missing)))
                else:
                    good.append((e, spec, hdr))
            self._cache = {key: (arc, good, bad)}
        return self._cache[key]

    def detect(self, path: Path) -> DetectResult:
        try:
            arc, good, bad = self._scan(path)
        except FormatError as e:
            return DetectResult(False, 0.0, str(e))
        if good:
            conf = min(0.95, 0.5 + 0.15 * len(good))
            return DetectResult(True, conf, f"{len(good)} Reddit CSV dosyası başlıklarıyla eşleşti")
        if bad:
            return DetectResult(True, 0.4, "Reddit dosya adları var ama sütunlar beklenenle uyuşmuyor")
        return DetectResult(False, 0.0, "Reddit CSV dosyası bulunamadı")

    def verify_format(self, path: Path) -> FormatReport:
        arc, good, bad = self._scan(path)
        rep = FormatReport(importer=NAME, ok=bool(good) and not arc.bad_zips)
        for e, spec, hdr in good:
            rep.found_files.append(f"{e.name} ({e.size} bayt) -> {spec.kind}")
            extra = [c for c in hdr if c not in spec.known]
            rep.unexpected_fields += [f"{e.name}: {c}" for c in extra]
        for e, why in bad:
            rep.missing.append(f"{e.name}: {why}")
        for b in arc.bad_zips:
            rep.missing.append(f"{b}: zip dosyası okunamadı (bozuk ya da eksik indirme)")
        if not good:
            rep.missing.append(
                "Reddit CSV dosyaları (comments.csv, posts.csv, ...) beklenen sütunlarla bulunamadı"
            )
        names_good = {e.basename.lower() for e, _, _ in good}
        for e in arc.entries:
            b = e.basename.lower()
            if b in _SKIPPED_BY_DESIGN:
                rep.unsupported.append(f"{e.name}: {_SKIPPED_BY_DESIGN[b]}")
            elif b.endswith(".csv") and b not in _SPECS:
                rep.unsupported.append(f"{e.name}: tanınmayan Reddit dosyası, bu sürümde işlenmiyor")
        if names_good & {"post_votes.csv", "comment_votes.csv", "saved_posts.csv",
                         "saved_comments.csv", "subscribed_subreddits.csv"}:
            rep.notes.append(
                "Tarihi olmayan dosyalarda (oylar, kaydedilenler, abonelikler) olay zamanı "
                "arşiv dosyasının tarihidir (payload'da zaman_kaynagi=dosya_tarihi)"
            )
        rep.notes.append("ip sütunları bilerek okunmuyor")
        return rep

    def input_files(self, path: Path) -> list[Origin]:
        _, good, _ = self._scan(path)
        seen: dict[Path, Origin] = {}
        for e, _, _ in good:
            seen.setdefault(e.origin.path, e.origin)
        return list(seen.values())

    def skipped_counts(self) -> dict[str, int]:
        return dict(self._skipped)

    def parse(self, path: Path) -> Iterator[EventIn]:
        _, good, _ = self._scan(path)
        for e, spec, _ in good:
            yield from self._parse_file(e, spec)

    def _parse_file(self, e: Entry, spec: _Spec) -> Iterator[EventIn]:
        fname = e.basename.lower()
        snapshot_ts = iso_utc(e.mtime)
        try:
            for row in csv_rows(e):
                if spec.ts_col:
                    ts = iso_utc(row.get(spec.ts_col) or "")
                    if ts is None:
                        self._skipped[f"{fname}: {spec.ts_col} okunamadı"] += 1
                        continue
                    snap = False
                else:
                    ts, snap = snapshot_ts, True
                keyvals = [(row.get(c) or "").strip() for c in spec.key_cols]
                if not all(keyvals):
                    self._skipped[f"{fname}: kimlik alanı boş"] += 1
                    continue
                payload = {c: row[c] for c in spec.known if c in row and c != "ip" and row[c] not in (None, "")}
                if snap:
                    payload["zaman_kaynagi"] = "dosya_tarihi"
                text = " ".join((row.get(c) or "").strip() for c in spec.text_cols).strip()
                yield EventIn(
                    ts=ts, kind=spec.kind, category=spec.category, payload=payload, text=text,
                    event_key=stable_key("rd", spec.kind, *keyvals),
                )
        except UnicodeDecodeError:
            raise FormatError(f"{e.name}: dosya UTF-8 değil; önceki kayıtlar eklendi.") from None
        except Exception as exc:  # csv.Error vb.; içerik sızdırmadan
            if exc.__class__.__module__ == "_csv":
                raise FormatError(f"{e.name}: CSV bozuk ({type(exc).__name__}).") from None
            raise


def factory() -> Reddit:
    return Reddit()
