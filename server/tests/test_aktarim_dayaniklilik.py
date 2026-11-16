"""Güvenlik incelemesi düzeltmeleri: yavaş istemci, kotalar, derin JSON, sertifika, UUID/sayı katılığı,
tek doğrulayıcı eşliği, dizin izinleri."""
import hashlib
import json
import logging
import os
import socket
import ssl
import stat
import sys
import time
import uuid
from pathlib import Path

import pytest
from conftest import AktarimDunyasi
from istemci_ornek import ham_istek, kutu_dosyasi
from kimlikserver.aktarim import AktarimAlici, eslestirme
from kimlikserver.aktarim import sertifika as sert_mod
from kimlikserver.aktarim.alici import UUID_DOSYA_RE, YENILENDI_UYARISI

from test_aktarim_kimlik import DOSYA, put_basliklari

FIX = Path(__file__).resolve().parents[2] / "importers" / "fixtures" / "android_giden"


def tls(port, el_sik=True):
    ham = socket.create_connection(("127.0.0.1", port), timeout=5)
    if not el_sik:
        return ham
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx.wrap_socket(ham)


def kapandi(s, en_gec=4.0):
    """Sunucu bağlantıyı en geç `en_gec` sn içinde kapattı mı?"""
    s.settimeout(en_gec)
    try:
        return s.recv(1) == b""
    except socket.timeout:
        return False
    except (OSError, ssl.SSLError):
        return True


def yeni(tmp_path, **sinirlar):
    return AktarimDunyasi(tmp_path, sinirlar=sinirlar)


# ----------------------------------------------------------------------------------- 1) yavaş istemci
def test_yavas_baslik_baytbayt_sure_icinde_kesilir_gecerli_istemci_hizmet_alir(tmp_path):
    d = yeni(tmp_path, baslik_toplam_zaman_asimi_s=1.0)
    try:
        i = d.eslesmis()
        yavaslar = [tls(d.alici.port) for _ in range(4)]            # IP başına sınır: 4
        for s in yavaslar:
            s.sendall(b"HEAD /giden/")                             # istek satırı bitmiyor
        t0 = time.monotonic()
        for s in yavaslar:                                         # damla damla devam: toplam süre yine de aşılır
            try:
                for _ in range(8):
                    s.sendall(b"x")
                    time.sleep(0.2)
            except (OSError, ssl.SSLError):
                break
        assert all(kapandi(s, 3) for s in yavaslar)
        assert time.monotonic() - t0 < 4.5                          # 1 sn sınırı + payanda; damlalar süreyi uzatmadı
        assert i.durum(DOSYA) == ("yok", 0)                         # kesilince geçerli istemci hizmet alır
    finally:
        d.kapat()


def test_ip_basina_dort_baglanti_besinci_reddedilir(tmp_path):
    d = yeni(tmp_path, el_sikisma_zaman_asimi_s=2.0)
    try:
        i = d.eslesmis()
        tutan = [tls(d.alici.port, el_sik=False) for _ in range(4)]   # el sıkışmayan 4 bağlantı slot tutar
        time.sleep(0.2)
        besinci = tls(d.alici.port, el_sik=False)
        assert kapandi(besinci, 1.0)                                  # hemen kapatılır (kabul edilmez)
        assert all(kapandi(s, 4) for s in tutan)                      # el sıkışma sınırı: 2 sn'de kesilir
        assert i.durum(DOSYA) == ("yok", 0)
        i.kapat()
        for _ in range(40):                                           # kapanan bağlantılar sayaçtan düşer
            if not d.alici._srv._ip_sayac:
                break
            time.sleep(0.05)
        assert d.alici._srv._ip_sayac == {}
    finally:
        d.kapat()


