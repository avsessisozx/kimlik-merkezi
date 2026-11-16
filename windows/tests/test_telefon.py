"""Telefon aktarımı (Windows tarafı): alıcının yaşam döngüsü, eşleştirme, içe alma, API güvenliği.
Alıcı testte rastgele port + 127.0.0.1 ile (kurucuya enjekte) çalışır; ağa çıkılmaz."""
from __future__ import annotations

import importlib.util
import socket
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

from kimlikwin.ayarlar import Ayarlar, VARSAYILAN
from kimlikwin.baslangic import Otomatik
from kimlikwin.cekirdek import IslemHatasi
from kimlikwin.yonetici import Yonetici

_IO = Path(__file__).resolve().parents[2] / "server" / "tests" / "istemci_ornek.py"
_spec = importlib.util.spec_from_file_location("istemci_ornek_telefon", _IO)
IO = importlib.util.module_from_spec(_spec)
sys.modules["istemci_ornek_telefon"] = IO
_spec.loader.exec_module(IO)

TEL = {"port": 0, "adres": "127.0.0.1", "bulma_port": None, "saglayici": None, "adresler": ["127.0.0.1"]}


class _AU:
    d = None

    def oku(self): return self.d
    def yaz(self, k): self.d = k
    def sil(self): self.d = None


def yap(tmp_path, ad="a"):
    return Yonetici(Ayarlar(tmp_path / f"ayar-{ad}"), Otomatik(_AU()), secici=lambda t: None,
                    claude_yolu=lambda: None, telefon_ayar=dict(TEL))


@pytest.fixture
def y(tmp_path):
    y = yap(tmp_path)
    y.api("sihirbaz_tamamla", {"yol": str(tmp_path / "veri"), "otomatik_baslat": False})
    yield y
    y.kapat()


def dinliyor(port) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def bekle(kosul, sure=15.0):
    son = time.time() + sure
    while time.time() < son:
        if kosul():
            return True
        time.sleep(0.05)
    return False


def eslestir(y, cihaz=None):
    cihaz = cihaz or str(uuid.uuid4())
    km1 = y.api("telefon_kod_uret", {})["kod"]
    i = IO.Istemci.kodla(km1, cihaz, host="127.0.0.1", port=y.telefon.alici().port)
    i.eslestir(IO.eslestirme_coz(km1)["k"])
    return i, cihaz


def dosya_yaz(klasor, cihaz, n=3, on_ek="k"):
    klasor.mkdir(parents=True, exist_ok=True)
    did = str(uuid.uuid4())
    yol = klasor / f"{did}.jsonl"
    yol.write_bytes(IO.kutu_dosyasi(cihaz, did, n, metin="telefonnotu", on_ek=on_ek))
    return yol


def test_ayar_varsayilan_kapali_ve_dinleyen_yok(y):
    assert VARSAYILAN["telefon_aktarimi"] is False
    d = y.api("telefon_durum", {})
    assert d["acik"] is False and d["calisiyor"] is False and d["port"] is None
    assert y.telefon.alici() is None


def test_ac_calisir_kapat_durur(y):
    d = y.api("telefon_ac", {"acik": True})
    assert d["calisiyor"] and d["port"] and dinliyor(d["port"])
    assert y.api("ayarlar", {})["telefon_aktarimi"] is True
    port = d["port"]
    d = y.api("telefon_ac", {"acik": False})
    assert d["calisiyor"] is False and bekle(lambda: not dinliyor(port))
    assert y.ayarlar["telefon_aktarimi"] is False


def test_uygulama_kapaninca_ve_acilinca(tmp_path):
    y = yap(tmp_path)
    y.api("sihirbaz_tamamla", {"yol": str(tmp_path / "veri"), "otomatik_baslat": False})
    port = y.api("telefon_ac", {"acik": True})["port"]
    assert dinliyor(port)
    y.kapat()                                    # uygulama kapandı: dinleyen yok
    assert bekle(lambda: not dinliyor(port)) and y.telefon.alici() is None
    y.baslat()                                   # ayar açık kaldı: uygulama açılınca yeniden başlar
    try:
        assert y.telefon.calisiyor() and dinliyor(y.telefon.alici().port)
    finally:
        y.kapat()


def test_ayar_kapaliysa_uygulama_acilinca_dinlemez(tmp_path):
    y = yap(tmp_path)
    y.api("sihirbaz_tamamla", {"yol": str(tmp_path / "veri"), "otomatik_baslat": False})
    try:
        assert y.telefon.alici() is None and not y.telefon.calisiyor()
    finally:
        y.kapat()


