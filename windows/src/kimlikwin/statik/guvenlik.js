/* Güvenlik sayfası, açılış kilit ekranı ve parola isteme penceresi.
   index.html'deki satır içi betikten SONRA çağrılır; h, api, pencere, bildir, hataGoster, $, git, start genel
   adlarını çağrı anında kullanır. Bu dosyadaki üst düzey adlar G/g ile başlar (çakışmasın).
   Parola ve kurtarma ifadesi: yalnız <input type=password> içinde ve istek gövdesinde bulunur; sayfa
   durumuna, localStorage'a, URL'ye, bildirimlere ya da hata raporuna ASLA yazılmaz. */
"use strict";

const G_KURAL_IFADE = 'Kurtarma ifadesi: en az 4 kelime ya da 20 karakter olsun; kısa, tahmin edilebilir ya da "gizli soru" '
  + 'cevabı gibi şeyler yazmayın. Kendi seçtiğiniz, başkasının bilemeyeceği uzun bir cümle iyidir.';
const G_KURAL_PAROLA = 'Parola: en az 10 karakter, en az 5 farklı karakter; kolay tahmin edilen bir parola ya da kurtarma ifadenizle aynı olamaz.';
const G_ONAY_ETIKETI = 'Parolamı VE kurtarma ifademi ikisini birden unutursam verimin kimse tarafından kurtarılamayacağını anladım.';
const G_ONAY_ETIKETI_MCP = 'Ayrıca parolayla Claude\'un (MCP) bu klasöre otomatik erişemeyeceğini anladım.';

function gGizliGirdi(id, etiket) {
  return h('input', { type: 'password', id, autocomplete: 'off', spellcheck: 'false', 'aria-label': etiket, style: 'max-width:420px;width:100%' });
}
function gGosterKutusu(...girdiler) {
  return h('label', { class: 'soluk' }, h('input', { type: 'checkbox', onchange: e => girdiler.forEach(g => { g.type = e.target.checked ? 'text' : 'password'; }) }), ' Yazdıklarımı göster');
}
function gCubuk(guc) {
  const t = { 'zayıf': [25, 'var(--tehlike)'], 'orta': [55, 'var(--uyari)'], 'iyi': [80, 'var(--ok)'], 'güçlü': [100, 'var(--ok)'] }[guc] || [0, 'var(--cizgi)'];
  const i = h('i', { style: `display:block;height:100%;width:${t[0]}%;background:${t[1]}` });
  return h('div', { style: 'height:8px;border-radius:4px;background:var(--cizgi);overflow:hidden;max-width:420px', 'aria-hidden': 'true' }, i);
}
const gNorm = s => s.normalize('NFKC').trim().split(/\s+/).join(' ').toLocaleLowerCase('tr');

/* Kurtarma ifadesi alanı: iki kutu, canlı kural/güç göstergesi (çekirdekteki doğrulayıcı sunucuda çalışır). */
function gIfadeAlani(degisti) {
  const a = gGizliGirdi('g-ifade', 'Kurtarma ifadesi'), b = gGizliGirdi('g-ifade2', 'Kurtarma ifadesini tekrar yazın');
  const sorun = h('div', { id: 'g-ifade-sorun', 'aria-live': 'polite' }), guc = h('div', { id: 'g-ifade-guc', class: 'soluk' }), cubuk = h('div', {});
  const durum = { uygun: false, esit: false, ifade: () => a.value, tekrar: () => b.value, gecerli: () => durum.uygun && durum.esit };
  let sayac = 0;
  const guncelle = async () => {
    const n = ++sayac;
    let r = null;
    if (a.value) r = await api('guvenlik_ifade_degerlendir', { ifade: a.value }).catch(() => null);
    if (n !== sayac) return;
    sorun.textContent = ''; guc.textContent = ''; cubuk.textContent = '';
    durum.uygun = !!(r && r.uygun);
    if (r) {
      r.sorunlar.forEach(s => sorun.append(h('div', { class: 'kotu' }, '✗ ' + s)));
      guc.textContent = `Güç göstergesi (sezgisel, kesin ölçüm değil): ${r.guc} · ${r.kelime} kelime, ${r.karakter} karakter`;
      cubuk.append(gCubuk(r.guc));
    }
    durum.esit = !!a.value && gNorm(a.value) === gNorm(b.value);
    if (r && r.uygun && !b.value) sorun.append(h('div', { class: 'soluk' }, 'Aynı ifadeyi ikinci kutuya da yazın (yazım hatasını yakalamak için).'));
    else if (r && r.uygun && !durum.esit) sorun.append(h('div', { class: 'kotu' }, '✗ İki giriş aynı değil.'));
    else if (durum.gecerli()) sorun.append(h('div', { class: 'tamam' }, '✓ Kurallara uyuyor ve iki giriş aynı.'));
    degisti();
  };
  a.addEventListener('input', guncelle); b.addEventListener('input', guncelle);
  durum.kap = h('div', {}, h('p', { class: 'soluk' }, G_KURAL_IFADE),
    h('div', { class: 'satir' }, a), h('div', { class: 'satir' }, b), gGosterKutusu(a, b), cubuk, guc, sorun);
  durum.temizle = () => { a.value = ''; b.value = ''; };
  return durum;
}

