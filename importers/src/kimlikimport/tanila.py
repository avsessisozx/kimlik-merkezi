"""Tanılama aracı: `kimlikmerkezi tanila <dosya-veya-klasör>`.

Dışa aktarma dosyasının YAPISINI raporlar; İÇERİĞİNİ YAZMAZ. Çıktı kullanıcının bir geliştiriciye
yapıştırabileceği kısa metindir. Ağa bağlanmaz (yalnız yerel dosya okur; hiçbir ağ modülü kullanılmaz).

Rapora girenler: hangi içe aktarıcının tanıdığı (ad + güven), dosya/klasör adları (varsayılan olarak
MASKELİ), alan adları ve türleri, kayıt sayıları, metin uzunluk aralıkları, sayıların hane sayısı
(epoch benzeri mi), tarih biçimi örüntüsü (rakamlar 9 ile değiştirilmiş: `9999-99-99T99:99:99Z`).
Rapora ASLA girmeyenler: metin/sayı değerleri, kişi/yer adları, URL'ler, e-posta, tarih değerleri.

Sızıntıya karşı kurallar (tests/test_tanila.py sentinel dizgiyle sınar):
- Değerler hiç yazılmaz; yalnız tür, uzunluk aralığı, hane sayısı ve tarih ŞEKLİ.
- Alan adı (JSON anahtarı, CSV başlığı, SQLite tablo/sütun, MBOX başlığı) varsayılan olarak YALNIZ
  bilinen kelime dağarcığındaysa yazılır; diğerleri şekline indirgenir (`{özel:a{5}Aaaa}`). Çünkü
  veri bazen anahtar adı olarak taşınır (kullanıcı adıyla anahtarlanmış sözlük) ve bir alanın "yeni
  alan" mı "veri" mi olduğu makineyle ayırt edilemez. Kimliğe benzeyen (UUID/uzun rakam/onaltılık)
  anahtarlar hiç yazılmaz; anahtar sayısı çoksa (ör. ChatGPT `mapping`) tek `{anahtar}` altında toplanır.
- Dosya/klasör adları varsayılan olarak yalnız biçimine indirgenir (a=küçük harf, A=büyük, 9=rakam);
  yalnız bilinen dışa aktarma adları açık kalır.
- `--adlari-goster`: dosya/klasör adlarını VE bilinmeyen alan adlarını gerçek haliyle yazar (yeni/yerelleşmiş
  adları görmek için). Kişi adı içeren klasör ya da veri taşıyan anahtar olabilir: kullanıcı bilerek seçer,
  paylaşmadan önce raporu gözden geçirmelidir. DEĞERLER bu modda da yazılmaz.
Bu araç gerçek bir dışa aktarmayla DOĞRULANMADI; sızıntısızlık yalnız sentetik sentinel testiyle sınandı.
"""
from __future__ import annotations

import csv
import io
import platform
import re
import sqlite3
import tarfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import ijson

from .base import FormatReport, open_archive, clear_archive_cache, strip_bom

MAX_FULL_BYTES = 256 * 1024 * 1024  # bunun üstündeki dosyada ilk 64 MiB örneklenir
SAMPLE_BYTES = 64 * 1024 * 1024
MAX_PATHS = 4000  # bir dosyada izlenen en çok farklı yol
MAX_FILE_GROUPS_SHOWN = 25  # --ayrinti ile 200
FULL_PER_GROUP = 1  # aynı biçimli dosya grubunda ayrıntılı çözümlenen dosya sayısı
SIBLING_LIMIT = 30
TREE_LINES = 30
TREE_LINES_DETAIL = 400

# Adı açık gösterilen bilinen dışa aktarma kelimeleri (küçük harf). Kişisel olmayan yapı adlarıdır.
_ALLOW_NAMES = {
    "takeout", "my activity", "chrome", "history.json", "browserhistory.json", "history", "places.sqlite",
    "youtube and youtube music", "watch-history.json", "search-history.json", "subscriptions.csv",
    "subscriptions", "playlists", "likes.json", "myactivity.json", "location history", "records.json",
    "semantic location history", "location history (timeline)", "timeline.json", "settings.json",
    "mail", "gemini apps", "gemini", "search", "maps", "discover", "profile", "archive_browser.html",
    "conversations.json", "user.json", "users.json", "projects.json", "memories.json", "message_feedback.json",
    "export_manifest.json", "chat.html", "shared_conversations.json", "library_files.json",
    "comments.csv", "posts.csv", "messages.csv", "messages_archive.csv", "chat_history.csv", "post_votes.csv",
    "comment_votes.csv", "saved_posts.csv", "saved_comments.csv", "subscribed_subreddits.csv", "ip_logs.csv",
    "statistics.csv", "playlist1.json", "yourlibrary.json", "searchqueries.json", "userdata.json",
    "follow.json", "inferences.json", "payments.json", "schema.json",
    "your_instagram_activity", "your_facebook_activity", "connections", "followers_and_following",
    "likes", "comments", "saved", "messages", "inbox", "content", "posts", "stories", "reels",
    "personal_information", "ads_information", "security_and_login_information", "media",
    "followers_1.json", "following.json", "liked_posts.json", "saved_posts.json", "post_comments_1.json",
    "posts_1.json", "message_1.json", "profile_information", "friends_and_followers", "logged_information",
    "your_posts__check_ins__photos_and_videos_1.json", "your_posts_1.json", "comments_and_reactions",
}
_ALLOW_RES = (
    re.compile(r"^[a-z][a-z_]*_\d{1,6}\.json$"),  # repositories_000001.json, message_1.json, followers_1.json
    re.compile(r"^conversations-\d{3}\.json$"),
    re.compile(r"^streaming_?history[\w\-]*\.json$", re.I),
    re.compile(r"^\d{4}(_[a-z]+)?\.json$", re.I),  # 2024.json, 2024_march.json
    re.compile(r"^\d{4}$"),
    re.compile(r"^takeout-\d{8}t\d{6}z-\d{3}\.zip$", re.I),
)
_SAFE_EXT = {"json", "jsonl", "csv", "html", "htm", "txt", "md", "mbox", "zip", "gz", "tar", "tgz", "sqlite",
             "db", "jpg", "jpeg", "png", "gif", "mp4", "mp3", "pdf", "kmz", "xml", "dat", "webp", "heic", "mov"}

