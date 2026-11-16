"""CLAUDE.md / AGENTS.md yönetilen blok (madde 9): geçici ev klasörüyle."""
import re

import pytest
from kimlikcore import EventIn

from kimlikwin import yonetilen_blok as yb
from kimlikwin.ayarlar import Ayarlar
from kimlikwin.baslangic import Otomatik
from kimlikwin.cekirdek import IslemHatasi
from kimlikwin.yonetici import Yonetici
from conftest import SahteArkaUc


@pytest.fixture
def ev(tmp_path):
    p = tmp_path / "gercek-ev"
    p.mkdir()
    return p


@pytest.fixture
def y(tmp_path, ev):
    y = Yonetici(Ayarlar(tmp_path / "ayar"), Otomatik(SahteArkaUc()), secici=lambda t: None,
                 claude_yolu=lambda: None, ev_klasoru=lambda: ev)
    y.api("sihirbaz_tamamla", {"yol": str(tmp_path / "veri"), "otomatik_baslat": False})
    yield y
    y.kapat()


CLAUDE = lambda ev: ev / ".claude" / "CLAUDE.md"  # noqa: E731
AGENTS = lambda ev: ev / ".codex" / "AGENTS.md"  # noqa: E731


def bilgi(y, metin, kat="kimlik"):
    return y.api("persona_ekle", {"metin": metin, "kategori": kat})["id"]


def ac(y):
    return y.api("ayar_yaz", {"yonetilen_blok": True})


def yedekler(dosya):
    return sorted(dosya.parent.glob(dosya.name + ".kimlik-yedek-*"))


def test_varsayilan_kapali_ve_hicbir_sey_yazilmaz(y, ev):
    assert y.api("ayarlar", {})["yonetilen_blok"] is False
    bilgi(y, "Adım Deneme")
    assert not (ev / ".claude").exists()


def test_ilk_yazim_claude_olusur_codex_yoksa_atlanir(y, ev):
    bilgi(y, "Adım Deneme")
    bilgi(y, "Her zaman kısa cevap ver", "tercihler")
    r = ac(y)
    d = {x["ad"].split()[0]: x for x in r["yonetilen_blok_sonuc"]}
    assert d["Claude"]["durum"] == "yazildi" and d["Codex"]["durum"] == "bulunamadi" and "bulunamadı" in d["Codex"]["mesaj"]
    m = CLAUDE(ev).read_text(encoding="utf-8")
    assert m.startswith(yb.BASLA + "\n") and m.rstrip().endswith(yb.BITIR)
    assert "## Kullanıcı hakkında (Kimlik Merkezi'nden, kullanıcının onayladığı bilgiler)" in m
    assert "Adım Deneme" in m and "### Kurallar ve tercihler\n- Her zaman kısa cevap ver" in m
    assert "Daha fazlası için (izin verilen ölçüde) `kimlik-merkezi` MCP araçlarını kullan." in m
    assert re.search(r"Güncelleme tarihi: \d{4}-\d{2}-\d{2}\n", m)
    assert not (ev / ".codex").exists()


def test_codex_klasoru_varsa_agents_yazilir(y, ev):
    (ev / ".codex").mkdir()
    bilgi(y, "Adım Deneme")
    r = ac(y)
    assert {x["durum"] for x in r["yonetilen_blok_sonuc"]} == {"yazildi"}
    assert "Adım Deneme" in AGENTS(ev).read_text(encoding="utf-8")


