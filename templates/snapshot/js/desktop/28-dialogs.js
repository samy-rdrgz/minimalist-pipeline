/* ---------- Événements ---------- */
function placeMenu(b,m){m.classList.add('fx');m.style.left='0px';m.style.top='0px';const r=b.getBoundingClientRect(),w=m.offsetWidth,h=m.offsetHeight;
  let x=m.classList.contains('right')?r.right-w:r.left;x=Math.max(8,Math.min(x,innerWidth-w-8));let y=r.bottom+4;if(y+h>innerHeight-8)y=Math.max(8,r.top-h-4);m.style.left=x+'px';m.style.top=y+'px'}
const stillHTML=(it,d)=>{const f=it.flags[d]||{};if(!S.review||!f.to_redo)return it.still&&it.still[d]?'<span class="tag you">toujours fini · vous</span>':'';
  return `<button class="btn sm ${it.still[d]?'':'tool'}" data-still="${d}" aria-pressed="${!!it.still[d]}" title="À refaire : ${esc(f.to_redo)}. Toujours fini : le travail fait tient, ce n'est pas une validation">${ic('b-checkmark')}Toujours fini</button>`};
const fixHTML=(it,n)=>{if(!S.review||n.mine||n.done||n.type==='note')return '';const on=!!it.fixed[n.id];
  return `<button class="btn sm ${on?'ok':'flat'}" data-fix="${n.id}" aria-pressed="${on}" title="${on?'Annuler':'Marquer '+(n.type==='rtk'?'corrigé':'fait')+' : appliqué à l\'import de votre revue'}">${ic('b-checkmark')}${on?'Corrigé · vous':(n.type==='rtk'?'Marquer corrigé':'Marquer fait')}</button>`};
function seqNext(){const it=cur(),sib=items.filter(i=>i.kind===it.kind&&groupOf(i)===groupOf(it)&&!omitted(i));const n=sib.findIndex(i=>i.name===it.name);
  if(n<0||n>=sib.length-1){S.seqPlay=false;togglePlay();msg('Fin de la séquence '+groupOf(it));renderWide();return}
  S.frame=1;select(sib[n+1].name,{open:false});}
