"""Arayüzden bağımsız iş mantığı: sihirbaz, Claude ayarı, otomatik başlama, hata raporu, sağlık."""
import json
import sys

import pytest
from kimlikcore import Hub, HubLockedError

from kimlikwin import claude_ayar, hata_raporu, saglik, veri_klasoru
from kimlikwin.baslangic import Otomatik


# ---------------------------------------------------------------- veri klasörü / sihirbaz
def test_boyut_metni():
    assert veri_klasoru.boyut_metni(512) == "512 B"
    assert veri_klasoru.boyut_metni(1536) == "1,5 KB"
    assert veri_klasoru.boyut_metni(5 * 1024**3) == "5,0 GB"


def test_denetle_durumlari(tmp_path):
    d = veri_klasoru.denetle(tmp_path / "yeni" / "alt")
    assert d.ok and d.durum == "yeni" and d.bos_alan > 0 and "B" in d.bos_alan_metni
    assert veri_klasoru.denetle("goreli/yol").durum == "goreli"
    assert not veri_klasoru.denetle("").ok
    dosya = tmp_path / "d.txt"
    dosya.write_text("x")
    assert veri_klasoru.denetle(dosya).durum == "dosya"
    dolu = tmp_path / "dolu"
    dolu.mkdir()
    (dolu / "baska.txt").write_text("x")
    assert veri_klasoru.denetle(dolu).durum == "dolu"
    bos = tmp_path / "bos"
    bos.mkdir()
    assert veri_klasoru.denetle(bos).durum == "bos"


def test_olustur_yapiyi_kurar_ve_mevcudu_kabul_eder(tmp_path):
    p = tmp_path / "kurulum"
    r = veri_klasoru.olustur(p)
    assert {"kimlik.db", "arsiv", "cikti"} <= set(r["dosyalar"])
    assert "erisim.db" not in r["dosyalar"] and "oneri.db" not in r["dosyalar"]   # artık kimlik.db içinde
    assert not r["mevcut_idi"]
    assert veri_klasoru.denetle(p).durum == "mevcut"
    assert veri_klasoru.olustur(p)["mevcut_idi"]
    with pytest.raises(ValueError):
        veri_klasoru.olustur(tmp_path / "x.txt" if (tmp_path / "x.txt").write_text("a") else p / "kimlik.db")


def test_sihirbaz_tamamla_ayar_ve_otomatik_baslama(yonetici, veri, arka_uc):
    assert yonetici.api("acilis", {})["sihirbaz"] is True
    with pytest.raises(Exception) as e:
        yonetici.api("durum", {})
    assert getattr(e.value, "kod", "") == "sihirbaz_gerekli"
    r = yonetici.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": True})
    assert r["baglanti"]["ortam"]["KIMLIK_VERI"] == str(veri)
    assert arka_uc.deger and "--arka-plan" in arka_uc.deger
    assert yonetici.ayarlar["ilk_acilis_tamam"] and yonetici.ayarlar["veri_klasoru"] == str(veri)
    assert yonetici.api("acilis", {})["sihirbaz"] is False
    # ayarlar diskten yeniden okununca da duruyor
    from kimlikwin.ayarlar import Ayarlar
    assert Ayarlar(yonetici.ayarlar.dizin)["ilk_acilis_tamam"] is True
    # girişte başlatma kapatılabilir
    yonetici.api("ayar_yaz", {"otomatik_baslat": False})
    assert arka_uc.deger is None and not yonetici.api("ayarlar", {})["otomatik_baslat"]


def test_otomatik_destek_yoksa_hata_degil_uyari(tmp_path, monkeypatch):
    from kimlikwin import baslangic
    from kimlikwin.ayarlar import Ayarlar
    from kimlikwin.yonetici import Yonetici
    monkeypatch.setattr(baslangic, "varsayilan_arka_uc", lambda: None)   # kayıt defteri arka ucu yok (platformdan bağımsız)
    y = Yonetici(Ayarlar(tmp_path / "a"), Otomatik(None), claude_yolu=lambda: None)
    assert not y.otomatik.desteklenir
    assert "desteklenm" in y.api("ayar_yaz", {"otomatik_baslat": True})["uyari"]


