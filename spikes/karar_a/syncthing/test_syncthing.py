"""Aday 2: Syncthing çekirdeği. İkili SYNCTHING_BIN ortam değişkeniyle verilir (CI indirir, SHA256 doğrular)."""
from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path

import pytest

from ortak import dogrula, dosya_yaz, olc, satir_uuidleri, sha256_dosya, uret_giden_kutusu
from st_yardim import Cift, Ornek, bekle, esitlendi, ikili

ADAY = "syncthing"
CIHAZ = "telefon-1"

pytestmark = pytest.mark.skipif(
    ikili() is None and not os.environ.get("SYNCTHING_ZORUNLU"),
    reason="SYNCTHING_BIN yok (bu ortamdan github indirilemiyor; CI'de koşar)")


@pytest.fixture
def cift_fabrikasi(tmp_path):
    olusan = []

    def yap(**kw):
        assert ikili(), "SYNCTHING_BIN ayarlı değil"
        c = Cift(tmp_path / f"c{len(olusan)}", ikili(), **kw).hazirla()
        olusan.append(c)
        return c

    yield yap
    for c in olusan:
        c.bitir()


def tel_yol(c: Cift) -> Path:
    return c.tel.klasor


def test_a_pc_kapaliyken_birikir(cift_fabrikasi):
    c = cift_fabrikasi()
    c.bagla()
    c.pc.oldur()  # PC kapandı
    g = uret_giden_kutusu(tel_yol(c), CIHAZ, 200, 50, doldur=800)
    toplam = sum(p.stat().st_size for p in (tel_yol(c) / CIHAZ).glob("*.jsonl"))
    c.tel.tara(c.kid)
    time.sleep(3)
    assert not c.pc.calisiyor() and not c.pc.ping(), "pc süreci öldürülemedi"
    assert not list((c.pc.klasor).rglob("*.jsonl"))  # kapalıyken hiçbir şey gelmedi
    t0 = time.perf_counter()
    c.pc.baslat()
    baslama = time.perf_counter() - t0
    assert esitlendi(c.pc, c.kid, 200, 180), c.pc.gunluk_son()
    sure = time.perf_counter() - t0
    dogrula(g, satir_uuidleri(c.pc.klasor))
    olc(ADAY, "a_pc_kapali_birikim", dosya=200, toplam_mb=f"{toplam/1e6:.1f}", pc_acilis_s=f"{baslama:.2f}",
        pc_acilistan_eksiksize_s=f"{sure:.2f}")


def test_b_buyuk_dosya_pc_kill(cift_fabrikasi):
    c = cift_fabrikasi(pc_secenek={"maxRecvKbps": 8192, "limitBandwidthInLan": "true"})
    c.bagla()
    yol = tel_yol(c) / CIHAZ / f"{uuid.uuid4()}.jsonl"
    kim = dosya_yaz(yol, CIHAZ, 100 * 1024, doldur=900)  # ~100 MB
    boyut = yol.stat().st_size
    c.tel.tara(c.kid)
    assert bekle(lambda: c.pc.gelen_bayt() >= 25 * 1024 * 1024, 120), "aktarım hızlanmadı/başlamadı"
    tmp = list(c.pc.klasor.rglob("*syncthing*.tmp"))
    gelen_kill = c.pc.gelen_bayt()
    c.pc.oldur()
    assert not c.pc.ping(), "pc süreci öldürülemedi"
    assert not (c.pc.klasor / CIHAZ / yol.name).exists()  # yarım dosya asıl adıyla görünmemeli
    tmp_kalan = len(list(c.pc.klasor.rglob("*syncthing*.tmp")))
    c.pc.xml_duzenle({"maxRecvKbps": 0, "limitBandwidthInLan": "false"})
    t0 = time.perf_counter()
    c.pc.baslat()
    assert esitlendi(c.pc, c.kid, 1, 180), c.pc.gunluk_son()
    sure = time.perf_counter() - t0
    hedef = c.pc.klasor / CIHAZ / yol.name
    assert sha256_dosya(hedef) == sha256_dosya(yol)
    devam_bayt = c.pc.gelen_bayt()
    assert not list(c.pc.klasor.rglob("*syncthing*.tmp"))
    dogrula(kim, satir_uuidleri(c.pc.klasor))
    olc(ADAY, "b_pc_kill_devam", boyut_bayt=boyut, kill_aninda_alinan_bayt=gelen_kill, kill_oncesi_tmp_dosya=len(tmp),
        kill_sonrasi_tmp_dosya=tmp_kalan, yeniden_baslayinca_alinan_bayt=devam_bayt,
        yeniden_baslayinca_tamamlanma_s=f"{sure:.2f}", sha_esit=True)


