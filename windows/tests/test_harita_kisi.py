"""Persona haritası köprüsü ve çoklu kişi (her kişi ayrı veri klasörü)."""
import sys

import pytest
from kimlikcore import Hub, HubLockedError

import harita_sahte
from kimlikwin import harita_kopru
from kimlikwin.cekirdek import IslemHatasi


@pytest.fixture(autouse=True)
def sahte():
    eski = harita_sahte.kur()
    yield
    harita_kopru.saglayici = eski


def olay_ekle(y):
    from kimlikcore import EventIn
    h = y.uygulama.hub
    sid = h.add_source("test", "1", None)
    h.add_events(sid, [EventIn(ts="2026-01-01T10:00:00Z", kind="x", category="video", text="a", event_key="k1")])


def test_uretimde_sahteye_dusme_yok(kurulu, monkeypatch):
    harita_kopru.saglayici = None
    monkeypatch.setitem(sys.modules, "kimlikserver.harita", None)   # modül yokmuş gibi
    with pytest.raises(IslemHatasi) as e:
        kurulu.api("harita", {})
    assert e.value.kod == "harita_yok"


def test_harita_bicimi_ve_bos_veri(kurulu):
    v = kurulu.api("harita", {})
    assert {b["id"] for b in v["bolgeler"]} == {"bas", "goz", "kulak", "agiz", "el", "kalp", "karin", "ayak", "ic"}
    assert v["profil"]["olay"] == 0 and all(not b["olay_sayisi"] for b in v["bolgeler"] if not b["kilitli"])
    olay_ekle(kurulu)
    v = kurulu.api("harita", {})
    assert v["profil"]["olay"] > 0 and any(b["olay_sayisi"] for b in v["bolgeler"])


def test_hassas_bolge_kilitli_sayi_ve_icerik_sizmaz(kurulu):
    olay_ekle(kurulu)
    cagrilar = []
    gercek_h, gercek_b = harita_kopru.saglayici

    def bolge_izle(hub, bid, **kw):
        cagrilar.append(bid)
        return gercek_b(hub, bid, **kw)
    harita_kopru.saglayici = (gercek_h, bolge_izle)
    v = kurulu.api("harita", {})
    for b in v["bolgeler"]:
        if b["id"] in ("kalp", "karin", "ayak"):
            assert b["kilitli"] and b["olay_sayisi"] is None and b["ozet"] == ""
    d = kurulu.api("harita_bolge", {"bolge_id": "kalp"})
    assert d["kilitli"] and d["grafikler"] == [] and "kalp" not in cagrilar     # sağlayıcı hiç çağrılmadı
    with pytest.raises(IslemHatasi) as e:
        kurulu.api("harita_hassas", {"bolge_id": "kalp", "ac": True})            # onaysız açılmaz
    assert e.value.kod == "onay_yok"
    with pytest.raises(IslemHatasi):
        kurulu.api("harita_hassas", {"bolge_id": "bas", "ac": True, "onay": True})  # hassas olmayan
    kurulu.api("harita_hassas", {"bolge_id": "kalp", "ac": True, "onay": True})
    d = kurulu.api("harita_bolge", {"bolge_id": "kalp"})
    assert not d["kilitli"] and d["grafikler"] and d["en_cok"] == []             # yalnız sayı/dağılım
    assert not any(b["kilitli"] for b in kurulu.api("harita", {})["bolgeler"] if b["id"] == "kalp")
    kurulu.api("harita_hassas", {"bolge_id": "kalp", "ac": False})
    assert kurulu.api("harita_bolge", {"bolge_id": "kalp"})["kilitli"]


def test_sagayici_hassas_icin_en_cok_dondururse_atilir(kurulu):
    harita_kopru.saglayici = (harita_kopru.saglayici[0],
                              lambda hub, bid, **kw: {"id": bid, "grafikler": [{"tur": "cubuk", "baslik": "x", "etiketler": ["a"], "degerler": [1], "ornek": "gizli metin"}],
                                                      "en_cok": [{"ad": "gizli", "sayi": 1, "ornek": "gizli"}], "notlar": []})
    kurulu.api("harita_hassas", {"bolge_id": "ayak", "ac": True, "onay": True})
    d = kurulu.api("harita_bolge", {"bolge_id": "ayak"})
    assert d["en_cok"] == [] and "ornek" not in d["grafikler"][0]


