"""Kimlik, yol güvenliği, boyut sınırları (AKTARIM §3). Reddedilen isteklerde diske 0 bayt yazılır."""
import hashlib
import json
import socket
import ssl
import sys
import uuid

import pytest
from istemci_ornek import Istemci, Yasak, Yetkisiz, ham_istek, kutu_dosyasi
from kimlikserver.aktarim.eslestirme import anahtar_ozeti

DOSYA = "11111111-1111-4111-8111-111111111111"


def diskte(a):
    return a.dosyalar("gelen_aktarim") + a.dosyalar("aktarim/gecici")


def put_basliklari(cihaz, anahtar, veri, bas=0, toplam=None, sha=None):
    toplam = toplam or len(veri)
    return {"Authorization": f"Bearer {anahtar}", "X-Cihaz": cihaz,
            "Content-Range": f"bytes {bas}-{bas + len(veri) - 1}/{toplam}",
            "X-Sha256": sha or hashlib.sha256(veri).hexdigest(), "Content-Length": str(len(veri))}


def test_durum_kimliksiz_yalniz_protokol_kimlikli_ayrinti(aktarim):
    d = Istemci("127.0.0.1", aktarim.alici.port, aktarim.alici.parmak_izi, aktarim.cihaz).pc_durumu()
    assert d == {"protokol": 1}                         # PC adı/sürüm sızmaz
    kod, _, govde = ham_istek(aktarim.alici.port, "GET", "/durum", {"Authorization": "Bearer " + "0" * 64,
                                                                    "X-Cihaz": aktarim.cihaz})
    assert kod == 200 and json.loads(govde) == {"protokol": 1}     # yanlış kimlik de aynı asgari yanıt
    i = aktarim.eslesmis()
    kod, _, govde = ham_istek(aktarim.alici.port, "GET", "/durum", {"Authorization": f"Bearer {i.anahtar}",
                                                                    "X-Cihaz": aktarim.cihaz})
    assert json.loads(govde) == {"protokol": 1, "surum": aktarim.alici.surum, "pc_adi": aktarim.alici.pc_adi}


@pytest.mark.parametrize("yontem", ["GET", "HEAD", "PUT", "POST", "DELETE", "PATCH", "OPTIONS"])
@pytest.mark.parametrize("yol", ["/giden/x", "/giden/", "/giden/{c}/{d}.jsonl", "/giden/../x"])
def test_kimliksiz_her_istek_ayni_401(aktarim, yontem, yol):
    yol = yol.format(c=aktarim.cihaz, d=DOSYA)
    kod, _, govde = ham_istek(aktarim.alici.port, yontem, yol, {})
    assert kod == 401
    if yontem != "HEAD":
        assert json.loads(govde) == {"hata": "yetkisiz"}


def test_eksik_yanlis_iptal_anahtar_401_ve_sifir_bayt(aktarim):
    i = aktarim.eslesmis()
    veri = kutu_dosyasi(aktarim.cihaz, DOSYA, 3)
    yol = f"/giden/{aktarim.cihaz}/{DOSYA}.jsonl"
    port = aktarim.alici.port
    # anahtarsız, başlıksız cihaz, yanlış anahtar, başka cihaz kimliği
    adaylar = [
        {k: v for k, v in put_basliklari(aktarim.cihaz, i.anahtar, veri).items() if k != "Authorization"},
        {k: v for k, v in put_basliklari(aktarim.cihaz, i.anahtar, veri).items() if k != "X-Cihaz"},
        put_basliklari(aktarim.cihaz, "0" * 64, veri),
        put_basliklari(str(uuid.uuid4()), i.anahtar, veri),
        put_basliklari(aktarim.cihaz, "kisa", veri),
    ]
    for b in adaylar:
        for yontem in ("PUT", "HEAD"):
            kod, _, _ = ham_istek(port, yontem, yol, b, veri if yontem == "PUT" else None)
            assert kod == 401, (yontem, b.keys())
    assert diskte(aktarim) == []
    # iptal edilmiş anahtar
    assert aktarim.hub.cihaz_iptal(aktarim.cihaz)
    kod, _, _ = ham_istek(port, "PUT", yol, put_basliklari(aktarim.cihaz, i.anahtar, veri), veri)
    assert kod == 401 and diskte(aktarim) == []
    with pytest.raises(Yetkisiz):
        i.durum(DOSYA)


