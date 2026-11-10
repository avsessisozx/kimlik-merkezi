"""mcp_cagri.py yardımcısı: izinli çağrı, yasak araç, anahtar sızıntısı, kapalı kategori."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import gercekler as G
import mcp_cagri as M
import tanir as T

YARDIMCI = Path(M.__file__).resolve()


@pytest.fixture(scope="module")
def kurulu(tmp_path_factory):
    c = tmp_path_factory.mktemp("tanir_c")
    T.cmd_uret(c, G.SEED)
    T.cmd_kur(c, False)
    return c


def cagir(kurulu, *args):
    cfg = kurulu / "paket" / "C" / "mcp.json"
    p = subprocess.run([sys.executable, str(YARDIMCI), "--yapilandirma", str(cfg), *args],
                       capture_output=True, text=True, timeout=120, env=os.environ.copy())
    return p


def anahtar(kurulu):
    return (kurulu / "anahtar" / "mcp_anahtari.txt").read_text(encoding="utf-8").strip()


def test_izinli_cagri_calisiyor(kurulu):
    p = cagir(kurulu, "kategorileri_listele")
    assert p.returncode == 0, p.stderr
    assert sorted(k["kategori"] for k in json.loads(p.stdout)["kategoriler"]) == \
        sorted(["kod", "muzik", "persona", "sosyal", "tarama", "video"])
    p = cagir(kurulu, "ara", "--arg", "sorgu=v60", "--arg", "limit=3")   # limit şemadan tamsayıya çevrilir
    assert p.returncode == 0, p.stderr
    kay = json.loads(p.stdout)["kayitlar"]
    assert 0 < len(kay) <= 3 and all("v60" in k["veri"].lower() for k in kay)
    p = cagir(kurulu, "ara", '{"sorgu": "v60", "kategori": "tarama", "limit": 1}')   # JSON dizgisi
    assert p.returncode == 0 and len(json.loads(p.stdout)["kayitlar"]) == 1


def test_yasak_ve_bilinmeyen_arac_reddedilir(kurulu):
    for ad in ("persona_oner", "olmayan_arac"):
        p = cagir(kurulu, ad)
        assert p.returncode == 2
        assert "izin yok" in json.loads(p.stdout)["hata"]


def test_ciktida_anahtar_ve_ortam_yok(kurulu):
    k = anahtar(kurulu)
    cfg = json.loads((kurulu / "paket" / "C" / "mcp.json").read_text(encoding="utf-8"))
    degerler = [v for v in cfg["mcpServers"]["kimlik-merkezi"]["env"].values() if len(v) >= 6]
    assert k in degerler
    for args in (("kategorileri_listele",), ("kimlik_karti",), ("ara", "--arg", "sorgu=v60"),
                 ("persona_oner",), ("ara", "--arg", "sorgu=x", "--arg", "kategori=eposta")):
        p = cagir(kurulu, *args)
        for d in degerler:
            assert d not in p.stdout and d not in p.stderr, args


def test_sansurle_hata_metnindeki_degeri_siler():
    assert M.sansurle("hata gizlisifre123 var", ["gizlisifre123"]) == "hata [GİZLİ] var"


def test_kapali_kategori_reddedilir_ve_sizmaz(kurulu):
    for kat, deger in (("eposta", "lx7qk2"), ("konum", "umitkoy"), ("mesaj", "deniz"), ("sohbet", "bulutiz")):
        p = cagir(kurulu, "ara", "--arg", f"sorgu={deger}", "--arg", f"kategori={kat}")
        assert p.returncode == 1 and "reddedildi" in json.loads(p.stdout)["hata"], kat
        assert deger not in json.loads(p.stdout)["hata"].lower().replace(f"'{kat}'", "")
    p = cagir(kurulu, "ara", "--arg", "sorgu=lx7qk2")   # kategorisiz: hassas değer dönmemeli
    assert p.returncode == 0 and json.loads(p.stdout)["kayitlar"] == []


def test_hatali_yapilandirma_turkce_hata(tmp_path):
    p = subprocess.run([sys.executable, str(YARDIMCI), "--yapilandirma", str(tmp_path / "yok.json"), "ara"],
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 2 and "bulunamadı" in json.loads(p.stdout)["hata"]
