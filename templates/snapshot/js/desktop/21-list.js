/* ---------- The list ---------- */
function renderQuick(){if(S.ws==='farm'){renderFarmQuick();return}if(S.ws==='links'){$('#quick').innerHTML=`<span class="dim">${T('Who links what: assets → shots')}</span>`;return}
  const pool=items.filter(i=>i.kind===(S.ws==='asset'?'asset':'shot'));if(LIVE&&S.quick==='mine')S.quick=null;
  const q=[];if(S.review&&!LIVE)q.push(['mine',T('My review'),pool.filter(touched).length,glyph('val','you')]);
  q.push(['rtk',T('Retakes'),pool.filter(i=>openRtk(i)).length,glyph('done','rtk',1)],['notes',T('Notes'),pool.filter(i=>openNotes(i)).length,ic('i-note')],['val',T('To validate'),pool.filter(toValidate).length,glyph('done')]);
  const nm=S.more.size+(S.dept?1:0);
  // On a narrow screen the filters fold behind one button (the active ones counted on it).
  const on=(S.quick?1:0)+nm;$('#quick').classList.toggle('folded',S.ws!=='synth'&&S.qFold!==false);
  $('#quick').innerHTML=(S.ws==='synth'?`<span class="dim">${T('What a cell says')}</span><span class="join">${[['done',T('Done')],['val',T('Validated')],['rtk',T('Retakes')]].map(([k,l])=>`<button class="btn" data-smode="${k}" aria-pressed="${S.smode===k}">${l}</button>`).join('')}</span><span class="faint sx-hint" title="${T('Click a sequence: its files, in the list.')}">${T('Click a sequence: its files, in the list.')}</span><button class="btn tool" data-weights aria-expanded="${S.weights}">${ic('b-info')}${T('How it\'s counted')}</button>`:`<button class="btn qfold only-phone" data-qfold aria-expanded="${S.qFold===false}">${ic('b-filter')}${T('Filters')}${on?` <span class="n">${on}</span>`:''}${ic(S.qFold===false?'b-downarrow_hlt':'b-rightarrow')}</button><span class="join">${q.map(([k,l,n,g])=>`<button class="btn" data-quick="${k}" aria-pressed="${S.quick===k}">${g.replace('class="g"','class="g" style="width:18px;height:18px"')}<span>${l}</span><span class="n">${n}</span></button>`).join('')}</span>
    <span class="anchor"><button class="btn ${nm?'':'tool'}" data-menu="m-more" aria-haspopup="true" aria-expanded="false" ${nm?'aria-pressed="true"':''}>${ic('b-filter')}${T('Filters')}${nm?` <span class="n">${nm}</span>`:''}${ic('b-tria_down')}</button>
    <div class="menu" id="m-more" hidden role="menu">
      <div class="menu-h">${T('Department')}</div>
      ${DEPTS[S.ws].map(d=>`<button class="mi" role="menuitemradio" aria-checked="${S.dept===d}" data-dept="${d}"><span class="ck">${S.dept===d?ic('b-checkmark'):''}</span><span class="lbl">${LBL[d]}</span></button>`).join('')}
      <div class="msep"></div>
      ${[['me',T('Me'),T('assigned to {who}',{who:me()})],...(LIVE?[['farm',T('In the farm'),T('rendering, queued, failed')]]:[]),['unfinished',T('Not finished'),T('a department not done yet')],['outdated',T('Render outdated'),T('rendered before the last stable')],['tracked',T('Tracked only'),T('hides the files with no department')]].map(([k,l,h])=>`<button class="mi" role="menuitemcheckbox" aria-checked="${S.more.has(k)}" data-more="${k}"><span class="ck">${S.more.has(k)?ic('b-checkmark'):''}</span><span class="lbl">${l}</span><span class="k">${h}</span></button>`).join('')}
      ${nm?'<div class="msep"></div><button class="mi" data-act="clear-more"><span class="ck"></span><span class="lbl">'+T('Clear all')+'</span></button>':''}
    </div></span>${S.review?`<button class="btn tool" data-bulk title="${T('Make a department required, or not, on several files')}">${ic('b-preferences')}${T('Departments…')}</button>`:''}`);
}
function renderList(){
  const L=$('#list');L.classList.toggle('graphmode',S.ws==='links');if(S.ws==='synth'){renderSynth();return}if(S.ws==='farm'){renderFarm();return}if(S.ws==='links'){renderGraph();return}
  const dl=DEPTS[S.ws];L.style.setProperty('--nd',dl.length);const vis=visible();
  if(!vis.length){L.innerHTML=`<div class="empty">${T('No file matches the filters.')}<button class="btn" data-act="clear">${T('Clear the filters')}</button></div>`+otherHTML();return}
  L.innerHTML=[...new Set(vis.map(groupOf))].map(g=>{
    const all=vis.filter(i=>groupOf(i)===g),act=all.filter(i=>!omitted(i)&&i.done!=null),hid=all.filter(omitted),filt=S.q||S.quick||S.more.size||S.dept,showH=S.showAside[g]||filt,its=showH?all:all.filter(i=>!omitted(i));
    const ad=act.length?act.reduce((a,i)=>a+i.done,0)/act.length:null,av=act.length?act.reduce((a,i)=>a+valOf(i),0)/act.length:null;
    return `<div class="grp ${S.closed.has(g)?'closed':''}" data-g="${g}">
      <div class="grp-h"><button class="ttl" data-fold="${g}" aria-expanded="${!S.closed.has(g)}">${ic('b-downarrow_hlt','i tri open')}${ic('b-rightarrow','i tri shut')}<b>${g}</b><span class="cnt">${S.ws==='shot'?T('{n} shot|{n} shots',{n:its.length}):T('{n} file|{n} files',{n:its.length})}</span></button>
        ${S.ws==='shot'?`<button class="btn sm play" data-seq="${g}" title="${T('The last videos of {seq}, one after the other',{seq:g})}">${ic('b-play')}${T('Play the sequence')}</button>`:''}${S.review?`<button class="btn sm tool" data-plan="${g}" data-k="${S.ws}" title="${S.ws==='shot'?T('A new shot in {seq}, made when the review is imported',{seq:g}):T('A new file {prefix}_…, made when the review is imported',{prefix:g})}">${ic('b-add')}${S.ws==='shot'?T('shot'):T('asset')}</button>`:''}
        <span class="prog"><span class="bar" style="--p:${(ad||0)*100}%;--c:var(--st-done)"><span>${T('Done')}</span><i></i><span>${pct(ad)}</span></span><span class="bar" style="--p:${(av||0)*100}%;--c:var(--st-val)"><span>${T('Validated')}</span><i></i><span>${pct(av)}</span></span></span></div>
      <div class="rows"><div class="cols"><span></span><span>${T('File')}</span>${dl.map(d=>`<span class="cd" title="${LBL[d]}">${LBL[d]}</span>`).join('')}<span class="c-prog">${T('Progress')}</span></div>
      ${its.map(rowHTML).join('')}${S.planned.map((p,n)=>p.g===g&&p.kind===S.ws?plannedRow(p,n):'').join('')}${hid.length&&!filt?`<button class="aside-t" data-aside="${g}">${T('{n} set aside',{n:hid.length})} · ${hid.map(i=>omitted(i)==='cancelled'?T('cancelled'):T('on hold')).filter((x,k,a)=>a.indexOf(x)===k).join(', ')} · ${S.showAside[g]?T('hide')+' ⌃':T('show')+' ⌄'}</button>`:''}</div></div>`}).join('')+otherHTML();
}
function plannedRow(p,n){return `<div class="row planned"><span class="thumb"></span><span class="fname"><span class="n">${esc(p.name)}</span>${p.desc?`<span class="d">${esc(p.desc)}</span>`:''}<span class="m"><span class="tag you">${T('new · made at the import')}</span></span></span>
  <span class="depts">${DEPTS[p.kind].map(d=>`<span class="cell ${p.deps.includes(d)?'':'na'}">${glyph(p.deps.includes(d)?'todo':'na')}<span class="ab">${AB[d]}</span><span class="tx"><span class="l">${p.deps.includes(d)?T('To do'):''}</span></span></span>`).join('')}</span>
  <span class="bars"><button class="btn sm flat" data-unplan="${n}" title="${T('Take this new file out of the review')}">${ic('b-x')}${T('Remove')}</button></span></div>`}
