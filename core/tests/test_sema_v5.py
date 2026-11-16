"""Şema v5: önem ağırlığı, konu bazında hassasiyet, göç, yeniden işaretleme (docs/SEMA.md)."""
import json
import sqlite3
import time

import pytest

from kimlikcore import EventIn, FormatError, Hub, SchemaTooOld, donusum, hassas, onem
from kimlikcore import sifreleme as sif
from kimlikcore import schema
from kimlikcore.hassas import hassas_konulari, paket_siniflandirici
from kimlikcore.onem import onem_hesapla

from test_migration import make_v1


# ----------------------------------------------------------------------------- önem
@pytest.mark.parametrize("kind,cat,payload,beklenen", [
    ("sohbet.mesaj", "sohbet", {"rol": "kullanici"}, 2),
    ("sohbet.mesaj", "sohbet", {"rol": "asistan"}, 0),
    ("sohbet.mesaj", "sohbet", {"rol": "sistem"}, 1),
    ("sohbet.mesaj", "sohbet", {}, 1),
    ("instagram.gonderi", "sosyal", {}, 2),
    ("facebook.yorum", "sosyal", {}, 2),
    ("meta.gonderi", "sosyal", {}, 2),
    ("reddit.yorum", "sosyal", {}, 2),
    ("reddit.gonderi", "sosyal", {}, 2),
    ("keep.not", "notlar", {}, 2),
    ("github.depo", "kod", {}, 2),
    ("github.issue", "kod", {}, 2),
    ("github.pr", "kod", {}, 2),
    ("instagram.begeni", "sosyal", {}, 0),
    ("instagram.takip", "sosyal", {}, 0),
    ("instagram.takipci", "sosyal", {}, 0),
    ("facebook.tepki", "sosyal", {}, 0),
    ("reddit.oy", "sosyal", {}, 0),
    ("youtube.abone", "video", {}, 0),
    ("spotify.abonelik", "muzik", {}, 0),
    ("facebook.arkadas", "sosyal", {}, 0),
    ("youtube.kaydedilen", "video", {}, 0),
    ("github.yildiz", "kod", {}, 0),
    ("github.izleme", "kod", {}, 0),
    ("youtube.izleme", "video", {}, 1),
    ("tarama.ziyaret", "tarama", {}, 1),
    ("eposta.mesaj", "eposta", {}, 1),
    ("sms.mesaj", "mesaj", {}, 1),
])
def test_onem_kural_tablosu(kind, cat, payload, beklenen):
    assert onem_hesapla(kind, cat, payload) == beklenen


# ----------------------------------------------------------------------------- hassas konu
POZITIF = [
    ("saglik", "Dün doktora gittim, tahlil sonuçlarım geldi"),
    ("saglik", "DEPRESYON ve ANKSİYETE nedeniyle terapiye başladım"),
    ("saglik", "ameliyatım yarın"),
    ("saglik", "I need to see a doctor about my prescription"),
    ("saglik", "kan tahlilim iyi çıktı"),
    ("hukuk", "Avukatımla görüştüm, dava açılıyor"),
    ("hukuk", "boşanma davası için DİLEKÇE yazdım"),
    ("hukuk", "ceza davası ertelendi"),
    ("hukuk", "my lawyer filed the lawsuit"),
    ("finans", "MAAŞ yatmadı, kredi kartı borcum var"),
    ("finans", "IBAN numaramı gönder"),
    ("finans", "evime haciz geldi, ipotek kaldırılmadı"),
    ("finans", "bank account and mortgage"),
    ("din_siyaset", "Bu akşam namaz sonrası dua edeceğim"),
    ("din_siyaset", "Seçimde oy verdim, siyasi parti kongresine gittim"),
    ("din_siyaset", "ISPARTA'da miting vardı"),
    ("din_siyaset", "we went to church"),
    ("cinsellik", "cinsel yönelimimi açıkladım"),
    ("cinsellik", "Eşcinsel arkadaşım LGBT etkinliğine gitti"),
    ("cinsellik", "erotik içerik"),
    ("cinsellik", "sexual orientation"),
]


@pytest.mark.parametrize("konu,metin", POZITIF)
def test_hassas_pozitif(konu, metin):
    assert konu in hassas_konulari(metin)


