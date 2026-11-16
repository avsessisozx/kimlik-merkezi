"""Aktarım, devam, tekrar, içe alma, doğrulama (AKTARIM §3, §4)."""
import hashlib
import logging
import threading
import time
import uuid

import pytest
from istemci_ornek import Istemci, ParmakIziUyusmadi, ham_istek, kutu_dosyasi, olay_kimlikleri
from kimlikserver.aktarim import gelenleri_ice_al

from test_aktarim_kimlik import put_basliklari


def olay_anahtarlari(hub):
    return {e.payload["dosya_id"] + ":" + e.text for e in hub.timeline(limit=100000)}


def test_tam_aktarim_ve_ice_alma(aktarim):
    i = aktarim.eslesmis()
    yol = aktarim.dosya_yaz(kayit=7)
    dosya_id = yol.stem
    sha = hashlib.sha256(yol.read_bytes()).hexdigest()
    r = i.dosya_gonder(yol)
    assert r["sonuc"] == "var" and r["gonderilen_bayt"] == yol.stat().st_size
    hedef = aktarim.veri / "gelen_aktarim" / aktarim.cihaz / f"{dosya_id}.jsonl"
    assert hedef.read_bytes() == yol.read_bytes()
    assert aktarim.hub.aktarim_dosyasi_var(aktarim.cihaz, dosya_id) == sha
    assert aktarim.tamamlananlar == [hedef]                       # geri çağrı yolu verdi
    assert aktarim.dosyalar("aktarim/gecici") == []
    assert aktarim.hub.cihazlar()[0]["last_seen"]
    # içe alma: olaylar veritabanında, dosya klasörden kalkar
    s = gelenleri_ice_al(aktarim.hub)
    assert s == {"dosya": 1, "yeni": 7, "yinelenen": 0, "eksik": 0}
    assert not hedef.exists()
    ev = aktarim.hub.timeline(limit=100)
    assert len(ev) == 7 and {e.device_id for e in ev} == {aktarim.cihaz}
    assert {e.kind for e in ev} == {"android.not.hizli"}
    assert len(aktarim.hub.raw_files()) == 1                      # ham arşive kopya
    # ikinci çağrı: işlenecek bir şey yok
    assert gelenleri_ice_al(aktarim.hub) == {"dosya": 0, "yeni": 0, "yinelenen": 0, "eksik": 0}


def test_ayni_dosya_iki_kez_ikinci_var_sifir_yeni_olay(aktarim):
    i = aktarim.eslesmis()
    yol = aktarim.dosya_yaz(kayit=4)
    yedek = yol.read_bytes()
    i.dosya_gonder(yol)
    assert gelenleri_ice_al(aktarim.hub)["yeni"] == 4
    n = len(aktarim.hub.timeline(limit=1000))
    # içe alınıp klasörden kaldırılmış dosya yeniden gönderilirse yine `var`
    yol.write_bytes(yedek)
    r = i.dosya_gonder(yol)
    assert r["sonuc"] == "var" and r["gonderilen_bayt"] == 0
    assert aktarim.dosyalar("gelen_aktarim") == []                  # yeniden yazılmadı
    # PUT ile zorlansa da var
    veri = yedek
    kod, h, _ = ham_istek(aktarim.alici.port, "PUT", f"/giden/{aktarim.cihaz}/{yol.stem}.jsonl",
                          put_basliklari(aktarim.cihaz, i.anahtar, veri), veri)
    assert kod == 200 and h["X-Durum"] == "var" and aktarim.dosyalar("gelen_aktarim") == []
    assert gelenleri_ice_al(aktarim.hub)["dosya"] == 0
    assert len(aktarim.hub.timeline(limit=1000)) == n


