"""Telefonu taklit eden örnek istemci (test yardımcısı; yalnız standart kütüphane).

Android uygulamasının yapacağını yapar: parmak izi SABİTLEME (başka sertifikaya bağlanmaz, hiçbir istek
gitmez), kodla eşleştirme, HEAD ile alıcıdaki bayta bakma, ofsetli PUT, `var` yanıtından sonra dosyayı silme
(opsiyonel), kopmada yeniden deneme.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import socket
import ssl
import time
import uuid
from pathlib import Path

from kimlikserver.aktarim.eslestirme import eslestirme_coz


class Yetkisiz(Exception):
    pass


class Yasak(Exception):
    pass


class ParmakIziUyusmadi(Exception):
    """Sertifika parmak izi tutmadı; hiçbir istek gönderilmedi."""


class _SabitBaglanti(http.client.HTTPSConnection):
    def __init__(self, host, port, pin, timeout):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE      # güven kökü yok; yerine parmak izi sabitleme
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        super().__init__(host, port, timeout=timeout, context=ctx)
        self._pin = pin.lower().replace(":", "")

    def connect(self):
        super().connect()
        if hashlib.sha256(self.sock.getpeercert(binary_form=True)).hexdigest() != self._pin:
            self.sock.close()
            self.sock = None
            raise ParmakIziUyusmadi("sertifika parmak izi uyuşmuyor")


def kutu_dosyasi(cihaz_id: str, dosya_id: str, kayit_sayisi: int = 5, *, metin: str = "sentetik not",
                 kapanis: str = "dogru", on_ek: str = "k") -> bytes:
    """AKTARIM §1 biçiminde giden kutusu dosyası. kapanis: dogru | yok | yanlis."""
    satirlar = [{"baslik": True, "bicim": 1, "cihaz_id": cihaz_id, "dosya_id": dosya_id,
                 "acilis": "2026-03-01T08:00:00Z", "uygulama": "0.2.0", "android_api": 31, "model": "TEST"}]
    kimlikler = []
    for i in range(kayit_sayisi):
        kid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{on_ek}/{dosya_id}/{i}"))
        kimlikler.append(kid)
        satirlar.append({"id": kid, "ts": f"2026-03-01T09:{i % 60:02d}:{i // 60 % 60:02d}Z", "tur": "not.hizli",
                         "kategori": "notlar", "metin": f"{metin} {i}", "yuk": {}, "onceki": None})
    if kapanis == "dogru":
        satirlar.append({"kapanis": True, "kayit_sayisi": kayit_sayisi})
    elif kapanis == "yanlis":
        satirlar.append({"kapanis": True, "kayit_sayisi": kayit_sayisi + 1})
    return ("\n".join(json.dumps(s, ensure_ascii=False) for s in satirlar) + "\n").encode("utf-8")


def olay_kimlikleri(cihaz_id: str, dosya_id: str, kayit_sayisi: int, on_ek: str = "k") -> set[str]:
    return {str(uuid.uuid5(uuid.NAMESPACE_URL, f"{on_ek}/{dosya_id}/{i}")) for i in range(kayit_sayisi)}


class Istemci:
    def __init__(self, host: str, port: int, parmak_izi: str, cihaz_id: str, anahtar: str | None = None, *,
                 parca_bayt: int = 256 * 1024, parca_arasi_s: float = 0.0, zaman_asimi: float = 15.0):
        self.host, self.port, self.pin, self.cihaz_id, self.anahtar = host, port, parmak_izi, cihaz_id, anahtar
        self.parca_bayt, self.parca_arasi_s, self.zaman_asimi = parca_bayt, parca_arasi_s, zaman_asimi
        self._bag: _SabitBaglanti | None = None
        self.istek_sayisi = 0
        self.silinenler: list[str] = []

    @classmethod
    def kodla(cls, km1: str, cihaz_id: str, *, host: str = "127.0.0.1", port: int | None = None, **kw) -> "Istemci":
        """`km1:` metninden kurar (adres/port geçersiz kılınabilir: testler 127.0.0.1 kullanır)."""
        k = eslestirme_coz(km1)
        return cls(host, port or k["p"], k["f"], cihaz_id, **kw)

    # --- düşük düzey
    def _istek(self, yontem, yol, basliklar=None, govde=None, *, kimlik=True):
        basliklar = dict(basliklar or {})
        if kimlik and self.anahtar is not None:
            basliklar["Authorization"] = f"Bearer {self.anahtar}"
            basliklar["X-Cihaz"] = self.cihaz_id
        for deneme in (0, 1):    # keep-alive kopmuşsa bir kez yeniden bağlan
            if self._bag is None:
                self._bag = _SabitBaglanti(self.host, self.port, self.pin, self.zaman_asimi)
            try:
                self.istek_sayisi += 1
                self._bag.request(yontem, yol, body=govde, headers=basliklar)
                y = self._bag.getresponse()
                veri = y.read()
                y.govde = veri
                if y.status == 401:
                    self.kapat()
                    raise Yetkisiz("401")
                if y.status == 403:
                    self.kapat()
                    raise Yasak("403")
                return y
            except (Yetkisiz, Yasak, ParmakIziUyusmadi):
                self.kapat()
                raise
            except (http.client.HTTPException, OSError, ssl.SSLError):
                self.kapat()
                if deneme == 1:
                    raise
        raise AssertionError("ulaşılmaz")

    def kapat(self):
        if self._bag is not None:
            try:
                self._bag.close()
            finally:
                self._bag = None

    # --- uçlar
    def eslestir(self, kod: str, ad: str = "Test telefonu", model: str = "TEST") -> str:
        y = self._istek("POST", "/eslestir", {"Content-Type": "application/json"}, json.dumps(
            {"cihaz_id": self.cihaz_id, "ad": ad, "platform": "android", "model": model, "kod": kod}), kimlik=False)
        if y.status != 200:
            raise Yetkisiz(f"eşleştirme reddedildi: {y.status}")
        self.anahtar = json.loads(y.govde)["cihaz_anahtari"]
        return self.anahtar

    def pc_durumu(self) -> dict:
        return json.loads(self._istek("GET", "/durum", kimlik=False).govde)

    def durum(self, dosya_id: str) -> tuple[str, int]:
        y = self._istek("HEAD", f"/giden/{self.cihaz_id}/{dosya_id}.jsonl")
        return y.getheader("X-Durum"), int(y.getheader("X-Alinan") or 0)

    def dosya_gonder(self, yol: Path, *, en_fazla_parca: int | None = None) -> dict:
        """Tek dosyayı gönderir/sürdürür. en_fazla_parca: bu kadar parçadan sonra keser (kopma taklidi)."""
        yol = Path(yol)
        dosya_id = yol.stem
        toplam = yol.stat().st_size
        sha = hashlib.sha256(yol.read_bytes()).hexdigest()
        ilk, ofset = self.durum(dosya_id)
        if ilk == "var":
            return {"sonuc": "var", "ilk_durum": ilk, "baslangic_ofset": ofset, "gonderilen_bayt": 0}
        bas0, gonderilen, parca_n = ofset, 0, 0
        with open(yol, "rb") as f:
            while True:
                if en_fazla_parca is not None and parca_n >= en_fazla_parca:
                    return {"sonuc": "kesildi", "ilk_durum": ilk, "baslangic_ofset": bas0, "gonderilen_bayt": gonderilen}
                f.seek(ofset)
                parca = f.read(self.parca_bayt)
                y = self._istek("PUT", f"/giden/{self.cihaz_id}/{dosya_id}.jsonl", {
                    "Content-Range": f"bytes {ofset}-{ofset + len(parca) - 1}/{toplam}", "X-Sha256": sha,
                    "Content-Type": "application/octet-stream"}, parca)
                parca_n += 1
                if y.status in (200, 201):
                    gonderilen += len(parca)
                    if y.getheader("X-Durum") == "var":
                        return {"sonuc": "var", "ilk_durum": ilk, "baslangic_ofset": bas0, "gonderilen_bayt": gonderilen}
                    ofset += len(parca)
                    if self.parca_arasi_s:
                        time.sleep(self.parca_arasi_s)
                elif y.status == 409:
                    ofset = int(y.getheader("X-Alinan") or 0)
                    time.sleep(0.02)
                    if ofset >= toplam:   # eşzamanlı başka gönderen dosyayı tamamladı: boş PUT (Content-Length: 0 -> 411) atma
                        durum, _ = self.durum(dosya_id)
                        if durum == "var":
                            return {"sonuc": "var", "ilk_durum": ilk, "baslangic_ofset": bas0, "gonderilen_bayt": gonderilen}
                elif y.status == 422:
                    return {"sonuc": "reddedildi", "ilk_durum": ilk, "baslangic_ofset": bas0,
                            "gonderilen_bayt": gonderilen, "neden": json.loads(y.govde).get("hata")}
                else:
                    raise RuntimeError(f"beklenmeyen durum {y.status}")

    def klasor_gonder(self, klasor: Path, *, var_olunca_sil: bool = True) -> dict:
        """Kapatılmış dosyaları gönderir; `var` alınan dosya silinir (telefon davranışı). Bağlantı yoksa bekler."""
        sonuc = {"tamam": 0, "var": 0, "bekleyen": 0, "hata": None, "reddedilen": 0, "gonderilen_bayt": 0}
        dosyalar = sorted(Path(klasor).glob("*.jsonl"))
        for i, p in enumerate(dosyalar):
            try:
                r = self.dosya_gonder(p)
            except (OSError, http.client.HTTPException, ssl.SSLError) as e:
                sonuc["bekleyen"] = len(dosyalar) - i
                sonuc["hata"] = type(e).__name__
                self.kapat()
                return sonuc
            sonuc["gonderilen_bayt"] += r["gonderilen_bayt"]
            if r["sonuc"] in ("var", "tamam"):
                sonuc["var"] += 1
                if var_olunca_sil:
                    self.silinenler.append(p.name)
                    p.unlink()
            else:
                sonuc["reddedilen"] += 1
        self.kapat()
        return sonuc

    def tekrarla(self, klasor: Path, sure_s: float, bekleme_s: float = 0.1) -> dict:
        bitis = time.time() + sure_s
        toplam = {"var": 0, "tur": 0, "bitti": False}
        while time.time() < bitis:
            r = self.klasor_gonder(klasor)
            toplam["tur"] += 1
            toplam["var"] += r["var"]
            if r["bekleyen"] == 0 and r["hata"] is None:
                toplam["bitti"] = True
                return toplam
            time.sleep(bekleme_s)
        return toplam


def ham_istek(port: int, yontem: str, yol: str, basliklar: dict | None = None, govde: bytes | None = None):
    """Doğrulamasız ham HTTPS isteği (olumsuz testler için): (durum, başlıklar, gövde)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    c = http.client.HTTPSConnection("127.0.0.1", port, timeout=10, context=ctx)
    try:
        c.request(yontem, yol, body=govde, headers=basliklar or {})
        y = c.getresponse()
        return y.status, dict(y.getheaders()), y.read()
    finally:
        c.close()