def test_c_ayni_icerik_iki_kez(cift_fabrikasi):
    c = cift_fabrikasi()
    c.bagla()
    kok = tel_yol(c) / CIHAZ
    a = kok / f"{uuid.uuid4()}.jsonl"
    kim = dosya_yaz(a, CIHAZ, 10 * 1024, doldur=900)  # ~10 MB
    boyut = a.stat().st_size
    b = kok / f"{uuid.uuid4()}.jsonl"  # aynı içerik, farklı ad
    shutil.copy(a, b)
    c.tel.tara(c.kid)
    assert esitlendi(c.pc, c.kid, 2, 120)
    dosyalar = sorted(p.name for p in (c.pc.klasor / CIHAZ).glob("*.jsonl"))
    bayt1 = c.pc.gelen_bayt()
    # aynı ad, aynı içerik, yeniden yazıldı (kopyala-üstüne-yaz)
    shutil.copy(b, a)
    os.utime(a, None)
    c.tel.tara(c.kid)
    time.sleep(4)
    bayt2 = c.pc.gelen_bayt()
    dosyalar2 = sorted(p.name for p in (c.pc.klasor / CIHAZ).glob("*.jsonl"))
    uuid_listesi = satir_uuidleri(c.pc.klasor)
    tekrar = len(uuid_listesi) - len(set(uuid_listesi))
    assert set(uuid_listesi) == set(kim)
    assert dosyalar2 == dosyalar
    olc(ADAY, "c_ayni_icerik", kaynak_dosya_boyut_bayt=boyut, pc_dosya_sayisi_farkli_adla=len(dosyalar),
        pc_alinan_bayt_iki_dosya=bayt1, ayni_ad_yeniden_yazimda_ek_bayt=bayt2 - bayt1,
        pc_satir_uuid_tekrar_sayisi=tekrar, ayni_ad_tek_kopya=len(dosyalar2) == len(dosyalar))


@pytest.mark.parametrize("ignore_delete", [False, True], ids=["ignoreDelete_kapali", "ignoreDelete_acik"])
def test_d1_telefonda_silme_yayilimi(cift_fabrikasi, ignore_delete):
    c = cift_fabrikasi(pc_klasor_ek={"ignoreDelete": ignore_delete})
    c.bagla()
    g = uret_giden_kutusu(tel_yol(c), CIHAZ, 5, 100)
    c.tel.tara(c.kid)
    assert esitlendi(c.pc, c.kid, 5, 120)
    silinen = sorted(g)[0]
    (tel_yol(c) / CIHAZ / silinen).unlink()
    c.tel.tara(c.kid)
    pc_dosya = c.pc.klasor / CIHAZ / silinen
    if not ignore_delete:
        silindi = bekle(lambda: not pc_dosya.exists(), 40)
        var = pc_dosya.exists()
    else:
        assert bekle(lambda: c.pc.db(c.kid)["globalDeleted"] >= 1, 40), "silme bilgisi pc'ye ulaşmadı"
        time.sleep(4)
        silindi = not pc_dosya.exists()
        var = pc_dosya.exists()
    d = c.pc.db(c.kid)
    kalan_pc = len(list((c.pc.klasor / CIHAZ).glob("*.jsonl")))
    olc(ADAY, f"d1_silme_{'ignoreDelete_acik' if ignore_delete else 'ignoreDelete_kapali'}",
        telefonda_silinen_pc_de_silindi=silindi, pc_dosya_hala_var=var, pc_kalan_dosya=kalan_pc,
        pc_needFiles=d.get("needFiles"), pc_needDeletes=d.get("needDeletes"),
        pc_receiveOnlyChangedFiles=d.get("receiveOnlyChangedFiles"), pc_state=d.get("state"))
    assert silindi is (not ignore_delete)


