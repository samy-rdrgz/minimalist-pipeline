/* ---------- Farm ---------- */
const JS=[['running','En cours','#6ea4ff','b-play'],['waiting','En attente','#9a9a9a','b-sorttime'],['failed','Échoués','#e5575f','b-x'],['finished','Finis','#5fb88a','b-checkmark']];
const jst=s=>{const x=JS.find(a=>a[0]===s)||JS[1];return `<span class="jst" style="background:${x[2]}" title="${x[1]}">${ic(x[3])}</span>`};
const jobItem=j=>items.find(i=>j.file.startsWith(i.name+'_'));
function farmJobs(){return F.jobs.filter(j=>!j.archived&&(!S.ff.s||j.state===S.ff.s)&&(!S.ff.mine||j.user===M.live.user)&&(!S.ff.q||(j.file+' '+j.shot).toLowerCase().includes(S.ff.q)))}
function renderFarmQuick(){
  const n=s=>F.jobs.filter(j=>!j.archived&&(!s||j.state===s)).length;
  $('#quick').innerHTML=`<span class="join">${[['','Tous'],...JS].map(([k,l])=>`<button class="btn" data-ffs="${k}" aria-pressed="${S.ff.s===k}">${l}<span class="n">${n(k)}</span></button>`).join('')}</span>
    <button class="btn ${S.ff.mine?'':'tool'}" data-ffm aria-pressed="${S.ff.mine}">${ic('b-user')}Les miens</button>
    ${F.left?`<span class="faint" style="font-size:var(--fs-s)" title="Le temps machine qu'il reste aux jobs, sur les workers en vie">${esc(F.left.replace('not estimated yet','pas encore estimés'))}</span>`:''}`;
}
function jobRow(j){const p=j.total?j.done/j.total:0;
  return `<div class="job ${S.farmSel===j.id?'sel':''}" data-job="${j.id}" tabindex="-1">${jst(j.state)}<span class="jt"><span class="f">${esc(j.file)}</span><span class="s">${esc([j.shot,j.text].filter(Boolean).join(' · '))}${j.priority!==10?' · priorité '+j.priority:''}</span></span>
    <span class="jbar">${j.total?`<i style="--p:${p*100}%"></i><span>${j.done} / ${j.total} frames</span>`:''}</span>
    <span class="meta">${[j.machines?j.machines+' machine'+(j.machines>1?'s':''):'',esc(j.user),fmtD(j.at)].filter(Boolean).join(' · ')}</span></div>`}
