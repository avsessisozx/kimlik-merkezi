"""Yapay zekâ sohbet geçmişi içe aktarıcıları: ChatGPT, Claude, genel metin/Markdown/JSON.

Kategori `sohbet` (hassas kabul edilir; ayrı onay ister, "hepsini aç"a dahil değildir). Çekirdekte
henüz tanımlı değilse (kimlikcore.Category) içe aktarma, hiçbir şey yazmadan anlaşılır hata verir.
Her mesaj bir olay (`sohbet.mesaj`), her konuşma başlığı ayrı bir olay (`sohbet.konusma`).
Olay anahtarı = platform + konuşma kimliği + mesaj kimliği (dosya/arşivden bağımsız): aynı konuşma
sonraki bir dışa aktarmada tekrar gelirse tekrar sayılmaz, yalnız yeni mesajlar eklenir.

Biçim bilgisi kaynakları (DOĞRULANMADI: gerçek dışa aktarma dosyası görülmedi):
- ChatGPT `conversations.json` (`mapping`/`current_node`, `author.role`, `content.parts`,
  `metadata.model_slug`): pionxzh/chatgpt-exporter `src/api.ts` tipleri (MIT) okundu, kod kopyalanmadı.
- Claude `conversations.json` (`uuid`, `name`, `created_at`, `chat_messages[].sender/text/content`):
  idanmashaal/now2ai-claude-export-processor kaynağı (GPLv3) YALNIZ alan adları için okundu; kod
  kopyalanmadı, bağımlılık yapılmadı.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import ijson
from kimlikcore import Category, EventIn, FormatError

from .base import (
    DetectResult,
    Entry,
    FormatReport,
    Origin,
    ScanImporter,
    epoch_to_iso,
    iso_utc,
    peek,
    stable_key,
    strip_bom,
)

SOHBET = "sohbet"  # INTERFACES §2'ye eklenmesi istendi (durum/importers.md); çekirdek henüz bilmiyor olabilir
USER, ASSISTANT = "kullanici", "asistan"
MAX_TEXT = 200_000


def core_supports_sohbet() -> bool:
    return SOHBET in Category.ALL


def clean(s) -> str:
    """Tek başına yüksek/alçak vekil (surrogate) karakterleri ve NUL'u temizler."""
    if not isinstance(s, str):
        return "" if s is None else str(s)
    try:
        s.encode("utf-8")
    except UnicodeEncodeError:
        s = s.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    return s.replace("\x00", "")


def message_event(*, platform: str, conv_id: str, title: str, role: str, text: str, ts: str,
                  msg_id: str, model: str | None = None, extra: dict | None = None) -> EventIn:
    payload = {"platform": platform, "konusma_id": conv_id, "baslik": title, "rol": role, "mesaj_id": msg_id,
               "ts": ts}
    if model:
        payload["model"] = model
    if extra:
        payload.update(extra)
    return EventIn(ts=ts, kind="sohbet.mesaj", category=SOHBET, payload=payload, text=text[:MAX_TEXT],
                   event_key=stable_key("chat", platform, conv_id, msg_id))


def title_event(*, platform: str, conv_id: str, title: str, ts: str, extra: dict | None = None) -> EventIn:
    payload = {"platform": platform, "konusma_id": conv_id, "baslik": title, "ts": ts}
    if extra:
        payload.update(extra)
    return EventIn(ts=ts, kind="sohbet.konusma", category=SOHBET, payload=payload, text=title,
                   event_key=stable_key("chat", platform, conv_id, "baslik"))


def _preflight(rep: FormatReport) -> None:
    if not core_supports_sohbet():
        rep.ok = False
        rep.missing.append(
            "Çekirdek 'sohbet' kategorisini henüz tanımıyor (kimlikcore.Category'ye eklenmesi gerekir); "
            "hiçbir şey yazılmadı")


