"""Güvenlik sayfası ve parola kilidi: web uçları (sahte anahtar sağlayıcıyla), parola akışları, kurtarma,
yanlış parola yavaşlatması, CSRF/Host/jeton, günlüğe/hata iletisine/diske sızıntı yok.

DPAPI burada denenemez (Linux): `SahteSaglayici` gerçek koruma sağlamaz, yalnız akışları sınar."""
import json
import logging
import time
import urllib.error
import urllib.request

import pytest

from kimlikcore import Hub, YanlisParola
from kimlikcore import sifreleme as sif
from kimlikwin import gunluk
from kimlikwin.ayarlar import Ayarlar
from kimlikwin.baslangic import Otomatik
from kimlikwin.web import Sunucu
from kimlikwin.yonetici import Yonetici

PAROLA = "Sizinti-parola-7391-xyz"
YENI_PAROLA = "Baska-parola-5520-qwe"
IFADE = "mavi bulut sabah ruzgari kasim 4817"
YENI_IFADE = "kirmizi liman gece dalgasi mayis 9026"
SIRLAR = [PAROLA, YENI_PAROLA, IFADE, YENI_IFADE, "yanlis-parola-0000-zzz", "yanlis ifade ama uzun yeterince 111"]


@pytest.fixture(autouse=True)
def sahte_sistem(monkeypatch):
    monkeypatch.setattr(sif, "KDF_N", 1 << 4)
    sif.saglayici_ayarla(sif.SahteSaglayici("guvenlik-testi"))
    yield
    sif.saglayici_ayarla(None)


class Saat:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class _AU:
    d = None

    def oku(self): return self.d
    def yaz(self, k): self.d = k
    def sil(self): self.d = None


def yeni_yonetici(tmp_path, saat=None):
    y = Yonetici(Ayarlar(tmp_path / "ayar"), Otomatik(_AU()), secici=lambda t: None, claude_yolu=lambda: None)
    if saat:
        y.guvenlik.sinir._saat = saat
    return y


@pytest.fixture
def saat():
    return Saat()


@pytest.fixture
def ym(tmp_path, veri, saat):
    y = yeni_yonetici(tmp_path, saat)
    y.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False})
    yield y
    y.kapat()


def hata_kodu(islev, *a, **k):
    from kimlikwin.cekirdek import IslemHatasi
    with pytest.raises(IslemHatasi) as e:
        islev(*a, **k)
    return e.value.kod


def parola_kur(ym, parola=PAROLA, ifade=IFADE):
    ym.api("guvenlik_kurtarma_kur", {"ifade": ifade, "ifade_tekrar": ifade, "anladim": True})
    ym.api("guvenlik_parola_ekle", {"parola": parola, "parola_tekrar": parola, "anladim": True})


def yeniden_baslat(tmp_path, ym, saat=None):
    ym.kapat()
    y = yeni_yonetici(tmp_path, saat)
    y.baslat()
    return y


# ------------------------------------------------------------------ durum, kurtarma ifadesi, parola
def test_durum_varsayilan_sifreli_parolasiz(ym):
    d = ym.api("guvenlik_durum", {})
    assert d["sifreli"] and not d["parola_var"] and not d["kurtarma_var"] and d["os_korumasi"]
    assert d["saglayici_var"] and d["kapali_notu"] is None
    assert "KİMSE" in d["uyari_kurtarma"]


def test_ifade_ve_parola_degerlendirici_cekirdegi_kullanir(ym):
    zayif = ym.api("guvenlik_ifade_degerlendir", {"ifade": "correct horse battery staple"})
    assert not zayif["uygun"] and zayif["guc"] == "zayıf"
    kisa = ym.api("guvenlik_ifade_degerlendir", {"ifade": "kısa yanıt"})
    assert not kisa["uygun"]
    iyi = ym.api("guvenlik_ifade_degerlendir", {"ifade": IFADE})
    assert iyi["uygun"] and iyi["guc"] in ("orta", "iyi", "güçlü")
    assert not ym.api("guvenlik_parola_degerlendir", {"parola": "kisa"})["uygun"]
    assert ym.api("guvenlik_parola_degerlendir", {"parola": PAROLA})["uygun"]


