"""Güncelleme ayarları ve API uçları (Yonetici): varsayılan AÇIK ama kapatılabilir; denetim yalnız kullanıcı bilgisini
gördükten sonra kendiliğinden çalışır; indirme/kurulum yalnız açık onayla; kurulum programı yalnız kapanıştan sonra."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from kimlikwin.ayarlar import Ayarlar, VARSAYILAN
from kimlikwin.baslangic import Otomatik
from kimlikwin.cekirdek import IslemHatasi
from kimlikwin.guncelleme import Guncelleme
from kimlikwin.yonetici import Yonetici

sys.path.insert(0, str(Path(__file__).parent))
from sahte_github import SahteGithub  # noqa: E402


class SahteArkaUc:
    d = None

    def oku(self): return self.d
    def yaz(self, k): self.d = k
    def sil(self): self.d = None


@pytest.fixture
def gh():
    s = SahteGithub()
    yield s
    s.kapat()


@pytest.fixture
def kur(tmp_path, gh):
    """(yonetici, baslatilanlar). Yonetici gerçek ayar dosyasıyla, ağ ise sahte yerel sunucuyla."""
    acilan = []

    def yap(**ayar):
        a = Ayarlar(tmp_path / "ayar")
        if ayar:
            a.guncelle(**ayar)
        g = Guncelleme(tmp_path / "ayar" / "guncelleme", "0.1.1", gh.politika(), baslatici=acilan.append)
        return Yonetici(a, Otomatik(SahteArkaUc()), secici=lambda t: None, claude_yolu=lambda: None, guncelleme=g)
    yap.acilan = acilan
    yield yap


def kurulu(y, veri, **kw):
    y.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False, **kw})


def bekle(kosul, zaman=10.0):
    bitis = time.monotonic() + zaman
    while time.monotonic() < bitis:
        if kosul():
            return True
        time.sleep(0.01)
    return False


def test_varsayilan_acik_ama_ayarlardan_kapatilabilir(kur, veri):
    assert VARSAYILAN["guncelleme_otomatik"] is True            # kullanıcı kararı: varsayılan AÇIK
    y = kur()
    kurulu(y, veri)
    assert y.api("ayarlar", {})["guncelleme_otomatik"] is True
    r = y.api("ayar_yaz", {"guncelleme_otomatik": False})
    assert r["guncelleme_otomatik"] is False
    assert Ayarlar(y.ayarlar.dizin)["guncelleme_otomatik"] is False       # kalıcı
    assert y.api("ayar_yaz", {"guncelleme_otomatik": True})["guncelleme_otomatik"] is True
    y.kapat()


def test_sihirbazda_secim_kaydedilir(kur, veri):
    y = kur()
    kurulu(y, veri, guncelleme_otomatik=False)
    assert y.ayarlar["guncelleme_otomatik"] is False and y.ayarlar["guncelleme_bilgi_goruldu"] is True
    y.kapat()


def test_sihirbaz_tamamlanmadan_ag_yok(kur, gh):
    y = kur()
    y.acilista_guncelleme()
    time.sleep(0.2)
    assert gh.istekler == [] and y.guncelleme.durum()["durum"] == "bosta"


def test_acilista_denetler_ayar_aciksa(kur, gh, veri):
    y = kur()
    kurulu(y, veri)
    y.acilista_guncelleme()
    assert y.guncelleme.bekle_durum("yeni")
    assert y.api("guncelleme_durum", {})["surum"] == "0.9.0" and y.api("guncelleme_durum", {})["otomatik"] is True
    assert gh.exe_istekleri() == []                                        # yalnız sürüm listesi soruldu
    y.kapat()


def test_acilista_ayar_kapaliysa_hic_baglanmaz(kur, gh, veri):
    y = kur()
    kurulu(y, veri, guncelleme_otomatik=False)
    y.acilista_guncelleme()
    time.sleep(0.3)
    assert gh.istekler == []
    y.kapat()


def test_eski_kurulumda_bilgi_gosterilmeden_otomatik_denetim_yok(kur, gh, veri, tmp_path):
    """0.1.1'den gelen kullanıcı 'ağa hiç çıkmaz' sözüyle kurmuştu: bilgilendirilmeden bağlanılmaz."""
    y = kur()
    kurulu(y, veri)
    y.ayarlar.guncelle(guncelleme_bilgi_goruldu=False)                       # eski kurulum durumu
    assert y.api("acilis", {})["guncelleme_bilgi_gerekli"] is True
    y.acilista_guncelleme()
    time.sleep(0.3)
    assert gh.istekler == []
    r = y.api("guncelleme_bilgi", {"otomatik": True})                       # kullanıcı "açık kalsın" dedi
    assert r["otomatik"] is True and y.api("acilis", {})["guncelleme_bilgi_gerekli"] is False
    assert y.guncelleme.bekle_durum("yeni")
    y.kapat()


