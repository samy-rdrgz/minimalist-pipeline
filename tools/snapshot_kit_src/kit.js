/* ==== kit/kit.js : la feuille de composants ====
   Les spécimens sont produits par les vraies fonctions de rendu de la page (rowHTML, deptHTML, noteHTML, mDept, mSheet…)
   avec les vraies données : un écart entre la page et la feuille est impossible par construction.
   Chaque fiche est mesurée dans le navigateur (getComputedStyle) puis comparée aux jetons : ce qui tombe hors échelle est signalé. */
const KT=JSON.parse(document.getElementById('ktok').textContent);
const it1=items.find(i=>i.name==='sq030_sh040'),it2=items.find(i=>i.name==='sq990_sh040'),it3=items.find(i=>i.name==='sq990_sh060'),as1=items.find(i=>i.name==='ch_ball');
S.review={name:'Valerie',role:'prod'};S.sel=it1.name;
it2.mine.lighting='rtk';it2.myNotes.unshift({type:'rtk',deps:['lighting'],dept:'lighting',text:'Le contre-jour est trop fort sur la table',frames:'f42-58',author:'Valerie',date:new Date().toISOString(),replies:[],at:1});
it1.assign={animation:['samyr','tom']};

/* ---------- Jetons : valeurs calculées ---------- */
const probe=document.createElement('div');probe.style.cssText='position:absolute;visibility:hidden;left:-9999px';document.body.appendChild(probe);
const px=v=>{probe.style.width=v;return parseFloat(getComputedStyle(probe).width)};
const fpx=v=>{probe.style.fontSize=v;return parseFloat(getComputedStyle(probe).fontSize)};
const G={sp:KT.size.filter(t=>/^--sp-/.test(t.n)),h:KT.size.filter(t=>/^--(h-|u$)/.test(t.n)),r:KT.size.filter(t=>/^--r(-|$)/.test(t.n)&&t.n!=='--r-pill'),fs:KT.size.filter(t=>/^--fs/.test(t.n))};
let TV={};
function readTok(){TV={};['sp','h','r'].forEach(g=>G[g].forEach(t=>TV[t.n]=px(`var(${t.n})`)));G.fs.forEach(t=>TV[t.n]=fpx(`var(${t.n})`))}
const tokFor=(v,g)=>{if(v<=1.01)return v<=0.01?'0':'1 px (filet)';const t=G[g].find(t=>Math.abs(TV[t.n]-v)<.6);return t?t.n:null};
const r1=v=>Math.round(v*10)/10;

