/* ---------- Watch large ---------- */
function renderWide(){
  const W=$('#wide');if(!S.wide){W.hidden=true;return}
  const it=cur();if(!it||S.ws==='farm'){S.wide=false;W.hidden=true;return}
  W.hidden=false;const g=groupOf(it),sib=items.filter(i=>i.kind===it.kind&&groupOf(i)===g),V=versOf(it),v=V[mVer(it).i],rv=S.review;
  const req=DEPTS[it.kind].filter(d=>required(it).includes(d));if(!req.includes(S.wdep))S.wdep=req.find(d=>it.mine[d]==='rtk')||req[0]||'';
  const mk=marks(it);
  const mkH=mk.map(f=>{const x=(fIdx(f.a)-1)/(NF-1)*100;return (f.b?`<span class="rng" style="left:${x}%;width:${(f.b-f.a)/(NF-1)*100}%"></span>`:'')+`<button class="mk ${f.rtk?'':'n'}" style="left:${x}%" data-goto="${f.a}" title="${f.rtk?'RTK':'Note'} f${f.a}${f.b?'-'+f.b:''} : ${esc(f.n.text||T('(no text)'))}"></button>`}).join('');
  const rng=S.rangeStart!=null?`<span class="rng sel" id="rng-sel" style="left:${(Math.min(S.rangeStart,S.frame)-1)/(NF-1)*100}%;width:${Math.abs(S.frame-S.rangeStart)/(NF-1)*100}%"></span>`:'';
  const dRow=d=>{const x=info(it,d),m=it.mine[d];return `<div class="wd ${d===S.wdep?'on':''}"><button class="wdn" data-wdep="${d}" title="${T('Write your retakes here')}">${glyph(x.base,x.corner,x.cnt,x.note)}<span class="nm"><b>${LBL[d]}</b><span class="s ${x.tone}">${esc(x.l)}${x.s?' · '+esc(x.s):''}</span></span></button>
    ${rv?`<span class="join"><button class="btn sm ok icon" data-wok="${d}" aria-pressed="${m==='val'}" ${rv.role===TEAM||!['done','rework'].includes(it.states[d])||it.ok[d]?'disabled':''} aria-label="${T('Validate {dept}',{dept:LBL[d]})}" title="${T('Validate')}">${ic('b-checkmark')}</button><button class="btn sm alert icon" data-wko="${d}" aria-pressed="${m==='rtk'}" aria-label="${T('Retake {dept}',{dept:LBL[d]})}" title="${T('Send back as a retake')}">${ic('b-x')}</button></span>`:''}</div>`};
  const notesAt=mk.length?mk.map(f=>`<button class="wn" data-goto="${f.a}"><span class="ft ${f.b?'rg':f.rtk?'':'nt'}">f${f.a}${f.b?'-'+f.b:''}</span><span class="tx">${esc(f.n.text||T('(no text)'))}<small> · ${esc((f.n.deps||[]).map(d=>LBL[d]||d).join(', ')||T('no department'))}${f.n.author?' · '+esc(f.n.author):''}</small></span></button>`).join(''):'<p class="faint" style="margin:0">'+T('No note at a frame on this video.')+'</p>';
  const writer=rv&&S.wdep?`<div class="ww"><div class="wwl"><span class="join"><button class="btn sm" data-wtype="rtk" aria-pressed="${S.wtype==='rtk'}">Retake</button><button class="btn sm" data-wtype="note" aria-pressed="${S.wtype==='note'}">${T('Remark')}</button></span>
      <span class="lbl">${S.rangeStart!=null?T('from <b>f{a}</b> to <b>f{b}</b> on <b>{dept}</b>',{a:fNo(S.rangeStart),b:`<span data-f>${fNo(S.frame)}</span>`,dept:LBL[S.wdep]}):T('at <b>f{b}</b> on <b>{dept}</b>',{b:`<span data-f>${fNo(S.frame)}</span>`,dept:LBL[S.wdep]})}</span>
      <button class="btn sm ${S.rangeStart!=null?'':'tool'}" data-tp="in" ${pOff(it)} aria-pressed="${S.rangeStart!=null}" title="${S.rangeStart!=null?T('Forget the range\'s start'):T('A range: its start at the frame shown, its end where you are when you add (I)')}">${S.rangeStart!=null?'⇤ f'+S.rangeStart+' ✕':'⇤ '+T('Range from here')}</button></div>
      <label class="field ta"><textarea id="w-ta" rows="3" placeholder="${T('Write as you watch: Enter adds, Shift+Enter goes to a new line')}" aria-label="${T('Text')}"></textarea></label></div>`
    :!rv?`<p class="faint" style="margin:0">${T('Start a review to validate, send back and write at a frame.')}</p><button class="btn primary" id="rv-open-w">${ic('b-greasepencil')}${T('Review')}</button>`:'';
  W.innerHTML=`<div class="w-head"><button class="btn icon" data-wclose aria-label="${T('Close')}" title="${T('Close (Esc)')}">${ic('b-x')}</button>
      <span class="phead"><span class="pname">${it.name}</span><span class="d">${[v&&v.folder,it.toCheck?T('to check'):'',it.desc].filter(Boolean).map(esc).join(' · ')}</span></span>
      <span class="faint only-wide">${S.seqPlay?'▶ '+T('playing the sequence')+' · ':''}${T('{k} / {n} in {seq}',{k:sib.findIndex(i=>i.name===it.name)+1,n:sib.length,seq:g})}</span>
      <span class="join"><button class="btn icon" data-wstep="-1" aria-label="${T('Previous file')}" title="${T('Previous file (←)')}">${ic('b-tria_left')}</button><button class="btn icon" data-wstep="1" aria-label="${T('Next file')}" title="${T('Next file (→)')}">${ic('b-tria_right')}</button></span>
      ${rv?`<span class="review-chip only-wide"><span class="who">${esc(rv.name)} · ${rv.role}</span></span>`:''}
      <button class="btn icon" data-act="player" aria-label="${T('This machine\'s player')}" title="${T('Open the original video in this machine\'s player')}">${ic('b-file_movie')}</button>
      <button class="btn icon" data-full aria-label="${T('Full screen')}" title="${T('Full screen')}">${ic('b-fullscreen_enter')}</button></div>
    <div class="w-body"><div class="w-main">
      <div class="w-stage ${S.m.side==='B'&&V.length>1?'is-b':''}">${it.thumb?`<img src="${it.thumb}" alt="${T('Picture of {name}',{name:it.name})}">`:`<span class="noimg">${T('Not rendered yet')}</span>`}<span class="hud">${V.length>1?`<b class="ab">${S.m.side}</b> `:''}${v?esc(v.folder)+' · ':''}f <span data-f>${fNo(S.frame)}</span></span></div>
      <div class="w-tl"><div class="scrub big ${rendered(it)?'':'off'}" data-scrub role="slider" tabindex="0" aria-label="Frame" aria-valuemin="1" aria-valuemax="${NF}" aria-valuenow="${S.frame}">${mkH}${rng}<span class="ph" style="left:${(S.frame-1)/(NF-1)*100}%"></span></div>
        <div class="ruler"><span>f1</span><span>f${Math.round(NF/4)}</span><span>f${Math.round(NF/2)}</span><span>f${Math.round(NF*3/4)}</span><span>f${NF}</span></div></div>
      <div class="w-tp"><span class="join"><button class="btn icon" data-tp="vprev" aria-label="${T('Previous version')}" title="${T('Previous version')}" ${V.length>1?'':'disabled'}>${ic('b-back')}</button>
        <button class="btn icon" data-tp="fprev" ${pOff(it)} aria-label="${T('Previous frame')}" title="${T('Previous frame (,)')}">${ic('b-frame_prev')}</button>
        <button class="btn icon play" data-tp="play" ${pOff(it)} aria-label="${T('Play')}" title="${T('Play (Space)')}">${ic(S.playing?'b-pause':'b-play')}</button>
        <button class="btn icon" data-tp="fnext" ${pOff(it)} aria-label="${T('Next frame')}" title="${T('Next frame (.)')}">${ic('b-frame_next')}</button>
        <button class="btn icon" data-tp="vnext" aria-label="${T('Next version')}" title="${T('Next version')}" ${V.length>1?'':'disabled'}>${ic('b-forward')}</button></span>
        <button class="btn icon" data-tp="snd" aria-label="${T('Sound')}" title="${T('Sound (M)')}" aria-pressed="${!S.muted}">${ic(S.muted?'b-mute_ipo_off':'b-mute_ipo_on')}</button>
        <span class="bigf">f <span data-f>${fNo(S.frame)}</span></span>${verHTML(it,'w')}${abHTML(it,'w').replace('ctl abrow','abrow')}<span class="sp"></span>
        <div class="strip"><span class="faint">${g}</span>${sib.map(i=>`<button class="${i.name===it.name?'cur':''}" data-film="${i.name}" title="${i.name}"><span class="thumb">${i.thumb?`<img src="${i.thumb}" alt="">`:''}</span><span class="fn"><span class="dt" style="background:${DOT[worst(i)]}"></span>${i.kind==='shot'?i.name.replace(i.group+'_',''):i.name}</span></button>`).join('')}</div></div>
    </div>
    <div class="w-side"><div class="sec"><div class="sec-h">${T('Departments')}<span class="sp"></span>${rv&&rv.role!==TEAM?`<button class="btn sm ok" data-valall title="${T('Validate every done department (V)')}">${ic('b-checkmark')}${T('All the done')}</button>`:''}</div>${req.map(dRow).join('')||'<span class="faint">'+T('No department required.')+'</span>'}</div>
      <div class="sec"><div class="sec-h">${T('Notes at their frames')}<span class="sp"></span><span class="faint" style="text-transform:none;letter-spacing:0">${T('click: go there')}</span></div>${notesAt}</div>
      <div class="sec wsec">${writer}</div></div></div>`;
  // The strip alone scrolls: scrollIntoView would also scroll the panes around it.
  const st=W.querySelector('.strip'),cb=st&&st.querySelector('.cur');if(cb)st.scrollLeft=cb.offsetLeft-st.offsetLeft-(st.clientWidth-cb.offsetWidth)/2;
}
function wideAdd(){
  const ta=$('#w-ta');if(!ta)return;const txt=ta.value.trim(),it=cur(),d=S.wdep;if(!txt&&S.wtype!=='rtk')return;
  const fr=rangeStr();
  A.note(it,{type:S.wtype,dept:d,text:txt,frames:fr});S.rangeStart=null;refresh();msg(S.wtype==='rtk'?T('Retake at {frames} on {dept}',{frames:fr||'—',dept:LBL[d]}):T('Remark at {frames} on {dept}',{frames:fr||'—',dept:LBL[d]}));$('#w-ta')?.focus();
}

