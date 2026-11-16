/* ---------- Affichage mobile ----------
   Tactile ET étroit (< 900 px ; une tablette en paysage reste en desktop). Deux usages seulement :
   · Revue (snapshot et live) : un plan à la fois, deux versions comparées à la même frame,
     valider, retake, attribuer, ajouter un département, écrire une note à la frame.
   · Farm (live seulement) : l'état de la farm, les jobs et leur %, relancer, rendre un plan.
   Le reste (liens, synthèse, outliner, réglages de fichiers) n'existe pas ici : version bureau.
   Lit le même état S, les mêmes sélecteurs (info, versOf, marks…) et appelle les mêmes actions A. */
const mSib=()=>items.filter(i=>i.kind===S.m.kind&&!omitted(i)&&(!S.m.filter||(S.m.filter==='val'?toValidate(i):S.m.filter==='rtk'?openRtk(i)>0:openNotes(i)>0)));
const mF={'':'Tout',val:'À valider',rtk:'Retakes',note:'Notes'};
const mShort=it=>it.kind==='shot'?it.name.replace(it.group+'_',''):it.name;
const mGl=it=>DEPTS[it.kind].filter(d=>required(it).includes(d)).map(d=>{const x=info(it,d);return glyph(x.base,x.corner,x.cnt,x.note)}).join('');

function mRender(){
  const R=$('#mob');if(!LIVE)S.m.tab='review';
  const ta=$('#m-ta'),keep=ta?ta.value:'',foc=document.activeElement===ta,top=$('#m-body')?.scrollTop||0;
  const n2=items.filter(touched).length+S.planned.length,nn=NEWS.length-newsSeen;
  R.innerHTML=`<header class="m-top"><span class="m-brand"><b>${esc(M.project)}</b><small>${LIVE?'live':'snapshot du '+fmtD(M.snapshot)}${S.review?' · '+esc(S.review.name)+' · '+S.review.role:''}</small></span><span class="sp"></span>
      ${LIVE?`<button class="m-ib" data-msheet="news" aria-label="Quoi de neuf">${ic('i-bell')}${nn?`<span class="cnt">${nn}</span>`:''}</button>`:''}
      ${S.review?`<button class="btn primary" data-msheet="send">${ic('b-export')}Envoyer<span class="n">${n2}</span></button>`:''}
      <button class="m-ib" data-msheet="menu" aria-label="Menu">${ic('b-preferences')}</button></header>
    <main class="m-body" id="m-body">${S.m.tab==='farm'?mFarm():mReview()}</main>
    ${S.m.tab==='review'?mComposer():''}
    ${LIVE?`<nav class="m-nav" role="tablist"><button role="tab" data-mtab="review" aria-selected="${S.m.tab==='review'}">${ic('b-file_movie')}<span>Revue</span></button>
      <button role="tab" data-mtab="farm" aria-selected="${S.m.tab==='farm'}">${ic('b-render_animation')}<span>Farm</span>${F.jobs.some(j=>!j.archived&&j.state==='failed')?'<span class="dot bad"></span>':''}</button></nav>`:''}
    ${S.m.sheet?mSheet():''}`;
  const nb=$('#m-body');if(nb)nb.scrollTop=top;
  const t2=$('#m-ta');if(t2){t2.value=keep;if(foc)t2.focus()}
}

