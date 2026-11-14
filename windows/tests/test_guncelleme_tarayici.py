"""GERÇEK TARAYICI (Playwright + Chromium) ile güncelleme arayüzü, sahte yerel GitHub'a karşı.
Çalışma koşulu test_tarayici.py ile aynıdır (node + playwright + Chromium; yoksa atlanır, CI'da KIMLIK_TARAYICI_ZORUNLU=1 ile kırmızı)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kimlikwin.ayarlar import Ayarlar
from kimlikwin.baslangic import Otomatik
from kimlikwin.guncelleme import Guncelleme
from kimlikwin.web import Sunucu
from kimlikwin.yonetici import Yonetici

sys.path.insert(0, str(Path(__file__).parent))
from sahte_github import SahteGithub  # noqa: E402
from test_tarayici import _atla, _node_ortami  # noqa: E402

BETIK = Path(__file__).parent / "tarayici" / "guncelleme.js"


class _AU:
    d = None

    def oku(self): return self.d
    def yaz(self, k): self.d = k
    def sil(self): self.d = None


@pytest.fixture(scope="module")
def duzen(tmp_path_factory):
    node = shutil.which("node")
    if not node:
        _atla("node kurulu değil")
    kok = tmp_path_factory.mktemp("gunc_tarayici")
    gh = SahteGithub()
    gh.kapi_esigi = None
    kayit: list[list[str]] = []
    g = Guncelleme(kok / "ayar" / "guncelleme", "0.1.1", gh.politika(zaman_asimi=1.0), baslatici=kayit.append)
    y = Yonetici(Ayarlar(kok / "ayar"), Otomatik(_AU()), secici=lambda t: None, claude_yolu=lambda: None, guncelleme=g)
    s = Sunucu(y, 0)
    s.baslat()
    ayar = kok / "ayar.json"
    ayar.write_text(json.dumps({"url": s.url, "sahte": gh.taban, "veri": str(kok / "veri")}), encoding="utf-8")
    try:
        p = subprocess.run([node, str(BETIK), str(ayar)], capture_output=True, text=True, timeout=240, env=_node_ortami())
    finally:
        s.durdur()
    if p.returncode == 77:
        gh.kapat()
        y.kapat()
        _atla("Playwright/Chromium yok: " + p.stderr.strip()[:200])
    assert p.returncode == 0, p.stderr[-2500:]
    sonuc = json.loads(p.stdout.strip().splitlines()[-1])
    yield sonuc, y, g, gh, kayit, kok
    y.kapat()
    gh.kapat()


def test_konsol_ve_bildirim_hatasi_yok(duzen):
    s = duzen[0]
    assert s["hatalar"] == [] and s["bildirim_hatalari"] == []


def test_sihirbaz_acilista_denetimi_acik_ve_acikca_yazili(duzen):
    sh = duzen[0]["sihirbaz"]
    assert sh["isaretli"] is True                                   # kullanıcı kararı: varsayılan AÇIK
    assert "Açılışta yeni sürüm olup olmadığını denetle" in sh["metin"] and "varsayılan: açık" in sh["metin"]
    assert "GitHub" in sh["metin"] and "internete çıkan tek yolu" in sh["metin"] and "indirme ve kurulum yalnız sizin onayınızla" in sh["metin"]
    assert "internete hiç bağlanmaz" in sh["metin"]                 # kapatınca ne olacağı da yazılı
    assert "Açılışta güncelleme denetimi: açık" in sh["ozet"]
    assert sh["sonra_kutu_bos"] is True


def test_ayarlar_karti_acik_yazar_ve_kapatilabilir(duzen):
    a = duzen[0]["ayar"]
    assert a["otomatik"] is True and a["onsurum"] is True
    assert "Açılışta yeni sürümü denetle (varsayılan: açık)" in a["kart"] and "Güncellemeleri denetle" in a["kart"]
    assert "TEK yoludur" in a["kart"] and "sizin onayınızla" in a["kart"]
    assert a["kapatilinca"] is False and a["acilinca"] is True
    assert duzen[0]["once"]["toplam"] == 0                          # sihirbaz/ayar gezintisi hiç ağ isteği yapmadı


def test_yeni_surum_sorusu_ve_onaysiz_indirme_yok(duzen):
    s = duzen[0]["soru"]
    assert "Yeni sürüm 0.9.0" in s["baslik"] and "indirmek ister misin?" in s["baslik"] and s["indir_var"]
    assert "yalnız siz onaylayınca başlar" in s["kutu"]
    assert s["sayac"]["exe"] == 0 and s["sayac"]["ozet"] == 0       # soru sorulurken bile indirme/özet isteği yok
    assert s["gizlendi"] is True


def test_ilerleme_cubugu_mb_yuzde_kalan_sure_duraklat_iptal(duzen):
    i = duzen[0]["ilerleme"]
    assert i["duraklat_var"] and i["iptal_var"] and i["deger"] > 5
    import re
    assert re.search(r"\d+,\d / \d+,\d MB — %\d+,\d — kalan süre: ", i["metin"]), i["metin"]


def test_iptal_yarim_dosyayi_siler_ve_soru_geri_gelir(duzen):
    assert "iptal edildi" in duzen[0]["iptal"]["kutu"] and duzen[0]["iptal"]["ilerleme_yok"] is True


def test_duraklat_ilerlemeyi_durdurur_devam_range_ile_surer(duzen):
    sonuc, y, g, gh, kayit, kok = duzen
    d = sonuc["duraklat"]
    assert "duraklatıldı" in d["metin"] and d["v1"] == d["v2"]       # duraklayınca çubuk ilerlemez
    aralik = sonuc["devam"]["sayac"]["aralikli"]
    assert aralik and all(a.startswith("bytes=") and int(a[6:-1]) > 0 for a in aralik)       # Range ile devam etti
    exe = gh.exe_istekleri()
    assert any("range" in e["basliklar"] for e in exe)


def test_hash_uyusmazligi_hata_gosterir_ve_dosya_kalmaz(duzen):
    h = duzen[0]["hash"]
    assert "Güncelleme tamamlanamadı" in h["baslik"] and "Doğrulama başarısız" in h["hata"] and "silindi" in h["hata"]
    assert h["kur_var"] is False


def test_ikinci_onay_ve_kurulum_kapanistan_sonra_baslar(duzen):
    sonuc, y, g, gh, kayit, kok = duzen
    assert "Şimdi kurmak ister misin?" in sonuc["devam"]["kutu"] and "SHA256SUMS.txt ile doğrulandı" in sonuc["devam"]["kutu"]
    assert sonuc["sonra_gizlendi"] is True and sonuc["mobil"]["tasma"] <= 0
    assert "Kurulum başlatılıyor" in sonuc["kur"]["baslik"]
    assert y.cikis_istegi is True                                   # arayüzdeki ikinci onay uygulamayı kapatmaya başlattı
    assert kayit == [], "kurulum programı uygulama kapanmadan başlatılmamalı"
    y.kapat()
    assert y.cikista_kurulum() is True
    (argv,) = kayit
    assert argv[0].endswith("KimlikMerkezi-Kurulum-v0.9.0.exe") and "/VERYSILENT" in argv and "/GUNCELLEME=1" in argv
    veri = kok / "veri"
    assert not any(str(veri) in a for a in argv)
    assert (veri / "kimlik.db").is_file()                           # veri klasörü yerinde


def test_indirilen_dosya_yalniz_uygulama_klasorunde(duzen):
    sonuc, y, g, gh, kayit, kok = duzen
    assert sorted(p.name for p in g.dizin.iterdir()) == ["KimlikMerkezi-Kurulum-v0.9.0.exe"]
    assert g.dizin == kok / "ayar" / "guncelleme"


@pytest.mark.parametrize("secim", ["acik", "kapat"])
def test_eski_kurulumda_bilgi_penceresi_otomatik_denetimden_once(tmp_path, secim):
    """0.1.1'den gelen kullanıcı 'ağa hiç çıkmaz' sözüyle kurmuştu: açılışta bir kez açıkça bilgilendirilir,
    seçmeden ağ isteği olmaz; 'Kapat' derse hiç bağlanılmaz."""
    node = shutil.which("node")
    if not node:
        _atla("node kurulu değil")
    gh = SahteGithub()
    g = Guncelleme(tmp_path / "ayar" / "guncelleme", "0.1.1", gh.politika(), baslatici=lambda a: None)
    y = Yonetici(Ayarlar(tmp_path / "ayar"), Otomatik(_AU()), secici=lambda t: None, claude_yolu=lambda: None, guncelleme=g)
    y.api("sihirbaz_tamamla", {"yol": str(tmp_path / "veri"), "otomatik_baslat": False})
    y.ayarlar.guncelle(guncelleme_bilgi_goruldu=False, guncelleme_otomatik=True)       # eski kurulum durumu
    y.acilista_guncelleme()                                                             # açılış: bilgi görülmeden denetim YOK
    s = Sunucu(y, 0)
    s.baslat()
    ayar = tmp_path / "ayar.json"
    ayar.write_text(json.dumps({"url": s.url, "sahte": gh.taban, "mod": "bilgi", "secim": secim}), encoding="utf-8")
    try:
        p = subprocess.run([node, str(BETIK), str(ayar)], capture_output=True, text=True, timeout=120, env=_node_ortami())
    finally:
        s.durdur()
        y.kapat()
    if p.returncode == 77:
        gh.kapat()
        _atla("Playwright/Chromium yok: " + p.stderr.strip()[:200])
    assert p.returncode == 0, p.stderr[-2000:]
    r = json.loads(p.stdout.strip().splitlines()[-1])
    gh.kapat()
    assert r["hatalar"] == []
    b = r["bilgi"]
    assert "GitHub" in b["metin"] and "yalnız sizin onayınızla" in b["metin"] and "internete hiç bağlanmaz" in b["metin"]
    assert b["sayac_once"]["toplam"] == 0 and b["pencere_kapandi"] is True
    assert b["ayar"] is (secim == "acik")
    assert y.ayarlar["guncelleme_bilgi_goruldu"] is True
    if secim == "kapat":
        assert b["sayac_sonra"]["toplam"] == 0                                          # kapatınca hiç bağlanılmadı
