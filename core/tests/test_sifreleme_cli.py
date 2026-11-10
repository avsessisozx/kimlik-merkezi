"""Şifreleme CLI komutları (sahte sağlayıcı; süreç içi çağrı, parola girdisi taklit edilir)."""
import json
import os
import subprocess
import sys

import pytest
from kimlikcore import Hub, cli, sifreleme as sif

from util import known_events

IFADE = "mavi bisikletle sahil yolunda sabah kahvesi içtim"
PAROLA = "kuzey-ruzgari-9071"


@pytest.fixture(autouse=True)
def ortam(monkeypatch):
    monkeypatch.setattr(sif, "KDF_N", 1 << 4)
    monkeypatch.setenv(sif.ENV_SAHTE, "cli-testi")
    monkeypatch.delenv(sif.ENV_PAROLA, raising=False)
    sif.saglayici_ayarla(None)


@pytest.fixture
def calistir(root, monkeypatch, capsys):
    girdiler: list[str] = []

    def gizli(istem):
        assert girdiler, f"beklenmeyen istem: {istem}"
        return girdiler.pop(0)

    monkeypatch.setattr(cli, "_gizli_oku", gizli)
    monkeypatch.setattr(cli, "_evet_mi", lambda istem, beklenen: girdiler.pop(0) == beklenen
                        if girdiler else False)

    def run(*args, gir=(), kod=0):
        girdiler[:] = list(gir)
        rc = cli.main(["--veri", str(root), *map(str, args)])
        c = capsys.readouterr()
        assert rc == kod, (c.out, c.err)
        assert not girdiler, f"kullanılmayan girdi: {girdiler}"
        return c

    return run


def test_baslat_varsayilan_sifreli_ve_durum(calistir, root):
    c = calistir("baslat")
    assert "Şifreleme: şifreli" in c.out
    d = json.loads(calistir("--json", "durum").out)
    assert d["sifreli"] and d["os_korumasi"] and not d["parola_var"] and not d["kurtarma_var"]
    assert d["saglayici"] == "sahte"
    assert "SAHTE sağlayıcı" in calistir("durum").out
    assert "KURULU DEĞİL" in calistir("durum").out


def test_baslat_saglayici_yoksa_sifresiz_ve_uyarir(calistir, root, monkeypatch):
    monkeypatch.delenv(sif.ENV_SAHTE)
    if sys.platform == "win32":
        pytest.skip("Windows'ta DPAPI vardır")
    c = calistir("baslat")
    assert "ŞİFRESİZ oluşturuldu" in c.out
    assert not (root / "anahtar.json").exists()


def test_baslat_sifresiz_bayragi(calistir, root):
    c = calistir("baslat", "--sifresiz")
    assert "Şifreleme: şifresiz" in c.out and "--sifresiz" in c.out


def test_mevcut_sifresiz_klasor_acilir_ve_sifrelenir(calistir, root):
    calistir("baslat", "--sifresiz")
    with Hub.open(root, write=True) as h:
        sid = h.add_source("t", "1", None)
        h.add_events(sid, known_events(5))
    c = calistir("baslat")  # yeniden baslat: otomatik dönüştürmez, ipucu verir
    assert "kimlikmerkezi sifrele" in c.out
    assert not json.loads(calistir("--json", "durum").out)["sifreli"]
    calistir("sifrele")
    assert json.loads(calistir("--json", "durum").out)["sifreli"]
    assert "Sonuç yok" not in calistir("ara", "bulgu003zz").out
    calistir("sifreyi-kaldir", "--onayla")
    assert not json.loads(calistir("--json", "durum").out)["sifreli"]
    assert "Sonuç yok" not in calistir("ara", "bulgu003zz").out


def test_sifreyi_kaldir_onay_olmadan_yapilmaz(calistir, root):
    calistir("baslat")
    c = calistir("sifreyi-kaldir", kod=1)  # stdin tty değil
    assert "Onaylanmadı" in c.err
    assert json.loads(calistir("--json", "durum").out)["sifreli"]


def test_parola_ekle_kurtarma_kurdurur_ve_uyarir(calistir, root):
    calistir("baslat")
    c = calistir("parola-ekle", "--anladim", gir=[IFADE, IFADE, PAROLA, PAROLA])
    assert "KİMSE tarafından kurtarılamaz" in c.out        # açık uyarı
    assert "Güç göstergesi" in c.out and "Parola eklendi" in c.out
    d = json.loads(calistir("--json", "durum", ).out)
    assert d["parola_var"] and d["kurtarma_var"] and not d["os_korumasi"]


def test_parola_ekle_zayif_ifade_reddedilir_veri_degismez(calistir, root):
    calistir("baslat")
    c = calistir("parola-ekle", "--anladim",
                 gir=["kısa", "kısa", "password password password password",
                      "password password password password", "123 456", "123 456"], kod=1)
    assert "kurallara uymuyor" in c.err
    d = json.loads(calistir("--json", "durum").out)
    assert not d["parola_var"] and not d["kurtarma_var"] and d["os_korumasi"]


def test_parola_ekle_ifade_ikinci_giriste_eslesmezse(calistir):
    calistir("baslat")
    c = calistir("parola-ekle", "--anladim", gir=[IFADE, IFADE + " x"] * 3, kod=1)
    assert "aynı değil" in c.err


