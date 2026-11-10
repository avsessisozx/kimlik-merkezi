"""Okuyucuların (QueryService / MCP stdio) şifreli veriyi anahtar sağlayıcıyla açması.

Tasarım (docs/SIFRELEME.md "MCP için anahtar erişimi"): MCP süreci Kimlik Merkezi'ni çalıştıran
Windows hesabıyla başlar; Hub.open anahtarı OS sağlayıcısından (DPAPI) kendisi alır, ayrı sır
taşınmaz. Parola koruması varsa KIMLIK_PAROLA ortam değişkeni gerekir. Burada DPAPI yerine sahte
sağlayıcı (KIMLIK_SAHTE_SAGLAYICI) kullanılır.
"""
import asyncio
import os
import sys

import pytest
from kimlikcore import Hub, sifreleme as sif
from mcp import Client, StdioServerParameters

from helpers import build_world
from kimlikserver.access import AccessLog
from kimlikserver.service import QueryService, ServiceError

IFADE = "mavi bisikletle sahil yolunda sabah kahvesi içtim"
PAROLA = "kuzey-ruzgari-9071"


@pytest.fixture(autouse=True)
def ortam(monkeypatch):
    monkeypatch.setattr(sif, "KDF_N", 1 << 4)
    monkeypatch.setenv(sif.ENV_SAHTE, "mcp-testi")
    monkeypatch.delenv(sif.ENV_PAROLA, raising=False)
    sif.saglayici_ayarla(None)


@pytest.fixture
def sifreli_world(veri):
    Hub.open(veri, write=True, sifreli=True).close()
    w = build_world(veri)
    w["root"] = veri
    assert sif.db_durumu(veri / "kimlik.db") == "sifreli"
    return w


def test_query_service_sifreli_veriyi_okur(sifreli_world):
    r = QueryService(sifreli_world["root"], sifreli_world["a_key"]).ara("kahve")
    assert {x["veri"] for x in r["kayitlar"]} == {"kahve makinesi notu", "kahve tarifi videosu"}
    assert [x[-1] for x in AccessLog(sifreli_world["root"]).read_all()] == ["ok"]


def test_baska_hesapta_anlasilir_hata(sifreli_world, monkeypatch):
    monkeypatch.setenv(sif.ENV_SAHTE, "baska-hesap")
    with pytest.raises(ServiceError, match="şifreli ve anahtar açılamadı"):
        QueryService(sifreli_world["root"], sifreli_world["a_key"]).ara("kahve")


def test_parolali_veri_env_parola_ister(sifreli_world, monkeypatch):
    root = sifreli_world["root"]
    dek = sif.anahtari_coz(root)
    sif.kurtarma_kur(root, dek, IFADE, IFADE)
    sif.parola_ekle(root, dek, PAROLA, PAROLA)
    svc = QueryService(root, sifreli_world["a_key"])
    with pytest.raises(ServiceError, match="KIMLIK_PAROLA"):
        svc.ara("kahve")
    monkeypatch.setenv(sif.ENV_PAROLA, "yanlis-yanlis-1")
    with pytest.raises(ServiceError, match="anahtar açılamadı"):
        svc.ara("kahve")
    monkeypatch.setenv(sif.ENV_PAROLA, PAROLA)
    assert len(svc.ara("kahve")["kayitlar"]) == 2


def test_mcp_stdio_sifreli_veri(sifreli_world):
    root = sifreli_world["root"]

    def params(env_ek):
        env = {"KIMLIK_VERI": str(root), "KIMLIK_ANAHTAR": sifreli_world["a_key"], **env_ek}
        if "PYTHONPATH" in os.environ:   # çocuk süreç bu çalışma ağacındaki kodu kullansın
            env["PYTHONPATH"] = os.environ["PYTHONPATH"]
        return StdioServerParameters(command=sys.executable, args=["-m", "kimlikserver.mcp"], env=env)

    async def cagir(env_ek):
        async with Client(params(env_ek)) as c:
            return await c.call_tool("ara", {"sorgu": "kahve"})

    def run(env_ek):
        return asyncio.run(asyncio.wait_for(cagir(env_ek), 60))

    ok = run({sif.ENV_SAHTE: "mcp-testi"})
    assert not ok.is_error and len(ok.structured_content["kayitlar"]) == 2
    kotu = run({sif.ENV_SAHTE: "baska-hesap"})
    assert kotu.is_error and "anahtar açılamadı" in kotu.content[0].text
    assert not (root / "kimlik.db-wal").exists() and not (root / "hub.lock").exists()
    # yazan süreç (Windows uygulaması) açıkken de okur: yazım sonrası kapsayıcı güncel
    with Hub.open(root, write=True) as h:
        h.add_events(h.add_source("sahte", "1", None), [])
        ok2 = run({sif.ENV_SAHTE: "mcp-testi"})
        assert not ok2.is_error