def test_kurtarma_onaysiz_reddedilir_ve_hicbir_sey_yazilmaz(ym):
    assert hata_kodu(ym.api, "guvenlik_kurtarma_kur", {"ifade": IFADE, "ifade_tekrar": IFADE}) == "onay_gerekli"
    assert hata_kodu(ym.api, "guvenlik_kurtarma_kur", {"ifade": IFADE, "ifade_tekrar": IFADE, "anladim": "evet"}) == "onay_gerekli"
    assert not ym.api("guvenlik_durum", {})["kurtarma_var"]


def test_kurtarma_kurallari_uygulanir(ym):
    from kimlikcore import KuralHatasi
    for ifade, tekrar in [("correct horse battery staple", "correct horse battery staple"),
                          ("kısa yanıt", "kısa yanıt"), (IFADE, IFADE + " farkli")]:
        with pytest.raises(KuralHatasi):
            ym.api("guvenlik_kurtarma_kur", {"ifade": ifade, "ifade_tekrar": tekrar, "anladim": True})
    assert not ym.api("guvenlik_durum", {})["kurtarma_var"]


def test_parola_once_kurtarma_ifadesi_zorunlu(ym):
    assert hata_kodu(ym.api, "guvenlik_parola_ekle",
                     {"parola": PAROLA, "parola_tekrar": PAROLA, "anladim": True}) == "kurtarma_gerekli"
    assert not ym.api("guvenlik_durum", {})["parola_var"]


def test_parola_onaysiz_ve_kuralsiz_reddedilir(ym):
    from kimlikcore import KuralHatasi
    ym.api("guvenlik_kurtarma_kur", {"ifade": IFADE, "ifade_tekrar": IFADE, "anladim": True})
    assert hata_kodu(ym.api, "guvenlik_parola_ekle", {"parola": PAROLA, "parola_tekrar": PAROLA}) == "onay_gerekli"
    for p, t in [("kisa", "kisa"), (PAROLA, PAROLA + "x"), (IFADE, IFADE)]:
        with pytest.raises(KuralHatasi):
            ym.api("guvenlik_parola_ekle", {"parola": p, "parola_tekrar": t, "anladim": True})
    d = ym.api("guvenlik_durum", {})
    assert d["kurtarma_var"] and not d["parola_var"] and d["os_korumasi"]


def test_parola_ekle_os_yuvasini_kaldirir_ve_oturum_acik_kalir(ym, veri):
    ym.api("persona_ekle", {"metin": "Çay severim", "kategori": "tercihler"})
    parola_kur(ym)
    d = ym.api("guvenlik_durum", {})
    assert d["parola_var"] and d["kurtarma_var"] and not d["os_korumasi"]
    assert ym.api("persona_liste", {})            # oturum açık
    assert hata_kodu(ym.api, "guvenlik_parola_ekle", {"parola": PAROLA, "parola_tekrar": PAROLA, "anladim": True}) == "parola_var"


# ------------------------------------------------------------------ açılışta parola kilidi
def test_parolali_klasor_acilista_kilitli_ve_diger_api_kapali(tmp_path, ym, saat):
    parola_kur(ym)
    y = yeniden_baslat(tmp_path, ym, saat)
    try:
        assert y.uygulama is None
        ac = y.api("acilis", {})
        assert ac["kilit"]["tur"] == "parola" and ac["kilit"]["kurtarma_var"] and not ac["sihirbaz"]
        assert PAROLA not in json.dumps(ac)
        for ad, g in [("durum", {}), ("ara", {"sorgu": "x"}), ("guvenlik_durum", {}), ("kaynaklar", {}),
                      ("claude_ekle", {}), ("kisiler", {}), ("harita", {})]:
            assert hata_kodu(y.api, ad, g) == "kilitli_parola", ad
    finally:
        y.kapat()


def test_dogru_parola_acar_yanlis_parola_reddedilir(tmp_path, ym, saat):
    parola_kur(ym)
    y = yeniden_baslat(tmp_path, ym, saat)
    try:
        assert hata_kodu(y.api, "parola_ac", {"parola": "yanlis-parola-0000-zzz"}) == "yanlis_parola"
        assert y.uygulama is None and y.kilit is not None
        assert y.api("parola_ac", {"parola": PAROLA}) == {"ok": True}
        assert y.kilit is None and y.api("durum", {})["sema"]
        assert y.api("acilis", {})["kilit"] is None
    finally:
        y.kapat()


