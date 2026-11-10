"""Tanılama aracı: içerik SIZDIRMAZ (sentinel dizgiyle kanıt), ağa bağlanmaz, bozuk girdide çökmez."""
from __future__ import annotations

import csv
import gzip
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from conftest import FIX
from kimlikimport import tanila as T

# İki sentinel: SV yalnız DEĞERLERDE, SN yalnız ADLARDA (dosya/klasör/anahtar/başlık/tablo adı) geçer.
# Değer sentineli HİÇBİR modda raporda görünmemeli; ad sentineli varsayılan modda görünmemeli.
SV = "ZQXDEGERZQX"
SN = "ZQXADZQX"
DEGERLER = [
    SV, "5551234567890", "2024-03-05T10:11:12Z", "1709287200123", "ornek.kisi@example.test",
    "https://example.test/gizli/yol?x=1", "Ayşe Örnek", "203.0.113.99",
]


def _yok(rapor: str, sentinel: str) -> None:
    low = rapor.lower()
    s = sentinel.lower()
    assert s not in low, f"sızdı: {sentinel}"
    for i in range(0, len(s) - 5):  # 6 harflik parçalar da yok
        assert s[i:i + 6] not in low, f"{sentinel} parçası sızdı: {s[i:i + 6]}"


def _degerler_yok(rapor: str) -> None:
    _yok(rapor, SV)
    low = rapor.lower()
    for d in DEGERLER:
        assert d.lower() not in low, f"değer sızdı: {d!r}"


def _agac(kok: Path) -> Path:
    """Değer sentineli (SV) hücre/metin/gövdede; ad sentineli (SN) klasör, dosya, anahtar, sütun başlığı,
    MBOX başlığı, tablo adı ve zip içi adlarda geçen çok biçimli sahte dışa aktarma klasörü."""
    d = kok / f"Klasor{SN}Ad"
    (d / f"kisi_{SN}_1234567890").mkdir(parents=True)
    rec = lambda i: {"title": f"Watched {SV} {i}", "titleUrl": DEGERLER[5], "time": DEGERLER[2], "header": "YouTube",
                     "sayi": 1709287200123 + i, "e": DEGERLER[4], "ip": DEGERLER[7], "ad": DEGERLER[6],
                     "tel": DEGERLER[1], f"anahtar{SN}": {"ic": SV}, "products": ["YouTube"]}
    (d / "MyActivity.json").write_text(json.dumps([rec(i) for i in range(5)], ensure_ascii=False), encoding="utf-8")
    # veri anahtar olarak: kullanıcı adıyla anahtarlanmış sözlük (12 farklı özel anahtar)
    (d / f"kisi_{SN}_1234567890" / "message_1.json").write_text(json.dumps({
        "participants": [{"name": SV}], "messages": [{"sender_name": SV, "content": SV, "timestamp_ms": 1709287200123}],
        "etiketler": {f"{SN}{i}": {"x": 1} for i in range(12)}}, ensure_ascii=False), encoding="utf-8")
    (d / "sohbet.jsonl").write_text("\n".join(json.dumps({"role": "user", "content": SV, "gizli_" + SN: 1}) for _ in range(3)),
                                    encoding="utf-8")
    with open(d / "tablo.csv", "w", encoding="utf-8", newline="") as f:  # başlıksız CSV: ilk satır veri gibi
        w = csv.writer(f)
        w.writerow([SN, "Ayşe Örnek", DEGERLER[4]])
        for i in range(4):
            w.writerow([SV, DEGERLER[6], DEGERLER[2]])
    (d / "posta.mbox").write_text(
        f"From 1@xxx Mon Mar 04 10:00:00 +0000 2024\nDate: Mon, 4 Mar 2024 10:00:00 +0000\nFrom: {DEGERLER[4]}\n"
        f"Subject: {SV}\nX-{SN}: 1\nMessage-ID: <{SV}@example.test>\n\n{SV} gövde\n\n", encoding="utf-8")
    con = sqlite3.connect(d / "places.sqlite")
    con.executescript("CREATE TABLE moz_places(id INTEGER PRIMARY KEY, url TEXT, title TEXT);"
                      "CREATE TABLE moz_historyvisits(id INTEGER PRIMARY KEY, place_id INT, visit_date INT);"
                      f"CREATE TABLE tablo_{SN}(sutun_{SN} TEXT);")
    con.execute("INSERT INTO moz_places VALUES (1, ?, ?)", (DEGERLER[5], SV))
    con.execute("INSERT INTO moz_historyvisits VALUES (1, 1, 1709287200123456)")
    con.execute(f"INSERT INTO tablo_{SN} VALUES (?)", (SV,))
    con.commit()
    con.close()
    (d / f"not_{SN}.txt").write_text(f"{SV} metin\nikinci satır {SV}\n", encoding="utf-8")
    with zipfile.ZipFile(d / f"arsiv_{SN}.zip", "w") as zf:
        zf.writestr(f"icerik_{SN}/conversations.json", json.dumps([{"mapping": {SN: {"id": SV}}, "title": SV}]))
    with tarfile.open(d / "export.tar.gz", "w:gz") as tf:
        data = json.dumps([{"type": "issue", "url": DEGERLER[5], "title": SV, "created_at": DEGERLER[2]}]).encode()
        ti = tarfile.TarInfo(f"issues_{SN}_000001.json")
        ti.size = len(data)
        tf.addfile(ti, io.BytesIO(data))
    return d


