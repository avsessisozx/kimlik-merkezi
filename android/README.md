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
Karşılaştırılan: (1) SAF `ACTION_OPEN_DOCUMENT_TREE`, (2) `MANAGE_EXTERNAL_STORAGE`. Her ikisi API 31 emülatöründe CI'de denenir (`IndirilenSafTest`: gerçek seçici UiAutomator ile sürülür, `KMSaf` alt klasörü seçilir; `IndirilenTumDosyalarDeneyi`: `appops` ile izin verilip `File` ile listelenir, ayrı adımda koşulur çünkü izin değişimi süreci öldürebilir). 
**Sonuç: SAF seçildi** (daha dar izin; `MANAGE_EXTERNAL_STORAGE` manifeste EKLENMEDİ).
- SAF (CI koşusu 43837595684, API 31 x86_64): gerçek klasör seçici UiAutomator ile sürüldü; `Download/KMSaf` alt klasörü seçildi ("Use this folder" + "Allow"), kalıcı okuma izni alındı, alt klasör (`KMSaf/alt`) dahil dosyalar ad/boyut/mime ile listelendi, ikinci tarama 0 kayıt üretti. YEŞİL.
- `MANAGE_EXTERNAL_STORAGE` deneyi aynı koşuda KIRMIZI: test hata iletisi vermeden bitti (büyük olasılıkla izin değişimi süreci öldürdü; ayrıca izin manifestte bildirilmediği için `appops` ile verilmesi anlamlı bir sonuç vermeyebilir). Bu yol daha geniş bir izin gerektirdiğinden ve SAF çalıştığından daha fazla araştırılmadı.
- Gözlem sınırı: Android 11+ İndirilenler KÖKÜNÜ seçtirmeyebilir (belgelenmiş platform kısıtı); bu emülatör testinde kök seçimi denenmedi, alt klasör seçildi. Arayüz bunu kullanıcıya söyler.

