"""Çekirdek CLI `ice-al --tur` çağrısı çalıştırıcıyla çalışıyor mu (uçtan uca, alt süreç)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
import subprocess

import pytest

# Alt süreç bu çalışma ağacının kimlikcore/kimlikimport kaynağını kullanır (ortamda başka bir
# çalışma ağacından kurulu paketler olabilir).
_ROOT = Path(__file__).resolve().parents[2]
SRC = os.pathsep.join([str(_ROOT / "core" / "src"), str(_ROOT / "importers" / "src")])


def cli(veri, *args):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONPATH": SRC}
    return subprocess.run([sys.executable, "-m", "kimlikcore", "--veri", str(veri), *args], env=env,
                          capture_output=True, encoding="utf-8")


def test_ice_al_tur_takeout_ve_tekrar(tmp_path, zipper):
    veri, z = tmp_path / "v", zipper("takeout_en")
    assert cli(veri, "baslat").returncode == 0
    a = cli(veri, "ice-al", str(z), "--tur", "google_takeout")
    assert a.returncode == 0 and "Eklenen: 22" in a.stdout, a.stdout + a.stderr
    b = cli(veri, "ice-al", str(z), "--tur", "takeout")  # takma ad
    assert b.returncode == 0 and "Eklenen: 0" in b.stdout and "Zaten vardı: 23" in b.stdout
    assert "source: 1" in cli(veri, "ozet").stdout and "event: 22" in cli(veri, "ozet").stdout


def test_ice_al_reddit_ve_hata_cikis_kodu(tmp_path, zipper):
    veri = tmp_path / "v"
    cli(veri, "baslat")
    assert "Eklenen: 16" in cli(veri, "ice-al", str(zipper("reddit")), "--tur", "reddit").stdout
    bad = cli(veri, "ice-al", str(zipper("takeout_html")), "--tur", "google_takeout")
    assert bad.returncode != 0 and "beklenen biçimde değil" in (bad.stderr + bad.stdout)
    unk = cli(veri, "ice-al", str(zipper("reddit")), "--tur", "yok")
    assert unk.returncode != 0 and "Kullanılabilir" in (unk.stderr + unk.stdout)
