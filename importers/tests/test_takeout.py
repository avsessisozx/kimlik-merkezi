from __future__ import annotations

import hashlib
import json
import zipfile
from collections import Counter

import pytest
from conftest import FIX, count_events, make_zip
from kimlikcore import FormatError
from kimlikimport.base import ImportFormatError
from kimlikimport.google_takeout import GoogleTakeout
from kimlikimport.run import run

# Fixture içeriği: izleme 4 + arama 2 + abonelik 3 + MyActivity/YouTube 2 (1'i tekrar)
# + MyActivity/Search 2 + 1 konum (3. kayıt zamansız -> atlanır) + Chrome 3 + 1 + 1 konum + Gmail 4 = 23 ayrıştırılan, 22 eklenen.
EXPECT_PARSED, EXPECT_ADDED, EXPECT_DUP = 23, 22, 1


def sha_tree(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_klasor_kayit_sayisi_ve_kategoriler(hub):
    r = run(hub, FIX / "takeout_en", "google_takeout")
    assert (r.parsed, r.added, r.duplicate) == (EXPECT_PARSED, EXPECT_ADDED, EXPECT_DUP)
    assert count_events(hub) == EXPECT_ADDED
    kinds = Counter(e.kind for e in hub.timeline(limit=1000))
    assert kinds["youtube.izleme"] == 4  # W1 W2 W3 + MyActivity'den yeni (ddd); W1 tekrarı tek kayıt
    assert kinds["youtube.arama"] == 2 and kinds["youtube.abonelik"] == 3
    assert kinds["youtube.etkinlik"] == 1
    assert kinds["google.arama"] == 2 and kinds["chrome.ziyaret"] == 4
    assert kinds["google.konum"] == 2
    cats = Counter(e.category for e in hub.timeline(limit=1000))
    assert cats["konum"] == 2 and cats["video"] == 10 and cats["tarama"] == 6 and cats["eposta"] == 4
    assert r.skipped == {"etkinlik: time yok/okunamadı": 1}


def test_gps_ayri_konum_olayi(hub):
    run(hub, FIX / "takeout_en", "google_takeout")
    for e in hub.timeline(limit=1000):
        blob = json.dumps(e.payload) + e.text
        if e.category != "konum":
            assert "41.123456" not in blob and "40.987654" not in blob, e.kind
    loc = [e for e in hub.timeline(categories=["konum"], limit=10)]
    assert any("41.123456" in json.dumps(e.payload) for e in loc)
    assert any("40.987654" in json.dumps(e.payload) for e in loc)


def test_arama_bulur(hub):
    run(hub, FIX / "takeout_en", "google_takeout")
    assert hub.search("ornek video dort")
    assert hub.search("Ornek Sayfa Iki")


def test_zip_ve_klasor_ayni_olaylar(hub, zipper):
    r1 = run(hub, FIX / "takeout_en", "google_takeout")
    r2 = run(hub, zipper("takeout_en"), "google_takeout")
    assert r2.added == 0 and r2.duplicate == EXPECT_PARSED
    assert count_events(hub) == r1.added


def test_iki_kez_alim_tekrarsiz(hub, zipper):
    z = zipper("takeout_en")
    a = run(hub, z, "google_takeout")
    b = run(hub, z)  # tür otomatik tanınır
    assert b.source_id == a.source_id
    assert b.added == 0 and b.duplicate == EXPECT_PARSED
    assert count_events(hub) == EXPECT_ADDED
    assert len(hub.sources()) == 1 and len(hub.raw_files()) == 1


def test_orijinal_degismez_ve_ham_arsiv_hash(hub, zipper, tmp_path):
    z = zipper("takeout_en")
    before = hashlib.sha256(z.read_bytes()).hexdigest()
    mtime = z.stat().st_mtime_ns
    r = run(hub, z)
    assert hashlib.sha256(z.read_bytes()).hexdigest() == before and z.stat().st_mtime_ns == mtime
    assert r.raw_files[0].sha256 == before
    assert (hub.root / r.raw_files[0].path).read_bytes() == z.read_bytes()
    assert hub.verify_archive() == []


def test_klasor_ham_arsiv_ve_degismez(hub):
    snap = sha_tree(FIX / "takeout_en")
    r = run(hub, FIX / "takeout_en", "google_takeout")
    assert sha_tree(FIX / "takeout_en") == snap
    names = sorted(x.name for x in r.raw_files)
    assert len(names) == 7 and len(set(names)) == 7  # aynı adlı MyActivity.json dosyaları ayrışır
    assert any(n.endswith("MyActivity.json") and "Search" in n for n in names)


def test_zip_diske_acilmaz(hub, zipper, tmp_path, monkeypatch):
    z = zipper("takeout_en")
    monkeypatch.setattr(zipfile.ZipFile, "extract", lambda *a, **k: pytest.fail("extract çağrıldı"))
    monkeypatch.setattr(zipfile.ZipFile, "extractall", lambda *a, **k: pytest.fail("extractall çağrıldı"))
    run(hub, z)


def test_turkce_adli_yapi_taninir(hub):
    # Klasör/dosya adları Türkçe (varsayım adları), içerik aynı: sonuç İngilizce yapıyla aynı olmalı.
    rep = GoogleTakeout().verify_format(FIX / "takeout_tr")
    assert rep.ok
    assert any("içeriğinden tanındı" in n for n in rep.notes)
    r = run(hub, FIX / "takeout_tr")
    assert (r.parsed, r.added) == (EXPECT_PARSED, EXPECT_ADDED)


def test_turkce_zip_adlari_utf8(hub, tmp_path):
    z = make_zip(FIX / "takeout_tr", tmp_path / "tr.zip")
    r = run(hub, z)
    assert r.added == EXPECT_ADDED


def test_eski_chrome_adi(hub):
    r = run(hub, FIX / "takeout_eski_chrome")
    assert r.added == 5  # 4 ziyaret + 1 konum


def test_gmail_mbox_eposta_kategorisi(hub):
    rep = GoogleTakeout().verify_format(FIX / "takeout_en")
    assert not any("MBOX" in u for u in rep.unsupported)
    assert any("mbox" in f for f in rep.found_files)
    run(hub, FIX / "takeout_en")
    ev = hub.timeline(categories=["eposta"], limit=100)
    assert len(ev) == 4 and all(e.kind == "gmail.ileti" for e in ev)
    by = {e.payload["ileti_kimligi"]: e for e in ev}
    m1, m2, m3 = by["<msg-1@example.test>"], by["<msg-2@example.test>"], by["<msg-3@example.test>"]
    assert m1.payload["konu"] == "Örnek konu şık" and "ö" in m1.payload["govde"]
    assert m1.payload["etiketler"] == ["Inbox", "Important", "Category Updates"]
    assert m1.ts == "2024-03-04T10:00:00Z" and m2.ts == "2024-03-05T11:00:00Z"  # +0300 -> UTC
    assert "HTML govde metni" in m2.payload["govde"] and "x{}" not in m2.payload["govde"]
    assert m3.payload["ekler"] == [{"ad": "ornek.pdf", "tur": "application/pdf", "boyut": 30}]
    assert "SENTETIK" not in json.dumps(m3.payload)  # ek içeriği alınmaz
    assert any(e.ts == "2024-03-07T13:00:00Z" for e in ev)  # Date yok -> From_ satırı
    assert hub.search("epostaozelkelime", categories=["eposta"])


def test_yalniz_mbox_alinir_ve_mbox_olmayan_reddedilir(hub, tmp_path):
    d = tmp_path / "m"
    d.mkdir()
    (d / "Mail.mbox").write_text("From a@b.test Mon Jan 1 00:00:00 2024\nDate: Mon, 1 Jan 2024 00:00:00 +0000\n"
                                 "Subject: x\nMessage-ID: <a@b>\n\ny\n")
    assert run(hub, d, "google_takeout").added == 1
    e = tmp_path / "n"
    e.mkdir()
    (e / "Mail.mbox").write_text("bu mbox degil\n")
    with pytest.raises(ImportFormatError) as ei:
        run(hub, e, "google_takeout")
    assert "'From ' ayırıcısıyla başlamıyor" in str(ei.value)


def test_html_bicimi_acik_hata(hub):
    with pytest.raises(ImportFormatError) as ei:
        run(hub, FIX / "takeout_html", "google_takeout")
    msg = str(ei.value)
    assert "HTML" in msg and "JSON" in msg and "MyActivity.html" in msg
    assert count_events(hub) == 0 and hub.sources() == []


def test_bozuk_json_anlasilir_hata(hub, tmp_path):
    d = tmp_path / "b" / "My Activity"
    d.mkdir(parents=True)
    (d / "MyActivity.json").write_text('[{"header":"Search","title":"x","time":"2024-01-01T00:00:00Z"}, {"header":')
    with pytest.raises(FormatError) as ei:
        run(hub, tmp_path / "b", "google_takeout")
    assert "bozuk" in str(ei.value)
    assert "Search" not in str(ei.value).replace("Search/", "")  # içerik sızmaz


def test_bozuk_zip(hub, tmp_path):
    z = tmp_path / "x.zip"
    z.write_bytes(b"PK\x03\x04bozuk")
    with pytest.raises(FormatError):
        run(hub, z, "google_takeout")


def test_beklenen_alan_yok(hub, tmp_path):
    d = tmp_path / "y"
    d.mkdir()
    (d / "Chrome.json").write_text(json.dumps({"Browser History": [{"foo": 1}, {"bar": 2}]}))
    with pytest.raises(ImportFormatError) as ei:
        run(hub, d, "google_takeout")
    assert "time_usec" in str(ei.value)


def test_tanimsiz_girdi(hub, tmp_path):
    f = tmp_path / "rastgele.txt"
    f.write_text("merhaba")
    with pytest.raises(FormatError) as ei:
        run(hub, f)
    assert "tanınmadı" in str(ei.value)
    with pytest.raises(FormatError):
        run(hub, tmp_path / "yok.zip")
    with pytest.raises(FormatError) as ei:
        run(hub, f, "olmayan_tur")
    assert "Kullanılabilir" in str(ei.value)


def test_rapor_icerik_icermez(hub):
    rep = GoogleTakeout().verify_format(FIX / "takeout_en")
    txt = rep.to_text()
    for secret in ("Ornek Video", "Ornek Sayfa", "ornek google arama", "Kanal A", "41.123456"):
        assert secret not in txt
    assert "watch-history.json" in txt and "Beklenmeyen alanlar" in txt


def test_bom_ve_bos_dizi(hub, tmp_path):
    d = tmp_path / "bom" / "Chrome"
    d.mkdir(parents=True)
    body = json.dumps({"Browser History": [{"title": "t", "url": "https://example.test/", "time_usec": 1709287200000000}]})
    (d / "History.json").write_bytes(b"\xef\xbb\xbf" + body.encode())
    (d / "bos.json").write_text("[]")
    r = run(hub, tmp_path / "bom", "google_takeout")
    assert r.added == 1


def test_kaldirilan_kaynak_yeniden_alinir(hub, zipper):
    z = zipper("takeout_en")
    a = run(hub, z)
    hub.remove_source(a.source_id, "deneme")
    assert count_events(hub) == 0
    b = run(hub, z)
    assert b.added == EXPECT_ADDED and count_events(hub) == EXPECT_ADDED


def test_kalici_silinen_icin_yine_de(hub, zipper):
    z = zipper("takeout_en")
    a = run(hub, z)
    hub.purge_source(a.source_id)
    with pytest.raises(FormatError) as ei:
        run(hub, z)
    assert "--yine-de" in str(ei.value)
    b = run(hub, z, yine_de=True)
    assert b.added == EXPECT_ADDED


def test_ilerleme_geri_cagrisi(hub, zipper):
    calls = []
    run(hub, zipper("takeout_en"), progress=lambda a, n: calls.append((a, n)))
    assert calls[0][0] == "dogrula" and ("kopyala", 0) in calls and calls[-1] == ("isle", EXPECT_PARSED)
