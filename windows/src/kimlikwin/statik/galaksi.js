/* Galaksi: arşivin yaşayan yıldız haritası (v0.3.0). Her kayıt bir yıldız, her kaynak bir küme.
   - Veri: api('galaksi') (veriden sayım; yorum yok). Çizim: tek <canvas>, insan figürü yok.
   - Yıl çubuğu: arşivi o yıla kadar gösterir. Kümeye tıkla -> panel; "İçine gir" -> alt konular (kayıt türleri).
   - Hâl katmanı: renk, hız, dağılım ve düzen (ızgara/akış) hâle göre değişir. Kullanıcının seçimi HER ZAMAN
     otomatik tahminden üstündür; tahmin açıkça "tahmin" diye etiketlenir ve gerekçesi yazılır.
   Kayıt metinleri güvenilmez veri: yalnız textContent ile eklenir. Ortak adlar (SAYI, TR_DILIM) ortak.js'ten. */
"use strict";
const GAL_PALET = ['#F6A596', '#F7D08A', '#7FD8C6', '#C9B6F2', '#9CC3F5', '#E8DCC0'];
const GAL_RENK = { 'Meta': '#F08B78', 'ChatGPT': '#5CCBB6', 'Claude': '#E8A87C', 'Gemini': '#8FB4F5', 'DeepSeek': '#7EA6E0',
  'Telefon': '#F5C268', 'Bilgisayar': '#B7A0EE', 'Google': '#9CC3F5', 'YouTube': '#F07C7C', 'Spotify': '#7FD89A', 'Reddit': '#F2A065' };
const GAL_KONUM = [[.38, .5], [.78, .22], [.7, .78], [.95, .55], [.1, .8], [.12, .2], [.5, .1], [.4, .95], [.9, .95], [.02, .5]];
const GAL_W = 900, GAL_H = 620;   // dünya birimi: tuval bunu `sc` ile ölçekler; böylece düzen her boyutta aynı kalır
const GAL_ANAHTAR = 'kimlik.hal';
// Hâller: ton (renk kayması, derece), hiz (hareket çarpanı), yayilim (kümenin dağılımı), izgara (0=serbest, 1=ızgara),
// akis (0=durgun, 1=akan dalgalar), parlak (genel parlaklık). Matematik/odak = ızgara, sözel/yaratıcı = akış.
const GAL_HALLER = {
  sakin:   { ad: 'Sakin',   ton: 0,   hiz: .45, yayilim: .85, izgara: 0,  akis: .15, parlak: .9 },
  enerjik: { ad: 'Enerjik', ton: 25,  hiz: 1.8, yayilim: 1.25, izgara: 0, akis: .35, parlak: 1.1 },
  odak:    { ad: 'Odak',    ton: -20, hiz: .7,  yayilim: .75, izgara: 1,  akis: 0,   parlak: 1 },
  akis:    { ad: 'Akış',    ton: 40,  hiz: 1,   yayilim: 1.1, izgara: 0,  akis: 1,   parlak: 1 },
  yorgun:  { ad: 'Yorgun',  ton: 55,  hiz: .25, yayilim: .7,  izgara: 0,  akis: .05, parlak: .6 },
};
const GAL_VARSAYILAN_HAL = { ton: 0, hiz: 1, yayilim: 1, izgara: 0, akis: .2, parlak: 1 };

function galHash(i, tuz) { let a = (i * 2654435761 + (tuz || 0) * 40503) | 0; a = Math.imul(a ^ (a >>> 15), 2246822507); a = Math.imul(a ^ (a >>> 13), 3266489909); return ((a ^ (a >>> 16)) >>> 0) / 4294967296; }
function galGauss(i, tuz) { const u1 = Math.max(galHash(i, tuz), 1e-6), u2 = galHash(i, tuz + 7); const m = Math.sqrt(-2 * Math.log(u1)); return [m * Math.cos(2 * Math.PI * u2), m * Math.sin(2 * Math.PI * u2)]; }
function galRenkKaydir(hex, derece, parlak) {
  const n = parseInt(hex.slice(1), 16); let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  r /= 255; g /= 255; b /= 255; const mx = Math.max(r, g, b), mn = Math.min(r, g, b); let hh = 0, s = 0; const l = (mx + mn) / 2;
  if (mx !== mn) { const d = mx - mn; s = l > .5 ? d / (2 - mx - mn) : d / (mx + mn);
    hh = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; hh *= 60; }
  return `hsl(${Math.round((hh + derece + 360) % 360)} ${Math.round(s * 100)}% ${Math.round(Math.min(92, l * 100 * parlak))}%)`;
}
function galTurAdi(kind) { const p = String(kind).split('.'); const a = p[0].charAt(0).toUpperCase() + p[0].slice(1); return p.length > 1 ? `${a} · ${p.slice(1).join(' ').replace(/_/g, ' ')}` : a; }
function galIkiHane(n) { return String(n).padStart(2, '0'); }

