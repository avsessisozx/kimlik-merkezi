"""Güncelleme denetimi, indirme ve kurulum: uygulamanın AĞA ÇIKAN TEK YOLU (docs/AG-GARANTISI.md).

Bütün ağ kodu bu dosyadadır; başka hiçbir modül ağ açamaz (statik denetim testi bunu kilitler).

Ne yapar
  1. Denetim: GitHub'daki herkese açık depo (DEPO) için yalnız `GET /repos/<depo>/releases` sorar.
     Kullanıcı ayarı kapatmadıkça açılışta, ya da Ayarlar'daki düğmeyle. Hiçbir kişisel/sürüm bilgisi
     gönderilmez: kullanıcı ajanı genel ("KimlikMerkezi-guncelleme"), çerez, yetki ve yönlendiren-sayfa başlığı yok; kendi sürümünüz
     yalnız YEREL karşılaştırmada kullanılır.
  2. İndirme: yalnız `indir(onay=True)` ile (kullanıcı "indirmek ister misin?" sorusuna evet dedikten sonra).
     Aynı sürümün SHA256SUMS.txt dosyası da o anda alınır. HTTP Range ile duraklat/devam ve iptal vardır.
  3. Doğrulama: indirilen dosyanın SHA-256 özeti SHA256SUMS.txt ile eşleşmezse dosya silinir, hata gösterilir.
     (Kurulum paketi imzasızdır; doğrulama YALNIZ bu özet ile yapılır. Özet dosyası ve paket aynı sürüm
     sayfasından geldiği için, GitHub hesabı/yayını ele geçirilmişse bu doğrulama koruma sağlamaz.)
  4. Kurulum: yalnız `kur(onay=True)` ile (ikinci onay); kurulum, uygulama TAMAMEN kapandıktan sonra
     (`kurulumu_baslat`) Inno Setup sessiz bayraklarıyla başlatılır. Veri klasörüne dokunulmaz.

Güvenlik: yalnız https; yönlendirmelerde ana makine beyaz listesi; indirme adresi yalnız bu deponun
`releases/download/<etiket>/<dosya>` yolu olabilir; dosya adı katı kalıba uymalı (yol geçişi yok); dosya
yalnız uygulamaya ait klasöre (ayar dizini/guncelleme) yazılır.

Test için ağ politikası (`AgPolitikasi`) kurucuya verilebilir (sahte yerel sunucu). Uygulamanın kendisi
(Yonetici) hiçbir zaman politika vermez; varsayılan `URETIM` politikası yalnız https ve GitHub ana makinelerini kabul eder.
Çevre değişkeni KIMLIK_GUNCELLEME=kapali her ağ erişimini kapatır (CI ve testler bunu kullanır)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__, gunluk

DEPO = "avsessisozx/kimlik-merkezi"
KULLANICI_AJANI = "KimlikMerkezi-guncelleme"
# Yalnız bu ana makinelere bağlanılır (yönlendirmeler dahil). Genişletmek bilinçli bir karardır:
# entegrasyon/test_ag_garantisi.py kümenin aynen bu olduğunu denetler.
#   api.github.com                      sürüm listesi (JSON)
#   github.com                          release dosyası adresi (302 ile aşağıdaki depolamaya yönlenir)
#   objects.githubusercontent.com,      release dosyalarının depolandığı GitHub CDN adları
#   release-assets.githubusercontent.com
IZINLI_ANA_MAKINELER = ("api.github.com", "github.com", "objects.githubusercontent.com",
                        "release-assets.githubusercontent.com")
EXE_KALIBI = re.compile(r"KimlikMerkezi-Kurulum-v[0-9A-Za-z][0-9A-Za-z._-]{0,60}\.exe")
OZET_ADI = "SHA256SUMS.txt"
MAKS_EXE = 800 * 1024 * 1024
MAKS_API_GOVDE = 2 * 1024 * 1024
MAKS_OZET_GOVDE = 64 * 1024
PARCA = 64 * 1024
KAPALI_ORTAM = "KIMLIK_GUNCELLEME"


class GuncellemeHatasi(Exception):
    """Kullanıcıya gösterilebilir (Türkçe) hata; devam_edilebilir: 'Devam' ile yeniden denenebilir."""

    def __init__(self, mesaj: str, devam_edilebilir: bool = False):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.devam_edilebilir = devam_edilebilir


class GuncellemeKapali(GuncellemeHatasi):
    pass


class OnayGerekli(GuncellemeHatasi):
    pass


def kapali_mi() -> bool:
    return os.environ.get(KAPALI_ORTAM, "").strip().lower() in ("kapali", "kapalı", "0", "hayir", "off")


# ------------------------------------------------------------------ ağ politikası

@dataclass(frozen=True)
class AgPolitikasi:
    api_taban: str = "https://api.github.com"
    site_taban: str = "https://github.com"
    izinli: tuple[str, ...] = IZINLI_ANA_MAKINELER
    https_zorunlu: bool = True
    proxy_kullan: bool = True          # Windows'ta sistem vekil sunucusu ayarı gibi
    zaman_asimi: float = 15.0          # bağlanma + her okuma için üst sınır (sn)
    yeniden_deneme: int = 3            # ilerleme olmadan art arda bağlantı denemesi
    bekleme: float = 1.5               # denemeler arası (sn)


URETIM = AgPolitikasi()


def adres_denetle(url: str, pol: AgPolitikasi) -> None:
    """Adres politikaya uymuyorsa GuncellemeHatasi. Her istek ve her yönlendirme buradan geçer."""
    try:
        p = urllib.parse.urlsplit(url)
        port = p.port
    except ValueError:
        raise GuncellemeHatasi("Geçersiz adres.") from None
    http_ok = (not pol.https_zorunlu) and p.scheme == "http"
    if p.scheme != "https" and not http_ok:
        raise GuncellemeHatasi("Yalnız https adreslerine bağlanılır.")
    if p.username or p.password:
        raise GuncellemeHatasi("Adreste kullanıcı bilgisi olamaz.")
    if (p.hostname or "").lower() not in pol.izinli:
        raise GuncellemeHatasi("İzin verilmeyen bir ana makineye yönlendirildi; işlem durduruldu.")
    if pol.https_zorunlu and port not in (None, 443):
        raise GuncellemeHatasi("Beklenmeyen bağlantı noktası.")


class _YonlendirmeDenetci(urllib.request.HTTPRedirectHandler):
    def __init__(self, pol: AgPolitikasi):
        self._pol = pol

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        adres_denetle(urllib.parse.urljoin(req.full_url, newurl), self._pol)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener(pol: AgPolitikasi) -> urllib.request.OpenerDirector:
    """Yalnız gerekli işleyiciler: file:, ftp:, data: yok."""
    o = urllib.request.OpenerDirector()
    o.add_handler(urllib.request.ProxyHandler(None if pol.proxy_kullan else {}))
    o.add_handler(urllib.request.HTTPSHandler())
    if not pol.https_zorunlu:
        o.add_handler(urllib.request.HTTPHandler())
    o.add_handler(urllib.request.HTTPDefaultErrorHandler())
    o.add_handler(_YonlendirmeDenetci(pol))
    o.add_handler(urllib.request.HTTPErrorProcessor())
    o.add_handler(urllib.request.UnknownHandler())
    o.addheaders = [("User-agent", KULLANICI_AJANI)]
    return o


# ------------------------------------------------------------------ sürümler

@dataclass(frozen=True)
class Surum:
    metin: str
    sayi: tuple[int, int, int]
    onsurum: tuple[tuple[int, Any], ...] | None   # None: kararlı sürüm

    def anahtar(self):
        # semver: önsürüm, aynı numaralı kararlı sürümden KÜÇÜKTÜR; sayısal tanımlayıcı < harfli tanımlayıcı
        return (self.sayi, 1 if self.onsurum is None else 0, self.onsurum or ())

    def __lt__(self, o: "Surum") -> bool:
        return self.anahtar() < o.anahtar()

    def __gt__(self, o: "Surum") -> bool:
        return self.anahtar() > o.anahtar()

    def __le__(self, o: "Surum") -> bool:
        return self.anahtar() <= o.anahtar()

    def __ge__(self, o: "Surum") -> bool:
        return self.anahtar() >= o.anahtar()


_SURUM_RE = re.compile(r"^v?(\d{1,6})\.(\d{1,6})\.(\d{1,6})(?:-([0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*))?$")


def surum_coz(metin: str) -> Surum | None:
    """'v0.1.2', '0.2.0-rc.1' -> Surum; çözülemezse None."""
    if not isinstance(metin, str):
        return None
    m = _SURUM_RE.match(metin.strip())
    if not m:
        return None
    on = None
    if m.group(4):
        on = tuple((0, int(t)) if t.isdigit() else (1, t) for t in m.group(4).split("."))
    return Surum(metin.strip().lstrip("v"), (int(m.group(1)), int(m.group(2)), int(m.group(3))), on)


def en_yeni_aday(surumler: Any, mevcut: str, onsurum_dahil: bool, pol: AgPolitikasi = URETIM) -> dict | None:
    """GitHub 'releases' listesinden, mevcuttan DAHA YENİ en yüksek sürümün bilgisi (yoksa None).
    Yalnız beklenen iki dosyası (kurulum exe + SHA256SUMS.txt) bu deponun release yolundaysa sayılır."""
    bu = surum_coz(mevcut)
    if bu is None or not isinstance(surumler, list):
        return None
    en: tuple[Surum, dict] | None = None
    for r in surumler:
        if not isinstance(r, dict) or r.get("draft") is True:
            continue
        etiket = r.get("tag_name")
        sv = surum_coz(etiket) if isinstance(etiket, str) else None
        if sv is None:
            continue
        if not onsurum_dahil and (r.get("prerelease") is True or sv.onsurum is not None):
            continue
        aday = _aday_bilgisi(r, etiket, sv, pol)
        if aday is None:
            continue
        if sv > bu and (en is None or sv > en[0]):
            en = (sv, aday)
    return en[1] if en else None


def _aday_bilgisi(r: dict, etiket: str, sv: Surum, pol: AgPolitikasi) -> dict | None:
    onek = f"{pol.site_taban}/{DEPO}/releases/download/{etiket}/"
    beklenen_ad = f"KimlikMerkezi-Kurulum-v{sv.metin}.exe"
    exe = ozet = None
    for a in r.get("assets") or []:
        if not isinstance(a, dict) or a.get("state", "uploaded") != "uploaded":
            continue
        ad, url, boyut = a.get("name"), a.get("browser_download_url"), a.get("size")
        if ad == beklenen_ad and EXE_KALIBI.fullmatch(ad) and ".." not in ad:
            if isinstance(boyut, int) and not isinstance(boyut, bool) and 0 < boyut <= MAKS_EXE and url == onek + ad:
                exe = {"ad": ad, "boyut": boyut, "url": url}
        elif ad == OZET_ADI and url == onek + ad:
            ozet = {"ad": ad, "url": url}
    if not exe or not ozet:
        return None
    return {"surum": sv.metin, "etiket": etiket, "dosya_adi": exe["ad"], "boyut": exe["boyut"],
            "indirme_url": exe["url"], "ozet_url": ozet["url"],
            "onsurum": bool(r.get("prerelease")) or sv.onsurum is not None}


def ozet_coz(metin: str, dosya_adi: str) -> str | None:
    """sha256sum biçimi ('<64 hex>  ad' ya da '<64 hex> *ad'); dosya için 64 haneli özeti verir."""
    for satir in metin.splitlines():
        m = re.fullmatch(r"([0-9A-Fa-f]{64})[ \t]+\*?(.+?)\s*", satir)
        if m and m.group(2) == dosya_adi:
            return m.group(1).lower()
    return None


def dosya_ozeti(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _baslat_surec(argv: list[str]) -> None:
    """Kurulum programını ayrı bir süreç olarak başlatır (uygulama kapansa da sürer). Kabuk yok."""
    kw: dict[str, Any] = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              close_fds=True, shell=False)
    if sys.platform == "win32":
        kw["creationflags"] = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(argv, **kw)


ETKIN = ("denetleniyor", "indiriliyor", "dogrulaniyor", "kuruluyor")


class Guncelleme:
    """Tek bir denetim/indirme/kurulum durum makinesi (iş parçacığı güvenli).

    Durumlar: bosta, denetleniyor, guncel, yeni, indiriliyor, duraklatildi, dogrulaniyor, hazir, kuruluyor,
    iptal, hata, kapali."""

    def __init__(self, dizin: Path, mevcut_surum: str | None = None, politika: AgPolitikasi = URETIM,
                 baslatici: Callable[[list[str]], None] = _baslat_surec):
        self.dizin = Path(dizin)
        self.mevcut = mevcut_surum or __version__
        self.politika = politika
        self._baslatici = baslatici
        self._opener = _opener(politika)
        self._k = threading.Condition(threading.RLock())
        self._olay = threading.Event()          # duraklat/iptal istendiğinde uyandırır
        self._is: threading.Thread | None = None
        self._istek: str | None = None          # None | "duraklat" | "iptal"
        self._onaylandi = False                 # kullanıcı bu aday için indirmeyi onayladı mı
        self._ozet_beklenen: str | None = None
        self._ornekler: deque[tuple[float, int]] = deque()
        self._bekleyen: list[str] | None = None
        self.durum_adi = "bosta"
        self.mesaj = ""
        self.aday: dict | None = None
        self.indirilen = 0
        self.toplam = 0
        self.son_denetim: str | None = None
        self.devam_edilebilir = False
        self.hata_asama: str | None = None
        self.exe_yolu: Path | None = None

    # ------------------------------------------------------------------ tek ağ çıkışı
    def _ac(self, url: str, basliklar: dict[str, str] | None = None):
        """Uygulamanın TEK ağ çağrısı: kapatma anahtarı, https/ana makine denetimi, genel kullanıcı ajanı."""
        if kapali_mi():
            raise GuncellemeKapali(f"Güncelleme denetimi bu ortamda kapatılmış ({KAPALI_ORTAM}=kapali).")
        adres_denetle(url, self.politika)
        istek = urllib.request.Request(url, headers={"User-Agent": KULLANICI_AJANI, **(basliklar or {})})
        return self._opener.open(istek, timeout=self.politika.zaman_asimi)

    def _oku_sinirli(self, url: str, ust: int, basliklar: dict[str, str]) -> bytes:
        try:
            with self._ac(url, basliklar) as y:
                veri = y.read(ust + 1)
        except urllib.error.HTTPError as e:
            raise GuncellemeHatasi(_http_mesaji(e.code)) from None
        if len(veri) > ust:
            raise GuncellemeHatasi("Sunucu yanıtı beklenenden büyük; işlem durduruldu.")
        return veri

    # ------------------------------------------------------------------ durum
    def _ayarla(self, durum: str, mesaj: str = "", **kw: Any) -> None:
        with self._k:
            self.durum_adi, self.mesaj = durum, mesaj
            for ad, deger in kw.items():
                setattr(self, ad, deger)
            self._k.notify_all()

    def bekle_durum(self, *durumlar: str, zaman: float = 15.0) -> bool:
        """Durum istenenlerden biri olana dek bekler (testler ve düğümlenme için)."""
        bitis = time.monotonic() + zaman
        with self._k:
            while self.durum_adi not in durumlar:
                kalan = bitis - time.monotonic()
                if kalan <= 0:
                    return False
                self._k.wait(min(kalan, 0.2))
        return True

    def _hiz(self) -> float:
        with self._k:
            if len(self._ornekler) < 2:
                return 0.0
            (t0, b0), (t1, b1) = self._ornekler[0], self._ornekler[-1]
        return (b1 - b0) / (t1 - t0) if t1 - t0 >= 0.25 else 0.0

    def durum(self) -> dict:
        with self._k:
            toplam, ind = self.toplam, self.indirilen
            aktif = self.durum_adi == "indiriliyor"
            hiz = self._hiz() if aktif else 0.0
            d = {"durum": self.durum_adi, "mesaj": self.mesaj, "mevcut": self.mevcut, "kapali": kapali_mi(),
                 "son_denetim": self.son_denetim, "devam_edilebilir": self.devam_edilebilir,
                 "indirilen": ind, "toplam": toplam, "hata_asama": self.hata_asama,
                 "yuzde": round(100.0 * ind / toplam, 1) if toplam else 0.0,
                 "hiz": round(hiz), "kalan_sn": round((toplam - ind) / hiz) if hiz > 0 and toplam else None,
                 "surum": None, "etiket": None, "dosya_adi": None, "boyut": None, "onsurum": None}
            if self.aday:
                d.update({k: self.aday.get(k) for k in ("surum", "etiket", "dosya_adi", "boyut", "onsurum")})
            return d

    # ------------------------------------------------------------------ 1) denetim
    def denetle(self, onsurum: bool = True, arka_planda: bool = True) -> dict:
        """Yeni sürüm var mı diye yalnız sürüm listesini sorar. İndirme BAŞLATMAZ."""
        with self._k:
            if self.durum_adi in ("denetleniyor", "indiriliyor", "duraklatildi", "dogrulaniyor", "hazir", "kuruluyor"):
                return self.durum()
            if kapali_mi():
                self._ayarla("kapali", f"Güncelleme denetimi bu ortamda kapatılmış ({KAPALI_ORTAM}=kapali).")
                return self.durum()
            self._ayarla("denetleniyor", "Sürüm bilgisi alınıyor…", aday=None, devam_edilebilir=False)
        if arka_planda:
            threading.Thread(target=self._denetle_is, args=(onsurum,), daemon=True, name="guncelleme-denetim").start()
        else:
            self._denetle_is(onsurum)
        return self.durum()

    def _denetle_is(self, onsurum: bool) -> None:
        try:
            ham = self._oku_sinirli(f"{self.politika.api_taban}/repos/{DEPO}/releases?per_page=30", MAKS_API_GOVDE,
                                    {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
            try:
                liste = json.loads(ham.decode("utf-8"))
            except ValueError:
                raise GuncellemeHatasi("Sürüm bilgisi okunamadı (geçersiz yanıt).") from None
            aday = en_yeni_aday(liste, self.mevcut, onsurum, self.politika)
            simdi = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if aday:
                self._ayarla("yeni", "", aday=aday, son_denetim=simdi, toplam=aday["boyut"], indirilen=0,
                             _onaylandi=False, _ozet_beklenen=None)
                gunluk.log().info("güncelleme denetimi: yeni sürüm %s var", aday["surum"])
            else:
                self._ayarla("guncel", "Kimlik Merkezi güncel.", aday=None, son_denetim=simdi)
                gunluk.log().info("güncelleme denetimi: güncel")
        except GuncellemeKapali as e:
            self._ayarla("kapali", e.mesaj)
        except GuncellemeHatasi as e:
            self._ayarla("hata", e.mesaj, hata_asama="denetim")
        except Exception as e:  # ağ yok, DNS, TLS ...
            gunluk.log().info("güncelleme denetimi başarısız: %s", type(e).__name__)
            self._ayarla("hata", _ag_mesaji(e), hata_asama="denetim")

    # ------------------------------------------------------------------ 2) indirme (yalnız onayla)
    def indir(self, *, onay: bool, arka_planda: bool = True) -> dict:
        """Kullanıcı onayladıysa (onay=True) aday sürümün kurulum dosyasını indirir. Onaysız hiçbir şey indirilmez."""
        if onay is not True:
            raise OnayGerekli("İndirmek için onayınız gerekir.")
        with self._k:
            if self.aday is None or self.durum_adi not in ("yeni", "iptal", "hata", "duraklatildi"):
                raise GuncellemeHatasi("İndirilecek bir sürüm yok; önce güncellemeleri denetleyin.")
            if self.durum_adi == "hata" and self.hata_asama == "denetim":
                raise GuncellemeHatasi("İndirilecek bir sürüm yok; önce güncellemeleri denetleyin.")
            self._onaylandi = True
        return self._is_baslat(arka_planda)

    def surdur(self, arka_planda: bool = True) -> dict:
        """Duraklatılmış (ya da kesilmiş) indirmeyi kaldığı yerden (HTTP Range) sürdürür."""
        with self._k:
            if not self._onaylandi or self.aday is None or self.durum_adi not in ("duraklatildi", "hata"):
                raise GuncellemeHatasi("Sürdürülecek bir indirme yok.")
        return self._is_baslat(arka_planda)

    def _is_baslat(self, arka_planda: bool) -> dict:
        eski = self._is
        if eski is not None and eski.is_alive() and eski is not threading.current_thread():
            eski.join(self.politika.zaman_asimi + 5)
            if eski.is_alive():
                raise GuncellemeHatasi("Önceki işlem hâlâ kapanıyor; birazdan yeniden deneyin.")
        with self._k:
            self._istek = None
            self._olay.clear()
            self._ornekler.clear()
            self._ayarla("indiriliyor", "", devam_edilebilir=False, hata_asama=None)
        if arka_planda:
            self._is = threading.Thread(target=self._indir_is, daemon=True, name="guncelleme-indirme")
            self._is.start()
        else:
            self._indir_is()
        return self.durum()

    def duraklat(self) -> dict:
        with self._k:
            if self.durum_adi == "indiriliyor":
                self._istek = "duraklat"
                self._olay.set()
                self._ayarla("duraklatildi", "İndirme duraklatıldı.")
        return self.durum()

    def iptal(self) -> dict:
        """İndirmeyi iptal eder ve yarım dosyayı siler."""
        with self._k:
            if self.durum_adi == "indiriliyor":
                self._istek = "iptal"
                self._olay.set()            # iş parçacığı dosyayı siler ve durumu "iptal" yapar
            elif self.durum_adi in ("duraklatildi", "hata") and self.aday is not None:
                self._parca_sil()
                self._ayarla("iptal", "İndirme iptal edildi.", indirilen=0, _onaylandi=False,
                             devam_edilebilir=False, exe_yolu=None)
        return self.durum()

    def _yollar(self) -> tuple[Path, Path]:
        ad = (self.aday or {}).get("dosya_adi", "")
        if not EXE_KALIBI.fullmatch(ad) or ".." in ad:
            raise GuncellemeHatasi("Geçersiz dosya adı.")
        yol = (self.dizin / ad)
        if yol.resolve().parent != self.dizin.resolve():
            raise GuncellemeHatasi("Geçersiz dosya yolu.")
        return yol, yol.with_name(ad + ".part")

    def _parca_sil(self) -> None:
        try:
            for y in self._yollar():
                y.unlink(missing_ok=True)
        except (OSError, GuncellemeHatasi):
            pass

    def _indir_is(self) -> None:
        try:
            self._indir_calistir()
        except GuncellemeKapali as e:
            self._ayarla("hata", e.mesaj, hata_asama="indirme")
        except GuncellemeHatasi as e:
            self._ayarla("hata", e.mesaj, hata_asama="indirme", devam_edilebilir=e.devam_edilebilir)
        except Exception as e:
            self._ayarla("hata", _ag_mesaji(e), hata_asama="indirme", devam_edilebilir=True)

    def _indir_calistir(self) -> None:
        aday = self.aday
        assert aday is not None
        self.dizin.mkdir(parents=True, exist_ok=True)
        self._eskileri_temizle(except_ad=aday["dosya_adi"])
        yol, parca = self._yollar()
        toplam = int(aday["boyut"])
        with self._k:
            self.toplam = toplam
        # (1) Aynı sürümün özet dosyası: büyük indirmeden ÖNCE, eksikse erken hata
        if self._ozet_beklenen is None:
            metin = self._oku_sinirli(aday["ozet_url"], MAKS_OZET_GOVDE, {"Accept": "text/plain, application/octet-stream"})
            beklenen = ozet_coz(metin.decode("utf-8", "replace"), aday["dosya_adi"])
            if beklenen is None:
                raise GuncellemeHatasi(f"{OZET_ADI} içinde {aday['dosya_adi']} için özet bulunamadı; indirme yapılmadı.")
            self._ozet_beklenen = beklenen
        if self._istek:
            return self._indir_bitir_istek(parca)
        # (2) önceden indirilmiş ve doğrulanmış dosya
        if yol.exists():
            self._ayarla("dogrulaniyor", "Dosya doğrulanıyor…", indirilen=toplam)
            if hmac.compare_digest(dosya_ozeti(yol), self._ozet_beklenen):
                return self._hazir(yol)
            yol.unlink(missing_ok=True)
        # (3) yer
        var = parca.stat().st_size if parca.exists() else 0
        try:
            bos = shutil.disk_usage(self.dizin).free
        except OSError:
            bos = None
        if bos is not None and bos < max(0, toplam - var) + 50 * 1024 * 1024:
            raise GuncellemeHatasi("Diskte yeterli boş yer yok (kurulum dosyası için yaklaşık "
                                   f"{toplam // 1048576 + 50} MB gerekir).")
        # (4) akış (kesilirse Range ile yeniden bağlanır)
        yeniden = sifirlama = 0
        while not self._istek:
            onceki = self.indirilen
            try:
                if self._akis(aday["indirme_url"], parca, toplam) == "bitti":
                    break
            except _Sifirla:
                sifirlama += 1
                if sifirlama > 2:
                    raise GuncellemeHatasi("Sunucu kısmi indirmeyi kabul etmiyor; indirme durduruldu.") from None
                parca.unlink(missing_ok=True)
                with self._k:
                    self.indirilen = 0
                continue
            except (GuncellemeHatasi, _DiskHatasi):
                raise
            except Exception as e:
                if self._istek:
                    break
                if self.indirilen > onceki:
                    yeniden = 0
                yeniden += 1
                if yeniden > self.politika.yeniden_deneme:
                    raise GuncellemeHatasi(f"{_ag_mesaji(e)} İndirme kaldığı yerden sürdürülebilir.", True) from None
                self._olay.wait(self.politika.bekleme)
                continue
            if self._istek:
                break
        if self._istek:
            return self._indir_bitir_istek(parca)
        # (5) doğrulama: özet eşleşmeden dosya kurulabilir adla ASLA bırakılmaz
        self._ayarla("dogrulaniyor", "Dosya doğrulanıyor…", indirilen=toplam)
        gercek = dosya_ozeti(parca)
        if not hmac.compare_digest(gercek, self._ozet_beklenen):
            parca.unlink(missing_ok=True)
            yol.unlink(missing_ok=True)
            gunluk.log().error("güncelleme doğrulaması BAŞARISIZ (özet uyuşmuyor); dosya silindi")
            self._ayarla("hata", "Doğrulama başarısız: indirilen dosyanın SHA-256 özeti yayındaki "
                                 f"{OZET_ADI} ile uyuşmuyor. Dosya silindi, kurulum yapılmadı.",
                         hata_asama="dogrulama", indirilen=0, _onaylandi=False, devam_edilebilir=False,
                         _ozet_beklenen=None)
            return
        os.replace(parca, yol)
        self._hazir(yol)

    def _hazir(self, yol: Path) -> None:
        gunluk.log().info("güncelleme dosyası indirildi ve doğrulandı")
        self._ayarla("hazir", "İndirme tamamlandı; SHA-256 özeti doğrulandı.", exe_yolu=yol,
                     indirilen=self.toplam, devam_edilebilir=False)

    def _indir_bitir_istek(self, parca: Path) -> None:
        if self._istek == "iptal":
            self._parca_sil()
            self._ayarla("iptal", "İndirme iptal edildi.", indirilen=0, _onaylandi=False, devam_edilebilir=False,
                         exe_yolu=None)
        else:
            self._ayarla("duraklatildi", "İndirme duraklatıldı.")

    def _akis(self, url: str, parca: Path, toplam: int) -> str:
        """Tek bağlantı denemesi. 'bitti' ya da 'durdu' (duraklat/iptal); ağ hatasında istisna atar."""
        basla = parca.stat().st_size if parca.exists() else 0
        if basla > toplam:
            parca.unlink(missing_ok=True)
            basla = 0
        with self._k:
            self.indirilen = basla
        if basla == toplam:
            return "bitti"
        baslik = {"Accept": "application/octet-stream"}
        if basla:
            baslik["Range"] = f"bytes={basla}-"
        try:
            yanit = self._ac(url, baslik)
        except urllib.error.HTTPError as e:
            if e.code == 416:           # istenen aralık sunucuda yok: baştan al
                raise _Sifirla() from None
            raise GuncellemeHatasi(_http_mesaji(e.code), e.code >= 500) from None
        with yanit:
            kod = yanit.status
            if basla and kod == 206:
                m = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", (yanit.headers.get("Content-Range") or "").strip())
                if not m or int(m.group(1)) != basla or int(m.group(3)) != toplam:
                    raise _Sifirla()
                kip = "ab"
            elif kod == 200:            # sunucu Range'i yok saydı (ya da ilk indirme): baştan
                uz = yanit.headers.get("Content-Length")
                if uz is not None and uz.isdigit() and int(uz) != toplam:
                    raise GuncellemeHatasi("Sunucudaki dosya boyutu sürüm bilgisindekiyle uyuşmuyor; indirme durduruldu.")
                basla, kip = 0, "wb"
            else:
                raise GuncellemeHatasi(f"Beklenmeyen sunucu yanıtı (HTTP {kod}).")
            with self._k:
                self.indirilen = basla
                self._ornekler.clear()
                self._ornekler.append((time.monotonic(), basla))
            try:
                f = open(parca, kip)
            except OSError:
                raise _DiskHatasi("İndirme klasörüne yazılamadı.") from None
            with f:
                while not self._istek:
                    blok = yanit.read(PARCA)
                    if not blok:
                        break
                    try:
                        f.write(blok)
                    except OSError:
                        raise _DiskHatasi("Diske yazılamadı (yer kalmamış olabilir).") from None
                    with self._k:
                        self.indirilen += len(blok)
                        simdi = time.monotonic()
                        self._ornekler.append((simdi, self.indirilen))
                        while len(self._ornekler) > 2 and simdi - self._ornekler[0][0] > 5.0:
                            self._ornekler.popleft()
                    if self.indirilen > toplam:
                        raise GuncellemeHatasi("Sunucu beklenenden fazla veri gönderdi; indirme durduruldu.")
        if self._istek:
            return "durdu"
        if self.indirilen != toplam:
            raise OSError("bağlantı erken kapandı")
        return "bitti"

    def _eskileri_temizle(self, except_ad: str | None = None) -> None:
        try:
            for p in self.dizin.iterdir():
                ad = p.name[:-5] if p.name.endswith(".part") else p.name
                if EXE_KALIBI.fullmatch(ad) and ad != except_ad:
                    p.unlink(missing_ok=True)
        except OSError:
            pass

    def temizle(self) -> None:
        """Açılışta: kurulu (ya da daha eski) sürümün artık dosyalarını ve 14 günden eski yarım indirmeleri siler."""
        bu = surum_coz(self.mevcut)
        try:
            dosyalar = list(self.dizin.iterdir()) if self.dizin.is_dir() else []
        except OSError:
            return
        for p in dosyalar:
            ad = p.name[:-5] if p.name.endswith(".part") else p.name
            if not EXE_KALIBI.fullmatch(ad):
                continue
            sv = surum_coz(ad[len("KimlikMerkezi-Kurulum-"):-4])
            try:
                if (sv is not None and bu is not None and sv <= bu) or \
                        (p.name.endswith(".part") and time.time() - p.stat().st_mtime > 14 * 86400):
                    p.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------------ 3) kurulum (ikinci onay)
    def kur(self, *, onay: bool, otomatik_baslat: bool) -> dict:
        """Kurulumu HAZIRLAR (ikinci onay). Kurulum programını uygulama tamamen kapandıktan sonra
        `kurulumu_baslat()` başlatır. Dosya hâlâ doğru özetteyse ilerler."""
        if onay is not True:
            raise OnayGerekli("Kurmak için onayınız gerekir.")
        with self._k:
            if self.durum_adi != "hazir" or self.exe_yolu is None or self._ozet_beklenen is None:
                raise GuncellemeHatasi("Kurulacak doğrulanmış bir dosya yok.")
            yol = self.exe_yolu
        gecerli, _ = self._yollar()
        if yol != gecerli or not yol.is_file() or not hmac.compare_digest(dosya_ozeti(yol), self._ozet_beklenen):
            yol.unlink(missing_ok=True)
            self._ayarla("hata", "Dosya doğrulanamadı (değişmiş olabilir); silindi. Kurulum yapılmadı.",
                         hata_asama="dogrulama", exe_yolu=None, _onaylandi=False)
            raise GuncellemeHatasi("Dosya doğrulanamadı; silindi.")
        self._bekleyen = kurulum_komutu(yol, otomatik_baslat, self.dizin / "kur.log")
        self._ayarla("kuruluyor", "Kurulum başlatılıyor; uygulama kapanacak ve kurulumdan sonra yeniden açılacak.")
        return self.durum()

    def kurulumu_baslat(self) -> bool:
        """Hazırlanmış kurulumu başlatır. Uygulama veri klasörünü kapattıktan SONRA çağrılır. Hata olursa False."""
        with self._k:
            argv, self._bekleyen = self._bekleyen, None
        if not argv:
            return False
        try:
            self._baslatici(argv)
        except Exception as e:
            gunluk.log().error("kurulum programı başlatılamadı: %s", type(e).__name__)
            return False
        gunluk.log().info("kurulum programı başlatıldı")
        return True

    @property
    def bekleyen_kurulum(self) -> list[str] | None:
        return list(self._bekleyen) if self._bekleyen else None


class _Sifirla(Exception):
    """Kısmi dosya sunucuyla uyuşmuyor: baştan indir."""


class _DiskHatasi(GuncellemeHatasi):
    pass


def kurulum_komutu(exe: Path, otomatik_baslat: bool, kayit: Path) -> list[str]:
    """Inno Setup sessiz kurulum bayrakları. Veri klasörüne dokunmaz (kurulum yalnız {app} klasörüne yazar).
    /GUNCELLEME=1: KimlikMerkezi.iss, kurulum bitince uygulamayı yeniden açar (sessiz kurulumda 'postinstall' çalışmaz).
    /TASKS: kullanıcının girişte başlatma tercihi korunur (kapalıysa kurulum geri açmasın)."""
    return [str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
            "/TASKS=" + ("otobaslat" if otomatik_baslat else "!otobaslat"), "/GUNCELLEME=1", f"/LOG={kayit}"]


def _http_mesaji(kod: int) -> str:
    if kod in (403, 429):
        return "GitHub istek sınırına takıldı; biraz sonra yeniden deneyin."
    if kod == 404:
        return "Sürüm bilgisi bulunamadı (404)."
    if 300 <= kod < 400:
        return "İzin verilmeyen ya da geçersiz bir yönlendirme; işlem durduruldu."
    return f"GitHub yanıtı beklenmedik (HTTP {kod})."


def _ag_mesaji(e: BaseException) -> str:
    if isinstance(e, urllib.error.HTTPError):
        return _http_mesaji(e.code)
    if isinstance(e, TimeoutError):
        return "Bağlantı zaman aşımına uğradı."
    if isinstance(e, urllib.error.URLError):
        return "Ağa bağlanılamadı (internet yok ya da GitHub'a erişilemiyor)."
    return f"Bağlantı hatası ({type(e).__name__})."