def test_varsayilan_mod_ne_deger_ne_ad_sizdirir(tmp_path):
    d = _agac(tmp_path)
    for ayrinti in (False, True):
        r = T.tanila(d, ayrinti=ayrinti)
        _degerler_yok(r)
        _yok(r, SN)  # dosya/klasör/anahtar/başlık/tablo adları da maskeli
        assert "TANILAMA RAPORU" in r and "{özel:" in r


def test_adlari_goster_modunda_yalniz_adlar_acilir_degerler_asla(tmp_path):
    d = _agac(tmp_path)
    r = T.tanila(d, adlari_goster=True, ayrinti=True)
    _degerler_yok(r)  # değerler bu modda da yok
    assert SN.lower() in r.lower()  # adlar açıldı (kullanıcı bilerek seçti)




def test_cli_tanila_sizdirmaz_ve_agsiz(tmp_path):
    d = _agac(tmp_path)
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
           "PYTHONPATH": os.pathsep.join([str(root / "core" / "src"), str(root / "importers" / "src")]),
           # ağ erişimi denenirse hemen hata: kapalı bir vekil adresi
           "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "ALL_PROXY": "http://127.0.0.1:9"}
    p = subprocess.run([sys.executable, "-m", "kimlikcore", "tanila", str(d)], env=env, capture_output=True, encoding="utf-8")
    assert p.returncode == 0, p.stderr
    _degerler_yok(p.stdout + p.stderr)
    _yok(p.stdout + p.stderr, SN)
    assert "TANILAMA RAPORU" in p.stdout and "İçe aktarıcıların tanıması" in p.stdout


def test_ag_baglantisi_kurulmaz(tmp_path, monkeypatch):
    d = _agac(tmp_path)

    def yasak(*a, **k):
        raise AssertionError("tanila ağ bağlantısı denedi")

    monkeypatch.setattr(socket.socket, "connect", yasak)
    monkeypatch.setattr(socket, "getaddrinfo", yasak)
    monkeypatch.setattr(socket, "create_connection", yasak)
    T.tanila(d)


def test_kaynakta_ag_modulu_yok():
    kaynak = Path(T.__file__).read_text(encoding="utf-8")
    for yasak in ("import socket", "import urllib", "import http", "import requests", "import ssl", "import ftplib",
                  "import smtplib", "import subprocess", "import webbrowser", "import asyncio"):
        assert yasak not in kaynak, yasak


def test_taninan_icaktarici_ve_yapi_sayilari():
    r = T.tanila(FIX / "takeout_en")
    assert "google_takeout: TANIDI" in r and "En iyi eşleşme: google_takeout" in r
    assert "kayıt sayısı" in r and "tarih" in r.lower() or "örüntü" in r
    r2 = T.tanila(FIX / "gercekci" / "chatgpt_parcali")
    assert "chatgpt: TANIDI" in r2 and "beklenen şekil bulundu: konuşma" in r2
    assert "saniye?" in r2  # create_time epoch benzeri hane sayısı


