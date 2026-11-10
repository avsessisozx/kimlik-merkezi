from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from kimlikcore import Hub

# Çekirdek `sohbet` kategorisini henüz tanımıyorsa (INTERFACES isteği bekliyor) testlerde taklit et.
from kimlikcore import Category  # noqa: E402

if "sohbet" not in Category.ALL:
    Category.ALL = frozenset(Category.ALL | {"sohbet"})
    Category.SENSITIVE = frozenset(Category.SENSITIVE | {"sohbet"})

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def make_zip(src_dir: Path, out: Path, *, strip: str | None = None) -> Path:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src_dir.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(src_dir).as_posix())
    return out


@pytest.fixture
def hub(tmp_path):
    h = Hub.open(tmp_path / "veri", write=True)
    yield h
    h.close()


@pytest.fixture
def fix():
    return FIX


@pytest.fixture
def zipper(tmp_path):
    def _z(name: str) -> Path:
        return make_zip(FIX / name, tmp_path / f"{name}.zip")

    return _z


def count_events(hub: Hub, **kw) -> int:
    return len(hub.timeline(limit=1_000_000, **kw))


# Ağ koruması (kök ag_koruma.py): paket klasöründen tek başına koşulsa da devrede olsun.
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
from ag_koruma import ag_korumasi, pytest_configure, pytest_unconfigure  # noqa: E402,F401
