"use strict";
/* Telefon aktarımı sayfası (docs/AKTARIM.md). Yalnız yerel /api/telefon_* uçlarını çağırır; ağa HİÇ bağlanmaz.
   QR kodu yerelde üretilir (qrcode.js, MIT; CDN yok). Eşleştirme kodu yalnız ekranda tutulur, günlüğe yazılmaz.
   Metinler textContent ile eklenir (h()). */
const TEL_ACIKLAMA='Bilgisayar yalnız ev ağından, yalnız eşleştirdiğin telefondan dosya kabul eder. Windows ilk seferde Güvenlik Duvarı izni sorabilir; \'Özel ağlar\' için izin ver. Ağ \'Ortak\' olarak ayarlıysa telefon bağlanamaz.';
const TEL = { kod: null, bitis: 0 };

/* QR matrisi: satırlar '0'/'1' metni (test ve çizim için). 'M' düzeyi; sürüm metne göre otomatik. */
function qrMatris(metin) {
  const q = qrcode(0, 'M');
  q.addData(metin, 'Byte');
  q.make();
  const n = q.getModuleCount(), satirlar = [];
  for (let r = 0; r < n; r++) {
    let s = '';
    for (let c = 0; c < n; c++) s += q.isDark(r, c) ? '1' : '0';
    satirlar.push(s);
  }
  return satirlar;
}
function qrTuval(metin, modul) {
  const m = qrMatris(metin), n = m.length, sessiz = 4, boy = (n + 2 * sessiz) * modul;
  const t = document.createElement('canvas');
  t.width = t.height = boy;
  t.setAttribute('role', 'img');
  t.setAttribute('aria-label', 'Eşleştirme QR kodu');
  const g = t.getContext('2d');
  g.fillStyle = '#fff';            // koyu temada da beyaz zemin + siyah modül: okuyucular için şart
  g.fillRect(0, 0, boy, boy);
  g.fillStyle = '#000';
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (m[r][c] === '1') g.fillRect((c + sessiz) * modul, (r + sessiz) * modul, modul, modul);
  t.dataset.surum = String((n - 17) / 4);
  return t;
}

function telSure(sn) { return Math.floor(sn / 60) + ':' + String(sn % 60).padStart(2, '0'); }