# Bilinen alan adı dağarcığı: bunlar "bilinen" sayılır, diğerleri "yeni/beklenmeyen" işaretlenir.
_EXTRA_VOCAB = {
    "mapping", "id", "message", "parent", "children", "author", "role", "name", "metadata", "content",
    "content_type", "parts", "text", "create_time", "update_time", "status", "end_turn", "weight", "recipient",
    "channel", "model_slug", "title", "current_node", "conversation_id", "default_model_slug", "uuid", "sender",
    "chat_messages", "created_at", "updated_at", "account", "attachments", "files", "file_name", "file_size",
    "file_type", "extracted_content", "summary", "type", "start_timestamp", "stop_timestamp", "citations",
    "participants", "messages", "timestamp_ms", "sender_name", "photos", "videos", "audio_files", "reactions",
    "reaction", "actor", "share", "link", "share_text", "is_still_participant", "thread_path", "magic_words",
    "string_list_data", "string_map_data", "href", "value", "timestamp", "media", "uri", "creation_timestamp",
    "media_metadata", "photo_metadata", "exif_data", "latitude", "longitude", "data", "post", "comment",
    "author_name", "media_list_data", "likes_media_likes", "relationships_following", "relationships_followers",
    "saved_saved_media", "comments_media_comments", "Comment", "Media Owner", "Time", "Saved on",
    "ts", "platform", "ms_played", "conn_country", "ip_addr", "ip_addr_decrypted", "username", "endTime",
    "artistName", "trackName", "msPlayed", "podcastName", "episodeName", "playlists", "items", "track",
    "episode", "audioBook", "localTrack", "addedDate", "lastModifiedDate", "numberOfFollowers", "description",
    "collaborators", "tracks", "albums", "shows", "episodes", "artists", "bannedTracks", "bannedArtists",
    "other", "artist", "album", "publisher", "searchTime", "searchQuery", "searchInteractionURIs",
    "url", "owner", "private", "language", "state", "body", "user", "repository", "full_name", "tag_name",
    "locations", "latitudeE7", "longitudeE7", "timelineObjects", "placeVisit", "activitySegment", "location",
    "duration", "startTimestamp", "endTimestamp", "startTimestampMs", "endTimestampMs", "semanticSegments",
    "rawSignals", "userLocationProfile", "startTime", "endTime", "visit", "activity", "timelinePath",
    "topCandidate", "placeLocation", "latLng", "placeId", "semanticType", "probability", "point", "time",
    "header", "titleUrl", "subtitles", "details", "locationInfos", "activityControls", "products",
    "Browser History", "favicon_url", "page_transition", "client_id", "time_usec", "snippet", "contentDetails",
    "videoId", "publishedAt", "resourceId", "kind", "etag", "playlistId", "position", "channelId", "channelTitle",
    "videoOwnerChannelTitle", "thumbnails", "safeHtmlItem", "html", "attachedFiles", "imageFile",
    "Channel ID", "Channel URL", "Channel title",
    "address", "accuracy", "accuracyMetres", "locationConfidence", "isCurrentLocation", "calibratedProbability",
    "sourceInfo", "deviceTag", "placeConfidence", "visitConfidence", "placeVisitType", "placeVisitImportance",
    "editConfirmationStatus", "distance", "activityType", "activities", "confidence", "waypointPath",
    "simplifiedRawPath", "centerLatE7", "centerLngE7", "otherCandidateLocations", "childVisits", "startLocation",
    "endLocation", "lastEditedTimestamp", "parkingEvent", "hierarchyLevel", "distanceMeters", "start", "end",
    "startTimeTimezoneUtcOffsetMinutes", "endTimeTimezoneUtcOffsetMinutes", "position", "LatLng", "accuracyMeters",
    "altitudeMeters", "source", "frequentPlaces", "is_visually_hidden_from_conversation", "request_id", "finish_details",
    "moderation_results", "safe_urls", "blocked_urls", "gizmo_id", "is_archived", "is_starred", "memory_scope",
    "model", "project_uuid", "settings", "decoding_id", "direction", "asset_pointer", "size_bytes", "thoughts",
    "finished", "language", "audio_asset_pointer", "reason_start", "reason_end", "shuffle", "skipped", "offline",
    "offline_timestamp", "incognito_mode", "episode_name", "episode_show_name", "spotify_track_uri",
    "spotify_episode_uri", "master_metadata_track_name", "master_metadata_album_artist_name",
    "master_metadata_album_album_name", "audiobook_title", "audiobook_uri", "audiobook_chapter_uri",
    "audiobook_chapter_title", "email", "phone_number", "chatgpt_plus_user", "export_files", "path",
}
_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_ .\-]{0,40}$")
_IDLIKE = re.compile(r"^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\d{4,}|[0-9a-fA-F]{12,}|[\w\-]{0,10}\d{6,}[\w\-]*)$")
_DATE_SHAPE = re.compile(r"^(?:[9\-+.:/ TZ,]{6,40})(?:\[UTC\]| UTC)?$")