@pytest.mark.parametrize("metin", [
    "hesap makinesi aldım", "bugün parti verdik, kutlama vardı", "karar verdim", "",
    "   ", "ceza puanı", "yarın toplantı var, saat 10", "kitap okudum ve yürüyüş yaptım",
    "tanıdık biriyle tanıştım", "secim yapmam gerekiyor",
])
def test_hassas_negatif(metin):
    assert hassas_konulari(metin) == []


def test_ince_ayrimlar():
    assert "finans" not in hassas_konulari("hesap makinesi")
    # BİLİNEN YANLIŞ POZİTİF (docs/SEMA.md): "doktor" ön eki "doktora"yı da yakalar.
    assert hassas_konulari("doktora tezimi yazıyorum") == ["saglik"]
    # çok sözcüklü terimde son sözcük ek alabilir, ilk sözcükler tam olmalı
    assert "finans" in hassas_konulari("kredi kartımı kaybettim")
    assert hassas_konulari("kredi") == ["finans"]
    assert hassas_konulari("kart kredi") == ["finans"]


def test_hassas_coklu_konu_alfabetik():
    assert hassas_konulari("avukat dedi ki doktor ve maaş") == ["finans", "hukuk", "saglik"]


def test_hassas_tam_sozcuk_ve_katlama():
    assert hassas_konulari("DUA etti") == ["din_siyaset"]
    assert hassas_konulari("duayen") == []          # "dua" yalnız tam sözcük
    assert hassas_konulari("Cami'ye gittik") == ["din_siyaset"]
    assert hassas_konulari("camiaya") == []


def test_paket_listesi_gecerli_ve_boyutlu():
    ham = hassas._paket_ham()
    assert set(ham["konular"]) == {"saglik", "hukuk", "finans", "din_siyaset", "cinsellik"}
    for kid, v in ham["konular"].items():
        n = len(v["terimler"]) + len(v.get("tam", []))
        assert n >= 40, (kid, n)
    assert paket_siniflandirici().konu_idleri == sorted(ham["konular"])


def test_hassas_performans():
    metin = ("bugün hava güzeldi, yürüyüşe çıktık ve kitap okuduk " * 4000)[:200_000]
    metin = metin[:100_000] + " doktor " + metin[100_000:]
    hassas_konulari("x")  # derleme önbelleğe
    t = time.perf_counter()
    assert hassas_konulari(metin) == ["saglik"]
    assert time.perf_counter() - t < 1.0


# ----------------------------------------------------------------------------- Hub: yazma
def _ev(i, text, kind="sentetik.not", cat="notlar", payload=None):
    return EventIn(event_key=f"k{i}", ts="2026-05-01T10:00:00Z", kind=kind, category=cat,
                   payload=payload or {}, text=text)


def test_add_events_alanlari_doldurur(hub):
    sid = hub.add_source("deneme", "1", None)
    hub.add_events(sid, [
        _ev(1, "doktor randevusu ve maaş", kind="x.sohbet", cat="tarama"),
        _ev(2, "düz metin", kind="sohbet.mesaj", cat="sohbet", payload={"rol": "kullanici"}),
        _ev(3, "yanıt", kind="sohbet.mesaj", cat="sohbet", payload={"rol": "asistan"}),
    ])
    e1, e2, e3 = (hub.search(w)[0] for w in ("randevusu", "düz", "yanıt"))
    assert (e1.onem, e1.hassas_konu) == (1, ("finans", "saglik"))
    assert (e2.onem, e2.hassas_konu) == (2, ())
    assert e3.onem == 0
    assert hub.get_event(e1.event_id).hassas_konu == ("finans", "saglik")
    assert hub.timeline(categories=["sohbet"], ascending=True)[0].onem in (0, 2)
    ham = hub.query("SELECT hassas_konu FROM events WHERE event_key='k1'")
    assert ham == [("finans,saglik",)]
    assert hub.query("SELECT hassas_konu FROM events WHERE event_key='k2'") == [(None,)]


