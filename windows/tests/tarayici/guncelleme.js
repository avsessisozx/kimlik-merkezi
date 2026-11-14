// Gerçek tarayıcıda (Playwright + Chromium) güncelleme arayüzü: sihirbazdaki açık bilgilendirme, Ayarlar kartı,
// "yeni sürüm var, indirmek ister misin?", onaysız indirmeme, ilerleme çubuğu, duraklat/devam (Range), iptal,
// hash uyuşmazlığı, ikinci onay ("şimdi kurmak ister misin?"). test_guncelleme_tarayici.py tarafından çalıştırılır.
// Kullanım: node guncelleme.js <ayar.json>   Çıktı: stdout'a tek satır JSON. Çıkış 77: Playwright/Chromium yok.
"use strict";
const fs = require('fs');
let chromium;
try { ({ chromium } = require('playwright')); } catch (e) { process.stderr.write('playwright yok: ' + e.message + '\n'); process.exit(77); }
const ayar = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const bekle = ms => new Promise(r => setTimeout(r, ms));
const sahte = (yol) => fetch(ayar.sahte + yol).then(r => r.json());
const SN = 20000;

async function metin(p, sec) { return p.evaluate(s => { const e = document.querySelector(s); return e ? e.innerText : null; }, sec); }
async function yok(p, sec) { return (await p.locator(sec).count()) === 0; }

