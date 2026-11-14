"""Güncelleme modülü (guncelleme.py): sahte yerel GitHub ile denetim, onaysız indirmeme, ilerleme, duraklat/devam,
hash uyuşmazlığı, sürüm karşılaştırma, iptal, yönlendirme/ana makine beyaz listesi, kurulum komutu.
Gerçek GitHub'a hiçbir test çıkmaz (ag_koruma.py engeller; ayrıca bir test bunu kanıtlar)."""
from __future__ import annotations

import os
import socket
import sys
import time
from collections import deque
from pathlib import Path

import pytest

import ag_koruma
from kimlikwin import guncelleme as G
from kimlikwin.guncelleme import Guncelleme, GuncellemeHatasi, OnayGerekli

sys.path.insert(0, str(Path(__file__).parent))
from sahte_github import SahteGithub  # noqa: E402

MB = 1024 * 1024


@pytest.fixture
def gh():
    s = SahteGithub()
    yield s
    s.kapat()


@pytest.fixture
def dizin(tmp_path):
    return tmp_path / "guncelleme"


def yap(gh, dizin, mevcut="0.1.1", **pol):
    kayit = []
    g = Guncelleme(dizin, mevcut, gh.politika(**pol), baslatici=kayit.append)
    g.kayit = kayit
    return g


def bekle(kosul, zaman=10.0):
    bitis = time.monotonic() + zaman
    while time.monotonic() < bitis:
        if kosul():
            return True
        time.sleep(0.01)
    return False


def dosyalar(dizin):
    return sorted(p.name for p in dizin.iterdir()) if dizin.exists() else []


# ------------------------------------------------------------------ sürüm karşılaştırma

@pytest.mark.parametrize("kucuk,buyuk", [
    ("0.1.1", "0.1.2"), ("0.1.2", "0.2.0"), ("0.2.0", "1.0.0"), ("0.9.0", "0.10.0"), ("v0.1.1", "v0.1.2"),
    ("0.2.0-rc1", "0.2.0"), ("0.2.0-rc.2", "0.2.0-rc.10"), ("0.2.0-alpha", "0.2.0-beta"),
    ("0.2.0-1", "0.2.0-alpha"), ("0.2.0-rc", "0.2.0-rc.1"), ("0.1.9", "0.2.0-rc1"),
])
def test_surum_siralamasi(kucuk, buyuk):
    a, b = G.surum_coz(kucuk), G.surum_coz(buyuk)
    assert a < b and b > a and not (b < a) and a <= b and not (a >= b)


def test_surum_esit_ve_v_oneki():
    assert G.surum_coz("v0.1.1") == G.surum_coz("0.1.1")
    assert not (G.surum_coz("0.1.1") < G.surum_coz("v0.1.1"))


@pytest.mark.parametrize("kotu", ["", "abc", "1.2", "1.2.3.4", "v1.2.3+build", "1.2.3-", "1.2.x", None, 5, "1..2"])
def test_gecersiz_surum_none(kotu):
    assert G.surum_coz(kotu) is None


def _surum(tag, prerelease=True, draft=False, ad=None, url=None, boyut=1000, ozet=True, taban="https://github.com"):
    onek = f"{taban}/avsessisozx/kimlik-merkezi/releases/download/{tag}/"
    ad = ad or f"KimlikMerkezi-Kurulum-{tag}.exe"
    assets = [{"name": ad, "size": boyut, "browser_download_url": url or onek + ad}]
    if ozet:
        assets.append({"name": "SHA256SUMS.txt", "browser_download_url": onek + "SHA256SUMS.txt"})
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft, "assets": assets}


def test_en_yeni_aday_secimi():
    liste = [_surum("v0.1.1"), _surum("v0.1.2"), _surum("v0.2.0"), _surum("v0.1.9")]
    assert G.en_yeni_aday(liste, "0.1.1", True)["surum"] == "0.2.0"
    assert G.en_yeni_aday(liste, "0.2.0", True) is None          # aynı sürüm: yeni yok
    assert G.en_yeni_aday(liste, "0.3.0", True) is None          # daha yeni kurulu: yeni yok