def test_bilgi_kapat_denilirse_ag_yok(kur, gh, veri):
    y = kur()
    kurulu(y, veri)
    y.ayarlar.guncelle(guncelleme_bilgi_goruldu=False)
    y.api("guncelleme_bilgi", {"otomatik": False})
    y.acilista_guncelleme()
    time.sleep(0.2)
    assert gh.istekler == [] and y.ayarlar["guncelleme_otomatik"] is False
    y.kapat()


def test_dugme_ayar_kapali_olsa_da_denetler(kur, gh, veri):
    y = kur()
    kurulu(y, veri, guncelleme_otomatik=False)
    y.api("guncelleme_denetle", {})
    assert y.guncelleme.bekle_durum("yeni")
    y.kapat()


def test_onsurum_ayari_denetimi_etkiler(kur, gh, veri):
    y = kur()
    kurulu(y, veri)
    y.api("ayar_yaz", {"guncelleme_onsurum": False})
    y.api("guncelleme_denetle", {})
    assert y.guncelleme.bekle_durum("guncel")                               # sahte sürüm 'prerelease'
    y.guncelleme.durum_adi = "bosta"
    y.api("ayar_yaz", {"guncelleme_onsurum": True})
    y.api("guncelleme_denetle", {})
    assert y.guncelleme.bekle_durum("yeni")
    y.kapat()


def test_api_indir_onaysiz_reddedilir(kur, gh, veri):
    y = kur()
    kurulu(y, veri)
    y.api("guncelleme_denetle", {})
    assert y.guncelleme.bekle_durum("yeni")
    for girdi in ({}, {"onay": False}, {"onay": "true"}, {"onay": 1}):
        with pytest.raises(IslemHatasi):
            y.api("guncelleme_indir", girdi)
    with pytest.raises(IslemHatasi):
        y.api("guncelleme_kur", {"onay": True})                             # indirilmedi
    assert gh.exe_istekleri() == [] and not y.cikis_istegi
    y.kapat()


def test_indir_kur_akisi_iki_onay_ve_gec_baslatma(kur, gh, veri):
    y = kur()
    kurulu(y, veri)
    y.api("guncelleme_denetle", {})
    assert y.guncelleme.bekle_durum("yeni")
    y.api("guncelleme_indir", {"onay": True})
    assert y.guncelleme.bekle_durum("hazir")
    assert not kur.acilan and not y.cikis_istegi                             # indirme = kurulum DEĞİL
    with pytest.raises(IslemHatasi):
        y.api("guncelleme_kur", {"onay": False})
    d = y.api("guncelleme_kur", {"onay": True})
    assert d["durum"] == "kuruluyor" and y.cikis_istegi is True              # uygulama kapanmaya başlar
    assert kur.acilan == [], "kurulum programı uygulama kapanmadan başlamamalı"
    y.kapat()                                                                # (calistir() finally bloğu)
    assert y.cikista_kurulum() is True
    assert len(kur.acilan) == 1 and "/VERYSILENT" in kur.acilan[0] and "/GUNCELLEME=1" in kur.acilan[0]
    assert "/TASKS=!otobaslat" in kur.acilan[0]                              # girişte başlatma kapalıydı: kurulum açmaz


def test_kurulum_veri_klasorune_dokunmaz(kur, gh, veri):
    y = kur()
    kurulu(y, veri)
    y.kapat()

    def iz():
        return sorted((p.relative_to(veri).as_posix(), p.stat().st_size, p.stat().st_mtime_ns) for p in veri.rglob("*"))
    once = iz()
    y.api("guncelleme_denetle", {})
    assert y.guncelleme.bekle_durum("yeni")
    y.api("guncelleme_indir", {"onay": True})
    assert y.guncelleme.bekle_durum("hazir")
    y.api("guncelleme_kur", {"onay": True})
    y.cikista_kurulum()
    assert iz() == once                                                      # ne dosya eklendi/silindi ne değişti
    for a in kur.acilan[0]:
        assert str(veri) not in a                                            # komut veri klasörünü hiç anmaz
    assert Path(y.guncelleme.dizin).resolve() != veri.resolve() and veri.resolve() not in Path(y.guncelleme.dizin).resolve().parents


def test_ortam_anahtari_kapaliysa_dugme_de_baglanmaz(kur, gh, veri, monkeypatch):
    monkeypatch.setenv("KIMLIK_GUNCELLEME", "kapali")
    y = kur()
    kurulu(y, veri)
    y.acilista_guncelleme()
    d = y.api("guncelleme_denetle", {})
    assert d["durum"] == "kapali" and d["kapali"] is True and gh.istekler == []
    y.kapat()


def test_uygulama_politika_vermez():
    """Yonetici varsayılan Guncelleme'yi ÜRETİM politikasıyla kurar (test politikası yalnız dışarıdan enjekte edilir)."""
    import tempfile
    from kimlikwin import guncelleme as G
    with tempfile.TemporaryDirectory() as d:
        y = Yonetici(Ayarlar(Path(d)), Otomatik(SahteArkaUc()), secici=lambda t: None, claude_yolu=lambda: None)
        assert y.guncelleme.politika is G.URETIM and y.guncelleme.dizin == Path(d) / "guncelleme"