const RF={};
const rform=it=>RF[it.name]=RF[it.name]||{ver:it.stable?'stable':'last',preset:S.preset,prio:10,mode:'all',sound:'on',off:{},start:'',end:'',frames:false};
function renderDlg(){
  const it=cur(),f=rform(it),dl=$('#dlg');const seg=(k,v,l)=>`<button class="btn sm" data-rf="${k}" data-v="${v}" aria-pressed="${f[k]===v}">${l}</button>`;
  const job=F.jobs.find(j=>!j.archived&&(j.state==='running'||j.state==='waiting')&&j.file.startsWith(it.name+'_'));
  const pr=F.presets.find(p=>p[0]===f.preset)||F.presets[0];
  dl.hidden=false;dl.innerHTML=`<div class="dlg-in rnd" role="dialog" aria-modal="true" aria-labelledby="rd-t"><h3 id="rd-t">${ic('b-file_movie')} Rendre ${esc(it.name)}</h3>
    ${job?`<p class="tag check" style="align-self:flex-start">Déjà dans la farm : ${esc(job.text)}${job.total?' · '+job.done+'/'+job.total:''}</p>`:''}
    <div class="prop"><span class="k">Version</span><span class="v"><span class="join full" style="flex:1">${it.stable?seg('ver','stable','Dernier stable · '+esc(it.stable)):''}${seg('ver','last','Dernière · '+esc(it.wip||it.stable||''))}</span></span></div>
    <div class="prop"><span class="k">Script avant rendu</span><span class="v"><span class="anchor" style="flex:1;min-width:0"><button class="enum" style="width:100%" data-menu="m-rpreset" aria-haspopup="true" aria-expanded="false"><span class="lb">${esc(pr[1])}</span>${ic('b-tria_down')}</button>
      <div class="menu" id="m-rpreset" hidden role="menu">${F.presets.map(p=>`<button class="mi" data-rpreset="${esc(p[0])}"><span class="ck">${p[0]===f.preset?ic('b-checkmark'):''}</span><span class="lbl">${esc(p[1])}</span></button>`).join('')}</div></span></span></div>
    <div class="prop"><span class="k">Frames</span><span class="v">${f.frames?`<label class="field" style="width:96px"><span class="faint">de</span><input data-rfn="start" value="${esc(f.start)}" placeholder="fichier" aria-label="Première frame"></label><label class="field" style="width:96px"><span class="faint">à</span><input data-rfn="end" value="${esc(f.end)}" placeholder="fichier" aria-label="Dernière frame"></label><button class="btn sm flat" data-rft>celles du fichier</button>`:`<span class="dim">celles du fichier</span><button class="btn sm tool" data-rft>Choisir</button>`}</span></div>
    <div class="prop"><span class="k">Priorité</span><span class="v"><span class="prio"><button class="btn sm icon" data-rprio="-1" aria-label="Baisser">−</button><b>${f.prio}</b><button class="btn sm icon" data-rprio="1" aria-label="Monter">+</button><span class="faint">la plus haute passe d'abord</span></span></span></div>
    <div class="prop"><span class="k">Machines</span><span class="v"><span class="join">${seg('mode','all','Toutes')}${seg('mode','single','Une seule')}</span></span></div>
    <div class="prop"><span class="k">Son</span><span class="v"><span class="join" title="Le son de la scène (séquenceur, speakers) dans la vidéo">${seg('sound','on','Avec le son')}${seg('sound','off','Sans le son')}</span></span></div>
    ${it.shots&&it.shots.length>1?`<div class="prop"><span class="k">Plans</span><span class="v"><span class="join">${it.shots.map(x=>`<button class="btn sm" data-rshot="${x}" aria-pressed="${!f.off[x]}">${x}</button>`).join('')}</span></span></div>`:''}
    <div class="acts">${it.kind==='shot'?`<button class="btn" data-rprev title="Les dernières vidéos de chaque plan de ${it.group}, bout à bout">Prévisualiser ${it.group}</button>`:''}<span style="flex:1"></span><button class="btn" data-dclose>Annuler</button><button class="btn primary" data-rsend>${ic('b-export')}Envoyer à la farm</button></div></div>`;
}
const NEWS=[];let newsSeen=0;
/* What's new (live): a change seen in the data Blender sends (applyData()). */
function pushNews(k,n,h,x){NEWS.unshift({k,n,h,x,at:new Date().toLocaleTimeString(LOCALE(),{hour:'2-digit',minute:'2-digit'})});renderNewsBtn();
  if(S.notifSys&&window.Notification&&Notification.permission==='granted'){try{new Notification(n+' · '+h,{body:x})}catch(_){}}}