/* ---------- Mesure ---------- */
const OFF=[];  // [composant, propriété, valeur, élément]
function measure(el,comp){
  const c=getComputedStyle(el),b=el.getBoundingClientRect();
  const chk=(lab,v,g,soft)=>{v=r1(v);const t=tokFor(v,g);if(!t&&!soft)OFF.push([comp,lab,v+' px',el]);return {v,t,soft}};
  const m={name:el.dataset.kv||el.getAttribute('aria-label')||el.textContent.trim().replace(/\s+/g,' ').slice(0,22)||el.className.split(' ')[0]};
  m.h=chk('hauteur',b.height,'h',!el.matches('.btn,.enum,.field:not(.ta),.mi,[role=tab],.vtab,.m-chip,.m-opt,.m-as,.m-vchip,.assign')||el.matches('.m-span'));
  const P=['paddingTop','paddingRight','paddingBottom','paddingLeft'].map(k=>r1(parseFloat(c[k])));m.padAll=P.join(' ');m.pad=[...new Set(P)].map(v=>chk('padding',v,'sp',el.matches('.tree li')));
  const g=(c.display.includes('flex')||c.display.includes('grid'))?(parseFloat(c.columnGap)||parseFloat(c.rowGap)||0):0;m.gap=g?chk('gap',g,'sp'):null;
  const rr=parseFloat(c.borderTopLeftRadius);m.r=rr&&rr<100?chk('arrondi',rr,'r'):null;
  m.fs=chk('police',parseFloat(c.fontSize),'fs');m.fw=c.fontWeight+' · '+c.fontFamily.split(',')[0].replace(/"/g,'');
  m.col=`fond ${col(c.backgroundColor)} · texte ${col(c.color)}${parseFloat(c.borderTopWidth)?' · bord '+col(c.borderTopColor):''}`;
  m.sig=[m.h.v,m.padAll,g,rr,m.fs.v,m.fw,m.col].join('|');return m;
}
const col=v=>{const m=v.match(/[\d.]+/g);if(!m)return v;const [r,g,b,a]=m.map(Number);if(a===0)return 'transparent';const hx='#'+[r,g,b].map(x=>x.toString(16).padStart(2,'0')).join('');
  const L=document.documentElement.dataset.ui==='light';const t=KT.color.find(t=>(L?t.light:t.dark).toLowerCase()===hx)||KT.color.find(t=>(L?t.dark:t.light).toLowerCase()===hx);return hx+(a!=null&&a<1?' '+Math.round(a*100)+'%':'')+(t?' ('+t.n+')':'')};
function specTable(ms){
  const seen=new Set(),rows=ms.filter(m=>!seen.has(m.sig)&&seen.add(m.sig));
  const T=x=>!x?'–':x.t?`<span class="tk">${x.t}</span>`:x.soft?x.v+' px':`<span class="bad">${x.v} px</span>`;
  return `<table class="kt"><tr><th>Variante</th><th>Hauteur</th><th>Padding</th><th>Gap</th><th>Arrondi</th><th>Police</th></tr>${rows.slice(0,8).map(m=>
    `<tr><td class="v">${esc(m.name)}</td><td>${m.h.v} px<br>${m.h.t||m.h.soft?T(m.h):T(m.h)}</td><td>${m.padAll}<br>${m.pad.map(T).join(' ')}</td><td>${T(m.gap)}</td><td>${T(m.r)}</td><td>${T(m.fs)}<br>${esc(m.fw)}</td></tr>`).join('')}</table>
    <table class="kt">${rows.slice(0,4).map(m=>`<tr><th>${esc(m.name)}</th><td>${m.col}</td></tr>`).join('')}</table>`;
}
/* ---------- Spécimens ---------- */
const B=(c,l,a='')=>`<button class="btn ${c}" data-kv="${l}" ${a}>${l}</button>`;
const legend=[['todo',null,'À faire'],['wip',null,'En cours'],['done',null,'Fini'],['done','redo','Fini, repris'],['done','wait','En attente'],['sup',null,'Validé sup'],['val',null,'Validé prod'],['old',null,'À revoir'],['wip','rtk','Retake ouvert'],['val','rtk','Validé, puis retake'],['val','you','Vous : validé'],['done','you-rtk','Vous : retake'],['done',null,'Note ouverte','n'],['na',null,'Non requis']];
const job=F.jobs.find(j=>j.state==='running'),jobF=F.jobs.find(j=>j.state==='failed');
const DESK=[
 {n:'Bouton',c:'.btn',m:'.btn',d:()=>`<div class="lbl-v">Variantes</div><div class="kc-row">${B('','Normal')}${B('primary','Principal')}${B('tool','Outil')}${B('flat','Plat')}${B('ok','Valider')}${B('alert','Retake')}${B('play','Lecture')}</div>
   <div class="lbl-v">États</div><div class="kc-row">${B('','Enfoncé','aria-pressed="true"')}${B('','Désactivé','disabled')}${B('primary','Désactivé','disabled')}</div>
   <div class="lbl-v">Tailles</div><div class="kc-row same">${B('','Normal 28')}<button class="btn icon" data-kv="Icône" aria-label="Icône">${ic('b-preferences')}</button>${B('sm','Petit 24')}<button class="btn sm icon" data-kv="Petite icône" aria-label="Petite icône">${ic('b-x')}</button></div>`,
  r:['Un seul bouton principal (bleu) par zone : celui qu\'on attend.','Vert = valider, rouge = renvoyer, bleu foncé = lire. Jamais pour décorer.','Icône seule : toujours un aria-label et un title.','Sm (24) seulement dans une liste dense ou un en-tête de section.']},
 {n:'Groupe de boutons',c:'.join',m:'.join',same:['.join','.btn'],d:()=>`<span class="join"><button class="btn" aria-pressed="true">Retake</button><button class="btn" aria-pressed="false">Remarque</button></span>
   <span class="join full" style="width:320px"><button class="btn sm" aria-pressed="false">Actif</button><button class="btn sm" aria-pressed="true">En pause</button><button class="btn sm" aria-pressed="false">Annulé</button></span>`,
  r:['Choix exclusif à 2–5 options : groupe. Au-delà : liste déroulante.','Les boutons d\'un groupe ont tous la même taille.']},
 {n:'Champ',c:'.field',m:'.field',d:()=>`<label class="field" style="width:320px">${ic('b-viewzoom')}<input placeholder="Aller à un fichier…" aria-label="Recherche"><span class="kbd">/</span></label>
   <label class="field ta" style="width:320px"><textarea rows="2" placeholder="Retake à cette frame…" aria-label="Texte"></textarea></label><span class="kc-row"><span class="kbd">Ctrl</span><span class="kbd">Entrée</span></span>`,
  r:['Fond le plus sombre (wcol_text) : on sait où on écrit.','Le raccourci clavier dans le champ quand il existe.']},
 {n:'Liste déroulante',c:'.enum',m:'.enum',d:()=>`<div style="width:360px">${verHTML(it1,'k')}</div>`,r:['Toujours la valeur courante visible, avec le compte (1/3).','Ouvre un menu, jamais un select natif en bureau.']},
 {n:'Menu',c:'.menu .mi',m:'.mi,.menu-h',st:1,d:()=>`<div class="menu" role="menu" style="width:260px"><div class="menu-h">Version à regarder</div><button class="mi" aria-checked="true"><span class="ck">${ic('b-checkmark')}</span><span class="lbl">v004-stable_003 · 12/11</span><span class="k">dernière</span></button><button class="mi"><span class="ck"></span><span class="lbl">v004-stable_001</span></button><div class="msep"></div><button class="mi"><span class="ck"></span><span class="lbl">Personne</span></button></div>`,
  r:['Positionné en fixe et recalé dans la fenêtre : jamais coupé.','Coche à gauche, raccourci ou précision à droite (.k).']},
 {n:'Onglets d\'espace',c:'.ws',m:'.ws [role=tab]',d:()=>`<div class="ws" role="tablist">${[['shot','Plans','b-camera_data',26],['asset','Assets','b-asset_manager',4],['links','Liens','b-linked',''],['farm','Farm','b-file_movie',10]].map(([k,l,i,c],n)=>`<button role="tab" aria-selected="${!n}">${ic(i)}<span class="lbl">${l}</span>${c!==''?`<span class="n">${c}</span>`:''}</button>`).join('')}</div>`,r:['Un clic change toute la page. En snapshot, Farm n\'existe pas.']},
 {n:'Onglets verticaux',c:'.vtabs .vtab',m:'.vtab',d:()=>`<div class="vtabs" role="tablist" style="position:static;height:auto">${[['plan','b-camera_data'],['notes','i-note'],['links','b-linked'],['files','b-file']].map(([k,i],n)=>`<button class="vtab" role="tab" aria-selected="${!n}" aria-label="${k}">${ic(i)}</button>`).join('')}</div>`,r:['Le détail d\'un fichier : vidéo d\'abord, le reste en onglets.']},
 {n:'Glyphes d\'état',c:'.g',m:'.legend-list li',d:()=>`<ul class="legend-list">${legend.map(([b,c,l,n])=>`<li>${glyph(b,c,2,!!n)}<span>${l}</span></li>`).join('')}</ul>`,r:['Forme pleine = état de base ; coin = ce qui s\'y ajoute ; bulle = note.','Le texte à côté répète toujours l\'information (jamais la couleur seule).']},
 {n:'Cellule d\'état',c:'.cell',m:'.cell',d:()=>`<div class="kc-row">${DEPTS.shot.map(d=>cellHTML(it3,d)).join('')}</div>`,r:['Glyphe + libellé + précision tronquée ; le title donne tout.']},
 {n:'Étiquette',c:'.tag',m:'.tag',d:()=>`<div class="kc-row"><span class="tag check" data-kv="check">à vérifier</span><span class="tag you" data-kv="you">vous</span><span class="tag rtk" data-kv="rtk">2 RTK</span><span class="tag omit" data-kv="omit">En pause</span><span class="tag fail" data-kv="fail">farm failed</span></div>`,r:['Une étiquette dit un fait sur le fichier, elle ne se clique pas.']},
 {n:'Attribution',c:'.assign',m:'.assign',d:()=>`<div class="kc-row">${assignHTML(it1,'animation','k')}${assignHTML(it1,'render','k2')}${assignHTML(it3,'lighting','k3')}</div>`,r:['En pointillés : personne. En bleu : changé dans votre revue.']},
 {n:'Puce de frame',c:'.ft',m:'.ft',d:()=>`<div class="kc-row"><span class="ft" data-kv="retake">f42</span><span class="ft rg" data-kv="plage">f42-58</span><span class="ft nt" data-kv="note">f12</span></div>`,r:['Rouge : retake, même en plage. Gris : remarque. Cliquer y va.']},
 {n:'Progression',c:'.jbar .sf',m:'.jbar,.sf',d:()=>`<span class="jbar" style="width:280px"><i style="--p:42%"></i><span>40 / 96 frames</span></span><span class="sf" style="--p:74%;--c:var(--st-done);width:280px"><span class="lab">Fait</span>74 %</span>`,r:['Toujours le chiffre à côté de la barre.']},
 {n:'Lecteur et transport',c:'.stage .scrub .ctl',m:'.ctl .btn,.ctl .enum,.scrub',same:['.ctl','.btn,.enum'],wide:1,d:()=>`<div style="max-width:520px">${stageHTML(it1)}</div>`,r:['Tous les boutons de transport ont la même taille ; Lecture en bleu foncé.','Repères : losange rouge = retake, gris = note ; plage en rouge.']},
 {n:'Carte de département',c:'.dept',m:'.dept',wide:1,d:()=>`<div style="max-width:520px;display:flex;flex-direction:column;gap:var(--sp-4)">${DEPTS.shot.map(d=>deptHTML(it2,d,'k')).join('')}</div>`,r:['Une carte par département requis ; les non requis n\'apparaissent pas.','Actions alignées à droite, toujours au même endroit.']},
 {n:'Note',c:'.nt',m:'.nt',wide:1,d:()=>`<div style="max-width:520px">${[...it2.myNotes.map(n=>({...n,mine:1})),...it1.notes.slice(0,2)].map(n=>noteHTML(n.mine?it2:it1,n)).join('')}</div>`,r:['Les vôtres en bleu tant qu\'elles ne sont pas envoyées.']},
 {n:'Liste : séquence et lignes',c:'.grp-h .row',m:'.row,.grp-h',wide:1,d:()=>`<section class="area" id="main" style="height:520px"><div class="area-body" id="list"></div></section>`,after:()=>{S.ws='shot';S.q='sq990_sh0';renderList();S.q=''},r:['Séparateurs entre lignes, pas de bandes alternées.','En-tête de séquence plus clair, Lire la séquence à côté du nom.']},
 {n:'Arborescence',c:'.tree',m:'.tree li',d:()=>`<div class="area" style="height:300px;width:260px"><div class="area-body"><ul class="tree" id="tree"></ul></div></div>`,after:()=>{S.tq='sq0';renderTree();S.tq=''},r:['Repliée indépendamment de la liste.']},
 {n:'Propriété',c:'.prop',m:'.prop',wide:1,d:()=>`<div style="max-width:520px">${filesHTML(it1)}</div>`,r:['Libellé à gauche (largeur fixe), valeur et action à droite.']},
 {n:'Nodes de liens',c:'.node',m:'.node',wide:1,d:()=>`<div style="max-width:620px" id="pbody">${linksHTML(as1)}</div>`,after:()=>requestAnimationFrame(drawWires),r:['Couleur d\'en-tête = type (asset / plan / ancien stable).','Fils en bézier, jamais par-dessus un node.']},
 {n:'Job de farm',c:'.job',m:'.job',wide:1,d:()=>`<div class="jobs" style="max-width:620px">${jobRow(job)}${jobRow(jobF)}</div>`,r:['État (pastille) · fichier · % · machines. Live seulement.']},
 {n:'Popover',c:'.pop',m:'.pop',st:1,d:()=>`<div class="pop news" style="width:320px"><h4>Quoi de neuf</h4><button class="newsi"><span class="dt" style="background:var(--st-rtk)"></span><span class="tx"><span class="h"><b>sq990_sh010</b><span class="faint">19:40</span></span>léa a écrit un retake<small>Animation · f40</small></span></button><p class="hint">Les notes, retakes, validations et rendus arrivent ici.</p></div>`,r:['Accroché à son bouton ; se ferme au clic dehors et à Échap.']},
 {n:'Dialogue',c:'.dlg-in',m:'.dlg-in,.dlg-in .prop',st:1,wide:1,d:()=>`<div id="k-dlg"></div>`,after:()=>{renderDlg();$('#k-dlg').innerHTML=$('#dlg').innerHTML;$('#dlg').hidden=true;$('#dlg').innerHTML=''},r:['Titre, réglages en lignes .prop, actions en bas à droite ; Échap ferme.']},
 {n:'Bulle de visite et message',c:'.tour .toast',m:'.tour,.toast',st:1,d:()=>`<div class="tour"><b>Le mode revue</b><p>Votre nom et votre rôle, puis validez, renvoyez, attribuez.</p><div class="acts"><span class="faint">6 / 7</span><span style="flex:1"></span><button class="btn sm flat">Passer</button><button class="btn sm primary">Suivant</button></div></div><div class="toast">Envoyé à Blender : rendu mis en file</div>`,r:['Le message confirme une action ; il ne demande rien.']},
];
/* Mobile : les pièces sont découpées dans le vrai rendu mobile. */
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
 {n:'Barre du haut · barre du bas',c:'.m-top .m-ib .m-nav',m:'.m-top,.m-ib,.m-nav button',d:()=>PH('haut',`<header class="m-top"><span class="m-brand"><b>alive</b><small>live · Valerie · prod</small></span><span class="sp"></span><button class="m-ib" aria-label="Quoi de neuf">${ic('i-bell')}<span class="cnt">2</span></button><button class="btn primary">${ic('b-export')}Envoyer<span class="n">4</span></button><button class="m-ib" aria-label="Menu">${ic('b-preferences')}</button></header>`)+PH('bas · live seulement',`<nav class="m-nav"><button aria-selected="true">${ic('b-file_movie')}<span>Revue</span></button><button aria-selected="false">${ic('b-render_animation')}<span>Farm</span><span class="dot bad"></span></button></nav>`),r:['Haut : projet, mode, cloche (live), Envoyer quand on est en revue.','Bas : Revue | Farm, seulement en live. En snapshot, pas de barre.']},
 {n:'Choix du plan',c:'.m-shotnav .m-pick',m:'.m-pick,.m-shotnav .m-ib',d:()=>PH('plan par plan',`<div class="m-body">${MP.nav}</div>`),r:['Un plan à la fois ; ◀ ▶ ou glisser sur l\'image ; le filtre du parcours reste affiché.']},
 {n:'Lecteur et comparaison A / B',c:'.m-player .m-tp .m-vers',m:'.m-tp .btn,.m-vchip,.scrub',same:['.m-tp','.btn'],wide:1,d:()=>PH('A / B à la même frame',`<div class="m-body">${MP.player}${MP.scrub}${MP.tp}${MP.vers}</div>`),r:['A bleu, B orange, sur la puce et autour de l\'image : on sait toujours ce qu\'on regarde.','Basculer garde la frame.']},
 {n:'Carte de département',c:'.m-dept .m-as',m:'.m-dept,.m-da .btn,.m-as',wide:1,d:()=>PH('valider · retake · attribuer',`<div class="m-body">${MP.dept}</div>`),r:['Valider / Retake en deux colonnes égales, 44 px.','L\'attribution est sur la carte, pas dans un menu.']},
 {n:'Note et zone d\'écriture',c:'.m-note .m-comp .m-chip',m:'.m-note,.m-comp .btn,.m-chip,.m-comp .field',wide:1,d:()=>PH('collée en bas',`<div class="m-body">${MP.note}</div>${MP.comp}`),r:['Type, département et frame en puces au-dessus du texte ; la frame se remplit seule.','16 px dans les champs : iOS ne zoome pas.']},
 {n:'Feuille : choix',c:'.m-sheet .m-opt',m:'.m-opt,.m-sheet-h,.m-filters .m-chip',wide:1,d:()=>PH('choisir un fichier',MP.pick)+PH('attribuer',MP.as),r:['Un seul composant pour tous les choix du mobile.','Coche à gauche, précision en petit dessous.']},
 {n:'Feuille : interrupteurs',c:'.m-opt.sw',m:'.m-opt.sw',d:()=>PH('ajouter un département',MP.depts),r:['Départements requis : ajout et retrait, envoyés avec la revue.']},
 {n:'Farm · rendre un plan',c:'.m-card .m-job .m-select',m:'.m-card,.m-job,.m-select,.m-sheet-f .btn',wide:1,d:()=>PH('suivre',`<div class="m-body">${MP.card}${MP.jobs}</div>`)+PH('rendre',MP.render)+PH('un job',MP.job),r:['Live seulement. Fichier, version, script, priorité : le reste en bureau.','Select natif sur mobile (liste longue, clavier du système).']},
];
const RULES=[['Espacements','Uniquement --sp-1 à --sp-11. Dans une box : --sp-6 de padding, --sp-4 entre widgets, --sp-7 entre sections.'],
 ['Hauteurs','Widget 28 (--u), petit 24 (--h-sm), en-tête 36 (--h-lg). Mobile : 44 (--h-touch) partout où l\'on touche.'],
 ['Arrondis','5 (--r) pour les widgets comme Blender, 8 (--r-l) pour les box et menus, 10 (--r-xl) pour dialogues et feuilles.'],
 ['Texte','13 courant, 11.5 secondaire, 15 titres de zone, 18 titres de page. Mono pour les noms de fichiers et les frames.'],
 ['Couleurs','Jamais de couleur en dur dans un composant : une variable de 10-tokens.css (sombre et clair). Les états ont leurs couleurs fixes.'],
 ['Snapshot / live','Ce qui demande Blender porte .live-only. En snapshot : pas de Farm, pas de Rendre, pas d\'ouverture dans Blender, pas de cloche.'],
 ['Bureau / mobile','Mobile si tactile ET < 900 px. Mêmes actions (A.*), mêmes sélecteurs ; l\'affichage seul change.']];

