"""Gerçeğe yakın BİÇİMLİ, tamamen UYDURMA dosyalar üretir (importers/fixtures/gercekci/).

Kullanım: python uret_gercekci.py [hedef_klasör]   (varsayılan: bu dosyanın yanındaki gercekci/)
Kişiler, yerler, metinler uydurmadır; koordinatlar haritada rastgele açık bir noktadır. Biçimler
importers/BICIM-DENETIMI.md'deki kaynaklara göre kurulmuştur; Türkçe klasör adları VARSAYIMDIR.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "gercekci"


def w(p: str, text: str | bytes, *, bom: bool = False) -> None:
    f = root / p
    f.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, str):
        text = ("﻿" if bom else "") + text
        f.write_text(text, encoding="utf-8")
    else:
        f.write_bytes(text)


def wj(p: str, obj, *, bom: bool = False, ascii_only: bool = False) -> None:
    w(p, json.dumps(obj, ensure_ascii=ascii_only, indent=2), bom=bom)


def meta_mojibake(obj):
    """Meta'nın bozuk kaçışı: UTF-8 baytları latin-1 sanılıp \\u00XX olarak yazılır."""
    if isinstance(obj, str):
        return obj.encode("utf-8").decode("latin-1")
    if isinstance(obj, list):
        return [meta_mojibake(x) for x in obj]
    if isinstance(obj, dict):
        return {k: meta_mojibake(v) for k, v in obj.items()}
    return obj


# ----------------------------------------------------------------------------- Takeout (Türkçe adlı, BOM'lu)
T = "takeout_tr_gercekci/Takeout"
YT = "https://www.youtube.com"
wj(f"{T}/YouTube ve YouTube Music/geçmiş/izleme geçmişi.json", [
    {"header": "YouTube", "title": "Watched Örnek Çay Demleme Videosu", "titleUrl": f"{YT}/watch?v=AAAAAAAAAAA",
     "subtitles": [{"name": "Örnek Kanal", "url": f"{YT}/channel/UCzzzzzzzzzzzzzzzzzzzzzz"}],
     "time": "2025-02-03T19:04:05.678Z", "products": ["YouTube"],
     "activityControls": ["YouTube watch history"], "details": [{"name": "From Google Ads"}]},
    {"header": "YouTube", "title": "Watched https://www.youtube.com/watch?v=BBBBBBBBBBB",
     "titleUrl": f"{YT}/watch?v=BBBBBBBBBBB", "time": "2025-02-04T08:00:00Z", "products": ["YouTube"],
     "activityControls": ["YouTube watch history"]},
], bom=True)
wj(f"{T}/YouTube ve YouTube Music/çalma listeleri/likes.json", [
    {"contentDetails": {"videoId": "CCCCCCCCCCC", "videoPublishedAt": "2024-01-01T00:00:00.000Z"},
     "etag": "etag1", "id": "pl1", "kind": "youtube#playlistItem",
     "snippet": {"channelId": "UCuuuuuuuuuuuuuuuuuuuuuu", "channelTitle": "Örnek Hesap", "description": "",
                 "playlistId": "LL", "position": 0, "publishedAt": "2024-05-06T07:08:09.000Z",
                 "resourceId": {"kind": "youtube#video", "videoId": "CCCCCCCCCCC"},
                 "thumbnails": {}, "title": "Örnek Beğenilen Video", "videoOwnerChannelTitle": "Örnek Kanal"},
     "status": {"privacyStatus": "private"}}])
w(f"{T}/YouTube ve YouTube Music/abonelikler/abonelikler.csv",
  "Kanal Kimliği,Kanal URL'si,Kanal başlığı\n"
  "UCaaaaaaaaaaaaaaaaaaaaaa,http://www.youtube.com/channel/UCaaaaaaaaaaaaaaaaaaaaaa,Örnek Kanal Bir\n")
