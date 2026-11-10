"""Giriş noktası.

  KimlikMerkezi.exe               tepsi + yerel web arayüzü, tarayıcıyı açar
  KimlikMerkezi.exe --arka-plan   aynısı, tarayıcıyı açmadan (girişte başlama)
  KimlikMerkezi.exe saglik        sağlık denetimi (ekransız; çıkış kodu 0/1)
  KimlikMerkezi.exe tanila <yol> [--adlari-goster] [--ayrinti]
                                  dışa aktarma dosyasının İÇERİKSİZ yapı raporu (konsolda: kimlikmerkezi-mcp.exe tanila ...)
  KimlikMerkezi.exe mcp           MCP (stdio); pencere/tepsi açmaz
  KimlikMerkezi.exe --sec dosya|klasor   (iç kullanım) seçme penceresi
Kurulu pakette MCP için ayrıca konsol exe'si `kimlikmerkezi-mcp.exe` vardır (Claude buna bağlanır).
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from kimlikcore import HubLockedError

from . import __version__, gunluk
from .ayarlar import Ayarlar
from .web import Sunucu
from .yonetici import Yonetici
from .yollar import ayar_dizini


def _calisan_dosyasi() -> Path:
    return ayar_dizini() / "calisan.json"


def calisan_adres() -> str | None:
    """Başka bir kopya çalışıyorsa adresini döner (sağlık ucu yanıt veriyorsa)."""
    try:
        port = int(json.loads(_calisan_dosyasi().read_text(encoding="utf-8"))["port"])
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/saglik", timeout=2) as r:
            if json.loads(r.read()).get("uygulama") == "kimlik-merkezi":
                return f"http://127.0.0.1:{port}/"
    except (OSError, ValueError, KeyError):
        pass
    return None


def sec(tur: str, cikti: str | None) -> int:
    import tkinter
    from tkinter import filedialog
    kok = tkinter.Tk()
    kok.withdraw()
    kok.attributes("-topmost", True)
    yol = filedialog.askdirectory(title="Klasör seçin") if tur == "klasor" else \
        filedialog.askopenfilename(title="Dosya seçin", filetypes=[("Arşiv ve veri", "*.zip *.json *.csv *.jsonl"), ("Tümü", "*.*")])
    if cikti:
        Path(cikti).write_text(yol or "", encoding="utf-8")
    return 0


def saglik_komutu(veri: str | None) -> int:
    from . import saglik
    klasor = veri or Ayarlar()["veri_klasoru"]
    if not klasor:
        print("Veri klasörü yapılandırılmamış.", file=sys.stderr)
        return 2
    s = saglik.denetle(klasor)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    print(saglik.metin(s))
    return 0 if s["ok"] else 1


def tanila_komutu(yol: str | None, adlari_goster: bool, ayrinti: bool) -> int:
    """`tanila <yol>`: çekirdek komut satırındaki mevcut `tanila` komutunu çağırır (veritabanı açmaz, ağa bağlanmaz)."""
    if not yol:
        print("Kullanım: kimlikmerkezi-mcp.exe tanila <dosya-veya-klasör> [--adlari-goster] [--ayrinti]", file=sys.stderr)
        return 2
    from kimlikcore.cli import main as cli_main
    argv = ["tanila", yol] + (["--adlari-goster"] if adlari_goster else []) + (["--ayrinti"] if ayrinti else [])
    return cli_main(argv)


def calistir(arka_plan: bool) -> int:
    gunluk.kur()
    gunluk.log().info("başlıyor, sürüm %s", __version__)
    mevcut = calisan_adres()
    if mevcut:
        if not arka_plan:
            webbrowser.open(mevcut)
        return 0
    yonetici = Yonetici()
    try:
        yonetici.baslat()
    except HubLockedError as e:
        gunluk.log().error("kilit: %s", type(e).__name__)
        print(f"Veri klasörü başka bir süreç tarafından yazılıyor: {e}", file=sys.stderr)
        return 3
    except Exception as e:  # bozuk/uyumsuz veritabanı: arayüz yine açılır, hata orada gösterilir
        gunluk.log().error("başlangıç hatası: %s", type(e).__name__)
        yonetici.baslangic_hatasi = f"{type(e).__name__}: {e}"
    sunucu = Sunucu(yonetici, int(yonetici.ayarlar["port"]))
    sunucu.baslat()
    ayar_dizini().mkdir(parents=True, exist_ok=True)
    _calisan_dosyasi().write_text(json.dumps({"port": sunucu.port}), encoding="utf-8")
    gunluk.log().info("web arayüzü %s", sunucu.url)
    if not arka_plan:
        webbrowser.open(sunucu.url)

    cikis = threading.Event()
    tepsi = None
    try:
        from .tepsi import Tepsi
        tepsi = Tepsi(lambda: webbrowser.open(sunucu.url), cikis.set,
                      yonetici.otomatik.etkin_mi, lambda a: yonetici.api("ayar_yaz", {"otomatik_baslat": a}))
    except Exception as e:  # pystray/Pillow yok ya da tepsi desteklenmiyor: tepsisiz sürer
        gunluk.log().warning("tepsi yok: %s", type(e).__name__)

    def bekle() -> None:
        while not cikis.is_set() and not yonetici.cikis_istegi:
            time.sleep(0.5)
        if tepsi:
            tepsi.durdur()
        cikis.set()

    threading.Thread(target=bekle, daemon=True).start()
    try:
        if tepsi:
            tepsi.calistir()
        else:
            while not cikis.is_set() and not yonetici.cikis_istegi:
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        sunucu.durdur()
        yonetici.kapat()
        try:
            _calisan_dosyasi().unlink()
        except OSError:
            pass
        gunluk.log().info("kapandı")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    import os
    for ad in ("stdout", "stderr"):          # pencereli exe'de akışlar None olabilir
        if getattr(sys, ad) is None:
            setattr(sys, ad, open(os.devnull, "w", encoding="utf-8"))
    if argv[:1] == ["mcp"]:
        from kimlikserver.mcp.__main__ import main as mcp_main
        return mcp_main()
    p = argparse.ArgumentParser(prog="KimlikMerkezi", description="Kimlik Merkezi (Windows)")
    p.add_argument("komut", nargs="?", choices=["saglik", "surum", "tanila"])
    p.add_argument("yol", nargs="?", help="tanila komutu için dışa aktarma dosyası/klasörü")
    p.add_argument("--adlari-goster", action="store_true", help="tanila: dosya/klasör adlarını maskesiz yaz (kişi adı içerebilir)")
    p.add_argument("--ayrinti", action="store_true", help="tanila: uzun, ayrıntılı rapor")
    p.add_argument("--arka-plan", action="store_true", help="tarayıcıyı açma, tepside başla")
    p.add_argument("--sec", choices=["dosya", "klasor"], help=argparse.SUPPRESS)
    p.add_argument("--cikti", help=argparse.SUPPRESS)
    p.add_argument("--veri", help="saglik komutu için veri klasörü")
    a = p.parse_args(argv)
    if a.sec:
        return sec(a.sec, a.cikti)
    if a.komut == "surum":
        import ijson
        print(f"Kimlik Merkezi {__version__}")
        print(f"ijson arka ucu: {ijson.backend}")   # C uzantısı pakette ise 'yajl2_c'
        for modul in ("pypdf", "docx"):              # belge okuyucular (dosya denetimi/içe aktarma); pakette olmalı
            try:
                __import__(modul)
                print(f"{modul}: var")
            except ImportError:
                print(f"{modul}: YOK")
        return 0
    if a.komut == "tanila":
        return tanila_komutu(a.yol, a.adlari_goster, a.ayrinti)
    if a.komut == "saglik":
        return saglik_komutu(a.veri)
    return calistir(a.arka_plan)


if __name__ == "__main__":
    sys.exit(main())
