/* Persona Haritası: HUD figür + etkileşimli keşif paneli (ECharts, yerel dosya, CDN yok).
   index.html'deki küresel yardımcıları kullanır: h, api, bildir, hataGoster, pencere, git, KISILER, kopyala. */
"use strict";
(function(){
const SAYI=n=>Number(n).toLocaleString('tr-TR');
const ONDALIK=n=>Number(n).toLocaleString('tr-TR',{maximumFractionDigits:1});
const AY=['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'];
const AYK=['Oca','Şub','Mar','Nis','May','Haz','Tem','Ağu','Eyl','Eki','Kas','Ara'];
const GUN=['Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi','Pazar'];
const GUNK=['Pzt','Sal','Çar','Per','Cum','Cmt','Paz'];
const DIM_AD={ay:'Ay',gun:'Gün',saat:'Saat',kanal:'Kanal',video:'Video',tur:'Tür',terim:'Terim',site:'Site',sanatci:'Sanatçı',parca:'Parça',subreddit:'Subreddit',depo:'Depo',dosya_turu:'Dosya türü',kategori:'Kategori',uygulama:'Uygulama',yer:'Yer',platform:'Platform'};
const HAP_AD={bas:'Baş',goz:'Gözler',kulak:'Kulaklar',agiz:'Ağız',el:'Eller',kalp:'Kalp',karin:'Karın',ayak:'Ayaklar',ic:'Merkez',zihin:'Zihin'};
const HASSAS=['kalp','karin','ayak','zihin'];
const HAREKET_AZ=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
const dimAd=k=>DIM_AD[k]||k;
function degerMetin(k,v){if(k==='ay'){const [y,m]=String(v).split('-');return `${AY[+m-1]} ${y}`;}if(k==='gun')return GUN[+v]||v;if(k==='saat')return String(v).padStart(2,'0')+':00';return String(v);}
function tarihMetin(ts){if(!ts)return '-';const d=new Date(ts);if(isNaN(d))return ts;return d.toLocaleString('tr-TR',{day:'numeric',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'UTC'});}
function gunMetin(ts){if(!ts)return '-';const d=new Date(ts);return isNaN(d)?ts:d.toLocaleDateString('tr-TR',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});}
function ayEtiket(a){const [y,m]=a.split('-');return `${AYK[+m-1]} ${y.slice(2)}`;}

// ------------------------------------------------------------------ durum
const HS={bolge:null,filtre:{},aralik:{tip:'tumu',baslangic:null,bitis:null},kayit:null,grup:null,karsilastir:null,veri:null,baz:null,kayitlar:null,kayitSayfa:0,harita:null,yukleme:0};
window.HARITA_DURUM=HS;
let GRAFIKLER=[];          // canlı ECharts örnekleri
let GOZLEM=null;

// ------------------------------------------------------------------ renkler (CSS değişkenlerinden)
function hex(c){c=(c||'').trim();if(c[0]==='#')return c.length===4?'#'+[...c.slice(1)].map(x=>x+x).join(''):c.slice(0,7);
  const m=c.match(/rgba?\(([^)]+)\)/);if(!m)return '#7f95b0';const [r,g,b]=m[1].split(',').map(x=>parseFloat(x));return '#'+[r,g,b].map(x=>Math.round(x).toString(16).padStart(2,'0')).join('');}
function R(){const cs=getComputedStyle(document.documentElement),g=n=>hex(cs.getPropertyValue(n));
  return {v:g('--vurgu'),v2:g('--vurgu2'),amber:g('--amber'),yazi:g('--yazi'),soluk:g('--soluk'),cizgi:g('--cizgi'),panel:g('--panel'),bg:g('--bg'),
    palet:[g('--c1'),g('--c2'),g('--c3'),g('--c4'),g('--c5'),g('--c6'),g('--c7'),g('--c8')]};}
function temel(r){return {backgroundColor:'transparent',textStyle:{fontFamily:'"Segoe UI",system-ui,sans-serif',color:r.soluk},
  animation:!HAREKET_AZ,animationDuration:800,animationEasing:'cubicOut',animationDurationUpdate:350,
  tooltip:{backgroundColor:r.panel,borderColor:r.v,borderWidth:1,padding:[8,12],textStyle:{color:r.yazi,fontSize:13},extraCssText:'box-shadow:0 8px 30px rgba(0,0,0,.45);border-radius:10px;backdrop-filter:blur(6px)'}};}
const gradyan=(c,a1,a2)=>new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:c+a1},{offset:1,color:c+a2}]);
function hexA(c,a){return c+Math.round(a*255).toString(16).padStart(2,'0');}   // '#rrggbb' + alfa
function yuzde(v,top){return top?` (%${ONDALIK(100*v/top)})`:'';}

