"""Içe aktarıcı kayıt defteri: ad -> fabrika. Yeni kaynak eklemek çekirdeği değiştirmez."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .base import Importer
from .google_takeout import factory as _takeout
from .browser import factory as _browser
from .files import factory as _files
from .github import factory as _github
from .meta import factory as _meta
from .spotify import factory as _spotify
from .reddit import factory as _reddit

_REGISTRY: dict[str, Callable[[], Importer]] = {
    "google_takeout": _takeout,
    "reddit": _reddit,
    "meta": _meta,
    "github": _github,
    "spotify": _spotify,
    "browser_history": _browser,
    "computer_files": _files,
}
# CLI'de kısa takma adlar (ice-al --tur takeout)
ALIASES = {"takeout": "google_takeout", "google": "google_takeout", "instagram": "meta", "facebook": "meta",
           "tarayici": "browser_history", "dosyalar": "computer_files", "chrome": "browser_history", "firefox": "browser_history"}


def register(name: str, factory: Callable[[], Importer]) -> None:
    _REGISTRY[name] = factory


def names() -> list[str]:
    return sorted(_REGISTRY)


def create(name: str) -> Importer:
    name = ALIASES.get(name, name)
    if name not in _REGISTRY:
        raise KeyError(name)
    return _REGISTRY[name]()


def detect_best(path: Path) -> tuple[Importer | None, list[tuple[str, object]]]:
    """Tüm içe aktarıcıları dener; en yüksek güvenli eşleşmeyi döner (>= 0.5)."""
    results = []
    best, best_conf = None, 0.0
    for n in names():
        imp = create(n)
        d = imp.detect(path)
        results.append((n, d))
        if d.matches and d.confidence > best_conf:
            best, best_conf = imp, d.confidence
    if best_conf < 0.5:
        best = None
    return best, results