def test_baska_cihazin_yoluna_yazma_403(aktarim):
    i = aktarim.eslesmis()
    baska = str(uuid.uuid4())
    veri = kutu_dosyasi(baska, DOSYA, 2)
    kod, _, _ = ham_istek(aktarim.alici.port, "PUT", f"/giden/{baska}/{DOSYA}.jsonl",
                          put_basliklari(aktarim.cihaz, i.anahtar, veri), veri)
    assert kod == 403 and diskte(aktarim) == []
    kod, _, _ = ham_istek(aktarim.alici.port, "HEAD", f"/giden/{baska}/{DOSYA}.jsonl",
                          {"Authorization": f"Bearer {i.anahtar}", "X-Cihaz": aktarim.cihaz})
    assert kod == 403


@pytest.mark.parametrize("yol", [
    "/giden/../../etc/passwd",
    "/giden/{c}/../{d}.jsonl",
    "/giden/{c}/{d}.jsonl/../x",
    "/giden/{c}/..%2f..%2fx.jsonl",
    "/giden/{c}/%2e%2e%2f{d}.jsonl",
    "/giden/{c}/not-a-uuid.jsonl",
    "/giden/{c}/{d}.txt",
    "/giden/{c}/{d}.jsonl?x=1",
    "/giden/{c}/{D}.jsonl",
    "/giden//{d}.jsonl",
    "/giden/{c}/{d}.jsonl/",
    "/giden/{c}",
    "/giden/",
])
def test_yol_gezinme_ve_uuid_olmayan_adlar_400(aktarim, yol):
    i = aktarim.eslesmis()
    veri = kutu_dosyasi(aktarim.cihaz, DOSYA, 2)
    yol = yol.format(c=aktarim.cihaz, d=DOSYA, D="abcdefab-1111-4111-8111-abcdefabcdef".upper())
    kod, _, _ = ham_istek(aktarim.alici.port, "PUT", yol, put_basliklari(aktarim.cihaz, i.anahtar, veri), veri)
    assert kod == 400, yol
    assert diskte(aktarim) == []
    assert not [p for p in aktarim.veri.rglob("*") if p.name in ("passwd", "x.jsonl")]


def test_baska_yontem_ve_yol_reddi(aktarim):
    i = aktarim.eslesmis()
    b = {"Authorization": f"Bearer {i.anahtar}", "X-Cihaz": aktarim.cihaz}
    port = aktarim.alici.port
    assert ham_istek(port, "GET", f"/giden/{aktarim.cihaz}/{DOSYA}.jsonl", b)[0] == 405
    assert ham_istek(port, "DELETE", f"/giden/{aktarim.cihaz}/{DOSYA}.jsonl", b)[0] == 405
    assert ham_istek(port, "GET", "/baska", b)[0] == 404
    assert ham_istek(port, "GET", "/eslestir", b)[0] == 405


@pytest.fixture
def kucuk(tmp_path):
    from conftest import AktarimDunyasi

    d = AktarimDunyasi(tmp_path, sinirlar={"dosya_en_fazla": 4096, "parca_en_fazla": 1024, "baslik_en_fazla": 2048})
    yield d
    d.kapat()


