# EVE GİDİNCE: KULLANICI ADIMLARI (sade, numaralı)

Bu rehber, gerçek verinle ilk denemeyi yapman içindir. Hedef: ürünün en büyük açığını (içe aktarıcılar gerçek dosyalarla hiç denenmedi) kapatmak ve "Claude beni tanıyor mu?" testini gerçek veriyle yapmak.

**Dürüst uyarı:** Üçüncü taraf menü adları (Google, Reddit, ChatGPT, Claude, DeepSeek, Gemini) bu ortamdan doğrulanamadı; aşağıda menü adı UYDURMUYORUM. Ekranda farklı gördüğünde ya da bir şey bulamadığında, ekrandaki yazıları bana yaz. Sorun çıkarsa her zaman önce "Hata raporunu kopyala" düğmesi.

## A. Kurulum (Windows)
1. GitHub'da depoya gir, sağda **Releases** bölümünden **v0.1.1** (ön sürüm) sürümünü aç. (Depo private olduğu sürece yalnız sen görürsün; giriş yapmış olman gerekir.)
2. `KimlikMerkezi-Kurulum-...exe` dosyasını indir.
3. (İstersen) bütünlüğü kontrol et: indirme klasöründe PowerShell aç, `Get-FileHash .\KimlikMerkezi-Kurulum-....exe` yaz; çıkan SHA256 değeri, sürümdeki `SHA256SUMS.txt` ile aynı olmalı.
4. Dosyaya çift tıkla. "Windows bilgisayarınızı korudu" çıkarsa (imzasız olduğu için):
   - **"Ek bilgi"** (More info) bağlantısına tıkla, sonra **"Yine de çalıştır"** (Run anyway).
   - Düğmeyi göremezsen dur ve bana yaz (Windows 11 Akıllı Uygulama Denetimi açıksa çıkmayabilir).
