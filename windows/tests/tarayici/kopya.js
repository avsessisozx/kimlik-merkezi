// Gerçek tarayıcıda: Kaynaklar > "Sohbet kopyalarını denetle" (denetle -> sayı görünür -> gizle -> onay -> sonuç).
// test_tarayici_kopya.py çalıştırır. Kullanım: node kopya.js <ayar.json>. Çıkış 77: Playwright/Chromium yok.
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
    const c = await b.newContext({ viewport: { width: 1280, height: 1000 } }), p = await c.newPage();
    p.on('pageerror', e => sonuc.hatalar.push('pageerror: ' + e));
    p.on('console', m => { if (m.type() === 'error') sonuc.hatalar.push('console: ' + m.text()); });
    await p.goto(ayar.url); await bekle(1200);
    await p.locator('nav button', { hasText: /^Kaynaklar$/ }).click();
    await p.waitForSelector('#kopya-karti', { timeout: 15000 });
    sonuc.kart = await metin(p, '#kopya-karti');
    await p.click('#kopya-denetle');
    await p.waitForSelector('#kopya-ozet', { timeout: 15000 });
    sonuc.denetim = await metin(p, '#kopya-ozet');
    sonuc.gizle_var = (await p.locator('#kopya-gizle').count()) === 1;
    await p.click('#kopya-gizle');
    await p.waitForSelector('#kopya-onay', { timeout: 5000 });
    sonuc.onay = await metin(p, '#kok-pencere');
    await p.click('#kopya-onay');
    await kosulBekle(p, () => { const e = document.querySelector('#kopya-ozet'); return e && e.innerText.includes('gizlendi'); });
    sonuc.sonuc = await metin(p, '#kopya-ozet');
    sonuc.gizle_sonra = (await p.locator('#kopya-gizle').count()) === 1;
    sonuc.rapor_dugmesi = (await p.locator('#kopya-rapor').count()) === 1;
    sonuc.bildirim_hatalari = await p.evaluate(() => [...document.querySelectorAll('#bildirim div.h')].map(d => d.textContent));
    await c.close();
    process.stdout.write(JSON.stringify(sonuc) + '\n');
  } finally { await b.close(); }
})().catch(e => { process.stderr.write('HATA: ' + (e && e.stack || e) + '\n'); process.exit(1); });
