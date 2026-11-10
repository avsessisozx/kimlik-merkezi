"""Ağ garantisi testleri (docs/AG-GARANTISI.md).

A) Koruma düzeneğinin kendisi çalışıyor mu (yerel serbest, dış hedef engelli, istisna yutulsa da başarısız).
B) Statik denetim: kaynak kodda harici bağlantı kütüphanesi / URL / CDN / telemetri yok;
   izinli istisnalar AÇIKÇA listelenmiştir. Yeni bir istisna eklemek bilinçli bir karar olmalıdır.
C) Yerel web arayüzü dosyalarında (windows/.../statik) harici URL yok.
"""
from __future__ import annotations

import ast
import re
import socket
import threading
from pathlib import Path

import pytest

import ag_koruma

KOK = Path(__file__).resolve().parents[1]
KAYNAK_DIZINLERI = [KOK / p / "src" for p in ("core", "server", "importers", "windows")]
STATIK = KOK / "windows" / "src" / "kimlikwin" / "statik"


def _goreli(p: Path) -> str:
    return p.relative_to(KOK).as_posix()


# ---------------------------------------------------------------- A) koruma düzeneği

def test_koruma_devrede():
    assert ag_koruma._orijinal, "ağ koruması kurulu değil (KIMLIK_AG_KORUMASI=kapali mı?)"


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.5.4.3"])
def test_yerel_hedefler_serbest(host):
    assert ag_koruma.yerel_mi(host)


@pytest.mark.parametrize("host", ["example.com", "8.8.8.8", "192.0.2.1", "0.0.0.0", "::ffff:8.8.8.8"])
def test_yerel_olmayan_hedefler_yerel_sayilmaz(host):
    assert not ag_koruma.yerel_mi(host)


def _ihlal_bekle(cagri):
    """Çağrı AgIhlali fırlatmalı ve ihlal kaydı oluşmalı; kaydı sonra temizleriz (test başarısız olmasın)."""
    with pytest.raises(ag_koruma.AgIhlali):
        cagri()
    assert ag_koruma.IHLALLER
    ag_koruma.IHLALLER.clear()


def test_dis_baglanti_engellenir_connect():
    s = socket.socket()
    try:
        _ihlal_bekle(lambda: s.connect(("93.184.216.34", 80)))
        _ihlal_bekle(lambda: s.connect_ex(("93.184.216.34", 80)))
    finally:
        s.close()


def test_dis_baglanti_engellenir_create_connection():
    _ihlal_bekle(lambda: socket.create_connection(("93.184.216.34", 80), timeout=1))


def test_dis_ad_cozumleme_engellenir():
    _ihlal_bekle(lambda: socket.getaddrinfo("example.com", 443))
    _ihlal_bekle(lambda: socket.gethostbyname("example.com"))


def test_udp_sendto_engellenir():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        _ihlal_bekle(lambda: s.sendto(b"x", ("93.184.216.34", 53)))
    finally:
        s.close()


def test_yerel_baglanti_calisir_127():
    """Yerel web arayüzü testlerinin dayandığı yol: 127.0.0.1'e gerçek bağlantı serbest."""
    sunucu = socket.socket()
    sunucu.bind(("127.0.0.1", 0))
    sunucu.listen(1)
    port = sunucu.getsockname()[1]
    kabul = []
    t = threading.Thread(target=lambda: kabul.append(sunucu.accept()[0]))
    t.start()
    with socket.create_connection(("127.0.0.1", port), timeout=5) as c:
        c.sendall(b"x")
    t.join(5)
    for k in kabul:
        k.close()
    sunucu.close()
    assert kabul and not ag_koruma.IHLALLER


def test_yerel_unix_soketi_serbest(tmp_path):
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("AF_UNIX yok (Windows)")
    yol = str(tmp_path / "s.sock")
    sunucu = socket.socket(socket.AF_UNIX)
    sunucu.bind(yol)
    sunucu.listen(1)
    with socket.socket(socket.AF_UNIX) as c:
        c.connect(yol)
    sunucu.close()
    assert not ag_koruma.IHLALLER


