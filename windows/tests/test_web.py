"""Gerçek yerel HTTP sunucusu üzerinden uçtan uca ekran mantığı (tarayıcısız)."""
import json
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from kimlikwin.web import Sunucu

FIX = Path(__file__).resolve().parents[2] / "importers" / "fixtures"


class Istemci:
    def __init__(self, s: Sunucu):
        self.s = s

    def post(self, ad, girdi=None, *, jeton="dogru", host=None, origin=None):
        basliklar = {"Content-Type": "application/json"}
        if jeton == "dogru":
            basliklar["X-Kimlik-Jeton"] = self.s.jeton
        elif jeton:
            basliklar["X-Kimlik-Jeton"] = jeton
        if host:
            basliklar["Host"] = host
        if origin:
            basliklar["Origin"] = origin
        req = urllib.request.Request(f"http://127.0.0.1:{self.s.port}/api/{ad}",
                                     json.dumps(girdi or {}).encode(), basliklar)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def api(self, ad, girdi=None):
        kod, j = self.post(ad, girdi)
        assert kod == 200, (ad, kod, j)
        return j


@pytest.fixture
def sunucu(yonetici):
    s = Sunucu(yonetici, 0)
    s.baslat()
    yield s
    s.durdur()


@pytest.fixture
def ist(sunucu, yonetici, veri):
    c = Istemci(sunucu)
    c.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False})
    return c


def test_yalniz_loopback_ve_guvenlik_basliklari(sunucu):
    assert sunucu.httpd.server_address[0] == "127.0.0.1"
    c = Istemci(sunucu)
    assert c.post("acilis", jeton=None)[0] == 403
    assert c.post("acilis", jeton="yanlis")[0] == 403
    assert c.post("acilis", host="evil.example:80")[0] == 403          # DNS yeniden bağlama
    assert c.post("acilis", origin="http://evil.example")[0] == 403    # başka site
    assert c.post("acilis")[0] == 200
    with urllib.request.urlopen(f"http://127.0.0.1:{sunucu.port}/saglik") as r:
        assert json.loads(r.read())["uygulama"] == "kimlik-merkezi"
    with urllib.request.urlopen(f"http://127.0.0.1:{sunucu.port}/") as r:
        html = r.read().decode()
        assert sunucu.jeton in html and "__JETON__" not in html and 'lang="tr"' in html
    # dışarıdan erişilebilecek bir adrese bağlı değil
    ip = socket.gethostbyname(socket.gethostname()) if socket.gethostname() else "127.0.0.1"
    if not ip.startswith("127."):
        with pytest.raises(OSError):
            socket.create_connection((ip, sunucu.port), timeout=2)


def test_bilinmeyen_islem_reddedilir(ist):
    assert ist.post("hub")[0] == 400
    assert ist.post("__class__")[0] == 400
    assert ist.post("ara", {"olmayan_arguman": 1})[0] == 400


def bekle_ice(ist, sn=60):
    t = time.time()
    while time.time() - t < sn:
        d = ist.api("ice_aktar_durum")
        if d["durum"] != "calisiyor":
            return d
        time.sleep(0.2)
    raise AssertionError("içe aktarma bitmedi")