def test_tek_yazan_surec(kurulu, veri):
    with pytest.raises(HubLockedError):
        Hub.open(veri, write=True)
    # okuyucu (MCP gibi) engellenmez
    with Hub.open(veri, write=False) as h:
        assert h.schema_version


# ---------------------------------------------------------------- Claude Desktop ayarı
GIRIS_ANAHTAR = lambda: ("app-1", "kim_deneme")  # noqa: E731


def test_claude_ekle_yedek_alir_ve_mevcutlari_bozmaz(tmp_path):
    f = tmp_path / "claude_desktop_config.json"
    ilk = {"theme": "dark", "mcpServers": {"baska": {"command": "x", "args": ["1"]}}}
    f.write_text(json.dumps(ilk), encoding="utf-8")
    s = claude_ayar.ekle(f, GIRIS_ANAHTAR, tmp_path / "v")
    assert s.durum == "eklendi" and s.yedek
    assert json.loads(open(s.yedek, encoding="utf-8").read()) == ilk
    yeni = json.loads(f.read_text(encoding="utf-8"))
    assert yeni["theme"] == "dark" and yeni["mcpServers"]["baska"] == ilk["mcpServers"]["baska"]
    g = yeni["mcpServers"]["kimlik-merkezi"]
    assert g["env"]["KIMLIK_ANAHTAR"] == "kim_deneme" and g["env"]["KIMLIK_VERI"] == str(tmp_path / "v")
    # ikinci kez: güncellenir, çoğalmaz, yedek yenisi
    s2 = claude_ayar.ekle(f, lambda: ("app-2", "kim_yeni"), tmp_path / "v")
    assert s2.durum == "guncellendi" and s2.yedek != s.yedek
    yeni = json.loads(f.read_text(encoding="utf-8"))
    assert list(yeni["mcpServers"]) == ["baska", "kimlik-merkezi"]
    assert yeni["mcpServers"]["kimlik-merkezi"]["env"]["KIMLIK_ANAHTAR"] == "kim_yeni"


def test_claude_ekle_bozuk_dosyaya_dokunmaz(tmp_path):
    f = tmp_path / "claude_desktop_config.json"
    f.write_text("{ bozuk json", encoding="utf-8")
    s = claude_ayar.ekle(f, GIRIS_ANAHTAR, tmp_path / "v")
    assert s.durum == "bozuk" and s.metin and "kim_deneme" in s.metin
    assert f.read_text(encoding="utf-8") == "{ bozuk json"
    assert not list(tmp_path.glob("*yedek*"))
    f.write_text('{"mcpServers": []}', encoding="utf-8")
    assert claude_ayar.ekle(f, GIRIS_ANAHTAR, tmp_path / "v").durum == "bozuk"


def test_claude_ekle_dosya_yoksa_metin_verir(tmp_path):
    s = claude_ayar.ekle(None, GIRIS_ANAHTAR, tmp_path / "v")
    assert s.durum == "bulunamadi" and json.loads(s.metin)["mcpServers"]["kimlik-merkezi"]["command"]


def test_claude_dosyasini_bulma(tmp_path):
    env = {"APPDATA": str(tmp_path / "ap"), "LOCALAPPDATA": str(tmp_path / "lo")}
    assert claude_ayar.bul(env) is None
    f = tmp_path / "ap" / "Claude" / "claude_desktop_config.json"
    f.parent.mkdir(parents=True)
    f.write_text("{}")
    assert claude_ayar.bul(env) == f


def test_claude_ekle_uygulama_uzerinden_anahtar_hash_olarak_saklanir(kurulu, tmp_path):
    f = tmp_path / "claude_desktop_config.json"
    f.write_text("{}", encoding="utf-8")
    kurulu.uygulama._claude_yolu = lambda: f
    r = kurulu.api("claude_ekle", {})
    assert r["durum"] == "eklendi"
    anahtar = json.loads(f.read_text(encoding="utf-8"))["mcpServers"]["kimlik-merkezi"]["env"]["KIMLIK_ANAHTAR"]
    assert anahtar.startswith("kim_")
    # düz anahtar veritabanında yok; hassas kategoriler kapalı, diğerleri açık
    ham = (kurulu.ayarlar["veri_klasoru"] and open(f"{kurulu.ayarlar['veri_klasoru']}/kimlik.db", "rb").read())
    assert anahtar.encode() not in ham
    app = next(u for u in kurulu.api("erisim", {})["uygulamalar"] if u["ad"] == "Claude Desktop")
    kat = {i["kategori"] for i in app["izinler"]}
    assert "notlar" in kat and not ({"eposta", "mesaj", "konum"} & kat)


