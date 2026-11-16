/* ---------- Liste ---------- */
function renderQuick(){if(S.ws==='farm'){renderFarmQuick();return}if(S.ws==='links'){$('#quick').innerHTML='<span class="dim">Qui lie quoi : assets → plans</span>';return}
  const pool=items.filter(i=>i.kind===(S.ws==='asset'?'asset':'shot'));
  const q=[];if(S.review)q.push(['mine','Ma revue',pool.filter(touched).length,glyph('val','you')]);
  q.push(['rtk','Retakes',pool.filter(i=>openRtk(i)).length,glyph('done','rtk',1)],['notes','Notes',pool.filter(i=>openNotes(i)).length,ic('i-note')],['val','À valider',pool.filter(toValidate).length,glyph('done')]);
  const nm=S.more.size+(S.dept?1:0);
  $('#quick').innerHTML=(S.ws==='synth'?'<span class="dim">Avancement du projet</span>':`<span class="join">${q.map(([k,l,n,g])=>`<button class="btn" data-quick="${k}" aria-pressed="${S.quick===k}">${g.replace('class="g"','class="g" style="width:18px;height:18px"')}<span>${l}</span><span class="n">${n}</span></button>`).join('')}</span>
    <span class="anchor"><button class="btn ${nm?'':'tool'}" data-menu="m-more" aria-haspopup="true" aria-expanded="false" ${nm?'aria-pressed="true"':''}>${ic('b-filter')}Filtres${nm?` <span class="n">${nm}</span>`:''}${ic('b-tria_down')}</button>
    <div class="menu" id="m-more" hidden role="menu">
      <div class="menu-h">Département</div>
      ${DEPTS[S.ws].map(d=>`<button class="mi" role="menuitemradio" aria-checked="${S.dept===d}" data-dept="${d}"><span class="ck">${S.dept===d?ic('b-checkmark'):''}</span><span class="lbl">${LBL[d]}</span></button>`).join('')}
      <div class="msep"></div>
      ${[['me','Moi','assigné à '+me()],...(LIVE?[['farm','Dans la farm','rendu, en file, échoué']]:[]),['unfinished','Pas fini','un département pas encore fini'],['outdated','Rendu périmé','rendu avant le dernier stable']].map(([k,l,h])=>`<button class="mi" role="menuitemcheckbox" aria-checked="${S.more.has(k)}" data-more="${k}"><span class="ck">${S.more.has(k)?ic('b-checkmark'):''}</span><span class="lbl">${l}</span><span class="k">${h}</span></button>`).join('')}
      ${nm?'<div class="msep"></div><button class="mi" data-act="clear-more"><span class="ck"></span><span class="lbl">Tout effacer</span></button>':''}
    </div></span>${S.review?`<button class="btn tool" data-bulk title="Rendre un département requis ou non sur plusieurs fichiers">${ic('b-preferences')}Départements…</button>`:''}`);
}
function renderList(){
  const L=$('#list');L.classList.toggle('graphmode',S.ws==='links');if(S.ws==='synth'){renderSynth();return}if(S.ws==='farm'){renderFarm();return}if(S.ws==='links'){renderGraph();return}
  const dl=DEPTS[S.ws];L.style.setProperty('--nd',dl.length);const vis=visible();
  if(!vis.length){L.innerHTML=`<div class="empty">Aucun fichier ne correspond aux filtres.<button class="btn" data-act="clear">Effacer les filtres</button></div>`+otherHTML();return}
  L.innerHTML=[...new Set(vis.map(groupOf))].map(g=>{
    const all=vis.filter(i=>groupOf(i)===g),act=all.filter(i=>!omitted(i)&&i.done!=null),hid=all.filter(omitted),filt=S.q||S.quick||S.more.size||S.dept,showH=S.showAside[g]||filt,its=showH?all:all.filter(i=>!omitted(i));
    const ad=act.length?act.reduce((a,i)=>a+i.done,0)/act.length:null,av=act.length?act.reduce((a,i)=>a+valOf(i),0)/act.length:null;
    return `<div class="grp ${S.closed.has(g)?'closed':''}" data-g="${g}">
      <div class="grp-h"><button class="ttl" data-fold="${g}" aria-expanded="${!S.closed.has(g)}">${ic('b-disclosure_tri_down','i tri')}<b>${g}</b><span class="cnt">${its.length} ${S.ws==='shot'?'plan':'fichier'}${its.length>1?'s':''}</span></button>
        ${S.ws==='shot'?`<button class="btn sm play" data-seq="${g}" title="Les dernières vidéos de ${g}, à la suite">${ic('b-play')}Lire la séquence</button>`:''}${S.review?`<button class="btn sm tool" data-plan="${g}" data-k="${S.ws}" title="Un nouveau ${S.ws==='shot'?'plan dans '+g:'fichier '+g+'_…'}, créé à l'import de la revue">${ic('b-add')}${S.ws==='shot'?'plan':'asset'}</button>`:''}
        <span class="prog"><span class="bar" style="--p:${(ad||0)*100}%;--c:var(--st-done)"><span>Fait</span><i></i><span>${pct(ad)}</span></span><span class="bar" style="--p:${(av||0)*100}%;--c:var(--st-val)"><span>Validé</span><i></i><span>${pct(av)}</span></span></span></div>
      <div class="rows"><div class="cols"><span></span><span>Fichier</span>${dl.map(d=>`<span class="cd" title="${LBL[d]}">${LBL[d]}</span>`).join('')}<span class="c-prog">Avancement</span></div>
      ${its.map(rowHTML).join('')}${S.planned.map((p,n)=>p.g===g&&p.kind===S.ws?plannedRow(p,n):'').join('')}${hid.length&&!filt?`<button class="aside-t" data-aside="${g}">${hid.length} mis de côté · ${hid.map(i=>omitted(i)==='cancelled'?'annulé':'en pause').filter((x,k,a)=>a.indexOf(x)===k).join(', ')} · ${S.showAside[g]?'masquer ⌃':'afficher ⌄'}</button>`:''}</div></div>`}).join('')+otherHTML();
}
function plannedRow(p,n){return `<div class="row planned"><span class="thumb"></span><span class="fname"><span class="n">${esc(p.name)}</span>${p.desc?`<span class="d">${esc(p.desc)}</span>`:''}<span class="m"><span class="tag you">nouveau · créé à l'import</span></span></span>
  <span class="depts">${DEPTS[p.kind].map(d=>`<span class="cell ${p.deps.includes(d)?'':'na'}">${glyph(p.deps.includes(d)?'todo':'na')}<span class="ab">${AB[d]}</span><span class="tx"><span class="l">${p.deps.includes(d)?'À faire':''}</span></span></span>`).join('')}</span>
  <span class="bars"><button class="btn sm flat" data-unplan="${n}" title="Retirer ce nouveau fichier de la revue">${ic('b-x')}Retirer</button></span></div>`}