def test_export_import_geri_uyumlu(tmp_path):
    with Hub.open(tmp_path / "a", write=True) as a:
        sid = a.add_source("deneme", "1", None)
        a.add_events(sid, [_ev(1, "avukat görüşmesi"), _ev(2, "sade", kind="reddit.oy", cat="sosyal")])
        a.export_jsonl(tmp_path / "e.jsonl")
    with Hub.open(tmp_path / "b", write=True) as b:
        r = b.import_jsonl(tmp_path / "e.jsonl")
        assert r.verified
        assert b.query("SELECT onem, hassas_konu FROM events ORDER BY seq") == [(2, "hukuk"), (0, None)]
    # Eski (v4) biçimli dosya: events'te alan yok, konu_izni türü yok. Yeniden hesaplanarak alınır.
    satirlar = (tmp_path / "e.jsonl").read_text(encoding="utf-8").splitlines()
    assert not any('"onem"' in s for s in satirlar)
    with Hub.open(tmp_path / "c", write=True) as c:
        c.import_jsonl(tmp_path / "e.jsonl")
        assert c.query("SELECT count(*) FROM events WHERE hassas_konu IS NOT NULL") == [(1,)]


def test_konu_izinleri_tablosu(hub):
    with hub.transaction() as c:
        c.execute("INSERT INTO app_keys(app_id, name, key_hash, created) VALUES ('a','x','h','2026-01-01T00:00:00Z')")
        c.execute("INSERT INTO konu_izinleri(app_id, konu, granted_at) VALUES ('a','saglik','2026-01-01T00:00:00Z')")
    with pytest.raises(sqlite3.IntegrityError):
        with hub.transaction() as c:
            c.execute("INSERT INTO konu_izinleri(app_id, konu, granted_at) VALUES ('yok','saglik','2026-01-01T00:00:00Z')")
    with pytest.raises(sqlite3.IntegrityError):
        with hub.transaction() as c:
            c.execute("INSERT INTO konu_izinleri(app_id, konu, granted_at) VALUES ('a','saglik','2026-01-02T00:00:00Z')")


def test_salt_okunur_v5_okur(root):
    with Hub.open(root, write=True) as h:
        sid = h.add_source("deneme", "1", None)
        h.add_events(sid, [_ev(1, "kanser tedavisi")])
    with Hub.open(root, write=False) as r:
        assert r.schema_version == 5
        assert r.timeline()[0].hassas_konu == ("saglik",)


# ----------------------------------------------------------------------------- ek liste
def test_kullanici_eki_ve_cikar(root):
    root.mkdir()
    (root / "hassas_konular.json").write_text(json.dumps({
        "konular": {"finans": {"terimler": ["kripto cüzdanım"], "tam": ["btc"]},
                    "ozel": {"terimler": ["gizlikonu"]}},
        "cikar": ["klinik", "hasta"],
    }, ensure_ascii=False), encoding="utf-8")
    with Hub.open(root, write=True) as h:
        assert h.goc_uyarilari == []
        sid = h.add_source("deneme", "1", None)
        h.add_events(sid, [_ev(1, "BTC aldım"), _ev(2, "kripto cüzdanım boş"), _ev(3, "gizlikonu burada"),
                           _ev(4, "klinik ziyaret"), _ev(5, "hasta ziyareti"), _ev(6, "doktor")])
        d = dict(h.query("SELECT event_key, hassas_konu FROM events"))
        assert d == {"k1": "finans", "k2": "finans", "k3": "ozel", "k4": None, "k5": None, "k6": "saglik"}


def test_bozuk_ek_dosya_uyari_verir(root):
    root.mkdir()
    (root / "hassas_konular.json").write_text("{bozuk", encoding="utf-8")
    with Hub.open(root, write=True) as h:
        assert any("hassas_konular.json" in u for u in h.goc_uyarilari)
        sid = h.add_source("deneme", "1", None)
        h.add_events(sid, [_ev(1, "doktor")])   # paket listesi kullanılır
        assert h.timeline()[0].hassas_konu == ("saglik",)
    (root / "hassas_konular.json").write_text('{"konular": {"saglik": {"terimler": ["abc"]}}}', encoding="utf-8")
    with Hub.open(root, write=True) as h:
        assert any("hassas_konular.json" in u for u in h.goc_uyarilari)


def test_yeniden_isaretle(root):
    with Hub.open(root, write=True) as h:
        sid = h.add_source("deneme", "1", None)
        h.add_events(sid, [_ev(1, "btc aldım"), _ev(2, "doktor"), _ev(3, "sade")])
        assert h.yeniden_isaretle() == {"incelenen": 3, "degisen": 0}
        gorulen = []
        (root / "hassas_konular.json").write_text(json.dumps(
            {"konular": {"finans": {"tam": ["btc"]}}, "cikar": ["doktor"]}), encoding="utf-8")
        assert h.yeniden_isaretle(gorulen.append) == {"incelenen": 3, "degisen": 2}
        assert gorulen == [3]
        assert dict(h.query("SELECT event_key, hassas_konu FROM events")) == {"k1": "finans", "k2": None, "k3": None}
        # önem kuralı da yeniden işlenir
        h.query("SELECT 1")
        with h.transaction() as c:
            c.execute("UPDATE events SET onem = 0 WHERE event_key = 'k3'")
        assert h.yeniden_isaretle()["degisen"] == 1


