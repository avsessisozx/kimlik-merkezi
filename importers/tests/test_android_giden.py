"""android_giden içe aktarıcısı (docs/AKTARIM.md §1, §4, §5). Fixture: fixtures/android_giden/ (sentetik)."""
import json
import shutil
import zipfile

import pytest
from conftest import FIX, count_events
from kimlikcore import FormatError
from kimlikimport import registry
from kimlikimport.base import ImportFormatError
from kimlikimport.run import run

KLASOR = FIX / "android_giden"
CIHAZ = "7c9e6679-7425-40de-944b-e07fc1f90ae7"
SAGLAM = "11111111-1111-4111-8111-111111111111"
KAPANISSIZ = "22222222-2222-4222-8222-222222222222"
SAYI = "33333333-3333-4333-8333-333333333333"
YARIM = "44444444-4444-4444-8444-444444444444"
BOZUK = "55555555-5555-4555-8555-555555555555"
BICIM2 = "66666666-6666-4666-8666-666666666666"
BILINMEYEN = "77777777-7777-4777-8777-777777777777"
YEDEK = "88888888-8888-4888-8888-888888888888"


def dosya(ad):
    return KLASOR / f"{ad}.jsonl"


def olaylar(hub):
    return hub.timeline(limit=1000)


def test_kayitli_ve_taninir():
    assert "android_giden" in registry.names()
    imp, _ = registry.detect_best(dosya(SAGLAM))
    assert imp is not None and imp.name == "android_giden"


def test_saglam_dosya_eslemesi(hub):
    r = run(hub, dosya(SAGLAM))
    assert r.importer == "android_giden" and r.parsed == 10 and r.added == 10
    tum = olaylar(hub)
    assert {e.device_id for e in tum} == {CIHAZ}
    assert all(e.kind == "android." + e.payload["tur"] for e in tum)
    assert all(e.payload["dosya_id"] == SAGLAM for e in tum)
    kat = {e.payload["tur"]: e.category for e in tum}
    assert kat == {"paylasim.link": "notlar", "paylasim.metin": "notlar", "not.hizli": "notlar",
                   "medya.foto": "medya_meta", "medya.video": "medya_meta", "medya.konum": "konum",
                   "indirilen.dosya": "dosyalar", "uygulama.kullanim": "uygulama"}
    # konum yalnız konum kaydında; foto/video yükünde GPS yok
    for e in tum:
        if e.payload["tur"] in ("medya.foto", "medya.video"):
            assert "enlem" not in e.payload and "boylam" not in e.payload
        if e.payload["tur"] == "medya.konum":
            assert e.payload["enlem"] == 41.0082 and e.payload["medya_id"]
    # düzenleme: yeni sürüm kaydı `onceki` taşır
    duz = [e for e in tum if "onceki" in e.payload]
    assert len(duz) == 1 and duz[0].payload["onceki"].endswith("000000000003")
    assert sum(1 for e in tum if e.payload["tur"] == "not.hizli") == 3


def test_cekirdek_onem_ve_hassas_isaret(hub):
    run(hub, dosya(SAGLAM))
    tum = olaylar(hub)
    hizli = [e for e in tum if e.kind == "android.not.hizli"]
    assert hizli and all(e.onem == 2 for e in hizli)            # notlar kategorisi -> önem 2
    doktor = [e for e in tum if "doktor" in e.text]
    assert len(doktor) == 1 and doktor[0].hassas_konu == ("saglik",)
    assert all(e.hassas_konu == () for e in tum if "doktor" not in e.text)
    assert next(e for e in tum if e.kind == "android.medya.foto").onem == 1


def test_ikinci_alim_sifir_yeni(hub):
    run(hub, dosya(SAGLAM))
    n = count_events(hub)
    r = run(hub, dosya(SAGLAM))
    assert r.added == 0 and r.duplicate == r.parsed == 10 and count_events(hub) == n


def test_ayni_kayit_farkli_dosyada_yeni_degil(hub):
    run(hub, dosya(SAGLAM))
    n = count_events(hub)
    r = run(hub, dosya(YEDEK))
    assert r.parsed == 2 and r.added == 1 and r.duplicate == 1 and count_events(hub) == n + 1