def test_ayni_kayit_farkli_dosyada_yeni_degil(aktarim):
    """Aynı kayıt kimliği iki farklı dosyada gelirse (kayıt başına anahtar) 0 yeni olay."""
    i = aktarim.eslesmis()
    a = aktarim.dosya_yaz(kayit=3)
    b = aktarim.dosya_yaz(kayit=3)
    # b'nin kayıtlarını a'nınkilerle aynı kimliklere çevir
    satirlar_a = a.read_bytes().decode().splitlines()
    satirlar_b = b.read_bytes().decode().splitlines()
    satirlar_b[1:4] = satirlar_a[1:4]
    b.write_bytes(("\n".join(satirlar_b) + "\n").encode())
    i.dosya_gonder(a)
    i.dosya_gonder(b)
    s = gelenleri_ice_al(aktarim.hub)
    assert s["dosya"] == 2 and s["yeni"] == 3 and s["yinelenen"] == 3


def test_sha_uyusmazligi_422_gecici_silinir(aktarim):
    i = aktarim.eslesmis()
    yol = aktarim.dosya_yaz(kayit=3)
    veri = yol.read_bytes()
    kod, _, govde = ham_istek(aktarim.alici.port, "PUT", f"/giden/{aktarim.cihaz}/{yol.stem}.jsonl",
                              put_basliklari(aktarim.cihaz, i.anahtar, veri, sha="0" * 64), veri)
    assert kod == 422
    assert aktarim.dosyalar("gelen_aktarim") == [] and aktarim.dosyalar("aktarim/gecici") == []
    assert aktarim.hub.aktarim_dosyasi_var(aktarim.cihaz, yol.stem) is None
    assert i.durum(yol.stem) == ("yok", 0)


@pytest.mark.parametrize("kapanis", ["yok", "yanlis"])
def test_kapanissiz_ya_da_sayisi_tutmayan_dosya_422(aktarim, kapanis):
    i = aktarim.eslesmis()
    yol = aktarim.dosya_yaz(kayit=3, kapanis=kapanis)
    r = i.dosya_gonder(yol)
    assert r["sonuc"] == "reddedildi"
    assert aktarim.dosyalar("gelen_aktarim") == [] and aktarim.dosyalar("aktarim/gecici") == []
    assert aktarim.hub.aktarim_dosyasi_var(aktarim.cihaz, yol.stem) is None


def test_baska_cihaz_basligi_ya_da_bozuk_satir_422(aktarim):
    i = aktarim.eslesmis()
    d1 = str(uuid.uuid4())
    yol = aktarim.cikis / f"{d1}.jsonl"
    yol.write_bytes(kutu_dosyasi(str(uuid.uuid4()), d1, 2))          # başlıktaki cihaz kimliği başka
    assert i.dosya_gonder(yol)["sonuc"] == "reddedildi"
    d2 = str(uuid.uuid4())
    yol2 = aktarim.cikis / f"{d2}.jsonl"
    yol2.write_bytes(kutu_dosyasi(aktarim.cihaz, d2, 2).replace(b'"tur"', b'"tur', 1))   # bozuk JSON satırı
    assert i.dosya_gonder(yol2)["sonuc"] == "reddedildi"
    assert aktarim.dosyalar("gelen_aktarim") == []


def test_yanlis_parmak_izi_istemci_gondermez(aktarim):
    yol = aktarim.dosya_yaz()
    k = Istemci("127.0.0.1", aktarim.alici.port, "ab" * 32, aktarim.cihaz, "x" * 64)
    with pytest.raises(ParmakIziUyusmadi):
        k.dosya_gonder(yol)
    assert aktarim.dosyalar("gelen_aktarim") == [] and aktarim.dosyalar("aktarim/gecici") == []


def test_pc_kapaliyken_birikir_acilinca_hepsi_gider(aktarim):
    i = aktarim.eslesmis(parca_bayt=300)
    ids = {aktarim.dosya_yaz(kayit=5).stem for _ in range(4)}
    aktarim.alici.durdur()
    r = i.klasor_gonder(aktarim.cikis)
    assert r["bekleyen"] == 4 and r["var"] == 0 and r["hata"]
    assert len(list(aktarim.cikis.glob("*.jsonl"))) == 4                  # telefon silmedi
    aktarim.yeni_alici()
    i2 = aktarim.istemci(anahtar=i.anahtar, parca_bayt=300)
    r = i2.klasor_gonder(aktarim.cikis)
    assert r["var"] == 4 and r["bekleyen"] == 0
    assert list(aktarim.cikis.glob("*.jsonl")) == []                       # yalnız `var` sonrası silindi
    assert {p.stem for p in aktarim.dosyalar("gelen_aktarim")} == ids


