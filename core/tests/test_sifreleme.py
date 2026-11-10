"""Şifreleme: dosya biçimi, anahtar yaşam döngüsü, kurallar, Hub, dönüşüm. Sahte sağlayıcı kullanılır
(gerçek Windows DPAPI burada denenemez; bkz. docs/SIFRELEME.md)."""
import hashlib
import json
import os
import sqlite3
import sys

import pytest
from kimlikcore import (
    AnahtarGerekli, EventIn, FormatError, Hub, KuralHatasi, SchemaTooOld, YanlisParola, donusum,
    schema, sifreleme as sif,
)
from kimlikcore.errors import SaglayiciYok, SifrelemeHatasi, SifreliDosyaBozuk

from util import known_events

IFADE = "mavi bisikletle sahil yolunda sabah kahvesi içtim"
PAROLA = "kuzey-ruzgari-9071"
GIZLI = "gizlisozcukkirmizi"


@pytest.fixture(autouse=True)
def hizli_kdf(monkeypatch):
    monkeypatch.setattr(sif, "KDF_N", 1 << 4)
    sif.saglayici_ayarla(sif.SahteSaglayici("birinci"))
    monkeypatch.delenv(sif.ENV_PAROLA, raising=False)
    monkeypatch.delenv(sif.ENV_SAHTE, raising=False)
    yield
    sif.saglayici_ayarla(None)


def doldur(hub):
    sid = hub.add_source("test", "1", None)
    hub.add_events(sid, known_events(20))
    hub.add_events(sid, [EventIn(event_key="gizli", ts="2026-03-01T00:00:00Z", kind="k", category="notlar",
                                 payload={"x": GIZLI}, text=f"Işık İstanbul {GIZLI} şifreli")])
    return sid


def tum_dosya_baytlari(root):
    for dp, _d, fs in os.walk(root):
        for f in fs:
            if f in ("erisim.db",):
                continue
            yield os.path.join(dp, f), open(os.path.join(dp, f), "rb").read()


# ------------------------------------------------------------------ dosya biçimi
@pytest.mark.parametrize("n", [0, 1, sif.PARCA - 1, sif.PARCA, sif.PARCA + 1, 3 * sif.PARCA + 5])
def test_bicim_gidis_donus_ve_boyut(tmp_path, n):
    dek = os.urandom(32)
    veri = os.urandom(n)
    p = tmp_path / "f"
    sif.bayt_sifrele_yaz(dek, veri, p)
    assert sif.sifreli_mi(p) and sif.acik_boyut(p) == n
    assert sif.bayt_coz_oku(dek, p) == veri
    assert sif.sifreli_sha256(dek, p) == (hashlib.sha256(veri).hexdigest(), n)


def test_bicim_bozulma_kirpilma_ekleme_yanlis_anahtar(tmp_path):
    dek = os.urandom(32)
    veri = os.urandom(2 * sif.PARCA + 10)
    p = tmp_path / "f"
    sif.bayt_sifrele_yaz(dek, veri, p)
    ham = p.read_bytes()
    boyut = sif.PARCA + 16

    def dene(b, anahtar=dek):
        q = tmp_path / "t"
        q.write_bytes(b)
        with pytest.raises(SifreliDosyaBozuk):
            sif.bayt_coz_oku(anahtar, q)

    dene(ham[:100] + bytes([ham[100] ^ 1]) + ham[101:])          # bit çevirme
    dene(ham[:24 + boyut])                                       # sondan parça kırpma
    dene(ham[:-1])                                               # son baytı kırpma
    dene(ham + b"x")                                             # sona ekleme
    dene(ham[:24] + ham[24 + boyut:24 + 2 * boyut] + ham[24:24 + boyut] + ham[24 + 2 * boyut:])  # sıra değiştirme
    dene(ham, os.urandom(32))                                    # yanlış anahtar
    dene(b"")