def test_toplam_32_baglanti_sinirinda_33uncu_reddedilir(tmp_path):
    d = yeni(tmp_path, el_sikisma_zaman_asimi_s=2.0, ip_basina_baglanti=100)
    try:
        i = d.eslesmis()
        tutan = [tls(d.alici.port, el_sik=False) for _ in range(32)]
        time.sleep(0.3)
        fazla = tls(d.alici.port, el_sik=False)
        assert kapandi(fazla, 1.0)                                    # 33. bağlantı kabul edilmez
        assert all(kapandi(s, 5) for s in tutan)
        assert i.durum(DOSYA) == ("yok", 0)                           # yer açılınca geçerli istemci hizmet alır
    finally:
        d.kapat()


def test_bosta_keepalive_kapanir(tmp_path):
    d = yeni(tmp_path, bosta_zaman_asimi_s=0.6)
    try:
        s = tls(d.alici.port)
        s.sendall(b"GET /durum HTTP/1.1\r\nHost: x\r\n\r\n")
        s.settimeout(3)
        yanit = b""
        while not yanit.endswith(b"}"):
            yanit += s.recv(4096)
        assert yanit.startswith(b"HTTP/1.1 200")
        t0 = time.monotonic()
        assert kapandi(s, 5) and time.monotonic() - t0 < 3
    finally:
        d.kapat()


def test_govde_toplam_zaman_asimi_damlayan_istemci_kesilir(tmp_path):
    d = yeni(tmp_path, govde_toplam_zaman_asimi_s=1.0)
    try:
        i = d.eslesmis()
        veri = kutu_dosyasi(d.cihaz, DOSYA, 3)
        b = put_basliklari(d.cihaz, i.anahtar, veri)
        s = tls(d.alici.port)
        s.sendall(("PUT /giden/%s/%s.jsonl HTTP/1.1\r\nHost: x\r\n" % (d.cihaz, DOSYA)
                   + "".join(f"{k}: {v}\r\n" for k, v in b.items()) + "\r\n").encode())
        t0 = time.monotonic()
        try:
            for k in range(30):                                       # her 0.25 sn'de 1 bayt: soket zaman aşımı hiç tetiklenmez
                s.sendall(veri[k:k + 1])
                time.sleep(0.25)
        except (OSError, ssl.SSLError):
            pass
        assert kapandi(s, 3) and time.monotonic() - t0 < 5
        assert d.dosyalar("gelen_aktarim") == [] and d.dosyalar("aktarim/gecici") == []
    finally:
        d.kapat()


# ----------------------------------------------------------------------------------- 2) kotalar
def test_cihaz_basina_acik_yukleme_sinirli_mevcutlar_surer(tmp_path):
    d = yeni(tmp_path, cihaz_basina_yarim_yukleme=2)
    try:
        i = d.eslesmis(parca_bayt=100)
        a, b, c = d.dosya_yaz(kayit=10), d.dosya_yaz(kayit=10), d.dosya_yaz(kayit=10)
        i.dosya_gonder(a, en_fazla_parca=1)
        i.dosya_gonder(b, en_fazla_parca=1)
        with pytest.raises(RuntimeError, match="429"):
            i.dosya_gonder(c)
        assert not (d.veri / "aktarim/gecici" / d.cihaz / f"{c.stem}.part").exists()
        assert i.dosya_gonder(a)["sonuc"] == "var"                     # mevcut yükleme sürdü, tamamlandı
        assert i.dosya_gonder(c, en_fazla_parca=1)["sonuc"] == "kesildi"   # yer açıldı
    finally:
        d.kapat()


def test_toplam_gecici_bayt_siniri(tmp_path):
    d = yeni(tmp_path, gecici_toplam_en_fazla=150)
    try:
        i = d.eslesmis(parca_bayt=200)
        a, b = d.dosya_yaz(kayit=10), d.dosya_yaz(kayit=10)
        i.dosya_gonder(a, en_fazla_parca=1)                            # 200 bayt >= 150
        with pytest.raises(RuntimeError, match="507"):
            i.dosya_gonder(b)
        assert i.dosya_gonder(a)["sonuc"] == "var"
        assert i.dosya_gonder(b)["sonuc"] == "var"                     # alan boşalınca yenisi de gider
    finally:
        d.kapat()


