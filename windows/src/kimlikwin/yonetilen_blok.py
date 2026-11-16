"""Yapay zekâ araçlarının her oturumda kendiliğinden okuduğu dosyalara (CLAUDE.md, AGENTS.md) kısa, YÖNETİLEN bir bölüm.

Yalnız iki SABİT yol: `~/.claude/CLAUDE.md` ve (yalnız `~/.codex` klasörü varsa) `~/.codex/AGENTS.md`. Yol dışarıdan
alınmaz. Yalnız işaretçiler ARASI değişir; dosyanın geri kalanı bayt bayt korunur (satır sonu biçimi ve BOM dahil).
İşaretçi bozuksa dosyaya dokunulmaz. Her yazmadan önce yedek (en yeni 3 tutulur), yazım atomik, içerik aynıysa yazılmaz.
İçeriğe yalnız kullanıcının onayladığı persona bilgileri girer (beyan_edilen + dosyadan_alinan); çıkarılan/eskimiş/gizli
bilgi, veriden özet ve hassas kategori içeriği girmez."""
from __future__ import annotations

import os
import re
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

BLOK_UST_SINIR = 3000
BASLA = "<!-- KIMLIK-MERKEZI:BASLA (bu bölümü Kimlik Merkezi uygulaması yönetir; elle değiştirmeyin) -->"
BITIR = "<!-- KIMLIK-MERKEZI:BITIR -->"
_BASLA_ONEK = "<!-- KIMLIK-MERKEZI:BASLA"
_BASLIK = "## Kullanıcı hakkında (Kimlik Merkezi'nden, kullanıcının onayladığı bilgiler)"
_KURAL_BASLIK = "### Kurallar ve tercihler"
_DIPNOT = "Daha fazlası için (izin verilen ölçüde) `kimlik-merkezi` MCP araçlarını kullan."
_TARIH_RE = re.compile(r"Güncelleme tarihi: \d{4}-\d{2}-\d{2}")
YEDEK_SAYISI = 3
DOSYA_UST_SINIR = 1024 * 1024        # bundan büyük dosyaya dokunulmaz
_KILIT = threading.Lock()
_BOM = b"\xef\xbb\xbf"


def ev_klasoru() -> Path:
    """Windows'ta %USERPROFILE%; testte `Yonetici(ev_klasoru=...)` ile değiştirilir."""
    return Path(os.environ.get("USERPROFILE") or Path.home())


@dataclass(frozen=True)
class Hedef:
    ad: str            # arayüzde gösterilen
    yol: Path
    klasor_sart: Path | None   # varsa: bu klasör YOKSA dosya atlanır (oluşturulmaz)


def hedefler(ev: Path) -> list[Hedef]:
    return [Hedef("Claude Code (~/.claude/CLAUDE.md)", ev / ".claude" / "CLAUDE.md", None),
            Hedef("Codex (~/.codex/AGENTS.md)", ev / ".codex" / "AGENTS.md", ev / ".codex")]


