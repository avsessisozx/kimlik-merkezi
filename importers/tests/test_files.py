"""Bilgisayar dosyaları: sentetik klasör ağacı (testte üretilir; ikili fixture depoya konmaz)."""
from __future__ import annotations

import json
import os
import struct
from collections import Counter

import pytest
from conftest import count_events
from kimlikcore import FormatError
from kimlikimport import registry
from kimlikimport.base import ImportFormatError
from kimlikimport.files import ComputerFiles
from kimlikimport.run import run


def make_pdf(path, text: str):
    stream = f"BT /F1 18 Tf 50 700 Td ({text}) Tj ET".encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
    path.write_bytes(bytes(out))


def make_mp4(path, lat_lon: bytes | None):
    def box(t, payload):
        return struct.pack(">I4s", 8 + len(payload), t) + payload

    mvhd = box(b"mvhd", b"\x00\x00\x00\x00" + struct.pack(">II", 2082844800 + 1709287200, 0) + b"\x00" * 80)
    udta = box(b"udta", box(b"\xa9xyz", struct.pack(">HH", len(lat_lon), 0x15C7) + lat_lon)) if lat_lon else b""
    path.write_bytes(box(b"ftyp", b"isom\x00\x00\x02\x00isom") + box(b"moov", mvhd + udta) + box(b"mdat", b"\x00" * 16))


@pytest.fixture
def tree(tmp_path):
    from docx import Document
    from PIL import Image
    from pypdf import PdfWriter

    r = tmp_path / "Belgelerim"
    (r / "alt/derin").mkdir(parents=True)
    (r / ".gizli").mkdir()
    (r / ".gizli/sir.txt").write_text("gizli klasor icerigi")
    (r / "node_modules").mkdir()
    (r / "node_modules/x.txt").write_text("atlanmali")
    (r / "not.txt").write_text("Türkçe not: ışık İstanbul dosyaozelkelime", encoding="utf-8")
    (r / "alt/liste.csv").write_text("a,b\n1,2\n")
    (r / "alt/ikili.bin").write_bytes(b"\x00\x01\x02" * 100)
    make_pdf(r / "alt/rapor.pdf", "Merhaba pdfozelkelime rapor")
    w = PdfWriter()
    w.add_blank_page(200, 200)
    with open(r / "alt/taranmis.pdf", "wb") as f:
        w.write(f)
    (r / "alt/bozuk.pdf").write_bytes(b"%PDF-1.4\nbu bozuk")
    d = Document()
    d.add_paragraph("Word belgesi docxozelkelime")
    d.save(r / "alt/derin/mektup.docx")
    im = Image.new("RGB", (40, 30), "red")
    ex = Image.Exif()
    ex[0x010F], ex[0x0110] = "OrnekMarka", "OrnekModel"
    ex.get_ifd(0x8769)[0x9003] = "2024:03:01 12:00:00"
    gps = ex.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (41.0, 0.0, 44.4), "E", (28.0, 58.0, 35.4)
    im.save(r / "alt/foto_gpsli.jpg", exif=ex)
    Image.new("RGB", (10, 10), "blue").save(r / "alt/foto_duz.png")
    make_mp4(r / "alt/video_gpsli.mp4", b"+41.0123+028.9765/")
    make_mp4(r / "alt/video_duz.mp4", None)
    for p in r.rglob("*"):
        if p.is_file():
            os.utime(p, (1709287200, 1709287200))
    return r

# belge: not, csv, bin(diğer), rapor, taranmış, bozuk, mektup = 7 dosya.kayit; foto 2 + video 2 = 4 medya; konum 2
EXPECT = 7 + 4 + 2


def test_kayit_sayisi_ve_kategoriler(hub, tree):
    r = run(hub, tree, "computer_files")
    assert (r.parsed, r.added, r.duplicate) == (EXPECT, EXPECT, 0)
    ev = hub.timeline(limit=100)
    assert Counter(e.category for e in ev) == {"dosyalar": 7, "medya_meta": 4, "konum": 2}
    assert Counter(e.kind for e in ev)["dosya.konum"] == 2
    assert r.raw_files == []  # dosyalar yerinde kalır, ham arşive kopyalanmaz