/* Parola alanı: iki kutu + çekirdek kuralları. */
function gParolaAlani(degisti, ad = 'g-parola') {
  const a = gGizliGirdi(ad, 'Parola'), b = gGizliGirdi(ad + '2', 'Parolayı tekrar yazın');
  const sorun = h('div', { id: ad + '-sorun', 'aria-live': 'polite' });
  const durum = { uygun: false, esit: false, parola: () => a.value, tekrar: () => b.value, gecerli: () => durum.uygun && durum.esit };
  let sayac = 0;
  const guncelle = async () => {
    const n = ++sayac;
    const r = a.value ? await api('guvenlik_parola_degerlendir', { parola: a.value }).catch(() => null) : null;
    if (n !== sayac) return;
    sorun.textContent = '';
    durum.uygun = !!(r && r.uygun);
    durum.esit = !!a.value && a.value === b.value;
    if (r) r.sorunlar.forEach(s => sorun.append(h('div', { class: 'kotu' }, '✗ ' + s)));
    if (r && r.uygun && !b.value) sorun.append(h('div', { class: 'soluk' }, 'Parolayı ikinci kutuya da yazın.'));
    else if (r && r.uygun && !durum.esit) sorun.append(h('div', { class: 'kotu' }, '✗ İki giriş aynı değil.'));
    else if (durum.gecerli()) sorun.append(h('div', { class: 'tamam' }, '✓ Kurallara uyuyor ve iki giriş aynı.'));
    degisti();
  };
  a.addEventListener('input', guncelle); b.addEventListener('input', guncelle);
  durum.kap = h('div', {}, h('p', { class: 'soluk' }, G_KURAL_PAROLA), h('div', { class: 'satir' }, a), h('div', { class: 'satir' }, b), gGosterKutusu(a, b), sorun);
  return durum;
}

function gHataKutusu() { return h('div', { class: 'hata', id: 'g-hata', style: 'display:none', role: 'alert' }); }
function gHataYaz(kutu, e) {
  kutu.textContent = (e && e.mesaj) || String(e);
  kutu.style.display = '';
}

/* ------------------------------------------------------------------ parola isteme penceresi (kişi değiştirme, kişi ekleme, sihirbaz) */
function gParolaSor(baslik, aciklama) {
  return new Promise(coz => {
    const p = gGizliGirdi('g-sor-parola', 'Parola'), hata = gHataKutusu();
    const tamam = h('button', { class: 'd', id: 'g-sor-tamam', onclick: () => { const v = p.value; p.value = ''; k(); coz(v); } }, 'Aç');
    const k = pencere(baslik || 'Parola gerekli', h('p', {}, aciklama || 'Bu veri klasörü parolayla korunuyor.'), h('div', { class: 'satir' }, p), gGosterKutusu(p), hata,
      h('div', { class: 'satir' }, tamam, h('button', { class: 'i', onclick: () => { p.value = ''; k(); coz(null); } }, 'Vazgeç')));
    p.addEventListener('keydown', e => { if (e.key === 'Enter') tamam.click(); });
    p.focus();
  });
}
/* fn(parola|null) çağrılır; sunucu 'parola_gerekli' derse parola sorulur, yanlışsa tekrar sorulur. */
async function gParolaIleDene(fn, aciklama) {
  try { return await fn(null); } catch (e) {
    if (!e || e.kod !== 'parola_gerekli') throw e;
  }
  for (;;) {
    const p = await gParolaSor('Parola gerekli', aciklama);
    if (p == null) throw { mesaj: 'Parola girilmedi; işlem iptal edildi.', iptal: true };
    try { return await fn(p); } catch (x) {
      if (x && (x.kod === 'yanlis_parola' || x.kod === 'cok_deneme')) { bildir(x.mesaj, true); continue; }
      throw x;
    }
  }
}