function renderNewsBtn(){if(isMob()){if(!S.m.sheet)mRender();return}const b=$('#news-b');if(!b)return;const n=NEWS.length-newsSeen;b.querySelector('.cnt').textContent=n;b.querySelector('.cnt').hidden=!n}
function newsPop(btn){const old=document.querySelector('.pop.news');if(old){old.remove();return}newsSeen=NEWS.length;renderNewsBtn();
  const p=document.createElement('div');p.className='pop news';p.setAttribute('role','dialog');p.setAttribute('aria-label','Quoi de neuf');
  const IC={rtk:'--st-rtk',render:'--st-done',ok:'--st-val'};
  p.innerHTML=`<h4>Quoi de neuf</h4>${NEWS.length?NEWS.map(x=>`<button class="newsi" data-goto-file="${x.n}"><span class="dt" style="background:var(${IC[x.k]})"></span><span class="tx"><span class="h"><b>${esc(x.n)}</b><span class="faint">${x.at}</span></span>${esc(x.h)}<small>${esc(x.x)}</small></span></button>`).join(''):'<p class="hint">Rien de nouveau depuis l\'ouverture de la page : les notes, retakes, validations et rendus arrivent ici.</p>'}
    <label class="check"><input type="checkbox" id="notif-sys" ${S.notifSys?'checked':''}> Me notifier aussi dans le système</label>`;
  btn.parentElement.appendChild(p);
}
const TOUR=[['#ws','Les espaces','Plans, Assets, Liens, Synthèse et Farm : un clic change toute la page.'],
  ['#quick','Les filtres','Retakes, notes, à valider : un clic filtre la liste. « Filtres » ouvre le reste.'],
  ['#list .row','Un fichier','Chaque losange est un département : sa forme dit l\'état, le coin ce qui s\'y ajoute.'],
  ['#ptabs','Le détail','Plan, Notes, Liens, Fichiers et rendus : le fichier sélectionné, en onglets.'],
  ['[data-wide]','En grand','La vidéo en grand, les départements à côté : on écrit les retakes en regardant.'],
  ['#review-slot','Le mode revue','Votre nom et votre rôle, puis validez, renvoyez, attribuez. Envoyer… donne le fichier à importer dans Blender.'],
  ['#help-b','La légende','Les états, les raccourcis, et cette visite.']];