def test_ortada_kesilen_aktarim_kaldigi_yerden_devam(aktarim):
    i = aktarim.eslesmis(parca_bayt=200)
    yol = aktarim.dosya_yaz(kayit=20)
    toplam = yol.stat().st_size
    sha = hashlib.sha256(yol.read_bytes()).hexdigest()
    r = i.dosya_gonder(yol, en_fazla_parca=3)
    assert r["sonuc"] == "kesildi" and r["gonderilen_bayt"] == 600
    assert i.durum(yol.stem) == ("kismi", 600)
    assert aktarim.dosyalar("gelen_aktarim") == []
    r = i.dosya_gonder(yol)                                              # yeni oturum
    assert r["baslangic_ofset"] == 600 and r["gonderilen_bayt"] == toplam - 600
    hedef = aktarim.veri / "gelen_aktarim" / aktarim.cihaz / f"{yol.stem}.jsonl"
    assert hashlib.sha256(hedef.read_bytes()).hexdigest() == sha


def test_alici_durdur_yeni_alici_ayni_bayttan_devam(aktarim):
    i = aktarim.eslesmis(parca_bayt=200)
    yol = aktarim.dosya_yaz(kayit=30)
    sha = hashlib.sha256(yol.read_bytes()).hexdigest()
    i.dosya_gonder(yol, en_fazla_parca=4)
    port = aktarim.alici.port
    aktarim.alici.durdur()
    yeni = aktarim.yeni_alici()
    assert yeni.port == port and yeni.parmak_izi == aktarim.alici.parmak_izi   # sertifika kalıcı: sabitleme bozulmaz
    i2 = aktarim.istemci(anahtar=i.anahtar, parca_bayt=200)
    assert i2.durum(yol.stem) == ("kismi", 800)
    r = i2.dosya_gonder(yol)
    assert r["baslangic_ofset"] == 800
    hedef = aktarim.veri / "gelen_aktarim" / aktarim.cihaz / f"{yol.stem}.jsonl"
    assert hashlib.sha256(hedef.read_bytes()).hexdigest() == sha


def test_istemci_baglanti_koparsa_yeniden_dener_ve_tamamlar(aktarim):
    i = aktarim.eslesmis(parca_bayt=150)
    yol = aktarim.dosya_yaz(kayit=15)
    i.dosya_gonder(yol, en_fazla_parca=2)
    i.kapat()
    # yarım gövdeyle kopan bağlantı: o parça hiç yazılmaz, ofset parça sınırında kalır
    import socket, ssl
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    t = ctx.wrap_socket(socket.create_connection(("127.0.0.1", aktarim.alici.port)))
    veri = yol.read_bytes()[300:450]
    b = put_basliklari(aktarim.cihaz, i.anahtar, veri, bas=300, toplam=yol.stat().st_size,
                       sha=hashlib.sha256(yol.read_bytes()).hexdigest())
    t.sendall(("PUT /giden/%s/%s.jsonl HTTP/1.1\r\nHost: x\r\n" % (aktarim.cihaz, yol.stem)
               + "".join(f"{k}: {v}\r\n" for k, v in b.items()) + "\r\n").encode() + veri[:50])
    t.close()
    time.sleep(0.3)
    assert i.durum(yol.stem) == ("kismi", 300)
    assert i.dosya_gonder(yol)["baslangic_ofset"] == 300
    assert len(aktarim.dosyalar("gelen_aktarim")) == 1


def test_yanlis_ofset_409_ve_x_alinan(aktarim):
    i = aktarim.eslesmis(parca_bayt=100)
    yol = aktarim.dosya_yaz(kayit=10)
    i.dosya_gonder(yol, en_fazla_parca=1)
    veri = yol.read_bytes()
    kod, h, _ = ham_istek(aktarim.alici.port, "PUT", f"/giden/{aktarim.cihaz}/{yol.stem}.jsonl",
                          put_basliklari(aktarim.cihaz, i.anahtar, veri[300:400], bas=300, toplam=len(veri),
                                         sha=hashlib.sha256(veri).hexdigest()), veri[300:400])
    assert kod == 409 and h["X-Alinan"] == "100"