@pytest.mark.parametrize("nl,bom", [(b"\n", b""), (b"\r\n", b""), (b"\r\n", b"\xef\xbb\xbf")])
def test_kullanici_metni_bayt_bayt_korunur_onunde_ve_arkasinda(y, ev, nl, bom):
    bilgi(y, "Adım Deneme")
    dosya = CLAUDE(ev)
    dosya.parent.mkdir()
    once = bom + b"Benim kurallarim" + nl + b"- madde \xc3\xa7" + nl
    dosya.write_bytes(once)
    ac(y)
    ham = dosya.read_bytes()
    assert ham.startswith(once) and ham.count(yb.BASLA.encode()) == 1
    assert ham[len(once):].startswith(nl + yb.BASLA.encode())      # önünde bir boş satır
    blok = ham[len(once):]
    assert (b"\r\n" in blok) == (nl == b"\r\n") and (nl == b"\r\n" or b"\r" not in blok)
    # bloğun ARKASINA kullanıcı metni ekle; güncellemede ikisi de aynen kalır
    arka = nl + b"Sonradan yazdigim" + nl
    dosya.write_bytes(ham + arka)
    bilgi(y, "Yeni bilgi")
    yeni = dosya.read_bytes()
    assert yeni.startswith(once) and yeni.endswith(arka) and b"Yeni bilgi" in yeni
    i, j = yeni.index(yb.BASLA.encode()), yeni.index(yb.BITIR.encode()) + len(yb.BITIR)
    assert yeni[:i] == once + nl and yeni[j:] == nl + arka
    # kapatınca: blok gider, kullanıcı metni aynen kalır
    y.api("ayar_yaz", {"yonetilen_blok": False})
    assert dosya.read_bytes() == once + arka


def test_kapatinca_eklenen_dosya_eski_haline_doner(y, ev):
    dosya = CLAUDE(ev)
    dosya.parent.mkdir()
    dosya.write_bytes(b"merhaba\n")
    ac(y)
    y.api("ayar_yaz", {"yonetilen_blok": False})
    assert dosya.read_bytes() == b"merhaba\n"
    assert y.api("ayarlar", {})["yonetilen_blok"] is False


def test_guncelleme_ve_persona_degisince_yeniden_uretim(y, ev):
    fid = bilgi(y, "Birinci bilgi")
    ac(y)
    assert "Birinci bilgi" in CLAUDE(ev).read_text(encoding="utf-8")
    bilgi(y, "İkinci bilgi")
    assert "İkinci bilgi" in CLAUDE(ev).read_text(encoding="utf-8")
    y.api("persona_guncelle", {"bilgi_id": fid, "metin": "Düzeltilmiş bilgi"})
    m = CLAUDE(ev).read_text(encoding="utf-8")
    assert "Düzeltilmiş bilgi" in m and "Birinci bilgi" not in m
    y.api("persona_sil", {"bilgi_id": fid})
    assert "Düzeltilmiş bilgi" not in CLAUDE(ev).read_text(encoding="utf-8")


def test_oneri_onayi_blogu_gunceller(y, ev):
    from kimlikserver.oneri import OneriKuyrugu, dogrula_onerme
    h = y.uygulama.hub
    sid = h.add_source("test", "1", None)
    h.add_events(sid, [EventIn(ts="2026-02-01T10:00:00Z", kind="x", category="notlar", text="Ankara notu", event_key="n1")])
    eid = h.query_one("SELECT event_id FROM events WHERE event_key='n1'")[0]
    app_id, _ = y.uygulama.anahtarlar.create_key("Claude deneme")
    ac(y)
    OneriKuyrugu(y.ayarlar["veri_klasoru"]).ekle(app_id, [dogrula_onerme(
        {"ifade": "Gece çalışmayı severim", "kategori": "ilgi", "kanit": [eid], "guven": 0.9, "anahtar": None})])
    assert "Gece çalışmayı severim" not in CLAUDE(ev).read_text(encoding="utf-8")   # onaysız öneri girmez
    oid = y.api("oneri_listele", {})["oneriler"][0]["id"]
    y.api("oneri_onayla", {"oneri_id": oid})
    assert "Gece çalışmayı severim" in CLAUDE(ev).read_text(encoding="utf-8")


