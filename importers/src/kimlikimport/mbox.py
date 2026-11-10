"""Gmail MBOX (Takeout) akışla okuma. Tüm dosya belleğe alınmaz: ileti ileti işlenir.

Ekler İÇE ALINMAZ (yalnız ad/tür/boyut kaydı); yalnız başlıklar ve metin gövdesi. Tek iletinin
okunan kısmı `MAX_MESSAGE_BYTES` ile sınırlıdır (aşan kısım atılır ve payload'da işaretlenir).
Biçim: mbox/mboxrd ("From " ayırıcı satırı; Gmail iletileri `X-Gmail-Labels` başlığı taşır).
"""
from __future__ import annotations

import email
import email.policy
import re
from collections.abc import Iterator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import IO

from kimlikcore import Category, EventIn

from .base import iso_utc, stable_key

MAX_MESSAGE_BYTES = 32 * 1024 * 1024
MAX_LINE = 1024 * 1024
TEXT_FOR_SEARCH = 20_000
BODY_IN_PAYLOAD = 50_000


def iter_raw_messages(f: IO[bytes], cap: int = MAX_MESSAGE_BYTES) -> Iterator[tuple[bytes, bytes, bool]]:
    """(From_ satırı, ham ileti baytları, kesildi mi) üretir."""
    from_line: bytes | None = None
    buf: list[bytes] = []
    size = 0
    truncated = False
    prev_blank = True
    at_line_start = True
    while True:
        line = f.readline(MAX_LINE)
        if not line:
            break
        is_sep = at_line_start and prev_blank and line.startswith(b"From ")
        if is_sep:
            if from_line is not None:
                yield from_line, b"".join(buf), truncated
            from_line, buf, size, truncated = line, [], 0, False
            prev_blank = False
            at_line_start = True
            continue
        if from_line is None:
            # ilk "From " satırından önceki içerik: mbox değil
            from_line = b""
        if size < cap:
            buf.append(line)
            size += len(line)
        else:
            truncated = True
        at_line_start = line.endswith(b"\n")
        if at_line_start:
            prev_blank = line in (b"\n", b"\r\n")
    if from_line is not None and (buf or from_line):
        yield from_line, b"".join(buf), truncated


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    try:
        p.feed(html)
        p.close()
    except Exception:  # bozuk HTML: elde edileni al
        pass
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


def _part_text(part) -> str:
    try:
        return part.get_content()
    except Exception:  # bilinmeyen karakter kümesi vb.
        raw = part.get_payload(decode=True) or b""
        return raw.decode("utf-8", "replace")


def _body_and_attachments(msg) -> tuple[str, list[dict]]:
    text = ""
    atts: list[dict] = []
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is not None:
        t = _part_text(body)
        text = html_to_text(t) if body.get_content_type() == "text/html" else t
    for p in msg.iter_attachments():
        try:
            payload = p.get_payload(decode=True)
            size = len(payload) if payload is not None else 0
        except Exception:
            size = 0
        atts.append({"ad": p.get_filename(), "tur": p.get_content_type(), "boyut": size})
    return text.strip(), atts


def _hdr(msg, name: str) -> str:
    try:
        v = msg[name]
        return str(v).strip() if v is not None else ""
    except Exception:  # bozuk başlık
        raw = msg.get(name)
        return str(raw)[:500] if raw else ""


def _date(msg, from_line: bytes) -> str | None:
    d = _hdr(msg, "Date")
    if d:
        try:
            dt = parsedate_to_datetime(d)
            return iso_utc(dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
        except (TypeError, ValueError, IndexError):
            pass
    tail = from_line.decode("ascii", "replace").strip().split(None, 2)
    if len(tail) == 3:
        for fmt in ("%a %b %d %H:%M:%S %z %Y", "%a %b %d %H:%M:%S %Y"):
            try:
                return iso_utc(datetime.strptime(tail[2], fmt))
            except ValueError:
                continue
    return None


def message_event(from_line: bytes, raw: bytes, truncated: bool) -> EventIn | None:
    """Tek iletiden olay; tarih çözülemezse None (çağıran sayar)."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    ts = _date(msg, from_line)
    if ts is None:
        return None
    subject, sender = _hdr(msg, "Subject"), _hdr(msg, "From")
    mid = _hdr(msg, "Message-ID")
    try:
        text, atts = _body_and_attachments(msg)
    except Exception:
        text, atts = "", []
    labels = [x.strip() for x in _hdr(msg, "X-Gmail-Labels").split(",") if x.strip()]
    payload = {
        "konu": subject, "kimden": sender, "kime": _hdr(msg, "To"), "kopya": _hdr(msg, "Cc"),
        "ileti_kimligi": mid, "etiketler": labels, "konusma_kimligi": _hdr(msg, "X-GM-THRID"),
        "govde": text[:BODY_IN_PAYLOAD], "ekler": atts,
    }
    if truncated:
        payload["kesildi"] = True
    if len(text) > BODY_IN_PAYLOAD:
        payload["govde_kesildi"] = True
    key = stable_key("gm", mid) if mid else stable_key("gm", ts, sender, subject)
    return EventIn(
        ts=ts, kind="gmail.ileti", category=Category.EPOSTA, payload=payload, event_key=key,
        text=f"{subject}\n{sender}\n{text[:TEXT_FOR_SEARCH]}".strip(),
    )
