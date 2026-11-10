// Gerçek tarayıcı (Playwright + Chromium) ile arayüz gezintisi. test_tarayici.py tarafından çalıştırılır.
// Kullanım: node gezinti.js <ayar.json>   Çıktı: stdout'a tek satır JSON. Çıkış 77: Playwright/Chromium yok (test atlanır).
// Neden gerçek tarayıcı: sayfa betiğindeki bir ReferenceError (ör. "SAYI is not defined") sunucu testlerinde
// görünmez; ekran hata bildirim kutusuna düşer, konsola değil. Burada ikisi de toplanır.
"use strict";
const fs = require('fs');
let chromium;
try { ({ chromium } = require('playwright')); } catch (e) { process.stderr.write('playwright yok: ' + e.message + '\n'); process.exit(77); }
const ayar = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const SAYFALAR = [['Anasayfa', 'Ana sayfa'], ['Harita', 'Harita'], ['İçe aktar', 'İçe aktar'], ['Arama', 'Arama'],
  ['Zaman çizelgesi', 'Zaman çizelgesi'], ['Persona', 'Persona'], ['Erişim', 'Erişim'], ['Kaynaklar', 'Kaynaklar'], ['Güvenlik', 'Güvenlik'], ['Ayarlar', 'Ayarlar'], ['Hakkında', 'Hakkında']];
const bekle = ms => new Promise(r => setTimeout(r, ms));