// ------------------------------------------------------------------ grafik kurucular
function grafikKur(g,r,tikla,baz){
  const sec=g.secili,top=g.degerler.flat?g.degerler.flat().reduce((a,b)=>a+b,0):0;
  const o=temel(r);
  const dim=(Array.isArray(g.boyut)?g.boyut[0]:g.boyut);
  const soluklastir=(i,adlar)=>sec==null||adlar[i]==sec;
  if(g.tur==='zaman'){
    const x=g.etiketler.map(ayEtiket);
    const seri=[{name:'Seçili',type:'line',data:g.degerler,smooth:.35,showSymbol:false,symbolSize:7,lineStyle:{width:2.6,color:r.v,shadowBlur:12,shadowColor:hexA(r.v,.6)},
      itemStyle:{color:r.v},areaStyle:{color:gradyan(r.v,'66','03')},emphasis:{focus:'series'},
      markLine:sec?{symbol:'none',silent:true,lineStyle:{color:r.amber,type:'dashed'},label:{formatter:degerMetin('ay',sec),color:r.amber},data:[{xAxis:g.etiketler.indexOf(sec)}]}:undefined}];
    if(baz){const d=new Map(baz.etiketler.map((e,i)=>[e,baz.degerler[i]]));
      seri.unshift({name:'Tüm kayıtlar',type:'line',data:g.etiketler.map(e=>d.get(e)||0),smooth:.35,showSymbol:false,lineStyle:{width:1.5,type:'dashed',color:r.soluk},areaStyle:{color:hexA(r.soluk,.07)},z:1});}
    Object.assign(o,{grid:{left:44,right:16,top:baz?34:16,bottom:62},
      legend:baz?{top:0,right:8,textStyle:{color:r.soluk},icon:'roundRect',itemWidth:14,itemHeight:4,inactiveColor:r.cizgi}:undefined,
      tooltip:{...o.tooltip,trigger:'axis',axisPointer:{type:'line',lineStyle:{color:r.v}},formatter:p=>`<b>${degerMetin('ay',g.etiketler[p[0].dataIndex])}</b><br>`+p.map(q=>`${q.marker} ${q.seriesName}: <b>${SAYI(q.value)}</b>`).join('<br>')},
      xAxis:{type:'category',data:x,boundaryGap:false,axisLine:{lineStyle:{color:r.cizgi}},axisTick:{show:false},axisLabel:{color:r.soluk,interval:Math.max(0,Math.ceil(x.length/9)-1)}},
      yAxis:{type:'value',splitNumber:3,axisLabel:{color:r.soluk,formatter:v=>SAYI(v)},splitLine:{lineStyle:{color:hexA(r.cizgi,.5),type:'dashed'}}},
      dataZoom:[{type:'inside',zoomOnMouseWheel:true,moveOnMouseMove:false,moveOnMouseWheel:false},
        {type:'slider',height:16,bottom:8,borderColor:'transparent',backgroundColor:hexA(r.cizgi,.25),fillerColor:hexA(r.v,.22),handleSize:'110%',
         handleStyle:{color:r.v,borderColor:r.v},moveHandleStyle:{color:r.v},dataBackground:{lineStyle:{color:r.soluk,opacity:.3},areaStyle:{color:r.soluk,opacity:.08}},selectedDataBackground:{lineStyle:{color:r.v},areaStyle:{color:r.v,opacity:.2}},textStyle:{color:r.soluk}}],
      brush:{xAxisIndex:0,brushType:'lineX',brushMode:'single',transformable:true,brushStyle:{color:hexA(r.amber,.16),borderColor:r.amber,borderWidth:1}},
      series:seri});
    return {o,init(c){c.dispatchAction({type:'takeGlobalCursor',key:'brush',brushOption:{brushType:'lineX',brushMode:'single'}});
      c.on('click',p=>{if(p.componentType==='series'&&tikla.deger)tikla.deger('ay',g.etiketler[p.dataIndex]);});
      c.on('brushEnd',p=>{const a=p.areas&&p.areas[0];if(!a||!a.coordRange)return;const [i,j]=a.coordRange.map(Math.round);
        const i0=Math.max(0,Math.min(i,j)),j0=Math.min(g.etiketler.length-1,Math.max(i,j));
        if(tikla.aralik)tikla.aralik(g.etiketler[i0],g.etiketler[j0]);c.dispatchAction({type:'brush',areas:[]});});}};
  }
  if(g.tur==='cubuk'){
    const n=g.etiketler.length,sirali=!!g.sirali,etiketler=g.etiketler,toplam=g.degerler.reduce((a,b)=>a+b,0);
    const yatay=!sirali;
    const veri=g.degerler.map((v,i)=>({value:v,itemStyle:{borderRadius:yatay?[0,7,7,0]:[7,7,0,0],opacity:soluklastir(i,etiketler)?1:.28,
      color:new echarts.graphic.LinearGradient(yatay?0:0,yatay?0:1,yatay?1:0,0,[{offset:0,color:hexA(r.v,.45)},{offset:1,color:r.v}])}}));
    const kat={type:'category',data:etiketler,inverse:yatay,axisTick:{show:false},axisLine:{lineStyle:{color:r.cizgi}},
      axisLabel:{color:r.yazi,width:yatay?112:undefined,overflow:'truncate',interval:0}};
    Object.assign(o,{grid:yatay?{left:122,right:54,top:6,bottom:6}:{left:34,right:8,top:18,bottom:24},
      tooltip:{...o.tooltip,trigger:'item',formatter:p=>`<b>${p.name}</b><br>${SAYI(p.value)} kayıt${yuzde(p.value,toplam)}`},
      xAxis:yatay?{type:'value',show:false}:kat,yAxis:yatay?kat:{type:'value',splitNumber:3,axisLabel:{color:r.soluk,formatter:SAYI},splitLine:{lineStyle:{color:hexA(r.cizgi,.5),type:'dashed'}}},
      series:[{type:'bar',data:veri,barWidth:yatay?Math.min(16,Math.floor(220/n)):'52%',showBackground:yatay,backgroundStyle:{color:hexA(r.cizgi,.28),borderRadius:[0,7,7,0]},
        label:yatay?{show:true,position:'right',color:r.soluk,formatter:p=>SAYI(p.value)}:{show:false},emphasis:{itemStyle:{shadowBlur:14,shadowColor:hexA(r.v,.6)}}}]});
    return {o,init(c){c.on('click',p=>{if(tikla.deger&&dim)tikla.deger(dim,dim==='gun'?p.dataIndex:etiketler[p.dataIndex]);});}};
  }
  if(g.tur==='pasta'){
    const toplam=g.degerler.reduce((a,b)=>a+b,0);
    const veri=g.etiketler.map((e,i)=>({name:e,value:g.degerler[i],itemStyle:{color:r.palet[i%r.palet.length],opacity:soluklastir(i,g.etiketler)?1:.3}}));
    Object.assign(o,{legend:{type:'scroll',bottom:0,left:'center',textStyle:{color:r.soluk},icon:'circle',itemWidth:8,itemHeight:8,inactiveColor:r.cizgi,pageIconColor:r.v,pageTextStyle:{color:r.soluk}},
      tooltip:{...o.tooltip,trigger:'item',formatter:p=>`${p.marker} <b>${p.name}</b><br>${SAYI(p.value)}${yuzde(p.value,toplam)}`},
      graphic:[{type:'text',left:'center',top:'36%',style:{text:SAYI(toplam),fill:r.yazi,fontSize:24,fontWeight:700,textAlign:'center'}},{type:'text',left:'center',top:'47%',style:{text:'kayıt',fill:r.soluk,fontSize:12,textAlign:'center'}}],
      series:[{type:'pie',radius:['46%','70%'],center:['50%','42%'],padAngle:2,itemStyle:{borderRadius:7,borderColor:r.panel,borderWidth:2},label:{show:false},
        emphasis:{scaleSize:6,itemStyle:{shadowBlur:18,shadowColor:hexA(r.v,.5)}},data:veri}]});
    return {o,init(c){c.on('click',p=>{if(tikla.deger&&dim)tikla.deger(dim,p.name);});}};
  }
  if(g.tur==='saat'){
    const mx=Math.max(1,...g.degerler);
    const veri=g.degerler.map((v,i)=>({value:v,itemStyle:{opacity:sec==null||+sec===i?1:.3,color:v===mx?r.amber:r.v}}));
    Object.assign(o,{polar:{radius:['16%','90%'],center:['50%','52%']},
      tooltip:{...o.tooltip,trigger:'item',formatter:p=>`<b>${String(p.dataIndex).padStart(2,'0')}:00 – ${String(p.dataIndex).padStart(2,'0')}:59</b><br>${SAYI(p.value)} kayıt${yuzde(p.value,top)}`},
      angleAxis:{type:'category',data:g.etiketler,startAngle:90,clockwise:true,axisLabel:{color:r.soluk,interval:2,fontSize:10},axisLine:{lineStyle:{color:r.cizgi}},axisTick:{show:false},splitLine:{show:true,lineStyle:{color:hexA(r.cizgi,.4)}}},
      radiusAxis:{show:false,max:mx*1.05},
      series:[{type:'bar',coordinateSystem:'polar',data:veri,itemStyle:{borderRadius:3},emphasis:{itemStyle:{shadowBlur:12,shadowColor:hexA(r.v,.7)}}}]});
    return {o,init(c){c.on('click',p=>{if(tikla.deger)tikla.deger('saat',p.dataIndex);});}};
  }
  if(g.tur==='hafta'){
    let m=g.degerler;if(!Array.isArray(m[0]))m=[m];
    const veri=[];m.forEach((satir,gi)=>satir.forEach((v,hi)=>veri.push([hi,gi,v])));
    const mx=Math.max(1,...m.flat());const sg=g.secili&&g.secili.gun!=null?+g.secili.gun:null,ss=g.secili&&g.secili.saat!=null?+g.secili.saat:null;
    Object.assign(o,{grid:{left:36,right:8,top:6,bottom:40},
      tooltip:{...o.tooltip,trigger:'item',formatter:p=>`<b>${GUN[p.value[1]]||''} ${String(p.value[0]).padStart(2,'0')}:00</b><br>${SAYI(p.value[2])} kayıt`},
      xAxis:{type:'category',data:[...Array(24).keys()].map(h=>String(h).padStart(2,'0')),splitArea:{show:false},axisLine:{show:false},axisTick:{show:false},axisLabel:{color:r.soluk,interval:2,fontSize:10}},
      yAxis:{type:'category',data:GUNK.slice(0,m.length),inverse:true,axisLine:{show:false},axisTick:{show:false},axisLabel:{color:r.soluk}},
      visualMap:{min:0,max:mx,calculable:false,orient:'horizontal',left:'center',bottom:0,itemWidth:10,itemHeight:140,text:['çok','az'],textStyle:{color:r.soluk,fontSize:10},inRange:{color:[hexA(r.v,.06),hexA(r.v,.35),r.v,r.amber]}},
      series:[{type:'heatmap',data:veri.map(d=>({value:d,itemStyle:(sg===d[1]&&ss===d[0])||(sg===d[1]&&ss==null)||(sg==null&&ss===d[0])?{borderColor:r.yazi,borderWidth:2}:undefined})),
        itemStyle:{borderRadius:3,borderColor:r.panel,borderWidth:1.5},emphasis:{itemStyle:{borderColor:r.yazi,borderWidth:2,shadowBlur:10,shadowColor:r.v}}}]});
    return {o,init(c){c.on('click',p=>{if(tikla.coklu)tikla.coklu({gun:p.value[1],saat:p.value[0]});});}};
  }
  if(g.tur==='agac'){
    const veri=g.etiketler.map((e,i)=>({name:e,value:g.degerler[i],itemStyle:{color:hexA(r.palet[i%4===0?0:i%4],.75),borderColor:r.panel,opacity:soluklastir(i,g.etiketler)?1:.3}}));
    Object.assign(o,{tooltip:{...o.tooltip,formatter:p=>`<b>${p.name}</b><br>${SAYI(p.value)} arama`},
      series:[{type:'treemap',data:veri,roam:false,nodeClick:false,breadcrumb:{show:false},width:'100%',height:'100%',squareRatio:1.2,
        label:{show:true,formatter:'{b}',color:r.yazi,fontSize:12,fontWeight:600,overflow:'truncate',position:'insideTopLeft',padding:[5,7]},
        itemStyle:{borderWidth:2,gapWidth:2,borderRadius:6},emphasis:{itemStyle:{shadowBlur:14,shadowColor:r.v}}}]});
    return {o,init(c){c.on('click',p=>{if(tikla.deger&&dim)tikla.deger(dim,p.name);});}};
  }
  return null;
}