wj(f"{T}/Konum Geçmişi/Records.json", {"locations": [
    {"latitudeE7": 410000000, "longitudeE7": 290000000, "accuracy": 18, "source": "WIFI", "deviceTag": -1,
     "timestamp": "2025-01-10T09:00:00.123Z", "platformType": "ANDROID", "formFactor": "PHONE",
     "serverTimestamp": "2025-01-10T09:00:05.000Z", "deviceTimestamp": "2025-01-10T09:00:00.000Z",
     "batteryCharging": False, "osLevel": 33, "deviceDesignation": "PRIMARY"},
    {"latitudeE7": 410010000, "longitudeE7": 290020000, "accuracy": 30, "source": "CELL", "timestampMs": "1736500000000",
     "activity": [{"activity": [{"type": "STILL", "confidence": 90}], "timestamp": "2025-01-10T09:01:00Z"}]},
    {"latitudeE7": 999999999999, "longitudeE7": 0, "timestamp": "2025-01-10T09:02:00Z"},
    {"yeniAlan": "bilinmeyen", "latitudeE7": 410020000, "longitudeE7": 290030000, "timestamp": "2025-01-10T09:03:00Z"},
]})
wj(f"{T}/Konum Geçmişi/Semantic Location History/2025/2025_OCAK.json", {"timelineObjects": [
    {"placeVisit": {"location": {"latitudeE7": 410000000, "longitudeE7": 290000000, "placeId": "ChIJornek1",
                                 "address": "Örnek Cad. No:1, Örnekşehir", "name": "Örnek Kafe",
                                 "semanticType": "TYPE_UNKNOWN", "locationConfidence": 80},
                    "duration": {"startTimestamp": "2025-01-10T09:00:00.000Z", "endTimestamp": "2025-01-10T10:00:00.000Z"},
                    "placeConfidence": "HIGH_CONFIDENCE", "visitConfidence": 90, "placeVisitType": "SINGLE_PLACE",
                    "placeVisitImportance": "MAIN", "editConfirmationStatus": "NOT_CONFIRMED"}},
    {"activitySegment": {"startLocation": {"latitudeE7": 410000000, "longitudeE7": 290000000},
                         "endLocation": {"latitudeE7": 410100000, "longitudeE7": 290100000},
                         "duration": {"startTimestamp": "2025-01-10T10:00:00Z", "endTimestamp": "2025-01-10T10:20:00Z"},
                         "distance": 4200, "activityType": "IN_PASSENGER_VEHICLE", "confidence": "HIGH",
                         "activities": [{"activityType": "IN_PASSENGER_VEHICLE", "probability": 0.9}]}},
    {"yeniTur": {"x": 1}},
]})
wj(f"{T}/Etkinliğim/Gemini Uygulamaları/Etkinliğim.json", [
    {"header": "Gemini Apps", "title": "Sorulan istem: Örnek bir soru sor", "time": "2025-03-01T12:00:00.000Z",
     "products": ["Gemini Apps"], "activityControls": ["Gemini Apps Activity"],
     "safeHtmlItem": [{"html": "<p>Örnek <b>yanıt</b> metni.</p>"}]},
    {"header": "Gemini Apps", "title": "Prompted Another sample question", "time": "2025-03-02T12:00:00Z",
     "products": ["Gemini Apps"]},
])
wj(f"{T}/Chrome/History.json", {"Browser History": [
    {"favicon_url": "https://example.test/f.ico", "page_transition": "LINK", "title": "Örnek Sayfa",
     "url": "https://example.test/a", "client_id": "cid", "time_usec": 1738600000000000}]})
w(f"{T}/Posta/Tüm posta Spam ve Çöp Kutusu dahil.mbox",
  "From 1800000000000000001@xxx Mon Feb 03 10:00:00 +0000 2025\n"
  "X-GM-THRID: 1800000000000000001\nX-Gmail-Labels: Inbox,\"Örnek, virgüllü etiket\",Important\n"
  "Date: Mon, 3 Feb 2025 13:00:00 +0300\nFrom: Örnek Gönderen <gonderen@example.test>\nTo: ben@example.test\n"
  "Subject: =?UTF-8?B?w5ZybmVrIGtvbnU=?=\nMessage-ID: <g1@example.test>\nMIME-Version: 1.0\n"
  "Content-Type: text/plain; charset=UTF-8\n\nMerhaba, uydurma ileti.\n\n")