function otherHTML(){if(!S.q)return '';const o=S.ws==='shot'?'asset':'shot',n=items.filter(i=>i.kind===o&&(i.name+' '+i.desc).toLowerCase().includes(S.q)).length;
  return n?`<button class="other-t" data-other="${o}">${o==='shot'?T('{n} result in Shots|{n} results in Shots',{n}):T('{n} result in Assets|{n} results in Assets',{n})} ›</button>`:''}
function rowHTML(it){
  const dl=DEPTS[it.kind],nn=openNotes(it),om=(it.setAside!==undefined?it.setAside:it.omit),fv=valOf(it);
  const tags=[];
  if(om&&om.state)tags.push(`<span class="tag omit" title="${T('Set aside: out of the figures')}">${om.state==='cancelled'?T('Cancelled'):T('On hold')}${om.reason?' · '+esc(om.reason):''}</span>`);
  if(nn)tags.push(`<span class="tag">${ic('i-note')}${nn}</span>`);
  if(it.toCheck)tags.push(`<span class="tag check" title="${T('Rendered, not checked by the team yet')}">${ic('b-hide_off')}${T('to check')}</span>`);
  if(it.outdated)tags.push(`<span class="tag check">${ic('b-error')}${T('render outdated')}</span>`);
  if(it.farm)tags.push(`<span class="tag ${it.farm.state==='failed'?'fail':''}" title="${T('In the farm: {what}',{what:esc(it.farm.tip)})}">${ic(it.farm.state==='waiting'?'b-sorttime':'b-file_movie')}farm ${esc(it.farm.text)}</span>`);
  if(touched(it))tags.push(`<span class="tag you">${T('you')}</span>`);
  return `<div class="row ${S.sel===it.name?'sel':''} ${om&&om.state?'omit':''} ${touched(it)?'mine':''}" data-n="${it.name}" tabindex="-1">
    <span class="thumb" ${it.thumb?`data-zoom="${it.name}" title="${T('See it large')}"`:''}>${it.thumb?`<img src="${it.thumb}" alt="" loading="lazy" decoding="async">`:''}</span>
    <span class="fname"><span class="n" title="${it.name}">${it.name}</span>${it.desc?`<span class="d" title="${esc(it.desc)}">${esc(it.desc)}</span>`:''}
      <span class="m"><span class="ver">${[it.wip,it.stable&&'stable '+it.stable].filter(Boolean).join(' · ')}${it.shots&&it.shots.length?' · '+T('{n} shot|{n} shots',{n:it.shots.length}):''}</span>${tags.join('')}</span></span>
    <span class="depts">${dl.map(d=>cellHTML(it,d)).join('')}</span>
    <span class="bars"><span class="bar" style="--p:${(it.done||0)*100}%;--c:var(--st-done)"><span>${T('Done')}</span><i></i><span>${pct(it.done)}</span></span><span class="bar" style="--p:${(fv||0)*100}%;--c:var(--st-val)"><span>${T('Validated')}</span><i></i><span>${pct(fv)}</span></span></span>
  </div>`;
}
/* A bar's figure sits on its colour from this share up. */
const IN=.62;
function renderSynth(){
  const L=$('#list'),mode=S.smode;
  const sumCell=(its,d)=>{const r=its.filter(i=>!omitted(i)&&(d?required(i).includes(d):true));if(!r.length)return null;
    const ds=d?[d]:null;let n=0,done=0,val=0,rtk=0;r.forEach(i=>{(ds||required(i)).forEach(x=>{n++;if(['done','rework'].includes(i.states[x]))done++;if(i.ok[x]||i.mine[x]==='val')val++;rtk+=rtkNotes(i,x).length})});
    return n?{done:done/n,val:val/n,rtk,n:r.length}:null};
  const field=c=>{if(!c)return '<span class="sf na">–</span>';
    if(mode==='rtk'){const p=Math.min(1,c.rtk/6);return `<span class="sf ${p>=IN?'in':''}" style="--p:${p*100}%;--c:var(--st-rtk)"><b class="v">${c.rtk?c.rtk+' RTK':'–'}</b></span>`}
    const p=mode==='val'?c.val:c.done;return `<span class="sf ${p>=IN?'in':''}" style="--p:${p*100}%;--c:${mode==='val'?'var(--st-val)':'var(--st-done)'}"><b class="v">${Math.round(p*100)} %</b></span>`};
  const table=(kind,title)=>{const dl=DEPTS[kind],pool=items.filter(i=>i.kind===kind),groups=[...new Set(pool.map(groupOf))];
    return `<div class="grp"><div class="grp-h"><b>${title}</b><span class="cnt">${pool.length}</span></div>
      <div class="stab" style="--nd:${dl.length}"><span class="sh"></span>${dl.map(d=>`<span class="sh">${LBL[d]}</span>`).join('')}<span class="sh">${T('Total')}</span>
      ${groups.map(g=>{const its=pool.filter(i=>groupOf(i)===g);return `<button class="sn" data-sgo="${g}" data-skind="${kind}" title="${T('Open {name}',{name:g})}">${ic('b-rightarrow','i rot')}<span class="mono">${g}</span><span class="faint">${its.length}</span></button>${dl.map(d=>field(sumCell(its,d))).join('')}${field(sumCell(its,null))}`}).join('')}</div></div>`};
  // The figure in black: on the bar's colour when it reaches it, else on a small white pill (a small share).
  const bar=(p,c,l)=>`<span class="sf ${p>=IN?'in':''}" style="--p:${p*100}%;--c:${c}"><span class="lab ${p>=.45?'on':''}">${l}</span><b class="v">${pct(p)}</b></span>`;
  const kp=(t,p,v)=>`<div class="kpi"><span class="t">${t}</span>${bar(p,'var(--st-done)',T('Done'))}${bar(v,'var(--st-val)',T('Validated'))}</div>`;
  L.innerHTML=`<div class="kpis">${kp(T('Shots'),M.progress.shot,M.validation.shot)}${kp(T('Assets'),M.progress.asset,M.validation.asset)}
    <div class="kpi"><span class="t">${T('Open retakes')}</span><span class="big">${items.reduce((a,i)=>a+openRtk(i),0)}</span><span class="faint">${T('on {n} file|on {n} files',{n:items.filter(openRtk).length})}</span></div>
    ${M.schedule?`<div class="kpi"><span class="t">${T('Schedule · day {d} / {total}',{d:M.schedule.elapsed_days,total:M.schedule.total_days})}</span><span class="sf sch ${M.progress.shot>=IN?'in':''}" style="--p:${M.progress.shot*100}%;--c:var(--st-done);--e:${M.schedule.expected*100}%" title="${T('The line: where the shots should be today')}"><span class="lab ${M.progress.shot>=.45?'on':''}">${T('Shots done')}</span><b class="v">${pct(M.progress.shot)}</b><i class="mk2"></i></span><span class="faint">${T('expected {pct}',{pct:pct(M.schedule.expected)})} · ${M.progress.shot<M.schedule.expected?'<span class="bad">'+T('{n} points behind',{n:Math.round((M.schedule.expected-M.progress.shot)*100)})+'</span>':T('on time')}</span></div>`:''}
    <div class="kpi"><span class="t">${T('Set aside')}</span><span class="big">${items.filter(omitted).length}</span><span class="faint">${T('on hold or cancelled, out of the figures')}</span></div></div>
  ${S.weights?`<p class="weights">${T('A department counts 0 % not started, {wip} % in progress, {rework} % reworked, {rtk} % done with an open retake, 100 % done. A file is the mean of its required departments, a sequence the mean of its files. Files set aside don\'t count. Validated is counted apart: by the role {role}, on the stable shown.',{wip:(M.weights||{}).wip??33,rework:(M.weights||{}).rework??67,rtk:(M.weights||{}).rtk??67,role:esc(M.role)})}</p>`:''}
  ${table('shot',T('Shots'))}${table('asset',T('Assets'))}`;
}