def test_ice_aktar_ara_zaman_kaynak_silme(ist, tmp_path):
    assert ist.post("ice_aktar_baslat", {"yol": ""})[0] == 400
    r = ist.api("ice_aktar_baslat", {"yol": str(FIX / "reddit")})
    assert r["durum"] == "calisiyor"
    d = bekle_ice(ist)
    assert d["durum"] == "bitti", d
    assert "Eklenen" in d["sonuc"]
    durum = ist.api("durum")
    assert durum["ozet"]["counts"]["event"] > 0 and durum["kaynak_sayisi"] == 1
    z = ist.api("zaman", {"limit": 5})["kayitlar"]
    assert z and z[0]["zaman"] >= z[-1]["zaman"]
    # arama: zaman çizelgesindeki bir kaydın bir kelimesi bulunur
    kelime = next((w for k in z for w in k["metin"].split() if len(w) > 4 and w.isalpha()), None)
    if kelime:
        assert any(k["id"] for k in ist.api("ara", {"sorgu": kelime})["kayitlar"])
    # aynı dosya tekrar: yeni kayıt eklenmez ("kaldığı yerden devam" güvenli)
    ist.api("ice_aktar_baslat", {"yol": str(FIX / "reddit")})
    d2 = bekle_ice(ist)
    assert d2["durum"] == "bitti" and "Eklenen: 0" in d2["sonuc"]
    # yarım iş kaydı bitti olarak işaretli
    assert ist.api("acilis")["yarim_is"] is None
    # kaynak kaldırma (gizler) ve kalıcı silme (onay ister)
    sid = ist.api("kaynaklar")["kaynaklar"][0]["id"]
    kod, j = ist.post("kaynak_sil", {"kaynak_id": sid, "onay": ""})
    assert kod == 400 and j["kod"] == "onay_yok"
    n = ist.api("kaynak_kaldir", {"kaynak_id": sid})["gizlenen"]
    assert n > 0 and ist.api("zaman", {"limit": 5})["kayitlar"] == []
    sil = ist.api("kaynak_sil", {"kaynak_id": sid, "onay": "sil"})
    assert sil["silinen_olay"] >= 0
    # kalıcı silinen girdi: yine de sorulur
    ist.api("ice_aktar_baslat", {"yol": str(FIX / "reddit")})
    d3 = bekle_ice(ist)
    assert d3["durum"] == "hata" and d3["hata_kodu"] == "daha_once_silinmis"
    ist.api("ice_aktar_baslat", {"yol": str(FIX / "reddit"), "yine_de": True})
    assert bekle_ice(ist)["durum"] == "bitti"


def test_taninmayan_dosya_hata_verir(ist, tmp_path):
    f = tmp_path / "rastgele.txt"
    f.write_text("merhaba", encoding="utf-8")
    ist.api("ice_aktar_baslat", {"yol": str(f)})
    d = bekle_ice(ist)
    assert d["durum"] == "hata" and d["hata"]
    assert ist.post("ice_aktar_baslat", {"yol": str(tmp_path / "yok.zip")})[0] == 200
    assert bekle_ice(ist)["durum"] == "hata"


def test_persona_celiski_ve_kimlik_karti(ist):
    p = ist.api("persona_liste")
    assert {k["kimlik"] for k in p["kategoriler"]} >= {"kimlik", "tercihler", "cihazlar"}
    a = ist.api("persona_ekle", {"metin": "Kahveyi sütsüz içerim", "kategori": "tercihler", "anahtar": "kahve"})["id"]
    b = ist.api("persona_ekle", {"metin": "Kahveyi sütlü içerim", "kategori": "tercihler", "anahtar": "kahve"})["id"]
    c = ist.api("celiskiler")["celiskiler"]
    assert len(c) == 1 and c[0]["eski"]["id"] == a and c[0]["yeni"]["id"] == b
    assert ist.api("durum")["acik_celiski"] == 1
    assert ist.api("celiski_coz", {"secilen_id": a})["kapanan"] == 1
    assert ist.api("celiskiler")["celiskiler"] == []
    ist.api("persona_guncelle", {"bilgi_id": a, "metin": "Kahveyi sütsüz ve şekersiz içerim"})
    kart = ist.api("kimlik_karti")["markdown"]
    assert "şekersiz" in kart and "sütlü" not in kart
    ist.api("persona_sil", {"bilgi_id": a})
    assert "şekersiz" not in ist.api("kimlik_karti")["markdown"]
    # belgeden işaretle: kaynak zorunlu ve kimlik kartında kaynak adı görünür
    ist.api("ice_aktar_baslat", {"yol": str(FIX / "reddit")})
    bekle_ice(ist)
    sid = ist.api("kaynaklar")["kaynaklar"][0]["id"]
    ist.api("persona_ekle", {"metin": "Reddit kullanıcıyım", "kategori": "ilgi", "kaynak_id": sid})
    assert "kaynak:" in ist.api("kimlik_karti")["markdown"]
    assert ist.post("persona_ekle", {"metin": "", "kategori": "ilgi"})[0] == 400