class _ConvImporter(ScanImporter):
    """JSON dizisi biçimli konuşma dosyaları için ortak iskelet (ChatGPT, Claude)."""

    platform = ""
    label = ""
    hint_keys: tuple[str, ...] = ()
    known_conv_keys: set[str] = set()

    def _do_scan(self, arc):
        files, bad, ignored = [], [], 0
        for e in arc.entries:
            if not e.name.lower().endswith(".json"):
                continue
            if not peek(e).lstrip().startswith(b"["):
                ignored += 1
                continue
            try:
                with e.open() as raw:
                    rec = next(ijson.items(strip_bom(raw), "item", use_float=True), None)
            except (ijson.JSONError, UnicodeDecodeError, OSError):
                bad.append(e.name)
                continue
            if isinstance(rec, dict) and all(k in rec for k in self.hint_keys):
                files.append(e)
            else:
                ignored += 1
        return files, bad, ignored, arc.bad_zips

    def detect(self, path: Path) -> DetectResult:
        try:
            _, (files, *_rest) = self._scan(path)
        except FormatError as e:
            return DetectResult(False, 0.0, str(e))
        if files:
            return DetectResult(True, 0.92, f"{self.label} konuşma dosyası ({len(files)})")
        return DetectResult(False, 0.0, f"{self.label} dışa aktarma dosyası bulunamadı")

    def verify_format(self, path: Path) -> FormatReport:
        _, (files, bad, ignored, bad_zips) = self._scan(path)
        rep = FormatReport(importer=self.name, ok=bool(files) and not bad and not bad_zips)
        for e in files:
            rep.found_files.append(f"{e.name} ({e.size} bayt)")
            extra: set[str] = set()
            try:
                with e.open() as raw:
                    for n, rec in enumerate(ijson.items(strip_bom(raw), "item", use_float=True)):
                        if n >= 50:
                            break
                        if isinstance(rec, dict):
                            extra |= set(rec) - self.known_conv_keys
            except (ijson.JSONError, UnicodeDecodeError):
                rep.ok = False
                rep.missing.append(f"{e.name}: JSON baştan okunamadı (bozuk)")
            rep.unexpected_fields += [f"{e.name}: {k}" for k in sorted(extra)]
        rep.missing += [f"{b}: bozuk JSON" for b in bad]
        rep.missing += [f"{b}: zip dosyası okunamadı (bozuk ya da eksik indirme)" for b in bad_zips]
        if not files:
            rep.missing.append(f"{self.label} conversations.json (konuşma dizisi) bulunamadı")
        if ignored:
            rep.notes.append(f"{ignored} JSON dosyası konuşma şekline uymadığı için yok sayıldı (kullanıcı/proje dosyaları dahil)")
        rep.notes.append("Kategori: sohbet (hassas kabul edilir, ayrı onay ister)")
        self._notes(rep)
        _preflight(rep)
        return rep

    def _notes(self, rep: FormatReport) -> None:
        pass

    def input_files(self, path: Path) -> list[Origin]:
        _, (files, *_r) = self._scan(path)
        seen: dict[Path, Origin] = {}
        for e in files:
            seen.setdefault(e.origin.path, e.origin)
        return list(seen.values())

    def parse(self, path: Path) -> Iterator[EventIn]:
        _, (files, *_r) = self._scan(path)
        for e in files:
            n = 0
            try:
                with e.open() as raw:
                    for conv in ijson.items(strip_bom(raw), "item", use_float=True):
                        n += 1
                        if isinstance(conv, dict):
                            yield from self._conversation(conv)
                        else:
                            self._skip("konuşma nesne değil")
            except (ijson.JSONError, UnicodeDecodeError) as exc:
                raise FormatError(
                    f"{e.name}: JSON {n}. konuşmadan sonra bozuk ({type(exc).__name__}). "
                    "Önceki konuşmalar eklendi; dosya düzeldikten sonra yeniden alın.") from None

    def _conversation(self, conv: dict) -> Iterator[EventIn]:  # pragma: no cover
        raise NotImplementedError