def test_taslak_ve_onsurum_filtresi():
    liste = [_surum("v0.2.0", prerelease=True), _surum("v0.1.5", prerelease=False), _surum("v0.3.0", draft=True, prerelease=False)]
    assert G.en_yeni_aday(liste, "0.1.1", True)["surum"] == "0.2.0"          # taslak asla
    assert G.en_yeni_aday(liste, "0.1.1", False)["surum"] == "0.1.5"         # ön sürüm işareti dışlanır
    assert G.en_yeni_aday([_surum("v0.2.0-rc1", prerelease=False)], "0.1.1", False) is None   # etiketteki önsürüm de
    assert G.en_yeni_aday([_surum("v0.2.0-rc1", prerelease=False)], "0.1.1", True)["onsurum"] is True


def test_onsurumden_kararliya_guncelleme():
    assert G.en_yeni_aday([_surum("v0.2.0", prerelease=False)], "0.2.0-rc1", False)["surum"] == "0.2.0"
    assert G.en_yeni_aday([_surum("v0.2.0-rc1")], "0.2.0", True) is None


@pytest.mark.parametrize("degisiklik", [
    dict(ad="KimlikMerkezi-Kurulum-v0.2.0.exe", url="https://evil.example/avsessisozx/kimlik-merkezi/releases/download/v0.2.0/KimlikMerkezi-Kurulum-v0.2.0.exe"),
    dict(url="https://github.com/baska/depo/releases/download/v0.2.0/KimlikMerkezi-Kurulum-v0.2.0.exe"),
    dict(url="http://github.com/avsessisozx/kimlik-merkezi/releases/download/v0.2.0/KimlikMerkezi-Kurulum-v0.2.0.exe"),
    dict(ad="..\\..\\evil.exe"), dict(ad="../x.exe"), dict(ad="KimlikMerkezi-Kurulum-v0.2.0.exe.bat"),
    dict(ad="KimlikMerkezi-Kurulum-v0.2.0\\..\\x.exe"), dict(ad="KimlikMerkezi-Kurulum-v9.9.9.exe"),
    dict(boyut=0), dict(boyut=10 ** 12), dict(boyut="500"), dict(boyut=True), dict(ozet=False),
])
def test_guvensiz_varlik_adaylari_reddedilir(degisiklik):
    assert G.en_yeni_aday([_surum("v0.2.0", **degisiklik)], "0.1.1", True) is None


def test_ozet_ayristirma():
    h = "ab" * 32
    assert G.ozet_coz(f"{h}  KimlikMerkezi-Kurulum-v1.exe\n{'cd' * 32}  baska\n", "KimlikMerkezi-Kurulum-v1.exe") == h
    assert G.ozet_coz(f"{h.upper()} *KimlikMerkezi-Kurulum-v1.exe\r\n", "KimlikMerkezi-Kurulum-v1.exe") == h
    assert G.ozet_coz(f"{h}  baska.exe\n", "KimlikMerkezi-Kurulum-v1.exe") is None
    assert G.ozet_coz(f"{h[:60]}  KimlikMerkezi-Kurulum-v1.exe\n", "KimlikMerkezi-Kurulum-v1.exe") is None
    assert G.ozet_coz("", "x") is None


# ------------------------------------------------------------------ ağ politikası

@pytest.mark.parametrize("url", [
    "https://api.github.com/repos/x/y/releases", "https://github.com/a/b", "https://objects.githubusercontent.com/x?y=1",
    "https://release-assets.githubusercontent.com/z", "https://GitHub.com/a",
])
def test_uretim_politikasi_kabul(url):
    G.adres_denetle(url, G.URETIM)