def test_ayni_veri_iki_kez_farkli_sifrelenir(tmp_path):
    dek = os.urandom(32)
    sif.bayt_sifrele_yaz(dek, b"ayni", tmp_path / "a")
    sif.bayt_sifrele_yaz(dek, b"ayni", tmp_path / "b")
    assert (tmp_path / "a").read_bytes() != (tmp_path / "b").read_bytes()


# ------------------------------------------------------------------ kurallar
@pytest.mark.parametrize("ifade", [
    "kısa", "bir iki üç", "gizli soru cevabı", "aaaaaaaaaaaaaaaaaaaaaaaa", "abcdefghijklmnopqrstuvwxyz",
    "12345678901234567890", "password password password password", "correct horse battery staple",
    "the quick brown fox jumps over the lazy dog", "a b c d", "ali ali ali ali ali ali",
    "Bir İki Üç Dört Beş", "", "   ",
])
def test_zayif_ifadeler_reddedilir(ifade):
    d = sif.ifade_degerlendir(ifade)
    assert not d["uygun"] and d["sorunlar"] and d["guc"] == "zayıf"


@pytest.mark.parametrize("ifade", [
    IFADE, "denizin kıyısında üç martı gördüm", "Evimizin bahçesindeki armut ağacı çok yaşlı",
    "tolgahan-deniz-ormanda-yuruyus-yapti",
])
def test_iyi_ifadeler_kabul(ifade):
    d = sif.ifade_degerlendir(ifade)
    assert d["uygun"], d


def test_ifade_kurali_dort_kelime_ya_da_yirmi_karakter():
    assert sif.ifade_degerlendir("kırmızı bulutlar yağmur getirir")["uygun"]          # 4 kelime, <20
    assert sif.ifade_degerlendir("kirmizibulutyagmurgetirir")["uygun"]                # 1 kelime, >=20
    assert not sif.ifade_degerlendir("kırmızı bulut sis")["uygun"]                 # 3 kelime, <20


def test_guc_gostergesi_siralamasi():
    assert sif.ifade_degerlendir("kırmızı bulut sisli dağ")["guc"] == "orta"
    assert sif.ifade_degerlendir(IFADE)["guc"] == "güçlü"


@pytest.mark.parametrize("p", ["kisa", "aaaaaaaaaaaa", "1234567890", "passwordpassword", "abcdefghijkl"])
def test_zayif_parola_reddedilir(p):
    assert not sif.parola_degerlendir(p)["uygun"]


def test_parola_ifade_ayni_olamaz():
    assert not sif.parola_degerlendir(IFADE, ifade=IFADE)["uygun"]
    assert sif.parola_degerlendir(PAROLA, ifade=IFADE)["uygun"]


def test_ifade_normallestirme_buyuk_kucuk_bosluk():
    assert sif.ifade_normallestir("  Işık   İSTANBUL ") == sif.ifade_normallestir("isik istanbul")


# ------------------------------------------------------------------ anahtar yaşam döngüsü
def test_anahtar_duz_metin_diskte_degil(tmp_path):
    dek = sif.anahtar_kur(tmp_path)
    metin = (tmp_path / sif.ANAHTAR_DOSYASI).read_bytes()
    assert dek not in metin and dek.hex().encode() not in metin
    import base64
    assert base64.b64encode(dek) not in metin
    assert sif.anahtari_coz(tmp_path) == dek
    with pytest.raises(SifrelemeHatasi):
        sif.anahtar_kur(tmp_path)  # üzerine yazılmaz


def test_baska_hesap_acamaz(tmp_path):
    sif.anahtar_kur(tmp_path)
    sif.saglayici_ayarla(sif.SahteSaglayici("baska-hesap"))
    with pytest.raises(AnahtarGerekli):
        sif.anahtari_coz(tmp_path)


def test_saglayici_yoksa_kurulamaz(tmp_path, monkeypatch):
    sif.saglayici_ayarla(None)
    monkeypatch.setattr(sif, "varsayilan_saglayici", lambda: None)   # sağlayıcı AÇIKÇA yok (Windows'ta DPAPI olsa da)
    with pytest.raises(SaglayiciYok):
        sif.anahtar_kur(tmp_path)


