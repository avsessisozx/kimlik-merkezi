"""SBOM betiği (windows/paket/sbom_uret.py): CycloneDX yapısı ve kapanışın temel özellikleri."""
import importlib.util
import json
from importlib import metadata
from pathlib import Path

import pytest

YOL = Path(__file__).resolve().parents[1] / "paket" / "sbom_uret.py"


def _modul():
    ozel = importlib.util.spec_from_file_location("sbom_uret", YOL)
    m = importlib.util.module_from_spec(ozel)
    ozel.loader.exec_module(m)
    return m


def _kurulu():
    try:
        return all(metadata.distribution(k) for k in ("kimlikcore", "kimlikserver", "kimlikimport", "kimlikwin"))
    except metadata.PackageNotFoundError:
        return False


pytestmark = pytest.mark.skipif(not _kurulu(), reason="kimlik* paketleri pip ile kurulu değil")


def test_sbom_yapisi(tmp_path):
    m = _modul()
    cikti = tmp_path / "alt" / "sbom.cdx.json"
    assert m.main(["--cikti", str(cikti), "--surum", "9.9.9", "--ek", "tepsi"]) == 0
    b = json.loads(cikti.read_text(encoding="utf-8"))
    assert b["bomFormat"] == "CycloneDX" and b["specVersion"] == "1.5"
    assert b["metadata"]["component"]["version"] == "9.9.9"
    adlar = {c["name"].lower() for c in b["components"]}
    assert {"kimlikcore", "kimlikserver", "kimlikimport", "kimlikwin", "mcp"} <= adlar
    refler = {c["bom-ref"] for c in b["components"]}
    assert len(refler) == len(b["components"])                      # bom-ref'ler benzersiz
    for d in b["dependencies"]:
        assert d["ref"] in refler | {"kimlik-merkezi"}
        assert set(d["dependsOn"]) <= refler                          # kopuk ilişki yok
    for c in b["components"]:
        assert c.get("licenses") or any("lisans-uyarisi" in p["name"] for p in c.get("properties", []))


def test_ayni_girdi_ayni_cikti(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    m = _modul()
    assert m.uret("1.0.0", set()) == m.uret("1.0.0", set())


def test_cp1252_konsolda_cokmez(tmp_path):
    """Windows CI'da konsol cp1252: Türkçe çıktı UnicodeEncodeError vermemeli (gerçek hata)."""
    import os
    import subprocess
    import sys
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    r = subprocess.run([sys.executable, str(YOL), "--cikti", str(tmp_path / "s.json")],
                       env=env, capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-300:]
    json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
