/* ---------- Sélection ---------- */
const narrow=()=>matchMedia('(max-width:860px)').matches;
function select(n,{open=true}={}){
  S.sel=n;S.form=null;S.reply=null;S.rangeStart=null;if(S.ws==='links'){S.gFocus=n;S.tab='links';renderList();renderTree();renderProps();requestAnimationFrame(()=>centerG(n));if(narrow())document.body.classList.add('props-open');document.body.classList.remove('out-open');return}
  document.querySelectorAll('.row.sel,.tree li.sel').forEach(e=>e.classList.remove('sel'));
  document.querySelectorAll(`.row[data-n="${CSS.escape(n)}"],.tree li[data-n="${CSS.escape(n)}"]`).forEach(e=>e.classList.add('sel'));
  document.querySelector(`.row[data-n="${CSS.escape(n)}"]`)?.scrollIntoView({block:'nearest'});
  renderProps();renderWide();if(open&&narrow()&&!S.wide)document.body.classList.add('props-open');document.body.classList.remove('out-open');
}
function step(dir){if(S.ws==='farm'||S.ws==='links'||S.ws==='synth')return;const v=S.wide?items.filter(i=>i.kind===cur().kind&&groupOf(i)===groupOf(cur())):visible().filter(i=>!S.closed.has(groupOf(i)));if(!v.length)return;
  let i=v.findIndex(x=>x.name===S.sel);i=i<0?0:Math.min(v.length-1,Math.max(0,i+dir));select(v[i].name,{open:false})}

/* ---------- Revue ---------- */
function validateAll(){const it=cur();if(!it||!S.review||S.review.role===TEAM)return;const n=A.validateAll(it);
  refresh();msg(n?`${n} département${n>1?'s':''} validé${n>1?'s':''} sur ${it.name}`:'Rien de fini à valider sur '+it.name)}
function submitForm(){
  const it=cur(),f=S.form,t=$('#f-txt').value.trim(),fr=$('#f-fr').value.trim().replace(/^f/,'');
  A.note(it,{type:f.type,dept:f.dept,text:t,frames:fr?'f'+fr:''});S.form=null;S.rangeStart=null;refresh();msg((f.type==='rtk'?'Retake':'Remarque')+' écrit sur '+it.name);
}
function sendDialog(){
  const ch=A.changes(),acts=reviewActions(),team=asTeam();
  const dl=$('#dlg');dl.hidden=false;
  dl.innerHTML=`<div class="dlg-in" role="dialog" aria-modal="true" aria-labelledby="sd-t"><h3 id="sd-t">Envoyer la revue</h3>
    <p class="faint" style="margin:0">${esc(S.review.name)} · ${esc(S.review.role)} · ${ch.length} modification${ch.length>1?'s':''}</p>
    ${ch.length?`<ul>${ch.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>`:'<p class="dim" style="margin:0">Rien dans cette revue pour l\'instant.</p>'}
    ${team&&ch.length&&!acts.length?'<p class="dim" style="margin:0">En équipe, rien à envoyer : l\'équipe ne valide pas — écrivez un retake ou une remarque.</p>':''}
    <p class="faint" style="margin:0;font-size:var(--fs-s)">${LIVE?'Appliquée tout de suite dans Blender, comme une revue importée.':`Le fichier <span class="mono">${esc(reviewName())}</span>, à importer dans Blender : Pipeline › Importer une revue.`}</p>
    <div class="acts"><button class="btn" data-rvclear ${ch.length?'':'disabled'}>Effacer la revue…</button><span style="flex:1"></span><button class="btn" data-dclose>Continuer la revue</button>
    <button class="btn primary" data-rvgo ${acts.length?'':'disabled'}>${ic('b-export')}${LIVE?'Envoyer à Blender':'Télécharger'}</button></div></div>`;
}
/* The review out: to Blender (live), else its file -- the share sheet on a tablet or a phone, else downloaded. */
function deliverReview(){const data=reviewFile();if(!data.actions.length)return;
  if(LIVE){liveSendReview();return}
  const text=JSON.stringify(data,null,2),name=reviewName();
  const download=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'application/json'}));a.download=name;
    document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove()},1000);toast('Téléchargé ('+name+') : Importer une revue le lit.')};
  const file=shareFile(text,name);if(!file)return download();
  navigator.share({files:[file],title:name}).then(()=>toast('Revue enregistrée ou envoyée : Importer une revue la lit.'),err=>{if(!err||err.name!=='AbortError')download()})}
/* The share sheet takes it as JSON, else as plain text (same .json name). null: no share sheet. */
function shareFile(text,name){if(!(navigator.share&&navigator.canShare&&matchMedia('(pointer:coarse)').matches))return null;
  for(const type of ['application/json','text/plain']){const f=new File([text],name,{type});try{if(navigator.canShare({files:[f]}))return f}catch(_){}}return null}
/* A review file downloaded from this page, read back to go on with it. */
function loadReview(file){if(!file)return;const rd=new FileReader();rd.onload=()=>{let data;try{data=JSON.parse(rd.result)}catch(_){toast('Pas un fichier de revue.');return}
  if(data.format!==M.format){toast('Pas une revue téléchargée depuis une page snapshot.');return}
  if(data.schema_version!==M.schema_version){toast('Cette revue vient d\'une autre version du snapshot : elle ne peut pas être chargée ici.');return}
  const go=()=>{clearReview();S.review={name:data.author||'',role:data.role||''};const unknown=fromActions(data.actions);refresh();renderAll();
    toast('Revue de '+(data.author||'?')+' chargée'+(unknown.length?' · '+unknown.length+' fichier(s) absents de cette page':''))};
  if(data.project!==M.project&&!confirm('Cette revue est pour '+data.project+', pas '+M.project+'. La charger quand même ?'))return;
  if(items.some(touched)&&!confirm('Remplacer la revue en cours par celle-ci ?'))return;go()};rd.readAsText(file)}
function settingsPop(btn){
  const old=document.querySelector('.pop.set');if(old){old.remove();return}
  const it=cur(),p=document.createElement('div');p.className='pop set';const om=(it.setAside!==undefined?it.setAside:it.omit)||{};const dis=S.review?'':'disabled';
  p.style.right='auto';p.style.left='0';
  p.innerHTML=`<h4>Réglages du fichier</h4><p class="hint">${S.review?'Envoyés avec votre revue.':'Passez en Mode revue pour les modifier.'}</p>
    <div class="sec-h">Départements requis</div><span class="join full">${DEPTS[it.kind].map(d=>`<button class="btn sm" data-req="${d}" aria-pressed="${required(it).includes(d)}" ${dis}>${AB[d]}</button>`).join('')}</span>
    <div class="sec-h">Mis de côté</div><span class="join full">${[['','Actif'],['on_hold','En pause'],['cancelled','Annulé']].map(([k,l])=>`<button class="btn sm" data-omit="${k}" aria-pressed="${(om.state||'')===k}" ${dis}>${l}</button>`).join('')}</span>
    ${om.state?`<label class="field"><input id="om-why" value="${esc(om.reason||'')}" placeholder="Pourquoi (pour l'équipe)" ${dis} aria-label="Raison"></label>`:''}
    <p class="hint">Mis de côté : hors des chiffres, toujours dans la liste.</p>`;
  btn.parentElement.appendChild(p);
}