def test_parola_kurtarma_olmadan_eklenemez(tmp_path):
    dek = sif.anahtar_kur(tmp_path)
    with pytest.raises(KuralHatasi, match="kurtarma"):
        sif.parola_ekle(tmp_path, dek, PAROLA, PAROLA)
    assert sif.zarf_oku(tmp_path)["parola"] is None


def test_kurtarma_kur_kurallari(tmp_path):
    dek = sif.anahtar_kur(tmp_path)
    with pytest.raises(KuralHatasi):
        sif.kurtarma_kur(tmp_path, dek, "kısa", "kısa")
    with pytest.raises(KuralHatasi, match="aynı değil"):
        sif.kurtarma_kur(tmp_path, dek, IFADE, IFADE + " x")
    assert sif.zarf_oku(tmp_path)["kurtarma"] is None
    sif.kurtarma_kur(tmp_path, dek, IFADE, IFADE.upper())  # büyük/küçük harf farkı aynı sayılır
    assert sif.zarf_oku(tmp_path)["kurtarma"] is not None


def test_parola_akisi_yanlis_parola_ve_os_yuvasi_kalkar(tmp_path):
    dek = sif.anahtar_kur(tmp_path)
    sif.kurtarma_kur(tmp_path, dek, IFADE, IFADE)
    with pytest.raises(KuralHatasi, match="aynı değil"):
        sif.parola_ekle(tmp_path, dek, PAROLA, PAROLA + "x")
    with pytest.raises(KuralHatasi):
        sif.parola_ekle(tmp_path, dek, "kisa", "kisa")
    with pytest.raises(KuralHatasi, match="aynı olamaz"):
        sif.parola_ekle(tmp_path, dek, IFADE, IFADE)
    sif.parola_ekle(tmp_path, dek, PAROLA, PAROLA)
    z = sif.zarf_oku(tmp_path)
    assert z["os"] is None and z["parola"] and z["kurtarma"]
    # artık hesap tek başına yetmez
    with pytest.raises(AnahtarGerekli):
        sif.anahtari_coz(tmp_path)
    with pytest.raises(YanlisParola):
        sif.anahtari_coz(tmp_path, parola="yanlis-parola-123")
    assert sif.anahtari_coz(tmp_path, parola=PAROLA) == dek
    assert sif.anahtari_coz(tmp_path, kurtarma=IFADE) == dek
    assert sif.anahtari_coz(tmp_path, kurtarma="  " + IFADE.upper()) == dek
    with pytest.raises(YanlisParola):
        sif.anahtari_coz(tmp_path, kurtarma="tamamen başka bir uzun ifade burada")
    # parola kurtarma yuvasını açmaz, ifade parola yuvasını açmaz (ayrı katmanlar)
    with pytest.raises(YanlisParola):
        sif.anahtari_coz(tmp_path, parola=IFADE)


def test_env_parola_ile_acilir(tmp_path, monkeypatch):
    dek = sif.anahtar_kur(tmp_path)
    sif.kurtarma_kur(tmp_path, dek, IFADE, IFADE)
    sif.parola_ekle(tmp_path, dek, PAROLA, PAROLA)
    monkeypatch.setenv(sif.ENV_PAROLA, PAROLA)
    assert sif.anahtari_coz(tmp_path) == dek
    monkeypatch.setenv(sif.ENV_PAROLA, "yanlis-yanlis-yanlis")
    with pytest.raises(YanlisParola):
        sif.anahtari_coz(tmp_path)


def test_yuva_degistirme_saldirisi_yakalanir(tmp_path):
    """Parola yuvasını kurtarma yuvası olarak kopyalamak (AAD'de yuva adı var) işe yaramaz."""
    dek = sif.anahtar_kur(tmp_path)
    sif.kurtarma_kur(tmp_path, dek, IFADE, IFADE)
    sif.parola_ekle(tmp_path, dek, PAROLA, PAROLA)
    z = sif.zarf_oku(tmp_path)
    z["kurtarma"] = z["parola"]
    (tmp_path / sif.ANAHTAR_DOSYASI).write_text(json.dumps(z))
    with pytest.raises(YanlisParola):
        sif.anahtari_coz(tmp_path, kurtarma=PAROLA)


