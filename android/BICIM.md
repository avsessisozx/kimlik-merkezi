# Giden kutusu disk biçimi (telefon)

Çözülmüş içerik `docs/AKTARIM.md` §1 ile birebirdir (başlık, kayıtlar, kapanış; UTF-8, satır sonu `\n`).
Bu belge yalnız telefondaki ŞİFRELİ disk biçimini anlatır. Testle sabitlenir: `CerceveTest`, `GidenKutusuTest`.

## Dosya
- Yer: `filesDir/giden/<dosya_id>.jsonl.kmx` (`dosya_id` UUID4).
- Dosya, art arda çerçevelerden oluşur. Çerçeve başına BİR satır (satırın sonundaki `\n` dahil). Ham düz metin diske yazılmaz.
- Çerçeve sırası: 0 = başlık, 1..N = kayıtlar, N+1 = kapanış (yalnız kapatılmış dosyada).
- Açık dosyaya yalnız çerçeve eklenir; her çerçeve yazıldıktan sonra `fsync`. Kapanış çerçevesi yazılan dosya değişmez.
- Satırdaki U+2028, U+2029, U+0085 karakterleri JSON içinde `\uXXXX` olarak kaçırılır (PC tarafında `splitlines` benzeri ayırıcılar satırı bölmesin).

## Çerçeve
```
uzunluk  : 4 bayt, big-endian işaretli tamsayı = sonraki bayt sayısı (nonce + şifreli metin + etiket)
nonce    : 12 bayt (AES-GCM, her çerçevede sağlayıcı üretir)
şifreli  : düz satırın uzunluğu kadar bayt
etiket   : 16 bayt (GCM kimlik doğrulama etiketi)
```
- Algoritma: AES-256-GCM, anahtar Android Keystore'da (takma ad `km_giden_kutusu_v1`), dışarı çıkarılamaz.
- AAD (kimlik doğrulanan ek veri): `dosya_id` (UTF-8) + `0x00` + çerçeve sırası (8 bayt big-endian). Başka dosyaya taşınan ya da yeri değişen çerçeve doğrulanmaz.
- `uzunluk` < 28 ya da > 16 MiB ise çerçeve bozuk sayılır.

## Açılışta onarım
- Sonda yarım çerçeve (kısa uzunluk öneki ya da eksik gövde): son tam çerçeveye kadar kesilir; atılan sayı günlüğe yazılır (içerik yazılmaz).
- Yalnızca yarım çerçeveden oluşan dosya silinir.
- Doğrulanamayan tam çerçeve (kurcalama/bozulma), geçersiz başlık, tutmayan `kayit_sayisi`, kapanıştan sonra satır: dosya BOZUK sayılır, silinmez, aktarıma ve sayaca girmez (`bozukDosyaSayisi`).
