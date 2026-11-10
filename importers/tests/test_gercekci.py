"""Gerçeğe yakın biçimli (uydurma) dosyalar: fixtures/gercekci/ (üretici: fixtures/uret_gercekci.py).

Biçim kaynakları ve doğrulama durumu: importers/BICIM-DENETIMI.md ve DOGRULAMA-DURUMU.md.
Bu testler "sahte gerçeğe-yakın veriyle geçti" demektir; gerçek veriyle doğrulama DEĞİLDİR.
"""
from __future__ import annotations

import io
import json
from collections import Counter

import pytest
from conftest import FIX, count_events
from kimlikimport import registry
from kimlikimport.base import iso_utc, strip_bom
from kimlikimport.mbox import _labels
from kimlikimport.run import run

G = FIX / "gercekci"


def kinds(hub):
    return Counter(e.kind for e in hub.timeline(limit=100000))


def test_takeout_turkce_adli_bom_konum_gemini(hub):
    r = run(hub, G / "takeout_tr_gercekci", "google_takeout")
    k = kinds(hub)
    assert (r.parsed, r.added) == (14, 14)
    assert k["youtube.izleme"] == 2 and k["youtube.begeni"] == 1 and k["youtube.abonelik"] == 1
    assert k["google.konum_kaydi"] == 3 and k["google.yer_ziyareti"] == 1 and k["google.hareket"] == 1
    assert k["sohbet.mesaj"] == 3 and k["gmail.ileti"] == 1 and k["chrome.ziyaret"] == 1
    assert r.skipped == {"konum kaydı: koordinat aralık dışı": 1, "yarı anlamlı konum: tanınmayan nesne türü": 1}
    tx = {e.text for e in hub.timeline(limit=100) if e.kind == "sohbet.mesaj"}
    assert "Örnek bir soru sor" in tx and "Another sample question" in tx  # iki dilde istem öneki atıldı
    assert "Örnek yanıt metni." in tx  # safeHtmlItem -> düz metin


def test_takeout_konum_kategorisi_ve_timestampms(hub):
    run(hub, G / "takeout_tr_gercekci", "google_takeout")
    konum = [e for e in hub.timeline(limit=100) if e.category == "konum"]
    assert len(konum) == 5
    assert "2025-01-10T09:00:00Z" in {e.ts for e in konum}  # ISO timestamp
    assert "2025-01-10T09:06:40Z" in {e.ts for e in konum}  # timestampMs: 1736500000000


def test_takeout_etiket_tirnakli_virgul(hub):
    run(hub, G / "takeout_tr_gercekci", "google_takeout")
    m = next(e for e in hub.timeline(limit=100) if e.kind == "gmail.ileti")
    assert m.payload["etiketler"] == ["Inbox", "Örnek, virgüllü etiket", "Important"]
    assert _labels('Inbox,"A, B",Sent') == ["Inbox", "A, B", "Sent"] and _labels("") == []


def test_yeni_timeline_json(hub):
    imp = registry.create("google_takeout")
    rep = imp.verify_format(G / "timeline_yeni")
    assert rep.ok and any("doğrulanmadı" in n for n in rep.notes)
    r = run(hub, G / "timeline_yeni", "google_takeout")
    assert (r.added, r.skipped) == (2, {"zaman çizelgesi: yol noktaları (timelinePath) alınmıyor": 1})
    visit = next(e for e in hub.timeline(limit=10) if e.kind == "google.yer_ziyareti")
    assert visit.ts == "2025-02-01T05:00:00Z"  # +03:00 -> UTC
    assert abs(visit.payload["enlem"] - 41.0123456) < 1e-9


def test_chatgpt_parcali_dal_arac_dusunce(hub):
    r = run(hub, G / "chatgpt_parcali", "chatgpt")
    assert r.added == 8  # 2 başlık + 6 mesaj
    tx = " ".join(e.text for e in hub.timeline(limit=100))
    assert "Sesli soru: kaç dakika?" in tx  # audio_transcription parçası
    assert "gizli düşünce" not in tx and "eski, yeniden üretilen dal" not in tx and "search('çay')" not in tx
    assert r.skipped.get("chatgpt: araç çağrısı (alıcı all değil) atlandı") == 1
    rep = registry.create("chatgpt").verify_format(G / "chatgpt_parcali")
    assert rep.ok and any("yeni_bilinmeyen_alan" in x for x in rep.unexpected_fields)


def test_cesu8_vekil_yarimlari_onarilir(hub, tmp_path):
    cesu = b'[{"title":"T","create_time":1.0,"current_node":"a","conversation_id":"c1","mapping":{' \
           b'"r":{"id":"r","message":null,"parent":null,"children":["a"]},' \
           b'"a":{"id":"a","parent":"r","children":[],"message":{"id":"m","author":{"role":"user"},"create_time":2.0,' \
           b'"content":{"content_type":"text","parts":["merhaba \xed\xa0\xbd\xed\xb8\x80 d\xc3\xbcnya"]},"metadata":{}}}}}]'
    (tmp_path / "conversations.json").write_bytes(b"\xef\xbb\xbf" + cesu)
    run(hub, tmp_path, "chatgpt")
    assert any("merhaba 😀 dünya" == e.text for e in hub.timeline(limit=10))


def test_strip_bom_gecersiz_utf8_yine_hata_verir():
    with pytest.raises(UnicodeDecodeError):
        strip_bom(io.BytesIO(b'["\xe9"]')).read()
    assert strip_bom(io.BytesIO('["é😀"]'.encode())).read() == '["é😀"]'.encode()


def test_instagram_yeni_saved_string_map_ve_mojibake(hub):
    r = run(hub, G / "meta_instagram_yeni", "meta")
    k = kinds(hub)
    assert r.added == 7 and r.skipped == {}
    assert k["instagram.kaydedilen"] == 1  # saved_saved_media + string_map_data: eskiden sessizce 0 olay
    tx = {e.text for e in hub.timeline(limit=100)}
    assert "Güzel şey, çok beğendim" in tx and "İyiyim, teşekkürler 😀" in tx  # latin-1/UTF-8 bozuk kaçış düzeldi
    rep = registry.create("meta").verify_format(G / "meta_instagram_yeni")
    assert rep.ok and not rep.unexpected_fields


def test_spotify_2024_adlari_ip_alinmaz_ve_java_zaman_eki(hub):
    r = run(hub, G / "spotify_2024", "spotify")
    k = kinds(hub)
    assert k["spotify.dinleme"] == 1 and k["spotify.podcast"] == 1 and k["spotify.arama"] == 2
    assert k["spotify.liste_ogesi"] == 1 and k["spotify.kutuphane_tracks"] == 1
    assert r.duplicate == 2  # standart + genişletilmiş aynı dinleme/podcast
    assert "ip_addr" not in json.dumps([e.payload for e in hub.timeline(limit=100)]) and "203.0.113" not in json.dumps(
        [e.payload for e in hub.timeline(limit=100)])
    assert iso_utc("2025-01-05T18:20:00.000Z[UTC]") == "2025-01-05T18:20:00Z"
    rep = registry.create("spotify").verify_format(G / "spotify_2024")
    assert any("Streaming_History_Video" in x for x in rep.unexpected_fields)  # video dosyası: bilinmeyen alanlar raporlanır
