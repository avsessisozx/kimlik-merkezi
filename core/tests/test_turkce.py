import pytest

from kimlikcore import EventIn, fold
from kimlikcore.turkish import build_fts_query


def put(hub, *texts, category="notlar"):
    sid = hub.add_source("test", "1", None)
    hub.add_events(sid, [
        EventIn(event_key=f"k{i}", ts="2026-01-01T00:00:00Z", kind="t", category=category, text=t)
        for i, t in enumerate(texts)
    ])
    return sid


@pytest.mark.parametrize("a,b", [("ışık", "ISIK"), ("İstanbul", "istanbul"), ("Işık", "isik"),
                                 ("ÇĞŞÖÜ", "çğşöü"), ("çğşöü", "cgsou"), ("DİYARBAKIR", "diyarbakır")])
def test_fold_esit(a, b):
    assert fold(a) == fold(b)


def test_fold_ornekler():
    assert fold("İSTANBUL ışık") == "istanbul isik"
    assert fold("ÇĞŞÖÜ çğşöü") == "cgsou cgsou"
    assert fold("Ağrı") == "agri"


def test_isik_ISIK(hub):
    put(hub, "Odada ışık yanıyor", "Güneş ISIK verir", "ilgisiz kayıt")
    a = {e.text for e in hub.search("ışık")}
    b = {e.text for e in hub.search("ISIK")}
    c = {e.text for e in hub.search("Işık")}
    assert a == b == c and len(a) == 2


def test_istanbul(hub):
    put(hub, "İstanbul'a gittik", "istanbul boğazı", "ISTANBUL", "Ankara")
    r1 = {e.text for e in hub.search("İstanbul")}
    r2 = {e.text for e in hub.search("istanbul")}
    assert r1 == r2 and len(r1) == 3


def test_cgsou(hub):
    put(hub, "çğşöü harfleri", "CGSOU yazıldı", "ÇĞŞÖÜ büyük", "baska")
    assert len(hub.search("çğşöü")) == 3
    assert len(hub.search("ÇĞŞÖÜ")) == 3
    assert len(hub.search("cgsou")) == 3


def test_tumce_ve_onek_ve_VE(hub):
    put(hub, "kırmızı elma ağacı", "elma kırmızı", "yeşil armut")
    assert len(hub.search('"kırmızı elma"')) == 1
    assert len(hub.search("elma kırmızı")) == 2  # VE
    assert len(hub.search("ağa*")) == 1
    assert len(hub.search("ağa")) == 0
    assert len(hub.search("arm", prefix=True)) == 1


def test_fts_islec_enjeksiyonu_zararsiz(hub):
    put(hub, "normal kayıt", "baska kayit")
    for q in ['kayıt OR', 'NEAR(a b)', 'text:kayıt', '"açık tırnak', "a AND", "***", "", "   ", "-x", "(", ")"]:
        hub.search(q)  # hata vermemeli
    assert hub.search("") == []


def test_sorgu_cikarimi():
    assert build_fts_query("ISIK") == '"isik"'
    assert build_fts_query('"iki kelime" x*') == '"iki kelime" "x"*'
    assert build_fts_query("e-posta") == '"e posta"'
    assert build_fts_query("!!!") is None


def test_kategori_filtresi(hub):
    sid = hub.add_source("t", "1", None)
    hub.add_events(sid, [
        EventIn(event_key="a", ts="2026-01-01T00:00:00Z", kind="x", category="notlar", text="ortak sözcük"),
        EventIn(event_key="b", ts="2026-01-01T00:00:00Z", kind="x", category="video", text="ortak sözcük"),
    ])
    assert len(hub.search("ortak")) == 2
    assert [e.category for e in hub.search("ortak", categories=["video"])] == ["video"]
    assert hub.search("ortak", categories=[]) == []
