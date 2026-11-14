"""Ağ garantisi testleri (docs/AG-GARANTISI.md).

A) Koruma düzeneğinin kendisi çalışıyor mu (yerel serbest, dış hedef engelli, istisna yutulsa da başarısız).
B) Statik denetim: kaynak kodda harici bağlantı kütüphanesi / URL / CDN / telemetri yok;
   izinli istisnalar AÇIKÇA listelenmiştir. Yeni bir istisna eklemek bilinçli bir karar olmalıdır.
C) Yerel web arayüzü dosyalarında (windows/.../statik) harici URL yok.
D) Güncelleme istisnası (windows/src/kimlikwin/guncelleme.py) DAR ve kilitli: tek modül, tek ağ çağrısı, sabit ana makine
   listesi, yalnız https; başka bir modül ağ açarsa test kırmızı olur.
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


@pytest.mark.parametrize("host", ["example.com", "8.8.8.8", "192.0.2.1", "0.0.0.0", "::ffff:8.8.8.8",
                                  "api.github.com", "github.com", "objects.githubusercontent.com"])
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
    ("windows/src/kimlikwin/guncelleme.py", "urllib.request"):
        "UYGULAMANIN TEK DIŞ AĞ YOLU: GitHub sürüm denetimi/indirme (api.github.com + release dosyaları); "
        "kullanıcı kapatabilir, indirme/kurulum yalnız onayla. Sınırları test_guncelleme_istisnasi_dar kilitler",
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


def _modul_ihlalleri(dosyalar):
    """dosyalar: [(Path, kök'e göre ad)] -> (ihlal iletileri, kullanılan istisna anahtarları)."""
    ihlaller, kullanilan = [], set()
    for yol, ad in dosyalar:
        for m in set(_ice_aktarilanlar(yol)):
            y = _yasak_mi(m)
            if y is None:
                continue
            anahtar = (ad, y)
            kullanilan.add(anahtar)
            if anahtar not in IZINLI_ISTISNALAR:
                ihlaller.append(f"{anahtar[0]}: '{m}' içe aktarıyor")
    return ihlaller, kullanilan


def test_kaynakta_yasak_ag_modulu_yok():
    ihlaller, kullanilan = _modul_ihlalleri([(y, _goreli(y)) for y in _py_dosyalari()])
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
    ("windows/src/kimlikwin/guncelleme.py", "api.github.com"): "sürüm listesi (AgPolitikasi.api_taban varsayılanı)",
    ("windows/src/kimlikwin/guncelleme.py", "github.com"): "release dosyası adresi (AgPolitikasi.site_taban varsayılanı)",
}
YASAK_ALAN_ADLARI = ("cdn.", "googleapis", "gstatic", "jsdelivr", "unpkg", "cloudflare", "cdnjs",
                     "googletagmanager", "google-analytics", "doubleclick", "sentry", "segment.",
                     "mixpanel", "amplitude", "posthog", "facebook.net", "bootstrapcdn")


def _sunucu(url: str) -> str:
    return re.sub(r"^[a-z]+://", "", url, flags=re.I).split("/", 1)[0].split("?", 1)[0].rsplit("@", 1)[-1].rsplit(":", 1)[0] \
        if not url.split("://", 1)[1].startswith("[") else "[::1]"


def _url_ihlalleri(dosyalar):
    ihlaller = []
    for yol, ad in dosyalar:
        for m in URL_RE.finditer(yol.read_text(encoding="utf-8")):
            url = m.group(0)
            host = _sunucu(url).lower()
            if host in IZINLI_URL_SUNUCU or (ad, host) in IZINLI_PY_URL:
                continue
            ihlaller.append(f"{ad}: {url}")
    return ihlaller


def test_kaynakta_harici_url_veya_cdn_yok():
    ihlaller = _url_ihlalleri([(y, _goreli(y)) for y in _py_dosyalari()])
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
ARAYUZ_DOSYALARI = ("index.html", "harita.js", "figur.js", "harita.css", "guncelleme.js")


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
    assert "Get-NetTCPConnection" in izle and "127.0.0.1" in izle and izle.isascii()
    yml = (KOK / ".github/workflows/paket.yml").read_text(encoding="utf-8")
    assert "ci_paket.ps1" in yml and "ag_sonuc.json" in yml
    yaml = pytest.importorskip("yaml")
    assert "jobs" in yaml.safe_load(yml)


# ---------------------------------------------------------------- E) güncelleme istisnası dar ve kilitli

GUNCELLEME = "windows/src/kimlikwin/guncelleme.py"
BEKLENEN_ANA_MAKINELER = ("api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")


def test_baska_modul_ag_acarsa_test_kirmizi(tmp_path):
    """Denetim gerçekten ısırıyor mu: izinli listede olmayan her modül (adı ne olursa olsun) ağ açınca ihlal sayılır."""
    ornekler = {
        "windows/src/kimlikwin/kotu1.py": "import urllib.request\nurllib.request.urlopen('https://example.com')\n",
        "windows/src/kimlikwin/kotu2.py": "from urllib import request\n",
        "server/src/kimlikserver/kotu3.py": "import requests\n",
        "core/src/kimlikcore/kotu4.py": "__import__('http.client')\n",
        "windows/src/kimlikwin/kotu5.py": "import importlib\nimportlib.import_module('socket')\n",
        "importers/src/kimlikimport/guncelleme.py": "import urllib.request\n",          # aynı AD, başka klasör: izin yok
        GUNCELLEME.replace("guncelleme.py", "guncelleme_kopya.py"): "import urllib.request\n",
        "windows/src/kimlikwin/kotu6.py": "import ssl\n",
    }
    dosyalar = []
    for ad, kod in ornekler.items():
        yol = tmp_path / ad.replace("/", "_")
        yol.write_text(kod, encoding="utf-8")
        dosyalar.append((yol, ad))
    ihlaller, _ = _modul_ihlalleri(dosyalar)
    assert len(ihlaller) == len(ornekler), ihlaller
    # istisna YALNIZ guncelleme.py + urllib.request için geçerli: aynı dosya adıyla socket/ssl ya da http.client yine ihlal
    yol = tmp_path / "g.py"
    yol.write_text("import urllib.request\nimport socket\nimport ssl\nimport http.client\n", encoding="utf-8")
    ihlaller, kullanilan = _modul_ihlalleri([(yol, GUNCELLEME)])
    assert len(ihlaller) == 3 and (GUNCELLEME, "urllib.request") in kullanilan
    # harici URL de başka modülde yasak, guncelleme.py'de yalnız iki sabit ana makine serbest
    yol.write_text("A = 'https://api.github.com'\nB = 'https://evil.example/x'\nC = 'https://github.com'\n", encoding="utf-8")
    assert len(_url_ihlalleri([(yol, GUNCELLEME)])) == 1
    assert len(_url_ihlalleri([(yol, "windows/src/kimlikwin/baska.py")])) == 3


def test_guncelleme_istisnasi_dar():
    from kimlikwin import guncelleme as G
    kaynak = (KOK / GUNCELLEME).read_text(encoding="utf-8")
    agac = ast.parse(kaynak)
    # 1) ana makine listesi sabit (genişletmek bilinçli karar: bu testi de değiştirmeyi gerektirir) ve yalnız https
    assert G.IZINLI_ANA_MAKINELER == BEKLENEN_ANA_MAKINELER
    assert G.URETIM.izinli == BEKLENEN_ANA_MAKINELER and G.URETIM.https_zorunlu is True
    assert G.URETIM.api_taban == "https://api.github.com" and G.URETIM.site_taban == "https://github.com"
    assert G.DEPO == "avsessisozx/kimlik-merkezi" and G.KULLANICI_AJANI == "KimlikMerkezi-guncelleme"
    # 2) tek modülde yalnız urllib.request (socket/ssl/http.client/requests yok)
    yasaklar = {y for m in _ice_aktarilanlar(KOK / GUNCELLEME) if (y := _yasak_mi(m))}
    assert yasaklar == {"urllib.request"}, yasaklar
    # 3) TEK ağ çağrısı: opener.open(...) bir yerde; urlopen / başka açma çağrısı yok
    acmalar = [n for n in ast.walk(agac) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr in ("open", "urlopen", "request", "getresponse")]
    assert len(acmalar) == 1 and isinstance(acmalar[0].func.value, ast.Attribute) and acmalar[0].func.value.attr == "_opener", \
        [ast.unparse(n) for n in acmalar]
    assert "urlopen" not in kaynak
    # 4) ağ kapatma anahtarı ve adres denetimi o tek çağrıdan önce
    govde = kaynak[kaynak.index("def _ac("):kaynak.index("def _oku_sinirli(")]
    assert govde.index("kapali_mi()") < govde.index("adres_denetle(") < govde.index("self._opener.open(")
    assert "User-Agent" in govde and "Cookie" not in kaynak and "Authorization" not in kaynak and "Referer" not in kaynak
    # 5) test politikası (https_zorunlu=False, başka ana makine) yalnız testlerde: uygulama kaynağında hiçbir yerde yok
    for yol in _py_dosyalari():
        if _goreli(yol) == GUNCELLEME:
            continue
        k = yol.read_text(encoding="utf-8")
        assert "AgPolitikasi" not in k and "https_zorunlu" not in k and "politika=" not in k, _goreli(yol)
    assert "https_zorunlu=False" not in kaynak.replace("https_zorunlu: bool = True", "")
    # 6) guncelleme.py'yi yalnız Yonetici kullanır; ağ işlevlerini (denetle/indir/surdur) başka modül çağırmaz
    for yol in _py_dosyalari():
        ad = _goreli(yol)
        k = yol.read_text(encoding="utf-8")
        if ad not in (GUNCELLEME, "windows/src/kimlikwin/yonetici.py"):
            assert not re.search(r"\bguncelleme\b", k.replace("guncelleme_", "")) or ad.startswith("windows/src/kimlikwin/statik"), ad
    yon = (KOK / "windows/src/kimlikwin/yonetici.py").read_text(encoding="utf-8")
    assert re.findall(r"guncelleme\.(denetle|indir|surdur)\(", yon) and "onay=onay is True" in yon


def test_arayuz_guncelleme_ana_makinesi_icermez():
    """Arayüz GitHub'a doğrudan bağlanamaz: ana makine adı yalnız guncelleme.py'de; arayüz yalnız yerel /api/ uçlarını kullanır."""
    for yol in _statik_dosyalar():
        if yol.suffix in (".js", ".html", ".css"):
            metin = yol.read_text(encoding="utf-8", errors="replace")
            if yol.name == "echarts.min.js":
                continue
            assert "api.github.com" not in metin and "githubusercontent" not in metin, yol.name
    js = (STATIK / "guncelleme.js").read_text(encoding="utf-8")
    assert "fetch(" not in js and "XMLHttpRequest" not in js and not re.search(r"https?://", js)


def test_ci_guncelleme_denetimi_kapali_ve_izleyici_siki():
    """CI: kurulu uygulama KIMLIK_GUNCELLEME=kapali ile çalışır; ağ izleyici istisna TANIMAZ (dış bağlantı = hata)."""
    ps = (KOK / "windows/paket/ci_paket.ps1").read_text(encoding="utf-8")
    izle = (KOK / "windows/paket/ag_izle.ps1").read_text(encoding="utf-8")
    dene = (KOK / "windows/paket/kurulu_dene.py").read_text(encoding="utf-8")
    assert "KIMLIK_GUNCELLEME" in ps and "KIMLIK_GUNCELLEME" in dene
    kod = "\n".join(s for s in izle.splitlines() if not s.lstrip().startswith("#")).lower()   # yorumlar hariç
    assert "github" not in kod and "githubusercontent" not in kod, "ağ izleyiciye GitHub istisnası eklenmemeli"
    assert "/GUNCELLEME=1" in ps and "veri_parmak.py" in ps          # üstüne kurulumda veri klasörü korunuyor mu adımı
