"""Persona (INTERFACES §5): bilgi ekleme, süre dolumu, çelişki yönetimi, kimlik kartı.

Okuma (`PersonaReader`) salt okunur Hub ile de çalışır (MCP); yazma (`Persona`) yazan Hub ister.

Kararlar (durum/server.md'de de yazılı):
- Çelişki: aynı `category` + `fact_key`, farklı metin. İkisi de saklanır; yenisi canlı kalır,
  eskisi `eskimis` olur (yapay zekâya verilmez) ve `contradictions` satırı açılır. Kullanıcı
  `resolve_contradiction` ile seçeneği değiştirebilir. `fact_key` verilmezse çelişki aranmaz.
- Kimlik kartı ve MCP çıktısı yalnız `beyan_edilen` + `dosyadan_alinan`, `hidden=0`,
  süresi dolmamış ve (varsa) kaynağı kaldırılmamış bilgileri içerir. Süre kontrolü okurken de
  yapılır; `check_expiry` ise durumu `eskimis`e çevirip kalıcı yazar (uygulama açılışında).
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from kimlikcore import FormatError, Hub, NotFoundError, norm_ts

from ._db import Clock, iso, read, utc_now, write_tx

LIVE_STATUSES = ("beyan_edilen", "dosyadan_alinan")
# Kart ve çıktılarda sabit sıra ve başlıklar.
FACT_CATEGORIES = ("kimlik", "tercihler", "ilgi", "cihazlar", "projeler", "is", "diger")
CATEGORY_TITLES = {
    "kimlik": "Kimlik",
    "tercihler": "Tercihler",
    "ilgi": "İlgi alanları",
    "cihazlar": "Cihazlar",
    "projeler": "Projeler",
    "is": "İş",
    "diger": "Diğer",
}
DEFAULT_EXPIRY_DAYS = 180
DEFAULT_EXPIRING = {"cihazlar": DEFAULT_EXPIRY_DAYS, "projeler": DEFAULT_EXPIRY_DAYS,
                    "is": DEFAULT_EXPIRY_DAYS}
MAX_STATEMENT = 2000

_COLS = ("fact_id, statement, source_id, date, status, valid_from, valid_until, category, "
         "fact_key, hidden, updated")
_UNSET = object()


@dataclass(frozen=True, slots=True)
class Fact:
    fact_id: str
    statement: str
    source_id: str | None
    date: str
    status: str
    valid_from: str | None
    valid_until: str | None
    category: str
    fact_key: str | None
    hidden: bool
    updated: str | None


@dataclass(frozen=True, slots=True)
class Contradiction:
    contradiction_id: str
    category: str
    fact_key: str | None
    opened: str
    resolved_at: str | None
    chosen_fact_id: str | None
    old_fact: Fact
    new_fact: Fact


def _fact(r: tuple) -> Fact:
    return Fact(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], bool(r[9]), r[10])


def _check_category(category: str) -> str:
    if category not in FACT_CATEGORIES:
        raise FormatError(f"Bilinmeyen persona kategorisi: {category!r}")
    return category


def _clean_statement(s: str) -> str:
    if not isinstance(s, str):
        raise FormatError("Bilgi metin olmalı.")
    s = s.strip()
    if not s:
        raise FormatError("Bilgi metni boş olamaz.")
    if len(s) > MAX_STATEMENT:
        raise FormatError(f"Bilgi metni en çok {MAX_STATEMENT} karakter olabilir.")
    return s


def _line(s: str) -> str:
    """Kartta tek satır: satır sonlarını boşluğa çevirir."""
    return re.sub(r"\s*[\r\n]+\s*", " ", s).strip()


class PersonaReader:
    """Salt okuma: canlı bilgiler, çelişkiler, kimlik kartı."""

    def __init__(self, hub: Hub, *, clock: Clock = utc_now):
        self.hub = hub
        self._clock = clock

    def _now(self) -> str:
        return iso(self._clock())

    # ---------------------------------------------------------------- okuma
    def get_fact(self, fact_id: str) -> Fact:
        with read(self.hub) as c:
            r = c.execute(f"SELECT {_COLS} FROM facts WHERE fact_id = ?", (fact_id,)).fetchone()
        if r is None:
            raise NotFoundError(f"Bilgi yok: {fact_id}")
        return _fact(r)

    def list_facts(self, categories: Iterable[str] | None = None, *,
                   include_inactive: bool = False) -> list[Fact]:
        """`include_inactive=False` (varsayılan): yalnız yapay zekâya verilebilenler
        (beyan_edilen + dosyadan_alinan, gizli değil, süresi dolmamış, kaynağı kaldırılmamış).
        True: gizli olmayan her şey (Persona ekranı için; `cikarilan`/`eskimis` dahil)."""
        cats = None if categories is None else [_check_category(c) for c in categories]
        sql = f"SELECT {', '.join('f.' + c.strip() for c in _COLS.split(','))} FROM facts f "
        sql += "LEFT JOIN sources s ON s.source_id = f.source_id WHERE f.hidden = 0"
        args: list = []
        if not include_inactive:
            sql += (" AND f.status IN ('beyan_edilen', 'dosyadan_alinan')"
                    " AND (f.valid_until IS NULL OR f.valid_until > ?)"
                    " AND (f.source_id IS NULL OR s.removed_at IS NULL)")
            args.append(self._now())
        if cats is not None:
            if not cats:
                return []
            sql += f" AND f.category IN ({','.join('?' * len(cats))})"
            args += cats
        sql += " ORDER BY f.date DESC, f.fact_id"
        with read(self.hub) as c:
            facts = [_fact(r) for r in c.execute(sql, args).fetchall()]
        order = {k: i for i, k in enumerate(FACT_CATEGORIES)}
        facts.sort(key=lambda f: order[f.category])  # sıralama kararlı: tarih yeniden eskiye kalır
        return facts

    def source_label(self, source_id: str | None) -> str | None:
        """Kaynak adı: `tür: dosya adı` (ham dosya varsa), yoksa yalnız tür."""
        if source_id is None:
            return None
        with read(self.hub) as c:
            s = c.execute("SELECT kind FROM sources WHERE source_id = ?", (source_id,)).fetchone()
            if s is None:
                return None
            f = c.execute("SELECT name FROM raw_files WHERE source_id = ? "
                          "ORDER BY stored_at, raw_id LIMIT 1", (source_id,)).fetchone()
        return f"{s[0]}: {f[0]}" if f else s[0]

    def list_contradictions(self, *, open_only: bool = True) -> list[Contradiction]:
        sql = ("SELECT contradiction_id, old_fact_id, new_fact_id, category, fact_key, opened, "
               "resolved_at, chosen_fact_id FROM contradictions")
        if open_only:
            sql += " WHERE resolved_at IS NULL"
        sql += " ORDER BY opened, contradiction_id"
        with read(self.hub) as c:
            rows = c.execute(sql).fetchall()
        return [Contradiction(r[0], r[3], r[4], r[5], r[6], r[7],
                              self.get_fact(r[1]), self.get_fact(r[2])) for r in rows]

    # ---------------------------------------------------------------- kimlik kartı
    def export_identity_card(self, categories: Iterable[str] | None = None) -> str:
        """Düz Markdown kimlik kartı. `categories=None`: tüm persona kategorileri.
        Yalnız beyan_edilen + dosyadan_alinan; `cikarilan` ve `eskimis` hiçbir koşulda girmez."""
        cats = list(FACT_CATEGORIES) if categories is None else list(categories)
        facts = self.list_facts(cats)
        by_cat: dict[str, list[Fact]] = {}
        for f in facts:
            by_cat.setdefault(f.category, []).append(f)
        labels: dict[str, str | None] = {}
        out = ["# Kimlik Kartı", "", f"Oluşturulma: {self._now()}", ""]
        for cat in FACT_CATEGORIES:
            items = by_cat.get(cat)
            if not items:
                continue
            out += [f"## {CATEGORY_TITLES[cat]}", ""]
            for f in items:
                line = f"- {_line(f.statement)}"
                if f.status == "dosyadan_alinan":
                    if f.source_id not in labels:
                        labels[f.source_id] = self.source_label(f.source_id)
                    line += f" (kaynak: {_line(labels[f.source_id] or 'bilinmeyen')})"
                out.append(line)
            out.append("")
        if len(out) == 4:
            out += ["Seçilen kategorilerde bilgi yok.", ""]
        return "\n".join(out)


class Persona(PersonaReader):
    """Yazan Hub ile persona işlemleri."""

    def __init__(self, hub: Hub, *, clock: Clock = utc_now,
                 expiry_days: dict[str, int | None] | None = None):
        super().__init__(hub, clock=clock)
        self.expiry_days: dict[str, int | None] = dict(DEFAULT_EXPIRING)
        if expiry_days:
            for k, v in expiry_days.items():
                _check_category(k)
                if v is not None and v <= 0:
                    raise FormatError("Süre gün olarak pozitif olmalı (süresiz için None).")
                self.expiry_days[k] = v

    # ---------------------------------------------------------------- ekleme
    def add_fact(self, statement: str, category: str, *, fact_key: str | None = None,
                 valid_until: str | datetime | None | object = _UNSET) -> str:
        """Elle ekleme: durum `beyan_edilen`."""
        return self._add(statement, category, "beyan_edilen", None, fact_key, valid_until)

    def add_fact_from_source(self, statement: str, category: str, source_id: str, *,
                             fact_key: str | None = None,
                             valid_until: str | datetime | None | object = _UNSET) -> str:
        """Kullanıcının belgeden/arşivden işaretlediği bilgi: durum `dosyadan_alinan`."""
        if not source_id:
            raise FormatError("dosyadan_alinan bilgi için kaynak zorunlu.")
        return self._add(statement, category, "dosyadan_alinan", source_id, fact_key, valid_until)

    def _valid_until(self, category: str, now: datetime, override) -> str | None:
        if override is not _UNSET:
            return None if override is None else norm_ts(override, assume_utc=True)
        days = self.expiry_days.get(category)
        return None if days is None else iso(now + timedelta(days=days))

    def _add(self, statement, category, status, source_id, fact_key, valid_until) -> str:
        statement = _clean_statement(statement)
        _check_category(category)
        fact_key = (fact_key or "").strip() or None
        now_dt = self._clock()
        now = iso(now_dt)
        vu = self._valid_until(category, now_dt, valid_until)
        with write_tx(self.hub) as c:
            if source_id is not None:
                s = c.execute("SELECT removed_at FROM sources WHERE source_id = ?",
                              (source_id,)).fetchone()
                if s is None:
                    raise NotFoundError(f"Kaynak yok: {source_id}")
                if s[0] is not None:
                    raise FormatError("Kaldırılmış kaynağa bilgi eklenemez.")
            live = c.execute(
                f"SELECT {_COLS} FROM facts WHERE category = ? AND hidden = 0 "
                "AND status IN ('beyan_edilen', 'dosyadan_alinan') "
                "AND ((? IS NULL AND fact_key IS NULL) OR fact_key = ?)",
                (category, fact_key, fact_key)).fetchall()
            for r in live:
                if r[1] == statement:  # aynı bilgi yeniden beyan: doğrulama tazelenir
                    c.execute("UPDATE facts SET valid_from = ?, valid_until = ?, updated = ? "
                              "WHERE fact_id = ?", (now, vu, now, r[0]))
                    return r[0]
            new_id = str(uuid.uuid4())
            c.execute(
                "INSERT INTO facts(fact_id, statement, source_id, date, status, valid_from, "
                "valid_until, category, fact_key, hidden, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                (new_id, statement, source_id, now, status, now, vu, category, fact_key, now))
            if fact_key is not None:
                for r in live:
                    c.execute("UPDATE facts SET status = 'eskimis', updated = ? WHERE fact_id = ?",
                              (now, r[0]))
                    c.execute(
                        "INSERT INTO contradictions(contradiction_id, old_fact_id, new_fact_id, "
                        "category, fact_key, opened) VALUES (?, ?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), r[0], new_id, category, fact_key, now))
        return new_id

    # ---------------------------------------------------------------- değiştirme, silme
    def update_fact(self, fact_id: str, *, statement: str | None = None,
                    category: str | None = None, fact_key: str | None | object = _UNSET,
                    valid_until: str | datetime | None | object = _UNSET) -> None:
        """Canlı bir bilgiyi günceller; doğrulama tarihi (`valid_from`) tazelenir.
        `eskimis`/`cikarilan` bilgi güncellenmez (yeniden `add_fact` ile beyan edilir)."""
        now_dt = self._clock()
        now = iso(now_dt)
        with write_tx(self.hub) as c:
            r = c.execute(f"SELECT {_COLS} FROM facts WHERE fact_id = ? AND hidden = 0",
                          (fact_id,)).fetchone()
            if r is None:
                raise NotFoundError(f"Bilgi yok: {fact_id}")
            f = _fact(r)
            if f.status not in LIVE_STATUSES:
                raise FormatError(f"{f.status} durumundaki bilgi güncellenemez.")
            new_stmt = f.statement if statement is None else _clean_statement(statement)
            new_cat = f.category if category is None else _check_category(category)
            new_key = f.fact_key if fact_key is _UNSET else ((fact_key or "").strip() or None)
            vu = self._valid_until(new_cat, now_dt, valid_until)  # varsayılan: süre yeniden başlar
            c.execute("UPDATE facts SET statement = ?, category = ?, fact_key = ?, valid_from = ?, "
                      "valid_until = ?, updated = ? WHERE fact_id = ?",
                      (new_stmt, new_cat, new_key, now, vu, now, fact_id))

    def delete_fact(self, fact_id: str) -> None:
        """Gizleme: satır silinmez, hiçbir çıktıda görünmez."""
        now = self._now()
        with write_tx(self.hub) as c:
            if c.execute("SELECT 1 FROM facts WHERE fact_id = ?", (fact_id,)).fetchone() is None:
                raise NotFoundError(f"Bilgi yok: {fact_id}")
            c.execute("UPDATE facts SET hidden = 1, updated = ? WHERE fact_id = ?", (now, fact_id))

    # ---------------------------------------------------------------- süre dolumu
    def check_expiry(self, now: str | datetime | None = None) -> int:
        """Süresi dolan canlı bilgileri `eskimis` yapar; sayıyı döner. Açılışta çağrılır."""
        cutoff = self._now() if now is None else norm_ts(now, assume_utc=True)
        with write_tx(self.hub) as c:
            cur = c.execute(
                "UPDATE facts SET status = 'eskimis', updated = ? WHERE hidden = 0 "
                "AND status IN ('beyan_edilen', 'dosyadan_alinan') "
                "AND valid_until IS NOT NULL AND valid_until <= ?", (cutoff, cutoff))
            return cur.rowcount

    # ---------------------------------------------------------------- çelişki çözümü
    def resolve_contradiction(self, chosen_id: str) -> int:
        """Kullanıcı `chosen_id`'yi geçerli seçer: o canlı olur (kaynağı varsa
        `dosyadan_alinan`, yoksa `beyan_edilen`), aynı kategori+anahtardaki diğerleri
        `eskimis` kalır; ilgili açık çelişki satırları kapanır. Kapanan satır sayısını döner."""
        now = self._now()
        with write_tx(self.hub) as c:
            row = c.execute(
                "SELECT category, fact_key FROM contradictions WHERE resolved_at IS NULL "
                "AND (old_fact_id = ? OR new_fact_id = ?) LIMIT 1", (chosen_id, chosen_id)).fetchone()
            if row is None:
                raise NotFoundError("Bu bilgi için açık çelişki yok.")
            chosen = c.execute("SELECT source_id, hidden FROM facts WHERE fact_id = ?",
                               (chosen_id,)).fetchone()
            if chosen is None or chosen[1]:
                raise NotFoundError(f"Bilgi yok: {chosen_id}")
            rows = c.execute(
                "SELECT contradiction_id, old_fact_id, new_fact_id FROM contradictions "
                "WHERE resolved_at IS NULL AND category = ? AND "
                "((? IS NULL AND fact_key IS NULL) OR fact_key = ?)",
                (row[0], row[1], row[1])).fetchall()
            involved = {chosen_id}
            for _, o, n in rows:
                involved.update((o, n))
            for fid in involved - {chosen_id}:
                c.execute("UPDATE facts SET status = 'eskimis', updated = ? WHERE fact_id = ?",
                          (now, fid))
            c.execute("UPDATE facts SET status = ?, updated = ? WHERE fact_id = ?",
                      ("dosyadan_alinan" if chosen[0] else "beyan_edilen", now, chosen_id))
            for cid, _, _ in rows:
                c.execute("UPDATE contradictions SET resolved_at = ?, chosen_fact_id = ? "
                          "WHERE contradiction_id = ?", (now, chosen_id, cid))
            return len(rows)
