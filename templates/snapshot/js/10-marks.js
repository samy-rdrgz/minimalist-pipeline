/* ---------- small pieces ---------- */
// A name: its group's prefix quiet, the rest in bold, a break allowed after
// each _ and - (no break inside a number).
function nameHtml(it){var p=it.name.indexOf(it.group+'_')===0?it.group+'_':'',rest=it.name.slice(p.length);
var br=function(s){return esc(s).replace(/([_-])/g,'$1<wbr>');};
return (p?'<span class="nm-pre">'+br(p)+'</span>':'')+'<span class="nm-main">'+br(rest)+'</span>';}
function thumb(it){return it.thumb?'<button type="button" class="thumb" data-zoom="'+it.i+'" aria-label="'+esc(it.name)+', full size">'+
'<span class="frame"><img alt="" loading="lazy" src="'+img(it.thumb)+'"></span></button>':'<span class="thumb none"><span class="frame"></span></span>';}
function mark(s){return s?'<i class="m s-'+s+'" title="'+LABEL[s]+'"></i>':'<i class="m na" title="Not required"></i>';}
// A department's symbol: validated (a ✓ in it) by the top role or another,
// else its state.
function validAt(it,d){var o=it.ok[d];return it.states[d]==='done'&&o&&!o.old?o:null;}
function symCls(it,d){var o=validAt(it,d);return o?(o.role===META.role?'s-prod':'s-sup'):'s-'+it.states[d];}
// Waiting on an earlier stage, to redo since one changed (not said still
// done in your review): the clock or the arrow in the diamond's place, its
// state a dot on it. Validated on an older stable: a dashed violet ring.
function flagOf(it,d){var f=(it.flags||{})[d]||{};return f.waiting?'wait':f.to_redo&&!peek(it).synced[d]?'redo':'';}
function marks(it,d){var o=it.ok[d];return o&&o.old?'<span class="mk-old"></span>':'';}
// Its capsule's words, two short lines: the state with its version and
// the validation; then a stage's flags (lib/status.py stage_flags()).
function capWords(it,d){var s=it.states[d],o=it.ok[d],v=validAt(it,d),f=(it.flags||{})[d]||{},w;
w=v?'✓ '+v.role.toUpperCase()+(v.by?' · '+v.by:'')+(it.stable_v?' · on '+it.stable_v:''):
s==='done'?'DONE'+(it.stable_v?' · stable '+it.stable_v:''):s==='rework'?'REWORKED SINCE '+(it.stable_v||'the stable'):
s==='wip'?'WIP'+(it.wip_v?' · '+it.wip_v:''):'NOT STARTED';
if(o&&o.old)w+=' · ✓ '+o.role.toUpperCase()+' on '+o.seen+', to review again';
return [w,[f.waiting?'waiting: '+f.waiting:'',f.to_redo?'redo: '+f.to_redo:''].filter(Boolean).join(' · ')];}
// An open retake on a department: its post-it -- red from a validation
// role, outlined from the team, their number in it. [html, words].
function rtkTag(it,d){var r=it.rtk[d];if(!r)return null;var n=(it.rtkNotes[d]||[]).length||1;
return ['<span class="pi pi-'+(r==='team'?'team':'role')+'">'+(n>1?n+' ':'')+'RTK</span>',
(n>1?n+' open retakes':'an open retake')+(r==='team'?' from the team':' from a validation role')];}
// A department's cell: its symbol, its capsule on hover or focus, its
// retake's post-it, your review's say (not in the panel: its own is by
// the state, noYou). Not required: empty.
function cell(it,d,noYou,noRtk){var rq=peek(it).req[d];
// Required or not any more in your review: shown as it'll be, + / − you.
if(!it.states[d])return rq?'<span class="cell req-add" tabindex="0" aria-label="'+esc(cap(d))+': required in your review"><span class="cap"><span class="g s-todo"></span><span class="lab">REQUIRED IN YOUR REVIEW</span></span>'+
(noYou?'':'<span class="you nt" title="Required in your review">+ YOU</span>')+'</span>':'<span class="cell na" aria-label="'+esc(cap(d))+': not required"></span>';
var w=capWords(it,d),r=rtkTag(it,d);if(rq===false)w=[w[0],'not required any more in your review'];
return '<span class="cell'+(rq===false?' req-rm':'')+'" tabindex="0" aria-label="'+esc(cap(d)+': '+(w[0]+(w[1]?' · '+w[1]:'')).toLowerCase()+(r?', '+r[1]:''))+'"><span class="cap">'+(flagOf(it,d)?'<span class="g fl fl-'+flagOf(it,d)+'"><svg class="fi" viewBox="0 0 16 16"><use href="#i-'+flagOf(it,d)+'"/></svg><i class="pz '+symCls(it,d)+'"></i>':
'<span class="g '+symCls(it,d)+'">'+(validAt(it,d)?'✓':''))+marks(it,d)+'</span><span class="lab">'+esc(w[0])+(w[1]?'<span class="l2">'+esc(w[1])+'</span>':'')+'</span></span>'+(r&&!noRtk?r[0]:'')+(noYou?'':rq===false?'<span class="you nt" title="Not required any more in your review">− YOU</span>':you(it,d)||(peek(it).synced[d]?'<span class="you sd" title="Still done in your review: its work holds">✓ YOU</span>':''))+'</span>';}
function okTag(it,d){var o=it.ok[d];if(!o)return '';
return '<span class="ok'+(o.old?' old':'')+'" title="'+esc(o.tip)+'">✓ '+esc(o.role)+'</span>';}
function rkTag(it,d){var r=rtkTag(it,d);return r?r[0]:'';}
// The same, in a line of text (the compact list, the panel).
function under(it,d){return '<span class="inl">'+rkTag(it,d)+okTag(it,d)+you(it,d)+'</span>';}
// "With your review": a file's Done and Validated as if the review went in
// (MPStatus, templates/snapshot/status.js -- lib/status.py's twin): its
// retakes, fixes, replies, departments, set aside, and its validations
// when made as the top role. null figures: set aside.
function reviewState(it){var e=rv.files[it.file];if(!e||!it.tracked&&!Object.keys(e.req||{}).length)return null;
var team=asTeam(),states={};Object.keys(it.states).forEach(function(d){states[d]=it.states[d];});
Object.keys(e.req||{}).forEach(function(d){if(e.req[d]){if(!(d in states))states[d]='todo';}else delete states[d];});
if(e.omit?e.omit.state:(it.omit||{}).state)return {omit:true};
var fixed=e.fixed||{},an=answered(it).deps,rtk=[];
Object.keys(states).forEach(function(d){var open=(it.rtkNotes[d]||[]).some(function(n){return !fixed[n.id];}),v=e.deps[d];
if(open||an[d]||(v&&sent(v)&&!v.ok&&retakes(v.text||'')>0))rtk.push(d);});
var gen=it.genRtks.some(function(n){return !fixed[n.id];})||retakes(e.text||'')>0;
var top=!team&&rv.role===META.role;
return {states:states,rtk:rtk,gen:gen,ok:function(d){var v=top?verdict(it,d):'';if(v==='ok')return 1;if(v==='no')return 0;return baseOk(it,d);}};}
function reviewed(it){var r=reviewState(it);if(!r)return {done:it.done,valid:it.valid};if(r.omit)return {done:null,valid:null};
var done=MPStatus.fileProgress({departments:r.states,rtk_departments:r.rtk,general_rtk:r.gen},W),vals=Object.keys(r.states).map(r.ok);
return {done:done,valid:vals.length?vals.reduce(function(s,x){return s+x;},0)/vals.length:null};}
// Validated by the top role (or an equivalent one) at the stable shown.
function baseOk(it,d){if(it.validated)return it.validated.indexOf(d)>=0?1:0;var o=it.ok[d];return o&&!o.old&&o.role===META.role?1:0;}
// A list's figures with the review: its files as reviewed, the new ones
// planned in it (nothing started yet).
function reviewedOf(list,planned){var r=list.map(reviewed),z=planned.map(function(c){return c.departments.length?0:null;});
return {done:MPStatus.average(r.map(function(x){return x.done;}).concat(z)),valid:MPStatus.average(r.map(function(x){return x.valid;}).concat(z))};}
// The figures with your review, after the pencil (Blender's grease
// pencil): only when it moves them; what they are now in its tip -- shown
// on hover, and on a tap (a touch screen has no hover). with: "with you",
// where there's room.
function withReview(before,after,with_){if(!reviewing()||after.done==null)return '';var vv=META.role&&after.valid!=null;
if(Math.round(after.done*100)===Math.round((before.done||0)*100)&&(!vv||Math.round(after.valid*100)===Math.round((before.valid||0)*100)))return '';
var tip='With your review: '+pct(after.done)+' done'+(vv?' · '+pct(after.valid)+' validated':'')+'\nNow: '+pct(before.done||0)+(vv?' · '+pct(before.valid||0):'');
return '<span class="lv" tabindex="0" role="note" data-tip="'+esc(tip)+'" aria-label="'+esc(tip)+'">'+ico('review')+(with_?'<i>with you</i> ':'')+'<strong>'+pct(after.done)+'</strong>'+(vv?' <em>· '+pct(after.valid)+'</em>':'')+'</span>';}
// Its tip floats over the page (a header or a list may clip it): on
// hover or focus, and a tap shows or hides it.
var lvTip=null,lvOn=null;function lvShow(l){if(!lvTip){lvTip=document.createElement('div');lvTip.className='lv-tip';lvTip.setAttribute('role','tooltip');document.body.appendChild(lvTip);}
lvOn=l;if(!l){lvTip.hidden=true;return;}lvTip.textContent=l.dataset.tip;lvTip.hidden=false;var r=l.getBoundingClientRect();
lvTip.style.left=Math.max(8,Math.min(r.left,innerWidth-lvTip.offsetWidth-8))+'px';lvTip.style.top=(r.bottom+6)+'px';}
document.addEventListener('click',function(ev){var l=ev.target.closest&&ev.target.closest('.lv');if(l){ev.stopPropagation();ev.preventDefault();lvShow(lvOn===l&&lvTip&&!lvTip.hidden?null:l);}else if(lvOn)lvShow(null);},true);
['mouseover','focusin'].forEach(function(k){document.addEventListener(k,function(ev){var l=ev.target.closest&&ev.target.closest('.lv');if(l)lvShow(l);});});
['mouseout','focusout'].forEach(function(k){document.addEventListener(k,function(ev){var l=ev.target.closest&&ev.target.closest('.lv');if(l&&!(ev.relatedTarget&&l.contains(ev.relatedTarget)))lvShow(null);});});
addEventListener('scroll',function(){if(lvOn)lvShow(null);},true);
// The panel's figures, with the review's.
function kpiHtml(it){return it.tracked?dv(it.done,it.valid,true)+withReview({done:it.done,valid:it.valid},reviewed(it),true):'';}
// Done and validated, always both: a double bar, then "84 % · 0 %".
function dv(done,val,big){if(done==null)return '<span class="faint">–</span>';var v=META.role&&val!=null;
return '<span class="dv'+(big?' big':'')+'"><span class="bar2"><i style="width:'+done*100+'%"></i>'+(v?'<i class="v" style="width:'+Math.min(val,done)*100+'%"></i>':'')+'</span>'+
'<span class="dvt"><b>'+pct(done)+'</b>'+(v?' <span class="vt" title="Validated by '+esc(META.role)+'">· '+pct(val)+'</span>':'')+'</span></span>';}

