"""`parola-ekle` onay istemi ve reddi: kullanıcıya tam olarak ne yazacağı açıkça söylenir
(rapor bulgusu: 'evet' yazınca neden olmadığı anlaşılmıyordu)."""
import builtins

import pytest
from kimlikcore import cli, sifreleme as sif

IFADE = "mavi bisikletle sahil yolunda sabah kahvesi içtim"


@pytest.fixture(autouse=True)
def ortam(monkeypatch):
    monkeypatch.setattr(sif, "KDF_N", 1 << 4)
    monkeypatch.setenv(sif.ENV_SAHTE, "cli-onay-testi")
    monkeypatch.delenv(sif.ENV_PAROLA, raising=False)
    sif.saglayici_ayarla(None)


def test_parola_ekle_istemi_buyuk_harfle_ANLADIM_der_ve_evet_reddedilir(root, monkeypatch, capsys):
    cli.main(["--veri", str(root), "baslat"])
    capsys.readouterr()
    girdiler = [IFADE, IFADE]
    monkeypatch.setattr(cli, "_gizli_oku", lambda istem: girdiler.pop(0))
    istemler: list[str] = []

    def sahte_input(istem=""):
        istemler.append(istem)
        return "evet"

    monkeypatch.setattr(builtins, "input", sahte_input)
    rc = cli.main(["--veri", str(root), "parola-ekle"])
    c = capsys.readouterr()
    assert rc == 1
    assert len(istemler) == 1 and "büyük harflerle ANLADIM" in istemler[0]
    assert "Onaylanmadı" in c.err and "ANLADIM" in c.err and "büyük harflerle" in c.err
