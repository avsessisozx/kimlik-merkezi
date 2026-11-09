"""hub.lock: yazan süreç için kilit dosyası; bayat kilit güvenle devralınır."""
from __future__ import annotations

import json
import os
import socket
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .errors import HubLockedError


def _proc_start(pid: int) -> str | None:
    """Linux'ta sürecin başlangıç zamanı (pid yeniden kullanımını yakalamak için)."""
    try:
        data = Path(f"/proc/{pid}/stat").read_text()
        rest = data[data.rindex(")") + 2 :].split()
        return rest[19]  # starttime (22. alan)
    except (OSError, ValueError, IndexError):
        return None


def _proc_state(pid: int) -> str | None:
    try:
        data = Path(f"/proc/{pid}/stat").read_text()
        return data[data.rindex(")") + 2 :].split()[0]
    except (OSError, ValueError, IndexError):
        return None


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":  # pragma: no cover - Windows'ta bu ortamda çalıştırılmadı
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.GetLastError() == 5  # Erişim reddedildi: süreç var
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return _proc_state(pid) != "Z"  # zombi = ölü


class HubLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.token: str | None = None

    def _read(self) -> dict | None:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    @staticmethod
    def _holder_alive(info: dict) -> bool:
        if info.get("host") != socket.gethostname():
            return True  # başka bilgisayardan doğrulanamaz; canlı say
        pid = info.get("pid")
        if not isinstance(pid, int):
            return False
        if pid == os.getpid():
            return True
        if not pid_alive(pid):
            return False
        recorded = info.get("pstart")
        if recorded is not None:
            now = _proc_start(pid)
            if now is not None and now != recorded:
                return False  # aynı pid başka süreç
        return True

    def acquire(self) -> None:
        token = uuid.uuid4().hex
        info = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "token": token,
            "pstart": _proc_start(os.getpid()),
            "started": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for _ in range(20):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                holder = self._read()
                if holder is None:
                    # Yazılmakta olan ya da bozuk dosya: kısa bekle, sonra yaşına bak.
                    time.sleep(0.1)
                    holder = self._read()
                    if holder is None:
                        try:
                            age = time.time() - self.path.stat().st_mtime
                        except FileNotFoundError:
                            continue
                        if age < 5:
                            raise HubLockedError("Veri klasörü kilitli (kilit dosyası okunamadı).")
                        holder = {}
                if holder and self._holder_alive(holder):
                    raise HubLockedError(
                        "Veri klasörünü başka bir süreç yazmak için kullanıyor "
                        f"(süreç no {holder.get('pid')}, bilgisayar {holder.get('host')}). "
                        "Önce onu kapatın."
                    )
                # Bayat kilit: atomik olarak kenara al (yalnız bir süreç başarır).
                stale = self.path.with_name(f"hub.lock.eski.{os.getpid()}.{token[:8]}")
                try:
                    os.replace(self.path, stale)
                except FileNotFoundError:
                    continue
                moved = self._read_path(stale)
                if holder and moved and moved.get("token") != holder.get("token"):
                    # Araya canlı bir kilit girmiş; geri koymayı dene.
                    try:
                        os.link(stale, self.path)
                    except OSError:
                        pass
                    stale.unlink(missing_ok=True)
                    raise HubLockedError("Veri klasörü başka bir süreç tarafından kilitlendi.")
                stale.unlink(missing_ok=True)
                continue
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(info, f)
                    f.flush()
                    os.fsync(f.fileno())
                self.token = token
                return
        raise HubLockedError("Kilit alınamadı (çok sayıda deneme).")

    @staticmethod
    def _read_path(p: Path) -> dict | None:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def release(self) -> None:
        if self.token is None:
            return
        info = self._read()
        if info and info.get("token") == self.token:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self.token = None