/* ------------------------------------------------------------------ açılış kilit ekranı */
function gKilitEkrani(kilit) {
  const k = $('#kok-pencere'); k.textContent = '';
  const parolaModu = kilit.tur === 'parola';
  const hata = gHataKutusu(), p = gGizliGirdi('g-kilit-parola', 'Parola');
  let bekleme = null;
  const ac = h('button', { class: 'd', id: 'g-kilit-ac' }, 'Aç');
  const sayim = sn => {
    clearInterval(bekleme); let kalan = sn;
    const yaz = () => { ac.disabled = kalan > 0; ac.textContent = kalan > 0 ? `Bekleyin (${kalan} sn)` : 'Aç'; };
    yaz(); bekleme = setInterval(() => { kalan--; yaz(); if (kalan <= 0) clearInterval(bekleme); }, 1000);
  };
  const hatayi = e => {
    gHataYaz(hata, e);
    if (e && e.kod === 'cok_deneme' && e.ek) sayim(parseInt(e.ek, 10) || 1);
    else if (e && e.kod === 'yanlis_parola' && e.ek) sayim(parseInt(e.ek, 10) || 1);
  };
  const bitti = async () => { clearInterval(bekleme); k.textContent = ''; await start(); };
  ac.onclick = async () => {
    hata.style.display = 'none'; const v = p.value; ac.disabled = true;
    try { await api('parola_ac', { parola: v }); p.value = ''; await bitti(); } catch (e) { hatayi(e); p.value = ''; if (!bekleme || ac.textContent === 'Aç') ac.disabled = false; p.focus(); }
  };
  p.addEventListener('keydown', e => { if (e.key === 'Enter' && !ac.disabled) ac.click(); });

  // kurtarma ifadesiyle aç
  const ifade = gGizliGirdi('g-kilit-ifade', 'Kurtarma ifadesi'), yeni = gParolaAlani(() => kurDugme(), 'g-kilit-yeni');
  const modYeni = h('input', { type: 'radio', name: 'g-kilit-mod', id: 'g-kilit-mod-yeni', checked: true });
  const modHesap = h('input', { type: 'radio', name: 'g-kilit-mod', id: 'g-kilit-mod-hesap' });
  const yeniKap = h('div', {}, yeni.kap);
  const kurHata = gHataKutusu();
  const kurDugme = () => { kur.disabled = !ifade.value || (modYeni.checked && !yeni.gecerli()); yeniKap.style.display = modYeni.checked ? '' : 'none'; };
  [modYeni, modHesap].forEach(m => m.addEventListener('change', kurDugme)); ifade.addEventListener('input', kurDugme);
  const kur = h('button', { class: 'd', id: 'g-kilit-kurtar', disabled: true, onclick: async () => {
    kurHata.style.display = 'none'; kur.disabled = true;
    const g = { ifade: ifade.value };
    if (modYeni.checked) { g.yeni_parola = yeni.parola(); g.yeni_parola_tekrar = yeni.tekrar(); }
    try { await api('kilit_kurtar', g); ifade.value = ''; await bitti(); } catch (e) { gHataYaz(kurHata, e); if (e && e.ek) { /* yavaşlatma */ } kurDugme(); }
  } }, 'Kurtarma ifadesiyle aç');
  const kurtarmaKutusu = h('div', { id: 'g-kilit-kurtarma', style: parolaModu ? 'display:none' : '' },
    h('p', {}, 'Kurtarma ifadenizi yazın. İsterseniz yeni bir parola belirlersiniz; ya da parolasız, yalnız bu Windows hesabına bağlı şifrelemeye dönersiniz.'),
    h('div', { class: 'satir' }, ifade), gGosterKutusu(ifade),
    h('div', { class: 'satir' }, h('label', {}, modYeni, ' Yeni parola belirle'), h('label', {}, modHesap, ' Parolasız: yalnız bu Windows hesabıma bağla')),
    yeniKap, kurHata, h('div', { class: 'satir' }, kur));
  const ayrac = h('button', { class: 'i', id: 'g-kilit-unuttum', onclick: () => { kurtarmaKutusu.style.display = kurtarmaKutusu.style.display === 'none' ? '' : 'none'; } }, 'Parolamı unuttum');
  k.append(h('div', { class: 'yer', style: 'background:var(--bg)' }, h('div', { class: 'pencere', role: 'dialog' },
    h('h2', {}, 'Kimlik Merkezi kilitli'),
    parolaModu
      ? [h('p', {}, (kilit.kisi ? `"${kilit.kisi}" ` : '') + 'verisi parolayla korunuyor. Devam etmek için parolanızı yazın.'),
         h('div', { class: 'satir' }, p), gGosterKutusu(p), hata, h('div', { class: 'satir' }, ac, kilit.kurtarma_var ? ayrac : null)]
      : [h('p', { class: 'uyari' }, 'Bu veri klasörü başka bir Windows hesabıyla ya da bilgisayarla şifrelenmiş; bu hesapta anahtarı açılamıyor. Kurtarma ifadenizle açabilirsiniz.')],
    kilit.kurtarma_var ? kurtarmaKutusu : h('p', { class: 'hata' }, 'Kurtarma ifadesi kurulu değil; parolayı unutursanız veriye ulaşılamaz.'))));
  p.focus();
}