function canliKur(kap,kurulum){
  const c=echarts.init(kap,null,{renderer:'canvas'});c.setOption(kurulum.o);if(kurulum.init)kurulum.init(c);GRAFIKLER.push(c);return c;}
function temizle(){GRAFIKLER.forEach(c=>{try{c.dispose();}catch(_){}});GRAFIKLER=[];}
function yenidenBoyut(){GRAFIKLER.forEach(c=>{try{c.resize();}catch(_){}});}
window.addEventListener('resize',()=>requestAnimationFrame(yenidenBoyut));

// ------------------------------------------------------------------ aralık
function sonTarih(){return (HS.harita&&HS.harita.profil&&HS.harita.profil.son)||new Date().toISOString();}
function aralikIst(){const a=HS.aralik;if(a.tip==='tumu')return null;return {baslangic:a.baslangic,bitis:a.bitis};}
function aralikSec(tip,ozel){const son=new Date(sonTarih()),bit=son.toISOString().slice(0,19)+'Z';let bas=null;
  if(tip==='30'){const d=new Date(son);d.setUTCDate(d.getUTCDate()-30);bas=d.toISOString().slice(0,19)+'Z';}
  else if(tip==='yil'){const d=new Date(son);d.setUTCFullYear(d.getUTCFullYear()-1);bas=d.toISOString().slice(0,19)+'Z';}
  else if(tip==='ozel'){HS.aralik={tip:'ozel',baslangic:ozel.baslangic,bitis:ozel.bitis};return;}
  HS.aralik=tip==='tumu'?{tip:'tumu',baslangic:null,bitis:null}:{tip,baslangic:bas,bitis:bit};}
function aySonu(a){const [y,m]=a.split('-').map(Number);const d=new Date(Date.UTC(y,m,0));return d.toISOString().slice(0,10)+'T23:59:59Z';}
const aralikMetni=()=>{const a=HS.aralik;return a.tip==='tumu'?'Tümü':`${gunMetin(a.baslangic)} – ${gunMetin(a.bitis)}`;};

// ------------------------------------------------------------------ ekran iskeleti
async function ekran(a){
  HS.yukleme++;
  let v;
  try{v=await api('harita',{aralik:aralikIst()});}
  catch(e){if(e.kod==='harita_yok'){a.append(h('h2',{},'Harita'),h('div',{class:'uyari'},e.mesaj+' Diğer ekranlar çalışmaya devam eder.'));return;}throw e;}
  HS.harita=v;
  const kisi=KISILER.kisiler.find(k=>k.secili);const ad=kisi?kisi.ad:v.profil.ad;
  const kok=h('div',{class:'hd'});
  const sol=h('div',{class:'sol'}),sag=h('div',{class:'sag'});
  const figKap=h('div',{class:'figur-kap hud'});
  const ust=h('div',{class:'ust'}),yol=h('div',{class:'yol',role:'navigation','aria-label':'Konum'}),panel=h('div',{id:'bolge-paneli',class:'bp'});
  HS.dom={kok,sol,sag,figKap,ust,yol,panel,ad};
  sol.append(figKap,beyanKarti(v));sag.append(ust,yol,panel);kok.append(sol,sag);a.append(kok);
  figurYenile();ustCiz();yolCiz();
  if(HS.bolge&&v.bolgeler.find(b=>b.id===HS.bolge))await bolgeYukle();else{HS.bolge=null;genelCiz();}
}
function beyanKarti(v){const k=h('div',{class:'kart hud'},h('h3',{class:'k-baslik'},'Beyan edilen bilgiler'));
  if(v.beyan&&v.beyan.length){k.append(h('ul',{class:'beyan'},v.beyan.slice(0,8).map(f=>h('li',{},f.veri||f.statement||f.metin||'',' ',h('span',{class:'rozet'},f.kategori||f.category||'')))));
    if(v.beyan.length>8)k.append(h('div',{class:'soluk'},`+${v.beyan.length-8} bilgi daha`));}
  else k.append(h('div',{class:'soluk'},'Henüz beyan edilen bilgi yok. '),h('button',{class:'i',onclick:()=>git('persona')},'Persona\'ya git'));
  return k;}
