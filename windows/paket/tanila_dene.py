"""Dosya denetimi (tanila) için SENTINEL yardımcıları. Hem kurulu_dene.py (Windows CI, gerçek exe) hem de
windows/tests (Linux, aynı mantık) kullanır; tek yerde durur ki iki taraf aynı şeyi sınasın.

Mantık: sahte bir dışa aktarma zip'i üretilir; DEĞERLERDE (SV) ve ADLARDA (SN) özel işaretli dizgiler vardır.
Varsayılan raporda ikisi de (ve 6 harflik parçaları) bulunmamalı. `--adlari-goster` raporunda ad işareti
görünebilir ama değer işareti ve diğer değerler yine bulunmamalı."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

SV = "ZQXDEGERZQX"      # yalnız değerlerde
SN = "ZQXADZQX"         # yalnız adlarda (dosya/klasör/anahtar/sütun başlığı)
DEGERLER = [SV, "5551234567890", "2024-03-05T10:11:12Z", "1709287200123", "ornek.kisi@example.test",
            "https://example.test/gizli/yol?x=1", "Ayşe Örnek", "203.0.113.99"]


def sahte_zip(hedef: Path) -> Path:
    """Küçük, çok biçimli sahte dışa aktarma zip'i (kişisel veri yok; tümü uydurma)."""
    kayit = lambda i: {"title": f"Watched {SV} {i}", "titleUrl": DEGERLER[5], "time": DEGERLER[2], "header": "YouTube",
                       "sayi": 1709287200123 + i, "e": DEGERLER[4], "ip": DEGERLER[7], "ad": DEGERLER[6],
                       "tel": DEGERLER[1], f"anahtar{SN}": {"ic": SV}, "products": ["YouTube"]}
    csv_ = io.StringIO()
    w = csv.writer(csv_)
    w.writerow([SN, "Ayşe Örnek", DEGERLER[4]])
    for _ in range(4):
        w.writerow([SV, DEGERLER[6], DEGERLER[2]])
    with zipfile.ZipFile(hedef, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"Klasor{SN}Ad/MyActivity.json", json.dumps([kayit(i) for i in range(5)], ensure_ascii=False))
        z.writestr(f"Klasor{SN}Ad/kisi_{SN}_1234567890/message_1.json", json.dumps(
            {"participants": [{"name": SV}], "messages": [{"sender_name": SV, "content": SV, "timestamp_ms": 1709287200123}],
             "etiketler": {f"{SN}{i}": {"x": 1} for i in range(12)}}, ensure_ascii=False))
        z.writestr(f"Klasor{SN}Ad/tablo.csv", csv_.getvalue())
        z.writestr(f"Klasor{SN}Ad/not_{SN}.txt", f"{SV} metin\nikinci satır {SV}\n")
    return hedef


def _parcalar(s: str):
    s = s.lower()
    yield s
    for i in range(0, len(s) - 5):
        yield s[i:i + 6]


def sizinti_var_mi(rapor: str, *, adlar_acik: bool = False) -> str | None:
    """Sızıntı varsa açıklama, yoksa None. Rapor boşsa da sorun sayılır (boş rapor sızdırmaz ama kanıt da olmaz)."""
    if "TANILAMA RAPORU" not in rapor:
        return "rapor başlığı yok (rapor üretilmemiş)"
    low = rapor.lower()
    for p in _parcalar(SV):
        if p in low:
            return f"değer işareti sızdı: {p}"
    for d in DEGERLER:
        if d.lower() in low:
            return f"değer sızdı: {d!r}"
    if not adlar_acik:
        for p in _parcalar(SN):
            if p in low:
                return f"ad işareti sızdı (varsayılan modda maskeli olmalı): {p}"
    return None
