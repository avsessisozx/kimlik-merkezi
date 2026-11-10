"""Uygulama iş mantığı: tek yazan Hub'ı tutar, ekranların her işlemini düz sözlük olarak döner.
Arayüz katmanından (web/tepsi) bağımsızdır ve doğrudan test edilir."""
from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kimlikcore import Category, FormatError, Hub, KimlikError, NotFoundError, fold
from kimlikcore import sifreleme as sif
from kimlikimport import ImportFormatError, registry
from kimlikimport.run import run as ice_aktar_calistir
from kimlikserver.access import KeyManager
from kimlikserver.oneri import OneriYonetici
from kimlikserver.persona import CATEGORY_TITLES, FACT_CATEGORIES, Persona

from . import claude_ayar, gunluk, harita_kopru
from .yollar import ayar_dizini

MCP_PAROLA_NOTU = (
    "Bu veri klasörü parolayla korunuyor. Claude (MCP) parola giremez ve parolayı Claude'un ayar dosyasına "
    "yazmak korumayı ortadan kaldırır (aynı Windows hesabındaki her program o dosyayı okuyabilir), bu yüzden "
    "parolalı klasör Claude'a otomatik eklenmez. Claude'un erişmesini istiyorsanız Güvenlik sayfasından "
    "parolayı kaldırın (veri yine Windows hesabınıza bağlı şifreli kalır).")
MCP_PAROLA_ONCE_NOTU = (
    "Parola eklerseniz Claude (MCP) bu klasörü açamaz: parola giremez ve parolayı Claude'un ayar dosyasına "
    "yazmak korumayı ortadan kaldırırdı (aynı Windows hesabındaki her program o dosyayı okuyabilir). Bu yüzden "
    "parolalı klasör Claude'a otomatik eklenmez. Claude erişimi istiyorsanız parola eklemeyin ya da sonra kaldırın.")
SIL_ONAY_METNI = "SİL"
KATEGORI_ETIKETLERI = {
    "tarama": "Tarama geçmişi", "video": "Video", "sosyal": "Sosyal medya", "muzik": "Müzik",
    "kod": "Kod", "notlar": "Notlar ve linkler", "dosyalar": "Dosyalar", "medya_meta": "Fotoğraf/video bilgisi",
    "uygulama": "Uygulama kullanımı", "persona": "Persona", "eposta": "E-posta", "mesaj": "Özel mesajlar",
    "konum": "Konum", "sohbet": "Yapay zekâ sohbetleri",
}


def kategori_adi(kimlik: str) -> str:
    """Etiketi olmayan (yeni eklenmiş) kategoride KeyError yerine kimliği gösterir."""
    return KATEGORI_ETIKETLERI.get(kimlik, kimlik)


class IslemHatasi(Exception):
    """Kullanıcıya olduğu gibi gösterilebilir Türkçe hata (kayıt içeriği taşımaz)."""

    def __init__(self, mesaj: str, kod: str = "hata", ek: str | None = None):
        super().__init__(mesaj)
        self.kod, self.ek = kod, ek


def _olay(e) -> dict[str, Any]:
    return {"id": e.event_id, "zaman": e.ts, "tur": e.kind, "kategori": e.category,
            "metin": e.text, "kaynak": e.source_id}


def _fact(f) -> dict[str, Any]:
    return {"id": f.fact_id, "metin": f.statement, "kategori": f.category, "durum": f.status,
            "kaynak": f.source_id, "tarih": f.date, "gecerlilik_bitis": f.valid_until, "anahtar": f.fact_key}