@pytest.mark.parametrize("url", [
    "http://api.github.com/x", "https://example.com/x", "https://github.com.evil.example/x", "https://evil.example/github.com",
    "https://user:pw@github.com/x", "https://github.com:8443/x", "file:///etc/passwd", "ftp://github.com/x",
    "https://127.0.0.1/x", "https://localhost/x", "//github.com/x", "https://githubusercontent.com/x", "data:text/plain,x",
])
def test_uretim_politikasi_red(url):
    with pytest.raises(GuncellemeHatasi):
        G.adres_denetle(url, G.URETIM)


def test_uretim_politikasi_degismez_ve_dar():
    assert G.URETIM.https_zorunlu and G.URETIM.proxy_kullan
    assert G.URETIM.izinli == ("api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")
    assert G.KULLANICI_AJANI == "KimlikMerkezi-guncelleme"
    with pytest.raises(Exception):
        G.URETIM.https_zorunlu = False        # dondurulmuş


def test_testler_gercek_github_a_cikamaz(tmp_path):
    """Üretim politikasıyla yapılan istek (testte) ağ korumasına takılır: testler hiçbir zaman GitHub'a gitmez."""
    if not ag_koruma._orijinal:
        pytest.skip("ağ koruması kapalı: gerçek ağa çıkmamak için atlandı")
    import dataclasses
    # Vekil kapalı: ortamda HTTPS_PROXY varsa istek yerel vekile gider ve ağ korumasının görmediği yoldan dışarı çıkardı.
    pol = dataclasses.replace(G.URETIM, proxy_kullan=False)
    g = Guncelleme(tmp_path / "g", "0.1.1", pol, baslatici=lambda a: None)
    g.denetle(arka_planda=False)
    assert g.durum()["durum"] == "hata"
    assert ag_koruma.IHLALLER, "ağ koruması üretim adresine çıkışı engellemedi"
    assert any("api.github.com" in i for i in ag_koruma.IHLALLER)
    ag_koruma.IHLALLER.clear()                # bu testin kendisi başarısız olmasın


# ------------------------------------------------------------------ denetim

def test_denetim_yeni_surum_bulur_ve_hicbir_sey_indirmez(gh, dizin):
    g = yap(gh, dizin)
    d = g.denetle(arka_planda=False)
    assert d["durum"] == "yeni" and d["surum"] == "0.9.0" and d["boyut"] == gh.boyut and d["onsurum"] is True
    assert d["dosya_adi"] == "KimlikMerkezi-Kurulum-v0.9.0.exe"
    assert [i["yol"].split("?")[0] for i in gh.istekler] == ["/repos/avsessisozx/kimlik-merkezi/releases"]
    assert not dizin.exists() or dosyalar(dizin) == []


def test_denetim_guncel(gh, dizin):
    gh.surumler = [{"etiket": "v0.1.1"}, {"etiket": "v0.1.0"}]
    d = yap(gh, dizin).denetle(arka_planda=False)
    assert d["durum"] == "guncel" and d["surum"] is None and d["son_denetim"].endswith("Z")


def test_denetim_istek_baslik_ve_icerigi_genel(gh, dizin):
    """Gönderilen her şey genel: sabit kullanıcı ajanı, çerez/yetki/Referer yok; sürüm/makine/kullanıcı bilgisi yok."""
    yap(gh, dizin, mevcut="0.1.1").denetle(arka_planda=False)
    (i,) = gh.istekler
    b = i["basliklar"]
    assert b["user-agent"] == "KimlikMerkezi-guncelleme"
    assert set(b) <= {"host", "user-agent", "accept", "x-github-api-version", "connection", "accept-encoding"}, set(b)
    ham = (i["yol"] + repr(b)).lower()
    for gizli in ("0.1.1", socket.gethostname().lower(), os.environ.get("USER", "u" * 9).lower(), str(Path.home()).lower()):
        assert gizli not in ham.replace("127.0.0.1", ""), gizli


def test_denetim_gecersiz_json(gh, dizin):
    gh.ham_liste = b"bu json degil"
    d = yap(gh, dizin).denetle(arka_planda=False)
    assert d["durum"] == "hata" and "okunamadı" in d["mesaj"]


