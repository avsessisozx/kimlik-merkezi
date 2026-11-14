"""Her içe aktarıcı için ortak dayanıklılık sözleşmesi (sentetik veriyle).

- bozuk / yarım (kesik) / boş dosya: çökmez; ya başarıyla (kısmen) alır ya da `FormatError` verir.
  Başka istisna türü (KeyError, TypeError, UnicodeDecodeError...) sözleşme ihlalidir.
- aynı dosyayı iki kez almak çift kayıt üretmez.
- bilinmeyen alan: çökmez, olay sayısı değişmez (atlanır; rapora yazılır).
- büyük dosya: akışla okunur (bellek tepe değeri dosya boyutundan çok küçük).
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import sqlite3
import tracemalloc
from pathlib import Path

import pytest
from conftest import FIX, count_events
from kimlikcore import FormatError
from kimlikimport import registry
from kimlikimport.run import run

U = 1_000_000

# (tur, fixture_klasörü, bozulacak_ana_dosya göreli yol)
CASES = [
    ("google_takeout", "takeout_en", "Takeout/My Activity/YouTube/MyActivity.json"),
    ("google_takeout", "takeout_en", "Takeout/Chrome/History.json"),
    ("google_takeout", "takeout_en", "Takeout/Mail/All mail Including Spam and Trash.mbox"),
    ("google_takeout", "gercekci/takeout_tr_gercekci", "Takeout/Konum Geçmişi/Records.json"),
    ("google_takeout", "gercekci/takeout_tr_gercekci", "Takeout/Konum Geçmişi/Semantic Location History/2025/2025_OCAK.json"),
    ("google_takeout", "gercekci/timeline_yeni", "Timeline.json"),
    ("reddit", "reddit", "comments.csv"),
    ("meta", "meta_instagram", "instagram-ornek-2024/your_instagram_activity/messages/inbox/ornekarkadas_123/message_1.json"),
    ("meta", "gercekci/meta_instagram_yeni", "instagram-ornek-2025/your_instagram_activity/saved/saved_posts.json"),
    ("github", "github", "issues_000001.json"),
    ("spotify", "spotify_genisletilmis", "Spotify Extended Streaming History/Streaming_History_Audio_2023_0.json"),
    ("spotify", "spotify_standart", "Spotify Account Data/StreamingHistory_music_0.json"),
    ("chatgpt", "chat_chatgpt", "conversations.json"),
    ("chatgpt", "gercekci/chatgpt_parcali", "conversations-000.json"),
    ("claude", "chat_claude", "conversations.json"),
    ("chat_file", "chat_generic", "deepseek_elle.json"),
]
IDS = [f"{t}:{Path(f).name}" for t, _, f in CASES]


def _kopya(tmp_path: Path, klasor: str, ana: str) -> tuple[Path, Path]:
    dst = tmp_path / "girdi"
    shutil.copytree(FIX / klasor, dst)
    return dst, dst / ana


def _dene(hub, girdi: Path, tur: str):
    """Sözleşme: başarı ya da FormatError. Dönüş: (sonuç|None, hata|None)."""
    try:
        return run(hub, girdi, tur), None
    except FormatError as e:  # ImportFormatError de FormatError'dur
        return None, e


@pytest.mark.parametrize("tur,klasor,ana", CASES, ids=IDS)
def test_yarim_kesik_dosya_cokmez(hub, tmp_path, tur, klasor, ana):
    girdi, dosya = _kopya(tmp_path, klasor, ana)
    veri = dosya.read_bytes()
    dosya.write_bytes(veri[: max(1, int(len(veri) * 0.6))])  # ortadan kesik
    r, err = _dene(hub, girdi, tur)
    if err is not None:
        assert str(err).strip()  # anlaşılır, boş olmayan Türkçe ileti
    else:
        assert r.parsed >= 0


@pytest.mark.parametrize("tur,klasor,ana", CASES, ids=IDS)
def test_bos_dosya_cokmez(hub, tmp_path, tur, klasor, ana):
    girdi, dosya = _kopya(tmp_path, klasor, ana)
    dosya.write_bytes(b"")
    r, err = _dene(hub, girdi, tur)
    assert (r is None) != (err is None)


@pytest.mark.parametrize("tur,klasor,ana", CASES, ids=IDS)
def test_bozuk_icerik_cokmez(hub, tmp_path, tur, klasor, ana):
    girdi, dosya = _kopya(tmp_path, klasor, ana)
    veri = bytearray(dosya.read_bytes())
    mid = len(veri) // 2
    veri[mid:mid + 12] = b"}{,,\xff\xfe[[\"::"  # JSON/CSV/MBOX'u bozan çöp baytlar
    dosya.write_bytes(bytes(veri))
    r, err = _dene(hub, girdi, tur)
    assert (r is None) != (err is None)


@pytest.mark.parametrize("tur,klasor,ana", CASES, ids=IDS)
def test_ayni_dosya_iki_kez_cift_kayit_yok(hub, tmp_path, tur, klasor, ana):
    girdi = FIX / klasor
    a = run(hub, girdi, tur)
    n1 = count_events(hub)
    b = run(hub, girdi, tur)
    assert a.added > 0
    assert b.added == 0 and b.duplicate == b.parsed
    assert count_events(hub) == n1


def _bilinmeyen_ekle(o, derinlik=0):
    if isinstance(o, dict):
        o = {k: _bilinmeyen_ekle(v, derinlik + 1) for k, v in o.items()}
        o["yeni_bilinmeyen_alan_xyz"] = {"ic": [1, 2, 3]}
        return o
    if isinstance(o, list):
        return [_bilinmeyen_ekle(v, derinlik + 1) for v in o]
    return o


JSON_CASES = [c for c in CASES if c[2].endswith(".json")]


@pytest.mark.parametrize("tur,klasor,ana", JSON_CASES, ids=[f"{t}:{Path(f).name}" for t, _, f in JSON_CASES])
def test_bilinmeyen_alan_atlanir_cokmez(hub, tmp_path, tur, klasor, ana):
    ref = run(hub, FIX / klasor, tur)  # temel: değişmemiş girdi
    girdi, dosya = _kopya(tmp_path, klasor, ana)
    nesne = json.loads(dosya.read_text(encoding="utf-8-sig"))
    dosya.write_text(json.dumps(_bilinmeyen_ekle(nesne), ensure_ascii=True), encoding="utf-8")
    # ikinci bir Hub'da aynı kayıt sayısı çıkmalı: yeni alan olayları azaltmaz/çoğaltmaz
    from kimlikcore import Hub
    h2 = Hub.open(tmp_path / "v2", write=True)
    try:
        r2 = run(h2, girdi, tur)
        assert r2.parsed == ref.parsed
        assert r2.added == ref.added
    finally:
        h2.close()


def test_bilinmeyen_csv_sutunu_raporlanir(hub, tmp_path):
    girdi, dosya = _kopya(tmp_path, "reddit", "comments.csv")
    satirlar = list(csv.reader(io.StringIO(dosya.read_text(encoding="utf-8-sig"))))
    satirlar[0].append("yeni_sutun_xyz")
    for s in satirlar[1:]:
        s.append("deger")
    with open(dosya, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(satirlar)
    rep = registry.create("reddit").verify_format(girdi)
    assert rep.ok and any("yeni_sutun_xyz" in x for x in rep.unexpected_fields)
    r = run(hub, girdi, "reddit")
    assert r.added > 0


# ------------------------------------------------------------------ tarayıcı geçmişi (SQLite)
def _chromium(path: Path, n: int = 5):
    con = sqlite3.connect(path)
    con.executescript("""
      CREATE TABLE urls(id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INT, typed_count INT, last_visit_time INT, hidden INT);
      CREATE TABLE visits(id INTEGER PRIMARY KEY, url INT, visit_time INT, from_visit INT, transition INT, segment_id INT, visit_duration INT);
    """)
    con.execute("INSERT INTO urls(id,url,title) VALUES (1,'https://example.test/a','A')")
    base = 11_644_473_600 * U + 1_709_287_200 * U
    con.executemany("INSERT INTO visits(url,visit_time,transition) VALUES (1,?,0)", [(base + i * U,) for i in range(n)])
    con.commit()
    con.close()


def test_tarayici_bozuk_yarim_bos_ve_cift(hub, tmp_path):
    ok = tmp_path / "ok" / "History"
    ok.parent.mkdir()
    _chromium(ok)
    a = run(hub, ok, "browser_history")
    b = run(hub, ok, "browser_history")
    assert a.added == 5 and b.added == 0 and b.duplicate == 5
    veri = ok.read_bytes()
    for ad, icerik in (("bos", b""), ("kesik", veri[: len(veri) // 2]), ("cop", b"SQLite format 3\x00" + b"\xff" * 4000),
                       ("metin", b"bu bir sqlite degil")):
        p = tmp_path / ad / "History"
        p.parent.mkdir()
        p.write_bytes(icerik)
        r, err = _dene(hub, p, "browser_history")
        assert err is not None or r is not None  # çökmedi


def test_tarayici_firefox_milisaniye_ve_mikrosaniye(hub, tmp_path):
    p = tmp_path / "places.sqlite"
    con = sqlite3.connect(p)
    con.executescript("""
      CREATE TABLE moz_places(id INTEGER PRIMARY KEY, url TEXT, title TEXT, description TEXT, visit_count INT);
      CREATE TABLE moz_historyvisits(id INTEGER PRIMARY KEY, from_visit INT, place_id INT, visit_date INT, visit_type INT);
    """)
    con.execute("INSERT INTO moz_places(id,url,title) VALUES (1,'https://example.test/ff','F')")
    con.executemany("INSERT INTO moz_historyvisits(place_id,visit_date,visit_type) VALUES (1,?,1)",
                    [(1_709_287_200 * U,), (1_709_287_260 * 1000,)])  # µs ve (eski) ms
    con.commit()
    con.close()
    run(hub, p, "browser_history")
    ts = sorted(e.ts for e in hub.timeline(limit=10))
    assert ts == ["2024-03-01T10:00:00Z", "2024-03-01T10:01:00Z"]


def test_tarayici_safari_taninir_ama_desteklenmez(tmp_path):
    p = tmp_path / "History.db"
    con = sqlite3.connect(p)
    con.executescript("CREATE TABLE history_items(id INTEGER PRIMARY KEY, url TEXT);"
                      "CREATE TABLE history_visits(id INTEGER PRIMARY KEY, history_item INT, visit_time REAL);")
    con.commit()
    con.close()
    rep = registry.create("browser_history").verify_format(p)
    assert not rep.ok and any("Safari" in m for m in rep.missing)


# ------------------------------------------------------------------ bilgisayar dosyaları
def test_dosyalar_bozuk_ve_bos_dosyalar_cokmez(hub, tmp_path):
    kok = tmp_path / "klasor"
    kok.mkdir()
    (kok / "bos.pdf").write_bytes(b"")
    (kok / "kesik.pdf").write_bytes(b"%PDF-1.4\n1 0 obj\n<<")
    (kok / "bozuk.docx").write_bytes(b"PK\x03\x04bozuk")
    (kok / "bozuk.jpg").write_bytes(b"\xff\xd8\xff\xe1\x00\x10Exif\x00\x00bozuk")
    (kok / "bos.txt").write_bytes(b"")
    (kok / "ikili.txt").write_bytes(b"\xff\xfe\x00\x81" * 100)
    a = run(hub, kok, "computer_files")
    b = run(hub, kok, "computer_files")
    # bozuk/boş PDF ve bozuk docx ATLANIR (kayıt yok, raporda); bozuk.jpg, bos.txt, ikili.txt yalnız kayıt olarak girer
    assert a.added == 3 and b.added == 0
    assert a.files["bozuk"] == 3 and {d["yol"] for d in a.files["bozuk_dosyalari"]} == {"bos.pdf", "kesik.pdf", "bozuk.docx"}


# ------------------------------------------------------------------ büyük dosya: akışla, bellek sabit
def _tepe_bellek(parse_iter) -> tuple[int, int]:
    tracemalloc.start()
    n = 0
    for _ in parse_iter:
        n += 1
    _, tepe = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return n, tepe


def _buyuk_takeout(p: Path, kayit: int):
    with open(p, "w", encoding="utf-8") as f:
        f.write("[")
        for i in range(kayit):
            if i:
                f.write(",")
            f.write(json.dumps({"header": "YouTube", "title": f"Watched Ornek {i}", "time": f"2024-03-{1 + i % 28:02d}T10:00:{i % 60:02d}Z",
                                "titleUrl": f"https://www.youtube.com/watch?v=v{i:010d}", "products": ["YouTube"],
                                "subtitles": [{"name": "K", "url": "https://www.youtube.com/channel/UCx"}] * 3,
                                "details": [{"name": "x" * 200}]}))
        f.write("]")


def _buyuk_chatgpt(p: Path, konusma: int):
    with open(p, "w", encoding="utf-8") as f:
        f.write("[")
        for i in range(konusma):
            if i:
                f.write(",")
            mapping = {"root": {"id": "root", "message": None, "parent": None, "children": ["u"]},
                       "u": {"id": "u", "parent": "root", "children": ["a"], "message": {
                           "id": f"u{i}", "author": {"role": "user"}, "create_time": 1738000000.0 + i,
                           "content": {"content_type": "text", "parts": ["soru " * 300]}, "metadata": {}}},
                       "a": {"id": "a", "parent": "u", "children": [], "message": {
                           "id": f"a{i}", "author": {"role": "assistant"}, "create_time": 1738000001.0 + i,
                           "content": {"content_type": "text", "parts": ["yanit " * 300]}, "metadata": {"model_slug": "x"}}}}
            f.write(json.dumps({"title": f"K{i}", "create_time": 1738000000.0 + i, "mapping": mapping,
                                "current_node": "a", "conversation_id": f"c{i:08d}"}))
        f.write("]")


def test_buyuk_takeout_json_akisla(tmp_path):
    """Dosya 5 kat büyüyünce bellek tepe değeri büyümez (akış)."""
    kucuk, buyuk = tmp_path / "k.json", tmp_path / "b.json"
    _buyuk_takeout(kucuk, 5_000)
    _buyuk_takeout(buyuk, 25_000)
    assert buyuk.stat().st_size > 8 * 1024 * 1024
    imp = registry.create("google_takeout")
    nk, tk = _tepe_bellek(imp.parse(kucuk))
    nb, tb = _tepe_bellek(imp.parse(buyuk))
    assert (nk, nb) == (5_000, 25_000)
    assert tb < tk * 1.5 + 1_000_000, (tk, tb)


def test_buyuk_chatgpt_json_akisla(tmp_path):
    from kimlikcore import Category
    if "sohbet" not in Category.ALL:
        pytest.skip("çekirdek sohbet kategorisini tanımıyor")
    kucuk, buyuk = tmp_path / "k.json", tmp_path / "conversations.json"
    _buyuk_chatgpt(kucuk, 600)
    _buyuk_chatgpt(buyuk, 3_000)
    assert buyuk.stat().st_size > 8 * 1024 * 1024
    imp = registry.create("chatgpt")
    nk, tk = _tepe_bellek(imp.parse(kucuk))
    nb, tb = _tepe_bellek(imp.parse(buyuk))
    assert (nk, nb) == (600 * 3, 3_000 * 3)
    assert tb < tk * 1.5 + 1_000_000, (tk, tb)


def test_buyuk_csv_ve_mbox_akisla(tmp_path):
    p = tmp_path / "comments.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "permalink", "date", "ip", "subreddit", "gildings", "link", "parent", "body", "media"])
        for i in range(40_000):
            w.writerow([f"c{i}", f"/r/x/{i}", "2024-03-01 10:00:00 UTC", "", "x", "0", "l", "", "metin " * 40, ""])
    boyut = p.stat().st_size
    n, tepe = _tepe_bellek(registry.create("reddit").parse(p))
    assert n == 40_000 and tepe < 4_000_000 < boyut
    m = tmp_path / "a.mbox"
    with open(m, "w", encoding="utf-8") as f:
        for i in range(6_000):
            f.write(f"From {i}@xxx Mon Mar 04 10:00:00 +0000 2024\nDate: Mon, 4 Mar 2024 10:00:00 +0000\n"
                    f"From: a@example.test\nSubject: s{i}\nMessage-ID: <m{i}@example.test>\n\n" + "govde " * 300 + "\n\n")
    n, tepe = _tepe_bellek(registry.create("google_takeout").parse(m))
    assert n == 6_000 and tepe < 4_000_000 < m.stat().st_size
