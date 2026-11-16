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

import hashlib
import hmac
import json
import logging
import os
import re
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

VARSAYILAN_PORT = 47821
PROTOKOL = 1
GELEN_KLASOR = "gelen_aktarim"
UUID_DOSYA_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.jsonl$")
_YOL_RE = re.compile(
    r"^/giden/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$")
_ARALIK_RE = re.compile(r"^bytes (\d{1,12})-(\d{1,12})/(\d{1,12})$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")

# Sınırlar (kurucuda değiştirilebilir; testler küçültür).
SINIRLAR = {
    "dosya_en_fazla": 512 * 1024 * 1024,   # tek dosya
    "parca_en_fazla": 8 * 1024 * 1024,     # tek PUT gövdesi
    "baslik_en_fazla": 16 * 1024,          # tüm başlıkların toplam boyutu
    "eslestir_govde_en_fazla": 4096,
    "satir_en_fazla": 4 * 1024 * 1024,     # dosyadaki tek satır
    "soket_zaman_asimi_s": 30.0,           # her okuma/yazma
    "el_sikisma_zaman_asimi_s": 10.0,
    "govde_toplam_zaman_asimi_s": 120.0,   # bir parçanın tamamı (yavaş istemci)
    "eszamanli_baglanti": 32,
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


class _Gecersiz(Exception):
    pass


def dosya_denetle(yol: Path, cihaz_id: str, dosya_id: str, satir_en_fazla: int) -> int:
    """Tam dosyayı akışla denetler: başlık (cihaz/dosya kimliği yoldakiyle aynı), her satır JSON nesnesi,
    son satır kapanış ve `kayit_sayisi` gerçek kayıt satırı sayısına eşit. Kayıt sayısını döner."""
    kayit = 0
    baslik_var = kapandi = False
    n = 0
    with open(yol, "rb") as f:
        while True:
            ham = f.readline(satir_en_fazla + 1)
            if not ham:
                break
            n += 1
            if len(ham) > satir_en_fazla and not ham.endswith(b"\n"):
                raise _Gecersiz(f"{n}. satır çok uzun")
            if kapandi:
                raise _Gecersiz("kapanış kaydından sonra satır var")
            try:
                o = json.loads(ham.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise _Gecersiz(f"{n}. satır geçerli JSON değil") from None
            if not isinstance(o, dict):
                raise _Gecersiz(f"{n}. satır nesne değil")
            if not baslik_var:
                if o.get("baslik") is not True:
                    raise _Gecersiz("ilk satır başlık değil")
                if o.get("cihaz_id") != cihaz_id or o.get("dosya_id") != dosya_id:
                    raise _Gecersiz("başlıktaki cihaz/dosya kimliği yolla uyuşmuyor")
                baslik_var = True
            elif o.get("kapanis") is True:
                k = o.get("kayit_sayisi")
                if not isinstance(k, int) or isinstance(k, bool) or k != kayit:
                    raise _Gecersiz("kapanıştaki kayıt sayısı dosyadakiyle tutmuyor")
                kapandi = True
            else:
                kayit += 1
    if not baslik_var:
        raise _Gecersiz("dosya boş")
    if not kapandi:
        raise _Gecersiz("kapanış kaydı yok")
    return kayit


def _sha256_dosya(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class _Sunucu(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32

    def __init__(self, adres, a: "AktarimAlici", bag: ssl.SSLContext):
        self.a = a
        self.bag = bag
        self._sem = threading.BoundedSemaphore(a.sinirlar["eszamanli_baglanti"])
        self._acik: set[socket.socket] = set()
        self._acik_kilit = threading.Lock()
        super().__init__(adres, _Isleyici)

    def get_request(self):
        ham, adres = self.socket.accept()
        # El sıkışma istek iş parçacığında (zaman aşımıyla): yavaş istemci kabul döngüsünü tutmaz.
        return self.bag.wrap_socket(ham, server_side=True, do_handshake_on_connect=False), adres

    def verify_request(self, request, client_address):
        if self.a.yalniz_yerel and not yerel_adres_mi(client_address[0]):
            return False    # bağlantı düzeyinde ret (el sıkışma bile yapılmaz)
        return True

    def process_request(self, request, client_address):
        if not self._sem.acquire(blocking=False):
            self.shutdown_request(request)
            return
        with self._acik_kilit:
            self._acik.add(request)
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._biraktir(request)
            raise

    def _biraktir(self, request) -> None:
        with self._acik_kilit:
            self._acik.discard(request)
        self._sem.release()

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._biraktir(request)

    def handle_error(self, request, client_address):
        pass    # kopan bağlantı/sertifika reddi gürültü yapmasın (içerik zaten günlüğe girmez)

    def baglantilari_kes(self) -> None:
        with self._acik_kilit:
            acik = list(self._acik)
        for s in acik:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except (OSError, ValueError):
                pass


class _Isleyici(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: _Sunucu

    def setup(self):
        s = self.server.a.sinirlar
        self.request.settimeout(s["el_sikisma_zaman_asimi_s"])
        self.request.do_handshake()
        self.request.settimeout(s["soket_zaman_asimi_s"])
        self.timeout = s["soket_zaman_asimi_s"]
        super().setup()

    def log_message(self, *a):
        pass

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
        except (OSError, ssl.SSLError):
            self.close_connection = True

    def _hata(self, kod: int, ileti: str, **basliklar):
        # Gövde okunmadıysa bağlantı yeniden kullanılamaz: kapat.
        self._cevap(kod, {"hata": ileti}, kapat=True, **basliklar)

    # --- kimlik
    def _kimlik(self) -> str | None:
        a = self.server.a
        cihaz = (self.headers.get("X-Cihaz") or "").strip()
        ver = self.headers.get("Authorization") or ""
        if not UUID_RE.match(cihaz) or not ver.startswith("Bearer ") or not (8 <= len(ver) - 7 <= 200):
            return None
        try:
            return cihaz if a.hub.cihaz_dogrula(cihaz, eslestirme.anahtar_ozeti(ver[7:].strip())) else None
        except Exception as e:  # noqa: BLE001
            _log.error("kimlik doğrulama hatası (%s)", type(e).__name__)
            raise _Hub503() from None

    def _baslik_boyutu_tamam(self) -> bool:
        n = sum(len(k) + len(v) for k, v in self.headers.items())
        return n <= self.server.a.sinirlar["baslik_en_fazla"]

    # --- yönlendirme
    def do_GET(self):
        self._yonlendir()

    do_HEAD = do_PUT = do_POST = do_GET

    def do_DELETE(self):
        self._hata(405, "yöntem desteklenmiyor")

    do_PATCH = do_OPTIONS = do_DELETE

    def _yonlendir(self):
        a = self.server.a
        try:
            if not self._baslik_boyutu_tamam():
                return self._hata(431, "başlıklar çok büyük")
            yol, yontem = self.path, self.command
            if yol == "/durum" and yontem in ("GET", "HEAD"):
                return self._cevap(200, {"surum": a.surum, "pc_adi": a.pc_adi, "protokol": PROTOKOL})
            if yol == "/eslestir":
                return self._eslestir() if yontem == "POST" else self._hata(405, "yalnız POST")
            if yol.startswith("/giden/"):
                if yontem not in ("HEAD", "PUT"):
                    return self._hata(405, "yalnız HEAD ve PUT")
                cihaz = self._kimlik()
                if cihaz is None:   # hiçbir şey okunmaz/yazılmaz
                    return self._hata(401, "yetkisiz")
                m = _YOL_RE.match(yol)
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
        try:
            n = int(self.headers.get("Content-Length") or "-1")
        except ValueError:
            n = -1
        if n < 0 or n > a.sinirlar["eslestir_govde_en_fazla"]:
            return self._hata(413 if n > 0 else 411, "gövde boyutu geçersiz")
        ham = self._govde_oku(n)
        if ham is None:
            return
        try:
            govde = json.loads(ham.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
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
        """Tam n bayt ya da None (kopma/zaman aşımı: bağlantı kapatılır, hiçbir şey yazılmaz)."""
        bitis = time.monotonic() + self.server.a.sinirlar["govde_toplam_zaman_asimi_s"]
        parcalar, kalan = [], n
        try:
            while kalan > 0:
                if time.monotonic() > bitis:
                    raise socket.timeout()
                b = self.rfile.read(min(kalan, 65536))
                if not b:
                    raise ConnectionError()
                parcalar.append(b)
                kalan -= len(b)
        except (OSError, ssl.SSLError):
            self.close_connection = True
            return None
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
        d, n = self._durum(cihaz, dosya)
        self._cevap(200, {"durum": d, "alinan": n}, X_Durum=d, X_Alinan=n)

    def _put(self, cihaz: str, dosya: str):
        a, lim = self.server.a, self.server.a.sinirlar
        try:
            uzunluk = int(self.headers.get("Content-Length") or "-1")
        except ValueError:
            uzunluk = -1
        if self.headers.get("Transfer-Encoding"):
            return self._hata(501, "Transfer-Encoding desteklenmiyor; Content-Length kullanın")
        if uzunluk <= 0:
            return self._hata(411, "Content-Length gerekli")
        if uzunluk > lim["parca_en_fazla"]:
            return self._hata(413, "parça çok büyük")
        m = _ARALIK_RE.match(self.headers.get("Content-Range") or "")
        sha = (self.headers.get("X-Sha256") or "").strip().lower()
        if not m or not _SHA_RE.match(sha):
            return self._hata(400, "Content-Range ya da X-Sha256 geçersiz")
        bas, son, toplam = map(int, m.groups())
        if son - bas + 1 != uzunluk or son >= toplam:
            return self._hata(400, "aralık Content-Length ile tutarsız")
        if toplam > lim["dosya_en_fazla"]:
            return self._hata(413, "dosya çok büyük")

        kilit = a.dosya_kilidi(cihaz, dosya)
        if not kilit.acquire(blocking=False):   # aynı dosyaya eşzamanlı ikinci yükleme
            part = a.gecici_klasoru / cihaz / f"{dosya}.part"
            return self._hata(409, "dosya şu an başka bir istekle yükleniyor", X_Durum="kismi",
                              X_Alinan=part.stat().st_size if part.is_file() else 0)
        try:
            return self._put_kilitli(cihaz, dosya, bas, uzunluk, toplam, sha)
        finally:
            kilit.release()

    def _put_kilitli(self, cihaz, dosya, bas, uzunluk, toplam, sha):
        a = self.server.a
        durum, mevcut = self._durum(cihaz, dosya)
        if durum == "var":
            if not self._govdeyi_at(uzunluk):
                return
            return self._cevap(200, {"durum": "var"}, X_Durum="var", X_Alinan=mevcut)
        dizin = a.gecici_klasoru / cihaz
        part, sha_dosya = dizin / f"{dosya}.part", dizin / f"{dosya}.sha"
        if mevcut > 0:   # başka içerikle başlamış eski yarım yükleme: sıfırdan
            eski = sha_dosya.read_text("ascii").strip() if sha_dosya.is_file() else ""
            if eski != sha:
                part.unlink(missing_ok=True)
                sha_dosya.unlink(missing_ok=True)
                mevcut = 0
        if bas != mevcut:
            if not self._govdeyi_at(uzunluk):
                return
            return self._cevap(409, {"durum": "kismi" if mevcut else "yok", "alinan": mevcut},
                               X_Durum="kismi" if mevcut else "yok", X_Alinan=mevcut)
        veri = self._govde_oku(uzunluk)   # yarım gövde = hiçbir şey yazılmaz
        if veri is None:
            return
        dizin.mkdir(parents=True, exist_ok=True)
        if mevcut == 0:
            sha_dosya.write_text(sha, "ascii")
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

        def reddet(neden: str):
            part.unlink(missing_ok=True)
            sha_dosya.unlink(missing_ok=True)
            _log.warning("dosya reddedildi: cihaz=%s dosya=%s neden=%s", cihaz, dosya, neden)
            self._cevap(422, {"hata": neden, "alinan": 0}, X_Durum="yok", X_Alinan=0)

        gercek = _sha256_dosya(part)
        if not hmac.compare_digest(gercek, beklenen_sha):
            return reddet("SHA-256 uyuşmuyor")
        try:
            kayit = dosya_denetle(part, cihaz, dosya, a.sinirlar["satir_en_fazla"])
        except _Gecersiz as e:
            return reddet(f"dosya geçersiz: {e}")
        hedef_dizin = a.gelen_klasoru / cihaz
        hedef_dizin.mkdir(parents=True, exist_ok=True)
        hedef = hedef_dizin / f"{dosya}.jsonl"
        os.replace(part, hedef)          # atomik; önce dosya, sonra tablo (kopma halinde dosya kaybolmaz)
        sha_dosya.unlink(missing_ok=True)
        a.hub.dosya_kaydet(cihaz, dosya, gercek, kayit)
        a._alinan += 1
        _log.info("dosya alındı: cihaz=%s dosya=%s bayt=%d kayit=%d", cihaz, dosya, hedef.stat().st_size, kayit)
        try:
            a.hub.tamamlandi(hedef)
        except Exception as e:  # noqa: BLE001 - geri çağrı hatası aktarımı bozmaz
            _log.warning("tamamlandı geri çağrısı hata verdi (%s)", type(e).__name__)
        self._cevap(201, {"durum": "var"}, X_Durum="var", X_Alinan=hedef.stat().st_size)


class _Hub503(Exception):
    pass


_OTOMATIK = sertifika.OTOMATIK


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
        self._bulma: Bulma | None = None
        self._sert: sertifika.Sertifika | None = None
        self._kilitler: dict[str, threading.Lock] = {}
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

    def dosya_kilidi(self, cihaz: str, dosya: str) -> threading.Lock:
        with self._kilitler_kilidi:
            return self._kilitler.setdefault(f"{cihaz}/{dosya}", threading.Lock())

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
        self.gelen_klasoru.mkdir(parents=True, exist_ok=True)
        self.gecici_klasoru.mkdir(parents=True, exist_ok=True)
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
        return {
            "calisiyor": self._srv is not None, "port": self.port,
            "bulma_port": self._bulma.port if self._bulma is not None else 0,
            "parmak_izi": sert.parmak_izi if sert else None,
            "anahtar_sarili": sert.anahtar_sarili if sert else None,
            "alinan_dosya": self._alinan, "pc_adi": self.pc_adi,
            "eslestirme_kodu_gecerli": self.kodlar.gecerli_mi(),
        }

    def __enter__(self) -> "AktarimAlici":
        self.baslat()
        return self

    def __exit__(self, *exc) -> None:
        self.durdur()