def test_denetim_baglanti_yok(gh, dizin):
    d = Guncelleme(dizin, "0.1.1", gh.politika(api_taban="http://127.0.0.1:9")).denetle(arka_planda=False)
    assert d["durum"] == "hata" and "bağlanılamadı" in d["mesaj"]


def test_denetim_http_hatasi(gh, dizin):
    d = Guncelleme(dizin, "0.1.1", gh.politika(api_taban=gh.taban + "/yok")).denetle(arka_planda=False)
    assert d["durum"] == "hata" and "404" in d["mesaj"]


def test_kapatma_anahtari_agi_tamamen_kapatir(gh, dizin, monkeypatch):
    monkeypatch.setenv("KIMLIK_GUNCELLEME", "kapali")
    g = yap(gh, dizin)
    d = g.denetle(arka_planda=False)
    assert d["durum"] == "kapali" and d["kapali"] is True
    assert gh.istekler == []
    g.aday = {"dosya_adi": "KimlikMerkezi-Kurulum-v0.9.0.exe", "boyut": 5, "indirme_url": gh.taban + "/x", "ozet_url": gh.taban + "/y"}
    g.durum_adi = "yeni"
    d = g.indir(onay=True, arka_planda=False)
    assert d["durum"] == "hata" and gh.istekler == []


# ------------------------------------------------------------------ onay şartı

def test_onaysiz_indirme_olmaz(gh, dizin):
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    for onay in (False, None, 1, "evet", "true"):
        with pytest.raises(OnayGerekli):
            g.indir(onay=onay)             # type: ignore[arg-type]
    with pytest.raises(TypeError):
        g.indir()                          # type: ignore[call-arg]
    with pytest.raises(TypeError):
        g.indir(True)                      # type: ignore[misc]   # onay yalnız anahtar sözcükle
    assert g.durum()["durum"] == "yeni"
    assert gh.exe_istekleri() == [] and all("SHA256SUMS" not in i["yol"] for i in gh.istekler)
    assert not dizin.exists() or dosyalar(dizin) == []


def test_denetimsiz_indirme_olmaz(gh, dizin):
    with pytest.raises(GuncellemeHatasi):
        yap(gh, dizin).indir(onay=True)
    assert gh.istekler == []


def test_onaysiz_kurulum_olmaz(gh, dizin):
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    with pytest.raises(OnayGerekli):
        g.kur(onay=False, otomatik_baslat=True)
    with pytest.raises(GuncellemeHatasi):
        g.kur(onay=True, otomatik_baslat=True)         # henüz indirilmedi/doğrulanmadı
    assert g.kayit == [] and g.kurulumu_baslat() is False


# ------------------------------------------------------------------ indirme, doğrulama

def test_indirme_dogrulama_ve_hazir(gh, dizin):
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    d = g.indir(onay=True, arka_planda=False)
    assert d["durum"] == "hazir" and d["yuzde"] == 100.0 and d["indirilen"] == d["toplam"] == gh.boyut
    ad = "KimlikMerkezi-Kurulum-v0.9.0.exe"
    assert dosyalar(dizin) == [ad]                                  # .part kalmadı
    assert (dizin / ad).read_bytes() == gh.icerik("v0.9.0")
    yollar = [i["yol"] for i in gh.istekler]
    assert yollar.index("/avsessisozx/kimlik-merkezi/releases/download/v0.9.0/SHA256SUMS.txt") < \
        yollar.index("/avsessisozx/kimlik-merkezi/releases/download/v0.9.0/" + ad)
    for i in gh.istekler:
        assert i["basliklar"]["user-agent"] == "KimlikMerkezi-guncelleme"
    assert g.kayit == []                                            # indirme kurulum BAŞLATMAZ