async function toplayici(sayfa) {
  const hatalar = [];
  sayfa.on('pageerror', e => hatalar.push('pageerror: ' + e));
  sayfa.on('console', m => { if (m.type() === 'error') hatalar.push('console: ' + m.text()); });
  sayfa.on('requestfailed', r => hatalar.push('istek başarısız: ' + r.url()));
  return hatalar;
}
// Arayüzün kendi hata bildirimi (#bildirim .h) da bir hatadır; ardından temizlenir.
async function bildirimHatalari(p) {
  return p.evaluate(() => { const k = [...document.querySelectorAll('#bildirim div.h')].map(d => d.firstChild ? d.firstChild.textContent : d.textContent); document.querySelector('#bildirim').textContent = ''; return k; });
}
async function git(p, ad) {
  await p.locator('nav button', { hasText: new RegExp('^' + ad + '$') }).click();
  await p.waitForFunction(() => document.querySelector('#ana').children.length > 0 || document.querySelector('#bildirim div.h'), null, { timeout: 15000 }).catch(() => {});
  await bekle(900);
}
// Yatay taşma: sayfa ya da (kaydırılabilir bir kap içinde olmayan) bir öğe görünür genişliği aşıyor mu
function tasma() {
  const W = innerWidth, kotu = [];
  const kaydirilir = e => { for (let x = e.parentElement; x; x = x.parentElement) { const o = getComputedStyle(x).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };
  document.querySelectorAll('#ana *').forEach(e => { const r = e.getBoundingClientRect(); if (r.width && r.right > W + 1 && !kaydirilir(e) && !e.closest('svg') && !e.closest('canvas')) kotu.push(e.tagName + '.' + (e.className && e.className.baseVal === undefined ? e.className : '') + ' sağ=' + Math.round(r.right)); });
  return { belge: document.documentElement.scrollWidth - W, ogeler: kotu.slice(0, 5) };
}
async function sonuclariTopla(b) {
  const sonuc = { sayfalar: {}, ice: {}, mobil: {}, tema: {} };

  // ---- masaüstü: her ana ekran
  { const c = await b.newContext({ viewport: { width: 1280, height: 850 } }), p = await c.newPage(), hatalar = await toplayici(p);
    await p.goto(ayar.url); await bekle(1500);
    sonuc.baslangic_hatalari = await bildirimHatalari(p);
    for (const [id, ad] of SAYFALAR) {
      await git(p, ad);
      const o = await p.evaluate(() => ({ metin: document.querySelector('#ana').innerText, cocuk: document.querySelector('#ana').children.length }));
      sonuc.sayfalar[id] = { bildirimler: await bildirimHatalari(p), metin_uzunlugu: o.metin.length, cocuk: o.cocuk,
        kotu_metin: ['undefined', 'NaN', '[object', 'ReferenceError'].filter(t => o.metin.includes(t)) };
      if (id === 'Anasayfa') sonuc.ana_metin = o.metin;
      if (id === 'Harita') { sonuc.harita_metin = o.metin; }
      if (id === 'Zaman çizelgesi' || id === 'Arama' || id === 'Persona') sonuc.sayfalar[id].metin = o.metin;
      if (id === 'Hakkında') sonuc.sayfalar[id].metin = o.metin;
    }
    // Harita: "Bu harita nedir?" kutusu görünür mü
    await git(p, 'Harita');
    sonuc.harita_nedir = await p.evaluate(() => { const d = document.querySelector('details.nedir'); return d ? { acik: d.open, metin: d.innerText } : null; });
    // "?" ipuçları: açılıyor mu
    await git(p, 'Ana sayfa');
    const ip = p.locator('.terim-i').first();
    if (await ip.count()) { await ip.hover(); await bekle(200); sonuc.ipucu_metni = await p.evaluate(() => { const k = document.querySelector('.terim-kutu'); return k ? k.innerText : null; }); }
    sonuc.konsol_hatalari = hatalar.slice();
    await c.close(); }

  // ---- içe aktar akışı (sahte dosyalarla, arayüzden)
  { const c = await b.newContext({ viewport: { width: 1280, height: 850 } }), p = await c.newPage(); await toplayici(p);
    await p.goto(ayar.url); await bekle(1200);
    for (const [ad, yol] of Object.entries(ayar.ice_dosyalari)) {
      await git(p, 'İçe aktar');
      if (!(await p.$('#ice-yol'))) { sonuc.ice[ad] = { bitti: false, metin: null, kutu_yok: true, bildirimler: await bildirimHatalari(p) }; continue; }
      await p.fill('#ice-yol', yol);
      await p.locator('button', { hasText: 'İçe aktarmayı başlat' }).click();
      const bitti = await p.waitForSelector('#ana .hata, #ana h3.tamam', { timeout: 30000 }).then(() => true).catch(() => false);
      sonuc.ice[ad] = { bitti, metin: bitti ? await p.evaluate(() => (document.querySelector('#ana .hata') || document.querySelector('#ana h3.tamam').closest('.kart')).innerText) : null,
        bildirimler: await bildirimHatalari(p) };
    }
    await c.close(); }

  // ---- dosya denetimi (tanila): düğme, rapor, kopyalama, temizleme
  { const c = await b.newContext({ viewport: { width: 1280, height: 850 }, permissions: ['clipboard-read', 'clipboard-write'] }), p = await c.newPage(); await toplayici(p);
    await p.goto(ayar.url); await bekle(1200);
    await git(p, 'İçe aktar');
    const t = { bildirimler: [] };
    t.dugme_var = (await p.locator('#tanila-dugme', { hasText: 'Dosyayı denetle (içerik göstermez)' }).count()) === 1;
    const kayitOnce = await p.evaluate(async () => (await api('durum')).ozet.counts.event || 0);
    await p.locator('#tanila-dugme').click();                      // yol boşken
    await bekle(500);
    t.bos_yol_hatasi = (await bildirimHatalari(p)).length > 0;
    await p.fill('#ice-yol', ayar.tanila_dosyasi);
    await p.locator('#tanila-dugme').click();
    t.rapor_var = await p.waitForSelector('#tanila-rapor', { timeout: 30000 }).then(() => true).catch(() => false);
    if (t.rapor_var) {
      t.aciklama_var = (await p.evaluate(() => document.querySelector('#tanila-alan').innerText)).includes('Bu rapor dosya içeriğini içermez, yalnız alan adları, türler ve sayılar.');
      t.rapor = await p.inputValue('#tanila-rapor');
      await p.locator('#tanila-kopyala').click(); await bekle(400);
      t.panoda = await p.evaluate(() => navigator.clipboard.readText()).catch(() => null);
      t.eklenen_kayit = (await p.evaluate(async () => (await api('durum')).ozet.counts.event || 0)) - kayitOnce;
      await p.locator('#tanila-temizle').click(); await bekle(400);
      t.temizlendi = (await p.locator('#tanila-rapor').count()) === 0 && (await p.evaluate(() => api('tanila_durum'))).durum === 'yok';
    }
    t.bildirimler = await bildirimHatalari(p);
    sonuc.tanila = t;
    await c.close(); }

  // ---- mobil 390px
  { const c = await b.newContext({ viewport: { width: 390, height: 844 } }), p = await c.newPage(); await toplayici(p);
    await p.goto(ayar.url); await bekle(1200);
    for (const [id, ad] of SAYFALAR) { await git(p, ad); sonuc.mobil[id] = await p.evaluate(tasma); await bildirimHatalari(p); }
    // radar etiketleri kırpılmış mı: tuvalin kenar sütunları boş olmalı
    await git(p, 'Harita');
    sonuc.mobil_radar = await p.evaluate(() => {
      const cv = document.querySelector('.cgraf.radar canvas'); if (!cv) return { yok: true };
      const g = cv.getContext('2d'), w = cv.width, h = cv.height, dolu = (x) => g.getImageData(x, 0, 1, h).data.some((v, i) => i % 4 === 3 && v > 0);
      return { genislik: w, sol_kenar_dolu: dolu(0) || dolu(1), sag_kenar_dolu: dolu(w - 1) || dolu(w - 2) };
    });
    await c.close(); }

  // ---- tema: varsayılan koyu; "Sistem" seçilince tarayıcı tercihine uyar
  for (const [ad, tercih, tema] of [['varsayilan_acik_tercih', 'light', null], ['sistem_acik_tercih', 'light', 'sistem'], ['sistem_koyu_tercih', 'dark', 'sistem'], ['acik_secili', 'dark', 'acik']]) {
    const c = await b.newContext({ viewport: { width: 1000, height: 700 }, colorScheme: tercih }), p = await c.newPage();
    await p.goto(ayar.url); await bekle(800);
    if (tema) { await p.evaluate(async t => { await api('ayar_yaz', { tema: t }); temaUygula(t); }, tema); await bekle(300); }
    sonuc.tema[ad] = await p.evaluate(() => { const m = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim(); const k = m.replace('#', ''); const n = parseInt(k.length === 3 ? k.split('').map(x => x + x).join('') : k, 16); const l = ((n >> 16) * 0.299 + ((n >> 8) & 255) * 0.587 + (n & 255) * 0.114); return { bg: m, parlaklik: Math.round(l), data_tema: document.documentElement.dataset.tema }; });
    await p.evaluate(async () => { await api('ayar_yaz', { tema: 'koyu' }); });
    await c.close();
  }
  return sonuc;
}
(async () => {
  let b;
  try { b = await chromium.launch(); } catch (e) { process.stderr.write('chromium açılamadı: ' + e.message + '\n'); process.exit(77); }
  try { process.stdout.write(JSON.stringify(await sonuclariTopla(b)) + '\n'); } finally { await b.close(); }
})().catch(e => { process.stderr.write(String(e && e.stack || e) + '\n'); process.exit(1); });