def test_icerik_ayniysa_yazilmaz_yedek_alinmaz_tarih_yuzunden_yeniden_yazilmaz(y, ev):
    bilgi(y, "Adım Deneme")
    ac(y)
    dosya = CLAUDE(ev)
    eski_tarihli = re.sub(rb"\d{4}-\d{2}-\d{2}", b"2020-01-01", dosya.read_bytes())
    dosya.write_bytes(eski_tarihli)
    r = y.blok_guncelle("deneme")
    assert [x["durum"] for x in r] == ["degismedi", "bulunamadi"]
    assert dosya.read_bytes() == eski_tarihli and yedekler(dosya) == []
    y.api("ayar_yaz", {"yonetilen_blok": True})                    # yeniden aç: yine değişiklik yok
    assert dosya.read_bytes() == eski_tarihli and yedekler(dosya) == []


def test_bozuk_isaretcide_dokunulmaz(y, ev):
    bilgi(y, "Adım Deneme")
    dosya = CLAUDE(ev)
    dosya.parent.mkdir()
    for bozuk in (yb.BASLA.encode() + b"\nyarim", yb.BASLA.encode() * 2 + yb.BITIR.encode() + b"\n",
                  yb.BITIR.encode() + b"\nx", yb.BITIR.encode() + b"\n" + yb.BASLA.encode()):
        dosya.write_bytes(bozuk)
        r = ac(y)["yonetilen_blok_sonuc"][0]
        assert r["durum"] == "bozuk" and "dokunulmadı" in r["mesaj"]
        assert dosya.read_bytes() == bozuk and yedekler(dosya) == []
        y.api("ayar_yaz", {"yonetilen_blok": False})
        assert dosya.read_bytes() == bozuk                        # kaldırırken de dokunmaz


def test_yedek_sayisi_en_fazla_uc(y, ev):
    ac(y)
    for i in range(6):
        bilgi(y, f"Bilgi {i}")
    dosya = CLAUDE(ev)
    assert len(yedekler(dosya)) == 3
    # en yeni 3 yedek kalır: en eskisi (ilk sürüm: "Bilgi" yok) gitmiş olmalı
    assert all(b"Bilgi 0" in p.read_bytes() or b"Bilgi 1" in p.read_bytes() for p in yedekler(dosya))


