/* ---------- Live: the page Blender serves (lib/live.py) ----------
   Its data kept up to date (/data, waited on), the review sent (/action), the farm's
   and the files' actions (/farm, /open, /play). Each says what it sent, then what Blender did. */
function livePost(path,body){return fetch(path+'?t='+encodeURIComponent(M.live.token||''),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json())}
const noAnswer=()=>toast('Blender ne répond pas.');
/* Open a file in Blender: the question first when Blender's own has unsaved changes. */
function liveOpen(file,save){livePost('open',{file,save:save||''}).then(res=>{if(res.ask)return askOpen(file,res.current);
  toast(res.ok?'Envoyé à Blender : ouverture de '+res.opened:'Pas ouvert : '+res.error)}).catch(noAnswer)}
function askOpen(file,current){const dl=$('#dlg');dl.hidden=false;
  dl.innerHTML=`<div class="dlg-in" role="alertdialog" aria-modal="true" aria-labelledby="ask-t"><h3 id="ask-t">${esc(current)} a des modifications non enregistrées dans Blender</h3>
    <div class="acts"><button class="btn" data-dclose>Annuler</button><span style="flex:1"></span><button class="btn" data-open-save="discard">Ne pas enregistrer</button><button class="btn primary" data-open-save="save">Enregistrer, puis ouvrir</button></div></div>`;
  dl.querySelector('[data-open-save="save"]').focus({preventScroll:true});
  dl.onclick=e=>{const b=e.target.closest('[data-open-save]');if(!b)return;dl.hidden=true;dl.onclick=null;liveOpen(file,b.dataset.openSave)}}
/* A render's full video in this machine's player. */
function livePlay(video){if(!video)return toast('Pas de vidéo pour ce rendu.');livePost('play',{video}).then(res=>toast(res.ok?'Envoyé à Blender : ouvre la vidéo dans le lecteur de cette machine':'Pas ouverte : '+res.error)).catch(noAnswer)}
/* The farm: a job's or a machine's action, a render, a sequence's preview. */
function farmPost(body,say){return livePost('farm',body).then(res=>{toast(res.ok?'Envoyé à Blender : '+(say||res.sent||body.action)+(res.note?' · '+res.note:''):'Pas fait : '+(res.error||'?'));return res}).catch(noAnswer)}
function renderSend(it,preview){const f=rform(it);
  if(preview)return farmPost({action:'preview',sequence:it.group,priority:f.prio},'prévisualisation de '+it.group);
  return farmPost({action:'render',file:f.ver==='stable'&&it.stableFile?it.stableFile:it.file,preset:f.preset,priority:f.prio,mode:f.mode,start:f.start,end:f.end,
    shots:it.shots&&it.shots.length>1?it.shots.filter(x=>!f.off[x]):null})}
/* The review to Blender: applied as an imported one would be. Once the data showing it is back, it leaves the review. */
let LV={after:0};
function liveSendReview(){const data=reviewFile();if(!data.actions.length)return;
  livePost('action',{author:data.author,role:data.role,review_date:data.written_at,actions:data.actions}).then(res=>{
    if(!res.ok){toast('Pas appliqué par Blender : '+(res.error||'pas de réponse'));return}
    LV.after=res.version||0;if((M.live.version||0)>=LV.after){clearReview();LV.after=0;renderAll()}
    toast('Envoyé à Blender : '+data.actions.length+' changement'+(data.actions.length>1?'s':'')+(res.skipped&&res.skipped.length?' · laissés de côté : '+res.skipped.map(x=>x[0]+' ('+x[1]+')').join(', '):''))}).catch(noAnswer)}
/* What changed between two passes, for What's new: a note, a render, a validation. */
function newsOf(before,after){const old={};before.forEach(i=>old[i.name]=i);
  after.forEach(it=>{const o=old[it.name];if(!o)return;
    const seen=new Set((o.notes||[]).map(n=>n.id));(it.notes||[]).filter(n=>!seen.has(n.id)).forEach(n=>pushNews(n.type==='rtk'?'rtk':'note',it.name,(n.author||'?')+(n.type==='rtk'?' a écrit un retake':' a écrit une note'),(n.deps||[]).map(d=>LBL[d]).join(', ')+(n.frames?' · '+n.frames:'')+' : '+n.text));
    if(it.render&&it.render!==o.render)pushNews('render',it.name,'Nouveau rendu',it.render);
    Object.keys(it.ok||{}).forEach(d=>{const a=it.ok[d],b=(o.ok||{})[d];if(a&&!a.old&&(!b||b.old||b.role!==a.role))pushNews('ok',it.name,(a.by||'?')+' a validé',LBL[d]+' · '+a.role)})})}
/* New data from Blender: the views drawn again, the selection and the review kept. A field being typed in: once left. */
let pendData=null;
function applyData(nd){const a=document.activeElement;if(a&&a.matches&&a.matches('textarea,input:not([type=checkbox]):not([type=radio])')){pendData=nd;return}pendData=null;
  if(nd.meta.live&&M.live&&nd.meta.live.root!==M.live.root)return location.reload();
  const before=items.map(i=>({name:i.name,notes:i.notes,render:i.render,ok:i.ok}));
  loadData(nd);newsOf(before,items);
  if(!items.some(i=>i.name===S.sel)&&items[0])S.sel=items[0].name;
  if(LV.after&&(M.live.version||0)>=LV.after){clearReview();LV.after=0}
  renderAll()}
document.addEventListener('focusout',()=>setTimeout(()=>{if(pendData)applyData(pendData)},0));
/* Waited on: Blender answers when something changed. A tab in the background asks nothing (a browser gives a server 6 connections). */
function liveStatus(s){const p=$('#p-live');if(!p)return;p.dataset.state=s;
  p.title=s==='on'?'Connecté à Blender · '+(M.live.user||''):s==='busy'?'Blender est occupé : la page attend':'Blender ne répond pas : nouvel essai';
  p.lastChild.textContent=s==='on'?'live':s==='busy'?'occupé':'déconnecté'}
let liveAb=null,polling=false;
function poll(){if(document.hidden){polling=false;return}polling=true;liveAb=window.AbortController?new AbortController():null;
  fetch('data?t='+encodeURIComponent(M.live.token||'')+'&since='+(M.live.version||0),{cache:'no-store',signal:liveAb?liveAb.signal:undefined}).then(r=>{if(!r.ok)throw r.status;return r.json()})
    .then(d=>{if(d.reading)return location.reload();liveStatus(d.busy?'busy':'on');if(d.data&&d.version!==(M.live.version||0))applyData(d.data);poll()})
    .catch(e=>{if(e&&e.name==='AbortError'){polling=false;return}liveStatus('off');setTimeout(poll,2000)})}
function liveStart(){if(!LIVE)return;
  if(!S.review&&M.live.user)S.review={name:M.live.user,role:M.live.role||TEAM};
  document.addEventListener('visibilitychange',()=>{if(document.hidden){if(liveAb)liveAb.abort()}else if(!polling)poll()});
  liveStatus('on');poll()}
