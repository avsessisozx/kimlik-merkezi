"""Spotify hesap verisi içe aktarıcısı: standart paket + genişletilmiş akış geçmişi (zip/klasör).

DOĞRULANMADI: support.spotify.com bu ortamdan açılamadı; dosya/alan adları hafızadan
(StreamingHistory_music_N.json, StreamingHistory_podcast_N.json, Playlist1.json, YourLibrary.json,
SearchQueries.json; genişletilmiş: Streaming_History_Audio_*.json). Tanıma dosya adına değil kayıt
alanlarına göre yapılır. Hepsi `muzik` kategorisi. IP, kullanıcı adı, kullanıcı aracısı, bağlantı
ülkesi bilerek ALINMAZ; Userdata.json gibi kimlik dosyaları okunmaz.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import ijson
from kimlikcore import Category, EventIn, FormatError

from .base import (
    DetectResult,
    Entry,
    FormatReport,
    Origin,
    ScanImporter,
    iso_utc,
    peek,
    stable_key,
    strip_bom,
)

NAME = "spotify"
_KNOWN = {
    "standard_music": {"endTime", "artistName", "trackName", "msPlayed"},
    "standard_podcast": {"endTime", "podcastName", "episodeName", "msPlayed"},
    "search": {"platform", "searchTime", "searchQuery", "searchInteractionURIs"},
    "extended": {"ts", "platform", "ms_played", "master_metadata_track_name",
                 "master_metadata_album_artist_name", "master_metadata_album_album_name",
                 "spotify_track_uri", "episode_name", "episode_show_name", "spotify_episode_uri",
                 "audiobook_title", "audiobook_uri", "audiobook_chapter_uri", "audiobook_chapter_title",
                 "reason_start", "reason_end", "shuffle", "skipped", "offline", "offline_timestamp",
                 "incognito_mode", "username", "conn_country", "ip_addr", "ip_addr_decrypted",
                 "user_agent_decrypted"},
}
_LIB_KEYS = ("tracks", "albums", "artists", "shows", "episodes")
_SAMPLE = 100


def _minute(ts: str) -> str:
    return ts[:16]


def _std_time(v) -> str | None:
    try:
        return datetime.strptime(str(v), "%Y-%m-%d %H:%M").replace(tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return iso_utc(v)


def _first(e: Entry, prefix: str):
    with e.open() as raw:
        return next(ijson.items(strip_bom(raw), prefix, use_float=True), None)


class _Scan:
    def __init__(self) -> None:
        self.files: list[tuple[str, Entry]] = []
        self.ignored = 0
        self.empty: list[Entry] = []
        self.corrupt: list[str] = []
        self.bad_zips: list[str] = []


class Spotify(ScanImporter):
    name = NAME

    def _do_scan(self, arc) -> _Scan:
        sc = _Scan()
        sc.bad_zips = arc.bad_zips
        for e in arc.entries:
            if not e.name.lower().endswith(".json"):
                continue
            s = peek(e).lstrip()
            try:
                if s.startswith(b"["):
                    rec = _first(e, "item")
                    if rec is None:
                        sc.empty.append(e)
                    elif isinstance(rec, dict):
                        keys = set(rec)
                        if {"ts", "ms_played"} <= keys:
                            sc.files.append(("extended", e))
                        elif {"endTime", "msPlayed", "trackName", "artistName"} <= keys:
                            sc.files.append(("standard_music", e))
                        elif {"endTime", "msPlayed"} <= keys and ("podcastName" in keys or "episodeName" in keys):
                            sc.files.append(("standard_podcast", e))
                        elif {"searchTime", "searchQuery"} <= keys:
                            sc.files.append(("search", e))
                        else:
                            sc.ignored += 1
                    else:
                        sc.ignored += 1
                elif s.startswith(b"{"):
                    if b'"playlists"' in s[:200]:
                        rec = _first(e, "playlists.item")
                        if isinstance(rec, dict) and "items" in rec:
                            sc.files.append(("playlists", e))
                            continue
                    lib = next((k for k in _LIB_KEYS if f'"{k}"'.encode() in s[:200]), None)
                    if lib and isinstance(_first(e, f"{lib}.item"), dict):
                        sc.files.append(("library", e))
                    else:
                        sc.ignored += 1
                else:
                    sc.ignored += 1
            except (ijson.JSONError, UnicodeDecodeError, OSError):
                sc.corrupt.append(e.name)
        return sc

    def detect(self, path: Path) -> DetectResult:
        try:
            _, sc = self._scan(path)
        except FormatError as e:
            return DetectResult(False, 0.0, str(e))
        if sc.files:
            return DetectResult(True, 0.9, "Spotify kayıtları: " + ", ".join(sorted({s for s, _ in sc.files})))
        return DetectResult(False, 0.0, "Spotify dinleme/kütüphane/arama JSON'u bulunamadı")

    def verify_format(self, path: Path) -> FormatReport:
        _, sc = self._scan(path)
        rep = FormatReport(importer=NAME, ok=bool(sc.files) and not sc.corrupt and not sc.bad_zips)
        for shape, e in sc.files:
            rep.found_files.append(f"{shape}: {e.name} ({e.size} bayt)")
            known = _KNOWN.get(shape)
            if known:
                extra: set[str] = set()
                try:
                    with e.open() as raw:
                        for n, rec in enumerate(ijson.items(strip_bom(raw), "item", use_float=True)):
                            if n >= _SAMPLE:
                                break
                            if isinstance(rec, dict):
                                extra |= set(rec) - known
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
            rep.missing.append("StreamingHistory / Streaming_History_Audio / Playlist / YourLibrary / SearchQueries JSON'u")
        if sc.ignored:
            rep.notes.append(f"{sc.ignored} JSON dosyası tanınan şekle uymadığı için yok sayıldı (kimlik dosyaları dahil)")
        rep.notes.append("ip, kullanıcı adı, kullanıcı aracısı ve bağlantı ülkesi alanları bilerek okunmaz")
        if any(s in ("library", "standard_music") for s, _ in sc.files):
            rep.notes.append("Kütüphane kayıtlarında olay zamanı arşiv dosyasının tarihidir (zaman_kaynagi=dosya_tarihi)")
        return rep

    def input_files(self, path: Path) -> list[Origin]:
        _, sc = self._scan(path)
        seen: dict[Path, Origin] = {}
        for _, e in sc.files:
            seen.setdefault(e.origin.path, e.origin)
        return list(seen.values())

    def parse(self, path: Path) -> Iterator[EventIn]:
        _, sc = self._scan(path)
        for shape, e in sc.files:
            n = 0
            try:
                for rec in self._records(shape, e):
                    n += 1
                    if not isinstance(rec[1] if shape == "library" else rec, dict):
                        self._skip(f"{shape}: kayıt nesne değil")
                        continue
                    yield from getattr(self, f"_ev_{shape}")(rec, e)
            except (ijson.JSONError, UnicodeDecodeError) as exc:
                raise FormatError(
                    f"{e.name}: JSON {n}. kayıttan sonra bozuk ({type(exc).__name__}). "
                    "Önceki kayıtlar eklendi; dosya düzeldikten sonra yeniden alın."
                ) from None

    @staticmethod
    def _records(shape: str, e: Entry):
        def gen(prefix, tag=None):
            with e.open() as raw:
                for rec in ijson.items(strip_bom(raw), prefix, use_float=True):
                    yield rec if tag is None else (tag, rec)

        if shape == "playlists":
            yield from gen("playlists.item")
        elif shape == "library":
            for k in _LIB_KEYS:
                yield from gen(f"{k}.item", k)
        else:
            yield from gen("item")

    # --- dinleme
    def _ev_standard_music(self, r, e):
        ts = _std_time(r.get("endTime"))
        name, artist = r.get("trackName"), r.get("artistName")
        if ts is None or not name:
            self._skip("standart müzik: endTime/trackName yok")
            return
        yield EventIn(ts=ts, kind="spotify.dinleme", category=Category.MUZIK,
                      payload={"sarki": name, "sanatci": artist, "sure_ms": r.get("msPlayed")},
                      text=f"{name} {artist or ''}".strip(),
                      event_key=stable_key("sp", "dinleme", _minute(ts), name, artist))

    def _ev_standard_podcast(self, r, e):
        ts = _std_time(r.get("endTime"))
        ep, show = r.get("episodeName"), r.get("podcastName")
        if ts is None or not (ep or show):
            self._skip("standart podcast: endTime/ad yok")
            return
        yield EventIn(ts=ts, kind="spotify.podcast", category=Category.MUZIK,
                      payload={"bolum": ep, "program": show, "sure_ms": r.get("msPlayed")},
                      text=f"{ep or ''} {show or ''}".strip(),
                      event_key=stable_key("sp", "podcast", _minute(ts), ep, show))

    def _ev_extended(self, r, e):
        ts = iso_utc(r.get("ts"))
        if ts is None:
            self._skip("genişletilmiş: ts okunamadı")
            return
        track, artist = r.get("master_metadata_track_name"), r.get("master_metadata_album_artist_name")
        ep, show = r.get("episode_name"), r.get("episode_show_name")
        common = {"sure_ms": r.get("ms_played"), "platform": r.get("platform"),
                  "baslama_nedeni": r.get("reason_start"), "bitis_nedeni": r.get("reason_end"),
                  "karisik": r.get("shuffle"), "atlandi": r.get("skipped"), "cevrimdisi": r.get("offline"),
                  "gizli_mod": r.get("incognito_mode")}
        common = {k: v for k, v in common.items() if v is not None}
        if track:
            yield EventIn(ts=ts, kind="spotify.dinleme", category=Category.MUZIK,
                          payload={"sarki": track, "sanatci": artist,
                                   "album": r.get("master_metadata_album_album_name"),
                                   "uri": r.get("spotify_track_uri"), **common},
                          text=f"{track} {artist or ''}".strip(),
                          event_key=stable_key("sp", "dinleme", _minute(ts), track, artist))
        elif ep or show:
            yield EventIn(ts=ts, kind="spotify.podcast", category=Category.MUZIK,
                          payload={"bolum": ep, "program": show, "uri": r.get("spotify_episode_uri"), **common},
                          text=f"{ep or ''} {show or ''}".strip(),
                          event_key=stable_key("sp", "podcast", _minute(ts), ep, show))
        elif r.get("audiobook_title"):
            yield EventIn(ts=ts, kind="spotify.sesli_kitap", category=Category.MUZIK,
                          payload={"kitap": r["audiobook_title"], "bolum": r.get("audiobook_chapter_title"), **common},
                          text=r["audiobook_title"],
                          event_key=stable_key("sp", "kitap", _minute(ts), r["audiobook_title"],
                                               r.get("audiobook_chapter_title")))
        else:
            self._skip("genişletilmiş: parça/bölüm/kitap adı yok")

    # --- arama
    def _ev_search(self, r, e):
        ts = iso_utc(r.get("searchTime"))
        q = r.get("searchQuery")
        if ts is None or not q:
            self._skip("arama: searchTime/searchQuery yok")
            return
        yield EventIn(ts=ts, kind="spotify.arama", category=Category.MUZIK,
                      payload={"sorgu": q, "platform": r.get("platform"),
                               "etkilesim_sayisi": len(r.get("searchInteractionURIs") or [])},
                      text=q, event_key=stable_key("sp", "arama", ts, q))

    # --- çalma listeleri
    def _ev_playlists(self, pl, e):
        name = pl.get("name") or ""
        for it in pl.get("items") or []:
            t = (it or {}).get("track") or {}
            ep = (it or {}).get("episode") or {}
            title = t.get("trackName") or ep.get("episodeName")
            ts = iso_utc(it.get("addedDate")) or iso_utc(pl.get("lastModifiedDate"))
            if not title or ts is None:
                self._skip("çalma listesi: öğe adı/tarih yok")
                continue
            artist = t.get("artistName") or ep.get("showName")
            yield EventIn(ts=ts, kind="spotify.liste_ogesi", category=Category.MUZIK,
                          payload={"liste": name, "ad": title, "sanatci": artist, "album": t.get("albumName"),
                                   "uri": t.get("trackUri") or ep.get("episodeUri")},
                          text=f"{title} {artist or ''} {name}".strip(),
                          event_key=stable_key("sp", "liste", name, t.get("trackUri") or title, artist))

    # --- kütüphane (zamansız anlık görüntü)
    def _ev_library(self, item, e):
        tag, r = item
        if not isinstance(r, dict):
            return
        ts = iso_utc(e.mtime)
        name = r.get("track") or r.get("album") or r.get("name") or r.get("episode")
        if not name:
            self._skip("kütüphane: ad yok")
            return
        artist = r.get("artist") or r.get("publisher")
        yield EventIn(ts=ts, kind=f"spotify.kutuphane_{tag}", category=Category.MUZIK,
                      payload={"ad": name, "sanatci": artist, "uri": r.get("uri"), "zaman_kaynagi": "dosya_tarihi"},
                      text=f"{name} {artist or ''}".strip(),
                      event_key=stable_key("sp", "kutuphane", tag, r.get("uri") or name, artist))


def factory() -> Spotify:
    return Spotify()