def _vocab() -> set[str]:
    v = set(_EXTRA_VOCAB)
    try:
        from . import google_takeout as gt
        for n in ("_ACTIVITY_KNOWN", "_CHROME_KNOWN", "_RECORD_KNOWN", "_SEMANTIC_KNOWN", "_TIMELINE_KNOWN", "_LIKE_KNOWN"):
            v |= set(getattr(gt, n))
        from . import chat, meta, spotify, reddit
        v |= chat.ChatGPT.known_conv_keys | chat.Claude.known_conv_keys
        for s in meta._KNOWN.values():
            v |= set(s)
        for s in spotify._KNOWN.values():
            v |= set(s)
        for sp in reddit._SPECS.values():
            v |= sp.known
    except Exception:  # sözlük eksik kalsa da araç çalışır
        pass
    return v


VOCAB = _vocab()


# ---------------------------------------------------------------------------------- şekil / maskeleme
def sekil(s: str) -> str:
    """Metni biçimine indirger: küçük harf=a, büyük harf=A, rakam=9, diğerleri aynen; 4+ tekrar `x{n}`."""
    out = []
    for ch in s:
        if ch.isdigit():
            out.append("9")
        elif ch.isalpha():
            out.append("A" if ch.isupper() else "a")
        elif ch.isspace():
            out.append(" ")
        elif ch in "._-/()+[],:":
            out.append(ch)
        else:
            out.append("?")
    sh = "".join(out)
    return re.sub(r"(.)\1{3,}", lambda m: f"{m.group(1)}{{{len(m.group(0))}}}", sh)


def ad_goster(seg: str, goster: bool) -> str:
    if goster:
        return seg
    low = seg.lower()
    if low in _ALLOW_NAMES or any(r.match(seg) for r in _ALLOW_RES):
        return seg
    stem, dot, ext = seg.rpartition(".")
    if dot and ext.lower() in _SAFE_EXT and stem:
        return f"<{sekil(stem)}>.{ext.lower()}"
    return f"<{sekil(seg)}>"


def yol_goster(path: str, goster: bool) -> str:
    return "/".join(ad_goster(p, goster) for p in path.replace("\\", "/").split("/") if p)


def _tarih_sekli(s: str) -> str | None:
    if not s or len(s) > 48 or sum(c.isdigit() for c in s) < 4:
        return None
    sh = re.sub(r"\d", "9", s)
    if _DATE_SHAPE.match(sh) and sum(sh.count(c) for c in "-/.:") >= 2:
        return sh
    # RFC 2822 benzeri: "Mon, 4 Mar 2024 10:00:00 +0000"
    m = re.fullmatch(r"(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), )?\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} \d\d:\d\d(?::\d\d)? ?[+\-]\d{4}( \(\w+\))?", s)
    if m:
        return re.sub(r"\d", "9", s)
    return None


# ---------------------------------------------------------------------------------- JSON yapı çıkarımı
class _Stat:
    __slots__ = ("n", "types", "smin", "smax", "dmin", "dmax", "shapes", "empty", "nulls")

    def __init__(self) -> None:
        self.n = 0
        self.types: Counter[str] = Counter()
        self.smin = self.dmin = 10**9
        self.smax = self.dmax = -1
        self.shapes: Counter[str] = Counter()
        self.empty = 0
        self.nulls = 0

    def merge(self, o: "_Stat") -> None:
        self.n += o.n
        self.types.update(o.types)
        self.smin, self.smax = min(self.smin, o.smin), max(self.smax, o.smax)
        self.dmin, self.dmax = min(self.dmin, o.dmin), max(self.dmax, o.dmax)
        self.shapes.update(o.shapes)
        self.empty += o.empty
        self.nulls += o.nulls


class _LimitedReader(io.RawIOBase):
    def __init__(self, f, limit: int):
        self._f, self._left, self.hit = f, limit, False

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        if self._left <= 0:
            self.hit = True
            return b""
        size = self._left if size is None or size < 0 else min(size, self._left)
        data = self._f.read(size)
        self._left -= len(data)
        return data

    def readinto(self, b) -> int:
        d = self.read(len(b))
        b[: len(d)] = d
        return len(d)


def _seg_for_key(k: str) -> str:
    return "{kimlik}" if _IDLIKE.match(k) else k