def test_parca_ve_dosya_ust_siniri(kucuk):
    i = kucuk.eslesmis()
    port = kucuk.alici.port
    veri = b"x" * 2000
    kod, _, _ = ham_istek(port, "PUT", f"/giden/{kucuk.cihaz}/{DOSYA}.jsonl",
                          put_basliklari(kucuk.cihaz, i.anahtar, veri, toplam=2000), veri)
    assert kod == 413                                    # parça > 1024
    veri = b"x" * 1000
    kod, _, _ = ham_istek(port, "PUT", f"/giden/{kucuk.cihaz}/{DOSYA}.jsonl",
                          put_basliklari(kucuk.cihaz, i.anahtar, veri, toplam=5000), veri)
    assert kod == 413                                    # dosya > 4096
    assert diskte(kucuk) == []


def test_baslik_boyutu_siniri(kucuk):
    i = kucuk.eslesmis()
    b = {"Authorization": f"Bearer {i.anahtar}", "X-Cihaz": kucuk.cihaz, "X-Sisirilmis": "a" * 3000}
    assert ham_istek(kucuk.alici.port, "HEAD", f"/giden/{kucuk.cihaz}/{DOSYA}.jsonl", b)[0] == 431


def test_icerik_uzunlugu_zorunlu_ve_aralik_tutarli(aktarim):
    i = aktarim.eslesmis()
    veri = kutu_dosyasi(aktarim.cihaz, DOSYA, 2)
    yol = f"/giden/{aktarim.cihaz}/{DOSYA}.jsonl"
    b = put_basliklari(aktarim.cihaz, i.anahtar, veri)
    assert ham_istek(aktarim.alici.port, "PUT", yol, {**b, "Content-Range": "bytes 0-5/9999"}, veri)[0] == 400
    assert ham_istek(aktarim.alici.port, "PUT", yol, {**b, "X-Sha256": "xyz"}, veri)[0] == 400
    assert ham_istek(aktarim.alici.port, "PUT", yol, {k: v for k, v in b.items() if k != "Content-Range"}, veri)[0] == 400
    assert diskte(aktarim) == []


def test_yavas_istemci_zaman_asimi(tmp_path):
    from conftest import AktarimDunyasi
    import time

    d = AktarimDunyasi(tmp_path, sinirlar={"soket_zaman_asimi_s": 0.5, "el_sikisma_zaman_asimi_s": 0.5})
    try:
        i = d.eslesmis()
        # el sıkışmayı hiç yapmayan bağlantı: sunucu bırakır, başka istekleri engellemez
        s = socket.create_connection(("127.0.0.1", d.alici.port))
        time.sleep(0.9)
        s.settimeout(2)
        try:
            kapali = s.recv(1) == b""
        except (ConnectionError, socket.timeout):
            kapali = isinstance(sys.exc_info()[1], ConnectionError)
        assert kapali, "el sıkışmayan bağlantı sunucu tarafından kapatılmadı"
        s.close()
        assert i.durum(DOSYA) == ("yok", 0)
        # gövdeyi yarıda bırakan/yavaş istemci: hiçbir şey yazılmaz
        veri = kutu_dosyasi(d.cihaz, DOSYA, 3)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ham = socket.create_connection(("127.0.0.1", d.alici.port))
        t = ctx.wrap_socket(ham)
        b = put_basliklari(d.cihaz, i.anahtar, veri)
        istek = "PUT /giden/%s/%s.jsonl HTTP/1.1\r\nHost: x\r\n" % (d.cihaz, DOSYA)
        istek += "".join(f"{k}: {v}\r\n" for k, v in b.items()) + "\r\n"
        t.sendall(istek.encode() + veri[:20])
        time.sleep(1.2)                                   # gövde tamamlanmadı, sunucu zaman aşımına uğradı
        t.close()
        assert diskte(d) == []
        assert i.durum(DOSYA) == ("yok", 0)
    finally:
        d.kapat()


def test_yeni_eslestirme_kodu_oncekini_gecersiz_kilar():
    from kimlikserver.aktarim.eslestirme import EslestirmeKodlari
    k = EslestirmeKodlari()
    eski = k.uret()
    yeni = k.uret()
    assert eski != yeni
    assert k.tuket(eski) is False
    assert k.tuket(yeni) is True