function figurYenile(){const d=HS.dom;d.figKap.textContent='';d.figKap.append(window.FIGUR.ciz(HS.harita,HS.bolge,bolgeSec),cipler());}
function cipler(){return h('div',{class:'cipler'},HS.harita.bolgeler.map(b=>h('button',{class:(b.kilitli?'kilitli ':'')+(HS.bolge===b.id?'secili':''),onclick:()=>bolgeSec(b.id)},
  HAP_AD[b.id]||b.ad,b.kilitli?'':h('span',{class:'cn'},SAYI(b.olay_sayisi||0)))));}

// ---- üst şerit: kişi, KPI, aralık seçici
function ustCiz(){const d=HS.dom,p=HS.harita.profil;d.ust.textContent='';
  const aralik=h('div',{class:'aralik',role:'group','aria-label':'Zaman aralığı'},
    [['30','Son 30 gün'],['yil','Son yıl'],['tumu','Tümü'],['ozel','Özel']].map(([t,ad])=>h('button',{class:'seg'+(HS.aralik.tip===t?' secili':''),'aria-pressed':HS.aralik.tip===t,onclick:async()=>{
      if(t==='ozel'){ozelAralik();return;}aralikSec(t);await tumunuYenile();}},ad)));
  d.ust.append(h('div',{class:'profil-ust'},h('div',{},h('h2',{class:'ad'},d.ad),h('div',{class:'soluk'},`${tarihAraligi(p)} · zaman aralığı: ${aralikMetni()}`)),
      h('div',{class:'kpi-buyuk'},h('div',{class:'sayi-b'},SAYI(p.olay)),h('div',{class:'soluk'},'kayıt'))),aralik);}
function tarihAraligi(p){return p.ilk?`${gunMetin(p.ilk)} – ${gunMetin(p.son)}`:'tarih yok';}
function ozelAralik(){const b=h('input',{type:'date',value:HS.aralik.baslangic?HS.aralik.baslangic.slice(0,10):''}),e=h('input',{type:'date',value:HS.aralik.bitis?HS.aralik.bitis.slice(0,10):''});
  const kapat=pencere('Özel zaman aralığı',h('div',{class:'satir'},'Başlangıç ',b,' Bitiş ',e),h('div',{class:'satir'},h('button',{class:'d',onclick:async()=>{
    if(!b.value||!e.value||b.value>e.value){bildir('Geçerli bir aralık seçin.',true);return;}aralikSec('ozel',{baslangic:b.value+'T00:00:00Z',bitis:e.value+'T23:59:59Z'});kapat();await tumunuYenile();}},'Uygula'),
    h('button',{class:'i',onclick:()=>kapat()},'Vazgeç')));}
async function tumunuYenile(){const v=await api('harita',{aralik:aralikIst()});HS.harita=v;figurYenile();ustCiz();yolCiz();if(HS.bolge)await bolgeYukle();else genelCiz();}

// ---- breadcrumb
function yolCiz(){const d=HS.dom;d.yol.textContent='';const li=[];
  li.push({ad:'Harita',tik:()=>{HS.bolge=null;HS.filtre={};HS.kayit=null;HS.karsilastir=null;figurYenile();yolCiz();genelCiz();}});
  if(HS.bolge){li.push({ad:HAP_AD[HS.bolge]||HS.bolge,tik:()=>{HS.filtre={};HS.kayit=null;bolgeYukle();}});
    Object.keys(HS.filtre).forEach((k,i,ks)=>li.push({ad:`${dimAd(k)}: ${degerMetin(k,HS.filtre[k])}`,tik:()=>{const yeni={};ks.slice(0,i+1).forEach(x=>yeni[x]=HS.filtre[x]);HS.filtre=yeni;HS.kayit=null;bolgeYukle();}}));}
  if(HS.kayit)li.push({ad:'Kayıt ayrıntısı',tik:null});
  const geri=h('button',{class:'i geri',disabled:li.length<2,onclick:geriGit,'aria-label':'Geri'},'← Geri');
  d.yol.append(geri);
  li.forEach((x,i)=>{if(i)d.yol.append(h('span',{class:'ayrac','aria-hidden':'true'},'›'));
    d.yol.append(x.tik&&i<li.length-1?h('button',{class:'crumb',onclick:x.tik},x.ad):h('span',{class:'crumb son','aria-current':'page'},x.ad));});}
function geriGit(){if(HS.kayit){kayitKapat();return;}const ks=Object.keys(HS.filtre);
  if(ks.length){delete HS.filtre[ks[ks.length-1]];bolgeYukle();return;}
  if(HS.bolge){HS.bolge=null;HS.karsilastir=null;figurYenile();yolCiz();genelCiz();}}

// ------------------------------------------------------------------ genel (bölge seçilmemiş) görünüm: radar + bölge kartları
function genelCiz(){const d=HS.dom,p=d.panel;temizle();p.textContent='';p.className='bp giris';
  const bl=HS.harita.bolgeler.filter(b=>!b.kilitli&&b.olay_sayisi);
  if(!HS.harita.profil.olay){p.append(h('div',{class:'kart bos-kutu hud'},h('h3',{},'Henüz veri yok'),h('p',{},'Bu kişi için içe aktarılmış kayıt bulunmuyor.'),h('button',{class:'d',onclick:()=>git('ice')},'İçe aktar\'a git')));return;}
  const toplam=bl.reduce((a,b)=>a+b.olay_sayisi,0);
  const radar=h('div',{class:'kart hud'},h('h3',{class:'k-baslik'},'Bölgeler arası profil',h('span',{class:'etiket-veri'},'veriden sayım')),
    h('div',{class:'ipucu'},'Bir eksenin adına ya da aşağıdaki karta tıklayın.'),h('div',{class:'cgraf radar',role:'img','aria-label':'Bölgeler arası profil radarı'}));
  const kartlar=h('div',{class:'bkartlar'},bl.sort((a,b)=>b.olay_sayisi-a.olay_sayisi).map(b=>h('button',{class:'bkart',onclick:()=>bolgeSec(b.id)},
    h('div',{class:'bk-ad'},HAP_AD[b.id]||b.ad),h('div',{class:'bk-say'},SAYI(b.olay_sayisi)),h('div',{class:'bk-cubuk'},h('i',{style:`width:${(100*b.olay_sayisi/toplam).toFixed(1)}%`})),
    h('div',{class:'soluk'},`%${ONDALIK(100*b.olay_sayisi/toplam)} · ${gunMetin(b.ilk)} → ${gunMetin(b.son)}`))));
  p.append(radar,h('div',{class:'kart hud'},h('h3',{class:'k-baslik'},'Bölgeler'),kartlar));
  const kap=radar.querySelector('.cgraf'),r=R();
  const mx=Math.max(...bl.map(b=>Math.sqrt(b.olay_sayisi)));
  const o=temel(r);Object.assign(o,{radar:{indicator:bl.map(b=>({name:HAP_AD[b.id]||b.ad,max:mx*1.1,id:b.id})),radius:'66%',center:['50%','54%'],shape:'polygon',splitNumber:4,triggerEvent:true,
      axisName:{color:r.yazi,fontSize:13,fontWeight:600,backgroundColor:hexA(r.v,.1),borderRadius:6,padding:[3,8]},axisLine:{lineStyle:{color:hexA(r.v,.3)}},splitLine:{lineStyle:{color:hexA(r.cizgi,.7)}},splitArea:{show:false}},
    tooltip:{...o.tooltip,trigger:'item',formatter:()=>bl.map(b=>`${HAP_AD[b.id]}: <b>${SAYI(b.olay_sayisi)}</b>`).join('<br>')},
    series:[{type:'radar',data:[{value:bl.map(b=>Math.sqrt(b.olay_sayisi)),name:'Profil'}],symbol:'circle',symbolSize:7,lineStyle:{color:r.v,width:2.4,shadowBlur:12,shadowColor:hexA(r.v,.6)},itemStyle:{color:r.v},areaStyle:{color:hexA(r.v,.22)}}]});
  requestAnimationFrame(()=>{const c=canliKur(kap,{o,init(c){c.on('click',q=>{if(q.targetType==='axisName'){const i=bl.findIndex(b=>(HAP_AD[b.id]||b.ad)===q.name);if(i>=0)bolgeSec(bl[i].id);}});}});});
}

