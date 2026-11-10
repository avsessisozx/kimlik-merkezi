from __future__ import annotations

import json
from collections import Counter

import pytest
from conftest import FIX, count_events
from kimlikcore import Category, FormatError
from kimlikimport import registry
from kimlikimport.base import ImportFormatError
from kimlikimport.chat import ChatGPT, Claude, GenericChat
from kimlikimport.run import run


def msgs(hub, platform=None):
    return [e for e in hub.timeline(categories=["sohbet"], limit=1000, ascending=True)
            if e.kind == "sohbet.mesaj" and (platform is None or e.payload["platform"] == platform)]


def test_kategori_hassas_ve_tanimli():
    assert "sohbet" in Category.ALL and "sohbet" in Category.SENSITIVE


def test_chatgpt_kayit_sayisi_ve_dal(hub, zipper):
    r = run(hub, zipper("chat_chatgpt"))
    assert r.importer == "chatgpt" and (r.parsed, r.added, r.duplicate) == (8, 8, 0)
    ev = hub.timeline(categories=["sohbet"], limit=100)
    assert Counter(e.kind for e in ev) == {"sohbet.mesaj": 6, "sohbet.konusma": 2}
    a = [e for e in msgs(hub, "chatgpt") if e.payload["konusma_id"] == "conv-a"]
    assert [(e.payload["rol"], e.text) for e in a] == [
        ("kullanici", "Merhaba chatgptozelkelime, ışık İstanbul"),
        ("asistan", "Selam, size nasıl yardımcı olabilirim?"),
        ("kullanici", "Yeni dal kullanıcı mesajı"),  # görsel işaretçisi alınmaz
        ("asistan", "```\nprint('merhaba')\n```")]
    assert "Eski dal" not in "".join(e.text for e in ev)  # terk edilen dal yok
    assert a[1].payload["model"] == "gpt-4o" and a[0].payload["baslik"] == "Ornek sohbet bir"
    assert a[0].ts == "2023-11-14T22:13:30Z" and a[0].payload["ts"] == a[0].ts
    assert {e.category for e in ev} == {"sohbet"}
    assert hub.search("ISIK istanbul", categories=["sohbet"])


def test_chatgpt_atlananlar_ve_unicode(hub):
    r = run(hub, FIX / "chat_chatgpt")
    assert r.skipped == {"chatgpt: system mesajı atlandı": 1,
                         "chatgpt: içerik türü atlandı (thoughts)": 1}
    b = [e for e in msgs(hub) if e.payload["konusma_id"] == "conv-b"][0]
    assert b.text.startswith("Emoji 😀 ve bozuk vekil") and "\ud83d" not in b.text.encode("utf-8", "replace").decode()
    json.dumps(b.payload, ensure_ascii=False).encode("utf-8")  # kodlanabilir
    # user.json (kimlik) okunmaz
    assert "gizli@example.test" not in json.dumps([e.payload for e in hub.timeline(limit=100)])


def test_iki_kez_ve_yeni_mesaj_eklenince_tekrarsiz(hub, zipper, tmp_path):
    z = zipper("chat_chatgpt")
    a = run(hub, z)
    b = run(hub, z)
    assert b.source_id == a.source_id and (b.added, b.duplicate) == (0, 8)
    # daha yeni dışa aktarma: aynı konuşmaya bir mesaj eklenmiş
    d = tmp_path / "yeni"
    d.mkdir()
    data = json.loads((FIX / "chat_chatgpt/conversations.json").read_text())
    m = data[1]["mapping"]
    m["b3"]["children"] = ["b4"]
    m["b4"] = {"id": "b4", "parent": "b3", "children": [], "message": {
        "id": "b4", "author": {"role": "user"}, "create_time": 1700100100.0,
        "content": {"content_type": "text", "parts": ["Yeni soru"]}, "metadata": {}}}
    data[1]["current_node"] = "b4"
    (d / "conversations.json").write_text(json.dumps(data), encoding="utf-8")
    c = run(hub, d)
    assert (c.added, c.duplicate) == (1, 8)
    assert count_events(hub, categories=["sohbet"]) == 9


def test_claude(hub, zipper):
    r = run(hub, zipper("chat_claude"))
    assert r.importer == "claude" and (r.parsed, r.added) == (6, 6)
    ms = msgs(hub, "claude")
    assert [(e.payload["rol"], e.text) for e in ms] == [
        ("kullanici", "Merhaba claudeozelkelime"), ("asistan", "Merhaba! Nasıl yardımcı olabilirim?"),
        ("kullanici", "İkinci konuşma soru"), ("asistan", "İkinci konuşma yanıt")]
    assert ms[0].payload["ekler"] == ["notlar.txt"] and ms[0].payload["mesaj_id"] == "cm-1"
    blob = json.dumps([e.payload for e in hub.timeline(limit=100)]) + "".join(e.text for e in hub.timeline(limit=100))
    for secret in ("gizliekicerik", "gizli dusunce", "gizli@example.test", "acc-gizli", "Gizli Kisi"):
        assert secret not in blob
    titles = {e.payload["konusma_id"]: e.text for e in hub.timeline(categories=["sohbet"], limit=100) if e.kind == "sohbet.konusma"}
    assert titles == {"cl-1": "Claude sohbeti bir", "cl-2": "(başlıksız)"}