/* ---------- Rendu ---------- */
function card(s,i,kind){return `<div class="kc ${s.wide?'wide':''}" id="${kind}${i}"><div class="kc-h"><b>${s.n}</b><code>${s.c}</code><span class="w" data-w></span></div>
  <div class="kc-b"><div class="kc-demo ${s.st?'k-static':''}">${s.d()}</div><div class="kc-spec"><div data-spec></div><ul>${s.r.map(x=>`<li>${x}</li>`).join('')}</ul></div></div></div>`}
function renderKit(){
  readTok();
  const row=(t,g)=>{const v=g==='fs'?TV[t.n]:TV[t.n];const vis=g==='sp'?`<span class="k-bar" style="width:${v*3}px"></span>`:g==='h'?`<span class="k-hbox" style="height:${v}px"></span>`:g==='r'?`<span class="k-box" style="border-radius:${v}px"></span>`:`<span style="font-size:${v}px;color:var(--text)">Plan sq030_sh040</span>`;
    return `<div class="k-tr"><code>${t.n}</code><span class="f">${esc(t.v)}</span><span class="px">${r1(v)} px</span><span class="vis">${vis}${t.c?`<span style="margin-left:var(--sp-5)">${esc(t.c)}</span>`:''}</span></div>`};
  $('#k-sp').innerHTML=G.sp.map(t=>row(t,'sp')).join('');$('#k-h').innerHTML=G.h.map(t=>row(t,'h')).join('');$('#k-r').innerHTML=G.r.map(t=>row(t,'r')).join('');$('#k-fs').innerHTML=G.fs.map(t=>row(t,'fs')).join('');
  let grp='';$('#k-col').innerHTML=`<table class="k-ctab"><tr><th>Variable</th><th>Sombre</th><th>Clair</th><th class="hide-s">Rôle</th></tr>${KT.color.map(t=>{const gg=t.n.startsWith('--st-')?'États (fixes)':t.n.startsWith('--node')||['--sock','--wire','--wire-edge'].includes(t.n)?'Nodes':/^--(play|alert|ok|you|rtk-t|wip-t|live-t)/.test(t.n)?'Accents':'Interface';
    const h=gg!==grp?`<tr class="k-grp"><td colspan="4">${gg}</td></tr>`:'';grp=gg;
    return h+`<tr><td class="m">${t.n}</td><td class="m"><span class="k-sw" style="background:${t.dark}"></span>${t.dark}</td><td class="m"><span class="k-sw" style="background:${t.light||t.dark}"></span>${t.light||'='}</td><td class="hide-s">${esc(t.c||'')}</td></tr>`}).join('')}</table>`;
  $('#k-desk').innerHTML=DESK.map((s,i)=>card(s,i,'d')).join('');DESK.forEach(s=>s.after&&s.after());
  mobPieces();$('#k-mob').innerHTML=`<h3 style="margin-top:0">Le vrai affichage mobile, interactif</h3><div class="k-phones" id="k-live"></div>`+MOBC.map((s,i)=>card(s,i,'m')).join('');
  const mob=$('#mob');mob.hidden=false;mob.classList.add('k-phone');$('#k-live').appendChild(mob);S.m.sheet=null;mRender();
  $('#k-rules').innerHTML=`<div class="k-rules">${RULES.map(([h,p])=>`<div class="k-rule"><h4>${h}</h4><p>${p}</p></div>`).join('')}</div>`;
  requestAnimationFrame(()=>requestAnimationFrame(specAll));
}
function specAll(){
  OFF.length=0;readTok();const SAME=[];
  [...DESK.map((s,i)=>[s,'d'+i]),...MOBC.map((s,i)=>[s,'m'+i])].forEach(([s,id])=>{const el=document.getElementById(id);
    const ms=[...el.querySelectorAll('.kc-demo '+s.m.split(',').join(',.kc-demo '))].filter(e=>e.offsetParent).slice(0,40).map(e=>measure(e,s.n));
    el.querySelector('[data-spec]').innerHTML=specTable(ms);
    const off=OFF.filter(o=>o[0]===s.n).length;let warn=off?off+' hors échelle':'';
    if(s.same){const [gs,cs]=s.same;el.querySelectorAll('.kc-demo '+gs).forEach(g=>{const hs=[...new Set([...g.querySelectorAll(cs)].filter(e=>e.offsetParent).map(e=>r1(e.getBoundingClientRect().height)))];if(hs.length>1){warn+=(warn?' · ':'')+'hauteurs '+hs.join(' / ');SAME.push([s.n+' · '+gs,hs.join(' / ')+' px'])}})}
    const w=el.querySelector('[data-w]');w.textContent=warn;w.className=warn?'w':'okk';if(!warn)w.textContent='✓ sur l\'échelle'});
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
  const hrows=Object.entries(hs).sort((a,b)=>a[0]-b[0]).map(([h,s])=>[h+' px'+(tokFor(+h,'h')?' · '+tokFor(+h,'h'):' · hors échelle'),[...s].slice(0,6).join(' ')]);
  const box=(t,p,L,ok)=>`<div class="ka"><h4>${t}<span class="n ${L.length?'':'z'}">${L.length}</span></h4><p>${p}</p>${L.length?`<ul>${L.slice(0,80).map(([a,b])=>`<li><b title="${esc(a)}">${esc(a)}</b><span>${esc(b)}</span></li>`).join('')}</ul>`:`<p>${ok}</p>`}</div>`;
  $('#k-audit').innerHTML=box('Mesures hors échelle','Mesurées sur les composants ci-dessous : une valeur qui ne tombe sur aucun jeton.',Object.entries(OFF.reduce((m,o)=>{const k=o[0]+'\u0001'+o[1]+' '+o[2];m[k]=(m[k]||0)+1;return m},{})).map(([k,n])=>{const [c,v]=k.split('\u0001');return [c,v+(n>1?' ×'+n:'')]}),'Tout tombe sur un jeton.')
    +box('Groupes à hauteurs mêlées','Des widgets côte à côte qui n\'ont pas la même hauteur.',SAME,'Aucun.')
    +box('Hauteurs de widgets en bureau','Toutes les hauteurs rencontrées : il en faut le moins possible (idéal : 24 et 28).',hrows,'')
    +box('Tailles encore en px dans le CSS','Padding, marges, gaps, arrondis et polices écrits en dur au lieu d\'un jeton.',hard,'Aucune.')
    +box('Icônes et repères en px','Hauteurs fixes de petits éléments (icônes, pastilles, barres). Candidats à des jetons --ic-*.',icons,'Aucun.')
    +box('Couleurs en dur','Hors des variables : elles ne suivront pas le thème sombre / clair.',hex,'Aucune.');
  $('#k-toc').innerHTML=`<a href="#audit" class="h">Audit</a><a href="#fond" class="h">Fondations</a><a href="#desk" class="h">Bureau</a>${DESK.map((s,i)=>`<a href="#d${i}">${s.n}${document.querySelector('#d'+i+' [data-w].w')?'<span class="w">●</span>':''}</a>`).join('')}<a href="#mobi" class="h">Mobile</a>${MOBC.map((s,i)=>`<a href="#m${i}">${s.n}${document.querySelector('#m'+i+' [data-w].w')?'<span class="w">●</span>':''}</a>`).join('')}<a href="#regles" class="h">Règles</a>`;
}
document.addEventListener('click',e=>{const t=e.target.closest('[data-ktheme]');if(t){document.querySelectorAll('[data-ktheme]').forEach(b=>b.setAttribute('aria-pressed',b===t));setTheme(t.dataset.ktheme);requestAnimationFrame(specAll)}
  const s=e.target.closest('[data-kscale]');if(s){document.querySelectorAll('[data-kscale]').forEach(b=>b.setAttribute('aria-pressed',b===s));S.scaleV=+s.dataset.kscale;document.documentElement.style.setProperty('--scale',s.dataset.kscale);requestAnimationFrame(()=>{drawWires();specAll()})}});
setTheme('dark');renderKit();
