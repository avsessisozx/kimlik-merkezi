#!/usr/bin/env python3
"""Sözleşme testi: telefon altın örneği (giden_ornek.jsonl) PC'nin GERÇEK içe aktarıcısından geçer."""
import sys
import tempfile
from pathlib import Path

from kimlikcore import Hub
from kimlikimport.android_giden import dosya_dogrula
from kimlikimport.run import run

ORNEK = Path(__file__).resolve().parents[1] / "app/src/test/resources/giden_ornek.jsonl"
CIHAZ = "3f2b8c1e-5a47-4d9e-8b36-1c7e0a9d4f52"
# tür -> (kategori, önem, hassas konu); notlar önem 2; "fatura.pdf" finans konusu işaretlenir (çekirdek kuralı)
BEKLENEN = {
    "not.hizli": ("notlar", 2, ()), "paylasim.link": ("notlar", 2, ()), "paylasim.metin": ("notlar", 2, ()),
    "medya.foto": ("medya_meta", 1, ()), "medya.video": ("medya_meta", 1, ()), "medya.konum": ("konum", 1, ()),
    "indirilen.dosya": ("dosyalar", 1, ("finans",)), "uygulama.kullanim": ("uygulama", 1, ()),
}
KAYIT = 9


def main() -> int:
    ok, n, neden = dosya_dogrula(ORNEK, CIHAZ, "b7d1e4a2-93c5-4f08-a1b6-2d8e5c3f7a90")
    assert ok and n == KAYIT, f"dosya_dogrula: ok={ok} kayit={n} neden={neden!r}"
    with tempfile.TemporaryDirectory() as d:
        hub = Hub.open(Path(d), write=True)
        try:
            r = run(hub, ORNEK, "android_giden")
            assert r.added == KAYIT and r.duplicate == 0, f"ilk alim: eklenen={r.added} yinelenen={r.duplicate}"
            olaylar = hub.timeline(limit=100)
            assert len(olaylar) == KAYIT, len(olaylar)
            for e in olaylar:
                tur = e.kind.removeprefix("android.")
                assert tur in BEKLENEN, f"bilinmeyen tur {e.kind}"
                kat, onem, hassas = BEKLENEN[tur]
                assert (e.category, e.onem, tuple(e.hassas_konu)) == (kat, onem, hassas), \
                    f"{e.kind}: kategori/onem/hassas = {(e.category, e.onem, tuple(e.hassas_konu))}"
                assert e.device_id == CIHAZ
            assert {e.kind.removeprefix("android.") for e in olaylar} == set(BEKLENEN)
            r2 = run(hub, ORNEK, "android_giden")
            assert r2.added == 0 and r2.duplicate == KAYIT, f"ikinci alim: eklenen={r2.added}"
        finally:
            hub.close()
    print(f"SOZLESME TAMAM: dosya_dogrula ok kayit={KAYIT}; icerik 9 olay; tur/kategori/onem/hassas dogru; 2. alim 0 yeni")
    return 0


if __name__ == "__main__":
    sys.exit(main())
