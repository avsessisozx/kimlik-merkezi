/* "Sen kimsin" sayfası (v0.3.0): üç ayrı bölüm, karışmaz.
   1) GERÇEK: verinden çıkan sayımlar ve tarihler (yorum yok).
   2) SENİN SÖYLEDİKLERİN: persona'da onayladığın bilgiler (beyan edilen / dosyadan alınan).
   3) YORUM (yapay zekâ önerisi): onayına bekleyen çıkarımlar. Her biri "yorum" diye işaretlidir ve sen onaylamadan
      kimlik kartına girmez. Kayıt metinleri güvenilmez veri: yalnız textContent ile eklenir. */
"use strict";
const SENKIMSIN = {
  ekran: async function (a) {
    const [oz, per, on] = await Promise.all([api('kimlik_ozeti'), api('persona_liste'), api('oneri_listele', { durum: 'bekliyor' })]);
    const katAd = Object.fromEntries(per.kategoriler.map(k => [k.kimlik, k.ad]));
    const durumAd = { beyan_edilen: 'Sen söyledin', dosyadan_alinan: 'Dosyadan alındı' };
    const kendi = per.bilgiler.filter(b => b.durum === 'beyan_edilen' || b.durum === 'dosyadan_alinan');
    a.append(h('h2', {}, 'Sen kimsin'),
      h('p', { class: 'soluk' }, 'Burada üç şey ayrı tutulur: verinden çıkan gerçekler, senin söylediklerin ve yapay zekânın yorumları. Yorumlar sen onaylamadıkça hiçbir yere işlenmez.'));

    const gercek = h('section', { class: 'kart sk-gercek' }, h('h3', {}, 'Verinden çıkan gerçekler', h('span', { class: 'sk-rozet gercek' }, 'sayım')));
    if (!oz.maddeler || !oz.maddeler.length) gercek.append(h('p', { class: 'soluk' }, oz.not || 'Henüz veri yok.'));
    else {
      const ul = h('ul', { class: 'sk-liste' });
      oz.maddeler.forEach(m => ul.append(h('li', {}, h('span', {}, m.metin), h('span', { class: 'soluk sk-kanit' }, ' · ' + m.kanit))));
      gercek.append(ul);
      if (oz.kaynaklar && oz.kaynaklar.length) gercek.append(h('div', { class: 'sk-kaynaklar' }, oz.kaynaklar.map(k => h('span', { class: 'rozet' }, `${k.ad} ${SAYI(k.sayi)}`))));
      gercek.append(h('div', { class: 'soluk' }, oz.not));
    }

    const senin = h('section', { class: 'kart sk-senin' }, h('h3', {}, 'Senin söylediklerin', h('span', { class: 'sk-rozet senin' }, 'onaylı')));
    if (!kendi.length) senin.append(h('p', { class: 'soluk' }, 'Henüz kendin hakkında bir bilgi eklemedin.'));
    else {
      const ul = h('ul', { class: 'sk-liste' });
      kendi.forEach(b => ul.append(h('li', {}, h('span', {}, b.metin), h('span', { class: 'soluk sk-kanit' }, ` · ${katAd[b.kategori] || b.kategori} · ${durumAd[b.durum]}`))));
      senin.append(ul);
    }
    senin.append(h('button', { class: 'i', onclick: () => git('persona') }, 'Bilgi ekle ya da düzenle'));

    const yorum = h('section', { class: 'kart sk-yorum' }, h('h3', {}, 'Yapay zekânın yorumları', h('span', { class: 'sk-rozet yorum' }, 'yorum')));
    if (!on.oneriler.length) yorum.append(h('p', { class: 'soluk' }, 'Onayını bekleyen bir yorum yok.'));
    else {
      yorum.append(h('p', { class: 'soluk' }, 'Bunlar bir yapay zekâ uygulamasının senin hakkında çıkardığı tahminlerdir; doğru olmayabilir. Onaylamazsan hiçbir yere işlenmez.'));
      const ul = h('ul', { class: 'sk-liste' });
      on.oneriler.slice(0, 8).forEach(o => ul.append(h('li', {}, h('span', {}, o.ifade), h('span', { class: 'soluk sk-kanit' }, ` · ${o.kategori_ad} · ${o.uygulama} · ${o.kanit_sayisi} kanıt kaydı`))));
      yorum.append(ul);
      if (on.oneriler.length > 8) yorum.append(h('div', { class: 'soluk' }, `Ve ${on.oneriler.length - 8} yorum daha.`));
    }
    yorum.append(h('button', { class: 'i', onclick: () => git('persona') }, 'Yorumları incele ve onayla'));
    a.append(gercek, senin, yorum);
  },
};