def test_ayar_acik_ama_uygulama_yokken_dinlemez(tmp_path):
    y = yap(tmp_path)
    y.ayarlar.guncelle(telefon_aktarimi=True)    # sihirbaz yok: uygulama None
    y.telefon.uyumlandir()
    assert y.telefon.alici() is None and y.api("telefon_durum", {})["uygulama_acik"] is False


def test_kisi_degisince_durur_ve_yeni_klasorle_baslar(y, tmp_path):
    d = y.api("telefon_ac", {"acik": True})
    eski = y.telefon.alici()
    eski_veri = Path(y.uygulama.veri)
    y.api("kisi_ekle", {"ad": "Ikinci", "yol": str(tmp_path / "veri2")})
    assert bekle(lambda: not dinliyor(d["port"]))
    yeni = y.telefon.alici()
    assert yeni is not None and yeni is not eski and yeni.calisiyor()
    assert Path(yeni.veri) == Path(y.uygulama.veri) != eski_veri       # alıcı etkin kişinin klasörüne bağlı


def test_kod_uret_kapaliyken_reddedilir(y):
    with pytest.raises(IslemHatasi):
        y.api("telefon_kod_uret", {})


def test_kod_gecerli_sonra_sure_dolar(y):
    y.api("telefon_ac", {"acik": True})
    r = y.api("telefon_kod_uret", {})
    assert r["kod"].startswith("km1:") and r["sure_s"] == 600
    d = y.api("telefon_durum", {})
    assert d["kod_gecerli"] is True and 0 < d["kod_kalan_s"] <= 600 and d["kod_gecersizlik_nedeni"] is None
    y.telefon.alici().eslestirme_kodu_uret(0.01, ["127.0.0.1"])      # kısa süreli kod üretilir (yeni kod eskiyi değiştirir)
    time.sleep(0.1)
    d = y.api("telefon_durum", {})
    assert d["kod_gecerli"] is False and d["kod_gecersizlik_nedeni"] == "sure_doldu"
    assert d["kod_gecersizlik_metni"]


def test_uctan_uca_eslestir_gonder_ara_ikinci_yeni_degil(y):
    y.api("telefon_ac", {"acik": True})
    i, cihaz = eslestir(y)
    d = y.api("telefon_durum", {})
    assert d["kod_gecersizlik_nedeni"] == "kullanildi" and len(d["cihazlar"]) == 1
    assert d["cihazlar"][0]["ad"] == "Test telefonu" and d["cihazlar"][0]["id"] == cihaz and d["cihazlar"][0]["eslesme"]
    kutu = y.uygulama.veri.parent / "telefon-kutu"
    yol = dosya_yaz(kutu, cihaz, 4)
    yedek = yol.read_bytes()
    assert i.dosya_gonder(yol)["sonuc"] == "var"
    assert bekle(lambda: y.api("telefon_durum", {})["toplam_yeni"] == 4)
    d = y.api("telefon_durum", {})
    assert d["son_alim"]["yeni"] == 4 and d["son_alim"]["dosya"] == 1 and d["son_alim"]["zaman"].endswith("Z")
    r = y.api("ara", {"sorgu": "telefonnotu"})
    assert len(r["sonuclar"] if "sonuclar" in r else r["kayitlar"]) == 4
    assert not list((y.uygulama.veri / "gelen_aktarim").rglob("*.jsonl"))
    yol.write_bytes(yedek)                         # ikinci gönderim: alıcı `var` der, 0 yeni
    assert i.dosya_gonder(yol)["gonderilen_bayt"] == 0
    time.sleep(0.5)
    assert y.api("telefon_durum", {})["toplam_yeni"] == 4


def test_ice_aktarma_surerken_gelen_dosya_bekler_sonra_alinir(y, tmp_path):
    y.api("telefon_ac", {"acik": True})
    i, cihaz = eslestir(y)
    uyg = y.uygulama
    from kimlikwin.cekirdek import IceAktarmaIsi
    sahte = IceAktarmaIsi("x", None, False)          # durum "calisiyor": içe aktarma sürüyor
    uyg.is_ = sahte
    yol = dosya_yaz(tmp_path / "kutu", cihaz, 2)
    assert i.dosya_gonder(yol)["sonuc"] == "var"      # dosya alıcıya düştü
    time.sleep(1.0)
    assert y.api("telefon_durum", {})["toplam_yeni"] == 0          # içe alınmadı: bekliyor
    assert list((uyg.veri / "gelen_aktarim").rglob("*.jsonl"))
    sahte.durum = "bitti"
    assert bekle(lambda: y.api("telefon_durum", {})["toplam_yeni"] == 2)


