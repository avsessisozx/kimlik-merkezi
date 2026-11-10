"""Kullanıcı ayarları (JSON, atomik yazım). Veri klasöründen ayrı bir dosyadır."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .yollar import ayar_dizini

VARSAYILAN: dict[str, Any] = {
    "veri_klasoru": None,        # sihirbaz tamamlanınca dolar
    "ilk_acilis_tamam": False,
    "tema": "sistem",            # sistem | acik | koyu
    "otomatik_baslat": True,     # kurulumda açık; Ayarlar'dan kapatılır
    "port": 47821,               # tercih edilen yerel port; doluysa boş bir port seçilir
}
TEMALAR = ("sistem", "acik", "koyu")


class Ayarlar:
    def __init__(self, dizin: Path | None = None):
        self.dizin = Path(dizin) if dizin else ayar_dizini()
        self.yol = self.dizin / "ayarlar.json"
        self.veri: dict[str, Any] = dict(VARSAYILAN)
        self.yukle()

    def yukle(self) -> None:
        self.veri = dict(VARSAYILAN)
        try:
            ham = json.loads(self.yol.read_text(encoding="utf-8"))
            if isinstance(ham, dict):
                self.veri.update({k: v for k, v in ham.items() if k in VARSAYILAN})
        except (OSError, ValueError):
            pass  # yok ya da bozuk: varsayılanlar; bozuk dosya bir sonraki kayıtta yenilenir

    def kaydet(self) -> None:
        self.dizin.mkdir(parents=True, exist_ok=True)
        gecici = self.yol.with_suffix(".tmp")
        gecici.write_text(json.dumps(self.veri, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(gecici, self.yol)

    def __getitem__(self, k: str) -> Any:
        return self.veri[k]

    def guncelle(self, **kw: Any) -> None:
        for k, v in kw.items():
            if k not in VARSAYILAN:
                raise KeyError(k)
            if k == "tema" and v not in TEMALAR:
                raise ValueError("Geçersiz tema.")
            self.veri[k] = v
        self.kaydet()
