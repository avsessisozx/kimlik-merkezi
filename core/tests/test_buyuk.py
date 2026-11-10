"""~2 GB sentetik JSONL'in bellek şişmeden alınması. Varsayılan çalıştırmada atlanır:
    pytest -m buyuk core/tests/test_buyuk.py -s
Boyut: KIMLIK_BUYUK_GB ortam değişkeni (varsayılan 2). Disk: ~4x boyut gerekir."""
import json
import os
import random
import subprocess
import sys
import time

import pytest

pytestmark = [pytest.mark.buyuk, pytest.mark.skipif(sys.platform == "win32", reason="resource modülü yok")]

INGEST = r"""
import json, resource, sys, time
from pathlib import Path
from kimlikcore import Hub, sha256_file
from kimlikcore.streaming import iter_event_jsonl
root, src = sys.argv[1], Path(sys.argv[2])
t0 = time.time()
with Hub.open(root, write=True) as hub:
    sha = sha256_file(src)
    t1 = time.time()
    sid = hub.add_source("buyuk-sentetik", "1", sha)
    raw = hub.store_raw(sid, src)
    t2 = time.time()
    res = hub.add_events(sid, iter_event_jsonl(src))
    t3 = time.time()
    hit = [e.event_key for e in hub.search("hedefkayit777zz")]
    cnt = hub._conn.execute("SELECT count(*) FROM events").fetchone()[0]
print(json.dumps({"added": res.added, "duplicate": res.duplicate, "count": cnt, "hit": hit,
                  "raw_size": raw.size, "sha": sha,
                  "maxrss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                  "t_hash": round(t1 - t0, 1), "t_raw": round(t2 - t1, 1), "t_events": round(t3 - t2, 1)}))
"""


def generate(path, target_bytes, hedef=777):
    rnd = random.Random(42)
    vocab = ["".join(rnd.choice("abcçdefgğhıijklmnoöprsştuüvyz") for _ in range(rnd.randint(4, 9))) for _ in range(5000)]
    pool = ["".join(rnd.choice("abcdefghijklmnop0123456789") for _ in range(600)) for _ in range(64)]
    n = 0
    size = 0
    with open(path, "w", encoding="utf-8", buffering=1 << 20) as f:
        while size < target_bytes:
            words = " ".join(vocab[(n * 7 + k * 131) % 5000] for k in range(24))
            text = f"kayıt {n} {words}" + (" hedefkayit777zz" if n == hedef else "")
            line = json.dumps({"event_key": f"b-{n}", "ts": f"2026-{1 + n % 12:02d}-{1 + n % 28:02d}T{n % 24:02d}:00:00Z",
                               "kind": "sentetik.kayit", "category": "notlar",
                               "payload": {"i": n, "blob": pool[n % 64]}, "text": text}, ensure_ascii=False) + "\n"
            f.write(line)
            size += len(line.encode("utf-8"))
            n += 1
    return n


def test_buyuk_dosya_bellek_sismeden_alinir(tmp_path, child_env):
    gb = float(os.environ.get("KIMLIK_BUYUK_GB", "2"))
    src = tmp_path / "buyuk.jsonl"
    t0 = time.time()
    n = generate(src, int(gb * 1024**3))
    real = src.stat().st_size
    print(f"\nüretildi: {n} satır, {real / 1024**3:.2f} GB, {time.time() - t0:.0f} sn")
    r = subprocess.run([sys.executable, "-c", INGEST, str(tmp_path / "hub"), str(src)], env=child_env,
                       capture_output=True, encoding="utf-8", timeout=7200)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    print("SONUC", out)
    assert out["added"] == n and out["duplicate"] == 0 and out["count"] == n
    assert out["raw_size"] == real
    assert out["hit"] == ["b-777"]
    # dosya 2 GB iken süreç tepe belleği bu sınırın çok altında kalmalı (akış + 64 MB sayfa önbelleği)
    assert out["maxrss_mb"] < 300, out
