# Ağ koruması (kök ag_koruma.py): paket klasöründen tek başına koşulsa da devrede olsun.
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from ag_koruma import ag_korumasi, pytest_configure, pytest_unconfigure  # noqa: E402,F401