/* ------------------------------------------------------------------ Güvenlik sayfası */
function gRozet(metin, tur) { return h('span', { class: 'rozet' + (tur === 'k' ? ' h' : ''), style: tur === 'i' ? 'border-color:var(--ok);color:var(--ok)' : '' }, metin); }
function gSatir(ad, ...icerik) { return h('div', { class: 'satir', style: 'margin:3px 0' }, h('b', { style: 'min-width:190px' }, ad), ...icerik); }

async function guvenlikSayfasi(a) {
  const d = await api('guvenlik_durum');
  a.append(h('h2', {}, 'Güvenlik'));
  if (d.donusum && d.donusum.durum === 'calisiyor') { gDonusumIzle(); return; }
  const durumKart = h('div', { class: 'kart', id: 'g-durum' }, h('h3', {}, 'Şifreleme durumu'),
    gSatir('Şifreleme', d.sifreli ? gRozet('açık', 'i') : gRozet('KAPALI', 'k')),
    gSatir('Anahtarı koruyan', d.sifreli ? (d.parola_var ? gRozet('parolanız') : gRozet(d.os_korumasi ? 'Windows hesabınız' : 'yok', d.os_korumasi ? '' : 'k')) : gRozet('-')),
    gSatir('Parola', d.parola_var ? gRozet('var', 'i') : gRozet('yok')),
    gSatir('Kurtarma ifadesi', d.kurtarma_var ? gRozet('kuruldu', 'i') : gRozet(d.sifreli ? 'KURULU DEĞİL' : '-', d.sifreli ? 'k' : '')),
    h('div', { class: 'soluk' }, 'Veri klasörü: ' + d.klasor));
  if (d.kapali_notu) durumKart.append(h('div', { class: 'hata' }, d.kapali_notu));
  if (!d.saglayici_var) durumKart.append(h('div', { class: 'uyari' }, 'Bu sistemde anahtar koruma sağlayıcısı (Windows DPAPI) yok; şifreleme açılamaz.'));
  else if (!d.gercek_koruma) durumKart.append(h('div', { class: 'uyari' }, 'Test amaçlı sahte anahtar sağlayıcısı kullanılıyor; gerçek koruma sağlamaz.'));
  if (d.ham_dosya_duz > 0) durumKart.append(h('div', { class: 'uyari' }, `${d.ham_dosya_duz} ham arşiv dosyası şifresiz kalmış. Şifrelemeyi kapatıp yeniden açmak bunu tamamlar.`));
  if (d.duz_kalintilar.length || d.eski_sifresiz_dosyalar.length) durumKart.append(h('div', { class: 'uyari' }, 'Düz metin kalıntı dosyalar var: ' + [...d.duz_kalintilar, ...d.eski_sifresiz_dosyalar].join(', ') + '.'));
  durumKart.append(h('div', { class: 'soluk', style: 'margin-top:8px' }, 'Şifrelenmeyenler: cikti klasörü ve dışa aktardığınız dosyalar. Aynı Windows hesabında çalışan kötü amaçlı bir program, parola yoksa anahtarı açtırabilir; parola bu riski azaltır. Ayrıntı: docs/SIFRELEME.md.'));
  a.append(durumKart);

  if (!d.sifreli) {
    a.append(h('div', { class: 'kart' }, h('h3', {}, 'Şifrelemeyi aç'),
      h('p', {}, 'Veritabanınız ve ham arşiv dosyalarınız şifrelenir; anahtar Windows hesabınıza bağlanır. Sonra isterseniz parola ekleyebilirsiniz.'),
      h('button', { class: 'd', id: 'g-sifrele', disabled: !d.saglayici_var, onclick: () => gDonusumPenceresi(d, 'ac') }, 'Şifrelemeyi aç…')));
  } else {
    a.append(h('div', { class: 'kart', id: 'g-kurtarma-kart' }, h('h3', {}, 'Kurtarma ifadesi'),
      h('p', {}, 'Parolayı unutursanız verinize dönmenin tek yolu. Parola eklemeden önce kurulması gerekir.'),
      h('p', { class: 'hata' }, d.uyari_kurtarma),
      h('button', { class: d.kurtarma_var ? 'i' : 'd', id: 'g-kurtarma-dugme', onclick: () => gAkis(d, 'kurtarma') }, d.kurtarma_var ? 'Kurtarma ifadesini değiştir…' : 'Kurtarma ifadesini kur…')));
    const pk = h('div', { class: 'kart', id: 'g-parola-kart' }, h('h3', {}, 'Parola'));
    if (!d.parola_var) {
      pk.append(h('p', {}, 'İsteğe bağlı. Parola eklenirse veri her açılışta parola ister ve Windows hesabına bağlı otomatik açılış kapanır; aynı hesaptaki başka bir program artık anahtarı kendiliğinden açtıramaz.'),
        h('div', { class: 'uyari' }, d.mcp_notu_ekle), d.claude_girisi_var ? h('div', { class: 'hata' }, 'Claude Desktop ayarında bir "kimlik-merkezi" girişi var; parola eklerseniz Claude bu klasöre erişemez hale gelir.') : null,
        h('button', { class: 'd', id: 'g-parola-ekle', onclick: () => gAkis(d, 'parola') }, 'Parola ekle…'));
    } else {
      pk.append(h('p', {}, 'Veri her açılışta parola ister. Parola kaldırılırsa anahtar yeniden Windows hesabınıza bağlanır (kurtarma ifadeniz kalır).'),
        h('div', { class: 'satir' },
          h('button', { class: 'i', id: 'g-parola-kaldir', disabled: !d.saglayici_var, onclick: () => gParolaKaldirPenceresi() }, 'Parolayı kaldır…'),
          h('button', { class: 'i', id: 'g-parola-sifirla', onclick: () => gSifirlaPenceresi() }, 'Parolayı kurtarma ifadesiyle sıfırla…')));
    }
    a.append(pk);
    a.append(h('div', { class: 'kart' }, h('h3', {}, 'Şifrelemeyi kapat'),
      h('p', {}, 'Veri düz metne çevrilir ve anahtar dosyası silinir. Bu bilgisayara erişen herkes verinizi okuyabilir.'),
      h('button', { class: 't', id: 'g-kapat', onclick: () => gDonusumPenceresi(d, 'kapat') }, 'Şifrelemeyi kapat…')));
  }
  a.append(h('div', { class: 'kart', id: 'g-claude' }, h('h3', {}, 'Claude (MCP) ve parola'),
    h('p', {}, 'Claude gibi uygulamalar verinize ayrı bir süreçle bağlanır ve parola giremez. Bu yüzden parolalı klasör Claude\'a otomatik eklenmez; parolayı Claude\'un ayar dosyasına yazmak korumayı ortadan kaldırırdı. Claude erişimi istiyorsanız parolasız (Windows hesabına bağlı şifreli) kalın.')));
}

