import json
import os
import subprocess
import sys
import time

import pytest

from kimlikcore import EventIn, Hub, HubLockedError, init_erisim_db, connect_erisim

from conftest import run_child

READER = r"""
import json, sys, time
from kimlikcore import Hub
root, secs = sys.argv[1], float(sys.argv[2])
out = {"iter": 0, "errors": [], "max_count": 0, "monotonic": True, "snapshot_stable": True,
       "write_blocked": False, "search_ok": True, "lock_file_created": False}
deadline = time.time() + secs
last = 0
while time.time() < deadline:
    try:
        h = Hub.open(root, write=False)
        c = h._conn
        c.execute("BEGIN")                      # uzun okuma işlemi (WAL anlık görüntüsü)
        n1 = c.execute("SELECT count(*) FROM events").fetchone()[0]
        time.sleep(0.05)
        n2 = c.execute("SELECT count(*) FROM events").fetchone()[0]
        if n1 != n2:
            out["snapshot_stable"] = False
        c.execute("COMMIT")
        if n1 < last:
            out["monotonic"] = False
        last = n1
        out["max_count"] = max(out["max_count"], n1)
        if n1 and not h.search("sentetik", limit=5):
            out["search_ok"] = False
        try:
            c.execute("INSERT INTO meta(key, value) VALUES ('x', 'y')")
        except Exception as e:
            out["write_blocked"] = "readonly" in str(e).lower() or "read-only" in str(e).lower()
        h.close()
        out["iter"] += 1
    except Exception as e:
        out["errors"].append(repr(e)[:200])
        time.sleep(0.05)
print(json.dumps(out))
"""