def test_genel_dosyalar(hub):
    r = run(hub, FIX / "chat_generic", "chat_file")
    # deepseek 1+2, md 1+3, txt 1+4, jsonl 1+2
    assert (r.parsed, r.added) == (3 + 4 + 5 + 3, 15)
    ds = [e for e in msgs(hub) if e.payload["konusma_id"] == "ds-1"]
    assert [e.payload["rol"] for e in ds] == ["kullanici", "asistan"] and ds[1].payload["model"] == "deepseek-chat"
    assert ds[0].ts == "2025-01-05T10:00:00Z" and "zaman_kaynagi" not in ds[0].payload
    md = [e for e in msgs(hub) if e.payload["baslik"] == "sohbet"]
    assert [e.payload["rol"] for e in md] == ["kullanici", "asistan", "kullanici"]
    assert md[0].text == "Türkçe soru: ışık nedir?\nikinci satır" and md[2].text == "son soru mdozelkelime"
    assert md[0].payload["zaman_kaynagi"] == "dosya_tarihi" and md[0].payload["sira"] == 0
    assert md[1].payload["model"] == "Claude"
    js = [e for e in msgs(hub) if e.text.startswith("jsonl")]
    assert js[0].ts == "2024-12-24T00:26:40Z"
    assert not hub.search("Bu bir sohbet değil", categories=["sohbet"])  # alakasız dosya yok sayıldı


def test_genel_tekrarsiz(hub):
    run(hub, FIX / "chat_generic", "dosyalar" if False else "chat_file")
    r = run(hub, FIX / "chat_generic", "deepseek")  # takma ad
    assert r.added == 0 and r.duplicate == 15


def test_gemini_takeout(hub, zipper):
    r = run(hub, zipper("takeout_gemini"))
    assert r.importer == "google_takeout" and (r.parsed, r.added) == (5, 5)
    ev = hub.timeline(categories=["sohbet"], limit=100, ascending=True)
    assert {e.payload["platform"] for e in ev} == {"gemini"} and len(ev) == 5
    assert ev[0].text == "Gemini sorusu bir geminiozelkelime" and ev[0].payload["rol"] == "kullanici"
    assert ev[1].text == "Gemini yaniti bir" and ev[1].payload["rol"] == "asistan"
    assert count_events(hub, categories=["tarama", "uygulama"]) == 0
    assert run(hub, zipper("takeout_gemini")).added == 0


def test_otomatik_tanima(zipper):
    for n, want in (("chat_chatgpt", "chatgpt"), ("chat_claude", "claude")):
        imp, _ = registry.detect_best(zipper(n))
        assert imp.name == want
    imp, _ = registry.detect_best(FIX / "chat_generic")
    assert imp.name == "chat_file"
    imp, _ = registry.detect_best(zipper("takeout_en"))
    assert imp.name == "google_takeout"  # sohbet importerları Takeout'u kapmaz


def test_bozuk_ve_eksik(hub, tmp_path):
    d = tmp_path / "x"
    d.mkdir()
    (d / "conversations.json").write_text('[{"title": "t", "mapping": {"a": {"id": "a"}}, "current_node": "a", "create_time": 1}, {"mapping"')
    with pytest.raises(FormatError):
        run(hub, d, "chatgpt")
    e = tmp_path / "e"
    e.mkdir()
    (e / "conversations.json").write_text('[{"foo": 1}]')
    with pytest.raises(ImportFormatError) as ei:
        run(hub, e, "claude")
    assert "chat_messages" in str(ei.value) or "bulunamadı" in str(ei.value)
    assert count_events(hub) == 0


def test_rapor_icerik_icermez():
    for imp, path in ((ChatGPT(), FIX / "chat_chatgpt"), (Claude(), FIX / "chat_claude"), (GenericChat(), FIX / "chat_generic")):
        txt = imp.verify_format(path).to_text()
        for secret in ("chatgptozelkelime", "claudeozelkelime", "deepseekozelkelime", "mdozelkelime", "Merhaba"):
            assert secret not in txt, (imp.name, secret)
        assert "sohbet" in txt


def test_cekirdek_kategoriyi_bilmiyorsa_durur(hub, monkeypatch):
    monkeypatch.setattr(Category, "ALL", frozenset(Category.ALL - {"sohbet"}))
    with pytest.raises(ImportFormatError) as ei:
        run(hub, FIX / "chat_claude", "claude")
    assert "sohbet" in str(ei.value) and hub.sources() == []
