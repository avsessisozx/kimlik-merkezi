"""Kimlik Merkezi Windows uygulaması.

Katmanlar (kabuk kararı değişirse yalnız üstteki katman değişir):
  - İş mantığı (arayüzden bağımsız, test edilir): yollar, ayarlar, veri_klasoru, claude_ayar,
    saglik, hata_raporu, baslangic, cekirdek (Uygulama).
  - Arayüz: web (yerel HTTP, yalnız 127.0.0.1) + statik/index.html, tepsi, uygulama (giriş noktası).
"""
__version__ = "0.1.0"
APP_AD = "Kimlik Merkezi"
