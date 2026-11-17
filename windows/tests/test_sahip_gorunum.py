"""Sahip görünümü (v0.3.0): verinin sahibi kendi bilgisayarında hassas kayıtları da TAM görür;
saat grafikleri yerel saatle gelir. Yapay zekâ (MCP) yolu bu köprüyü kullanmaz."""
from __future__ import annotations

from kimlikwin import harita_kopru as hk


class _Hub:
    def get_event(self, _id):
        class E:
            category = "mesaj"
        return E()


def _saglayici(cagrilar):
    def harita(hub, ac_hassas=frozenset(), aralik=None):
        cagrilar.append(("harita", set(ac_hassas)))
        return {"bolgeler": [{"id": "kalp", "olay_sayisi": 7, "ilk": "a", "son": "b", "ozet": "7 kayıt"}]}

    def bolge(hub, bid, ac_hassas=frozenset(), utc_kaydirma=0, sahip=False, **kw):
        cagrilar.append(("bolge", bid, set(ac_hassas), utc_kaydirma, sahip))
        return {"id": bid, "grafikler": [{"ornek": "X"}], "en_cok": [{"ad": "kişi", "sayi": 3}], "gruplar": [1]}

    def kayitlar(hub, bid, ac_hassas=frozenset(), utc_kaydirma=0, sahip=False, **kw):
        cagrilar.append(("kayitlar", bid, utc_kaydirma, sahip))
        return {"toplam": 1, "kayitlar": [{"id": "e1", "kategori": "mesaj", "baslik": "Merhaba anne", "alt": "gerçek metin"}]}

    def ayrinti(hub, eid, sahip=False, ac_hassas=frozenset()):
        cagrilar.append(("ayrinti", sahip))
        return {"id": eid, "metin": "gerçek içerik", "alanlar": [{"ad": "lat", "deger": 41.0}]}

    return hk.Saglayici(harita, bolge, kayitlar, ayrinti)


def test_sahip_hassas_bolgeyi_kilitsiz_ve_icerikli_gorur(monkeypatch):
    cagrilar: list = []
    monkeypatch.setattr(hk, "saglayici", _saglayici(cagrilar))
    monkeypatch.setattr(hk, "SAHIP", True)
    monkeypatch.setattr(hk, "YEREL_KAYMA", 3)
    # hiçbir bölge açılmadan (ac_hassas boş) bile kilit yok
    h = hk.harita(_Hub(), set())
    assert all(not b["kilitli"] for b in h["bolgeler"]) and h["bolgeler"][0]["olay_sayisi"] == 7
    b = hk.bolge(_Hub(), "kalp", set())
    assert not b["kilitli"] and b["en_cok"] and b["gruplar"] and b["grafikler"][0]["ornek"] == "X"
    k = hk.kayitlar(_Hub(), "kalp", set())
    assert k["kayitlar"][0]["baslik"] == "Merhaba anne" and "gizli" not in str(k)
    d = hk.ayrinti(_Hub(), "e1", set())
    assert not d["kilitli"] and d["metin"] == "gerçek içerik" and d["alanlar"] and not d.get("icerik_gizli")
    # sağlayıcıya sahip bayrağı ve Türkiye saat farkı (+3) gitti
    assert ("bolge", "kalp", set(hk.HASSAS), 3, True) in cagrilar
    assert ("kayitlar", "kalp", 3, True) in cagrilar and ("ayrinti", True) in cagrilar


def test_sahip_kapaliyken_eski_savunma_calisir(monkeypatch):
    cagrilar: list = []
    monkeypatch.setattr(hk, "saglayici", _saglayici(cagrilar))
    monkeypatch.setattr(hk, "SAHIP", False)
    assert hk.bolge(_Hub(), "kalp", set())["kilitli"] is True
    assert hk.kayitlar(_Hub(), "kalp", set())["kilitli"] is True
    assert hk.ayrinti(_Hub(), "e1", set()) == {"id": "e1", "kilitli": True}
    assert not cagrilar            # kilitliyken sağlayıcı hiç çağrılmadı


def test_varsayilan_uretimde_sahip_acik():
    import importlib
    taze = importlib.reload(hk)
    assert taze.SAHIP is True


def test_yerel_kayma_sistem_saatinden_ve_ezilebilir(monkeypatch):
    monkeypatch.setattr(hk, "YEREL_KAYMA", None)
    assert isinstance(hk.yerel_kayma(), int) and -12 <= hk.yerel_kayma() <= 14
    monkeypatch.setattr(hk, "YEREL_KAYMA", 3)
    assert hk.yerel_kayma() == 3