def test_alim_surerken_ice_aktarma_mesgul_der(y, tmp_path):
    uyg = y.uygulama
    uyg._telefon_ice = True
    uyg.telefon_bekleme_s = 0.2
    try:
        with pytest.raises(IslemHatasi) as e:
            y.api("ice_aktar_baslat", {"yol": str(tmp_path)})
        assert e.value.kod == "mesgul"
        with pytest.raises(IslemHatasi):
            y.api("kopya_baslat", {})
        assert uyg.telefon_ice_al() is None
    finally:
        uyg._telefon_ice = False


def test_acilista_onceki_oturumdan_kalanlar_alinir(tmp_path):
    y = yap(tmp_path)
    y.api("sihirbaz_tamamla", {"yol": str(tmp_path / "veri"), "otomatik_baslat": False})
    veri = Path(y.uygulama.veri)
    y.kapat()
    dosya_yaz(veri / "gelen_aktarim" / str(uuid.uuid4()), "yok", 1)       # cihaz klasörü adı rastgele
    cihaz = str(uuid.uuid4())
    dosya_yaz(veri / "gelen_aktarim" / cihaz, cihaz, 3)
    y.baslat()
    try:
        assert bekle(lambda: y.telefon.durum()["toplam_yeni"] >= 3)
    finally:
        y.kapat()


def test_cihaz_iptali_sonrasi_401(y, tmp_path):
    y.api("telefon_ac", {"acik": True})
    i, cihaz = eslestir(y)
    assert i.pc_durumu()["protokol"] == 1
    y.api("telefon_cihaz_kaldir", {"device_id": cihaz})
    assert y.api("telefon_durum", {})["cihazlar"][0]["iptal"] is True
    yol = dosya_yaz(tmp_path / "kutu", cihaz, 1)
    with pytest.raises(IO.Yetkisiz):
        i.dosya_gonder(yol)
    with pytest.raises(IslemHatasi):
        y.api("telefon_cihaz_kaldir", {"device_id": "yok"})


def test_api_uclari_yol_adres_port_kabul_etmez(y):
    for ad, girdi in (("telefon_durum", {"port": 1}), ("telefon_ac", {"acik": True, "adres": "0.0.0.0"}),
                      ("telefon_kod_uret", {"yol": "/etc"}), ("telefon_cihaz_kaldir", {"device_id": "x", "yol": "/"})):
        with pytest.raises(TypeError):
            y.api(ad, girdi)
    from kimlikwin.yonetici import UYGULAMA_API
    import inspect
    for ad in ("telefon_durum", "telefon_ac", "telefon_kod_uret", "telefon_cihaz_kaldir"):
        ad_listesi = set(inspect.signature(getattr(y, "api_" + ad)).parameters)
        assert not ad_listesi & {"yol", "adres", "port", "klasor", "dosya"}
    assert not any(a.startswith("telefon") for a in UYGULAMA_API)


def test_hata_raporunda_kod_anahtar_adres_yok(y, tmp_path):
    y.api("telefon_ac", {"acik": True})
    i, cihaz = eslestir(y)
    km1 = y.api("telefon_kod_uret", {})["kod"]
    metin = y.api("hata_raporu", {"adim": "deneme", "mesaj": "x"})["metin"]
    assert "Telefon aktarımı: açık; eşleşmiş cihaz: 1; son alım: yok" in metin
    for sir in (km1, km1[4:], i.anahtar, cihaz, "127.0.0.1"):
        assert sir not in metin
    from kimlikwin import gunluk
    kayit = "\n".join(gunluk.son_satirlar(200, y.ayarlar.dizin))
    for sir in (km1, i.anahtar):
        assert sir not in kayit


def test_tepsi_menusu_telefon_ogesi(monkeypatch):
    import types
    ogeler = []

    class MenuItem:
        def __init__(self, metin, eylem, **kw):
            self.metin, self.eylem = metin, eylem
            ogeler.append(self)

    sahte = types.SimpleNamespace(MenuItem=MenuItem, Menu=lambda *o: o, Icon=lambda *a: types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "pystray", sahte)
    from kimlikwin import tepsi
    monkeypatch.setattr(tepsi, "simge_olustur", lambda *a, **k: None)
    durum = {"a": False}
    tepsi.Tepsi(lambda: None, lambda: None, lambda: True, lambda a: None,
                lambda: durum["a"], lambda a: durum.update(a=a))
    tel = next(o for o in ogeler if callable(o.metin))
    assert tel.metin() == "Telefon aktarımı: kapalı"
    tel.eylem()
    assert durum["a"] is True and tel.metin() == "Telefon aktarımı: açık"
    assert tepsi.telefon_metni(False) == "Telefon aktarımı: kapalı"


