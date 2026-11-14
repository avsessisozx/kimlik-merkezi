"use strict";
/* Güncelleme arayüzü: üstteki kutu (yeni sürüm sorusu, ilerleme, ikinci onay) ve Ayarlar kartı.
   Bu dosya ağa HİÇ bağlanmaz: yalnız yerel /api/guncelleme_* uçlarını (api()) çağırır; GitHub ile konuşan tek kod
   guncelleme.py'dir. Metinler textContent ile eklenir (h()).
   İndirme ve kurulum yalnız aşağıdaki düğmelere basınca (onay:true) başlar. */
const GUNC = { d: null, gizli: null, elle: false, anahtar: null, t: null };
const GUNC_AKTIF = ['denetleniyor', 'indiriliyor', 'dogrulaniyor', 'kuruluyor'];

function guncMB(b) { return (b / 1048576).toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }); }
function guncSure(sn) {
  if (sn == null) return 'hesaplanıyor';
  if (sn < 60) return sn + ' sn';
  if (sn < 3600) return Math.floor(sn / 60) + ' dk ' + (sn % 60) + ' sn';
  return Math.floor(sn / 3600) + ' sa ' + Math.floor((sn % 3600) / 60) + ' dk';
}
function guncIlerlemeMetni(d) {
  const yuzde = d.yuzde.toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const son = d.durum === 'duraklatildi' ? 'duraklatıldı' : 'kalan süre: ' + guncSure(d.kalan_sn);
  return `${guncMB(d.indirilen)} / ${guncMB(d.toplam)} MB — %${yuzde} — ${son}`;
}
function guncDurumMetni(d) {
  switch (d.durum) {
    case 'bosta': return 'Henüz denetlenmedi.';
    case 'denetleniyor': return 'Denetleniyor…';
    case 'guncel': return `Kimlik Merkezi güncel (${d.mevcut}). Son denetim: ${tarih(d.son_denetim)}`;
    case 'yeni': case 'iptal': return `Yeni sürüm ${d.surum} var (üstteki kutudan indirebilirsiniz).`;
    case 'hazir': return `Sürüm ${d.surum} indirildi ve doğrulandı; kurmak için üstteki kutuyu kullanın.`;
    case 'kuruluyor': return 'Kurulum başlatılıyor…';
    case 'hata': case 'kapali': return d.mesaj;
    default: return 'İndirme sürüyor (üstteki kutuya bakın).';
  }
}
function guncBannerGerekli(d) {
  switch (d.durum) {
    case 'yeni': case 'iptal': case 'hazir': return GUNC.gizli !== d.surum;
    case 'indiriliyor': case 'duraklatildi': case 'dogrulaniyor': case 'kuruluyor': return true;
    case 'hata': return d.surum != null ? GUNC.gizli !== d.surum : GUNC.elle;   // otomatik denetim hatası ekranı bölmez
    default: return false;
  }
}
async function guncEylem(ad, girdi) {
  try { GUNC.d = await api(ad, girdi || {}); } catch (e) { hataGoster(e); }
  guncCiz();
  guncYenile();
}
function guncKutuKur(d) {
  const dugme = (id, ad, sinif, fn) => h('button', { id, class: sinif, onclick: fn }, ad);
  const gizle = () => { GUNC.gizli = d.surum; guncCiz(); };
  const ek = (...c) => h('div', { class: 'satir' }, ...c);
  switch (d.durum) {
    case 'yeni': case 'iptal':
      return [h('b', { id: 'gunc-baslik' }, `Yeni sürüm ${d.surum}${d.onsurum ? ' (ön sürüm)' : ''} var, indirmek ister misin?`),
        h('div', { class: 'soluk' }, `${d.dosya_adi} (${guncMB(d.boyut)} MB). ` + (d.durum === 'iptal' ? 'Önceki indirme iptal edildi. ' : '') +
          'İndirme yalnız siz onaylayınca başlar; dosya GitHub\'dan alınır ve SHA-256 ile doğrulanır. Kurulum için ayrıca onayınız istenir.'),
        ek(dugme('gunc-indir', 'İndir', 'd', () => guncEylem('guncelleme_indir', { onay: true })), dugme('gunc-simdi-degil', 'Şimdi değil', 'i', gizle))];
    case 'indiriliyor': case 'duraklatildi':
      return [h('b', { id: 'gunc-baslik' }, `Sürüm ${d.surum} indiriliyor`),
        h('progress', { id: 'gunc-ilerleme', max: 100, value: d.yuzde }), h('div', { id: 'gunc-metin', class: 'soluk' }, guncIlerlemeMetni(d)),
        ek(d.durum === 'indiriliyor' ? dugme('gunc-duraklat', 'Duraklat', 'i', () => guncEylem('guncelleme_duraklat'))
                                     : dugme('gunc-devam', 'Devam', 'd', () => guncEylem('guncelleme_surdur')),
           dugme('gunc-iptal', 'İptal', 't', () => guncEylem('guncelleme_iptal')))];
    case 'dogrulaniyor':
      return [h('b', { id: 'gunc-baslik' }, 'İndirme tamamlandı; SHA-256 özeti doğrulanıyor…')];
    case 'hazir':
      return [h('b', { id: 'gunc-baslik' }, `Sürüm ${d.surum} indirildi ve SHA-256 özeti SHA256SUMS.txt ile doğrulandı. Şimdi kurmak ister misin?`),
        h('div', { class: 'soluk' }, 'Kimlik Merkezi kapanır, kurulum sessizce yapılır ve uygulama yeniden açılır. Veri klasörünüze dokunulmaz. ' +
          'Kurulum paketi imzasızdır; doğrulama yalnızca yayındaki SHA-256 özetiyle yapılır.'),
        ek(dugme('gunc-kur', 'Şimdi kur', 'd', () => guncEylem('guncelleme_kur', { onay: true })), dugme('gunc-sonra', 'Sonra', 'i', gizle))];
    case 'kuruluyor':
      return [h('b', { id: 'gunc-baslik' }, 'Kurulum başlatılıyor: Kimlik Merkezi kapanacak ve kurulumdan sonra yeniden açılacak.')];
    case 'hata':
      return [h('b', { id: 'gunc-baslik', class: 'kotu' }, 'Güncelleme tamamlanamadı'), h('div', { id: 'gunc-hata' }, d.mesaj),
        ek(...(d.surum != null && d.hata_asama !== 'denetim' ? [dugme('gunc-yeniden', d.devam_edilebilir ? 'Kaldığı yerden dene' : 'Yeniden indir', 'd',
            () => guncEylem('guncelleme_indir', { onay: true }))] : []), dugme('gunc-kapat', 'Kapat', 'i', () => { GUNC.gizli = d.surum; GUNC.elle = false; guncCiz(); }))];
    default: return [];
  }
}
function guncCiz() {
  const d = GUNC.d, k = $('#guncelleme-kutu');
  if (!d || !k) return;
  const ds = $('#ayar-gunc-durum');
  if (ds) ds.textContent = guncDurumMetni(d);
  if (!guncBannerGerekli(d)) { k.textContent = ''; GUNC.anahtar = null; return; }
  const anahtar = d.durum + ':' + d.surum + ':' + (d.mesaj || '');
  if (anahtar !== GUNC.anahtar) {
    k.textContent = '';
    k.append(h('div', { class: 'guncelleme' + (d.durum === 'hata' ? ' hata-kutu' : ''), role: 'region', 'aria-label': 'Güncelleme' }, ...guncKutuKur(d)));
    GUNC.anahtar = anahtar;
  }
  const p = $('#gunc-ilerleme'), m = $('#gunc-metin');
  if (p) p.value = d.yuzde;
  if (m) m.textContent = guncIlerlemeMetni(d);
}
async function guncYenile() {
  clearTimeout(GUNC.t);
  let d;
  try { d = await api('guncelleme_durum'); }
  catch (e) {
    if (GUNC.d && GUNC.d.durum === 'kuruluyor') {   // uygulama kapandı: kurulum sürüyor
      const k = $('#guncelleme-kutu');
      if (k) { k.textContent = ''; k.append(h('div', { class: 'guncelleme' }, h('b', { id: 'gunc-baslik' }, 'Kimlik Merkezi kapandı; kurulum sürüyor ve bitince uygulama yeniden açılacak. Bu sekmeyi kapatabilirsiniz.'))); }
    }
    return;
  }
  GUNC.d = d;
  guncCiz();
  if (GUNC_AKTIF.includes(d.durum)) GUNC.t = setTimeout(guncYenile, d.durum === 'indiriliyor' ? 400 : 800);
}
// Eski sürümden gelen kullanıcı: "ağa hiç çıkmaz" sözü değişti, bunu bir kez açıkça söyle (görmeden otomatik denetim yapılmaz).
function guncBilgiPenceresi() {
  const kapat = pencere('Yeni: güncelleme denetimi',
    h('p', {}, 'Bu sürümle birlikte Kimlik Merkezi, açılışta GitHub\'daki herkese açık sürüm listesine bakarak yeni bir sürüm olup olmadığını denetleyebilir. ' +
      'Gönderilen tek şey "yeni sürüm var mı" sorusudur (IP adresiniz GitHub tarafından görülür); sürümünüz, adınız ve verileriniz gönderilmez. ' +
      'Yeni sürüm bulunursa indirme ve kurulum yalnız sizin onayınızla yapılır.'),
    h('p', { class: 'soluk' }, 'Kapatırsanız uygulama internete hiç bağlanmaz. Bu seçimi Ayarlar\'dan istediğiniz zaman değiştirebilirsiniz.'),
    h('div', { class: 'satir' },
      h('button', { id: 'gunc-bilgi-acik', class: 'd', onclick: async () => { await api('guncelleme_bilgi', { otomatik: true }).catch(hataGoster); kapat(); guncYenile(); } }, 'Açık kalsın'),
      h('button', { id: 'gunc-bilgi-kapali', class: 'i', onclick: async () => { await api('guncelleme_bilgi', { otomatik: false }).catch(hataGoster); kapat(); } }, 'Kapat')));
}
function guncBaslat(ac) {
  if (ac && ac.guncelleme_bilgi_gerekli) guncBilgiPenceresi();
  guncYenile();
}
// Ayarlar sayfasındaki kart
function guncAyarKarti(s) {
  const oto = h('input', { type: 'checkbox', id: 'ayar-gunc-otomatik', checked: s.guncelleme_otomatik, onchange: async e => {
    await api('ayar_yaz', { guncelleme_otomatik: e.target.checked }).catch(hataGoster);
    bildir(e.target.checked ? 'Açılışta güncelleme denetimi açık.' : 'Açılışta güncelleme denetimi kapalı: uygulama internete bağlanmaz.'); } });
  const on = h('input', { type: 'checkbox', id: 'ayar-gunc-onsurum', checked: s.guncelleme_onsurum, onchange: async e => {
    await api('ayar_yaz', { guncelleme_onsurum: e.target.checked }).catch(hataGoster); } });
  const durum = h('div', { id: 'ayar-gunc-durum', class: 'soluk' }, GUNC.d ? guncDurumMetni(GUNC.d) : '');
  return h('div', { class: 'kart', id: 'ayar-guncelleme' }, h('h3', {}, 'Güncellemeler'),
    h('div', {}, `Kurulu sürüm: ${s.surum}`),
    h('div', { class: 'satir' }, h('label', {}, oto, ' Açılışta yeni sürümü denetle (varsayılan: açık)')),
    h('div', { class: 'satir' }, h('label', {}, on, ' Ön sürümleri de dikkate al')),
    h('div', { class: 'satir' }, h('button', { id: 'ayar-gunc-denetle', class: 'i', onclick: () => { GUNC.elle = true; GUNC.gizli = null; GUNC.anahtar = null; guncEylem('guncelleme_denetle'); } }, 'Güncellemeleri denetle'), durum),
    h('p', { class: 'soluk' }, 'Denetim yalnız GitHub\'daki herkese açık sürüm listesini sorar; IP adresiniz GitHub tarafından görülür, ancak sürümünüz, adınız ya da verileriniz gönderilmez. ' +
      'Bu, uygulamanın internete çıkan TEK yoludur; seçenek kapalıyken (ve düğmeye basmadığınız sürece) hiç bağlanmaz. Yeni sürüm bulunursa indirme ve kurulum yalnız sizin onayınızla yapılır.'));
}