# ----------------------------------------------------------------------------------- ChatGPT
class ChatGPT(_ConvImporter):
    name = "chatgpt"
    platform = "chatgpt"
    label = "ChatGPT"
    hint_keys = ("mapping",)
    known_conv_keys = {"title", "create_time", "update_time", "mapping", "moderation_results", "current_node",
                       "conversation_id", "id", "is_archived", "safe_urls", "default_model_slug",
                       "conversation_template_id", "gizmo_id", "gizmo_type", "plugin_ids", "is_starred",
                       "voice", "async_status", "disabled_tool_ids", "is_do_not_remember",
                       "memory_scope", "context_scopes", "sugar_item_id", "sugar_item_visible",
                       "pinned_time", "is_read_only", "conversation_origin"}

    def _notes(self, rep):
        rep.notes.append("Yalnız güncel dal (current_node'dan köke) alınır; yeniden üretilen eski dallar alınmaz")
        rep.notes.append("Sistem/araç/gizli mesajlar ve metin olmayan içerik (görsel, düşünce özeti) atlanır ve sayılır")

    @staticmethod
    def _text(content) -> tuple[str, str | None]:
        """(metin, atlanan_tür). Yalnız metin parçaları; görsel/ses işaretçileri alınmaz."""
        if not isinstance(content, dict):
            return "", "içeriksiz"
        ct = content.get("content_type")
        if ct in ("text", "multimodal_text", None):
            parts = content.get("parts") or []
            t = "\n".join(p for p in parts if isinstance(p, str)).strip()
            return t, None
        if ct == "code":
            t = str(content.get("text") or "").strip()
            return (f"```\n{t}\n```" if t else ""), None
        if ct == "user_editable_context":
            return "", "kullanıcı bağlamı"
        return "", str(ct)

    def _conversation(self, conv):
        mapping = conv.get("mapping")
        if not isinstance(mapping, dict):
            self._skip("chatgpt: mapping yok")
            return
        title = clean(conv.get("title")) or "(başlıksız)"
        cid = clean(conv.get("conversation_id") or conv.get("id")) or stable_key("c", title, conv.get("create_time"))
        cts = epoch_to_iso(conv.get("create_time")) or epoch_to_iso(conv.get("update_time"))
        if cts is None:
            self._skip("chatgpt: konuşma zamanı yok")
            return
        # güncel dal: current_node -> köke, tersine çevir
        chain, seen, cur = [], set(), conv.get("current_node")
        while cur and cur in mapping and cur not in seen:
            seen.add(cur)
            chain.append(mapping[cur])
            cur = mapping[cur].get("parent")
        if not chain:  # current_node yok: kökten ilk çocuk zinciri
            chain = [n for n in mapping.values() if isinstance(n, dict)]
            chain.sort(key=lambda n: (n.get("message") or {}).get("create_time") or 0)
            self._skip("chatgpt: current_node yok, düğümler zamana göre sıralandı")
        else:
            chain.reverse()
        yield title_event(platform=self.platform, conv_id=cid, title=title, ts=cts)
        default_model = conv.get("default_model_slug")
        for node in chain:
            msg = node.get("message") if isinstance(node, dict) else None
            if not isinstance(msg, dict):
                continue
            role = ((msg.get("author") or {}).get("role"))
            meta = msg.get("metadata") or {}
            if role not in ("user", "assistant"):
                self._skip(f"chatgpt: {role or '?'} mesajı atlandı")
                continue
            if meta.get("is_visually_hidden_from_conversation"):
                self._skip("chatgpt: gizli mesaj atlandı")
                continue
            text, skipped = self._text(msg.get("content"))
            if skipped:
                self._skip(f"chatgpt: içerik türü atlandı ({skipped})")
                continue
            text = clean(text)
            if not text:
                self._skip("chatgpt: boş metin")
                continue
            ts = epoch_to_iso(msg.get("create_time")) or cts
            yield message_event(
                platform=self.platform, conv_id=cid, title=title, text=text, ts=ts,
                role=USER if role == "user" else ASSISTANT,
                msg_id=clean(msg.get("id") or node.get("id")),
                model=(meta.get("model_slug") or default_model) if role == "assistant" else None)


# ----------------------------------------------------------------------------------- Claude
class Claude(_ConvImporter):
    name = "claude"
    platform = "claude"
    label = "Claude"
    hint_keys = ("chat_messages",)
    known_conv_keys = {"uuid", "name", "summary", "created_at", "updated_at", "account", "chat_messages",
                       "model", "project_uuid", "is_starred", "settings"}

    def _notes(self, rep):
        rep.notes.append("Ek dosyaların çıkarılmış içeriği (extracted_content) alınmaz, yalnız dosya adı kaydedilir")
        rep.notes.append("Araç kullanımı/düşünme blokları atlanır; users.json ve projects.json okunmaz")

    @staticmethod
    def _text(m: dict) -> str:
        parts = []
        blocks = m.get("content")
        if isinstance(blocks, list):
            for b in blocks:
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                    parts.append(str(b["text"]))
        t = "\n".join(parts).strip()
        return t or str(m.get("text") or "").strip()

    def _conversation(self, conv):
        title = clean(conv.get("name")) or "(başlıksız)"
        cid = clean(conv.get("uuid")) or stable_key("c", title, conv.get("created_at"))
        cts = iso_utc(conv.get("created_at")) or iso_utc(conv.get("updated_at"))
        msgs = conv.get("chat_messages")
        if cts is None or not isinstance(msgs, list):
            self._skip("claude: konuşma zamanı/mesajları yok")
            return
        yield title_event(platform=self.platform, conv_id=cid, title=title, ts=cts)
        for i, m in enumerate(msgs):
            if not isinstance(m, dict):
                self._skip("claude: mesaj nesne değil")
                continue
            sender = m.get("sender")
            if sender not in ("human", "assistant"):
                self._skip(f"claude: gönderen '{sender}' atlandı")
                continue
            text = clean(self._text(m))
            atts = [clean(a.get("file_name")) for a in (m.get("attachments") or []) + (m.get("files") or [])
                    if isinstance(a, dict) and (a.get("file_name"))]
            if not text and not atts:
                self._skip("claude: boş mesaj")
                continue
            ts = iso_utc(m.get("created_at")) or cts
            yield message_event(
                platform=self.platform, conv_id=cid, title=title, text=text or " ".join(atts), ts=ts,
                role=USER if sender == "human" else ASSISTANT,
                msg_id=clean(m.get("uuid")) or f"{i}:{ts}", model=conv.get("model"),
                extra={"ekler": atts} if atts else None)