/* ----- Revue : un plan ----- */
function mReview(){
  const it=cur();if(!it)return '<div class="empty">Aucun fichier.</div>';
  const sib=mSib(),k=sib.findIndex(i=>i.name===it.name),{V,a,b,i}=mVer(it),v=V[i],rv=S.review;
  const mk=marks(it);
  const mkH=mk.map(f=>{const x=(f.a-1)/(NF-1)*100;return (f.b?`<span class="rng" style="left:${x}%;width:${(f.b-f.a)/(NF-1)*100}%"></span>`:'')+`<button class="mk ${f.rtk?'':'n'}" style="left:${x}%" data-goto="${f.a}" aria-label="${f.rtk?'Retake':'Note'} f${f.a}"></button>`}).join('');
  const rng=S.rangeStart!=null?`<span class="rng sel" id="rng-sel" style="left:${(Math.min(S.rangeStart,S.frame)-1)/(NF-1)*100}%;width:${Math.abs(S.frame-S.rangeStart)/(NF-1)*100}%"></span>`:'';
  const req=DEPTS[it.kind].filter(d=>required(it).includes(d));
  const notes=[...it.myNotes.map(n=>({...n,mine:true})),...it.notes.filter(n=>!n.done)];
  return `<div class="m-shotnav"><button class="m-ib" data-mstep="-1" aria-label="Plan précédent" ${k<=0?'disabled':''}>${ic('b-tria_left')}</button>
      <button class="m-pick" data-msheet="pick" aria-label="Choisir le plan"><span class="t"><b>${esc(mShort(it))}</b><small>${esc(groupOf(it))} · ${k<0?'hors filtre':(k+1)+' / '+sib.length}${S.m.filter?' · '+mF[S.m.filter]:''}</small></span><span class="gls">${mGl(it)}</span>${ic('b-tria_down')}</button>
      <button class="m-ib" data-mstep="1" aria-label="Plan suivant" ${k<0||k>=sib.length-1?'disabled':''}>${ic('b-tria_right')}</button></div>
    ${it.desc||it.descEdit?`<p class="m-desc">${esc(it.descEdit??it.desc)}</p>`:''}
    <div class="m-player ${S.m.side==='B'&&V.length>1?'is-b':''}" id="m-player">${it.thumb?`<img src="${it.thumb}" alt="Image de ${esc(it.name)}" draggable="false">`:`<span class="noimg">Pas encore de rendu</span>`}
      <span class="m-hud">${V.length>1?`<b class="ab">${S.m.side}</b>`:''}${v?esc(verLab(v)):'aucune version'}</span><span class="m-fr">f <span data-f>${S.frame}</span></span></div>
    <div class="scrub big" data-scrub role="slider" tabindex="0" aria-label="Frame" aria-valuemin="1" aria-valuemax="${NF}" aria-valuenow="${S.frame}">${mkH}${rng}<span class="ph" style="left:${(S.frame-1)/(NF-1)*100}%"></span></div>
    <div class="m-tp"><button class="btn icon" data-tp="fprev" aria-label="Frame précédente">${ic('b-frame_prev')}</button><button class="btn icon play" data-tp="play" aria-label="Lecture">${ic(S.playing?'b-pause':'b-play')}</button><button class="btn icon" data-tp="fnext" aria-label="Frame suivante">${ic('b-frame_next')}</button><button class="btn icon" data-mloop aria-pressed="${S.m.loop}" aria-label="Boucler ce plan" title="${S.m.loop?'Rejoue ce plan en boucle':'Enchaîne les plans du parcours'}">${ic('b-file_refresh')}</button>
      ${V.length>1?`<span class="join m-ab" role="group" aria-label="Version affichée"><button class="btn" data-mside="A" aria-pressed="${S.m.side==='A'}">A</button><button class="btn" data-mside="B" aria-pressed="${S.m.side==='B'}">B</button></span>`:''}</div>
    ${V.length>1?`<div class="m-vers"><button class="m-vchip ${S.m.side==='A'?'on':''}" data-msheet="verA"><b>A</b><span class="lb">${esc(verLab(V[a]))}</span>${ic('b-tria_down')}</button><button class="m-vchip ${S.m.side==='B'?'on':''}" data-msheet="verB"><b>B</b><span class="lb">${esc(verLab(V[b]))}</span>${ic('b-tria_down')}</button></div>
      `:''}<p class="m-hint">${S.m.loop?'Boucle : ce plan se rejoue.':'Lecture : les plans du parcours s\'enchaînent.'}${V.length>1?' A / B : même frame, autre version.':''} Glisser sur l'image : plan suivant.</p>
    <section class="m-sec"><div class="m-sec-h">Départements<span class="sp"></span>${rv?`<button class="btn tool" data-msheet="depts">${ic('b-add')}Département</button>`:''}</div>
      ${rv&&rv.role!==TEAM&&req.some(d=>canVal(it,d)&&!it.rtk[d]&&!it.mine[d])?`<button class="btn ok m-wide" data-mvalall>${ic('b-checkmark')}Valider tout le fini</button>`:''}
      ${req.map(d=>mDept(it,d)).join('')||'<p class="m-hint">Aucun département requis.</p>'}</section>
    <section class="m-sec"><div class="m-sec-h">Notes<span class="n">${notes.length}</span></div>
      ${notes.map(n=>`<div class="m-note">${n.frames?`<button class="ft ${/-/.test(n.frames)?'rg':n.type==='rtk'?'':'nt'}" data-goto="${(String(n.frames).match(/\d+/)||[1])[0]}">${esc(n.frames)}</button>`:`<span class="ft ${n.type==='rtk'?'':'nt'}">${n.type==='rtk'?'RTK':'note'}</span>`}
        <span class="tx">${esc(n.text||'(sans texte)')}<small>${esc(((n.deps||[]).map(d=>LBL[d]||d).join(', ')||'sans département')+' · '+(n.mine?'vous, pas encore envoyé':n.author||''))}</small></span>
        ${n.mine?`<button class="m-ib" data-unnote="${n.at}" aria-label="Retirer">${ic('b-loop_back')}</button>`:''}</div>`).join('')||'<p class="m-hint">Aucune note ouverte.</p>'}</section>`;
}
function mDept(it,d){
  const x=info(it,d),m=it.mine[d],a=assignOf(it,d),rv=S.review,f=it.flags[d]||{};
  return `<div class="m-dept ${m?'mine':''}"><div class="m-dh">${glyph(x.base,x.corner,x.cnt,x.note)}<span class="nm"><b>${LBL[d]}</b><span class="s ${x.tone}">${esc(x.l)}${x.s?' · '+esc(x.s):''}</span></span>
      ${rv?`<button class="m-as ${a.length?'':'none'} ${it.assign&&d in it.assign?'chg':''}" data-msheet="as:${d}">${ic('b-user')}<span>${a.length?esc(a.join(', ')):'Attribuer'}</span></button>`:a.length?`<span class="m-as ro">${ic('b-user')}<span>${esc(a.join(', '))}</span></span>`:''}</div>
    ${rv?`<div class="m-da"><button class="btn ok" data-mval="${d}" aria-pressed="${m==='val'}" ${rv.role===TEAM||!canVal(it,d)?'disabled':''}>${ic('b-checkmark')}${m==='val'?'Validé':'Valider'}</button>
      <button class="btn alert" data-mrtk="${d}" aria-pressed="${m==='rtk'}">${ic('b-x')}${m==='rtk'?'Retake · vous':'Retake'}</button>
      ${f.to_redo?`<button class="btn ${it.still[d]?'ok':'tool'} m-span" data-still="${d}" aria-pressed="${!!it.still[d]}">${ic('b-checkmark')}Toujours fini <small>${esc(f.to_redo)}</small></button>`:''}</div>`:''}</div>`;
}
function mComposer(){
  if(!S.review)return `<div class="m-comp"><button class="btn primary m-wide" data-msheet="start">${ic('b-greasepencil')}Commencer la revue</button></div>`;
  const it=cur(),req=DEPTS[it.kind].filter(d=>required(it).includes(d));if(S.m.cdept&&!req.includes(S.m.cdept))S.m.cdept=null;
  return `<div class="m-comp"><div class="m-cr"><span class="join m-ct"><button class="btn icon" data-mct="rtk" aria-pressed="${S.m.ctype==='rtk'}" aria-label="Retake" title="Retake">${ic('b-x')}</button><button class="btn icon" data-mct="note" aria-pressed="${S.m.ctype==='note'}" aria-label="Remarque" title="Remarque">${ic('i-note')}</button></span>
      <button class="m-chip" data-msheet="cdept"><span>${S.m.cdept?LBL[S.m.cdept]:'Sans dépt.'}</span>${ic('b-tria_down')}</button>
      <button class="m-chip ${S.rangeStart!=null?'on':''}" data-tp="in" aria-pressed="${S.rangeStart!=null}" title="Une plage : son début ici">${S.rangeStart!=null?'f'+S.rangeStart+' →':'⇤'} f<span data-f>${S.frame}</span></button></div>
    <div class="m-cr"><label class="field ta"><textarea id="m-ta" rows="1" placeholder="${S.m.ctype==='rtk'?'Retake':'Remarque'} à cette frame…" aria-label="Texte de la note"></textarea></label>
      <button class="btn primary icon m-send" data-msend aria-label="Ajouter à ma revue">${ic('b-export')}</button></div></div>`;
}

