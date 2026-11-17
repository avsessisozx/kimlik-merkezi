# İmza anahtarı (bilerek depoda)

`kimlikmerkezi-imza.p12`, Android APK'sını imzalar. Bu anahtar **bilerek herkese açık depodadır**: depo sahibinin kararıdır (17 Kasım 2026), uygulama yalnız kendi kullanımı içindir. Parolası `.github/workflows/android.yml` içinde yazılıdır.

Sonuç: bu depodan gelmeyen, aynı anahtarla imzalı bir APK'yı kimse sizden ayırt edemez. Uygulamayı **yalnız bu deponun Releases sayfasından** kurun; başka kaynaktan gelen "güncellemeleri" kurmayın.

Sertifika SHA-256: 3D:5C:62:A6:0E:99:F3:7E:CF:B7:AC:A4:75:2E:05:1D:87:FA:CF:FF:32:98:31:41:7A:48:6D:9E:8E:7A:D8:36
