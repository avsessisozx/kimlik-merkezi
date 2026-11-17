# YOL HARİTASI — "Jarvis'in hafızası" (kullanıcı hedefi; onay beklenmez, sırayla yapılır)

Hedef: dijital kimliğe ait her şey tek yerde toplanır; kullanıcı bir yapay zekâya/programa bir şey söylediğinde o onu zaten tanır. Yerel, kullanıcının, yapay zekâdan bağımsız.

Sıra (bir sonraki işçi boşalınca):
1. [çalışıyor] Sohbet içe aktarıcıları (ChatGPT, Claude, DeepSeek, Gemini) — İ3
2. [çalışıyor] Persona Haritası veri katmanı (İ2) + ekran (İ5)
3. Persona çıkarım kuyruğu (İ2): MCP `persona_oner` (yalnız ayrı dosyaya öneri), Windows inceleme ekranı (İ5), onay → beyan_edilen. Çıkarımı yapan: kullanıcının kendi yapay zekâsı (MCP üzerinden); API anahtarı gerekmez.
4. Ses ve görüntü girişi (İ3 + İ2): bilgisayardaki ses notları/kayıtlar ve görsel/ekran görüntüleri klasörü → yerel yazıya dökme (faster-whisper, CPU/4 GB GPU, küçük model) ve OCR (yerel, ör. RapidOCR/Tesseract; lisans kontrol) → `notlar`/`dosyalar` olayları. Model indirme ilk kullanımda, kullanıcıya sorulur; internetsiz çalışma bozulmaz.
5. Sürekli güncel kalma (İ5 + İ3): izlenen klasörler (İndirilenler, Belgeler, ses/ekran görüntüsü klasörleri) arka planda yeni dosyayı içe alır; tarayıcı geçmişi periyodik alınır; Windows tepsi uygulaması açıkken çalışır.
6. Gerçek bağlantı doğrulaması: Claude Desktop/Claude Code'da "beni tanıyor mu" senaryosu (kullanıcı cihazında; adımlar KULLANICI_ADIMLARI.md).
7. [bitti] v0.1.1, v0.1.2, v0.1.3 ön sürümleri (v0.1.3: rol, kopya temizliği, token tasarrufu, hassas konu izni, önem, yönetilen CLAUDE.md bloğu; 16 Kasım 2026).
8. [çalışıyor] Android toplayıcı (v0.2.0; Karar A: doğrudan HTTPS, bkz. KARAR-SENKRON.md): giden kutusu, paylaş-hedefi, hızlı not, foto metadatası, aktarım (Karar A araştırması İ6; CI'de emülatör).
9. Sonra: anlamsal arama (Aşama 9), isteğe bağlı sesli/görüntülü arayüz (kapsam dışı, ayrı karar).
