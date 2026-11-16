// Gerçek tarayıcıda (Playwright + Chromium): "Claude'a ekle" sonrası izin ekranı ve "Yeni anahtar" akışı (önerilenler işaretli,
// boş kayıtta uyarı, "Hiç izni yok" etiketi). test_tarayici_erisim.py tarafından çalıştırılır.
// Kullanım: node erisim_izin.js <ayar.json>   Çıktı: stdout'a tek satır JSON. Çıkış 77: Playwright/Chromium yok.
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
const isaretliler = p => p.evaluate(() => [...document.querySelectorAll('#izin-ekrani input[data-kat]')].filter(c => c.checked).map(c => c.dataset.kat).sort());
const hepsi = p => p.evaluate(() => [...document.querySelectorAll('#izin-ekrani input[data-kat]')].map(c => c.dataset.kat).sort());

(async () => {
  let b;
  try { b = await chromium.launch(); } catch (e) { process.stderr.write('chromium açılamadı: ' + e.message + '\n'); process.exit(77); }
  const sonuc = { hatalar: [], diyaloglar: [] };
  try {
    const c = await b.newContext({ viewport: { width: 1280, height: 1000 } }), p = await c.newPage();
    p.on('pageerror', e => sonuc.hatalar.push('pageerror: ' + e));
    p.on('console', m => { if (m.type() === 'error') sonuc.hatalar.push('console: ' + m.text()); });
    let kabul = true;
    p.on('dialog', d => { sonuc.diyaloglar.push(d.message()); (kabul ? d.accept() : d.dismiss()); });
    await p.goto(ayar.url); await bekle(1200);
    await p.locator('nav button', { hasText: /^Erişim$/ }).click();
    await p.waitForSelector('text=Claude Desktop\'a ekle', { timeout: 15000 });

    // ---- Claude'a ekle -> doğrudan izin ekranı
    await p.getByRole('button', { name: "Claude'a ekle" }).click();
    await p.waitForSelector('#izin-ekrani', { timeout: 15000 });
    sonuc.claude = { metin: await metin(p, '#izin-ekrani'), acik: await isaretliler(p), hepsi: await hepsi(p) };
    sonuc.claude.api = await p.evaluate(async () => (await api('erisim')).uygulamalar.filter(u => u.ad === 'Claude Desktop' && !u.iptal).map(u => u.izinler.map(i => i.kategori).sort()));
    await p.click('#izin-kapat'); await bekle(600);
    sonuc.claude.kapandi = (await p.locator('#izin-ekrani').count()) === 0;

    // ---- Yeni anahtar -> izin ekranı, önerilenler işaretli, Kaydet demeden hiçbir şey verilmez
    await p.fill('input[placeholder^="Uygulama adı"]', 'Deneme uygulaması');
    await p.getByRole('button', { name: 'Anahtar üret' }).click();
    await p.waitForSelector('#anahtar-tamam', { timeout: 15000 });
    await p.click('#anahtar-tamam');
    await p.waitForSelector('#izin-ekrani', { timeout: 15000 });
    sonuc.yeni = { metin: await metin(p, '#izin-ekrani'), secili: await isaretliler(p), hepsi: await hepsi(p) };
    sonuc.yeni.api_kaydetmeden = await p.evaluate(async () => (await api('erisim')).uygulamalar.find(u => u.ad === 'Deneme uygulaması'));
    sonuc.yeni.liste_etiketi = (await p.locator('.izinsiz-etiket').allInnerTexts());

    // hepsini kaldır -> Kaydet -> uyarı (önce vazgeç, sonra onayla)
    for (const k of sonuc.yeni.secili) { await p.locator(`#izin-ekrani input[data-kat="${k}"]`).uncheck(); await bekle(300); }
    sonuc.yeni.bos_secili = await isaretliler(p);
    sonuc.diyaloglar.length = 0;
    kabul = false;
    await p.click('#izin-kaydet'); await bekle(600);
    sonuc.uyari_vazgec = { diyalog: [...sonuc.diyaloglar], ekran_acik: (await p.locator('#izin-ekrani').count()) === 1 };
    kabul = true; sonuc.diyaloglar.length = 0;
    await p.click('#izin-kaydet'); await bekle(800);
    sonuc.uyari_onay = { diyalog: [...sonuc.diyaloglar], ekran_kapandi: (await p.locator('#izin-ekrani').count()) === 0,
      etiket: await p.locator('.izinsiz-etiket').allInnerTexts() };

    // ikinci anahtar: varsayılan öneriyle Kaydet
    await p.fill('input[placeholder^="Uygulama adı"]', 'Onerili');
    await p.getByRole('button', { name: 'Anahtar üret' }).click();
    await p.waitForSelector('#anahtar-tamam', { timeout: 15000 });
    await p.click('#anahtar-tamam');
    await p.waitForSelector('#izin-ekrani', { timeout: 15000 });
    sonuc.diyaloglar.length = 0;
    await p.click('#izin-kaydet'); await bekle(1000);
    sonuc.onerili = { diyalog: [...sonuc.diyaloglar], api: await p.evaluate(async () => (await api('erisim')).uygulamalar.find(u => u.ad === 'Onerili').izinler.map(i => i.kategori).sort()) };

    // üçüncü: "Kaydetmeden kapat" izinsiz kalırsa uyarı
    await p.fill('input[placeholder^="Uygulama adı"]', 'Kapatilan');
    await p.getByRole('button', { name: 'Anahtar üret' }).click();
    await p.waitForSelector('#anahtar-tamam', { timeout: 15000 });
    await p.click('#anahtar-tamam');
    await p.waitForSelector('#izin-ekrani', { timeout: 15000 });
    sonuc.diyaloglar.length = 0; kabul = false;
    await p.click('#izin-kapat'); await bekle(600);
    sonuc.kapat_uyari = { diyalog: [...sonuc.diyaloglar], ekran_acik: (await p.locator('#izin-ekrani').count()) === 1 };
    sonuc.bildirim_hatalari = await p.evaluate(() => [...document.querySelectorAll('#bildirim div.h')].map(d => d.textContent));
    await c.close();
    process.stdout.write(JSON.stringify(sonuc) + '\n');
  } finally { await b.close(); }
})().catch(e => { process.stderr.write('HATA: ' + (e && e.stack || e) + '\n'); process.exit(1); });