let tourAt=-1;
function tour(n){document.querySelectorAll('.tour-hl').forEach(e=>e.classList.remove('tour-hl'));$('#tour')?.remove();
  if(n<0||n>=TOUR.length){tourAt=-1;return}
  let el=document.querySelector(TOUR[n][0]);if(!el||!el.offsetParent){if(n<TOUR.length-1)return tour(n+1);return tour(-1)}
  tourAt=n;el.scrollIntoView({block:'nearest'});el.classList.add('tour-hl');const r=el.getBoundingClientRect();
  const b=document.createElement('div');b.id='tour';b.className='tour';b.setAttribute('role','dialog');b.setAttribute('aria-live','polite');
  b.innerHTML=`<b>${TOUR[n][1]}</b><p>${TOUR[n][2]}</p><div class="acts"><span class="faint">${n+1} / ${TOUR.length}</span><span style="flex:1"></span>${n<TOUR.length-1?'<button class="btn sm flat" data-tour="end">Passer</button><button class="btn sm primary" data-tour="next">Suivant</button>':'<button class="btn sm primary" data-tour="end">Terminer</button>'}</div>`;
  document.body.appendChild(b);const w=b.offsetWidth,h=b.offsetHeight;let x=Math.min(Math.max(8,r.left),innerWidth-w-8),y=r.bottom+10;if(y+h>innerHeight-8)y=Math.max(8,r.top-h-10);b.style.left=x+'px';b.style.top=y+'px';
}
function setTheme(t){S.theme=t;try{localStorage.setItem('mp-snapshot:theme',t)}catch(_){}
  const sys=matchMedia('(prefers-color-scheme: light)').matches;const ui=t==='light'||(t==='system'&&sys)?'light':'dark';
  document.documentElement.dataset.ui=ui;if(t==='blender')applyBlenderTheme();else document.documentElement.removeAttribute('style'),document.documentElement.style.setProperty('--scale',S.scaleV||1);
  closeMenus();if(S.ws==='links')requestAnimationFrame(drawGraph);
}
/* Blender's theme, read at the export (meta.theme: {css variable: colour}); none, Blender's dark. */
function applyBlenderTheme(){document.documentElement.dataset.ui='dark';Object.entries(M.theme||{}).forEach(([k,v])=>document.documentElement.style.setProperty(k,v))}
function planDlg(g,kind){
  const its=items.filter(i=>i.kind===kind&&groupOf(i)===g);let next='';
  if(kind==='shot'){const nums=its.flatMap(i=>[i.name,...(i.shots||[]).map(s=>g+'_'+s)]).map(n=>+(n.match(/sh(\d+)/)||[])[1]||0).concat(S.planned.filter(p=>p.g===g).map(p=>+(p.name.match(/sh(\d+)/)||[])[1]||0));next=g+'_sh'+String(Math.max(0,...nums)+10).padStart(3,'0')}
  else next=g+'_';
  const dl=$('#dlg');dl.hidden=false;
  dl.innerHTML=`<div class="dlg-in" role="dialog" aria-modal="true" aria-labelledby="pl-t"><h3 id="pl-t">Nouveau ${kind==='shot'?'plan dans '+g:'fichier '+g+'_…'}</h3>
    <p class="faint" style="margin:0">Créé dans le projet à l'import de votre revue, avec ses dossiers.</p>
    <div class="prop"><span class="k">Nom</span><span class="v"><label class="field" style="flex:1"><input id="pl-n" value="${next}" aria-label="Nom"></label></span></div>
    <div class="prop"><span class="k">Description</span><span class="v"><label class="field" style="flex:1"><input id="pl-d" placeholder="Ce qu'il montre" aria-label="Description"></label></span></div>
    <div class="prop"><span class="k">Départements</span><span class="v"><span class="join">${DEPTS[kind].map(d=>`<button class="btn sm" data-pld="${d}" aria-pressed="true">${LBL[d]}</button>`).join('')}</span></span></div>
    <div class="acts"><button class="btn" data-dclose>Annuler</button><button class="btn primary" data-plok="${g}" data-plk="${kind}">${ic('b-add')}Ajouter à ma revue</button></div></div>`;
  setTimeout(()=>$('#pl-n').focus(),0);
}
function bulkDlg(){
  const o=S.bulk=S.bulk||{kind:'shot',g:'',d:DEPTS.shot[0],on:true};
  const pool=items.filter(i=>i.kind===o.kind&&(!o.g||groupOf(i)===o.g)),gs=[...new Set(items.filter(i=>i.kind===o.kind).map(groupOf))];
  const n=pool.filter(i=>required(i).includes(o.d)!==o.on).length;
  const dl=$('#dlg');dl.hidden=false;
  dl.innerHTML=`<div class="dlg-in" role="dialog" aria-modal="true" aria-labelledby="bk-t"><h3 id="bk-t">Départements de plusieurs fichiers</h3>
    <div class="prop"><span class="k">Fichiers</span><span class="v"><span class="join">${[['shot','Plans'],['asset','Assets']].map(([k,l])=>`<button class="btn sm" data-bk="kind" data-v="${k}" aria-pressed="${o.kind===k}">${l}</button>`).join('')}</span></span></div>
    <div class="prop"><span class="k">${o.kind==='shot'?'Séquence':'Préfixe'}</span><span class="v"><span class="join">${['',...gs].map(g=>`<button class="btn sm" data-bk="g" data-v="${g}" aria-pressed="${o.g===g}">${g||'Toutes'}</button>`).join('')}</span></span></div>
    <div class="prop"><span class="k">Département</span><span class="v"><span class="join">${DEPTS[o.kind].map(d=>`<button class="btn sm" data-bk="d" data-v="${d}" aria-pressed="${o.d===d}">${LBL[d]}</button>`).join('')}</span></span></div>
    <div class="prop"><span class="k">Le rendre</span><span class="v"><span class="join"><button class="btn sm" data-bk="on" data-v="1" aria-pressed="${o.on}">requis</button><button class="btn sm" data-bk="on" data-v="0" aria-pressed="${!o.on}">non requis</button></span></span></div>
    <p class="dim" style="margin:0">${n} fichier${n>1?'s':''} sur ${pool.length} change${n>1?'nt':''}.</p>
    <div class="acts"><button class="btn" data-dclose>Annuler</button><button class="btn primary" data-bkok ${n?'':'disabled'}>Appliquer à ${n} fichier${n>1?'s':''}</button></div></div>`;
}