const GALAKSI = {
  durum: null,
  ekran: async function (a) {
    GALAKSI.durdur();
    const veri = await api('galaksi');
    const S = GALAKSI.durum = { veri, secili: null, icinde: null, tur: null, hover: null, kayitSayfa: 0,
      yilMin: 0, yilMax: 0, yil: 0, oynuyor: false, hal: { ...GAL_VARSAYILAN_HAL }, halSecim: null, halOtomatik: null,
      cam: { x: GAL_W / 2, y: GAL_H / 2, s: 1 }, camHedef: { x: GAL_W / 2, y: GAL_H / 2, s: 1 }, sc: 1, w: 0, h: 0, zaman: 0, raf: 0, dur: false };
    const y = veri.yillar ? Object.keys(veri.yillar).map(Number).sort((p, q) => p - q) : [];
    S.yilMin = y.length ? y[0] : new Date().getFullYear(); S.yilMax = y.length ? y[y.length - 1] : S.yilMin; S.yil = S.yilMax;
    try { const k = JSON.parse(localStorage.getItem(GAL_ANAHTAR) || 'null'); if (k && GAL_HALLER[k.secim]) S.halSecim = k.secim; } catch (_) { /* depolama yok: sorun değil */ }
    GALAKSI.hazirla(S);
    if (!veri.toplam) { a.append(h('h2', {}, 'Galaksi'), h('div', { class: 'kart bos-kutu' }, h('h3', {}, 'Henüz veri yok'),
      h('p', {}, 'İçe aktardığınız ya da telefondan gelen kayıtlar burada yıldız olarak görünür.'), h('button', { class: 'd', onclick: () => git('ice') }, 'İçe aktar\'a git'))); return; }
    GALAKSI.kur(a, S);
  },
  // Kümeleri birbirine ve etiketlerine çarpmayacak şekilde yerleştirir (başlık ve alt çubuk için kenar boşluğu bırakır).
  yerlestir(kumeler) {
    const n = kumeler.length;
    kumeler.forEach((k, i) => { const [fx, fy] = i < GAL_KONUM.length ? GAL_KONUM[i] : [galHash(i, 3), galHash(i, 5)]; k.cx = 70 + fx * (GAL_W - 140); k.cy = 150 + fy * (GAL_H - 300); });
    for (let it = 0; it < 500; it++) {
      let oldu = false;
      for (let a = 0; a < n; a++) for (let b = a + 1; b < n; b++) {
        const A = kumeler[a], B = kumeler[b]; let dx = B.cx - A.cx, dy = B.cy - A.cy; const d = Math.hypot(dx, dy) || .01, min = (A.r + B.r) * .95 + 36;
        if (d < min) { const p = (min - d) / 2; dx /= d; dy /= d; A.cx -= dx * p; A.cy -= dy * p; B.cx += dx * p; B.cy += dy * p; oldu = true; }
      }
      kumeler.forEach(k => { k.cx = Math.max(60 + k.r * .6, Math.min(GAL_W - 60 - k.r * .6, k.cx)); k.cy = Math.max(130 + k.r * .5, Math.min(GAL_H - 140 - k.r * .5, k.cy)); });
      if (!oldu) break;
    }
  },
  hazirla(S) {
    const v = S.veri, n = v.yildizlar.t.length, maxN = Math.max(1, ...v.gruplar.map(g => g.sayi));
    const kucult = Math.min(1, Math.pow(6 / Math.max(1, v.gruplar.length), .6));   // çok kaynak varsa kümeler küçülür
    S.kumeler = v.gruplar.map((g, i) => ({ ...g, i, cx: 0, cy: 0, r: Math.round((26 + 130 * Math.sqrt(g.sayi / maxN)) * kucult), renk: GAL_RENK[g.ad] || GAL_PALET[i % GAL_PALET.length], yildiz: 0 }));
    GALAKSI.yerlestir(S.kumeler);
    // Her yıldız için: kümesi, ham konumu (birim gauss), zaman, faz, kendi türü; tür başına alt küme sırası
    S.ys = new Array(n);
    const turSay = {};
    for (let i = 0; i < n; i++) {
      const g = v.yildizlar.g[i], k = v.yildizlar.k[i], [gx, gy] = galGauss(i, 11);
      S.ys[i] = { g, k, t: v.yildizlar.t[i], gx, gy, faz: galHash(i, 19) * 6.283, boy: 1.4 + galHash(i, 23) * 2.4, o: .45 + galHash(i, 29) * .5, sira: 0 };
      S.kumeler[g].yildiz++; (turSay[g] = turSay[g] || {})[k] = (turSay[g][k] || 0) + 1;
    }
    // alt kümeler: her küme için en kalabalık 6 tür (+ "Diğer"), sırayla çember üzerine
    S.alt = S.kumeler.map((km, g) => {
      const sirali = Object.entries(turSay[g] || {}).sort((p, q) => q[1] - p[1]);
      const ilk = sirali.slice(0, 6).map(([k, c]) => ({ k: +k, ad: galTurAdi(v.turler[+k]), tur: v.turler[+k], sayi: c }));
      const kalan = sirali.slice(6).reduce((s, [, c]) => s + c, 0);
      if (kalan) ilk.push({ k: -1, ad: 'Diğer türler', tur: null, sayi: kalan });
      ilk.forEach((u, j) => { const aci = (j / Math.max(1, ilk.length)) * 6.283 - 1.2; u.ax = Math.cos(aci) * km.r * .62; u.ay = Math.sin(aci) * km.r * .62; u.renk = GAL_PALET[j % GAL_PALET.length]; });
      return ilk;
    });
    // yıldızların alt küme indeksi ve kümedeki sırası (ızgara düzeni için)
    const say = S.kumeler.map(() => 0);
    S.ys.forEach(s => { const al = S.alt[s.g]; const j = al.findIndex(u => u.k === s.k); s.alt = j >= 0 ? j : al.length - 1; s.sira = say[s.g]++; });
    S.halOtomatik = GALAKSI.tahmin(S);
  },
  // Otomatik hâl tahmini: yalnız kayıt zamanlarından (son 14 gün): gece payı, hız, çeşitlilik. Gerekçe kullanıcıya yazılır.
  tahmin(S) {
    const t = S.veri.yildizlar.t; if (!t.length) return null;
    const simdi = Date.now() / 1000, son = simdi - 14 * 86400; let n = 0, gece = 0;
    for (let i = t.length - 1; i >= 0 && t[i] >= son; i--) { n++; const sa = (new Date(t[i] * 1000).getUTCHours() + 3) % 24; if (sa >= 23 || sa < 5) gece++; }
    if (n < 8) return { id: 'sakin', neden: `Son 14 günde az kayıt var (${n}); ortam sakin gösterilir.` };
    const gunluk = n / 14, toplamGun = Math.max(1, (t[t.length - 1] - t[0]) / 86400), ort = t.length / toplamGun;
    if (gece / n > .35) return { id: 'yorgun', neden: `Son 14 günde kayıtların %${Math.round(100 * gece / n)}'i gece (23:00–05:00).` };
    if (gunluk > ort * 1.8) return { id: 'enerjik', neden: `Son 14 günde günlük kayıt hızı genel ortalamanın ${(gunluk / ort).toFixed(1).replace('.', ',')} katı.` };
    if (gunluk < ort * .4) return { id: 'sakin', neden: 'Son 14 günde kayıt hızı genel ortalamanın altında.' };
    return { id: 'akis', neden: 'Son 14 günde kayıt hızı genel ortalama düzeyinde.' };
  },
  halId(S) { return S.halSecim || (S.halOtomatik && S.halOtomatik.id) || null; },
  durdur() { const S = GALAKSI.durum; if (S) { S.dur = true; cancelAnimationFrame(S.raf); if (S.zamanlayici) clearInterval(S.zamanlayici); if (S.ro) S.ro.disconnect(); } GALAKSI.durum = null; },
  kur(a, S) {
    const v = S.veri;
    const tuval = h('canvas', { class: 'gal-tuval', role: 'img', 'aria-label': 'Arşivin yıldız haritası' });
    const baslik = h('div', { class: 'gal-baslik' }, h('div', { class: 'gal-ust' }, 'Arşivin'), h('div', { class: 'gal-sayi' }, SAYI(v.toplam) + ' kayıt'), h('div', { class: 'gal-alt', id: 'gal-alt' }));
    const panel = h('aside', { class: 'gal-panel', id: 'gal-panel' });
    const cip = h('div', { class: 'gal-cipler', role: 'group', 'aria-label': 'Kaynaklar' });
    const yilEtiket = h('div', { class: 'gal-yil', id: 'gal-yil' }, String(S.yil));
    const kaydirici = h('input', { type: 'range', min: S.yilMin, max: S.yilMax, step: 1, value: S.yil, 'aria-label': 'Yıl: arşivi o yıla kadar göster',
      oninput: e => { S.yil = +e.target.value; yilEtiket.textContent = S.yil; GALAKSI.ustMetin(S); } });
    const oynat = h('button', { class: 'gal-oynat', 'aria-label': 'Yılları oynat', onclick: () => GALAKSI.oynat(S, oynat, kaydirici, yilEtiket) }, '▶');
    const alt = h('div', { class: 'gal-cubuk' }, oynat, h('div', { class: 'gal-yilkap' }, kaydirici, h('div', { class: 'gal-yiluc' }, h('span', {}, S.yilMin), h('span', {}, S.yilMax))), yilEtiket);
    const hal = h('div', { class: 'gal-hal', id: 'gal-hal' });
    const girdi = h('input', { type: 'text', id: 'gal-ara-girdi', placeholder: 'Ara: "geçen yaz ChatGPT" ya da mikrofona bas', 'aria-label': 'Galakside ara',
      onkeydown: e => { if (e.key === 'Enter') GALAKSI.sorgula(S, e.target.value); } });
    const mik = h('button', { class: 'gal-mik', id: 'gal-mik', 'aria-label': 'Sesle ara', title: 'Sesle ara (konuş, bitince tekrar bas)', onclick: () => GALAKSI.dinle(S) }, '🎤');
    const araCubuk = h('div', { class: 'gal-ara' }, girdi, h('button', { class: 'gal-ara-d', onclick: () => GALAKSI.sorgula(S, girdi.value) }, 'Ara'), mik, h('div', { class: 'gal-ara-not soluk', id: 'gal-ara-not' }));
    const sahne = h('section', { class: 'gal-sahne' }, tuval, baslik, araCubuk, hal, alt);
    a.append(h('div', { class: 'gal-kap' }, sahne, panel), h('div', { class: 'gal-liste-kap' }, h('h3', {}, 'Kaynaklar'), cip));
    GALAKSI.cipleriCiz(S, cip); GALAKSI.halCiz(S, hal); GALAKSI.panelCiz(S, panel); GALAKSI.ustMetin(S);
    S.tuval = tuval; S.g = tuval.getContext('2d');
    const boyut = () => { const r = sahne.getBoundingClientRect(), d = Math.min(2, window.devicePixelRatio || 1); S.w = Math.max(320, r.width); S.h = Math.max(380, r.height);
      tuval.width = Math.round(S.w * d); tuval.height = Math.round(S.h * d); tuval.style.width = S.w + 'px'; tuval.style.height = S.h + 'px'; S.d = d; S.sc = Math.min(S.w / GAL_W, S.h / GAL_H); };
    boyut(); if (window.ResizeObserver) { S.ro = new ResizeObserver(boyut); S.ro.observe(sahne); }
    tuval.addEventListener('click', e => GALAKSI.tikla(S, e));
    tuval.addEventListener('mousemove', e => { const k = GALAKSI.kumeBul(S, e); const id = k ? k.i : null; if (id !== S.hover) { S.hover = id; tuval.style.cursor = k ? 'pointer' : 'default'; } });
    tuval.addEventListener('mouseleave', () => { S.hover = null; });
    const azHareket = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    S.azHareket = azHareket;
    const dongu = ts => { if (S.dur) return; S.zaman = ts / 1000; GALAKSI.ciz(S); S.raf = requestAnimationFrame(dongu); };
    S.raf = requestAnimationFrame(dongu);
  },
  ustMetin(S) {
    const el = document.getElementById('gal-alt'); if (!el) return;
    const v = S.veri, ic = S.icinde != null ? S.kumeler[S.icinde] : null;
    el.textContent = ic ? `${ic.ad} içindesin` : (S.yil < S.yilMax ? `${S.yilMin} – ${S.yil} arasındaki hâli` : `${v.gruplar.length} kaynak · ${S.yilMin} – ${S.yilMax}`);
  },
  cipleriCiz(S, cip) {
    cip.textContent = '';
    S.kumeler.forEach(k => cip.append(h('button', { class: 'gal-cip' + (S.secili === k.i ? ' secili' : ''), style: `--renk:${k.renk}`,
      onclick: () => GALAKSI.sec(S, k.i) }, h('i', {}), k.ad, h('span', { class: 'soluk' }, ' ' + SAYI(k.sayi)))));
  },
  halCiz(S, el) {
    el.textContent = '';
    const aktif = GALAKSI.halId(S), tahmin = S.halOtomatik;
    el.append(h('span', { class: 'gal-hal-ad' }, 'Hâl'));
    Object.entries(GAL_HALLER).forEach(([id, ho]) => el.append(h('button', { class: 'gal-hal-dugme' + (aktif === id ? ' secili' : ''), 'aria-pressed': String(aktif === id),
      onclick: () => { S.halSecim = id; try { localStorage.setItem(GAL_ANAHTAR, JSON.stringify({ secim: id })); } catch (_) { /* yok */ } GALAKSI.halCiz(S, el); } }, ho.ad)));
    if (S.halSecim) el.append(h('button', { class: 'gal-hal-dugme otomatik', onclick: () => { S.halSecim = null; try { localStorage.removeItem(GAL_ANAHTAR); } catch (_) { /* yok */ } GALAKSI.halCiz(S, el); } }, 'Otomatiğe dön'));
    el.append(h('div', { class: 'gal-hal-not soluk' }, S.halSecim ? 'Hâli sen seçtin.' : (tahmin ? `Tahmin: ${GAL_HALLER[tahmin.id].ad}. ${tahmin.neden}` : 'Hâl için yeterli veri yok.')));
  },
  sec(S, i) { S.sorgu = null; S.secili = i; GALAKSI.cipleriCiz(S, document.querySelector('.gal-cipler')); GALAKSI.panelCiz(S, document.getElementById('gal-panel')); },
  gir(S) { if (S.secili == null) return; S.icinde = S.secili; S.tur = null; const k = S.kumeler[S.icinde];
    S.camHedef = { x: k.cx, y: k.cy, s: Math.min(4, Math.max(1.6, 300 / k.r)) }; GALAKSI.ustMetin(S); GALAKSI.panelCiz(S, document.getElementById('gal-panel')); },
  geri(S) { S.icinde = null; S.tur = null; S.camHedef = { x: GAL_W / 2, y: GAL_H / 2, s: 1 }; GALAKSI.ustMetin(S); GALAKSI.panelCiz(S, document.getElementById('gal-panel')); },
  oynat(S, dugme, kaydirici, etiket) {
    if (S.zamanlayici) { clearInterval(S.zamanlayici); S.zamanlayici = null; S.oynuyor = false; dugme.textContent = '▶'; return; }
    S.oynuyor = true; dugme.textContent = 'II'; if (S.yil >= S.yilMax) S.yil = S.yilMin;
    const adim = () => { kaydirici.value = S.yil; etiket.textContent = S.yil; GALAKSI.ustMetin(S); };
    adim();
    S.zamanlayici = setInterval(() => { if (S.yil >= S.yilMax) { clearInterval(S.zamanlayici); S.zamanlayici = null; S.oynuyor = false; dugme.textContent = '▶'; return; } S.yil++; adim(); }, 900);
  },
  // dünya (0..1) -> ekran
  ekranXY(S, wx, wy) { const c = S.cam, f = S.sc * c.s; return [(wx - c.x) * f + S.w / 2, (wy - c.y) * f + S.h / 2]; },
  kumeBul(S, e) {
    const r = S.tuval.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
    if (S.icinde != null) return null;
    let en = null, enD = 1e9;
    S.kumeler.forEach(k => { const [x, y] = GALAKSI.ekranXY(S, k.cx, k.cy); const d = Math.hypot(px - x, py - y); if (d < k.r * S.sc * S.cam.s * 1.05 && d < enD) { en = k; enD = d; } });
    return en;
  },
  tikla(S, e) {
    const r = S.tuval.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
    if (S.icinde != null) {
      const k = S.kumeler[S.icinde]; const [x, y] = GALAKSI.ekranXY(S, k.cx, k.cy); let sec = null, enD = 1e9;
      S.alt[S.icinde].forEach((u, j) => { const d = Math.hypot(px - (x + u.ax * S.sc * S.cam.s), py - (y + u.ay * S.sc * S.cam.s)); if (d < k.r * .3 * S.sc * S.cam.s && d < enD) { sec = j; enD = d; } });
      if (sec != null) GALAKSI.altSec(S, sec);
      return;
    }
    const k = GALAKSI.kumeBul(S, e); if (k) GALAKSI.sec(S, k.i);
  },
  altSec(S, j) { S.tur = j; S.kayitSayfa = 0; GALAKSI.panelCiz(S, document.getElementById('gal-panel')); },
  ciz(S) {
    const g = S.g, d = S.d, t = S.zaman;
    const hid = GALAKSI.halId(S), hedef = hid ? GAL_HALLER[hid] : GAL_VARSAYILAN_HAL;
    for (const a of Object.keys(GAL_VARSAYILAN_HAL)) S.hal[a] += (hedef[a] - S.hal[a]) * .04;   // hâl yumuşakça geçer
    for (const a of ['x', 'y', 's']) S.cam[a] += (S.camHedef[a] - S.cam[a]) * .07;
    const H = S.hal, hiz = S.azHareket ? 0 : H.hiz, zt = t * hiz;
    g.setTransform(d, 0, 0, d, 0, 0);
    const arka = g.createRadialGradient(S.w * .4, S.h * .5, 10, S.w * .4, S.h * .5, Math.max(S.w, S.h) * .8);
    arka.addColorStop(0, '#1B2447'); arka.addColorStop(1, '#0B1020'); g.fillStyle = arka; g.fillRect(0, 0, S.w, S.h);
    for (let i = 0; i < 70; i++) { g.globalAlpha = .12 + galHash(i, 41) * .35; g.fillStyle = '#CFCCE0'; g.fillRect(galHash(i, 43) * S.w, galHash(i, 47) * S.h, 1.4, 1.4); }
    const sonT = Date.UTC(S.yil + 1, 0, 1) / 1000, kamS = S.cam.s * S.sc, ic = S.icinde;
    // kümelerin parıltısı
    S.kumeler.forEach(k => {
      const [cx, cy] = GALAKSI.ekranXY(S, k.cx, k.cy), r = k.r * kamS;
      const bas = ic != null && ic !== k.i; const soluk = bas ? .04 : (S.hover != null && S.hover !== k.i && ic == null ? .45 : 1);
      const gr = g.createRadialGradient(cx, cy, 0, cx, cy, r * 1.7); gr.addColorStop(0, galRenkKaydir(k.renk, H.ton, H.parlak).replace('hsl(', 'hsla(').replace(')', ' / .30)')); gr.addColorStop(.62, 'rgba(0,0,0,0)');
      g.globalAlpha = soluk; g.fillStyle = gr; g.beginPath(); g.arc(cx, cy, r * 1.7, 0, 6.283); g.fill();
      if (S.secili === k.i && ic == null) { g.globalAlpha = .7; g.strokeStyle = '#EDEAF5'; g.setLineDash([5, 6]); g.beginPath(); g.arc(cx, cy, r * 1.05, 0, 6.283); g.stroke(); g.setLineDash([]); }
      if (ic == null) { g.globalAlpha = soluk; g.fillStyle = '#EDEAF5'; g.font = '600 15px "Segoe UI",system-ui,sans-serif'; g.textAlign = 'center'; g.fillText(k.ad, cx, cy + r * .98); g.fillStyle = '#A9A6BD'; g.font = '13px "Segoe UI",system-ui,sans-serif'; g.fillText(SAYI(k.sayi) + ' kayıt', cx, cy + r * .98 + 17); }
    });
    // yıldızlar
    const rkCache = {}; let cizilen = 0;
    for (let i = 0; i < S.ys.length; i++) {
      const s = S.ys[i]; if (s.t >= sonT) continue; const k = S.kumeler[s.g], bas = ic != null && ic !== s.g;
      let renk, ox = s.gx, oy = s.gy, sig = k.r / 2.3;
      if (ic === s.g) { const u = S.alt[s.g][s.alt]; ox = s.gx * .42; oy = s.gy * .42; sig = k.r / 2.3; ox += u.ax / sig; oy += u.ay / sig; renk = u.renk; } else renk = k.renk;
      let px = ox * sig * H.yayilim, py = oy * sig * H.yayilim;
      const lim = k.r * 1.3; const uz = Math.hypot(px, py); if (uz > lim) { px = px / uz * lim; py = py / uz * lim; }
      if (H.izgara > 0.01) {   // ızgara düzeni: yıldızları kare ızgara hücrelerine yaklaştır
        const n = k.yildiz, kenar = Math.ceil(Math.sqrt(n)), adim = (k.r * 2.2) / kenar, gx = ((s.sira % kenar) - kenar / 2) * adim, gy = (Math.floor(s.sira / kenar) - kenar / 2) * adim;
        px += (gx - px) * H.izgara; py += (gy - py) * H.izgara;
      }
      if (H.akis > 0.01) { px += Math.sin(zt * .8 + py * .03 + s.faz) * 9 * H.akis; py += Math.cos(zt * .6 + px * .03 + s.faz) * 7 * H.akis; }
      px += Math.sin(zt * .35 + k.i) * 5; py += Math.cos(zt * .3 + k.i * 2) * 6;      // kümenin nefesi
      const [cx, cy] = GALAKSI.ekranXY(S, k.cx, k.cy), x = cx + px * kamS, y = cy + py * kamS;
      if (x < -6 || y < -6 || x > S.w + 6 || y > S.h + 6) continue;
      const tw = S.azHareket ? 1 : .75 + .25 * Math.sin(zt * 2 + s.faz);
      const sq = S.sorgu, ic2 = sq && sq.bas != null && s.t >= sq.bas && s.t < sq.bit, sqKume = sq && sq.kume != null && sq.kume !== s.g;
      const sorguCarpan = !sq ? 1 : (sqKume ? .08 : (sq.bas == null || ic2 ? 1 : .12));
      g.globalAlpha = (bas ? .05 : s.o * tw * sorguCarpan) * Math.min(1, H.parlak);
      const key = renk + '|' + H.ton; let c = rkCache[key]; if (!c) c = rkCache[key] = galRenkKaydir(renk, H.ton, H.parlak);
      g.fillStyle = c; const b = s.boy * Math.min(2.2, Math.sqrt(S.cam.s));
      if (b < 2.6) g.fillRect(x - b / 2, y - b / 2, b, b); else { g.beginPath(); g.arc(x, y, b / 2, 0, 6.283); g.fill(); }
      cizilen++;
    }
    // alt küme adları
    if (ic != null) {
      const k = S.kumeler[ic], [cx, cy] = GALAKSI.ekranXY(S, k.cx, k.cy);
      S.alt[ic].forEach((u, j) => { const x = cx + u.ax * kamS, y = cy + u.ay * kamS + 8; const sec = S.tur === j; g.globalAlpha = 1; g.font = '600 13px "Segoe UI",system-ui,sans-serif'; g.textAlign = 'center';
        const w = g.measureText(u.ad).width + 22; g.fillStyle = 'rgba(11,16,32,.78)'; g.strokeStyle = u.renk; g.lineWidth = sec ? 2.4 : 1; g.beginPath(); g.roundRect ? g.roundRect(x - w / 2, y - 14, w, 26, 13) : g.rect(x - w / 2, y - 14, w, 26); g.fill(); g.stroke(); g.lineWidth = 1;
        g.fillStyle = '#EDEAF5'; g.fillText(u.ad, x, y + 4); });
    }
    g.globalAlpha = 1; S.cizilen = cizilen;
  },
  panelCiz(S, el) {
    if (!el) return; el.textContent = '';
    const v = S.veri;
    if (S.sorgu) { GALAKSI.sorguPaneli(S, el); return; }
    if (S.icinde != null) {
      const k = S.kumeler[S.icinde], al = S.alt[S.icinde], tek = S.tur != null ? al[S.tur] : null;
      el.append(h('div', { class: 'gal-etiket' }, 'İçindesin'), h('div', { class: 'gal-ad' }, k.ad), h('div', { class: 'gal-buyuk' }, SAYI(k.sayi)), h('div', { class: 'soluk' }, 'kayıt'),
        h('p', {}, 'Renkler bu kaynağın kayıt türlerini ayırır. Bir türün adına dokun, kayıtları aşağıda açılsın.'));
      const turKap = h('div', { class: 'gal-turler' }); al.forEach((u, j) => turKap.append(h('button', { class: 'gal-tur' + (S.tur === j ? ' secili' : ''), style: `--renk:${u.renk}`, onclick: () => GALAKSI.altSec(S, j) },
        h('i', {}), u.ad, h('span', { class: 'soluk' }, (v.seyreltme > 1 ? ' ≈' : ' ') + SAYI(u.sayi * v.seyreltme))))); el.append(turKap);
      if (tek) GALAKSI.kayitListesi(S, el, k, tek); else el.append(h('button', { class: 'i', onclick: () => GALAKSI.kayitListesi(S, el, k, null) }, 'Tüm kayıtları göster'));
      el.append(h('button', { class: 'gal-geri', onclick: () => GALAKSI.geri(S) }, '← Tüm galaksi')); return;
    }
    if (S.secili != null) {
      const k = S.kumeler[S.secili], pay = (100 * k.sayi / Math.max(1, v.toplam)).toLocaleString('tr-TR', { maximumFractionDigits: 1 });
      el.append(h('div', { class: 'gal-etiket' }, 'Kaynak'), h('div', { class: 'gal-ad' }, k.ad), h('div', { class: 'gal-buyuk' }, SAYI(k.sayi)), h('div', { class: 'soluk' }, `kayıt · arşivin %${pay} kadarı`),
        k.ilk ? h('p', {}, `İlk kayıt ${tarih(k.ilk).slice(0, 10)}, son kayıt ${tarih(k.son).slice(0, 10)}.`) : h('p', {}, 'Bu kaynağın kayıtlarında gerçek bir tarih yok.'),
        h('button', { class: 'd', onclick: () => GALAKSI.gir(S) }, 'İçine gir'));
      return;
    }
    el.append(h('div', { class: 'gal-ad' }, 'Arşivin bir takımyıldızı.'), h('p', {}, 'Her parlayan küme bir kaynak, her nokta bir kayıt. Bir kümeye dokun; ayrıntısı burada açılsın. Alttaki çubuğu kaydırırsan arşivin yıllar içinde nasıl büyüdüğünü görürsün.'),
      ...[v.tarihsiz ? h('p', { class: 'soluk' }, `${SAYI(v.tarihsiz)} kaydın gerçek tarihi yok; sayılırlar ama yıl çubuğunda yer almazlar.`) : null,
        v.seyreltme > 1 ? h('p', { class: 'soluk' }, `Çizimde her ${v.seyreltme} kayıttan biri gösterilir; sayılar tamdır.`) : null].filter(Boolean));
  },
  // ---- arama (yazılı ya da sesli): kurallarla çözülür, galaksi sonuca uçar
  async sorgula(S, metin) {
    metin = String(metin || '').trim(); if (!metin) return;
    const not = document.getElementById('gal-ara-not'); not.textContent = 'Aranıyor…';
    let r; try { r = await api('ses_sorgu', { metin }); } catch (e) { not.textContent = ''; hataGoster(e); return; }
    if (r.bos) { not.textContent = 'Ne aradığını anlayamadım. Tarih, kaynak ya da bir sözcük söyle (ör. "geçen yaz ChatGPT").'; return; }
    const kume = r.kaynak ? S.kumeler.find(k => k.ad === r.kaynak) : null;
    S.sorgu = { ...r, kume: kume ? kume.i : null }; S.secili = kume ? kume.i : null; S.icinde = null; S.tur = null; S.kayitSayfa = 0;
    S.camHedef = kume ? { x: kume.cx, y: kume.cy, s: 1.8 } : { x: GAL_W / 2, y: GAL_H / 2, s: 1 };
    if (r.bit != null) { const y = Math.max(S.yilMin, Math.min(S.yilMax, new Date((r.bit - 1) * 1000).getUTCFullYear())); S.yil = y;
      const kay = document.querySelector('.gal-yilkap input'); if (kay) kay.value = y; const et = document.getElementById('gal-yil'); if (et) et.textContent = y; }
    not.textContent = 'Anladığım: ' + r.anlasilan.join(' · ');
    GALAKSI.cipleriCiz(S, document.querySelector('.gal-cipler')); GALAKSI.ustMetin(S); GALAKSI.panelCiz(S, document.getElementById('gal-panel'));
  },
  sorguPaneli(S, el) {
    const q = S.sorgu;
    el.append(h('div', { class: 'gal-etiket' }, 'Arama'), h('div', { class: 'gal-ad' }, '«' + q.metin + '»'),
      h('div', { class: 'soluk' }, 'Anladığım:'), h('ul', { class: 'gal-anlasilan' }, q.anlasilan.map(x => h('li', {}, x))),
      h('button', { class: 'gal-geri', onclick: () => { S.sorgu = null; S.secili = null; S.camHedef = { x: GAL_W / 2, y: GAL_H / 2, s: 1 }; document.getElementById('gal-ara-not').textContent = '';
        document.getElementById('gal-ara-girdi').value = ''; GALAKSI.cipleriCiz(S, document.querySelector('.gal-cipler')); GALAKSI.ustMetin(S); GALAKSI.panelCiz(S, el); } }, '← Aramayı temizle'));
    GALAKSI.kayitListesi(S, el, q.kume != null ? S.kumeler[q.kume] : null, null);
  },
  // ---- mikrofon: tarayıcıda 16 kHz mono PCM kaydı -> yerel Whisper (ses internete gitmez)
  async dinle(S) {
    const mik = document.getElementById('gal-mik'), not = document.getElementById('gal-ara-not');
    if (S.kayit) { S.kayit.bitir(); return; }
    let d; try { d = await api('ses_durum'); } catch (e) { hataGoster(e); return; }
    if (!d.motor_kurulu) { GALAKSI.sesKurPaneli(S, d); return; }
    if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) { not.textContent = 'Bu pencerede mikrofon kullanılamıyor. Yazarak arayabilirsin.'; return; }
    let akim; try { akim = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true } }); } catch (e) { not.textContent = 'Mikrofon izni verilmedi ya da mikrofon yok. Yazarak arayabilirsin.'; return; }
    const AC = window.AudioContext || window.webkitAudioContext, ac = new AC({ sampleRate: 16000 }), kaynak = ac.createMediaStreamSource(akim), isl = ac.createScriptProcessor(4096, 1, 1), parcalar = [];
    isl.onaudioprocess = e => parcalar.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    kaynak.connect(isl); isl.connect(ac.destination);
    mik.classList.add('kayitta'); not.textContent = 'Dinliyorum… (bitince tekrar mikrofona bas)';
    const bitir = async () => {
      if (!S.kayit) return; clearTimeout(zm); S.kayit = null; mik.classList.remove('kayitta');
      try { isl.disconnect(); kaynak.disconnect(); akim.getTracks().forEach(t => t.stop()); await ac.close(); } catch (_) { /* kapanmış */ }
      const n = parcalar.reduce((a, p) => a + p.length, 0), pcm = new Int16Array(n); let o = 0;
      parcalar.forEach(p => { for (let i = 0; i < p.length; i++) pcm[o++] = Math.max(-32768, Math.min(32767, Math.round(p[i] * 32767))); });
      let ikili = ''; const b = new Uint8Array(pcm.buffer); for (let i = 0; i < b.length; i += 8192) ikili += String.fromCharCode.apply(null, b.subarray(i, i + 8192));
      not.textContent = 'Çözümlüyorum… (ilk seferde model yüklenirken biraz sürer)';
      try { const r = await api('ses_tani', { pcm: btoa(ikili) }); document.getElementById('gal-ara-girdi').value = r.metin; if (r.metin) await GALAKSI.sorgula(S, r.metin); else not.textContent = 'Bir şey duyamadım.'; }
      catch (e) { not.textContent = ''; hataGoster(e); }
    };
    const zm = setTimeout(bitir, 12000); S.kayit = { bitir };
  },
  sesKurPaneli(S, d) {
    const el = document.getElementById('gal-panel'); el.textContent = '';
    el.append(h('div', { class: 'gal-ad' }, 'Sesle arama'), h('p', {}, d.aciklama));
    const durum = h('div', { class: 'soluk', id: 'ses-kur-durum' }, d.kurulum && d.kurulum.mesaj || '');
    if (d.python_var) el.append(h('button', { class: 'd', onclick: async () => { try { await api('ses_kur'); } catch (e) { hataGoster(e); return; }
      const yokla = async () => { const x = await api('ses_durum').catch(() => null); if (!x) return; durum.textContent = x.kurulum.mesaj; if (x.kurulum.durum === 'calisiyor' && GALAKSI.durum === S) setTimeout(yokla, 3000); }; yokla(); } }, 'Ses motorunu kur'));
    el.append(durum, h('p', { class: 'soluk' }, 'Kurulana kadar yukarıdaki kutuya yazarak arayabilirsin.'),
      h('button', { class: 'gal-geri', onclick: () => GALAKSI.panelCiz(S, el) }, 'Kapat'));
  },
  async kayitListesi(S, el, k, tur) {
    const kutu = h('div', { class: 'gal-kayitlar' }, h('div', { class: 'soluk' }, 'Yükleniyor…')); el.append(kutu);
    const q = S.sorgu, bit = q && q.bit != null ? q.bit : Math.floor(Date.UTC(S.yil + 1, 0, 1) / 1000);
    let r; try { r = await api('galaksi_kayitlar', { grup: k ? k.ad : '', bas: q && q.bas != null ? q.bas : null, bit, arama: q ? q.arama : null, tur: tur && tur.tur ? tur.tur : null, limit: 20, offset: S.kayitSayfa * 20 }); } catch (e) { kutu.textContent = ''; hataGoster(e); return; }
    kutu.textContent = ''; kutu.append(h('div', { class: 'soluk' }, S.sorgu ? `${SAYI(r.toplam)} kayıt bulundu, yeniden eskiye` : `${SAYI(r.toplam)} kayıt (${S.yil} sonuna kadar), yeniden eskiye`));
    r.kayitlar.forEach(x => kutu.append(h('button', { class: 'gal-kayit', onclick: () => { if (typeof kayitAc === 'function') kayitAc(x.event_id); } },
      h('div', { class: 'soluk' }, tarih(x.ts) + ' · ' + galTurAdi(x.kind)), h('div', {}, x.baslik || x.ozet || '(metin yok)'))));
    if (r.toplam > (S.kayitSayfa + 1) * 20) kutu.append(h('button', { class: 'i', onclick: () => { S.kayitSayfa++; GALAKSI.panelCiz(S, document.getElementById('gal-panel')); } }, 'Daha eski kayıtlar'));
    if (S.kayitSayfa > 0) kutu.append(h('button', { class: 'i', onclick: () => { S.kayitSayfa--; GALAKSI.panelCiz(S, document.getElementById('gal-panel')); } }, 'Daha yeni kayıtlar'));
  },
};