def test_arkaplan_indirme_ilerleme_artarak_gider(gh, dizin):
    gh.kapi_esigi = 1 * MB
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    g.indir(onay=True)
    assert bekle(lambda: g.durum()["indirilen"] >= 1 * MB)
    d = g.durum()
    assert d["durum"] == "indiriliyor" and d["toplam"] == gh.boyut and 0 < d["yuzde"] < 100
    assert d["yuzde"] == pytest.approx(100 * d["indirilen"] / gh.boyut, abs=0.1)
    gh.kapi.set()
    assert g.bekle_durum("hazir")
    assert g.durum()["yuzde"] == 100.0


def test_hiz_ve_kalan_sure_hesabi(gh, dizin):
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    g.durum_adi, g.toplam, g.indirilen = "indiriliyor", 11_000, 1_000
    g._ornekler = deque([(10.0, 0), (11.0, 1_000)])
    d = g.durum()
    assert d["hiz"] == 1000 and d["kalan_sn"] == 10 and d["yuzde"] == 9.1
    g._ornekler = deque([(10.0, 0)])
    assert g.durum()["kalan_sn"] is None                            # örnek yok: tahmin uydurulmaz
    g.durum_adi = "duraklatildi"
    assert g.durum()["hiz"] == 0 and g.durum()["kalan_sn"] is None


def test_duraklat_ve_range_ile_devam(gh, dizin):
    gh.kapi_esigi = 1 * MB
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    g.indir(onay=True)
    assert bekle(lambda: g.durum()["indirilen"] >= 1 * MB)
    assert g.duraklat()["durum"] == "duraklatildi"
    g._is.join(5)
    assert not g._is.is_alive()
    parca = dizin / "KimlikMerkezi-Kurulum-v0.9.0.exe.part"
    n = parca.stat().st_size
    assert 0 < n < gh.boyut and n == g.durum()["indirilen"]
    gh.kapi.set()
    time.sleep(0.2)
    assert g.durum()["durum"] == "duraklatildi" and parca.stat().st_size == n      # duraklayınca veri akmaz
    g.surdur()
    assert g.bekle_durum("hazir")
    exe = gh.exe_istekleri()
    assert len(exe) == 2 and "range" not in exe[0]["basliklar"] and exe[1]["basliklar"]["range"] == f"bytes={n}-"
    assert (dizin / "KimlikMerkezi-Kurulum-v0.9.0.exe").read_bytes() == gh.icerik("v0.9.0")
    assert dosyalar(dizin) == ["KimlikMerkezi-Kurulum-v0.9.0.exe"]


def test_sunucu_range_yok_sayarsa_bastan_indirir(gh, dizin):
    gh.range_destek = False
    gh.kapi_esigi = 1 * MB
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    g.indir(onay=True)
    assert bekle(lambda: g.durum()["indirilen"] >= 1 * MB)
    g.duraklat()
    g._is.join(5)
    gh.kapi.set()
    g.surdur()
    assert g.bekle_durum("hazir")
    assert (dizin / "KimlikMerkezi-Kurulum-v0.9.0.exe").read_bytes() == gh.icerik("v0.9.0")      # bozuk birleştirme yok


def test_baglanti_kopunca_otomatik_range_ile_surer(gh, dizin):
    gh.kes_esigi = 1 * MB
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    assert g.indir(onay=True, arka_planda=False)["durum"] == "hazir"
    exe = gh.exe_istekleri()
    assert len(exe) == 2 and exe[1]["basliklar"]["range"].startswith("bytes=") and not exe[1]["basliklar"]["range"].startswith("bytes=0")
    assert (dizin / "KimlikMerkezi-Kurulum-v0.9.0.exe").read_bytes() == gh.icerik("v0.9.0")


