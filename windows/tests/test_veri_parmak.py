"""CI 'üstüne kurulum' adımının kullandığı parmak izi aracı (windows/paket/veri_parmak.py) gerçekten fark yakalıyor mu."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "paket"))
import veri_parmak as VP  # noqa: E402


@pytest.fixture
def klasor(tmp_path):
    v = tmp_path / "veri"
    (v / "arsiv").mkdir(parents=True)
    (v / "kimlik.db").write_bytes(b"SQLite" * 100)
    (v / "arsiv" / "a.zip").write_bytes(b"zip")
    ayar = tmp_path / "ayar"
    ayar.mkdir()
    (ayar / "ayarlar.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _yaz(k):
    return VP.main(["yaz", str(k / "iz.json"), str(k / "veri"), str(k / "ayar" / "ayarlar.json")])


def test_degismeyen_klasor_gecer(klasor):
    assert _yaz(klasor) == 0 and VP.main(["denetle", str(klasor / "iz.json")]) == 0


@pytest.mark.parametrize("islem", ["degistir", "sil", "ekle", "ayar"])
def test_her_fark_yakalanir(klasor, islem):
    assert _yaz(klasor) == 0
    v = klasor / "veri"
    if islem == "degistir":
        (v / "kimlik.db").write_bytes(b"SQLite" * 100 + b"!")
    elif islem == "sil":
        (v / "arsiv" / "a.zip").unlink()
    elif islem == "ekle":
        (v / "yeni.txt").write_text("x", encoding="utf-8")
    else:
        (klasor / "ayar" / "ayarlar.json").write_text('{"a": 1}', encoding="utf-8")
    assert VP.main(["denetle", str(klasor / "iz.json")]) == 1


def test_bos_ya_da_yanlis_klasorde_parmak_izi_alinmaz(tmp_path):
    (tmp_path / "bos").mkdir()
    assert VP.main(["yaz", str(tmp_path / "iz.json"), str(tmp_path / "bos")]) == 1      # kimlik.db yok: sahte 'geçti' olmasın
    assert VP.main(["yaz", str(tmp_path / "iz.json"), str(tmp_path / "yok")]) == 1
