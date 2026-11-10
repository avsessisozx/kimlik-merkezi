"""Tek MCP aracı çağıran komut satırı yardımcısı (C koşulu için).

Cevaplayıcı ajanın kendi MCP istemcisi yoksa, yalnız bu betik verilir. Betik `mcp.json`
(Claude Code `mcpServers` biçimi) içindeki command/args/env ile sunucuyu GERÇEK MCP stdio
protokolüyle başlatır, TEK bir izinli aracı çağırır, sonucu JSON olarak stdout'a yazar ve
sunucuyu kapatır.

  python mcp_cagri.py --yapilandirma mcp.json kategorileri_listele
  python mcp_cagri.py --yapilandirma mcp.json ara --arg sorgu=v60 --arg limit=5
  python mcp_cagri.py --yapilandirma mcp.json ara '{"sorgu": "kahve", "kategori": "tarama"}'

Güvenlik: yalnız altı salt-okur araç izinlidir (`persona_oner` ve bilinmeyenler reddedilir).
Yapılandırmadaki ortam değişkeni değerleri (anahtar dahil) çıktıdan SİLİNİR; betik bunları
yazmaz. Betik kendisi ağa bağlanmaz (yalnız çocuk sürece stdio ile konuşur). Bu bir ERİŞİM
KISITI DEĞİL, kolaylık ve kaza önleyicidir: Bash'i olan bir ajan yine de dosyaları açabilir.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

IZINLI = ("kategorileri_listele", "ara", "zaman_cizelgesi", "persona_getir", "kimlik_karti", "ornekle")
SUNUCU_ADI = "kimlik-merkezi"
ZAMAN_ASIMI = 90


class Hata(Exception):
    pass


def yapilandirma_oku(yol: str) -> dict:
    try:
        ham = json.loads(Path(yol).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Hata(f"Yapılandırma dosyası bulunamadı: {yol}")
    except (OSError, ValueError) as e:
        raise Hata(f"Yapılandırma okunamadı ({type(e).__name__}).")
    sunucular = ham.get("mcpServers") if isinstance(ham, dict) else None
    if not isinstance(sunucular, dict) or not sunucular:
        raise Hata("Yapılandırmada 'mcpServers' bulunamadı.")
    s = sunucular.get(SUNUCU_ADI) or (next(iter(sunucular.values())) if len(sunucular) == 1 else None)
    if not isinstance(s, dict) or not s.get("command"):
        raise Hata(f"Yapılandırmada '{SUNUCU_ADI}' sunucusu (command ile) bulunamadı.")
    return s


def argumanlar(konumsal_json: str | None, ciftler: list[str]) -> dict:
    arg: dict = {}
    if konumsal_json:
        try:
            arg = json.loads(konumsal_json)
        except ValueError:
            raise Hata("JSON argüman dizgisi geçersiz.")
        if not isinstance(arg, dict):
            raise Hata("JSON argüman dizgisi bir nesne olmalı.")
    for c in ciftler:
        if "=" not in c:
            raise Hata(f"--arg 'anahtar=deger' biçiminde olmalı: {c!r}")
        k, v = c.split("=", 1)
        arg[k.strip()] = v
    return arg


def sema_ile_donustur(arg: dict, sema: dict) -> dict:
    """--arg değerleri dizgidir; araç şemasındaki tipe göre sayıya/mantıksala çevir."""
    ozellik = (sema or {}).get("properties", {})
    for k, v in list(arg.items()):
        tip = ozellik.get(k, {}).get("type")
        if not isinstance(v, str):
            continue
        try:
            if tip == "integer":
                arg[k] = int(v)
            elif tip == "number":
                arg[k] = float(v)
            elif tip == "boolean":
                arg[k] = v.strip().lower() in ("1", "true", "evet", "dogru")
        except ValueError:
            raise Hata(f"'{k}' bir {tip} olmalı: {v!r}")
    return arg


def sansurle(metin: str, gizli: list[str]) -> str:
    for g in sorted(gizli, key=len, reverse=True):
        if g:
            metin = metin.replace(g, "[GİZLİ]")
    return metin


async def cagir(sunucu: dict, arac: str, arg: dict, gizli: list[str]) -> tuple[dict, bool]:
    from mcp import Client, StdioServerParameters
    p = StdioServerParameters(command=sunucu["command"], args=list(sunucu.get("args", [])),
                              env={str(k): str(v) for k, v in (sunucu.get("env") or {}).items()})
    async with Client(p) as c:
        araclar = {t.name: t for t in (await c.list_tools()).tools}
        if arac not in araclar:
            raise Hata(f"Sunucu '{arac}' aracını sunmuyor.")
        sema = araclar[arac].input_schema
        arg = sema_ile_donustur(arg, sema)
        r = await c.call_tool(arac, arg)
        if r.is_error:
            metin = " ".join(getattr(x, "text", "") for x in r.content)
            return {"hata": sansurle(metin, gizli) or "Araç hata döndürdü."}, True
        if r.structured_content is not None:
            return r.structured_content, False
        return {"metin": sansurle(" ".join(getattr(x, "text", "") for x in r.content), gizli)}, False


def ana(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kimlik Merkezi MCP sunucusunda tek izinli aracı çağırır.")
    ap.add_argument("--yapilandirma", required=True, help="mcp.json yolu")
    ap.add_argument("arac", help="araç adı: " + ", ".join(IZINLI))
    ap.add_argument("json_arguman", nargs="?", help="isteğe bağlı JSON argüman nesnesi")
    ap.add_argument("--arg", action="append", default=[], metavar="anahtar=deger")
    try:
        a = ap.parse_args(argv)
        if a.arac not in IZINLI:
            raise Hata(f"'{a.arac}' aracına izin yok. İzinli araçlar: {', '.join(IZINLI)}."
                       + (" 'persona_oner' bu ölçümde kullanılamaz." if a.arac == "persona_oner" else ""))
        sunucu = yapilandirma_oku(a.yapilandirma)
        arg = argumanlar(a.json_arguman, a.arg)
        gizli = [str(v) for v in (sunucu.get("env") or {}).values() if len(str(v)) >= 6]
        try:
            cikti, hata = asyncio.run(asyncio.wait_for(cagir(sunucu, a.arac, arg, gizli), ZAMAN_ASIMI))
        except Hata:
            raise
        except asyncio.TimeoutError:
            raise Hata(f"Sunucu {ZAMAN_ASIMI} sn içinde yanıt vermedi.")
        except Exception as e:  # noqa: BLE001 - ayrıntı anahtar içerebilir, yalnız tür yazılır
            raise Hata(f"Sunucu çağrısı başarısız ({type(e).__name__}).")
    except Hata as e:
        print(json.dumps({"hata": str(e)}, ensure_ascii=False))
        return 2
    print(sansurle(json.dumps(cikti, ensure_ascii=False, indent=2), gizli))
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(ana())