def test_hash_uyusmazligi_dosyayi_siler_ve_hata_gosterir(gh, dizin):
    gh.bozuk_ozet = True
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    d = g.indir(onay=True, arka_planda=False)
    assert d["durum"] == "hata" and "Doğrulama başarısız" in d["mesaj"] and "silindi" in d["mesaj"]
    assert g.hata_asama == "dogrulama" and g.exe_yolu is None
    assert dosyalar(dizin) == []                                    # ne .exe ne .part
    with pytest.raises(GuncellemeHatasi):
        g.kur(onay=True, otomatik_baslat=True)
    assert g.kayit == []
    gh.bozuk_ozet = False                                           # sunucu düzelince yeniden denenebilir
    assert g.indir(onay=True, arka_planda=False)["durum"] == "hazir"


def test_ozet_dosyasinda_satir_yoksa_buyuk_dosya_indirilmez(gh, dizin):
    gh.ozet_yok = True
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    d = g.indir(onay=True, arka_planda=False)
    assert d["durum"] == "hata" and "özet bulunamadı" in d["mesaj"]
    assert gh.exe_istekleri() == [] and dosyalar(dizin) == []


def test_iptal_calisirken_dosyayi_siler(gh, dizin):
    gh.kapi_esigi = 1 * MB
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    g.indir(onay=True)
    assert bekle(lambda: g.durum()["indirilen"] >= 1 * MB)
    g.iptal()
    assert g.bekle_durum("iptal")
    assert dosyalar(dizin) == [] and g.durum()["indirilen"] == 0
    assert g.kayit == []
    with pytest.raises(GuncellemeHatasi):
        g.surdur()                                                   # iptal edilen sürdürülemez
    gh.kapi.set()
    assert g.indir(onay=True, arka_planda=False)["durum"] == "hazir"   # yeni onayla baştan


def test_iptal_duraklatilmisken(gh, dizin):
    gh.kapi_esigi = 1 * MB
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    g.indir(onay=True)
    assert bekle(lambda: g.durum()["indirilen"] >= 1 * MB)
    g.duraklat()
    g._is.join(5)
    assert g.iptal()["durum"] == "iptal"
    assert dosyalar(dizin) == []


def test_tamamlanmis_dosya_varsa_yeniden_indirilmez(gh, dizin):
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    g.indir(onay=True, arka_planda=False)
    n = len(gh.exe_istekleri())
    g2 = yap(gh, dizin)
    g2.denetle(arka_planda=False)
    assert g2.indir(onay=True, arka_planda=False)["durum"] == "hazir"
    assert len(gh.exe_istekleri()) == n                              # yalnız yerel doğrulama


# ------------------------------------------------------------------ yönlendirme, güvenlik

def test_ayni_sunucu_icinde_yonlendirme_izlenir(gh, dizin):
    gh.yonlendir_ic = True
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    assert g.indir(onay=True, arka_planda=False)["durum"] == "hazir"
    assert any(i["yol"].startswith("/cdn/") for i in gh.istekler)


@pytest.mark.parametrize("hedef", ["https://example.com/x.exe", "http://localhost:{port}/x.exe", "http://127.0.0.2:{port}/x.exe",
                                   "file:///etc/passwd", "ftp://127.0.0.1/x"])
def test_beyaz_liste_disi_yonlendirme_reddedilir(gh, dizin, hedef):
    gh.yonlendir_disari = hedef.format(port=gh.port)
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    d = g.indir(onay=True, arka_planda=False)
    assert d["durum"] == "hata" and dosyalar(dizin) == []
    assert "yönlendir" in d["mesaj"] or "Yalnız https" in d["mesaj"], d["mesaj"]
    assert ag_koruma.IHLALLER == []                                  # dış adrese bağlanma girişimi bile olmadı


def test_dosya_adi_yol_gecisi_reddedilir(gh, dizin):
    g = yap(gh, dizin)
    for kotu in ("..\\x.exe", "../x.exe", "a/b.exe", "KimlikMerkezi-Kurulum-v1.exe/../../x", "KimlikMerkezi-Kurulum-v1\x00.exe"):
        g.aday = {"dosya_adi": kotu, "boyut": 5, "indirme_url": "", "ozet_url": "", "surum": "1", "etiket": "v1", "onsurum": True}
        with pytest.raises(GuncellemeHatasi):
            g._yollar()


