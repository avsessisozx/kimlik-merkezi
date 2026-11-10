from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from kimlikcore import Hub

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