def test_persona_sure_kontrolu_acilista(yonetici, veri):
    """Açılışta süresi dolan cihaz bilgisi eskir (saat enjekte edilir)."""
    from datetime import datetime, timedelta, timezone

    yonetici.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False})
    from kimlikserver.persona import Persona as P
    eski = datetime.now(timezone.utc) - timedelta(days=400)
    P(yonetici.uygulama.hub, clock=lambda: eski).add_fact("Eski telefon", "cihazlar")
    yonetici.kapat()
    yonetici.baslat()
    assert yonetici.uygulama.eskiyen == 1
    assert yonetici.api("acilis", {})["eskiyen"] == 1
    assert yonetici.api("persona_sure_kontrol", {})["eskiyen"] == 0


def test_erisim_anahtar_izin_hassas_onay_ve_kayit(ist):
    r = ist.api("anahtar_uret", {"ad": "Deneme Uygulaması"})
    app, anahtar = r["id"], r["anahtar"]
    assert anahtar.startswith("kim_")
    # hassas kategori onaysız açılamaz
    kod, j = ist.post("izin_ver", {"app_id": app, "kategori": "eposta"})
    assert kod == 400 and "hassas" in j["hata"]
    assert ist.post("izin_ver", {"app_id": app, "kategori": "eposta", "hassas_onay": True})[0] == 200
    # toplu açma hassasları KAPSAMAZ
    ist.api("izin_kaldir", {"app_id": app, "kategori": "eposta"})
    acilan = ist.api("izin_toplu", {"app_id": app})["acilan"]
    assert "notlar" in acilan and not ({"eposta", "mesaj", "konum"} & set(acilan))
    # süreli izin
    ist.api("izin_ver", {"app_id": app, "kategori": "konum", "hassas_onay": True, "bitis": "2099-01-01T00:00:00Z"})
    u = next(x for x in ist.api("erisim")["uygulamalar"] if x["id"] == app)
    assert next(i for i in u["izinler"] if i["kategori"] == "konum")["bitis"].startswith("2099")
    ist.api("anahtar_iptal", {"app_id": app})
    assert ist.post("izin_ver", {"app_id": app, "kategori": "notlar"})[0] == 400
    assert ist.api("erisim_kaydi")["satirlar"] == []
    b = ist.api("baglanti_bilgisi", {"anahtar": anahtar})
    assert anahtar in b["metin"] and b["ortam"]["KIMLIK_ANAHTAR"] == anahtar


def test_mcp_stdio_uygulamanin_urettigi_anahtarla(ist, veri):
    """Uygulama anahtar üretip izin verir; gerçek MCP süreci aynı veriyi okur (uygulama yazan olarak açıkken)."""
    import asyncio
    import sys

    from mcp import Client, StdioServerParameters

    ist.api("persona_ekle", {"metin": "Ben deneme kullanıcısıyım", "kategori": "kimlik"})
    r = ist.api("anahtar_uret", {"ad": "MCP deneme"})
    ist.api("izin_ver", {"app_id": r["id"], "kategori": "persona"})
    env = {"KIMLIK_VERI": str(veri), "KIMLIK_ANAHTAR": r["anahtar"]}
    if "PYTHONPATH" in os.environ:   # çocuk süreç bu çalışma ağacındaki kodu kullansın
        env["PYTHONPATH"] = os.environ["PYTHONPATH"]
    p = StdioServerParameters(command=sys.executable, args=["-m", "kimlikserver.mcp"], env=env)

    async def go():
        async with Client(p) as c:
            return (await c.list_tools()).tools, await c.call_tool("kimlik_karti", {})
    araclar, kart = asyncio.run(asyncio.wait_for(go(), 60))
    assert {t.name for t in araclar} == {"kategorileri_listele", "ara", "zaman_cizelgesi", "persona_getir", "kimlik_karti", "persona_oner", "ornekle"} and "deneme kullanıcısıyım" in kart.structured_content["veri"]
    log = ist.api("erisim_kaydi")["satirlar"]
    assert [s["arac"] for s in log] == ["kimlik_karti"] and log[0]["sonuc"] == "ok"