def test_bos_disk_denetimi_507(tmp_path):
    d = yeni(tmp_path, bos_disk_en_az=10 ** 15)
    try:
        i = d.eslesmis()
        with pytest.raises(RuntimeError, match="507"):
            i.dosya_gonder(d.dosya_yaz())
        assert d.dosyalar("aktarim/gecici") == [] and d.dosyalar("gelen_aktarim") == []
    finally:
        d.kapat()


def test_eski_gecici_dosyalar_temizlenir(aktarim):
    dizin = aktarim.veri / "aktarim/gecici" / aktarim.cihaz
    dizin.mkdir(parents=True)
    eski, taze = dizin / f"{uuid.uuid4()}.part", dizin / f"{uuid.uuid4()}.part"
    for p in (eski, taze, eski.with_suffix(".sha")):
        p.write_bytes(b"x")
    gec = time.time() - 8 * 86400
    os.utime(eski, (gec, gec))
    os.utime(eski.with_suffix(".sha"), (gec, gec))
    assert aktarim.alici.eski_gecicileri_temizle() == 2
    assert not eski.exists() and not eski.with_suffix(".sha").exists() and taze.exists()
    # alıcı başlarken de temizler
    os.utime(taze, (gec, gec))
    aktarim.alici.durdur()
    aktarim.yeni_alici()
    assert not taze.exists()


def test_kilit_sozlugu_kuculur(aktarim):
    i = aktarim.eslesmis(parca_bayt=200)
    for _ in range(3):
        i.dosya_gonder(aktarim.dosya_yaz(kayit=6))
    yarim = aktarim.dosya_yaz(kayit=6)
    i.dosya_gonder(yarim, en_fazla_parca=1)                            # tamamlanmayan da sözlükte kalmaz
    assert aktarim.alici._kilitler == {}


# ----------------------------------------------------------------------------------- 3) derin JSON ve genel hata
def test_derin_json_alicida_422_gecici_temiz(aktarim):
    i = aktarim.eslesmis()
    dosya = str(uuid.uuid4())
    b = kutu_dosyasi(aktarim.cihaz, dosya, 1).splitlines()
    b.insert(1, b"[" * 200000 + b"]" * 200000)
    veri = b"\n".join(b) + b"\n"
    kod, _, _ = ham_istek(aktarim.alici.port, "PUT", f"/giden/{aktarim.cihaz}/{dosya}.jsonl",
                          put_basliklari(aktarim.cihaz, i.anahtar, veri), veri)
    assert kod == 422
    assert aktarim.dosyalar("aktarim/gecici") == [] and aktarim.dosyalar("gelen_aktarim") == []


def test_beklenmeyen_hata_yarim_dosyayi_temizler(aktarim, monkeypatch):
    import kimlikimport.android_giden as ag

    def patla(*a, **k):
        raise RuntimeError("beklenmeyen")

    monkeypatch.setattr(ag, "dosya_dogrula", patla)
    i = aktarim.eslesmis()
    yol = aktarim.dosya_yaz(kayit=3)
    veri = yol.read_bytes()
    kod, _, _ = ham_istek(aktarim.alici.port, "PUT", f"/giden/{aktarim.cihaz}/{yol.stem}.jsonl",
                          put_basliklari(aktarim.cihaz, i.anahtar, veri), veri)
    assert kod == 500 and aktarim.dosyalar("aktarim/gecici") == [] and aktarim.dosyalar("gelen_aktarim") == []


# ----------------------------------------------------------------------------------- 4) sertifika
def test_ilk_uretim_yenilendi_degil_repr_parola_icermez(tmp_path):
    from kimlikcore.sifreleme import SahteSaglayici

    s = sert_mod.hazirla(tmp_path, SahteSaglayici("g"))
    assert s.yeniden_uretildi is False and s.parola
    assert s.parola.decode() not in repr(s) and "parola" not in repr(s)


