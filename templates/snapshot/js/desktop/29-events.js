function v6Click(t){
  const tou=t.closest('[data-tour]');if(tou){tou.dataset.tour==='next'?tour(tourAt+1):tour(-1);return true}
  if(t.closest('[data-tourstart]')){$('#dlg').hidden=true;closeMenus();setTimeout(()=>tour(0),50);return true}
  const th=t.closest('[data-theme]');if(th){setTheme(th.dataset.theme);return true}
  const nb=t.closest('#news-b');if(nb){newsPop(nb);return true}
  const shs=t.closest('[data-shot]');if(shs){S.shot[S.sel]=shs.dataset.shot;S.ver[S.sel]=0;renderProps();renderWide();return true}
  if(t.closest('[data-render]')){renderDlg();return true}
  const rf=t.closest('[data-rf]');if(rf){rform(cur())[rf.dataset.rf]=rf.dataset.v;renderDlg();return true}
  if(t.closest('[data-rft]')){const f=rform(cur());f.frames=!f.frames;if(!f.frames){f.start='';f.end=''}renderDlg();return true}
  const rp=t.closest('[data-rprio]');if(rp){rform(cur()).prio+=+rp.dataset.rprio;renderDlg();return true}
  const rs=t.closest('[data-rshot]');if(rs){const f=rform(cur());f.off[rs.dataset.rshot]=!f.off[rs.dataset.rshot];renderDlg();return true}
  const rpp=t.closest('[data-rpreset]');if(rpp){rform(cur()).preset=rpp.dataset.rpreset;closeMenus();renderDlg();return true}
  if(t.closest('[data-rprev]')){$('#dlg').hidden=true;renderSend(cur(),true);return true}
  if(t.closest('[data-rsend]')){$('#dlg').hidden=true;renderSend(cur());return true}
  const pa=t.closest('[data-plan]');if(pa){planDlg(pa.dataset.plan,pa.dataset.k);return true}
  const pd=t.closest('[data-pld]');if(pd){pd.setAttribute('aria-pressed',pd.getAttribute('aria-pressed')!=='true');return true}
  const po=t.closest('[data-plok]');if(po){const name=$('#pl-n').value.trim();if(!name)return true;A.plan({name,g:po.dataset.plok,kind:po.dataset.plk,desc:$('#pl-d').value.trim(),deps:[...document.querySelectorAll('[data-pld][aria-pressed=true]')].map(b=>b.dataset.pld)});$('#dlg').hidden=true;refresh();msg(T('{name}: made when your review is imported',{name}));return true}
  const pu=t.closest('[data-unplan]');if(pu){A.unplan(+pu.dataset.unplan);refresh();return true}
  if(t.closest('[data-bulk]')){closeMenus();bulkDlg();return true}
  const bk=t.closest('[data-bk]');if(bk){const o=S.bulk;const k=bk.dataset.bk,v=bk.dataset.v;if(k==='kind'){o.kind=v;o.g='';o.d=DEPTS[v][0]}else if(k==='on')o.on=v==='1';else o[k]=v;bulkDlg();return true}
  if(t.closest('[data-bkok]')){const o=S.bulk;let n=0;items.filter(i=>i.kind===o.kind&&(!o.g||groupOf(i)===o.g)).forEach(i=>{if(required(i).includes(o.d)===o.on)return;A.setReq(i,o.d,o.on);n++});$('#dlg').hidden=true;refresh();msg(o.on?T('{n} files: {dept} required',{n,dept:LBL[o.d]}):T('{n} files: {dept} not required',{n,dept:LBL[o.d]}));return true}
  if(t.closest('[data-desc]')){S.editDesc=true;renderProps();setTimeout(()=>$('#desc-in')?.focus(),0);return true}
  if(t.closest('[data-descok]')){const it=cur(),v=$('#desc-in').value.trim();A.desc(it,v);S.editDesc=false;refresh();return true}
  if(t.closest('[data-desccancel]')){S.editDesc=false;renderProps();return true}
  const asd=t.closest('[data-aside]');if(asd){const g=asd.dataset.aside;S.showAside[g]=!S.showAside[g];renderList();return true}
  const ot=t.closest('[data-other]');if(ot){S.ws=ot.dataset.other;renderAll();return true}
  if(t.closest('[data-weights]')){S.weights=!S.weights;renderList();return true}
  return false;
}
function helpDlg(){
  const L=[['todo',null,T('To do'),T('not started')],['wip',null,T('In progress'),T('dots')],['done',null,T('Done'),T('full')],['rework',null,T('Done, reworked'),T('reworked since the stable: the arrow in the diamond')],['done','redo',T('To redo'),T('an earlier stage changed: the orange corner')],
    ['done','wait',T('Waiting'),T('an earlier stage isn\'t ready')],['sup',null,T('Validated by a role'),T('tick, light')],['val',null,T('Validated by the top role'),T('tick, {role}',{role:M.role||''})],['old',null,T('To review again'),T('validated on an older stable')],
    ['wip','rtk',T('Open retake'),T('the number: how many RTK')],['val','rtk',T('Validated, then a retake'),T('read the corner with the shape')],['val','you',T('You: validated'),T('not sent yet')],['done','you-rtk',T('You: retake'),T('not sent yet')],['done',null,T('Open note'),T('bubble at the bottom right'),'n'],['na',null,T('Not required'),T('dash')]];
  const dl=$('#dlg');dl.hidden=false;
  dl.innerHTML=`<div class="dlg-in" role="dialog" aria-modal="true" aria-labelledby="hl-t"><h3 id="hl-t">${T('Legend and keys')}</h3>
    <p class="faint" style="margin:0">${T('The diamond says the state, the corner what comes on top. The words beside it always say it again.')}</p>
    <ul class="legend-list">${L.map(([b,c,l,s,n])=>`<li>${glyph(b,c,2,!!n)}<span>${l}<small>${s}</small></span></li>`).join('')}</ul>
    <div class="sec-h">${T('Keys')}</div>
    <ul class="legend-list" style="gap:6px">${[['↑ ↓',T('previous / next file')],['/',T('go to a file')],['W',T('watch large')],['← →',T('large: previous / next file')],[', .',T('one frame back / on')],[T('Space'),T('play')],['C',T('compare: version A / version B, same frame')],['M',T('sound')],['I',T('large, reviewing: a range\'s start')],['V',T('reviewing: validate all the done')],['X',T('reviewing: a retake or remark on no department')],['R',T('reply')],[T('Ctrl+Enter'),T('done writing')],[T('Esc'),T('close')]].map(([k,l])=>`<li style="grid-template-columns:110px 1fr"><span class="kbd" style="justify-self:start">${k}</span><span>${l}</span></li>`).join('')}</ul>
    <div class="acts"><button class="btn" data-tourstart>${T('Guided tour')}</button><span style="flex:1"></span><button class="btn" data-dclose>${T('Close')}</button></div></div>`;
}
document.addEventListener('click',e=>{
  const t=e.target;
  const lg=t.closest('[data-lang]');if(lg){MPI18n.choose(lg.dataset.lang);location.reload();return}
  const mb=t.closest('[data-menu]');if(mb){const m=document.getElementById(mb.dataset.menu);const o=m.hidden;closeMenus();m.hidden=!o;mb.setAttribute('aria-expanded',o);if(o)placeMenu(mb,m);return}
  if(!t.closest('.menu'))closeMenus();
  if(!t.closest('.pop')&&!t.closest('#rv-open')&&!t.closest('[data-settings]')&&!t.closest('#news-b'))document.querySelectorAll('.pop').forEach(p=>p.remove());
  const a=t.closest('[data-act]');if(a){const k=a.dataset.act;closeMenus();
    if(k==='videos')pickVideos();
    if(k==='player'){const it=cur(),m=it&&mVer(it),v=m&&m.V[m.i];if(LIVE)livePlay(v&&v.video);else if(v&&v.video){const u=videoSrc(v.video);if(u)open(u,'_blank');else toast(T('Video not found: choose the videos folder (View).'))}}
    if(k==='share'){shareDialog();return}
    if(k==='blender'){const it=cur();if(it)liveOpen(it.file)}
    if(k==='folder')farmPost({action:'open',job_id:S.farmSel,value:'folder'},T('opens the folder'));
    if(k==='log')farmPost({action:'open',job_id:S.farmSel,value:'log:0'},T('opens the log'));
    if(k==='copy'){const u=location.href.split('#')[0]+'#'+S.sel;(navigator.clipboard?navigator.clipboard.writeText(u):Promise.reject()).then(()=>toast(T('Link copied')),()=>toast(u))}
    if(k==='collapse'){items.forEach(i=>S.closed.add(groupOf(i)));renderTree();renderList()}
    if(k==='expand'){S.closed.clear();renderTree();renderList()}
    if(k==='clear'){S.quick=null;S.q='';S.more.clear();S.dept=null;$('#q').value='';renderQuick();renderList()}
    if(k==='clear-more'){S.more.clear();S.dept=null;renderQuick();renderList()}
    return}
  const tg=t.closest('[data-tg]');if(tg){const g=tg.dataset.tg;S.closedTree.has(g)?S.closedTree.delete(g):S.closedTree.add(g);renderTree();return}
  const fs=t.closest('[data-ffs]');if(fs){S.ff.s=fs.dataset.ffs;renderQuick();renderList();renderTree();return}
  if(t.closest('[data-ffm]')){S.ff.mine=!S.ff.mine;renderQuick();renderList();renderTree();return}
  const jb=t.closest('[data-job]');if(jb){S.farmSel=jb.dataset.job;document.querySelectorAll('.job.sel').forEach(e=>e.classList.remove('sel'));jb.classList.add('sel');renderProps();if(narrow())document.body.classList.add('props-open');return}
  const wk=t.closest('[data-wk]');if(wk){S.farmSel='w:'+wk.dataset.wk;document.querySelectorAll('.job.sel').forEach(e=>e.classList.remove('sel'));wk.classList.add('sel');renderProps();if(narrow())document.body.classList.add('props-open');return}
  const fa=t.closest('[data-farm]');if(fa){farmAction(fa.dataset.farm,fa);return}
  const pr=t.closest('[data-prio]');if(pr){const j=F.jobs.find(x=>x.id===S.farmSel);if(j)farmPost({action:'priority',job_id:j.id,value:j.priority+(+pr.dataset.prio)},T('priority {n}',{n:j.priority+(+pr.dataset.prio)}));return}
  const vr=t.closest('[data-ver]');if(vr){S.ver[S.sel]=+vr.dataset.ver;closeMenus();if(S.tab==='files'&&!S.wide)S.tab='plan';renderProps();renderWide();return}
  const ps=t.closest('[data-preset]');if(ps){S.preset=ps.dataset.preset;closeMenus();renderProps();return}
  const as=t.closest('[data-assign]');if(as){const it=cur(),d=as.dataset.assign,a=A.assignToggle(it,d,as.dataset.p);
    closeMenus();refresh();msg(LBL[d]+': '+(a.join(', ')||T('nobody')));return}
  if(t.closest('[data-relink]')){const it=cur();if(it)relinkSend([it.file]);return}
  const ga=t.closest('[data-gall]');if(ga){S.gAll=ga.dataset.gall==='1';renderList();return}
  if(t.closest('[data-gopen]')){S.gOpen=!S.gOpen;renderList();return}
  if(t.closest('[data-gclear]')){S.gFocus=null;renderList();return}
  const gn=t.closest('[data-gn]');if(gn){const n=gn.dataset.gn;S.gFocus=S.gFocus===n?null:n;S.sel=n;S.tab='links';renderList();renderProps();renderTree();if(narrow()&&S.gFocus)document.body.classList.add('props-open');return}
  const wd=t.closest('[data-wdep]');if(wd){S.wdep=wd.dataset.wdep;renderWide();$('#w-ta')?.focus();return}
  const wo=t.closest('[data-wok]');if(wo&&!wo.disabled){A.toggleVal(cur(),wo.dataset.wok);refresh();return}
  const wk2=t.closest('[data-wko]');if(wk2){const d=wk2.dataset.wko;A.toggleRtk(cur(),d);S.wdep=d;S.wtype='rtk';refresh();$('#w-ta')?.focus();return}
  const wt=t.closest('[data-wtype]');if(wt){const tx=$('#w-ta')?.value||'';S.wtype=wt.dataset.wtype;renderWide();if($('#w-ta')){$('#w-ta').value=tx;$('#w-ta').focus()}return}
  const sl=t.closest('[data-still]');if(sl){A.still(cur(),sl.dataset.still);refresh();return}
  const fx=t.closest('[data-fix]');if(fx){A.fixed(cur(),fx.dataset.fix);refresh();return}
  const zm=t.closest('[data-zoom]');if(zm){const it=items.find(i=>i.name===zm.dataset.zoom);const dl=$('#dlg');dl.hidden=false;dl.innerHTML=`<div class="dlg-in zoom" role="dialog" aria-modal="true" aria-label="${T('{name}, large',{name:it.name})}"><img src="${it.thumb}" alt="${it.name}"><div class="acts"><span class="mono" style="flex:1">${it.name}</span><button class="btn" data-dclose>${T('Close')}</button></div></div>`;return}
  const sm=t.closest('[data-smode]');if(sm){S.smode=sm.dataset.smode;renderList();return}
  const sg=t.closest('[data-sgo]');if(sg){S.ws=sg.dataset.skind;S.closed.clear();S.q='';$('#q').value='';const f=items.find(i=>i.kind===S.ws&&groupOf(i)===sg.dataset.sgo);S.sel=f.name;S.tab='plan';renderAll();document.querySelector(`.grp[data-g="${CSS.escape(sg.dataset.sgo)}"]`)?.scrollIntoView({block:'start'});return}
  const gz=t.closest('[data-gz]');if(gz){const k=+gz.dataset.gz;if(k)zoomG(k>0?1.25:.8);else fitG();drawGraph();return}
  const ab=t.closest('[data-ab]');if(ab){S.m.side=ab.dataset.ab;refresh();return}
  const vb=t.closest('[data-verb]');if(vb){S.m.b[S.sel]=+vb.dataset.verb;S.m.side='B';closeMenus();refresh();return}
  const dv=t.closest('[data-demo-view]');if(dv){closeMenus();setView(dv.dataset.demoView);return}
  if(v6Click(t))return;
  const sc=t.closest('[data-scale]');if(sc){setScale(+sc.dataset.scale);closeMenus();return}
  const ws=t.closest('[data-ws]');if(ws){S.ws=ws.dataset.ws;S.quick=null;S.dept=null;if((S.ws==='shot'||S.ws==='asset')&&cur()?.kind!==S.ws)S.sel=items.find(i=>i.kind===S.ws).name;if(S.ws==='links')S.tab='links';else if(S.tab==='links'&&S.ws!=='synth')S.tab='plan';renderAll();return}
  if(t.closest('#rv-open')){reviewPop();return}
  if(t.closest('#rv-open-w')){S.wide=false;renderWide();setTimeout(reviewPop,0);return}
  if(t.closest('#rv-stop')){S.review=null;S.form=null;S.reply=null;if(S.quick==='mine')S.quick=null;renderAll();msg(T('Review left: your changes are kept in this browser.'));return}
  if(t.closest('#rv-send')){sendDialog();return}
  if(t.closest('#help-b')){helpDlg();return}
  if(t.closest('[data-dclose]')||t.id==='dlg'){$('#dlg').hidden=true;return}
  if(t.closest('[data-rvgo]')){$('#dlg').hidden=true;deliverReview();return}
  if(t.closest('[data-rvclear]')){if(confirm(T('Clear the whole review in progress? A file already downloaded keeps what it holds.'))){clearReview();$('#dlg').hidden=true;renderAll();toast(T('Review cleared'))}return}
  if(t.closest('[data-qfold]')){S.qFold=S.qFold===false;renderQuick();return}
  const q=t.closest('[data-quick]');if(q){S.quick=S.quick===q.dataset.quick?null:q.dataset.quick;renderQuick();renderList();return}
  const dp=t.closest('[data-dept]');if(dp){S.dept=S.dept===dp.dataset.dept?null:dp.dataset.dept;renderQuick();renderList();return}
  const mo=t.closest('[data-more]');if(mo){const k=mo.dataset.more;S.more.has(k)?S.more.delete(k):S.more.add(k);renderQuick();renderList();return}
  const fo=t.closest('[data-fold]');if(fo){const g=fo.dataset.fold;S.closed.has(g)?S.closed.delete(g):S.closed.add(g);renderTree();renderList();return}
  const sq=t.closest('[data-seq]');if(sq){const f=visible().find(i=>i.group===sq.dataset.seq)||items.find(i=>i.group===sq.dataset.seq);S.sel=f.name;S.wide=true;S.frame=1;S.seqPlay=true;renderAll();if(!S.playing)togglePlay();msg(T('Playing {seq}: the shots one after the other',{seq:sq.dataset.seq}));return}
  const tr=t.closest('.heat tr[data-g]');if(tr){S.ws='shot';S.closed.clear();S.sel=items.find(i=>i.group===tr.dataset.g).name;renderAll();return}
  const fl=t.closest('[data-film]');if(fl){select(fl.dataset.film,{open:false});return}
  const gf=t.closest('[data-goto-file]');if(gf){const n=gf.dataset.gotoFile,it=items.find(i=>i.name===n);if(it){if(it.kind!==S.ws){S.ws=it.kind;S.sel=n;S.tab='plan';renderAll()}else select(n,{open:false})}else toast(T('{name} isn\'t in this snapshot',{name:n}));return}
  const row=t.closest('.row[data-n],.tree li[data-n]');if(row){select(row.dataset.n);return}
  const tab=t.closest('[data-tab]');if(tab){S.tab=tab.dataset.tab;renderProps();return}
  const nf=t.closest('[data-nf]');if(nf){S.noteFilter=nf.dataset.nf;refresh();return}
  const go=t.closest('[data-goto]');if(go){setFrame(fIdx(+go.dataset.goto));if(S.tab!=='plan'&&!S.wide){S.tab='plan';renderProps()}return}
  const tp=t.closest('[data-tp]');if(tp&&!tp.disabled){const k=tp.dataset.tp;
    if(k==='fprev')setFrame(S.frame-1);if(k==='fnext')setFrame(S.frame+1);if(k==='play')togglePlay();
    if(k==='vprev'||k==='vnext'){const n=versOf(cur()).length;if(n>1){S.ver[S.sel]=((S.ver[S.sel]||0)+(k==='vnext'?1:-1)+n)%n;renderProps();renderWide()}}
    if(k==='snd'){S.muted=!S.muted;PV.muted=S.muted;document.querySelectorAll('[data-tp="snd"]').forEach(b=>{b.innerHTML=ic(S.muted?'b-mute_ipo_off':'b-mute_ipo_on');b.setAttribute('aria-pressed',!S.muted)})}
    if(k==='in'){S.rangeStart=S.rangeStart==null?S.frame:null;refresh()}return}
  if(t.closest('[data-wide]')){S.wide=true;renderWide();return}
  if(t.closest('[data-wclose]')){S.wide=false;S.seqPlay=false;if(S.playing)togglePlay();if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});renderWide();renderProps();return}
  const wsS=t.closest('[data-wstep]');if(wsS){step(+wsS.dataset.wstep);return}
  if(t.closest('[data-full]')){const W=$('#wide');(document.fullscreenElement?document.exitFullscreen():W.requestFullscreen?.())?.catch?.(()=>toast(T('Full screen not available here')));return}
  const v=t.closest('[data-val]');if(v&&!v.disabled){A.validate(cur(),v.dataset.val);refresh();return}
  if(t.closest('[data-valall]')){validateAll();return}
  const u=t.closest('[data-undo]');if(u){A.undo(cur(),u.dataset.undo);refresh();return}
  const rk=t.closest('[data-rtk]');if(rk){S.form=newForm(rk.dataset.rtk);refresh();document.getElementById('f-txt')?.focus();return}
  if(t.closest('[data-gen]')){S.form=newForm('');refresh();document.getElementById('f-txt')?.focus();return}
  const fd=t.closest('[data-fdep]'),fsh=t.closest('[data-fshot]');
  if((fd||fsh)&&S.form){const tx=$('#f-txt').value,l=fd?S.form.deps:S.form.shots,x=fd?fd.dataset.fdep:fsh.dataset.fshot;
    if(fsh&&!x)S.form.shots=[];else if(l.includes(x))l.splice(l.indexOf(x),1);else l.push(x);refresh();$('#f-txt').value=tx;$('#f-txt').focus();return}
  const ft=t.closest('[data-ftype]');if(ft){const tx=$('#f-txt').value;S.form.type=ft.dataset.ftype;refresh();$('#f-txt').value=tx;$('#f-txt').focus();return}
  if(t.closest('[data-fcancel]')){S.form=null;refresh();return}
  if(t.closest('[data-fok]')){submitForm();return}
  const rp=t.closest('[data-reply]');if(rp&&!rp.disabled){S.reply=rp.dataset.reply;refresh();document.getElementById('r-txt')?.focus();return}
  if(t.closest('[data-rcancel]')){S.reply=null;refresh();return}
  const ro=t.closest('[data-rok]');if(ro){A.reply(cur(),ro.dataset.rok,$('#r-txt').value.trim());S.reply=null;refresh();return}
  const ur=t.closest('[data-unreply]');if(ur){A.unreply(cur(),ur.dataset.unreply);refresh();return}
  const un=t.closest('[data-unnote]');if(un){A.unnote(cur(),un.dataset.unnote);refresh();return}
  const st=t.closest('[data-settings]');if(st){settingsPop(st);return}
  const rq=t.closest('[data-req]');if(rq&&!rq.disabled){const it=cur();A.toggleReq(it,rq.dataset.req);rq.setAttribute('aria-pressed',required(it).includes(rq.dataset.req));renderList();renderTop();renderQuick();return}
  const om=t.closest('[data-omit]');if(om&&!om.disabled){const it=cur();A.omit(it,om.dataset.omit);document.querySelector('.pop.set')?.remove();refresh();return}
  if(t.closest('[data-checked]')){const it=cur();it.toCheck=false;if(LIVE)liveChecked(it);refresh();msg(T('Checked: {name} is no longer "to check"',{name:S.sel}));return}
  if(t.closest('#pp-prev')){step(-1);return}if(t.closest('#pp-next')){step(1);return}
  if(t.closest('#pp-close')){document.body.classList.remove('props-open');return}
  if(t.closest('#out-toggle')){document.body.classList.toggle('out-open');return}
  if(t.closest('#scrim')){document.body.classList.remove('out-open');return}
});
document.addEventListener('change',e=>{if(e.target.id==='notif-sys'){S.notifSys=e.target.checked;if(S.notifSys){if(!window.Notification){S.notifSys=false;e.target.checked=false;toast(T('This browser has no notifications'));return}Promise.resolve(Notification.requestPermission()).then(p=>{if(p!=='granted'){S.notifSys=false;e.target.checked=false;toast(T('Notifications refused here: the bell stays up to date'))}}).catch(()=>{S.notifSys=false;e.target.checked=false})}}
  const rn=e.target.closest&&e.target.closest('[data-rfn]');if(rn)rform(cur())[rn.dataset.rfn]=e.target.value});
