"""Klasörler arası uçtan uca akış (yalnız kimlikcore + kimlikserver, gerçek süreçler):

jsonl içe aktar (CLI) -> ara (CLI) -> izin ver (KeyManager) -> gerçek stdio MCP ile sorgula
-> erişim kaydı (erisim.db) -> kimlik kartı (MCP + Persona).
Paketler `pip install -e core -e server` ile kurulu olmalıdır.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys

import pytest
from kimlikcore import Hub
from kimlikserver.access import AccessLog, KeyManager
from kimlikserver.persona import Persona
from mcp import Client, StdioServerParameters

SATIRLAR = [
    {"ts": "2026-10-01T09:00:00Z", "kind": "sentetik.not", "category": "notlar",
     "text": "Şişli'de kahve toplantısı notu", "event_key": "n1"},
    {"ts": "2026-10-02T09:00:00Z", "kind": "sentetik.not", "category": "notlar",
     "text": "ışık faturası hatırlatması", "event_key": "n2"},
    {"ts": "2026-10-03T09:00:00Z", "kind": "sentetik.video", "category": "video",
     "text": "kahve demleme videosu", "event_key": "v1"},
    {"ts": "2026-10-04T09:00:00Z", "kind": "sentetik.eposta", "category": "eposta",
     "text": "kahve siparişi onay e-postası GIZLIEPOSTA", "event_key": "e1"},
]


def _cli(root, *args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-m", "kimlikcore", "--veri", str(root), *map(str, args)],
                       env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _mcp(root, key):
    return StdioServerParameters(
        command=sys.executable, args=["-m", "kimlikserver.mcp"],
        env={"KIMLIK_VERI": str(root), "KIMLIK_ANAHTAR": key})


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 90))


@pytest.fixture
def dunya(tmp_path):
    root = tmp_path / "veri"
    girdi = tmp_path / "gir.jsonl"
    girdi.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in SATIRLAR) + "\n",
                     encoding="utf-8")
    _cli(root, "baslat")
    ice = json.loads(_cli(root, "--json", "ice-al", girdi))
    return {"root": root, "girdi": girdi, "ice": ice}


def test_icealdan_kimlik_kartina(dunya):
    root = dunya["root"]

    # 1. içe aktarma
    assert dunya["ice"]["eklenen"] == 4
    # aynı dosya ikinci kez: tekrar sayılır, çoğalmaz
    ikinci = json.loads(_cli(root, "--json", "ice-al", dunya["girdi"]))
    assert ikinci["eklenen"] == 0 and ikinci["tekrar"] == 4

    # 2. CLI ile arama (Türkçe katlama: ISIK -> ışık)
    bulunan = json.loads(_cli(root, "--json", "ara", "ISIK"))
    assert len(bulunan) == 1

    # 3. izin ver: A uygulamasına yalnız notlar + persona; B hiçbir şey
    with Hub.open(root, write=True) as hub:
        km = KeyManager(hub)
        a_id, a_key = km.create_key("Uygulama A")
        _b_id, b_key = km.create_key("Uygulama B")
        km.grant(a_id, "notlar")
        km.grant(a_id, "persona")
        p = Persona(hub)
        p.add_fact("Adım Deneme Kullanıcı", "kimlik")
        p.add_fact_from_source("Kahveyi sütsüz içer", "tercihler", dunya["ice"]["kaynak"])

    # 4. gerçek stdio MCP
    async def go():
        async with Client(_mcp(root, a_key)) as c:
            araclar = (await c.list_tools()).tools
            kat = await c.call_tool("kategorileri_listele", {})
            ok = await c.call_tool("ara", {"sorgu": "kahve"})
            video = await c.call_tool("ara", {"sorgu": "kahve", "kategori": "video"})
            eposta = await c.call_tool("ara", {"sorgu": "GIZLIEPOSTA", "kategori": "eposta"})
            kart = await c.call_tool("kimlik_karti", {})
        async with Client(_mcp(root, b_key)) as c:
            b_ara = await c.call_tool("ara", {"sorgu": "kahve"})
        return araclar, kat, ok, video, eposta, kart, b_ara

    araclar, kat, ok, video, eposta, kart, b_ara = _run(go())

    assert {t.name for t in araclar} == {"kategorileri_listele", "ara", "zaman_cizelgesi",
                                         "persona_getir", "kimlik_karti"}
    assert [k["kategori"] for k in kat.structured_content["kategoriler"]] == ["notlar", "persona"]

    # yalnız izinli kategori döner; kayıt metni yalnız `veri` alanında, etiketli
    kayitlar = ok.structured_content["kayitlar"]
    assert [r["veri"] for r in kayitlar] == ["Şişli'de kahve toplantısı notu"]
    assert all(r["etiket"] == "veri" for r in kayitlar)

    # izinsiz kategori reddedilir ve içerik sızmaz
    for r in (video, eposta):
        assert r.is_error and "reddedildi" in r.content[0].text
        assert "GIZLIEPOSTA" not in r.content[0].text and "demleme" not in r.content[0].text
    # izni olmayan uygulama hiçbir şey görmez
    assert b_ara.is_error or b_ara.structured_content["kayitlar"] == []
    assert "Şişli" not in json.dumps(b_ara.structured_content or {}, ensure_ascii=False)

    # 5. erişim kaydı
    satirlar = AccessLog(root).read_all()
    a_satirlari = [s for s in satirlar if s[1] == a_id]
    assert [(s[2], s[5]) for s in a_satirlari] == [
        ("kategorileri_listele", "ok"), ("ara", "ok"), ("ara", "reddedildi"),
        ("ara", "reddedildi"), ("kimlik_karti", "ok")]
    assert [s[4] for s in a_satirlari if s[2] == "ara" and s[5] == "ok"] == [1]
    assert not [s for s in satirlar if s[1] == a_id and s[5] == "hata"]
    assert any(s[1] != a_id for s in satirlar)  # B'nin reddi de kaydedildi

    # 6. kimlik kartı
    metin = kart.structured_content["veri"]
    assert "Adım Deneme Kullanıcı" in metin
    assert "Kahveyi sütsüz içer" in metin and "kaynak:" in metin
    assert "GIZLIEPOSTA" not in metin


def test_iptal_sonrasi_ve_gizleme_stdio_uzerinden(dunya):
    root = dunya["root"]
    with Hub.open(root, write=True) as hub:
        km = KeyManager(hub)
        a_id, a_key = km.create_key("Uygulama A")
        km.grant(a_id, "notlar")
        olay = hub.search("kahve", categories=["notlar"])[0]

    async def go():
        async with Client(_mcp(root, a_key)) as c:
            once = await c.call_tool("ara", {"sorgu": "kahve"})
            with Hub.open(root, write=True) as hub:  # çalışan MCP varken gizle
                hub.hide_event(olay.event_id, "test")
            sonra = await c.call_tool("ara", {"sorgu": "kahve"})
            with Hub.open(root, write=True) as hub:
                KeyManager(hub).revoke_key(a_id)
            iptal = await c.call_tool("ara", {"sorgu": "ışık"})
            return once, sonra, iptal

    once, sonra, iptal = _run(go())
    assert len(once.structured_content["kayitlar"]) == 1
    assert sonra.structured_content["kayitlar"] == []  # tombstone sorguda dönmez
    assert iptal.is_error