# ---------------------------------------------------------------- kişiler
def test_kisi_ekle_sec_kalici_ve_ayri_veri(kurulu, tmp_path, veri):
    k = kurulu.api("kisiler", {})
    assert [x["ad"] for x in k["kisiler"]] == ["Ben"] and k["kisiler"][0]["secili"]
    olay_ekle(kurulu)
    kurulu.api("persona_ekle", {"metin": "Ben kahve severim", "kategori": "tercihler"})
    ikinci = tmp_path / "ayse"
    k = kurulu.api("kisi_ekle", {"ad": "Ayşe", "yol": str(ikinci)})
    assert [x["ad"] for x in k["kisiler"]] == ["Ben", "Ayşe"] and next(x for x in k["kisiler"] if x["secili"])["ad"] == "Ayşe"
    # başka kişi = başka veri, başka persona
    assert kurulu.api("durum", {})["ozet"]["counts"]["event"] == 0
    assert kurulu.api("persona_liste", {})["bilgiler"] == []
    kurulu.api("persona_ekle", {"metin": "Ayşe çay sever", "kategori": "tercihler"})
    assert kurulu.api("harita", {})["profil"]["olay"] == 0
    # seçim kalıcı: yeniden başlayınca Ayşe açılır
    from kimlikwin.ayarlar import Ayarlar
    assert Ayarlar(kurulu.ayarlar.dizin)["secili_kisi"] == k["secili"]
    kurulu.kapat()
    kurulu.baslat()
    assert kurulu.api("durum", {})["veri_klasoru"] == str(ikinci)
    # geri dön
    ben = next(x for x in kurulu.api("kisiler", {})["kisiler"] if x["ad"] == "Ben")
    kurulu.api("kisi_sec", {"kisi_id": ben["id"]})
    assert kurulu.api("durum", {})["ozet"]["counts"]["event"] == 1
    assert [f["metin"] for f in kurulu.api("persona_liste", {})["bilgiler"]] == ["Ben kahve severim"]
    # seçili olmayan kişinin klasörü kilitli değil (yalnız seçili kişi yazılır)
    with Hub.open(ikinci, write=True):
        pass
    with pytest.raises(HubLockedError):
        Hub.open(veri, write=True)


def test_kisi_dogrulamalari(kurulu, tmp_path):
    for ad in ("", "x" * 61):
        with pytest.raises(IslemHatasi):
            kurulu.api("kisi_ekle", {"ad": ad, "yol": str(tmp_path / "a")})
    with pytest.raises(IslemHatasi):
        kurulu.api("kisi_ekle", {"ad": "ben", "yol": str(tmp_path / "b")})          # aynı ad
    with pytest.raises(IslemHatasi):
        kurulu.api("kisi_ekle", {"ad": "Yeni", "yol": str(kurulu.ayarlar["veri_klasoru"])})  # aynı klasör
    k = kurulu.api("kisi_ekle", {"ad": "Yeni", "yol": str(tmp_path / "yeni")})
    ben = next(x for x in k["kisiler"] if x["ad"] == "Ben")
    with pytest.raises(IslemHatasi):
        kurulu.api("kisi_kaldir", {"kisi_id": next(x for x in k["kisiler"] if x["secili"])["id"]})   # seçili kaldırılamaz
    k = kurulu.api("kisi_kaldir", {"kisi_id": ben["id"]})
    assert [x["ad"] for x in k["kisiler"]] == ["Yeni"]
    assert (tmp_path / "veri" / "kimlik.db").exists()                                  # veriye dokunulmadı
    assert kurulu.api("kisi_yeniden_adlandir", {"kisi_id": k["secili"], "ad": "Yeni2"})["kisiler"][0]["ad"] == "Yeni2"


def test_kilitli_kisi_acilamazsa_eskisi_geri_gelir(kurulu, tmp_path):
    k = kurulu.api("kisi_ekle", {"ad": "Z", "yol": str(tmp_path / "z")})
    z = next(x for x in k["kisiler"] if x["secili"])
    ben = next(x for x in k["kisiler"] if x["ad"] == "Ben")
    kurulu.api("kisi_sec", {"kisi_id": ben["id"]})
    baska = Hub.open(tmp_path / "z", write=True)          # başka süreç gibi Z'yi tutuyor
    try:
        with pytest.raises(IslemHatasi) as e:
            kurulu.api("kisi_sec", {"kisi_id": z["id"]})
        assert e.value.kod == "kisi_acilamadi" and kurulu.uygulama is not None and kurulu.api("kisiler", {})["secili"] == ben["id"]
    finally:
        baska.close()


def test_eski_kurulum_ben_kisisine_tasinir(yonetici, veri):
    from kimlikwin import veri_klasoru
    veri_klasoru.olustur(veri)
    yonetici.ayarlar.guncelle(veri_klasoru=str(veri), ilk_acilis_tamam=True)    # kisiler alanı olmayan eski ayar
    yonetici.baslat()
    assert [k["ad"] for k in yonetici.api("kisiler", {})["kisiler"]] == ["Ben"]


def test_sihirbaz_kisi_adini_alir(yonetici, veri):
    yonetici.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False, "ad": "Deniz"})
    assert yonetici.api("kisiler", {})["kisiler"][0]["ad"] == "Deniz"
