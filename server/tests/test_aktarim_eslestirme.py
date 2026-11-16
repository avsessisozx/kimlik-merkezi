"""Eşleştirme: tek kullanımlık kod, süre, kaba kuvvet sınırı, km1 biçimi (AKTARIM §2)."""
import json
import re

import pytest
from istemci_ornek import Yetkisiz, ham_istek
from kimlikserver.aktarim import eslestirme_coz, eslestirme_metni, yerel_ipv4_adresleri
from kimlikserver.aktarim.eslestirme import EN_FAZLA_YANLIS, EslestirmeKodlari, anahtar_ozeti


class Saat:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _k(a):
    return eslestirme_coz(a.alici.eslestirme_kodu_uret())["k"]


def test_km1_bicimi(aktarim):
    metin = aktarim.alici.eslestirme_kodu_uret(adresler=["192.168.1.20"])
    assert metin.startswith("km1:") and "=" not in metin
    k = eslestirme_coz(metin)
    assert set(k) == {"a", "p", "f", "k", "n"}
    assert k["a"] == ["192.168.1.20"] and k["p"] == aktarim.alici.port
    assert k["f"] == aktarim.alici.parmak_izi and re.fullmatch(r"[0-9a-f]{64}", k["f"])
    assert k["n"] == aktarim.alici.pc_adi and len(k["k"]) >= 20
    assert eslestirme_coz(eslestirme_metni(["10.0.0.5"], 1, "ab", "kod", "Ünlü PC"))["n"] == "Ünlü PC"
    assert all(a.startswith(("10.", "172.", "192.168.")) for a in yerel_ipv4_adresleri())


def test_gecerli_kod_anahtar_bir_kez_ve_ozet_saklanir(aktarim):
    kod = _k(aktarim)
    i = aktarim.istemci()
    anahtar = i.eslestir(kod)
    assert re.fullmatch(r"[0-9a-f]{64}", anahtar)            # 32 bayt
    (d,) = aktarim.hub.cihazlar()
    assert d["device_id"] == aktarim.cihaz and d["platform"] == "android" and d["paired_at"]
    assert aktarim.hub.cihaz_dogrula(aktarim.cihaz, anahtar_ozeti(anahtar))
    # anahtarın kendisi hiçbir yerde yok: veritabanında yalnız özet
    ham = aktarim.hub._conn.execute("SELECT key_hash FROM devices").fetchone()[0]
    assert ham != anahtar and ham == anahtar_ozeti(anahtar)
    # ikinci kullanım
    with pytest.raises(Yetkisiz):
        aktarim.istemci().eslestir(kod)
    # eşleşen anahtar çalışır
    assert i.durum("11111111-1111-4111-8111-111111111111") == ("yok", 0)


def test_eskimis_kod(aktarim):
    saat = Saat()
    aktarim.alici.kodlar = EslestirmeKodlari(saat)
    kod = _k(aktarim)
    saat.t += 601
    with pytest.raises(Yetkisiz):
        aktarim.istemci().eslestir(kod)
    assert aktarim.hub.cihazlar() == []
    saat.t = 1000.0
    kod = _k(aktarim)
    saat.t += 599
    aktarim.istemci().eslestir(kod)    # 10 dakika içinde geçerli


def test_bes_yanlis_deneme_kodu_oldurur(aktarim):
    kod = _k(aktarim)
    for _ in range(EN_FAZLA_YANLIS):
        with pytest.raises(Yetkisiz):
            aktarim.istemci().eslestir("yanlis-kod")
    with pytest.raises(Yetkisiz):          # artık doğru kod bile geçersiz
        aktarim.istemci().eslestir(kod)
    assert aktarim.hub.cihazlar() == []
    assert aktarim.alici.durum()["eslestirme_kodu_gecerli"] is False
    kod2 = _k(aktarim)                     # yeni kod yeniden çalışır
    aktarim.istemci().eslestir(kod2)


def test_dort_yanlis_sonra_dogru_calisir(aktarim):
    kod = _k(aktarim)
    for _ in range(EN_FAZLA_YANLIS - 1):
        with pytest.raises(Yetkisiz):
            aktarim.istemci().eslestir("yanlis")
    aktarim.istemci().eslestir(kod)


def test_kod_uretilmeden_eslestirme_yok(aktarim):
    with pytest.raises(Yetkisiz):
        aktarim.istemci().eslestir("herhangi")


@pytest.mark.parametrize("govde,beklenen", [
    (b"bu json degil", 400),
    (b"[1,2]", 400),
    (json.dumps({"cihaz_id": "../x", "ad": "a", "kod": "k"}).encode(), 400),
    (json.dumps({"cihaz_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7", "ad": "", "kod": "k"}).encode(), 400),
    (b"x" * 5000, 413),
])
def test_eslestir_bozuk_govde(aktarim, govde, beklenen):
    _k(aktarim)
    kod, _, _ = ham_istek(aktarim.alici.port, "POST", "/eslestir", {"Content-Length": str(len(govde))}, govde)
    assert kod == beklenen
    assert aktarim.hub.cihazlar() == []


def test_yeniden_eslesme_anahtari_yeniler_eski_gecersiz(aktarim):
    eski = aktarim.eslesmis()
    yeni = aktarim.eslesmis()
    assert yeni.anahtar != eski.anahtar
    with pytest.raises(Yetkisiz):
        eski.durum("11111111-1111-4111-8111-111111111111")
    yeni.durum("11111111-1111-4111-8111-111111111111")