function otherHTML(){if(!S.q)return '';const o=S.ws==='shot'?'asset':'shot',n=items.filter(i=>i.kind===o&&(i.name+' '+i.desc).toLowerCase().includes(S.q)).length;
  return n?`<button class="other-t" data-other="${o}">${n} résultat${n>1?'s':''} dans ${o==='shot'?'Plans':'Assets'} ›</button>`:''}
function rowHTML(it){
  const dl=DEPTS[it.kind],nn=openNotes(it),om=(it.setAside!==undefined?it.setAside:it.omit),fv=valOf(it);
  const tags=[];
  if(om&&om.state)tags.push(`<span class="tag omit" title="Mis de côté : hors des chiffres">${om.state==='cancelled'?'Annulé':'En pause'}${om.reason?' · '+esc(om.reason):''}</span>`);
  if(nn)tags.push(`<span class="tag">${ic('i-note')}${nn}</span>`);
  if(it.toCheck)tags.push(`<span class="tag check" title="Rendu, pas encore vérifié par l'équipe">${ic('b-hide_off')}à vérifier</span>`);
  if(it.outdated)tags.push(`<span class="tag check">${ic('b-error')}rendu périmé</span>`);
  if(it.farm)tags.push(`<span class="tag ${it.farm.state==='failed'?'fail':''}" title="Dans la farm : ${esc(it.farm.tip)}">${ic(it.farm.state==='waiting'?'b-sorttime':'b-file_movie')}farm ${esc(it.farm.text)}</span>`);
  if(touched(it))tags.push('<span class="tag you">vous</span>');
  return `<div class="row ${S.sel===it.name?'sel':''} ${om&&om.state?'omit':''} ${touched(it)?'mine':''}" data-n="${it.name}" tabindex="-1">
    <span class="thumb" ${it.thumb?`data-zoom="${it.name}" title="Voir en grand"`:''}>${it.thumb?`<img src="${it.thumb}" alt="" loading="lazy" decoding="async">`:''}</span>
    <span class="fname"><span class="n" title="${it.name}">${it.name}</span>${it.desc?`<span class="d" title="${esc(it.desc)}">${esc(it.desc)}</span>`:''}
      <span class="m"><span class="ver">${[it.wip,it.stable&&'stable '+it.stable].filter(Boolean).join(' · ')}${it.shots&&it.shots.length?' · '+it.shots.length+' plans':''}</span>${tags.join('')}</span></span>
    <span class="depts">${dl.map(d=>cellHTML(it,d)).join('')}</span>
    <span class="bars"><span class="bar" style="--p:${(it.done||0)*100}%;--c:var(--st-done)"><span>Fait</span><i></i><span>${pct(it.done)}</span></span><span class="bar" style="--p:${(fv||0)*100}%;--c:var(--st-val)"><span>Validé</span><i></i><span>${pct(fv)}</span></span></span>
  </div>`;
}
function renderSynth(){
  const L=$('#list'),mode=S.smode;
  const sumCell=(its,d)=>{const r=its.filter(i=>!omitted(i)&&(d?required(i).includes(d):true));if(!r.length)return null;
    const ds=d?[d]:null;let n=0,done=0,val=0,rtk=0;r.forEach(i=>{(ds||required(i)).forEach(x=>{n++;if(['done','rework'].includes(i.states[x]))done++;if(i.ok[x]||i.mine[x]==='val')val++;rtk+=rtkNotes(i,x).length})});
    return n?{done:done/n,val:val/n,rtk,n:r.length}:null};
  const field=c=>{if(!c)return '<span class="sf na">–</span>';
    if(mode==='rtk')return `<span class="sf ${c.rtk?'hot':''}" style="--p:${Math.min(1,c.rtk/6)*100}%;--c:var(--st-rtk)">${c.rtk?c.rtk+' RTK':'–'}</span>`;
    const p=mode==='val'?c.val:c.done;return `<span class="sf" style="--p:${p*100}%;--c:${mode==='val'?'var(--st-val)':'var(--st-done)'}">${Math.round(p*100)} %</span>`};
  const table=(kind,title)=>{const dl=DEPTS[kind],pool=items.filter(i=>i.kind===kind),groups=[...new Set(pool.map(groupOf))];
    return `<div class="grp"><div class="grp-h"><b>${title}</b><span class="cnt">${pool.length}</span></div>
      <div class="stab" style="--nd:${dl.length}"><span class="sh"></span>${dl.map(d=>`<span class="sh">${LBL[d]}</span>`).join('')}<span class="sh">Total</span>
      ${groups.map(g=>{const its=pool.filter(i=>groupOf(i)===g);return `<button class="sn" data-sgo="${g}" data-skind="${kind}" title="Ouvrir ${g}">${ic('b-disclosure_tri_down','i rot')}<span class="mono">${g}</span><span class="faint">${its.length}</span></button>${dl.map(d=>field(sumCell(its,d))).join('')}${field(sumCell(its,null))}`}).join('')}</div></div>`};
  const kp=(t,p,v)=>`<div class="kpi"><span class="t">${t}</span><span class="sf" style="--p:${p*100}%;--c:var(--st-done)"><span class="lab">Fait</span>${pct(p)}</span><span class="sf" style="--p:${v*100}%;--c:var(--st-val)"><span class="lab">Validé</span>${pct(v)}</span></div>`;
  L.innerHTML=`<div class="kpis">${kp('Plans',M.progress.shot,M.validation.shot)}${kp('Assets',M.progress.asset,M.validation.asset)}
    <div class="kpi"><span class="t">Retakes ouverts</span><span class="big">${items.reduce((a,i)=>a+openRtk(i),0)}</span><span class="faint">sur ${items.filter(openRtk).length} fichiers</span></div>
    ${M.schedule?`<div class="kpi"><span class="t">Planning · jour ${M.schedule.elapsed_days} / ${M.schedule.total_days}</span><span class="sf sch" style="--p:${M.progress.shot*100}%;--c:var(--st-done);--e:${M.schedule.expected*100}%" title="Le trait : où les plans devraient en être aujourd'hui"><span class="lab">Plans faits</span>${pct(M.progress.shot)}<i class="mk2"></i></span><span class="faint">attendu ${pct(M.schedule.expected)} · ${M.progress.shot<M.schedule.expected?'<span class="bad">en retard de '+Math.round((M.schedule.expected-M.progress.shot)*100)+' points</span>':'dans les temps'}</span></div>`:''}
    <div class="kpi"><span class="t">Mis de côté</span><span class="big">${items.filter(omitted).length}</span><span class="faint">en pause ou annulés, hors des chiffres</span></div></div>
  <div class="sbar"><span class="dim">Ce que dit une case</span><span class="join">${[['done','Fait'],['val','Validé'],['rtk','Retakes']].map(([k,l])=>`<button class="btn sm" data-smode="${k}" aria-pressed="${mode===k}">${l}</button>`).join('')}</span><span class="faint">Clic sur une séquence : ses fichiers, dans la liste.</span><span style="flex:1"></span><button class="btn sm tool" data-weights aria-expanded="${S.weights}">${ic('b-info')}Comment c'est compté</button></div>
  ${S.weights?`<p class="weights">Un département compte 0 % pas commencé, ${(M.weights||{}).wip??33} % en cours, ${(M.weights||{}).rework??67} % repris, ${(M.weights||{}).rtk??67} % fini avec un retake ouvert, 100 % fini. Un fichier est la moyenne de ses départements requis, une séquence la moyenne de ses fichiers. Les fichiers mis de côté ne comptent pas. Validé se compte à part : au rôle ${esc(M.role)}, sur le stable affiché.</p>`:''}
  ${table('shot','Plans')}${table('asset','Assets')}`;
}

