"""PC alıcısı: yerel ağda HTTPS (docs/AKTARIM.md §3). Yalnız standart kütüphane + `cryptography` (sertifika).

Uçlar: `GET /durum`, `HEAD|PUT /giden/<cihaz_id>/<dosya_id>.jsonl`, `POST /eslestir`.
Kimlik: `Authorization: Bearer <cihaz_anahtari>` + `X-Cihaz`. Kimlik doğrulanmadan hiçbir bayt okunmaz/yazılmaz.

HUB ERİŞİMİ: alıcı iş parçacıkları Hub'a doğrudan dokunmaz; çağıranın verdiği `HubKopru` işlevlerini kullanır
(hepsi iş parçacığı güvenli olmalı). Windows uygulaması bunları kendi yazan-Hub kuyruğuna bağlar ya da
`DogrudanKopru(hub)` kullanır (Hub yöntemleri kendi kilidini tutar).

Dosya yerleşimi (veri klasörü altında):
  aktarim/sertifika.pem, aktarim/anahtar.pem      kendinden imzalı sertifika (bkz. sertifika.py)
  aktarim/gecici/<cihaz_id>/<dosya_id>.part|.sha  yarım yüklemeler
  gelen_aktarim/<cihaz_id>/<dosya_id>.jsonl       tamamlanmış, doğrulanmış dosyalar (içe alınınca kaldırılır)
Günlüğe kayıt içeriği yazılmaz: yalnız kimlikler, bayt ve kayıt sayıları.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import socket
import ssl
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol

from . import eslestirme, sertifika
from .bulma import BULMA_PORTU, Bulma
from .eslestirme import UUID_RE, EslestirmeKodlari, yerel_adres_mi

_log = logging.getLogger("kimlikserver.aktarim")

VARSAYILAN_PORT = 47823   # 47821 Windows uygulamasının yerel arayüz portudur
PROTOKOL = 1
GELEN_KLASOR = "gelen_aktarim"
_U = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
UUID_DOSYA_RE = re.compile(_U + r"\.jsonl")            # her yerde fullmatch
_YOL_RE = re.compile(rf"/giden/({_U})/({_U})\.jsonl")   # fullmatch
_ARALIK_RE = re.compile(r"bytes ([0-9]{1,12})-([0-9]{1,12})/([0-9]{1,12})")   # ASCII rakam (\d Unicode'u da yakalar)
_SAYI_RE = re.compile(r"[0-9]{1,12}")
_SHA_RE = re.compile(r"[0-9a-fA-F]{64}")

# Sınırlar (kurucuda değiştirilebilir; testler küçültür).
SINIRLAR = {
    "dosya_en_fazla": 512 * 1024 * 1024,   # tek dosya
    "parca_en_fazla": 8 * 1024 * 1024,     # tek PUT gövdesi
    "baslik_en_fazla": 16 * 1024,          # tüm başlıkların toplam boyutu
    "eslestir_govde_en_fazla": 4096,
    "soket_zaman_asimi_s": 30.0,           # her okuma/yazma (tek işlem)
    "el_sikisma_zaman_asimi_s": 10.0,      # TLS el sıkışmasının TOPLAMI
    "baslik_toplam_zaman_asimi_s": 10.0,   # istek satırı + tüm başlıkların TOPLAMI (slowloris)
    "bosta_zaman_asimi_s": 15.0,           # keep-alive bağlantıda yeni istek bekleme
    "govde_toplam_zaman_asimi_s": 120.0,   # bir parçanın tamamı (yavaş istemci)
    "eszamanli_baglanti": 32,
    "ip_basina_baglanti": 4,
    "cihaz_basina_yarim_yukleme": 8,
    "gecici_toplam_en_fazla": 1024 * 1024 * 1024,   # tüm yarım yüklemelerin toplam baytı
    "bos_disk_en_az": 500 * 1024 * 1024,   # ve boş alan >= 2 x kalan bayt
    "bosaltma_zaman_asimi_s": 5.0,         # hata yanıtından önce gövdeyi boşaltma süre üst sınırı
    "gecici_omur_s": 7 * 24 * 3600.0,      # bundan eski .part/.sha temizlenir
    "temizlik_araligi_s": 24 * 3600.0,
}


class HubKopru(Protocol):
    """Alıcının Hub'a erişim yüzü. Çağıran sağlar; tüm işlevler İŞ PARÇACIĞI GÜVENLİ olmalı (alıcı iş
    parçacıklarından çağrılır). Hata fırlatırsa istek 503 alır, hiçbir şey yazılmış sayılmaz."""

    def cihaz_dogrula(self, device_id: str, key_hash: str) -> bool: ...
    def cihaz_ekle(self, device_id: str, name: str, platform: str | None, key_hash: str) -> None: ...
    def dosya_var(self, device_id: str, dosya_id: str) -> str | None: ...        # sha256 ya da None
    def dosya_kaydet(self, device_id: str, dosya_id: str, sha256: str, kayit_sayisi: int) -> None: ...
    def tamamlandi(self, yol: Path) -> None: ...   # dosya gelen_aktarim/'a düştü ve kaydedildi (hızlı dönmeli)


class DogrudanKopru:
    """Hub'a doğrudan bağlanan basit köprü (Hub yöntemleri kendi kilidini tutar; yazan Hub gerekir)."""

    def __init__(self, hub, tamamlandi: Callable[[Path], None] | None = None):
        self._hub, self._tamamlandi = hub, tamamlandi

    def cihaz_dogrula(self, device_id, key_hash):
        return self._hub.cihaz_dogrula(device_id, key_hash)

    def cihaz_ekle(self, device_id, name, platform, key_hash):
        self._hub.cihaz_ekle(device_id, name, platform, key_hash)

    def dosya_var(self, device_id, dosya_id):
        return self._hub.aktarim_dosyasi_var(device_id, dosya_id)

    def dosya_kaydet(self, device_id, dosya_id, sha256, kayit_sayisi):
        self._hub.aktarim_dosyasi_kaydet(device_id, dosya_id, sha256, kayit_sayisi)
        self._hub.cihaz_goruldu(device_id)

    def tamamlandi(self, yol):
        if self._tamamlandi is not None:
            self._tamamlandi(yol)