def json_yapisi(f, *, multiple: bool = False) -> dict:
    """ijson olaylarıyla yapı çıkarır; değer SAKLANMAZ. Dönüş: {'stats','children','records','error','partial'}."""
    stats: dict[tuple, _Stat] = defaultdict(_Stat)
    children: dict[tuple, Counter] = defaultdict(Counter)  # üst yol -> {anahtar: kez}
    stack: list[tuple] = [()]  # geçerli kapsayıcı yolları
    kinds: list[str] = []  # 'map' | 'array'
    cur_key: str | None = None
    events = 0
    error = None
    overflow = False
    try:
        for _prefix, ev, val in ijson.parse(strip_bom(f), use_float=True, multiple_values=multiple):
            events += 1
            if ev == "map_key":
                cur_key = _seg_for_key(str(val))
                continue
            if ev in ("end_map", "end_array"):
                stack.pop()
                kinds.pop()
                cur_key = None
                continue
            parent = stack[-1]
            if kinds and kinds[-1] == "map":
                path = parent + (cur_key if cur_key is not None else "?",)
                children[parent][path[-1]] += 1
            elif kinds:
                path = parent + ("[]",)
            else:
                path = ()
            if len(stats) >= MAX_PATHS and path not in stats:
                overflow = True
                if ev in ("start_map", "start_array"):
                    stack.append(path)
                    kinds.append("map" if ev == "start_map" else "array")
                cur_key = None
                continue
            st = stats[path]
            if ev == "start_map":
                st.n += 1
                st.types["nesne"] += 1
                stack.append(path)
                kinds.append("map")
            elif ev == "start_array":
                st.n += 1
                st.types["dizi"] += 1
                stack.append(path)
                kinds.append("array")
            elif ev == "null":
                st.n += 1
                st.nulls += 1
                st.types["null"] += 1
            elif ev == "boolean":
                st.n += 1
                st.types["bool"] += 1
            elif ev == "string":
                st.n += 1
                st.types["metin"] += 1
                ln = len(val)
                st.smin, st.smax = min(st.smin, ln), max(st.smax, ln)
                if ln == 0:
                    st.empty += 1
                elif len(st.shapes) < 6:
                    sh = _tarih_sekli(val)
                    if sh:
                        st.shapes[sh] += 1
            elif ev in ("integer", "number", "double"):
                st.n += 1
                is_int = isinstance(val, int) and not isinstance(val, bool)
                st.types["tamsayı" if is_int else "ondalık"] += 1
                digits = len(str(abs(int(val)))) if val == val and abs(val) < 1e300 else 0
                st.dmin, st.dmax = min(st.dmin, digits), max(st.dmax, digits)
            cur_key = None
    except (ijson.JSONError, UnicodeDecodeError, ValueError, OSError) as exc:
        error = type(exc).__name__
    return {"stats": stats, "children": children, "events": events, "error": error, "overflow": overflow}


def _collapse(stats: dict, children: dict) -> tuple[dict, dict]:
    """Kardeş anahtar sayısı çok olan üst yolların çocuklarını `{anahtar}` altında toplar:
    toplam > SIBLING_LIMIT ise hepsi; kelime dağarcığında olmayan kardeş > 8 ise yalnız onlar
    (ör. ChatGPT `mapping`, kullanıcı etiketi sözlükleri)."""
    wide = {p for p, c in children.items() if len(c) > SIBLING_LIMIT}
    wide_unk = {p for p, c in children.items() if sum(1 for k in c if k not in VOCAB and k != "[]") > 8}
    if not wide and not wide_unk:
        return stats, children

    def seg_of(prefix: tuple, seg: str) -> str:
        if prefix in wide or (prefix in wide_unk and seg not in VOCAB and seg != "[]"):
            return "{anahtar}"
        return seg

    new: dict[tuple, _Stat] = defaultdict(_Stat)
    for path, st in stats.items():
        new[tuple(seg_of(tuple(path[:i]), seg) for i, seg in enumerate(path))].merge(st)
    newc: dict[tuple, Counter] = defaultdict(Counter)
    for p, c in children.items():
        np = tuple(seg_of(tuple(p[:i]), seg) for i, seg in enumerate(p))
        for k, v in c.items():
            newc[np][seg_of(p, k)] += v
    return new, newc


def _gizle_anahtar(seg: str, goster: bool) -> str:
    """Alan adını yazmak güvenli mi? Değilse şekline indirger (`--adlari-goster` açıksa yazılır)."""
    if seg in ("[]", "{kimlik}", "{anahtar}", "?") or seg in VOCAB or goster:
        return seg
    return "{özel:" + sekil(seg) + "}"


def agac_satirlari(res: dict, max_lines: int = TREE_LINES, max_depth: int = 6,
                   goster: bool = False) -> tuple[list[str], set[str], dict]:
    """(satırlar, bilinmeyen_alanlar, kayıt_bilgisi)."""
    stats, children = _collapse(res["stats"], res["children"])
    paths = sorted(stats, key=lambda p: (len(p), p))
    # güvenli gösterim
    shown: dict[tuple, str] = {}
    unknown: set[str] = set()
    for p in sorted(stats, key=len):
        if not p:
            shown[p] = "$"
            continue
        parent = p[:-1]
        seg = _gizle_anahtar(p[-1], goster)
        if seg not in VOCAB and seg not in ("[]", "{kimlik}", "{anahtar}") and not seg.startswith("{özel"):
            unknown.add(seg)
        if seg.startswith("{özel"):
            unknown.add(seg)
        shown[p] = shown[parent] + ("[]" if seg == "[]" else "." + seg)
    lines = []
    for p in paths:
        st = stats[p]
        if len(p) > max_depth:
            continue
        has_child = any(len(q) == len(p) + 1 and q[: len(p)] == p for q in stats)
        if st.types and set(st.types) <= {"nesne"} and has_child and p and p[-1] != "[]":
            continue  # kapsayıcı nesne: çocukları zaten görünüyor
        if set(st.types) == {"dizi"} and has_child:
            continue  # dizi: öğe satırı (`[]`) sayıyı taşıyor
        parts = [f"{st.n}×"]
        t = ",".join(k if len(st.types) == 1 else f"{k}:{v}" for k, v in sorted(st.types.items()))
        parts.append(t)
        if st.smax >= 0:
            parts.append(f"uzunluk {st.smin}-{st.smax}")
        if st.dmax >= 0 and ("tamsayı" in st.types or "ondalık" in st.types):
            hint = ""
            if st.dmin == st.dmax:
                hint = {10: " saniye?", 13: " ms?", 16: " µs?"}.get(st.dmax, "")
            parts.append(f"{st.dmin}-{st.dmax} hane{hint}")
        if st.shapes:
            parts.append("örüntü " + " | ".join(f"{sh}" + (f" ({n})" if len(st.shapes) > 1 else "")
                                              for sh, n in st.shapes.most_common(3)))
        if st.empty:
            parts.append(f"boş:{st.empty}")
        lines.append(f"  {shown[p]}  " + " ".join(parts))
    if len(lines) > max_lines:
        extra = len(lines) - max_lines
        lines = lines[:max_lines] + [f"  … {extra} satır daha (kısaltıldı; --ayrinti ile tümü)"]
    # kayıt bilgisi: en kısa dizi öğesi yolu
    rec = {"sayi": None, "alanlar": set()}
    arr_items = [p for p in paths if p and p[-1] == "[]" and any(t in stats[p].types for t in ("nesne",))]
    if arr_items:
        p0 = arr_items[0]
        rec["sayi"] = stats[p0].n
        rec["alanlar"] = {k for k in children.get(p0, {}) if k not in ("[]",)}
    elif () in stats and "nesne" in stats[()].types:
        rec["sayi"] = stats[()].n
        rec["alanlar"] = set(children.get((), {}))
    return lines, unknown, rec