def test_yeniden_isaretle_salt_okunurda_yok(root):
    with Hub.open(root, write=True):
        pass
    with Hub.open(root, write=False) as r:
        with pytest.raises(Exception):
            r.yeniden_isaretle()


def test_cli_yeniden_isaretle(root, child_env):
    import subprocess, sys
    with Hub.open(root, write=True) as h:
        sid = h.add_source("deneme", "1", None)
        h.add_events(sid, [_ev(1, "avukat")])
        with h.transaction() as c:
            c.execute("UPDATE events SET hassas_konu = NULL")
    r = subprocess.run([sys.executable, "-m", "kimlikcore", "--veri", str(root), "--json", "yeniden-isaretle"],
                       env=child_env, capture_output=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"incelenen": 1, "degisen": 1}
    r = subprocess.run([sys.executable, "-m", "kimlikcore", "--veri", str(root), "yeniden-isaretle"],
                       env=child_env, capture_output=True, encoding="utf-8")
    assert "1 olay incelendi, 0" in r.stdout


# ----------------------------------------------------------------------------- göç
def test_goc_v4ten_v5e_eski_veri_isaretlenir(root):
    make_v1(root, upto=2)
    c = sqlite3.connect(root / "kimlik.db", isolation_level=None)
    c.execute("UPDATE events SET text = 'doktor ve avukat', kind='reddit.begeni', category='sosyal' WHERE event_id='id1'")
    c.execute("UPDATE events SET kind='sohbet.mesaj', category='sohbet', payload='{\"rol\":\"kullanici\"}' WHERE event_id='id2'")
    c.close()
    with pytest.raises(SchemaTooOld):
        Hub.open(root, write=False)
    with Hub.open(root, write=True) as h:
        assert h.schema_version == 5
        assert h.query("SELECT 1 FROM sqlite_master WHERE name='konu_izinleri'")
        e1, e2, e3 = (h.get_event(i) for i in ("id1", "id2", "id3"))
        assert (e1.onem, e1.hassas_konu) == (0, ("hukuk", "saglik"))
        assert e2.onem == 2
        assert (e3.onem, e3.hassas_konu) == (2, ())      # kategori 'notlar'
        assert h.query("PRAGMA foreign_key_check") == []


def test_goc_adimi_idempotent(tmp_path):
    c = sqlite3.connect(tmp_path / "x.db", isolation_level=None)
    schema.migrate(c)
    schema._v5(c)    # ikinci kez çalışırsa bozulmaz
    assert schema.current_version(c) == 5


def test_basarisiz_v5_gocu_geri_alinir(root):
    make_v1(root, upto=2)
    # v3 ve v4 uygulansın, v5 patlasın
    c = sqlite3.connect(root / "kimlik.db", isolation_level=None)

    def bozuk_v5(conn):
        schema._v5(conn)
        raise RuntimeError("v5 patladı")

    with pytest.raises(RuntimeError):
        schema.migrate(c, migrations={**schema.MIGRATIONS, 5: bozuk_v5})
    assert schema.current_version(c) == 4
    kolonlar = {r[1] for r in c.execute("PRAGMA table_info(events)")}
    assert "onem" not in kolonlar and "hassas_konu" not in kolonlar
    assert c.execute("SELECT 1 FROM sqlite_master WHERE name='konu_izinleri'").fetchone() is None
    schema.migrate(c)
    assert schema.current_version(c) == 5