# ---------------------------------------------------------------- sağlık ve hata raporu
def test_saglik_ve_rapor(kurulu):
    s = kurulu.api("saglik", {})
    assert s["ok"], s["metin"]
    assert "FTS5" in s["metin"]
    r = kurulu.api("hata_raporu", {"adim": "deneme", "mesaj": "örnek hata"})["metin"]
    assert "Adım: deneme" in r and "örnek hata" in r and "tüm kontroller geçti" in r
    assert "Son " in r


def test_rapor_kullanici_yolunu_maskeler(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    r = hata_raporu.olustur("x", RuntimeError(f"yol {Path.home()}/gizli"), ayar_dizin=tmp_path)
    assert str(tmp_path) not in r and "%KULLANICI%" in r


def test_saglik_bozuk_klasor(tmp_path):
    s = saglik.denetle(tmp_path / "yok")
    assert not s["ok"]


def test_olustur_yeni_klasor_varsayilan_sifreli_saglayici_varsa(tmp_path, monkeypatch):
    """Sahte sağlayıcı (DPAPI yerine) varken yeni klasör şifreli kurulur ve okunur."""
    monkeypatch.setenv("KIMLIK_SAHTE_SAGLAYICI", "windows-testi")
    p = tmp_path / "sifreli"
    r = veri_klasoru.olustur(p)
    assert r["sifreli"] and "anahtar.json" in r["dosyalar"]
    assert b"SQLite format" not in (p / "kimlik.db").read_bytes()
    assert veri_klasoru.olustur(p)["mevcut_idi"]       # yeniden açılır


def test_claude_ekle_basarisizsa_aranan_yerleri_soyler_basariliysa_soylemez(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)   # gerçek Windows'ta kendi Claude kurulumu bulunmasın
    from kimlikwin.ayarlar import Ayarlar
    from kimlikwin.yonetici import Yonetici
    y = Yonetici(Ayarlar(tmp_path / "a"), Otomatik(None), claude_yolu=lambda: None)
    try:
        y.api("sihirbaz_tamamla", {"yol": str(tmp_path / "v"), "otomatik_baslat": False})
        r = y.api("claude_ekle", {})
        assert r["durum"] == "bulunamadi" and r["app_id"] and r["metin"]
        assert any("claude_desktop_config.json" in x and "Claude" in x for x in r["aranan"])
        assert str(tmp_path / "AppData") in r["aranan"][0]
        dosya = tmp_path / "c.json"
        dosya.write_text("{}", encoding="utf-8")
        y.uygulama._claude_yolu = lambda: dosya
        r2 = y.api("claude_ekle", {})
        assert r2["durum"] == "eklendi" and r2["aranan"] == []
    finally:
        y.kapat()


def test_ana_sayfa_ile_harita_toplami_farki_hassas_ve_gizlenenlerden_gelir(kurulu):
    """Arayüzdeki açıklamanın dayanağı: durum().event = diskteki TÜM kayıtlar; harita profil toplamı =
    kilitsiz kategoriler ve gizlenmemiş kayıtlar."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    import demo_veri
    u = kurulu.uygulama
    demo_veri.uret(u.hub, olcek=0.02)
    toplam = u.durum()["ozet"]["counts"]["event"]
    hassas = u.hub.query("SELECT COUNT(*) FROM events WHERE category IN ('eposta','mesaj','konum','sohbet','medya_meta')")[0][0]
    assert hassas > 0   # medya_meta hassas değil ama 'Ayaklar' (konum) bölgesine bağlı: o bölge kilitliyken sayılmaz
    assert u.harita()["profil"]["olay"] == toplam - hassas
    gizlenen_once = u.harita()["profil"]["olay"]
    u.hub.query("SELECT 1")  # salt okunur sorgu; gizleme API'si aşağıda
    ilk = u.ara("a", None, 1)["kayitlar"]
    if ilk:
        u.kayit_gizle(ilk[0]["id"])
        assert u.harita()["profil"]["olay"] == gizlenen_once - 1
        assert u.durum()["ozet"]["counts"]["event"] == toplam