// ------------------------------------------------------------------ bölge seçimi
function bolgeSec(id){const ayni=HS.bolge===id;HS.bolge=id;HS.filtre={};HS.kayit=null;HS.karsilastir=null;HS.grup=null;
  figurYenile();yolCiz();bolgeYukle(true);
  if(!ayni&&window.innerWidth<=1000)HS.dom.yol.scrollIntoView({behavior:HAREKET_AZ?'auto':'smooth',block:'start'});}

async function bolgeYukle(){
  const tur=++HS.yukleme,d=HS.dom,id=HS.bolge;yolCiz();
  const b=HS.harita.bolgeler.find(x=>x.id===id);
  if(HS.kayit)kayitKapat(true);
  const istek={bolge_id:id,filtre:HS.filtre,aralik:aralikIst()};
  d.panel.className='bp';d.panel.style.opacity='.55';
  try{
    const filtreVar=Object.keys(HS.filtre).some(k=>k!=='ay');
    const [v,k,baz]=await Promise.all([api('harita_bolge',istek),
      api('harita_kayitlar',{...istek,limit:20,offset:0}).catch(e=>{if(e.kod==='ozellik_yok'||e.kod==='yok')return {ozellik_yok:true,kayitlar:[],toplam:0};throw e;}),
      filtreVar?api('harita_bolge',{bolge_id:id,filtre:{},aralik:aralikIst()}).catch(()=>null):Promise.resolve(null)]);
    if(tur!==HS.yukleme)return;
    HS.veri=v;HS.kayitlar=k;HS.kayitSayfa=0;HS.baz=baz;
    if(!HS.grup||!(v.gruplar||[]).some(g=>g.id===HS.grup))HS.grup=(v.gruplar&&v.gruplar[0]&&v.gruplar[0].id)||null;
    d.panel.style.opacity='1';panelCiz(b);
  }catch(e){d.panel.style.opacity='1';hataGoster(e);}
}
async function filtreAyarla(dim,deger){const f=HS.filtre;
  if(f[dim]!==undefined&&String(f[dim])===String(deger))delete f[dim];else f[dim]=deger;HS.kayit=null;await bolgeYukle();}
async function coklu(obj){const f=HS.filtre;const hepsi=Object.entries(obj).every(([k,v])=>String(f[k])===String(v));
  Object.entries(obj).forEach(([k,v])=>{if(hepsi)delete f[k];else f[k]=v;});await bolgeYukle();}
async function aralikFirca(i,j){aralikSec('ozel',{baslangic:i+'-01T00:00:00Z',bitis:aySonu(j)});delete HS.filtre.ay;await tumunuYenile();}
async function filtreSifirla(){HS.filtre={};HS.kayit=null;await bolgeYukle();}

// ------------------------------------------------------------------ bölge paneli
function panelCiz(b){const d=HS.dom,p=d.panel,v=HS.veri;temizle();p.textContent='';p.className='bp giris';
  const kilitSutun=HASSAS.includes(HS.bolge);
  p.append(h('div',{class:'panel-baslik'},h('h2',{},(v.ad||b.ad||HAP_AD[HS.bolge]).replace(/^([^:]+):/,'$1 ·')),h('span',{class:'etiket-veri'},'veriden sayım'),
    h('span',{class:'bosluk'}),
    !v.kilitli?h('button',{class:'i',onclick:karsilastirmaSec},HS.karsilastir?'Karşılaştırmayı değiştir':'Karşılaştır'):null,
    HS.karsilastir?h('button',{class:'i',onclick:()=>{HS.karsilastir=null;bolgeYukle();}},'Karşılaştırmayı kapat'):null,
    kilitSutun&&!v.kilitli?h('button',{class:'i',onclick:async()=>{await api('harita_hassas',{bolge_id:HS.bolge,ac:false}).catch(hataGoster);git('harita');}},'Tekrar kilitle'):null));
  if(v.kilitli){p.append(kilitKutusu(b));return;}
  if(!v.toplam&&!(v.grafikler||[]).length&&!Object.keys(HS.filtre).length){p.append(h('div',{class:'kart bos-kutu hud'},h('h3',{},'Henüz veri yok'),h('p',{},'Bu bölge için içe aktarılmış kayıt bulunmuyor.'),h('button',{class:'d',onclick:()=>git('ice')},'İçe aktar\'a git')));return;}
  if(v.filtre_destegi===false)p.append(h('div',{class:'uyari'},'Bu sürümün veri katmanı filtreleme/aralık desteği sunmuyor; grafikler tüm veriyi gösterir.'));
  p.append(filtreCipleri());
  if(v.kpi&&v.kpi.length)p.append(h('div',{class:'kpiler'},v.kpi.map((k,i)=>h('div',{class:'kpi hud',style:`--i:${i}`},h('div',{class:k.metin?'kpi-s kucuk':'kpi-s'},k.metin?k.deger:(typeof k.deger==='number'&&k.deger%1?ONDALIK(k.deger):SAYI(k.deger))),h('div',{class:'soluk'},k.ad)))));
  if(HS.karsilastir){karsilastirmaCiz(p);return;}
  p.append(h('div',{class:'ipucu fb'},'Grafiklerde bir çubuğa, dilime, hücreye ya da noktaya tıklayın: seçim filtre olur. Zaman grafiğinde sürükleyerek aralık seçin, tekerlekle yakınlaştırın.'));
  const izgara=h('div',{class:'grafikler'});p.append(izgara);
  const tikla={deger:filtreAyarla,coklu,aralik:aralikFirca};
  const bekle=[];
  (v.grafikler||[]).forEach((g,i)=>{const bz=g.tur==='zaman'&&HS.baz?(HS.baz.grafikler||[]).find(x=>x.tur==='zaman'):null;
    const kap=h('div',{class:'cgraf '+g.tur,role:'img','aria-label':g.baslik});
    const genis=g.tur==='zaman'||g.tur==='agac'||g.tur==='hafta';
    izgara.append(h('div',{class:'kart hud giris'+(genis?' genis':''),style:`--i:${i}`},h('h4',{class:'k-baslik'},g.baslik,g.secili!=null&&typeof g.secili!=='object'?h('span',{class:'rozet sec'},degerMetin(g.boyut,g.secili)):null),kap));
    bekle.push(()=>{const k=grafikKur(g,R(),tikla,bz);if(k)canliKur(kap,k);});});
  gruplarKarti(p);kayitlarKarti(p);
  requestAnimationFrame(()=>bekle.forEach(f=>f()));}
