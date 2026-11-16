/* ---------- Détail ---------- */
function marks(it){
  const out=[];[...it.notes.filter(n=>!n.done),...it.myNotes].forEach(n=>{if(!n.frames)return;const m=String(n.frames).match(/(\d+)(?:-(\d+))?/);if(m)out.push({a:+m[1],b:m[2]?+m[2]:null,rtk:n.type==='rtk',n})});return out;
}
const fmtDay=sec=>{const d=new Date(sec*1000);return d.toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit'})};
const verLab=v=>[v.shot,v.folder,v.dept?(LBL[v.dept]||v.dept):'',v.at?fmtDay(v.at):''].filter(Boolean).join(' · ');
function shotsHTML(it){if(!it.shots||it.shots.length<2)return '';const c=shotOf(it);
  return `<div class="shotsel"><span class="faint">Plan du bloc</span><span class="join">${['',...it.shots].map(x=>`<button class="btn sm" data-shot="${x}" aria-pressed="${c===x}">${x||'Bloc entier'}</button>`).join('')}</span></div>`}
/* A block's renders, one shot at a time: the shot chosen ('' its renders made whole), else the first that has any.
   A and B are always two versions of that same shot. */
const shotOf=it=>{const c=S.shot[it.name];if(c!=null)return c;const has=s=>it.versions.some(v=>(v.shot||'')===s);
  return has('')||!it.versions.length?'':((it.shots||[]).find(has)??(it.versions[0].shot||''))};
const versOf=it=>{const c=shotOf(it);return it.versions.filter(v=>(v.shot||'')===c)};
/* Comparer A / B : la bascule et le choix de B, sous le choix de version (A). Touche C. */
function abHTML(it,ctx){const {V,b}=mVer(it);if(V.length<2)return '';
  return `<div class="ctl abrow"><span class="join" role="group" aria-label="Version affichée"><button class="btn" data-ab="A" aria-pressed="${S.m.side==='A'}" title="Version A (C)">A</button><button class="btn" data-ab="B" aria-pressed="${S.m.side==='B'}" title="Version B, même frame (C)">B</button></span>
    <span class="anchor vpick"><button class="enum" data-menu="m-verb-${ctx}" aria-haspopup="true" aria-expanded="false" title="La version à comparer (B)"><b class="ab b">B</b><span class="lb">${esc(verLab(V[b]))}</span>${ic('b-tria_down')}</button>
    <div class="menu" id="m-verb-${ctx}" hidden role="menu"><div class="menu-h">Comparer avec</div>${V.map((x,n)=>`<button class="mi" role="menuitemradio" aria-checked="${n===b}" data-verb="${n}"><span class="ck">${n===b?ic('b-checkmark'):''}</span><span class="lbl">${esc(verLab(x))}</span>${n===0?'<span class="k">dernière</span>':''}</button>`).join('')}</div></span></div>`}
function verHTML(it,ctx){
  const V=versOf(it);if(!V.length)return `<span class="vro faint">Pas encore de rendu</span>`;
  const i=Math.min(S.ver[it.name]||0,V.length-1);
  if(V.length<2)return `<span class="vro">${ic('b-file_movie')}<span class="lb">${esc(verLab(V[0]))}</span></span>`;
  return `<span class="anchor vpick"><button class="enum" data-menu="m-ver-${ctx}" aria-haspopup="true" aria-expanded="false" title="La version de rendu à regarder (A)"><b class="ab">A</b><span class="lb">${esc(verLab(V[i]))}</span><span class="n">${i+1}/${V.length}</span>${ic('b-tria_down')}</button>
    <div class="menu" id="m-ver-${ctx}" hidden role="menu"><div class="menu-h">Version à regarder</div>${V.map((x,n)=>`<button class="mi" role="menuitemradio" aria-checked="${n===i}" data-ver="${n}"><span class="ck">${n===i?ic('b-checkmark'):''}</span><span class="lbl">${esc(verLab(x))}</span>${n===0?'<span class="k">dernière</span>':''}</button>`).join('')}</div></span>`;
}
function stageHTML(it){
  const V=versOf(it),v=V[mVer(it).i];
  const mk=marks(it).map(f=>{const x=(fIdx(f.a)-1)/(NF-1)*100;return (f.b?`<span class="rng" style="left:${x}%;width:${(f.b-f.a)/(NF-1)*100}%"></span>`:'')+`<button class="mk ${f.rtk?'':'n'}" style="left:${x}%" data-goto="${f.a}" title="${f.rtk?'RTK':'Note'} f${f.a}${f.b?'-'+f.b:''} : ${esc(f.n.text||'(sans texte)')}"></button>`}).join('');
  return `${shotsHTML(it)}<div class="stage ${S.m.side==='B'&&V.length>1?'is-b':''}">${it.thumb?`<img src="${it.thumb}" alt="Image de ${it.name}">`:`<span class="noimg">Pas encore de rendu</span>`}
      <span class="hud">${V.length>1?`<b class="ab">${S.m.side}</b> `:''}${shotOf(it)?shotOf(it)+' · ':''}${v?esc(v.folder)+' · ':''}f <span data-f>${fNo(S.frame)}</span></span></div>
    <div class="scrub" data-scrub role="slider" tabindex="0" aria-label="Frame" aria-valuemin="1" aria-valuemax="${NF}" aria-valuenow="${S.frame}">${mk}<span class="ph" style="left:${(S.frame-1)/(NF-1)*100}%"></span></div>
    <div class="ctl">
      <span class="join"><button class="btn icon" data-tp="vprev" aria-label="Version précédente" title="Version précédente" ${V.length>1?'':'disabled'}>${ic('b-back')}</button><button class="btn icon" data-tp="fprev" aria-label="Frame précédente" title="Frame précédente (,)">${ic('b-frame_prev')}</button><button class="btn icon play" data-tp="play" aria-label="Lecture" title="Lecture (Espace)">${ic(S.playing?'b-pause':'b-play')}</button><button class="btn icon" data-tp="fnext" aria-label="Frame suivante" title="Frame suivante (.)">${ic('b-frame_next')}</button><button class="btn icon" data-tp="vnext" aria-label="Version suivante" title="Version suivante" ${V.length>1?'':'disabled'}>${ic('b-forward')}</button></span>
      <span class="join"><button class="btn icon" data-tp="snd" aria-label="Son" title="Son (M)" aria-pressed="${!S.muted}">${ic(S.muted?'b-mute_ipo_off':'b-mute_ipo_on')}</button><button class="btn icon" data-act="player" ${V.length?'':'disabled'} aria-label="Lecteur de cette machine" title="Ouvrir la vidéo originale dans le lecteur de cette machine">${ic('b-url')}</button></span>
      <span class="fr">f <span data-f>${fNo(S.frame)}</span> / ${fNo(NF)}</span></div>
    <div class="ctl">${verHTML(it,'p')}<button class="btn" data-wide title="Regarder en grand : la vidéo, les départements et les notes à leurs frames (W)">${ic('b-window')}En grand</button></div>${abHTML(it,'p')}`;
}
const assignOf=(it,d)=>(it.assign&&d in it.assign)?it.assign[d]:(it.assignees[d]||[]);
function assignHTML(it,d,ctx){
  const a=assignOf(it,d),chg=it.assign&&d in it.assign;
  if(!S.review)return a.length?`<span class="assign ro" title="Attribué à">${ic('b-user')}${esc(a.join(', '))}</span>`:'';
  return `<span class="anchor"><button class="assign ${a.length?'':'none'} ${chg?'chg':''}" data-menu="m-as-${ctx}-${d}" aria-haspopup="true" aria-expanded="false" title="Attribuer ${LBL[d]}">${ic('b-user')}${a.length?esc(a.join(', ')):'Attribuer'}${ic('b-tria_down')}</button>
    <div class="menu right" id="m-as-${ctx}-${d}" hidden role="menu"><div class="menu-h">${LBL[d]} : attribué à</div>${M.team.map(p=>`<button class="mi" role="menuitemcheckbox" aria-checked="${a.includes(p)}" data-assign="${d}" data-p="${esc(p)}"><span class="ck">${a.includes(p)?ic('b-checkmark'):''}</span><span class="lbl">${esc(p)}</span>${p===M.live.user?'<span class="k">moi</span>':''}</button>`).join('')}
    <div class="msep"></div><button class="mi" data-assign="${d}" data-p=""><span class="ck"></span><span class="lbl">Personne</span></button></div></span>`;
}
function deptHTML(it,d,ctx='p'){
  const x=info(it,d);if(x.base==='na')return '';
  const f=it.flags[d]||{},rv=S.review,team=rv&&rv.role===TEAM;
  const canVal=rv&&!team&&['done','rework'].includes(it.states[d])&&!it.ok[d]&&!it.mine[d]&&!it.rtk[d];
  const acts=rv?`<span class="acts">${it.mine[d]?`<button class="btn sm tool" data-undo="${d}" title="Reprendre ma modification">${ic('b-loop_back')}Reprendre</button>`:
    `${team?'':`<button class="btn sm ok icon" data-val="${d}" ${canVal?'':'disabled'} aria-label="Valider ${LBL[d]}" title="${canVal?'Valider comme '+rv.role:'Rien de fini à valider'}">${ic('b-checkmark')}</button>`}<button class="btn sm alert" data-rtk="${d}" title="Écrire un retake sous ce département">Retake</button>`}</span>`:'';
  const ex=[f.waiting&&x.tone!=='wait'?`<span class="wait">${ic('b-sorttime')} attend : ${esc(f.waiting)}</span>`:'',f.to_redo&&x.tone!=='redo'?`<span class="redo">↻ à refaire : ${esc(f.to_redo)}</span>`:'',it.ok[d]&&!it.mine[d]?`<span class="faint">validé par ${esc(it.ok[d].by)} (${it.ok[d].role})</span>`:''].filter(Boolean).join('');
  const frm=S.form&&S.form.dept===d?formHTML(d):'';
  return `<div class="dept">${glyph(x.base,x.corner,x.cnt,x.note)}<span class="nm"><b>${LBL[d]}</b><span class="s ${x.tone}">${esc(x.l)}${x.s?' · '+esc(x.s):''}</span></span>${acts}<span class="extra">${assignHTML(it,d,ctx)}${ex}${stillHTML(it,d)}</span>${frm}</div>`;
}
function formHTML(d){
  const types=[['rtk','Retake'],['note','Remarque']];
  return `<div class="form"><span class="join">${types.map(([k,l])=>`<button class="btn sm" data-ftype="${k}" aria-pressed="${S.form.type===k}">${l}</button>`).join('')}</span>
    <label class="field ta"><textarea id="f-txt" rows="2" placeholder="${S.form.type==='rtk'?'Ce qui ne va pas'+(d?' sur '+LBL[d]:'')+'…':'Une remarque, rien n\'est renvoyé…'}" aria-label="Texte"></textarea></label>
    <div class="r"><label class="field" style="width:calc(110px*var(--scale))"><span class="faint">f</span><input id="f-fr" value="${S.rangeStart!=null?Math.min(S.rangeStart,S.frame)+'-'+Math.max(S.rangeStart,S.frame):S.frame}" aria-label="Frame ou plage"></label>
    <span class="faint" style="font-size:var(--fs-s)">Ctrl+Entrée</span><span style="flex:1"></span><button class="btn sm" data-fcancel>Annuler</button><button class="btn sm ${S.form.type==='rtk'?'alert':'primary'}" data-fok>Écrire</button></div></div>`;
}
function notesHTML(it){
  let ns=[...it.myNotes.map(n=>({...n,mine:1})),...it.notes];if(S.noteFilter==='open')ns=ns.filter(n=>!n.done);
  if(S.noteFilter==='frame')ns=ns.filter(n=>n.frames).sort((a,b)=>parseInt(a.frames.slice(1))-parseInt(b.frames.slice(1)));
  const gen=S.form&&S.form.dept===''?`<div class="dept">${formHTML('')}</div>`:'';
  return `<div class="sec"><div class="sec-h">Notes<span class="n">${openNotes(it)}</span><span class="sp"></span>
      <span class="join">${[['open','Ouvertes'],['frame','Par frame'],['all','Toutes']].map(([k,l])=>`<button class="btn sm" data-nf="${k}" aria-pressed="${S.noteFilter===k}">${l}</button>`).join('')}</span>
      ${S.review?`<button class="btn sm" data-gen title="Un retake ou une remarque sans département (X)">${ic('b-add')}Note</button>`:''}</div>${gen}
    ${ns.length?ns.map(n=>noteHTML(it,n)).join(''):`<span class="faint">Aucune note ${S.noteFilter==='all'?'':S.noteFilter==='frame'?'à une frame':'ouverte'}.</span>`}</div>`;
}
function noteHTML(it,n){
  const reps=[...(n.replies||[]),...(it.myReplies[n.id]||[]).map(r=>({...r,mine:1}))];
  const rf=S.reply===n.id?`<div class="form"><label class="field ta"><textarea id="r-txt" rows="2" placeholder="Votre réponse…" aria-label="Réponse"></textarea></label><div class="r"><span style="flex:1"></span><button class="btn sm" data-rcancel>Annuler</button><button class="btn sm primary" data-rok="${n.id}">Répondre</button></div></div>`:'';
  const who=n.type==='rtk'?(n.team?'équipe':n.role||'équipe'):'';
  return `<div class="nt ${n.type} ${n.done?'closed':''} ${n.mine?'mine':''}">
    <div class="h"><span class="type ${n.type}">${n.type==='rtk'?'RTK':n.type==='todo'?'à faire':'note'}</span>${(n.deps||[]).length?n.deps.map(d=>LBL[d]||d).join(', '):'<span>sans département</span>'}${who?`<span>· ${esc(who)}</span>`:''}
      ${n.frames?`<button class="chip-frame" data-goto="${parseInt(String(n.frames).replace(/\D+/,''))}" title="Aller à ${esc(n.frames)}">${esc(n.frames)}</button>`:''}${n.mine?'<span class="tag you">vous</span>':''}<span class="sp"></span><span class="who">${esc(n.author&&n.author!=='unknown'?n.author:'')}</span><span>${fmtD(n.date)}</span>${n.done?'<span>· fermé</span>':''}</div>
    <div class="t ${n.text?'':'empty'}">${n.text?esc(n.text):'(sans texte)'}</div>
    ${reps.length?`<div class="rep">${reps.map(r=>`<div><div class="h"><span class="who">${esc(r.author)}</span><span>${fmtD(r.date)}</span>${r.mine?`<span class="tag you">vous</span><button class="btn sm flat" data-unreply="${n.id}" title="Reprendre ma réponse">${ic('b-loop_back')}</button>`:''}</div><div class="t">${esc(r.text)}</div></div>`).join('')}</div>`:''}
    ${rf}
    <div class="f">${fixHTML(it,n)}${n.mine?`<button class="btn sm flat" data-unnote="${n.at}" title="Reprendre">${ic('b-loop_back')}Reprendre</button>`:''}${!n.mine&&S.reply!==n.id?`<button class="btn sm flat" data-reply="${n.id}" ${S.review?'':'disabled'} title="${S.review?'Répondre (R)':'Passez en Mode revue pour répondre'}">${ic('b-file_parent')}Répondre</button>`:''}</div>
  </div>`;
}
const verOf=f=>(String(f).match(/_(v\d+(?:-stable)?)\.blend$/)||[])[1]||f;
function linksHTML(it){
  const ins=it.links,by=it.linkedBy;
  const byOld=n=>{const o=items.find(i=>i.name===n);const l=o&&o.links.find(x=>x.name===it.name);return l&&l.newer?l:null};
  const nodeA=l=>`<div class="node ${l.newer?'old':''}" data-goto-file="${l.name}" title="Ouvrir ${l.name}"><div class="nh">${ic('b-asset_manager')}<span>${l.name}</span></div><div class="nb"><div class="sock">${verOf(l.file)}${l.newer?` · <b style="color:#f4a1a5">${verOf(l.newer)} existe</b>`:''}</div><div class="sock out ${l.newer?'bad':'ok'}" data-o="${l.name}"><i></i>Lien</div></div></div>`;
  const target=`<div class="node shot cur"><div class="nh">${ic(it.kind==='shot'?'b-camera_data':'b-asset_manager')}<span>${it.name}</span></div><div class="nb">
    ${ins.map(l=>`<div class="sock in ${l.newer?'bad':''}" data-i="${l.name}"><i></i>${l.name}</div>`).join('')}${by.length?`<div class="sock out" data-o="__cur"><i></i>Lié par</div>`:''}</div></div>`;
  const nodeB=n=>{const o=byOld(n);return `<div class="node shot" data-goto-file="${n}" title="Ouvrir ${n}"><div class="nh">${ic('b-camera_data')}<span>${n}</span></div><div class="nb"><div class="sock in ${o?'bad':''}" data-i="by:${n}"><i></i>${o?'lie '+verOf(o.file)+' (ancien)':'à jour'}</div></div></div>`};
  const old=ins.filter(l=>l.newer).length+by.filter(byOld).length;
  const graph=!ins.length&&!by.length?`<div class="empty" style="padding:24px">${it.name} ne lie aucun fichier et n'est lié par aucun.</div>`:
    `<div class="nodes-wrap"><div class="nodes" id="nodes"><svg class="wires" id="wires"></svg>${ins.length?`<div class="ncol">${ins.map(nodeA).join('')}</div>`:''}<div class="ncol">${target}</div>${by.length?`<div class="ncol">${by.map(nodeB).join('')}</div>`:''}</div></div>`;
  return `<div class="sec"><div class="sec-h">Liens<span class="sp"></span><span class="faint" style="text-transform:none;letter-spacing:0">${ins.length} lié${ins.length>1?'s':''} · lié par ${by.length}</span></div>
    ${graph}<p class="faint" style="margin:0;font-size:var(--fs-s)">Fil rouge : un stable plus récent existe. Clic sur un node : ouvre le fichier.</p>
    ${old?`<div class="pacts"><button class="btn primary live-only" data-relink title="Crée une version -updatelink qui lie les derniers stables, en arrière-plan, sans rien écraser">${ic('b-linked')}Mettre à jour les liens (${old})</button></div>`:''}</div>`;
}
function wirePath(x1,y1,x2,y2,ym){
  if(x2>=x1-4){const dx=Math.max(30,(x2-x1)*.5);return `M${x1},${y1} C${x1+dx},${y1} ${x2-dx},${y2} ${x2},${y2}`}
  const k=16;return `M${x1},${y1} C${x1+k},${y1} ${x1+k},${ym} ${x1},${ym} L${x2},${ym} C${x2-k},${ym} ${x2-k},${y2} ${x2},${y2}`;
}
function drawWires(){
  const box=$('#nodes');if(!box)return;const R=box.getBoundingClientRect();let p='';
  const link=(o,n,c)=>{if(!o||!n)return;const a=o.getBoundingClientRect(),b=n.getBoundingClientRect();
    const x1=a.left+a.width/2-R.left,y1=a.top+a.height/2-R.top,x2=b.left+b.width/2-R.left,y2=b.top+b.height/2-R.top;
    const no=o.closest('.node').getBoundingClientRect(),nn=n.closest('.node').getBoundingClientRect();const ym=(Math.min(no.bottom,nn.bottom)+Math.max(no.top,nn.top))/2-R.top;
    const d=wirePath(x1,y1,x2,y2,ym);p+=`<path d="${d}" fill="none" stroke="#111" stroke-width="4.5"/><path d="${d}" fill="none" stroke="${c}" stroke-width="2.4"/>`};
  box.querySelectorAll('[data-i]').forEach(n=>{const k=n.dataset.i,c=n.classList.contains('bad')?'#e5575f':'#8a8a8a';
    link(k.startsWith('by:')?box.querySelector('[data-o="__cur"] i'):box.querySelector(`[data-o="${k}"] i`),n.querySelector('i'),c)});
  const w=$('#wires');if(w)w.innerHTML=p;
}
function filesHTML(it){
  const w=it.work?Math.floor(it.work/3600)+' h '+String(Math.round(it.work%3600/60)).padStart(2,'0'):'–';
  const row=(k,v,btn='')=>`<div class="prop"><span class="k">${k}</span><span class="v"><span class="ro" title="${esc(v)}">${esc(v||'–')}</span>${btn}</span></div>`;
  const pr=F.presets.find(p=>p[0]===S.preset)||F.presets[0];
  return `<div class="sec"><div class="sec-h">Fichiers</div>
    ${row('Fichier wip',it.file?it.file+'.blend':'')}${row('Stable',it.stable?it.name+'_'+it.stable+'-stable.blend':'')}
    ${row('Temps de travail',w)}<p class="faint" style="margin:0;font-size:var(--fs-s)">Toutes les sessions qui ont sauvé, toutes versions, tout le monde ensemble.</p>
    ${it.shots&&it.shots.length?row('Plans du bloc',it.shots.join(' · ')):''}</div>
  <div class="sec"><div class="sec-h">Rendus</div>
    ${it.versions.length?it.versions.map((v,n)=>`<div class="prop"><span class="k">${n===0?'Dernier':''}</span><span class="v"><span class="ro">${esc(verLab(v))}</span><button class="btn icon" data-ver="${n}" aria-label="Regarder" title="Regarder cette version">${ic('b-play')}</button><button class="btn icon" data-act="player" aria-label="Lecteur de cette machine" title="Ouvrir dans le lecteur de cette machine">${ic('b-file_movie')}</button></span></div>`).join(''):'<span class="faint">Aucun rendu.</span>'}
    ${row('Farm',it.farm?it.farm.text:'aucun job')}</div>
  <div class="pacts live-only"><button class="btn primary" data-render>${ic('b-render_animation')}Rendre…</button></div>`;
}
function headHTML(it){
  const d=it.descEdit!==undefined?it.descEdit:it.desc;
  const desc=S.editDesc?`<span class="desc-ed"><label class="field"><input id="desc-in" value="${esc(d)}" aria-label="Description"></label><button class="btn sm primary" data-descok>OK</button><button class="btn sm" data-desccancel>Annuler</button></span>`
    :`<span class="d" title="${esc(d)}">${esc(d||(S.review?'Ajouter une description':''))}${it.descEdit!==undefined?' <span class="tag you">vous</span>':''}${S.review?`<button class="ed" data-desc aria-label="Modifier la description" title="Modifier la description">${ic('b-greasepencil')}</button>`:''}</span>`;
  return `<span class="phead"><span class="pname">${it.name}</span>${desc}</span>
    <button class="btn flat icon live-only" data-render aria-label="Rendre" title="Rendre : envoyer à la farm, avec ses réglages">${ic('b-render_animation')}</button>
    <button class="btn flat icon" data-act="copy" aria-label="Copier un lien vers ce fichier" title="Copier un lien vers ce fichier">${ic('b-linked')}</button>
    <span class="anchor"><button class="btn flat icon" data-settings aria-label="Réglages du fichier" title="Réglages : départements requis, mis de côté">${ic('b-preferences')}</button></span>
    <button class="btn flat icon live-only" data-act="blender" aria-label="Ouvrir dans Blender" title="Ouvrir dans Blender">${ic('b-blender')}</button>
    <span class="join"><button class="btn icon" id="pp-prev" aria-label="Fichier précédent" title="Précédent (↑)">${ic('b-tria_up')}</button><button class="btn icon" id="pp-next" aria-label="Fichier suivant" title="Suivant (↓)">${ic('b-tria_down')}</button></span>
    <button class="btn flat icon only-phone" id="pp-close" aria-label="Fermer" title="Fermer (Échap)">${ic('b-x')}</button>`;
}
function renderProps(){
  const H=$('#p-head'),TB=$('#ptabs'),B=$('#pbody');
  if(S.ws==='farm'){TB.hidden=true;renderFarmDetail(H,B);return}
  TB.hidden=false;const it=cur();
  if(!it){H.innerHTML='<span class="phead"><span class="pname">Aucune sélection</span></span>';TB.innerHTML='';B.innerHTML='<div class="empty">Sélectionnez un fichier dans la liste.</div>';return}
  H.innerHTML=headHTML(it);
  const nr=openRtk(it),nn=openNotes(it),nl=it.links.length+it.linkedBy.length,lo=it.links.some(l=>l.newer);
  TB.innerHTML=[['plan',it.kind==='shot'?'b-camera_data':'b-asset_manager',it.kind==='shot'?'Plan':'Asset'],['notes','i-note','Notes',nn,nr?'r':''],['links','b-linked','Liens',nl,lo?'r':''],['files','b-file','Fichiers et rendus']]
    .map(([k,i,l,n,c])=>`<button class="vtab" role="tab" data-tab="${k}" aria-selected="${S.tab===k}" title="${l}" aria-label="${l}">${ic(i)}${n?`<span class="cnt ${c||''}">${n}</span>`:''}</button>`).join('');
  const om=(it.setAside!==undefined?it.setAside:it.omit);
  const tags=[om&&om.state?`<span class="tag omit">${om.state==='cancelled'?'Annulé':'En pause'}${om.reason?' · '+esc(om.reason):''}</span>`:'',
    it.toCheck?`<span class="tag check">${ic('b-hide_off')}rendu à vérifier</span><button class="btn sm" data-checked title="Vu : sort de « à vérifier »">Vu</button>`:'',
    it.outdated?`<span class="tag check">${ic('b-error')}rendu périmé</span>`:'',it.farm?`<span class="tag ${it.farm.state==='failed'?'fail':''}">farm ${esc(it.farm.text)}</span>`:''].filter(Boolean).join('');
  let h='';
  if(S.tab==='plan'){
    const req=DEPTS[it.kind].filter(d=>required(it).includes(d));
    h=`<div class="sec">${stageHTML(it)}${tags?`<div class="pacts tags">${tags}</div>`:''}</div>
     <div class="sec"><div class="sec-h">Départements<span class="sp"></span>${S.review&&S.review.role!==TEAM?`<button class="btn sm ok" data-valall title="Valider tous les départements finis (V)">${ic('b-checkmark')}Tout le fini</button>`:''}</div>
     ${req.length?req.map(d=>deptHTML(it,d)).join(''):'<span class="faint">Aucun département requis.</span>'}${!S.review?'<p class="faint" style="margin:0;font-size:var(--fs-s)">Passez en Mode revue pour valider, demander un retake ou attribuer.</p>':''}</div>
     <button class="notes-link" data-tab="notes">${ic('i-note')}<span>Notes</span>${nr?`<span class="tag rtk">${nr} RTK</span>`:''}<span class="faint">${nn} ouverte${nn>1?'s':''}</span><span class="sp"></span>${ic('b-tria_right')}</button>`;
  }
  if(S.tab==='notes')h=notesHTML(it);
  if(S.tab==='links')h=linksHTML(it);
  if(S.tab==='files')h=filesHTML(it);
  B.innerHTML=h;
  if(S.tab==='links')requestAnimationFrame(drawWires);
}