def test_yutulan_ihlal_kaydi_kalir():
    """İstisna try/except ile yutulsa bile ihlal kaydı kalır; ag_korumasi fixture'ı bunu hata sayar."""
    s = socket.socket()
    try:
        try:
            s.connect(("93.184.216.34", 80))
        except OSError:
            pass  # kodun yuttuğunu varsay
        assert ag_koruma.IHLALLER, "yutulan ihlal kaydedilmedi"
    finally:
        s.close()
        ag_koruma.IHLALLER.clear()  # bu testin kendisi başarısız olmasın


# ---------------------------------------------------------------- B) statik denetim (Python kaynağı)

# Ağ yeteneği olan modüller. Başka bir modül eklemek için önce buraya yazın.
YASAK_MODULLER = {
    "requests", "urllib.request", "urllib3", "http.client", "httplib2", "httpx", "aiohttp",
    "socket", "ssl", "ftplib", "smtplib", "imaplib", "poplib", "telnetlib", "xmlrpc.client",
    "websocket", "websockets", "asyncio.streams", "webbrowser", "paramiko", "pycurl",
    "sentry_sdk", "posthog", "mixpanel", "segment", "analytics", "opentelemetry", "datadog",
}

# İZİN VERİLEN İSTİSNALAR: (dosya, modül) -> neden. Başka her kullanım testi başarısız yapar.
IZINLI_ISTISNALAR = {
    ("core/src/kimlikcore/lock.py", "socket"):
        "yalnız socket.gethostname() (kilit dosyasına makine adı); ağ bağlantısı yok",
    ("windows/src/kimlikwin/web.py", "socket"):
        "yalnız 127.0.0.1'e bind ederek boş port bulma; dış bağlantı yok",
    ("windows/src/kimlikwin/uygulama.py", "urllib.request"):
        "yalnız http://127.0.0.1:<port>/saglik (kendi yerel sunucusunu yoklar)",
    ("windows/src/kimlikwin/uygulama.py", "webbrowser"):
        "yalnız kendi yerel adresini (sunucu.url = http://127.0.0.1:<port>/) kullanıcının tarayıcısında açar",
}


def _py_dosyalari():
    for d in KAYNAK_DIZINLERI:
        assert d.is_dir(), d
        yield from sorted(d.rglob("*.py"))


def _ice_aktarilanlar(yol: Path):
    agac = ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            for a in n.names:
                yield a.name
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            yield n.module
            for a in n.names:  # "from urllib import request" biçimi
                yield f"{n.module}.{a.name}"
        elif isinstance(n, ast.Call) and getattr(n.func, "id", "") == "__import__" and n.args:
            if isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                yield n.args[0].value
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr == "import_module" and n.args
              and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
            yield n.args[0].value


def _yasak_mi(modul: str) -> str | None:
    for y in YASAK_MODULLER:
        if modul == y or modul.startswith(y + "."):
            return y
    return None


def test_kaynakta_yasak_ag_modulu_yok():
    ihlaller, kullanilan = [], set()
    for yol in _py_dosyalari():
        for m in set(_ice_aktarilanlar(yol)):
            y = _yasak_mi(m)
            if y is None:
                continue
            anahtar = (_goreli(yol), y)
            kullanilan.add(anahtar)
            if anahtar not in IZINLI_ISTISNALAR:
                ihlaller.append(f"{anahtar[0]}: '{m}' içe aktarıyor")
    assert not ihlaller, "izinsiz ağ modülü (gerekçeyle IZINLI_ISTISNALAR'a eklenmeli):\n" + "\n".join(ihlaller)
    eskimis = set(IZINLI_ISTISNALAR) - kullanilan
    assert not eskimis, f"artık gerekmeyen istisnalar listeden silinmeli: {sorted(eskimis)}"


def test_istisna_dosyalari_yalniz_yerel_kullaniyor():
    """İstisnaların gerekçesi kodda da doğru mu: socket.connect/create_connection yok, urlopen yalnız 127.0.0.1."""
    web = (KOK / "windows/src/kimlikwin/web.py").read_text(encoding="utf-8")
    lock = (KOK / "core/src/kimlikcore/lock.py").read_text(encoding="utf-8")
    uyg = (KOK / "windows/src/kimlikwin/uygulama.py").read_text(encoding="utf-8")
    for ad, kod in (("web.py", web), ("lock.py", lock)):
        assert not re.search(r"\.connect\(|create_connection|getaddrinfo|gethostbyname\(", kod), ad
    assert re.search(r'^ADRES = "127\.0\.0\.1"$', web, re.M)
    assert not re.search(r"0\.0\.0\.0|\"\"\s*,\s*p\b", web)
    cagrilar = re.findall(r"urlopen\(([^)]*)\)", uyg)
    assert cagrilar and all("127.0.0.1" in c for c in cagrilar), cagrilar