function kilitKutusu(b){return h('div',{class:'kart kilit-kutu hud'},
  kilitSvg(),h('h3',{},'Bu bölge hassas ve kilitli'),h('p',{class:'soluk'},'Kayıtların içeriği hiçbir koşulda gösterilmez. Onaylarsanız yalnızca SAYILAR ve zaman dağılımı görünür; uygulama kapanınca yeniden kilitlenir.'),
  h('button',{class:'d amber',onclick:()=>hassasOnay(b)},'Sayıları göstermek için onay ver…'));}
function kilitSvg(){const s=document.createElementNS('http://www.w3.org/2000/svg','svg');s.setAttribute('viewBox','0 0 24 24');s.setAttribute('aria-hidden','true');s.setAttribute('class','kilit-b');
  s.innerHTML='<path d="M7 10V7a5 5 0 0 1 10 0v3h1.5A1.5 1.5 0 0 1 20 11.5v8a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 19.5v-8A1.5 1.5 0 0 1 5.5 10zm2 0h6V7a3 3 0 0 0-6 0z"/>';return s;}
function hassasOnay(b){const c=h('input',{type:'checkbox'});
  const dugme=h('button',{class:'t',disabled:true,onclick:async()=>{try{await api('harita_hassas',{bolge_id:HS.bolge,ac:true,onay:true});kapat();git('harita');}catch(e){hataGoster(e);}}},'Evet, sayıları göster');
  c.onchange=()=>{dugme.disabled=!c.checked;};
  const kapat=pencere('Hassas bölge onayı',h('p',{},`"${HAP_AD[HS.bolge]}" bölgesi hassas verilere dayanır (${b&&b.kategoriler?b.kategoriler.join(', '):'hassas kategori'}).`),
    h('p',{class:'soluk'},'Açarsanız yalnızca kayıt sayıları ve zaman dağılımı görünür. Mesaj, e-posta, sohbet ya da konum içeriği ve ham koordinat hiçbir zaman gösterilmez. Bu ayar yalnızca bu oturum için geçerlidir.'),
    h('label',{},c,' Ne açtığımı biliyorum.'),h('div',{class:'satir'},dugme,h('button',{class:'i',onclick:()=>kapat()},'Vazgeç')));}
function filtreCipleri(){const f=HS.filtre,ks=Object.keys(f),a=HS.aralik;
  const k=h('div',{class:'cipler-f','aria-label':'Etkin filtreler'});
  if(!ks.length&&a.tip==='tumu')return h('div',{class:'cipler-f bos'});
  if(a.tip!=='tumu')k.append(h('button',{class:'fcip aralik',title:'Aralığı kaldır',onclick:async()=>{aralikSec('tumu');await tumunuYenile();}},'Aralık: '+aralikMetni(),h('span',{class:'x'},'×')));
  ks.forEach(x=>k.append(h('button',{class:'fcip',title:'Filtreyi kaldır',onclick:()=>filtreAyarla(x,f[x])},`${dimAd(x)}: ${degerMetin(x,f[x])}`,h('span',{class:'x'},'×'))));
  if(ks.length+(a.tip!=='tumu'?1:0)>1||ks.length)k.append(h('button',{class:'i kucuk',onclick:async()=>{HS.filtre={};aralikSec('tumu');HS.kayit=null;await tumunuYenile();}},'Tümünü sıfırla'));
  return k;}

// ---- gruplar (alt grup → öğe)
function gruplarKarti(p){const v=HS.veri,gr=v.gruplar||[];if(!gr.length)return;
  const kart=h('div',{class:'kart hud giris'});
  const sek=h('div',{class:'sekmeler',role:'tablist'},gr.map(g=>h('button',{role:'tab','aria-selected':HS.grup===g.id,class:'sek'+(HS.grup===g.id?' secili':''),onclick:()=>{HS.grup=g.id;panelYenileGrup(kart,gr);}},g.ad)));
  kart.append(h('h4',{class:'k-baslik'},'En çok ',h('span',{class:'ipucu'},'öğeye tıklayın: ayrıntıya inin')),sek,h('div',{class:'gl'}));p.append(kart);panelYenileGrup(kart,gr);}
function panelYenileGrup(kart,gr){kart.querySelectorAll('.sek').forEach((s,i)=>{const on=gr[i].id===HS.grup;s.classList.toggle('secili',on);s.setAttribute('aria-selected',on);});
  const g=gr.find(x=>x.id===HS.grup),l=kart.querySelector('.gl');l.textContent='';const mx=Math.max(1,...g.ogeler.map(o=>o.sayi)),toplam=g.ogeler.reduce((a,o)=>a+o.sayi,0);
  const sec=HS.filtre[g.id];
  g.ogeler.slice(0,12).forEach((o,i)=>l.append(h('button',{class:'oge'+(sec!=null&&String(sec)===o.ad?' secili':''),style:`--w:${(100*o.sayi/mx).toFixed(1)}%;--i:${i}`,title:g.eylem==='ara'?'Arama\'da aç':'Ayrıntıya in',onclick:()=>{
      if(g.eylem==='ara'){window.ARAMA_SORGU=o.ad;git('ara');}else filtreAyarla(g.id,o.ad);}},
    h('span',{class:'sira'},String(i+1).padStart(2,'0')),h('span',{class:'ad'},o.ad),h('span',{class:'cb'},h('i',{})),h('span',{class:'sy'},SAYI(o.sayi),h('small',{},` %${ONDALIK(100*o.sayi/toplam)}`)))));
  if(g.eylem==='ara'&&sec!=null)l.append(h('button',{class:'i kucuk',onclick:()=>{window.ARAMA_SORGU=String(sec);git('ara');}},'Arama\'da aç: '+sec));}

// ---- kayıtlar
function kayitlarKarti(p){const k=HS.kayitlar;const kart=h('div',{class:'kart hud giris',id:'kayitlar-karti'});
  kart.append(h('h4',{class:'k-baslik'},'Kayıtlar',k&&!k.ozellik_yok?h('span',{class:'rozet'},SAYI(k.toplam)+' kayıt'):null));
  if(!k||k.ozellik_yok){kart.append(h('div',{class:'soluk'},'Kayıt listesi bu sürümün veri katmanında yok.'));p.append(kart);return;}
  if(k.kilitli){kart.append(h('div',{class:'soluk'},'Bu bölge kilitli.'));p.append(kart);return;}
  const liste=h('div',{class:'kliste',role:'list'});kart.append(liste);satirEkle(liste,k.kayitlar);
  kart.append(h('div',{class:'satir'},HS.kayitlar.toplam>k.kayitlar.length?h('button',{class:'i',id:'daha',onclick:dahaFazla},'Daha fazla'):null,
    !k.kayitlar.length?h('span',{class:'soluk'},'Bu filtreyle kayıt yok.'):null));
  p.append(kart);}