def test_yanlis_deneme_yavaslatilir_ve_beklerken_dogru_parola_bile_denenmez(tmp_path, ym, saat):
    parola_kur(ym)
    y = yeniden_baslat(tmp_path, ym, saat)
    try:
        for _ in range(2):   # ilk iki hata bedava
            assert hata_kodu(y.api, "parola_ac", {"parola": "yanlis-parola-0000-zzz"}) == "yanlis_parola"
        assert hata_kodu(y.api, "parola_ac", {"parola": "yanlis-parola-0000-zzz"}) == "yanlis_parola"   # 3. hata: 5 sn
        assert hata_kodu(y.api, "parola_ac", {"parola": PAROLA}) == "cok_deneme"
        saat.t += 4
        assert hata_kodu(y.api, "parola_ac", {"parola": PAROLA}) == "cok_deneme"
        saat.t += 2
        assert hata_kodu(y.api, "parola_ac", {"parola": "yanlis-parola-0000-zzz"}) == "yanlis_parola"   # 4. hata: 10 sn
        saat.t += 9
        assert hata_kodu(y.api, "parola_ac", {"parola": PAROLA}) == "cok_deneme"
        saat.t += 2
        assert y.api("parola_ac", {"parola": PAROLA}) == {"ok": True}
        assert y.guvenlik.sinir.kalan() == 0
    finally:
        y.kapat()


def test_bekleme_ust_siniri(saat):
    from kimlikwin.guvenlik import DenemeSiniri
    s = DenemeSiniri(saat)
    bekler = [s.basarisiz() for _ in range(12)]
    assert bekler[:3] == [0, 0, 5] and max(bekler) == 300 and bekler[3] == 10


def test_kilit_ekraninda_kurtarma_ifadesiyle_yeni_parola(tmp_path, ym, saat):
    parola_kur(ym)
    y = yeniden_baslat(tmp_path, ym, saat)
    try:
        assert hata_kodu(y.api, "kilit_kurtar", {"ifade": "tamamen yanlis bir ifade burada 123"}) == "yanlis_parola"
        assert y.uygulama is None
        r = y.api("kilit_kurtar", {"ifade": IFADE.upper(), "yeni_parola": YENI_PAROLA, "yeni_parola_tekrar": YENI_PAROLA})
        assert r["mod"] == "parola" and y.uygulama is not None and y.kilit is None
        d = y.api("guvenlik_durum", {})
        assert d["parola_var"] and not d["os_korumasi"]
    finally:
        y.kapat()
    y2 = yeni_yonetici(tmp_path, saat)
    y2.baslat()
    try:
        assert hata_kodu(y2.api, "parola_ac", {"parola": PAROLA}) == "yanlis_parola"   # eski parola geçersiz
        y2.api("parola_ac", {"parola": YENI_PAROLA})
    finally:
        y2.kapat()


def test_kilit_ekraninda_kurtarma_parolasiz_hesaba_baglar(tmp_path, ym, saat):
    parola_kur(ym)
    y = yeniden_baslat(tmp_path, ym, saat)
    try:
        r = y.api("kilit_kurtar", {"ifade": IFADE})
        assert r["mod"] == "os" and y.uygulama is not None
        d = y.api("guvenlik_durum", {})
        assert not d["parola_var"] and d["os_korumasi"] and d["kurtarma_var"]
    finally:
        y.kapat()
    y2 = yeni_yonetici(tmp_path, saat)
    y2.baslat()
    assert y2.uygulama is not None and y2.kilit is None      # artık parola sorulmaz
    y2.kapat()


def test_baska_hesapta_acilamayan_klasor_kurtarma_ekrani_gosterir(tmp_path, ym, saat):
    ym.api("guvenlik_kurtarma_kur", {"ifade": IFADE, "ifade_tekrar": IFADE, "anladim": True})
    ym.kapat()
    sif.saglayici_ayarla(sif.SahteSaglayici("baska-hesap"))       # farklı Windows hesabı
    y = yeni_yonetici(tmp_path, saat)
    y.baslat()
    try:
        assert y.kilit["tur"] == "hesap" and y.uygulama is None
        assert hata_kodu(y.api, "parola_ac", {"parola": PAROLA}) == "parola_degil"
        assert y.api("kilit_kurtar", {"ifade": IFADE})["mod"] == "os"
        assert y.uygulama is not None
    finally:
        y.kapat()


