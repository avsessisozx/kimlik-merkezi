"""Güvenlik sayfasının iş mantığı: şifreleme durumu, kurtarma ifadesi, parola, kurtarma, şifrelemeyi aç/kapat,
açılışta parola kilidi ve yanlış deneme yavaşlatması.

İş mantığı ÇEKİRDEKTE (kimlikcore.sifreleme / donusum / Hub) durur; burası yalnız onları çağırır, kullanıcıya
Türkçe hata ve onay kuralları ekler. KURALLAR:
  * Parola ve kurtarma ifadesi yalnız istek gövdesinde gelir; günlüğe, hata raporuna, hata iletisine YAZILMAZ
    (hata iletileri sabit metindir; web katmanı ayrıca gövdedeki sırları iletilerden süpürür).
  * Parola yalnız bellekte tutulur (`_parolalar`); diske, ayar dosyasına, ortam değişkenine yazılmaz.
  * Kurtarılamaz uyarısı sunucu tarafında da zorunludur (`anladim is True`); arayüz atlansa bile işlem reddedilir.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kimlikcore import AnahtarGerekli, SifrelemeHatasi, YanlisParola
from kimlikcore import donusum
from kimlikcore import sifreleme as sif

from . import claude_ayar, gunluk
from .cekirdek import MCP_PAROLA_NOTU, MCP_PAROLA_ONCE_NOTU, IslemHatasi

if TYPE_CHECKING:  # pragma: no cover
    from .yonetici import Yonetici

KALDIR_ONAY = "KALDIR"      # şifrelemeyi kapatma için yazılacak sözcük (CLI ile aynı)

# Kilitliyken (parola sorulmadan önce) çağrılabilen işlemler. Başka hiçbir şey çalışmaz.
# Kural değerlendiricileri veri okumaz (yalnız gelen metni çekirdek kurallarına göre puanlar); kilit ekranındaki
# "yeni parola" alanı da bunları kullanır.
DEGERLENDIRICILER = frozenset({"guvenlik_ifade_degerlendir", "guvenlik_parola_degerlendir"})
KILITLI_IZINLI = frozenset({"acilis", "parola_ac", "kilit_kurtar", "hata_raporu", "cikis"}) | DEGERLENDIRICILER
# Dönüşüm sürerken (veritabanı kapalı) çağrılabilenler.
MESGUL_IZINLI = frozenset({"acilis", "guvenlik_donusum_durum", "hata_raporu"})

GUVENLIK_API = frozenset({
    "guvenlik_durum", "guvenlik_ifade_degerlendir", "guvenlik_parola_degerlendir", "guvenlik_kurtarma_kur",
    "guvenlik_parola_ekle", "guvenlik_parola_kaldir", "guvenlik_kurtar", "guvenlik_donustur_baslat",
    "guvenlik_donusum_durum", "parola_ac", "kilit_kurtar",
})

SIFRELEME_KAPALI_NOTU = ("Şifreleme kapalı: verileriniz diskte düz metin olarak duruyor. Bu klasörü başka biri "
                         "kopyalarsa okuyabilir.")


def klasor_anahtari(klasor: str | Path) -> str:
    return os.path.normcase(str(klasor))


class DenemeSiniri:
    """Art arda yanlış denemeleri yavaşlatır. İlk 2 hata bedava; sonra 5, 10, 20... sn (üst sınır 300 sn).
    Bekleme sürerken parola HİÇ denenmez (scrypt çalıştırılmaz). Sayaç bellektedir: uygulama yeniden
    başlatılırsa sıfırlanır (dürüst sınır: yerel kaba kuvveti durdurmaz, yalnız yavaşlatır)."""

    ILK_BEDAVA = 2
    TABAN_SN = 5
    UST_SN = 300

    def __init__(self, saat: Callable[[], float] = time.monotonic):
        self._saat = saat
        self._hata = 0
        self._izin_zamani = 0.0
        self._kilit = threading.Lock()

    def kalan(self) -> int:
        with self._kilit:
            return max(0, int(self._izin_zamani - self._saat() + 0.999))

    def kontrol(self) -> None:
        k = self.kalan()
        if k > 0:
            raise IslemHatasi(f"Çok fazla yanlış deneme. {k} saniye sonra yeniden deneyin.", "cok_deneme", str(k))

    def basarisiz(self) -> int:
        """Başarısız denemeyi sayar; uygulanan bekleme süresini (sn) döner."""
        with self._kilit:
            self._hata += 1
            n = self._hata - self.ILK_BEDAVA
            bekle = 0 if n <= 0 else min(self.TABAN_SN * 2 ** (n - 1), self.UST_SN)
            self._izin_zamani = self._saat() + bekle
            return bekle

    def basarili(self) -> None:
        with self._kilit:
            self._hata = 0
            self._izin_zamani = 0.0


class DonusumIsi:
    """Arka planda çalışan şifrele / şifreyi kaldır işi. Durum arayüzden sorgulanır."""

    def __init__(self, tur: str):
        self.tur = tur
        self.durum = "calisiyor"        # calisiyor | bitti | hata
        self.mesaj = "Başlıyor..."
        self.sonuc: dict | None = None
        self.hata: str | None = None
        self._kilit = threading.Lock()

    def ilerleme(self, mesaj: str) -> None:
        with self._kilit:
            self.mesaj = mesaj

    def to_dict(self) -> dict[str, Any]:
        with self._kilit:
            return {"tur": self.tur, "durum": self.durum, "mesaj": self.mesaj, "hata": self.hata,
                    "sonuc": self.sonuc}


class Guvenlik:
    def __init__(self, y: "Yonetici", saat: Callable[[], float] = time.monotonic):
        self.y = y
        self.sinir = DenemeSiniri(saat)
        self._parolalar: dict[str, str] = {}     # YALNIZ bellek; klasör -> parola
        self.is_: DonusumIsi | None = None

    # ------------------------------------------------------------------ yardımcılar
    def _klasor(self) -> Path:
        return Path(self.y.ayarlar["veri_klasoru"])

    def zarf(self, klasor: str | Path) -> dict | None:
        try:
            return sif.zarf_oku(klasor)
        except SifrelemeHatasi:
            return None

    def kayitli_parola(self, klasor: str | Path) -> str | None:
        """Bellekteki parola; yalnız klasörde parola yuvası varsa (aksi halde Hub.open parola yuvasını arar)."""
        z = self.zarf(klasor)
        if not (z and z.get("parola")):
            return None
        return self._parolalar.get(klasor_anahtari(klasor))

    def hatirla(self, klasor: str | Path, parola: str | None) -> None:
        z = self.zarf(klasor)
        if parola and z and z.get("parola"):
            self._parolalar[klasor_anahtari(klasor)] = parola

    def unut(self, klasor: str | Path) -> None:
        self._parolalar.pop(klasor_anahtari(klasor), None)

    def _bekleme_hatasi(self, ne: str) -> IslemHatasi:
        bekle = self.sinir.basarisiz()
        ek = str(bekle) if bekle else None
        mesaj = f"{ne} yanlış."
        if bekle:
            mesaj += f" Çok fazla yanlış deneme: {bekle} saniye bekleyin."
        return IslemHatasi(mesaj, "yanlis_parola", ek)

    def parolali(self, klasor: str | Path, parola: str | None, islev: Callable[[], Any]) -> Any:
        """Parola gerektirebilecek bir açma işlemini çalıştırır: yanlış parolada sayaç, parola yokken
        'parola_gerekli' kodu, başarıda parolayı belleğe alma."""
        if parola is not None:
            self.sinir.kontrol()
        try:
            sonuc = islev()
        except YanlisParola:
            if parola is None:
                raise IslemHatasi("Bu klasör parolayla korunuyor; parolayı girin.", "parola_gerekli") from None
            raise self._bekleme_hatasi("Parola") from None
        except AnahtarGerekli:
            z = self.zarf(klasor)
            if parola is None and z and z.get("parola"):
                raise IslemHatasi("Bu klasör parolayla korunuyor; parolayı girin.", "parola_gerekli") from None
            raise
        if parola is not None:
            self.sinir.basarili()
            self.hatirla(klasor, parola)
        return sonuc

    def _sifreli_olmali(self) -> dict:
        z = self.zarf(self._klasor())
        if z is None or sif.db_durumu(self._klasor() / "kimlik.db") != "sifreli":
            raise IslemHatasi("Bu veri klasörü şifreli değil. Önce şifrelemeyi açın.", "sifreli_degil")
        return z

    def _dek(self) -> bytes:
        k = self._klasor()
        try:
            return sif.anahtari_coz(k, parola=self.kayitli_parola(k))
        except AnahtarGerekli:
            raise IslemHatasi("Anahtar açılamadı. Uygulamayı yeniden başlatıp parolanızı girin.",
                              "anahtar_yok") from None

    @staticmethod
    def _onay(anladim: Any) -> None:
        if anladim is not True:
            raise IslemHatasi("Devam etmek için kurtarılamaz uyarısını okuyup onaylamanız gerekir.", "onay_gerekli")

    def _yeniden_dogrula(self, z: dict, parola: str | None) -> None:
        """Parola varsa tehlikeli işlemden önce parola yeniden istenir (açık bir oturumun başında biri olsa bile)."""
        if not z.get("parola"):
            return
        if not parola:
            raise IslemHatasi("Bu işlem için mevcut parolanızı yazın.", "parola_gerekli")
        self.sinir.kontrol()
        try:
            sif.anahtari_coz(self._klasor(), parola=parola)
        except YanlisParola:
            raise self._bekleme_hatasi("Parola") from None
        self.sinir.basarili()

    def _claude_girisi_var(self) -> bool:
        try:
            yol = self.y.claude_yolu()
            if yol is None:
                return False
            veri = json.loads(Path(yol).read_bytes().decode("utf-8-sig") or "{}")
            return claude_ayar.GIRIS_AD in (veri.get("mcpServers") or {})
        except (OSError, ValueError, AttributeError, TypeError):
            return False

    # ------------------------------------------------------------------ durum
    def api_guvenlik_durum(self) -> dict:
        k = self._klasor()
        d = sif.durum(k)
        sag = sif.varsayilan_saglayici()
        return {
            "klasor": str(k), "sifreli": d["sifreli"], "parola_var": d["parola_var"],
            "kurtarma_var": d["kurtarma_var"], "os_korumasi": d["os_korumasi"],
            "saglayici_var": sag is not None, "saglayici": sag.ad if sag else None,
            "gercek_koruma": bool(sag) and sag.ad != "sahte",
            "ham_dosya_duz": d["ham_dosya_duz"], "duz_kalintilar": d["duz_kalintilar"],
            "eski_sifresiz_dosyalar": d["eski_sifresiz_dosyalar"],
            "claude_girisi_var": self._claude_girisi_var(),
            "kapali_notu": None if d["sifreli"] else SIFRELEME_KAPALI_NOTU,
            "uyari_kurtarma": sif.UYARI_KURTARMA, "mcp_notu": MCP_PAROLA_NOTU, "mcp_notu_ekle": MCP_PAROLA_ONCE_NOTU,
            "kaldir_onay": KALDIR_ONAY,
            "donusum": self.is_.to_dict() if self.is_ else None,
        }

    # ------------------------------------------------------------------ kural göstergeleri (çekirdek doğrulayıcısı)
    def api_guvenlik_ifade_degerlendir(self, ifade: str = "") -> dict:
        return sif.ifade_degerlendir(ifade or "")

    def api_guvenlik_parola_degerlendir(self, parola: str = "", ifade: str | None = None) -> dict:
        return sif.parola_degerlendir(parola or "", ifade)

    # ------------------------------------------------------------------ kurtarma ifadesi ve parola
    def api_guvenlik_kurtarma_kur(self, ifade: str, ifade_tekrar: str, anladim: bool = False,
                                  mevcut_parola: str | None = None) -> dict:
        z = self._sifreli_olmali()
        self._onay(anladim)
        self._yeniden_dogrula(z, mevcut_parola)
        sif.kurtarma_kur(self._klasor(), self._dek(), ifade, ifade_tekrar)
        gunluk.log().info("kurtarma ifadesi kuruldu")
        return {"kurtarma_var": True}

    def api_guvenlik_parola_ekle(self, parola: str, parola_tekrar: str, anladim: bool = False) -> dict:
        z = self._sifreli_olmali()
        if z.get("parola"):
            raise IslemHatasi("Zaten bir parola var. Değiştirmek için önce parolayı kaldırın.", "parola_var")
        if not z.get("kurtarma"):
            raise IslemHatasi("Parola eklemeden önce kurtarma ifadesi kurulmalı.", "kurtarma_gerekli")
        self._onay(anladim)
        sif.parola_ekle(self._klasor(), self._dek(), parola, parola_tekrar)
        self.hatirla(self._klasor(), parola)       # oturum açık kalsın; yeniden başlatınca parola sorulur
        gunluk.log().info("parola eklendi")
        return {"parola_var": True}

    def api_guvenlik_parola_kaldir(self, mevcut_parola: str | None = None) -> dict:
        z = self._sifreli_olmali()
        if not z.get("parola"):
            raise IslemHatasi("Bu klasörde parola yok.", "parola_yok")
        if sif.varsayilan_saglayici() is None:
            raise IslemHatasi("Bu sistemde Windows hesabı koruması (DPAPI) yok; parola kaldırılamaz.", "saglayici_yok")
        self._yeniden_dogrula(z, mevcut_parola)
        sif.parola_kaldir(self._klasor(), self._dek())
        self.unut(self._klasor())
        gunluk.log().info("parola kaldırıldı")
        return {"parola_var": False}

    def api_guvenlik_kurtar(self, ifade: str, yeni_parola: str | None = None,
                            yeni_parola_tekrar: str | None = None) -> dict:
        """Oturum açıkken: parolayı kurtarma ifadesiyle sıfırla (yeni parola) ya da parolasız Windows hesabına bağla."""
        self._sifreli_olmali()
        mod = self._kurtar(self._klasor(), ifade, yeni_parola, yeni_parola_tekrar)
        if mod == "parola":
            self.hatirla(self._klasor(), yeni_parola)
        else:
            self.unut(self._klasor())
        return {"mod": mod}

    def _kurtar(self, klasor: Path, ifade: str, yeni: str | None, yeni_tekrar: str | None) -> str:
        self.sinir.kontrol()
        try:
            mod = sif.kurtar(klasor, ifade, yeni, yeni_tekrar)
        except YanlisParola:
            raise self._bekleme_hatasi("Kurtarma ifadesi") from None
        self.sinir.basarili()
        gunluk.log().info("kurtarma ifadesiyle erişim yeniden kuruldu (%s)", mod)
        return mod

    # ------------------------------------------------------------------ açılış kilidi
    def kilit_bilgisi(self, klasor: str | Path) -> dict | None:
        """Açılamayan klasör için kilit ekranı bilgisi; ekranın çözebileceği durum değilse None."""
        z = self.zarf(klasor)
        if z is None:
            return None
        if z.get("parola"):
            tur = "parola"
        elif z.get("kurtarma"):
            tur = "hesap"        # Windows hesabı anahtarı açamıyor; kurtarma ifadesi var
        else:
            return None
        return {"tur": tur, "klasor": str(klasor), "kurtarma_var": bool(z.get("kurtarma")),
                "kisi": next((k["ad"] for k in self.y.ayarlar["kisiler"]
                              if klasor_anahtari(k["klasor"]) == klasor_anahtari(klasor)), None)}

    def _kilit_gerekli(self) -> dict:
        if self.y.kilit is None:
            raise IslemHatasi("Veri klasörü kilitli değil.", "kilitli_degil")
        return self.y.kilit

    def api_parola_ac(self, parola: str) -> dict:
        kilit = self._kilit_gerekli()
        if kilit["tur"] != "parola":
            raise IslemHatasi("Bu klasör parolayla değil; kurtarma ifadesiyle açılır.", "parola_degil")
        self.sinir.kontrol()
        try:
            uyg = self.y.uygulama_olustur(kilit["klasor"], parola)
        except YanlisParola:
            raise self._bekleme_hatasi("Parola") from None
        self.sinir.basarili()
        self.hatirla(kilit["klasor"], parola)
        self.y.uygulama, self.y.kilit = uyg, None
        gunluk.log().info("parolalı klasör açıldı")
        return {"ok": True}

    def api_kilit_kurtar(self, ifade: str, yeni_parola: str | None = None,
                         yeni_parola_tekrar: str | None = None) -> dict:
        kilit = self._kilit_gerekli()
        if not kilit.get("kurtarma_var"):
            raise IslemHatasi("Bu klasörde kurtarma ifadesi kurulmamış.", "kurtarma_yok")
        mod = self._kurtar(Path(kilit["klasor"]), ifade, yeni_parola, yeni_parola_tekrar)
        parola = yeni_parola if mod == "parola" else None
        if parola:
            self.hatirla(kilit["klasor"], parola)
        else:
            self.unut(kilit["klasor"])
        self.y.uygulama = self.y.uygulama_olustur(kilit["klasor"], parola)
        self.y.kilit = None
        return {"ok": True, "mod": mod}

    # ------------------------------------------------------------------ şifrelemeyi aç / kapat
    def api_guvenlik_donustur_baslat(self, tur: str, onay: str = "", mevcut_parola: str | None = None) -> dict:
        if tur not in ("ac", "kapat"):
            raise IslemHatasi("Geçersiz işlem.")
        if self.is_ is not None and self.is_.durum == "calisiyor":
            raise IslemHatasi("Bir dönüşüm zaten sürüyor.", "mesgul")
        klasor = self._klasor()
        d = sif.durum(klasor)
        parola = None
        if tur == "ac":
            if d["sifreli"]:
                raise IslemHatasi("Bu klasör zaten şifreli.", "zaten_sifreli")
            if sif.varsayilan_saglayici() is None:
                raise IslemHatasi("Bu sistemde anahtar koruma sağlayıcısı (Windows DPAPI) yok; şifreleme açılamaz.",
                                  "saglayici_yok")
        else:
            z = self._sifreli_olmali()
            if onay != KALDIR_ONAY:
                raise IslemHatasi(f"Şifrelemeyi kapatmak için {KALDIR_ONAY} yazmalısınız.", "onay_gerekli")
            self._yeniden_dogrula(z, mevcut_parola)
            parola = self.kayitli_parola(klasor)
        self.y.mesgul = "donusum"
        self.y.kapat()           # veritabanı kapanır, hub.lock bırakılır; dönüşüm kendi kilidini alır
        is_ = DonusumIsi(tur)
        self.is_ = is_
        threading.Thread(target=self._donustur, args=(is_, klasor, parola), daemon=True, name="donusum").start()
        return is_.to_dict()

    def _donustur(self, is_: DonusumIsi, klasor: Path, parola: str | None) -> None:
        sonuc: dict | None = None
        hata: str | None = None
        try:
            if is_.tur == "ac":
                sonuc = donusum.sifrele(klasor, ilerleme=is_.ilerleme)
            else:
                sonuc = donusum.sifreyi_kaldir(klasor, parola=parola, ilerleme=is_.ilerleme)
                self.unut(klasor)
        except SifrelemeHatasi as e:
            hata = str(e)
        except Exception as e:
            gunluk.log().error("dönüşüm hatası: %s", type(e).__name__)
            hata = f"Beklenmeyen hata: {type(e).__name__}. Veri klasörü bozulmamış olmalı; Güvenlik sayfasından durumu kontrol edin."
        with self.y._api_kilit:
            try:
                self.y.uygulama = self.y.uygulama_olustur(klasor, None)
            except Exception as e:
                gunluk.log().error("dönüşüm sonrası açılamadı: %s", type(e).__name__)
                self.y.baslangic_hatasi = f"Dönüşüm sonrası veri klasörü açılamadı ({type(e).__name__}). " \
                                          "Uygulamayı yeniden başlatın."
                hata = hata or self.y.baslangic_hatasi
            self.y.mesgul = None
            with is_._kilit:
                if hata:
                    is_.durum, is_.hata = "hata", hata
                else:
                    is_.durum = "bitti"
                    is_.mesaj = "Tamamlandı."
                    is_.sonuc = {k: v for k, v in (sonuc or {}).items() if isinstance(v, (int, str, bool))}
        gunluk.log().info("dönüşüm %s: %s", is_.tur, "hata" if hata else "bitti")

    def api_guvenlik_donusum_durum(self) -> dict:
        return self.is_.to_dict() if self.is_ else {"durum": "yok"}


__all__ = ["Guvenlik", "DenemeSiniri", "GUVENLIK_API", "KILITLI_IZINLI", "MESGUL_IZINLI", "DEGERLENDIRICILER"]
