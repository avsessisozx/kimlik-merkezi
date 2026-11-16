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
root, secs, ilerleme, dur = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4]
import os
out = {"iter": 0, "errors": [], "max_count": 0, "monotonic": True, "snapshot_stable": True,
       "write_blocked": False, "search_ok": True, "lock_file_created": False}
deadline = time.time() + secs
last = 0
while time.time() < deadline and not os.path.exists(dur):
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
        with open(ilerleme, "w") as f:           # hazır/ilerleme işareti: tamamlanan yineleme sayısı
            f.write(str(out["iter"]))
    except Exception as e:
        out["errors"].append(repr(e)[:200])
        time.sleep(0.05)
print(json.dumps(out))
"""


def _toplu(i, n=40):
    return [EventIn(event_key=f"w{i}-{j}", ts="2026-02-01T00:00:00Z", kind="x", category="notlar",
                    text=f"sentetik yazı {i} {j}") for j in range(n)]


def _ilerleme(path):
    try:
        return int(path.read_text() or 0)
    except (OSError, ValueError):
        return 0


def test_wal_mode_ro_ikinci_surec_yazani_bozmaz(root, child_env, tmp_path):
    # Zamanlamadan bağımsız: okuyucu hazır olunca yazılır, okuyucu yeterince yineleyene dek sürer;
    # "bekletmedi" savı okuyucusuz ölçülen taban süreye göredir.
    ilerleme, dur = tmp_path / "ilerleme", tmp_path / "dur"
    with Hub.open(root, write=True) as hub:
        sid = hub.add_source("sentetik", "1", None)
        hub.add_events(sid, [EventIn(event_key="seed", ts="2026-01-01T00:00:00Z", kind="x",
                                     category="notlar", text="sentetik tohum")])
        assert hub._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        written = 1
        i = 0
        taban = 0.0
        for _ in range(8):  # okuyucu YOKKEN taban
            t0 = time.time()
            written += hub.add_events(sid, _toplu(i)).added
            taban = max(taban, time.time() - t0)
            i += 1
        p = subprocess.Popen([sys.executable, "-c", READER, str(root), "120", str(ilerleme), str(dur)],
                             env=child_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        try:
            t_hazir = time.time() + 60
            while _ilerleme(ilerleme) < 1:  # okuyucu hazır (ilk yineleme tamam)
                assert p.poll() is None, p.communicate()[1]
                assert time.time() < t_hazir, "okuyucu hazır olmadı"
                time.sleep(0.05)
            slowest = 0.0
            toplu = 0
            t_son = time.time() + 60
            while (_ilerleme(ilerleme) < 6 or toplu < 5) and time.time() < t_son:
                t0 = time.time()
                written += hub.add_events(sid, _toplu(i)).added
                slowest = max(slowest, time.time() - t0)
                i += 1
                toplu += 1
        finally:
            dur.write_text("1")
        stdout, stderr = p.communicate(timeout=60)
        assert p.returncode == 0, stderr
        res = json.loads(stdout)
        print("OKUYUCU", res, "yazilan", written, "taban", round(taban, 3), "en yavas toplu yazim", round(slowest, 3))
        assert res["errors"] == [], res
        assert res["iter"] >= 6, res
        assert res["monotonic"] and res["snapshot_stable"] and res["search_ok"] and res["write_blocked"], res
        assert 0 < res["max_count"] <= written
        assert slowest < taban * 5 + 2.0  # okuyucu yazanı bekletmedi (göreli)
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
                           env=child_env, capture_output=True, encoding="utf-8")
        assert c.returncode == 3 and "başka bir süreç" in c.stderr
    with Hub.open(root, write=True):  # kapanınca kilit serbest
        pass


def test_bayat_kilit_devralinir(root, child_env):
    # Kilit alıp öldürülen gerçek bir süreç.
    code = ("from kimlikcore import Hub; import sys, time\n"
            "Hub.open(sys.argv[1], write=True); print('hazir', flush=True); time.sleep(60)\n")
    p = subprocess.Popen([sys.executable, "-c", code, str(root)], env=child_env,
                         stdout=subprocess.PIPE, encoding="utf-8")
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


def test_hub_artik_erisim_db_olusturmaz_eski_yardimci_calisir(root):
    with Hub.open(root, write=True):
        pass
    assert not (root / "erisim.db").exists() and not (root / "oneri.db").exists()
    # Eski dosyayı okuyabilmek için yardımcılar geriye dönük olarak duruyor.
    init_erisim_db(root)
    c = connect_erisim(root)
    try:
        cols = [r[1] for r in c.execute("PRAGMA table_info(access_log)")]
        assert cols == ["id", "ts", "app_id", "tool", "category", "result_count", "outcome"]
    finally:
        c.close()
