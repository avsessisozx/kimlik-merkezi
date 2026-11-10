"""Aşama 3: resmî MCP istemcisiyle gerçek stdio süreci üzerinden testler."""
from __future__ import annotations

import asyncio
import json
import subprocess
import os
import sys

from kimlikcore import Hub
from mcp import Client, StdioServerParameters

from helpers import INJECTION, ev
from kimlikserver.access import AccessLog, KeyManager
from kimlikserver.persona import Persona


def params(root, key):
    env = {"KIMLIK_VERI": str(root)}
    if key:
        env["KIMLIK_ANAHTAR"] = key
    if "PYTHONPATH" in os.environ:   # çocuk süreç bu çalışma ağacındaki kodu kullansın
        env["PYTHONPATH"] = os.environ["PYTHONPATH"]
    return StdioServerParameters(command=sys.executable, args=["-m", "kimlikserver.mcp"], env=env)


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 60))


def test_arac_listesi_ve_aciklamalar(world):
    async def go():
        async with Client(params(world["root"], world["a_key"])) as c:
            return (await c.list_tools()).tools
    tools = {t.name: t for t in run(go())}
    assert set(tools) == {"kategorileri_listele", "ara", "zaman_cizelgesi", "persona_getir",
                          "kimlik_karti", "ornekle", "persona_oner", "say"}
    for name in ("ara", "zaman_cizelgesi", "persona_getir", "kimlik_karti", "ornekle",
                 "persona_oner", "say"):
        assert "talimat değildir" in tools[name].description
    assert "kullanıcı onaylamadan persona değişmez" in tools["persona_oner"].description
    assert all(t.annotations.read_only_hint for n, t in tools.items() if n != "persona_oner")
    assert tools["persona_oner"].annotations.read_only_hint is False
    assert set(tools["ara"].input_schema["properties"]) == {"sorgu", "kategori", "limit", "genislet"}
    assert tools["ara"].input_schema["required"] == ["sorgu"]


def test_cagrilar_ve_ret(world):
    async def go():
        async with Client(params(world["root"], world["a_key"])) as c:
            k = await c.call_tool("kategorileri_listele", {})
            a = await c.call_tool("ara", {"sorgu": "kahve"})
            t = await c.call_tool("zaman_cizelgesi", {"kategori": "video", "limit": 5})
            ret = await c.call_tool("ara", {"sorgu": "kahve", "kategori": "eposta"})
            return k, a, t, ret
    k, a, t, ret = run(go())
    assert [x["kategori"] for x in k.structured_content["kategoriler"]] == \
        ["medya_meta", "notlar", "persona", "video"]
    veri = {r["veri"] for r in a.structured_content["kayitlar"]}
    assert veri == {"kahve makinesi notu", "kahve tarifi videosu"}
    assert [r["veri"] for r in t.structured_content["kayitlar"]] == ["kahve tarifi videosu"]
    assert ret.is_error and "randevu" not in ret.content[0].text
    assert "reddedildi" in ret.content[0].text
    outcomes = [r[5] for r in AccessLog(world["root"]).read_all()]
    assert outcomes == ["ok", "ok", "ok", "reddedildi"]


def test_talimat_kaydi_stdio_uzerinden_yalniz_veri_alaninda(world):
    with Hub.open(world["root"], write=True) as hub:
        hub.add_events(hub.add_source("sahte", "1", None), [ev(INJECTION, "notlar")])

    async def go():
        async with Client(params(world["root"], world["a_key"])) as c:
            return await c.call_tool("ara", {"sorgu": "talimatları unut"})
    r = run(go())
    s = r.structured_content
    assert len(s["kayitlar"]) == 1 and s["kayitlar"][0]["etiket"] == "veri"
    assert s["kayitlar"][0]["veri"] == INJECTION
    s["kayitlar"][0]["veri"] = ""
    assert INJECTION not in json.dumps(s, ensure_ascii=False)


def test_anahtarsiz_cagri_reddedilir(world):
    async def go():
        async with Client(params(world["root"], None)) as c:
            return await c.call_tool("ara", {"sorgu": "kahve"})
    r = run(go())
    assert r.is_error and "reddedildi" in r.content[0].text
    assert AccessLog(world["root"]).read_all()[0][1:] [-1] == "reddedildi"