# Yeni telefon dışa aktarımı (Timeline.json, semanticSegments) - topluluk kaynaklı biçim
wj("timeline_yeni/Timeline.json", {
    "semanticSegments": [
        {"startTime": "2025-02-01T08:00:00.000+03:00", "endTime": "2025-02-01T09:00:00.000+03:00",
         "startTimeTimezoneUtcOffsetMinutes": 180, "endTimeTimezoneUtcOffsetMinutes": 180,
         "visit": {"hierarchyLevel": 0, "probability": 0.9, "topCandidate": {
             "placeId": "ChIJornek2", "semanticType": "HOME", "probability": 0.8,
             "placeLocation": {"latLng": "41.0123456°, 29.0123456°"}}}},
        {"startTime": "2025-02-01T09:00:00.000+03:00", "endTime": "2025-02-01T09:30:00.000+03:00",
         "activity": {"start": {"latLng": "41.0123456°, 29.0123456°"}, "end": {"latLng": "41.0500000°, 29.0500000°"},
                      "distanceMeters": 5000.5, "probability": 0.7,
                      "topCandidate": {"type": "IN_PASSENGER_VEHICLE", "probability": 0.6}}},
        {"startTime": "2025-02-01T09:30:00.000+03:00", "endTime": "2025-02-01T09:40:00.000+03:00",
         "timelinePath": [{"point": "41.05°, 29.05°", "time": "2025-02-01T09:31:00.000+03:00"}]},
    ],
    "rawSignals": [{"position": {"LatLng": "41.0°, 29.0°", "accuracyMeters": 20, "altitudeMeters": 10.0,
                                 "source": "GPS", "timestamp": "2025-02-01T08:01:00.000+03:00"}}],
    "userLocationProfile": {"frequentPlaces": []},
})

# ----------------------------------------------------------------------------- ChatGPT (parçalı)
def node(nid, parent, children, role=None, parts=None, ctype="text", t=None, **kw):
    msg = None
    if role:
        content = {"content_type": ctype, "parts": parts if parts is not None else []}
        content.update(kw.pop("content_extra", {}))
        msg = {"id": nid, "author": {"role": role, "name": kw.pop("name", None), "metadata": {}},
               "create_time": t, "update_time": t, "content": content, "status": "finished_successfully",
               "end_turn": True, "weight": 1.0, "metadata": kw.pop("meta", {}),
               "recipient": kw.pop("recipient", "all"), "channel": None}
    return {"id": nid, "message": msg, "parent": parent, "children": children}


conv1 = {
    "title": "Örnek çay sohbeti", "create_time": 1738000000.123, "update_time": 1738000500.5,
    "mapping": {
        "root": node("root", None, ["sys"]),
        "sys": node("sys", "root", ["u1"], "system", [""], t=None, meta={"is_visually_hidden_from_conversation": True}),
        "u1": node("u1", "sys", ["a1", "a1b"], "user", ["Çay nasıl demlenir?"], t=1738000010.0,
                   meta={"request_id": "r1"}),
        "a1b": node("a1b", "u1", [], "assistant", ["(eski, yeniden üretilen dal)"], t=1738000020.0,
                    meta={"model_slug": "gpt-4o"}),
        "a1": node("a1", "u1", ["tc", ], "assistant", ["Önce suyu kaynatın."], t=1738000030.0,
                   meta={"model_slug": "gpt-4o", "finish_details": {"type": "stop"}}),
        "tc": node("tc", "a1", ["to"], "assistant", ["search('çay')"], ctype="code", t=1738000040.0,
                   recipient="browser", content_extra={"language": "unknown", "text": "search('çay')"}),
        "to": node("to", "tc", ["u2"], "tool", [""], ctype="tether_browsing_display", t=1738000050.0, name="browser",
                   content_extra={"result": "x", "summary": None}),
        "u2": node("u2", "to", ["a2"], "user",
                   [{"content_type": "audio_transcription", "text": "Sesli soru: kaç dakika?", "direction": "in", "decoding_id": None},
                    {"content_type": "audio_asset_pointer", "asset_pointer": "sediment://file_x", "size_bytes": 10}],
                   ctype="multimodal_text", t=1738000060.0),
        "a2": node("a2", "u2", ["a3"], "assistant", [], ctype="thoughts", t=1738000070.0,
                   content_extra={"thoughts": [{"summary": "x", "content": "gizli düşünce", "finished": True}]}),
        "a3": node("a3", "a2", [], "assistant", ["Üç dakika."], t=1738000080.0, meta={"model_slug": "gpt-4o"}),
    },
    "moderation_results": [], "current_node": "a3", "conversation_id": "c0000001-0000-4000-8000-000000000001",
    "default_model_slug": "gpt-4o", "safe_urls": [], "blocked_urls": [], "gizmo_id": None, "is_archived": False,
    "is_starred": None, "memory_scope": "global_enabled", "yeni_bilinmeyen_alan": {"x": 1},
}
conv2 = {
    "title": None, "create_time": 1739000000.0, "update_time": 1739000100.0,
    "mapping": {"root": node("root", None, ["u"]),
                "u": node("u", "root", ["a"], "user", ["Tek satırlık soru"], t=1739000010.0),
                "a": node("a", "u", [], "assistant", ["Tek satırlık yanıt"], t=1739000020.0, meta={"model_slug": "o3"})},
    "current_node": "a", "id": "c0000002-0000-4000-8000-000000000002",
}
wj("chatgpt_parcali/conversations-000.json", [conv1])
wj("chatgpt_parcali/conversations-001.json", [conv2])
wj("chatgpt_parcali/export_manifest.json", {"export_files": [
    {"path": "conversations-000.json", "size_bytes": 1}, {"path": "conversations-001.json", "size_bytes": 1}]})