/* ----- Farm : surveiller, relancer, rendre ----- */
function mFarm(){
  const W=F.workers,act=W.filter(w=>w.status!=='silent'),busy=W.filter(w=>w.file&&w.status!=='silent');
  const st={dead:'arrêté',running:'actif',stale:'figé',ok:'actif'}[F.status]||F.status,bad=F.status==='dead'||F.status==='stale';
  const js=F.jobs.filter(j=>!j.archived);
  return `<div class="m-card ${bad?'bad':''}">${jst(bad?'failed':'running')}<span class="t"><b>Moniteur ${st}</b><small>${act.length} machine${act.length>1?'s':''} en ligne · ${busy.length} en rendu${W.length-act.length?' · '+(W.length-act.length)+' silencieuse'+(W.length-act.length>1?'s':''):''}</small>
      ${F.left?`<small>${esc(F.left.replace('not estimated yet','pas encore estimés'))}</small>`:''}</span></div>
    <button class="btn primary m-wide" data-msheet="render">${ic('b-render_animation')}Rendre un plan…</button>
    ${JS.map(([s,l])=>{const g=js.filter(j=>j.state===s);if(!g.length)return '';
      return `<section class="m-sec"><div class="m-sec-h">${l}<span class="n">${g.length}</span></div>${(s==='finished'?g.slice(0,5):g).map(j=>{const p=j.total?j.done/j.total:0;
        return `<button class="m-job" data-msheet="job:${j.id}">${jst(j.state)}<span class="jt"><b>${esc(j.file)}</b><small>${esc([j.text,j.user].filter(Boolean).join(' · '))}</small>
          ${j.total?`<span class="jbar"><i style="--p:${p*100}%"></i></span>`:''}</span><span class="pc">${j.total?Math.round(p*100)+' %':''}</span></button>`}).join('')}
        ${s==='finished'&&g.length>5?`<p class="m-hint">et ${g.length-5} autres : version bureau.</p>`:''}</section>`}).join('')}
    <section class="m-sec"><div class="m-sec-h">Machines<span class="n">${W.length}</span></div>${W.map(w=>`<div class="m-job ro">${jst(w.status==='silent'?'waiting':w.file?'running':'finished')}<span class="jt"><b>${esc(w.name)}</b><small>${w.status==='silent'?'silencieuse depuis le '+fmtD(w.since):esc([w.status,w.file].filter(Boolean).join(' · '))}</small></span></div>`).join('')}</section>`;
}