def test_kurtarma_ifadesi_olmayan_acilamayan_klasor_kilit_ekrani_vermez(tmp_path, ym, saat):
    ym.kapat()
    sif.saglayici_ayarla(sif.SahteSaglayici("baska-hesap"))
    y = yeni_yonetici(tmp_path, saat)
    from kimlikcore import AnahtarGerekli
    with pytest.raises(AnahtarGerekli):          # uygulama.py bunu 'başlangıç hatası' olarak gösterir
        y.baslat()


# ------------------------------------------------------------------ parolayı kaldır / sıfırla (oturum açıkken)
def test_parola_kaldir_mevcut_parola_ister(tmp_path, ym, saat):
    parola_kur(ym)
    assert hata_kodu(ym.api, "guvenlik_parola_kaldir", {}) == "parola_gerekli"
    assert hata_kodu(ym.api, "guvenlik_parola_kaldir", {"mevcut_parola": "yanlis-parola-0000-zzz"}) == "yanlis_parola"
    assert ym.api("guvenlik_durum", {})["parola_var"]
    ym.api("guvenlik_parola_kaldir", {"mevcut_parola": PAROLA})
    d = ym.api("guvenlik_durum", {})
    assert not d["parola_var"] and d["os_korumasi"] and d["kurtarma_var"]
    y = yeniden_baslat(tmp_path, ym, saat)
    assert y.uygulama is not None
    y.kapat()


def test_oturum_aciksen_kurtarma_ifadesiyle_parola_sifirla(tmp_path, ym, saat):
    parola_kur(ym)
    assert hata_kodu(ym.api, "guvenlik_kurtar", {"ifade": "yanlis ifade ama uzun yeterince 111"}) == "yanlis_parola"
    assert ym.api("guvenlik_kurtar", {"ifade": IFADE, "yeni_parola": YENI_PAROLA,
                                      "yeni_parola_tekrar": YENI_PAROLA})["mod"] == "parola"
    y = yeniden_baslat(tmp_path, ym, saat)
    try:
        y.api("parola_ac", {"parola": YENI_PAROLA})
    finally:
        y.kapat()


def test_ifade_degistirmek_parolaliyken_mevcut_parola_ister(ym):
    parola_kur(ym)
    g = {"ifade": YENI_IFADE, "ifade_tekrar": YENI_IFADE, "anladim": True}
    assert hata_kodu(ym.api, "guvenlik_kurtarma_kur", g) == "parola_gerekli"
    ym.api("guvenlik_kurtarma_kur", {**g, "mevcut_parola": PAROLA})
    assert ym.api("guvenlik_kurtar", {"ifade": YENI_IFADE})["mod"] == "os"


# ------------------------------------------------------------------ şifrelemeyi kapat / aç
def bekle(ym, sn=60):
    bas = time.time()
    while time.time() - bas < sn:
        d = ym.api("guvenlik_donusum_durum", {})
        if d["durum"] != "calisiyor":
            return d
        time.sleep(0.05)
    raise AssertionError("dönüşüm bitmedi")


def test_sifrelemeyi_kapat_ve_ac_veri_korunur(tmp_path, ym, veri):
    ym.api("persona_ekle", {"metin": "Çay severim", "kategori": "tercihler"})
    assert hata_kodu(ym.api, "guvenlik_donustur_baslat", {"tur": "kapat"}) == "onay_gerekli"
    assert hata_kodu(ym.api, "guvenlik_donustur_baslat", {"tur": "kapat", "onay": "kaldir"}) == "onay_gerekli"
    assert hata_kodu(ym.api, "guvenlik_donustur_baslat", {"tur": "ac"}) == "zaten_sifreli"
    ym.api("guvenlik_donustur_baslat", {"tur": "kapat", "onay": "KALDIR"})
    assert hata_kodu(ym.api, "durum", {}) == "mesgul"               # dönüşüm sürerken diğer işlemler kapalı
    d = bekle(ym)
    assert d["durum"] == "bitti", d
    assert sif.db_durumu(veri / "kimlik.db") == "duz" and not (veri / "anahtar.json").exists()
    g = ym.api("guvenlik_durum", {})
    assert not g["sifreli"] and g["kapali_notu"]
    assert "Çay severim" in json.dumps(ym.api("persona_liste", {}), ensure_ascii=False)
    ym.api("guvenlik_donustur_baslat", {"tur": "ac"})
    assert bekle(ym)["durum"] == "bitti"
    assert sif.db_durumu(veri / "kimlik.db") == "sifreli" and ym.api("guvenlik_durum", {})["os_korumasi"]
    assert "Çay severim" in json.dumps(ym.api("persona_liste", {}), ensure_ascii=False)