async function telefonSayfasi(a) {
  a.append(h('h2', {}, 'Telefon'),
    h('p', { class: 'soluk' }, 'Telefondaki Kimlik Merkezi uygulaması, ev ağında bu bilgisayara dosya gönderebilir. Aktarım varsayılan olarak kapalıdır.'));
  const anahtar = h('input', { type: 'checkbox', id: 'tel-ac' });
  const durumSatiri = h('div', { id: 'tel-durum', class: 'soluk' });
  const uyariKutusu = h('div', { id: 'tel-uyari' });
  const alimSatiri = h('div', { id: 'tel-alim' });
  const kodAlani = h('div', { id: 'tel-kod-alani' });
  const liste = h('div', { id: 'tel-cihazlar' });
  const ekle = h('button', { class: 'd', id: 'tel-ekle', disabled: true, onclick: () => kodUret() }, 'Telefon ekle');

  anahtar.addEventListener('change', async () => {
    const acmak = anahtar.checked;
    anahtar.checked = !acmak;            // sunucu yanıtı gelene kadar eski hâlde kalsın
    if (acmak) {
      const kapat = pencere('Telefondan aktarımı aç', h('p', { id: 'tel-aciklama' }, TEL_ACIKLAMA),
        h('div', { class: 'satir' },
          h('button', { class: 'd', id: 'tel-onay', onclick: async () => { kapat(); await ayarla(true); } }, 'Aç'),
          h('button', { class: 'i', onclick: () => kapat() }, 'Vazgeç')));
    } else await ayarla(false);
  });
  async function ayarla(acik) {
    try { await api('telefon_ac', { acik }); } catch (e) { hataGoster(e); }
    await yenile();
  }

  async function kodUret() {
    try {
      const r = await api('telefon_kod_uret', {});
      TEL.kod = r.kod; TEL.bitis = Date.now() + r.sure_s * 1000;
      kodCiz(null);
    } catch (e) { hataGoster(e); }
  }
  function kodCiz(d) {
    kodAlani.textContent = '';
    if (!TEL.kod) return;
    const kalan = Math.max(0, Math.round((TEL.bitis - Date.now()) / 1000));
    const gecersiz = d && !d.kod_gecerli && (d.kod_gecersizlik_nedeni || kalan === 0);
    if (gecersiz || kalan === 0) {
      const neden = d && d.kod_gecersizlik_metni;
      const eslesti = d && d.kod_gecersizlik_nedeni === 'kullanildi';
      TEL.kod = null;
      kodAlani.append(h('div', { class: eslesti ? 'tamam' : 'uyari', id: 'tel-kod-gecersiz' },
        eslesti ? 'Telefon eşleşti.' : 'Kod geçersiz oldu' + (neden ? ' (' + neden.replace(/\.$/, '') + ')' : '') + ', yenisini üret.',
        ' ', eslesti ? null : h('button', { class: 'i', onclick: () => kodUret() }, 'Yeni kod üret')));
      return;
    }
    const kutu = h('textarea', { readonly: '', id: 'tel-kod', rows: 4, onclick: e => e.target.select(), 'aria-label': 'Eşleştirme kodu' });
    kutu.value = TEL.kod;
    kodAlani.append(
      h('p', {}, 'Telefondaki uygulamada "Bilgisayar ekle"yi aç; bu QR kodu okut ya da aşağıdaki kodu yapıştır. Kod tek kullanımlıktır.'),
      h('div', { id: 'tel-qr' }, qrTuval(TEL.kod, 5)),
      kutu,
      h('div', { class: 'satir' }, h('button', { class: 'i', id: 'tel-kod-kopyala', onclick: () => kopyala(TEL.kod) }, 'Kodu kopyala'),
        h('span', { class: 'soluk', id: 'tel-kalan' }, 'Kalan süre: ' + telSure(kalan))));
  }
  function tikla() {   // saniyede bir: yalnız sayaç
    const s = $('#tel-kalan');
    if (!s || !TEL.kod) return;
    const kalan = Math.max(0, Math.round((TEL.bitis - Date.now()) / 1000));
    if (kalan === 0) kodCiz(null); else s.textContent = 'Kalan süre: ' + telSure(kalan);
  }

  async function yenile() {
    const d = await api('telefon_durum', {});
    anahtar.checked = d.acik;
    ekle.disabled = !d.calisiyor;
    durumSatiri.textContent = '';
    if (d.calisiyor) {
      const adr = d.adresler.length ? d.adresler.map(x => x + ':' + d.port).join(', ') : 'adres bulunamadı (port ' + d.port + ')';
      durumSatiri.append('Çalışıyor. Telefon elle adres isterse: ', h('b', { id: 'tel-adres' }, adr));
    } else if (d.acik && !d.uygulama_acik) durumSatiri.append('Açık, ama veri klasörü açık değil; alıcı çalışmıyor.');
    else durumSatiri.append(d.acik ? 'Açık, ama alıcı çalışmıyor.' : 'Kapalı.');
    uyariKutusu.textContent = '';
    if (d.hata) uyariKutusu.append(h('div', { class: 'uyari', id: 'tel-hata' }, d.hata));
    if (d.sertifika_yenilendi && d.uyari) uyariKutusu.append(h('div', { class: 'uyari', id: 'tel-sertifika' }, d.uyari));
    alimSatiri.textContent = '';
    if (d.son_alim) alimSatiri.append(h('p', { id: 'tel-alim-metin' },
      `Telefondan ${SAYI(d.toplam_yeni)} yeni kayıt alındı; son alım: ${tarih(d.son_alim.zaman)}` +
      (d.son_alim.yinelenen ? ` (${SAYI(d.son_alim.yinelenen)} kayıt zaten vardı)` : '') +
      (d.son_alim.eksik ? ` — ${SAYI(d.son_alim.eksik)} dosya alınamadı, sonra yeniden denenecek` : '')));
    if (TEL.kod && d.kod_kalan_s != null) TEL.bitis = Date.now() + d.kod_kalan_s * 1000;
    if (TEL.kod && !d.kod_gecerli) kodCiz(d);
    liste.textContent = '';
    if (!d.cihazlar.length) liste.append(h('p', { class: 'soluk', id: 'tel-bos' }, 'Henüz eşleşmiş telefon yok.'));
    d.cihazlar.forEach(c => liste.append(h('div', { class: 'kart tel-cihaz', 'data-id': c.id },
      h('div', {}, h('b', {}, c.ad || 'Adsız telefon'), ' · ', c.platform || 'bilinmiyor'),
      h('div', { class: 'soluk' }, 'Eşleşme: ' + tarih(c.eslesme) + ' · Son görülme: ' + tarih(c.son_gorulme)),
      c.iptal ? h('div', { class: 'rozet h' }, 'Eşleştirme kaldırıldı')
        : h('div', { class: 'satir' }, h('button', { class: 't', onclick: async () => {
          if (!confirm('Bu telefonun eşleştirmesi kaldırılsın mı? Telefon yeniden eşleşmedikçe dosya gönderemez.')) return;
          try { await api('telefon_cihaz_kaldir', { device_id: c.id }); bildir('Eşleştirme kaldırıldı.'); } catch (e) { hataGoster(e); }
          await yenile();
        } }, 'Eşleştirmeyi kaldır')))));
  }

  a.append(h('div', { class: 'kart' }, h('label', {}, anahtar, ' Telefondan aktarımı aç'), durumSatiri, uyariKutusu, alimSatiri),
    h('div', { class: 'kart' }, h('h3', {}, 'Telefon ekle'), h('div', { class: 'satir' }, ekle), kodAlani),
    h('div', { class: 'kart' }, h('h3', {}, 'Eşleşmiş telefonlar'), liste),
    h('div', { class: 'kart' }, h('h3', {}, 'Telefon dosyası al'),
      h('p', { class: 'soluk' }, 'Telefonda "Dosyaya aktar" ile oluşturduğun .zip ya da .jsonl dosyasını elle de alabilirsin (tür "android_giden" olarak tanınır).'),
      h('button', { class: 'i', id: 'tel-dosya-al', onclick: () => git('ice') }, 'Telefon dosyası al')));
  await yenile();
  yoklama = setInterval(() => yenile().catch(() => {}), 2000);
  yoklamaT = setInterval(tikla, 1000);
}