wj("chatgpt_parcali/user.json", {"id": "user-ornek", "email": "ornek@example.test", "chatgpt_plus_user": False,
                                   "phone_number": None})
wj("chatgpt_parcali/message_feedback.json", [])

# ----------------------------------------------------------------------------- Meta Instagram (yeni sürüm adları)
IG = "meta_instagram_yeni/instagram-ornek-2025"
wj(f"{IG}/your_instagram_activity/saved/saved_posts.json", {"saved_saved_media": [
    {"title": "ornek_hesap", "string_map_data": {"Saved on": {"href": "https://www.instagram.com/p/AAAA1111/",
                                                                "timestamp": 1738400000}}}]}, ascii_only=True)
wj(f"{IG}/your_instagram_activity/comments/post_comments_1.json", [
    {"string_map_data": {"Comment": {"value": "Güzel şey, çok beğendim"},
                         "Media Owner": {"value": "ornek_hesap"},
                         "Time": {"timestamp": 1738500000}}}], ascii_only=True)
w(f"{IG}/your_instagram_activity/comments/post_comments_1.json",
  json.dumps([{"string_map_data": {"Comment": {"value": meta_mojibake("Güzel şey, çok beğendim")},
                                    "Media Owner": {"value": "ornek_hesap"},
                                    "Time": {"timestamp": 1738500000}}}], ensure_ascii=True, indent=2))
wj(f"{IG}/your_instagram_activity/likes/liked_posts.json", {"likes_media_likes": [
    {"title": "ornek_hesap", "string_list_data": [
        {"href": "https://www.instagram.com/p/BBBB2222/", "value": "❤", "timestamp": 1738600000}]}]}, ascii_only=True)
wj(f"{IG}/connections/followers_and_following/followers_1.json", [
    {"title": "", "media_list_data": [], "string_list_data": [
        {"href": "https://www.instagram.com/ornek_takipci", "value": "ornek_takipci", "timestamp": 1738700000}]}])
wj(f"{IG}/connections/followers_and_following/following.json", {"relationships_following": [
    {"title": "ornek_hesap", "string_list_data": [
        {"href": "https://www.instagram.com/ornek_hesap", "timestamp": 1738800000}]}]})
w(f"{IG}/your_instagram_activity/messages/inbox/ornekkisi_1234567890/message_1.json",
  json.dumps(meta_mojibake({
      "participants": [{"name": "Örnek Kişi"}, {"name": "Ben"}],
      "messages": [{"sender_name": "Örnek Kişi", "timestamp_ms": 1738900000000, "content": "Merhaba, nasılsın?", "is_geoblocked_for_viewer": False},
                   {"sender_name": "Ben", "timestamp_ms": 1738900060000, "content": "İyiyim, teşekkürler 😀",
                    "reactions": [{"reaction": "❤", "actor": "Örnek Kişi"}]}],
      "title": "Örnek Kişi", "is_still_participant": True, "thread_path": "inbox/ornekkisi_1234567890",
      "magic_words": []}), ensure_ascii=True, indent=2))

