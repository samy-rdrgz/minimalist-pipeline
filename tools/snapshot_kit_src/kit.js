/* ==== kit/kit.js: the component sheet ====
   The specimens are drawn by the page's own render functions (rowHTML, deptHTML, noteHTML, mDept, mSheet…)
   with real data: the page and the sheet can't drift apart, by construction.
   Each card is measured in the browser (getComputedStyle) then checked against the tokens: what falls off the scale is flagged. */
const KT=JSON.parse(document.getElementById('ktok').textContent);
const it1=items.find(i=>i.name==='sq030_sh040'),it2=items.find(i=>i.name==='sq990_sh040'),it3=items.find(i=>i.name==='sq990_sh060'),as1=items.find(i=>i.name==='ch_ball');
/* The demo links nothing: a few links of its own here, for the link nodes to show (one to an older stable). */
const KSH=items.filter(i=>i.kind==='shot').slice(0,4);
KSH.forEach((x,k)=>{x.links=[{name:as1.name,file:as1.name+'_v003-stable.blend',newer:k===1?as1.name+'_v004-stable.blend':''}]});as1.linkedBy=KSH.map(x=>x.name);
/* The Links space's nodes as renderGraph() draws them, side by side: an asset, a shot folded to its title, a sequence folded into a group node. */
function gNodes(){const sh=KSH[0];
  const asset=`<div class="node gnode" style="position:static;width:230px"><div class="nh">${ic('b-asset_manager')}<span>${as1.name}</span><span class="dt" style="background:${DOT[worst(as1)]}"></span></div><div class="nb"><div class="sock out"><i></i>linked by ${as1.linkedBy.length}</div></div></div>`;
  const shot=`<div class="node gnode shot" style="position:static;width:230px"><div class="nh">${ic('b-camera_data')}<span>${sh.name}</span><span class="dt" style="background:${DOT[worst(sh)]}"></span></div><div class="nb"><div class="sock in"><i></i>${as1.name} · v003-stable</div><div class="sock in bad"><i></i>pr_lamp · v001-stable (older)</div></div></div>`;
  const fold=`<div class="node gnode shot fold" style="position:static;width:230px"><div class="nh">${ic('b-camera_data')}<span>${KSH[1].name}</span><span class="dt" style="background:${DOT[worst(KSH[1])]}"></span></div><div class="nb"></div></div>`;
  const grp=`<div class="node gnode shot grp" style="position:static;width:230px"><div class="nh">${ic('b-outliner')}<span>sq990</span><span class="gcount">9 shots</span><span class="dt" style="background:var(--st-rtk)"></span></div><div class="nb"><div class="sock in"><i></i>${as1.name} <b class="mult">×9</b></div><div class="sock in"><i></i>env_hall <b class="mult">×6</b></div><div class="sock in bad"><i></i>pr_lamp <b class="mult">×2</b></div></div></div>`;
  return `<div class="kc-row" style="align-items:flex-start;gap:var(--sp-9);flex-wrap:wrap">${asset}${shot}${fold}${grp}</div>`}
S.review={name:'Valerie',role:'prod'};S.sel=it1.name;
it2.mine.lighting='rtk';it2.myNotes.unshift({type:'rtk',deps:['lighting'],dept:'lighting',text:'The backlight is too strong on the table',frames:'f42-58',author:'Valerie',date:new Date().toISOString(),replies:[],at:1});
it1.assign={animation:['samyr','tom']};

/* ---------- Tokens: computed values ---------- */
const probe=document.createElement('div');probe.style.cssText='position:absolute;visibility:hidden;left:-9999px';document.body.appendChild(probe);
const px=v=>{probe.style.width=v;return parseFloat(getComputedStyle(probe).width)};
const fpx=v=>{probe.style.fontSize=v;return parseFloat(getComputedStyle(probe).fontSize)};
const G={sp:KT.size.filter(t=>/^--sp-/.test(t.n)),h:KT.size.filter(t=>/^--(h-|u$)/.test(t.n)),r:KT.size.filter(t=>/^--r(-|$)/.test(t.n)&&t.n!=='--r-pill'),fs:KT.size.filter(t=>/^--fs/.test(t.n))};
let TV={};
function readTok(){TV={};['sp','h','r'].forEach(g=>G[g].forEach(t=>TV[t.n]=px(`var(${t.n})`)));G.fs.forEach(t=>TV[t.n]=fpx(`var(${t.n})`))}
const tokFor=(v,g)=>{if(v<=1.01)return v<=0.01?'0':'1 px (hairline)';const t=G[g].find(t=>Math.abs(TV[t.n]-v)<.6);return t?t.n:null};
const r1=v=>Math.round(v*10)/10;

