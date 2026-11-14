"""Karışık sahte klasör: her biçimden örnek + bozuk dosyalar. Testte üretilir (ikili fixture depoya konmaz)."""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

# (dosya adı -> beklenen sınıf, arama anahtarı|None)
ICERIKLI = {
    "metin_utf8.txt": "anahtutf8", "metin_utf16bom.txt": "anahtutf16bom", "metin_utf16le.txt": "anahtutf16le",
    "metin_cp1254.txt": "anahtcp1254", "not.md": "anahtmd", "veri.json": "anahtjson", "olaylar.jsonl": "anahtjsonl",
    "tablo.csv": "anahtcsv", "tablo.tsv": "anahttsv", "yapi.xml": "anahtxml", "sayfa.html": "anahthtml",
    "ayar.yaml": "anahtyaml", "sunucu.log": "anahtlog", "kod.py": "anahtpy", "Makefile": "anahtmakefile",
    "bilinmeyen.xyz": "anahtxyz", "posta.eml": "anahteml", "metin.rtf": "anahtrtf", "tablo.xlsx": "anahtxlsx",
    "sunum.pptx": "anahtpptx", "belge.odt": "anahtodt", "sayfa.ods": "anahtods", "mektup.docx": "anahtdocx",
    "kilavuz.pdf": "anahtpdf", "alt/derin/ic_not.txt": "anahtderin", "foto.jpg": None,
}
YALNIZ_KAYIT = {"muzik.mp3": "ses", "program.exe": "ikili", "tuhaf.qqq": "ikili", "arsiv.zip": "zip",
                "eski.doc": "ole", "parolali.docx": "ole", "taranmis.pdf": "tarama", "bos.txt": "bos"}
BOZUK = ["bozuk.pdf", "bozuk.docx", "bozuk.xlsx", "bozuk.pptx", "bozuk.odt", "bozuk.zip", "kesik.pdf"]


def pdf_yaz(yol: Path, metin: str) -> None:
    ak = f"BT /F1 18 Tf 50 700 Td ({metin}) Tj ET".encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(ak) + ak + b"\nendstream",
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
    yol.write_bytes(bytes(out))


def _zip(yol: Path, parcalar: dict[str, str]) -> None:
    with zipfile.ZipFile(yol, "w", zipfile.ZIP_DEFLATED) as z:
        for ad, ic in parcalar.items():
            z.writestr(ad, ic)


def uret(k: Path) -> Path:
    from docx import Document
    from PIL import Image
    from pypdf import PdfWriter

    k.mkdir(parents=True, exist_ok=True)
    (k / "alt/derin").mkdir(parents=True, exist_ok=True)
    w = lambda ad, ic, **kw: (k / ad).write_text(ic, encoding="utf-8", **kw)  # noqa: E731
    w("metin_utf8.txt", "Türkçe çalışkan öğrenci anahtutf8")
    (k / "metin_utf16bom.txt").write_bytes("Merhaba dünya anahtutf16bom".encode("utf-16"))
    (k / "metin_utf16le.txt").write_bytes("Selam dünya anahtutf16le".encode("utf-16-le"))
    (k / "metin_cp1254.txt").write_bytes("Çalışkan öğrenci ığş anahtcp1254".encode("cp1254"))
    w("not.md", "# Başlık\nanahtmd")
    w("veri.json", '{"ad": "anahtjson"}')
    w("olaylar.jsonl", '{"a": "anahtjsonl"}\n{"a": 2}\n')
    w("tablo.csv", "a,b\nanahtcsv,2\n")
    w("tablo.tsv", "a\tb\nanahttsv\t2\n")
    w("yapi.xml", "<kok><oge>anahtxml</oge></kok>")
    w("sayfa.html", "<html><body><p>anahthtml</p><script>gizlibetik()</script></body></html>")
    w("ayar.yaml", "anahtar: anahtyaml\n")
    w("sunucu.log", "2024-01-01 INFO anahtlog\n")
    w("kod.py", "print('anahtpy')\n")
    w("Makefile", "all:\n\techo anahtmakefile\n")
    w("bilinmeyen.xyz", "uzantisi bilinmeyen ama metin anahtxyz")
    w("posta.eml", "From: ali@example.com\nTo: veli@example.com\nSubject: Servis randevusu\nDate: Mon, 4 Mar 2024 10:00:00 +0300\n"
                   "Content-Type: text/plain; charset=utf-8\n\nGovde anahteml\n")
    w("metin.rtf", "{\\rtf1\\ansi\\ansicpg1254{\\fonttbl{\\f0 Arial;}}\\f0 Merhaba \\'fc\\'f6 anahtrtf\\par ikinci satir}")
    _zip(k / "tablo.xlsx", {
        "xl/workbook.xml": "<workbook/>",
        "xl/sharedStrings.xml": "<sst><si><t>anahtxlsx</t></si><si><r><t>Ayse</t></r><r><t> Yilmaz</t></r></si></sst>",
        "xl/worksheets/sheet1.xml": '<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>42</v></c></row>'
                                    '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2" t="inlineStr"><is><t>satir&amp;iki</t></is></c></row>'
                                    "</sheetData></worksheet>"})
    _zip(k / "sunum.pptx", {"ppt/presentation.xml": "<p/>",
                            "ppt/slides/slide1.xml": "<p:sld><a:p><a:r><a:t>anahtpptx</a:t></a:r></a:p></p:sld>",
                            "ppt/notesSlides/notesSlide1.xml": "<n><a:p><a:r><a:t>konusmanotu</a:t></a:r></a:p></n>"})
    for ad, an in (("belge.odt", "anahtodt"), ("sayfa.ods", "anahtods")):
        _zip(k / ad, {"content.xml": f"<office:document-content><text:p>{an}</text:p><text:p>ikinci</text:p></office:document-content>"})
    d = Document()
    d.add_paragraph("Word mektubu anahtdocx")
    d.save(k / "mektup.docx")
    pdf_yaz(k / "kilavuz.pdf", "Servis kilavuzu anahtpdf")
    w("alt/derin/ic_not.txt", "alt klasor anahtderin")
    Image.new("RGB", (8, 8), "red").save(k / "foto.jpg")
    # yalnız kayıt (sağlam ama içeriği okunamaz)
    (k / "muzik.mp3").write_bytes(b"ID3\x03\x00\x00" + os.urandom(2000))
    (k / "program.exe").write_bytes(b"MZ\x90\x00" + os.urandom(3000))
    (k / "tuhaf.qqq").write_bytes(bytes(range(256)) * 8)
    _zip(k / "arsiv.zip", {"a.txt": "icindeki"})
    (k / "eski.doc").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + os.urandom(500))
    (k / "parolali.docx").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + os.urandom(500))
    pw = PdfWriter()
    pw.add_blank_page(200, 200)
    with open(k / "taranmis.pdf", "wb") as f:
        pw.write(f)
    (k / "bos.txt").write_bytes(b"")
    # bozuk
    (k / "bozuk.pdf").write_bytes(b"%PDF-1.4\nbu bozuk")
    (k / "kesik.pdf").write_bytes((k / "kilavuz.pdf").read_bytes()[:120])
    for ad in ("bozuk.docx", "bozuk.xlsx", "bozuk.pptx", "bozuk.odt", "bozuk.zip"):
        (k / ad).write_bytes(b"PK\x03\x04" + os.urandom(64))
    return k
