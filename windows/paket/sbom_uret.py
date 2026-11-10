"""Yazılım malzeme listesi (SBOM) üretir: CycloneDX 1.5, JSON.

Yeni bağımlılık YOKTUR: yalnızca Python standart kitaplığı ve kurulu paketlerin üst verisi
(`importlib.metadata`) kullanılır. Betik, paketin kurulduğu ortamda (CI'da PyInstaller'dan
önce `pip install` yapılan ortam) çalıştırılmalıdır; liste o ortamda KURULU olanı yansıtır.

Kullanım:
    python sbom_uret.py --cikti cikti/sbom.cdx.json [--surum 0.1.0] [--ek tepsi]

Nasıl çalışır:
  - Kökler: kimlikcore, kimlikserver, kimlikimport, kimlikwin (uygulamanın kendi paketleri).
  - Her paketin `Requires-Dist` satırlarından kurulu bağımlılıklar yinelemeli izlenir.
  - `extra == ...` işaretli satırlar yalnız o paket için istenen eklerde sayılır: kökler için `--ek`,
    diğerleri için bağımlılık satırındaki `ad[ek]` yazımı (ör. `pyjwt[crypto]`) ile.
  - Diğer ortam işaretleri (ör. `sys_platform == "win32"`) DEĞERLENDİRİLMEZ; bağımlılık o ortamda
    kurulu değilse atlanır. Yani liste "bu ortamda kurulu olan" kümesidir.
  - Lisans: önce `License-Expression`, sonra `License ::` sınıflandırıcıları, sonra kısa `License`
    alanı. Hiçbiri yoksa lisans UYDURULMAZ; bileşene "lisans belirtilmemiş" özelliği yazılır.
  - Pakete gömülü pip dışı bileşenler: CPython çalışma zamanı ve Apache ECharts (sürümü dosyadan okunur).
  - Üretim araçları (PyInstaller) yalnız `metadata.tools` altında anılır, bileşen listesine girmez.
Çıktı aynı girdiyle aynıdır (serialNumber içeriğin özetinden türetilir); zaman damgası için
SOURCE_DATE_EPOCH ortam değişkeni desteklenir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import uuid
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

KOKLER = ("kimlikcore", "kimlikserver", "kimlikimport", "kimlikwin")
STATIK = Path(__file__).resolve().parent.parent / "src" / "kimlikwin" / "statik"
_AD_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?")
_EXTRA_RE = re.compile(r"""extra\s*==\s*['"]([^'"]+)['"]""")


def kanonik(ad: str) -> str:
    return re.sub(r"[-_.]+", "-", ad).lower()


def _dist(ad: str) -> metadata.Distribution | None:
    try:
        return metadata.distribution(ad)
    except metadata.PackageNotFoundError:
        return None


def gereksinimler(d: metadata.Distribution, ekler: set[str]) -> list[tuple[str, set[str]]]:
    """`d`nin doğrudan bağımlılıkları: (kanonik ad, istenen ekler). Ek işaretli satırlar yalnız
    `ekler` içinde istenmişse sayılır."""
    out: list[tuple[str, set[str]]] = []
    for satir in d.requires or []:
        govde, _, isaret = satir.partition(";")
        m = _AD_RE.match(govde)
        if not m:
            continue
        ex = _EXTRA_RE.findall(isaret)
        if ex and not any(e in ekler for e in ex):
            continue
        istenen = {e.strip().lower() for e in (m.group(2) or "").split(",") if e.strip()}
        out.append((kanonik(m.group(1)), istenen))
    return out


def lisans(md) -> tuple[list[dict], str | None]:
    """(CycloneDX licenses listesi, uyarı). Uydurma yok: bulunamazsa boş liste + uyarı."""
    ifade = (md.get("License-Expression") or "").strip()
    if ifade:
        return [{"expression": ifade}], None
    adlar = []
    for c in md.get_all("Classifier") or []:
        if c.startswith("License :: "):
            son = c.split(" :: ")[-1].strip()
            if son and son != "OSI Approved":
                adlar.append(son)
    if adlar:
        return [{"license": {"name": a}} for a in dict.fromkeys(adlar)], None
    alan = (md.get("License") or "").strip()
    if alan and "\n" not in alan and len(alan) <= 100 and alan.upper() != "UNKNOWN":
        return [{"license": {"name": alan}}], None
    return [], "lisans üst veriden belirlenemedi; elle doğrulanmalı"


def bilesen(d: metadata.Distribution, kok: bool) -> dict:
    md = d.metadata
    ad, surum = md["Name"], d.version
    ref = f"pkg:pypi/{kanonik(ad)}@{surum}"
    b: dict = {"type": "application" if kok else "library", "bom-ref": ref, "name": ad,
               "version": surum, "purl": ref}
    props = []
    if kok:
        # Uygulamanın kendi paketlerinin üst verisinde lisans alanı yok; lisans depodaki LICENSE (MIT).
        b["licenses"] = [{"license": {"id": "MIT"}}]
        props.append({"name": "kimlik:uygulamanin-kendi-paketi", "value": "true"})
    else:
        lis, uyari = lisans(md)
        if lis:
            b["licenses"] = lis
        if uyari:
            props.append({"name": "kimlik:lisans-uyarisi", "value": uyari})
    if props:
        b["properties"] = props
    return b


def pip_bilesenleri(ekler: set[str]) -> tuple[list[dict], list[dict], list[str]]:
    """(bileşenler, bağımlılık ilişkileri, kurulmamış kökler). Ek istekleri sabit noktaya kadar yayılır."""
    kokler = {kanonik(k) for k in KOKLER}
    eksik = [k for k in KOKLER if _dist(k) is None]
    istek: dict[str, set[str]] = {kanonik(k): set(ekler) for k in KOKLER if _dist(k) is not None}
    kayit: dict[str, metadata.Distribution] = {}
    iliski: dict[str, list[str]] = {}
    degisti = True
    while degisti:
        degisti = False
        for k in sorted(istek):
            d = kayit.get(k) or _dist(k)
            if d is None:
                continue    # bu ortamda kurulu değil (ör. başka platforma özgü bağımlılık)
            kayit[k] = d
            alt = []
            for ad, ex in gereksinimler(d, istek[k]):
                if _dist(ad) is None:
                    continue
                alt.append(ad)
                if ad not in istek:
                    istek[ad] = set(ex); degisti = True
                elif not ex <= istek[ad]:
                    istek[ad] |= ex; degisti = True
            iliski[k] = alt
    bil = [bilesen(d, k in kokler) for k, d in sorted(kayit.items())]
    ref = {k: f"pkg:pypi/{kanonik(d.metadata['Name'])}@{d.version}" for k, d in kayit.items()}
    dep = [{"ref": ref[k], "dependsOn": sorted({ref[a] for a in v if a in ref})}
           for k, v in sorted(iliski.items())]
    return bil, dep, eksik


def gomulu_bilesenler() -> list[dict]:
    """Pakete pip dışı yoldan giren bileşenler (yalnız bulunabilenler; bulunamayan uydurulmaz)."""
    out = [{"type": "platform", "bom-ref": "cpython", "name": "CPython",
            "version": platform.python_version(), "licenses": [{"license": {"id": "Python-2.0"}}],
            "description": "Python çalışma zamanı (PyInstaller paketine gömülür)"}]
    js = STATIK / "echarts.min.js"
    if js.is_file():
        veri = js.read_bytes()
        m = re.search(rb'version="(\d+\.\d+\.\d+)"', veri)
        if m:
            s = m.group(1).decode()
            out.append({"type": "library", "bom-ref": f"echarts@{s}", "name": "Apache ECharts",
                        "version": s, "purl": f"pkg:npm/echarts@{s}",
                        "licenses": [{"license": {"id": "Apache-2.0"}}],
                        "hashes": [{"alg": "SHA-256", "content": hashlib.sha256(veri).hexdigest()}],
                        "description": "Grafikler; kimlikwin/statik içinde yerel dosya (CDN yok)"})
    return out


def uret(surum: str, ekler: set[str]) -> dict:
    pip_b, dep, eksik = pip_bilesenleri(ekler)
    if eksik:
        raise SystemExit(f"Kurulu olmayan kök paket(ler): {', '.join(eksik)}. "
                         "Önce paketleri kurun (pip install ./core ./server ./importers ./windows).")
    bil = pip_b + gomulu_bilesenler()
    araclar = [{"type": "application", "name": "sbom_uret.py", "version": "1"}]
    pyi = _dist("pyinstaller")
    if pyi is not None:
        araclar.append({"type": "application", "name": "PyInstaller", "version": pyi.version})
    ts = datetime.fromtimestamp(int(os.environ["SOURCE_DATE_EPOCH"]), timezone.utc) \
        if os.environ.get("SOURCE_DATE_EPOCH") else datetime.now(timezone.utc)
    belge = {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "metadata": {
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tools": {"components": araclar},
            "component": {"type": "application", "bom-ref": "kimlik-merkezi", "name": "Kimlik Merkezi",
                          "version": surum, "licenses": [{"license": {"id": "MIT"}}]},
        },
        "components": bil,
        "dependencies": [{"ref": "kimlik-merkezi", "dependsOn": sorted(
            c["bom-ref"] for c in pip_b if c.get("type") == "application")}] + dep,
    }
    ozet = hashlib.sha256(json.dumps([bil, dep, surum], sort_keys=True).encode()).hexdigest()
    belge["serialNumber"] = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "kimlik-merkezi-sbom:" + ozet))
    return belge


def _utf8_akis() -> None:
    """Windows konsolu (cp1252 vb.) Türkçe harfte çökmesin: çıktı UTF-8, çözülemeyen karakter '?' olur."""
    for akis in (sys.stdout, sys.stderr):
        try:
            akis.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _utf8_akis()
    p = argparse.ArgumentParser(description="CycloneDX SBOM (JSON) üretir; yeni bağımlılık gerektirmez.")
    p.add_argument("--cikti", required=True, help="yazılacak dosya (örn. cikti/sbom.cdx.json)")
    p.add_argument("--surum", default=None, help="uygulama sürümü (varsayılan: kimlikwin sürümü)")
    p.add_argument("--ek", action="append", default=[], help="kök paketlerin istenen ekleri (örn. tepsi)")
    a = p.parse_args(argv)
    surum = a.surum
    if surum is None:
        d = _dist("kimlikwin")
        surum = d.version if d else "0.0.0"
    belge = uret(surum, set(a.ek))
    hedef = Path(a.cikti)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(json.dumps(belge, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    belirsiz = [c["name"] for c in belge["components"]
                if any(x.get("name") == "kimlik:lisans-uyarisi" for x in c.get("properties", []))]
    print(f"SBOM yazıldı: {hedef} ({len(belge['components'])} bileşen)")
    if belirsiz:
        print("UYARI: lisansı belirlenemeyen bileşenler: " + ", ".join(belirsiz), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