def test_parola_kaldir_hesaba_doner(tmp_path):
    dek = sif.anahtar_kur(tmp_path)
    sif.kurtarma_kur(tmp_path, dek, IFADE, IFADE)
    sif.parola_ekle(tmp_path, dek, PAROLA, PAROLA)
    sif.parola_kaldir(tmp_path, dek)
    assert sif.anahtari_coz(tmp_path) == dek
    assert sif.zarf_oku(tmp_path)["parola"] is None and sif.zarf_oku(tmp_path)["kurtarma"]


def test_kurtar_yeni_parola_ve_hesaba_yeniden_baglama(tmp_path):
    dek = sif.anahtar_kur(tmp_path)
    sif.kurtarma_kur(tmp_path, dek, IFADE, IFADE)
    sif.parola_ekle(tmp_path, dek, PAROLA, PAROLA)
    # parola unutuldu: ifadeyle yeni parola
    with pytest.raises(YanlisParola):
        sif.kurtar(tmp_path, "yanlış ifade yanlış ifade yanlış", "yeni-parola-12345", "yeni-parola-12345")
    with pytest.raises(KuralHatasi):
        sif.kurtar(tmp_path, IFADE, "kisa", "kisa")
    assert sif.kurtar(tmp_path, IFADE, "yeni-parola-12345", "yeni-parola-12345") == "parola"
    with pytest.raises(YanlisParola):
        sif.anahtari_coz(tmp_path, parola=PAROLA)           # eski parola artık geçmez
    assert sif.anahtari_coz(tmp_path, parola="yeni-parola-12345") == dek
    # parolasız mod, hesap değişti: ifadeyle yeni hesaba bağla
    sif.parola_kaldir(tmp_path, dek)
    sif.saglayici_ayarla(sif.SahteSaglayici("yeni-hesap"))
    with pytest.raises(AnahtarGerekli):
        sif.anahtari_coz(tmp_path)
    assert sif.kurtar(tmp_path, IFADE) == "os"
    assert sif.anahtari_coz(tmp_path) == dek


def test_dpapi_windows_disinda_kurulamaz(monkeypatch):
    monkeypatch.setattr(sif.sys, "platform", "linux")   # platform AÇIKÇA Windows değil (yalnız bu test süresince)
    with pytest.raises(SaglayiciYok):
        sif.DpapiSaglayici()


@pytest.mark.skipif(sys.platform != "win32", reason="gerçek DPAPI yalnız Windows'ta")
def test_dpapi_gercek_gidis_donus():  # pragma: no cover - Linux'ta atlanır
    s = sif.DpapiSaglayici()
    sarili = s.sar(b"x" * 32)
    assert b"x" * 32 not in sarili and s.ac(sarili) == b"x" * 32
    with pytest.raises(AnahtarGerekli):
        s.ac(sarili[:-3] + b"abc")


# ------------------------------------------------------------------ Hub (şifreli)
def test_sifreli_hub_diskte_bilinen_metin_yok_ve_arama_calisir(root):
    with Hub.open(root, write=True, sifreli=True) as h:
        assert h.sifreli
        doldur(h)
        assert [e.event_key for e in h.search("ISIK")] == ["gizli"]
        assert len(h.search("bulgu003*", prefix=True)) == 1
        assert len(h.search("istanbul")) >= 1
        assert len(h.search("şanlıurfa")) >= 1
    assert sif.db_durumu(root / "kimlik.db") == "sifreli"
    for yol, b in tum_dosya_baytlari(root):
        low = b.lower()
        for aranan in (GIZLI.encode(), "istanbul".encode(), "işık".encode(), "bulgu003zz".encode(),
                       "sentetik".encode(), b"SQLite format", "şanlıurfa".encode()):
            assert aranan not in low, (yol, aranan)
    assert not (root / "kimlik.db-wal").exists()


