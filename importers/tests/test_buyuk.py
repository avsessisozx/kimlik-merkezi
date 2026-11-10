"""~1 GiB sentetik Takeout zip'i bellek şişmeden içe alınıyor mu (pytest -m buyuk).

Zip içindeki watch-history.json 1 GiB'ı aşar (sıkıştırılmış zip küçüktür). Çalıştırıcı zip'i diske
açmadan akışla okur. Tepe bellek alt sürecin ru_maxrss değeriyle ölçülür.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
import zipfile
from datetime import UTC, datetime, timedelta

import pytest

TARGET_BYTES = 1024 * 1024 * 1024  # 1 GiB (sıkıştırılmamış JSON)
MAX_RSS_MB = 300
BASE = datetime(2020, 1, 1, tzinfo=UTC)


def _record(i: int) -> str:
    t = (BASE + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
    vid = f"{i:011d}"
    pad = "sentetik baslik " * 30  # kayıt ~900 bayt
    title = f"Watched {pad}{i}" + (" hedefkayit777zz" if i == 12345 else "")
    return json.dumps({
        "header": "YouTube", "title": title, "titleUrl": f"https://www.youtube.com/watch?v={vid}",
        "subtitles": [{"name": f"Kanal {i % 1000}", "url": f"https://www.youtube.com/channel/UC{i % 1000:022d}"}],
        "time": t, "products": ["YouTube"], "activityControls": ["YouTube watch history"],
    }, ensure_ascii=False)


def make_big_zip(path, target=TARGET_BYTES) -> tuple[int, int]:
    n = size = 0
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        with zf.open("Takeout/YouTube and YouTube Music/history/watch-history.json", "w",
                     force_zip64=True) as f:
            f.write(b"[\n")
            size += 2
            buf: list[str] = []
            while size < target:
                buf.append(("," if n else "") + _record(n))
                n += 1
                if len(buf) >= 2000:
                    data = "\n".join(buf).encode()
                    f.write(data + b"\n")
                    size += len(data) + 1
                    buf.clear()
            if buf:
                data = "\n".join(buf).encode()
                f.write(data + b"\n")
                size += len(data) + 1
            f.write(b"]\n")
            size += 2
    return n, size


CHILD = textwrap.dedent("""
    import resource, sys, json, time
    from pathlib import Path
    from kimlikcore import Hub
    from kimlikimport.run import run
    zip_path, veri = sys.argv[1], sys.argv[2]
    t = time.time()
    with Hub.open(Path(veri), write=True) as hub:
        r = run(hub, Path(zip_path))
        found = len(hub.search("hedefkayit777zz"))
    print(json.dumps({"parsed": r.parsed, "added": r.added, "dup": r.duplicate, "found": found,
                      "sn": round(time.time() - t, 1),
                      "rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}))
""")


@pytest.mark.buyuk
def test_1gib_zip_bellek(tmp_path):
    z = tmp_path / "buyuk.zip"
    t0 = time.time()
    n, size = make_big_zip(z)
    print(f"\nüretim: {n} kayıt, {size / 2**30:.2f} GiB JSON, zip {z.stat().st_size / 2**20:.0f} MiB, "
          f"{time.time() - t0:.0f} sn")
    assert size >= TARGET_BYTES
    out = subprocess.run([sys.executable, "-c", CHILD, str(z), str(tmp_path / "veri")],
                         capture_output=True, encoding="utf-8", timeout=7200,
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert out.returncode == 0, out.stderr[-2000:]
    res = json.loads(out.stdout.strip().splitlines()[-1])
    print("sonuç:", res)
    assert res["parsed"] == n and res["added"] == n and res["dup"] == 0
    assert res["found"] == 1
    assert res["rss_mb"] < MAX_RSS_MB, res


# ---------------------------------------------------------------- Gmail MBOX (Takeout zip içinde)
def _mbox_message(i: int) -> str:
    t = BASE + timedelta(seconds=i * 7)
    body = ("Sentetik ileti govdesi, satir icerigi. " * 40 + "\n") * 3
    if i == 4321:
        body += "hedefmbox777zz\n"
    att = "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=" * 2 + "\n"
    return (
        f"From {i}@xxx {t.strftime('%a %b %d %H:%M:%S +0000 %Y')}\n"
        f"X-Gmail-Labels: Inbox,Etiket{i % 50}\nDate: {t.strftime('%a, %d %b %Y %H:%M:%S +0000')}\n"
        f"From: gonderen{i % 500}@example.test\nTo: ben@example.test\nSubject: Sentetik konu {i}\n"
        f"Message-ID: <m{i}@example.test>\nMIME-Version: 1.0\n"
        'Content-Type: multipart/mixed; boundary="bb"\n\n--bb\nContent-Type: text/plain; charset=UTF-8\n\n'
        f"{body}\n--bb\nContent-Type: application/octet-stream; name=\"a.bin\"\n"
        'Content-Disposition: attachment; filename="a.bin"\nContent-Transfer-Encoding: base64\n\n'
        + att * 30 + "--bb--\n\n"
    )


def make_big_mbox_zip(path, target=TARGET_BYTES) -> tuple[int, int]:
    n = size = 0
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        with zf.open("Takeout/Mail/All mail Including Spam and Trash.mbox", "w", force_zip64=True) as f:
            while size < target:
                data = "".join(_mbox_message(n + k) for k in range(500)).encode()
                f.write(data)
                n += 500
                size += len(data)
    return n, size


@pytest.mark.buyuk
def test_1gib_mbox_bellek(tmp_path):
    z = tmp_path / "mbox.zip"
    t0 = time.time()
    n, size = make_big_mbox_zip(z)
    print(f"\nüretim: {n} ileti, {size / 2**30:.2f} GiB mbox, zip {z.stat().st_size / 2**20:.0f} MiB, "
          f"{time.time() - t0:.0f} sn")
    assert size >= TARGET_BYTES
    child = CHILD.replace("hedefkayit777zz", "hedefmbox777zz")
    out = subprocess.run([sys.executable, "-c", child, str(z), str(tmp_path / "veri")],
                         capture_output=True, encoding="utf-8", timeout=7200,
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert out.returncode == 0, out.stderr[-2000:]
    res = json.loads(out.stdout.strip().splitlines()[-1])
    print("sonuç:", res)
    assert res["parsed"] == n and res["added"] == n and res["dup"] == 0 and res["found"] == 1
    assert res["rss_mb"] < MAX_RSS_MB, res
