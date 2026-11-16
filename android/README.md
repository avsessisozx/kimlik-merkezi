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

## İsteğe bağlı toplayıcılar (hepsi varsayılan KAPALI)
Ayarlar ekranından tek tek açılır; izin yalnız açılırken istenir. Reddedilirse anahtar kapalı kalır. Arka plan zamanlayıcısı yok: tarama "Şimdi tara" ile ve (açıksa) uygulama açılışında çalışır. Dosya içeriği hiçbir toplayıcıda okunmaz.
- Fotoğraf/video (`medya.foto`, `medya.video`): MediaStore'dan yalnız ad, boyut, mime, ölçü, süre, çekim zamanı. API 33+ `READ_MEDIA_IMAGES/VIDEO`, API 30-32 `READ_EXTERNAL_STORAGE`; API 34+ "yalnız seçtiklerim" erişiminde yalnız seçilenler görünür (ekranda söylenir). İmleç türe göre (`date_added`, `_id`).
- Konum (`medya.konum`): AYRI ayar ve izin (`ACCESS_MEDIA_LOCATION`); AYRI imleç. `setRequireOriginal` + ExifInterface fotoğrafın EXIF başlığını okur (yalnız konum için tek açılış; başka içerik okunmaz). `medya.foto` kaydında GPS alanı asla olmaz.
- İndirilenler (`indirilen.dosya`): kullanıcının seçtiği klasör (SAF), kalıcı okuma izni; alt klasörler gezilir. Görülen dosyalar `filesDir/indirilen_gorulen.txt` içinde özetle tutulur.
- Uygulama kullanımı (`uygulama.kullanim`): `UsageStatsManager.queryAndAggregateUsageStats` ile her TAMAMLANMIŞ yerel gün için ayrı aralık (gün sınırı yerel gece yarısı); bugün yazılmaz; ilk açılışta en çok son 7 gün. Sistem "kullanım erişimi" ekranına yönlendirilir.

**Yeniden kurulum notu:** kayıt `id`'leri rastgele UUID4 olduğu için yeniden kurulumdan sonra imleçler sıfırlanır ve aynı medya yeniden kayıt üretir. PC tarafının tekilleştirebilmesi için `medya.foto`, `medya.video` ve `medya.konum` kayıtlarının `yuk.medya_id` alanı kararlıdır: SHA-256(`tür|MediaStore _id|date_added|boyut`) ilk 32 hex. (`indirilen.dosya` ve `uygulama.kullanim` için bu işte kararlı kimlik yok: PC `ad+boyut` / `paket+gun` ile tekilleştirebilir.)

### İndirilenler için yol kararı
Karşılaştırılan: (1) SAF `ACTION_OPEN_DOCUMENT_TREE`, (2) `MANAGE_EXTERNAL_STORAGE`. Her ikisi API 31 emülatöründe CI'de denenir (`IndirilenSafTest`: gerçek seçici UiAutomator ile sürülür, `KMSaf` alt klasörü seçilir; `IndirilenTumDosyalarDeneyi`: `appops` ile izin verilip `File` ile listelenir, ayrı adımda koşulur çünkü izin değişimi süreci öldürebilir). SONUÇ: aşağıya yazılır.
