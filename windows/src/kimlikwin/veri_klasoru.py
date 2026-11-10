"""İlk açılış sihirbazının veri klasörü mantığı (arayüzden bağımsız)."""
from __future__ import annotations

import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from kimlikcore import Hub
from kimlikcore.sifreleme import varsayilan_acik_mi

DB_AD = "kimlik.db"


def boyut_metni(n: int) -> str:
    """1536 -> '1,5 KB' (Türkçe ondalık virgül, 1024 tabanı)."""
    deger = float(n)
    for birim in ("B", "KB", "MB", "GB", "TB"):
        if deger < 1024 or birim == "TB":
            s = f"{deger:.0f}" if birim == "B" else f"{deger:.1f}".replace(".", ",")
            return f"{s} {birim}"
        deger /= 1024
    return f"{n} B"


def bos_alan(yol: Path | str) -> int:
    """Yolun (henüz yoksa var olan en yakın üst klasörün) bulunduğu sürücüdeki boş bayt."""
    p = Path(yol).absolute()
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


@dataclass
class Denetim:
    ok: bool
    durum: str          # yeni | bos | mevcut | dolu | dosya | yazilamaz | goreli
    mesaj: str
    bos_alan: int
    bos_alan_metni: str

    def to_dict(self) -> dict:
        return asdict(self)


def _yazilabilir(klasor: Path) -> bool:
    """Klasöre gerçekten dosya yazıp silerek dener (izin bayrağına güvenilmez)."""
    deneme = klasor / f".yazma-denemesi-{uuid.uuid4().hex}"
    try:
        deneme.write_bytes(b"x")
        deneme.unlink()
        return True
    except OSError:
        return False


def denetle(yol: str | Path) -> Denetim:
    """Seçilen klasör kullanılabilir mi? Alt sınır konmaz; boş alan yalnız gösterilir."""
    if not str(yol).strip():
        return Denetim(False, "goreli", "Bir klasör yolu yazın ya da seçin.", 0, "-")
    p = Path(str(yol).strip().strip('"'))
    if not p.is_absolute():
        return Denetim(False, "goreli", "Tam yol gerekli (ör. C:\\Kullanıcılar\\...\\KimlikMerkezi).", 0, "-")
    try:
        bos = bos_alan(p)
    except OSError:
        return Denetim(False, "yazilamaz", "Bu sürücüye erişilemiyor.", 0, "-")
    metin = boyut_metni(bos)
    if p.exists() and not p.is_dir():
        return Denetim(False, "dosya", "Bu yol bir dosya; klasör seçin.", bos, metin)
    if not p.exists():
        # oluşturulabilir mi: var olan en yakın üst klasöre yazılabilmeli
        ust = p
        while not ust.exists() and ust != ust.parent:
            ust = ust.parent
        if not _yazilabilir(ust):
            return Denetim(False, "yazilamaz", "Bu konuma klasör oluşturulamıyor (yazma izni yok).", bos, metin)
        return Denetim(True, "yeni", "Klasör oluşturulacak.", bos, metin)
    if not _yazilabilir(p):
        return Denetim(False, "yazilamaz", "Bu klasöre yazılamıyor (yazma izni yok).", bos, metin)
    if (p / DB_AD).is_file():
        return Denetim(True, "mevcut", "Bu klasörde zaten bir Kimlik Merkezi veritabanı var; kullanılacak.", bos, metin)
    if any(p.iterdir()):
        return Denetim(False, "dolu", "Klasör boş değil. Boş bir klasör ya da yeni bir ad seçin.", bos, metin)
    return Denetim(True, "bos", "Boş klasör; veritabanı burada oluşturulacak.", bos, metin)


def olustur(yol: str | Path, parola: str | None = None) -> dict:
    """Veritabanını ve klasör yapısını (kimlik.db, arsiv/, cikti/) kendisi oluşturur."""
    d = denetle(yol)
    if not d.ok:
        raise ValueError(d.mesaj)
    p = Path(str(yol).strip().strip('"'))
    # Yeni klasör varsayılan ŞİFRELİ (anahtar Windows hesabına bağlı); sağlayıcı yoksa şifresiz.
    with Hub.open(p, write=True, parola=parola, sifreli=True if d.durum != "mevcut" and varsayilan_acik_mi() else None) as hub:
        surum = hub.schema_version
        sifreli = hub.sifreli
    return {"yol": str(p), "sema": surum, "mevcut_idi": d.durum == "mevcut", "sifreli": sifreli,
            "dosyalar": sorted(x.name for x in p.iterdir())}


def varsayilan_oner() -> str:
    from .yollar import varsayilan_veri_klasoru
    return str(varsayilan_veri_klasoru())
