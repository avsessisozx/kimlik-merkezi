"""Aşama 2: persona testleri (sentetik veri, sahte saat)."""
from __future__ import annotations

import pytest
from kimlikcore import FormatError, Hub, NotFoundError

from kimlikserver.persona import Persona, PersonaReader


@pytest.fixture
def hub(veri):
    with Hub.open(veri, write=True) as h:
        yield h


@pytest.fixture
def persona(hub, clock):
    return Persona(hub, clock=clock)


def _raw_insert(hub, statement, status, category="kimlik", valid_until=None):
    with hub.transaction() as c:
        c.execute(
            "INSERT INTO facts(fact_id, statement, source_id, date, status, valid_from, valid_until,"
            " category, fact_key, hidden, updated) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, NULL, 0, ?)",
            (f"raw-{statement}", statement, "2026-11-01T00:00:00Z", status, "2026-11-01T00:00:00Z",
             valid_until, category, "2026-11-01T00:00:00Z"))


def test_elle_eklenen_beyan_kartta(persona):
    fid = persona.add_fact("Adım Deneme Kişi", "kimlik")
    f = persona.get_fact(fid)
    assert f.status == "beyan_edilen" and f.source_id is None and f.valid_until is None
    card = persona.export_identity_card(["kimlik"])
    assert "### Kimlik" in card and "- Adım Deneme Kişi (beyan, son doğrulama: 2026-11-09)" in card
    assert "## Bu kişi hakkında bilinenler" in card
    assert "kaynak:" not in card


def test_cikarilan_ve_eskimis_kartta_yok(persona, hub):
    persona.add_fact("Görünür bilgi", "kimlik")
    _raw_insert(hub, "Tahmin edilen bilgi", "cikarilan")
    _raw_insert(hub, "Eski bilgi", "eskimis")
    for cats in (None, ["kimlik"]):
        card = persona.export_identity_card(cats)
        assert "Görünür bilgi" in card
        assert "Tahmin edilen bilgi" not in card
        assert "Eski bilgi" not in card
    assert [f.statement for f in persona.list_facts()] == ["Görünür bilgi"]
    # Persona ekranı için hepsi listelenebilir ama kart/çıktıya girmez
    assert len(persona.list_facts(include_inactive=True)) == 3


def test_dosyadan_alinan_kaynak_adiyla(persona, hub, tmp_path):
    belge = tmp_path / "ozgecmis.txt"
    belge.write_text("sentetik belge")
    sid = hub.add_source("belge", "1", None)
    hub.store_raw(sid, belge)
    persona.add_fact_from_source("Python biliyor", "ilgi", sid)
    f = persona.list_facts(["ilgi"])[0]
    assert f.status == "dosyadan_alinan" and f.source_id == sid
    card = persona.export_identity_card(["ilgi"])
    assert "- Python biliyor (dosyadan, kaynak: belge: ozgecmis.txt, son doğrulama: 2026-11-09)" in card


def test_kaynaksiz_veya_yok_kaynak_reddedilir(persona):
    with pytest.raises(FormatError):
        persona.add_fact_from_source("x", "ilgi", "")
    with pytest.raises(NotFoundError):
        persona.add_fact_from_source("x", "ilgi", "yok-boyle-kaynak")


def test_kaldirilmis_kaynagin_bilgisi_kartta_yok(persona, hub):
    sid = hub.add_source("belge", "1", None)
    persona.add_fact_from_source("Kaynaktan bilgi", "ilgi", sid)
    assert "Kaynaktan bilgi" in persona.export_identity_card()
    hub.remove_source(sid, "yanlış alındı")
    assert "Kaynaktan bilgi" not in persona.export_identity_card()
    with pytest.raises(FormatError):
        persona.add_fact_from_source("Yeni", "ilgi", sid)


def test_celiski_iki_kaydi_saklar(persona):
    eski = persona.add_fact("Telefonum Realme 7 Pro", "cihazlar", fact_key="telefon")
    yeni = persona.add_fact("Telefonum Mi 10T Pro", "cihazlar", fact_key="telefon")
    assert eski != yeni
    ikisi = {f.fact_id: f for f in persona.list_facts(include_inactive=True)}
    assert set(ikisi) == {eski, yeni}  # ikisi de veritabanında
    assert ikisi[yeni].status == "beyan_edilen"  # yenisi öne alındı
    assert ikisi[eski].status == "eskimis"
    (c,) = persona.list_contradictions()
    assert (c.old_fact.fact_id, c.new_fact.fact_id) == (eski, yeni)
    card = persona.export_identity_card()
    assert "Mi 10T Pro" in card and "Realme" not in card


def test_celiski_cozumu_eskiyi_secebilir(persona):
    eski = persona.add_fact("Şehir: Ankara", "kimlik", fact_key="sehir")
    yeni = persona.add_fact("Şehir: İzmir", "kimlik", fact_key="sehir")
    assert persona.resolve_contradiction(eski) == 1
    assert persona.list_contradictions() == []
    durum = {f.fact_id: f.status for f in persona.list_facts(include_inactive=True)}
    assert durum == {eski: "beyan_edilen", yeni: "eskimis"}
    (kapali,) = persona.list_contradictions(open_only=False)
    assert kapali.chosen_fact_id == eski and kapali.resolved_at
    with pytest.raises(NotFoundError):
        persona.resolve_contradiction(eski)