## PC'ye gönderim (İŞ A3)
Sözleşme: `docs/AKTARIM.md` §2, §3, §5, §7, §8. Kod `.../aktarim/` altında.
- **TLS sabitleme:** ağ kütüphanesi yok; `HttpsURLConnection` + özel `SSLSocketFactory`/`X509TrustManager`. Yalnız eşleştirmede sabitlenen sertifikanın SHA-256 (DER) parmak izi kabul edilir; sistem deposuna ve ana makine adına güvenilmez. Parmak izi el sıkışmada doğrulanır, yani uyuşmayan sunucuya TEK BAYT uygulama verisi gitmez. `HostnameVerifier` yalnız o bağlantı nesnesi içindir. Yalnız sayısal RFC1918/link-local IPv4 adreslerine bağlanılır (IPv6 ve ana makine adı yok); `Proxy.NO_PROXY`; düz HTTP hem `usesCleartextTraffic=false` + `network_security_config` hem de kodda (şema sabit `https`) kapalı.
- **Sıra:** HEAD -> en çok 1 MiB'lik PUT parçaları (`Content-Range`, `X-Sha256` = ÇÖZÜLMÜŞ içeriğin özeti) -> `var` görülünce dosya silinir. 409 `X-Alinan`'a hizalanır; 401 durur ve silmez; 422 dosyayı "reddedildi" işaretler (silinmez, tekrar denenmez, raporda sayılır); 429/507 beklenir; bağlantı kopmaları 1-2-4 sn üstel beklemeyle sınırlı denenir ve HEAD ile kaldığı yerden sürer. Çözülmüş içerik diske düz yazılmaz (bellekte akış; özet için ilk geçiş, gönderim için ikinci).
- **Adres:** kayıtlı adresler -> UDP 47822 yayını (`KM1?<ilk 16 hex>` / `KM1!<port>`; yayın için `CHANGE_WIFI_MULTICAST_STATE` gerekmez, `INTERNET` yeter) -> Ayarlar > PC ile eşleştir ekranında elle adres.
- **Tetikleyiciler:** "PC'ye gönder" düğmesi, uygulama açılışı (eşleşmişse), WorkManager periyodik iş (15 dk, sınırsız ağ, pil düşük değil; Ayarlar'dan kapatılır, varsayılan açık). Arka plan gönderimi bildirim göstermez (istenmemiş özellik kaldırıldı); ana ekranda "Son başarılı gönderim" yeter. Iş durdurulursa (`isStopped`) dosyalar/parçalar arasında temiz çıkılır.
- **QR:** CameraX (Apache-2.0) önizleme + `com.google.zxing:core` 3.5.3 (Apache-2.0), tamamen çevrimdışı; Google Play Hizmetleri'ne bağlı kod tarayıcı YOK. Kamera izni yalnız eşleştirme ekranında "QR kodu tara"ya basınca istenir. Kamera yolu emülatörde sınanmaz; yalnız çözücü (`QrCozucu`) birim testlidir (zxing ile üretilen QR görüntüsü). Kod yapıştırma yolu uçtan uca emülatörde sınanır.
- **Elle aktarım:** Ayarlar > Dosyaya aktar: "Bu dosya şifresizdir" uyarısı, SAF `CreateDocument` ile tek `.zip` (her dosya çözülmüş `<dosya_id>.jsonl`), sonra "PC'ye alındı, telefondan sil" onayı; onay yoksa silinmez. Seçici ekranı emülatör testinde sürülmez; zip içeriği testlidir.
- **Pil yardımı:** "Arka planda gönderim çalışmıyorsa" sayfası yalnız sistemin pil kısıtlama ve uygulama ayrıntıları ekranlarına götürür; üretici ayar adı tahmin edilmez.
- **Testler:** `src/ortakTest/` hem JVM hem emülatör testlerine eklenir: sahte PC mantığı (`PcMantik`), gerçek TLS test sunucusu (`SahteSunucu`) ve `test_sunucu_YALNIZ_TEST.p12` (YALNIZ TEST; parola `test1234`; kendinden imzalı, hiçbir üretim işlevi yok). Gerçek PC alıcısına karşı emülatör testi ayrı iştir.

## A4 kararları (gözden geçirme düzeltmeleri)
- **Kayıt boyutu:** `metin` en çok 64 KiB (UTF-8, kod noktası sınırında kesilir, sonuna "… [kısaltıldı]"), `yuk` içindeki her metin alanı (`url`, `baslik`, `kaynak_uygulama`...) en çok 2 KiB, serileştirilmiş kayıt satırı en çok 1 MiB (aşarsa alanlar daha da kısaltılır; yine aşarsa kayıt `kayit_cok_buyuk` koduyla reddedilir). PC satır sınırı 4 MiB. Paylaşım ve hızlı not kısaltılınca kısa bildirim gösterir. Uzun bir `url` kısaltılırsa tam adres kaybolur (bilinen ödün).
- **Eşik kapatması:** kayıt diske yazıldıktan sonra kapatma hata verirse çağırana hata dönmez; kod günlüğe yazılır, sonraki eklemede yeniden denenir.
- **Toplu ekleme:** `GidenKutusu.kayitlariEkle` grup başına tek fsync; medya taraması 200'lük gruplarla yazar, imleç yalnız grup yazıldıktan sonra ilerler.
- **Gönderim kodları:** `pc_tamamlayamadi` (PC tam boyutlu ama tamamlanmamış dosya bildirdi: tur biter, dosya silinmez, ret işaretlenmez), `bekle` (429/507/413 ya da bu yanıtlardan sonra bağlantı hatası), `sertifika` (kayıtlı adreste parmak izi uyuşmadı, UDP ve diğer adresler denendi, doğru PC bulunamadı), `durduruldu`. `422` + `X-Durum: yok` bir kez baştan denenir; diğer 422'ler kalıcı ret. Eşleştirme kalkınca ret listesi ve periyodik iş temizlenir.
- **Hata raporu:** "Doğrulama durumu" satırı: giden kutusu dosya/bozuk sayısı, son başarılı gönderim, eşleşme.
- **CI:** SAF seçildiği için MANAGE_EXTERNAL_STORAGE deneyi kaldırıldı.

## Sürüm ve imzalama
- Sürüm: `app/build.gradle.kts` içinde `versionName = "0.2.0"`, `versionCode = 200`. Sürüm artırma kuralı: `versionName` MAJOR.MINOR.PATCH; `versionCode = MAJOR*10000 + MINOR*100 + PATCH` (0.2.0 → 200; 0.2.1 → 201; 0.3.0 → 300; 1.0.0 → 10000). Her yayında ikisi birlikte artar, `versionCode` asla düşmez.
- `signingConfigs.release` YALNIZ ortam değişkenlerinden okunur: `KM_KEYSTORE_DOSYA` (yol), `KM_KEYSTORE_PAROLA`, `KM_ANAHTAR_AD`, `KM_ANAHTAR_PAROLA`. Hiçbiri depoda yoktur. Eksikse `assembleRelease` İMZASIZ `app-release-unsigned.apk` üretir; debug anahtarına SESSİZCE DÜŞÜLMEZ (yerelde ikisi de denendi).
- `isMinifyEnabled = false` bilinçli: R8 kuralları (Compose, kotlinx-serialization, WorkManager) doğrulanmadan küçültme açılmaz.
- CI: `surum-apk` işi YALNIZ `workflow_dispatch` ile ve `imzali: true` girdisiyle çalışır. Secrets: `KM_KEYSTORE_B64` (base64 keystore), `KM_KEYSTORE_PAROLA`, `KM_ANAHTAR_AD`, `KM_ANAHTAR_PAROLA`; biri yoksa iş anlaşılır iletiyle KIRMIZI olur. `assembleRelease` + `lintVitalRelease`, `apksigner verify --print-certs` (sertifika SHA-256 günlüğe yazılır), artifact `KimlikMerkezi-v<sürüm>.apk`. `surum-dogrula` işi bu APK'yı API 31 emülatörüne kurar, BAŞLATIR ve ana ekranın açıldığını denetler (`android/ci/surum_dogrula.sh`).

## Sınanmayanlar
- Kamera ile QR okuma emülatörde sınanmadı (yalnız çözücü birim testli; kod yapıştırma uçtan uca sınandı).
- Gerçek ağda UDP yayınla PC bulma emülatörde sınanmadı (iletiler ve seçim mantığı birim testli).
- Gerçek PC alıcısına karşı emülatör testi ayrı iştir.
