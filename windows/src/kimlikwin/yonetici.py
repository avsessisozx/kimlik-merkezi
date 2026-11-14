"""Arayüzün tek giriş noktası: ayarlar, sihirbaz, Uygulama (iş mantığı) ve yardımcılar.
Web katmanı yalnızca `api(ad, girdi)` çağırır; kabuk değişirse bu sınıf aynen kalır."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from kimlikcore import AnahtarGerekli, KimlikError

from . import APP_AD, __version__, claude_ayar, harita_kopru, gunluk, hata_raporu, saglik, veri_klasoru
from .ayarlar import Ayarlar
from .baslangic import Otomatik, veri_yolunu_kaydet
from .cekirdek import IslemHatasi, Uygulama
from .tanila_is import TanilaIsi
from .guvenlik import DEGERLENDIRICILER, GUVENLIK_API, KILITLI_IZINLI, MESGUL_IZINLI, Guvenlik

# Uygulama'nın dışarıya açılan yöntemleri (ad -> yöntem). Başka hiçbir şey çağrılamaz.
UYGULAMA_API = frozenset({
    "durum", "ara", "zaman", "kayit_gizle", "kaynaklar", "kaynak_kaldir", "kaynak_sil", "turler",
    "ice_aktar_baslat", "ice_aktar_durum", "persona_liste", "persona_ekle", "persona_guncelle",
    "persona_sil", "persona_sure_kontrol", "oneri_listele", "oneri_kanit", "oneri_onayla", "oneri_duzelt", "oneri_reddet", "oneri_hic_dogru_degil", "oneri_toplu_reddet", "celiskiler", "celiski_coz", "kimlik_karti", "erisim",
    "anahtar_uret", "anahtar_iptal", "izin_ver", "izin_kaldir", "izin_toplu", "erisim_kaydi",
    "baglanti_bilgisi", "claude_ekle", "harita", "harita_bolge", "harita_hassas", "harita_kayitlar", "harita_ayrinti",
})


def sec_dialog(tur: str) -> str | None:
    """Dosya/klasör seçme penceresi, AYRI süreçte (tkinter ana iş parçacığı sorunu olmasın).
    Sonuç geçici dosyayla döner (pencereli exe'de stdout güvenilir değildir)."""
    import os
    import tempfile
    fd, cikti = tempfile.mkstemp(prefix="kimlik-sec-", suffix=".txt")
    os.close(fd)
    taban = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "kimlikwin"]
    try:
        subprocess.run([*taban, "--sec", tur, "--cikti", cikti], timeout=600)
        yol = Path(cikti).read_text(encoding="utf-8").strip()
    except (OSError, subprocess.SubprocessError):
        yol = ""
    finally:
        try:
            os.unlink(cikti)
        except OSError:
            pass
    return yol or None


