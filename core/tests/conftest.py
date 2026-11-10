import os
import sys
from pathlib import Path

import pytest

SRC = str(Path(__file__).resolve().parents[1] / "src")


@pytest.fixture(scope="session")
def child_env():
    """Alt süreçlerin kimlikcore'u bulması için ortam."""
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


@pytest.fixture
def root(tmp_path):
    return tmp_path / "hub"


@pytest.fixture
def hub(root):
    from kimlikcore import Hub

    h = Hub.open(root, write=True)
    yield h
    h.close()


def run_child(code: str, env, *args, timeout=120):
    import subprocess

    return subprocess.run(
        [sys.executable, "-c", code, *map(str, args)],
        env=env, capture_output=True, encoding="utf-8", timeout=timeout,
    )