def test_anahtarsiz_ve_ayni_metin_celiski_sayilmaz(persona):
    a = persona.add_fact("Kahve severim", "tercihler")
    b = persona.add_fact("Çay severim", "tercihler")  # anahtar yok: çelişki aranmaz
    assert persona.list_contradictions() == []
    assert len(persona.list_facts(["tercihler"])) == 2
    k1 = persona.add_fact("Şehir: İzmir", "kimlik", fact_key="sehir")
    k2 = persona.add_fact("Şehir: İzmir", "kimlik", fact_key="sehir")  # aynı metin: tazelenir
    assert k1 == k2 and persona.list_contradictions() == [] and a != b


def test_sure_dolumu_sahte_saatle(persona, clock):
    cihaz = persona.add_fact("Dizüstü bilgisayar: X", "cihazlar")
    kimlik = persona.add_fact("Doğum yılı 1990", "kimlik")
    assert persona.get_fact(cihaz).valid_until == "2027-05-08T12:00:00Z"  # +180 gün
    assert persona.get_fact(kimlik).valid_until is None
    clock.advance(days=179)
    assert persona.check_expiry() == 0
    assert "Dizüstü" in persona.export_identity_card()
    clock.advance(days=2)
    # check_expiry çağrılmadan da süresi dolan bilgi CANLI bölümde yok (okuma anında süzülür);
    # ama sessizce düşmez: AYRI "Süresi doldu - doğrulanmadı" bölümünde görünür.
    kart = persona.export_identity_card()
    canli = kart.split("### Süresi doldu")[0]
    assert "Dizüstü" not in canli and "### Süresi doldu - doğrulanmadı" in kart
    assert "[Cihazlar] Dizüstü bilgisayar: X (beyan" in kart.split("### Süresi doldu")[1]
    assert persona.get_fact(cihaz).status == "beyan_edilen"
    assert persona.check_expiry() == 1
    assert persona.get_fact(cihaz).status == "eskimis"
    assert persona.get_fact(kimlik).status == "beyan_edilen"  # süresiz kategori eskimez
    clock.advance(days=3650)
    assert persona.check_expiry() == 0 and "Doğum yılı" in persona.export_identity_card()


def test_sure_kategori_bazinda_ayarlanir(hub, clock):
    p = Persona(hub, clock=clock, expiry_days={"is": 30, "ilgi": 10, "projeler": None})
    i = p.add_fact("Şirket: Örnek A.Ş.", "is")
    g = p.add_fact("Satranç", "ilgi")
    pr = p.add_fact("Proje X", "projeler")
    assert p.get_fact(i).valid_until == "2026-12-09T12:00:00Z"
    assert p.get_fact(g).valid_until == "2026-11-19T12:00:00Z"
    assert p.get_fact(pr).valid_until is None


def test_guncelle_sil(persona, clock):
    fid = persona.add_fact("Projem: Alfa", "projeler")
    clock.advance(days=100)
    persona.update_fact(fid, statement="Projem: Beta")
    f = persona.get_fact(fid)
    assert f.statement == "Projem: Beta"
    assert f.valid_until == "2027-08-16T12:00:00Z"  # doğrulama tazelendi: +180 gün (bugünden)
    persona.delete_fact(fid)
    assert persona.get_fact(fid).hidden is True
    assert "Beta" not in persona.export_identity_card()
    assert persona.list_facts(include_inactive=True) == []
    with pytest.raises(NotFoundError):
        persona.update_fact(fid, statement="x")


def test_eskimis_guncellenemez(persona, hub):
    _raw_insert(hub, "Eski", "eskimis")
    with pytest.raises(FormatError):
        persona.update_fact("raw-Eski", statement="Yeni")


def test_kart_secilen_kategoriler_ve_bos(persona):
    persona.add_fact("Kimlik bilgisi", "kimlik")
    persona.add_fact("Tercih bilgisi", "tercihler")
    k = persona.export_identity_card(["tercihler"])
    assert "Tercih bilgisi" in k and "Kimlik bilgisi" not in k
    assert "Seçilen kategorilerde bilgi yok." in persona.export_identity_card(["ilgi"])
    with pytest.raises(FormatError):
        persona.export_identity_card(["yok"])


def test_kart_satir_sonu_ve_okuyucu_rolu(persona, hub, veri):
    persona.add_fact("Birinci satır\n## Sahte başlık", "diger")
    hub2_card = PersonaReader(hub).export_identity_card()
    assert "\n## Sahte başlık" not in hub2_card and "\n### Sahte" not in hub2_card  # çok satırlı metin tek satıra indirilir
    ro = Hub.open(veri, write=False)
    try:
        assert "Birinci satır" in PersonaReader(ro).export_identity_card()
    finally:
        ro.close()
