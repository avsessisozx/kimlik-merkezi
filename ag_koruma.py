"""Test sırasında ağ koruması (pytest eklentisi gibi çalışır; yeni bağımlılık yok).

Amaç: "Uygulama dışarıya hiç bağlantı denemiyor" iddiasının testle kanıtı (docs/AG-GARANTISI.md).

Ne yapar: testler sürerken şu Python işlevlerini sarar; hedef YEREL değilse çağrı yapılmaz,
`AgIhlali` fırlatılır ve ihlal kaydedilir; kaydı olan test, istisna yutulmuş olsa bile BAŞARISIZ olur.
  - socket.socket.connect / connect_ex / sendto (AF_INET, AF_INET6 için)
  - socket.create_connection
  - socket.getaddrinfo, gethostbyname, gethostbyname_ex, gethostbyaddr (ad çözümleme = DNS sızıntısı)
Yerel sayılanlar: Unix soketi, 127.0.0.0/8, ::1, "localhost" ve makinenin KENDİ adı/arayüz adresleri
(bir yerel sunucunun dışarıdan erişilebilir adrese bağlı OLMADIĞINI sınayan testler için; bu paketler
makineden çıkmaz). Makine adı kur() anında bir kez çözülür.
Yerel web arayüzü testleri (127.0.0.1) bu yüzden çalışır.

Kapsamı: yalnız testi çalıştıran Python süreci (ve iş parçacıkları). Alt süreçler (ör. MCP stdio
testlerinde başlatılan çocuk Python) bu korumanın DIŞINDADIR; onları statik denetim testi ve
paket CI'sindeki bağlantı izleme adımı ele alır. Ayrıntı: docs/AG-GARANTISI.md.

Kullanım: kök conftest.py ve paket conftest.py dosyaları bu modülden `pytest_configure`,
`pytest_runtest_setup`, `pytest_runtest_call`, `pytest_unconfigure` ve `ag_korumasi` içe aktarır.
Kapatma (yalnız hata ayıklama için): KIMLIK_AG_KORUMASI=kapali
"""
from __future__ import annotations

import ipaddress
import os
import socket
import threading

import pytest

YEREL_AD = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})
IHLALLER: list[str] = []
_kilit = threading.Lock()
_orijinal: dict[str, object] = {}


class AgIhlali(OSError):
    """Yerel olmayan bir hedefe ağ erişimi denendi."""


_KENDI_AD: set[str] = set()
_KENDI_IP: set[str] = set()


def _kendini_tani() -> None:
    """Makinenin kendi adı ve arayüz adresleri (kur() içinde, koruma kurulmadan ÖNCE bir kez)."""
    try:
        ad = socket.gethostname().lower()
        if ad:
            _KENDI_AD.add(ad)
            for ip in socket.gethostbyname_ex(ad)[2]:
                _KENDI_IP.add(ip)
    except OSError:
        pass


def yerel_mi(host) -> bool:
    if host is None or host == "":
        return True  # getaddrinfo(None, port): çözümleme yok (bind/pasif kullanım)
    if isinstance(host, (bytes, bytearray)):
        host = bytes(host).decode("ascii", "replace")
    host = str(host).strip().strip("[]").split("%", 1)[0].lower()
    if host in YEREL_AD or host in _KENDI_AD or host in _KENDI_IP:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _kaydet(islem: str, hedef) -> None:
    ileti = f"yerel olmayan ağ erişimi denendi: {islem} -> {hedef!r}"
    with _kilit:
        IHLALLER.append(ileti)
    raise AgIhlali(ileti)


def _adres_host(adres):
    # AF_INET/AF_INET6: (host, port, ...) ; AF_UNIX: str/bytes
    if isinstance(adres, (tuple, list)) and adres:
        return adres[0]
    return None


def _kontrol_adres(soket, islem, adres) -> None:
    if soket.family in (socket.AF_INET, socket.AF_INET6):
        host = _adres_host(adres)
        if not yerel_mi(host):
            _kaydet(islem, adres)


def kur() -> None:
    """Korumayı kurar (tekrar çağrılırsa bir şey yapmaz)."""
    if _orijinal or os.environ.get("KIMLIK_AG_KORUMASI") == "kapali":
        return
    _kendini_tani()
    S = socket.socket
    for ad in ("connect", "connect_ex"):
        _orijinal[ad] = getattr(S, ad)

        def sarmal(self, adres, _ad=ad):
            _kontrol_adres(self, f"socket.{_ad}", adres)
            return _orijinal[_ad](self, adres)

        setattr(S, ad, sarmal)
    _orijinal["sendto"] = S.sendto

    def sendto(self, *a):
        _kontrol_adres(self, "socket.sendto", a[-1])
        return _orijinal["sendto"](self, *a)

    S.sendto = sendto

    _orijinal["create_connection"] = socket.create_connection

    def create_connection(adres, *a, **k):
        if not yerel_mi(_adres_host(adres)):
            _kaydet("socket.create_connection", adres)
        return _orijinal["create_connection"](adres, *a, **k)

    socket.create_connection = create_connection

    _orijinal["getaddrinfo"] = socket.getaddrinfo

    def getaddrinfo(host, *a, **k):
        if not yerel_mi(host):
            _kaydet("socket.getaddrinfo", host)
        return _orijinal["getaddrinfo"](host, *a, **k)

    socket.getaddrinfo = getaddrinfo

    for ad in ("gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        _orijinal[ad] = getattr(socket, ad)

        def ara(host, _ad=ad):
            if not yerel_mi(host):
                _kaydet(f"socket.{_ad}", host)
            return _orijinal[_ad](host)

        setattr(socket, ad, ara)


def kaldir() -> None:
    S = socket.socket
    for ad in ("connect", "connect_ex", "sendto"):
        if ad in _orijinal:
            setattr(S, ad, _orijinal[ad])
    for ad in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        if ad in _orijinal:
            setattr(socket, ad, _orijinal[ad])
    _orijinal.clear()


# ---- pytest bağlantıları (conftest.py dosyalarından içe aktarılır) ----

def pytest_configure(config):
    kur()


def pytest_unconfigure(config):
    kaldir()


@pytest.fixture(autouse=True)
def ag_korumasi():
    """Her test: ihlal kaydı varsa (istisna yutulmuş olsa da) test başarısız olur."""
    with _kilit:
        IHLALLER.clear()
    yield
    with _kilit:
        bulunan = list(IHLALLER)
        IHLALLER.clear()
    if bulunan:
        pytest.fail("AĞ İHLALİ: " + "; ".join(bulunan), pytrace=False)
