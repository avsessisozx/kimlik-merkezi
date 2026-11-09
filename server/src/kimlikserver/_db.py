"""Hub'ın bağlantısına tek noktadan erişim.

Çekirdek (kimlikcore) persona/anahtar/izin tabloları için genel bir API sunmuyor; bu modül
`Hub._conn/_tx/_mutex` özel üyelerine bağımlılığı tek yerde toplar (bkz. durum/server.md,
Müdüre istekler: genel bir `Hub.transaction()` / `Hub.read()` istenmiştir).
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable

from kimlikcore import Hub, HubReadOnlyError

Clock = Callable[[], datetime]
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(TS_FORMAT)


@contextmanager
def read(hub: Hub) -> Iterator:
    with hub._mutex:
        yield hub._conn


@contextmanager
def write_tx(hub: Hub) -> Iterator:
    if not hub.writable:
        raise HubReadOnlyError("Hub salt okunur açıldı; yazma işlemi yapılamaz.")
    with hub._mutex:
        with hub._tx() as c:
            yield c