def test_parola_ekle_onaysiz_yapilmaz(calistir):
    calistir("baslat")
    calistir("kurtarma-kur", gir=[IFADE, IFADE])
    c = calistir("parola-ekle", gir=["evet-anladim"], kod=1)
    assert "Onaylanmadı" in c.err
    assert not json.loads(calistir("--json", "durum").out)["parola_var"]


def test_parola_ekle_parola_eslesmezse(calistir):
    calistir("baslat")
    calistir("kurtarma-kur", gir=[IFADE, IFADE])
    calistir("parola-ekle", "--anladim", gir=[PAROLA, PAROLA + "x"], kod=1)
    calistir("parola-ekle", "--anladim", gir=["kisa", "kisa"], kod=1)
    assert not json.loads(calistir("--json", "durum").out)["parola_var"]


def test_parolali_klasorde_yanlis_parola_reddi_ve_env(calistir, root, monkeypatch):
    calistir("baslat")
    calistir("parola-ekle", "--anladim", gir=[IFADE, IFADE, PAROLA, PAROLA])
    # tty yok -> parola sorulamaz -> açık hata (sessizce şifresiz açmaz)
    c = calistir("ozet", kod=1)
    assert "parolayla korunuyor" in c.err
    monkeypatch.setenv(sif.ENV_PAROLA, "yanlis-parola-123")
    assert "Parola yanlış" in calistir("ozet", kod=1).err
    monkeypatch.setenv(sif.ENV_PAROLA, PAROLA)
    calistir("ozet")


def test_etkilesimli_terminalde_parola_sorulur(calistir, root, monkeypatch):
    calistir("baslat")
    calistir("parola-ekle", "--anladim", gir=[IFADE, IFADE, PAROLA, PAROLA])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    calistir("ozet", gir=[PAROLA])
    calistir("ozet", gir=["yanlis-parola-123"], kod=1)
    monkeypatch.delenv(sif.ENV_PAROLA, raising=False)


def test_parola_kaldir(calistir, root, monkeypatch):
    calistir("baslat")
    calistir("parola-ekle", "--anladim", gir=[IFADE, IFADE, PAROLA, PAROLA])
    monkeypatch.setenv(sif.ENV_PAROLA, PAROLA)
    calistir("parola-kaldir")
    monkeypatch.delenv(sif.ENV_PAROLA)
    d = json.loads(calistir("--json", "durum").out)
    assert not d["parola_var"] and d["os_korumasi"] and d["kurtarma_var"]
    calistir("ozet")


def test_kurtar_yeni_parola_ve_yanlis_ifade(calistir, root, monkeypatch):
    calistir("baslat")
    calistir("parola-ekle", "--anladim", gir=[IFADE, IFADE, PAROLA, PAROLA])
    calistir("kurtar", "--yeni-parola", gir=["tamamen başka bir ifade deneme", "yeni-parola-9999",
                                             "yeni-parola-9999"], kod=1)
    c = calistir("kurtar", "--yeni-parola", gir=[IFADE.upper(), "yeni-parola-9999", "yeni-parola-9999"])
    assert "Yeni parola kuruldu" in c.out
    monkeypatch.setenv(sif.ENV_PAROLA, PAROLA)
    assert "Parola yanlış" in calistir("ozet", kod=1).err   # eski parola geçmez
    monkeypatch.setenv(sif.ENV_PAROLA, "yeni-parola-9999")
    calistir("ozet")


def test_kurtar_hesap_degisince_yeniden_baglar(calistir, root, monkeypatch):
    calistir("baslat")
    calistir("kurtarma-kur", gir=[IFADE, IFADE])
    with Hub.open(root, write=True) as h:
        sid = h.add_source("t", "1", None)
        h.add_events(sid, known_events(4))
    monkeypatch.setenv(sif.ENV_SAHTE, "baska-hesap")        # başka Windows hesabı / bilgisayar
    c = calistir("ozet", kod=1)
    assert "kurtar" in c.err.lower() or "Sahte" in c.err
    calistir("kurtar", gir=[IFADE])
    assert json.loads(calistir("--json", "ozet").out)["counts"]["event"] == 4


def test_cli_alt_surec_sahte_saglayici_ve_diskte_duz_metin_yok(tmp_path, child_env):
    """Gerçek süreçte uçtan uca: ice-al + ara; veritabanı dosyasında bilinen metin yok."""
    veri = tmp_path / "v"
    env = dict(child_env, **{sif.ENV_SAHTE: "alt-surec"})

    def run(*a):
        r = subprocess.run([sys.executable, "-m", "kimlikcore", "--veri", str(veri), *a], env=env,
                           capture_output=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        return r.stdout

    f = tmp_path / "g.jsonl"
    f.write_text(json.dumps({"ts": "2026-04-01T08:00:00Z", "kind": "k", "category": "notlar",
                             "payload": {"gizli": "benzersizsozcukpayload"},
                             "text": "CLI ışık benzersizsozcukmetin"}, ensure_ascii=False) + "\n", encoding="utf-8")
    run("baslat")
    run("ice-al", str(f), "--tur", "jsonl")
    assert "benzersizsozcukmetin" in run("ara", "ISIK")
    for dp, _d, fs in os.walk(veri):
        for n in fs:
            if n == "erisim.db":
                continue
            b = open(os.path.join(dp, n), "rb").read()
            for x in (b"benzersizsozcuk", "ışık".encode(), b"SQLite format"):
                assert x not in b, (n, x)