function satirEkle(liste,kayitlar){kayitlar.forEach(r=>liste.append(h('button',{class:'krow',role:'listitem',onclick:()=>kayitAc(r.id)},
  h('span',{class:'kt'},tarihMetin(r.ts)),h('span',{class:'kb'},r.baslik||r.tur),h('span',{class:'rozet'},r.tur||r.kategori),h('span',{class:'ok'},'›'))));}
async function dahaFazla(){const tur=HS.yukleme;const k=HS.kayitlar;const off=k.kayitlar.length;
  const r=await api('harita_kayitlar',{bolge_id:HS.bolge,filtre:HS.filtre,aralik:aralikIst(),limit:20,offset:off}).catch(hataGoster);if(!r||tur!==HS.yukleme)return;
  k.kayitlar.push(...r.kayitlar);satirEkle(document.querySelector('#kayitlar-karti .kliste'),r.kayitlar);
  if(k.kayitlar.length>=k.toplam){const b=document.getElementById('daha');if(b)b.remove();}}
async function kayitAc(id){let r;try{r=await api('harita_ayrinti',{olay_id:id});}catch(e){hataGoster(e);return;}
  HS.kayit=id;yolCiz();document.getElementById('cekmece')?.remove();
  const rows=(r.alanlar||[]).map(a=>h('tr',{},h('th',{},a.ad),h('td',{},String(a.deger))));
  const c=h('aside',{id:'cekmece',class:'cekmece hud',role:'dialog','aria-label':'Kayıt ayrıntısı'},
    h('div',{class:'panel-baslik'},h('h3',{style:'margin:0'},'Kayıt ayrıntısı'),h('span',{class:'bosluk'}),h('button',{class:'i',onclick:()=>kayitKapat(),'aria-label':'Kapat'},'Kapat ✕')),
    r.kilitli?h('div',{class:'uyari'},'Bu kayıt hassas ve kilitli; ayrıntı gösterilmez.'):h('div',{},
      r.icerik_gizli?h('div',{class:'uyari amber'},'Hassas kategori: içerik hiçbir koşulda gösterilmez; yalnız kaynak ve zaman bilgisi var.'):null,
      h('dl',{class:'ayr'},h('dt',{},'Tarih'),h('dd',{},tarihMetin(r.ts)),h('dt',{},'Ham tarih'),h('dd',{class:'mono'},r.ham_ts||r.ts),h('dt',{},'Tür'),h('dd',{},r.tur),h('dt',{},'Kategori'),h('dd',{},r.kategori),
        h('dt',{},'Kaynak'),h('dd',{},r.kaynak?`${r.kaynak.ad||'-'} (sürüm ${r.kaynak.surum||'-'}, alındı ${gunMetin(r.kaynak.alindi)})`:'-'),
        h('dt',{},'Kaynak dosya'),h('dd',{class:'mono'},(r.kaynak_dosya&&r.kaynak_dosya.length)?r.kaynak_dosya.join(', '):'-'),
        r.metin?h('dt',{},'Metin'):null,r.metin?h('dd',{class:'metin'},r.metin):null),
      rows.length?h('table',{class:'ayr-tablo'},h('tbody',{},rows)):null));
  document.body.append(c);c.querySelector('button').focus();document.addEventListener('keydown',escKapat);}
function escKapat(e){if(e.key==='Escape')kayitKapat();}
function kayitKapat(sessiz){document.getElementById('cekmece')?.remove();document.removeEventListener('keydown',escKapat);if(HS.kayit){HS.kayit=null;if(!sessiz)yolCiz();}}

// ------------------------------------------------------------------ karşılaştırma
function karsilastirmaSec(){const kisiler=KISILER.kisiler;const tur=h('select',{},h('option',{value:'kisi'},'Başka bir kişiyle'),h('option',{value:'donem'},'Başka bir dönemle'));
  const kisi=h('select',{},kisiler.map(k=>h('option',{value:k.id},k.ad+(k.secili?' (şu anki)':''))));
  const donem=h('select',{},h('option',{value:'oncekiyil'},'Son 12 ay ↔ önceki 12 ay'),h('option',{value:'gecenyil'},'Seçili aralık ↔ bir yıl önceki aynı aralık'),h('option',{value:'ozel'},'Özel dönem…'));
  const b=h('input',{type:'date'}),e=h('input',{type:'date'});const ozelSatir=h('div',{class:'satir'},'B dönemi: ',b,' – ',e);ozelSatir.style.display='none';
  const kisiS=h('div',{class:'satir'},'Kişi: ',kisi),donemS=h('div',{class:'satir'},'Dönem: ',donem);donemS.style.display='none';
  tur.onchange=()=>{kisiS.style.display=tur.value==='kisi'?'':'none';donemS.style.display=tur.value==='donem'?'':'none';ozelSatir.style.display=(tur.value==='donem'&&donem.value==='ozel')?'':'none';};
  donem.onchange=tur.onchange;
  const kapat=pencere('Karşılaştır',h('p',{class:'soluk'},'Seçili bölgeyi ve filtreleri iki kişi ya da iki dönem için yan yana gösterir.'),h('div',{class:'satir'},tur),kisiS,donemS,ozelSatir,
    h('div',{class:'satir'},h('button',{class:'d',onclick:async()=>{
      if(tur.value==='kisi'){const k=kisiler.find(x=>x.id===kisi.value);HS.karsilastir={tur:'kisi',kisi_id:k.id,ad:k.ad};}
      else if(donem.value==='ozel'){if(!b.value||!e.value){bildir('Dönemi seçin.',true);return;}HS.karsilastir={tur:'donem',ad:`${gunMetin(b.value)} – ${gunMetin(e.value)}`,aralik:{baslangic:b.value+'T00:00:00Z',bitis:e.value+'T23:59:59Z'}};}
      else if(donem.value==='oncekiyil'){aralikSec('yil');const son=new Date(HS.aralik.baslangic),bas=new Date(son);bas.setUTCFullYear(bas.getUTCFullYear()-1);
        HS.karsilastir={tur:'donem',ad:'Önceki 12 ay',aralik:{baslangic:bas.toISOString().slice(0,19)+'Z',bitis:HS.aralik.baslangic}};}
      else{const a=aralikIst()||{baslangic:HS.harita.profil.ilk,bitis:HS.harita.profil.son};const sh=s=>{const d=new Date(s);d.setUTCFullYear(d.getUTCFullYear()-1);return d.toISOString().slice(0,19)+'Z';};
        HS.karsilastir={tur:'donem',ad:'Bir yıl önce',aralik:{baslangic:sh(a.baslangic),bitis:sh(a.bitis)}};}
      kapat();await tumunuYenile();}},'Karşılaştır'),h('button',{class:'i',onclick:()=>kapat()},'Vazgeç')));}
