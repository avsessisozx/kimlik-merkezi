// Gerçek tarayıcıda: Telefon sayfası (aç -> kod+QR -> eşleşme (Python yapar) -> cihaz listesi -> kaldır -> kapat).
// test_tarayici_telefon.py çalıştırır. Kullanım: node telefon.js <ayar.json>. Çıkış 77: Playwright/Chromium yok.
// Eşgüdüm: "KOD <json>" satırı yazılır, sonra ayar.sinyal dosyası oluşana kadar beklenir (eşleşmeyi Python yapar).
"use strict";
const fs = require('fs');
let chromium;
try { ({ chromium } = require('playwright')); } catch (e) { process.stderr.write('playwright yok: ' + e.message + '\n'); process.exit(77); }
const ayar = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const bekle = ms => new Promise(r => setTimeout(r, ms));
async function kosulBekle(p, fn, arg, { timeout = 20000 } = {}) {
  const son = Date.now() + timeout;
  for (;;) {
    if (await p.evaluate(fn, arg === undefined ? null : arg)) return;
    if (Date.now() > son) throw new Error(`kosulBekle: ${timeout} ms içinde koşul sağlanmadı`);
    await bekle(100);
  }
}
const metin = (p, s) => p.evaluate(x => { const e = document.querySelector(x); return e ? e.innerText : null; }, s);
(async () => {
  let b;
  try { b = await chromium.launch(); } catch (e) { process.stderr.write('chromium açılamadı: ' + e.message + '\n'); process.exit(77); }
  const sonuc = { hatalar: [] };
  try {
    const c = await b.newContext({ viewport: { width: 1280, height: 1100 } }), p = await c.newPage();
    p.on('pageerror', e => sonuc.hatalar.push('pageerror: ' + e));
    p.on('console', m => { if (m.type() === 'error') sonuc.hatalar.push('console: ' + m.text()); });
    p.on('dialog', d => d.accept());
    await p.goto(ayar.url); await bekle(1200);
    await p.locator('nav button', { hasText: /^Telefon$/ }).click();
    await p.waitForSelector('#tel-ac', { timeout: 15000 });
    sonuc.baslangic_durum = await metin(p, '#tel-durum');
    sonuc.ekle_pasif = await p.evaluate(() => document.querySelector('#tel-ekle').disabled);
    await p.click('#tel-ac');                                   // ilk açış: açıklama penceresi
    await p.waitForSelector('#tel-aciklama', { timeout: 5000 });
    sonuc.aciklama = await metin(p, '#tel-aciklama');
    await p.click('#tel-onay');
    await kosulBekle(p, () => document.querySelector('#tel-durum').innerText.startsWith('Çalışıyor'));
    sonuc.acik_durum = await metin(p, '#tel-durum');
    sonuc.acik_isaret = await p.evaluate(() => document.querySelector('#tel-ac').checked);
    await p.click('#tel-ekle');
    await p.waitForSelector('#tel-kod', { timeout: 10000 });
    sonuc.kod = await p.evaluate(() => document.querySelector('#tel-kod').value);
    sonuc.kalan = await metin(p, '#tel-kalan');
    sonuc.qr = await p.evaluate(() => { const t = document.querySelector('#tel-qr canvas'); return t ? { w: t.width, surum: t.dataset.surum, png: t.toDataURL('image/png') } : null; });
    process.stdout.write('KOD ' + JSON.stringify({ kod: sonuc.kod, png: sonuc.qr && sonuc.qr.png }) + '\n');
    for (let i = 0; i < 300 && !fs.existsSync(ayar.sinyal); i++) await bekle(100);
    await p.waitForSelector('.tel-cihaz', { timeout: 15000 });
    sonuc.cihaz = await metin(p, '.tel-cihaz');
    sonuc.kod_sonrasi = await metin(p, '#tel-kod-alani');         // kod kullanıldı: "Telefon eşleşti."
    await p.click('.tel-cihaz button');                            // confirm otomatik kabul
    await kosulBekle(p, () => { const e = document.querySelector('.tel-cihaz'); return e && e.innerText.includes('Eşleştirme kaldırıldı'); });
    sonuc.kaldirilan = await metin(p, '.tel-cihaz');
    sonuc.kaldir_dugmesi_kaldi = (await p.locator('.tel-cihaz button').count()) > 0;
    sonuc.dosya_al = (await p.locator('#tel-dosya-al').count()) === 1;
    await p.click('#tel-dosya-al');
    await p.waitForSelector('#ice-yol', { timeout: 10000 });
    sonuc.ice_sayfasi = true;
    await p.locator('nav button', { hasText: /^Telefon$/ }).click();
    await p.waitForSelector('#tel-ac');
    await p.click('#tel-ac');                                      // kapat (onay penceresi yok)
    await kosulBekle(p, () => document.querySelector('#tel-durum').innerText.startsWith('Kapalı'));
    sonuc.kapali_durum = await metin(p, '#tel-durum');
    sonuc.ekle_pasif_sonra = await p.evaluate(() => document.querySelector('#tel-ekle').disabled);
    sonuc.bildirim_hatalari = await p.evaluate(() => [...document.querySelectorAll('#bildirim div.h')].map(d => d.textContent));
    await c.close();
    process.stdout.write(JSON.stringify(sonuc) + '\n');
  } finally { await b.close(); }
})().catch(e => { process.stderr.write('HATA: ' + (e && e.stack || e) + '\n'); process.exit(1); });
