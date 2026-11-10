from __future__ import annotations

import json
import tarfile
from collections import Counter

import pytest
from conftest import FIX, count_events, make_zip
from kimlikcore import FormatError
from kimlikimport import registry
from kimlikimport.base import ImportFormatError
from kimlikimport.github import GitHub
from kimlikimport.run import run


@pytest.fixture
def tgz(tmp_path):
    p = tmp_path / "github-ornek-export.tar.gz"
    with tarfile.open(p, "w:gz") as tf:
        for f in sorted((FIX / "github").iterdir()):
            tf.add(f, arcname=f"export/{f.name}")
        # medya (JSON olmayan) üye: yok sayılmalı
        (tmp_path / "x.png").write_bytes(b"\x89PNG")
        tf.add(tmp_path / "x.png", arcname="export/avatar.png")
    return p


def test_tar_gz_kayit_sayisi_ve_kategori(hub, tgz):
    r = run(hub, tgz)
    assert r.importer == "github" and (r.parsed, r.added, r.duplicate) == (9, 9, 0)
    ev = hub.timeline(limit=100)
    assert {e.category for e in ev} == {"kod"}
    kinds = Counter(e.kind for e in ev)
    assert kinds == {"github.depo": 2, "github.issue": 2, "github.issue_comment": 2, "github.pr": 1,
                     "github.yildiz": 2}
    assert r.skipped == {"github issue: zaman alanı yok": 1}
    assert hub.search("Ornek issue govdesi", categories=["kod"])


def test_gizli_turler_alinmaz_ve_raporlanir(hub, tgz):
    rep = GitHub().verify_format(tgz)
    txt = rep.to_text()
    assert rep.ok and "users_000001.json" in txt and "public_keys_000001.json" in txt
    run(hub, tgz)
    blob = json.dumps([e.payload for e in hub.timeline(limit=100)]) + "".join(e.text for e in hub.timeline(limit=100))
    assert "gizli@example.test" not in blob and "AAAAORNEK" not in blob


def test_iki_kez_tekrarsiz_ve_ham_arsiv(hub, tgz):
    a = run(hub, tgz)
    b = run(hub, tgz)
    assert b.source_id == a.source_id and (b.added, b.duplicate) == (0, 9)
    assert count_events(hub) == 9 and len(hub.raw_files()) == 1
    assert hub.raw_files()[0].name == tgz.name and hub.verify_archive() == []


def test_klasor_ve_zip(hub, tmp_path):
    assert run(hub, FIX / "github", "github").added == 9
    z = make_zip(FIX / "github", tmp_path / "g.zip")
    r = run(hub, z, "github")
    assert r.added == 0 and r.duplicate == 9
    imp, _ = registry.detect_best(z)
    assert imp.name == "github"


def test_otomatik_tanima_tar(tgz):
    imp, res = registry.detect_best(tgz)
    assert imp.name == "github"


def test_bozuk_tar_ve_bos(hub, tmp_path):
    bad = tmp_path / "bozuk.tar.gz"
    bad.write_bytes(b"\x1f\x8b\x08\x00bozuk gzip")
    with pytest.raises(FormatError):
        run(hub, bad, "github")
    d = tmp_path / "bos"
    d.mkdir()
    (d / "x.json").write_text('{"a": 1}')
    with pytest.raises(ImportFormatError) as ei:
        run(hub, d, "github")
    assert "type" in str(ei.value)
    assert count_events(hub) == 0


def test_bozuk_json_icerik_sizdirmaz(hub, tmp_path):
    d = tmp_path / "b"
    d.mkdir()
    (d / "issues_000001.json").write_text('[{"type": "issue", "title": "gizlibaslik", "created_at": "2022-01-01T00:00:00Z"}, {"type"')
    with pytest.raises(FormatError) as ei:
        run(hub, d, "github")
    assert "gizlibaslik" not in str(ei.value)
