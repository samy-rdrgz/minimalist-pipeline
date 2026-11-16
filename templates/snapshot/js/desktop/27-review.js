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
function validateAll(){const it=cur();if(!it||!S.review||S.review.role==='équipe')return;const n=A.validateAll(it);
  refresh();msg(n?`${n} département${n>1?'s':''} validé${n>1?'s':''} sur ${it.name}`:'Rien de fini à valider sur '+it.name)}
function submitForm(){
  const it=cur(),f=S.form,t=$('#f-txt').value.trim(),fr=$('#f-fr').value.trim().replace(/^f/,'');
  A.note(it,{type:f.type,dept:f.dept,text:t,frames:fr?'f'+fr:''});S.form=null;S.rangeStart=null;refresh();msg((f.type==='rtk'?'Retake':'Remarque')+' écrit sur '+it.name);
}
function sendDialog(){
  const ch=A.changes(),json=A.exportJSON();
  const dl=$('#dlg');dl.hidden=false;
  dl.innerHTML=`<div class="dlg-in" role="dialog" aria-modal="true" aria-labelledby="sd-t"><h3 id="sd-t">Envoyer la revue</h3>
    <p class="faint" style="margin:0">${esc(S.review.name)} · ${S.review.role} · ${ch.length} modification${ch.length>1?'s':''}</p>
    ${ch.length?`<ul>${ch.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>`:'<p class="dim" style="margin:0">Rien dans cette revue pour l\'instant.</p>'}
    <p class="faint" style="margin:0;font-size:var(--fs-s)">Dans le vrai snapshot, ce bouton télécharge <span class="mono">review_${esc(S.review.name.toLowerCase())}.json</span>, à importer dans Blender (Pipeline › Importer une revue). Ici, copiez son contenu :</p>
    <textarea readonly id="sd-json" aria-label="Contenu de la revue">${esc(json)}</textarea>
    <div class="acts"><button class="btn" data-dclose>Continuer la revue</button><button class="btn primary" data-dcopy>${ic('b-copydown')}Copier</button></div></div>`;
}
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