def test_wal_mode_ro_ikinci_surec_yazani_bozmaz(root, child_env):
    with Hub.open(root, write=True) as hub:
        sid = hub.add_source("sentetik", "1", None)
        hub.add_events(sid, [EventIn(event_key="seed", ts="2026-01-01T00:00:00Z", kind="x",
                                     category="notlar", text="sentetik tohum")])
        assert hub._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        p = subprocess.Popen([sys.executable, "-c", READER, str(root), "4"], env=child_env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        written = 1
        slowest = 0.0
        t_end = time.time() + 4.5
        i = 0
        while time.time() < t_end:
            batch = [EventIn(event_key=f"w{i}-{j}", ts="2026-02-01T00:00:00Z", kind="x", category="notlar",
                             text=f"sentetik yazı {i} {j}") for j in range(40)]
            t0 = time.time()
            written += hub.add_events(sid, batch).added
            slowest = max(slowest, time.time() - t0)
            i += 1
        stdout, stderr = p.communicate(timeout=60)
        assert p.returncode == 0, stderr
        res = json.loads(stdout)
        print("OKUYUCU", res, "yazilan", written, "en yavas toplu yazim", round(slowest, 3))
        assert res["errors"] == [], res
        assert res["iter"] > 5
        assert res["monotonic"] and res["snapshot_stable"] and res["search_ok"] and res["write_blocked"], res
        assert 0 < res["max_count"] <= written
        assert slowest < 3.0  # okuyucu yazanı bekletmedi
        assert hub._conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert hub._conn.execute("SELECT count(*) FROM events").fetchone()[0] == written
        assert not (root / "hub.lock").read_text() == ""  # kilit yazanın elinde duruyor
    # okuyucu kilit dosyası oluşturmaz/silmez; yazan kapanınca kilit kalkar
    assert not (root / "hub.lock").exists()


def test_ro_okuyucu_yazan_kapaliyken_de_acilir(root, child_env):
    with Hub.open(root, write=True) as hub:
        sid = hub.add_source("s", "1", None)
        hub.add_events(sid, [EventIn(event_key="a", ts="2026-01-01T00:00:00Z", kind="x", category="notlar", text="merhaba")])
    code = ("from kimlikcore import Hub; import sys; h=Hub.open(sys.argv[1], write=False); "
            "print(len(h.search('merhaba'))); h.close()")
    r = run_child(code, child_env, root)
    assert r.returncode == 0 and r.stdout.strip() == "1", r.stderr


def test_ikinci_yazan_surec_kilitli_hatasi_alir(root, child_env):
    code = ("from kimlikcore import Hub, HubLockedError; import sys\n"
            "try:\n Hub.open(sys.argv[1], write=True); print('ACILDI')\n"
            "except HubLockedError as e: print('KILITLI', e)\n")
    with Hub.open(root, write=True):
        r = run_child(code, child_env, root)
        assert r.stdout.startswith("KILITLI"), r.stdout + r.stderr
        with pytest.raises(HubLockedError):
            Hub.open(root, write=True)  # aynı süreçte de
        # CLI anlaşılır hata ve çıkış kodu 3 verir
        c = subprocess.run([sys.executable, "-m", "kimlikcore", "--veri", str(root), "baslat"],
                           env=child_env, capture_output=True, text=True)
        assert c.returncode == 3 and "başka bir süreç" in c.stderr
    with Hub.open(root, write=True):  # kapanınca kilit serbest
        pass


def test_bayat_kilit_devralinir(root, child_env):
    # Kilit alıp öldürülen gerçek bir süreç.
    code = ("from kimlikcore import Hub; import sys, time\n"
            "Hub.open(sys.argv[1], write=True); print('hazir', flush=True); time.sleep(60)\n")
    p = subprocess.Popen([sys.executable, "-c", code, str(root)], env=child_env,
                         stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "hazir"
    with pytest.raises(HubLockedError):
        Hub.open(root, write=True)  # sahibi canlı
    old = json.loads((root / "hub.lock").read_text())
    p.kill()
    p.wait()
    assert (root / "hub.lock").exists()  # SIGKILL: kilit dosyası arkada kaldı
    with Hub.open(root, write=True) as h:  # bayat kilit devralındı
        new = json.loads((root / "hub.lock").read_text())
        assert new["pid"] == os.getpid() and new["token"] != old["token"]
        assert h.summary()["counts"]["event"] == 0
    assert not list(root.glob("hub.lock*"))


def test_bozuk_ve_baska_pid_kilidi(root):
    root.mkdir()
    (root / "hub.lock").write_text('{"pid": 999999999, "host": "%s", "token": "x"}' % __import__("socket").gethostname())
    with Hub.open(root, write=True):
        pass
    (root / "hub.lock").write_text("bozuk")
    os.utime(root / "hub.lock", (time.time() - 60, time.time() - 60))
    with Hub.open(root, write=True):
        pass
    (root / "hub.lock").write_text('{"pid": 1, "host": "baska-bilgisayar", "token": "x"}')
    with pytest.raises(HubLockedError):
        Hub.open(root, write=True)  # başka bilgisayarın kilidi doğrulanamaz: canlı sayılır


def test_erisim_db_bos_sema_ve_cok_surecli_yazim(root, child_env):
    with Hub.open(root, write=True):
        pass
    db = root / "erisim.db"
    assert db.exists()
    c = connect_erisim(root)
    cols = [r[1] for r in c.execute("PRAGMA table_info(access_log)")]
    assert cols == ["id", "ts", "app_id", "tool", "category", "result_count", "outcome"]
    assert c.execute("SELECT count(*) FROM access_log").fetchone()[0] == 0
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert c.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
    init_erisim_db(root)  # ikinci çağrı zararsız
    code = r"""
import sys
from kimlikcore import connect_erisim
c = connect_erisim(sys.argv[1])
for i in range(300):
    c.execute("INSERT INTO access_log(ts, app_id, tool, category, result_count, outcome) VALUES (?,?,?,?,?,?)",
              ("2026-01-01T00:00:00Z", sys.argv[2], "ara", "notlar", 1, "ok"))
print("tamam")
"""
    procs = [subprocess.Popen([sys.executable, "-c", code, str(root), f"app{i}"], env=child_env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(4)]
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0 and out.strip() == "tamam", err
    assert c.execute("SELECT count(*) FROM access_log").fetchone()[0] == 1200
    with pytest.raises(Exception):
        c.execute("INSERT INTO access_log(ts, app_id, tool, outcome) VALUES ('t','a','t','belirsiz')")
    c.close()