# ---------------------------------------------------------------------------------- beklenen şekiller
# importer -> şekil adı -> bu dosyada kayıt düzeyinde bulunması beklenen alanlar
EXPECTED = {
    "google_takeout": {
        "etkinlik (My Activity/YouTube geçmişi)": {"time", "title"},
        "chrome geçmişi": {"time_usec", "url"},
        "konum kaydı (Records.json)": {"latitudeE7", "longitudeE7"},
        "yer/hareket (Semantic)": {"placeVisit"},
        "zaman çizelgesi (Timeline.json)": {"startTime", "endTime"},
        "youtube beğeni": {"snippet", "contentDetails"},
    },
    "chatgpt": {"konuşma": {"mapping", "current_node", "create_time", "title"}},
    "claude": {"konuşma": {"uuid", "name", "created_at", "chat_messages"}},
    "meta": {
        "liste (string_list_data)": {"string_list_data"},
        "harita (string_map_data)": {"string_map_data"},
        "mesaj": {"participants", "messages"},
        "gönderi": {"media"},
    },
    "spotify": {
        "genişletilmiş akış": {"ts", "ms_played"},
        "standart müzik": {"endTime", "trackName", "artistName", "msPlayed"},
        "arama": {"searchTime", "searchQuery"},
    },
    "github": {"kayıt": {"type", "url"}},
    "reddit": {"gönderi": {"id", "permalink", "date", "title"}, "yorum": {"id", "permalink", "date", "body"}},
}


def _kayit_karsilastir(importer: str, rec_keys: set[str]) -> str | None:
    shapes = EXPECTED.get(importer)
    if not shapes or not rec_keys:
        return None
    best, best_missing = None, None
    for name, req in shapes.items():
        miss = req - rec_keys
        if not miss:
            return f"beklenen şekil bulundu: {name}"
        if best_missing is None or len(miss) < len(best_missing):
            best, best_missing = name, miss
    return f"en yakın şekil '{best}' için eksik alanlar: {', '.join(sorted(best_missing))}"


# ---------------------------------------------------------------------------------- dosya çözümleyiciler
def _ilk_bayt(open_fn, n: int = 4096) -> bytes:
    with open_fn() as f:
        return f.read(n)


def _tur(name: str, head: bytes) -> str:
    low = name.lower()
    h = head[3:] if head.startswith(b"\xef\xbb\xbf") else head
    if h.startswith(b"SQLite format 3\x00"):
        return "sqlite"
    if low.endswith(".mbox") or h.startswith(b"From "):
        return "mbox"
    if low.endswith(".jsonl") or low.endswith(".ndjson"):
        return "jsonl"
    if low.endswith(".json") or h.lstrip()[:1] in (b"{", b"["):
        return "json"
    if low.endswith(".csv"):
        return "csv"
    if low.endswith((".html", ".htm")):
        return "html"
    if low.endswith((".txt", ".md", ".markdown")):
        return "metin"
    return "diger"


def _json_rapor(open_fn, size: int, multiple: bool, ayrinti: bool = False, goster: bool = False) -> tuple[list[str], dict]:
    out: list[str] = []
    partial = size > MAX_FULL_BYTES
    with open_fn() as raw:
        lim = _LimitedReader(raw, SAMPLE_BYTES) if partial else raw
        res = json_yapisi(lim, multiple=multiple)
        hit = getattr(lim, "hit", False)
    lines, unknown, rec = agac_satirlari(res, TREE_LINES_DETAIL if ayrinti else TREE_LINES, 12 if ayrinti else 5, goster)
    if res["error"] and hit:
        out.append(f"  (dosya büyük: yalnız ilk {SAMPLE_BYTES // (1024 * 1024)} MiB çözümlendi, sayılar kısmi)")
    elif res["error"]:
        out.append(f"  UYARI: JSON bozuk ya da yarım ({res['error']}); bozulmadan önceki {res['events']} olay çözümlendi")
    if res["overflow"]:
        out.append(f"  (yol sınırı {MAX_PATHS} aşıldı; ek yollar gösterilmiyor)")
    if rec["sayi"] is not None:
        out.append(f"  kayıt sayısı (ilk dizi/nesne): {rec['sayi']}")
    out.extend(lines)
    yeni = sorted(u for u in unknown if u not in VOCAB and u != "?")
    if yeni:
        out.append("  kelime dağarcığında olmayan alanlar: " + ", ".join(yeni[:20]) + (" …" if len(yeni) > 20 else ""))
    return out, {"unknown": unknown, "rec": rec, "error": res["error"]}