@pytest.mark.parametrize("bozma", ["anahtar_bozuk", "eslesmeyen_cift", "sertifika_eksik"])
def test_acilamayan_cift_sessizce_yenilenmez(tmp_path, bozma, caplog):
    caplog.set_level(logging.WARNING)
    a = sert_mod.hazirla(tmp_path / "a", None)
    dizin = tmp_path / "a" / "aktarim"
    if bozma == "anahtar_bozuk":
        (dizin / "anahtar.pem").write_bytes(b"bozuk")
    elif bozma == "eslesmeyen_cift":
        baska = sert_mod.hazirla(tmp_path / "b", None)
        (dizin / "sertifika.pem").write_bytes(baska.sertifika_yolu.read_bytes())
    else:
        (dizin / "sertifika.pem").unlink()
    eski_fp = a.parmak_izi
    y = sert_mod.hazirla(tmp_path / "a", None)
    assert y.yeniden_uretildi is True and y.parmak_izi != eski_fp
    assert [p for p in dizin.iterdir() if ".eski-" in p.name], "eski dosyalar saklanmalı"
    assert "yeniden eşleşmeli" in caplog.text
    # yeni çift tutarlı: sonraki açılışta yenilenmiş sayılmaz
    z = sert_mod.hazirla(tmp_path / "a", None)
    assert z.yeniden_uretildi is False and z.parmak_izi == y.parmak_izi


def test_durumda_sertifika_yenilendi_uyarisi(tmp_path):
    sert_mod.hazirla(tmp_path / "veri", None)
    (tmp_path / "veri" / "aktarim" / "anahtar.pem").write_bytes(b"bozuk")
    a = AktarimAlici(None, tmp_path / "veri", port=0, adres="127.0.0.1", bulma_port=None, saglayici=None)
    a.baslat()
    try:
        st = a.durum()
        assert st["sertifika_yenilendi"] is True and st["uyari"] == YENILENDI_UYARISI
    finally:
        a.durdur()
    a2 = AktarimAlici(None, tmp_path / "veri", port=0, adres="127.0.0.1", bulma_port=None, saglayici=None)
    a2.baslat()
    try:
        assert a2.durum()["sertifika_yenilendi"] is False and a2.durum()["uyari"] is None
    finally:
        a2.durdur()


def test_cift_atomik_yazilir_gecici_dosya_kalmaz(tmp_path):
    sert_mod.hazirla(tmp_path, None)
    assert not [p for p in (tmp_path / "aktarim").iterdir() if p.name.endswith(".yeni")]


# ----------------------------------------------------------------------------------- 5) UUID katılığı
def test_uuid_fullmatch():
    u = str(uuid.uuid4())
    assert eslestirme.UUID_RE.fullmatch(u) and not eslestirme.UUID_RE.fullmatch(u + "\n")
    assert UUID_DOSYA_RE.fullmatch(u + ".jsonl") and not UUID_DOSYA_RE.fullmatch(u + ".jsonl\n")
    assert eslestirme.eslestir({"cihaz_id": u + "\n", "ad": "a", "kod": "k"}, eslestirme.EslestirmeKodlari(),
                               lambda *a: None, "pc")[0] == 400


def test_eslestirme_http_cihaz_id_satir_sonu_400(aktarim):
    aktarim.alici.eslestirme_kodu_uret()
    govde = json.dumps({"cihaz_id": str(uuid.uuid4()) + "\n", "ad": "a", "kod": "k"}).encode()
    assert ham_istek(aktarim.alici.port, "POST", "/eslestir", {"Content-Length": str(len(govde))}, govde)[0] == 400
    assert aktarim.hub.cihazlar() == []