def test_goc_20000_olay_performans(tmp_path, capsys):
    c = sqlite3.connect(tmp_path / "p.db", isolation_level=None)
    for v in (1, 2, 3, 4):
        for s in schema.MIGRATIONS[v]:
            c.execute(s)
        c.execute("INSERT INTO schema_migrations VALUES (?, 'x')", (v,))
    c.execute("PRAGMA user_version = 4")
    c.execute("INSERT INTO sources VALUES ('s1','k','1',NULL,'2026-01-01T00:00:00Z',NULL,NULL)")
    c.execute("BEGIN")
    metin = "bugün hava güzeldi ve yürüyüşe çıktık " * 8
    c.executemany(
        "INSERT INTO events(event_id,event_key,source_id,ts,kind,category,payload,text,schema_version,hidden,ingested_at)"
        " VALUES (?,?,'s1','2026-01-01T00:00:00Z',?,?,'{}',?,4,0,'x')",
        [(f"i{i}", f"k{i}", "sohbet.mesaj" if i % 3 == 0 else "x.y", "notlar" if i % 5 == 0 else "tarama",
          metin + (" doktor" if i % 7 == 0 else "")) for i in range(20000)])
    c.execute("COMMIT")
    t = time.perf_counter()
    schema.migrate(c)
    sure = time.perf_counter() - t
    print(f"\nGOC_20000_SURE={sure:.2f}s")
    assert sure < 30
    assert c.execute("SELECT count(*) FROM events WHERE hassas_konu='saglik'").fetchone()[0] == len(range(0, 20000, 7))


# ----------------------------------------------------------------------------- gözden geçirme düzeltmeleri
@pytest.mark.parametrize("konu,metin", [
    # ünsüz yumuşaması / ünlü düşmesi / kök
    ("saglik", "kliniğe gittim"), ("saglik", "Klinik randevusu"),
    ("hukuk", "sanığı dinlediler"), ("din_siyaset", "mezhebi farklıymış"),
    ("hukuk", "dün tutuklandı"), ("hukuk", "tutuklular serbest"),
    ("saglik", "gebe kaldım"), ("saglik", "doğum yaptım"),
    # kesme işareti (düz ve kıvrık)
    ("din_siyaset", "Kur'an okudum"), ("din_siyaset", "Kur\u2019an-ı Kerim"), ("din_siyaset", "Kuran-ı Kerim"),
    ("din_siyaset", "Allah'a şükür"), ("din_siyaset", "Allah\u2019a şükür"),
    ("din_siyaset", "CHP'ye oy"), ("din_siyaset", "CHP\u2019ye oy"), ("din_siyaset", "AKP'liler"),
    ("din_siyaset", "DEM Parti'nin"), ("din_siyaset", "İYİ Parti'ye"),
    ("din_siyaset", "incil okudum"), ("din_siyaset", "Church service"),
    # yeni terimler
    ("saglik", "sağlık sorunum"), ("saglik", "tahlil"), ("saglik", "intihar düşüncesi"),
    ("saglik", "kendimi öldüreceğim"), ("saglik", "uyuşturucu"), ("saglik", "esrar içti"),
    ("saglik", "bağımlılık"), ("saglik", "kürtaj"), ("saglik", "grip oldum"), ("saglik", "covid"),
    ("saglik", "korona"), ("saglik", "diş hekimi"), ("saglik", "dişçiye gittim"), ("saglik", "tümör"),
    ("saglik", "biyopsi"), ("saglik", "insülin"), ("saglik", "epilepsi"), ("saglik", "otizm"),
    ("saglik", "bipolar"), ("saglik", "şizofreni"), ("saglik", "kaygı bozukluğu"), ("saglik", "panik atak"),
    ("saglik", "ambulans"), ("saglik", "acil servis"), ("saglik", "yoğun bakım"), ("saglik", "nefes darlığı"),
    ("saglik", "kan testi"), ("saglik", "yüksek ateş"), ("saglik", "ateşim var"), ("saglik", "diş ağrısı"),
    ("saglik", "antidepresan"), ("saglik", "psikolog"),
    ("hukuk", "hukuk bürosu"), ("hukuk", "hukuki süreç"), ("hukuk", "polis geldi"), ("hukuk", "karakola gittik"),
    ("hukuk", "hakim karar verdi"), ("hukuk", "yargıç"), ("hukuk", "cezaevi"), ("hukuk", "hapis yattı"),
    ("hukuk", "sabıka kaydı"), ("hukuk", "taciz"), ("hukuk", "tecavüz"), ("hukuk", "şiddet gördüm"),
    ("hukuk", "gözaltına alındı"), ("hukuk", "ifade verdim"), ("hukuk", "suç duyurusu"),
    ("finans", "kira ödedim"), ("finans", "vergi"), ("finans", "banka"), ("finans", "bütçe"),
    ("finans", "fatura"), ("finans", "sigorta"), ("finans", "bitcoin"), ("finans", "kripto aldım"),
    ("finans", "dolar yükseldi"), ("finans", "euro"), ("finans", "SGK'dan"), ("finans", "borsa"),
    ("finans", "hisse senedi"), ("finans", "yatırım"), ("finans", "birikim"), ("finans", "emekli maaşı"),
    ("din_siyaset", "siyaset"), ("din_siyaset", "siyasi"), ("din_siyaset", "referandum"),
    ("din_siyaset", "seçmen"), ("din_siyaset", "oy pusulası"), ("din_siyaset", "hükümet"),
    ("din_siyaset", "protesto"), ("din_siyaset", "müslüman"), ("din_siyaset", "hristiyan"),
    ("din_siyaset", "yahudi"), ("din_siyaset", "alevi"), ("din_siyaset", "sünni"), ("din_siyaset", "tanrı"),
    ("din_siyaset", "başörtüsü"), ("din_siyaset", "türban"), ("din_siyaset", "hac"), ("din_siyaset", "umre"),
    ("din_siyaset", "mevlit"), ("din_siyaset", "laik"), ("din_siyaset", "atatürkçü"),
    ("din_siyaset", "muhalefet"), ("din_siyaset", "cumhurbaşkanı"), ("din_siyaset", "Cumhurbaşkanlığı"),
    ("din_siyaset", "milletvekili"), ("din_siyaset", "sandık başı"),
    ("cinsellik", "trans"), ("cinsellik", "transseksüel"), ("cinsellik", "cinsiyet kimliği"),
    ("cinsellik", "cinsel kimlik"), ("cinsellik", "seks"), ("cinsellik", "cinsel ilişki"),
    ("cinsellik", "mastürbasyon"), ("cinsellik", "prezervatif"), ("cinsellik", "doğum kontrol"),
    ("cinsellik", "biseksüel"), ("cinsellik", "lezbiyen"),
])
def test_hassas_gozden_gecirme_pozitif(konu, metin):
    assert konu in hassas_konulari(metin)


