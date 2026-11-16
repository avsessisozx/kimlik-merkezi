"""Ağ yüzü: adres süzgeci, TLS, sertifika, UDP bulma, alıcı yaşam döngüsü."""
import hashlib
import socket
import ssl
import stat
import sys

import pytest
from kimlikserver.aktarim import AktarimAlici, yerel_adres_mi
from kimlikserver.aktarim import sertifika as sert_mod


@pytest.mark.parametrize("adres", [
    "10.0.0.1", "10.255.255.255", "172.16.0.1", "172.31.255.254", "192.168.1.20", "169.254.10.10",
    "127.0.0.1", "127.5.5.5", "::1", "fe80::1", "::ffff:192.168.1.5", "::ffff:127.0.0.1", "::ffff:10.1.2.3",
    "fe80::1%eth0",
])
def test_adres_suzgeci_yerel_kabul(adres):
    assert yerel_adres_mi(adres)


@pytest.mark.parametrize("adres", [
    "8.8.8.8", "93.184.216.34", "172.32.0.1", "172.15.255.255", "192.169.0.1", "11.0.0.1", "100.64.0.1",
    "::ffff:8.8.8.8", "2001:4860:4860::8888", "fc00::1", "", "yerel", "999.1.1.1", "192.168.1",
])
def test_adres_suzgeci_yerel_degil_ret(adres):
    assert not yerel_adres_mi(adres)


def test_acik_internet_adresi_baglanti_duzeyinde_reddedilir(aktarim):
    """verify_request reddi: bağlantı el sıkışmadan kapanır (sunucu içi çağrı; gerçek dış adres kullanılmaz)."""
    srv = aktarim.alici._srv
    assert srv.verify_request(None, ("127.0.0.1", 1)) is True
    assert srv.verify_request(None, ("8.8.8.8", 1)) is False
    assert srv.verify_request(None, ("::ffff:93.184.216.34", 1)) is False
    assert srv.verify_request(None, ("::ffff:192.168.0.9", 1)) is True
    aktarim.alici.yalniz_yerel = False
    assert srv.verify_request(None, ("8.8.8.8", 1)) is True


def test_tls12_alti_reddedilir_ve_yalniz_tls(aktarim):
    port = aktarim.alici.port
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        ctx.maximum_version = ssl.TLSVersion.TLSv1_1
    except (ValueError, ssl.SSLError):
        pytest.skip("bu OpenSSL TLS 1.1 istemcisine izin vermiyor")
    with pytest.raises((ssl.SSLError, OSError)):
        with ctx.wrap_socket(socket.create_connection(("127.0.0.1", port), timeout=5)):
            pass
    # düz HTTP (TLS'siz) istek cevap almaz
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(b"GET /durum HTTP/1.1\r\nHost: x\r\n\r\n")
    try:
        veri = s.recv(100)
    except OSError:
        veri = b""
    assert not veri.startswith(b"HTTP/")
    s.close()


def test_sertifika_ozellikleri(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec

    s = sert_mod.hazirla(tmp_path, None)
    c = x509.load_pem_x509_certificate(s.sertifika_yolu.read_bytes())
    assert isinstance(c.public_key(), ec.EllipticCurvePublicKey) and c.public_key().curve.name == "secp256r1"
    omur = c.not_valid_after_utc - c.not_valid_before_utc
    assert 3650 <= omur.days <= 3660
    assert s.parmak_izi == hashlib.sha256(c.public_bytes(__import__("cryptography").hazmat.primitives.serialization.Encoding.DER)).hexdigest()
    assert s.sertifika_yolu.parent == tmp_path / "aktarim" and not s.anahtar_sarili
    if sys.platform != "win32":
        assert stat.S_IMODE(s.anahtar_yolu.stat().st_mode) == 0o600
    # kalıcı: ikinci çağrı aynı sertifika
    assert sert_mod.hazirla(tmp_path, None).parmak_izi == s.parmak_izi


def test_sertifika_anahtari_saglayiciyla_sarilir(tmp_path):
    from kimlikcore.sifreleme import SahteSaglayici

    sg = SahteSaglayici("deneme")
    s = sert_mod.hazirla(tmp_path, sg)
    assert s.anahtar_sarili and b"ENCRYPTED" in s.anahtar_yolu.read_bytes()
    assert (tmp_path / "aktarim" / "anahtar.parola.sarili").is_file()
    assert sert_mod.hazirla(tmp_path, sg).parmak_izi == s.parmak_izi
    # sağlayıcı açamazsa (başka hesap) sertifika yeniden üretilir: parmak izi değişir
    assert sert_mod.hazirla(tmp_path, SahteSaglayici("baska")).parmak_izi != s.parmak_izi


def test_sarili_anahtarla_alici_calisir(tmp_path):
    from conftest import AktarimDunyasi
    from kimlikcore.sifreleme import SahteSaglayici

    d = AktarimDunyasi(tmp_path, saglayici=SahteSaglayici("x"))
    try:
        assert d.alici.durum()["anahtar_sarili"] is True
        d.eslesmis().durum("11111111-1111-4111-8111-111111111111")
    finally:
        d.kapat()


def _bul(bulma_port, mesaj):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.8)
    try:
        s.sendto(mesaj, ("127.0.0.1", bulma_port))
        return s.recvfrom(100)[0]
    except socket.timeout:
        return None
    finally:
        s.close()


def test_udp_bulma(aktarim):
    st = aktarim.alici.durum()
    bp = st["bulma_port"]
    assert bp
    onek = aktarim.alici.parmak_izi[:16]
    assert _bul(bp, f"KM1?{onek}".encode()) == f"KM1!{aktarim.alici.port}".encode()
    assert _bul(bp, f"KM1?{'0' * 16}".encode()) is None            # yanlış parmak izi: yanıt yok
    assert _bul(bp, b"merhaba") is None
    assert _bul(bp, f"KM1?{onek[:8]}".encode()) is None            # kısa önek de olmaz
    aktarim.alici.durdur()
    assert _bul(bp, f"KM1?{onek}".encode()) is None                # alıcıyla birlikte durur
    aktarim.yeni_alici(bulma_port=0)
    assert _bul(aktarim.alici.durum()["bulma_port"], f"KM1?{onek}".encode()) is not None


def test_udp_bulma_yalniz_yerel_kaynak(aktarim):
    b = aktarim.alici._bulma
    assert b._yalniz_yerel is True
    # kaynak süzgeci aynı yerel_adres_mi kullanır: yerel olmayan kaynak yanıt almaz
    gonderilen = []

    class S:
        def recvfrom(self, n):
            if gonderilen:
                raise OSError
            gonderilen.append(1)
            return b"KM1?" + aktarim.alici.parmak_izi[:16].encode(), ("8.8.8.8", 5)

        def sendto(self, *a):
            raise AssertionError("yerel olmayan kaynağa yanıt verildi")

    b2 = type(b)(aktarim.alici.parmak_izi, lambda: 1, 0)
    b2._soket = S()
    b2._dongu()


def test_yasam_dongusu_durum(aktarim):
    a = aktarim.alici
    assert a.durum()["calisiyor"] and a.durum()["port"] == a.port
    a.durdur()
    a.durdur()                                  # tekrar zararsız
    assert not a.durum()["calisiyor"]
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", a.port), timeout=1).close()
    a.baslat()
    assert a.durum()["calisiyor"]
