// Güvenlik sayfası ve kilit ekranı için gerçek tarayıcı senaryoları (Playwright + Chromium).
// Kullanım: node guvenlik.js <ayar.json> <mod>   Modlar: akis | kilit-yanlis | kilit-dogru | kilit-kurtar
// Çıktı: stdout'un son satırı JSON. Çıkış 77: Playwright/Chromium yok.
"use strict";
const fs = require('fs');
let chromium;
try { ({ chromium } = require('playwright')); } catch (e) { process.stderr.write('playwright yok: ' + e.message + '\n'); process.exit(77); }
const ayar = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const mod = process.argv[3];
const bekle = ms => new Promise(r => setTimeout(r, ms));
// CSP (script-src bez 'unsafe-eval') altında page.waitForFunction çalışmaz; koşulu Node tarafında yoklarız (evaluate CSP'ye takılmaz).
async function kosulBekle(p, fn, arg, { timeout = 30000 } = {}) {
  const son = Date.now() + timeout;
  for (;;) {
    if (await p.evaluate(fn, arg === undefined ? null : arg)) return;
    if (Date.now() > son) throw new Error(`kosulBekle: ${timeout} ms içinde koşul sağlanmadı`);
    await new Promise(r => setTimeout(r, 100));
  }
}
const goruntu = async (p, ad) => { if (ayar.ekran_dizini) await p.screenshot({ path: `${ayar.ekran_dizini}/guvenlik-${ad}.png` }); };
const metin = p => p.evaluate(() => document.body.innerText);
const hatalar = [];

async function bildirimHatalari(p) {
  return p.evaluate(() => [...document.querySelectorAll('#bildirim div.h')].map(d => d.firstChild ? d.firstChild.textContent : d.textContent));
}
async function metinBekle(p, parca, ms = 8000) {
  await kosulBekle(p, t => document.body.innerText.includes(t), parca, { timeout: ms });
}
async function git(p, ad) {
  await p.locator('nav button', { hasText: new RegExp('^' + ad + '$') }).click();
  await kosulBekle(p, () => document.querySelector('#ana').children.length > 0, null, { timeout: 15000 });
  await bekle(500);
}
async function ifadeYaz(p, a, b) {
  await p.fill('#g-ifade', a); await p.fill('#g-ifade2', b); await bekle(700);
}
function tasma() {
  const W = innerWidth, kotu = [];
  document.querySelectorAll('#ana *, #kok-pencere *').forEach(e => { const r = e.getBoundingClientRect(); if (r.width && r.right > W + 1 && !e.closest('.tablo-kap')) kotu.push(e.tagName + '#' + e.id + ' sağ=' + Math.round(r.right)); });
  return { belge: document.documentElement.scrollWidth - W, ogeler: kotu.slice(0, 5) };
}

