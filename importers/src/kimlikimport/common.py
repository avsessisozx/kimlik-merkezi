"""Birden çok içe aktarıcının paylaştığı olay üreticileri."""
from __future__ import annotations

from collections.abc import Iterator

from kimlikcore import Category, EventIn

from .base import has_coordinates, stable_key


def chrome_visit_events(
    *, kind: str, ts: str, unix_usec: int, url: str, title: str, transition, key_browser: str = "chrome"
) -> Iterator[EventIn]:
    """Chromium ziyaret kaydı. Anahtar Takeout'un Chrome kaydıyla AYNI: aynı ziyaret hem Takeout'tan
    hem yerel geçmişten gelirse tekrar sayılmaz. URL'de koordinat varsa ayrı `konum` olayı."""
    key = stable_key("gt", key_browser, int(unix_usec), url)
    if has_coordinates(url):
        yield EventIn(
            ts=ts, kind=kind, category=Category.TARAMA, event_key=key,
            payload={"baslik": title, "gecis": transition, "url": None, "url_konum_ayrildi": True},
            text=title,
        )
        yield EventIn(
            ts=ts, kind="google.konum", category=Category.KONUM, event_key=key + ":konum",
            payload={"kaynak": key_browser, "url": url, "baslik": title}, text=title,
        )
    else:
        yield EventIn(
            ts=ts, kind=kind, category=Category.TARAMA, event_key=key,
            payload={"baslik": title, "url": url, "gecis": transition},
            text=f"{title} {url}".strip(),
        )
