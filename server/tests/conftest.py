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