def _csv_rapor(open_fn, goster: bool = False) -> tuple[list[str], dict]:
    out: list[str] = []
    with open_fn() as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
        rd = csv.reader(text)
        try:
            header = next(rd, None)
        except csv.Error as e:
            return [f"  UYARI: CSV başlığı okunamadı ({type(e).__name__})"], {"header": set()}
        if header is None:
            return ["  boş CSV"], {"header": set()}
        shown = []
        for h in header:
            h = h.strip()
            # başlıksız CSV'de ilk satır veridir: --adlari-goster'de bile yalnız boşluksuz, ASCII, tanımlayıcı
            # biçimli başlıklar yazılır (e-posta, "Ad Soyad" gibi hücreler maskelenir)
            ok = h in VOCAB or (goster and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-]{0,40}", h) is not None)
            shown.append(h if ok else "{özel:" + sekil(h) + "}")
        n = 0
        empty = [0] * len(header)
        lmin = [10**9] * len(header)
        lmax = [-1] * len(header)
        shapes: list[Counter] = [Counter() for _ in header]
        bad_width = 0
        try:
            for row in rd:
                n += 1
                if len(row) != len(header):
                    bad_width += 1
                for i, v in enumerate(row[: len(header)]):
                    if v == "":
                        empty[i] += 1
                    else:
                        lmin[i], lmax[i] = min(lmin[i], len(v)), max(lmax[i], len(v))
                        if len(shapes[i]) < 4:
                            sh = _tarih_sekli(v)
                            if sh:
                                shapes[i][sh] += 1
        except csv.Error as e:
            out.append(f"  UYARI: CSV {n}. satırdan sonra bozuk ({type(e).__name__})")
        except UnicodeDecodeError:
            out.append(f"  UYARI: CSV UTF-8 değil ({n}. satırdan sonra)")
    out.append(f"  satır sayısı: {n}; sütun sayısı: {len(header)}" + (f"; sütun sayısı uymayan satır: {bad_width}" if bad_width else ""))
    for i, name in enumerate(shown):
        extra = []
        if lmax[i] >= 0:
            extra.append(f"uzunluk {lmin[i]}-{lmax[i]}")
        if empty[i]:
            extra.append(f"boş:{empty[i]}")
        if shapes[i]:
            extra.append("tarih şekli: " + " | ".join(f"{s} ({c})" for s, c in shapes[i].most_common(2)))
        out.append(f"  sütun {i + 1}: {name}" + (" — " + "; ".join(extra) if extra else ""))
    return out, {"header": set(header)}


_HDR = re.compile(rb"^([A-Za-z][A-Za-z0-9\-]{1,40}):")
_MAIL_HDR = {
    "from", "to", "cc", "bcc", "subject", "date", "message-id", "in-reply-to", "references", "mime-version",
    "content-type", "content-transfer-encoding", "content-disposition", "content-id", "received", "return-path",
    "delivered-to", "reply-to", "sender", "x-gmail-labels", "x-gm-thrid", "x-gm-msgid", "list-id",
    "list-unsubscribe", "authentication-results", "received-spf", "dkim-signature", "x-mailer", "user-agent",
    "importance", "precedence", "auto-submitted",
}
_SQL_VOCAB = {
    "urls", "visits", "moz_places", "moz_historyvisits", "moz_bookmarks", "moz_meta", "moz_annos",
    "history_items", "history_visits", "id", "url", "title", "visit_count", "typed_count", "last_visit_time",
    "hidden", "visit_time", "from_visit", "transition", "segment_id", "visit_duration", "place_id", "visit_date",
    "visit_type", "description", "history_item", "sqlite_sequence", "meta", "keyword_search_terms", "downloads",
}


def _mbox_rapor(open_fn, goster: bool = False) -> tuple[list[str], dict]:
    n = 0
    hdrs: Counter[str] = Counter()
    date_shapes: Counter[str] = Counter()
    prev_blank = True
    in_hdr = False
    with open_fn() as f:
        while True:
            line = f.readline(65536)
            if not line:
                break
            if prev_blank and line.startswith(b"From "):
                n += 1
                in_hdr = True
                prev_blank = False
                continue
            if in_hdr and n <= 500:
                if line in (b"\n", b"\r\n"):
                    in_hdr = False
                else:
                    m = _HDR.match(line)
                    if m:
                        name = m.group(1).decode("ascii")
                        hdrs[name] += 1
                        if name.lower() == "date":
                            sh = _tarih_sekli(line.split(b":", 1)[1].strip().decode("ascii", "replace"))
                            if sh:
                                date_shapes[sh] += 1
            elif line in (b"\n", b"\r\n"):
                in_hdr = False
            prev_blank = line in (b"\n", b"\r\n")
    out = [f"  ileti sayısı: {n}"]
    shown = ", ".join(f"{k if goster or k.lower() in _MAIL_HDR else '{özel:' + sekil(k) + '}'}:{v}"
                      for k, v in hdrs.most_common(30))
    out.append(f"  başlık adları (ilk 500 iletide): {shown or '(yok)'}")
    if date_shapes:
        out.append("  Date başlık şekli: " + " | ".join(f"{s} ({c})" for s, c in date_shapes.most_common(3)))
    return out, {}


