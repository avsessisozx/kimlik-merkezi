"""Kurulu uygulamayı gerçek süreçlerle dener (CI, Windows). Kullanım:
  python kurulu_dene.py <kurulum_dizini> <calisma_dizini> <takeout_klasoru>
Konsol exe'sinin `tanila` komutunu sentinel'li sahte örnekle dener (sızıntı yok, çıkış 0). Uygulamayı arka planda başlatır, yerel web API'siyle sihirbazı tamamlar, içe aktarır, "Claude'a ekle"yi
SAHTE ayar dosyasıyla dener, arayüzün dosya denetimi ucunu bir kez çağırır, MCP exe'sini gerçek stdio ile sorgular, uygulamayı kapatır.
Başarısızlıkta sıfır olmayan kodla çıkar; her adım yazdırılır."""
from __future__ import annotations

import sys as _sys
for _akis in (_sys.stdout, _sys.stderr):    # Windows konsolu (cp1252) Türkçe harfte çökmesin
    try:
        _akis.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

kurulum, calisma, fixture = (Path(a) for a in sys.argv[1:4])
BEKLENEN_SURUM = sys.argv[4] if len(sys.argv) > 4 else None
APP = kurulum / "KimlikMerkezi.exe"
MCP = kurulum / "kimlikmerkezi-mcp.exe"
ayar = calisma / "ayar"
veri = calisma / "veri"
appdata = calisma / "appdata"
claude_cfg = appdata / "Claude" / "claude_desktop_config.json"
claude_cfg.parent.mkdir(parents=True, exist_ok=True)
onceki = {"theme": "dark", "mcpServers": {"baska": {"command": "x", "args": []}}}
claude_cfg.write_text(json.dumps(onceki), encoding="utf-8")


def adim(m):
    print(f"[dene] {m}", flush=True)


def kontrol(kosul, m):
    if not kosul:
        print(f"[dene] BAŞARISIZ: {m}", flush=True)
        raise SystemExit(1)
    adim(f"tamam: {m}")


# ---- konsol exe: sürüm (ijson C uzantısı) ve sağlık komutu
r = subprocess.run([str(MCP), "surum"], capture_output=True, text=True, encoding="utf-8", timeout=60)
adim(r.stdout.strip())
if BEKLENEN_SURUM:
    kontrol(f"Kimlik Merkezi {BEKLENEN_SURUM}\n" in r.stdout.replace("\r\n", "\n"), f"exe sürümü {BEKLENEN_SURUM} (Release sürümüyle eşleşiyor)")
kontrol(r.returncode == 0 and "ijson arka ucu: yajl2_c" in r.stdout, "pakette ijson C uzantısı (yajl2_c) var")
kontrol("pypdf: var" in r.stdout and "docx: var" in r.stdout, "pakette pypdf ve python-docx (belge okuyucular) var")

# ---- konsol exe: `tanila <yol>` (dosya denetimi). Sahte örnekte özel işaretli dizgiler (sentinel) rapora SIZMAMALI.
import tanila_dene as TD
os.makedirs(calisma, exist_ok=True)
sahte = TD.sahte_zip(calisma / "sentinel-ornek.zip")
tenv = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", KIMLIK_AYAR_DIZINI=str(ayar))
tenv.pop("KIMLIK_VERI", None)
for ek, acik in (([], False), (["--ayrinti"], False), (["--adlari-goster"], True)):
    t = subprocess.run([str(MCP), "tanila", str(sahte), *ek], capture_output=True, text=True, encoding="utf-8",
                       timeout=300, env=tenv, cwd=str(calisma))
    kontrol(t.returncode == 0, f"kimlikmerkezi-mcp.exe tanila {' '.join(ek)} çıkış kodu 0 (stderr: {t.stderr.strip()[:200]})")
    sorun = TD.sizinti_var_mi(t.stdout, adlar_acik=acik)
    kontrol(sorun is None, f"tanila raporunda sentinel sızıntısı yok ({'adlar açık' if acik else 'varsayılan'}; {len(t.stdout)} karakter)"
            + (f" — {sorun}" if sorun else ""))
t = subprocess.run([str(MCP), "tanila", str(calisma / "yok-boyle-dosya")], capture_output=True, text=True, encoding="utf-8", timeout=60, env=tenv)
kontrol(t.returncode == 1, "olmayan yolda tanila çıkış kodu 1 (çökmedi)")