def test_parolaliyken_kapatmak_parola_ister(tmp_path, ym, veri, saat):
    parola_kur(ym)
    g = {"tur": "kapat", "onay": "KALDIR"}
    assert hata_kodu(ym.api, "guvenlik_donustur_baslat", g) == "parola_gerekli"
    assert hata_kodu(ym.api, "guvenlik_donustur_baslat", {**g, "mevcut_parola": "yanlis-parola-0000-zzz"}) == "yanlis_parola"
    assert ym.uygulama is not None                                  # reddedilince veritabanı kapanmadı
    ym.api("guvenlik_donustur_baslat", {**g, "mevcut_parola": PAROLA})
    assert bekle(ym)["durum"] == "bitti"
    assert sif.db_durumu(veri / "kimlik.db") == "duz"
    assert not ym.api("guvenlik_durum", {})["parola_var"]


def test_saglayici_yoksa_sifrelemeyi_acmak_reddedilir(ym):
    ym.api("guvenlik_donustur_baslat", {"tur": "kapat", "onay": "KALDIR"})
    bekle(ym)
    sif.saglayici_ayarla(None)
    assert hata_kodu(ym.api, "guvenlik_donustur_baslat", {"tur": "ac"}) == "saglayici_yok"
    assert ym.uygulama is not None


# ------------------------------------------------------------------ MCP + parola kararı
def test_parolali_klasorde_claude_ekle_reddedilir_ve_ayar_dosyasina_dokunulmaz(tmp_path, veri, saat):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text('{"mcpServers": {}}', encoding="utf-8")
    y = Yonetici(Ayarlar(tmp_path / "ayar"), Otomatik(_AU()), secici=lambda t: None, claude_yolu=lambda: cfg)
    y.guvenlik.sinir._saat = saat
    try:
        y.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False})
        assert y.api("claude_ekle", {})["durum"] == "eklendi"          # parolasızken çalışır
        assert y.api("baglanti_bilgisi", {})["parola_uyari"] is None
        assert y.api("guvenlik_durum", {})["claude_girisi_var"] is True
        parola_kur(y)
        once = cfg.read_text(encoding="utf-8")
        assert hata_kodu(y.api, "claude_ekle", {}) == "parola_mcp"
        assert cfg.read_text(encoding="utf-8") == once
        assert len(list(tmp_path.glob("claude_desktop_config.json.kimlik-yedek-*"))) == 1   # yalnız ilk (parolasız) ekleme yedek aldı
        b = y.api("baglanti_bilgisi", {})
        assert "parola" in b["parola_uyari"].lower() and PAROLA not in json.dumps(b)
        assert "KIMLIK_PAROLA" not in b["metin"]
    finally:
        y.kapat()


def test_mcp_parolali_klasoru_kendiliginden_acamaz(tmp_path, ym, veri, monkeypatch):
    from kimlikcore import AnahtarGerekli
    parola_kur(ym)
    monkeypatch.delenv("KIMLIK_PAROLA", raising=False)
    with pytest.raises(AnahtarGerekli):
        Hub.open(veri, write=False)       # MCP süreci böyle açar (DPAPI yuvası yok, parola yok)


# ------------------------------------------------------------------ kişi değişimi ve sihirbaz
def test_baska_kisinin_parolali_klasorune_gecis_parola_ister(tmp_path, ym, saat):
    diger = tmp_path / "diger"
    ym.api("kisi_ekle", {"ad": "Ayşe", "yol": str(diger)})
    parola_kur(ym)                                        # Ayşe'nin klasörü parolalı
    ben = next(k for k in ym.api("kisiler", {})["kisiler"] if k["ad"] == "Ben")
    ym.api("kisi_sec", {"kisi_id": ben["id"]})
    ayse = next(k for k in ym.api("kisiler", {})["kisiler"] if k["ad"] == "Ayşe")
    ym.guvenlik.unut(diger)                               # parola bellekte yokmuş gibi
    assert hata_kodu(ym.api, "kisi_sec", {"kisi_id": ayse["id"]}) == "parola_gerekli"
    assert ym.uygulama is not None and ym.api("kisiler", {})["secili"] == ben["id"]   # eski kişi geri açıldı
    assert hata_kodu(ym.api, "kisi_sec", {"kisi_id": ayse["id"], "parola": "yanlis-parola-0000-zzz"}) == "yanlis_parola"
    assert ym.api("kisi_sec", {"kisi_id": ayse["id"], "parola": PAROLA})["secili"] == ayse["id"]