/* ---------- Measuring ---------- */
const OFF=[];  // [component, property, value, element]
function measure(el,comp){
  const c=getComputedStyle(el),b=el.getBoundingClientRect();
  const chk=(lab,v,g,soft)=>{v=r1(v);const t=tokFor(v,g);if(!t&&!soft)OFF.push([comp,lab,v+' px',el]);return {v,t,soft}};
  const m={name:el.dataset.kv||el.getAttribute('aria-label')||el.textContent.trim().replace(/\s+/g,' ').slice(0,22)||el.className.split(' ')[0]};
  m.h=chk('height',b.height,'h',!el.matches('.btn,.enum,.field:not(.ta),.mi,[role=tab],.vtab,.m-chip,.m-opt,.m-as,.m-vchip,.assign')||el.matches('.m-span'));
  const P=['paddingTop','paddingRight','paddingBottom','paddingLeft'].map(k=>r1(parseFloat(c[k])));m.padAll=P.join(' ');m.pad=[...new Set(P)].map(v=>chk('padding',v,'sp',el.matches('.tree li')));
  const g=(c.display.includes('flex')||c.display.includes('grid'))?(parseFloat(c.columnGap)||parseFloat(c.rowGap)||0):0;m.gap=g?chk('gap',g,'sp'):null;
  const rr=parseFloat(c.borderTopLeftRadius);m.r=rr&&rr<100?chk('radius',rr,'r'):null;
  m.fs=chk('font',parseFloat(c.fontSize),'fs');m.fw=c.fontWeight+' · '+c.fontFamily.split(',')[0].replace(/"/g,'');
  m.col=`ground ${col(c.backgroundColor)} · text ${col(c.color)}${parseFloat(c.borderTopWidth)?' · border '+col(c.borderTopColor):''}`;
  m.sig=[m.h.v,m.padAll,g,rr,m.fs.v,m.fw,m.col].join('|');return m;
}
const col=v=>{const m=v.match(/[\d.]+/g);if(!m)return v;const [r,g,b,a]=m.map(Number);if(a===0)return 'transparent';const hx='#'+[r,g,b].map(x=>x.toString(16).padStart(2,'0')).join('');
  const L=document.documentElement.dataset.ui==='light';const t=KT.color.find(t=>(L?t.light:t.dark).toLowerCase()===hx)||KT.color.find(t=>(L?t.dark:t.light).toLowerCase()===hx);return hx+(a!=null&&a<1?' '+Math.round(a*100)+'%':'')+(t?' ('+t.n+')':'')};
function specTable(ms){
  const seen=new Set(),rows=ms.filter(m=>!seen.has(m.sig)&&seen.add(m.sig));
  const T=x=>!x?'–':x.t?`<span class="tk">${x.t}</span>`:x.soft?x.v+' px':`<span class="bad">${x.v} px</span>`;
  return `<table class="kt"><tr><th>Variant</th><th>Height</th><th>Padding</th><th>Gap</th><th>Radius</th><th>Font</th></tr>${rows.slice(0,8).map(m=>
    `<tr><td class="v">${esc(m.name)}</td><td>${m.h.v} px<br>${m.h.t||m.h.soft?T(m.h):T(m.h)}</td><td>${m.padAll}<br>${m.pad.map(T).join(' ')}</td><td>${T(m.gap)}</td><td>${T(m.r)}</td><td>${T(m.fs)}<br>${esc(m.fw)}</td></tr>`).join('')}</table>
    <table class="kt">${rows.slice(0,4).map(m=>`<tr><th>${esc(m.name)}</th><td>${m.col}</td></tr>`).join('')}</table>`;
}
/* ---------- Specimens ---------- */
const B=(c,l,a='')=>`<button class="btn ${c}" data-kv="${l}" ${a}>${l}</button>`;
const legend=[['todo',null,'To do'],['wip',null,'In progress'],['done',null,'Done'],['done','redo','To redo'],['done','wait','Waiting'],['sup',null,'Validated sup'],['val',null,'Validated prod'],['old',null,'To review again'],['wip','rtk','Open retake'],['val','rtk','Validated, then a retake'],['val','you','You: validated'],['done','you-rtk','You: retake'],['done',null,'Open note','n'],['na',null,'Not required']];
const job=F.jobs.find(j=>j.state==='running'),jobF=F.jobs.find(j=>j.state==='failed');
const DESK=[
 {n:'Button',c:'.btn',m:'.btn',d:()=>`<div class="lbl-v">Variants</div><div class="kc-row">${B('','Normal')}${B('primary','Primary')}${B('tool','Tool')}${B('flat','Flat')}${B('ok','Validate')}${B('alert','Retake')}${B('play','Play')}</div>
   <div class="lbl-v">States</div><div class="kc-row">${B('','Pressed','aria-pressed="true"')}${B('','Disabled','disabled')}${B('primary','Disabled','disabled')}</div>
   <div class="lbl-v">Sizes</div><div class="kc-row same">${B('','Normal 28')}<button class="btn icon" data-kv="Icon" aria-label="Icon">${ic('b-preferences')}</button>${B('sm','Small 24')}<button class="btn sm icon" data-kv="Small icon" aria-label="Small icon">${ic('b-x')}</button></div>`,
  r:['One primary button (blue) per area: the one expected.','Pink = validate, orange = send back, dark = play. Never for decoration.','Icon alone: always an aria-label and a title.','Sm (24) only in a dense list or a section header.']},
 {n:'Button group',c:'.join',m:'.join',same:['.join','.btn'],d:()=>`<span class="join"><button class="btn" aria-pressed="true">Retake</button><button class="btn" aria-pressed="false">Remark</button></span>
   <span class="join full" style="width:320px"><button class="btn sm" aria-pressed="false">Active</button><button class="btn sm" aria-pressed="true">On hold</button><button class="btn sm" aria-pressed="false">Cancelled</button></span>`,
  r:['An exclusive choice of 2–5 options: a group. More: a drop-down.','A group\'s buttons all have the same size.']},
 {n:'Field',c:'.field',m:'.field',d:()=>`<label class="field" style="width:320px">${ic('b-viewzoom')}<input placeholder="Go to a file…" aria-label="Search"><span class="kbd">/</span></label>
   <label class="field ta" style="width:320px"><textarea rows="2" placeholder="Retake at this frame…" aria-label="Text"></textarea></label><span class="kc-row"><span class="kbd">Ctrl</span><span class="kbd">Enter</span></span>`,
  r:['The darkest ground (wcol_text): where you write is plain to see.','The keyboard shortcut in the field when there is one (hidden on a touch screen).']},
 {n:'Drop-down',c:'.enum',m:'.enum',d:()=>`<div style="width:360px">${verHTML(it1,'k')}</div>`,r:['The current value always shown, with the count (1/3).','Opens a menu, never a native select on the desktop.']},
 {n:'Menu',c:'.menu .mi',m:'.mi,.menu-h',st:1,d:()=>`<div class="menu" role="menu" style="width:260px"><div class="menu-h">Version to watch</div><button class="mi" aria-checked="true"><span class="ck">${ic('b-checkmark')}</span><span class="lbl">v004-stable_003 · 12/11</span><span class="k">latest</span></button><button class="mi"><span class="ck"></span><span class="lbl">v004-stable_001</span></button><div class="msep"></div><button class="mi"><span class="ck"></span><span class="lbl">Nobody</span></button></div>`,
  r:['Fixed, and moved back inside the window: never cut off.','The tick on the left, a key or a detail on the right (.k).']},
 {n:'Space tabs',c:'.ws',m:'.ws [role=tab]',d:()=>`<div class="ws" role="tablist">${[['shot','Shots','b-camera_data',26],['asset','Assets','b-asset_manager',4],['links','Links','b-linked',''],['farm','Farm','b-file_movie',10]].map(([k,l,i,c],n)=>`<button role="tab" aria-selected="${!n}">${ic(i)}<span class="lbl">${l}</span>${c!==''?`<span class="n">${c}</span>`:''}</button>`).join('')}</div>`,r:['A click changes the whole page. In a snapshot, there is no Farm.']},
 {n:'Vertical tabs',c:'.vtabs .vtab',m:'.vtab',d:()=>`<div class="vtabs" role="tablist" style="position:static;height:auto">${[['plan','b-camera_data'],['notes','i-note'],['links','b-linked'],['files','b-file']].map(([k,i],n)=>`<button class="vtab" role="tab" aria-selected="${!n}" aria-label="${k}">${ic(i)}</button>`).join('')}</div>`,r:['A file\'s detail: the video first, the rest in tabs.']},
 {n:'State glyphs',c:'.g',m:'.legend-list li',d:()=>`<ul class="legend-list">${legend.map(([b,c,l,n])=>`<li>${glyph(b,c,2,!!n)}<span>${l}</span></li>`).join('')}</ul>`,r:['Solid shape = the base state; corner = what comes on top; bubble = a note.','The words beside it always say it again (never the colour alone).']},
 {n:'State cell',c:'.cell',m:'.cell',d:()=>`<div class="kc-row">${DEPTS.shot.map(d=>cellHTML(it3,d)).join('')}</div>`,r:['Glyph + label + a detail cut short; the title gives it all.']},
 {n:'Tag',c:'.tag',m:'.tag',d:()=>`<div class="kc-row"><span class="tag check" data-kv="check">${ic('b-hide_off')}to check</span><span class="tag you" data-kv="you">you</span><span class="tag rtk" data-kv="rtk">2 RTK</span><span class="tag omit" data-kv="omit">On hold</span><span class="tag fail" data-kv="fail">farm failed</span><span class="tag" data-kv="note">${ic('i-note')}3</span></div>`,r:['A tag says a fact about the file; it isn\'t clicked.','An opaque chip (the dialogs\' ground), never a tint, never an outline.','Its mark: the glyphs\' solid diamond in the state\'s colour (or its icon, in that colour). A hollow diamond: set aside.']},
 {n:'Switch',c:'.swi .tg',m:'.swi',d:()=>`<div class="swis" style="width:280px;margin:0"><button class="swi" role="switch" aria-checked="true" data-kv="on"><span class="lbl">Animation</span><span class="tg"></span></button><button class="swi" role="switch" aria-checked="false" data-kv="off"><span class="lbl">Lighting</span><span class="tg"></span></button><button class="swi" role="switch" aria-checked="true" disabled data-kv="locked"><span class="lbl">Render<small>start a review</small></span><span class="tg"></span></button></div>`,r:['A yes / no setting that applies at once: required departments, the render\'s sound, notifications.','The whole row is the button (role=switch, aria-checked); the switch on its right.','Several exclusive choices: a button group, not switches.']},
 {n:'Review in progress',c:'.review-chip',m:'.review-chip',d:()=>`<div class="topbar" style="min-height:0;padding:var(--sp-4)"><span class="review-chip"><span class="who">Valerie · prod</span><button class="btn primary">${ic('b-export')}Send…<span class="n">4</span></button><button class="btn flat icon" aria-label="Leave">${ic('b-x')}</button></span></div>`,r:['The top bar\'s tint; the solid "you" dot, the colour of the glyphs\' corner.']},
 {n:'Assignment',c:'.assign',m:'.assign',d:()=>`<div class="kc-row">${assignHTML(it1,'animation','k')}${assignHTML(it1,'render','k2')}${assignHTML(it3,'lighting','k3')}</div>`,r:['Dashed: nobody. Turquoise: changed in your review.']},
 {n:'Frame chip',c:'.ft',m:'.ft',d:()=>`<div class="kc-row"><span class="ft" data-kv="retake">f42</span><span class="ft rg" data-kv="range">f42-58</span><span class="ft nt" data-kv="note">f12</span></div>`,r:['Orange: a retake, a range too. Grey: a remark. A click goes there.']},
 {n:'Progress',c:'.jbar .sf',m:'.jbar,.sf',d:()=>`<span class="jbar" style="width:280px"><i style="--p:42%"></i><span>40 / 96 frames</span></span><span class="sf in" style="--p:74%;--c:var(--st-done);width:280px"><span class="lab on">Done</span><b class="v">74 %</b></span><span class="sf" style="--p:12%;--c:var(--st-val);width:280px"><span class="lab">Validated</span><b class="v">12 %</b></span>`,r:['Always the figure beside the bar.','The bar solid in its state colour; the figure black, on a pill of the bar's own colour.']},
 {n:'Player and transport',c:'.stage .scrub .ctl',m:'.ctl .btn,.ctl .enum,.scrub',same:['.ctl','.btn,.enum'],wide:1,d:()=>`<div style="max-width:520px">${stageHTML(it1)}</div>`,r:['Every transport button the same size; Play dark.','The stage takes the video\'s shape, its height between a min and a max.','Marks: orange diamond = retake, grey = note; a range in orange.']},
 {n:'Department card',c:'.dept',m:'.dept',wide:1,d:()=>`<div style="max-width:520px;display:flex;flex-direction:column;gap:var(--sp-4)">${DEPTS.shot.map(d=>deptHTML(it2,d,'k')).join('')}</div>`,r:['A card per required department; the others aren\'t shown.','Actions aligned right, always in the same place.']},
 {n:'Note',c:'.nt',m:'.nt',wide:1,d:()=>`<div style="max-width:520px">${[...it2.myNotes.map(n=>({...n,mine:1})),...it1.notes.slice(0,2)].map(n=>noteHTML(n.mine?it2:it1,n)).join('')}</div>`,r:['Yours in turquoise until they are sent.']},
 {n:'List: sequence and rows',c:'.grp-h .row',m:'.row,.grp-h',wide:1,d:()=>`<section class="area" id="main" style="height:520px"><div class="area-body" id="list"></div></section>`,after:()=>{S.ws='shot';S.q='sq990_sh0';renderList();S.q=''},r:['Separators between rows, no stripes.','A lighter sequence header, Play the sequence beside its name.']},
 {n:'Tree',c:'.tree',m:'.tree li',d:()=>`<div class="area" style="height:300px;width:260px"><div class="area-body"><ul class="tree" id="tree"></ul></div></div>`,after:()=>{S.tq='sq0';renderTree();S.tq=''},r:['Folded apart from the list.']},
 {n:'Property',c:'.prop',m:'.prop',wide:1,d:()=>`<div style="max-width:520px">${filesHTML(it1)}</div>`,r:['The label on the left (fixed width), the value and its action on the right.']},
 {n:'Link nodes',c:'.node',m:'.node',wide:1,d:()=>`<div style="max-width:620px" id="pbody">${linksHTML(as1)}</div>`,after:()=>requestAnimationFrame(drawWires),r:['Header colour = type (asset / shot / older stable).','Bézier wires, never over a node.']},
 {n:'Links: graph nodes',c:'.gnode .grp',m:'.gnode',wide:1,d:gNodes,r:['No wire at rest: the hovered node\'s, else the clicked one\'s (All wires: every one). By type: the assets in their prefix\'s block; by links: by barycentre.','An asset clicked: the shots show its socket alone, + n others.','An asset: its out socket, linked by n. A shot: an in socket per asset it links, red when an older stable.','Folded to its title (the default, unless clicked or linked to the one clicked): the wires meet its title\'s edge.','A sequence of several shots folded into a group node, as Blender\'s: each asset once, ×n its shots -- one wire for n. Clicked, it unfolds.','Assets level with the middle of what links them: the most shared ones in the middle.']},
 {n:'Farm job',c:'.job',m:'.job',wide:1,d:()=>`<div class="jobs" style="max-width:620px">${jobRow(job)}${jobRow(jobF)}</div>`,r:['State (dot) · file · % · machines. Live only.']},
 {n:'Popover',c:'.pop',m:'.pop',st:1,d:()=>`<div class="pop news" style="width:320px"><h4>What\'s new</h4><button class="newsi"><span class="dt" style="background:var(--st-rtk)"></span><span class="tx"><span class="h"><b>sq990_sh010</b><span class="faint">19:40</span></span>léa wrote a retake<small>Animation · f40</small></span></button><p class="hint">Notes, retakes, validations and renders come here.</p></div>`,r:['Placed by its button, held inside the window; closed by a click outside and Esc.']},
 {n:'Dialog',c:'.dlg-in',m:'.dlg-in,.dlg-in .prop',st:1,wide:1,d:()=>`<div id="k-dlg"></div>`,after:()=>{renderDlg();$('#k-dlg').innerHTML=$('#dlg').innerHTML;$('#dlg').hidden=true;$('#dlg').innerHTML=''},r:['A title, settings in .prop rows, actions at the bottom right; Esc closes.']},
 {n:'Tour bubble and message',c:'.tour .toast',m:'.tour,.toast',st:1,d:()=>`<div class="tour"><b>Reviewing</b><p>Your name and your role, then validate, send back, assign.</p><div class="acts"><span class="faint">6 / 7</span><span style="flex:1"></span><button class="btn sm flat">Skip</button><button class="btn sm primary">Next</button></div></div><div class="toast">Sent to Blender: render queued</div>`,r:['The message confirms an action; it asks nothing.']},
];
/* Mobile: the pieces are cut out of the real phone view. */
let MP={};
function mobPieces(){const box=document.createElement('div');S.m.tab='review';S.sel=it1.name;S.m.side='A';
  box.innerHTML=mReview()+mComposer();const q=s=>box.querySelector(s)?.outerHTML||'';
  MP={nav:q('.m-shotnav'),player:q('.m-player'),scrub:q('.scrub'),tp:q('.m-tp'),vers:q('.m-vers'),dept:[...box.querySelectorAll('.m-dept')].map(e=>e.outerHTML).join(''),note:[...box.querySelectorAll('.m-note')].slice(0,2).map(e=>e.outerHTML).join(''),comp:q('.m-comp')};
  const sh=k=>{S.m.sheet=k;const h=mSheet();S.m.sheet=null;return h};
  MP.pick=sh('pick');MP.as=sh('as:animation');MP.depts=sh('depts');MP.render=sh('render');MP.job=sh('job:'+job.id);
  box.innerHTML=mFarm();MP.card=box.querySelector('.m-card').outerHTML;MP.jobs=[...box.querySelectorAll('.m-job')].slice(0,3).map(e=>e.outerHTML).join('');
}
const PH=(cap,h)=>`<div class="k-phone mob"><div class="k-cap">${cap}</div>${h}</div>`;
const MOBC=[
 {n:'Top bar · bottom bar',c:'.m-top .m-ib .m-nav',m:'.m-top,.m-ib,.m-nav button',d:()=>PH('top',`<header class="m-top"><span class="m-brand"><b>alive</b><small>live · Valerie · prod</small></span><span class="sp"></span><button class="m-ib" aria-label="What\'s new">${ic('i-bell')}<span class="cnt">2</span></button><button class="btn primary">${ic('b-export')}Send<span class="n">4</span></button><button class="m-ib" aria-label="Menu">${ic('b-preferences')}</button></header>`)+PH('bottom · live only',`<nav class="m-nav"><button aria-selected="true">${ic('b-file_movie')}<span>Review</span></button><button aria-selected="false">${ic('b-render_animation')}<span>Farm</span><span class="dot bad"></span></button></nav>`),r:['Top: the project, the mode, the bell (live), Send while reviewing.','Bottom: Review | Farm, live only. In a snapshot, no bar.']},
 {n:'Shot picker',c:'.m-shotnav .m-pick',m:'.m-pick,.m-shotnav .m-ib',d:()=>PH('a shot at a time',`<div class="m-body">${MP.nav}</div>`),r:['A shot at a time; ◀ ▶ or swipe the picture; the path\'s filter stays shown.']},
 {n:'Player and A / B',c:'.m-player .m-tp .m-vers',m:'.m-tp .btn,.m-vchip,.scrub',same:['.m-tp','.btn'],wide:1,d:()=>PH('A / B at the same frame',`<div class="m-body">${MP.player}${MP.scrub}${MP.tp}${MP.vers}</div>`),r:['A blue, B yellow, on the chip and around the picture: what you watch is always plain.','Switching keeps the frame.']},
 {n:'Department card',c:'.m-dept .m-as',m:'.m-dept,.m-da .btn,.m-as',wide:1,d:()=>PH('validate · retake · assign',`<div class="m-body">${MP.dept}</div>`),r:['Validate / Retake in two equal columns, 44 px.','The assignment is on the card, not in a menu.']},
 {n:'Note and writing box',c:'.m-note .m-comp .m-chip',m:'.m-note,.m-comp .btn,.m-chip,.m-comp .field',wide:1,d:()=>PH('held at the bottom',`<div class="m-body">${MP.note}</div>${MP.comp}`),r:['Type, department and frame as chips above the text; the frame fills itself in.','16 px in the fields: iOS doesn\'t zoom. The keyboard raises only this box.']},
 {n:'Sheet: choices',c:'.m-sheet .m-opt',m:'.m-opt,.m-sheet-h,.m-filters .m-chip',wide:1,d:()=>PH('choose a file',MP.pick)+PH('assign',MP.as),r:['One component for every choice on the phone.','The tick on the left, a detail small below.']},
 {n:'Sheet: switches',c:'.m-opt.sw',m:'.m-opt.sw',d:()=>PH('add a department',MP.depts),r:['Required departments: added and removed, sent with the review. The desktop\'s switch, at a finger\'s size.']},
 {n:'Farm · render a shot',c:'.m-card .m-job .m-select',m:'.m-card,.m-job,.m-select,.m-sheet-f .btn',wide:1,d:()=>PH('follow',`<div class="m-body">${MP.card}${MP.jobs}</div>`)+PH('render',MP.render)+PH('a job',MP.job),r:['Live only. File, version, script, priority: the rest on the desktop.','A native select on the phone (a long list, the system\'s picker).']},
];
const RULES=[['Spacing','Only --sp-1 to --sp-11. In a box: --sp-6 padding, --sp-4 between widgets, --sp-7 between sections.'],
 ['Heights','Widget 28 (--u), small 24 (--h-sm), header 36 (--h-lg). Phone: 44 (--h-touch) wherever a finger goes.'],
 ['Radii','5 (--r) for widgets, as Blender, 8 (--r-l) for boxes and menus, 10 (--r-xl) for dialogs and sheets.'],
 ['Text','13 body, 11.5 secondary, 15 area titles, 18 page titles. Mono for file names and frames.'],
 ['Colours','Never a colour written in a component: a variable of 10-tokens.css (dark and light). The states have their fixed colours, always solid.'],
 ['Snapshot / live','What needs Blender has .live-only. In a snapshot: no Farm, no Render, no opening in Blender, no bell.'],
 ['Desktop / phone','The phone view: touch AND < 900 px. The same actions (A.*), the same selectors; only the display changes.']];

/* ---------- Drawing ---------- */
function card(s,i,kind){return `<div class="kc ${s.wide?'wide':''}" id="${kind}${i}"><div class="kc-h"><b>${s.n}</b><code>${s.c}</code><span class="w" data-w></span></div>
  <div class="kc-b"><div class="kc-demo ${s.st?'k-static':''}">${s.d()}</div><div class="kc-spec"><div data-spec></div><ul>${s.r.map(x=>`<li>${x}</li>`).join('')}</ul></div></div></div>`}
function renderKit(){
  readTok();
  const row=(t,g)=>{const v=g==='fs'?TV[t.n]:TV[t.n];const vis=g==='sp'?`<span class="k-bar" style="width:${v*3}px"></span>`:g==='h'?`<span class="k-hbox" style="height:${v}px"></span>`:g==='r'?`<span class="k-box" style="border-radius:${v}px"></span>`:`<span style="font-size:${v}px;color:var(--text)">Plan sq030_sh040</span>`;
    return `<div class="k-tr"><code>${t.n}</code><span class="f">${esc(t.v)}</span><span class="px">${r1(v)} px</span><span class="vis">${vis}${t.c?`<span style="margin-left:var(--sp-5)">${esc(t.c)}</span>`:''}</span></div>`};
  $('#k-sp').innerHTML=G.sp.map(t=>row(t,'sp')).join('');$('#k-h').innerHTML=G.h.map(t=>row(t,'h')).join('');$('#k-r').innerHTML=G.r.map(t=>row(t,'r')).join('');$('#k-fs').innerHTML=G.fs.map(t=>row(t,'fs')).join('');
  let grp='';$('#k-col').innerHTML=`<table class="k-ctab"><tr><th>Variable</th><th>Dark</th><th>Light</th><th class="hide-s">Role</th></tr>${KT.color.map(t=>{const gg=t.n.startsWith('--st-')?'States (fixed)':t.n.startsWith('--node')||['--sock','--wire','--wire-edge'].includes(t.n)?'Nodes':/^--(play|alert|ok|you|rtk-t|wip-t|live-t)/.test(t.n)?'Accents':'Interface';
    const h=gg!==grp?`<tr class="k-grp"><td colspan="4">${gg}</td></tr>`:'';grp=gg;
    return h+`<tr><td class="m">${t.n}</td><td class="m"><span class="k-sw" style="background:${t.dark}"></span>${t.dark}</td><td class="m"><span class="k-sw" style="background:${t.light||t.dark}"></span>${t.light||'='}</td><td class="hide-s">${esc(t.c||'')}</td></tr>`}).join('')}</table>`;
  $('#k-desk').innerHTML=DESK.map((s,i)=>card(s,i,'d')).join('');DESK.forEach(s=>s.after&&s.after());
  mobPieces();$('#k-mob').innerHTML=`<h3 style="margin-top:0">The real phone view, live</h3><div class="k-phones" id="k-live"></div>`+MOBC.map((s,i)=>card(s,i,'m')).join('');
  const mob=$('#mob');mob.hidden=false;mob.classList.add('k-phone');$('#k-live').appendChild(mob);S.m.sheet=null;mRender();
  $('#k-rules').innerHTML=`<div class="k-rules">${RULES.map(([h,p])=>`<div class="k-rule"><h4>${h}</h4><p>${p}</p></div>`).join('')}</div>`;
  requestAnimationFrame(()=>requestAnimationFrame(specAll));
}
function specAll(){
  OFF.length=0;readTok();const SAME=[];
  [...DESK.map((s,i)=>[s,'d'+i]),...MOBC.map((s,i)=>[s,'m'+i])].forEach(([s,id])=>{const el=document.getElementById(id);
    const ms=[...el.querySelectorAll('.kc-demo '+s.m.split(',').join(',.kc-demo '))].filter(e=>e.offsetParent).slice(0,40).map(e=>measure(e,s.n));
    el.querySelector('[data-spec]').innerHTML=specTable(ms);
    const off=OFF.filter(o=>o[0]===s.n).length;let warn=off?off+' off the scale':'';
    if(s.same){const [gs,cs]=s.same;el.querySelectorAll('.kc-demo '+gs).forEach(g=>{const hs=[...new Set([...g.querySelectorAll(cs)].filter(e=>e.offsetParent).map(e=>r1(e.getBoundingClientRect().height)))];if(hs.length>1){warn+=(warn?' · ':'')+'heights '+hs.join(' / ');SAME.push([s.n+' · '+gs,hs.join(' / ')+' px'])}})}
    const w=el.querySelector('[data-w]');w.textContent=warn;w.className=warn?'w':'okk';if(!warn)w.textContent='✓ on the scale'});
  audit(SAME);
}
function audit(SAME){
  const css=[...document.styleSheets].find(s=>s.ownerNode&&s.ownerNode.id==='pagecss');const hard=[],hex=[],icons=[];
  const PROPS=/^(padding|margin|gap|row-gap|column-gap|border-.*-radius|font-size|height|min-height)/;
  const walk=rules=>[...rules].forEach(r=>{if(r.cssRules&&!r.style){walk(r.cssRules);return}if(!r.style)return;const sel=r.selectorText||'';
    for(const p of r.style){const v=r.style.getPropertyValue(p);
      if(PROPS.test(p)&&!/var\(|calc\(|env\(/.test(v)){const m=v.match(/(\d*\.?\d+)px/g);if(m&&m.some(x=>parseFloat(x)>1&&parseFloat(x)<64))(/height/.test(p)?icons:hard).push([sel,p+': '+v])}
      if(!sel.startsWith(':root')&&/#[0-9a-f]{3,8}\b|rgba?\(/i.test(v)&&!/var\(/.test(v)&&!/^(--|box-shadow|text-shadow|filter)/.test(p))hex.push([sel,p+': '+v])}});
  walk(css.cssRules);
  const hs={};document.querySelectorAll('#k-desk .kc-demo :is(.btn,.enum,.field,[role=tab],.vtab,.mi)').forEach(e=>{if(!e.offsetParent)return;const h=r1(e.getBoundingClientRect().height);(hs[h]=hs[h]||new Set()).add(e.classList.length?'.'+[...e.classList].slice(0,2).join('.'):'['+e.getAttribute('role')+']')});
  const hrows=Object.entries(hs).sort((a,b)=>a[0]-b[0]).map(([h,s])=>[h+' px'+(tokFor(+h,'h')?' · '+tokFor(+h,'h'):' · off the scale'),[...s].slice(0,6).join(' ')]);
  const box=(t,p,L,ok)=>`<div class="ka"><h4>${t}<span class="n ${L.length?'':'z'}">${L.length}</span></h4><p>${p}</p>${L.length?`<ul>${L.slice(0,80).map(([a,b])=>`<li><b title="${esc(a)}">${esc(a)}</b><span>${esc(b)}</span></li>`).join('')}</ul>`:`<p>${ok}</p>`}</div>`;
  $('#k-audit').innerHTML=box('Measures off the scale','Measured on the components below: a value that falls on no token.',Object.entries(OFF.reduce((m,o)=>{const k=o[0]+'\u0001'+o[1]+' '+o[2];m[k]=(m[k]||0)+1;return m},{})).map(([k,n])=>{const [c,v]=k.split('\u0001');return [c,v+(n>1?' ×'+n:'')]}),'Everything falls on a token.')
    +box('Groups of mixed heights','Widgets side by side that don\'t have the same height.',SAME,'None.')
    +box('Widget heights on the desktop','Every height met: as few as possible (ideally 24 and 28).',hrows,'')
    +box('Sizes still in px in the CSS','Padding, margins, gaps, radii and fonts written as they are instead of a token.',hard,'None.')
    +box('Icons and marks in px','Fixed heights of small things (icons, dots, bars). Candidates for --ic-* tokens.',icons,'None.')
    +box('Colours written as they are','Outside the variables: they won\'t follow the dark / light theme.',hex,'None.');
  $('#k-toc').innerHTML=`<a href="#audit" class="h">Audit</a><a href="#fond" class="h">Foundations</a><a href="#desk" class="h">Desktop</a>${DESK.map((s,i)=>`<a href="#d${i}">${s.n}${document.querySelector('#d'+i+' [data-w].w')?'<span class="w">●</span>':''}</a>`).join('')}<a href="#mobi" class="h">Phone</a>${MOBC.map((s,i)=>`<a href="#m${i}">${s.n}${document.querySelector('#m'+i+' [data-w].w')?'<span class="w">●</span>':''}</a>`).join('')}<a href="#regles" class="h">Rules</a>`;
}
document.addEventListener('click',e=>{const t=e.target.closest('[data-ktheme]');if(t){document.querySelectorAll('[data-ktheme]').forEach(b=>b.setAttribute('aria-pressed',b===t));setTheme(t.dataset.ktheme);requestAnimationFrame(specAll)}
  const s=e.target.closest('[data-kscale]');if(s){document.querySelectorAll('[data-kscale]').forEach(b=>b.setAttribute('aria-pressed',b===s));S.scaleV=+s.dataset.kscale;document.documentElement.style.setProperty('--scale',s.dataset.kscale);requestAnimationFrame(()=>{drawWires();specAll()})}});
setTheme('dark');renderKit();