@pytest.mark.parametrize("ad,parca", [
    (KAPANISSIZ, "kapanış kaydı yok"),
    (SAYI, "kayıt sayısı tutmuyor"),
    (YARIM, "yarım kalmış"),
    (BOZUK, "bozuk"),
    (BICIM2, "desteklenmiyor"),
])
def test_eksik_dosyadan_hic_kayit_alinmaz(hub, ad, parca):
    with pytest.raises(ImportFormatError) as ei:
        run(hub, dosya(ad))
    metin = ei.value.report.to_text()
    assert parca in metin and f"{ad}.jsonl" in metin
    assert count_events(hub) == 0 and hub.sources() == []


def test_gecersiz_kategori_dosya_reddi(hub, tmp_path):
    for kat in ("tarama", "persona", "yok_boyle"):
        s = dosya(SAGLAM).read_text(encoding="utf-8").replace('"kategori": "notlar"', f'"kategori": "{kat}"', 1)
        p = tmp_path / f"{kat}.jsonl"
        p.write_text(s, encoding="utf-8")
        with pytest.raises(ImportFormatError) as ei:
            run(hub, p)
        assert "geçersiz kategori" in ei.value.report.to_text()
    assert count_events(hub) == 0


def test_bilinmeyen_tur_alinir_ve_sayilir(hub):
    r = run(hub, dosya(BILINMEYEN))
    assert r.added == 2
    assert any("1 kayıt bilinmeyen türde" in n for n in r.report.notes)
    assert any(e.kind == "android.ses.kayit" for e in olaylar(hub))


def test_klasor_karisik(hub, tmp_path):
    kl = tmp_path / "kutu"
    kl.mkdir()
    for ad in (SAGLAM, KAPANISSIZ, SAYI, YARIM, BOZUK, BICIM2):
        shutil.copy(dosya(ad), kl / f"{ad}.jsonl")
    r = run(hub, kl, "android_giden")
    assert r.added == 10 and r.report.ok
    assert r.report.found_files == [f"{SAGLAM}.jsonl"]
    assert len(r.report.missing) == 4 and len(r.report.unsupported) == 1
    assert "1 tanesi alınabilir; 4 eksik/bozuk, 1 desteklenmeyen" in " ".join(r.report.notes)
    # ham arşive yalnız sağlam dosya girer
    assert len(r.raw_files) == 1


def test_karisik_zip(hub):
    r = run(hub, KLASOR / "karisik.zip")
    assert r.added == 12 and r.report.ok     # 10 sağlam + 2 bilinmeyen-tür dosyası
    assert len(r.report.found_files) == 2 and len(r.report.missing) == 2
    n = count_events(hub)
    assert run(hub, KLASOR / "karisik.zip").added == 0 and count_events(hub) == n


def test_klasor_ici_zip_elle_aktarim(hub, tmp_path):
    kl = tmp_path / "x"
    kl.mkdir()
    with zipfile.ZipFile(kl / "yedek.zip", "w") as z:
        z.write(dosya(SAGLAM), f"{SAGLAM}.jsonl")
    assert run(hub, kl).added == 10


def test_tum_dosyalar_bozuksa_rapor_anlasilir(hub, tmp_path):
    kl = tmp_path / "k"
    kl.mkdir()
    shutil.copy(dosya(KAPANISSIZ), kl / "a.jsonl")
    with pytest.raises(ImportFormatError) as ei:
        run(hub, kl, "android_giden")
    assert "dosya eksik: kapanış kaydı yok" in str(ei.value)


def test_jsonl_olmayan_girdi(hub, tmp_path):
    (tmp_path / "a.txt").write_text("merhaba")
    with pytest.raises(FormatError):
        run(hub, tmp_path / "a.txt", "android_giden")


def test_rapor_icerik_sizdirmaz(hub, tmp_path):
    gizli = "GIZLI-ICERIK-XYZ"
    kl = tmp_path / "k"
    kl.mkdir()
    for ad in (KAPANISSIZ, SAYI, YARIM, BOZUK, BICIM2, SAGLAM):
        s = dosya(ad).read_text(encoding="utf-8").replace("not.hizli", "not.hizli", 1)
        s = s.replace('"metin": "', f'"metin": "{gizli} ').replace('"metin":"', f'"metin":"{gizli} ')
        (kl / f"{ad}.jsonl").write_text(s, encoding="utf-8")
    # bozuk satırın içeriği (kesik JSON) de rapora girmemeli
    r = run(hub, kl, "android_giden")
    rapor = r.report.to_text()
    assert gizli not in rapor and "Süt" not in rapor and "ornek.test" not in rapor
    for ad in (KAPANISSIZ, SAYI, YARIM, BOZUK):
        assert f"{ad}.jsonl" in rapor
    assert gizli not in str(r)