def _sha256_dosya(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()




def _kes(sock) -> None:
    """Bağlantıyı başka iş parçacığından keser (engelli okumayı uyandırır). SSL katmanına dokunmaz."""
    try:
        socket.socket.shutdown(sock, socket.SHUT_RDWR)
    except (OSError, ValueError):
        pass


def _bekci(sock, sure_s: float) -> threading.Timer:
    """`sure_s` sonra bağlantıyı keser; işlem zamanında biterse `.cancel()` edilir (TOPLAM süre sınırı)."""
    t = threading.Timer(sure_s, _kes, args=(sock,))
    t.daemon = True
    t.start()
    return t


def _dizin_yap(yol: Path) -> None:
    """Klasörü (ve eksik üstlerini) oluşturur; aktarım klasörleri yalnız sahibine açık (POSIX 0700)."""
    var = [yol, *yol.parents]
    olusacak = [d for d in reversed(var) if not d.exists()]
    yol.mkdir(parents=True, exist_ok=True)
    for d in olusacak:
        try:
            if d == yol or d.name in ("aktarim", "gecici", GELEN_KLASOR) or d.parent.name in ("gecici", GELEN_KLASOR):
                os.chmod(d, 0o700)
        except OSError:  # pragma: no cover
            pass


def _ip(adres: str) -> str:
    a = str(adres).split("%", 1)[0]
    return a[7:] if a.lower().startswith("::ffff:") else a


class _Sunucu(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32

    def __init__(self, adres, a: "AktarimAlici", bag: ssl.SSLContext):
        self.a = a
        self.bag = bag
        self._toplam = 0
        self._acik: dict[socket.socket, str] = {}
        self._ip_sayac: dict[str, int] = {}
        self._bosta: dict[socket.socket, float] = {}   # yanıtı bitmiş, yeni istek bekleyen bağlantılar (zaman damgası)
        self._acik_kilit = threading.Lock()
        super().__init__(adres, _Isleyici)

    def get_request(self):
        ham, adres = self.socket.accept()
        # El sıkışma istek iş parçacığında (toplam süre sınırıyla): yavaş istemci kabul döngüsünü tutmaz.
        return self.bag.wrap_socket(ham, server_side=True, do_handshake_on_connect=False), adres

    def verify_request(self, request, client_address):
        if self.a.yalniz_yerel and not yerel_adres_mi(client_address[0]):
            return False    # bağlantı düzeyinde ret (el sıkışma bile yapılmaz)
        return True

    def process_request(self, request, client_address):
        ip = _ip(client_address[0])
        with self._acik_kilit:
            ip_dolu = self._ip_sayac.get(ip, 0) >= self.a.sinirlar["ip_basina_baglanti"]
            toplam_dolu = self._toplam >= self.a.sinirlar["eszamanli_baglanti"]
            kabul = not (ip_dolu or toplam_dolu)
            if not kabul:
                # Sınır dolu: EN ESKİ BOŞTA bağlantı (IP doluysa o IP'ninki) kapatılır; aktif istek/yükleme ve
                # el sıkışan bağlantılar etkilenmez. Yeni bağlantı kabul edilir (sayaç eskisi bitince düşer).
                aday = [(t, k) for k, t in self._bosta.items() if not ip_dolu or self._acik.get(k) == ip]
                if aday:
                    _, eski = min(aday, key=lambda x: x[0])
                    self._bosta.pop(eski, None)
                    _kes(eski)
                    kabul = True
            if kabul:
                self._ip_sayac[ip] = self._ip_sayac.get(ip, 0) + 1
                self._toplam += 1
                self._acik[request] = ip
        if not kabul:
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._biraktir(request)
            raise

    def _biraktir(self, request) -> None:
        with self._acik_kilit:
            self._bosta.pop(request, None)
            ip = self._acik.pop(request, None)
            if ip is None:
                return
            self._toplam -= 1
            n = self._ip_sayac.get(ip, 1) - 1
            if n <= 0:
                self._ip_sayac.pop(ip, None)
            else:
                self._ip_sayac[ip] = n

    def process_request_thread(self, request, client_address):
        # Sayaçlar soket kapanmadan ÖNCE düşer: istemci kapanmayı görüp hemen yeniden bağlandığında eski
        # bağlantı hâlâ sayılmasın (Windows/Linux zamanlama farkı). Yanıt gövdesi okunmadan kapatılan
        # bağlantıda (401 vb.) Windows okunmamış veriyle close'ta RST üretip yanıtı siler: kısa süre atılarak boşaltılır.
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self._biraktir(request)
            self._nazik_kapat(request)

    def _nazik_kapat(self, request) -> None:
        try:
            socket.socket.shutdown(request, socket.SHUT_WR)     # SSL katmanına dokunmadan: yanıt iletildi
            bitis = time.monotonic() + 2.0
            while True:
                kalan = bitis - time.monotonic()
                if kalan <= 0:
                    break
                request.settimeout(kalan)
                if not socket.socket.recv(request, 65536):
                    break
        except (OSError, ValueError):
            pass
        finally:
            self.shutdown_request(request)

    def handle_error(self, request, client_address):
        pass    # kopan bağlantı/sertifika reddi gürültü yapmasın (içerik zaten günlüğe girmez)

    def baglantilari_kes(self) -> None:
        with self._acik_kilit:
            acik = list(self._acik)
        for s in acik:
            _kes(s)


class _Isleyici(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: _Sunucu

    def setup(self):
        s = self.server.a.sinirlar
        self.request.settimeout(s["soket_zaman_asimi_s"])
        bekci = _bekci(self.request, s["el_sikisma_zaman_asimi_s"])      # el sıkışmanın TOPLAM süresi
        try:
            self.request.do_handshake()
        finally:
            bekci.cancel()
        self.timeout = s["soket_zaman_asimi_s"]
        super().setup()

    def log_message(self, *a):
        pass

    # --- süre sınırları: boşta keep-alive + istek satırı/başlıkların TOPLAM süresi
    def handle_one_request(self):
        s = self.server.a.sinirlar
        try:
            self.request.settimeout(s["bosta_zaman_asimi_s"])
            with self.server._acik_kilit:
                self.server._bosta[self.request] = time.monotonic()
            try:
                if not self.rfile.peek(1):
                    self.close_connection = True
                    return
            finally:
                with self.server._acik_kilit:
                    self.server._bosta.pop(self.request, None)
            self.request.settimeout(s["soket_zaman_asimi_s"])
        except (OSError, ssl.SSLError, ValueError):
            self.close_connection = True
            return
        self._bekci = _bekci(self.request, s["baslik_toplam_zaman_asimi_s"])
        try:
            super().handle_one_request()
        finally:
            self._bekci.cancel()

    def parse_request(self):
        try:
            return super().parse_request()
        finally:
            self._bekci.cancel()      # başlıklar tamam (ya da hata): gövde kendi sınırına tabidir

    # --- yanıt
    def _cevap(self, kod: int, govde: dict | None = None, *, kapat: bool = False, **basliklar):
        data = json.dumps(govde if govde is not None else {}).encode()
        if kapat:
            self.close_connection = True
        try:
            self.send_response(kod)
            for k, v in basliklar.items():
                self.send_header(k.replace("_", "-"), str(v))
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if kapat:
                self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except (OSError, ssl.SSLError, ValueError):
            self.close_connection = True

    def _hata(self, kod: int, ileti: str, **basliklar):
        # Gövde okunmadıysa bağlantı yeniden kullanılamaz: kapat. Ama istemci gövdeyi yazarken bağlantı
        # sıfırlanıp yanıt kodu görülmesin diye (kimlikli PUT'ta) gövde SINIRLI boşaltılır.
        self._bosalt()
        self._cevap(kod, {"hata": ileti}, kapat=True, **basliklar)

    _bosaltilacak = 0

    def _bosalt(self) -> None:
        n, self._bosaltilacak = self._bosaltilacak, 0
        lim = self.server.a.sinirlar
        n = min(n, lim["parca_en_fazla"])
        if n <= 0:
            return
        bitis = time.monotonic() + lim["bosaltma_zaman_asimi_s"]
        try:
            while n > 0:
                kalan = bitis - time.monotonic()
                if kalan <= 0:
                    break
                self.request.settimeout(kalan)
                b = self.rfile.read(min(n, 65536))
                if not b:
                    break
                n -= len(b)
        except (OSError, ssl.SSLError, ValueError):
            pass
        self.close_connection = True

    # --- kimlik
    def _kimlik(self) -> str | None:
        a = self.server.a
        cihaz = (self.headers.get("X-Cihaz") or "").strip()
        ver = self.headers.get("Authorization") or ""
        if not UUID_RE.fullmatch(cihaz) or not ver.startswith("Bearer ") or not (8 <= len(ver) - 7 <= 200):
            return None
        try:
            return cihaz if a.hub.cihaz_dogrula(cihaz, eslestirme.anahtar_ozeti(ver[7:].strip())) else None
        except Exception as e:  # noqa: BLE001
            _log.error("kimlik doğrulama hatası (%s)", type(e).__name__)
            raise _Hub503() from None

    def _baslik_boyutu_tamam(self) -> bool:
        n = sum(len(k) + len(v) for k, v in self.headers.items())
        return n <= self.server.a.sinirlar["baslik_en_fazla"]

    def _sayi(self, ad: str) -> int:
        """Katı ASCII rakam; yoksa/bozuksa -1."""
        v = self.headers.get(ad)
        return int(v) if v is not None and _SAYI_RE.fullmatch(v) else -1

    # --- yönlendirme
    def do_GET(self):
        self._yonlendir()

    do_HEAD = do_PUT = do_POST = do_DELETE = do_PATCH = do_OPTIONS = do_GET

    def _yonlendir(self):
        a = self.server.a
        try:
            if not self._baslik_boyutu_tamam():
                return self._hata(431, "başlıklar çok büyük")
            yol, yontem = self.path, self.command
            if yol == "/durum" and yontem in ("GET", "HEAD"):
                # Kimliksiz yanıt yalnız protokol sürümü; PC adı/sürüm kimlikli istekte (ve eşleştirme kodunda).
                govde = {"protokol": PROTOKOL}
                try:
                    if self._kimlik() is not None:
                        govde.update({"surum": a.surum, "pc_adi": a.pc_adi})
                except _Hub503:
                    pass
                return self._cevap(200, govde)
            if yol == "/eslestir":
                return self._eslestir() if yontem == "POST" else self._hata(405, "yalnız POST")
            if yol.startswith("/giden/"):
                cihaz = self._kimlik()              # kimliksiz her istek (yöntem/yol ne olursa olsun) aynı 401
                if cihaz is None:   # hiçbir şey okunmaz/yazılmaz
                    return self._hata(401, "yetkisiz")
                if yontem not in ("HEAD", "PUT"):
                    return self._hata(405, "yalnız HEAD ve PUT")
                m = _YOL_RE.fullmatch(yol)
                if not m:
                    return self._hata(400, "geçersiz yol")
                if m.group(1) != cihaz:
                    return self._hata(403, "başka cihazın yoluna erişilemez")
                return (self._head if yontem == "HEAD" else self._put)(cihaz, m.group(2))
            return self._hata(404, "bulunamadı")
        except _Hub503:
            self._hata(503, "hizmet geçici olarak kullanılamıyor")
        except (OSError, ssl.SSLError, socket.timeout):
            self.close_connection = True
        except Exception as e:  # noqa: BLE001
            _log.error("istek hatası (%s)", type(e).__name__)
            self._hata(500, "sunucu hatası")

    # --- /eslestir
    def _eslestir(self):
        a = self.server.a
        n = self._sayi("Content-Length")
        if n < 0 or n > a.sinirlar["eslestir_govde_en_fazla"]:
            return self._hata(413 if n > 0 else 411, "gövde boyutu geçersiz")
        ham = self._govde_oku(n)
        if ham is None:
            return
        try:
            govde = json.loads(ham.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, RecursionError):
            return self._hata(400, "geçerli JSON değil")
        try:
            kod, yanit = eslestirme.eslestir(govde, a.kodlar, a.hub.cihaz_ekle, a.pc_adi)
        except Exception as e:  # noqa: BLE001
            _log.error("eşleştirme hatası (%s)", type(e).__name__)
            return self._hata(503, "hizmet geçici olarak kullanılamıyor")
        if kod == 200:
            _log.info("cihaz eşleşti: %s", yanit["cihaz_id"])
            return self._cevap(200, yanit)
        self._cevap(kod, yanit, kapat=(kod == 401))

    # --- /giden
    def _govde_oku(self, n: int) -> bytes | None:
        """Tam n bayt ya da None (kopma/zaman aşımı: bağlantı kapatılır, hiçbir şey yazılmaz).
        Gövdenin TOPLAM süresi sınırlıdır (bekçi): damla damla gönderen istemci de kesilir."""
        self._bosaltilacak = 0
        bekci = _bekci(self.request, self.server.a.sinirlar["govde_toplam_zaman_asimi_s"])
        parcalar, kalan = [], n
        try:
            while kalan > 0:
                b = self.rfile.read(min(kalan, 65536))
                if not b:
                    raise ConnectionError()
                parcalar.append(b)
                kalan -= len(b)
        except (OSError, ssl.SSLError, ValueError):
            self.close_connection = True
            return None
        finally:
            bekci.cancel()
        return b"".join(parcalar)

    def _govdeyi_at(self, n: int) -> bool:
        return self._govde_oku(n) is not None

    def _durum(self, cihaz: str, dosya: str) -> tuple[str, int]:
        a = self.server.a
        son = a.gelen_klasoru / cihaz / f"{dosya}.jsonl"
        if a.hub.dosya_var(cihaz, dosya) is not None:
            return "var", son.stat().st_size if son.is_file() else 0
        part = a.gecici_klasoru / cihaz / f"{dosya}.part"
        if part.is_file():
            return "kismi", part.stat().st_size
        return "yok", 0

    def _head(self, cihaz, dosya):
        self.server.a.tam_boyutlu_kurtar_kilitli(cihaz, dosya)
        d, n = self._durum(cihaz, dosya)
        self._cevap(200, {"durum": d, "alinan": n}, X_Durum=d, X_Alinan=n)

    def _put(self, cihaz: str, dosya: str):
        a, lim = self.server.a, self.server.a.sinirlar
        uzunluk = self._sayi("Content-Length")
        self._bosaltilacak = uzunluk if not self.headers.get("Transfer-Encoding") else 0
        if self.headers.get("Transfer-Encoding"):
            return self._hata(501, "Transfer-Encoding desteklenmiyor; Content-Length kullanın")
        if uzunluk <= 0:
            return self._hata(411, "Content-Length gerekli (yalnız rakamlar)")
        if uzunluk > lim["parca_en_fazla"]:
            return self._hata(413, "parça çok büyük")
        m = _ARALIK_RE.fullmatch(self.headers.get("Content-Range") or "")
        sha = (self.headers.get("X-Sha256") or "").strip().lower()
        if not m or not _SHA_RE.fullmatch(sha):
            return self._hata(400, "Content-Range ya da X-Sha256 geçersiz")
        bas, son, toplam = map(int, m.groups())
        if son - bas + 1 != uzunluk or son >= toplam:
            return self._hata(400, "aralık Content-Length ile tutarsız")
        if toplam > lim["dosya_en_fazla"]:
            return self._hata(413, "dosya çok büyük")

        with a.kilit_al(cihaz, dosya) as kilit:
            if not kilit.acquire(blocking=False):   # aynı dosyaya eşzamanlı ikinci yükleme
                part = a.gecici_klasoru / cihaz / f"{dosya}.part"
                return self._hata(409, "dosya şu an başka bir istekle yükleniyor", X_Durum="kismi",
                                  X_Alinan=part.stat().st_size if part.is_file() else 0)
            try:
                try:
                    return self._put_kilitli(cihaz, dosya, bas, uzunluk, toplam, sha)
                except Exception:
                    # Beklenmeyen hata: yarım dosya ve yan dosyası kalmasın (istemci sıfırdan dener)
                    d = a.gecici_klasoru / cihaz
                    (d / f"{dosya}.part").unlink(missing_ok=True)
                    (d / f"{dosya}.sha").unlink(missing_ok=True)
                    raise
            finally:
                kilit.release()

    @staticmethod
    def _yan_oku(sha_dosya: Path) -> tuple[str, int]:
        try:
            sha, toplam = sha_dosya.read_text("ascii").split()
            return sha, int(toplam)
        except (OSError, ValueError):
            return "", -1

    def _put_kilitli(self, cihaz, dosya, bas, uzunluk, toplam, sha):
        a = self.server.a
        lim = a.sinirlar
        a.tam_boyutlu_kurtar(cihaz, dosya)     # kilit elimizde
        durum, mevcut = self._durum(cihaz, dosya)
        if durum == "var":
            if not self._govdeyi_at(uzunluk):
                return
            return self._cevap(200, {"durum": "var"}, X_Durum="var", X_Alinan=mevcut)
        dizin = a.gecici_klasoru / cihaz
        part, sha_dosya = dizin / f"{dosya}.part", dizin / f"{dosya}.sha"
        if mevcut > 0:
            eski_sha, eski_toplam = self._yan_oku(sha_dosya)
            if eski_sha != sha:       # başka içerikle başlamış eski yarım yükleme: sıfırdan
                part.unlink(missing_ok=True)
                sha_dosya.unlink(missing_ok=True)
                mevcut = 0
            elif eski_toplam != toplam:    # aynı dosyanın parçalarında toplam değişti: tutarsız
                part.unlink(missing_ok=True)
                sha_dosya.unlink(missing_ok=True)
                _log.warning("toplam boyut değişti: cihaz=%s dosya=%s", cihaz, dosya)
                return self._hata(422, "Content-Range toplamı parçalar arasında değişti; baştan başlayın",
                                  X_Durum="yok", X_Alinan=0)
        if mevcut == 0:
            ret = a.yeni_yukleme_kotasi(cihaz)
            if ret:
                return self._hata(*ret)
        if bas != mevcut:
            if not self._govdeyi_at(uzunluk):
                return
            return self._cevap(409, {"durum": "kismi" if mevcut else "yok", "alinan": mevcut},
                               X_Durum="kismi" if mevcut else "yok", X_Alinan=mevcut)
        bos = shutil.disk_usage(a.gecici_klasoru).free
        if bos < max(2 * (toplam - mevcut), lim["bos_disk_en_az"]):
            return self._hata(507, "PC'de yeterli boş disk alanı yok")
        veri = self._govde_oku(uzunluk)   # yarım gövde = hiçbir şey yazılmaz
        if veri is None:
            return
        _dizin_yap(dizin)
        if mevcut == 0:
            sha_dosya.write_text(f"{sha} {toplam}", "ascii")
        with open(part, "ab") as f:
            f.write(veri)
            f.flush()
            os.fsync(f.fileno())
        yeni = bas + uzunluk
        if yeni < toplam:
            return self._cevap(200, {"durum": "kismi", "alinan": yeni}, X_Durum="kismi", X_Alinan=yeni)
        self._tamamla(cihaz, dosya, part, sha_dosya, sha)

    def _tamamla(self, cihaz, dosya, part: Path, sha_dosya: Path, beklenen_sha: str):
        a = self.server.a
        ok, neden, hedef = a.tamamla(cihaz, dosya, part, sha_dosya, beklenen_sha)
        if not ok:
            return self._cevap(422, {"hata": neden, "alinan": 0}, X_Durum="yok", X_Alinan=0)
        self._cevap(201, {"durum": "var"}, X_Durum="var", X_Alinan=hedef.stat().st_size)


class _Hub503(Exception):
    pass


_OTOMATIK = sertifika.OTOMATIK
YENILENDI_UYARISI = "Güvenlik sertifikası yenilendi; telefonların yeniden eşleştirilmesi gerekir."


class AktarimAlici:
    """Telefon aktarımı alıcısı. `baslat()` dinlemeye başlar (TLS 1.2+), `durdur()` tüm bağlantıları keser."""

    def __init__(self, hub_saglayici: HubKopru, veri_klasoru: Path | str, port: int = VARSAYILAN_PORT,
                 adres: str = "0.0.0.0", yalniz_yerel: bool = True, *, pc_adi: str | None = None,
                 surum: str = "0.2.0", saglayici=_OTOMATIK, bulma_port: int | None = BULMA_PORTU,
                 sinirlar: dict | None = None):
        self.hub = hub_saglayici
        self.veri = Path(veri_klasoru)
        self.adres, self.yalniz_yerel = adres, yalniz_yerel
        self._port_ayar = port
        self.port = port
        self.pc_adi = pc_adi or socket.gethostname()
        self.surum = surum
        self._saglayici = saglayici
        self._bulma_ayar = bulma_port
        self.sinirlar = {**SINIRLAR, **(sinirlar or {})}
        self.kodlar = EslestirmeKodlari()
        self.gelen_klasoru = self.veri / GELEN_KLASOR
        self.gecici_klasoru = self.veri / "aktarim" / "gecici"
        self._srv: _Sunucu | None = None
        self._iplik: threading.Thread | None = None
        self._temizlik: threading.Thread | None = None
        self._dur = threading.Event()
        self._bulma: Bulma | None = None
        self._sert: sertifika.Sertifika | None = None
        self._kilitler: dict[str, list] = {}      # anahtar -> [Lock, kullanıcı sayısı]; boşalınca silinir
        self._kilitler_kilidi = threading.Lock()
        self._alinan = 0

    # --- sertifika / eşleştirme
    def sertifika(self) -> sertifika.Sertifika:
        if self._sert is None:
            self._sert = sertifika.hazirla(self.veri, self._saglayici)
        return self._sert

    @property
    def parmak_izi(self) -> str:
        return self.sertifika().parmak_izi

    def eslestirme_kodu_uret(self, sure_s: float = eslestirme.KOD_SURESI_S, adresler: list[str] | None = None) -> str:
        """Yeni tek kullanımlık kod üretir ve `km1:` metnini döner (Windows uygulaması QR olarak da gösterir)."""
        kod = self.kodlar.uret(sure_s)
        if adresler is None:
            adresler = eslestirme.yerel_ipv4_adresleri()
        return eslestirme.eslestirme_metni(adresler, self.port, self.parmak_izi, kod, self.pc_adi)

    @contextlib.contextmanager
    def kilit_al(self, cihaz: str, dosya: str):
        """Dosya başına kilit; kimse kullanmıyorsa sözlükten silinir (sözlük büyümez)."""
        anahtar = f"{cihaz}/{dosya}"
        with self._kilitler_kilidi:
            g = self._kilitler.setdefault(anahtar, [threading.Lock(), 0])
            g[1] += 1
        try:
            yield g[0]
        finally:
            with self._kilitler_kilidi:
                g[1] -= 1
                if g[1] <= 0:
                    self._kilitler.pop(anahtar, None)

    # --- tamamlama (SHA + doğrulayıcı); işleyiciden ve kurtarmadan çağrılır
    def tamamla(self, cihaz, dosya, part: Path, sha_dosya: Path, beklenen_sha: str):
        """(ok, neden, hedef). Başarısızsa geçici dosyalar silinir."""

        def reddet(neden: str):
            part.unlink(missing_ok=True)
            sha_dosya.unlink(missing_ok=True)
            _log.warning("dosya reddedildi: cihaz=%s dosya=%s neden=%s", cihaz, dosya, neden)
            return False, neden, None

        gercek = _sha256_dosya(part)
        if not hmac.compare_digest(gercek, beklenen_sha):
            return reddet("SHA-256 uyuşmuyor")
        # TEK doğrulayıcı: içe aktarıcının kendi kuralları (aksi halde alıcı kabul eder, içe aktarıcı reddederdi)
        from kimlikimport.android_giden import dosya_dogrula

        ok, kayit, neden = dosya_dogrula(part, cihaz, dosya)
        if not ok:
            return reddet(f"dosya geçersiz: {neden}")
        hedef_dizin = self.gelen_klasoru / cihaz
        _dizin_yap(hedef_dizin)
        hedef = hedef_dizin / f"{dosya}.jsonl"
        os.replace(part, hedef)          # atomik; önce dosya, sonra tablo (kopma halinde dosya kaybolmaz)
        sha_dosya.unlink(missing_ok=True)
        self.hub.dosya_kaydet(cihaz, dosya, gercek, kayit)
        self._alinan += 1
        _log.info("dosya alındı: cihaz=%s dosya=%s bayt=%d kayit=%d", cihaz, dosya, hedef.stat().st_size, kayit)
        try:
            self.hub.tamamlandi(hedef)
        except Exception as e:  # noqa: BLE001 - geri çağrı hatası aktarımı bozmaz
            _log.warning("tamamlandı geri çağrısı hata verdi (%s)", type(e).__name__)
        return True, "", hedef

    def tam_boyutlu_kurtar(self, cihaz: str, dosya: str) -> None:
        """Dosya kilidi ELDEYKEN: .part boyutu bildirilen toplama eşitse (tamamlama öncesi ölüm) tamamlamayı
        yeniden dener; tutmazsa geçici dosyalar silinir."""
        dizin = self.gecici_klasoru / cihaz
        part, sha_dosya = dizin / f"{dosya}.part", dizin / f"{dosya}.sha"
        try:
            if not part.is_file():
                return
            sha, toplam = _Isleyici._yan_oku(sha_dosya)
            if toplam < 0 or not _SHA_RE.fullmatch(sha) or part.stat().st_size != toplam:
                return
            self.tamamla(cihaz, dosya, part, sha_dosya, sha.lower())
        except Exception as e:  # noqa: BLE001
            _log.warning("tam boyutlu geçici dosya kurtarılamadı (%s)", type(e).__name__)

    def tam_boyutlu_kurtar_kilitli(self, cihaz: str, dosya: str) -> None:
        with self.kilit_al(cihaz, dosya) as kilit:
            if not kilit.acquire(blocking=False):
                return
            try:
                self.tam_boyutlu_kurtar(cihaz, dosya)
            finally:
                kilit.release()

    def baslangic_kurtarma(self) -> None:
        for p in list(self.gecici_klasoru.glob("*/*.part")):
            if UUID_RE.fullmatch(p.parent.name) and UUID_DOSYA_RE.fullmatch(p.stem + ".jsonl"):
                self.tam_boyutlu_kurtar_kilitli(p.parent.name, p.stem)

    # --- kota / temizlik
    def yeni_yukleme_kotasi(self, cihaz: str):
        """Yeni (sıfırdan) yükleme kabul edilebilir mi? Reddedilirse (kod, ileti) döner; mevcutlar sürer."""
        lim = self.sinirlar
        d = self.gecici_klasoru / cihaz
        acik = sum(1 for p in d.glob("*.part")) if d.is_dir() else 0
        if acik >= lim["cihaz_basina_yarim_yukleme"]:
            return 429, "bu cihazın açık yarım yükleme sayısı sınırı dolu"
        toplam = 0
        for p in self.gecici_klasoru.glob("*/*.part"):
            try:
                toplam += p.stat().st_size
            except OSError:
                pass
        if toplam >= lim["gecici_toplam_en_fazla"]:
            return 507, "PC'deki geçici alan sınırı dolu"
        return None

    def eski_gecicileri_temizle(self, simdi: float | None = None) -> int:
        """`gecici_omur_s`'ten eski .part/.sha dosyalarını siler; silinen sayısını döner."""
        simdi = time.time() if simdi is None else simdi
        n = 0
        for p in list(self.gecici_klasoru.glob("*/*")):
            if p.suffix not in (".part", ".sha"):
                continue
            try:
                if simdi - p.stat().st_mtime > self.sinirlar["gecici_omur_s"]:
                    p.unlink()
                    n += 1
            except OSError:
                pass
        for d in self.gecici_klasoru.glob("*"):
            try:
                d.rmdir()       # boşsa
            except OSError:
                pass
        return n

    def _temizlik_dongusu(self) -> None:
        while not self._dur.wait(self.sinirlar["temizlik_araligi_s"]):
            try:
                self.eski_gecicileri_temizle()
            except Exception as e:  # noqa: BLE001
                _log.warning("geçici temizliği hata verdi (%s)", type(e).__name__)

    # --- yaşam döngüsü
    def calisiyor(self) -> bool:
        return self._srv is not None

    def baslat(self) -> None:
        if self._srv is not None:
            return
        s = self.sertifika()
        bag = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        bag.minimum_version = ssl.TLSVersion.TLSv1_2
        bag.load_cert_chain(s.sertifika_yolu, s.anahtar_yolu, password=(s.parola.decode() if s.parola else None))
        _dizin_yap(self.gelen_klasoru)
        _dizin_yap(self.gecici_klasoru)
        try:
            self.eski_gecicileri_temizle()
        except Exception as e:  # noqa: BLE001
            _log.warning("geçici temizliği hata verdi (%s)", type(e).__name__)
        try:
            self.baslangic_kurtarma()
        except Exception as e:  # noqa: BLE001
            _log.warning("başlangıç kurtarması hata verdi (%s)", type(e).__name__)
        self._dur.clear()
        self._temizlik = threading.Thread(target=self._temizlik_dongusu, name="aktarim-temizlik", daemon=True)
        self._temizlik.start()
        self._srv = _Sunucu((self.adres, self._port_ayar), self, bag)
        self.port = self._srv.server_address[1]
        self._iplik = threading.Thread(target=self._srv.serve_forever, kwargs={"poll_interval": 0.2},
                                       name="aktarim-alici", daemon=True)
        self._iplik.start()
        if self._bulma_ayar is not None:
            self._bulma = Bulma(s.parmak_izi, lambda: self.port, self._bulma_ayar, self.adres, self.yalniz_yerel)
            if not self._bulma.baslat():
                self._bulma = None
        _log.info("aktarım alıcısı dinliyor: port=%d", self.port)

    def durdur(self) -> None:
        srv, self._srv = self._srv, None
        if srv is None:
            return
        self._dur.set()
        if self._bulma is not None:
            self._bulma.durdur()
            self._bulma = None
        srv.shutdown()
        srv.server_close()
        srv.baglantilari_kes()
        if self._iplik is not None:
            self._iplik.join(timeout=5)
        self._iplik = None
        _log.info("aktarım alıcısı durdu")

    def durum(self) -> dict:
        sert = self._sert
        gecerli, neden = self.kodlar.durum()
        yenilendi = bool(sert and sert.yeniden_uretildi)
        return {
            "calisiyor": self._srv is not None, "port": self.port,
            "bulma_port": self._bulma.port if self._bulma is not None else 0,
            "parmak_izi": sert.parmak_izi if sert else None,
            "anahtar_sarili": sert.anahtar_sarili if sert else None,
            "sertifika_yenilendi": yenilendi, "uyari": YENILENDI_UYARISI if yenilendi else None,
            "alinan_dosya": self._alinan, "pc_adi": self.pc_adi,
            # neden: None | "sure_doldu" | "cok_yanlis_deneme" | "kullanildi" | "uretilmedi" | "iptal"
            "eslestirme_kodu_gecerli": gecerli, "eslestirme_kodu_gecersizlik_nedeni": neden,
        }

    def __enter__(self) -> "AktarimAlici":
        self.baslat()
        return self

    def __exit__(self, *exc) -> None:
        self.durdur()