# ------------------------------------------------------------------ içerik
def _satir(s: str, sinir: int = 300) -> str:
    """Persona beyanını TEK güvenli satıra indirir: satır sonları boşluk olur; işaretçi ve HTML yorum parçaları
    (iç içe kaçışlar dahil, sabit noktaya kadar) ile `KIMLIK-MERKEZI` dizgisi tümden silinir; baştaki # etkisizleşir."""
    s = re.sub(r"\s+", " ", s or "").strip()
    onceki = None
    while s != onceki:
        onceki = s
        s = re.sub(r"KIMLIK-MERKEZI", "", s, flags=re.I)
        s = s.replace("<!", "").replace("-->", "")
        s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[#\s]+", "", s)
    return s if len(s) <= sinir else s[:sinir - 1].rstrip() + "…"


def _derle(bilgiler: list[str], kurallar: list[str], kirpilan: int, tarih: date) -> str:
    s = [_BASLIK]
    s += [f"- {b}" for b in bilgiler]
    if kurallar:
        s += ["", _KURAL_BASLIK] + [f"- {k}" for k in kurallar]
    if not bilgiler and not kurallar and not kirpilan:
        s.append("(Henüz onaylanmış bilgi yok.)")
    if kirpilan:
        s += ["", f"... ve {kirpilan} bilgi daha"]
    s += ["", _DIPNOT, f"Güncelleme tarihi: {tarih.isoformat()}"]
    return "\n".join(s)


def icerik_uret(okuyucu, bugun: date | None = None, sinir: int = BLOK_UST_SINIR) -> str:
    """İşaretçisiz içerik (LF). `okuyucu`: PersonaReader/Persona (`list_facts()` = yalnız onaylı, canlı bilgiler)."""
    from kimlikserver.persona import CATEGORY_TITLES
    bugun = bugun or datetime.now(timezone.utc).date()
    bilgiler: list[str] = []
    kurallar: list[str] = []
    for f in okuyucu.list_facts():
        if f.status not in ("beyan_edilen", "dosyadan_alinan"):      # savunma: çıkarılan/eskimiş asla
            continue
        m = _satir(f.statement)
        if not m:
            continue
        (kurallar if f.category == "tercihler" else bilgiler).append(
            m if f.category == "tercihler" else f"{CATEGORY_TITLES.get(f.category, f.category)}: {m}")
    toplam = len(bilgiler) + len(kurallar)
    for kirp in range(toplam + 1):            # önce bilgilerin sonundan, sonra kuralların sonundan kırp
        ab = max(0, len(bilgiler) - kirp)
        ak = len(kurallar) - max(0, kirp - len(bilgiler))
        metin = _derle(bilgiler[:ab], kurallar[:ak], kirp, bugun)
        if len(metin) <= sinir:
            return metin
    return _derle([], [], toplam, bugun)[:sinir]


# ------------------------------------------------------------------ dosya işlemleri
def _normal(b: bytes) -> bytes:
    return _TARIH_RE.sub("Güncelleme tarihi: -", b.decode("utf-8", "replace")).encode("utf-8")


def _isaretci_satirlari(ham: bytes) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """(BASLA konumları, BITIR konumları): YALNIZ tam satır olan işaretçiler (baş/son boşluk hariç); ``` / ~~~ ile
    çevrili kod bloklarının içindekiler yok sayılır. Konum = (işaretçi metninin başı, sonu) bayt."""
    basla, bitir, ic, konum = [], [], False, 0
    for satir in ham.splitlines(keepends=True):
        govde = satir.rstrip(b"\r\n")
        kes = govde.strip().removeprefix(_BOM).strip()
        if kes.startswith((b"```", b"~~~")):
            ic = not ic
        elif not ic and kes:
            ilk = konum + govde.index(kes)
            if kes == BITIR.encode():
                bitir.append((ilk, ilk + len(kes)))
            elif kes.startswith(_BASLA_ONEK.encode()) and kes.endswith(b"-->"):
                basla.append((ilk, ilk + len(kes)))
        konum += len(satir)
    return basla, bitir


def _isaretciler(ham: bytes) -> tuple[int, int] | str:
    """(başlangıç, bitiş) bayt konumları (bitiş = BITIR işaretçisinin sonu), (-1,-1)=blok yok, ya da hata iletisi."""
    basla, bitir = _isaretci_satirlari(ham)
    a, b = len(basla), len(bitir)
    if a == 0 and b == 0:
        return (-1, -1)
    if a > 1 or b > 1:
        return "Dosyada birden çok Kimlik Merkezi işaretçisi var."
    if a == 1 and b == 0:
        return "Başlangıç işaretçisi var, bitiş işaretçisi yok."
    if a == 0:
        return "Bitiş işaretçisi var, başlangıç işaretçisi yok."
    if bitir[0][0] < basla[0][0]:
        return "İşaretçilerin sırası bozuk."
    return basla[0][0], bitir[0][1]


def _blok_baytlari(icerik: str, nl: str) -> bytes:
    return nl.join([BASLA, *icerik.split("\n"), BITIR]).encode("utf-8")


def yeni_baytlar(mevcut: bytes | None, icerik: str | None) -> tuple[bytes | None, str]:
    """(yeni dosya içeriği ya da None=değişmez, durum). durum: olusturulacak | eklenecek | guncellenecek |
    kaldirilacak | degismeyecek | bozuk:<ileti>. `icerik=None`: bloğu kaldır."""
    ham = mevcut or b""
    nl = "\r\n" if b"\r\n" in ham else "\n"
    kon = _isaretciler(ham)
    if isinstance(kon, str):
        return None, "bozuk:" + kon
    i, j = kon
    if icerik is None:                                            # kaldır
        if i < 0:
            return None, "degismeyecek"
        bit = j
        for n in (b"\r\n", b"\n"):
            if ham[bit:bit + len(n)] == n:
                bit += len(n)
                break
        bas = i
        for n in (b"\r\n", b"\n"):                                # eklerken konan boş satırı geri al
            if ham[:bas].endswith(n + n):
                bas -= len(n)
                break
        return ham[:bas] + ham[bit:], "kaldirilacak"
    blok = _blok_baytlari(icerik, nl)
    if i >= 0:                                                    # güncelle
        if _normal(ham[i:j]) == _normal(blok):
            return None, "degismeyecek"
        return ham[:i] + blok + ham[j:], "guncellenecek"
    nlb = nl.encode()
    if not ham or ham == _BOM:
        return ham + blok + nlb, "olusturulacak"
    son = b"" if ham.endswith((b"\n",)) else nlb
    return ham + son + nlb + blok + nlb, "eklenecek"


def _yedek_al(yol: Path, simdi: Callable[[], datetime]) -> Path:
    ad = f"{yol.name}.kimlik-yedek-{simdi():%Y%m%d-%H%M%S}"
    yedek, n = yol.with_name(ad), 1
    while yedek.exists():
        yedek, n = yol.with_name(f"{ad}-{n}"), n + 1
    yedek.write_bytes(yol.read_bytes())
    eskiler = sorted(p for p in yol.parent.glob(yol.name + ".kimlik-yedek-*") if p.is_file())
    for p in eskiler[:-YEDEK_SAYISI]:
        try:
            p.unlink()
        except OSError:
            pass
    return yedek


def _atomik_yaz(yol: Path, veri: bytes) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    fd, ad = tempfile.mkstemp(prefix=yol.name + ".", suffix=".kimlik-tmp", dir=yol.parent)
    gecici = Path(ad)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(veri)
        os.replace(gecici, yol)
    except OSError:
        try:
            gecici.unlink()
        except OSError:
            pass
        raise


_YAZILDI = {"olusturulacak": "yazildi", "eklenecek": "yazildi", "guncellenecek": "guncellendi", "kaldirilacak": "kaldirildi"}
_MESAJ = {"yazildi": "Bölüm yazıldı.", "guncellendi": "Bölüm güncellendi.", "kaldirildi": "Bölüm kaldırıldı (yazdıklarınıza dokunulmadı).",
          "degismedi": "Değişiklik yok; dosyaya dokunulmadı.",
          "bulunamadi": "~/.codex klasörü bulunamadı (Codex kurulu görünmüyor); atlandı.",
          "yok": "Dosyada Kimlik Merkezi bölümü yok."}


def _hedef_isle(h: Hedef, icerik: str | None, yaz: bool, simdi: Callable[[], datetime]) -> dict[str, Any]:
    o = {"ad": h.ad, "durum": "", "mesaj": "", "yedek": False}
    yol = h.yol
    try:
        if yol.is_symlink():                       # bağlantıyı koparma: gerçek dosyaya yaz, yedek de orada
            yol = yol.resolve()
    except OSError:
        pass
    h = Hedef(h.ad, yol, h.klasor_sart)
    try:
        if yol.is_file() and yol.stat().st_size > DOSYA_UST_SINIR:
            return {**o, "durum": "buyuk", "mesaj": "Dosya çok büyük, dokunulmadı."}
    except OSError:
        pass
    if h.klasor_sart is not None and not h.klasor_sart.is_dir():
        return {**o, "durum": "bulunamadi", "mesaj": _MESAJ["bulunamadi"]}
    try:
        mevcut = h.yol.read_bytes() if h.yol.is_file() else None
    except OSError as e:
        return {**o, "durum": "hata", "mesaj": f"Dosya okunamadı: {e.strerror or e}"}
    if mevcut is None and icerik is None:
        return {**o, "durum": "yok", "mesaj": _MESAJ["yok"]}
    yeni, durum = yeni_baytlar(mevcut, icerik)
    if durum.startswith("bozuk:"):
        return {**o, "durum": "bozuk", "mesaj": durum[6:] + " Dosyaya dokunulmadı; işaretçileri düzeltin ya da bölümü silin."}
    if yeni is None:
        return {**o, "durum": "yok" if icerik is None else "degismedi", "mesaj": _MESAJ["yok" if icerik is None else "degismedi"]}
    sonuc = _YAZILDI[durum]
    if not yaz:
        return {**o, "durum": sonuc, "mesaj": _MESAJ[sonuc].replace("yazıldı", "yazılacak").replace("güncellendi", "güncellenecek")
                .replace("kaldırıldı", "kaldırılacak")}
    try:
        if mevcut is not None:
            _yedek_al(h.yol, simdi)
            o["yedek"] = True
        _atomik_yaz(h.yol, yeni)
    except OSError as e:
        return {**o, "durum": "hata", "mesaj": f"Yazılamadı, dosya değişmedi: {e.strerror or e}"}
    return {**o, "durum": sonuc, "mesaj": _MESAJ[sonuc]}


def uygula(ev: Path, icerik: str | None, simdi: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> list[dict[str, Any]]:
    """`icerik` yazılır (None: bölüm kaldırılır). Her hedef için {ad, durum, mesaj, yedek}."""
    with _KILIT:
        return [_hedef_isle(h, icerik, True, simdi) for h in hedefler(ev)]


def onizle(ev: Path, icerik: str | None) -> list[dict[str, Any]]:
    """Hiçbir şey yazmadan ne olacağını söyler."""
    return [_hedef_isle(h, icerik, False, datetime.now) for h in hedefler(ev)]