def test_sihirbazda_mevcut_parolali_klasor_parola_ister(tmp_path, veri, saat):
    y1 = yeni_yonetici(tmp_path, saat)
    y1.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False})
    parola_kur(y1)
    y1.kapat()
    (tmp_path / "ayar" / "ayarlar.json").unlink(missing_ok=True)
    for f in (tmp_path / "ayar").glob("*.json"):
        f.unlink()
    y2 = yeni_yonetici(tmp_path, saat)
    try:
        assert y2.api("acilis", {})["sihirbaz"] is True
        assert hata_kodu(y2.api, "sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False}) == "parola_gerekli"
        assert y2.uygulama is None
        y2.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False, "parola": PAROLA})
        assert y2.uygulama is not None
    finally:
        y2.kapat()


# ------------------------------------------------------------------ web katmanı: jeton, Host, Origin, yöntem
class Istemci:
    def __init__(self, s: Sunucu):
        self.s = s

    def post(self, ad, girdi=None, *, jeton="dogru", host=None, origin=None, ham=None):
        b = {"Content-Type": "application/json"}
        if jeton == "dogru":
            b["X-Kimlik-Jeton"] = self.s.jeton
        elif jeton:
            b["X-Kimlik-Jeton"] = jeton
        if host:
            b["Host"] = host
        if origin:
            b["Origin"] = origin
        req = urllib.request.Request(f"http://127.0.0.1:{self.s.port}/api/{ad}",
                                     ham if ham is not None else json.dumps(girdi or {}).encode(), b)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def api(self, ad, girdi=None):
        kod, govde = self.post(ad, girdi)
        assert kod == 200, (ad, kod, govde)
        return json.loads(govde)


@pytest.fixture
def web(ym):
    s = Sunucu(ym, 0)
    s.baslat()
    yield Istemci(s), s
    s.durdur()


YENI_UCLAR = ["guvenlik_durum", "guvenlik_ifade_degerlendir", "guvenlik_parola_degerlendir", "guvenlik_kurtarma_kur",
              "guvenlik_parola_ekle", "guvenlik_parola_kaldir", "guvenlik_kurtar", "guvenlik_donustur_baslat",
              "guvenlik_donusum_durum", "parola_ac", "kilit_kurtar"]


@pytest.mark.parametrize("ad", YENI_UCLAR)
def test_yeni_uclar_jeton_host_origin_ister(web, ad):
    c, s = web
    g = {"parola": PAROLA, "ifade": IFADE}
    assert c.post(ad, g, jeton=None)[0] == 403
    assert c.post(ad, g, jeton="yanlis")[0] == 403
    assert c.post(ad, g, host="evil.example")[0] == 403
    assert c.post(ad, g, origin="http://evil.example")[0] == 403
    with pytest.raises(urllib.error.HTTPError) as e:           # GET ile erişilemez (yalnız POST)
        urllib.request.urlopen(f"http://127.0.0.1:{s.port}/api/{ad}?parola={PAROLA}")
    assert e.value.code == 404


def test_web_uclarinda_tam_akis(web, veri):
    c, _ = web
    assert c.api("guvenlik_durum")["sifreli"]
    kod, govde = c.post("guvenlik_kurtarma_kur", {"ifade": "kısa", "ifade_tekrar": "kısa", "anladim": True})
    assert kod == 400 and "ifade" in json.loads(govde)["hata"].lower()
    c.api("guvenlik_kurtarma_kur", {"ifade": IFADE, "ifade_tekrar": IFADE, "anladim": True})
    c.api("guvenlik_parola_ekle", {"parola": PAROLA, "parola_tekrar": PAROLA, "anladim": True})
    assert c.api("guvenlik_durum")["parola_var"]
    kod, govde = c.post("guvenlik_parola_kaldir", {"mevcut_parola": "yanlis-parola-0000-zzz"})
    assert kod == 400 and json.loads(govde)["kod"] == "yanlis_parola"