# ----------------------------------------------------------------------------------- 6) tek doğrulayıcı eşliği
BOZUKLAR = ["22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333",
            "44444444-4444-4444-8444-444444444444", "55555555-5555-4555-8555-555555555555",
            "66666666-6666-4666-8666-666666666666"]


@pytest.mark.parametrize("dosya_id", BOZUKLAR)
def test_icaktarici_reddedecegi_dosya_alicida_da_422(aktarim, dosya_id):
    """İçe aktarıcının reddettiği her fixture alıcıda 422 alır; telefon dosyayı silmez."""
    i = aktarim.eslesmis()
    metin = (FIX / f"{dosya_id}.jsonl").read_text(encoding="utf-8").replace("7c9e6679-7425-40de-944b-e07fc1f90ae7", aktarim.cihaz)
    yol = aktarim.cikis / f"{dosya_id}.jsonl"
    yol.write_text(metin, encoding="utf-8")
    assert i.dosya_gonder(yol)["sonuc"] == "reddedildi"
    assert yol.exists() and i.silinenler == []
    assert aktarim.dosyalar("aktarim/gecici") == [] and aktarim.dosyalar("gelen_aktarim") == []
    assert aktarim.hub.aktarim_dosyasi_var(aktarim.cihaz, dosya_id) is None


@pytest.mark.parametrize("degis", [
    ("kategori", lambda s: s.replace('"kategori": "notlar"', '"kategori": "persona"', 1)),
    ("ts", lambda s: s.replace('"ts": "', '"ts": "bozuk', 1)),
    ("yuk", lambda s: s.replace('"yuk": {}', '"yuk": 5', 1)),
    ("uzun", lambda s: s.replace('"metin": "', '"metin": "' + "a" * (4 * 1024 * 1024), 1)),
], ids=lambda d: d[0])
def test_alan_kurallari_alicida_da_gecerli(aktarim, degis):
    i = aktarim.eslesmis()
    dosya = str(uuid.uuid4())
    metin = kutu_dosyasi(aktarim.cihaz, dosya, 2).decode()
    metin = degis[1](metin)
    yol = aktarim.cikis / f"{dosya}.jsonl"
    yol.write_text(metin, encoding="utf-8")
    assert i.dosya_gonder(yol)["sonuc"] == "reddedildi"


def test_saglam_fixture_alicida_kabul(aktarim):
    i = aktarim.eslesmis()
    dosya_id = "11111111-1111-4111-8111-111111111111"
    yol = aktarim.cikis / f"{dosya_id}.jsonl"
    yol.write_text((FIX / f"{dosya_id}.jsonl").read_text(encoding="utf-8").replace(
        "7c9e6679-7425-40de-944b-e07fc1f90ae7", aktarim.cihaz), encoding="utf-8")
    assert i.dosya_gonder(yol)["sonuc"] == "var"


# ----------------------------------------------------------------------------------- 8) kod geçersizlik nedeni
def test_durumda_kod_gecersizlik_nedeni(aktarim):
    from kimlikserver.aktarim.eslestirme import EslestirmeKodlari

    class Saat:
        t = 0.0

        def __call__(self):
            return self.t

    saat = Saat()
    aktarim.alici.kodlar = EslestirmeKodlari(saat)
    st = aktarim.alici.durum
    assert (st()["eslestirme_kodu_gecerli"], st()["eslestirme_kodu_gecersizlik_nedeni"]) == (False, "uretilmedi")
    kod = eslestirme.eslestirme_coz(aktarim.alici.eslestirme_kodu_uret())["k"]
    assert (st()["eslestirme_kodu_gecerli"], st()["eslestirme_kodu_gecersizlik_nedeni"]) == (True, None)
    saat.t = 601
    assert st()["eslestirme_kodu_gecersizlik_nedeni"] == "sure_doldu" and st()["eslestirme_kodu_gecerli"] is False
    saat.t = 0
    aktarim.alici.eslestirme_kodu_uret()
    for _ in range(5):
        aktarim.alici.kodlar.tuket("yanlis")
    assert st()["eslestirme_kodu_gecersizlik_nedeni"] == "cok_yanlis_deneme"
    kod = eslestirme.eslestirme_coz(aktarim.alici.eslestirme_kodu_uret())["k"]
    assert aktarim.alici.kodlar.tuket(kod)
    assert st()["eslestirme_kodu_gecersizlik_nedeni"] == "kullanildi" and not st()["eslestirme_kodu_gecerli"]


