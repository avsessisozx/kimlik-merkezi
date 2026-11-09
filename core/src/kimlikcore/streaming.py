"""Akışla okuma yardımcıları: dosyanın tamamı asla belleğe alınmaz."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

from .errors import FormatError
from .models import EventIn

CHUNK = 1024 * 1024
MAX_LINE_BYTES = 64 * 1024 * 1024  # tek satır sınırı; aşılırsa FormatError


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def iter_lines(path: Path | str, *, max_line: int = MAX_LINE_BYTES) -> Iterator[tuple[int, bytes]]:
    """(satır_no, ham_bayt) üretir; boş satırlar atlanır. Tek satır en çok `max_line` bayt."""
    with open(path, "rb") as f:
        n = 0
        while True:
            line = f.readline(max_line + 1)
            if not line:
                return
            n += 1
            if len(line) > max_line and not line.endswith(b"\n"):
                raise FormatError(f"{n}. satır {max_line} bayttan uzun.")
            if line.strip():
                yield n, line


def iter_event_jsonl(path: Path | str) -> Iterator[EventIn]:
    """Dahili 'jsonl' türü: her satır bir EventIn nesnesi.

    Alanlar: ts, kind, category (zorunlu); payload, text, device_id, event_key (isteğe bağlı).
    Hata iletisinde kayıt içeriği yer almaz, yalnız satır numarası.
    """
    allowed = {"ts", "kind", "category", "payload", "text", "device_id", "event_key"}
    for n, line in iter_lines(path):
        try:
            obj = json.loads(line)
        except ValueError as e:
            raise FormatError(f"{n}. satır geçerli JSON değil.") from e
        if not isinstance(obj, dict):
            raise FormatError(f"{n}. satır bir nesne değil.")
        extra = set(obj) - allowed
        if extra:
            raise FormatError(f"{n}. satırda bilinmeyen alanlar: {', '.join(sorted(extra))}")
        for req in ("ts", "kind", "category"):
            if req not in obj:
                raise FormatError(f"{n}. satırda '{req}' alanı yok.")
        yield EventIn(**obj)