def test_sifreli_hub_turkce_fts_katlama(root):
    with Hub.open(root, write=True, sifreli=True) as h:
        doldur(h)
    with Hub.open(root, write=False) as h:
        for q in ("ışık", "ISIK", "Işık", "isik"):
            assert [e.event_key for e in h.search(q)] == ["gizli"], q
        assert len(h.search("ŞANLIURFA")) == len(h.search("sanliurfa")) > 0
        assert h.search("sanl*", prefix=True)
        assert h.timeline(limit=3)


def test_sifreli_hub_tx_sonrasi_baska_okuyucu_gorur_kapatmadan(root):
    h = Hub.open(root, write=True, sifreli=True)
    try:
        sid = h.add_source("t", "1", None)
        h.add_events(sid, known_events(3))
        with Hub.open(root, write=False) as r:
            assert len(r.timeline(limit=10)) == 3
        with h.transaction() as c:
            c.execute("INSERT INTO meta(key, value) VALUES ('a', 'b')")
        with Hub.open(root, write=False) as r:
            assert r.query_one("SELECT value FROM meta WHERE key='a'") == ("b",)
    finally:
        h.close()


def test_sifreli_hub_salt_okunur_yazamaz_ve_ikinci_yazici_kilitli(root):
    from kimlikcore import HubLockedError, HubReadOnlyError
    with Hub.open(root, write=True, sifreli=True) as h:
        doldur(h)
        with pytest.raises(HubLockedError):
            Hub.open(root, write=True)
        with Hub.open(root, write=False) as r:
            with pytest.raises(HubReadOnlyError):
                r.add_source("x", "1", None)
            with pytest.raises(sqlite3.OperationalError):
                r.query("DELETE FROM events")


def test_yanlis_saglayici_ile_hub_acilmaz(root, monkeypatch):
    with Hub.open(root, write=True, sifreli=True) as h:
        doldur(h)
    sif.saglayici_ayarla(sif.SahteSaglayici("baska"))
    for yaz in (False, True):
        with pytest.raises(AnahtarGerekli):
            Hub.open(root, write=yaz)
    sif.saglayici_ayarla(None)
    monkeypatch.setattr(sif, "varsayilan_saglayici", lambda: None)   # sağlayıcı AÇIKÇA yok
    with pytest.raises(SaglayiciYok):
        Hub.open(root, write=False)


def test_parolali_hub(root, monkeypatch):
    with Hub.open(root, write=True, sifreli=True) as h:
        doldur(h)
    dek = sif.anahtari_coz(root)
    sif.kurtarma_kur(root, dek, IFADE, IFADE)
    sif.parola_ekle(root, dek, PAROLA, PAROLA)
    with pytest.raises(AnahtarGerekli):
        Hub.open(root, write=False)
    with pytest.raises(YanlisParola):
        Hub.open(root, write=False, parola="yanlis-yanlis-1")
    with Hub.open(root, write=False, parola=PAROLA) as h:
        assert h.search("isik")
    monkeypatch.setenv(sif.ENV_PAROLA, PAROLA)
    with Hub.open(root, write=True) as h:   # MCP/arka plan yolu: ortam değişkeni
        assert h.search("isik")


def test_sifresiz_klasore_sifreli_istenemez(root):
    with Hub.open(root, write=True) as h:
        doldur(h)
    with pytest.raises(FormatError, match="sifrele"):
        Hub.open(root, write=True, sifreli=True)


def test_bozuk_kapsayici_acilmaz(root):
    with Hub.open(root, write=True, sifreli=True) as h:
        doldur(h)
    p = root / "kimlik.db"
    b = bytearray(p.read_bytes())
    b[200] ^= 0xFF
    p.write_bytes(bytes(b))
    with pytest.raises(SifreliDosyaBozuk):
        Hub.open(root, write=False)


