import pytest

from helpers import FakeClock, build_world


@pytest.fixture
def veri(tmp_path):
    root = tmp_path / "veri"
    root.mkdir()
    return root


@pytest.fixture
def world(veri):
    w = build_world(veri)
    w["root"] = veri
    return w


@pytest.fixture
def clock():
    return FakeClock()


# Ağ koruması (kök ag_koruma.py): paket klasöründen tek başına koşulsa da devrede olsun.
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
from ag_koruma import ag_korumasi, pytest_configure, pytest_unconfigure  # noqa: E402,F401