def test_metin_cikarma_ve_arama(hub, tree):
    run(hub, tree, "computer_files")
    for w in ("dosyaozelkelime", "pdfozelkelime", "docxozelkelime"):
        assert hub.search(w, categories=["dosyalar"]), w
    assert hub.search("ISIK istanbul", categories=["dosyalar"])
    st = {e.payload["ad"]: e.payload["metin_durumu"] for e in hub.timeline(categories=["dosyalar"], limit=50)}
    assert st["rapor.pdf"] == st["mektup.docx"] == st["not.txt"] == "var"
    assert st["taranmis.pdf"] == "yok" and st["bozuk.pdf"] == "hata" and st["ikili.bin"] == "uygulanmaz"
    assert not hub.search("gizli klasor icerigi") and not hub.search("atlanmali")


def test_gps_ayri_konum_olayi(hub, tree):
    run(hub, tree, "computer_files")
    ev = hub.timeline(limit=100)
    for e in ev:
        if e.category != "konum":
            assert "41.0" not in json.dumps(e.payload), e.kind
    loc = {e.payload["dosya"]: e.payload for e in ev if e.category == "konum"}
    assert set(loc) == {"alt/foto_gpsli.jpg", "alt/video_gpsli.mp4"}
    assert loc["alt/foto_gpsli.jpg"]["enlem"] == pytest.approx(41.012333, abs=1e-5)
    assert loc["alt/foto_gpsli.jpg"]["boylam"] == pytest.approx(28.9765, abs=1e-5)
    assert loc["alt/video_gpsli.mp4"]["enlem"] == 41.0123 and loc["alt/video_gpsli.mp4"]["boylam"] == 28.9765
    photo = next(e for e in ev if e.payload.get("ad") == "foto_gpsli.jpg")
    assert photo.payload["ust_veri"]["marka"] == "OrnekMarka" and photo.payload["ust_veri"]["genislik"] == 40
    assert photo.payload["ust_veri"]["cekim_zamani_yerel"] == "2024:03:01 12:00:00"
    vid = next(e for e in ev if e.payload.get("ad") == "video_duz.mp4")
    assert vid.payload["ust_veri"]["olusturma"] == "2024-03-01T10:00:00Z"


def test_iki_kez_tekrarsiz_ve_degisen_dosya(hub, tree):
    a = run(hub, tree, "computer_files")
    b = run(hub, tree, "computer_files")
    assert b.source_id == a.source_id and (b.added, b.duplicate) == (0, EXPECT)
    (tree / "not.txt").write_text("degisti yeni icerik")
    os.utime(tree / "not.txt", (1709300000, 1709300000))
    c = run(hub, tree, "computer_files")
    assert c.source_id != a.source_id and c.added == 1 and c.duplicate == EXPECT - 1


def test_dosyalar_degismez_ve_otomatik_secilmez(hub, tree):
    snap = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in tree.rglob("*") if p.is_file()}
    imp, _ = registry.detect_best(tree)
    assert imp is None  # otomatik tanıma bu türü seçmez
    run(hub, tree, "dosyalar")  # takma ad
    assert snap == {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in tree.rglob("*") if p.is_file()}


def test_bos_klasor_ve_rapor(hub, tmp_path):
    d = tmp_path / "bos"
    d.mkdir()
    with pytest.raises(ImportFormatError) as ei:
        run(hub, d, "computer_files")
    assert "taranacak dosya yok" in str(ei.value)
    with pytest.raises(FormatError):
        run(hub, tmp_path / "yok", "computer_files")


def test_rapor_icerik_icermez(tree):
    txt = ComputerFiles().verify_format(tree).to_text()
    assert "dosyaozelkelime" not in txt and "rapor.pdf" not in txt and "OCR yok" in txt


def test_tek_dosya(hub, tree):
    r = run(hub, tree / "not.txt", "computer_files")
    assert r.added == 1 and count_events(hub) == 1
