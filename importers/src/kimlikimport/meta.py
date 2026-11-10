"""Instagram / Facebook hesap verisi (Meta "Bilgilerini indir", JSON biçimi) içe aktarıcısı.

DOĞRULANMADI: Meta'nın yardım sayfalarına bu ortamdan erişilemedi; dosya/alan adları ikincil
bilgiden ve hafızadan. Bu yüzden dosya ADINA değil İÇERİK ŞEKLİNE bakılır (üst anahtar adı, kayıt
alanları); tanınmayan JSON sayılıp rapora yazılır. Meta'nın bilinen mojibake sorunu (UTF-8 baytları
latin-1 sanılıp kaçışlanmış) metinlerde düzeltilir.

Eşleme: gönderi/beğeni/yorum/takip/arkadaş/kaydedilen -> `sosyal`; mesajlar -> `mesaj` (hassas);
gönderi EXIF/yer koordinatları ayrı `konum` olayı.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import ijson
from kimlikcore import Category, EventIn, FormatError

from .base import (
    DetectResult,
    Entry,
    FormatReport,
    Origin,
    ScanImporter,
    epoch_to_iso,
    fix_tree,
    peek,
    stable_key,
    strip_bom,
)

NAME = "meta"

# Üst anahtar -> (şekil, tür kısa adı). Anahtar adları hafızadan; bilinmeyen anahtar için içerik
# şekli (string_list_data) bakılır.
_TOP = {
    "likes_media_likes": ("string_list", "begeni"),
    "likes_comment_likes": ("string_list", "begeni"),
    "relationships_following": ("string_list", "takip"),
    "relationships_followers": ("string_list", "takipci"),
    "saved_saved_media": ("string_list", "kaydedilen"),
    "comments_media_comments": ("string_list", "yorum"),
    "comments_reels_comments": ("string_list", "yorum"),
    "comments_v2": ("fb_comments", "yorum"),
    "reactions_v2": ("fb_reactions", "tepki"),
    "friends_v2": ("fb_friends", "arkadas"),
}
_KNOWN = {
    "string_list": {"title", "media_list_data", "string_list_data"},
    "string_map": {"string_map_data", "title", "media_list_data"},
    "ig_posts": {"media", "title", "creation_timestamp"},
    "fb_posts": {"timestamp", "data", "title", "attachments", "tags", "event"},
    "fb_comments": {"timestamp", "data", "title", "attachments"},
    "fb_reactions": {"timestamp", "data", "title"},
    "fb_friends": {"name", "timestamp", "contact_info"},
    "messages": {"sender_name", "timestamp_ms", "content", "type", "share", "photos", "videos",
                 "audio_files", "reactions", "is_geoblocked_for_viewer", "is_unsent", "sticker",
                 "call_duration", "gifs", "files", "missed", "ip", "bumped_message_metadata"},
}
_FIRST_KEY = re.compile(rb'^\s*\{\s*"([^"]+)"\s*:')
_SAMPLE = 100


def _slug(key: str) -> str:
    k = key.lower()
    for a, b in (("like", "begeni"), ("follower", "takipci"), ("following", "takip"),
                 ("comment", "yorum"), ("saved", "kaydedilen"), ("friend", "arkadas")):
        if a in k:
            return b
    return "kayit"


def _platform(entry_name: str, hrefs: str = "") -> str:
    n = entry_name.lower()
    h = hrefs.lower()
    if "instagram" in n or "instagram.com" in h:
        return "instagram"
    if "facebook" in n or "facebook.com" in h:
        return "facebook"
    return ""


def _first_item(entry: Entry, prefix: str):
    with entry.open() as raw:
        return next(ijson.items(strip_bom(raw), prefix, use_float=True), None)


def _classify(entry: Entry, sc: "_Scan") -> None:
    if not entry.name.lower().endswith(".json"):
        if entry.name.lower().endswith((".html", ".htm")) and any(
            x in entry.name.lower() for x in ("instagram", "facebook")
        ):
            sc.html += 1
        return
    head = peek(entry)
    s = head.lstrip()
    try:
        if s.startswith(b"{"):
            m = _FIRST_KEY.match(head)
            if not m:
                sc.ignored += 1
                return
            key = m.group(1).decode("utf-8", "replace")
            if key in ("participants", "messages"):
                sc.add("messages", entry, "messages", "mesaj")
            elif key in _TOP:
                shape, slug = _TOP[key]
                sc.add(shape, entry, key, slug)
            else:
                rec = _first_item(entry, f"{key}.item")
                if isinstance(rec, dict) and "string_list_data" in rec:
                    sc.add("string_list", entry, key, _slug(key))
                else:
                    sc.ignored += 1
        elif s.startswith(b"["):
            rec = _first_item(entry, "item")
            if rec is None:
                sc.empty.append(entry)
            elif isinstance(rec, dict) and "string_list_data" in rec:
                sc.add("string_list", entry, "", _slug(entry.basename))
            elif isinstance(rec, dict) and "string_map_data" in rec:
                sc.add("string_map", entry, "", _slug(entry.basename))
            elif isinstance(rec, dict) and isinstance(rec.get("media"), list):
                sc.add("ig_posts", entry, "", "gonderi")
            elif isinstance(rec, dict) and "timestamp" in rec and isinstance(rec.get("data"), list):
                sc.add("fb_posts", entry, "", "gonderi")
            else:
                sc.ignored += 1
        else:
            sc.ignored += 1
    except (ijson.JSONError, UnicodeDecodeError, OSError):
        sc.corrupt.append(entry.name)


class _Scan:
    def __init__(self) -> None:
        self.files: list[tuple[str, Entry, str, str]] = []  # (şekil, girdi, üst anahtar, tür)
        self.empty: list[Entry] = []
        self.corrupt: list[str] = []
        self.ignored = 0
        self.html = 0
        self.bad_zips: list[str] = []

    def add(self, shape: str, entry: Entry, key: str, slug: str) -> None:
        self.files.append((shape, entry, key, slug))


class Meta(ScanImporter):
    name = NAME

    def _do_scan(self, arc) -> _Scan:
        sc = _Scan()
        sc.bad_zips = arc.bad_zips
        for e in arc.entries:
            _classify(e, sc)
        return sc

    def detect(self, path: Path) -> DetectResult:
        try:
            _, sc = self._scan(path)
        except FormatError as e:
            return DetectResult(False, 0.0, str(e))
        if sc.files:
            hinted = any(_platform(e.name) for _, e, _, _ in sc.files)
            return DetectResult(True, 0.9 if hinted else 0.7,
                                f"{len(sc.files)} Instagram/Facebook JSON dosyası tanındı")
        if sc.html:
            return DetectResult(True, 0.6, "Instagram/Facebook HTML biçimi (JSON gerekli)")
        return DetectResult(False, 0.0, "Instagram/Facebook JSON içeriği bulunamadı")

    def verify_format(self, path: Path) -> FormatReport:
        _, sc = self._scan(path)
        rep = FormatReport(importer=NAME, ok=bool(sc.files) and not sc.corrupt and not sc.bad_zips)
        for shape, e, _, slug in sc.files:
            rep.found_files.append(f"{shape}/{slug}: {e.name} ({e.size} bayt)")
            try:
                extra = self._sample_extra(shape, e, sc)
            except (ijson.JSONError, UnicodeDecodeError):
                rep.ok = False
                rep.missing.append(f"{e.name}: JSON baştan okunamadı (bozuk)")
                continue
            rep.unexpected_fields += [f"{e.name}: {k}" for k in sorted(extra)]
        for c in sc.corrupt:
            rep.missing.append(f"{c}: bozuk JSON")
        for b in sc.bad_zips:
            rep.missing.append(f"{b}: zip dosyası okunamadı (bozuk ya da eksik indirme)")
        if not sc.files:
            rep.missing.append("Instagram/Facebook JSON içeriği (beğeniler, yorumlar, gönderiler, mesajlar...) bulunamadı")
        if sc.html and not sc.files:
            rep.unsupported.append(f"{sc.html} HTML dosyası: HTML biçimi desteklenmez, indirirken JSON seçin")
        if sc.ignored:
            rep.notes.append(f"{sc.ignored} JSON dosyası tanınan bir şekle uymadığı için yok sayıldı")
        for e in sc.empty:
            rep.notes.append(f"{e.name}: boş JSON dizisi")
        rep.notes.append("Metinlerdeki Meta mojibake sorunu (UTF-8/latin-1) düzeltilir")
        return rep

    def _sample_extra(self, shape: str, e: Entry, sc) -> set[str]:
        known = _KNOWN.get(shape)
        if not known:
            return set()
        prefix = self._prefix(shape, e, sc)
        extra: set[str] = set()
        with e.open() as raw:
            for n, rec in enumerate(ijson.items(strip_bom(raw), prefix, use_float=True)):
                if n >= _SAMPLE:
                    break
                if isinstance(rec, dict):
                    extra |= set(rec) - known
        return extra

    def _prefix(self, shape: str, e: Entry, sc) -> str:
        for sh, en, key, _ in sc.files:
            if en is e:
                return "messages.item" if shape == "messages" else (f"{key}.item" if key else "item")
        return "item"

    def input_files(self, path: Path) -> list[Origin]:
        _, sc = self._scan(path)
        seen: dict[Path, Origin] = {}
        for _, e, _, _ in sc.files:
            seen.setdefault(e.origin.path, e.origin)
        return list(seen.values())

    # ------------------------------------------------------------------ ayrıştırma
    def parse(self, path: Path) -> Iterator[EventIn]:
        _, sc = self._scan(path)
        for shape, e, key, slug in sc.files:
            prefix = "messages.item" if shape == "messages" else (f"{key}.item" if key else "item")
            n = 0
            try:
                with e.open() as raw:
                    for rec in ijson.items(strip_bom(raw), prefix, use_float=True):
                        n += 1
                        if not isinstance(rec, dict):
                            self._skip(f"{shape}: kayıt nesne değil")
                            continue
                        yield from self._events(shape, slug, e, fix_tree(rec))
            except (ijson.JSONError, UnicodeDecodeError) as exc:
                raise FormatError(
                    f"{e.name}: JSON {n}. kayıttan sonra bozuk ({type(exc).__name__}). "
                    "Önceki kayıtlar eklendi; dosya düzeldikten sonra yeniden alın."
                ) from None

    def _events(self, shape: str, slug: str, e: Entry, rec: dict) -> Iterator[EventIn]:
        fn = getattr(self, f"_ev_{shape}")
        yield from fn(slug, e, rec)

    # --- string_list_data (beğeni, takip, takipçi, kaydedilen, eski yorum)
    def _ev_string_list(self, slug, e, rec):
        title = rec.get("title") or ""
        for d in rec.get("string_list_data") or []:
            if not isinstance(d, dict):
                continue
            ts = epoch_to_iso(d.get("timestamp"))
            if ts is None:
                self._skip("string_list_data: timestamp yok")
                continue
            href, value = d.get("href") or "", d.get("value") or ""
            plat = _platform(e.name, href) or "meta"
            kind = f"{plat}.{slug}"
            payload = {"baslik": title, "deger": value, "baglanti": href}
            text = value if slug == "yorum" and value else " ".join(x for x in (title, value, href) if x)
            yield EventIn(ts=ts, kind=kind, category=Category.SOSYAL, payload=payload, text=text,
                          event_key=stable_key("meta", kind, d.get("timestamp"), title, value, href))

    # --- string_map_data (yeni Instagram yorum listeleri)
    def _ev_string_map(self, slug, e, rec):
        m = rec.get("string_map_data") or {}
        ts = None
        for k, v in m.items():
            if isinstance(v, dict) and v.get("timestamp"):
                ts = epoch_to_iso(v["timestamp"])
                break
        if ts is None:
            self._skip("string_map_data: zaman yok")
            return
        vals = {k: (v.get("value") if isinstance(v, dict) else None) for k, v in m.items()}
        plat = _platform(e.name) or "instagram"
        kind = f"{plat}.{slug}"
        text = vals.get("Comment") or " ".join(str(x) for x in vals.values() if x)
        yield EventIn(ts=ts, kind=kind, category=Category.SOSYAL, payload={"alanlar": vals}, text=text,
                      event_key=stable_key("meta", kind, ts, *sorted((k, str(v)) for k, v in vals.items())))

    # --- Instagram gönderileri
    def _ev_ig_posts(self, slug, e, rec):
        media = [x for x in rec.get("media") or [] if isinstance(x, dict)]
        ts = epoch_to_iso(rec.get("creation_timestamp")) or next(
            (t for t in (epoch_to_iso(x.get("creation_timestamp")) for x in media) if t), None)
        if ts is None:
            self._skip("ig_posts: creation_timestamp yok")
            return
        caption = rec.get("title") or next((x.get("title") for x in media if x.get("title")), "") or ""
        uris = [x.get("uri") for x in media if x.get("uri")]
        kind = f"{_platform(e.name) or 'instagram'}.gonderi"
        key = stable_key("meta", kind, ts, caption, *uris)
        yield EventIn(ts=ts, kind=kind, category=Category.SOSYAL,
                      payload={"baslik": caption, "medya": uris}, text=caption, event_key=key)
        coords = _find_coords(media)
        if coords:
            yield EventIn(ts=ts, kind="meta.konum", category=Category.KONUM, event_key=key + ":konum",
                          payload={"kaynak": kind, "koordinatlar": coords}, text=caption)

    # --- Facebook gönderileri
    def _ev_fb_posts(self, slug, e, rec):
        ts = epoch_to_iso(rec.get("timestamp"))
        if ts is None:
            self._skip("fb_posts: timestamp yok")
            return
        posts = [d.get("post") for d in rec.get("data") or [] if isinstance(d, dict) and d.get("post")]
        title = rec.get("title") or ""
        text = "\n".join(posts) or title
        uris = [d.get("media", {}).get("uri") for a in rec.get("attachments") or []
                for d in (a.get("data") or []) if isinstance(d, dict) and isinstance(d.get("media"), dict)
                and d["media"].get("uri")]
        kind = f"{_platform(e.name) or 'facebook'}.gonderi"
        key = stable_key("meta", kind, rec.get("timestamp"), title, text)
        yield EventIn(ts=ts, kind=kind, category=Category.SOSYAL,
                      payload={"baslik": title, "gonderi": posts, "medya": uris}, text=text, event_key=key)
        coords = _find_coords(rec.get("attachments"))
        if coords:
            yield EventIn(ts=ts, kind="meta.konum", category=Category.KONUM, event_key=key + ":konum",
                          payload={"kaynak": kind, "koordinatlar": coords}, text=title)

    def _ev_fb_comments(self, slug, e, rec):
        ts = epoch_to_iso(rec.get("timestamp"))
        c = next((d.get("comment") for d in rec.get("data") or []
                  if isinstance(d, dict) and isinstance(d.get("comment"), dict)), {})
        if ts is None:
            self._skip("fb_comments: timestamp yok")
            return
        text = c.get("comment") or ""
        kind = "facebook.yorum"
        yield EventIn(ts=ts, kind=kind, category=Category.SOSYAL,
                      payload={"baslik": rec.get("title"), "yorum": text, "yazar": c.get("author")},
                      text=text or rec.get("title") or "",
                      event_key=stable_key("meta", kind, rec.get("timestamp"), text))

    def _ev_fb_reactions(self, slug, e, rec):
        ts = epoch_to_iso(rec.get("timestamp"))
        r = next((d.get("reaction") for d in rec.get("data") or []
                  if isinstance(d, dict) and isinstance(d.get("reaction"), dict)), {})
        if ts is None:
            self._skip("fb_reactions: timestamp yok")
            return
        kind = "facebook.tepki"
        yield EventIn(ts=ts, kind=kind, category=Category.SOSYAL,
                      payload={"baslik": rec.get("title"), "tepki": r.get("reaction")},
                      text=rec.get("title") or "",
                      event_key=stable_key("meta", kind, rec.get("timestamp"), rec.get("title")))

    def _ev_fb_friends(self, slug, e, rec):
        ts = epoch_to_iso(rec.get("timestamp"))
        if ts is None or not rec.get("name"):
            self._skip("fb_friends: ad/timestamp yok")
            return
        kind = "facebook.arkadas"
        yield EventIn(ts=ts, kind=kind, category=Category.SOSYAL, payload={"ad": rec["name"]},
                      text=rec["name"], event_key=stable_key("meta", kind, rec["name"], rec.get("timestamp")))

    # --- mesajlar (hassas)
    def _ev_messages(self, slug, e, rec):
        ts = epoch_to_iso(rec.get("timestamp_ms"))
        if ts is None:
            self._skip("messages: timestamp_ms yok")
            return
        content = rec.get("content") or ""
        share = rec.get("share") if isinstance(rec.get("share"), dict) else {}
        thread = e.name.rsplit("/", 2)[-2] if "/" in e.name else ""
        plat = _platform(e.name) or "meta"
        kind = f"{plat}.mesaj"
        extra = " ".join(x for x in (share.get("share_text"), share.get("link")) if x)
        payload = {
            "gonderen": rec.get("sender_name"), "icerik": content, "tur": rec.get("type"),
            "konusma": thread, "paylasim": share.get("link"),
            "ek": {k: len(rec[k]) for k in ("photos", "videos", "audio_files", "files", "gifs")
                   if isinstance(rec.get(k), list) and rec[k]},
        }
        yield EventIn(ts=ts, kind=kind, category=Category.MESAJ, payload=payload,
                      text=" ".join(x for x in (content, extra) if x),
                      event_key=stable_key("meta", kind, thread, rec.get("timestamp_ms"),
                                           rec.get("sender_name"), content))


def _find_coords(o, out=None, name=None):
    """İç içe yapıda enlem/boylam çiftlerini toplar (exif_data, place.coordinate vb.);
    en yakın üst `name` yer adı olarak eklenir."""
    out = [] if out is None else out
    if isinstance(o, dict):
        nm = o.get("name") if isinstance(o.get("name"), str) else name
        lat = o.get("latitude", o.get("lat"))
        lon = o.get("longitude", o.get("lon", o.get("lng")))
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            item = {"enlem": lat, "boylam": lon}
            if nm:
                item["ad"] = nm
            out.append(item)
        for v in o.values():
            _find_coords(v, out, nm)
    elif isinstance(o, list):
        for v in o:
            _find_coords(v, out, name)
    return out


def factory() -> Meta:
    return Meta()
