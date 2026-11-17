"""Yerel sesli arama motoru (v0.3.0): Whisper, bu bilgisayarda, ayrı bir Python sürecinde. Ses internete GİTMEZ.

Neden ayrı süreç: Whisper (faster-whisper + CUDA kütüphaneleri) yüzlerce MB tutar; uygulamanın içine gömülmez.
İlk kullanımda kullanıcının bilgisayarındaki gerçek bir Python'a kurulur ("Ses motorunu kur"), model ilk
tanımada indirilir ve sonra yerelden çalışır. Ölçüm (GTX 1050 Ti): medium modeli ≈1,2 sn/cümle.
Çalışan Python'u bulurken Microsoft Store'un sahte `python`unu atlamak için her aday GERÇEKTEN çalıştırılır."""
from __future__ import annotations

import base64
import glob
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from .yollar import ayar_dizini

MODEL = "medium"
_CREATIONFLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)

CALISAN_KAYNAK = r'''
import base64, glob, json, os, sys
for sp in list(sys.path):
    for d in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
        if os.path.isdir(d):
            try: os.add_dll_directory(d)
            except (OSError, AttributeError): pass
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
import numpy as np
from faster_whisper import WhisperModel
def yanit(o): sys.stdout.write(json.dumps(o, ensure_ascii=False) + "\n"); sys.stdout.flush()
model = None
for satir in sys.stdin:
    try:
        i = json.loads(satir)
        if i["op"] == "hazir":
            hata = None
            for cihaz, tur in (("cuda", "int8_float16"), ("cpu", "int8")):
                try:
                    model = WhisperModel(i.get("model", "medium"), device=cihaz, compute_type=tur); break
                except Exception as e:
                    hata = str(e); model = None
            yanit({"ok": model is not None, "cihaz": cihaz if model else None, "hata": None if model else hata})
        elif i["op"] == "tani":
            pcm = np.frombuffer(base64.b64decode(i["pcm"]), dtype=np.int16).astype(np.float32) / 32768.0
            segs, _ = model.transcribe(pcm, language="tr", beam_size=1, condition_on_previous_text=False)
            yanit({"ok": True, "metin": " ".join(s.text.strip() for s in segs).strip()})
        elif i["op"] == "bitir":
            break
    except Exception as e:
        yanit({"ok": False, "hata": f"{type(e).__name__}: {e}"})
'''