def test_baska_icerikle_eski_yarim_yukleme_sifirlanir(aktarim):
    i = aktarim.eslesmis(parca_bayt=100)
    yol = aktarim.dosya_yaz(kayit=10)
    i.dosya_gonder(yol, en_fazla_parca=2)
    yol.write_bytes(kutu_dosyasi(aktarim.cihaz, yol.stem, 10, metin="DEGISTI"))   # aynı kimlik, başka içerik
    r = i.dosya_gonder(yol)
    assert r["sonuc"] == "var"
    hedef = aktarim.veri / "gelen_aktarim" / aktarim.cihaz / f"{yol.stem}.jsonl"
    assert hedef.read_bytes() == yol.read_bytes()


def test_esanli_ayni_dosya_tek_kayit(aktarim):
    yol = aktarim.dosya_yaz(kayit=40)
    sha = hashlib.sha256(yol.read_bytes()).hexdigest()
    ana = aktarim.eslesmis()
    sonuclar, hatalar = [], []

    def is_(n):
        try:
            c = aktarim.istemci(anahtar=ana.anahtar, parca_bayt=400 + n)
            for _ in range(200):
                r = c.dosya_gonder(yol)
                if r["sonuc"] in ("var", "tamam"):
                    sonuclar.append(r)
                    return
                time.sleep(0.01)
        except Exception as e:  # noqa: BLE001
            hatalar.append(repr(e))

    iplikler = [threading.Thread(target=is_, args=(n,)) for n in range(4)]
    [t.start() for t in iplikler]
    [t.join(60) for t in iplikler]
    assert not hatalar and len(sonuclar) == 4
    (hedef,) = aktarim.dosyalar("gelen_aktarim")
    assert hashlib.sha256(hedef.read_bytes()).hexdigest() == sha
    assert aktarim.hub.aktarim_dosyasi_var(aktarim.cihaz, yol.stem) == sha
    assert len(aktarim.tamamlananlar) == 1 and aktarim.dosyalar("aktarim/gecici") == []
    assert gelenleri_ice_al(aktarim.hub)["yeni"] == 40


def test_ice_alma_hatasi_dosya_yerinde_kalir(aktarim):
    i = aktarim.eslesmis()
    yol = aktarim.dosya_yaz(kayit=3)
    i.dosya_gonder(yol)
    (hedef,) = aktarim.dosyalar("gelen_aktarim")
    # alıcının doğruladığı dosya sonradan bozulursa (disk hatası vb.) içe alma anlaşılır biçimde başarısız olur
    hedef.write_bytes(hedef.read_bytes()[:-30])
    s = gelenleri_ice_al(aktarim.hub)
    assert s == {"dosya": 0, "yeni": 0, "yinelenen": 0, "eksik": 1}
    assert hedef.exists() and aktarim.hub.timeline(limit=10) == []


def test_gunlukte_kayit_metni_yok(aktarim, caplog):
    caplog.set_level(logging.DEBUG)
    gizli = "COK-GIZLI-KAYIT-METNI"
    i = aktarim.eslesmis()
    yol = aktarim.dosya_yaz(kayit=3, metin=gizli)
    i.dosya_gonder(yol)
    aktarim.dosya_yaz(kayit=2, kapanis="yok")
    i.dosya_gonder(next(p for p in aktarim.cikis.glob("*.jsonl") if p != yol))
    gelenleri_ice_al(aktarim.hub)
    tum = "\n".join(r.getMessage() for r in caplog.records)
    assert "dosya alındı" in tum and gizli not in tum and i.anahtar not in tum
    assert gizli not in str(caplog.text)


def test_geri_cagri_hatasi_aktarimi_bozmaz(aktarim):
    def kotu(_):
        raise RuntimeError("arayüz hatası")

    aktarim.kopru._tamamlandi = kotu
    i = aktarim.eslesmis()
    yol = aktarim.dosya_yaz(kayit=2)
    assert i.dosya_gonder(yol)["sonuc"] == "var"
    assert aktarim.hub.aktarim_dosyasi_var(aktarim.cihaz, yol.stem)