/* ----- Feuilles (bottom sheets) : un seul composant pour tous les choix ----- */
function mSheet(){
  const k=S.m.sheet,it=cur();let t='',h='',foot='';
  const opt=(attr,on,lbl,sub='',extra='')=>`<button class="m-opt" ${attr} role="menuitemradio" aria-checked="${on}"><span class="ck">${on?ic('b-checkmark'):''}</span><span class="lbl">${lbl}${sub?`<small>${sub}</small>`:''}</span>${extra}</button>`;
  if(k==='pick'){t='Choisir un fichier';const sib=mSib(),gs=[...new Set(sib.map(groupOf))];
    const cnt=f=>items.filter(i=>i.kind===S.m.kind&&!omitted(i)&&(!f||(f==='val'?toValidate(i):f==='rtk'?openRtk(i)>0:openNotes(i)>0))).length;
    h=`<span class="join full">${[['shot','Plans'],['asset','Assets']].map(([x,l])=>`<button class="btn" data-mkind="${x}" aria-pressed="${S.m.kind===x}">${l}</button>`).join('')}</span>
      <div class="m-filters">${Object.entries(mF).map(([x,l])=>`<button class="m-chip ${S.m.filter===x?'on':''}" data-mfilter="${x}">${l}<span class="n">${cnt(x)}</span></button>`).join('')}</div>
      ${gs.map(g=>`<div class="m-grp">${esc(g)}</div>${sib.filter(i=>groupOf(i)===g).map(i=>opt(`data-mgo="${i.name}"`,i.name===S.sel,`<span class="mono">${esc(mShort(i))}</span>`,esc(i.descEdit??i.desc??''),`<span class="gls">${mGl(i)}</span>`)).join('')}`).join('')||'<p class="m-hint">Rien ne correspond à ce filtre.</p>'}`}
  if(k==='verA'||k==='verB'){const {V,a,b}=mVer(it),cur2=k==='verA'?a:b;t='Version '+k.slice(3);
    h=V.map((x,n)=>opt(`data-mver="${n}"`,n===cur2,esc(verLab(x)),n===0?'la dernière':'')).join('')}
  if(k&&k.startsWith('as:')){const d=k.slice(3),a=assignOf(it,d);t=LBL[d]+' : attribué à';
    h=M.team.map(p=>opt(`data-massign="${d}" data-p="${esc(p)}"`,a.includes(p),esc(p),p===M.live.user?'moi':'')).join('')+opt(`data-massign="${d}" data-p=""`,!a.length,'Personne');
    foot=`<button class="btn m-wide" data-mclose>Terminé</button>`}
  if(k==='depts'){t='Départements de '+mShort(it);
    h=`<p class="m-hint">Un département requis compte dans les chiffres du plan. Envoyé avec votre revue.</p>`+DEPTS[it.kind].map(d=>{const on=required(it).includes(d);
      return `<button class="m-opt sw" data-mreq="${d}" role="switch" aria-checked="${on}"><span class="lbl">${LBL[d]}<small>${on?'requis':'non requis'}${it.req&&it.req[d]!==(d in it.states)?' · vous':''}</small></span><span class="tg"></span></button>`}).join('');
    foot=`<button class="btn m-wide" data-mclose>Terminé</button>`}
  if(k==='cdept'){t='La note porte sur';const req=DEPTS[it.kind].filter(d=>required(it).includes(d));
    h=req.map(d=>opt(`data-mcd="${d}"`,S.m.cdept===d,LBL[d])).join('')+opt('data-mcd=""',!S.m.cdept,'Sans département','tout le plan')}
  if(k==='start'){t='Commencer la revue';
    h=`<label class="field"><input id="m-name" value="${esc(M.live.user||'')}" placeholder="Votre nom" aria-label="Votre nom" autocomplete="name"></label>
      <span class="join full">${[...M.roles,TEAM].map(r=>`<button class="btn" data-mrole="${r}" aria-pressed="${r===(S.m.role||M.role||M.roles[0])}">${r}</button>`).join('')}</span>
      <p class="m-hint">${{prod:'prod : le rôle le plus haut, vos validations comptent dans les chiffres.',sup:'sup : votre validation compte, la prod peut encore la reprendre.',team:'team : pas de validation, seulement des retakes et des remarques.'}[S.m.role||M.role||M.roles[0]]||''}</p>
      <div class="m-sec-h">Parcours</div>${Object.entries(mF).map(([x,l])=>opt(`data-mfilter="${x}" data-keep`,S.m.filter===x,l,x===''?'tous les plans, dans l\'ordre':'')).join('')}`;
    foot=`<button class="btn primary m-wide" data-mstart>${ic('b-greasepencil')}Commencer</button>`}
  if(k==='send'){t='Envoyer la revue';const ch=A.changes();
    h=`<p class="m-hint">${esc(S.review.name)} · ${S.review.role} · ${ch.length} modification${ch.length>1?'s':''}</p>${ch.length?`<ul class="m-list">${ch.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>`:'<p class="m-hint">Rien dans cette revue pour l\'instant.</p>'}
      <p class="m-hint">${LIVE?'Envoyée directement à Blender, qui l\'importe.':'Donne le fichier review_'+esc(S.review.name.toLowerCase())+'.json, à importer dans Blender (Pipeline › Importer une revue).'}</p>`;
    foot=`<button class="btn m-wide" data-mstop>Quitter la revue</button><button class="btn primary m-wide" data-msendgo ${ch.length?'':'disabled'}>${ic('b-export')}${LIVE?'Envoyer à Blender':'Télécharger le fichier'}</button>`}
  if(k==='news'){t='Quoi de neuf';newsSeen=NEWS.length;const IC={rtk:'--st-rtk',render:'--st-done',ok:'--st-val'};
    h=NEWS.length?NEWS.map(x=>`<button class="m-opt" data-mgo="${x.n}"><span class="dt" style="background:var(${IC[x.k]})"></span><span class="lbl"><span class="mono">${esc(x.n)}</span> · ${esc(x.h)}<small>${esc(x.x)} · ${x.at}</small></span></button>`).join(''):'<p class="m-hint">Rien de nouveau depuis l\'ouverture de la page.</p>'}
  if(k==='menu'){t='Menu';
    h=`<div class="m-sec-h">Thème</div><span class="join full">${[['dark','Sombre'],['light','Clair'],['blender','Blender'],['system','Système']].map(([x,l])=>`<button class="btn" data-theme="${x}" aria-pressed="${S.theme===x}">${l}</button>`).join('')}</span>
      <div class="m-sec-h">Légende</div><ul class="legend-list">${[['done',null,'Fini'],['wip','rtk','Retake ouvert'],['val',null,'Validé prod'],['done','wait','En attente'],['done','redo','À refaire'],['val','you','Vous : validé'],['done','you-rtk','Vous : retake'],['done',null,'Note ouverte','n']].map(([b,c,l,n])=>`<li>${glyph(b,c,1,!!n)}<span>${l}</span></li>`).join('')}</ul>
      <p class="m-hint">Liens, synthèse, réglages des fichiers et filtres avancés : version bureau.</p>`;
    foot=`${S.review?'<button class="btn m-wide" data-mstop>Quitter la revue</button>':''}<button class="btn m-wide" data-mview="desktop">Version bureau</button>`}
  if(k&&k.startsWith('job:')){const j=F.jobs.find(x=>x.id===k.slice(4));if(!j){S.m.sheet=null;return ''}
    const live=j.state==='running'||j.state==='waiting',x=JS.find(a=>a[0]===j.state);t=j.file;
    h=`${j.total?`<span class="jbar big"><i style="--p:${j.done/j.total*100}%"></i><span>${j.done} / ${j.total} frames · ${Math.round(j.done/j.total*100)} %</span></span>`:''}
      <dl class="dl"><dt>État</dt><dd>${jst(j.state)} ${x[1]} · ${esc(j.text)}</dd><dt>Machines</dt><dd>${j.names.length?esc(j.names.join(', ')):'aucune'}</dd><dt>Envoyé</dt><dd>${esc(j.user)} · ${fmtD(j.at)}</dd>
      <dt>Priorité</dt><dd>${live&&!j.pending?`<span class="prio"><button class="btn icon" data-mprio="-1" aria-label="Baisser">−</button><b>${j.priority}</b><button class="btn icon" data-mprio="1" aria-label="Monter">+</button></span>`:j.priority}</dd></dl>`;
    foot=`${j.retry?'<button class="btn primary m-wide" data-mjob="retry">Relancer</button>':''}${j.removable?'<button class="btn alert m-wide" data-mjob="remove">Retirer de la file</button>':live?'<button class="btn alert m-wide" data-mjob="cancel">Annuler le rendu</button>':''}${j.state==='failed'||j.state==='finished'?'<button class="btn m-wide" data-mjob="archive">Archiver</button>':''}`}
  if(k==='render'){t='Rendre un plan';const f=S.m.rf=S.m.rf||{file:it.name,ver:it.stable?'stable':'last',preset:S.preset,prio:10};const rf=items.find(i=>i.name===f.file)||it;
    h=`<label class="m-lab">Fichier<select class="m-select" data-mrf="file">${[...new Set(items.map(groupOf))].map(g=>`<optgroup label="${esc(g)}">${items.filter(i=>groupOf(i)===g).map(i=>`<option value="${i.name}" ${i.name===f.file?'selected':''}>${esc(i.name)}</option>`).join('')}</optgroup>`).join('')}</select></label>
      <div class="m-lab">Version<span class="join full">${rf.stable?`<button class="btn" data-mrv="stable" aria-pressed="${f.ver==='stable'}">Stable · ${esc(rf.stable)}</button>`:''}<button class="btn" data-mrv="last" aria-pressed="${f.ver==='last'||!rf.stable}">Dernière · ${esc(rf.wip||rf.stable||'')}</button></span></div>
      <label class="m-lab">Script avant rendu<select class="m-select" data-mrf="preset">${F.presets.map(p=>`<option value="${esc(p[0])}" ${p[0]===f.preset?'selected':''}>${esc(p[1])}</option>`).join('')}</select></label>
      <div class="m-lab">Priorité<span class="prio"><button class="btn icon" data-mrp="-1" aria-label="Baisser">−</button><b>${f.prio}</b><button class="btn icon" data-mrp="1" aria-label="Monter">+</button><span class="m-hint">la plus haute passe d'abord</span></span></div>
      <p class="m-hint">Frames, machines, son, plans d'un bloc : version bureau.</p>`;
    foot=`<button class="btn primary m-wide" data-mrender>${ic('b-export')}Envoyer à la farm</button>`}
  return `<div class="m-sheet" data-mclose-bg><div class="m-sheet-in" role="dialog" aria-modal="true" aria-label="${esc(t)}"><div class="m-sheet-h"><b>${esc(t)}</b><span class="sp"></span><button class="m-ib" data-mclose aria-label="Fermer">${ic('b-x')}</button></div>
    <div class="m-sheet-b">${h}</div>${foot?`<div class="m-sheet-f">${foot}</div>`:''}</div></div>`;
}

/* ----- Événements mobiles (les data-tp, data-goto, data-unnote, data-still, data-theme sont ceux du desktop) ----- */
function mGo(n,keep){if(!n)return;const it=items.find(i=>i.name===n);if(!it)return;S.sel=n;S.m.kind=it.kind;S.frame=1;S.rangeStart=null;if(S.playing&&!keep)togglePlay();S.m.sheet=null;mRender();$('#m-body').scrollTop=0}
/* Fin de la vidéo en lecture : boucle, ou plan suivant du parcours (la lecture continue), ou arrêt à la fin. */
function mEnd(){if(S.m.loop){setFrame(1);return}const sib=mSib(),k=sib.findIndex(i=>i.name===S.sel),n=sib[k+1];
  if(!n){togglePlay();setFrame(1);toast('Fin du parcours');return}mGo(n.name,true)}
function mStep(d){const sib=mSib(),k=sib.findIndex(i=>i.name===S.sel),n=sib[k+d];if(n)mGo(n.name)}
$('#mob').addEventListener('click',e=>{const t=e.target,q=s=>t.closest(s);let x;
  if(t.matches('[data-mclose-bg]')||q('[data-mclose]')){S.m.sheet=null;mRender();return}
  if(x=q('[data-msheet]')){S.m.sheet=x.dataset.msheet;if(S.m.sheet==='render')S.m.rf=null;if(S.m.sheet==='start')S.m.role=null;mRender();return}
  if(x=q('[data-mview]')){setView(x.dataset.mview);return}
  if(q('[data-theme]')){setTimeout(mRender,0);return}
  if(x=q('[data-mtab]')){S.m.tab=x.dataset.mtab;mRender();return}
  if(x=q('[data-mstep]')){mStep(+x.dataset.mstep);return}
  if(x=q('[data-mgo]')){if(S.m.tab==='farm')S.m.tab='review';mGo(x.dataset.mgo);return}
  if(x=q('[data-mkind]')){S.m.kind=x.dataset.mkind;mRender();return}
  if(x=q('[data-mfilter]')){S.m.filter=x.dataset.mfilter;if(!x.hasAttribute('data-keep')){const f=mSib()[0];if(f&&!mSib().some(i=>i.name===S.sel))S.sel=f.name}mRender();return}
  if(q('[data-mloop]')){S.m.loop=!S.m.loop;mRender();return}
  if(x=q('[data-mside]')){S.m.side=x.dataset.mside;mRender();return}
  if(x=q('[data-mver]')){const it=cur();if(S.m.sheet==='verA')S.ver[it.name]=+x.dataset.mver;else S.m.b[it.name]=+x.dataset.mver;S.m.side=S.m.sheet==='verA'?'A':'B';S.m.sheet=null;mRender();return}
  if(x=q('[data-massign]')){const a=A.assignToggle(cur(),x.dataset.massign,x.dataset.p);if(!x.dataset.p)S.m.sheet=null;mRender();toast(LBL[x.dataset.massign]+' : '+(a.join(', ')||'personne'));return}
  if(x=q('[data-mreq]')){A.toggleReq(cur(),x.dataset.mreq);mRender();return}
  if(x=q('[data-mcd]')){S.m.cdept=x.dataset.mcd||null;S.m.sheet=null;mRender();$('#m-ta')?.focus();return}
  if(x=q('[data-mct]')){S.m.ctype=x.dataset.mct;mRender();return}
  if(x=q('[data-mval]')){if(x.disabled)return;A.toggleVal(cur(),x.dataset.mval);mRender();return}
  if(q('[data-mvalall]')){const n=A.validateAll(cur());mRender();toast(n+' département'+(n>1?'s':'')+' validé'+(n>1?'s':''));return}
  if(x=q('[data-mrtk]')){const d=x.dataset.mrtk;if(A.toggleRtk(cur(),d)){S.m.ctype='rtk';S.m.cdept=d;mRender();$('#m-ta')?.focus()}else mRender();return}
  if(q('[data-msend]')){const it=cur(),ta=$('#m-ta'),txt=ta.value.trim();if(!txt&&S.m.ctype!=='rtk'){ta.focus();return}
    A.note(it,{type:S.m.ctype,dept:S.m.cdept,text:txt,frames:rangeStr()});ta.value='';S.rangeStart=null;mRender();toast((S.m.ctype==='rtk'?'Retake':'Remarque')+' ajouté à votre revue');return}
  if(x=q('[data-mrole]')){S.m.role=x.dataset.mrole;mRender();return}
  if(q('[data-mstart]')){S.review={name:$('#m-name').value.trim()||'Anonyme',role:S.m.role||M.role||M.roles[0]};S.m.sheet=null;const f=mSib()[0];if(f&&!mSib().some(i=>i.name===S.sel))S.sel=f.name;mRender();return}
  if(q('[data-mstop]')){S.review=null;S.m.sheet=null;mRender();toast('Revue quittée : vos modifications restent affichées jusqu\'au rechargement');return}
  if(q('[data-msendgo]')){S.m.sheet=null;mRender();deliverReview();return}
  if(x=q('[data-mjob]')){const j=F.jobs.find(y=>y.id===S.m.sheet.slice(4));toast('Envoyé à Blender : '+A.job(x.dataset.mjob,j));S.m.sheet=null;mRender();return}
  if(x=q('[data-mprio]')){const j=F.jobs.find(y=>y.id===S.m.sheet.slice(4));j.priority+=+x.dataset.mprio;mRender();return}
  if(x=q('[data-mrv]')){S.m.rf.ver=x.dataset.mrv;mRender();return}
  if(x=q('[data-mrp]')){S.m.rf.prio+=+x.dataset.mrp;mRender();return}
  if(q('[data-mrender]')){const f=S.m.rf,it=items.find(i=>i.name===f.file);A.queueJob({file:f.ver==='stable'&&it.stable?it.name+'_'+it.stable+'-stable':it.file||it.name,priority:f.prio,preset:f.preset==='NONE'?'':f.preset});
    S.m.sheet=null;mRender();toast('Envoyé à Blender : rendu de '+it.name+' mis en file');return}
});
$('#mob').addEventListener('change',e=>{const r=e.target.closest('[data-mrf]');if(r){S.m.rf[r.dataset.mrf]=r.value;if(r.dataset.mrf==='file')S.m.rf.ver=items.find(i=>i.name===r.value).stable?'stable':'last';mRender()}});
$('#mob').addEventListener('input',e=>{if(e.target.id==='m-ta'){e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,120)+'px'}});
/* Glisser horizontalement sur l'image : plan suivant / précédent. */
let mSw=null;
$('#mob').addEventListener('pointerdown',e=>{if(e.target.closest('#m-player'))mSw={x:e.clientX,y:e.clientY}});
$('#mob').addEventListener('pointerup',e=>{if(!mSw)return;const dx=e.clientX-mSw.x,dy=e.clientY-mSw.y;mSw=null;if(Math.abs(dx)>60&&Math.abs(dy)<50)mStep(dx<0?1:-1)});
$('#mob').addEventListener('pointercancel',()=>mSw=null);