async function karsilastirmaCiz(p){const kk=HS.karsilastir,A=HS.veri;
  p.append(h('div',{class:'ipucu fb'},'Karşılaştırma: seri adlarına tıklayarak seri açıp kapatabilirsiniz.'));
  let B;try{B=kk.tur==='kisi'?await api('harita_karsilastir',{kisi_id:kk.kisi_id,bolge_id:HS.bolge,filtre:HS.filtre,aralik:aralikIst()}):
      await api('harita_bolge',{bolge_id:HS.bolge,filtre:HS.filtre,aralik:kk.aralik});}catch(e){hataGoster(e);return;}
  const etA=kk.tur==='kisi'?(KISILER.kisiler.find(k=>k.secili)||{ad:'Ben'}).ad:'Bu dönem',etB=kk.ad;
  const gz=(v,t)=>(v.grafikler||[]).find(g=>g.tur===t);const topla=v=>v.toplam!=null?v.toplam:((v.kpi||[]).find(k=>k.ad==='Kayıt')||{deger:0}).deger;
  const ta=topla(A),tb=topla(B),fark=ta?((tb-ta)/ta*100):0;
  p.append(h('div',{class:'kpiler'},h('div',{class:'kpi hud'},h('div',{class:'kpi-s'},SAYI(ta)),h('div',{class:'soluk'},'Kayıt · '+etA)),h('div',{class:'kpi hud'},h('div',{class:'kpi-s'},SAYI(tb)),h('div',{class:'soluk'},'Kayıt · '+etB)),
    h('div',{class:'kpi hud'},h('div',{class:'kpi-s '+(fark>=0?'art':'azal')},(fark>=0?'+':'')+ONDALIK(fark)+'%'),h('div',{class:'soluk'},'Fark (B / A)'))));
  const izgara=h('div',{class:'grafikler'});p.append(izgara);const r=R();const isler=[];
  const kart=(baslik,genis)=>{const kap=h('div',{class:'cgraf'});izgara.append(h('div',{class:'kart hud giris'+(genis?' genis':'')},h('h4',{class:'k-baslik'},baslik),kap));return kap;};
  const za=gz(A,'zaman'),zb=gz(B,'zaman');
  if(za&&zb){const kap=kart('Aylık etkinlik: A ve B',true);const idx=kk.tur==='donem';const n=Math.max(za.degerler.length,zb.degerler.length);
    const x=idx?[...Array(n).keys()].map(i=>`${i+1}. ay`):[...new Set([...za.etiketler,...zb.etiketler])].sort();
    const al=(g)=>idx?[...g.degerler,...Array(n-g.degerler.length).fill(null)]:x.map(e=>{const i=g.etiketler.indexOf(e);return i<0?null:g.degerler[i];});
    const o=temel(r);Object.assign(o,{grid:{left:44,right:16,top:34,bottom:30},legend:{top:0,right:8,textStyle:{color:r.soluk},icon:'roundRect',itemWidth:14,itemHeight:4,inactiveColor:r.cizgi},
      tooltip:{...o.tooltip,trigger:'axis',formatter:ps=>`<b>${idx?ps[0].name:degerMetin('ay',ps[0].name)}</b><br>`+ps.map(q=>`${q.marker} ${q.seriesName}${idx?` (${(q.seriesIndex?zb:za).etiketler[q.dataIndex]?degerMetin('ay',(q.seriesIndex?zb:za).etiketler[q.dataIndex]):'-'})`:''}: <b>${q.value==null?'-':SAYI(q.value)}</b>`).join('<br>')},
      xAxis:{type:'category',data:x,boundaryGap:false,axisLine:{lineStyle:{color:r.cizgi}},axisTick:{show:false},axisLabel:{color:r.soluk,interval:Math.max(0,Math.ceil(n/9)-1),formatter:v=>idx?v:ayEtiket(v)}},
      yAxis:{type:'value',splitNumber:3,axisLabel:{color:r.soluk,formatter:SAYI},splitLine:{lineStyle:{color:hexA(r.cizgi,.5),type:'dashed'}}},
      series:[{name:etA,type:'line',data:al(za),smooth:.35,showSymbol:false,connectNulls:true,lineStyle:{width:2.6,color:r.v,shadowBlur:10,shadowColor:hexA(r.v,.5)},itemStyle:{color:r.v},areaStyle:{color:gradyan(r.v,'55','03')}},
              {name:etB,type:'line',data:al(zb),smooth:.35,showSymbol:false,connectNulls:true,lineStyle:{width:2.6,color:r.amber,shadowBlur:10,shadowColor:hexA(r.amber,.5)},itemStyle:{color:r.amber},areaStyle:{color:gradyan(r.amber,'44','02')}}]});
    isler.push(()=>canliKur(kap,{o}));}
  const sa=gz(A,'saat'),sb=gz(B,'saat');
  if(sa&&sb){const kap=kart('Günün saatleri: A ve B');const o=temel(r);Object.assign(o,{grid:{left:40,right:10,top:34,bottom:24},legend:{top:0,right:8,textStyle:{color:r.soluk},icon:'roundRect',itemWidth:14,itemHeight:4,inactiveColor:r.cizgi},
      tooltip:{...o.tooltip,trigger:'axis'},xAxis:{type:'category',data:sa.etiketler,axisLine:{lineStyle:{color:r.cizgi}},axisTick:{show:false},axisLabel:{color:r.soluk,interval:2}},
      yAxis:{type:'value',splitNumber:3,axisLabel:{color:r.soluk,formatter:SAYI},splitLine:{lineStyle:{color:hexA(r.cizgi,.5),type:'dashed'}}},
      series:[{name:etA,type:'bar',data:sa.degerler,itemStyle:{color:r.v,borderRadius:[4,4,0,0]}},{name:etB,type:'bar',data:sb.degerler,itemStyle:{color:r.amber,borderRadius:[4,4,0,0]}}]});isler.push(()=>canliKur(kap,{o}));}
  const ga=(A.gruplar||[])[0],gb=(B.gruplar||[]).find(g=>ga&&g.id===ga.id);
  if(ga&&gb){const kap=kart('En çok '+ga.ad.toLowerCase()+': A ve B');const adlar=[...new Set([...ga.ogeler.slice(0,8).map(o=>o.ad),...gb.ogeler.slice(0,8).map(o=>o.ad)])].slice(0,10);
    const al=(g)=>adlar.map(a=>(g.ogeler.find(o=>o.ad===a)||{sayi:0}).sayi);
    const o=temel(r);Object.assign(o,{grid:{left:118,right:46,top:34,bottom:6},legend:{top:0,right:8,textStyle:{color:r.soluk},icon:'roundRect',itemWidth:14,itemHeight:4,inactiveColor:r.cizgi},tooltip:{...o.tooltip,trigger:'axis',axisPointer:{type:'shadow'}},
      xAxis:{type:'value',show:false},yAxis:{type:'category',data:adlar,inverse:true,axisTick:{show:false},axisLine:{lineStyle:{color:r.cizgi}},axisLabel:{color:r.yazi,width:108,overflow:'truncate'}},
      series:[{name:etA,type:'bar',data:al(ga),barWidth:9,itemStyle:{color:r.v,borderRadius:[0,5,5,0]},label:{show:true,position:'right',color:r.soluk,formatter:q=>SAYI(q.value),fontSize:10}},
              {name:etB,type:'bar',data:al(gb),barWidth:9,itemStyle:{color:r.amber,borderRadius:[0,5,5,0]},label:{show:true,position:'right',color:r.soluk,formatter:q=>SAYI(q.value),fontSize:10}}]});isler.push(()=>canliKur(kap,{o}));}
  requestAnimationFrame(()=>isler.forEach(f=>f()));}

window.HARITA={ekran,durum:HS,temizle,yenidenBoyut,figurYenile};
})();