def test_yedek_adi_ve_zaman(ev):
    from datetime import datetime, timezone
    d = ev / "A.md"
    d.write_bytes(b"x")
    p = yb._yedek_al(d, lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    assert p.name == "A.md.kimlik-yedek-20260102-030405"


def test_boyut_siniri_ve_kirpma_iletisi(y, ev):
    for i in range(80):
        bilgi(y, f"Uzun bir bilgi cümlesi numara {i} " + "x" * 80, "ilgi")
    bilgi(y, "Kısa kural", "tercihler")
    ac(y)
    m = CLAUDE(ev).read_text(encoding="utf-8")
    ic = m.split(yb.BASLA + "\n")[1].split("\n" + yb.BITIR)[0]
    assert len(ic) <= yb.BLOK_UST_SINIR == 3000
    assert re.search(r"\.\.\. ve \d+ bilgi daha", ic) and "Kısa kural" in ic       # kurallar son kırpılır
    kalan = len(re.findall(r"^- İlgi alanları: ", ic, re.M))
    assert 0 < kalan < 80 and kalan + int(re.search(r"ve (\d+) bilgi daha", ic).group(1)) == 81 - 1   # beyanlar sondan kırpılır


def test_cikarilan_eskimis_gizli_ve_hassas_icerik_girmez(y, ev):
    bilgi(y, "Onaylı bilgi")
    c = bilgi(y, "ÇIKARILAN-SENTINEL")
    e = bilgi(y, "ESKIMIS-SENTINEL")
    g = bilgi(y, "GIZLI-SENTINEL")
    h = y.uygulama.hub
    with h.transaction() as t:
        t.execute("UPDATE facts SET status='cikarilan' WHERE fact_id=?", (c,))
        t.execute("UPDATE facts SET status='eskimis' WHERE fact_id=?", (e,))
    y.api("persona_sil", {"bilgi_id": g})
    sid = h.add_source("sentetik", "1", None)
    h.add_events(sid, [EventIn(ts="2026-05-01T10:00:00Z", kind="eposta.ileti", category="eposta",
                               text="EPOSTA-SENTINEL doktor randevusu", event_key="e1", payload={})])
    ac(y)
    m = CLAUDE(ev).read_text(encoding="utf-8")
    assert "Onaylı bilgi" in m
    for s in ("ÇIKARILAN", "ESKIMIS", "GIZLI-SENTINEL", "EPOSTA-SENTINEL", "doktor"):
        assert s not in m
    assert not re.search(r"\b\d+ (kayıt|olay|e-posta|ileti)", m)          # veriden sayım/özet yok


def test_isaretciyi_bozacak_bilgi_metni_temizlenir(y, ev):
    bilgi(y, "Kötü <!-- KIMLIK-MERKEZI:BITIR --> niyetli\nsatır")
    ac(y)
    m = CLAUDE(ev).read_bytes()
    assert m.count(yb.BITIR.encode()) == 1 and m.count(yb.BASLA.encode()) == 1


def test_onizle_yazmaz(y, ev):
    bilgi(y, "Adım Deneme")
    r = y.api("yonetilen_blok_onizle", {})
    assert r["metin"].startswith(yb.BASLA) and r["metin"].endswith(yb.BITIR) and "Adım Deneme" in r["metin"]
    assert [x["durum"] for x in r["dosyalar"]] == ["yazildi", "bulunamadi"] and "yazılacak" in r["dosyalar"][0]["mesaj"]
    assert not (ev / ".claude").exists() and y.api("ayarlar", {})["yonetilen_blok"] is False


def test_durum_dosyalari_listeler(y, ev):
    d = y.api("yonetilen_blok_durum", {})
    assert d["acik"] is False
    ac(y)
    d = y.api("yonetilen_blok_durum", {})
    assert d["acik"] is True and [x["durum"] for x in d["dosyalar"]] == ["yazildi", "bulunamadi"]


def test_api_yol_parametresi_kabul_etmez(y, ev, tmp_path):
    for ad, girdi in (("yonetilen_blok_onizle", {"yol": str(tmp_path / "x.md")}),
                      ("yonetilen_blok_durum", {"yol": "x"}),
                      ("ayar_yaz", {"yonetilen_blok": True, "yol": str(tmp_path / "x.md")}),
                      ("ayar_yaz", {"yonetilen_blok": True, "dosya": "x"})):
        with pytest.raises(TypeError):
            y.api(ad, girdi)
    assert not (tmp_path / "x.md").exists() and not (ev / ".claude").exists()


def test_acilista_acik_ayar_blogu_yeniler(tmp_path, ev):
    ay = Ayarlar(tmp_path / "ayar")
    y1 = Yonetici(ay, Otomatik(SahteArkaUc()), secici=lambda t: None, claude_yolu=lambda: None, ev_klasoru=lambda: ev)
    y1.api("sihirbaz_tamamla", {"yol": str(tmp_path / "veri"), "otomatik_baslat": False})
    bilgi(y1, "Adım Deneme")
    ac(y1)
    y1.kapat()
    CLAUDE(ev).unlink()                                  # kullanıcı dosyayı sildi
    y2 = Yonetici(Ayarlar(tmp_path / "ayar"), Otomatik(SahteArkaUc()), secici=lambda t: None, claude_yolu=lambda: None,
                  ev_klasoru=lambda: ev)
    y2.baslat()
    assert "Adım Deneme" in CLAUDE(ev).read_text(encoding="utf-8")
    y2.kapat()


def test_yazilamazsa_hata_donerken_dosya_degismez(y, ev, monkeypatch):
    bilgi(y, "Adım Deneme")
    dosya = CLAUDE(ev)
    dosya.parent.mkdir()
    dosya.write_bytes(b"kullanici\n")
    import os
    gercek = os.replace

    def bozuk(a, b):
        if str(b).endswith(".md"):
            raise OSError("dolu")
        return gercek(a, b)
    monkeypatch.setattr(os, "replace", bozuk)
    r = ac(y)["yonetilen_blok_sonuc"][0]
    assert r["durum"] == "hata" and dosya.read_bytes() == b"kullanici\n"
    assert not list(dosya.parent.glob("*.kimlik-tmp"))