document.addEventListener('input',e=>{if(e.target.id==='om-why'){A.omitReason(cur(),e.target.value);renderList()}});
document.addEventListener('keydown',e=>{
  const typing=e.target.matches('input,textarea');
  if(e.target.id==='w-ta'&&e.key==='Enter'&&!e.shiftKey){e.preventDefault();wideAdd();return}
  if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){if(S.form&&document.getElementById('f-txt')){submitForm();return}if(S.reply){document.querySelector('[data-rok]')?.click();return}}
  if(e.key==='Escape'&&tourAt>=0){tour(-1);return}
  if(e.key==='Escape'){
    if(!$('#dlg').hidden){$('#dlg').hidden=true;return}
    if(S.form||S.reply){S.form=null;S.reply=null;refresh();return}
    if(document.querySelector('.pop')){document.querySelectorAll('.pop').forEach(p=>p.remove());return}
    closeMenus();if(typing){e.target.blur();return}
    if(S.wide){S.wide=false;S.seqPlay=false;if(S.playing)togglePlay();renderWide();renderProps();return}
    if(document.body.classList.contains('props-open'))document.body.classList.remove('props-open');else document.body.classList.remove('out-open');return}
  if(typing||!$('#dlg').hidden)return;
  const k=e.key;
  if(k==='/'){e.preventDefault();$('#q').focus();return}
  if(k==='?'){helpDlg();return}
  if(k==='ArrowDown'&&!S.wide){e.preventDefault();step(1)}
  if(k==='ArrowUp'&&!S.wide){e.preventDefault();step(-1)}
  if(S.wide&&k==='ArrowRight'&&!e.target.closest('[data-scrub]')){step(1)}
  if(S.wide&&k==='ArrowLeft'&&!e.target.closest('[data-scrub]')){step(-1)}
  if(e.target.closest('[data-scrub]')&&(k==='ArrowRight'||k==='ArrowLeft')){e.preventDefault();setFrame(S.frame+(k==='ArrowRight'?1:-1))}
  if(k==='w'||k==='W'){if(cur()){S.wide=!S.wide;renderWide();renderProps()}}
  if(k===','){setFrame(S.frame-1)}if(k==='.'){setFrame(S.frame+1)}
  if(k===' '&&(S.wide||S.tab==='plan')){e.preventDefault();togglePlay()}
  if((k==='c'||k==='C')&&cur()&&versOf(cur()).length>1){S.m.side=S.m.side==='A'?'B':'A';refresh()}
  if(k==='m'||k==='M'){document.querySelector('[data-tp="snd"]')?.click()}
  if(!S.review)return;
  if(k==='v'||k==='V')validateAll();
  if(k==='x'||k==='X'){e.preventDefault();if(S.wide){S.wtype='rtk';renderWide();$('#w-ta')?.focus();return}S.tab='plan';S.form=newForm('');refresh();document.getElementById('f-txt')?.focus()}
  if((k==='i'||k==='I')&&S.wide){S.rangeStart=S.rangeStart==null?S.frame:null;refresh()}
  if(k==='r'||k==='R'){const b=document.querySelector('[data-reply]:not([disabled])');if(b){e.preventDefault();b.click()}}
});
$('#q').addEventListener('input',e=>{S.q=e.target.value.trim().toLowerCase();S.ff.q=S.q;renderList()});
$('#q').addEventListener('keydown',e=>{if(e.key==='Enter'){const f=visible()[0];if(f){select(f.name);e.target.blur()}}});
$('#tree-q').addEventListener('input',e=>{S.tq=e.target.value.trim().toLowerCase();renderTree()});
function setScale(s){S.scaleV=s;document.documentElement.style.setProperty('--scale',s);try{localStorage.setItem('mp-snapshot:scale',s)}catch(_){};requestAnimationFrame(drawWires)}
try{const s=parseFloat(localStorage.getItem('mp-snapshot:scale'));if(s)document.documentElement.style.setProperty('--scale',s)}catch(_){}
new ResizeObserver(()=>drawWires()).observe($('#pbody'));new ResizeObserver(()=>{if(S.ws==='links')drawGraph()}).observe($('#list'));
document.addEventListener('scroll',e=>{if(!e.target.closest||!e.target.closest('.menu'))closeMenus()},true);addEventListener('resize',closeMenus);
document.addEventListener('dblclick',e=>{const gn=e.target.closest('[data-gn]');if(gn){const it=items.find(i=>i.name===gn.dataset.gn);S.ws=it.kind;S.sel=it.name;S.tab='plan';S.gFocus=null;renderAll()}});
document.addEventListener('change',e=>{if(e.target.matches&&e.target.matches('.rv-load')){const f=e.target.files[0];e.target.value='';closeMenus();loadReview(f)}});