/* Parola ekleme / kurtarma kurma akışı: ifade -> uyarı+onay -> (parola). Adım değişince pencere yeniden çizilir;
   yazarken yalnız düğmenin açık/kapalı durumu güncellenir (kutular yeniden oluşturulmaz). */
function gAkis(d, mod) {
  const st = { adim: d.kurtarma_var && mod === 'parola' ? 'onay' : 'ifade', onay: false, mevcut: '', kurduk: false, guncelle: () => {} };
  const ifade = gIfadeAlani(() => st.guncelle());
  const parola = gParolaAlani(() => st.guncelle());
  const mevcutGirdi = gGizliGirdi('g-mevcut-parola', 'Mevcut parola');
  mevcutGirdi.addEventListener('input', () => { st.mevcut = mevcutGirdi.value; st.guncelle(); });
  const hata = gHataKutusu();
  const kapat = () => { st.mevcut = ''; mevcutGirdi.value = ''; ifade.temizle(); $('#kok-pencere').textContent = ''; git('guvenlik'); };
  const baslik = mod === 'parola' ? 'Parola ekle' : (d.kurtarma_var ? 'Kurtarma ifadesini değiştir' : 'Kurtarma ifadesini kur');
  const ciz = () => {
    hata.style.display = 'none';
    let govde, dugmeler;
    if (st.adim === 'ifade') {
      const ileri = h('button', { class: 'd', id: 'g-ileri', disabled: true, onclick: () => { st.adim = 'onay'; ciz(); } }, 'İleri');
      st.guncelle = () => { ileri.disabled = !ifade.gecerli(); };
      govde = [h('p', { class: 'soluk' }, mod === 'parola' ? '1/3 · Önce kurtarma ifadesi. Parolayı unutursanız verinize dönmenin tek yolu budur.' : 'Kurtarma ifadenizi seçin.'), ifade.kap];
      dugmeler = [ileri];
      setTimeout(st.guncelle, 0);
    } else if (st.adim === 'onay') {
      const mcpGerek = mod === 'parola';
      const gerekliParola = d.parola_var && mod === 'kurtarma';
      const onayKutusu = h('input', { type: 'checkbox', id: 'g-onay', checked: st.onay, onchange: e => { st.onay = e.target.checked; st.guncelle(); } });
      const devam = h('button', { class: 'd', id: 'g-devam', disabled: true, onclick: () => onayla(devam) }, mod === 'parola' ? 'Devam' : 'Kurtarma ifadesini kur');
      st.guncelle = () => { devam.disabled = !st.onay || (gerekliParola && !st.mevcut); };
      govde = [h('p', { class: 'soluk' }, mod === 'parola' ? (d.kurtarma_var ? '1/2' : '2/3') + ' · Uyarıyı okuyun ve onaylayın.' : 'Uyarıyı okuyun ve onaylayın.'),
        h('div', { class: 'hata', id: 'g-uyari' }, h('b', {}, 'KURTARILAMAZ. '), d.uyari_kurtarma),
        mcpGerek ? h('div', { class: 'uyari', id: 'g-mcp-uyari' }, d.mcp_notu_ekle) : null,
        gerekliParola ? h('div', {}, h('p', {}, 'Mevcut parolanızı yazın:'), h('div', { class: 'satir' }, mevcutGirdi)) : null,
        h('label', {}, onayKutusu, ' ' + G_ONAY_ETIKETI + (mcpGerek ? ' ' + G_ONAY_ETIKETI_MCP : '')), hata];
      dugmeler = [!(d.kurtarma_var && mod === 'parola') ? h('button', { class: 'i', id: 'g-geri', onclick: () => { st.adim = 'ifade'; ciz(); } }, 'Geri') : null, devam];
      st.guncelle();
    } else {
      const kaydet = h('button', { class: 'd', id: 'g-parola-kaydet', disabled: true, onclick: async () => {
        kaydet.disabled = true; hata.style.display = 'none';
        try { await api('guvenlik_parola_ekle', { parola: parola.parola(), parola_tekrar: parola.tekrar(), anladim: true }); kapat(); bildir('Parola eklendi. Veri artık her açılışta parola isteyecek.'); }
        catch (e) { gHataYaz(hata, e); st.guncelle(); }
      } }, 'Parolayı ekle');
      st.guncelle = () => { kaydet.disabled = !parola.gecerli(); };
      govde = [h('p', { class: 'soluk' }, '3/3 · Şimdi parolanızı belirleyin.'), st.kurduk ? h('div', { class: 'tamam', id: 'g-ifade-kuruldu' }, '✓ Kurtarma ifadesi kuruldu.') : null, parola.kap, hata];
      dugmeler = [kaydet];
    }
    pencere(baslik, ...govde, h('div', { class: 'satir' }, ...dugmeler, h('button', { class: 'i', id: 'g-vazgec', onclick: () => kapat() }, st.kurduk ? 'Şimdilik burada dur' : 'Vazgeç')));
  };
  const onayla = async dugme => {
    hata.style.display = 'none'; dugme.disabled = true;
    try {
      if (!d.kurtarma_var || mod === 'kurtarma') {
        await api('guvenlik_kurtarma_kur', { ifade: ifade.ifade(), ifade_tekrar: ifade.tekrar(), anladim: true, mevcut_parola: st.mevcut || null });
        st.kurduk = true; d = { ...d, kurtarma_var: true };
        ifade.temizle(); st.mevcut = ''; mevcutGirdi.value = '';
        if (mod === 'kurtarma') { kapat(); bildir('Kurtarma ifadesi kuruldu. Kâğıda yazıp güvenli bir yerde saklayın; bilgisayarda düz metin olarak tutmayın.'); return; }
      }
      st.adim = 'parola'; ciz();
    } catch (e) { gHataYaz(hata, e); st.guncelle(); }
  };
  ciz();
}