# ---- lisans dosyaları ve pystray (LGPL) değiştirilebilirliği: kurulu pakette ayrı dosyalar olarak durmalı
lis = [p for p in kurulum.rglob("*") if p.is_file() and "lisanslar" in p.parts]
adlar = {p.name for p in lis}
kontrol({"LICENSE", "THIRD-PARTY-NOTICES.md"} <= adlar, "lisans dosyaları kurulu pakette var (LICENSE, THIRD-PARTY-NOTICES.md)")
kontrol(any(p.name == "COPYING.LGPL" and p.parent.name == "pystray" for p in lis), "pystray LGPL metni (COPYING.LGPL) kurulu pakette var")
pys = [p for p in kurulum.rglob("*") if p.is_file() and p.suffix in (".pyc", ".py") and "pystray" in p.parts and "lisanslar" not in p.parts]
kontrol(any(p.stem == "_base" for p in pys) and any(p.stem == "_win32" for p in pys),
        "pystray modülleri ayrı dosya (.pyc) olarak kurulu pakette (kullanıcı değiştirebilir)")

# ---- uygulamayı başlat
env = dict(os.environ, KIMLIK_AYAR_DIZINI=str(ayar), APPDATA=str(appdata), PYTHONIOENCODING="utf-8")
env.pop("KIMLIK_VERI", None)
surec = subprocess.Popen([str(APP), "--arka-plan"], env=env)
calisan = ayar / "calisan.json"
port = None
for _ in range(120):
    if surec.poll() is not None:
        kontrol(False, f"uygulama erken kapandı (çıkış {surec.returncode}); günlük: {(ayar / 'gunluk.log').read_text(encoding='utf-8') if (ayar / 'gunluk.log').exists() else 'yok'}")
    try:
        port = json.loads(calisan.read_text(encoding="utf-8"))["port"]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/saglik", timeout=2) as x:
            if json.loads(x.read())["ok"]:
                break
    except (OSError, ValueError, KeyError):
        pass
    time.sleep(0.5)
else:
    kontrol(False, "web arayüzü açılmadı")
kontrol(True, f"uygulama başladı, 127.0.0.1:{port} /saglik yanıt veriyor")

with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as x:
    html = x.read().decode("utf-8")
jeton = re.search(r'name="kimlik-jeton" content="([^"]+)"', html).group(1)
kontrol('lang="tr"' in html and "Kimlik Merkezi" in html, "arayüz sayfası (Türkçe) sunuluyor")


def api(ad, girdi=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/{ad}", json.dumps(girdi or {}).encode(),
                                 {"Content-Type": "application/json", "X-Kimlik-Jeton": jeton})
    try:
        with urllib.request.urlopen(req, timeout=60) as x:
            return json.loads(x.read())
    except urllib.error.HTTPError as e:
        kontrol(False, f"api/{ad} -> HTTP {e.code} {e.read().decode('utf-8')[:300]}")


