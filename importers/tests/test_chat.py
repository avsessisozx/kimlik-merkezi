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


# --- Madde 2/3: kopya mesajlar (yeniden üretim, dosyalar arası, farklı kimlik) ---
def _metinler(hub):
    return [(e.payload["konusma_id"], e.payload["rol"], e.text) for e in msgs(hub, "chatgpt")]


def test_chatgpt_kopya_fixture_tek_dal_ve_tek_kayit(hub):
    r = run(hub, FIX / "chat_chatgpt_kopya")
    ms = _metinler(hub)
    # (a) current_node yok, 3 çocuk: yalnız en yeni yaprak
    assert [m for m in ms if m[0] == "kopya-a"] == [
        ("kopya-a", "kullanici", "Soru kopya-a"), ("kopya-a", "asistan", "Cevap uc")]
    assert not any("Cevap bir" in m[2] or "Cevap iki" in m[2] for m in ms)
    # (b) iki dosyada aynı sohbet: tek kopya
    assert sum(1 for m in ms if m[0] == "kopya-a") == 2
    # (c) farklı conversation_id/message.id ile ikinci kopya: tek
    assert sum(1 for m in ms if m[2] == "Dallanma sorusu") == 1
    assert sum(1 for m in ms if m[2] == "Dallanma cevabi") == 1
    # (d) aynı dalda ikiz düğüm: tek kayıt
    assert [m[2] for m in ms if m[0] == "kopya-d"] == ["Ikiz mesaj", "Tek cevap"]
    # (e) message.id yok: kayıt üretilir
    assert [m[2] for m in ms if m[0] == "kopya-e"] == ["Idsiz soru", "Idsiz cevap"]
    assert r.skipped.get("chatgpt: kopya mesaj atlandı", 0) >= 5
    assert "Cevap" not in "".join(str(v) for v in r.skipped)  # içerik sızmaz


def test_chatgpt_kopya_ikinci_alim_ve_farkli_zip_adi_sifir_yeni(hub, tmp_path):
    from conftest import make_zip
    z1 = make_zip(FIX / "chat_chatgpt_kopya", tmp_path / "bir.zip")
    a = run(hub, z1)
    n = count_events(hub, categories=["sohbet"])
    assert a.added == n and n > 0
    b = run(hub, z1)
    assert b.added == 0 and count_events(hub, categories=["sohbet"]) == n
    z2 = make_zip(FIX / "chat_chatgpt_kopya", tmp_path / "iki-farkli-ad.zip")
    c = run(hub, z2)
    assert c.added == 0 and count_events(hub, categories=["sohbet"]) == n


def test_chatgpt_ana_fixture_farkli_zip_adi_sifir_yeni(hub, tmp_path):
    from conftest import make_zip
    a = run(hub, make_zip(FIX / "chat_chatgpt", tmp_path / "ilk.zip"))
    b = run(hub, make_zip(FIX / "chat_chatgpt", tmp_path / "baska-ad.zip"))
    assert a.added == 8 and b.added == 0


def test_chatgpt_anahtar_bicimi_degismedi():
    from kimlikimport.base import stable_key
    from kimlikimport.chat import message_event
    e = message_event(platform="chatgpt", conv_id="c", title="t", role="kullanici", text="x",
                      ts="2023-01-01T00:00:00Z", msg_id="m")
    assert e.event_key == stable_key("chat", "chatgpt", "c", "m")


def test_chatgpt_msg_id_yok_yedek_anahtar_kararli(hub):
    run(hub, FIX / "chat_chatgpt_kopya")
    e = [x for x in msgs(hub, "chatgpt") if x.payload["konusma_id"] == "kopya-e"]
    assert all(x.payload["mesaj_id"] for x in e)


def test_chatgpt_gecersiz_current_node_tek_dal(hub, tmp_path):
    d = tmp_path / "g"
    d.mkdir()
    data = json.loads((FIX / "chat_chatgpt_kopya/conversations-000.json").read_text())
    data[0]["current_node"] = "yok-boyle-dugum"
    (d / "conversations.json").write_text(json.dumps(data), encoding="utf-8")
    run(hub, d)
    a = [e.text for e in msgs(hub, "chatgpt") if e.payload["konusma_id"] == "kopya-a"]
    assert a == ["Soru kopya-a", "Cevap uc"]


def test_claude_ve_genel_konusma_ici_kopya(hub, tmp_path):
    d = tmp_path / "cl"
    d.mkdir()
    m = lambda u, t, s="human": {"uuid": u, "sender": s, "text": t, "created_at": "2024-01-01T10:00:00Z"}
    (d / "conversations.json").write_text(json.dumps([{
        "uuid": "cc1", "name": "Ikiz", "created_at": "2024-01-01T09:00:00Z",
        "chat_messages": [m("1", "Merhaba"), m("2", " Merhaba "), m("3", "Merhaba", "assistant")]}]), encoding="utf-8")
    r = run(hub, d)
    assert [e.text for e in msgs(hub, "claude")] == ["Merhaba", "Merhaba"]
    assert r.skipped.get("claude: kopya mesaj atlandı") == 1
    g = tmp_path / "gn"
    g.mkdir()
    (g / "s.json").write_text(json.dumps({"id": "g1", "title": "G", "messages": [
        {"role": "user", "content": "Selam", "ts": "2024-01-01T10:00:00Z"},
        {"role": "user", "content": "Selam", "ts": "2024-01-01T10:00:00Z"},
        {"role": "user", "content": "Selam", "ts": "2024-01-01T10:00:01Z"},
        {"role": "user", "content": "Zamansiz"}, {"role": "user", "content": "Zamansiz"}]}), encoding="utf-8")
    r = run(hub, g, "chat_file")
    assert [e.text for e in msgs(hub, "dosya")] == ["Selam", "Selam", "Zamansiz", "Zamansiz"]