5. Kurulum yönetici izni istemez. Bitince uygulamayı aç; **ilk açılış sihirbazı** veri klasörünü sorar.
6. **Şifreleme varsayılan olarak AÇIK** gelir (Windows hesabına bağlı, parolasız). Parola eklemek istersen uygulamadaki **Güvenlik** sayfasından eklenir. Parola eklerken önce bir **kurtarma ifadesi** kurman istenir. Hem parolayı hem kurtarma ifadesini unutursan verin KURTARILAMAZ. İfadeyi bir kâğıda yaz ve güvenli bir yerde sakla. (Parola eklemek zorunlu değil.)
   - **ÖNEMLİ:** Parola eklersen **Claude Desktop bu klasöre bağlanamaz** (bilinçli güvenlik kararı: parola Claude'un düz metin ayar dosyasına yazılamaz). Bu yüzden **önce Bölüm D'deki Claude testini yap, parolayı en son ekle.** Parolayı kaldırırsan Claude bağlantısı yeniden çalışır.
7. Hata çıkarsa uygulamada **"Hata raporunu kopyala"** düğmesine bas, metni bana yapıştır.

## B. Veri arşivlerini iste (hazır olması saatler-günler sürer, önce bunu başlat)
Menü adlarını ben bilmiyorum; aşağıdakiler yön gösterir. Bulamazsan ekran yazısını bana ilet.
1. **Google Takeout** (takeout.google.com): önce tüm seçimleri kaldır; YouTube ve YouTube Music, Chrome, "Etkinliklerim" (My Activity), konum geçmişi (varsa), Gmail (isteğe bağlı) seç. Geçmiş verilerinde **JSON** biçimini seç (HTML değil). Hazır olunca e-postayla gelen bağlantıdan zip'i indir. Gemini etkinliği için "Etkinliklerim" kapsamında bak.
2. **Reddit:** tarayıcıda `reddit.com/settings/data-request` adresine git, hesap geçmişi için istek gönder. Zip gelince indir.
3. **ChatGPT, Claude, DeepSeek:** her birinin ayarlar bölümünde veri dışa aktarma / indirme seçeneği aranır; adı değişebilir. Bulduğunda e-postayla gelen bağlantıdan zip'i indir. Bulamazsan bana o uygulamanın ayarlar ekranındaki başlıkları yaz.
4. **Instagram/Facebook (Meta), GitHub, Spotify:** her birinin "verilerimi indir" bölümünden iste; JSON biçimi tercih et. Bekleme süresi uzun olabilir.
5. Hepsi aynı anda gelmek zorunda değil. Gelen zip'i **açma**, olduğu gibi kullan.

## C. İçe aktarma (her zip için)
0. Bir dosyanın tanınıp tanınmadığını önce görmek istersen **İçe aktar** ekranındaki **"Dosyayı denetle (içerik göstermez)"** düğmesini kullan: dosyayı seç, çıkan raporu kopyala. Rapor yalnız alan adı, tür ve sayı içerir; içeriğini göstermez. Dosya tanınmazsa bu raporu bana yapıştır.
1. Uygulamada **İçe aktar** ekranını aç, zip'i seç.
2. Ekranda **biçim raporu** görünür (dosya adları ve alan adları, kişisel içerik yok). Başarılıysa kaç kayıt eklendiği yazar.
3. **Bir şey ters giderse** (dosya tanınmadı, hata, 0 kayıt, ya da "bozuk"): biçim raporunu ve hata metnini kopyalayıp bana yapıştır. Bu, içe aktarıcıyı gerçeğe göre düzeltmem için en değerli veri. İçerik değil yalnız yapı içerir.
4. Gerçek dosyada ilk kez deneme olduğu için ilk içe aktarmalarda hata çıkması NORMAL. Bu testin amacı bu.
5. Kaynaklar sayfasında ve Harita'da kayıtların göründüğünü kontrol et.

## D. Claude ile "beni tanıyor mu?" testi (MCP)
1. **Erişim** ekranından **"Claude'a ekle"** düğmesine bas. Sonuç kutusu başarılı ya da başarısız olduğunu açıkça söyler; başarısızsa aranan dosya yollarını gösterir.
2. **Dikkat:** "Claude'a ekle", **hassas olmayan 10 kategoriyi süresiz AÇIK** verir. E-posta, mesaj, konum ve sohbet kapalı kalır; onları açmak için ayrı onay istenir. Daha dar bir yetki istersen "Yeni anahtar" ile hiçbir izin vermeden başlayıp Erişim ekranından tek tek açabilirsin.
3. Claude Desktop'u tamamen kapatıp yeniden aç.
4. Yeni sohbette önce: "kategorilerimi listele". Sonuç gelmezse bana yaz.
5. Sonra kendi sorularını sor. Önerilen kısa test (hafızasız ve hafızalı karşılaştır):
   - Önce **hafızasız** bir sohbette (MCP kapalıyken ya da başka bir yapay zekâda) 5–6 şey sor: "Ben hangi şehirde yaşıyorum?", "Kod yazarken hangi dili ve editörü kullanıyorum?", "Son zamanlarda hangi konulara ilgi duyuyorum?", "Hangi müzikleri dinlerim?", "Günün hangi saatlerinde çalışırım?"
   - Aynı soruları **MCP açıkken** sor. Cevapları yan yana koy.
   - Yanlış, uydurma ya da hiç bilmediği şeyler olursa bana yaz: hangi soru, ne dedi, gerçek ne. Bu, kimlik kartı ve aramanın gerçek veriyle ne kadar iyi olduğunu gösteren en önemli kanıt.
6. Ayrıca bir hassas kategori kapalıyken (örn. e-posta) o kategoriye ait bir şey sor: **cevap vermemeli**, "izin yok" demeli. Verirse ciddi bir hata, hemen bana yaz.
7. **Persona önerileri:** Claude sana `persona_oner` ile çıkarım önerebilir; bunlar **Persona > Öneriler** sekmesinde bekler. Kendin onayla, düzelt ya da reddet. Onaylamadıkça hiçbir şey kalıcı olmaz.

## E. Telefon ve diğer cihazlar
Android toplayıcı henüz yok (sonraki sürüm). Şimdilik telefondaki verileri yukarıdaki arşivlerle (Google, Meta, Spotify...) getiriyoruz.

## F. Bana ne getireceksin (özet)
1. Her içe aktarma için: başarılı mı, kaç kayıt, hata/biçim raporu.
2. Kurulum ya da açılışta yaşadığın her takılma (ekran yazısıyla).
3. "Beni tanıyor mu?" testinin yan yana cevapları.
4. Hassas kategori kapalıyken sızıntı olup olmadığı.

## G. Bekleyen sorular
1. DeepSeek masaüstü uygulamasının tam adı nedir?
2. Redmi Note 10 Pro ve Galaxy Tab A9 Plus Android sürümü (sonraki sürüm için).
3. İzin varsayılanı: "Claude'a ekle" 10 hassas olmayan kategoriyi açık versin mi (şu an böyle) yoksa hiçbirini açmasın mı?
4. Varsayılan tema koyu kalsın mı?

---

# v0.1.3: YERELDE DENEYECEKLERİN (16 Kasım 2026)

CI bunları test edemez, çünkü gerçek verin yalnız senin bilgisayarında. Düğme adlarını uygulamadaki metinden aldım; ekranda farklı görürsen ekrandaki yazıyı bana ilet. Sorun olursa önce "Hata raporunu kopyala".

## H. Güncelleme
1. Releases sayfasından **v0.1.3** kurulum dosyasını indir, üstüne kur (verin korunur).
2. Önce **Kimlik Merkezi uygulamasını aç** (veritabanı yeni biçime geçer; 22.000 kayıtta birkaç saniye).
3. Sonra **Claude Desktop'u tamamen kapat, yeniden aç.** Kapatmazsan Claude "bu bağlantı eski sürümle çalışıyor" der.

## I. Kopya temizleme raporu (en önemli deneme)
1. Uygulamada **Kaynaklar** sayfasını aç, **"Sohbet kopyalarını denetle"** kartını bul.
2. **Denetle**'ye bas. Hiçbir şey değişmez, yalnız sayı raporu çıkar. **"Raporu kopyala"** ile raporu bana yapıştır (yalnız sayı içerir, içerik yok).
3. "Yeniden üret" kopyaları (aynı soruya birden çok cevap) ancak ChatGPT dışa aktarma dosyasını da gösterirsen bulunur: aynı kartta dosyayı seç, yeniden **Denetle**.
4. Rapordaki sayılar mantıklıysa **"Kopyaları gizle"** → onayla. Kayıtlar silinmez, gizlenir.
5. Raporda **"atlanan konuşma"** sıfırdan büyükse bana yaz: o konuşmalarda paket ile veritabanı uyuşmamış, güvenlik için dokunulmamış demektir.
6. Bana yaz: toplam kayıt sayısı önce/sonra, raporun kendisi, Claude'da artık aynı mesajın iki kez gelip gelmediği.

## J. Rol süzgeci
1. Claude'da sor: "Sohbet kayıtlarımda rol dağılımını say." (Beklenen: kullanıcı ve asistan ayrı sayılır.)
2. "Yalnız benim yazdığım sohbet mesajlarından 5 örnek getir." (Gelenlerin hiçbiri yapay zekâ cevabı olmamalı.)
3. Yanlış rol görürsen: hangi platform (ChatGPT/Claude/dosya), bana yaz.

## K. Token boyutları
1. Claude'da aynı aramayı yap (ör. daha önce 5 sonuçta ~10 bin token tutan arama). Claude Desktop'ta araç çağrısının cevabını açıp uzunluğuna bak: kısa alıntılar gelmeli, tam metin yalnız Claude `kayit_getir` çağırınca.
2. "Aylara göre kayıt sayımı" iste: 96 satır yerine sıkışık liste gelmeli.
3. Bana yaz: eskisine göre gözle fark var mı; Claude gereksiz yere çok `kayit_getir` çağırıyor mu.

## L. Hassas konular
1. Sohbet izni açıkken Claude'a sağlıkla ilgili bir şey sor (ör. "doktorla ilgili ne konuştum?"). **Beklenen: bulamaması.**
2. Uygulamada **Erişim** sayfasında Claude anahtarının **"Hassas konular"** bölümünden yalnız "Sağlık"ı aç (ayrı onay sorar). Aynı soruyu yeniden sor: şimdi bulmalı. Sonra kapat.
3. **Önemli:** izin KAPALIYKEN hassas bir kayıt Claude'a geldiyse (ör. hukuk, para, sağlık), kayıttaki hangi sözcüğün kaçtığını bana yaz. Sözcük listesi elle yazıldı, mutlaka boşlukları vardır; bu denemenin amacı onları bulmak.
4. Tersi de olur: ilgisiz bir kayıt "hassas" diye gizlenebilir (ör. "doktora tezi"). Canını sıkan olursa yaz.

## M. CLAUDE.md bölümü (isteğe bağlı, varsayılan kapalı)
1. **Ayarlar** sayfasında CLAUDE.md / AGENTS.md ile ilgili kartı bul. Önce **Önizle**: ne yazılacağını gösterir, yazmaz.
2. Açarsan `C:\Users\<adın>\.claude\CLAUDE.md` dosyasına işaretli bir bölüm eklenir. Dosyada kendi yazdıkların varsa aynen kalmalı; aynı klasörde `.kimlik-yedek-...` adlı yedek oluşur.
3. Kontrol et: (a) kendi metnin duruyor mu, (b) Claude Code'da yeni oturumda "beni tanıyor musun?" diye sor, araç çağırmadan temel bilgini biliyor mu, (c) ayarı kapatınca bölüm kalkıyor mu.
4. Persona boşsa bölüm "(Henüz onaylanmış bilgi yok.)" yazar; önce **Persona > Öneriler**'den birkaç bilgi onayla.

## N. "Claude'a ekle" izin ekranı
1. **Erişim > "Claude'a ekle"**: bittiğinde izin ekranı kendiliğinden açılmalı ve neyin açık, neyin kapalı olduğunu göstermeli.
2. "Yeni anahtar" ile anahtar üret: önerilen kategoriler işaretli gelmeli; hiçbirini seçmeden kapatmaya çalışınca uyarı çıkmalı.

## O. Bana getireceklerin (özet)
Kopya raporu (I.2), rol denemesi sonucu, token gözlemi, kaçan/gereksiz işaretlenen hassas kayıt örnekleri (sözcük yeter, içerik değil), CLAUDE.md'de kendi metninin korunup korunmadığı.

---

# v0.2.0 ÖNCESİ: SENDEN BEKLENEN TEK İŞ — Android imza anahtarını GitHub'a ekle (16 Kasım 2026)

Neden: imzalı APK'yı GitHub Actions üretiyor ve bunun için imza anahtarına ihtiyacı var. Bu oturum GitHub'ın "gizli değer" ayarına yazamıyor (erişim engelli), o yüzden bu adımı senin yapman gerekiyor. Anahtar eklenene kadar imzalı APK yayınlanamaz.

1. Sohbette sana gönderilen üç dosyayı indir: `kimlikmerkezi-imza.p12`, `KM_KEYSTORE_B64.txt`, `GITHUB-SECRETS.txt`. **Üçünü de güvenli bir yerde sakla.** Anahtar kaybolursa sonraki sürümler eskisinin üstüne kurulamaz (uygulamayı kaldırıp yeniden kurman gerekir, aktarılmamış kayıtlar kaybolur). Bu dosyaları kimseye gönderme, depoya koyma, sohbete yapıştırma.
2. Tarayıcıda `github.com/avsessisozx/kimlik-merkezi` deposunu aç.
3. Deponun **Settings** sekmesine gir. Sol menüde **Secrets and variables** altında **Actions**'ı aç. (GitHub menü adlarını değiştirmiş olabilir; bulamazsan ekrandaki başlıkları bana yaz.)
4. **New repository secret** ile dört gizli değer ekle. Adlar ve değerler `GITHUB-SECRETS.txt` içinde yazılı:
   - `KM_KEYSTORE_B64`: `KM_KEYSTORE_B64.txt` dosyasının tamamı (tek uzun satır).
   - `KM_KEYSTORE_PAROLA`
   - `KM_ANAHTAR_AD`
   - `KM_ANAHTAR_PAROLA`
5. Bitince bana "anahtarları ekledim" yaz. Ben imzalı APK işini çalıştırırım; APK emülatörde açılıp doğrulanınca v0.2.0 yayınlanır.
6. Kontrol: imzalı APK'nın sertifika parmak izi `GITHUB-SECRETS.txt` dosyasının sonundaki SHA-256 ile aynı olmalı (iş günlüğünde yazar; ben karşılaştırırım).

---

# v0.2.0: TELEFONDA DENEYECEKLERİN (yazıldı: 16 Kasım 2026; sürüm yayınlanınca geçerli)

CI bunları test edemez: gerçek telefon, gerçek ev ağı, pil ve üretici kısıtlamaları yalnız sende. Uygulama içi düğme adlarını koddan aldım. **Telefonun ve Windows'un kendi ayar ekranlarındaki adları bilmiyorum ve uydurmuyorum**; farklı görürsen ekrandaki yazıyı bana ilet. Sorun olursa iki uygulamada da "Hata raporunu kopyala".

## P. Bilgisayar tarafı (önce bunu yap)
1. Releases sayfasından **v0.2.0** Windows kurulum dosyasını indirip üstüne kur. Önce Kimlik Merkezi'ni aç, sonra Claude Desktop'u kapatıp yeniden aç.
2. Uygulamada **Telefon** sayfasını aç, **"Telefondan aktarımı aç"** seçeneğini aç.
3. Windows bir Güvenlik Duvarı penceresi gösterebilir. **Özel ağlar** için izin ver. Pencere çıkmazsa ya da neye basacağından emin değilsen ekrandaki yazıyı bana ilet.
4. Ev ağın Windows'ta "Ortak" olarak ayarlıysa telefon bağlanamaz. Bağlanamazsan ilk bakacağımız yer burası; ağ profilini nereden değiştireceğini ekran adını bilmeden yazmak istemiyorum, o durumda bana haber ver.
5. Telefon sayfasında bilgisayarın yerel adresi ve portu yazar (ör. `192.168.x.x : 47823`). Not al; otomatik bulma çalışmazsa telefona elle gireceksin.

## R. Telefona kurulum (önce Realme 7 Pro)
1. Releases sayfasından (github.com/avsessisozx/kimlik-merkezi/releases, v0.2.0) `KimlikMerkezi-v0.2.0.apk` dosyasını telefona indir. İstersen `KimlikMerkezi-v0.2.0.apk.sha256` ile özetini karşılaştır. Dosyayı YALNIZ bu sayfadan al: imza anahtarı bilerek herkese açık depoda (kullanıcı kararı).
2. Dosyaya dokun. Android "bilinmeyen kaynaktan yükleme" için izin isteyecek; izin verip kur. Android sürümüne göre Google ek bir doğrulama ya da bekleme isteyebilir (2026'da gelen "geliştirici doğrulaması"); öyle bir ekran çıkarsa ekrandaki yazıyı bana ilet, geçmeye çalışma.
3. Olmazsa bilgisayardan ADB ile kurulur (bu yol her durumda çalışması beklenen yol): telefonda geliştirici seçeneklerinden USB hata ayıklamayı aç, USB ile bağla, bilgisayarda:
   ```
   adb install KimlikMerkezi-v0.2.0.apk
   ```
   ADB'yi daha önce kullanmadıysan bana yaz, adım adım anlatırım.
4. Uygulamayı aç. Bir hızlı not yaz, sonra başka bir uygulamadan (ör. tarayıcı) bir linki **Paylaş** ile Kimlik Merkezi'ne gönder. Ana ekranda "X kayıt henüz PC'ye gitmedi" sayısı artmalı.

## S. Eşleştirme
1. Bilgisayarda Telefon sayfasında **"Telefon ekle"**ye bas: bir QR ve altında uzun bir kod çıkar (10 dakika geçerli).
2. Telefonda **"PC'ye gönder"**e bas; eşleşme yoksa eşleştirme ekranı açılır. QR'ı okut. **Kamerayla QR okuma hiç denenmedi**; okumazsa bilgisayardaki kodu kopyalayıp kendine gönder (ör. kendine not/mesaj) ve telefonda "kodu yapıştır" alanına yapıştır.
3. Telefon "<bilgisayar adı> ile eşleştirilsin mi?" diye sorar; onayla.
4. Bilgisayarda Telefon sayfasındaki cihaz listesinde telefonun görünmeli.
5. Hata alırsan mesajı aynen yaz. En olası nedenler: telefon ile bilgisayar aynı Wi-Fi'da değil; Güvenlik Duvarı izni verilmedi; kodun süresi doldu.

## T. Gönderim ve asıl deneme (bilgisayar kapalı 1 gün)
1. **Hemen:** telefonda "PC'ye gönder"e bas. Bekleyen sayı 0 olmalı; bilgisayarda "Telefondan N yeni kayıt alındı" yazmalı; notun aramada çıkmalı.
2. **Asıl deneme:** bilgisayarı kapat (ya da Kimlik Merkezi'ni kapat). Bir gün boyunca telefonu normal kullan; birkaç not yaz, birkaç link paylaş. Ertesi gün bilgisayarı ve Kimlik Merkezi'ni aç.
3. Önce HİÇBİR ŞEYE BASMADAN yarım saat bekle: telefon kendiliğinden gönderdi mi? (Bunu bilmiyorum; Realme ve Xiaomi arka plan uygulamalarını kapatabiliyor.)
4. Göndermediyse telefonda uygulamayı açıp "PC'ye gönder"e bas. Hepsi gelmeli, hiçbiri iki kez gelmemeli.
5. Kesinti denemesi: çok sayıda kayıt varken gönderim sürerken telefonun Wi-Fi'ını kapatıp aç, yeniden "PC'ye gönder". Kaldığı yerden bitmeli.
6. Bana yaz: (a) kendiliğinden gönderdi mi, ne kadar sonra; (b) eksik ya da çift kayıt var mı; (c) telefonda "Son başarılı gönderim" saati doğru mu; (d) pilde fark ettiğin bir şey.

## U. Arka planda çalışmıyorsa
1. Telefondaki uygulamada Ayarlar'da "Arka planda gönderim çalışmıyorsa" sayfasını aç; oradaki düğme seni telefonun pil ayarına götürür. Açılan ekranda Kimlik Merkezi için pil kısıtlamasını kaldır. Realme ve Xiaomi'de bu ayarın adı ve yeri farklıdır; bulamazsan ekrandaki seçenekleri bana yaz.
2. Her durumda çalışan yol: uygulamayı açıp "PC'ye gönder"e basmak.

## V. İsteğe bağlı toplayıcılar (hepsi kapalı gelir)
Telefonda Ayarlar'dan tek tek açılır: fotoğraf-video bilgisi (içerik değil, yalnız ad/boyut/tarih), fotoğraf konumu (ayrı izin; konum bilgisayarda "konum" kategorisine düşer ve o kategori hassastır), indirilenler (bir klasör seçersin), uygulama kullanım süreleri (telefon seni özel bir izin ekranına götürür). Açtıklarını ve izin ekranında takıldığın yeri bana yaz. İlk fotoğraf taraması galeri büyükse biraz sürebilir.

## Y. Uyarılar
- Uygulamayı KALDIRMA: gönderilmemiş kayıtlar ve eşleştirme silinir. Güncellerken üstüne kur.
- Yedek yol: telefonda Ayarlar > "Dosyaya aktar" (dosya şifresizdir), dosyayı bilgisayara taşı, bilgisayarda Telefon sayfasında "Telefon dosyası al".
- Mi 10T Pro, Redmi Note 10 Pro ve tablet: aynı adımlar. Her cihaz ayrı eşleştirilir. Android 12 dışındaki sürümler hiç denenmedi; izin ekranında sorun çıkarsa Android sürümünü de yaz.

## Z. Bana getireceklerin (özet)
Eşleştirme oldu mu (QR mı, kod mu); ilk gönderim sonucu; bir günlük denemede kendiliğinden gönderdi mi; eksik/çift kayıt; takıldığın her ekranın yazısı; iki uygulamanın hata raporu (sorun olduysa).