try:
    if BEKLENEN_SURUM:
        kontrol(api("hakkinda")["surum"] == BEKLENEN_SURUM, f"Hakkında ekranı sürümü {BEKLENEN_SURUM}")
    kontrol(api("acilis")["sihirbaz"] is True, "ilk açılışta sihirbaz isteniyor")
    d = api("sihirbaz_denetle", {"yol": str(veri)})
    kontrol(d["ok"] and d["bos_alan"] > 0, f"veri klasörü denetimi geçti, boş alan: {d['bos_alan_metni']}")
    t = api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": True})
    kontrol((veri / "kimlik.db").is_file() and not (veri / "erisim.db").exists() and (veri / "arsiv").is_dir(),
            "veritabanı ve klasörler oluştu: " + ", ".join(t["dosyalar"]))
    s = api("saglik")
    kontrol(s["ok"], "sağlık denetimi geçti\n" + s["metin"])

    # dosya denetimi (arayüz ucu): sentinel rapora sızmamalı, veritabanına hiçbir şey eklenmemeli
    once = api("durum")["ozet"]["counts"]["event"]
    api("tanila_baslat", {"yol": str(sahte)})
    for _ in range(240):
        td = api("tanila_durum")
        if td["durum"] != "calisiyor":
            break
        time.sleep(0.5)
    kontrol(td["durum"] == "bitti" and td["hata"] is None, f"arayüz ucu tanila_baslat: denetim bitti ({td['durum']})")
    sorun = TD.sizinti_var_mi(td["rapor"])
    kontrol(sorun is None, "arayüz ucu raporunda sentinel sızıntısı yok" + (f" — {sorun}" if sorun else ""))
    kontrol(api("durum")["ozet"]["counts"]["event"] == once and api("kaynaklar")["kaynaklar"] == [], "dosya denetimi veritabanına kayıt/kaynak eklemedi")
    api("tanila_temizle")

    # içe aktar (zip)
    zp = calisma / "takeout.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(fixture.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(fixture).as_posix())
    api("ice_aktar_baslat", {"yol": str(zp)})
    for _ in range(240):
        j = api("ice_aktar_durum")
        if j["durum"] != "calisiyor":
            break
        time.sleep(0.5)
    kontrol(j["durum"] == "bitti", f"içe aktarma bitti: {j.get('hata') or j['sonuc']}")
    n = api("durum")["ozet"]["counts"]["event"]
    kontrol(n > 0, f"{n} olay veritabanında")

    # yerel grafik kütüphanesi pakete girdi mi (CDN yok, internetsiz çalışır)
    for ad, asgari in (("echarts.min.js", 500_000), ("harita.js", 5_000), ("figur.js", 3_000), ("ortak.js", 200), ("harita.css", 3_000), ("ECHARTS-LICENSE.txt", 5_000)):
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/statik/{ad}", timeout=20) as x:
            boy = len(x.read())
        kontrol(boy >= asgari, f"pakette statik/{ad} var ({boy} bayt)")
    # persona haritası (gerçek kimlikserver.harita) paketlenmiş uygulamada çalışıyor
    hv = api("harita")
    kontrol(len(hv["bolgeler"]) >= 9 and hv["profil"]["olay"] > 0, f"harita: {len(hv['bolgeler'])} bölge, {hv['profil']['olay']} olay")
    hb = api("harita_bolge", {"bolge_id": "goz", "filtre": {}})
    kontrol(not hb["kilitli"] and "grafikler" in hb, "harita bölgesi (gözler) okunuyor")

    # Claude'a ekle (sahte ayar dosyası, APPDATA yönlendirildi)
    c = api("claude_ekle")
    kontrol(c["durum"] == "eklendi" and c["yedek"], "Claude'a ekle: eklendi + yedek alındı")
    yeni = json.loads(claude_cfg.read_text(encoding="utf-8"))
    kontrol(yeni["theme"] == "dark" and yeni["mcpServers"]["baska"] == onceki["mcpServers"]["baska"],
            "var olan girişler bozulmadı")
    giris = yeni["mcpServers"]["kimlik-merkezi"]
    kontrol(Path(giris["command"]).samefile(MCP), f"giriş kurulu MCP exe'sini gösteriyor: {giris['command']}")

    # ---- gerçek stdio MCP: Claude'un yapacağı gibi, ayara yazılan komut ve ortamla
    from mcp import Client, StdioServerParameters
    p = StdioServerParameters(command=giris["command"], args=giris["args"], env={**os.environ, **giris["env"]})

    async def go():
        async with Client(p) as cl:
            araclar = (await cl.list_tools()).tools
            kat = await cl.call_tool("kategorileri_listele", {})
            ara = await cl.call_tool("ara", {"sorgu": "a", "kategori": "tarama"})
            ret = await cl.call_tool("ara", {"sorgu": "a", "kategori": "eposta"})
            return araclar, kat, ara, ret
    araclar, kat, ara, ret = asyncio.run(asyncio.wait_for(go(), 90))
    kontrol({a.name for a in araclar} == {"kategorileri_listele", "ara", "zaman_cizelgesi", "persona_getir", "kimlik_karti", "persona_oner", "ornekle"},
            "MCP stdio araç listesi: " + ", ".join(sorted(a.name for a in araclar)))
    kontrol(len(kat.structured_content["kategoriler"]) > 0, "izinli kategoriler listelendi (uygulama yazan olarak açıkken)")
    kontrol(ret.is_error, "izinsiz (hassas) kategori reddedildi")
    kayit = api("erisim_kaydi")["satirlar"]
    kontrol({"ok", "reddedildi"} <= {k["sonuc"] for k in kayit}, f"erişim kaydı {len(kayit)} satır")
finally:
    try:
        api("cikis")
    except BaseException:
        pass
    try:
        surec.wait(timeout=20)
        adim(f"uygulama kapandı, çıkış kodu {surec.returncode}")
    except subprocess.TimeoutExpired:
        surec.kill()
        adim("uygulama zorla kapatıldı")

try:
    adim("uygulama günlüğü:\n" + (ayar / "gunluk.log").read_text(encoding="utf-8"))
except OSError:
    adim("günlük yok")
adim("TÜM ADIMLAR GEÇTİ")