def _sqlite_rapor(path: Path, goster: bool = False) -> list[str]:
    out = []
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    except sqlite3.Error as e:
        return [f"  UYARI: SQLite açılamadı ({type(e).__name__})"]
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        ad = lambda x: x if (goster or x in _SQL_VOCAB) else "{özel:" + sekil(x) + "}"
        for t in tables[:60]:
            cols = [r[1] for r in con.execute('PRAGMA table_info("' + t.replace('"', '""') + '")')]
            try:
                cnt = con.execute('SELECT COUNT(*) FROM "' + t.replace('"', '""') + '"').fetchone()[0]
            except sqlite3.Error:
                cnt = "?"
            out.append(f"  tablo {ad(t)}: {cnt} satır; sütunlar: {', '.join(ad(c) for c in cols)}")
        if len(tables) > 60:
            out.append(f"  … {len(tables) - 60} tablo daha")
    except sqlite3.Error as e:
        out.append(f"  UYARI: şema okunamadı ({type(e).__name__})")
    finally:
        con.close()
    return out


def _metin_rapor(open_fn) -> list[str]:
    lines = chars = maxlen = 0
    with open_fn() as f:
        for ln in f:
            lines += 1
            chars += len(ln)
            maxlen = max(maxlen, len(ln))
    return [f"  satır: {lines}; en uzun satır: {maxlen} bayt; toplam: {chars} bayt"]


# ---------------------------------------------------------------------------------- girdi gezme
class _Dosya:
    __slots__ = ("ad", "boyut", "ac", "yerel")

    def __init__(self, ad: str, boyut: int, ac, yerel: Path | None = None):
        self.ad, self.boyut, self.ac, self.yerel = ad, boyut, ac, yerel


def _dosyalar(path: Path):
    """(ad, boyut, açıcı, yerel_yol|None) üretir. tar/zip/klasör/tek dosya. Hiçbir şey diske açılmaz."""
    name = path.name.lower()
    if path.is_file() and name.endswith((".tar.gz", ".tgz", ".tar")):
        try:
            with tarfile.open(path, "r:*") as tf:
                members = [m for m in tf.getmembers() if m.isfile()]
        except (tarfile.TarError, EOFError, OSError) as e:
            raise ValueError(f"tar okunamadı ({type(e).__name__})") from None

        def mk(mname):
            def _open():
                tf2 = tarfile.open(path, "r:*")
                f = tf2.extractfile(mname)
                return _TarFile(tf2, f)
            return _open

        for m in members:
            yield _Dosya(m.name, m.size, mk(m.name))
        return
    arc = open_archive(path)
    for e in arc.entries:
        yield _Dosya(e.name, e.size, e.open, e.origin.path if not e.origin.is_zip else None)


class _TarFile(io.RawIOBase):
    def __init__(self, tf, f):
        self._tf, self._f = tf, f

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        return self._f.read(size)

    def readline(self, size: int = -1) -> bytes:
        return self._f.readline(size)

    def readinto(self, b) -> int:
        d = self._f.read(len(b))
        b[: len(d)] = d
        return len(d)

    def __iter__(self):
        return iter(self._f)

    def close(self) -> None:
        try:
            self._f.close()
            self._tf.close()
        finally:
            super().close()


def _grup_anahtari(ad: str) -> str:
    """Aynı biçimli dosyaları gruplamak için: her bölüm maskeli gösterimiyle (gerçek ad değil) birleştirilir."""
    return "/".join(ad_goster(s, False) for s in ad.replace("\\", "/").split("/") if s)