def test_temizle_eski_ve_kurulu_surum_dosyalarini_siler(gh, dizin):
    dizin.mkdir()
    eski = dizin / "KimlikMerkezi-Kurulum-v0.1.1.exe"
    esit_parca = dizin / "KimlikMerkezi-Kurulum-v0.1.0.exe.part"
    yeni = dizin / "KimlikMerkezi-Kurulum-v0.2.0.exe"
    baska = dizin / "kur.log"
    for p in (eski, esit_parca, yeni, baska):
        p.write_bytes(b"x")
    yap(gh, dizin, mevcut="0.1.1").temizle()
    assert dosyalar(dizin) == ["KimlikMerkezi-Kurulum-v0.2.0.exe", "kur.log"]


# ------------------------------------------------------------------ kurulum

def test_kurulum_komutu_ve_gec_baslatma(gh, dizin):
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    g.indir(onay=True, arka_planda=False)
    d = g.kur(onay=True, otomatik_baslat=True)
    assert d["durum"] == "kuruluyor"
    assert g.kayit == [], "kurulum programı kapanıştan ÖNCE başlatılmamalı"
    argv = g.bekleyen_kurulum
    exe = dizin / "KimlikMerkezi-Kurulum-v0.9.0.exe"
    assert argv[0] == str(exe)
    assert {"/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/GUNCELLEME=1", "/TASKS=otobaslat"} <= set(argv)
    assert any(a.startswith("/LOG=") and Path(a[5:]).parent == dizin for a in argv)
    assert not any(a.startswith("/DIR") or "SILVERIYI" in a for a in argv)       # veri/kurulum klasörüne dokunan bayrak yok
    assert g.kurulumu_baslat() is True
    assert g.kayit == [argv]
    assert g.kurulumu_baslat() is False and len(g.kayit) == 1                     # iki kez başlamaz


def test_kurulum_girisde_baslatma_tercihini_korur(gh, dizin):
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    g.indir(onay=True, arka_planda=False)
    g.kur(onay=True, otomatik_baslat=False)
    assert "/TASKS=!otobaslat" in g.bekleyen_kurulum and "/TASKS=otobaslat" not in g.bekleyen_kurulum


def test_kurulumdan_once_dosya_yeniden_dogrulanir(gh, dizin):
    g = yap(gh, dizin)
    g.denetle(arka_planda=False)
    g.indir(onay=True, arka_planda=False)
    exe = dizin / "KimlikMerkezi-Kurulum-v0.9.0.exe"
    exe.write_bytes(exe.read_bytes()[:-1] + b"!")                                  # indirmeden sonra değiştirildi
    with pytest.raises(GuncellemeHatasi):
        g.kur(onay=True, otomatik_baslat=True)
    assert not exe.exists() and g.durum()["durum"] == "hata" and g.kurulumu_baslat() is False


def test_baslatici_hatasi_false_doner(gh, dizin):
    def kotu(argv):
        raise OSError("yok")
    g = Guncelleme(dizin, "0.1.1", gh.politika(), baslatici=kotu)
    g.denetle(arka_planda=False)
    g.indir(onay=True, arka_planda=False)
    g.kur(onay=True, otomatik_baslat=True)
    assert g.kurulumu_baslat() is False


def test_varsayilan_baslatici_kabuksuz_ve_ayrik(monkeypatch):
    cagrilar = []
    monkeypatch.setattr(G.subprocess, "Popen", lambda argv, **kw: cagrilar.append((argv, kw)))
    G._baslat_surec(["/tmp/x.exe", "/VERYSILENT"])
    (argv, kw), = cagrilar
    assert argv == ["/tmp/x.exe", "/VERYSILENT"] and kw["shell"] is False and kw["close_fds"] is True
    assert kw["stdin"] is G.subprocess.DEVNULL and (kw.get("start_new_session") or kw.get("creationflags"))
