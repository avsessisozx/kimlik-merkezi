"""Veri sınıfları ve sabitler (INTERFACES §2, §3)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


class Category:
    """Kategori kimlikleri (izin birimi)."""

    TARAMA = "tarama"
    VIDEO = "video"
    SOSYAL = "sosyal"
    MUZIK = "muzik"
    KOD = "kod"
    NOTLAR = "notlar"
    DOSYALAR = "dosyalar"
    MEDYA_META = "medya_meta"
    UYGULAMA = "uygulama"
    PERSONA = "persona"
    EPOSTA = "eposta"
    MESAJ = "mesaj"
    KONUM = "konum"

    SENSITIVE = frozenset({"eposta", "mesaj", "konum"})
    ALL = frozenset(
        {
            "tarama", "video", "sosyal", "muzik", "kod", "notlar", "dosyalar",
            "medya_meta", "uygulama", "persona", "eposta", "mesaj", "konum",
        }
    )


class FactStatus:
    BEYAN_EDILEN = "beyan_edilen"
    DOSYADAN_ALINAN = "dosyadan_alinan"
    CIKARILAN = "cikarilan"
    ESKIMIS = "eskimis"
    ALL = frozenset({"beyan_edilen", "dosyadan_alinan", "cikarilan", "eskimis"})


FACT_CATEGORIES_EXPIRING = ("cihazlar", "projeler", "is")
FACT_CATEGORIES_PERMANENT = ("kimlik", "tercihler", "ilgi", "diger")


@dataclass(frozen=True, slots=True, kw_only=True)
class EventIn:
    ts: str | datetime
    kind: str
    category: str
    payload: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    device_id: str | None = None
    event_key: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Event(EventIn):
    event_id: str
    source_id: str
    schema_version: int
    hidden: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RawFile:
    raw_id: str
    source_id: str
    name: str
    path: str  # veri klasörüne göre, '/' ayraçlı: arsiv/<sha256>/<ad>
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class Source:
    source_id: str
    kind: str
    version: str
    file_sha256: str | None
    imported_at: str
    removed_at: str | None
    removed_reason: str | None
    event_count: int = 0


@dataclass(frozen=True, slots=True)
class AddResult:
    added: int
    duplicate: int


@dataclass(frozen=True, slots=True)
class PurgeResult:
    source_id: str
    source_kind: str
    events_deleted: int
    raw_files_deleted: int
    hashes: tuple[str, ...]
    facts_demoted: int


@dataclass(frozen=True, slots=True)
class PurgedInfo:
    tombstone_id: str
    source_kind: str | None
    purged_at: str
    count: int
    file_sha256: str | None


@dataclass(frozen=True, slots=True)
class ExportResult:
    path: str
    counts: dict[str, int]
    bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ImportResult:
    counts: dict[str, int]
    raw_missing: int
    verified: bool