def tanila(path: Path | str, *, adlari_goster: bool = False, ayrinti: bool = False) -> str:
    """Raporu döner (düz metin). Yalnız yerel dosya okur."""
    from . import registry
    from . import __version__ as imp_ver

    path = Path(path)
    if not path.exists():
        return f"Girdi yok."
    L: list[str] = []
    L.append("KİMLİK MERKEZİ — TANILAMA RAPORU (içerik içermez)")
    L.append(f"kimlikimport {imp_ver}; Python {platform.python_version()}; {platform.system()}")
    L.append("Bu rapor dosya içeriğini yazmaz: yalnız alan adları, türler, sayılar, uzunluk aralıkları ve tarih ŞEKLİ.")
    if adlari_goster:
        L.append("Dosya/klasör adları ve bilinmeyen alan adları GERÇEK (--adlari-goster): paylaşmadan önce kişi adı/veri taşıyıp taşımadığına bakın.")
    else:
        L.append("Dosya/klasör ve bilinmeyen alan adları maskelidir (a=küçük harf, A=büyük, 9=rakam); bilinen dışa aktarma adları açık.")
        L.append("Yeni/yerelleşmiş adları görmek gerekirse: kimlikmerkezi tanila <yol> --adlari-goster (adlara bakıp paylaşın).")
    L.append("")

    # 1) hangi içe aktarıcı tanıyor
    clear_archive_cache()
    L.append("1) İçe aktarıcıların tanıması")
    tanimlar: dict[str, float] = {}
    verify: dict[str, FormatReport | None] = {}
    for n in registry.names():
        imp = None
        try:
            imp = registry.create(n)
            d = imp.detect(path)
            tanimlar[n] = round(d.confidence, 2) if d.matches else 0.0
            L.append(f"  - {n}: {'TANIDI' if d.matches else 'tanımadı'} (güven {d.confidence:.2f})")
            if d.matches:
                try:
                    verify[n] = imp.verify_format(path)
                except Exception as exc:  # içerik sızdırmamak için yalnız tür adı
                    verify[n] = None
                    L.append(f"      verify_format hata verdi: {type(exc).__name__}")
        except Exception as exc:
            L.append(f"  - {n}: çözümleme hatası ({type(exc).__name__})")
        finally:
            close = getattr(imp, "close", None)
            if close:
                try:
                    close()
                except Exception:
                    pass
    best = max(tanimlar.items(), key=lambda kv: kv[1], default=(None, 0.0))
    L.append(f"  En iyi eşleşme: {best[0] if best[1] >= 0.5 else 'YOK (hiçbiri ≥0.50 güvenle tanımadı)'}")
    for n, rep in verify.items():
        if rep is None:
            continue
        L.append(f"  [{n}] biçim denetimi: {'UYGUN' if rep.ok else 'UYGUN DEĞİL'}; "
                 f"bulunan dosya {len(rep.found_files)}, eksik {len(rep.missing)}, beklenmeyen alan {len(rep.unexpected_fields)}, "
                 f"desteklenmeyen {len(rep.unsupported)}")
        for item in rep.unexpected_fields[:15]:
            f_, _, fld = item.rpartition(": ")
            fld_s = fld if fld in VOCAB or adlari_goster else "{özel:" + sekil(fld) + "}"
            L.append(f"      beklenmeyen alan: {yol_goster(f_, adlari_goster)}: {fld_s}")
    L.append("")

    # 2) dosya yapısı
    try:
        files = list(_dosyalar(path))
    except ValueError as e:
        L.append(f"2) Dosya yapısı: UYARI {e}")
        return "\n".join(L)
    ext_count: Counter[str] = Counter()
    for fl in files:
        ext = fl.ad.rsplit(".", 1)[-1].lower() if "." in fl.ad.rsplit("/", 1)[-1] else "(uzantısız)"
        ext_count[ext if ext in _SAFE_EXT or ext == "(uzantısız)" else "(diğer)"] += 1
    total_size = sum(f.boyut for f in files)
    L.append(f"2) Dosya yapısı: {len(files)} dosya, toplam {total_size} bayt; uzantılar: "
             + ", ".join(f"{k}:{v}" for k, v in ext_count.most_common()))
    groups: dict[str, list[_Dosya]] = defaultdict(list)
    for fl in files:
        groups[_grup_anahtari(fl.ad)].append(fl)
    ordered = sorted(groups.items(), key=lambda kv: (-sum(f.boyut for f in kv[1]), kv[0]))
    limit = 200 if ayrinti else MAX_FILE_GROUPS_SHOWN
    if len(ordered) > limit:
        L.append(f"   ({len(ordered)} dosya grubu; en büyük {limit} tanesi gösteriliyor)")
    importer_best = best[0] if best[1] >= 0.5 else None
    for gkey, members in ordered[:limit]:
        sizes = [m.boyut for m in members]
        shown_name = yol_goster(members[0].ad, adlari_goster) if len(members) == 1 else (
            gkey if not adlari_goster else yol_goster(members[0].ad, True) + f" (+ benzer {len(members) - 1})")
        L.append("")
        L.append(f"* {shown_name}  [{len(members)} dosya; boyut {min(sizes)}-{max(sizes)} bayt]")
        for m in members[:FULL_PER_GROUP]:
            L.extend(_dosya_rapor(m, importer_best, adlari_goster, ayrinti))
        if len(members) > FULL_PER_GROUP:
            L.append(f"  (aynı biçimli {len(members) - FULL_PER_GROUP} dosya ayrıntılandırılmadı)")
    if len(ordered) > limit:
        L.append(f"\n… {len(ordered) - limit} dosya grubu daha (kısaltıldı; --ayrinti ile daha çoğu)")
    return "\n".join(L)


def _dosya_rapor(m: _Dosya, importer: str | None, goster: bool, ayrinti: bool = False) -> list[str]:
    try:
        head = _ilk_bayt(m.ac)
    except Exception as exc:
        return [f"  UYARI: dosya açılamadı ({type(exc).__name__})"]
    if not head and m.boyut == 0:
        return ["  boş dosya (0 bayt)"]
    t = _tur(m.ad, head)
    out = [f"  tür: {t}"]
    try:
        if t in ("json", "jsonl"):
            rows, info = _json_rapor(m.ac, m.boyut, multiple=(t == "jsonl"), ayrinti=ayrinti, goster=goster)
            out.extend(rows)
            if importer and info["rec"]["alanlar"]:
                cmp = _kayit_karsilastir(importer, info["rec"]["alanlar"])
                if cmp:
                    out.append(f"  [{importer}] {cmp}")
        elif t == "csv":
            rows, _ = _csv_rapor(m.ac, goster)
            out.extend(rows)
        elif t == "mbox":
            rows, _ = _mbox_rapor(m.ac, goster)
            out.extend(rows)
        elif t == "sqlite":
            if m.yerel is not None:
                out.extend(_sqlite_rapor(m.yerel, goster))
            else:
                out.append("  SQLite (arşiv içinde; şema için önce çıkarın)")
        elif t in ("metin", "html"):
            out.extend(_metin_rapor(m.ac))
        else:
            out.append("  (ikili/bilinmeyen tür; içerik okunmadı)")
    except Exception as exc:
        out.append(f"  UYARI: çözümleme hatası ({type(exc).__name__})")
    return out


def main(yol: str, adlari_goster: bool = False, ayrinti: bool = False) -> str:
    return tanila(Path(yol), adlari_goster=adlari_goster, ayrinti=ayrinti)
