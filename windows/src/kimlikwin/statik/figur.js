/* HUD insan figürü: yüzsüz tel-kafes/anatomik silüet, ince kontur + iç gradyan, bölge düğümleri ve bağlantı çizgileri.
   Saf SVG, bağımlılıksız, ölçeklenebilir. window.FIGUR.ciz(veri, secili, tikla) -> <svg> */
"use strict";
(function(){
const NS='http://www.w3.org/2000/svg';
function sv(e,o,...c){const n=document.createElementNS(NS,e);for(const [k,v] of Object.entries(o||{}))if(v!=null&&v!==false)n.setAttribute(k,v);
  for(const x of c.flat()){if(x==null||x===false)continue;n.append(x.nodeType?x:document.createTextNode(String(x)));}return n;}
const AD={bas:'BAŞ',goz:'GÖZLER',kulak:'KULAKLAR',agiz:'AĞIZ',el:'ELLER',kalp:'KALP',karin:'KARIN',ayak:'AYAKLAR',ic:'MERKEZ',zihin:'ZİHİN'};
const AD_ACIK={bas:'Baş',goz:'Gözler',kulak:'Kulaklar',agiz:'Ağız',el:'Eller',kalp:'Kalp',karin:'Karın',ayak:'Ayaklar',ic:'Merkez',zihin:'Zihin'};
const CX=320,OFF=40,VW=720,VH=730;
const K1=1.18,YB=398,YK=.9;
const T1=`translate(${CX} 0) scale(${K1} 1) translate(${-CX} 0)`,T2=`translate(${CX} ${YB}) scale(${K1} ${YK}) translate(${-CX} ${-YB})`;
const tf1=(x,y)=>[CX+(x-CX)*K1,y],tf2=(x,y)=>[CX+(x-CX)*K1,YB+(y-YB)*YK];
// 24x24 çizgi simgeleri
const IK={
 bas:'M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM15.2 15.2L21 21',
 goz:'M2 12s3.8-7 10-7 10 7 10 7-3.8 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
 kulak:'M6.5 10.5a5.5 5.5 0 0 1 11 0c0 3.2-2.5 4-3.4 6.2-.7 1.7-1 4-3.6 4-2.2 0-3.2-1.5-3.2-3.2M10 10.6a2 2 0 0 1 4 0c0 1.2-1.1 1.6-1.7 2.8',
 agiz:'M3 12c3-4.2 6-4.2 9-2.2 3-2 6-2 9 2.2-3 5-6 6-9 6s-6-1-9-6zM3 12h18',
 el:'M8 13V5.5a1.5 1.5 0 0 1 3 0V11M11 11V4.5a1.5 1.5 0 0 1 3 0V11M14 11V5.5a1.5 1.5 0 0 1 3 0V13M17 13v-1.5a1.5 1.5 0 0 1 3 0V16c0 4-3 6-7 6h-1c-3 0-4.700-1.600-6.200-4.100L4 14.200a1.500 1.500 0 0 1 2.500-1.600L8 14',
 kalp:'M12 20.5S3 15 3 8.800A4.800 4.800 0 0 1 12 6.600 4.800 4.800 0 0 1 21 8.800C21 15 12 20.500 12 20.500z',
 karin:'M3 6h18v12H3zM3 7l9 6.500L21 7',
 ayak:'M12 21s-7-6-7-11a7 7 0 0 1 14 0c0 5-7 11-7 11zM12 7.500a2.500 2.500 0 1 0 0 5 2.500 2.500 0 0 0 0-5z',
 ic:'M4 4h6.500v6.500H4zM13.500 4H20v6.500h-6.500zM4 13.500h6.500V20H4zM13.500 13.500H20V20h-6.500z',
 zihin:'M4 5h16v10.500H10.500L6 19.500V15.500H4zM8.500 10h.01M12 10h.01M15.500 10h.01'};
// düğüm ankrajı, kart (taraf, y), bölge şekli
const YER={
 bas:{n:[CX,40],k:['s',22]}, goz:{n:[CX,68],k:['s',94]}, agiz:{n:[CX,100],k:['s',166]}, kulak:{n:[CX+43,76],k:['r',94]}, zihin:{n:[CX+80,26],k:['r',22]},
 kalp:{n:tf1(342,214),k:['r',198]}, ic:{n:tf1(CX,262),k:['r',282]}, karin:{n:tf1(CX,326),k:['r',366]},
 el:{n:tf1(176,424),k:['s',366]}, ayak:{n:tf2(282,708),k:['s',620]}};
const KW=156,KH=56;
const YAR='M308 136C290 139 262 142 244 150C236 154 233 164 234 178L252 198C258 230 268 262 273 292C276 314 262 334 260 356C259 378 290 394 320 398L320 138Z';
const KOL='M246 150C230 158 220 188 214 228C209 260 198 288 190 318C184 344 176 370 170 392C164 404 160 418 164 430C170 442 182 440 185 430C189 416 196 396 203 374C211 346 225 316 231 290C239 262 245 232 251 204C253 186 253 168 249 154Z';
const BACAK='M262 352C258 400 253 450 256 520C258 562 262 622 262 678L264 692L300 692L298 684C300 622 304 562 300 520C304 460 312 420 320 398Z';
const AYAK='M262 690C250 702 246 714 252 718L304 718C308 706 302 694 300 688Z';
const AYNA=`translate(${2*CX} 0) scale(-1 1)`;
function govde(){
  const out=[];  // {el, t}
  const ekle=(el,t)=>{el.setAttribute('transform',t);out.push(el);return el;};
  ekle(sv('ellipse',{cx:CX,cy:72,rx:37,ry:46}),'');
  ekle(sv('path',{d:`M${CX-15} 114L${CX-15} 142L${CX+15} 142L${CX+15} 114Z`}),'');
  [YAR,KOL].forEach(d=>{ekle(sv('path',{d}),T1);ekle(sv('path',{d}),`${T1} ${AYNA}`);});
  [BACAK,AYAK].forEach(d=>{ekle(sv('path',{d}),T2);ekle(sv('path',{d}),`${T2} ${AYNA}`);});
  return out;
}
function ciz(veri,secili,tikla,stil){
  stil=stil||window.FIGUR.stil;
  const svg=sv('svg',{class:'figur hud-fig',viewBox:`0 0 ${VW} ${VH}`,role:'group','aria-label':'İnsan figürü: bir bölgeye tıklayın'});
  const defs=sv('defs',{},
    sv('linearGradient',{id:'fg-dolgu',x1:0,y1:0,x2:0,y2:1},sv('stop',{offset:'0%','stop-color':'var(--vurgu)','stop-opacity':.32}),sv('stop',{offset:'55%','stop-color':'var(--vurgu)','stop-opacity':.1}),sv('stop',{offset:'100%','stop-color':'var(--vurgu)','stop-opacity':.03})),
    sv('radialGradient',{id:'fg-zemin',cx:'50%',cy:'50%',r:'50%'},sv('stop',{offset:'0%','stop-color':'var(--vurgu)','stop-opacity':.35}),sv('stop',{offset:'100%','stop-color':'var(--vurgu)','stop-opacity':0})),
    sv('filter',{id:'fg-glow',x:'-30%',y:'-30%',width:'160%',height:'160%'},sv('feGaussianBlur',{stdDeviation:2.4,result:'b'}),sv('feMerge',{},sv('feMergeNode',{in:'b'}),sv('feMergeNode',{in:'SourceGraphic'}))),
    sv('pattern',{id:'fg-nokta',width:6,height:6,patternUnits:'userSpaceOnUse'},sv('circle',{cx:3,cy:3,r:1.05,fill:'var(--vurgu)','fill-opacity':.55})),
    sv('pattern',{id:'fg-tarama',width:8,height:8,patternUnits:'userSpaceOnUse'},sv('line',{x1:0,y1:.5,x2:8,y2:.5,stroke:'var(--vurgu)','stroke-opacity':.28,'stroke-width':1})),
    sv('pattern',{id:'fg-cizgili',width:7,height:7,patternUnits:'userSpaceOnUse',patternTransform:'rotate(45)'},sv('line',{x1:0,y1:0,x2:0,y2:7,stroke:'var(--amber)','stroke-width':2.4,'stroke-opacity':.75})));
  const G=govde();
  const kil=sv('clipPath',{id:'fg-kes'},...G.map(p=>p.cloneNode(true)));
  svg.append(defs,kil);
  const fig=sv('g',{transform:`translate(${OFF} 0)`});svg.append(fig);
  // zemin (hologram tabanı)
  const zemin=sv('g',{class:'fg-zemin'},sv('ellipse',{cx:CX,cy:690,rx:160,ry:26,fill:'url(#fg-zemin)'}),
    ...[110,76,44].map((r,i)=>sv('ellipse',{cx:CX,cy:690,rx:r+50,ry:(r+50)*.17,fill:'none',stroke:'var(--vurgu)','stroke-opacity':.55-i*.12,'stroke-width':1.1,'stroke-dasharray':i===1?'3 6':null})),
    sv('line',{x1:CX,y1:682,x2:CX,y2:724,stroke:'var(--vurgu)','stroke-opacity':.25}));
  fig.append(zemin);
  // ızgara (hologram arka planı)
  fig.append(sv('g',{class:'fg-izgara'},...[...Array(13).keys()].map(i=>sv('line',{x1:164+i*26,y1:20,x2:164+i*26,y2:690,stroke:'var(--vurgu)','stroke-opacity':.05})),
    ...[...Array(14).keys()].map(i=>sv('line',{x1:150,y1:30+i*50,x2:490,y2:30+i*50,stroke:'var(--vurgu)','stroke-opacity':.05}))));
  // silüet
  const sil=sv('g',{class:'fg-sil'});
  const dolguNode=sv('g',{'clip-path':'url(#fg-kes)'},sv('rect',{x:120,y:20,width:400,height:700,fill:'url(#fg-dolgu)'}));
  if(stil==='kafes'){dolguNode.append(sv('rect',{x:120,y:20,width:400,height:700,fill:'url(#fg-tarama)'}));
    // enine kontur çizgileri (anatomik kesitler)
    [150,190,236,290,352,420,520,600,670].forEach(y=>dolguNode.append(sv('path',{d:`M180 ${y}Q${CX} ${y+(y<130?8:12)} 460 ${y}`,fill:'none',stroke:'var(--vurgu)','stroke-opacity':.22,'stroke-width':1})));
    [-44,-22,0,22,44].forEach(dx=>dolguNode.append(sv('path',{d:`M${CX+dx} 142C${CX+dx*1.6} 220 ${CX+dx*1.1} 300 ${CX+dx*1.4} 396`,fill:'none',stroke:'var(--vurgu)','stroke-opacity':.16})));}
  if(stil==='noktali')dolguNode.append(sv('rect',{x:120,y:20,width:400,height:700,fill:'url(#fg-nokta)'}));
  sil.append(dolguNode);
  const kontur=sv('g',{class:'fg-kontur',filter:'url(#fg-glow)'},...G.map(p=>{const c=p.cloneNode(true);c.setAttribute('fill','none');return c;}));
  sil.append(kontur);
  // anatomik detay çizgileri
  const det=sv('g',{class:'fg-det'});
  const gu=sv('g',{transform:T1}),ga=sv('g',{transform:T2});det.append(gu,ga);
  const simet=(d)=>[sv('path',{d}),sv('path',{d,transform:AYNA})];
  gu.append(...simet('M306 146Q288 154 262 160'),...simet('M312 168Q296 176 280 182'),...simet('M268 232C288 238 304 240 316 238'),...simet('M270 250C290 258 306 260 316 258'),...simet('M274 292Q296 304 316 302'),
    sv('path',{d:'M320 148V300'}),...simet('M284 332Q304 346 318 340'),sv('circle',{cx:CX,cy:318,r:2.2}),...simet('M262 356Q290 366 316 360'),
    ...simet('M214 232Q222 238 230 232'),...simet('M192 314Q200 322 208 316'));
  ga.append(...simet('M270 514Q284 524 298 514'),...simet('M268 598Q282 606 296 598'));
  [[246,152],[214,262],[190,320]].forEach(([x,y])=>gu.append(sv('circle',{class:'eklem',cx:x,cy:y,r:2.6}),sv('circle',{class:'eklem',cx:2*CX-x,cy:y,r:2.6})));
  [[262,358],[278,520],[280,676]].forEach(([x,y])=>ga.append(sv('circle',{class:'eklem',cx:x,cy:y,r:2.6}),sv('circle',{class:'eklem',cx:2*CX-x,cy:y,r:2.6})));
  gu.append(sv('circle',{class:'eklem',cx:CX,cy:142,r:2.6}));
  sil.append(det);fig.append(sil);

  // bölgeler
  const sekil={
    bas:()=>[sv('ellipse',{cx:CX,cy:72,rx:38,ry:47})],
    goz:()=>[sv('rect',{x:CX-31,y:58,width:62,height:22,rx:11})],
    kulak:()=>[sv('ellipse',{cx:CX-40,cy:78,rx:6,ry:12}),sv('ellipse',{cx:CX+40,cy:78,rx:6,ry:12})],
    agiz:()=>[sv('rect',{x:CX-19,y:92,width:38,height:20,rx:10})],
    el:()=>[sv('g',{transform:T1},sv('ellipse',{cx:176,cy:418,rx:16,ry:26,transform:'rotate(8 176 418)'}),sv('ellipse',{cx:2*CX-176,cy:418,rx:16,ry:26,transform:`rotate(-8 ${2*CX-176} 418)`}))],
    kalp:()=>[sv('g',{transform:T1},sv('path',{d:'M342 238C322 224 322 204 335 203C340 203 342 207 342 210C342 207 345 203 350 203C363 204 363 224 342 238Z'}))],
    ic:()=>[sv('g',{transform:T1},sv('circle',{cx:CX,cy:262,r:18}))],
    karin:()=>[sv('g',{transform:T1},sv('rect',{x:CX-36,y:296,width:72,height:60,rx:22}))],
    ayak:()=>[sv('g',{transform:T2},sv('ellipse',{cx:282,cy:706,rx:28,ry:12}),sv('ellipse',{cx:2*CX-282,cy:706,rx:28,ry:12}))],
    zihin:()=>[sv('ellipse',{cx:CX+86,cy:24,rx:22,ry:13}),sv('circle',{cx:CX+58,cy:44,r:6}),sv('circle',{cx:CX+46,cy:56,r:3.6})]};
  const maks=Math.max(1,...veri.bolgeler.filter(b=>!b.kilitli).map(b=>b.olay_sayisi||0));
  const kartlar=sv('g',{class:'fg-kartlar'}),baglar=sv('g',{class:'fg-baglar'}),dugumler=sv('g',{class:'fg-dugumler'}),sekiller=sv('g',{class:'fg-sekiller'});
  const hepsi=[];
  veri.bolgeler.forEach(b=>{const y=YER[b.id];if(!y||!sekil[b.id])return;
    const bos=!b.kilitli&&!b.olay_sayisi,[nx0,ny]=y.n,nx=nx0+OFF,[taraf,ky]=y.k,kx=taraf==='s'?6:VW-6-KW,sec=secili===b.id;
    const cls='bolge'+(b.kilitli?' kilitli':'')+(bos?' bos':'')+(sec?' secili':'');
    const g=sv('g',{class:cls,'data-id':b.id,tabindex:0,role:'button','aria-label':`${AD_ACIK[b.id]}: ${b.kilitli?'kilitli':(bos?'henüz veri yok':SAYI(b.olay_sayisi)+' kayıt')}`,
      style:`--yog:${b.kilitli||bos?1:(.35+.65*Math.sqrt((b.olay_sayisi||0)/maks)).toFixed(2)}`});
    // bağlantı: karttan düğüme dirsekli çizgi
    const ex=taraf==='s'?kx+KW:kx,ey=ky+KH/2,mx=taraf==='s'?ex+18:ex-18;
    g.append(sv('path',{class:'bag',d:`M${ex} ${ey}H${mx}L${nx} ${ny}`}));
    g.append(sv('g',{class:'sekil',transform:`translate(${OFF} 0)`},...sekil[b.id]()));
    // düğüm
    const kucuk=['bas','goz','agiz','kulak','zihin'].includes(b.id),rr=kucuk?10:12.5,sc=kucuk?.54:.67,of=12*sc;
    g.append(sv('circle',{class:'halka',cx:nx,cy:ny,r:rr+2.5}),sv('circle',{class:'dugum',cx:nx,cy:ny,r:rr}),
      sv('path',{class:'simge',d:IK[b.id],transform:`translate(${nx-of} ${ny-of}) scale(${sc})`}));
    g.append(sv('circle',{class:'vur',cx:nx,cy:ny,r:20,fill:'transparent'}));
    // kart
    g.append(sv('rect',{class:'kart-zemin',x:kx,y:ky,width:KW,height:KH,rx:6}),
      sv('path',{class:'kose',d:`M${kx} ${ky+9}V${ky}H${kx+9}M${kx+KW-9} ${ky}H${kx+KW}V${ky+9}M${kx+KW} ${ky+KH-9}V${ky+KH}H${kx+KW-9}M${kx+9} ${ky+KH}H${kx}V${ky+KH-9}`}),
      sv('text',{class:'k-ad',x:kx+12,y:ky+19},AD[b.id]));
    if(b.kilitli){g.append(sv('path',{class:'k-kilit',d:'M7 10V7a5 5 0 0 1 10 0v3h1.5A1.5 1.5 0 0 1 20 11.5v8a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 19.5v-8A1.5 1.5 0 0 1 5.5 10zm2 0h6V7a3 3 0 0 0-6 0z',transform:`translate(${kx+11} ${ky+25}) scale(.9)`}),sv('text',{class:'k-alt amber',x:kx+34,y:ky+43},'KİLİTLİ'));}
    else if(bos)g.append(sv('text',{class:'k-alt',x:kx+12,y:ky+43},'VERİ YOK'));
    else{g.append(sv('text',{class:'k-sayi',x:kx+12,y:ky+45},SAYI(b.olay_sayisi)),sv('text',{class:'k-alt',x:kx+KW-12,y:ky+45,'text-anchor':'end'},'kayıt'));
      g.append(sv('rect',{class:'k-cubuk-z',x:kx+12,y:ky+KH-6,width:KW-24,height:2.5,rx:1.2}),sv('rect',{class:'k-cubuk',x:kx+12,y:ky+KH-6,width:(KW-24)*Math.sqrt((b.olay_sayisi||0)/maks),height:2.5,rx:1.2}));}
    g.addEventListener('click',()=>tikla(b.id));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();tikla(b.id);}});
    hepsi.push(g);});
  hepsi.forEach(g=>svg.append(g));
  return svg;}
window.FIGUR={ciz,stil:'kafes'};
})();
