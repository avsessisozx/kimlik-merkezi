# Üçüncü taraf bileşenler

Kimlik Merkezi kendi kodunu MIT lisansıyla sunar (bkz. `LICENSE`). Aşağıdaki bileşenler
kendi lisanslarıyla gelir. Lisans türleri, kurulu sürümlerin paket üst verisinden alınmıştır;
yayın öncesi bir kez daha doğrulanmalıdır.

| Bileşen | Kullanım | Lisans |
|---|---|---|
| Apache ECharts 6.1.0 | Grafikler (yerelde paketli, CDN yok) | Apache-2.0 (`windows/src/kimlikwin/statik/ECHARTS-LICENSE.txt`, `ECHARTS-NOTICE.txt`) |
| mcp (Python SDK) 2.3.0 | MCP sunucusu | MIT |
| cryptography (≥42) | Veri şifreleme (AES-256-GCM); tekerlek OpenSSL (Apache-2.0) içerir | Apache-2.0 OR BSD-3-Clause |
| ijson | Akışlı JSON ayrıştırma | BSD-3-Clause (ve ISC) |
| pypdf | PDF metni | BSD-3-Clause |
| python-docx | DOCX metni | MIT |
| Pillow | Görsel üst verisi, tepsi simgesi | MIT-CMU (HPND benzeri) |
| pystray 0.19.5 (isteğe bağlı) | Windows tepsi simgesi | **LGPL-3.0** |
| PyInstaller | Windows paketi oluşturma | GPL-2.0 + paketleme istisnası (üretilen programa bulaşmaz) |
| Inno Setup | Kurulum programı oluşturma | Inno Setup Lisansı (serbest) |

## pystray hakkında not (LGPL-3.0)
pystray ayrı bir kütüphane olarak kullanılır, kodu değiştirilmemiştir ve yalnızca tepsi
simgesi içindir. Paketlenmiş sürümde kullanıcı bu kütüphaneyi kendi sürümüyle değiştirebilmelidir;
bu gereklilik yayın öncesi paket yapısında (klasör tipi paket) ayrıca doğrulanacaktır.
