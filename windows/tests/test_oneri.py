"""Persona öneri inceleme ekranı: kuyruk (oneri.db) -> Onayla / Düzelt / Reddet / Hiç doğru değil / Toplu reddet."""
import pytest
from kimlikcore import EventIn
from kimlikserver.oneri import OneriKuyrugu, dogrula_onerme

import harita_sahte
from kimlikwin import harita_kopru
from kimlikwin.cekirdek import IslemHatasi


@pytest.fixture(autouse=True)
def sahte():
    eski = harita_sahte.kur()
    yield
    harita_kopru.saglayici = eski


@pytest.fixture
def d(kurulu):
    h = kurulu.uygulama.hub
    sid = h.add_source("test", "1", None)
    h.add_events(sid, [EventIn(ts="2026-02-01T10:00:00Z", kind="sohbet.mesaj", category="sohbet", text="Ankara'da yaşıyorum", event_key="s1"),
                       EventIn(ts="2026-02-02T10:00:00Z", kind="x", category="notlar", text="Python projesi notu", event_key="n1")])
    ids = {r[0]: r[1] for r in h.query("SELECT event_key, event_id FROM events")}
    app_id, _ = kurulu.uygulama.anahtarlar.create_key("Claude deneme")
    kurulu.ids, kurulu.app = ids, app_id
    return kurulu


def ekle(d, ifade, kat="kimlik", kanit=("s1",), guven=0.8, anahtar=None):
    k = OneriKuyrugu(d.ayarlar["veri_klasoru"])
    return k.ekle(d.app, [dogrula_onerme({"ifade": ifade, "kategori": kat, "kanit": [d.ids[x] for x in kanit], "guven": guven, "anahtar": anahtar})])


def test_bos_kuyruk_ve_sayac(d):
    assert d.api("oneri_listele", {}) == {"oneriler": [], "sayi": 0}
    assert d.api("persona_liste", {})["oneri_sayisi"] == 0


def test_listele_kanit_onayla_persona_ve_haritaya_duser(d):
    ekle(d, "Ankara'da yaşıyor", "kimlik", ("s1",), 0.9, "sehir")
    assert d.api("persona_liste", {})["oneri_sayisi"] == 1
    o = d.api("oneri_listele", {})["oneriler"][0]
    assert o["ifade"] == "Ankara'da yaşıyor" and o["kategori_ad"] == "Kimlik" and o["kanit_sayisi"] == 1 and o["uygulama"] == "Claude deneme" and o["guven"] == 0.9
    k = d.api("oneri_kanit", {"oneri_id": o["id"]})["kanit"]
    assert k[0]["metin"] == "Ankara'da yaşıyorum" and k[0]["hassas"] is True and k[0]["kategori"] == "sohbet"
    # onaylanmadan persona ve kimlik kartında yok
    assert "Ankara" not in d.api("kimlik_karti", {})["markdown"]
    d.api("oneri_onayla", {"oneri_id": o["id"]})
    assert d.api("oneri_listele", {})["sayi"] == 0
    assert any(f["metin"] == "Ankara'da yaşıyor" and f["durum"] == "beyan_edilen" for f in d.api("persona_liste", {})["bilgiler"])
    assert any(b["veri"] == "Ankara'da yaşıyor" for b in d.api("harita", {})["beyan"])      # Haritadaki "Beyan edilen bilgiler"
    assert "Ankara'da yaşıyor" in d.api("kimlik_karti", {})["markdown"]
    with pytest.raises(Exception):
        d.api("oneri_onayla", {"oneri_id": o["id"]})        # ikinci karar yok


def test_duzelt_reddet_hic_dogru_degil_toplu(d):
    ekle(d, "Python kullanır", "ilgi", ("n1",))
    ekle(d, "Mac kullanır", "cihazlar", ("n1",))
    ekle(d, "Kedisi var", "ilgi", ("n1",))
    ekle(d, "Pilot", "is", ("n1",))
    o = {x["ifade"]: x["id"] for x in d.api("oneri_listele", {})["oneriler"]}
    with pytest.raises(IslemHatasi):
        d.api("oneri_duzelt", {"oneri_id": o["Python kullanır"], "ifade": "  "})
    d.api("oneri_duzelt", {"oneri_id": o["Python kullanır"], "ifade": "Python ile geliştirme yapar"})
    assert any(f["metin"] == "Python ile geliştirme yapar" for f in d.api("persona_liste", {})["bilgiler"])
    assert not any(f["metin"] == "Python kullanır" for f in d.api("persona_liste", {})["bilgiler"])
    d.api("oneri_reddet", {"oneri_id": o["Mac kullanır"]})
    d.api("oneri_hic_dogru_degil", {"oneri_id": o["Kedisi var"]})
    # "hiç doğru değil": aynı ifade bir daha kuyruğa girmez; "reddet": girebilir mi, sınır sunucuya ait (yalnız doğrulanır)
    sonuc = ekle(d, "Kedisi var", "ilgi", ("n1",))
    assert d.api("oneri_listele", {})["sayi"] == 1                      # yalnız "Pilot" bekliyor
    assert sonuc is not None
    assert d.api("oneri_toplu_reddet", {})["reddedilen"] == 1
    assert d.api("oneri_listele", {})["sayi"] == 0
    gecmis = d.api("oneri_listele", {"durum": "reddedildi"})
    assert {x["ifade"] for x in gecmis["oneriler"]} >= {"Mac kullanır", "Pilot"}


def test_kanit_yok_ve_gizli_kayit(d):
    ekle(d, "Not kaydı", "ilgi", ("n1",))
    o = d.api("oneri_listele", {})["oneriler"][0]
    d.uygulama.hub.hide_event(d.ids["n1"], "test")
    k = d.api("oneri_kanit", {"oneri_id": o["id"]})["kanit"][0]
    assert k["gizli"] is True and k["metin"] == ""
    with pytest.raises(IslemHatasi):
        d.api("oneri_kanit", {"oneri_id": "yok"})
