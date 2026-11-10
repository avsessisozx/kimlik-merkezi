"""Gelen kutusu: yazan Hub'ı beklemeden, çok süreçten güvenle bırakılan küçük kayıtlar.

Neden var: MCP süreçleri (birden çok, aynı anda) erişim günlüğüne ve persona öneri kuyruğuna yazmak
ister; ama şifreli `kimlik.db` tek yazan süreç (hub.lock) tarafından bellek içi kapsayıcı olarak tutulur
(docs/SIFRELEME.md). Birden çok süreç kapsayıcıyı aynı anda "oku-değiştir-yaz" yaparsa güncellemeler
kaybolur; ayrı bir SQLite dosyası ise şifrelenemez. Çözüm: her kayıt `gelen/` altında KENDİ dosyasıdır
(benzersiz ad, geçici dosya + fsync + atomik yeniden adlandırma), şifreli klasörde aynı AES-GCM
biçimiyle şifrelenir. İki yazar hiç aynı dosyaya dokunmadığı için kayıp ya da kilit çakışması olamaz.
Yazan Hub (`Hub.gelen_birlestir`) bu dosyaları veritabanına işler ve siler; yazan Hub açık değilken
dosyalar bekler, okuyucular (`listele`) bekleyenleri de görür.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from . import sifreleme as sif
from .errors import SifrelemeHatasi

KLASOR = "gelen"
TURLER = ("erisim", "oneri")
UZANTI = ".gelen"
BOZUK = "bozuk"
_SURUM = 1


class GelenKutusu:
    """`root/gelen/` klasörü. `dek` verilirse dosyalar şifreli yazılır/okunur."""

    def __init__(self, root: Path | str, dek: bytes | None = None):
        self.root = Path(root)
        self.dir = self.root / KLASOR
        self._dek = dek

    @classmethod
    def ac(cls, root: Path | str, *, parola: str | None = None,
           saglayici: "sif.AnahtarSaglayici | None" = None) -> "GelenKutusu":
        """Veri klasörü şifreliyse anahtarı `Hub.open` ile aynı yoldan alır (OS sağlayıcısı, parola
        argümanı, KIMLIK_PAROLA); alınamazsa `AnahtarGerekli`. Şifresiz klasörde düz yazar."""
        root = Path(root)
        dek = None
        if sif.db_durumu(root / "kimlik.db") == "sifreli":
            dek = sif.anahtari_coz(root, parola=parola, saglayici=saglayici)
        return cls(root, dek)

    # ------------------------------------------------------------------ yazma
    def yaz(self, tur: str, kayit: dict[str, Any]) -> str:
        """Kaydı kendi dosyasına atomik yazar (fsync'li). Dosya adını döner. Hata -> OSError."""
        if tur not in TURLER:
            raise ValueError(f"Bilinmeyen gelen kutusu türü: {tur}")
        self.dir.mkdir(parents=True, exist_ok=True)
        ad = f"{tur}-{time.time_ns():020d}-{secrets.token_hex(6)}{UZANTI}"
        veri = json.dumps({"v": _SURUM, "tur": tur, "kayit": kayit}, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
        hedef = self.dir / ad
        if self._dek is not None:
            sif.bayt_sifrele_yaz(self._dek, veri, hedef)
            return ad
        tmp = hedef.with_name(ad + f".gecici-{secrets.token_hex(4)}")
        try:
            with open(tmp, "wb") as f:
                f.write(veri)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, hedef)
        finally:
            tmp.unlink(missing_ok=True)
        return ad

    # ------------------------------------------------------------------ okuma
    def adlar(self, tur: str | None = None) -> list[str]:
        if not self.dir.is_dir():
            return []
        on = f"{tur}-" if tur else ""
        return sorted(p.name for p in self.dir.iterdir()
                      if p.is_file() and p.name.endswith(UZANTI) and p.name.startswith(on))

    def oku(self, ad: str) -> tuple[str, dict[str, Any]]:
        """(tür, kayıt). Çözülemeyen/bozuk dosyada ValueError ya da SifrelemeHatasi."""
        yol = self.dir / ad
        if sif.sifreli_mi(yol):
            if self._dek is None:
                raise SifrelemeHatasi("Gelen kutusunda şifreli dosya var ama anahtar yok.")
            ham = sif.bayt_coz_oku(self._dek, yol)
        else:
            ham = yol.read_bytes()
        d = json.loads(ham.decode("utf-8"))
        if not isinstance(d, dict) or d.get("v") != _SURUM or d.get("tur") not in TURLER \
                or not isinstance(d.get("kayit"), dict):
            raise ValueError("Gelen kutusu kaydı tanınmadı.")
        return d["tur"], d["kayit"]

    def listele(self, tur: str | None = None) -> tuple[list[tuple[str, dict[str, Any]]], list[str]]:
        """([(ad, kayıt)...] oluşturulma sırasıyla, okunamayan dosya adları)."""
        iyi, kotu = [], []
        for ad in self.adlar(tur):
            try:
                t, k = self.oku(ad)
            except (OSError, ValueError, SifrelemeHatasi):
                kotu.append(ad)
                continue
            iyi.append((ad, k))
        return iyi, kotu

    def sil(self, ad: str) -> None:
        (self.dir / ad).unlink(missing_ok=True)

    def karantina(self, ad: str) -> None:
        """Okunamayan/geçersiz dosyayı `gelen/bozuk/` altına alır (silmez: kullanıcı inceleyebilir)."""
        k = self.dir / BOZUK
        k.mkdir(exist_ok=True)
        try:
            os.replace(self.dir / ad, k / ad)
        except OSError:
            pass