# Sunucu bağlama adresleri: yalnız 127.0.0.1 (ya da hiç sunucu yok).
def test_sunucular_yalniz_127_dinler():
    bulunan = []
    for yol in _py_dosyalari():
        kod = yol.read_text(encoding="utf-8")
        for m in re.finditer(r"""["'](0\.0\.0\.0|::|)["']\s*,\s*(?:p\b|port\b|\d{2,5}\b)""", kod):
            satir = kod[: m.start()].count("\n") + 1
            bulunan.append(f"{_goreli(yol)}:{satir}")
        if re.search(r"""host\s*=\s*["']0\.0\.0\.0["']""", kod):
            bulunan.append(_goreli(yol))
    assert not bulunan, f"tüm arayüzlerde dinleme şüphesi: {bulunan}"


URL_RE = re.compile(r"""(?:https?|wss?|ftp)://[^\s"'<>)\]},;`\\]+""", re.I)
IZINLI_URL_SUNUCU = {"127.0.0.1", "localhost", "[::1]"}
# Python kaynağında başka URL de yasak; belgeleme amaçlı bir tane gerekirse buraya (dosya, sunucu) yazın.
IZINLI_PY_URL: dict[tuple[str, str], str] = {
    ("windows/src/kimlikwin/web.py", "{adres"): "f-dizgesi http://{ADRES}:port ; ADRES = '127.0.0.1' (ayrı testle doğrulanır)",
}
YASAK_ALAN_ADLARI = ("cdn.", "googleapis", "gstatic", "jsdelivr", "unpkg", "cloudflare", "cdnjs",
                     "googletagmanager", "google-analytics", "doubleclick", "sentry", "segment.",
                     "mixpanel", "amplitude", "posthog", "facebook.net", "bootstrapcdn")


def _sunucu(url: str) -> str:
    return re.sub(r"^[a-z]+://", "", url, flags=re.I).split("/", 1)[0].split("?", 1)[0].rsplit("@", 1)[-1].rsplit(":", 1)[0] \
        if not url.split("://", 1)[1].startswith("[") else "[::1]"


def test_kaynakta_harici_url_veya_cdn_yok():
    ihlaller = []
    for yol in _py_dosyalari():
        for m in URL_RE.finditer(yol.read_text(encoding="utf-8")):
            url = m.group(0)
            host = _sunucu(url).lower()
            if host in IZINLI_URL_SUNUCU or (_goreli(yol), host) in IZINLI_PY_URL:
                continue
            ihlaller.append(f"{_goreli(yol)}: {url}")
    assert not ihlaller, "Python kaynağında harici URL:\n" + "\n".join(ihlaller)
    # CDN / telemetri adları URL biçiminde olmasa bile (yalnız ad) geçmesin
    for yol in _py_dosyalari():
        kod = yol.read_text(encoding="utf-8").lower()
        for ad in YASAK_ALAN_ADLARI:
            assert ad not in kod, f"{_goreli(yol)}: '{ad}' geçiyor (CDN/telemetri şüphesi)"


# ---------------------------------------------------------------- C) yerel arayüz dosyaları

# Standart gösterim / lisans metinleri; bağlantı KURMAZ (XML ad alanı kimliği ya da yorum satırı).
IZINLI_STATIK_URL = {
    "www.w3.org",          # SVG/XLink/XML ad alanı tanımlayıcısı (ağa gitmez)
    "www.apache.org",      # lisans metni
    "github.com",          # ECHARTS-LICENSE / zrender LICENSE yorumları (yalnız metin)
}
ARAYUZ_DOSYALARI = ("index.html", "harita.js", "figur.js", "harita.css")


def _statik_dosyalar():
    assert STATIK.is_dir()
    return sorted(p for p in STATIK.iterdir() if p.is_file())