async function akis(b) {
  const s = {};
  const c = await b.newContext({ viewport: { width: 1280, height: 900 } }), p = await c.newPage();
  p.on('pageerror', e => hatalar.push('pageerror: ' + e)); p.on('console', m => { if (m.type() === 'error') hatalar.push('console: ' + m.text()); });
  await p.goto(ayar.url); await bekle(1200);
  await git(p, 'Güvenlik');
  s.durum_metin = await metin(p);
  await goruntu(p, '01-durum');
  s.parola_ekle_dugmesi = await p.locator('#g-parola-ekle').count();

  // --- Parola ekle: 1) kurtarma ifadesi kuralları
  await p.click('#g-parola-ekle'); await p.waitForSelector('#g-ifade');
  s.ifade_baslik = await metin(p);
  s.ileri_bos = await p.isDisabled('#g-ileri');
  await ifadeYaz(p, 'correct horse battery staple', 'correct horse battery staple');
  s.zayif_metin = await p.innerText('#g-ifade-sorun'); s.zayif_ileri_kapali = await p.isDisabled('#g-ileri');
  await goruntu(p, '02-ifade-zayif');
  await ifadeYaz(p, 'kısa yanıt', 'kısa yanıt');
  s.kisa_metin = await p.innerText('#g-ifade-sorun'); s.kisa_ileri_kapali = await p.isDisabled('#g-ileri');
  await ifadeYaz(p, ayar.ifade, ayar.ifade + ' farklı');
  s.farkli_metin = await p.innerText('#g-ifade-sorun'); s.farkli_ileri_kapali = await p.isDisabled('#g-ileri');
  await ifadeYaz(p, ayar.ifade, ayar.ifade);
  s.iyi_metin = await p.innerText('#g-ifade-sorun'); s.guc_metin = await p.innerText('#g-ifade-guc'); s.iyi_ileri_acik = !(await p.isDisabled('#g-ileri'));
  await goruntu(p, '03-ifade-iyi');
  s.ifade_tipi = await p.getAttribute('#g-ifade', 'type');
  await p.click('#g-ileri');

  // --- 2) kurtarılamaz uyarısı ve ZORUNLU onay kutusu
  await p.waitForSelector('#g-onay');
  s.uyari_metin = await p.innerText('#g-uyari'); s.mcp_uyari = await p.innerText('#g-mcp-uyari');
  s.devam_onaysiz_kapali = await p.isDisabled('#g-devam');
  await goruntu(p, '04-onay');
  await p.click('#g-onay'); s.devam_onayli_acik = !(await p.isDisabled('#g-devam'));
  await p.click('#g-onay'); s.devam_onay_kalkinca_kapali = await p.isDisabled('#g-devam');
  await p.click('#g-onay');
  await p.click('#g-devam');

  // --- 3) parola
  await p.waitForSelector('#g-parola');
  s.ifade_kuruldu = await p.locator('#g-ifade-kuruldu').count();
  s.kaydet_bos_kapali = await p.isDisabled('#g-parola-kaydet');
  await p.fill('#g-parola', 'kisa'); await p.fill('#g-parola2', 'kisa'); await bekle(600);
  s.kisa_parola = await p.innerText('#g-parola-sorun'); s.kisa_parola_kapali = await p.isDisabled('#g-parola-kaydet');
  await p.fill('#g-parola', ayar.parola); await p.fill('#g-parola2', ayar.parola + 'x'); await bekle(600);
  s.farkli_parola = await p.innerText('#g-parola-sorun'); s.farkli_parola_kapali = await p.isDisabled('#g-parola-kaydet');
  await p.fill('#g-parola', ayar.parola); await p.fill('#g-parola2', ayar.parola); await bekle(600);
  s.parola_acik = !(await p.isDisabled('#g-parola-kaydet'));
  await goruntu(p, '05-parola');
  await p.click('#g-parola-kaydet');
  await metinBekle(p, 'Parola eklendi');
  await bekle(1200);
  s.sonra_metin = await metin(p);
  s.parola_dugmeleri = [await p.locator('#g-parola-kaldir').count(), await p.locator('#g-parola-sifirla').count()];
  await goruntu(p, '06-parola-eklendi');
  s.tasma_masaustu = await p.evaluate(tasma);
  s.bildirimler = await bildirimHatalari(p);
  await c.close();

  // mobil görünüm
  const m = await b.newContext({ viewport: { width: 390, height: 800 } }), mp = await m.newPage();
  await mp.goto(ayar.url); await bekle(1200);
  await git(mp, 'Güvenlik'); await goruntu(mp, '07-mobil');
  s.tasma_mobil = await mp.evaluate(tasma);
  await mp.click('#g-parola-kaldir'); await mp.waitForSelector('#g-mevcut-parola'); await goruntu(mp, '08-mobil-kaldir');
  s.tasma_mobil_pencere = await mp.evaluate(tasma);
  await m.close();
  s.konsol = hatalar.slice();
  return s;
}

