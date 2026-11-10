"""Tarayıcısız statik denetim: ortak.js'teki tek tanımlar başka betikte yeniden bildirilmemeli ve yükleme sırası doğru olmalı.
(Asıl koruma test_tarayici.py'deki gerçek tarayıcı testidir; bu, onun çalışamadığı yerde de ucuz bir ağdır.)"""
import re
from pathlib import Path

STATIK = Path(__file__).resolve().parents[1] / "src" / "kimlikwin" / "statik"


def _metin(ad):
    return (STATIK / ad).read_text(encoding="utf-8")


def _ortak_adlar():
    return re.findall(r"^(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)", _metin("ortak.js"), re.M)


def test_ortak_js_SAYI_tanimlar():
    assert "SAYI" in _ortak_adlar()


def test_ortak_adlar_baska_yerde_yeniden_bildirilmez():
    for ad in _ortak_adlar():
        kalip = re.compile(rf"\b(?:const|let|var|function)\s+{re.escape(ad)}\b")
        for dosya in ("figur.js", "harita.js", "index.html"):
            assert not kalip.search(_metin(dosya)), f"{dosya} içinde {ad} yeniden bildirilmiş; tek tanım ortak.js'te olmalı"


def test_ortak_js_diger_betiklerden_once_yuklenir():
    html = _metin("index.html")
    sira = [html.index(f'src="/statik/{a}"') for a in ("ortak.js", "echarts.min.js", "figur.js", "harita.js")]
    assert sira == sorted(sira)
    assert html.index('src="/statik/harita.js"') < html.index("<script>\n\"use strict\";")   # satır içi betik en sona