def test_statik_dosyalarda_harici_url_yok():
    ihlaller = []
    for yol in _statik_dosyalar():
        for m in URL_RE.finditer(yol.read_text(encoding="utf-8", errors="replace")):
            host = _sunucu(m.group(0)).lower()
            if host in IZINLI_URL_SUNUCU or host in IZINLI_STATIK_URL:
                continue
            ihlaller.append(f"{yol.name}: {m.group(0)}")
    assert not ihlaller, "statik dosyada izinsiz URL:\n" + "\n".join(ihlaller)


def test_statik_url_istisnalari_baglanti_degil():
    """İzinli w3.org/apache/github adresleri kodda bir isteğe dönüşmemeli (fetch/src/href/import içinde değil)."""
    for yol in _statik_dosyalar():
        if yol.suffix == ".txt":
            continue
        metin = yol.read_text(encoding="utf-8", errors="replace")
        for h in IZINLI_STATIK_URL:
            assert not re.search(rf"""(fetch|import|src|href|url)\s*[\(=:]\s*["']?https?://{re.escape(h)}""", metin), (yol.name, h)


def test_arayuz_ozel_dosyalari_ag_istegi_yapmiyor():
    html = (STATIK / "index.html").read_text(encoding="utf-8")
    # script/link/img/iframe/source ... src/href değerleri yerel olmalı
    for m in re.finditer(r"""\b(src|href|action|data|poster|srcset)\s*=\s*["']([^"']*)["']""", html, re.I):
        deger = m.group(2).strip()
        assert not re.match(r"^(?:[a-z][a-z0-9+.-]*:|//)", deger, re.I) or deger.startswith(("data:", "#")), deger
    assert not re.search(r"<(iframe|embed|object)\b", html, re.I)
    assert not re.search(r"@import|http-equiv\s*=\s*[\"']refresh", html, re.I)
    for ad in ARAYUZ_DOSYALARI:
        metin = (STATIK / ad).read_text(encoding="utf-8")
        for yasak in ("XMLHttpRequest", "WebSocket", "sendBeacon", "EventSource", "importScripts",
                      "navigator.serviceWorker", "new Image(", "createElement('script')", 'createElement("script")'):
            assert yasak not in metin, f"{ad}: {yasak}"
        assert not re.search(r"@import", metin), ad
        for m in re.finditer(r"url\(\s*([^)]*)\)", metin):
            d = m.group(1).strip("'\" ")
            assert d.startswith(("#", "data:", "/statik/")) , f"{ad}: url({d})"
        for m in re.finditer(r"\bfetch\(\s*([^,)]*)", metin):
            ilk = m.group(1).strip()
            assert ilk[:2] in ("'/", '"/', "`/") and not ilk[1:3] == "//", f"{ad}: fetch({ilk})"
    for yol in _statik_dosyalar():
        if yol.suffix != ".js":
            continue
        metin = yol.read_text(encoding="utf-8", errors="replace")
        for yasak in ("XMLHttpRequest", "WebSocket", "sendBeacon", "EventSource"):
            assert yasak not in metin, f"{yol.name}: {yasak}"
        # kütüphane dosyası da kendi başına fetch yapmasın
        if yol.name not in ARAYUZ_DOSYALARI:
            assert "fetch(" not in metin, yol.name


# ---------------------------------------------------------------- D) paket CI'sinin ağ adımı yerinde mi

def test_paket_ci_ag_izleme_adimi_bagli():
    """paket.yml/ci_paket.ps1 ağ izleyiciyi gerçekten çağırıyor (CI burada çalıştırılamaz; bağlantıyı denetler)."""
    ps = (KOK / "windows/paket/ci_paket.ps1").read_text(encoding="utf-8")
    izle = (KOK / "windows/paket/ag_izle.ps1").read_text(encoding="utf-8")
    assert "ag_izle.ps1" in ps and "kurulu_dene.py" in ps
    assert "Get-NetTCPConnection" in izle and "127.0.0.1" in izle
    yml = (KOK / ".github/workflows/paket.yml").read_text(encoding="utf-8")
    assert "ci_paket.ps1" in yml and "ag_sonuc.json" in yml
    yaml = pytest.importorskip("yaml")
    assert "jobs" in yaml.safe_load(yml)