# ----------------------------------------------------------------------------------- 9) sayı katılığı, toplam tutarlılığı
@pytest.mark.parametrize("deger", ["+5", "0x5", "1_0", "5.0", "-1", "5 5", ""])
def test_content_length_kati_rakam(aktarim, deger):
    i = aktarim.eslesmis()
    b = {"Authorization": f"Bearer {i.anahtar}", "X-Cihaz": aktarim.cihaz, "Content-Length": deger,
         "Content-Range": "bytes 0-4/10", "X-Sha256": "0" * 64}
    kod, _, _ = ham_istek(aktarim.alici.port, "PUT", f"/giden/{aktarim.cihaz}/{DOSYA}.jsonl", b, b"")
    assert kod == 411
    assert aktarim.dosyalar("aktarim/gecici") == []


@pytest.mark.parametrize("aralik", ["bytes +0-4/10", "bytes 0-4/1_0", "bytes 0 -4/10", "bytes ٠-٤/١٠"])
def test_content_range_kati_rakam(aktarim, aralik):
    i = aktarim.eslesmis()
    veri = b"x" * 5
    b = put_basliklari(aktarim.cihaz, i.anahtar, veri)
    try:
        kod, _, _ = ham_istek(aktarim.alici.port, "PUT", f"/giden/{aktarim.cihaz}/{DOSYA}.jsonl",
                              {**b, "Content-Range": aralik}, veri)
    except UnicodeEncodeError:
        return   # istemci kitaplığı bile göndermiyor
    assert kod == 400 and aktarim.dosyalar("aktarim/gecici") == []


def test_content_range_toplami_parcalar_arasinda_degisirse_422(aktarim):
    i = aktarim.eslesmis(parca_bayt=100)
    yol = aktarim.dosya_yaz(kayit=10)
    veri = yol.read_bytes()
    sha = hashlib.sha256(veri).hexdigest()
    url = f"/giden/{aktarim.cihaz}/{yol.stem}.jsonl"
    b = put_basliklari(aktarim.cihaz, i.anahtar, veri[:100], bas=0, toplam=len(veri), sha=sha)
    assert ham_istek(aktarim.alici.port, "PUT", url, b, veri[:100])[0] == 200
    b2 = put_basliklari(aktarim.cihaz, i.anahtar, veri[100:200], bas=100, toplam=len(veri) + 7, sha=sha)
    assert ham_istek(aktarim.alici.port, "PUT", url, b2, veri[100:200])[0] == 422
    assert aktarim.dosyalar("aktarim/gecici") == []                    # tutarsız yarım yükleme silindi
    assert i.dosya_gonder(yol)["sonuc"] == "var"                       # baştan başlayınca tamamlanır


# ----------------------------------------------------------------------------------- 10) dizin izinleri
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX izinleri")
def test_klasorler_0700(aktarim):
    i = aktarim.eslesmis(parca_bayt=200)
    y1, y2 = aktarim.dosya_yaz(kayit=6), aktarim.dosya_yaz(kayit=6)
    i.dosya_gonder(y1)
    i.dosya_gonder(y2, en_fazla_parca=1)
    for p in (aktarim.veri / "gelen_aktarim", aktarim.veri / "gelen_aktarim" / aktarim.cihaz,
              aktarim.veri / "aktarim", aktarim.veri / "aktarim" / "gecici",
              aktarim.veri / "aktarim" / "gecici" / aktarim.cihaz):
        assert stat.S_IMODE(p.stat().st_mode) == 0o700, p