def test_beklenmeyen_ve_eksik_alan_raporlanir(tmp_path):
    p = tmp_path / "conversations.json"
    konus = [{"mapping": {"a": {"id": "a", "message": None, "parent": None, "children": []}}, "title": "x",
              "create_time": 1.0, "current_node": "a", "yeni_alan_xyz": 1} for _ in range(4)]
    p.write_text(json.dumps(konus), encoding="utf-8")
    r = T.tanila(p)
    assert "yeni_alan_xyz" not in r and "{özel:" in r  # varsayılan: bilinmeyen alan adı maskeli
    assert "yeni_alan_xyz" in T.tanila(p, adlari_goster=True)  # --adlari-goster ile açılır
    eksik = tmp_path / "e" / "conversations.json"
    eksik.parent.mkdir()
    eksik.write_text(json.dumps([{"mapping": {}, "title": "x"}]), encoding="utf-8")
    assert "eksik alanlar" in T.tanila(eksik) and "current_node" in T.tanila(eksik)


def test_tek_kayitta_gorulen_bilinmeyen_anahtar_yazilmaz(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps([{"time": "2024-01-01T00:00:00Z", "title": "t", SN: "v"}]), encoding="utf-8")
    r = T.tanila(p)
    assert SN.lower() not in r.lower() and "{özel:" in r


@pytest.mark.parametrize("ad,veri", [
    ("bos.json", b""), ("kesik.json", b'[{"a": 1, "b": "uzun metin', ), ("bozuk.json", b"{]]:::\xff\xfe"),
    ("bom.json", b"\xef\xbb\xbf[{\"time\": \"2024-01-01T00:00:00Z\", \"title\": \"x\"}]"),
    ("bos.csv", b""), ("sadece_baslik.csv", b"a,b,c\n"), ("bozuk.csv", b'a,b\n"tirnak acik,1\n2,3\n'),
    ("utf16.csv", "a,b\n1,2\n".encode("utf-16")), ("bos.mbox", b"From "), ("rastgele.bin", os.urandom(2000)),
    ("sqlite_bozuk.sqlite", b"SQLite format 3\x00" + b"\xff" * 100),
])
def test_bozuk_girdide_cokmez(tmp_path, ad, veri):
    p = tmp_path / ad
    p.write_bytes(veri)
    r = T.tanila(p)
    assert "TANILAMA RAPORU" in r


def test_yarim_json_sayilari_bozulmadan_once_raporlar(tmp_path):
    p = tmp_path / "yarim.json"
    veri = json.dumps([{"time": f"2024-03-{1 + i % 28:02d}T00:00:00Z", "title": "t", "header": "YouTube"} for i in range(50)])
    p.write_text(veri[: int(len(veri) * 0.7)], encoding="utf-8")
    r = T.tanila(p)
    assert "bozuk ya da yarım" in r and "×" in r


def test_zip_ve_targz_ve_bozuk_zip(tmp_path):
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("conversations.json", json.dumps([{"mapping": {}, "title": "t", "current_node": "x", "create_time": 1}]))
    assert "chatgpt" in T.tanila(z)
    bozuk = tmp_path / "b.zip"
    bozuk.write_bytes(z.read_bytes()[:40])
    assert "TANILAMA RAPORU" in T.tanila(bozuk)
    tg = tmp_path / "x.tar.gz"
    tg.write_bytes(gzip.compress(b"bozuk tar"))
    assert "TANILAMA RAPORU" in T.tanila(tg)


def test_buyuk_json_bellek_sabit(tmp_path):
    import tracemalloc
    p = tmp_path / "b.json"
    with open(p, "w", encoding="utf-8") as f:
        f.write("[")
        for i in range(40_000):
            f.write(("," if i else "") + json.dumps({"time": "2024-03-01T10:00:00Z", "title": "metin " * 20, "n": i}))
        f.write("]")
    tracemalloc.start()
    r = T.tanila(p)
    _, tepe = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert "40000×" in r
    assert tepe < 20_000_000 < p.stat().st_size * 4
