/* ---------- Topbar ---------- */
function renderTop(){
  const n=k=>items.filter(i=>i.kind===k).length;
  $('#ws').innerHTML=[['shot','Plans','b-camera_data',n('shot')],['asset','Assets','b-asset_manager',n('asset')],['links','Liens','b-linked',''],['synth','Synthèse','b-spreadsheet',''],...(LIVE?[['farm','Farm','b-render_animation',F.jobs.filter(j=>!j.archived&&(j.state==='running'||j.state==='waiting')).length]]:[])]
    .map(([k,l,i,c])=>`<button role="tab" data-ws="${k}" aria-selected="${S.ws===k}" title="${l}">${ic(i)}<span class="lbl">${l}</span>${c!==''?`<span class="n">${c}</span>`:''}</button>`).join('');
  $('#p-name').textContent=M.project;$('#p-live').title='Connecté à Blender · '+M.live.user;$('#p-date').textContent=(LIVE?'live · ':'snapshot du ')+fmtD(M.snapshot)+' · '+M.exported_by;
  const n2=items.filter(touched).length;
  $('#review-slot').innerHTML=!S.review?`<button class="btn primary" id="rv-open" aria-haspopup="dialog">${ic('b-greasepencil')}<span class="only-wide">Mode revue</span></button>`:
    `<span class="review-chip"><span class="who">${esc(S.review.name)} · ${S.review.role}</span><button class="btn primary" id="rv-send" title="Ce qu'elle contient, puis le fichier à envoyer">${ic('b-export')}<span class="only-wide">Envoyer…</span><span class="n">${n2}</span></button><button class="btn flat icon" id="rv-stop" aria-label="Quitter le mode revue" title="Quitter le mode revue">${ic('b-x')}</button></span>`;
}
function reviewPop(){
  const slot=$('#review-slot');if(slot.querySelector('.pop')){slot.querySelector('.pop').remove();return}
  const p=document.createElement('div');p.className='pop';p.setAttribute('role','dialog');p.setAttribute('aria-label','Démarrer une revue');
  const sh=items.filter(i=>i.kind==='shot');
  p.innerHTML=`<h4>Démarrer une revue</h4>
    <div class="prop"><span class="k">Nom</span><span class="v"><label class="field" style="flex:1"><input id="rv-name" value="${esc(M.live.user||'')}" aria-label="Votre nom"></label></span></div>
    <div class="prop"><span class="k">Rôle</span><span class="v"><span class="join full" style="flex:1">${M.roles.map(r=>`<button class="btn" data-role="${r}" aria-pressed="${r===M.role}">${r}</button>`).join('')}<button class="btn" data-role="team" aria-pressed="false">team</button></span></span></div>
    <p class="hint" id="rv-help">prod : le rôle le plus haut, vos validations comptent dans les chiffres.</p>
    <div class="prop" style="align-items:start"><span class="k" style="padding-top:5px">Parcours</span><span class="v" style="flex-direction:column;align-items:stretch">
      <button class="btn" data-path="val" aria-pressed="true">À valider <span class="n">${sh.filter(toValidate).length}</span></button>
      <button class="btn" data-path="rtk" aria-pressed="false">Retakes ouverts <span class="n">${sh.filter(i=>openRtk(i)).length}</span></button>
      <button class="btn" data-path="" aria-pressed="false">Tout, dans l'ordre</button></span></div>
    <button class="btn primary" id="rv-go">Commencer</button>`;
  slot.appendChild(p);
  const help={prod:'prod : le rôle le plus haut, vos validations comptent dans les chiffres.',sup:'sup : votre validation compte, la prod peut encore la reprendre.',team:'team : pas de validation, seulement des retakes et des remarques.'};
  p.addEventListener('click',e=>{
    const r=e.target.closest('[data-role]');if(r){p.querySelectorAll('[data-role]').forEach(b=>b.setAttribute('aria-pressed',b===r));$('#rv-help').textContent=help[r.dataset.role]}
    const pa=e.target.closest('[data-path]');if(pa)p.querySelectorAll('[data-path]').forEach(b=>b.setAttribute('aria-pressed',b===pa));
    if(e.target.closest('#rv-go')){S.review={name:$('#rv-name').value.trim()||'Anonyme',role:p.querySelector('[data-role][aria-pressed=true]').dataset.role};
      S.quick=p.querySelector('[data-path][aria-pressed=true]').dataset.path||null;S.ws='shot';const f=visible()[0];if(f)S.sel=f.name;p.remove();renderAll();msg('Mode revue : V valide les départements finis, X écrit un retake.')}
  });
  setTimeout(()=>$('#rv-name')?.select(),0);
}

/* ---------- Outliner ---------- */
function renderTree(){
  if(S.ws==='farm'){const n=s=>F.jobs.filter(j=>!j.archived&&(!s||j.state===s)).length;
    $('#tree').innerHTML=[['','Tous les jobs'],...JS].map(([k,l])=>`<li class="it ${S.ff.s===k?'sel':''}" data-ffs="${k}" style="padding-left:12px">${k?jst(k):ic('b-render_animation')}<span class="nm" style="font-family:var(--ui);font-size:var(--fs)">${l}</span><span class="pc">${n(k)}</span></li>`).join('')
      +`<li class="it" data-ffm style="padding-left:12px">${ic('b-user')}<span class="nm" style="font-family:var(--ui);font-size:var(--fs)">Les miens</span><span class="pc">${F.jobs.filter(j=>!j.archived&&j.user===M.live.user).length}</span></li>`;
    $('#tree').querySelectorAll('.jst').forEach(e=>{e.style.width='16px';e.style.height='16px'});return}
  const kind=S.ws==='synth'?'shot':S.ws;const vis=items.filter(i=>(S.ws==='links'?(i.links.length||i.linkedBy.length||S.gAll):i.kind===kind)&&(!S.tq||i.name.toLowerCase().includes(S.tq)));
  $('#tree').innerHTML=[...new Set(vis.map(groupOf))].map(g=>{const its=vis.filter(i=>groupOf(i)===g),cl=S.closedTree.has(g);const act=its.filter(i=>!omitted(i)&&i.done!=null);
    const avg=act.length?act.reduce((a,i)=>a+i.done,0)/act.length:null;
    return `<li class="seq ${cl?'closed':''}" data-tg="${g}">${ic('b-disclosure_tri_down','i tri')}<span class="nm">${g}</span><span class="pc">${pct(avg)}</span></li>`+(cl?'':its.map(i=>
      `<li class="it ${(S.ws==='links'?S.gFocus===i.name:S.sel===i.name)?'sel':''} ${omitted(i)?'om':''}" data-n="${i.name}"><span style="width:8px;height:8px;border-radius:50%;flex:none;background:${DOT[worst(i)]}"></span><span class="nm">${i.kind==='shot'?i.name.replace(i.group+'_',''):i.name}</span>${openNotes(i)?`<span class="pc">${ic('i-note')}${openNotes(i)}</span>`:''}</li>`).join(''))}).join('');
  $('#tree').querySelectorAll('.pc svg').forEach(s=>{s.style.width='11px';s.style.height='11px'});
}

