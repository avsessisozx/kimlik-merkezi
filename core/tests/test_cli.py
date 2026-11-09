import json
import subprocess
import sys

import pytest


@pytest.fixture
def cli(child_env, root):
    def run(*args, ok=True, veri=None, **kw):
        r = subprocess.run([sys.executable, "-m", "kimlikcore", "--veri", str(veri or root), *map(str, args)],
                           env=child_env, capture_output=True, text=True, **kw)
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
    r1 = json.loads(cli("--json", "ice-al", f).stdout)
    assert r1["eklenen"] == 15
    r2 = json.loads(cli("--json", "ice-al", f).stdout)
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
    assert json.loads(cli("--json", "kaynak-sil", sid, "--onayla").stdout)["silinen_kayit"] == 15
    # silinmiş dosyayı yeniden almak onay ister
    blocked = cli("ice-al", f, ok=False)
    assert blocked.returncode == 1 and "kalıcı sildiniz" in blocked.stderr
    assert json.loads(cli("--json", "ice-al", f, "--yine-de").stdout)["eklenen"] == 15


def test_cli_hata_mesajlari(cli, tmp_path):
    r = cli("ara", "x", ok=False)
    assert r.returncode == 1 and "bulunamadı" in r.stderr
    assert "kimlikcore" in cli("--json", "surum").stdout
    bad = tmp_path / "bozuk.jsonl"
    bad.write_text('{"ts": "2026-01-01T00:00:00Z", "kind": "k"}\n', encoding="utf-8")
    cli("baslat")
    r = cli("ice-al", bad, ok=False)
    assert r.returncode == 1 and "category" in r.stderr
    r = cli("ice-al", tmp_path / "yok.jsonl", ok=False)
    assert r.returncode == 1
    r = cli("ice-al", bad, "--tur", "google_takeout", ok=False)
    assert r.returncode == 1 and "kimlikimport" in r.stderr