async function kilitAc(b, w = 1280) {
  const c = await b.newContext({ viewport: { width: w, height: 800 } }), p = await c.newPage();
  p.on('pageerror', e => hatalar.push('pageerror: ' + e)); p.on('console', m => { if (m.type() === 'error' && !/423|429|400/.test(m.text())) hatalar.push('console: ' + m.text()); });
  await p.goto(ayar.url); await p.waitForSelector('#g-kilit-parola, #g-kilit-kurtarma', { timeout: 10000 });
  return { c, p };
}

async function kilitYanlis(b) {
  const s = {}; const { c, p } = await kilitAc(b);
  s.baslik = await metin(p);
  s.nav_bos = await p.evaluate(() => document.querySelector('#nav').children.length);
  await goruntu(p, '09-kilit');
  for (let i = 0; i < 3; i++) {
    await p.fill('#g-kilit-parola', 'yanlis-parola-0000-zzz'); await p.click('#g-kilit-ac');
    await kosulBekle(p, () => document.querySelector('#g-hata').style.display !== 'none', null, { timeout: 8000 }); await bekle(300);
    s['hata' + i] = await p.innerText('#g-hata');
  }
  s.dugme_metni = await p.innerText('#g-kilit-ac'); s.dugme_kapali = await p.isDisabled('#g-kilit-ac');
  await goruntu(p, '10-kilit-yanlis');
  s.ana_icerik = await p.evaluate(() => document.querySelector('#ana').children.length);
  s.konsol = hatalar.slice();
  await c.close(); return s;
}

async function kilitDogru(b) {
  const s = {}; const { c, p } = await kilitAc(b);
  await p.fill('#g-kilit-parola', ayar.parola); await p.click('#g-kilit-ac');
  await kosulBekle(p, () => document.querySelector('#nav').children.length > 0, null, { timeout: 15000 }); await bekle(1200);
  s.kilit_kalkti = (await p.locator('#g-kilit-parola').count()) === 0;
  s.nav = await p.evaluate(() => document.querySelector('#nav').innerText);
  s.parola_alani_yok = (await p.locator('input[type=password]').count()) === 0;
  await goruntu(p, '11-acildi');
  s.bildirimler = await bildirimHatalari(p); s.konsol = hatalar.slice();
  await c.close(); return s;
}

async function kilitKurtar(b) {
  const s = {}; const { c, p } = await kilitAc(b);
  await p.click('#g-kilit-unuttum'); await p.waitForSelector('#g-kilit-ifade');
  await goruntu(p, '12-kurtar');
  await p.fill('#g-kilit-ifade', 'tamamen yanlis bir ifade burada 123'); await p.fill('#g-kilit-yeni', ayar.yeni_parola); await p.fill('#g-kilit-yeni2', ayar.yeni_parola); await bekle(700);
  await p.click('#g-kilit-kurtar'); await kosulBekle(p, () => document.querySelectorAll('#g-kilit-kurtarma .hata').length && [...document.querySelectorAll('#g-kilit-kurtarma .hata')].some(e => e.style.display !== 'none'), null, { timeout: 8000 });
  s.yanlis_ifade = await p.evaluate(() => [...document.querySelectorAll('#g-kilit-kurtarma .hata')].filter(e => e.style.display !== 'none').map(e => e.innerText).join('|'));
  await p.fill('#g-kilit-ifade', ayar.ifade); await bekle(300);
  await p.click('#g-kilit-kurtar');
  await kosulBekle(p, () => document.querySelector('#nav').children.length > 0, null, { timeout: 15000 }); await bekle(800);
  s.acildi = (await p.locator('#g-kilit-parola').count()) === 0;
  s.bildirimler = await bildirimHatalari(p); s.konsol = hatalar.slice();
  await c.close(); return s;
}

