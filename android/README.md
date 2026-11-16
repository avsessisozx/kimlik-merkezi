# Kimlik Merkezi Toplayıcı (Android)

Yalnız toplayıcı: notları ve paylaşılan metin/bağlantıları şifreli giden kutusunda biriktirir (aktarım sonraki iş). Kotlin + Jetpack Compose, minSdk 30, targetSdk/compileSdk 35, paket `app.kimlikmerkezi.toplayici`. Giden kutusu biçimi: `docs/AKTARIM.md` §1; disk biçimi: `BICIM.md`.

## Yapı
- `app/src/main/kotlin/.../giden`: giden kutusu, çerçeve, şifreleme (Keystore)
- `.../gunluk`: içerik yazmayan günlük, hata raporu
- `.../paylasim`: paylaş hedefi (`ACTION_SEND text/plain`), URL ayrıştırma
- `.../ui`: Compose ekranları
- `app/src/test`: JVM birim testleri; `giden_ornek.jsonl` PC içe aktarıcısı için altın örnek
- `app/src/androidTest`: emülatör testleri (Keystore, arayüz)

## Komutlar (bu klasörden; `local.properties` içinde `sdk.dir`, depoya girmez)
```
./gradlew testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest
./gradlew connectedDebugAndroidTest   # emülatör/cihaz gerekir; CI'de API 31
```