class IceAktarmaIsi:
    """Arka planda çalışan tek içe aktarma. Durum ilerleme çubuğu için sorgulanır."""

    def __init__(self, yol: str, tur: str | None, yine_de: bool):
        self.yol, self.tur, self.yine_de = yol, tur, yine_de
        self.durum = "calisiyor"         # calisiyor | bitti | hata
        self.asama = "dogrula"
        self.sayi = 0
        self.sonuc: str | None = None
        self.hata: str | None = None
        self.hata_kodu: str | None = None
        self.biçim_raporu: str | None = None
        self._kilit = threading.Lock()

    def to_dict(self) -> dict[str, Any]:
        with self._kilit:
            return {"durum": self.durum, "asama": self.asama, "sayi": self.sayi, "yol": self.yol,
                    "sonuc": self.sonuc, "hata": self.hata, "hata_kodu": self.hata_kodu,
                    "bicim_raporu": self.biçim_raporu}

    def ilerleme(self, asama: str, sayi: int) -> None:
        with self._kilit:
            self.asama, self.sayi = asama, sayi


class Uygulama:
    def __init__(self, veri: str | Path, *, ayar_dizin: Path | None = None,
                 claude_yolu: Callable[[], Path | None] = claude_ayar.bul, parola: str | None = None):
        self.veri = Path(veri)
        self.ayar_dizin = Path(ayar_dizin) if ayar_dizin else ayar_dizini()
        self._claude_yolu = claude_yolu
        self.hub = Hub.open(self.veri, write=True, parola=parola)   # tek yazan süreç: hub.lock alınır
        self.persona = Persona(self.hub)
        self.anahtarlar = KeyManager(self.hub)
        self.oneriler = OneriYonetici(self.hub, self.veri, persona=self.persona)
        self.is_: IceAktarmaIsi | None = None
        self._harita_kilit = threading.RLock()   # web iş parçacıkları aynı SQLite bağlantısını eşzamanlı kullanmasın
        self.hassas_acik: set[str] = set()      # yalnız bu oturum ve bu kişi için; kalıcı değil
        self._is_kilit = threading.Lock()
        self.eskiyen = self.persona.check_expiry()   # açılışta süre kontrolü
        gunluk.log().info("hub açıldı; süresi dolan bilgi: %d", self.eskiyen)

    def kapat(self) -> None:
        self.hub.close()

    # ------------------------------------------------------------------ durum
    def durum(self) -> dict[str, Any]:
        ozet = self.hub.summary()
        kaynaklar = self.hub.sources(include_removed=False)
        acik = len(self.persona.list_contradictions())
        return {"veri_klasoru": str(self.veri), "sema": self.hub.schema_version,
                "ozet": ozet, "kaynak_sayisi": len(kaynaklar),
                "acik_celiski": acik, "eskiyen": self.eskiyen,
                "kategoriler": self.kategoriler()}

    @staticmethod
    def kategoriler() -> list[dict[str, Any]]:
        return [{"kimlik": k, "ad": kategori_adi(k), "hassas": k in Category.SENSITIVE}
                for k in sorted(Category.ALL, key=lambda x: (x in Category.SENSITIVE, x))]

    # ------------------------------------------------------------------ persona haritası (§12)
    def _kopru(self, fn, *a, **kw):
        try:
            with self._harita_kilit:
                return fn(self.hub, *a, **kw)
        except harita_kopru.HaritaYok as e:
            raise IslemHatasi(str(e), "harita_yok") from None
        except harita_kopru.OzellikYok as e:
            raise IslemHatasi(str(e), "ozellik_yok") from None
        except NotFoundError as e:
            raise IslemHatasi(str(e), "yok") from None

    def harita(self, aralik: dict | None = None) -> dict[str, Any]:
        return self._kopru(harita_kopru.harita, self.hassas_acik, aralik)

    def harita_bolge(self, bolge_id: str, filtre: dict | None = None, aralik: dict | None = None) -> dict[str, Any]:
        return self._kopru(harita_kopru.bolge, bolge_id, self.hassas_acik, filtre, aralik)

    def harita_kayitlar(self, bolge_id: str, filtre: dict | None = None, aralik: dict | None = None,
                        limit: int = 20, offset: int = 0) -> dict[str, Any]:
        return self._kopru(harita_kopru.kayitlar, bolge_id, self.hassas_acik, filtre, aralik, limit, offset)

    def harita_ayrinti(self, olay_id: str) -> dict[str, Any]:
        return self._kopru(harita_kopru.ayrinti, olay_id, self.hassas_acik)

    def harita_hassas(self, bolge_id: str, ac: bool, onay: bool = False) -> dict[str, Any]:
        """Hassas bölgenin SAYILARINI açar/kapatır; açmak için ayrı onay şart, içerik hiçbir zaman gösterilmez."""
        if bolge_id not in harita_kopru.HASSAS:
            raise IslemHatasi("Bu bölge hassas değil.")
        if ac:
            if not onay:
                raise IslemHatasi("Hassas bölgeyi açmak için onay gerekir.", "onay_yok")
            self.hassas_acik.add(bolge_id)
        else:
            self.hassas_acik.discard(bolge_id)
        return {"acik": sorted(self.hassas_acik)}

    # ------------------------------------------------------------------ arama ve zaman çizelgesi
    def ara(self, sorgu: str, kategoriler: list[str] | None = None, limit: int = 50) -> dict[str, Any]:
        if not (sorgu or "").strip():
            return {"kayitlar": []}
        ev = self.hub.search(sorgu, categories=kategoriler or None, limit=min(int(limit), 200), prefix=True)
        return {"kayitlar": [_olay(e) for e in ev]}

    def zaman(self, kategoriler: list[str] | None = None, baslangic: str | None = None,
              bitis: str | None = None, limit: int = 100, atla: int = 0) -> dict[str, Any]:
        ev = self.hub.timeline(categories=kategoriler or None, since=baslangic or None, until=bitis or None,
                               limit=min(int(limit), 500), offset=int(atla))
        return {"kayitlar": [_olay(e) for e in ev]}

    def kayit_gizle(self, olay_id: str) -> dict:
        self.hub.hide_event(olay_id, "kullanıcı gizledi")
        return {"ok": True}

    # ------------------------------------------------------------------ kaynaklar
    def kaynaklar(self) -> dict[str, Any]:
        return {"kaynaklar": [
            {"id": s.source_id, "tur": s.kind, "surum": s.version, "alindi": s.imported_at,
             "kaldirildi": s.removed_at, "neden": s.removed_reason, "kayit": s.event_count}
            for s in self.hub.sources()]}

    def kaynak_kaldir(self, kaynak_id: str, neden: str = "") -> dict:
        n = self.hub.remove_source(kaynak_id, neden or "kullanıcı kaldırdı")
        return {"gizlenen": n}

    def kaynak_sil(self, kaynak_id: str, onay: str = "") -> dict:
        """KALICI silme. Onay çağıranın sorumluluğudur (INTERFACES Ek 1.1): arayüz "SİL" yazdırır."""
        if fold((onay or "").strip()) != fold(SIL_ONAY_METNI):
            raise IslemHatasi(f"Kalıcı silmek için onay kutusuna {SIL_ONAY_METNI} yazın.", "onay_yok")
        r = self.hub.purge_source(kaynak_id)
        return {"silinen_olay": r.events_deleted, "silinen_dosya": r.raw_files_deleted,
                "eskiyen_bilgi": r.facts_demoted}

    # ------------------------------------------------------------------ içe aktarma
    def turler(self) -> dict:
        return {"turler": registry.names()}

    def ice_aktar_baslat(self, yol: str, tur: str | None = None, yine_de: bool = False) -> dict:
        yol = (yol or "").strip().strip('"')
        if not yol:
            raise IslemHatasi("Bir dosya ya da klasör yolu yazın ya da seçin.")
        with self._is_kilit:
            if self.is_ and self.is_.durum == "calisiyor":
                raise IslemHatasi("Başka bir içe aktarma sürüyor.", "mesgul")
            is_ = IceAktarmaIsi(yol, tur or None, bool(yine_de))
            self.is_ = is_
        self._is_dosyasi({"yol": yol, "tur": tur, "durum": "calisiyor"})
        threading.Thread(target=self._ice_aktar_is, args=(is_,), daemon=True, name="ice-aktar").start()
        return is_.to_dict()

    def _ice_aktar_is(self, is_: IceAktarmaIsi) -> None:
        try:
            r = ice_aktar_calistir(self.hub, is_.yol, is_.tur, yine_de=is_.yine_de, progress=is_.ilerleme)
            with is_._kilit:
                is_.sonuc, is_.durum = str(r), "bitti"
            self._is_dosyasi({"yol": is_.yol, "tur": is_.tur, "durum": "bitti"})
            gunluk.log().info("içe aktarma bitti: %s eklenen=%d tekrar=%d", r.importer, r.added, r.duplicate)
        except ImportFormatError as e:
            with is_._kilit:
                is_.durum, is_.hata_kodu = "hata", "bicim"
                is_.hata, is_.biçim_raporu = "Bu dosya beklenen biçimde değil.", e.report.to_text()
            self._is_dosyasi({"yol": is_.yol, "tur": is_.tur, "durum": "hata"})
            gunluk.log().warning("içe aktarma: biçim uygun değil (%s)", e.report.importer)
        except FormatError as e:
            kod = "daha_once_silinmis" if "kalıcı sildiniz" in str(e) else "hata"
            with is_._kilit:
                is_.durum, is_.hata, is_.hata_kodu = "hata", str(e), kod
            self._is_dosyasi({"yol": is_.yol, "tur": is_.tur, "durum": "hata"})
            gunluk.log().warning("içe aktarma hatası: %s", type(e).__name__)
        except Exception as e:  # beklenmeyen; ayrıntı günlükte (içerik yok)
            with is_._kilit:
                is_.durum, is_.hata, is_.hata_kodu = "hata", f"Beklenmeyen hata: {type(e).__name__}: {e}", "beklenmeyen"
            self._is_dosyasi({"yol": is_.yol, "tur": is_.tur, "durum": "hata"})
            gunluk.log().error("içe aktarma beklenmeyen hata: %s", type(e).__name__)

    def ice_aktar_durum(self) -> dict:
        return self.is_.to_dict() if self.is_ else {"durum": "yok"}

    def _is_dosyasi(self, veri: dict) -> None:
        try:
            self.ayar_dizin.mkdir(parents=True, exist_ok=True)
            (self.ayar_dizin / "ice_aktar_durum.json").write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def yarim_kalan_is(self) -> dict | None:
        """Uygulama içe aktarma sürerken kapandıysa son iş: "kaldığı yerden devam" (aynı dosya yeniden
        verilir; kayıtlar event_key ile tekilleştirildiği için tekrar eklenmez)."""
        try:
            d = json.loads((self.ayar_dizin / "ice_aktar_durum.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return d if d.get("durum") == "calisiyor" and not (self.is_ and self.is_.durum == "calisiyor") else None

    # ------------------------------------------------------------------ persona
    def persona_liste(self) -> dict:
        facts = self.persona.list_facts(include_inactive=True)
        return {"bilgiler": [_fact(f) for f in facts], "oneri_sayisi": len(self.oneriler.kuyruk_listele("bekliyor")),
                "kategoriler": [{"kimlik": k, "ad": CATEGORY_TITLES[k]} for k in FACT_CATEGORIES],
                "kaynaklar": [{"id": s.source_id, "ad": f"{s.kind} ({s.imported_at[:10]})"}
                              for s in self.hub.sources(include_removed=False)]}

    def persona_ekle(self, metin: str, kategori: str, kaynak_id: str | None = None,
                     anahtar: str | None = None) -> dict:
        if kaynak_id:
            fid = self.persona.add_fact_from_source(metin, kategori, kaynak_id, fact_key=anahtar or None)
        else:
            fid = self.persona.add_fact(metin, kategori, fact_key=anahtar or None)
        return {"id": fid}

    def persona_guncelle(self, bilgi_id: str, metin: str | None = None, kategori: str | None = None) -> dict:
        self.persona.update_fact(bilgi_id, statement=metin, category=kategori)
        return {"ok": True}

    def persona_sil(self, bilgi_id: str) -> dict:
        self.persona.delete_fact(bilgi_id)
        return {"ok": True}

    def persona_sure_kontrol(self) -> dict:
        return {"eskiyen": self.persona.check_expiry()}

    def celiskiler(self) -> dict:
        return {"celiskiler": [
            {"id": c.contradiction_id, "kategori": c.category, "anahtar": c.fact_key, "acilis": c.opened,
             "eski": _fact(c.old_fact), "yeni": _fact(c.new_fact)}
            for c in self.persona.list_contradictions()]}

    # ------------------------------------------------------------------ persona önerileri (yapay zekâ önerir, kullanıcı onaylar)
    def _oneri(self, o) -> dict[str, Any]:
        adlar = {a[0]: a[1] for a in self.anahtarlar.list_keys()}
        return {"id": o.oneri_id, "ts": o.ts, "uygulama": adlar.get(o.app_id, "bilinmeyen uygulama"), "ifade": o.statement,
                "kategori": o.category, "kategori_ad": CATEGORY_TITLES.get(o.category, o.category), "anahtar": o.fact_key,
                "guven": round(o.guven, 3), "kanit_sayisi": len(o.kanit_event_ids), "durum": o.durum}

    def oneri_listele(self, durum: str | None = "bekliyor") -> dict:
        liste = [self._oneri(o) for o in self.oneriler.kuyruk_listele(durum or None)]
        return {"oneriler": liste, "sayi": len(liste)}

    def oneri_kanit(self, oneri_id: str) -> dict:
        """Önerinin dayandığı kayıtlar (kullanıcı kendi verisini kendi uygulamasında görür; yalnız tıklayınca yüklenir)."""
        o = next((x for x in self.oneriler.kuyruk_listele(None) if x.oneri_id == oneri_id), None)
        if o is None:
            raise IslemHatasi("Öneri bulunamadı.", "yok")
        out = []
        for eid in o.kanit_event_ids:
            try:
                e = self.hub.get_event(eid)
            except NotFoundError:
                out.append({"id": eid, "yok": True})
                continue
            out.append({"id": e.event_id, "yok": False, "zaman": e.ts, "tur": e.kind, "kategori": e.category,
                        "hassas": e.category in Category.SENSITIVE, "gizli": bool(e.hidden), "metin": "" if e.hidden else e.text[:600]})
        return {"kanit": out}

    def oneri_onayla(self, oneri_id: str) -> dict:
        return {"fact_id": self.oneriler.onayla(oneri_id)}

    def oneri_duzelt(self, oneri_id: str, ifade: str) -> dict:
        if not (ifade or "").strip():
            raise IslemHatasi("Düzeltilmiş ifade boş olamaz.")
        return {"fact_id": self.oneriler.duzelt(oneri_id, ifade)}

    def oneri_reddet(self, oneri_id: str) -> dict:
        self.oneriler.reddet(oneri_id)
        return {"ok": True}

    def oneri_hic_dogru_degil(self, oneri_id: str) -> dict:
        self.oneriler.hic_dogru_degil(oneri_id)
        return {"ok": True}

    def oneri_toplu_reddet(self, idler: list[str] | None = None) -> dict:
        return {"reddedilen": self.oneriler.toplu_reddet(idler)}

    def celiski_coz(self, secilen_id: str) -> dict:
        return {"kapanan": self.persona.resolve_contradiction(secilen_id)}

    def kimlik_karti(self, kategoriler: list[str] | None = None) -> dict:
        return {"markdown": self.persona.export_identity_card(kategoriler or None)}

    # ------------------------------------------------------------------ erişim
    def erisim(self) -> dict:
        izinler = self.anahtarlar.list_grants()
        uygulamalar = []
        for app_id, ad, olusturma, iptal in self.anahtarlar.list_keys():
            uygulamalar.append({
                "id": app_id, "ad": ad, "olusturma": olusturma, "iptal": iptal,
                "izinler": [{"kategori": g.category, "bitis": g.expires_at, "hassas_onay": g.confirmed_sensitive}
                            for g in izinler if g.app_id == app_id]})
        return {"uygulamalar": uygulamalar, "kategoriler": self.kategoriler()}

    def anahtar_uret(self, ad: str) -> dict:
        app_id, duz = self.anahtarlar.create_key(ad)
        return {"id": app_id, "anahtar": duz, "uyari": "Bu anahtar yalnızca şimdi gösterilir; saklanmaz."}

    def anahtar_iptal(self, app_id: str) -> dict:
        self.anahtarlar.revoke_key(app_id)
        return {"ok": True}

    def izin_ver(self, app_id: str, kategori: str, bitis: str | None = None, hassas_onay: bool = False) -> dict:
        self.anahtarlar.grant(app_id, kategori, expires_at=bitis or None, confirmed_sensitive=bool(hassas_onay))
        return {"ok": True}

    def izin_kaldir(self, app_id: str, kategori: str) -> dict:
        self.anahtarlar.revoke_grant(app_id, kategori)
        return {"ok": True}

    def izin_toplu(self, app_id: str, bitis: str | None = None) -> dict:
        """Yalnız hassas OLMAYAN kategoriler. Hassaslar tek tek, ayrı onayla açılır."""
        return {"acilan": self.anahtarlar.grant_all_non_sensitive(app_id, expires_at=bitis or None)}

    def erisim_kaydi(self, limit: int = 200) -> dict:
        self.hub.gelen_birlestir()   # MCP süreçlerinin gelen kutusuna bıraktığı kayıtları işle
        satirlar = self.hub.query("SELECT ts, app_id, tool, category, result_count, outcome FROM access_log "
                                  "ORDER BY id DESC LIMIT ?", (min(int(limit), 1000),))
        adlar = {a[0]: a[1] for a in self.anahtarlar.list_keys()}
        return {"satirlar": [{"zaman": r[0], "uygulama": adlar.get(r[1], r[1]), "arac": r[2],
                              "kategori": r[3], "sayi": r[4], "sonuc": r[5]} for r in satirlar]}

    # ------------------------------------------------------------------ bağlantı ve Claude
    def parola_var_mi(self) -> bool:
        z = sif.zarf_oku(self.veri)
        return bool(z and z.get("parola"))

    def baglanti_bilgisi(self, anahtar: str = "<ANAHTAR>") -> dict:
        giris = claude_ayar.giris_olustur(self.veri, anahtar)
        return {"komut": giris["command"], "arguman": giris["args"], "ortam": giris["env"],
                "metin": claude_ayar.ayar_metni(giris),
                "parola_uyari": MCP_PAROLA_NOTU if self.parola_var_mi() else None}

    def claude_ekle(self) -> dict:
        if self.parola_var_mi():
            # Karar (docs/SIFRELEME.md §6): parolayı Claude ayar dosyasına koymayız; sessizce bozuk giriş de yazmayız.
            raise IslemHatasi(MCP_PAROLA_NOTU, "parola_mcp")
        yol = self._claude_yolu()

        def uret() -> tuple[str, str]:
            app_id, duz = self.anahtarlar.create_key("Claude Desktop")
            self.anahtarlar.grant_all_non_sensitive(app_id)  # hassaslar kapalı kalır
            return app_id, duz

        s = claude_ayar.ekle(yol, uret, self.veri)
        if s.durum not in ("eklendi", "guncellendi"):
            s.aranan = claude_ayar.arama_yerleri()
        gunluk.log().info("claude'a ekle: %s", s.durum)
        return s.to_dict()


def simdi() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = ["Uygulama", "IslemHatasi", "KimlikError", "SIL_ONAY_METNI"]