async function donusum(b) {
  const s = {}; const c = await b.newContext({ viewport: { width: 1280, height: 900 } }), p = await c.newPage();
  p.on('pageerror', e => hatalar.push('pageerror: ' + e)); p.on('console', m => { if (m.type() === 'error') hatalar.push('console: ' + m.text()); });
  await p.goto(ayar.url); await bekle(1200);
  await git(p, 'Güvenlik');
  await p.click('#g-kapat'); await p.waitForSelector('#g-donus-yaz');
  s.kapat_metin = await metin(p);
  s.basta_kapali = await p.isDisabled('#g-donus-basla');
  await p.fill('#g-donus-yaz', 'KALDIR'); await p.fill('#g-mevcut-parola', ayar.yeni_parola);
  s.onaysiz_kapali = await p.isDisabled('#g-donus-basla');
  await goruntu(p, '13-kapat');
  await p.click('#g-donus-onay'); s.onayli_acik = !(await p.isDisabled('#g-donus-basla'));
  await p.fill('#g-donus-yaz', 'kaldir'); s.kucuk_harf_kapali = await p.isDisabled('#g-donus-basla');
  await p.fill('#g-donus-yaz', 'KALDIR');
  await p.click('#g-donus-basla');
  await p.waitForSelector('#g-donus-sonuc', { timeout: 60000 });
  s.kapat_sonuc = await p.innerText('#g-donus-sonuc');
  await p.click('#g-donus-tamam'); await bekle(800);
  s.kapali_metin = await metin(p); await goruntu(p, '14-kapali');
  await p.click('#g-sifrele'); await p.waitForSelector('#g-donus-onay');
  s.ac_basta_kapali = await p.isDisabled('#g-donus-basla');
  await p.click('#g-donus-onay'); await p.click('#g-donus-basla');
  await p.waitForSelector('#g-donus-sonuc', { timeout: 60000 });
  s.ac_sonuc = await p.innerText('#g-donus-sonuc');
  await p.click('#g-donus-tamam'); await bekle(800);
  s.acik_metin = await metin(p);
  s.bildirimler = await bildirimHatalari(p); s.konsol = hatalar.slice();
  await c.close(); return s;
}

async function sihirbaz(b) {
  const s = {}; const c = await b.newContext({ viewport: { width: 1280, height: 900 } }), p = await c.newPage();
  p.on('pageerror', e => hatalar.push('pageerror: ' + e)); p.on('console', m => { if (m.type() === 'error') hatalar.push('console: ' + m.text()); });
  await p.goto(ayar.url); await p.waitForSelector('.pencere input[type=text]');
  await p.locator('.pencere input[type=text]').nth(1).fill(ayar.sihirbaz_yol);
  await kosulBekle(p, () => !document.querySelector('.pencere button.d').disabled, null, { timeout: 10000 });
  s.adim1 = await metin(p); await goruntu(p, '15-sihirbaz-1');
  await p.click('.pencere button.d'); await bekle(300);
  await p.locator('.pencere button.d', { hasText: 'Kur' }).click();
  await p.waitForSelector('#sihirbaz-sifreleme', { timeout: 20000 });
  s.adim3 = await p.innerText('#sihirbaz-sifreleme'); await goruntu(p, '16-sihirbaz-3');
  s.konsol = hatalar.slice();
  await c.close(); return s;
}

(async () => {
  let b;
  try { b = await chromium.launch(); } catch (e) { process.stderr.write('chromium açılamadı: ' + e.message + '\n'); process.exit(77); }
  try {
    const f = { akis, 'kilit-yanlis': kilitYanlis, 'kilit-dogru': kilitDogru, 'kilit-kurtar': kilitKurtar, donusum, sihirbaz }[mod];
    const sonuc = await f(b);
    process.stdout.write(JSON.stringify(sonuc) + '\n');
  } catch (e) {
    process.stderr.write('senaryo hatası: ' + (e && e.stack || e) + '\n'); await b.close(); process.exit(1);
  }
  await b.close();
})();
