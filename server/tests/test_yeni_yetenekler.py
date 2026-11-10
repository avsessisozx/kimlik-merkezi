"""İ2 turu (INTERFACES Ek 1.6): zengin kimlik kartı, eşanlamlı arama, `say` toplulaştırma,
yerel saat, zamansız kayıtlar ve izin sızıntısı yokluğu. Tüm veri uydurmadır."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from kimlikcore import EventIn, Hub

from helpers import FakeClock, ev
from kimlikserver import esanlam
from kimlikserver.access import KeyManager
from kimlikserver.kart import KART_UST_SINIR
from kimlikserver.persona import Persona, PersonaReader
from kimlikserver.service import QueryService, ServiceError
from kimlikserver.yerelsaat import YerelSaat

IST = YerelSaat.cozumle("Europe/Istanbul")
SIMDI = datetime(2026, 11, 10, 9, 0, 0, tzinfo=timezone.utc)
ACIK = ["tarama", "video", "sosyal", "muzik", "kod", "persona"]
GIZLI = ["GIZLI-EPOSTA-QX7", "GIZLI-MESAJ-QX7", "GIZLI-KONUM-QX7", "GIZLI-SOHBET-QX7"]


def _olaylar():
    """Sentetik kişi: 300 dinleme (2 sanatçı), sabahçı commit'ler, aramalar, zamansız abonelikler
    ve dört hassas kategoriden işaretli kayıtlar."""
    out = []
    for i in range(300):  # 240 Mavi Dalga + 60 Gece Vardiyası (son 200 kayıt örneklemi yanıltır)
        sanatci = "Gece Vardiyası" if i >= 240 else "Mavi Dalga"
        gun = 1 + i // 12
        out.append(EventIn(ts=f"2026-0{1 + (i % 9)}-{(i % 27) + 1:02d}T{(i % 20) + 1:02d}:10:00Z",
                           kind="spotify.dinleme", category="muzik",
                           payload={"sanatci": sanatci, "sarki": f"Şarkı {i % 7}"},
                           text=f"Şarkı {i % 7} {sanatci}", event_key=f"mz{i}") if gun else None)
    for i in range(40):  # UTC 02:30-03:50 -> İstanbul 05:30-06:50
        out.append(EventIn(ts=f"2026-10-{(i % 27) + 1:02d}T0{2 + i % 2}:{30 + i % 20}:00Z",
                           kind="github.commit", category="kod",
                           payload={"depo": "https://github.com/ornek/mahalle-takvimi"},
                           text=f"düzeltme {i}", event_key=f"kd{i}"))
    out.append(EventIn(ts="2026-03-03T12:00:00Z", kind="github.depo", category="kod",
                       payload={"ad": "mahalle-takvimi", "dil": "Python"}, text="mahalle-takvimi",
                       event_key="depo1"))
    for i, t in enumerate(["fedora kurulumu", "fedora kurulumu", "ubuntu usb hazırlama",
                           "kızılay kafe", "linux nedir"]):
        out.append(EventIn(ts=f"2026-10-{20 + i:02d}T10:00:00Z", kind="google.arama",
                           category="tarama", payload={"baslik": "Searched for " + t},
                           text="Searched for " + t, event_key=f"ar{i}"))
    for i in range(3):  # zamansız: zamanı dosya tarihi
        out.append(EventIn(ts="2026-11-10T09:00:00Z", kind="youtube.abonelik", category="video",
                           payload={"kanal_adi": f"Kanal {i}", "zaman_kaynagi": "dosya_tarihi"},
                           text=f"Kanal {i}", event_key=f"ab{i}"))
    out += [ev(GIZLI[0], "eposta", payload={"konu": GIZLI[0]}),
            ev(GIZLI[1], "mesaj", payload={"govde": GIZLI[1]}),
            EventIn(ts="2026-09-01T06:00:00Z", kind="google.yer_ziyareti", category="konum",
                    payload={"ad": GIZLI[2], "enlem": 39.9, "boylam": 32.8},
                    text=GIZLI[2] + " Ümitköy Çankaya", event_key="kn1"),
            EventIn(ts="2026-09-02T06:00:00Z", kind="sohbet.mesaj", category="sohbet",
                    payload={"platform": "chatgpt"}, text=GIZLI[3] + " Kızılay", event_key="sh1")]
    return [e for e in out if e is not None]


@pytest.fixture
def dunya(veri):
    with Hub.open(veri, write=True) as hub:
        sid = hub.add_source("test", "1", None)
        hub.add_events(sid, _olaylar())
        km = KeyManager(hub)
        app, anahtar = km.create_key("Acik")
        for k in ACIK:
            km.grant(app, k)
        # hassasların hepsi AÇIK olan ikinci anahtar (kartın yine de içerik taşımadığını sınamak için)
        app2, anahtar2 = km.create_key("Hepsi")
        for k in ACIK:
            km.grant(app2, k)
        for k in ("eposta", "mesaj", "konum", "sohbet"):
            km.grant(app2, k, confirmed_sensitive=True)
        p = Persona(hub, clock=lambda: datetime(2026, 1, 15, 12, tzinfo=timezone.utc))
        p.add_fact("Adı Deneme Kişi", "kimlik")
        p.add_fact("Fedora Linux kullanan dizüstü bilgisayarı var", "cihazlar", fact_key="pc")
        p.add_fact("Eski şehir Bursa", "kimlik", fact_key="sehir")
        p2 = Persona(hub, clock=lambda: datetime(2026, 8, 1, 12, tzinfo=timezone.utc))
        p2.add_fact("Şehir Ankara", "kimlik", fact_key="sehir")  # öncekini yerinden eder
        with hub.transaction() as c:
            c.execute("INSERT INTO facts(fact_id, statement, source_id, date, status, valid_from, "
                      "valid_until, category, fact_key, hidden, updated) VALUES ('oneri-1', "
                      "'ONAYSIZ-CIKARIM', NULL, '2026-10-01T00:00:00Z', 'cikarilan', NULL, NULL, "
                      "'ilgi', NULL, 0, '2026-10-01T00:00:00Z')")
    return {"root": veri, "key": anahtar, "key_hepsi": anahtar2}


def svc(d, key=None, tz=IST):
    return QueryService(d["root"], key or d["key"], clock=FakeClock(SIMDI), saat_dilimi=tz)


# ------------------------------------------------------------------ kimlik kartı
def test_kart_beyan_etiketleri_eskiyen_ayri_cikarilan_ve_yerinden_edilen_yok(dunya):
    kart = svc(dunya).kimlik_karti()["veri"]
    canli, eski = kart.split("### Süresi doldu - doğrulanmadı")
    eski = eski.split("## Veriden özet")[0]
    assert "Adı Deneme Kişi (beyan, son doğrulama: 2026-01-15)" in canli
    assert "Şehir Ankara (beyan" in canli
    assert "Fedora" not in canli and "[Cihazlar] Fedora Linux" in eski  # sessizce düşmedi, AYRI
    assert "Bursa" not in kart  # çelişkiyle yerini yenisine bırakan bilgi kartta yok
    assert "ONAYSIZ-CIKARIM" not in kart  # onaysız öneri/çıkarım kartta yok
    assert "## Bilinmeyenler / veride bulunamayanlar" in kart


def test_kart_veri_ozeti_yerel_saat_ve_etiketler(dunya):
    kart = svc(dunya).kimlik_karti()["veri"]
    assert "[çıkarım] En çok dinlenen sanatçılar (dinleme sayısı): Mavi Dalga (240), Gece Vardiyası (60)" in kart
    assert "mahalle-takvimi (" in kart and "Python (1)" in kart
    # UTC 02:30-03:50 commit'ler İstanbul'da (+03:00) 05:30-06:50
    assert "Kod etkinliği en çok 05:00-06:59 arasında (yerel saat, Europe/Istanbul +03:00" in kart
    assert "fedora (2)" in kart  # arama sözcükleri
    assert "yerel: 2026-11-10T12:00:00+03:00 (Europe/Istanbul)" in kart
    # varsayılan UTC çıktısı farklı saat verir ve bunu açıkça yazar
    utc = svc(dunya, tz=YerelSaat.cozumle("UTC")).kimlik_karti()["veri"]
    assert "02:00-03:59" in utc and "(UTC)" in utc


@pytest.mark.parametrize("anahtar", ["key", "key_hepsi"])
def test_kartta_hassas_kategorilerden_hicbir_icerik_yok(dunya, anahtar):
    """Hassas kategoriler İZİNLİ olsa bile kartta içerik/özet yok; izinsizse zaten yok."""
    r = svc(dunya, dunya[anahtar]).kimlik_karti()
    govde = json.dumps(r, ensure_ascii=False)
    for g in GIZLI:
        assert g not in govde
    assert "Ümitköy" not in govde and "Çankaya" not in govde
    assert set(r["ozet_kategorileri"]) <= {"kod", "tarama", "video", "muzik", "sosyal"}
    for hassas in ("eposta", "mesaj", "konum", "sohbet"):
        assert hassas not in r["veri"]  # kart reddedilen/özetlenmeyen kategori adı bile taşımaz


def test_kart_okuyucusu_hassas_kategori_verilse_de_yok_sayar(dunya):
    with Hub.open(dunya["root"], write=False) as hub:
        kart = PersonaReader(hub, clock=FakeClock(SIMDI)).export_identity_card(
            veri_kategorileri=["eposta", "mesaj", "konum", "sohbet", "muzik"], saat_dilimi=IST)
    assert "Mavi Dalga" in kart
    assert not any(g in kart for g in GIZLI)


def test_kart_boyut_siniri_ve_oncelik(dunya):
    with Hub.open(dunya["root"], write=True) as hub:
        sid = hub.add_source("buyuk", "1", None)
        hub.add_events(sid, [EventIn(ts=f"2026-10-{1 + i % 27:02d}T10:{i % 60:02d}:00Z",
                                     kind="github.commit", category="kod",
                                     payload={"depo": f"depo-{i:04d}-" + "u" * 80},
                                     text="x", event_key=f"b{i}") for i in range(400)])
        p = Persona(hub, clock=FakeClock(SIMDI))
        for i in range(80):
            p.add_fact(f"Beyan {i} " + "a" * 150, "tercihler")
    with Hub.open(dunya["root"], write=False) as hub:
        kart = PersonaReader(hub, clock=FakeClock(SIMDI)).export_identity_card(
            veri_kategorileri=ACIK[:5], saat_dilimi=IST, )
    assert len(kart) <= KART_UST_SINIR + 3000  # beyan üst sınırı + bilinmeyenler her zaman girer
    assert "## Bilinmeyenler / veride bulunamayanlar" in kart  # öncelikli bölüm düşmedi
    assert "beyan daha gösterilmedi" in kart  # kırpılan beyan sayısı sessizce gizlenmez
    assert 30 <= kart.count("- Beyan ") <= 40


def test_kart_ozet_kapali_ve_izin_gerekli(dunya):
    r = svc(dunya).kimlik_karti(ozet=False)
    assert "Veriden özet" not in r["veri"] and r["ozet_kategorileri"] == []
    with pytest.raises(ServiceError):  # persona izni olmayan anahtar
        with Hub.open(dunya["root"], write=True) as hub:
            km = KeyManager(hub)
            a, k = km.create_key("PersonaYok")
            km.grant(a, "muzik")
        svc(dunya, k).kimlik_karti()


# ------------------------------------------------------------------ say
def test_say_tum_kayitlar_uzerinden_sayar_son_200_degil(dunya):
    s = svc(dunya)
    r = s.say("sanatci", en_cok=2)
    assert [(x["veri"], x["sayi"]) for x in r["satirlar"]] == [("Mavi Dalga", 240), ("Gece Vardiyası", 60)]
    assert r["alanli_kayit"] == 300 and r["farkli_deger"] == 2 and r["diger_sayi"] == 0
    # zaman_cizelgesi son 200 kaydı verir: onlardan saymak yanlış olurdu
    son = s.zaman_cizelgesi("muzik", limit=200)["kayitlar"]
    assert len(son) == 200
    assert r["satirlar"][0]["oran"] == 0.8


def test_say_zaman_araligi_yerel_saat_ve_zamansiz(dunya):
    s = svc(dunya)
    r = s.say("saat", kategori="kod", baslangic="2026-10-01T00:00:00Z", bitis="2026-10-31T23:59:59Z")
    saat = {x["veri"][:2]: x["sayi"] for x in r["satirlar"]}
    assert saat["05"] + saat["06"] == 40 and r["saat_dilimi"]["utc_farki"] == "+03:00"
    assert r["satirlar"][0]["veri"] == "00:00-00:59" and len(r["satirlar"]) == 24
    v = s.say("tur", kategori="video", baslangic="2026-01-01T00:00:00Z")
    assert v["satirlar"] == [] and v["zamansiz_kayit"] == 3 and "zamansız" in " ".join(v["notlar"])
    t = s.say("tur", kategori="video")  # aralıksız: zamansızlar sayılır ama işaretlenir
    assert [(x["veri"], x["sayi"]) for x in t["satirlar"]] == [("youtube.abonelik", 3)]
    assert t["zamansiz_kayit"] == 3
    # saatsiz tarih giren yerel saat sayılır: 2026-10-01T03:00 (+03) == 00:00Z
    assert s.say("tur", kategori="kod", baslangic="2026-10-01T03:00:00")["filtre"]["baslangic_utc"] \
        == "2026-10-01T00:00:00Z"


def test_say_tur_kaynak_ve_gun_ay(dunya):
    s = svc(dunya)
    assert s.say("tur", tur="github.*")["satirlar"][0] == {
        "etiket": "veri", "veri": "github.commit", "sayi": 40, "oran": round(40 / 41, 4)}
    assert s.say("kaynak", kategori="kod")["satirlar"][0]["veri"] == "test"
    assert len(s.say("gun", kategori="kod")["satirlar"]) == 7
    assert all(len(x["veri"]) == 7 for x in s.say("ay", kategori="kod")["satirlar"])
    assert s.say("depo", kategori="kod")["satirlar"][0]["veri"] == "mahalle-takvimi"  # URL son parça
    with pytest.raises(ServiceError, match="Bilinmeyen alan"):
        s.say("parola")
    assert len(s.say("sanatci", en_cok=999)["satirlar"]) <= 50


def test_say_izne_saygili_ve_hassasta_icerik_yok(dunya):
    s = svc(dunya)
    with pytest.raises(ServiceError, match="reddedildi"):
        s.say("tur", kategori="konum")
    tum = json.dumps(s.say("tur"), ensure_ascii=False)  # kategorisiz: yalnız izinli kategoriler
    assert not any(g in tum for g in GIZLI) and "yer_ziyareti" not in tum
    h = svc(dunya, dunya["key_hepsi"])
    # konum izni açık: tür/kategori/zaman sayılır ama yer adı (içerik alanı) HİÇ hesaplanmaz
    assert [x["veri"] for x in h.say("tur", kategori="konum")["satirlar"]] == ["google.yer_ziyareti"]
    d = h.say("depo", kategori="konum")
    assert d["satirlar"] == [] and "hassas" in " ".join(d.get("notlar", []))
    assert GIZLI[2] not in json.dumps(h.say("depo"), ensure_ascii=False)
    assert h.say("platform", kategori="sohbet")["satirlar"][0]["veri"] == "chatgpt"


# ------------------------------------------------------------------ yerel saat
def test_saat_dilimi_cozumleme_ve_uyari(monkeypatch):
    assert YerelSaat.cozumle("Europe/Istanbul").bilgi(SIMDI)["utc_farki"] == "+03:00"
    f = YerelSaat.cozumle("UTC+05:30")
    assert f.yerel("2026-11-10T00:00:00Z") == "2026-11-10T05:30:00+05:30" and f.ad == "UTC+05:30"
    monkeypatch.setenv("KIMLIK_SAAT_DILIMI", "America/New_York")
    ny = YerelSaat.cozumle()
    assert ny.kaynak.startswith("KIMLIK_SAAT_DILIMI") and ny.yerel("2026-07-01T12:00:00Z").endswith("-04:00")
    assert ny.yerel("2026-12-01T12:00:00Z").endswith("-05:00")  # yaz saati doğru
    monkeypatch.setenv("KIMLIK_SAAT_DILIMI", "Yok/Boyle")
    k = YerelSaat.cozumle()
    assert k.uyari and "çözülemedi" in k.bilgi(SIMDI)["uyari"]


def test_ciktilarda_yerel_zaman_ve_zaman_dilimi_aciklik(dunya):
    r = svc(dunya).ara("fedora", genislet=False)
    k = r["kayitlar"][0]
    assert k["zaman"].endswith("Z") and k["yerel_zaman"].endswith("+03:00")
    assert r["saat_dilimi"]["ad"] == "Europe/Istanbul" and "UTC" in r["saat_dilimi"]["aciklama"]
    assert svc(dunya).kategorileri_listele()["saat_dilimi"]["utc_farki"] == "+03:00"
    assert svc(dunya).ornekle("tarama", 3)["saat_dilimi"]["ad"] == "Europe/Istanbul"


# ------------------------------------------------------------------ zamansız kayıtlar
def test_zaman_cizelgesi_zamansizi_ayirir(dunya):
    r = svc(dunya).zaman_cizelgesi("video")
    assert r["kayitlar"] == [] and r["zamansiz_toplam"] == 3 and len(r["zamansiz_kayitlar"]) == 3
    assert all(k["zaman_gercek"] is False for k in r["zamansiz_kayitlar"])
    tum = svc(dunya).zaman_cizelgesi(limit=10)
    assert all("zaman_gercek" not in k for k in tum["kayitlar"])
    assert tum["kayitlar"][0]["zaman"] >= tum["kayitlar"][-1]["zaman"]
    # zaman aralığında zamansızlar gösterilmez ama sayılır
    a = svc(dunya).zaman_cizelgesi("video", baslangic="2026-01-01T00:00:00Z")
    assert a["zamansiz_kayitlar"] == [] and a["zamansiz_toplam"] == 3 and "gösterilmedi" in a["zamansiz_notu"]
    # ara: zamansız kayıt işaretlenir
    z = svc(dunya).ara("Kanal 1", genislet=False)["kayitlar"]
    assert z and z[0]["zaman_gercek"] is False


# ------------------------------------------------------------------ eşanlamlı arama
def test_esanlamli_arama_eslesen_terim_gorunur(dunya):
    s = svc(dunya)
    r = s.ara("Linux")
    dogrudan = [k for k in r["kayitlar"] if k["eslesme"] == "dogrudan"]
    ilgili = [k for k in r["kayitlar"] if k["eslesme"] == "ilgili"]
    assert [k["veri"] for k in dogrudan] == ["Searched for linux nedir"]
    assert {k["eslesen_terim"] for k in ilgili} == {"fedora", "ubuntu"}
    assert all(k["aranan_terim"] == "Linux" for k in ilgili)
    assert r["kayitlar"].index(dogrudan[0]) < r["kayitlar"].index(ilgili[0])  # doğrudan önce
    ozet = r["genisletilen_terimler"][0]
    assert ozet["terim"] == "Linux" and {"terim": "fedora", "kayit": 2} in ozet["iliskili"]
    assert "genislet=false" in r["genisletme_notu"]
    kapali = s.ara("Linux", genislet=False)
    assert [k["veri"] for k in kapali["kayitlar"]] == ["Searched for linux nedir"]
    assert "genisletilen_terimler" not in kapali


def test_esanlam_turkce_katlama_bozulmaz_ve_izin_asilmaz(dunya):
    s = svc(dunya)
    assert [k["veri"] for k in s.ara("KIZILAY", genislet=False)["kayitlar"]] == ["Searched for kızılay kafe"]
    assert [k["veri"] for k in s.ara("kizilay")["kayitlar"]] == ["Searched for kızılay kafe"]
    # sözlük genişletmesi izinsiz kategoriye ulaşamaz: kullanıcı sözlüğü 'semt' -> hassas kayıt metni
    (dunya["root"] / "esanlamlilar.json").write_text(json.dumps(
        {"alt_kavramlar": {"semt": ["ümitköy", "GIZLI-KONUM-QX7"]}}), encoding="utf-8")
    r = s.ara("semt")
    assert r["kayitlar"] == []
    assert GIZLI[2] not in json.dumps(r["kayitlar"], ensure_ascii=False)
    h = svc(dunya, dunya["key_hepsi"]).ara("semt")  # izin varsa gelir ve 'ilgili' diye işaretlenir
    assert {k["eslesme"] for k in h["kayitlar"]} == {"ilgili"}


def test_sozluk_dosyasi_yapisi_ve_genisletilebilirlik(tmp_path):
    soz = esanlam.yukle()
    assert "fedora" in soz.genislet("linux") and "linux" not in soz.genislet("fedora")  # tek yön
    assert soz.genislet("kahve")[0] == "coffee" and "v60" in soz.genislet("kahve")
    assert soz.genislet("hiçbirşeyyok") == []
    assert "kiralık" not in soz.genislet("ev")  # uydurma ilişki yok
    d = tmp_path / "v"
    d.mkdir()
    (d / "esanlamlilar.json").write_text('{"esanlamlilar": [["foo", "bar"]]}', encoding="utf-8")
    assert esanlam.yukle(d).genislet("FOO") == ["bar"]
    assert esanlam.yukle(d).genislet("linux")  # paket içi sözlük korunur
    (d / "esanlamlilar.json").write_text("bozuk{", encoding="utf-8")
    assert esanlam.yukle(d).genislet("linux")  # bozuk dosya sessizce atlanır
    vs = esanlam.varyantlar("linux kurulum", soz)
    assert vs and len(vs) <= esanlam.VARYANT_UST and vs[0].sorgu == '"fedora" kurulum'
    assert esanlam.varyantlar("kel*", soz) == []


# ------------------------------------------------------------------ izin sızıntısı (Q31 kanıtı)
ARAMALAR = ["kızılay", "çankaya", "ümitköy", "semt", "ofis", "hafta içi", "linux", "kafe", "GIZLI"]


def _tum_araclar(s: QueryService):
    for q in ARAMALAR:
        yield s.ara(q, limit=200)
        yield s.ornekle("tarama", 200, q)
    yield s.zaman_cizelgesi(limit=200)
    for k in ("tarama", "video", "sosyal", "muzik", "kod"):
        yield s.zaman_cizelgesi(k, limit=200)
    for alan in ("tur", "kategori", "kaynak", "platform", "terim", "site", "kanal", "sanatci",
                 "depo", "dil", "saat", "gun", "ay"):
        yield s.say(alan, en_cok=50)
    yield s.kimlik_karti()
    yield s.persona_getir()


def test_izinsiz_kategori_hicbir_aractan_sizmaz(dunya):
    s = svc(dunya)  # ACIK: hassas kategori izni YOK
    metin = ""
    for r in _tum_araclar(s):
        metin += json.dumps(r, ensure_ascii=False)
    for g in GIZLI:
        assert g not in metin
    assert "Ümitköy" not in metin and "yer_ziyareti" not in metin
    for kat in ("eposta", "mesaj", "konum", "sohbet"):
        with pytest.raises(ServiceError, match="reddedildi"):
            s.ara("GIZLI", kategori=kat)
        with pytest.raises(ServiceError, match="reddedildi"):
            s.say("tur", kategori=kat)
        with pytest.raises(ServiceError, match="reddedildi"):
            s.zaman_cizelgesi(kategori=kat)
    # kayıtların kategorileri yalnız izinli olanlardan
    for r in _tum_araclar(s):
        for k in r.get("kayitlar", []) + r.get("zamansiz_kayitlar", []):
            if "id" in k:  # (persona_getir kayıtlarındaki 'kategori' persona bilgi kategorisidir)
                assert k["kategori"] in ACIK


def test_say_ve_kart_sifreli_klasorde_calisir(tmp_path, monkeypatch):
    from kimlikcore import sifreleme as sif
    monkeypatch.setattr(sif, "KDF_N", 1 << 4)
    monkeypatch.setenv(sif.ENV_SAHTE, "mcp-testi")
    monkeypatch.delenv(sif.ENV_PAROLA, raising=False)
    sif.saglayici_ayarla(None)
    veri = tmp_path / "sifreli"
    veri.mkdir()
    Hub.open(veri, write=True, sifreli=True).close()
    with Hub.open(veri, write=True) as hub:
        hub.add_events(hub.add_source("t", "1", None), _olaylar())
        km = KeyManager(hub)
        a, k = km.create_key("A")
        for c in ACIK:
            km.grant(a, c)
        Persona(hub, clock=FakeClock(SIMDI)).add_fact("Adı Deneme", "kimlik")
    assert sif.db_durumu(veri / "kimlik.db") == "sifreli"
    s = QueryService(veri, k, clock=FakeClock(SIMDI), saat_dilimi=IST)
    assert s.say("sanatci", en_cok=1)["satirlar"][0]["sayi"] == 240
    kart = s.kimlik_karti()["veri"]
    assert "Mavi Dalga (240)" in kart and not any(g in kart for g in GIZLI)
    assert s.ara("linux")["kayitlar"]