def _calisir_mi(komut: list[str], kod: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run([*komut, "-c", kod], capture_output=True, text=True, timeout=25, creationflags=_CREATIONFLAGS)
    except (OSError, subprocess.SubprocessError):
        return None


def python_adaylari() -> list[list[str]]:
    adaylar: list[list[str]] = []
    if not getattr(sys, "frozen", False):
        adaylar.append([sys.executable])
    adaylar += [["py", "-3"], ["python"], ["python3"]]
    yerel = os.environ.get("LOCALAPPDATA")
    if yerel:
        for yol in sorted(glob.glob(os.path.join(yerel, "Programs", "Python", "Python3*", "python.exe")), reverse=True):
            adaylar.append([yol])
    return adaylar


def bul_python() -> list[str] | None:
    """Gerçekten çalışan, 3.9+ bir Python; yoksa None."""
    for k in python_adaylari():
        r = _calisir_mi(k, "import sys;print(sys.version_info[0]*100+sys.version_info[1])")
        if r and r.returncode == 0 and r.stdout.strip().isdigit() and int(r.stdout.strip()) >= 309:
            return k
    return None


def motor_kurulu(python: list[str]) -> bool:
    r = _calisir_mi(python, "import faster_whisper, numpy")
    return bool(r and r.returncode == 0)


class SesMotoru:
    def __init__(self, dizin: Path | None = None):
        self.dizin = Path(dizin) if dizin else ayar_dizini() / "ses"
        self.kilit = threading.RLock()
        self.surec: subprocess.Popen | None = None
        self.python: list[str] | None = None
        self.hazir = False
        self.cihaz: str | None = None
        self.kurulum: dict[str, Any] = {"durum": "yok", "mesaj": ""}      # yok | calisiyor | bitti | hata
        self.son_hata: str | None = None

    # ------------------------------------------------------------------ durum
    def durum(self) -> dict[str, Any]:
        with self.kilit:
            if self.python is None:
                self.python = bul_python()
            kurulu = bool(self.python and motor_kurulu(self.python))
            return {"python_var": self.python is not None, "motor_kurulu": kurulu, "hazir": self.hazir, "cihaz": self.cihaz,
                    "model": MODEL, "kurulum": dict(self.kurulum), "hata": self.son_hata,
                    "aciklama": ("Ses motoru hazır." if kurulu else
                                 "Sesli arama için bu bilgisayara bir kerelik 'Ses motoru' kurulur (yaklaşık 1-2 GB indirme). Ses internete gönderilmez." if self.python
                                 else "Sesli arama için bilgisayarda Python 3 gerekli (python.org). Yazarak arama şimdi de çalışır.")}

    # ------------------------------------------------------------------ kurulum (arka planda)
    def kur_baslat(self) -> dict[str, Any]:
        with self.kilit:
            if self.kurulum["durum"] == "calisiyor":
                return dict(self.kurulum)
            if self.python is None:
                self.python = bul_python()
            if self.python is None:
                self.kurulum = {"durum": "hata", "mesaj": "Çalışan bir Python 3 bulunamadı. python.org'dan kurup tekrar deneyin."}
                return dict(self.kurulum)
            self.kurulum = {"durum": "calisiyor", "mesaj": "İndiriliyor ve kuruluyor… (birkaç dakika sürebilir)"}
        threading.Thread(target=self._kur, daemon=True).start()
        return dict(self.kurulum)

    def _kur(self) -> None:
        paketler = ["faster-whisper", "numpy"]
        if sys.platform == "win32":
            paketler += ["nvidia-cublas-cu12", "nvidia-cudnn-cu12"]      # GPU için; yoksa CPU'da da çalışır
        try:
            r = subprocess.run([*self.python, "-m", "pip", "install", "--disable-pip-version-check", *paketler], capture_output=True,
                               text=True, timeout=3600, creationflags=_CREATIONFLAGS)
            if r.returncode != 0:
                self.kurulum = {"durum": "hata", "mesaj": "Kurulum başarısız: " + (r.stderr or r.stdout)[-600:]}
            else:
                self.kurulum = {"durum": "bitti", "mesaj": "Ses motoru kuruldu."}
        except (OSError, subprocess.SubprocessError) as e:
            self.kurulum = {"durum": "hata", "mesaj": f"Kurulum çalıştırılamadı: {type(e).__name__}: {e}"}

    # ------------------------------------------------------------------ tanıma
    def _baslat(self) -> None:
        if self.surec and self.surec.poll() is None and self.hazir:
            return
        self.kapat()
        if self.python is None:
            self.python = bul_python()
        if self.python is None or not motor_kurulu(self.python):
            raise SesHatasi("Ses motoru kurulu değil.", "motor_yok")
        self.dizin.mkdir(parents=True, exist_ok=True)
        betik = self.dizin / "ses_calisan.py"
        betik.write_text(CALISAN_KAYNAK, encoding="utf-8")
        self.surec = subprocess.Popen([*self.python, str(betik)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                      text=True, encoding="utf-8", creationflags=_CREATIONFLAGS)
        y = self._sor({"op": "hazir", "model": MODEL})
        if not y.get("ok"):
            self.kapat()
            raise SesHatasi("Ses modeli yüklenemedi: " + str(y.get("hata"))[:300], "model_yok")
        self.hazir, self.cihaz = True, y.get("cihaz")

    def _sor(self, istek: dict[str, Any]) -> dict[str, Any]:
        assert self.surec and self.surec.stdin and self.surec.stdout
        try:
            self.surec.stdin.write(json.dumps(istek) + "\n")
            self.surec.stdin.flush()
            satir = self.surec.stdout.readline()
        except (OSError, ValueError) as e:
            raise SesHatasi(f"Ses süreci yanıt vermedi: {e}", "surec") from None
        if not satir:
            raise SesHatasi("Ses süreci beklenmedik biçimde kapandı.", "surec")
        return json.loads(satir)

    def tani(self, pcm_b64: str) -> str:
        """16 kHz, tek kanal, 16 bit PCM (base64) -> Türkçe metin."""
        try:
            ham = base64.b64decode(pcm_b64, validate=True)
        except ValueError:
            raise SesHatasi("Ses verisi bozuk.", "veri") from None
        if len(ham) < 16000 * 2 * 0.3:
            raise SesHatasi("Ses çok kısa; mikrofona basılı tutup konuşun.", "kisa")
        if len(ham) > 16000 * 2 * 20:
            raise SesHatasi("Ses en fazla 20 saniye olabilir.", "uzun")
        with self.kilit:
            try:
                self._baslat()
                y = self._sor({"op": "tani", "pcm": pcm_b64})
            except SesHatasi as e:
                self.son_hata = str(e)
                raise
        if not y.get("ok"):
            self.son_hata = str(y.get("hata"))
            raise SesHatasi("Tanıma hatası: " + self.son_hata[:300], "tani")
        self.son_hata = None
        return str(y.get("metin", ""))

    def kapat(self) -> None:
        with self.kilit:
            s, self.surec, self.hazir = self.surec, None, False
            if s and s.poll() is None:
                try:
                    s.stdin.write(json.dumps({"op": "bitir"}) + "\n")
                    s.stdin.flush()
                    s.wait(timeout=5)
                except (OSError, ValueError, subprocess.SubprocessError):
                    s.kill()


class SesHatasi(Exception):
    def __init__(self, mesaj: str, kod: str = "ses"):
        super().__init__(mesaj)
        self.kod = kod