(async () => {
  let b;
  try { b = await chromium.launch(); } catch (e) { process.stderr.write('chromium açılamadı: ' + e.message + '\n'); process.exit(77); }
  const sonuc = { hatalar: [] };
  try {
    if (ayar.mod === 'bilgi') {      // eski sürümden gelen kurulum: otomatik denetimden önce tek seferlik bilgilendirme
      const c = await b.newContext({ viewport: { width: 1280, height: 850 } }), p = await c.newPage();
      p.on('pageerror', e => sonuc.hatalar.push('pageerror: ' + e));
      p.on('console', m => { if (m.type() === 'error') sonuc.hatalar.push('console: ' + m.text()); });
      await p.goto(ayar.url);
      await p.waitForSelector('#gunc-bilgi-acik', { timeout: SN });
      sonuc.bilgi = { metin: await metin(p, '#kok-pencere') };
      sonuc.bilgi.sayac_once = await sahte('/_sayac');
      await p.click(ayar.secim === 'kapat' ? '#gunc-bilgi-kapali' : '#gunc-bilgi-acik');
      await bekle(1500);
      sonuc.bilgi.pencere_kapandi = await yok(p, '#gunc-bilgi-acik');
      sonuc.bilgi.ayar = (await p.evaluate(() => api('ayarlar'))).guncelleme_otomatik;
      sonuc.bilgi.sayac_sonra = await sahte('/_sayac');
      await c.close();
      process.stdout.write(JSON.stringify(sonuc) + '\n');
      return;
    }
    const c = await b.newContext({ viewport: { width: 1280, height: 850 } }), p = await c.newPage();
    p.on('pageerror', e => sonuc.hatalar.push('pageerror: ' + e));
    p.on('console', m => { if (m.type() === 'error') sonuc.hatalar.push('console: ' + m.text()); });
    const bildirimHatalari = () => p.evaluate(() => [...document.querySelectorAll('#bildirim div.h')].map(d => d.innerText));

    // ---- 1) ilk açılış sihirbazı: açılışta denetim AÇIK ve açıkça yazılı
    await p.goto(ayar.url);
    await p.waitForSelector('#kok-pencere input[type=text]', { timeout: SN });
    const girdiler = p.locator('#kok-pencere input[type=text]');
    await girdiler.nth(1).fill(ayar.veri);
    await p.waitForSelector('#kok-pencere button:has-text("İleri"):not([disabled])', { timeout: SN });
    await p.locator('#kok-pencere button:has-text("İleri")').click();
    await p.waitForSelector('#sihirbaz-gunc', { timeout: SN });
    sonuc.sihirbaz = { isaretli: await p.isChecked('#sihirbaz-gunc'), metin: await metin(p, '#kok-pencere') };
    await p.locator('#kok-pencere button:has-text("Kur")').click();
    await p.waitForSelector('#sihirbaz-gunc-ozet', { timeout: SN });
    sonuc.sihirbaz.ozet = await metin(p, '#sihirbaz-gunc-ozet');
    await p.locator('#kok-pencere button:has-text("Başla")').click();
    await p.waitForSelector('nav button', { timeout: SN });
    await bekle(800);
    sonuc.sihirbaz.sonra_kutu_bos = await yok(p, '.guncelleme');       // sihirbaz bitince kendiliğinden denetim/indirme yok

    // ---- 2) Ayarlar kartı
    await p.locator('nav button', { hasText: /^Ayarlar$/ }).click();
    await p.waitForSelector('#ayar-guncelleme', { timeout: SN });
    sonuc.ayar = { kart: await metin(p, '#ayar-guncelleme'), otomatik: await p.isChecked('#ayar-gunc-otomatik'), onsurum: await p.isChecked('#ayar-gunc-onsurum') };
    await p.uncheck('#ayar-gunc-otomatik'); await bekle(500);
    sonuc.ayar.kapatilinca = (await p.evaluate(() => api('ayarlar'))).guncelleme_otomatik;
    await p.check('#ayar-gunc-otomatik'); await bekle(500);
    sonuc.ayar.acilinca = (await p.evaluate(() => api('ayarlar'))).guncelleme_otomatik;
    sonuc.once = await sahte('/_sayac');                              // şimdiye dek GitHub'a (sahteye) hiç istek gitmedi

    // ---- 3) denetle düğmesi: soru çıkar, ama ONAYSIZ hiçbir şey indirilmez
    await p.click('#ayar-gunc-denetle');
    await p.waitForSelector('#gunc-baslik', { timeout: SN });
    sonuc.soru = { baslik: await metin(p, '#gunc-baslik'), kutu: await metin(p, '.guncelleme'), indir_var: !(await yok(p, '#gunc-indir')) };
    await bekle(1500);
    sonuc.soru.sayac = await sahte('/_sayac');
    await p.click('#gunc-simdi-degil');
    sonuc.soru.gizlendi = await yok(p, '.guncelleme');
    await p.click('#ayar-gunc-denetle');
    await p.waitForSelector('#gunc-indir', { timeout: SN });

    // ---- 4) hash uyuşmazlığı: hata gösterilir, dosya silinir
    await sahte('/_ayar/bozuk_ozet/1');
    await p.click('#gunc-indir');
    await p.waitForSelector('#gunc-hata', { timeout: SN });
    sonuc.hash = { baslik: await metin(p, '#gunc-baslik'), hata: await metin(p, '#gunc-hata'), kur_var: !(await yok(p, '#gunc-kur')) };
    await sahte('/_ayar/bozuk_ozet/0');

    // ---- 5) iptal: yarım dosya silinir, soru yeniden gelir
    await sahte('/_ayar/kapi_esigi/1048576');
    await p.click('#gunc-yeniden');
    await p.waitForFunction(() => { const e = document.querySelector('#gunc-ilerleme'); return e && Number(e.value) > 5; }, null, { timeout: SN });
    sonuc.ilerleme = { metin: await metin(p, '#gunc-metin'), deger: await p.evaluate(() => Number(document.querySelector('#gunc-ilerleme').value)),
      duraklat_var: !(await yok(p, '#gunc-duraklat')), iptal_var: !(await yok(p, '#gunc-iptal')) };
    await p.click('#gunc-iptal');
    await p.waitForSelector('#gunc-indir', { timeout: SN });
    sonuc.iptal = { kutu: await metin(p, '.guncelleme'), ilerleme_yok: await yok(p, '#gunc-ilerleme') };

    // ---- 6) duraklat / devam (HTTP Range)
    await p.click('#gunc-indir');
    await p.waitForFunction(() => { const e = document.querySelector('#gunc-ilerleme'); return e && Number(e.value) > 5; }, null, { timeout: SN });
    await p.click('#gunc-duraklat');
    await p.waitForSelector('#gunc-devam', { timeout: SN });
    const v1 = await p.evaluate(() => Number(document.querySelector('#gunc-ilerleme').value));
    await bekle(1500);
    sonuc.duraklat = { metin: await metin(p, '#gunc-metin'), v1, v2: await p.evaluate(() => Number(document.querySelector('#gunc-ilerleme').value)) };
    await sahte('/_kapi/ac');
    await p.click('#gunc-devam');
    await p.waitForSelector('#gunc-kur', { timeout: SN });
    sonuc.devam = { sayac: await sahte('/_sayac'), kutu: await metin(p, '.guncelleme') };

    // ---- 7) ikinci onay: "Sonra" kurmaz; mobilde taşma yok; "Şimdi kur" ancak o zaman
    await p.click('#gunc-sonra');
    sonuc.sonra_gizlendi = await yok(p, '.guncelleme');
    await p.click('#ayar-gunc-denetle');           // yeniden denetim: hazır dosya varken durum korunur, kutu geri gelir
    await p.waitForSelector('#gunc-kur', { timeout: SN });
    await p.setViewportSize({ width: 390, height: 844 });
    await bekle(300);
    sonuc.mobil = await p.evaluate(() => ({ tasma: document.documentElement.scrollWidth - innerWidth }));
    await p.setViewportSize({ width: 1280, height: 850 });
    await p.click('#gunc-kur');
    await p.waitForFunction(() => { const e = document.querySelector('#gunc-baslik'); return e && e.innerText.includes('Kurulum başlatılıyor'); }, null, { timeout: SN });
    sonuc.kur = { baslik: await metin(p, '#gunc-baslik') };
    sonuc.bildirim_hatalari = await bildirimHatalari();
    await c.close();
  } finally { await b.close(); }
  process.stdout.write(JSON.stringify(sonuc) + '\n');
})().catch(e => { process.stderr.write(String(e && e.stack || e) + '\n'); process.exit(1); });