function renderFarm(){
  const L=$('#list'),me=F.me,shown=farmJobs();const st={dead:'arrêté',running:'actif',stale:'figé',ok:'actif'}[F.status]||F.status;
  let h=`<div class="fme">${jst(me.worker?'running':'waiting')}<span class="t"><b>Cette machine : ${me.worker?'worker'+(me.rendering?' · en rendu':' · au repos'):'pas un worker'}</b>
      <span class="faint">Hôte de la farm : ${esc(me.host?'cette machine':me.host_name||'aucun')} · <span class="${F.status==='dead'?'bad':''}">moniteur ${st}</span></span></span>
    <button class="btn ${me.worker?'':'primary'}" data-farm="worker">${me.worker?'Ne plus être un worker':'En faire un worker'}</button></div>`;
  h+=JS.map(([s,l])=>{const js=shown.filter(j=>j.state===s);if(!js.length)return '';
    return `<div class="grp"><div class="grp-h"><b>${l}</b><span class="cnt">${js.length}</span><span style="flex:1"></span>${s==='failed'||s==='finished'?`<button class="btn sm tool" data-farm="archive_all" data-v="${s}">Archiver les ${l.toLowerCase()}</button>`:''}</div><div class="jobs">${js.map(jobRow).join('')}</div></div>`}).join('');
  if(!shown.length)h+=`<div class="empty">${F.jobs.some(j=>!j.archived)?'Aucun job ne correspond.':'Aucun job dans la farm.'}</div>`;
  h+=`<div class="grp"><div class="grp-h"><b>Machines</b><span class="cnt">${F.workers.length}</span></div><div class="jobs">${F.workers.map(w=>`<div class="job ${S.farmSel==='w:'+w.uuid?'sel':''}" data-wk="${w.uuid}">${jst(w.status==='silent'?'waiting':w.file?'running':'finished')}<span class="jt"><span class="f">${esc(w.name)}</span><span class="s">${w.status==='silent'?'silencieux depuis le '+fmtD(w.since)+' : planté, fermé ou en veille ?':esc([w.status,w.file].filter(Boolean).join(' · '))}</span></span></div>`).join('')||'<div class="empty">Aucun worker : « En faire un worker » sur chaque machine qui rend.</div>'}</div></div>`;
  L.innerHTML=h;
}
function renderFarmDetail(H,B){
  const id=S.farmSel;
  if(id&&id.startsWith('w:')){const w=F.workers.find(x=>'w:'+x.uuid===id);if(w){H.innerHTML=`<span class="phead"><span class="pname">${esc(w.name)}</span><span class="d">Machine</span></span>`;
    B.innerHTML=`<div class="sec"><dl class="dl"><dt>État</dt><dd>${w.status==='silent'?'silencieux':esc(w.status)}</dd><dt>Depuis</dt><dd>${fmtD(w.since)}</dd><dt>Fichier</dt><dd>${esc(w.file||'–')}</dd><dt>Cette machine</dt><dd>${w.mine?'oui':'non'}</dd><dt>Hôte</dt><dd>${w.host?'oui':'non'}</dd></dl>
      <div class="pacts">${w.status!=='silent'?`<button class="btn alert" data-farm="stop">Arrêter</button>`:''}${w.status==='silent'?`<button class="btn" data-farm="forget">Oublier cette machine</button>`:''}</div></div>`;return}}
  const j=F.jobs.find(x=>x.id===id&&!x.archived);
  if(!j){H.innerHTML='<span class="phead"><span class="pname">Farm</span><span class="d">Sélectionnez un job ou une machine</span></span>';B.innerHTML='<div class="empty">Le détail d\'un job s\'affiche ici : étapes, frames, machines, priorité et actions.</div>';return}
  const it=jobItem(j),live=j.state==='running'||j.state==='waiting',x=JS.find(a=>a[0]===j.state);
  H.innerHTML=`<span class="phead"><span class="pname">${esc(j.file)}</span><span class="d">${x[1]} · ${esc(j.text)}</span></span>`;
  B.innerHTML=`<div class="sec">${j.total?`<span class="jbar big"><i style="--p:${j.done/j.total*100}%"></i><span>${j.done} / ${j.total} frames</span></span>`:''}
    <dl class="dl"><dt>État</dt><dd>${jst(j.state)} ${esc(j.text)}</dd><dt>Étape</dt><dd class="mono">${esc(j.stage)}</dd>${j.preset||j.department?`<dt>Script</dt><dd>${esc([j.preset,j.department].filter(Boolean).join(' · '))}</dd>`:''}
    <dt>Frames</dt><dd>${j.range?j.range.join(' – '):'–'}${j.shot?' · '+esc(j.shot):''}</dd><dt>Machines</dt><dd class="mono">${j.names.length?esc(j.names.join(', ')):'aucune'}</dd>
    <dt>Envoyé par</dt><dd>${esc(j.user)} · ${fmtD(j.at)}</dd>
    <dt>Priorité</dt><dd>${live&&!j.pending?`<span class="prio"><button class="btn sm icon" data-prio="-1" aria-label="Baisser">−</button><b>${j.priority}</b><button class="btn sm icon" data-prio="1" aria-label="Monter">+</button><span class="faint">la plus haute passe d'abord</span></span>`:j.priority}</dd>
    <dt>Job</dt><dd class="mono">${esc(j.id)}</dd></dl>
    <div class="pacts">${it?`<button class="btn" data-goto-file="${it.name}">${ic('b-file')}Fiche du fichier</button>`:''}
      ${j.removable?`<button class="btn alert" data-farm="remove">Retirer de la file</button>`:live?`<button class="btn alert" data-farm="cancel">Annuler</button>`:''}
      ${j.retry?`<button class="btn primary" data-farm="retry">Relancer</button>`:''}${j.recompile?`<button class="btn" data-farm="recompile">Recompiler</button>`:''}
      ${j.state==='failed'||j.state==='finished'?`<button class="btn" data-farm="archive">Archiver</button>`:''}
      <button class="btn" data-act="folder">${ic('b-file_folder')}Son dossier</button><button class="btn" data-act="log">${ic('b-file')}Logs</button></div></div>`;
}
function farmAction(k,el){
  const j=F.jobs.find(x=>x.id===S.farmSel),w=F.workers.find(x=>'w:'+x.uuid===S.farmSel);
  if(k==='worker')farmPost({action:'worker',value:!F.me.worker},F.me.worker?'cette machine n\'est plus un worker':'cette machine devient un worker');
  if(k==='archive_all')farmPost({action:'archive_all',value:el.dataset.v},'archivage des jobs '+(el.dataset.v==='failed'?'échoués':'finis'));
  if(k==='submit'){const it=cur();if(it)renderSend(it)}
  if(j&&['remove','archive','cancel','retry','recompile'].includes(k))farmPost({action:k,job_id:j.id},{remove:'retiré de la file',archive:'archivé',cancel:'annulé',retry:'relancé',recompile:'recompilation'}[k]+' · '+j.file);
  if(w&&k==='forget')farmPost({action:'forget_worker',value:w.uuid},'machine oubliée');
  if(w&&k==='stop')farmPost({action:'stop_worker',value:w.uuid},'arrêt de '+w.name);
}
