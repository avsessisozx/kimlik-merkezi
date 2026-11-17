# Android toplayıcı temeli: karar belgesi (v0.3.0)

Soru: telefondaki veri toplama işini kendi kodumuzla mı sürdürelim, AWARE çerçevesine mi geçelim, yoksa ikisini mi karıştıralım?
Aşağıdaki bilgiler araştırmadan gelir (AWARE'in resmî sayfaları ve deposu). **AWARE bu telefonda denenmedi.** Karar senin.

## Senin ihtiyacın
- Veri yalnız senin PC'ne gitmeli (yerel ağ, şifreli, internet sunucusu yok).
- Hassas veri (ekran metni) yapay zekâ erişiminden ayrı kalmalı.
- Her toplayıcı ayrı açılıp kapanmalı, hepsi kapalı başlamalı.
- Realme 7 Pro (Android 12) üzerinde çalışmalı; bakımı sana yük olmamalı.

## Seçenekler

| | 1. Kendi kodumuz (şu anki) | 2. AWARE'e geçiş | 3. Karışık |
|---|---|---|---|
| Veri nereye gider | Yalnız eşleşmiş PC'ye, şifreli dosya | AWARE kendi MySQL sunucusuna/panosuna yükler; PC alıcımızla uyuşmaz | AWARE yerel kaydeder, bizim bir aracı kodla PC'ye aktarılır |
| Sensör çeşitliliği | Az ama istediklerimiz (medya, konum, indirilen, kullanım, adım, ekran metni) | Çok (ekran metni, dokunma, sensörler vb.) | Çok |
| Bizim biçimimize uyum | Tam | Çevirici gerekir | Çevirici gerekir |
| Ekran metnini ayrı hassas kategoriye koyma | Yapıldı (`mesaj`) | Kendimiz sarmak gerekir | Kendimiz sarmak gerekir |
| Bakım | Sende/bizde | AWARE'in ekibine bağlı; eski sürüm ("Legacy") arşivde | İki parça birden |
| Risk | Her sensörü kendimiz yazarız | Sunucu varsayımı bizim "yerel, sunucusuz" fikrimize ters | En karmaşık yol |

## Önerim (kısa)
Kendi kodumuzla devam. Gerekçe: AWARE'in veri yolu bizim PC alıcısıyla uyuşmuyor; aracı yazmak, kendi toplayıcıyı yazmaktan az iş değil. İhtiyaç duyulan yeni sensör olursa tek tek ekleriz (bu sürümde adım ve ekran metni böyle eklendi).
AWARE'i ilerde yalnız "hangi sensörler var" fikri için örnek olarak okuyabiliriz.

## Doğrulanmayanlar
- AWARE Legacy'nin Android 12'de çalıştığı bu telefonda denenmedi.
- Karşılaştırma tablosu belgelerden çıkarıldı, ölçüm değildir.

**Seçim:** hangisini istediğini söyle; söylemezsen 1 ile devam ederim.