def test_elle_aktarim_jsonl_ve_zip_android_giden_olarak_taninir(y, tmp_path):
    import zipfile
    cihaz = str(uuid.uuid4())
    kutu = tmp_path / "elle"
    a = dosya_yaz(kutu, cihaz, 3, on_ek="a")
    zip_yolu = tmp_path / "giden.zip"
    b = dosya_yaz(kutu, cihaz, 2, on_ek="b")
    with zipfile.ZipFile(zip_yolu, "w") as z:
        z.write(b, b.name)
    for yol, beklenen in ((a, 3), (zip_yolu, 2)):          # tür verilmeden (otomatik tanıma)
        y.api("ice_aktar_baslat", {"yol": str(yol)})
        assert bekle(lambda: y.api("ice_aktar_durum", {})["durum"] != "calisiyor")
        d = y.api("ice_aktar_durum", {})
        assert d["durum"] == "bitti", d
        assert f"{beklenen}" in d["sonuc"] and "android_giden" in d["sonuc"]


def test_varsayilan_port_47823_web_portuyla_cakisirsa_bos_porta_duser(tmp_path):
    from kimlikwin import telefon
    assert telefon.ALICI_PORTU == 47823
    ayar = {k: v for k, v in TEL.items() if k != "port"}
    y = Yonetici(Ayarlar(tmp_path / "ayar-p"), Otomatik(_AU()), secici=lambda t: None,
                 claude_yolu=lambda: None, telefon_ayar=ayar)
    try:
        y.api("sihirbaz_tamamla", {"yol": str(tmp_path / "veri"), "otomatik_baslat": False})
        y.ayarlar.guncelle(port=47823)                  # web arayüzü de 47823 ister: alıcı OS'un verdiği porta düşer
        d = y.api("telefon_ac", {"acik": True})
        assert d["calisiyor"] and d["port"] and d["port"] != 47823 and dinliyor(d["port"])
        assert IO.eslestirme_coz(y.api("telefon_kod_uret", {})["kod"])["p"] == d["port"]
    finally:
        y.kapat()


# ---------------------------------------------------------------- açılış yarışı: telefon alımı kullanıcı işini reddettirmez
def _yavas_alim(monkeypatch, sure):
    import kimlikserver.aktarim as ak
    monkeypatch.setattr(ak, "gelenleri_ice_al", lambda hub, *a, **k: (time.sleep(sure), {"dosya": 0, "yeni": 0, "yinelenen": 0, "eksik": 0})[1])


def _alim_baslat(uyg):
    t = threading.Thread(target=uyg.telefon_ice_al, daemon=True)
    t.start()
    assert bekle(lambda: uyg._telefon_ice, 5)
    return t


def test_acilista_ayar_kapali_bos_klasor_telefon_alimi_cagrilmaz(tmp_path, monkeypatch):
    from kimlikwin.cekirdek import Uygulama
    cagri = []
    orijinal = Uygulama.telefon_ice_al
    monkeypatch.setattr(Uygulama, "telefon_ice_al", lambda self: (cagri.append(1), orijinal(self))[1])
    y = yap(tmp_path)
    y.api("sihirbaz_tamamla", {"yol": str(tmp_path / "veri"), "otomatik_baslat": False})
    y.kapat()
    cagri.clear()
    y.baslat()
    try:
        time.sleep(0.6)
        assert cagri == [] and not y.uygulama._telefon_ice
        assert y.api("kopya_baslat", {})["durum"] in ("calisiyor", "bitti")
    finally:
        y.kapat()


def test_alim_surerken_kopya_ve_ice_aktar_bekleyip_baslar(y, tmp_path, monkeypatch):
    uyg = y.uygulama
    _yavas_alim(monkeypatch, 1.0)
    t = _alim_baslat(uyg)
    t0 = time.time()
    assert y.api("kopya_baslat", {})["durum"] in ("calisiyor", "bitti")
    assert time.time() - t0 >= 0.5 and not uyg._telefon_ice
    t.join(5)
    assert bekle(lambda: y.api("kopya_durum", {})["durum"] != "calisiyor")
    veri = tmp_path / "ic"
    veri.mkdir()
    (veri / "a.txt").write_text("merhaba", encoding="utf-8")
    t = _alim_baslat(uyg)
    t0 = time.time()
    y.api("ice_aktar_baslat", {"yol": str(veri), "tur": "dosyalar"})
    assert time.time() - t0 >= 0.5
    t.join(5)


def test_alim_bekleme_suresi_asilinca_mesgul_hatasi(y, tmp_path):
    uyg = y.uygulama
    uyg.telefon_bekleme_s = 0.3
    uyg._telefon_ice = True
    try:
        for ad, arg in (("kopya_baslat", {}), ("ice_aktar_baslat", {"yol": str(tmp_path)})):
            t0 = time.time()
            with pytest.raises(IslemHatasi) as e:
                y.api(ad, arg)
            assert e.value.kod == "mesgul" and 0.25 <= time.time() - t0 < 5
    finally:
        uyg._telefon_ice = False