def test_ham_arsiv_sifreli_dogrulama_ve_silme(root, tmp_path):
    ham = tmp_path / "disa_aktarim.txt"
    ham.write_text(f"ham dosya {GIZLI} içeriği\n" * 50, encoding="utf-8")
    with Hub.open(root, write=True, sifreli=True) as h:
        sid = h.add_source("test", "1", None)
        raw = h.store_raw(sid, ham)
        assert raw.size == ham.stat().st_size
        assert sif.sifreli_mi(root / raw.path)
        assert GIZLI.encode() not in (root / raw.path).read_bytes()
        assert b"".join(h.raw_parcalari(raw.path)) == ham.read_bytes()
        assert h.verify_archive() == []
        h.store_raw(sid, ham)  # aynı dosya ikinci kez: hata yok
        h.add_events(sid, known_events(3))
        r = h.purge_source(sid)
        assert r.raw_files_deleted == 1
        assert not (root / raw.path).exists()
        h.compact()
    for yol, b in tum_dosya_baytlari(root):
        assert GIZLI.encode() not in b


def test_arsiv_bozulursa_dogrulama_yakalar(root, tmp_path):
    ham = tmp_path / "a.txt"
    ham.write_text("x" * 1000)
    with Hub.open(root, write=True, sifreli=True) as h:
        sid = h.add_source("test", "1", None)
        raw = h.store_raw(sid, ham)
        p = root / raw.path
        os.chmod(p, 0o644)
        b = bytearray(p.read_bytes())
        b[40] ^= 1
        p.write_bytes(bytes(b))
        assert any("bozuk" in x for x in h.verify_archive())


def test_toplu_ice_alma_zamanli_yazma_ve_dogruluk(root):
    with Hub.open(root, write=True, sifreli=True) as h:
        sid = h.add_source("t", "1", None)
        r = h.add_events(sid, (EventIn(event_key=f"k{i}", ts="2026-01-01T00:00:00Z", kind="k",
                                       category="notlar", payload={"i": i}, text=f"kayıt {i} ışık")
                               for i in range(3000)), batch_size=500)
        assert r.added == 3000
    with Hub.open(root, write=False) as h:
        assert h.summary()["counts"]["event"] == 3000


# ------------------------------------------------------------------ dönüşüm
def duz_hub_hazirla(root, tmp_path):
    ham = tmp_path / "girdi.json"
    ham.write_text(f'{{"gizli": "{GIZLI}"}}', encoding="utf-8")
    with Hub.open(root, write=True) as h:
        sid = doldur(h)
        h.store_raw(sid, ham)
        ozet = h.summary()
    return ham, ozet


def test_sifrele_ve_sifreyi_kaldir_gidis_donus(root, tmp_path):
    ham, ozet0 = duz_hub_hazirla(root, tmp_path)
    # şifresiz halde düz metin gerçekten diskte (testin anlamlı olduğunu gösterir)
    assert any(GIZLI.encode() in b for _y, b in tum_dosya_baytlari(root))
    r = donusum.sifrele(root)
    assert r["veritabani_sifrelendi"] and r["ham_dosya_sifrelendi"] == 1
    d = sif.durum(root)
    assert d["sifreli"] and d["ham_dosya_duz"] == 0 and d["duz_kalintilar"] == []
    for yol, b in tum_dosya_baytlari(root):
        assert GIZLI.encode() not in b and "işık".encode() not in b.lower(), yol
    assert not any(n.endswith(("-wal", "-shm", ".duz-eski")) for n in os.listdir(root))
    with Hub.open(root, write=False) as h:
        assert h.summary() == ozet0
        assert [e.event_key for e in h.search("ISIK")] == ["gizli"]
        assert h.verify_archive() == []
    # ikinci çağrı zararsız
    assert donusum.sifrele(root)["ham_dosya_sifrelendi"] == 0
    # geri al
    donusum.sifreyi_kaldir(root)
    assert not (root / sif.ANAHTAR_DOSYASI).exists()
    assert sif.db_durumu(root / "kimlik.db") == "duz"
    con = sqlite3.connect(root / "kimlik.db")      # düz sqlite3 ile doğrudan açılır
    assert con.execute("select count(*) from events").fetchone()[0] == ozet0["counts"]["event"]
    con.close()
    with Hub.open(root, write=True) as h:
        assert h.summary() == ozet0 and h.verify_archive() == []
        assert h.search("isik")
    ham_dosyalar = [p for p in (root / "arsiv").rglob("*") if p.is_file()]
    assert len(ham_dosyalar) == 1 and ham_dosyalar[0].read_bytes() == ham.read_bytes()


