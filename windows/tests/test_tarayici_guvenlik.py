"""Güvenlik sayfası ve açılış kilit ekranı için GERÇEK TARAYICI testi (Playwright + Chromium).

Kurulum/atlama kuralları test_tarayici.py ile aynı (node + playwright + Chromium yoksa atlanır;
KIMLIK_TARAYICI_ZORUNLU=1 ise kırmızı olur). Ekran görüntüsü için KIMLIK_EKRAN_DIZINI verilirse
`guvenlik-*.png` dosyaları oraya yazılır. Sahte anahtar sağlayıcısı kullanılır (DPAPI yok)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from kimlikcore import sifreleme as sif
from kimlikwin.ayarlar import Ayarlar
from kimlikwin.baslangic import Otomatik
from kimlikwin.web import Sunucu
from kimlikwin.yonetici import Yonetici

sys.path.insert(0, str(Path(__file__).parent))
from test_tarayici import _atla, _node_ortami  # noqa: E402

BETIK = Path(__file__).parent / "tarayici" / "guvenlik.js"
IFADE = "mavi bulut sabah ruzgari kasim 4817"
PAROLA = "Sizinti-parola-7391-xyz"
YENI_PAROLA = "Baska-parola-5520-qwe"


class _AU:
    d = None

    def oku(self): return self.d
    def yaz(self, k): self.d = k
    def sil(self): self.d = None


class Saat:
    t = 1000.0

    def __call__(self):
        return self.t


def _yonetici(ayar_dizin):
    return Yonetici(Ayarlar(ayar_dizin), Otomatik(_AU()), secici=lambda t: None, claude_yolu=lambda: None)


def _calistir(mod, ayar_yolu):
    p = subprocess.run([shutil.which("node"), str(BETIK), str(ayar_yolu), mod], capture_output=True, text=True,
                       timeout=240, env=_node_ortami())
    if p.returncode == 77:
        _atla("Playwright/Chromium yok: " + p.stderr.strip()[:200])
    assert p.returncode == 0, p.stderr[-3000:]
    return json.loads(p.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def sonuclar(tmp_path_factory):
    if not shutil.which("node"):
        _atla("node kurulu değil")
    kok = tmp_path_factory.mktemp("guvenlik_tarayici")
    os.environ["KIMLIK_AYAR_DIZINI"] = str(kok / "ayar")
    mp = pytest.MonkeyPatch()
    mp.setattr(sif, "KDF_N", 1 << 4)
    sif.saglayici_ayarla(sif.SahteSaglayici("tarayici"))
    saat = Saat()
    veri = kok / "veri"
    ayar = {"ifade": IFADE, "parola": PAROLA, "yeni_parola": YENI_PAROLA,
            "ekran_dizini": os.environ.get("KIMLIK_EKRAN_DIZINI")}
    if ayar["ekran_dizini"]:
        Path(ayar["ekran_dizini"]).mkdir(parents=True, exist_ok=True)
    out: dict = {}
    sunucular = []

    def sun(y):
        y.guvenlik.sinir._saat = saat
        s = Sunucu(y, 0)
        s.baslat()
        sunucular.append((s, y))
        ayar["url"] = s.url
        yol = kok / "ayar.json"
        yol.write_text(json.dumps(ayar), encoding="utf-8")
        return yol

    try:
        y = _yonetici(kok / "ayar")
        y.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False})
        y.api("persona_ekle", {"metin": "Çay severim", "kategori": "tercihler"})
        yol = sun(y)
        out["akis"] = _calistir("akis", yol)
        out["akis_durum"] = y.api("guvenlik_durum", {})
        for s, yy in sunucular:
            s.durdur()
            yy.kapat()
        sunucular.clear()

        y2 = _yonetici(kok / "ayar")
        y2.baslat()
        out["kilitli"] = y2.kilit is not None
        yol = sun(y2)
        out["kilit_yanlis"] = _calistir("kilit-yanlis", yol)
        saat.t += 1000
        out["kilit_dogru"] = _calistir("kilit-dogru", yol)
        out["acildi_sonra"] = y2.uygulama is not None
        for s, yy in sunucular:
            s.durdur()
            yy.kapat()
        sunucular.clear()

        y3 = _yonetici(kok / "ayar")
        y3.baslat()
        yol = sun(y3)
        out["kilit_kurtar"] = _calistir("kilit-kurtar", yol)
        out["kurtar_sonra"] = y3.api("guvenlik_durum", {})
        persona = json.dumps(y3.api("persona_liste", {}), ensure_ascii=False)
        out["veri_duruyor"] = "Çay severim" in persona
        out["donusum"] = _calistir("donusum", yol)
        out["donusum_sonra"] = y3.api("guvenlik_durum", {})
        persona2 = json.dumps(y3.api("persona_liste", {}), ensure_ascii=False)
        out["veri_duruyor_donusumden_sonra"] = "Çay severim" in persona2
        for s_, yy in sunucular:
            s_.durdur()
            yy.kapat()
        sunucular.clear()

        # ilk açılış sihirbazı: yeni (boş) ayar dizini
        os.environ["KIMLIK_AYAR_DIZINI"] = str(kok / "ayar2")
        y4 = _yonetici(kok / "ayar2")
        ayar["sihirbaz_yol"] = str(kok / "yeni-veri")
        yol = sun(y4)
        out["sihirbaz"] = _calistir("sihirbaz", yol)
        out["sihirbaz_durum"] = y4.api("guvenlik_durum", {})
        yield out
    finally:
        for s, yy in sunucular:
            s.durdur()
            yy.kapat()
        sif.saglayici_ayarla(None)
        mp.undo()


def test_guvenlik_sayfasi_durumu_gosterir(sonuclar):
    a = sonuclar["akis"]
    m = a["durum_metin"]
    assert "Şifreleme durumu" in m and "KURULU DEĞİL" in m and "açık" in m
    assert a["parola_ekle_dugmesi"] == 1


def test_ifade_kurallari_mesajlari(sonuclar):
    a = sonuclar["akis"]
    assert a["ileri_bos"] is True
    assert "tahmin edilebilir" in a["zayif_metin"] and a["zayif_ileri_kapali"]
    assert "En az 4 kelime" in a["kisa_metin"] and a["kisa_ileri_kapali"]
    assert "İki giriş aynı değil" in a["farkli_metin"] and a["farkli_ileri_kapali"]
    assert "Kurallara uyuyor" in a["iyi_metin"] and a["iyi_ileri_acik"]
    assert "Güç göstergesi" in a["guc_metin"] and "sezgisel" in a["guc_metin"]
    assert a["ifade_tipi"] == "password"


def test_onay_kutusu_zorunlu_ve_kurtarilamaz_uyarisi_acik(sonuclar):
    a = sonuclar["akis"]
    assert "KURTARILAMAZ" in a["uyari_metin"] and "KİMSE" in a["uyari_metin"]
    assert "Claude" in a["mcp_uyari"] and "parola" in a["mcp_uyari"].lower()
    assert a["devam_onaysiz_kapali"] is True
    assert a["devam_onayli_acik"] is True
    assert a["devam_onay_kalkinca_kapali"] is True


def test_parola_adimi_ve_sonuc(sonuclar):
    a = sonuclar["akis"]
    assert a["ifade_kuruldu"] == 1 and a["kaydet_bos_kapali"] is True
    assert "en az 10" in a["kisa_parola"] and a["kisa_parola_kapali"]
    assert "İki giriş aynı değil" in a["farkli_parola"] and a["farkli_parola_kapali"]
    assert a["parola_acik"] is True
    assert a["parola_dugmeleri"] == [1, 1]
    assert "Parolayı kaldır" in a["sonra_metin"] and "kuruldu" in a["sonra_metin"]
    d = sonuclar["akis_durum"]
    assert d["parola_var"] and d["kurtarma_var"] and not d["os_korumasi"]


def test_sayfa_hatasiz_ve_tasmasiz(sonuclar):
    a = sonuclar["akis"]
    assert a["bildirimler"] == [] and a["konsol"] == []
    for k in ("tasma_masaustu", "tasma_mobil", "tasma_mobil_pencere"):
        assert a[k]["belge"] <= 0 and a[k]["ogeler"] == [], (k, a[k])


def test_acilista_kilit_ekrani_ve_yavaslatma(sonuclar):
    assert sonuclar["kilitli"] is True
    k = sonuclar["kilit_yanlis"]
    assert "kilitli" in k["baslik"] and k["nav_bos"] == 0 and k["ana_icerik"] == 0
    assert "Parola yanlış" in k["hata0"] and "Parola yanlış" in k["hata1"]
    assert "Parola yanlış" in k["hata2"] and "saniye bekleyin" in k["hata2"]
    assert "Bekleyin" in k["dugme_metni"] and k["dugme_kapali"] is True
    assert k["konsol"] == []


def test_dogru_parola_uygulamayi_acar(sonuclar):
    k = sonuclar["kilit_dogru"]
    assert k["kilit_kalkti"] and k["parola_alani_yok"] and "Güvenlik" in k["nav"]
    assert sonuclar["acildi_sonra"] and k["bildirimler"] == []


def test_kilit_ekraninda_kurtarma_ifadesiyle_acma(sonuclar):
    k = sonuclar["kilit_kurtar"]
    assert "Kurtarma ifadesi yanlış" in k["yanlis_ifade"]
    assert k["acildi"] and k["bildirimler"] == []
    d = sonuclar["kurtar_sonra"]
    assert d["parola_var"] and not d["os_korumasi"]
    assert sonuclar["veri_duruyor"]


def test_sifreleme_kapat_ac_arayuzden(sonuclar):
    d = sonuclar["donusum"]
    assert "DÜZ METİN" in d["kapat_metin"] and "KALDIR" in d["kapat_metin"] and "dakikalar" in d["kapat_metin"]
    assert d["basta_kapali"] and d["onaysiz_kapali"] and d["onayli_acik"] and d["kucuk_harf_kapali"]
    assert "tamamlandı" in d["kapat_sonuc"]
    assert "KAPALI" in d["kapali_metin"] and "düz metin" in d["kapali_metin"]
    assert d["ac_basta_kapali"] and "tamamlandı" in d["ac_sonuc"]
    assert "açık" in d["acik_metin"] and "KAPALI" not in d["acik_metin"].split("Şifreleme durumu")[1][:200]
    assert d["bildirimler"] == [] and d["konsol"] == []
    s = sonuclar["donusum_sonra"]
    assert s["sifreli"] and s["os_korumasi"] and not s["parola_var"] and not s["kurtarma_var"]
    assert sonuclar["veri_duruyor_donusumden_sonra"]


def test_sihirbaz_sifrelemenin_varsayilan_acik_oldugunu_soyler(sonuclar):
    w = sonuclar["sihirbaz"]
    assert "Şifreleme varsayılan olarak AÇIK" in w["adim1"] and "Güvenlik sayfasından parola ekleyebilirsiniz" in w["adim1"]
    assert "Şifreleme AÇIK" in w["adim3"] and "parola ekleyebilirsiniz" in w["adim3"]
    assert w["konsol"] == []
    assert sonuclar["sihirbaz_durum"]["sifreli"]