# ----------------------------------------------------------------------------- Spotify (2024 adları)
SP = "spotify_2024/Spotify Extended Streaming History"
wj(f"{SP}/Streaming_History_Audio_2023-2025_0.json", [
    {"ts": "2025-01-05T18:30:12Z", "platform": "windows", "ms_played": 187000, "conn_country": "TR",
     "ip_addr": "203.0.113.7", "master_metadata_track_name": "Örnek Şarkı", "master_metadata_album_artist_name": "Örnek Sanatçı",
     "master_metadata_album_album_name": "Örnek Albüm", "spotify_track_uri": "spotify:track:0000000000000000000001",
     "episode_name": None, "episode_show_name": None, "spotify_episode_uri": None,
     "audiobook_title": None, "audiobook_uri": None, "audiobook_chapter_uri": None, "audiobook_chapter_title": None,
     "reason_start": "trackdone", "reason_end": "trackdone", "shuffle": False, "skipped": False, "offline": False,
     "offline_timestamp": None, "incognito_mode": False},
    {"ts": "2025-01-05T18:33:20Z", "platform": "windows", "ms_played": 1200, "conn_country": "TR", "ip_addr": "203.0.113.7",
     "master_metadata_track_name": None, "master_metadata_album_artist_name": None, "master_metadata_album_album_name": None,
     "spotify_track_uri": None, "episode_name": "Örnek Bölüm", "episode_show_name": "Örnek Podcast",
     "spotify_episode_uri": "spotify:episode:0000000000000000000002", "audiobook_title": None, "audiobook_uri": None,
     "audiobook_chapter_uri": None, "audiobook_chapter_title": None, "reason_start": "clickrow", "reason_end": "fwdbtn",
     "shuffle": True, "skipped": True, "offline": False, "offline_timestamp": None, "incognito_mode": False},
])
wj(f"{SP}/Streaming_History_Video_2023-2025.json", [
    {"ts": "2025-01-06T10:00:00Z", "ms_played": 5000, "video_title": "x", "yeni_alan": 1}])
wj("spotify_2024/Spotify Account Data/StreamingHistory_music_0.json", [
    {"endTime": "2025-01-05 18:30", "artistName": "Örnek Sanatçı", "trackName": "Örnek Şarkı", "msPlayed": 187000}])
wj("spotify_2024/Spotify Account Data/StreamingHistory_podcast_0.json", [
    {"endTime": "2025-01-05 18:33", "podcastName": "Örnek Podcast", "episodeName": "Örnek Bölüm", "msPlayed": 1200}])
wj("spotify_2024/Spotify Account Data/Playlist1.json", {"playlists": [
    {"name": "Örnek Liste", "lastModifiedDate": "2025-01-02", "collaborators": [], "numberOfFollowers": 0,
     "description": None, "items": [
        {"track": {"trackName": "Örnek Şarkı", "artistName": "Örnek Sanatçı", "albumName": "Örnek Albüm",
                   "trackUri": "spotify:track:0000000000000000000001"},
         "episode": None, "audioBook": None, "localTrack": None, "addedDate": "2024-12-30"}]}]})
wj("spotify_2024/Spotify Account Data/YourLibrary.json", {
    "tracks": [{"artist": "Örnek Sanatçı", "album": "Örnek Albüm", "track": "Örnek Şarkı",
                "uri": "spotify:track:0000000000000000000001"}],
    "albums": [], "shows": [{"name": "Örnek Podcast", "publisher": "Örnek", "uri": "spotify:show:1"}],
    "episodes": [], "bannedTracks": [], "artists": [{"name": "Örnek Sanatçı", "uri": "spotify:artist:1"}],
    "bannedArtists": [], "other": []})
wj("spotify_2024/Spotify Account Data/SearchQueries.json", [
    {"platform": "WINDOWS", "searchTime": "2025-01-05T18:20:00.000Z[UTC]", "searchQuery": "örnek", "searchInteractionURIs": []},
    {"platform": "WINDOWS", "searchTime": "2025-01-05T18:21:00.000Z", "searchQuery": "ornek2", "searchInteractionURIs": ["spotify:track:1"]}])
wj("spotify_2024/Spotify Account Data/Userdata.json", {"username": "ornekkullanici", "email": "ornek@example.test"})
print("tamam:", root)
