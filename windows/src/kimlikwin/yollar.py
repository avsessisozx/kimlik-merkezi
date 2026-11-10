"""Uygulama klasörleri. Ortam değişkenleriyle değiştirilebilir (testler için)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _taban() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "KimlikMerkezi"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "kimlikmerkezi"


def ayar_dizini() -> Path:
    """Ayar dosyası, günlük, çalışan-süreç bilgisi. Veri klasöründen AYRIDIR."""
    env = os.environ.get("KIMLIK_AYAR_DIZINI")
    return Path(env) if env else _taban() / "Ayar"


def varsayilan_veri_klasoru() -> Path:
    return _taban() / "Veri"
