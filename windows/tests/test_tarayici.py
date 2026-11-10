"""GERÇEK TARAYICI testi (Playwright + Chromium): her ana ekranı açar, hata bildirim kutusunu, konsolu,
içe aktar akışını, mobil taşmayı ve temayı denetler.

Neden var: 'SAYI is not defined' gibi bir betik hatası sunucu testlerinde görünmez (arayüz hatayı yakalayıp
bildirim kutusuna yazar, ekran boş kalır). Bu test o hatayı yakalar.

Çalışma koşulu: `node` + `playwright` (npm) + Chromium. Yoksa test ATLANIR (CI'da KIMLIK_TARAYICI_ZORUNLU=1
verilirse atlamak yerine KIRMIZI olur). Playwright'ın yeri: NODE_PATH ya da KIMLIK_PLAYWRIGHT_YOLU
(node_modules klasörü). Kurulum: `npm i playwright && npx playwright install chromium`."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from kimlikcore import Hub
from kimlikwin.ayarlar import Ayarlar
from kimlikwin.baslangic import Otomatik
from kimlikwin.web import Sunucu
from kimlikwin.yonetici import Yonetici

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "paket"))
import demo_veri  # noqa: E402

BETIK = Path(__file__).parent / "tarayici" / "gezinti.js"
FIX = Path(__file__).resolve().parents[2] / "importers" / "fixtures"
ZORUNLU = os.environ.get("KIMLIK_TARAYICI_ZORUNLU") == "1"


def _atla(neden: str):
    if ZORUNLU:
        pytest.fail("Tarayıcı testi zorunlu ama çalıştırılamadı: " + neden)
    pytest.skip(neden)


def _node_ortami() -> dict:
    env = dict(os.environ)
    yollar = [env.get("KIMLIK_PLAYWRIGHT_YOLU", ""), env.get("NODE_PATH", "")]
    npm = shutil.which("npm")
    if npm:
        try:
            yollar.append(subprocess.run([npm, "root", "-g"], capture_output=True, text=True, timeout=30).stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    env["NODE_PATH"] = os.pathsep.join(y for y in yollar if y)
    return env


class _AU:
    d = None

    def oku(self): return self.d
    def yaz(self, k): self.d = k
    def sil(self): self.d = None


@pytest.fixture(scope="module")
def sonuc(tmp_path_factory):
    node = shutil.which("node")
    if not node:
        _atla("node kurulu değil")
    kok = tmp_path_factory.mktemp("tarayici")
    os.environ["KIMLIK_AYAR_DIZINI"] = str(kok / "ayar")
    veri = kok / "veri"
    y = Yonetici(Ayarlar(kok / "ayar"), Otomatik(_AU()), secici=lambda t: None, claude_yolu=lambda: None)
    y.api("sihirbaz_tamamla", {"yol": str(veri), "otomatik_baslat": False})
    y.kapat()
    with Hub.open(veri, write=True) as hub:
        demo_veri.uret(hub, olcek=0.02)
    y = Yonetici(Ayarlar(kok / "ayar"), Otomatik(_AU()), secici=lambda t: None, claude_yolu=lambda: None)
    y.baslat()
    for metin, kat in [("Windows 11 bilgisayarım var", "cihazlar"),
                       ("İstanbul'da yaşıyorum ve yazılım geliştiriyorum, açık kaynak projelerde çalışıyorum", "is"),
                       ("Koyu temayı tercih ederim", "tercihler")]:
        y.api("persona_ekle", {"metin": metin, "kategori": kat})
    # içe aktar için sahte dosyalar: sağlam (Reddit örnek zip), bozuk zip, tanınmayan metin
    ok = kok / "reddit.zip"
    with zipfile.ZipFile(ok, "w") as z:
        for p in sorted((FIX / "reddit").iterdir()):
            z.write(p, p.name)
    bozuk = kok / "bozuk.zip"
    bozuk.write_bytes(b"PK\x03\x04" + bytes(range(256)) * 4)
    tanin = kok / "notlar.txt"
    tanin.write_text("bu bir dışa aktarma dosyası değil", encoding="utf-8")
    import tanila_dene
    sentinel = tanila_dene.sahte_zip(kok / "sentinel.zip")
    s = Sunucu(y, 0)
    s.baslat()
    ayar = kok / "ayar.json"
    ayar.write_text(json.dumps({"url": s.url, "ice_dosyalari": {"bozuk": str(bozuk), "taninmayan": str(tanin), "saglam": str(ok)},
                                "tanila_dosyasi": str(sentinel)}), encoding="utf-8")
    try:
        p = subprocess.run([node, str(BETIK), str(ayar)], capture_output=True, text=True, timeout=300, env=_node_ortami())
    finally:
        s.durdur()
        y.kapat()
    if p.returncode == 77:
        _atla("Playwright/Chromium yok: " + p.stderr.strip()[:200])
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout.strip().splitlines()[-1])


SAYFALAR = ["Anasayfa", "Harita", "İçe aktar", "Arama", "Zaman çizelgesi", "Persona", "Erişim", "Kaynaklar", "Güvenlik", "Ayarlar", "Hakkında"]


@pytest.mark.parametrize("ad", SAYFALAR)
def test_ekran_hatasiz_acilir(sonuc, ad):
    s = sonuc["sayfalar"][ad]
    assert s["bildirimler"] == [], f"{ad}: arayüz hata bildirimi verdi: {s['bildirimler']}"
    assert s["cocuk"] > 0 and s["metin_uzunlugu"] > 30, f"{ad}: ekran boş kaldı"
    assert s["kotu_metin"] == [], f"{ad}: ekranda hatalı metin: {s['kotu_metin']}"


def test_konsolda_hata_yok(sonuc):
    assert sonuc["baslangic_hatalari"] == []
    assert sonuc["konsol_hatalari"] == []


def test_ice_aktar_sahte_dosyalarla(sonuc):
    ice = sonuc["ice"]
    for ad, d in ice.items():
        assert not d.get("kutu_yok"), f"{ad}: İçe aktar ekranı açılmadı (dosya yolu kutusu yok); bildirimler: {d['bildirimler']}"
        assert d["bitti"], f"{ad}: içe aktarma sonuç vermedi"
        assert d["bildirimler"] == [], f"{ad}: {d['bildirimler']}"
    assert "Tamamlandı" in ice["saglam"]["metin"]
    assert "bozuk görünüyor" in ice["bozuk"]["metin"] and "tanıyamadım" not in ice["bozuk"]["metin"]
    assert "Bu dosyayı tanıyamadım" in ice["taninmayan"]["metin"] and "bozuk görünüyor" not in ice["taninmayan"]["metin"]


def test_mobil_yatay_tasma_yok(sonuc):
    for ad, t in sonuc["mobil"].items():
        assert t["belge"] <= 0, f"{ad}: sayfa yatay taşıyor ({t['belge']}px)"
        assert t["ogeler"] == [], f"{ad}: taşan öğeler {t['ogeler']}"


def test_mobil_radar_etiketi_kirpilmiyor(sonuc):
    r = sonuc["mobil_radar"]
    assert not r.get("yok"), "radar çizilmedi"
    assert not r["sol_kenar_dolu"] and not r["sag_kenar_dolu"], f"radar etiketi kırpılıyor: {r}"


def test_tema_sistem_tercihine_uyar(sonuc):
    t = sonuc["tema"]
    assert t["varsayilan_acik_tercih"]["data_tema"] == "koyu" and t["varsayilan_acik_tercih"]["parlaklik"] < 80   # tasarım: varsayılan koyu
    assert t["sistem_acik_tercih"]["parlaklik"] > 180
    assert t["sistem_koyu_tercih"]["parlaklik"] < 80
    assert t["acik_secili"]["parlaklik"] > 180


def test_utc_ve_aciklamalar_gorunur(sonuc):
    for ad in ("Zaman çizelgesi", "Arama", "Persona"):
        assert "UTC" in sonuc["sayfalar"][ad]["metin"], f"{ad}: saatin UTC olduğu yazmıyor"
    assert "Harita'daki toplamdan farklı" in sonuc["ana_metin"]
    assert sonuc["harita_nedir"] and sonuc["harita_nedir"]["acik"] and "Kilitli" in sonuc["harita_nedir"]["metin"]
    assert sonuc["ipucu_metni"] and len(sonuc["ipucu_metni"]) > 20
    assert "Terimler sözlüğü" in sonuc["sayfalar"]["Hakkında"]["metin"]


def test_dosya_denetle_dugmesi_rapor_ve_kopyala(sonuc):
    t = sonuc["tanila"]
    assert t["bildirimler"] == [], t["bildirimler"]
    assert t["aciklama_var"] and t["dugme_var"], "açıklama/düğme yok"
    assert t["rapor_var"], "rapor görünmedi"
    import tanila_dene
    assert tanila_dene.sizinti_var_mi(t["rapor"]) is None
    assert t["panoda"] == t["rapor"], "Kopyala düğmesi raporu panoya koymadı"
    assert t["eklenen_kayit"] == 0, "denetim bir şey içe aktardı"
    assert t["temizlendi"], "Raporu temizle çalışmadı"
    assert t["bos_yol_hatasi"], "yol boşken anlaşılır hata verilmedi"