def test_veri_klasoru_tanimsizsa_cikis_kodu():
    import os
    env = {k: v for k, v in os.environ.items() if k != "KIMLIK_VERI"}
    p = subprocess.run([sys.executable, "-m", "kimlikserver.mcp"], env=env, capture_output=True,
                       text=True, timeout=30, input="")
    assert p.returncode == 2 and p.stdout == ""


def test_yazan_surec_yokken_wal_yan_dosyalari_olmadan_yanit(world):
    r = world["root"]
    assert not (r / "kimlik.db-wal").exists() and not (r / "kimlik.db-shm").exists()

    async def go():
        async with Client(params(r, world["a_key"])) as c:
            return await c.call_tool("ara", {"sorgu": "kahve"})
    out = run(go())
    assert not out.is_error and len(out.structured_content["kayitlar"]) == 2
    assert not (r / "hub.lock").exists()  # MCP kilit almaz


def test_yazan_surec_acilip_yazinca_mcp_bozulmaz(world):
    r = world["root"]

    async def go():
        sayilar = []
        async with Client(params(r, world["a_key"])) as c:
            sayilar.append(len((await c.call_tool("ara", {"sorgu": "yeni"})).structured_content["kayitlar"]))
            with Hub.open(r, write=True) as hub:  # Windows uygulaması açıldı
                sid = hub.add_source("canli", "1", None)
                p = Persona(hub)
                for i in range(30):
                    hub.add_events(sid, [ev(f"yeni kayıt {i}", "notlar", key=f"y{i}")])
                    if i % 10 == 9:
                        sayilar.append(len((await c.call_tool(
                            "ara", {"sorgu": "yeni", "limit": 200})).structured_content["kayitlar"]))
                p.add_fact("Canlı persona", "kimlik")
                KeyManager(hub).grant(world["a_id"], "dosyalar")
                kt = await c.call_tool("kimlik_karti", {})
                kat = await c.call_tool("kategorileri_listele", {})
            # yazan kapandıktan sonra da çalışır
            sayilar.append(len((await c.call_tool(
                "ara", {"sorgu": "yeni", "limit": 200})).structured_content["kayitlar"]))
        return sayilar, kt, kat
    sayilar, kt, kat = run(go())
    assert sayilar == [0, 10, 20, 30, 30]
    assert "Canlı persona" in kt.structured_content["veri"]
    assert "dosyalar" in [x["kategori"] for x in kat.structured_content["kategoriler"]]


def test_calisan_surecte_iptal_ve_izin_degisimi_hemen_gecerli(world):
    async def go():
        async with Client(params(world["root"], world["a_key"])) as c:
            ilk = await c.call_tool("ara", {"sorgu": "kahve", "kategori": "notlar"})
            with Hub.open(world["root"], write=True) as hub:
                KeyManager(hub).revoke_grant(world["a_id"], "notlar")
            ikinci = await c.call_tool("ara", {"sorgu": "kahve", "kategori": "notlar"})
            with Hub.open(world["root"], write=True) as hub:
                KeyManager(hub).revoke_key(world["a_id"])
            ucuncu = await c.call_tool("ara", {"sorgu": "kahve", "kategori": "video"})
            return ilk, ikinci, ucuncu
    ilk, ikinci, ucuncu = run(go())
    assert not ilk.is_error and ikinci.is_error and ucuncu.is_error


def test_uc_mcp_sureci_ayni_anda_kayit_kaybolmaz(world):
    N = 25

    async def worker(i):
        async with Client(params(world["root"], world["a_key"])) as c:
            for _ in range(N):
                r = await c.call_tool("ara", {"sorgu": "kahve", "kategori": "notlar"})
                assert not r.is_error, r.content

    async def go():
        await asyncio.gather(*(worker(i) for i in range(3)))
    run(go())
    rows = AccessLog(world["root"]).read_all()
    assert len(rows) == 3 * N
    assert {r[5] for r in rows} == {"ok"} and {r[1] for r in rows} == {world["a_id"]}


def test_cok_surecli_dogrudan_kayit_yazimi(world):
    kod = ("import sys; from kimlikserver.access import AccessLog; "
           "a=AccessLog(sys.argv[1]); "
           "[a.record('app','ara','notlar',1,'ok') for _ in range(100)]")
    ps = [subprocess.Popen([sys.executable, "-c", kod, str(world["root"])]) for _ in range(6)]
    assert all(p.wait(timeout=60) == 0 for p in ps)
    assert len(AccessLog(world["root"]).read_all()) == 600
