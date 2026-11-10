import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def cli(child_env, root):
    def run(*args, ok=True, veri=None, **kw):
        r = subprocess.run([sys.executable, "-m", "kimlikcore", "--veri", str(veri or root), *map(str, args)],
                           env=child_env, capture_output=True, encoding="utf-8", **kw)
        if ok:
            assert r.returncode == 0, r.stderr
        return r
    return run


def write_jsonl(path, n=15):
    path.write_text("\n".join(json.dumps({
        "ts": f"2026-04-{1 + i:02d}T08:00:00Z", "kind": "sentetik.not", "category": "notlar",
        "payload": {"i": i}, "text": f"CLI kaydı {i} ışık İstanbul"}, ensure_ascii=False) for i in range(n)) + "\n",
        encoding="utf-8")


def test_cli_uctan_uca(cli, tmp_path, root):
    f = tmp_path / "gir.jsonl"
    write_jsonl(f)
    assert "Şema sürümü" in cli("baslat").stdout
    r1 = json.loads(cli("--json", "ice-al", f, "--tur", "jsonl").stdout)
    assert r1["eklenen"] == 15
    r2 = json.loads(cli("--json", "ice-al", f, "--tur", "jsonl").stdout)
    assert r2["eklenen"] == 0 and r2["tekrar"] == 15 and r2["kaynak"] == r1["kaynak"]
    found = json.loads(cli("--json", "ara", "ISIK", "--limit", "100").stdout)
    assert len(found) == 15
    assert len(json.loads(cli("--json", "ara", "istanbul", "--kategori", "video").stdout)) == 0
    zaman = json.loads(cli("--json", "zaman", "--limit", "3").stdout)
    assert len(zaman) == 3 and zaman[0]["ts"] > zaman[1]["ts"]
    assert "Sonuç yok" in cli("ara", "olmayanterim").stdout
    ozet = json.loads(cli("--json", "ozet").stdout)
    assert ozet["counts"]["event"] == 15 and ozet["counts"]["source"] == 1
    out = tmp_path / "d.jsonl"
    assert "Dışa aktarıldı" in cli("disa-aktar", out).stdout
    # boş klasöre geri yükle
    r = cli("ice-aktar", out, veri=tmp_path / "y")
    assert "Doğrulama: tamam" in r.stdout
    # gizle / kaldır / sil
    ev = found[0]["event_id"]
    cli("kayit-gizle", ev, "--neden", "deneme")
    assert len(json.loads(cli("--json", "ara", "ISIK", "--limit", "100").stdout)) == 14
    sid = r1["kaynak"]
    assert json.loads(cli("--json", "kaynak-kaldir", sid, "--neden", "x").stdout)["gizlenen"] == 14
    assert "Sonuç yok" in cli("ara", "ISIK").stdout
    assert "KALDIRILDI" in cli("kaynaklar").stdout
    denied = cli("kaynak-sil", sid, ok=False, stdin=subprocess.DEVNULL)
    assert denied.returncode == 1 and "--onayla" in denied.stderr
    # stdin boş boru: EOFError traceback'i yerine anlaşılır hata
    pipe = cli("kaynak-sil", sid, ok=False, input="")
    assert pipe.returncode == 1 and "--onayla" in pipe.stderr and "Traceback" not in pipe.stderr
    assert json.loads(cli("--json", "kaynak-sil", sid, "--onayla").stdout)["silinen_kayit"] == 15
    # silinmiş dosyayı yeniden almak onay ister
    blocked = cli("ice-al", f, "--tur", "jsonl", ok=False)
    assert blocked.returncode == 1 and "kalıcı sildiniz" in blocked.stderr
    assert json.loads(cli("--json", "ice-al", f, "--tur", "jsonl", "--yine-de").stdout)["eklenen"] == 15


def test_cli_hata_mesajlari(cli, tmp_path):
    r = cli("ara", "x", ok=False)
    assert r.returncode == 1 and "bulunamadı" in r.stderr
    assert "kimlikcore" in cli("--json", "surum").stdout
    bad = tmp_path / "bozuk.jsonl"
    bad.write_text('{"ts": "2026-01-01T00:00:00Z", "kind": "k"}\n', encoding="utf-8")
    cli("baslat")
    r = cli("ice-al", bad, "--tur", "jsonl", ok=False)
    assert r.returncode == 1 and "category" in r.stderr
    r = cli("ice-al", tmp_path / "yok.jsonl", ok=False)
    assert r.returncode == 1
    r = cli("ice-al", bad, "--tur", "yok_boyle_bir_tur", ok=False)
    assert r.returncode == 1 and r.stderr.startswith("Hata:")
    # jsonl dizin kabul etmez; diğer türler dizin kabul eder (çalıştırıcıya bırakılır)
    r = cli("ice-al", tmp_path, "--tur", "jsonl", ok=False)
    assert r.returncode == 1 and "dosya ister" in r.stderr


IMPORTERS = importlib.util.find_spec("kimlikimport") is not None
FIXTURES = Path(__file__).resolve().parents[2] / "importers" / "fixtures"


@pytest.mark.skipif(not IMPORTERS, reason="kimlikimport kurulu değil")
def test_cli_ice_al_klasor_ve_otomatik_tanima(cli, tmp_path):
    cli("baslat")
    klasor = FIXTURES / "reddit"
    assert klasor.is_dir()
    a = json.loads(cli("--json", "ice-al", klasor).stdout)  # --tur yok: otomatik
    assert a["added"] > 0 and a["importer"] == "reddit"
    b = json.loads(cli("--json", "ice-al", klasor, "--tur", "auto").stdout)
    assert b["added"] == 0 and b["duplicate"] == a["parsed"] and b["source_id"] == a["source_id"]
    # kalıcı silinmiş girdi: çalıştırıcı tek yerde sorar
    cli("kaynak-sil", a["source_id"], "--onayla")
    blocked = cli("ice-al", klasor, ok=False)
    assert blocked.returncode == 1 and "kalıcı sildiniz" in blocked.stderr
    assert json.loads(cli("--json", "ice-al", klasor, "--yine-de").stdout)["added"] == a["added"]
    # tanınmayan girdi
    bos = tmp_path / "bos"
    bos.mkdir()
    r = cli("ice-al", bos, ok=False)
    assert r.returncode == 1 and "tanınmadı" in r.stderr


def test_kaynak_sil_tty_stdin_eof(monkeypatch, root, capsys):
    """Windows'ta NUL/kapalı stdin isatty()=True görünür; input() EOFError verir."""
    import io

    from kimlikcore import cli as climod
    from kimlikcore import Hub

    with Hub.open(root, write=True) as h:
        sid = h.add_source("x", "1", None)
    class FakeIn(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.setattr("sys.stdin", FakeIn(""))
    assert climod.main(["--veri", str(root), "kaynak-sil", sid]) == 1
    err = capsys.readouterr().err
    assert "--onayla" in err and "Traceback" not in err
    with Hub.open(root, write=False) as r:
        assert len(r.sources()) == 1  # silinmedi
