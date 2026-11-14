"""Bilgisayar dosyaları: karışık sahte klasör (her biçimden örnek + bozuk dosyalar).
Kural: okunabilen her şey içeriğiyle, okunamayan sağlam dosya yalnız kayıt, bozuk dosya atlanır ve raporlanır."""
from __future__ import annotations

import pytest
from karisik_klasor import BOZUK, ICERIKLI, YALNIZ_KAYIT, uret
from kimlikimport import files
from kimlikimport.run import run


@pytest.fixture
def karisik(tmp_path):
    return uret(tmp_path / "karisik")


def _kayitlar(hub):
    return {e.payload["yol"]: e.payload for e in hub.timeline(limit=500) if e.kind in ("dosya.kayit", "medya.foto")}


def test_ozet_sayilari_ve_bozuk_atlanir(hub, karisik):
    r = run(hub, karisik, "computer_files")
    o = r.files
    assert (o["icerikli"], o["yalniz_kayit"], o["bozuk"]) == (len(ICERIKLI), len(YALNIZ_KAYIT), len(BOZUK))
    assert o["toplam"] == len(ICERIKLI) + len(YALNIZ_KAYIT) + len(BOZUK)
    assert r.parsed == r.added == len(ICERIKLI) + len(YALNIZ_KAYIT)     # bozuklar için kayıt YOK
    kay = _kayitlar(hub)
    assert not (set(BOZUK) & set(kay))
    assert {d["yol"] for d in o["bozuk_dosyalari"]} == set(BOZUK)
    assert all(d["neden"] for d in o["bozuk_dosyalari"])
    assert o["metinsiz_pdf"] == 1
    # rapor metni (arayüz ve CLI aynısını gösterir)
    m = o["metin"]
    assert f"{len(ICERIKLI)} dosya içeriğiyle" in m and f"{len(YALNIZ_KAYIT)} dosya yalnız kayıt" in m
    assert f"{len(BOZUK)} dosya bozuk" in m and "1 PDF'de okunabilir metin yok (taranmış olabilir)" in m
    assert m in str(r)


def test_her_bicimin_icerigi_aranir(hub, karisik):
    run(hub, karisik, "computer_files")
    for ad, anahtar in ICERIKLI.items():
        if anahtar:
            assert hub.search(anahtar, categories=["dosyalar"]), f"{ad}: '{anahtar}' bulunamadı"
    # kodlamalar ve alt biçimler
    assert hub.search("ogrenci", categories=["dosyalar"])           # utf-8 ve cp1254 (öğrenci)
    assert hub.search("konusmanotu", categories=["dosyalar"])       # pptx konuşmacı notu
    assert hub.search("satir&iki", categories=["dosyalar"]) or hub.search("iki", categories=["dosyalar"])  # xlsx satır içi metin
    assert hub.search("Servis randevusu", categories=["dosyalar"])  # eml başlığı
    assert not hub.search("gizlibetik", categories=["dosyalar"])    # html betiği metne girmez
    kay = _kayitlar(hub)
    assert kay["metin_cp1254.txt"]["kodlama"] == "cp1254" and kay["metin_utf16bom.txt"]["kodlama"] == "utf-16"
    assert kay["metin_utf16le.txt"]["kodlama"] == "utf-16" and kay["metin_utf8.txt"]["kodlama"] == "utf-8"
    assert kay["bilinmeyen.xyz"]["icerik_durumu"] == "okundu"       # uzantısı bilinmeyen ama metin


def test_yalniz_kayit_isaretli_ve_ad_tur_boyut_tarih_var(hub, karisik):
    run(hub, karisik, "computer_files")
    kay = _kayitlar(hub)
    for ad in YALNIZ_KAYIT:
        p = kay[ad]
        assert p["icerik_durumu"] == "yalnız kayıt", ad
        assert "içerik okunamadı, yalnız kayıt eklendi" in p["kayit_notu"], ad
        assert p["ad"] == ad and p["uzanti"] == "." + ad.rsplit(".", 1)[1] and "boyut" in p and p["tarih"].endswith("Z") and p["tur"]
    assert kay["muzik.mp3"]["tur"] == "ses" and kay["taranmis.pdf"]["metin_durumu"] == "yok"
    for ad, anahtar in ICERIKLI.items():
        assert kay[ad]["icerik_durumu"] == "okundu", ad
    # yalnız kayıt dosyasının adı aranabilir
    assert hub.search("muzik", categories=["dosyalar"])