function gParolaKaldirPenceresi() {
  const p = gGizliGirdi('g-mevcut-parola', 'Mevcut parola'), hata = gHataKutusu();
  const dugme = h('button', { class: 'd', id: 'g-kaldir-onay', disabled: true, onclick: async () => {
    dugme.disabled = true; hata.style.display = 'none';
    try { await api('guvenlik_parola_kaldir', { mevcut_parola: p.value }); p.value = ''; k(); bildir('Parola kaldırıldı; anahtar yeniden Windows hesabınıza bağlandı.'); git('guvenlik'); }
    catch (e) { gHataYaz(hata, e); dugme.disabled = false; p.value = ''; }
  } }, 'Parolayı kaldır');
  p.addEventListener('input', () => { dugme.disabled = !p.value; });
  const k = pencere('Parolayı kaldır', h('p', {}, 'Veri artık parola sormadan, yalnız Windows hesabınıza bağlı anahtarla açılır. Kurtarma ifadeniz geçerli kalır. Claude (MCP) erişimi yeniden mümkün olur.'),
    h('p', {}, 'Mevcut parolanızı yazın:'), h('div', { class: 'satir' }, p), gGosterKutusu(p), hata,
    h('div', { class: 'satir' }, dugme, h('button', { class: 'i', onclick: () => { p.value = ''; k(); } }, 'Vazgeç')));
}

