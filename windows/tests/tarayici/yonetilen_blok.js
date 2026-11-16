// Gerçek tarayıcıda: Ayarlar > yönetilen blok kartı (önizle -> yazmaz; aç -> dosya oluşur; kapat -> bölüm kalkar).
// test_tarayici_blok.py çalıştırır. Kullanım: node yonetilen_blok.js <ayar.json>. Çıkış 77: Playwright/Chromium yok.
"use strict";
const fs = require('fs');
let chromium;
try { ({ chromium } = require('playwright')); } catch (e) { process.stderr.write('playwright yok: ' + e.message + '\n'); process.exit(77); }
const ayar = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const bekle = ms => new Promise(r => setTimeout(r, ms));
async function kosulBekle(fn, { timeout = 20000 } = {}) {
  const son = Date.now() + timeout;
  for (;;) {
    if (await fn()) return;
    if (Date.now() > son) throw new Error(`kosulBekle: ${timeout} ms içinde koşul sağlanmadı`);
    await bekle(100);
  }
}
const metin = (p, s) => p.evaluate(x => { const e = document.querySelector(x); return e ? (e.value !== undefined && e.tagName === 'TEXTAREA' ? e.value : e.innerText) : null; }, s);
const var_ = y => fs.existsSync(y);
(async () => {
  let b;
  try { b = await chromium.launch(); } catch (e) { process.stderr.write('chromium açılamadı: ' + e.message + '\n'); process.exit(77); }
  const sonuc = { hatalar: [] };
  try {
    const c = await b.newContext({ viewport: { width: 1280, height: 1000 } }), p = await c.newPage();
    p.on('pageerror', e => sonuc.hatalar.push('pageerror: ' + e));
    p.on('console', m => { if (m.type() === 'error') sonuc.hatalar.push('console: ' + m.text()); });
    await p.goto(ayar.url); await bekle(1200);
    await p.locator('nav button', { hasText: /^Ayarlar$/ }).click();
    await p.waitForSelector('#ayar-yonetilen-blok', { timeout: 15000 });
    await bekle(500);
    sonuc.kart = await metin(p, '#ayar-yonetilen-blok');
    sonuc.baslangic_acik = await p.isChecked('#ayar-blok');
    await p.click('#blok-onizle');
    await p.waitForSelector('#blok-onizle-metin', { timeout: 10000 });
    sonuc.onizleme = await metin(p, '#blok-onizle-metin');
    sonuc.onizleme_sonrasi_dosya = var_(ayar.claude);
    await p.getByRole('button', { name: 'Kapat' }).click();
    await p.check('#ayar-blok');
    await kosulBekle(async () => var_(ayar.claude));
    await bekle(400);
    sonuc.acik_dosya = fs.readFileSync(ayar.claude, 'utf8');
    sonuc.acik_liste = await metin(p, '#blok-dosyalar');
    sonuc.ayar_acik = await p.evaluate(async () => (await api('ayarlar')).yonetilen_blok);
    await p.uncheck('#ayar-blok');
    await kosulBekle(async () => !fs.readFileSync(ayar.claude, 'utf8').includes('KIMLIK-MERKEZI:BASLA'));
    sonuc.kapali_dosya = fs.readFileSync(ayar.claude, 'utf8');
    sonuc.bildirim_hatalari = await p.evaluate(() => [...document.querySelectorAll('#bildirim div.h')].map(d => d.textContent));
    await c.close();
    process.stdout.write(JSON.stringify(sonuc) + '\n');
  } finally { await b.close(); }
})().catch(e => { process.stderr.write('HATA: ' + (e && e.stack || e) + '\n'); process.exit(1); });
