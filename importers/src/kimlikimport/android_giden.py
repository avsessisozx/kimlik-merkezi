"""Android giden kutusu içe aktarıcısı (docs/AKTARIM.md §1, §4, §5).

Girdi: tek `.jsonl` giden kutusu dosyası, bunları içeren klasör ya da `.zip` (elle aktarım).
Her dosya: başlık satırı, kayıt satırları, kapanış satırı. Kapanışı olmayan, `kayit_sayisi` tutmayan,
yarım/bozuk satırlı ya da geçersiz kayıtlı dosyadan HİÇ kayıt alınmaz (sessizce yanlış okunmaz);
sağlam dosyalar alınır, eksikler raporda dosya adıyla sayılır. Rapor içerik taşımaz: yalnız dosya adı,
satır numarası, alan adı ve sayılar. Dosyalar akışla okunur (iki geçiş: doğrula, sonra ayrıştır).
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from kimlikcore import EventIn, FormatError

from .base import DetectResult, Entry, FormatReport, Origin, ScanImporter, iso_utc, open_archive, stable_key

NAME = "android_giden"
# Telefonun yazabileceği kategoriler (AKTARIM §1 tablosu); persona/eposta/mesaj/sohbet gibi başkaları reddedilir.
_KATEGORILER = frozenset({"notlar", "medya_meta", "konum", "dosyalar", "uygulama"})
BICIM = 1
MAX_SATIR = 4 * 1024 * 1024     # tek satır üst sınırı; PC alıcısı da aynı sabiti kullanır
_MAX_SATIR = MAX_SATIR
_BILINEN_TURLER = frozenset({
    "paylasim.link", "paylasim.metin", "not.hizli", "medya.foto", "medya.video", "medya.konum",
    "indirilen.dosya", "uygulama.kullanim",
})


class _Bozuk(Exception):
    """Dosya eksik/bozuk; iletide yalnız neden, satır no ve alan adı (içerik YOK). `kod`: kararlı neden kodu."""

    def __init__(self, ileti: str, kod: str = "bozuk"):
        super().__init__(ileti)
        self.kod = kod


class _Desteklenmiyor(Exception):
    kod = "bicim_desteklenmiyor"


@dataclass(slots=True)
class _Dosya:
    entry: Entry
    cihaz_id: str = ""
    dosya_id: str = ""
    kayit: int = 0
    bilinmeyen: int = 0


@dataclass(slots=True)
class _Tarama:
    saglam: list[_Dosya] = field(default_factory=list)
    eksik: list[str] = field(default_factory=list)       # "ad: neden"
    desteklenmeyen: list[str] = field(default_factory=list)
    jsonl_disi: int = 0


def _satirlar(f) -> Iterator[tuple[int, bool, dict]]:
    """(satır no, son_mu, nesne) üretir. Bozuk satırda _Bozuk. Satır uzunluğu MAX_SATIR ile sınırlıdır
    (aşırı uzun satır belleğe alınmadan reddedilir)."""
    onceki: tuple[int, bytes] | None = None
    n = 0
    while True:
        ham = f.readline(MAX_SATIR + 1)
        if not ham:
            break
        n += 1
        if len(ham) > MAX_SATIR:
            raise _Bozuk(f"{n}. satır aşırı uzun", "satir_uzun")
        if onceki is not None:
            yield _coz(onceki[0], onceki[1], False)
        if not ham.strip():
            raise _Bozuk(f"{n}. satır boş", "bos_satir")
        onceki = (n, ham)
    if onceki is not None:
        yield _coz(onceki[0], onceki[1], True)


def _coz(n: int, ham: bytes, son: bool) -> tuple[int, bool, dict]:
    try:
        o = json.loads(ham.decode("utf-8"))
    except (RecursionError, MemoryError):
        raise _Bozuk(f"{n}. satır işlenemeyecek kadar derin/büyük JSON", "derin_json") from None
    except (ValueError, UnicodeDecodeError):
        if son:
            raise _Bozuk(f"{n}. satır yarım kalmış (kesik dosya)", "satir_yarim") from None
        raise _Bozuk(f"{n}. satır bozuk (geçerli JSON değil)", "satir_bozuk") from None
    if not isinstance(o, dict):
        raise _Bozuk(f"{n}. satır bir JSON nesnesi değil", "satir_bozuk")
    return n, son, o


def _oku(entry: Entry) -> Iterator[tuple[str, int, dict]]:
    with entry.open() as f:
        yield from _oku_akis(f)


def _oku_akis(f) -> Iterator[tuple[str, int, dict]]:
    """("baslik"|"kayit", satır no, nesne) üretir; kapanış doğrulanır, bozuklukta _Bozuk/_Desteklenmiyor."""
    baslik = None
    sayi = 0
    kapandi = False
    for n, _son, o in _satirlar(f):
        if kapandi:
            raise _Bozuk(f"{n}. satır: kapanış kaydından sonra satır var", "kapanis_sonrasi")
        if baslik is None:
            if o.get("baslik") is not True:
                raise _Bozuk("ilk satır başlık kaydı değil", "baslik_yok")
            b = o.get("bicim")
            if b != BICIM:
                raise _Desteklenmiyor(f"biçim sürümü {b if isinstance(b, int) else '?'}: bu sürüm desteklenmiyor")
            for alan in ("cihaz_id", "dosya_id"):
                if not isinstance(o.get(alan), str) or not o[alan]:
                    raise _Bozuk(f"başlıkta `{alan}` yok", "baslik_yok")
            baslik = o
            yield "baslik", n, o
            continue
        if o.get("kapanis") is True:
            k = o.get("kayit_sayisi")
            if not isinstance(k, int) or isinstance(k, bool) or k != sayi:
                raise _Bozuk(f"kayıt sayısı tutmuyor (kapanışta {k if isinstance(k, int) else '?'}, dosyada {sayi})", "sayi_tutmuyor")
            kapandi = True
            continue
        _kayit_denetle(n, o)
        sayi += 1
        yield "kayit", n, o
    if baslik is None:
        raise _Bozuk("dosya boş", "bos")
    if not kapandi:
        raise _Bozuk("dosya eksik: kapanış kaydı yok", "kapanis_yok")


def _kayit_denetle(n: int, o: dict) -> None:
    for alan in ("id", "tur", "kategori"):
        if not isinstance(o.get(alan), str) or not o[alan]:
            raise _Bozuk(f"{n}. satır: `{alan}` yok ya da metin değil", "alan_gecersiz")
    if o["kategori"] not in _KATEGORILER:
        raise _Bozuk(f"{n}. satır: geçersiz kategori", "kategori_gecersiz")
    if iso_utc(o.get("ts")) is None:
        raise _Bozuk(f"{n}. satır: `ts` okunamadı", "ts_gecersiz")
    if not isinstance(o.get("metin", ""), str):
        raise _Bozuk(f"{n}. satır: `metin` metin değil", "alan_gecersiz")
    if not isinstance(o.get("yuk", {}), dict):
        raise _Bozuk(f"{n}. satır: `yuk` nesne değil", "alan_gecersiz")
    if o.get("onceki") is not None and not isinstance(o["onceki"], str):
        raise _Bozuk(f"{n}. satır: `onceki` metin değil", "alan_gecersiz")


def dosya_dogrula(yol, cihaz_id: str | None = None, dosya_id: str | None = None) -> tuple[bool, int, str]:
    """Giden kutusu dosyasını baştan sona doğrular (içe aktarıcının TÜM kuralları): başlık, `bicim` 1, kategori
    kümesi, alan türleri, `ts`, satır uzunluğu, kapanış ve kayıt sayısı. Saf işlev: dosyaya yazmaz, Hub'a dokunmaz.

    cihaz_id/dosya_id verilirse başlıktakilerin aynı olması da aranır (PC alıcısı yoldakini verir).
    Dönüş: (ok, kayit_sayisi, neden_kodu); ok ise neden_kodu "". Kodlar: baslik_yok, bicim_desteklenmiyor,
    kapanis_yok, sayi_tutmuyor, satir_yarim, satir_bozuk, satir_uzun, bos_satir, alan_gecersiz,
    kategori_gecersiz, ts_gecersiz, kapanis_sonrasi, derin_json, bos, kimlik_uyusmuyor, okunamadi."""
    kayit = 0
    try:
        with open(yol, "rb") as f:
            for tur, _n, o in _oku_akis(f):
                if tur == "baslik":
                    if (cihaz_id is not None and o["cihaz_id"] != cihaz_id) or (
                            dosya_id is not None and o["dosya_id"] != dosya_id):
                        return False, 0, "kimlik_uyusmuyor"
                else:
                    kayit += 1
    except (_Bozuk, _Desteklenmiyor) as x:
        return False, 0, x.kod
    except (RecursionError, MemoryError):
        return False, 0, "derin_json"
    except OSError:
        return False, 0, "okunamadi"
    return True, kayit, ""


class AndroidGiden(ScanImporter):
    name = NAME
    version = "0.1.0"

    def _do_scan(self, arc) -> _Tarama:
        t = _Tarama()
        for e in arc.entries:
            if not e.name.lower().endswith(".jsonl"):
                t.jsonl_disi += 1
                continue
            d = _Dosya(e)
            try:
                for tur, _n, o in _oku(e):
                    if tur == "baslik":
                        d.cihaz_id, d.dosya_id = o["cihaz_id"], o["dosya_id"]
                    else:
                        d.kayit += 1
                        if o["tur"] not in _BILINEN_TURLER:
                            d.bilinmeyen += 1
            except _Desteklenmiyor as x:
                t.desteklenmeyen.append(f"{e.name}: {x}")
            except _Bozuk as x:
                t.eksik.append(f"{e.name}: {x}")
            except OSError as x:
                t.eksik.append(f"{e.name}: okunamadı ({type(x).__name__})")
            else:
                t.saglam.append(d)
        return t

    # --- sözleşme
    def detect(self, path: Path) -> DetectResult:
        try:
            arc, _ = self._scan(Path(path))
        except FormatError as e:
            return DetectResult(False, 0.0, str(e))
        for e in arc.entries:
            if e.name.lower().endswith(".jsonl") and _baslik_mu(e):
                return DetectResult(True, 0.95, "Android giden kutusu dosyası (başlık satırı bulundu)")
        return DetectResult(False, 0.0, "Android giden kutusu başlık satırı olan .jsonl dosyası bulunamadı")

    def verify_format(self, path: Path) -> FormatReport:
        _, t = self._scan(Path(path))
        rep = FormatReport(importer=NAME, ok=bool(t.saglam))
        rep.found_files = [d.entry.name for d in t.saglam]
        rep.missing = list(t.eksik)
        rep.unsupported = list(t.desteklenmeyen)
        if not t.saglam and not t.eksik and not t.desteklenmeyen:
            rep.missing.append("giden kutusu dosyası (.jsonl)")
        toplam = len(t.saglam) + len(t.eksik) + len(t.desteklenmeyen)
        if t.eksik or t.desteklenmeyen:
            rep.notes.append(
                f"{toplam} dosyadan {len(t.saglam)} tanesi alınabilir; {len(t.eksik)} eksik/bozuk, "
                f"{len(t.desteklenmeyen)} desteklenmeyen dosyadan hiç kayıt alınmayacak")
        bil = sum(d.bilinmeyen for d in t.saglam)
        if bil:
            rep.notes.append(f"{bil} kayıt bilinmeyen türde (ileri uyum; kategorisi geçerli olduğu için alınır)")
        if t.jsonl_disi:
            rep.notes.append(f"{t.jsonl_disi} .jsonl olmayan dosya yok sayıldı")
        return rep

    def input_files(self, path: Path) -> list[Origin]:
        _, t = self._scan(Path(path))
        seen: dict[Path, Origin] = {}
        for d in t.saglam:
            seen.setdefault(d.entry.origin.path, d.entry.origin)
        return list(seen.values())

    def parse(self, path: Path) -> Iterator[EventIn]:
        _, t = self._scan(Path(path))
        for d in t.saglam:
            try:
                for tur, _n, o in _oku(d.entry):
                    if tur == "baslik":
                        continue
                    yield _olay(d.cihaz_id, d.dosya_id, o)
            except (_Bozuk, _Desteklenmiyor) as x:
                raise FormatError(f"{d.entry.name}: dosya içe alma sırasında değişmiş ({x})") from None


def _olay(cihaz_id: str, dosya_id: str, o: dict) -> EventIn:
    payload = dict(o.get("yuk") or {})
    payload["tur"] = o["tur"]
    if o.get("onceki"):
        payload["onceki"] = o["onceki"]
    payload["dosya_id"] = dosya_id
    return EventIn(
        ts=iso_utc(o["ts"]), kind="android." + o["tur"], category=o["kategori"], payload=payload,
        text=o.get("metin") or "", device_id=cihaz_id, event_key=stable_key("android", cihaz_id, o["id"]),
    )


def _baslik_mu(e: Entry) -> bool:
    try:
        with e.open() as f:
            ilk = f.readline(65536)
        o = json.loads(ilk.decode("utf-8-sig"))
        return isinstance(o, dict) and o.get("baslik") is True and "cihaz_id" in o
    except (ValueError, OSError):
        return False


def factory() -> AndroidGiden:
    return AndroidGiden()