function gSifirlaPenceresi() {
  const ifade = gGizliGirdi('g-sifirla-ifade', 'Kurtarma ifadesi'), hata = gHataKutusu();
  const modYeni = h('input', { type: 'radio', name: 'g-sifirla-mod', id: 'g-sifirla-yeni', checked: true });
  const modHesap = h('input', { type: 'radio', name: 'g-sifirla-mod', id: 'g-sifirla-hesap' });
  const yeni = gParolaAlani(() => guncelle(), 'g-sifirla-parola');
  const yeniKap = h('div', {}, yeni.kap);
  const dugme = h('button', { class: 'd', id: 'g-sifirla-onay', disabled: true, onclick: async () => {
    dugme.disabled = true; hata.style.display = 'none';
    const g = { ifade: ifade.value };
    if (modYeni.checked) { g.yeni_parola = yeni.parola(); g.yeni_parola_tekrar = yeni.tekrar(); }
    try { const r = await api('guvenlik_kurtar', g); ifade.value = ''; k(); bildir(r.mod === 'parola' ? 'Yeni parola kuruldu.' : 'Parola kaldırıldı; veri yalnız Windows hesabınıza bağlı.'); git('guvenlik'); }
    catch (e) { gHataYaz(hata, e); guncelle(); }
  } }, 'Sıfırla');
  const guncelle = () => { dugme.disabled = !ifade.value || (modYeni.checked && !yeni.gecerli()); yeniKap.style.display = modYeni.checked ? '' : 'none'; };
  ifade.addEventListener('input', guncelle); [modYeni, modHesap].forEach(m => m.addEventListener('change', guncelle));
  const k = pencere('Parolayı kurtarma ifadesiyle sıfırla', h('p', {}, 'Kurtarma ifadenizi yazın. Eski parola geçersiz olur.'),
    h('div', { class: 'satir' }, ifade), gGosterKutusu(ifade),
    h('div', { class: 'satir' }, h('label', {}, modYeni, ' Yeni parola belirle'), h('label', {}, modHesap, ' Parolasız: yalnız Windows hesabıma bağla')),
    yeniKap, hata, h('div', { class: 'satir' }, dugme, h('button', { class: 'i', onclick: () => { ifade.value = ''; k(); } }, 'Vazgeç')));
}