def test_web_kilitliyken_kod_423_ve_cok_deneme_429(tmp_path, ym, saat):
    parola_kur(ym)
    y = yeniden_baslat(tmp_path, ym, saat)
    s = Sunucu(y, 0)
    s.baslat()
    c = Istemci(s)
    try:
        assert c.post("durum")[0] == 423
        assert json.loads(c.post("durum")[1])["kod"] == "kilitli_parola"
        assert c.api("acilis")["kilit"]["tur"] == "parola"
        for _ in range(3):
            assert c.post("parola_ac", {"parola": "yanlis-parola-0000-zzz"})[0] == 400
        kod, govde = c.post("parola_ac", {"parola": PAROLA})
        assert kod == 429 and int(json.loads(govde)["ek"]) > 0
        saat.t += 100
        assert c.api("parola_ac", {"parola": PAROLA}) == {"ok": True}
    finally:
        s.durdur()
        y.kapat()


# ------------------------------------------------------------------ SIZINTI: günlük, hata iletisi, rapor, diske
def _tum_dosyalar_metni(*kokler):
    for kok in kokler:
        for f in kok.rglob("*"):
            if f.is_file() and f.name != "hub.lock":
                yield f, f.read_bytes()


def test_parola_ve_ifade_hicbir_yere_sizmaz(tmp_path, ym, veri, saat, capfd):
    ayar_dizin = tmp_path / "ayar"
    gunluk_yolu = gunluk.kur(ayar_dizin)
    yakalanan: list[str] = []

    class Tut(logging.Handler):
        def emit(self, kayit):
            yakalanan.append(self.format(kayit) + "|" + repr(kayit.args) + "|" + str(kayit.exc_info))

    tut = Tut(logging.NOTSET)
    gunluk.log().addHandler(tut)
    gunluk.log().setLevel(logging.DEBUG)
    kok_log = logging.getLogger()
    kok_log.addHandler(tut)
    yanitlar: list[str] = []
    s = Sunucu(ym, 0)
    s.baslat()
    c = Istemci(s)

    def p(ad, g=None):
        kod, govde = c.post(ad, g)
        yanitlar.append(govde)
        return kod, govde

    try:
        # başarılı ve başarısız akışlar (gövdede sır var)
        p("guvenlik_kurtarma_kur", {"ifade": "correct horse battery staple", "ifade_tekrar": "correct horse battery staple", "anladim": True})
        p("guvenlik_kurtarma_kur", {"ifade": IFADE, "ifade_tekrar": IFADE, "anladim": True})
        p("guvenlik_ifade_degerlendir", {"ifade": IFADE})
        p("guvenlik_parola_degerlendir", {"parola": PAROLA})
        p("guvenlik_parola_ekle", {"parola": PAROLA, "parola_tekrar": PAROLA + "x", "anladim": True})
        p("guvenlik_parola_ekle", {"parola": PAROLA, "parola_tekrar": PAROLA, "anladim": True})
        p("guvenlik_parola_kaldir", {"mevcut_parola": "yanlis-parola-0000-zzz"})
        p("guvenlik_kurtar", {"ifade": "yanlis ifade ama uzun yeterince 111"})
        p("guvenlik_kurtar", {"ifade": IFADE, "yeni_parola": YENI_PAROLA, "yeni_parola_tekrar": YENI_PAROLA})
        p("guvenlik_donustur_baslat", {"tur": "kapat", "onay": "KALDIR", "mevcut_parola": "yanlis-parola-0000-zzz"})
        p("kisi_sec", {"kisi_id": "yok", "parola": PAROLA})
        p("hata_raporu", {"adim": "deneme", "mesaj": "x", "ek": ""})
        # beklenmeyen/özel hata: iletisinde parola olan bir istisna
        import kimlikcore.sifreleme as k
        orijinal = k.parola_kaldir
        k.parola_kaldir = lambda *a, **kw: (_ for _ in ()).throw(ValueError(f"patladi {YENI_PAROLA}"))
        try:
            kod, govde = p("guvenlik_parola_kaldir", {"mevcut_parola": YENI_PAROLA})
            assert kod == 400 and YENI_PAROLA not in govde and "***" in govde
        finally:
            k.parola_kaldir = orijinal
        k.parola_kaldir = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError(f"patladi {YENI_PAROLA}"))
        try:
            kod, govde = p("guvenlik_parola_kaldir", {"mevcut_parola": YENI_PAROLA})
            assert kod == 500 and YENI_PAROLA not in govde
        finally:
            k.parola_kaldir = orijinal
        # yeniden başlat: kilit ekranı + yanlış/doğru parola
        ym.kapat()
        s.durdur()
        y = yeni_yonetici(tmp_path, saat)
        y.baslat()
        s = Sunucu(y, 0)
        s.baslat()
        c = Istemci(s)
        for _ in range(3):
            p("parola_ac", {"parola": "yanlis-parola-0000-zzz"})
        p("parola_ac", {"parola": YENI_PAROLA})
        saat.t += 1000
        p("kilit_kurtar", {"ifade": "yanlis ifade ama uzun yeterince 111"})
        p("parola_ac", {"parola": YENI_PAROLA})
        rapor = c.api("hata_raporu", {"adim": "x", "mesaj": "y"})["metin"]
        yanitlar.append(json.dumps(rapor))
        ham_istek = c.post("parola_ac", ham=b'{"parola": "' + PAROLA.encode() + b'"')    # bozuk JSON
        yanitlar.append(ham_istek[1])
        assert ham_istek[0] == 400
        erisim = json.dumps(y.api("erisim_kaydi", {})) if y.uygulama else ""
    finally:
        s.durdur()
        gunluk.log().removeHandler(tut)
        kok_log.removeHandler(tut)
        for yy in (ym, locals().get("y")):
            if yy:
                yy.kapat()
    cikti = capfd.readouterr()
    ortak = [gunluk_yolu.read_text(encoding="utf-8", errors="replace"), "\n".join(yakalanan),
             "\n".join(yanitlar), cikti.out, cikti.err, erisim]
    for sir in SIRLAR:
        for i, metin in enumerate(ortak):
            assert sir not in metin, f"sır sızdı (kaynak #{i}): {sir!r}"
    # diskte: ayar klasörü ve veri klasöründeki HİÇBİR dosyada düz sır olmamalı (anahtar.json dahil)
    for f, ham in _tum_dosyalar_metni(tmp_path / "ayar", veri):
        for sir in SIRLAR:
            assert sir.encode("utf-8") not in ham, f"{f.name} içinde düz sır var"
    assert len(yanitlar) > 15


