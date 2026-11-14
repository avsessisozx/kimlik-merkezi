// İçe aktar ekranı: "Bilgisayarımdaki dosyalar ve klasörler" akışı (Playwright + Chromium).
// Kullanım: node dosya_ice.js <ayar.json>   Çıktı: stdout'un son satırı JSON. Çıkış 77: Playwright/Chromium yok.
"use strict";
const fs = require('fs');
let chromium;
try { ({ chromium } = require('playwright')); } catch (e) { process.stderr.write('playwright yok: ' + e.message + '\n'); process.exit(77); }
const ayar = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const bekle = ms => new Promise(r => setTimeout(r, ms));
const hatalar = [];
async function bildirimHatalari(p) {
  return p.evaluate(() => [...document.querySelectorAll('#bildirim div.h')].map(d => d.firstChild ? d.firstChild.textContent : d.textContent));
}
async function ice(p) {
  await p.locator('nav button', { hasText: /^İçe aktar$/ }).click();
  await p.waitForSelector('#dosya-karti', { timeout: 15000 });
}
const metin = (p, sel) => p.evaluate(s => { const e = document.querySelector(s); return e ? e.innerText : null; }, sel);

(async () => {
  const b = await chromium.launch().catch(e => { process.stderr.write('chromium yok: ' + e.message + '\n'); process.exit(77); });
  const sonuc = {};
  try {
    const c = await b.newContext({ viewport: { width: 1280, height: 900 } }), p = await c.newPage();
    p.on('pageerror', e => hatalar.push('pageerror: ' + e)); p.on('console', m => { if (m.type() === 'error') hatalar.push('console: ' + m.text()); });
    await p.goto(ayar.url); await bekle(1200);
    await ice(p);
    sonuc.baslik = await metin(p, '#dosya-karti h3');
    sonuc.baslangic_secim = await metin(p, '#dosya-secim');

    // 1) Klasör seç -> başlat -> bitiş özeti (computer_files AÇIKÇA seçilir; tür kutusu 'Otomatik' kalır)
    await p.click('#dosya-klasor-sec');
    await p.waitForFunction(() => !document.querySelector('#dosya-secim').innerText.startsWith('Henüz'), null, { timeout: 8000 });
    sonuc.klasor_secim = await metin(p, '#dosya-secim');
    sonuc.tur_kutusu = await p.evaluate(() => document.querySelector('#ana select').value);
    await p.click('#dosya-baslat');
    await p.waitForSelector('#dosya-ozeti', { timeout: 60000 });
    sonuc.ozet_metin = await metin(p, '#dosya-ozet-metin');
    sonuc.metinsiz = await metin(p, '#dosya-metinsiz');
    sonuc.ozeti_kart = await metin(p, '#dosya-ozeti');
    await p.evaluate(() => document.querySelectorAll('#dosya-ozeti details').forEach(d => d.open = true));
    sonuc.ayrintilar = await metin(p, '#dosya-ozeti');
    sonuc.bildirim1 = await bildirimHatalari(p);

    // 2) Birden çok dosya seç (sahte seçici satır satır yol döner)
    await p.click('#dosya-dosyalar-sec');
    await p.waitForFunction(() => document.querySelector('#dosya-secim').innerText.includes('öğe seçildi'), null, { timeout: 8000 });
    sonuc.cok_secim = await metin(p, '#dosya-secim');
    await p.click('#dosya-baslat');
    await p.waitForFunction(() => /Tamamlandı|bozuk\/okunamadığı/.test(document.querySelector('#ana').innerText), null, { timeout: 60000 });
    await bekle(800);
    sonuc.cok_ozet = await metin(p, '#dosya-ozet-metin');

    // 3) İlerleme çizimi: sunucu yanıtı taklit edilir (gerçek içe aktarma çok hızlı biter)
    await p.route('**/api/ice_aktar_durum', r => r.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ durum: 'calisiyor', asama: 'isle', sayi: 3, yol: 'x', dosya_islenen: 3, dosya_toplam: 12 }) }));
    await p.reload(); await bekle(1200); await ice(p);
    await p.waitForSelector('#ice-ilerleme', { timeout: 8000 });
    sonuc.ilerleme_metin = await metin(p, '#ice-ilerleme');
    sonuc.ilerleme_cubuk = await p.evaluate(() => { const e = document.querySelector('#ana progress'); return e ? [e.value, e.max] : null; });
    await p.unroute('**/api/ice_aktar_durum');

    // 4) Dosya seçme penceresi çağrıları ve mobil taşma
    await c.close();
    const m = await b.newContext({ viewport: { width: 390, height: 800 } }), q = await m.newPage();
    await q.goto(ayar.url); await bekle(1200); await ice(q);
    sonuc.mobil_tasma = await q.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    sonuc.konsol_hatalari = hatalar.slice();
  } finally { await b.close(); }
  console.log(JSON.stringify(sonuc));
})().catch(e => { process.stderr.write(String(e && e.stack || e) + '\n'); process.exit(1); });