@pytest.mark.parametrize("metin", [
    "şirketi kuran kişi", "inciler taktı", "Churchill konuştu", "ateş yaktık", "diş fırçası aldım",
    "Europe turu", "kirazlar olgunlaştı", "kriptografi dersi", "esrarengiz olay", "transfer yaptı",
])
def test_hassas_gozden_gecirme_negatif(metin):
    assert hassas_konulari(metin) == []


def test_yumusama_algoritmasi_kural_olarak():
    assert hassas.kok_bicimleri("klinik") == ["klinik", "klinig"]
    assert hassas.kok_bicimleri("mezhep") == ["mezhep", "mezheb"]
    assert hassas.kok_bicimleri("tedavi") == ["tedavi"]
    assert hassas.kok_bicimleri("renk") == ["renk", "reng"]


def test_yeniden_isaretle_bozuk_ekte_hicbir_sey_degistirmez(root):
    with Hub.open(root, write=True) as h:
        sid = h.add_source("deneme", "1", None)
        h.add_events(sid, [_ev(1, "btc aldım"), _ev(2, "doktor")])
        (root / "hassas_konular.json").write_text("{bozuk", encoding="utf-8")
        with h.transaction() as c:
            c.execute("UPDATE events SET hassas_konu = NULL")
        with pytest.raises(FormatError, match="hiçbir olay değiştirilmedi"):
            h.yeniden_isaretle()
        assert h.query("SELECT count(*) FROM events WHERE hassas_konu IS NOT NULL") == [(0,)]


def test_bozuk_ek_goc_uyarisi_yeniden_isaretle_der(root):
    root.mkdir()
    (root / "hassas_konular.json").write_text("{bozuk", encoding="utf-8")
    with Hub.open(root, write=True) as h:
        assert any("ek listesi okunamadı" in u and "`yeniden-isaretle` çalıştırın" in u for u in h.goc_uyarilari)


def test_cli_yeniden_isaretle_bozuk_ekte_hata_kodu(root, child_env):
    import subprocess, sys
    with Hub.open(root, write=True):
        pass
    (root / "hassas_konular.json").write_text("[]x", encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "kimlikcore", "--veri", str(root), "yeniden-isaretle"],
                       env=child_env, capture_output=True, encoding="utf-8")
    assert r.returncode != 0 and "hiçbir olay değiştirilmedi" in r.stderr