def test_ayarlar_tema_ve_hata_raporu(ist):
    assert ist.api("ayar_yaz", {"tema": "koyu"})["tema"] == "koyu"
    assert ist.post("ayar_yaz", {"tema": "mor"})[0] == 400
    h = ist.api("hakkinda")
    assert "SmartScreen" in h["smartscreen_notu"] and "BitLocker" in h["sifreleme_notu"]
    assert "Kimlik Merkezi hata raporu" in ist.api("hata_raporu", {"adim": "x"})["metin"]
    assert ist.api("acilis")["tema"] == "koyu"


def test_tum_kategorilerin_etiketi_var_ve_bilinmeyen_kategori_patlamaz(ist, monkeypatch):
    from kimlikcore import Category

    from kimlikwin import cekirdek
    eksik = [k for k in Category.ALL if k not in cekirdek.KATEGORI_ETIKETLERI]
    assert not eksik, f"etiketi olmayan kategori: {eksik}"
    assert cekirdek.KATEGORI_ETIKETLERI["sohbet"] == "Yapay zekâ sohbetleri"
    # çekirdeğe yeni kategori eklenip etiket unutulursa: KeyError değil, kimlik gösterilir
    monkeypatch.setattr(Category, "ALL", frozenset(Category.ALL | {"yeni_kat"}))
    kat = {k["kimlik"]: k for k in ist.api("durum")["kategoriler"]}
    assert kat["yeni_kat"]["ad"] == "yeni_kat" and kat["sohbet"]["ad"] == "Yapay zekâ sohbetleri"
    assert any(k["kimlik"] == "yeni_kat" for k in ist.api("erisim")["kategoriler"])


def test_sohbet_hassas_ayri_onay_ister_ve_toplu_acmaya_girmez(ist):
    app = ist.api("anahtar_uret", {"ad": "Sohbet deneme"})["id"]
    k = {x["kimlik"]: x for x in ist.api("erisim")["kategoriler"]}
    assert k["sohbet"]["hassas"] is True
    kod, j = ist.post("izin_ver", {"app_id": app, "kategori": "sohbet"})
    assert kod == 400 and "hassas" in j["hata"]
    assert "sohbet" not in ist.api("izin_toplu", {"app_id": app})["acilan"]
    assert ist.post("izin_ver", {"app_id": app, "kategori": "sohbet", "hassas_onay": True})[0] == 200


def _ham(sunucu, istek: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", sunucu.port), timeout=5) as c:
        c.sendall(istek)
        veri = b""
        while True:
            try:
                x = c.recv(65536)
            except OSError:
                break
            if not x:
                break
            veri += x
            if b"\r\n\r\n" in veri:
                bas, _, govde = veri.partition(b"\r\n\r\n")
                n = [int(l.split(b":")[1]) for l in bas.split(b"\r\n") if l.lower().startswith(b"content-length")]
                if n and len(govde) >= n[0]:
                    break
        return veri


def test_ascii_disi_jeton_403_doner(sunucu):
    """ASCII dışı X-Kimlik-Jeton başlığı yakalanmamış istisna/kopan bağlantı değil, 403 vermeli."""
    host = f"127.0.0.1:{sunucu.port}".encode()
    istek = (b"POST /api/acilis HTTP/1.1\r\nHost: " + host + b"\r\nConnection: close\r\n"
             b"Content-Type: application/json\r\nX-Kimlik-Jeton: \xe9\xe9\xe9\r\nContent-Length: 2\r\n\r\n{}")
    yanit = _ham(sunucu, istek)
    assert yanit.startswith(b"HTTP/1.1 403"), yanit[:80]
    # sunucu hâlâ yaşıyor ve doğru jetonla çalışıyor
    assert Istemci(sunucu).post("acilis")[0] == 200


def test_csp_ek_yonergeler(sunucu):
    with urllib.request.urlopen(f"http://127.0.0.1:{sunucu.port}/") as r:
        csp = r.headers["Content-Security-Policy"]
    for y in ("base-uri 'none'", "form-action 'none'", "object-src 'none'", "frame-ancestors 'none'"):
        assert y in csp
