// qrcode.js + telefon.js'teki qrMatris'i tarayıcısız (node vm) çalıştırır: stdin'den metin satırları, stdout'a JSON matrisler.
// Kullanım: node qr_matris.js <statik klasörü>   (test_telefon_qr.py çalıştırır)
"use strict";
const fs = require('fs'), vm = require('vm'), path = require('path');
const statik = process.argv[2];
const ctx = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(statik, 'qrcode.js'), 'utf8'), ctx);
vm.runInContext(fs.readFileSync(path.join(statik, 'telefon.js'), 'utf8'), ctx);
const girdi = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(girdi.map(m => vm.runInContext('qrMatris(' + JSON.stringify(m) + ')', ctx))));
