"""Ortak zaman yardımcıları. Hub erişimi çekirdeğin genel API'siyle yapılır
(`Hub.transaction()`, `Hub.query()`, `Hub.query_one()`; bkz. docs/SEMA.md bölüm 9)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

Clock = Callable[[], datetime]
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(TS_FORMAT)