def test_sifrele_parolali_klasorde_sifreyi_kaldir_parola_ister(root, tmp_path):
    duz_hub_hazirla(root, tmp_path)
    donusum.sifrele(root)
    dek = sif.anahtari_coz(root)
    sif.kurtarma_kur(root, dek, IFADE, IFADE)
    sif.parola_ekle(root, dek, PAROLA, PAROLA)
    with pytest.raises(AnahtarGerekli):
        donusum.sifreyi_kaldir(root)
    with pytest.raises(YanlisParola):
        donusum.sifreyi_kaldir(root, parola="yanlis-yanlis-1")
    assert sif.db_durumu(root / "kimlik.db") == "sifreli"
    donusum.sifreyi_kaldir(root, parola=PAROLA)
    assert sif.db_durumu(root / "kimlik.db") == "duz"


def test_sifrele_yarim_kalirsa_tamamlanir(root, tmp_path):
    ham, ozet0 = duz_hub_hazirla(root, tmp_path)
    donusum.sifrele(root)
    # yarım kalmış durum benzetimi: bir ham dosya yeniden düz
    dek = sif.anahtari_coz(root)
    f = next(p for p in (root / "arsiv").rglob("*") if p.is_file())
    os.chmod(f, 0o644)
    f.write_bytes(ham.read_bytes())
    assert sif.durum(root)["ham_dosya_duz"] == 1
    donusum.sifrele(root)
    assert sif.durum(root)["ham_dosya_duz"] == 0
    with Hub.open(root, write=False) as h:
        assert h.verify_archive() == [] and h.summary() == ozet0
    assert dek


def test_sifrele_hata_olursa_eski_hal_korunur(root, tmp_path, monkeypatch):
    duz_hub_hazirla(root, tmp_path)
    once = (root / "kimlik.db").read_bytes()

    def boz(*a, **k):
        raise RuntimeError("disk dolu benzetimi")
    monkeypatch.setattr(sif, "bayt_sifrele_yaz", boz)
    with pytest.raises(RuntimeError):
        donusum.sifrele(root)
    monkeypatch.undo()
    assert sif.db_durumu(root / "kimlik.db") == "duz"
    assert not (root / sif.ANAHTAR_DOSYASI).exists()
    with Hub.open(root, write=False) as h:
        assert h.search("isik")
    assert once  # dosya hâlâ açılabiliyor


def test_eski_sema_sifreli_klasor_gocu(root):
    root.mkdir()
    (root / "arsiv").mkdir()
    con = sqlite3.connect(root / "kimlik.db", isolation_level=None)
    schema.migrate(con, migrations={1: schema.MIGRATIONS[1]})
    con.execute("INSERT INTO sources VALUES ('s','jsonl','1',NULL,'2026-01-01T00:00:00Z',NULL,NULL)")
    con.close()
    donusum.sifrele(root)
    with pytest.raises(SchemaTooOld):
        Hub.open(root, write=False)
    with Hub.open(root, write=True) as h:             # yazan süreç göç ettirir ve şifreli yazar
        assert h.schema_version == schema.SCHEMA_VERSION
        assert h.sources()[0].source_id == "s"
    with Hub.open(root, write=False) as h:
        assert h.schema_version == schema.SCHEMA_VERSION
    assert sif.db_durumu(root / "kimlik.db") == "sifreli"