class Yonetici:
    def __init__(self, ayarlar: Ayarlar | None = None, otomatik: Otomatik | None = None,
                 secici: Callable[[str], str | None] = sec_dialog,
                 claude_yolu: Callable[[], Path | None] = claude_ayar.bul):
        self.ayarlar = ayarlar or Ayarlar()
        self.otomatik = otomatik or Otomatik()
        self.secici = secici
        self.claude_yolu = claude_yolu
        self.uygulama: Uygulama | None = None
        self.son_dogrulama: str | None = None
        self.baslangic_hatasi: str | None = None
        self.cikis_istegi = False
        self.kilit: dict | None = None        # parolalı klasör açılamadı: kilit ekranı bilgisi
        self.mesgul: str | None = None        # "donusum": şifreleme dönüşümü sürüyor, veritabanı kapalı
        self.tanila: TanilaIsi | None = None  # 'Dosyayı denetle' işi (salt okunur, veritabanına dokunmaz)
        self.guvenlik = Guvenlik(self)
        self._api_kilit = threading.RLock()   # kişi değişimi ve sorgular aynı SQLite bağlantısında çakışmasın

    # ------------------------------------------------------------------ yaşam döngüsü
    def baslat(self) -> None:
        """Kurulum tamamlanmışsa seçili kişinin Hub'ını yazan olarak açar. Kilitliyse hata verir."""
        if not (self.ayarlar["ilk_acilis_tamam"] and self.ayarlar["veri_klasoru"]):
            return
        self._kisileri_hazirla()
        k = self._secili_kisi()
        try:
            self.uygulama = self.uygulama_olustur(k["klasor"])
            self.kilit = None
        except AnahtarGerekli:
            # Parolalı klasör: arayüz AÇILIŞTA parola sorar (guvenlik.py); başka hata türleri aynen yükselir.
            kilit = self.guvenlik.kilit_bilgisi(k["klasor"])
            if kilit is None:
                raise
            self.uygulama, self.kilit = None, kilit

    def uygulama_olustur(self, klasor: str, parola: str | None = None) -> Uygulama:
        """Klasörü yazan olarak açar. Parola verilmediyse bellekteki (bu oturumda girilmiş) parola kullanılır."""
        if parola is None:
            parola = self.guvenlik.kayitli_parola(klasor)
        return Uygulama(klasor, ayar_dizin=self.ayarlar.dizin, claude_yolu=self.claude_yolu, parola=parola)

    # ------------------------------------------------------------------ kişiler (her kişi ayrı veri klasörü)
    def _kisileri_hazirla(self) -> None:
        """Eski kurulumlarda (tek veri klasörü) otomatik "Ben" kişisi oluşturur."""
        kisiler = list(self.ayarlar["kisiler"])
        klasor = self.ayarlar["veri_klasoru"]
        if not kisiler and klasor:
            kisiler = [{"id": uuid.uuid4().hex[:8], "ad": "Ben", "klasor": klasor}]
            self.ayarlar.guncelle(kisiler=kisiler, secili_kisi=kisiler[0]["id"])
        elif kisiler and not any(k["id"] == self.ayarlar["secili_kisi"] for k in kisiler):
            self.ayarlar.guncelle(secili_kisi=kisiler[0]["id"], veri_klasoru=kisiler[0]["klasor"])

    def _secili_kisi(self) -> dict:
        return next(k for k in self.ayarlar["kisiler"] if k["id"] == self.ayarlar["secili_kisi"])

    def api_kisiler(self) -> dict:
        self._kisileri_hazirla()
        sec = self.ayarlar["secili_kisi"]
        return {"kisiler": [{**k, "secili": k["id"] == sec} for k in self.ayarlar["kisiler"]], "secili": sec}

    def _gec(self, kisi: dict, parola: str | None = None) -> None:
        """Seçili kişiyi değiştirir: eski Hub kapanır, yenisi açılır; olmazsa eskisi geri açılır."""
        eski = self._secili_kisi() if self.uygulama else None
        self.kapat()
        try:
            self.uygulama = self.guvenlik.parolali(
                kisi["klasor"], parola, lambda: self.uygulama_olustur(kisi["klasor"], parola))
        except BaseException as e:
            if eski:
                self.uygulama = self.uygulama_olustur(eski["klasor"])
            if isinstance(e, IslemHatasi):
                raise
            if isinstance(e, KimlikError):
                raise IslemHatasi(f"{kisi['ad']} açılamadı: {e}", "kisi_acilamadi") from None
            raise
        self.ayarlar.guncelle(secili_kisi=kisi["id"], veri_klasoru=kisi["klasor"])

    def api_kisi_sec(self, kisi_id: str, parola: str | None = None) -> dict:
        kisi = next((k for k in self.ayarlar["kisiler"] if k["id"] == kisi_id), None)
        if kisi is None:
            raise IslemHatasi("Böyle bir kişi yok.")
        if kisi_id != self.ayarlar["secili_kisi"]:
            self._gec(kisi, parola)
        return self.api_kisiler()

    def api_kisi_ekle(self, ad: str, yol: str, parola: str | None = None) -> dict:
        """Yeni kişi = yeni veri klasörü (boş ya da mevcut Kimlik Merkezi klasörü). Eklenince seçilir."""
        ad = (ad or "").strip()
        if not ad or len(ad) > 60:
            raise IslemHatasi("Kişi adı 1-60 karakter olmalı.")
        if any(k["ad"].casefold() == ad.casefold() for k in self.ayarlar["kisiler"]):
            raise IslemHatasi("Bu adda bir kişi zaten var.")
        yol = str(yol).strip().strip('"')
        if any(os.path.normcase(k["klasor"]) == os.path.normcase(yol) for k in self.ayarlar["kisiler"]):
            raise IslemHatasi("Bu klasör başka bir kişiye ait.")
        self.guvenlik.parolali(yol, parola, lambda: veri_klasoru.olustur(yol, parola))
        kisi = {"id": uuid.uuid4().hex[:8], "ad": ad, "klasor": yol}
        self.ayarlar.guncelle(kisiler=[*self.ayarlar["kisiler"], kisi])
        self._gec(kisi)
        return self.api_kisiler()

    def api_kisi_kaldir(self, kisi_id: str) -> dict:
        """Kişiyi listeden çıkarır; veri klasörüne DOKUNMAZ."""
        if kisi_id == self.ayarlar["secili_kisi"]:
            raise IslemHatasi("Seçili kişi kaldırılamaz; önce başka bir kişiyi seçin.")
        self.ayarlar.guncelle(kisiler=[k for k in self.ayarlar["kisiler"] if k["id"] != kisi_id])
        return self.api_kisiler()

    def api_kisi_yeniden_adlandir(self, kisi_id: str, ad: str) -> dict:
        ad = (ad or "").strip()
        if not ad or len(ad) > 60:
            raise IslemHatasi("Kişi adı 1-60 karakter olmalı.")
        self.ayarlar.guncelle(kisiler=[{**k, "ad": ad} if k["id"] == kisi_id else k for k in self.ayarlar["kisiler"]])
        return self.api_kisiler()

    # ------------------------------------------------------------------ dosya denetimi (tanila)
    def _ice_aktar_suruyor(self) -> bool:
        return bool(self.uygulama and self.uygulama.is_ and self.uygulama.is_.durum == "calisiyor")

    def api_ice_aktar_baslat(self, yol: str = "", tur: str | None = None, yine_de: bool = False,
                             yollar: list[str] | None = None) -> dict:
        """Uygulama.ice_aktar_baslat'a gider; yalnız tanila ile aynı anda çalışmasın (paylaşılan arşiv önbelleği)."""
        if self.uygulama is None:
            raise IslemHatasi("Önce ilk açılış sihirbazını tamamlayın.", "sihirbaz_gerekli")
        if self.tanila is not None and self.tanila.canli:
            raise IslemHatasi("Bir dosya denetimi sürüyor; bitmesini bekleyin.", "mesgul")
        return self.uygulama.ice_aktar_baslat(yol, tur, yine_de, yollar)

    def api_tanila_baslat(self, yol: str, adlari_goster: bool = False, ayrinti: bool = False) -> dict:
        """Dosyanın içeriksiz yapı raporunu arka planda üretir. Veritabanına yazmaz, kilit gerektirmez."""
        yol = (yol or "").strip().strip('"') if isinstance(yol, str) else ""
        if not yol:
            raise IslemHatasi("Denetlenecek bir dosya ya da klasör seçin.")
        if not os.path.exists(yol):
            raise IslemHatasi("Bu dosya ya da klasör bulunamadı.")
        if self.tanila is not None and self.tanila.canli:
            raise IslemHatasi("Önceki dosya denetimi hâlâ sürüyor; bitmesini bekleyin.", "mesgul")
        if self._ice_aktar_suruyor():
            raise IslemHatasi("Bir içe aktarma sürüyor; bitince dosyayı denetleyebilirsiniz.", "mesgul")
        self.tanila = TanilaIsi(yol, bool(adlari_goster), bool(ayrinti))
        self.tanila.baslat()
        gunluk.log().info("dosya denetimi başladı")      # yol/ad günlüğe yazılmaz
        return self.tanila.to_dict()

    def api_tanila_durum(self) -> dict:
        return self.tanila.to_dict() if self.tanila else {"durum": "yok"}

    def api_tanila_temizle(self) -> dict:
        """Ekrandan çıkarken raporu bellekten at (rapor yapı bilgisi içerir)."""
        if self.tanila is not None and not self.tanila.canli:
            self.tanila = None
        return {"ok": True}

    def kapat(self) -> None:
        if self.uygulama:
            self.uygulama.kapat()
            self.uygulama = None

    # ------------------------------------------------------------------ API
    def api(self, ad: str, girdi: dict[str, Any]) -> Any:
        if ad == "sec":                       # dosya penceresi dakikalarca açık kalabilir; kilit tutma
            return self.api_sec(**girdi)
        with self._api_kilit:
            return self._api(ad, girdi)

    def _api(self, ad: str, girdi: dict[str, Any]) -> Any:
        if self.mesgul and ad not in MESGUL_IZINLI:
            raise IslemHatasi("Şifreleme dönüşümü sürüyor; bitene kadar bekleyin (uygulamayı kapatmayın).", "mesgul")
        if self.kilit is not None and ad not in KILITLI_IZINLI:
            raise IslemHatasi("Veri klasörü parolayla kilitli; önce parolayı girin.", "kilitli_parola")
        if ad in GUVENLIK_API:
            if ad.startswith("guvenlik_") and self.uygulama is None and ad != "guvenlik_donusum_durum" \
                    and ad not in DEGERLENDIRICILER:
                raise IslemHatasi("Önce ilk açılış sihirbazını tamamlayın.", "sihirbaz_gerekli")
            return getattr(self.guvenlik, "api_" + ad)(**girdi)
        yerel = getattr(self, "api_" + ad, None)
        if yerel is not None:
            return yerel(**girdi)
        if ad in UYGULAMA_API:
            if self.uygulama is None:
                raise IslemHatasi("Önce ilk açılış sihirbazını tamamlayın.", "sihirbaz_gerekli")
            return getattr(self.uygulama, ad)(**girdi)
        raise IslemHatasi("Bilinmeyen işlem.", "yok")

    def api_acilis(self) -> dict:
        return {"sihirbaz": self.uygulama is None and self.kilit is None and not self.mesgul,
                "kilit": self.kilit, "mesgul": self.mesgul,
                "tema": self.ayarlar["tema"], "surum": __version__,
                "ad": APP_AD, "varsayilan_klasor": veri_klasoru.varsayilan_oner(),
                "otomatik_baslat": self.ayarlar["otomatik_baslat"],
                "yarim_is": self.uygulama.yarim_kalan_is() if self.uygulama else None,
                "eskiyen": self.uygulama.eskiyen if self.uygulama else 0,
                "baslangic_hatasi": self.baslangic_hatasi}

    def api_harita_karsilastir(self, kisi_id: str, bolge_id: str, filtre: dict | None = None,
                               aralik: dict | None = None) -> dict:
        """Başka bir kişinin (ya da aynı kişinin) bölge verisi, karşılaştırma için. Diğer kişinin klasörü
        SALT OKUNUR açılır; hassas bölge yalnız bu oturumda zaten açıksa gelir."""
        if self.uygulama is None:
            raise IslemHatasi("Önce ilk açılış sihirbazını tamamlayın.", "sihirbaz_gerekli")
        if kisi_id == self.ayarlar["secili_kisi"]:
            return self.uygulama.harita_bolge(bolge_id, filtre, aralik)
        kisi = next((k for k in self.ayarlar["kisiler"] if k["id"] == kisi_id), None)
        if kisi is None:
            raise IslemHatasi("Böyle bir kişi yok.")
        from kimlikcore import Hub
        try:
            with Hub.open(kisi["klasor"], write=False, parola=self.guvenlik.kayitli_parola(kisi["klasor"])) as hub:
                return {**harita_kopru.bolge(hub, bolge_id, self.uygulama.hassas_acik, filtre, aralik), "kisi": kisi["ad"]}
        except harita_kopru.HaritaYok as e:
            raise IslemHatasi(str(e), "harita_yok") from None
        except AnahtarGerekli:
            raise IslemHatasi(f"{kisi['ad']} parolayla korunuyor; karşılaştırmak için önce Kişi menüsünden o kişiyi "
                              "seçip parolasını girin.", "kisi_acilamadi") from None
        except KimlikError as e:
            raise IslemHatasi(f"{kisi['ad']} okunamadı: {e}", "kisi_acilamadi") from None

    def api_sec(self, tur: str) -> dict:
        if tur not in ("dosya", "klasor", "dosyalar"):
            raise IslemHatasi("Geçersiz seçim türü.")
        secim = self.secici(tur)
        yollar = [y for y in (secim or "").split("\n") if y.strip()] if tur == "dosyalar" else []
        return {"yol": yollar[0] if yollar else secim, "yollar": yollar}

    def api_sihirbaz_denetle(self, yol: str) -> dict:
        return veri_klasoru.denetle(yol).to_dict()

    def api_sihirbaz_tamamla(self, yol: str, otomatik_baslat: bool = True, ad: str = "Ben",
                             parola: str | None = None) -> dict:
        if self.uygulama is not None or self.kilit is not None:
            raise IslemHatasi("Kurulum zaten tamamlanmış.")
        bilgi = self.guvenlik.parolali(yol, parola, lambda: veri_klasoru.olustur(yol, parola))
        kisi = {"id": uuid.uuid4().hex[:8], "ad": (ad or "Ben").strip()[:60] or "Ben", "klasor": bilgi["yol"]}
        self.ayarlar.guncelle(veri_klasoru=bilgi["yol"], ilk_acilis_tamam=True, otomatik_baslat=bool(otomatik_baslat),
                              kisiler=[kisi], secili_kisi=kisi["id"])
        self._otomatik_uygula(bool(otomatik_baslat))
        veri_yolunu_kaydet(bilgi["yol"])
        self.guvenlik.hatirla(bilgi["yol"], parola)
        self.baslat()
        gunluk.log().info("ilk açılış tamamlandı (şema %s)", bilgi["sema"])
        return {**bilgi, "baglanti": self.uygulama.baglanti_bilgisi() if self.uygulama else None}

    def _otomatik_uygula(self, acik: bool) -> str | None:
        if not self.otomatik.desteklenir:
            return "Bu sistemde girişte başlatma desteklenmiyor."
        try:
            self.otomatik.ayarla(acik)
        except OSError as e:
            return f"Girişte başlatma ayarlanamadı: {e.strerror or e}"
        return None

    def api_ayarlar(self) -> dict:
        return {"tema": self.ayarlar["tema"], "otomatik_baslat": self.otomatik.etkin_mi(),
                "otomatik_destek": self.otomatik.desteklenir, "veri_klasoru": self.ayarlar["veri_klasoru"],
                "port": self.ayarlar["port"]}

    def api_ayar_yaz(self, tema: str | None = None, otomatik_baslat: bool | None = None) -> dict:
        uyari = None
        if tema is not None:
            try:
                self.ayarlar.guncelle(tema=tema)
            except ValueError as e:
                raise IslemHatasi(str(e)) from None
        if otomatik_baslat is not None:
            uyari = self._otomatik_uygula(bool(otomatik_baslat))
            if uyari is None:
                self.ayarlar.guncelle(otomatik_baslat=bool(otomatik_baslat))
        return {**self.api_ayarlar(), "uyari": uyari}

    def api_saglik(self) -> dict:
        veri = self.ayarlar["veri_klasoru"]
        if not veri:
            return {"ok": False, "kontroller": [{"ad": "veri klasörü seçildi", "ok": False, "ayrinti": ""}], "metin": ""}
        s = saglik.denetle(veri)
        self.son_dogrulama = ("tüm kontroller geçti" if s["ok"] else "BAŞARISIZ kontroller var") + " (sağlık denetimi)"
        return {**s, "metin": saglik.metin(s)}

    def api_hata_raporu(self, adim: str = "", mesaj: str = "", ek: str = "") -> dict:
        h = RuntimeError(mesaj) if mesaj else None
        return {"metin": hata_raporu.olustur(adim, h, self.son_dogrulama, ek or None, self.ayarlar.dizin)}

    def api_hakkinda(self) -> dict:
        import kimlikcore
        return {"ad": APP_AD, "surum": __version__, "cekirdek": kimlikcore.__version__,
                "python": sys.version.split()[0],
                "veri_klasoru": self.ayarlar["veri_klasoru"],
                "lisanslar": ["Python (PSF)", "SQLite (kamu malı)", "mcp SDK (MIT)", "ijson (BSD-3-Clause)",
                              "PyInstaller (GPLv2+, paketlenen uygulama için istisnalı)",
                              "pystray (LGPL-3.0)", "Pillow (HPND)", "Inno Setup (kendi lisansı)"],
                "sifreleme_notu": "Yeni veri klasörü varsayılan olarak şifrelenir (anahtar Windows hesabınıza bağlıdır; "
                                  "bu hesapta çalışan başka bir program da anahtarı açtırabilir). İsteğe bağlı parola, "
                                  "kurtarma ifadesi ve şifrelemeyi açıp kapatma Güvenlik sayfasındadır. Dışa "
                                  "aktardığınız dosyalar ve cikti klasörü şifrelenmez. Ek önlem olarak veri klasörünü "
                                  "BitLocker/VeraCrypt gibi şifreli bir birimde tutmanız önerilir. "
                                  "Ayrıntı: docs/SIFRELEME.md.",
                "smartscreen_notu": "Uygulama imzasızdır: Windows SmartScreen 'Windows bilgisayarınızı "
                                    "korudu' uyarısı gösterebilir ve bazı antivirüsler yanlış alarm "
                                    "verebilir. Kurulum dosyasının bütünlüğünü SHA256SUMS ile doğrulayın."}

    def api_cikis(self) -> dict:
        self.cikis_istegi = True
        return {"ok": True}


__all__ = ["Yonetici", "KimlikError", "UYGULAMA_API"]