def test_buyuk_dosya_akisla(hub, tmp_path):
    import tracemalloc

    p = tmp_path / "buyuk.jsonl"
    baslik = {"baslik": True, "bicim": 1, "cihaz_id": CIHAZ, "dosya_id": "99999999-9999-4999-8999-999999999999"}
    n = 30000
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(baslik) + "\n")
        for i in range(n):
            f.write(json.dumps({"id": f"b-{i}", "ts": "2026-03-01T09:00:00Z", "tur": "not.hizli", "kategori": "notlar",
                                "metin": "sentetik not " * 20 + str(i), "yuk": {}, "onceki": None}) + "\n")
        f.write(json.dumps({"kapanis": True, "kayit_sayisi": n}) + "\n")
    boyut = p.stat().st_size
    tracemalloc.start()
    r = run(hub, p)
    _, tepe = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert r.added == n and tepe < boyut


# --- tek doğrulayıcı: dosya_dogrula ---------------------------------------------------------------
from kimlikimport.android_giden import MAX_SATIR, dosya_dogrula  # noqa: E402


@pytest.mark.parametrize("ad,kod", [
    (KAPANISSIZ, "kapanis_yok"), (SAYI, "sayi_tutmuyor"), (YARIM, "satir_yarim"), (BOZUK, "satir_bozuk"),
    (BICIM2, "bicim_desteklenmiyor"),
])
def test_dosya_dogrula_neden_kodlari(ad, kod):
    assert dosya_dogrula(dosya(ad)) == (False, 0, kod)


def test_dosya_dogrula_saglam_ve_kimlik():
    assert dosya_dogrula(dosya(SAGLAM)) == (True, 10, "")
    assert dosya_dogrula(dosya(SAGLAM), CIHAZ, SAGLAM) == (True, 10, "")
    assert dosya_dogrula(dosya(SAGLAM), CIHAZ, KAPANISSIZ) == (False, 0, "kimlik_uyusmuyor")
    assert dosya_dogrula(dosya("yok-boyle")) == (False, 0, "okunamadi")


def _sat(tmp_path, degis):
    s = dosya(SAGLAM).read_text(encoding="utf-8").splitlines()
    degis(s)
    p = tmp_path / "x.jsonl"
    p.write_text("\n".join(s) + "\n", encoding="utf-8")
    return p


def test_dosya_dogrula_alan_ts_kategori_bos_satir_uzun(tmp_path):
    assert dosya_dogrula(_sat(tmp_path, lambda s: s.__setitem__(1, s[1].replace('"ts": "', '"ts": "bozuk')))) == (False, 0, "ts_gecersiz")
    assert dosya_dogrula(_sat(tmp_path, lambda s: s.__setitem__(1, s[1].replace('"kategori": "notlar"', '"kategori": "persona"')))) == (False, 0, "kategori_gecersiz")
    assert dosya_dogrula(_sat(tmp_path, lambda s: s.__setitem__(1, s[1].replace('"yuk": {', '"yuk": [1], "x": {')))) == (False, 0, "alan_gecersiz")
    assert dosya_dogrula(_sat(tmp_path, lambda s: s.insert(2, ""))) == (False, 0, "bos_satir")
    assert dosya_dogrula(_sat(tmp_path, lambda s: s.append(s[1]))) == (False, 0, "kapanis_sonrasi")
    assert dosya_dogrula(_sat(tmp_path, lambda s: s.__setitem__(1, '{"id":"a","tur":"x","kategori":"notlar","ts":"2026-01-01T00:00:00Z","metin":"' + "a" * MAX_SATIR + '"}'))) == (False, 0, "satir_uzun")
    assert dosya_dogrula(_sat(tmp_path, lambda s: s.__setitem__(0, '{"baslik": false}'))) == (False, 0, "baslik_yok")


def test_derin_json_yalniz_o_dosyayi_reddeder(hub, tmp_path):
    kl = tmp_path / "k"
    kl.mkdir()
    shutil.copy(dosya(SAGLAM), kl / f"{SAGLAM}.jsonl")
    s = dosya(KAPANISSIZ).read_text(encoding="utf-8").splitlines()
    s[1] = "[" * 200000
    (kl / f"{KAPANISSIZ}.jsonl").write_text("\n".join(s) + "\n", encoding="utf-8")
    assert dosya_dogrula(kl / f"{KAPANISSIZ}.jsonl")[0] is False
    r = run(hub, kl, "android_giden")
    assert r.added == 10 and len(r.report.missing) == 1
