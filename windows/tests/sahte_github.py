"""Sahte GitHub (yalnız 127.0.0.1): sürüm listesi JSON'u, SHA256SUMS.txt ve Range destekli büyük kurulum dosyası.

Testler gerçek GitHub'a ASLA çıkmaz (ag_koruma.py bunu zaten engeller). Sunucu, istemcinin gönderdiği her isteği
(yol + başlıklar) `istekler` listesine yazar; böylece 'onaysız indirme yok' ve 'başlıklar genel' gibi iddialar sınanır.

Özellikler (SahteGithub alanları):
  kapi_esigi   bu kadar bayttan sonra `kapi` açılana dek DURUR (duraklat/iptal testleri için; None: hiç durmaz)
  range_destek False ise Range başlığı yok sayılır (200 ile baştan gönderir)
  bozuk_ozet   True ise SHA256SUMS.txt yanlış özet taşır
  ozet_yok     True ise SHA256SUMS.txt'de kurulum dosyası satırı yoktur
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEPO = "avsessisozx/kimlik-merkezi"


def icerik_uret(etiket: str, boyut: int) -> bytes:
    """Etikete özgü, deterministik 'kurulum dosyası' (ardışık bloklar farklı olsun ki yanlış birleştirme fark edilsin)."""
    bloklar, n, i = [], 0, 0
    while n < boyut:
        b = hashlib.sha256(f"{etiket}:{i}".encode()).digest() * 32      # 1 KiB
        bloklar.append(b)
        n += len(b)
        i += 1
    return b"".join(bloklar)[:boyut]


class SahteGithub:
    def __init__(self, surumler: list[dict] | None = None, boyut: int = 3 * 1024 * 1024):
        self.boyut = boyut
        self.surumler = surumler if surumler is not None else [{"etiket": "v0.9.0"}]
        self.kapi_esigi: int | None = None
        self.kapi = threading.Event()
        self.range_destek = True
        self.bozuk_ozet = False
        self.ozet_yok = False
        self.ham_liste: bytes | None = None           # sürüm listesi yerine bu ham gövde (geçersiz JSON testi)
        self.yonlendir_disari: str | None = None      # exe isteğini bu adrese 302'le (beyaz liste testi)
        self.kes_esigi: int | None = None             # ilk exe yanıtında bu kadar bayttan sonra bağlantıyı KOPAR
        self._kesildi = False
        self.yonlendir_ic = False                     # exe isteğini aynı sunucudaki /cdn/... adresine 302'le
        self.istekler: list[dict] = []
        self._kilit = threading.Lock()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Isleyici)
        self.httpd.sahte = self  # type: ignore[attr-defined]
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self._t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._t.start()

    @property
    def taban(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def politika(self, **kw):
        from kimlikwin.guncelleme import AgPolitikasi
        d = dict(api_taban=self.taban, site_taban=self.taban, izinli=("127.0.0.1",), https_zorunlu=False,
                 proxy_kullan=False, zaman_asimi=0.6, yeniden_deneme=2, bekleme=0.05)
        d.update(kw)
        return AgPolitikasi(**d)

    def icerik(self, etiket: str) -> bytes:
        return icerik_uret(etiket, self.boyut)

    def ozet(self, etiket: str) -> str:
        return hashlib.sha256(self.icerik(etiket)).hexdigest()

    def exe_adi(self, etiket: str) -> str:
        return f"KimlikMerkezi-Kurulum-{etiket}.exe"

    def liste(self) -> list[dict]:
        cikti = []
        for s in self.surumler:
            e = s["etiket"]
            onek = f"{self.taban}/{DEPO}/releases/download/{e}/"
            ad = self.exe_adi(e)
            assets = s.get("assets")
            if assets is None:
                assets = [
                    {"name": ad, "size": self.boyut, "state": "uploaded", "browser_download_url": onek + ad},
                    {"name": "SHA256SUMS.txt", "size": 200, "state": "uploaded", "browser_download_url": onek + "SHA256SUMS.txt"},
                    {"name": f"KimlikMerkezi-{e}.sbom.cdx.json", "size": 10, "state": "uploaded",
                     "browser_download_url": onek + "sbom.json"},
                ]
            cikti.append({"tag_name": e, "draft": s.get("draft", False), "prerelease": s.get("prerelease", True),
                          "name": f"Kimlik Merkezi {e}", "assets": assets})
        return cikti

    def kapat(self) -> None:
        self.kapi.set()
        self.httpd.shutdown()
        self.httpd.server_close()

    def exe_istekleri(self) -> list[dict]:
        with self._kilit:
            return [i for i in self.istekler if i["yol"].endswith(".exe")]

    def kaydet(self, yol: str, basliklar: dict) -> None:
        with self._kilit:
            self.istekler.append({"yol": yol, "basliklar": dict(basliklar)})


class _Isleyici(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _gonder(self, kod, govde: bytes, tur="application/json", ekstra=None):
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        for k, v in (ekstra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(govde)

    def do_GET(self):
        s: SahteGithub = self.server.sahte  # type: ignore[attr-defined]
        basliklar = {k.lower(): v for k, v in self.headers.items()}
        yol = self.path
        # Tarayıcı testi denetim uçları (istek günlüğüne yazılmaz)
        if yol == "/_sayac":
            with s._kilit:
                govde = {"toplam": len(s.istekler), "exe": len([i for i in s.istekler if i["yol"].endswith(".exe")]),
                         "ozet": len([i for i in s.istekler if i["yol"].endswith("SHA256SUMS.txt")]),
                         "aralikli": [i["basliklar"]["range"] for i in s.istekler if "range" in i["basliklar"]]}
            return self._gonder(200, json.dumps(govde).encode())
        if yol in ("/_kapi/ac", "/_kapi/kapat"):
            s.kapi.set() if yol.endswith("ac") else s.kapi.clear()
            return self._gonder(200, b"{}")
        m = re.fullmatch(r"/_ayar/(bozuk_ozet|kapi_esigi)/(.+)", yol)
        if m:
            ad, deger = m.groups()
            setattr(s, ad, (deger == "1") if ad == "bozuk_ozet" else (None if deger == "yok" else int(deger)))
            return self._gonder(200, b"{}")
        s.kaydet(yol, basliklar)
        if yol.split("?")[0] == f"/repos/{DEPO}/releases":
            return self._gonder(200, s.ham_liste if s.ham_liste is not None else json.dumps(s.liste()).encode())
        m = re.fullmatch(rf"/{DEPO}/releases/download/([^/]+)/(.+)", yol)
        if m:
            etiket, ad = m.groups()
            if ad == "SHA256SUMS.txt":
                if s.ozet_yok:
                    metin = f"{'0' * 64}  baska-dosya.txt\n"
                else:
                    ozet = ("f" * 64) if s.bozuk_ozet else s.ozet(etiket)
                    metin = f"{ozet}  {s.exe_adi(etiket)}\n{'a' * 64}  KimlikMerkezi-{etiket}.sbom.cdx.json\n"
                return self._gonder(200, metin.encode(), "text/plain")
            if ad == s.exe_adi(etiket):
                if s.yonlendir_disari:
                    return self._gonder(302, b"", ekstra={"Location": s.yonlendir_disari})
                if s.yonlendir_ic:
                    return self._gonder(302, b"", ekstra={"Location": f"{s.taban}/cdn/{etiket}/{ad}"})
                return self._dosya(s, etiket, basliklar)
        m = re.fullmatch(r"/cdn/([^/]+)/(.+)", yol)
        if m:
            return self._dosya(s, m.group(1), basliklar)
        self._gonder(404, b"{}")

    def _dosya(self, s: SahteGithub, etiket: str, basliklar: dict):
        veri = s.icerik(etiket)
        n = len(veri)
        basla, kod, ekstra = 0, 200, {}
        r = basliklar.get("range")
        if r and s.range_destek:
            m = re.fullmatch(r"bytes=(\d+)-", r)
            if not m or int(m.group(1)) >= n:
                return self._gonder(416, b"", ekstra={"Content-Range": f"bytes */{n}"})
            basla = int(m.group(1))
            kod = 206
            ekstra["Content-Range"] = f"bytes {basla}-{n - 1}/{n}"
        self.send_response(kod)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(n - basla))
        for k, v in ekstra.items():
            self.send_header(k, v)
        self.end_headers()
        sent, esik = 0, s.kapi_esigi
        try:
            while basla + sent < n:
                if esik is not None and sent >= esik and not s.kapi.is_set():
                    self.wfile.flush()
                    if not s.kapi.wait(20):
                        return
                if s.kes_esigi is not None and not s._kesildi and sent >= s.kes_esigi:
                    s._kesildi = True
                    self.close_connection = True
                    return
                parca = veri[basla + sent: basla + sent + 65536]
                if esik is not None and sent < esik:
                    parca = parca[: esik - sent]
                if s.kes_esigi is not None and not s._kesildi and sent < s.kes_esigi:
                    parca = parca[: s.kes_esigi - sent]
                self.wfile.write(parca)
                sent += len(parca)
        except OSError:
            pass