def test_d2_pc_dosyayi_disari_tasir(cift_fabrikasi, tmp_path):
    c = cift_fabrikasi()
    c.bagla()
    g = uret_giden_kutusu(tel_yol(c), CIHAZ, 5, 100)
    c.tel.tara(c.kid)
    assert esitlendi(c.pc, c.kid, 5, 120)
    tasinan = sorted(g)[0]
    hedef = tmp_path / "islenen"
    hedef.mkdir()
    shutil.move(str(c.pc.klasor / CIHAZ / tasinan), str(hedef / tasinan))
    c.pc.tara(c.kid)
    time.sleep(6)
    pc_d = c.pc.db(c.kid)
    tel_d = c.tel.db(c.kid)
    olc(ADAY, "d2_pc_disari_tasima", telefonda_dosya_hala_var=(tel_yol(c) / CIHAZ / tasinan).exists(),
        pc_klasorde_geri_geldi=(c.pc.klasor / CIHAZ / tasinan).exists(),
        pc_receiveOnlyChangedDeletes=pc_d.get("receiveOnlyChangedDeletes"),
        pc_receiveOnlyChangedFiles=pc_d.get("receiveOnlyChangedFiles"), pc_needFiles=pc_d.get("needFiles"),
        telefon_globalFiles=tel_d.get("globalFiles"), telefon_globalDeleted=tel_d.get("globalDeleted"),
        pc_state=pc_d.get("state"))
    assert (tel_yol(c) / CIHAZ / tasinan).exists()  # receiveonly: yerel silme telefona yayılmaz


def test_e_kurulum_adimlari(tmp_path):
    assert ikili(), "SYNCTHING_BIN yok"
    tel = Ornek("telefon", tmp_path / "t", ikili())
    pc = Ornek("pc", tmp_path / "p", ikili())
    tel.uret()
    pc.uret({"defaultFolderPath": str(tmp_path / "pc_varsayilan")})
    for o in (tel, pc):
        o.baslat()
    try:
        # PC tarafı: 1 kez telefonun kimliğini ekle (autoAcceptFolders açık)
        pc.cihaz_ekle(tel, autoAcceptFolders=True)
        # telefon tarafı: pc kimliğini ekle + klasörü pc ile paylaş
        tel.cihaz_ekle(pc)
        tel.klasor_ekle("giden-kutusu", "sendonly", pc)
        gorundu = bekle(lambda: any(f["id"] == "giden-kutusu" for f in pc.rest("GET", "/rest/config/folders")), 60)
        assert gorundu, "paylaşılan klasör pc'de kendiliğinden belirmedi"
        f = next(f for f in pc.rest("GET", "/rest/config/folders") if f["id"] == "giden-kutusu")
        olc(ADAY, "e_kurulum", pc_otomatik_kabul_klasor_turu=f["type"], pc_otomatik_kabul_yolu=f["path"],
            rest_cagrisi_pc_tarafi="1 cihaz ekle(autoAcceptFolders) + sonra tür=receiveonly değiştir",
            rest_cagrisi_telefon_tarafi="2 (cihaz ekle, klasör paylaş)")
    finally:
        tel.oldur()
        pc.oldur()