def test_dosya_ilerlemesi(hub, karisik):
    cagrilar = []
    run(hub, karisik, "computer_files", file_progress=lambda i, t: cagrilar.append((i, t)))
    top = len(ICERIKLI) + len(YALNIZ_KAYIT) + len(BOZUK)
    assert cagrilar[-1] == (top, top) and len(cagrilar) == top
    assert [i for i, _ in cagrilar] == sorted(i for i, _ in cagrilar)


def test_birden_cok_dosya_ve_klasor(hub, karisik, tmp_path):
    ayri = tmp_path / "baska"
    ayri.mkdir()
    (ayri / "not.txt").write_text("baskadizin anahtbaska", encoding="utf-8")
    (karisik / "alt/not.txt").write_text("alt dizin ayni ad anahtalt", encoding="utf-8")
    r = run(hub, [karisik / "kilavuz.pdf", karisik / "bozuk.pdf", ayri / "not.txt", karisik / "alt", karisik / "alt/not.txt"], "computer_files")
    assert (r.files["icerikli"], r.files["bozuk"]) == (4, 1)      # kilavuz, baska/not, alt/derin/ic_not, alt/not (mükerrer seçim tek kez)
    assert hub.search("anahtbaska") and hub.search("anahtalt") and hub.search("anahtpdf")
    with pytest.raises(Exception, match="Birden çok"):
        run(hub, [karisik / "kilavuz.pdf", ayri / "not.txt"])      # tür verilmeden


def test_tek_beklenmeyen_hata_icerigi_dusurmez(hub, karisik, monkeypatch):
    def kotu(p):
        if p.name == "foto.jpg":
            raise RuntimeError("beklenmedik")
        return {}, None, "var"
    monkeypatch.setattr(files, "photo_meta", kotu)
    r = run(hub, karisik, "computer_files")
    assert r.files["bozuk"] == len(BOZUK) + 1
    assert any(d["yol"] == "foto.jpg" and "beklenmeyen" in d["neden"] for d in r.files["bozuk_dosyalari"])
    assert hub.search("anahtpdf", categories=["dosyalar"])


def test_eslesmeyen_vekil_karakter_veritabanini_dusurmez(hub, tmp_path, monkeypatch):
    assert files._temiz("a\ud800b\x00c").encode("utf-8") == b"a?bc"
    d = tmp_path / "k"
    d.mkdir()
    from karisik_klasor import pdf_yaz
    pdf_yaz(d / "a.pdf", "vekilanahtar")
    # sahte pypdf: eşleşmeyen vekil karakter döndürür (gerçek PDF'lerde görülebilir)
    import pypdf
    monkeypatch.setattr(pypdf._page.PageObject, "extract_text", lambda self, *a, **k: "vekilanahtar \ud83d bitis")
    r = run(hub, d, "computer_files")
    assert r.added == 1 and hub.search("vekilanahtar")


def test_dosya_okunamazsa_klasor_yine_alinir(hub, karisik):
    # yalnız bozuk dosyalardan oluşan klasör: hata değil, 0 kayıt + açıklama
    d = karisik.parent / "yalniz_bozuk"
    d.mkdir()
    (d / "x.pdf").write_bytes(b"%PDF-1.4\nbozuk")
    (d / "y.docx").write_bytes(b"PK\x03\x04bozuk")
    r = run(hub, d, "computer_files")
    assert (r.added, r.files["bozuk"], r.files["icerikli"]) == (0, 2, 0) and "2 dosya bozuk" in str(r)