def test_web_katmani_istek_gunlugu_yazmaz(web, capfd):
    c, _ = web
    c.post("guvenlik_parola_ekle", {"parola": PAROLA, "parola_tekrar": PAROLA, "anladim": True})
    c.post("durum")
    o = capfd.readouterr()
    assert o.out == "" and o.err == ""            # BaseHTTPRequestHandler erişim satırı yok


def test_kilitliyken_yalniz_kural_degerlendiricileri_calisir(tmp_path, ym, saat):
    parola_kur(ym)
    y = yeniden_baslat(tmp_path, ym, saat)
    try:
        assert y.api("guvenlik_parola_degerlendir", {"parola": PAROLA})["uygun"]
        assert y.api("guvenlik_ifade_degerlendir", {"ifade": IFADE})["uygun"]
        for ad in ("guvenlik_durum", "guvenlik_kurtar", "guvenlik_parola_kaldir", "guvenlik_donustur_baslat"):
            assert hata_kodu(y.api, ad, {"ifade": IFADE} if ad == "guvenlik_kurtar" else {}) == "kilitli_parola", ad
    finally:
        y.kapat()


def test_kilit_kurtar_zayif_yeni_parolayi_reddeder_ve_kilit_kalir(tmp_path, ym, saat):
    from kimlikcore import KuralHatasi
    parola_kur(ym)
    y = yeniden_baslat(tmp_path, ym, saat)
    try:
        with pytest.raises(KuralHatasi):
            y.api("kilit_kurtar", {"ifade": IFADE, "yeni_parola": "kisa", "yeni_parola_tekrar": "kisa"})
        assert y.uygulama is None and y.kilit is not None
        y.api("parola_ac", {"parola": PAROLA})      # eski parola hâlâ geçerli
    finally:
        y.kapat()


def test_hakkinda_notu_artik_parola_ekrani_yok_demez(ym):
    n = ym.api("hakkinda", {})["sifreleme_notu"]
    assert "Güvenlik sayfası" in n and "ekranı yoktur" not in n