/* Şifrelemeyi aç / kapat (veri yeniden yazılır). */
function gDonusumPenceresi(d, tur) {
  const kapat = tur === 'kapat';
  const onay = h('input', { type: 'checkbox', id: 'g-donus-onay' });
  const yaz = h('input', { type: 'text', id: 'g-donus-yaz', placeholder: d.kaldir_onay, autocomplete: 'off' });
  const mevcut = gGizliGirdi('g-mevcut-parola', 'Mevcut parola'), hata = gHataKutusu();
  const dugme = h('button', { class: kapat ? 't' : 'd', id: 'g-donus-basla', disabled: true, onclick: async () => {
    dugme.disabled = true; hata.style.display = 'none';
    try { await api('guvenlik_donustur_baslat', { tur, onay: yaz.value, mevcut_parola: mevcut.value || null }); mevcut.value = ''; gDonusumIzle(); }
    catch (e) { gHataYaz(hata, e); mevcut.value = ''; guncelle(); }
  } }, kapat ? 'Şifrelemeyi kapat' : 'Şifrelemeyi aç');
  const guncelle = () => { dugme.disabled = !onay.checked || (kapat && (yaz.value !== d.kaldir_onay || (d.parola_var && !mevcut.value))); };
  onay.addEventListener('change', guncelle); yaz.addEventListener('input', guncelle); mevcut.addEventListener('input', guncelle);
  const ortak = [h('p', { class: 'uyari' }, 'Bu işlem tüm veriyi yeniden yazar ve veri miktarına göre dakikalar sürebilir. Bitene kadar uygulamayı KAPATMAYIN ve bilgisayarı uykuya almayın; işlem sürerken uygulamanın diğer bölümleri kullanılamaz.'),
    h('p', {}, 'Claude Desktop gibi bu klasöre bağlı programları başlamadan önce kapatın. Önemli veriniz varsa önce veri klasörünün bir kopyasını (anahtar.json dahil) başka yere alın. İşlem yarıda kalırsa eski hâl korunur ve yeniden çalıştırılabilir; disk dolu olursa başlamadan hata verir.')];
  const k = pencere(kapat ? 'Şifrelemeyi kapat' : 'Şifrelemeyi aç',
    ...(kapat ? [h('div', { class: 'hata' }, 'Veri DÜZ METİN olarak diske yazılır; anahtar dosyası (parola ve kurtarma ifadesi dahil) silinir. Bu bilgisayarı, diski ya da yedeği ele geçiren herkes verinizi okuyabilir.'), ...ortak,
        d.parola_var ? h('div', {}, h('p', {}, 'Mevcut parolanızı yazın:'), h('div', { class: 'satir' }, mevcut)) : null,
        h('p', {}, `Onaylamak için ${d.kaldir_onay} yazın:`), h('div', { class: 'satir' }, yaz)]
      : [h('p', {}, 'Veriniz ve ham arşiv dosyalarınız şifrelenir; anahtar Windows hesabınıza bağlanır. Sonra Güvenlik sayfasından kurtarma ifadesi ve parola ekleyebilirsiniz. cikti klasörü ve dışa aktardığınız dosyalar şifrelenmez.'), ...ortak]),
    h('label', {}, onay, ' Yukarıdakileri okudum, devam etmek istiyorum.'), hata,
    h('div', { class: 'satir' }, dugme, h('button', { class: 'i', onclick: () => k() }, 'Vazgeç')));
}

async function gDonusumIzle() {
  const gorunum = () => {
    const ek = h('p', { id: 'g-donus-mesaj', 'aria-live': 'polite' }, 'Başlıyor...');
    pencere('Dönüştürülüyor…', h('p', { class: 'uyari' }, 'Lütfen bekleyin; uygulamayı kapatmayın. Bu işlem uzun sürebilir.'), h('progress', {}), ek);
    return ek;
  };
  let ek = gorunum();
  for (;;) {
    let s;
    try { s = await api('guvenlik_donusum_durum'); } catch (e) { await new Promise(r => setTimeout(r, 1500)); continue; }
    if (s.durum === 'calisiyor') { ek.textContent = s.mesaj; await new Promise(r => setTimeout(r, 800)); if (!document.body.contains(ek)) ek = gorunum(); continue; }
    const kapat = pencere(s.durum === 'bitti' ? 'Tamamlandı' : 'Dönüşüm yapılamadı',
      s.durum === 'bitti' ? h('p', { class: 'tamam', id: 'g-donus-sonuc' }, 'İşlem tamamlandı.') : h('div', { class: 'hata', id: 'g-donus-sonuc' }, s.hata || 'Bilinmeyen hata.'),
      s.durum === 'hata' ? h('p', {}, 'Veriniz bu işlemden önceki hâlinde korunmuş olmalıdır; Güvenlik sayfasından durumu kontrol edin.') : null,
      h('div', { class: 'satir' }, h('button', { class: 'd', id: 'g-donus-tamam', onclick: () => { kapat(); git('guvenlik'); } }, 'Tamam')));
    return;
  }
}