# ----------------------------------------------------------------------------------- genel dosya
_USERS = {"user", "human", "you", "me", "kullanici", "kullanıcı", "ben", "sen", "prompt", "soru"}
_ASSIST = {"assistant", "ai", "bot", "model", "gpt", "chatgpt", "claude", "gemini", "deepseek", "copilot",
           "asistan", "yanit", "yanıt", "cevap"}
_SPEAKER = re.compile(r"^([^:：*_]{1,32})(?:\s*(?:\*\*|__))?\s*([:：])?(?:\s*(?:\*\*|__))?\s*(.*)$")
_TS_KEYS = ("ts", "timestamp", "created_at", "time", "create_time", "date", "tarih")


def _role_of(v) -> str | None:
    s = str(v or "").strip().lower()
    if s in _USERS:
        return USER
    if s in _ASSIST:
        return ASSISTANT
    return None


def _flatten_content(c) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        out = []
        for p in c:
            if isinstance(p, str):
                out.append(p)
            elif isinstance(p, dict) and isinstance(p.get("text"), str):
                out.append(p["text"])
        return "\n".join(out)
    if isinstance(c, dict) and isinstance(c.get("text"), str):
        return c["text"]
    return ""


class GenericChat(ScanImporter):
    """Yedek yol: kullanıcının elle hazırladığı metin/Markdown/JSON/JSONL sohbet dosyası (DeepSeek dahil
    resmî dışa aktarması olmayan kaynaklar için). DeepSeek: resmî bir dışa aktarma bulunamadı
    (yalnız üçüncü taraf tarayıcı eklentileri); bu yol kullanılır.

    Kabul edilen biçimler:
    - JSON: {"baslik"|"title", "id", "messages":[{"role","content","ts"?}]} nesnesi, bu nesnelerin dizisi,
      ya da yalnız mesaj dizisi; JSONL: her satır mesaj ya da konuşma.
    - Metin/Markdown: "Kullanıcı: ..." / "Asistan: ..." (User/Human/Assistant/AI/Claude/ChatGPT/DeepSeek/
      Gemini...) satırlarıyla ya da "## User" / "## Assistant" başlıklarıyla ayrılmış dönüşler.
    Zaman yoksa dosyanın tarihi kullanılır (`zaman_kaynagi=dosya_tarihi`)."""

    name = "chat_file"
    platform = "dosya"

    def _do_scan(self, arc):
        files, bad, ignored = [], [], 0
        for e in arc.entries:
            ext = e.name.lower().rsplit(".", 1)[-1] if "." in e.basename else ""
            if ext not in ("json", "jsonl", "md", "markdown", "txt") or e.size == 0:
                continue
            try:
                kind = self._sniff(e, ext)
            except (ijson.JSONError, UnicodeDecodeError, OSError):
                bad.append(e.name)
                continue
            if kind:
                files.append((kind, e))
            else:
                ignored += 1
        return files, bad, ignored, arc.bad_zips

    def _sniff(self, e: Entry, ext: str) -> str | None:
        if ext == "json":
            head = peek(e, 65536).lstrip()
            if head.startswith(b"{"):
                if e.size > 64 * 1024 * 1024:
                    return None
                with e.open() as raw:
                    rec = json.loads(strip_bom(raw).read().decode("utf-8"))
                return "json_conv" if isinstance(rec, dict) and isinstance(rec.get("messages"), list) else None
            if head.startswith(b"["):
                with e.open() as raw:
                    rec = next(ijson.items(strip_bom(raw), "item", use_float=True), None)
                if isinstance(rec, dict):
                    if isinstance(rec.get("messages"), list):
                        return "json_convs"
                    if "role" in rec and "content" in rec:
                        return "json_msgs"
            return None
        if ext == "jsonl":
            first = next((ln for ln in e.open() if ln.strip()), b"")
            try:
                rec = json.loads(first)
            except ValueError:
                return None
            if isinstance(rec, dict):
                if isinstance(rec.get("messages"), list):
                    return "jsonl_convs"
                if "role" in rec and "content" in rec:
                    return "jsonl_msgs"
            return None
        # metin / markdown: en az iki tanınan konuşmacı satırı
        n = 0
        with e.open() as raw:
            for i, line in enumerate(raw):
                if i > 2000:
                    break
                if self._speaker(line.decode("utf-8", "replace")):
                    n += 1
                    if n >= 2:
                        return "text"
        return None

    @staticmethod
    def _speaker(line: str):
        """(rol, ad, aynı satırdaki metin) ya da None. Başlık (## Kullanıcı) ya da 'Ad:' biçimi."""
        s = line.strip()
        heading = False
        m = re.match(r"^#{1,6}\s*", s)
        if m:
            heading, s = True, s[m.end():]
        s = s.lstrip("*_ ")
        m = _SPEAKER.match(s)
        if not m:
            return None
        who, colon, rest = m.group(1).strip(), m.group(2), m.group(3).strip()
        role = _role_of(who)
        if role is None or not (colon or heading):
            return None
        if heading and not colon and rest:
            return None
        return role, who, rest

    def detect(self, path: Path) -> DetectResult:
        try:
            _, (files, *_r) = self._scan(path)
        except FormatError as e:
            return DetectResult(False, 0.0, str(e))
        if files:
            return DetectResult(True, 0.6, f"genel sohbet dosyası ({len(files)}): " + ", ".join(sorted({k for k, _ in files})))
        return DetectResult(False, 0.0, "sohbet dosyası bulunamadı")

    def verify_format(self, path: Path) -> FormatReport:
        _, (files, bad, ignored, bad_zips) = self._scan(path)
        rep = FormatReport(importer=self.name, ok=bool(files) and not bad and not bad_zips)
        for kind, e in files:
            rep.found_files.append(f"{kind}: {e.name} ({e.size} bayt)")
        rep.missing += [f"{b}: bozuk/okunamadı" for b in bad]
        rep.missing += [f"{b}: zip dosyası okunamadı" for b in bad_zips]
        if not files:
            rep.missing.append("tanınan sohbet dosyası yok (JSON messages[{role,content}], JSONL ya da 'Kullanıcı:/Asistan:' metni)")
        if ignored:
            rep.notes.append(f"{ignored} dosya sohbet düzenine uymadığı için yok sayıldı")
        rep.notes.append("Zaman yoksa dosya tarihi kullanılır (zaman_kaynagi=dosya_tarihi); kategori sohbet (hassas)")
        _preflight(rep)
        return rep

    def input_files(self, path: Path) -> list[Origin]:
        _, (files, *_r) = self._scan(path)
        seen: dict[Path, Origin] = {}
        for _, e in files:
            seen.setdefault(e.origin.path, e.origin)
        return list(seen.values())

    def parse(self, path: Path) -> Iterator[EventIn]:
        _, (files, *_r) = self._scan(path)
        for kind, e in files:
            try:
                yield from getattr(self, f"_p_{kind}")(e)
            except (ijson.JSONError, UnicodeDecodeError, ValueError) as exc:
                if isinstance(exc, FormatError):
                    raise
                raise FormatError(f"{e.name}: dosya bozuk ({type(exc).__name__}). Önceki kayıtlar eklendi.") from None

    # --- ortak: bir konuşmayı olaylara çevir
    def _emit(self, e: Entry, conv_id: str, title: str, msgs: list[tuple[str, str, str | None, str | None]],
              conv_ts: str | None):
        file_ts = iso_utc(e.mtime)
        cts = conv_ts or file_ts
        yield title_event(platform=self.platform, conv_id=conv_id, title=title, ts=cts,
                          extra=None if conv_ts else {"zaman_kaynagi": "dosya_tarihi"})
        for i, (role, text, ts, model) in enumerate(msgs):
            text = clean(text).strip()
            if not text:
                self._skip("boş mesaj")
                continue
            real = ts is not None
            yield message_event(platform=self.platform, conv_id=conv_id, title=title, role=role, text=text,
                                ts=ts or cts, msg_id=str(i), model=model,
                                extra=None if real else {"zaman_kaynagi": "dosya_tarihi", "sira": i})

    @staticmethod
    def _msg(m: dict):
        role = _role_of(m.get("role") or m.get("sender") or m.get("author"))
        text = _flatten_content(m.get("content", m.get("text", m.get("message"))))
        ts = None
        for k in _TS_KEYS:
            if m.get(k) not in (None, ""):
                ts = iso_utc(m[k]) if isinstance(m[k], str) and not str(m[k]).replace(".", "").isdigit() else epoch_to_iso(m[k])
                if ts:
                    break
        return role, text, ts, m.get("model")

    def _conv_from_obj(self, e: Entry, obj: dict, idx: int):
        title = clean(obj.get("baslik") or obj.get("title") or obj.get("name")) or e.basename
        cid = clean(obj.get("id") or obj.get("uuid") or obj.get("conversation_id")) or stable_key("f", e.basename, idx)
        msgs = []
        for m in obj.get("messages") or []:
            if not isinstance(m, dict):
                self._skip("mesaj nesne değil")
                continue
            role, text, ts, model = self._msg(m)
            if role is None:
                self._skip("rol tanınmadı/sistem mesajı atlandı")
                continue
            msgs.append((role, text, ts, model))
        cts = None
        for k in _TS_KEYS:
            if obj.get(k):
                cts = iso_utc(obj[k]) if isinstance(obj[k], str) else epoch_to_iso(obj[k])
                break
        return cid, title, msgs, cts

    def _p_json_conv(self, e):
        with e.open() as raw:
            obj = json.loads(strip_bom(raw).read().decode("utf-8"))
        cid, title, msgs, cts = self._conv_from_obj(e, obj, 0)
        yield from self._emit(e, cid, title, msgs, cts)

    def _p_json_convs(self, e):
        with e.open() as raw:
            for i, obj in enumerate(ijson.items(strip_bom(raw), "item", use_float=True)):
                if isinstance(obj, dict):
                    cid, title, msgs, cts = self._conv_from_obj(e, obj, i)
                    yield from self._emit(e, cid, title, msgs, cts)

    def _p_json_msgs(self, e):
        msgs = []
        with e.open() as raw:
            for m in ijson.items(strip_bom(raw), "item", use_float=True):
                if isinstance(m, dict):
                    r = self._msg(m)
                    if r[0]:
                        msgs.append(r)
                    else:
                        self._skip("rol tanınmadı/sistem mesajı atlandı")
        yield from self._emit(e, stable_key("f", e.basename), e.basename, msgs, None)

    def _p_jsonl_convs(self, e):
        with e.open() as raw:
            for i, line in enumerate(raw):
                if line.strip():
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        cid, title, msgs, cts = self._conv_from_obj(e, obj, i)
                        yield from self._emit(e, cid, title, msgs, cts)

    def _p_jsonl_msgs(self, e):
        msgs = []
        with e.open() as raw:
            for line in raw:
                if line.strip():
                    m = json.loads(line)
                    r = self._msg(m) if isinstance(m, dict) else (None,)
                    if r[0]:
                        msgs.append(r)
                    else:
                        self._skip("rol tanınmadı/sistem mesajı atlandı")
        yield from self._emit(e, stable_key("f", e.basename), e.basename, msgs, None)

    def _p_text(self, e):
        msgs: list[tuple[str, str, str | None, str | None]] = []
        role = None
        buf: list[str] = []
        who_name = None

        def flush():
            if role and "".join(buf).strip():
                msgs.append((role, "\n".join(buf).strip(), None, who_name if role == ASSISTANT else None))

        with e.open() as raw:
            for line in raw:
                s = line.decode("utf-8", "replace")
                sp = self._speaker(s)
                if sp:
                    flush()
                    role, who, rest = sp
                    who_name = who if role == ASSISTANT else None
                    buf = [rest] if rest else []
                elif role:
                    buf.append(s.rstrip("\n"))
        flush()
        yield from self._emit(e, stable_key("f", e.basename), e.basename.rsplit(".", 1)[0], msgs, None)


def chatgpt_factory() -> ChatGPT:
    return ChatGPT()


def claude_factory() -> Claude:
    return Claude()


def generic_factory() -> GenericChat:
    return GenericChat()
