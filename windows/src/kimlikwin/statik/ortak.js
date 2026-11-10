/* Ortak yardımcılar: diğer betiklerden (figur.js, harita.js, index.html) ÖNCE yüklenir.
   Tek tanım: SAYI. Başka dosyada yeniden tanımlamayın (aynı ada const bildirmek betiği çökertir);
   windows/tests/test_arayuz_betikleri.py bunu denetler. */
"use strict";
// Sayı biçimi her yerde tr-TR (binlik ayraç nokta): 15171 -> "15.171"
const SAYI=n=>Number(n).toLocaleString('tr-TR');
// Kayıt saatleri veritabanında UTC tutulur ve her yerde UTC olarak gösterilir; hep bu etiketle.
const UTC_ETIKET='UTC';