# ----------------------------------------------------------------------------- footer
def _jsonl_disa(tmp_path):
    with Hub.open(tmp_path / "a", write=True) as a:
        sid = a.add_source("deneme", "1", None)
        a.add_events(sid, [_ev(1, "avukat")])
        a.export_jsonl(tmp_path / "e.jsonl")
    return [json.loads(x) for x in (tmp_path / "e.jsonl").read_text(encoding="utf-8").splitlines()]


def _yaz(tmp_path, kayitlar, ad):
    yol = tmp_path / ad
    yol.write_text("\n".join(json.dumps(k, ensure_ascii=False, separators=(",", ":")) for k in kayitlar) + "\n",
                   encoding="utf-8")
    return yol


def test_footer_eski_dosya_konu_izni_olmadan_kabul(tmp_path):
    k = _jsonl_disa(tmp_path)
    k[-1]["counts"].pop("konu_izni")
    k[-1]["digests"].pop("konu_izni")
    k[0]["schema_version"] = 4
    with Hub.open(tmp_path / "b", write=True) as b:
        r = b.import_jsonl(_yaz(tmp_path, k, "eski.jsonl"))
        assert r.counts["event"] == 1


@pytest.mark.parametrize("tur", ["event", "source", "fact", "app_key"])
def test_footer_baska_turun_ozeti_eksikse_reddedilir(tmp_path, tur):
    k = _jsonl_disa(tmp_path)
    k[-1]["counts"].pop(tur)
    with Hub.open(tmp_path / "b", write=True) as b:
        with pytest.raises(FormatError):
            b.import_jsonl(_yaz(tmp_path, k, "x.jsonl"))
    k = _jsonl_disa(tmp_path)
    k[-1]["digests"].pop(tur)
    with Hub.open(tmp_path / "c", write=True) as b:
        with pytest.raises(FormatError):
            b.import_jsonl(_yaz(tmp_path, k, "y.jsonl"))


# ----------------------------------------------------------------------------- şifreli göç
@pytest.fixture
def sahte_saglayici():
    sif.saglayici_ayarla(sif.SahteSaglayici("birinci"))
    yield
    sif.saglayici_ayarla(None)


def _v4_sifreli(root):
    root.mkdir()
    (root / "arsiv").mkdir()
    con = sqlite3.connect(root / "kimlik.db", isolation_level=None)
    schema.migrate(con, migrations={v: schema.MIGRATIONS[v] for v in (1, 2, 3, 4)})
    con.execute("INSERT INTO sources VALUES ('s','jsonl','1',NULL,'2026-01-01T00:00:00Z',NULL,NULL)")
    con.execute(
        "INSERT INTO events(event_id,event_key,source_id,ts,kind,category,payload,text,schema_version,hidden,ingested_at)"
        " VALUES ('e1','k1','s','2026-01-01T00:00:00Z','x.y','notlar','{}','doktor randevusu',4,0,'x')")
    con.close()
    donusum.sifrele(root)
    assert sif.db_durumu(root / "kimlik.db") == "sifreli"


def test_sifreli_hub_v4ten_v5e_goc(root, sahte_saglayici):
    _v4_sifreli(root)
    with Hub.open(root, write=True) as h:
        assert h.schema_version == 5
        e = h.get_event("e1")
        assert (e.onem, e.hassas_konu) == (2, ("saglik",))
    assert sif.db_durumu(root / "kimlik.db") == "sifreli"
    with Hub.open(root, write=False) as r:
        assert r.get_event("e1").hassas_konu == ("saglik",)


def test_sifreli_hub_v5_gocu_yarida_hata_eski_dosya_kalir(root, monkeypatch, sahte_saglayici):
    _v4_sifreli(root)
    once = (root / "kimlik.db").read_bytes()
    gercek = schema._v5

    def yarida(conn, *a, **k):
        gercek(conn, *a, **k)
        raise RuntimeError("göç yarıda kesildi")

    monkeypatch.setattr(schema, "_v5", yarida)
    with pytest.raises(RuntimeError):
        Hub.open(root, write=True)
    monkeypatch.undo()
    assert (root / "kimlik.db").read_bytes() == once        # şifreli dosya dokunulmadı
    assert not (root / "hub.lock").exists()
    with pytest.raises(SchemaTooOld):
        Hub.open(root, write=False)                          # hâlâ sürüm 4
    with Hub.open(root, write=True) as h:                    # sonra düzgün göç eder
        assert h.schema_version == 5
