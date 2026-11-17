"""Ses motoru yönetimi: Python bulma (sahte `python`u atlama), kısa/uzun/bozuk ses reddi, kurulu değilken açık hata."""
import base64

import pytest

from kimlikwin import ses
from kimlikwin.ses import SesHatasi, SesMotoru


def pcm_b64(saniye):
    return base64.b64encode(b"\x00\x00" * int(16000 * saniye)).decode()


def test_bul_python_calismayan_adayi_atlar(monkeypatch):
    cagrilan = []

    def sahte(komut, kod):
        cagrilan.append(komut)
        if komut == ["python"]:                       # Microsoft Store sahte python: çıktı yok
            return type("R", (), {"returncode": 9009, "stdout": "", "stderr": "Python bulunamadı"})()
        if komut == ["py", "-3"]:
            return type("R", (), {"returncode": 0, "stdout": "313\n", "stderr": ""})()
        return None
    monkeypatch.setattr(ses, "python_adaylari", lambda: [["python"], ["py", "-3"]])
    monkeypatch.setattr(ses, "_calisir_mi", sahte)
    assert ses.bul_python() == ["py", "-3"] and cagrilan[0] == ["python"]


def test_eski_python_kabul_edilmez(monkeypatch):
    monkeypatch.setattr(ses, "python_adaylari", lambda: [["python"]])
    monkeypatch.setattr(ses, "_calisir_mi", lambda k, c: type("R", (), {"returncode": 0, "stdout": "308\n", "stderr": ""})())
    assert ses.bul_python() is None


@pytest.mark.parametrize("veri,kod", [("!!!bozuk!!!", "veri"), (pcm_b64(0.1), "kisa"), (pcm_b64(25), "uzun")])
def test_gecersiz_ses_reddedilir(tmp_path, veri, kod):
    with pytest.raises(SesHatasi) as e:
        SesMotoru(tmp_path).tani(veri)
    assert e.value.kod == kod


def test_motor_yokken_acik_hata(tmp_path, monkeypatch):
    monkeypatch.setattr(ses, "bul_python", lambda: None)
    with pytest.raises(SesHatasi) as e:
        SesMotoru(tmp_path).tani(pcm_b64(1))
    assert e.value.kod == "motor_yok"


def test_durum_python_yoksa_yazarak_aramayi_soyler(tmp_path, monkeypatch):
    monkeypatch.setattr(ses, "bul_python", lambda: None)
    d = SesMotoru(tmp_path).durum()
    assert d["python_var"] is False and d["motor_kurulu"] is False and "Yazarak" in d["aciklama"]


def test_calisan_betik_gecerli_python():
    compile(ses.CALISAN_KAYNAK, "ses_calisan.py", "exec")
