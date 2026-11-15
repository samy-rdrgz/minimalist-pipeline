// The production snapshot page (lib/snapshot_page.py): everything below is
// drawn from the data the export embeds (#data). One file, offline, any
// browser; the review written here is kept in this browser and downloaded
// as the .json Import review reads (REVIEW_JSON_FORMAT).
(function(){
'use strict';
var $=function(id){return document.getElementById(id);};
var DATA=JSON.parse($('data').textContent),META=DATA.meta,D=DATA.items;
var TABS=[['shot','Shots'],['asset','Assets'],['library','Libraries']];
var LABEL={done:'Done',rework:'Done, reworked since',wip:'In progress',todo:'Not started'};
var NL=String.fromCharCode(10);
var esc=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});};
var cap=function(s){return s.charAt(0).toUpperCase()+s.slice(1);};
var pct=function(v){return v==null?'–':Math.round(v*100)+' %';};
function isDone(s){return s==='done'||s==='rework';}
function plural(n,w){return n+' '+w+(n===1?'':'s');}
// A note's author, nothing when not known (no "unknown").
function author(n){var a=(n.author||'').trim();return a&&a.toLowerCase()!=='unknown'?esc(a):'';}

/* ---------- images: each stored once (#data images), turned into blob URLs
once — short src strings, however often the list is redrawn ---------- */
var urls={};
function img(id){if(!id)return '';if(urls[id])return urls[id];
try{var b=atob(DATA.images[id]),a=new Uint8Array(b.length);for(var i=0;i<b.length;i++)a[i]=b.charCodeAt(i);
urls[id]=URL.createObjectURL(new Blob([a],{type:'image/jpeg'}));}
catch(e){urls[id]='data:image/jpeg;base64,'+DATA.images[id];}return urls[id];}

/* ---------- items ---------- */
// Made again from new data on the live page (applyData()).
var byFile={},byName={},byKey={},tabs=[];
function prepare(){byFile={};byName={};byKey={};
D.forEach(function(it,i){it.i=i;byFile[it.file]=it;byName[it.name]=it;if(it.live&&it.live.key)byKey[it.live.key]=it;
it.tab=it.root==='library'?'library':it.kind;
it.tracked=Object.keys(it.states).length>0;
var open=it.notes.filter(function(n){return !n.closed;});
// Open threads, by where the page shows them: an open RTK under its
// department (none: the general retakes), the rest as notes.
it.rtkNotes={};it.genRtks=[];it.otherNotes=[];
open.forEach(function(n){if(n.type==='rtk'&&n.done===false){
if(n.deps.length)n.deps.forEach(function(d){(it.rtkNotes[d]=it.rtkNotes[d]||[]).push(n);});else it.genRtks.push(n);}});
it.todos={};it.dnotes={};open.forEach(function(n){if(n.type==='todo'&&n.done===false)n.deps.forEach(function(d){it.todos[d]=(it.todos[d]||0)+1;});
// An open note on a department (a remark, the prod's "n:" one): its grey ◆ too.
else if(n.type==='note'&&!n.approval)n.deps.forEach(function(d){it.dnotes[d]=(it.dnotes[d]||0)+1;});});
it.openNotes=open.filter(function(n){return !(n.type==='rtk'&&n.done===false)&&!n.approval;});});
// The sections present, then Breakdown: the progress by group and department.
tabs=TABS.filter(function(t){return D.some(function(it){return it.tab===t[0];});}).concat([['breakdown','Breakdown']]);}
prepare();
function depsOf(tab){return META.departments[tab==='shot'?'shot':'asset'];}
function validNow(it,d){return it.ok[d]&&!it.ok[d].old;}

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
function reviewed(it){var e=rv.files[it.file];if(!e||!it.tracked&&!Object.keys(e.req||{}).length)return {done:it.done,valid:it.valid};
var team=asTeam(),states={};Object.keys(it.states).forEach(function(d){states[d]=it.states[d];});
Object.keys(e.req||{}).forEach(function(d){if(e.req[d]){if(!(d in states))states[d]='todo';}else delete states[d];});
if(e.omit?e.omit.state:(it.omit||{}).state)return {done:null,valid:null};
var fixed=e.fixed||{},an=answered(it).deps,rtk=[];
Object.keys(states).forEach(function(d){var open=(it.rtkNotes[d]||[]).some(function(n){return !fixed[n.id];}),v=e.deps[d];
if(open||an[d]||(v&&sent(v)&&!v.ok&&retakes(v.text||'')>0))rtk.push(d);});
var gen=it.genRtks.some(function(n){return !fixed[n.id];})||retakes(e.text||'')>0;
var done=MPStatus.fileProgress({departments:states,rtk_departments:rtk,general_rtk:gen},W);
var top=!team&&rv.role===META.role,vals=Object.keys(states).map(function(d){var v=top?verdict(it,d):'';
if(v==='ok')return 1;if(v==='no')return 0;var o=it.ok[d];return o&&!o.old&&o.role===META.role?1:0;});
return {done:done,valid:vals.length?vals.reduce(function(s,x){return s+x;},0)/vals.length:null};}
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

/* ---------- review state: as the page before (same key, same shape) ---------- */
// creates: the new shots and assets the review asks for (planned).
var rv={author:'',role:'',date:'',files:{},creates:[]};
// Live: what's on its way to Blender (liveSend()).
var LIVE_OUT={busy:false,again:false,sent:{},t:0,after:null,say:'live'};
var KEY='mp-review:'+META.project+':'+(META.live?'live':META.snapshot);
// synced: Still done per department; req: a department required added
// (true) or removed (false); omit: {state, reason} set aside or counted again.
function entry(it){var e=rv.files[it.file]||(rv.files[it.file]={deps:{},all:false,text:'',desc:null});e.fixed=e.fixed||{};e.replies=e.replies||{};e.synced=e.synced||{};e.req=e.req||{};e.assign=e.assign||{};return e;}
function peek(it){var e=rv.files[it.file]||{deps:{},all:false,text:'',desc:null,fixed:{},replies:{}};e.synced=e.synced||{};e.req=e.req||{};e.assign=e.assign||{};return e;}
// A file's own changes in the review: still done, departments, set aside,
// who a department is assigned to.
function fileChanges(it,e){return Object.keys(e.synced||{}).length+Object.keys(e.req||{}).length+(omitChanged(it,e)?1:0)+Object.keys(e.assign||{}).length;}
// Who a department is assigned to: as the review leaves it.
function people(it,d){var e=peek(it);return d in e.assign?e.assign[d]:((it.assignees||{})[d]||[]);}
// Me: the review's name (Review asks it), lower case as the team's.
function me(){return (rv.author||'').trim().toLowerCase();}
function mineDeps(it){var m=me();return m?Object.keys(it.states).filter(function(d){return people(it,d).indexOf(m)>=0;}):[];}
function omitChanged(it,e){return !!e.omit&&(e.omit.state!==((it.omit||{}).state||'')||(e.omit.state&&e.omit.reason!==((it.omit||{}).reason||'')));}
// The open notes this review replies to with a retake (anything but
// "note:" lines): still to redo -- their departments sent back as a ✕
// would ({deps}), the whole file's when they have none (gen).
function answered(it){var e=peek(it),ids=replies(e),out={deps:{},gen:false};if(!ids.length)return out;
it.notes.forEach(function(n){if(!n.closed&&ids.indexOf(n.id)>=0&&!noteOnly(e.replies[n.id])){
if(n.deps.length)n.deps.forEach(function(d){out.deps[d]=1;});else out.gen=true;}});return out;}
// Replies written, by the note they answer.
function replies(e){var r=e.replies||{};return Object.keys(r).filter(function(id){return (r[id]||'').trim();});}
function changes(it){var e=rv.files[it.file];if(!e)return 0;
var n=Object.keys(e.deps).filter(function(d){return sent(e.deps[d]);}).length+(e.all&&!asTeam()?1:0)+(e.text.trim()?1:0)+Object.keys(e.fixed||{}).length+replies(e).length;
if(e.desc!==null&&e.desc.trim()&&e.desc.trim()!==it.desc)n++;return n+fileChanges(it,e);}
// What this review says of a department: 'ok' (its own ✓, or all done), 'no',
// 'note' (only "note:" lines: a remark, its validation left as it is), or ''.
// Written as the team (Role "team", no validation role of that name): its
// retakes and notes are the team's own, it validates nothing -- a ✓ or an
// empty ✕ (a validation withdrawn) is neither shown as yours nor sent.
function asTeam(){return rv.role==='team'&&(META.roles||[]).indexOf('team')<0;}
function sent(v){return !asTeam()||(!v.ok&&!!(v.text||'').trim());}
function verdict(it,d){var e=peek(it),v=e.deps[d];if(v&&sent(v))return v.ok?'ok':noteOnly(v.text)?'note':'no';
if(answered(it).deps[d])return 'no';
return e.all&&!asTeam()&&isDone(it.states[d])?'ok':'';}
function you(it,d){var v=verdict(it,d);if(!v)return '';
return v==='ok'?'<span class="you y" title="Validated in your review">✓ YOU</span>':v==='note'?youNote():
'<span class="you n" title="Sent back in your review">✕ YOU</span>';}
function youNote(){return '<span class="you nt" title="A note in your review: a remark, nothing withdrawn">✎ YOU</span>';}
// Written, and nothing but "note:" lines.
function noteOnly(t){return !!(t&&t.trim())&&retakes(t)===0;}
function notesIn(t){return (t||'').split(NL).filter(function(l){return NOTE_RE.test(l);}).length;}
// "note:" -- or "note :", "n:", any case -- after the line's tags: a remark
// (lib/review_import.py _NOTE_PREFIX, the same).
var NOTE_RE=/^\s*(?:\[[^\]]*\]\s*)*(?:note|n)\s*:/i;
function retakes(t){return t.split(NL).filter(function(l){var w=l.trim().split(' ').filter(function(x){return x&&x.charAt(0)!=='[';});
return w.length&&!NOTE_RE.test(l);}).length;}
function summary(){var c={files:0,ok:0,rt:0,out:0,desc:0,fixed:0,replies:0,notes:0,changes:0};D.forEach(function(it){if(!changes(it))return;var e=rv.files[it.file];c.files++;c.fixed+=Object.keys(e.fixed||{}).length;c.replies+=replies(e).length;c.changes+=fileChanges(it,e);
Object.keys(e.deps).forEach(function(d){var v=e.deps[d];if(!sent(v))return;if(v.ok)c.ok++;else if(v.text.trim()){c.rt+=retakes(v.text);c.notes+=notesIn(v.text);}else c.out++;});
var an=answered(it).deps;Object.keys(an).forEach(function(d){if(!e.deps[d]&&!asTeam())c.out++;});
if(e.all&&!asTeam())Object.keys(it.states).forEach(function(d){if(isDone(it.states[d])&&!e.deps[d]&&!an[d])c.ok++;});
c.rt+=retakes(e.text);c.notes+=notesIn(e.text);if(e.desc!==null&&e.desc.trim()&&e.desc.trim()!==it.desc)c.desc++;});c.creates=(rv.creates||[]).length;return c;}
function store(){try{localStorage.setItem(KEY,JSON.stringify(rv));}catch(e){}}
// Live (served by Blender): each change sent too, a moment later (liveSend()).
function save(){store();if(META.live&&reviewing())liveSend();}

/* ---------- badges: only what the row shows nowhere else ---------- */
// The small icons of the tags (stand-ins for Blender's, see NOTES.md).
var IC={eye:'<path d="M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="2" fill="currentColor"/>',
time:'<circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 4.6V8l2.4 1.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
render:'<rect x="1.5" y="3" width="13" height="10" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M6.5 5.8v4.4L10.2 8z" fill="currentColor"/>',
cancel:'<path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
warn:'<path d="M8 2l6.5 11.5h-13z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 6.5v3.2M8 11.6v.1" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
// The player's, after Blender's PLAY, PAUSE, FRAME_PREV / NEXT, REW / FF,
// FULLSCREEN_ENTER / EXIT.
play:'<path d="M4.5 2.8v10.4c0 .6.6 1 1.1.7l8-5.2c.5-.3.5-1 0-1.3l-8-5.2c-.5-.4-1.1 0-1.1.6z" fill="currentColor"/>',
pause:'<rect x="3.5" y="2.5" width="3" height="11" rx="1" fill="currentColor"/><rect x="9.5" y="2.5" width="3" height="11" rx="1" fill="currentColor"/>',
fprev:'<rect x="3" y="3" width="2" height="10" rx=".8" fill="currentColor"/><path d="M12.5 3.6v8.8c0 .5-.5.8-.9.5L6 8.5c-.4-.3-.4-.8 0-1.1l5.6-4.3c.4-.3.9 0 .9.5z" fill="currentColor"/>',
fnext:'<rect x="11" y="3" width="2" height="10" rx=".8" fill="currentColor"/><path d="M3.5 3.6v8.8c0 .5.5.8.9.5L10 8.5c.4-.3.4-.8 0-1.1L4.4 3.1c-.4-.3-.9 0-.9.5z" fill="currentColor"/>',
rew:'<rect x="1.5" y="3" width="2" height="10" rx=".8" fill="currentColor"/><path d="M9 3.8v8.4L4.5 8zM14.5 3.8v8.4L10 8z" fill="currentColor" stroke="currentColor" stroke-width=".8" stroke-linejoin="round"/>',
ff:'<rect x="12.5" y="3" width="2" height="10" rx=".8" fill="currentColor"/><path d="M7 3.8v8.4L11.5 8zM1.5 3.8v8.4L6 8z" fill="currentColor" stroke="currentColor" stroke-width=".8" stroke-linejoin="round"/>',
fsin:'<path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
fsout:'<path d="M6 2.5V6H2.5M13.5 6H10V2.5M10 13.5V10h3.5M2.5 10H6v3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
trash:'<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 8.5h5.6l.7-8.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
export:'<path d="M8 10.5V2.5M5 5.5l3-3 3 3M3 10v3.5h10V10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
review:'<path d="M10.5 2.5l3 3L6 13H3v-3z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
check:'<path d="M3 8.5l3.2 3L13 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
reply:'<path d="M6 4L2.5 7.5 6 11M2.5 7.5H10a3.5 3.5 0 0 1 3.5 3.5V12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
sound:'<path d="M2.5 6h2.5l3.5-3v10l-3.5-3H2.5z" fill="currentColor"/><path d="M10.5 5.5a3.5 3.5 0 0 1 0 5M12 3.5a6 6 0 0 1 0 9" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
text:'<path d="M3.5 2.5h9v11h-9z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>',
range:'<path d="M4.5 3H3v10h1.5M11.5 3H13v10h-1.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><circle cx="8" cy="8" r="2.6" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M8 6.6V8l.9.7" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
mute:'<path d="M2.5 6h2.5l3.5-3v10l-3.5-3H2.5z" fill="currentColor"/><path d="M10.5 6l4 4M14.5 6l-4 4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'};
// Blender's own where the page has it (icon_sprite(): "b-<name>", its
// file in templates/snapshot/icons), else the stand-in above.
var BI={play:'b-play',pause:'b-pause',fprev:'b-frame_prev',fnext:'b-frame_next',rew:'b-rew',ff:'b-ff',eye:'b-hide_off',
trash:'b-trash',import:'b-import',export:'b-export',user:'b-user',movie:'b-file_movie',prevk:'b-prev_keyframe',nextk:'b-next_keyframe',link:'b-decorate_linked',
time:'b-time',render:'b-render_still',cancel:'b-cancel',warn:'b-status_warning',fsin:'b-fullscreen_enter',fsout:'b-fullscreen_exit',
review:'b-greasepencil',help:'b-question',filter:'b-filter',search:'b-viewzoom',folder:'b-file_folder',check:'b-checkmark',team:'b-community',reply:'b-file_parent',text:'b-text',box:'b-checkbox_dehlt',settings:'b-preferences',range:'b-preview_range'};
function ico(n){return BI[n]&&document.getElementById(BI[n])?'<svg class="ico bi-'+n+'" aria-hidden="true"><use href="#'+BI[n]+'"/></svg>':
'<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">'+IC[n]+'</svg>';}
function tag(cls,icon,text,tip){return '<span class="tg tg-'+cls+'"'+(tip?' title="'+esc(tip)+'"':'')+'>'+(icon?ico(icon):'')+esc(text)+'</span>';}
// Under a file's name: a retake on no department, then its renders' tags
// -- to check, outdated, in the farm (queued, rendering, failed).
function flags(it){var h='',e=peek(it);
if(it.genRtks.length){var tm=it.genRtks.every(function(n){return n.team;});
h+='<span class="inl" title="An open retake on no department: it holds back every department"><span class="pi pi-gen pi-'+(tm?'team':'role')+'">'+(it.genRtks.length>1?it.genRtks.length+' general RTK':'General RTK')+'</span></span>';}
// A retake on no department in your review: the departments' own ✕ you.
var gen=answered(it).gen;
if(e.text.trim()||gen)h+='<span class="inl">'+(noteOnly(e.text)&&!gen?youNote():'<span class="you n" title="A retake on no department, in your review">✕ YOU</span>')+'</span>';
// Set aside, or changed in your review: as it'll be, ✎ you.
var om=omitChanged(it,e)?e.omit:it.omit;
if(om&&om.state)h+=tag('check','',(om.state==='cancelled'?'Cancelled':'On hold')+(om.reason?': '+om.reason:''),'Set aside: out of the figures');
else if(om)h+=tag('check','','Active again','Counted again in your review');
if(omitChanged(it,e))h+='<span class="inl"><span class="you nt" title="Set aside or back in your review">✎ YOU</span></span>';
if(it.to_check)h+=tag('check','eye','render to check','Rendered, not checked by the team yet');
if(it.outdated)h+=tag('old','warn','render outdated','Rendered from an older version than the last stable');
if(it.farm){var k=it.farm.state==='failed'?'fail':it.farm.state==='waiting'?'wait':'run';
h+=tag(k,k==='fail'?'cancel':k==='wait'?'time':'render','farm '+it.farm.text,'In the farm: '+it.farm.tip);}
if(e.desc!==null&&e.desc.trim()&&e.desc.trim()!==it.desc)h+=tag('check','','✎ description','Your review changes its description');
// Who a department is assigned to, changed in your review.
var ac=Object.keys(e.assign||{}),to=function(d){return cap(d)+' → '+(e.assign[d].join(', ')||'nobody');};
if(ac.length)h+=tag('check','user',ac.length===1?to(ac[0]):ac.length+' departments reassigned','Assigned in your review: '+ac.map(to).join(' · '));
return h;}
function subline(it){var p=['<span class="vers">'+esc(it.versions||'not saved yet')+'</span>'];
if(it.shots.length>1)p.push('<span>'+plural(it.shots.length,'shot')+'</span>');
if(it.openNotes.length){var t=it.openNotes.some(function(n){return n.type==='todo';});
p.push('<span class="nn'+(t?' todo':'')+'">'+plural(it.openNotes.length,'open note')+'</span>');}
return p.join('<i class="sep"> · </i>');}
/* ---------- header and summary ---------- */
var snapDate=new Date(META.snapshot);
var DAYS=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
// Day/month(/year), never the US order: 15/11/2026.
function fmtDay(d,year){return two(d.getDate())+'/'+two(d.getMonth()+1)+(year?'/'+d.getFullYear():'');}
function two(n){return ('0'+n).slice(-2);}
// A stored date, everywhere: how long ago within a week, else its day;
// the whole date in its tooltip. An old one with no time: from midnight.
function fmtDate(iso){if(!iso)return '';var d=new Date(iso.length<=10?iso+'T00:00:00':iso);if(isNaN(d))return esc(iso);
var s=(Date.now()-d)/1000,short=iso.length<=10;
var w=short?(s<86400?'today':s<2*86400?'yesterday':s<7*86400?Math.floor(s/86400)+' days ago':fmtDay(d,true)):
s<60?'just now':s<3600?Math.round(s/60)+' min ago':s<86400?Math.round(s/3600)+' h ago':s<2*86400?'yesterday':s<7*86400?Math.round(s/86400)+' days ago':fmtDay(d,true);
return '<time datetime="'+esc(iso)+'" title="'+fmtDay(d,true)+(short?'':' '+two(d.getHours())+':'+two(d.getMinutes()))+'">'+w+'</time>';}
// A date field: a button that says it as the page does, the system's
// picker behind it (its own text came out 11/15/2026).
function dateField(id,v){return '<span class="datef"><button type="button" class="btn dbtn" data-for="'+id+'">'+fmtDay(new Date(v+'T00:00:00'),true)+'</button><input id="'+id+'" type="date" value="'+esc(v)+'" tabindex="-1" aria-hidden="true"></span>';}
function wireDates(root){root.querySelectorAll('.dbtn').forEach(function(b){var inp=$(b.dataset.for);
b.onclick=function(){try{inp.showPicker();}catch(e){inp.classList.add('shown');inp.focus();}};
inp.addEventListener('change',function(){if(inp.value)b.textContent=fmtDay(new Date(inp.value+'T00:00:00'),true);});});}
// Now as the addon writes it: local time with its offset.
function isoNow(){var d=new Date(),o=-d.getTimezoneOffset(),a=Math.abs(o);
return d.getFullYear()+'-'+two(d.getMonth()+1)+'-'+two(d.getDate())+'T'+two(d.getHours())+':'+two(d.getMinutes())+':'+two(d.getSeconds())+(o<0?'-':'+')+two(Math.floor(a/60))+':'+two(a%60);}
$('h-project').innerHTML=esc(META.project).replace(/([_-])/g,'$1<wbr>');
function stamp(){snapDate=new Date(META.snapshot);var at=two(snapDate.getHours())+':'+two(snapDate.getMinutes());
// Live: served by Blender, the time of its last change.
if(META.live){$('h-when').textContent='Live · '+at;$('h-when').title='Served by Blender on this machine, kept up to date: last change at '+at;return;}
$('h-when').textContent=fmtDay(snapDate,true)+', '+at;
$('h-when').title='Snapshot of '+DAYS[snapDate.getDay()]+' '+fmtDay(snapDate,true)+', '+at+(META.exported_by?', exported by '+META.exported_by:'');}
stamp();
$('f-ver').textContent='v'+META.addon_version+' · one self-contained file, nothing loaded from the web';
document.title=META.project+(META.live?' · live':' · snapshot '+fmtDay(snapDate,true));
if(!META.live)(function(){var days=Math.floor((Date.now()-snapDate.getTime())/864e5);
if(days>=1){var a=$('age');a.hidden=false;a.textContent=days===1?'1 day old':days+' days old';
a.title='This page shows the project as it was then: it may have moved since.';}})();
// A Done's pace (done / expected): its band, as a progress spreadsheet's.
function band(done,exp){if(!exp)return null;var p=done/exp;
return p>=1.05?['ahead','ahead']:p>=1?['ontrack','on track']:p>=0.9?['slip','slightly behind']:['behind','behind'];}
// The header's figures, one line: each section's Done and Validated, its
// pace with a schedule (the Breakdown window has the rest).
function summaryCards(){var S=META.schedule,exp=S?S.expected:null,h='';
[['shot','Shots','shot'],['asset','Assets','file']].forEach(function(s){var done=META.progress[s[0]];if(done==null)return;
var n=D.filter(function(it){return it.kind===s[0];}).length,val=(META.validation||{})[s[0]],pace='',tip=s[1]+': '+plural(n,s[2])+', done '+pct(done)+(val!=null?', validated '+pct(val):'');
if(S){var b=band(done,exp),at=(S.at||{})[s[0]],days=at?Math.abs(at.days):0,cls=b?b[0]:'ontrack';
tip+=', expected '+pct(exp)+(days?', '+plural(days,'working day')+' '+(done>=exp?'ahead':'behind'):'');
if(b)pace='<span class="pace p-'+cls+'">'+Math.round(done/exp*100)+' %</span>';}
var mine=D.filter(function(it){return it.kind===s[0];}),plan=(rv.creates||[]).filter(function(c){return c.kind===s[0];});
h+='<span class="kpi" title="'+esc(tip)+'"><span class="kl">'+s[1]+'</span>'+dv(done,val,true)+pace+withReview({done:done,valid:val},reviewedOf(mine,plan),true)+'</span>';});
$('summary').innerHTML=h;}
// The schedule, at the Breakdown's top.
function scheduleCard(){var S=META.schedule;if(!S)return '';var a=new Date(S.start),b2=new Date(S.end),y=a.getFullYear()!==b2.getFullYear();
return '<div class="card sched"><div class="k-label">Schedule, on '+fmtDay(snapDate)+'</div><div class="k-row"><span class="k-big">Day '+S.elapsed_days+
'<small> / '+S.total_days+'</small></span><span style="font-size:14px;color:var(--ink-2)">'+pct(S.expected)+' expected</span></div>'+
'<div class="track"><i class="f" style="width:'+S.expected*100+'%"></i></div><div class="ends"><span>'+fmtDay(a,y)+'</span><span>'+fmtDay(b2,y)+'</span></div></div>';}
var W=META.weights;
$('weights').textContent='Each required department counts the same: not started 0 %, in progress '+W.wip+' %, done but reworked since '+W.rework+
' %, done with an open RTK '+W.rtk+' %, done 100 %. A file averages its departments — a retake on no department counts as an RTK on one of its done departments —, a group its files.'+
(META.role?' Validated, apart: the share of the required departments '+META.role+' (or an equivalent role) validated at the stable shown — a newer stable needs it again.':'');

/* ---------- the list ---------- */
var state={tab:tabs.length?tabs[0][0]:'shot',q:'',f:{},dep:'',open:{},untracked:{},showHidden:false};
// Set aside (on hold, cancelled) or with no tracked department: out of the
// list until shown -- a line at each group's end says how many, and why.
// Shown or not: kept in this browser.
var HID_KEY='mp-snapshot:hidden';try{state.showHidden=localStorage.getItem(HID_KEY)==='1';}catch(e){}
function hiddenFile(it){return !it.tracked||!!it.omit;}
function hiddenWhy(list){var oh=0,ca=0,un=0;list.forEach(function(it){if(!it.tracked)un++;else if(it.omit.state==='cancelled')ca++;else oh++;});
return [oh?'on hold':'',ca?'cancelled':'',un?'no tracked department':''].filter(Boolean).join(', ');}
var FILTERS={
rtk:function(it,d){return d?!!it.rtk[d]||it.genRtks.length>0:Object.keys(it.rtk).length>0||it.genRtks.length>0;},
notes:function(it){return it.openNotes.length>0||it.genRtks.length>0||Object.keys(it.rtkNotes).length>0;},
outdated:function(it){return it.outdated;},
farm:function(it){return !!it.farm;},
tovalid:function(it,d){return d?isDone(it.states[d])&&!validNow(it,d):Object.keys(it.states).some(function(x){return isDone(it.states[x])&&!validNow(it,x);});},
todo:function(it,d){return d?it.states[d]&&!isDone(it.states[d]):it.tracked&&it.done<100;},
// What this review touched: validated, withdrawn, retakes, a description.
mine:function(it){return changes(it)>0;},
// A department assigned to me (the review's name), or the one picked.
me:function(it,d){var m=mineDeps(it);return d?m.indexOf(d)>=0:m.length>0;}};
function match(it,anyTab){
if(!anyTab&&it.tab!==state.tab)return false;
if(state.q&&it.name.toLowerCase().indexOf(state.q)<0)return false;
if(state.dep&&!(state.dep in it.states))return false;
for(var f in state.f)if(state.f[f]&&!FILTERS[f](it,state.dep))return false;
return true;}
function avg(a){var n=a.filter(function(x){return x!=null;});return n.length?n.reduce(function(s,x){return s+x;},0)/n.length:null;}
function filtering(){return !!(state.q||state.dep||Object.keys(state.f).some(function(f){return state.f[f];}));}
var visible=[];
function drawTabs(){$('seg').innerHTML=tabs.map(function(t){return '<button type="button" data-tab="'+t[0]+'" aria-pressed="'+(t[0]===state.tab)+'">'+t[1]+
(t[0]==='breakdown'?'':'<span>'+D.filter(function(it){return it.tab===t[0];}).length+'</span>')+'</button>';}).join('');
var deps=depsOf(state.tab).filter(function(d){return D.some(function(it){return it.tab===state.tab&&d in it.states;});});
if(deps.indexOf(state.dep)<0)state.dep='';
$('depf').innerHTML='<option value="" data-short="All depts.">All departments</option>'+deps.map(function(d){return '<option value="'+esc(d)+'"'+(d===state.dep?' selected':'')+'>'+esc(cap(d))+'</option>';}).join('');
$('depf').classList.toggle('on',!!state.dep);sync('depf');}
function chipCounts(){var fb=document.querySelector('.chipf[data-f="farm"]');if(fb)fb.hidden=!D.some(function(it){return it.farm;});
// Me: only with a team (Edit project).
var fm=document.querySelector('.chipf[data-f="me"]');if(fm)fm.hidden=!(META.team||[]).length;document.querySelectorAll('.chipf[data-f]').forEach(function(b){b.querySelector('b').textContent=D.filter(function(it){
return it.tab===state.tab&&(!state.dep||state.dep in it.states)&&FILTERS[b.dataset.f](it,state.dep);}).length;});}
// A row of the list (render(): its departments' columns).
var rowDeps=[],rowCols='';
function rowHtml(it){var deps=rowDeps,cols=rowCols;
// Tinted once this review touched it: where you've been, at a glance.
return '<div class="row'+((omitChanged(it,peek(it))?peek(it).omit.state:it.omit)?' omit':'')+(changes(it)?' rv-mine':'')+(it.i===cur?' sel':'')+'" role="button" tabindex="0" data-i="'+it.i+'" style="--cols:'+cols+'"'+(changes(it)?' title="In your review"':'')+'>'+thumb(it)+
'<span class="r-name">'+nameHtml(it)+'<small>'+subline(it)+'</small><span class="flags">'+flags(it)+'</span></span>'+
deps.map(function(d){return '<span class="d">'+cell(it,d)+'</span>';}).join('')+
'<span class="r-pct">'+(it.tracked?dv(it.done,it.valid):'<span class="faint">–</span>')+'</span>'+
(it.tracked?'<span class="dl">'+deps.filter(function(d){return d in it.states;}).map(function(d){return '<span><b class="dn n-'+it.states[d]+'" title="'+LABEL[it.states[d]]+'">'+esc(cap(d))+'</b>'+under(it,d)+'</span>';}).join('')+'</span>':'')+'</div>';}
// One file's row redrawn in place, the list around it untouched: a ✓ or a
// ✕ in the panel rebuilt the whole list, and on an iPad that sent the
// page to the top (the row tapped had the focus, and was gone). The whole
// list only when the review is a filter (the row may come or go).
function renderRow(i){var row=$('list').querySelector('.row[data-i="'+i+'"]');
if(!row||state.f.mine){render();return;}
var tmp=document.createElement('div');tmp.innerHTML=rowHtml(D[i]);var n=tmp.firstChild;
row.className=n.className;if(n.title)row.title=n.title;else row.removeAttribute('title');row.innerHTML=n.innerHTML;
var grp=row.closest('.group');if(grp){grp.classList.toggle('rv-all',allReviewed(D[i].group));
var g=D[i].group,all=D.filter(function(it){return it.tab===state.tab&&it.group===g&&match(it);}),tr=all.filter(function(it){return it.tracked;}),gp=grp.querySelector('.g-pct');
if(gp)gp.outerHTML=gPct(g,all,avg(tr.map(function(x){return x.done;})),avg(tr.map(function(x){return x.valid;})));}chipCounts();countBar();}
function render(){chipCounts();barFade();
// Breakdown: the figures in place of the list, no filter to apply.
document.body.classList.toggle('tab-bd',state.tab==='breakdown');
if(state.tab==='breakdown'){visible=[];$('list').innerHTML='<div class="bd">'+stats()+'</div>';countBar();return;}
var items=D.filter(function(it){return match(it);});
var deps=depsOf(state.tab).filter(function(d){return items.some(function(it){return d in it.states||peek(it).req[d];});});
// Many departments: narrower columns, never past the page.
var w=deps.length>7?56:deps.length>5?68:84;
var cols='104px minmax(0,1fr) '+deps.map(function(){return w+'px';}).join(' ')+' 96px;--n:'+deps.length;
rowDeps=deps;rowCols=cols;
var groups={},order=[];
items.forEach(function(it){if(!groups[it.group]){groups[it.group]=[];order.push(it.group);}groups[it.group].push(it);});
visible=[];var filt=filtering();
var h=order.map(function(g){
var all=groups[g],tr=all.filter(function(it){return it.tracked;}),un=all.filter(hiddenFile),act=all.filter(function(it){return !hiddenFile(it);});
var done=avg(tr.map(function(i){return i.done;})),val=avg(tr.map(function(i){return i.valid;}));
var key=state.tab+g,closed=state.open[key]===false||(state.open[key]===undefined&&!act.length&&!filt),shown=state.showHidden||state.untracked[key]||filt;
// The hidden shown: back in their place, by name -- not after the rest.
var rows=shown?all:act;
if(!closed)rows.forEach(function(it){visible.push(it.i);});
var ini=initials(deps);
var head='<div class="thead" style="--cols:'+cols+'"><span></span><span></span>'+deps.map(function(d){return '<span class="d" title="'+esc(cap(d))+'" data-ini="'+esc(ini[d])+'">'+esc(cap(d))+'</span>';}).join('')+
'<span style="text-align:right">Done</span></div>';
var body=rows.map(rowHtml).join('');
if(un.length&&!filt)body+='<button class="untracked" data-hid="'+(shown?'0':'1')+'" data-g="'+esc(g)+'">'+un.length+' hidden · '+esc(hiddenWhy(un))+' · '+(shown?'hide ⌃':'show ⌄')+'</button>';
// The new ones this review asks for: planned, until the import makes them.
body+=(rv.creates||[]).map(function(c,n){return c.tab===state.tab&&c.group===g?'<div class="row planned" style="--cols:'+cols+'"><span class="thumb none"><span class="frame"></span></span>'+
'<span class="r-name"><span class="nm-main">'+esc(c.label)+'</span><small>planned · new '+c.kind+(c.description?' · '+esc(c.description):'')+'</small></span>'+
// Its departments, faintly: not started, once it's made.
rowDeps.map(function(d){return '<span class="d">'+(c.departments.indexOf(d)>=0?'<span class="cell" title="'+esc(cap(d))+': required"><span class="cap"><span class="g s-todo"></span></span></span>':'')+'</span>';}).join('')+
'<button type="button" class="btn icon unplan" data-unplan="'+n+'" title="Drop this new '+c.kind+'" aria-label="Drop this new '+c.kind+'">'+ico('trash')+'</button></div>':'';}).join('');
var nv=groupVideos(g).length;
// A div, not a button: its playlist's ▶ sits in it, after the name.
return '<div class="group'+(closed?' closed':'')+(allReviewed(g)?' rv-all':'')+'"><div class="g-h" role="button" tabindex="0" aria-expanded="'+!closed+'" data-g="'+esc(g)+'"><span class="g-name"><i class="caret"></i>'+esc(g)+
(nv?'<button type="button" class="g-play play" data-gplay="'+esc(g)+'" title="Watch the '+esc(g)+' videos in a row ('+nv+')" aria-label="Watch the '+esc(g)+' videos in a row">'+ico('play')+'</button>':'')+'<small>'+plural(all.length,'file')+'</small>'+
// Reviewing: a new shot (a sequence) or asset (a prefix) here.
(reviewing()&&state.tab!=='breakdown'?'<button type="button" class="btn g-new" data-new="'+esc(g)+'" title="A new '+(state.tab==='shot'?'shot in '+esc(g):'asset '+esc(g)+'_…')+', made at the review\'s import">+ '+(state.tab==='shot'?'shot':'asset')+'</button>':'')+'</span>'+
gPct(g,all,done,val)+
'</div><div class="rows">'+(tr.length?head:'')+body+'</div></div>';}).join('');
// The row or group that had the focus has it again (the keys go on),
// and the page stays where it was if the list is still as long.
var fe=document.activeElement,fsel=fe&&$('list').contains(fe)?(fe.classList.contains('row')?'.row[data-i="'+fe.dataset.i+'"]':fe.classList.contains('g-h')?'.g-h[data-g="'+CSS.escape(fe.dataset.g)+'"]':null):null,y0=scrollY;
var others=filt?tabs.filter(function(t){return t[0]!==state.tab;}).map(function(t){return [t,D.filter(function(it){return it.tab===t[0]&&match(it,true);}).length];}).filter(function(x){return x[1];}):[];
$('list').innerHTML=(h||'<div class="empty">Nothing here.</div>')+others.map(function(x){return '<button class="untracked" data-other="'+x[0][0]+'" style="text-align:center">'+
(x[1]===1?'1 match':x[1]+' matches')+' in '+x[0][1].toLowerCase()+' ›</button>';}).join('');
if(cur!=null){var s=$('list').querySelector('.row[data-i="'+cur+'"]');if(s)s.classList.add('sel');}
if(fsel){var nf=$('list').querySelector(fsel);if(nf)nf.focus({preventScroll:true});}
if(lockY==null&&scrollY!==y0)scrollTo(0,y0);
countBar();
// The videos' folder button, next to ?: until one is chosen, while a render has a video.
$('vidb').hidden=!!META.live||!!PICKED||!D.some(function(it){return it.renders.some(function(r){return r.video;});});}
// A capsule with no room on its right (the panel, the window's edge):
// opened to the left -- measured as the pointer or the focus comes.
function flipCap(e){var c=e.target.closest&&e.target.closest('.cell');if(!c)return;var lab=c.querySelector('.lab');if(!lab)return;
// In the panel itself: its right edge, the window's.
var r=c.getBoundingClientRect(),p=$('panel'),edge=cur!=null&&!p.hidden&&!document.body.classList.contains('panel-full')&&!p.contains(c)?p.getBoundingClientRect().left:innerWidth;
c.classList.toggle('flip',r.left+lab.scrollWidth+48>edge-8);}
document.addEventListener('mouseover',flipCap);document.addEventListener('focusin',flipCap);
// A finger: a first tap on a diamond stretches it into its words, a
// second one (or a tap elsewhere on the row) opens the file.
document.addEventListener('click',function(e){if(!touchPin.matches)return;var c=e.target.closest('#list .cell[tabindex]');
document.querySelectorAll('.cell.peek').forEach(function(x){if(x!==c)x.classList.remove('peek');});
if(!c||c.classList.contains('peek'))return;e.stopPropagation();e.preventDefault();flipCap({target:c});c.classList.add('peek');},true);
$('list').addEventListener('click',function(e){var t;
if(e.target.closest('[data-zoom]'))return;
if((t=e.target.closest('[data-other]')))return setTab(t.dataset.other);
if((t=e.target.closest('[data-new]'))){e.stopPropagation();return newFile(t.dataset.new);}
if((t=e.target.closest('[data-unplan]'))){rv.creates.splice(+t.dataset.unplan,1);save();render();return;}
if((t=e.target.closest('[data-gplay]'))){var gf=D.filter(function(x){return x.tab===state.tab&&x.group===t.dataset.gplay&&match(x)&&allVideos(x).length;})[0];
if(gf){openPanel(gf.i);openWatch(true);}return;}
if((t=e.target.closest('.row')))return openPanel(+t.dataset.i);
if((t=e.target.closest('.untracked'))){state.showHidden=t.dataset.hid==='1';if(!state.showHidden)state.untracked={};
try{localStorage.setItem(HID_KEY,state.showHidden?'1':'');}catch(e){}return render();}
if((t=e.target.closest('.g-h'))){state.open[state.tab+t.dataset.g]=t.parentNode.classList.contains('closed');render();}});
// A touch screen: a tap on a row or a group's name doesn't take the focus
// (iPad Safari gives it to anything with a tabindex) -- nothing focused
// in the list to lose when it's redrawn.
$('list').addEventListener('mousedown',function(e){if(touchPin.matches&&e.target.closest('.row,.g-h'))e.preventDefault();});
$('list').addEventListener('keydown',function(e){var r=e.target.closest('.row');
if(e.target.classList.contains('g-h')&&(e.key==='Enter'||e.key===' ')){e.preventDefault();e.target.click();return;}if(r&&(e.key==='Enter'||e.key===' ')){e.preventDefault();openPanel(+r.dataset.i);}});
// A compact list's column names: each department's first letter, more of
// it where an earlier one took it (Layout L, Lighting Li).
function initials(deps){var out={},seen={};deps.forEach(function(d){var n=1,c;do{c=d.charAt(0).toUpperCase()+d.slice(1,n);n++;}while(seen[c]&&n<=d.length);seen[c]=1;out[d]=c;});return out;}
// A new shot or asset, from the page: its name checked against the
// project's naming (META.naming), planned until the review is imported.
function newFile(g){var N=META.naming||{},shot=state.tab==='shot',SQ=N.sequence||{prefix:'sq',digits:3},SH=N.shot||{prefix:'sh',digits:3};
var deps=META.departments[shot?'shot':'asset']||[],dl=$('dlg'),pick={};deps.forEach(function(d){pick[d]=true;});
var pad=function(n,k){n=String(n);while(n.length<k)n='0'+n;return n;};
dl.innerHTML='<div class="dlg-in start" role="dialog" aria-modal="true" aria-labelledby="nf-t"><h3 id="nf-t">New '+(shot?'shot in '+esc(g):'asset')+'</h3>'+
(shot?'<div class="row3"><label>Shot<input id="nf-n" inputmode="numeric" placeholder="'+pad(90,SH.digits)+' (or '+pad(90,SH.digits)+'-'+pad(100,SH.digits)+')"></label><label>First frame<input id="nf-a" inputmode="numeric" value="'+esc(N.frame_start||1001)+'"></label><label>Last frame<input id="nf-b" inputmode="numeric" placeholder="optional"></label></div>':
'<label>Name<input id="nf-n" placeholder="'+esc(g)+'_…"></label>')+
'<label>Description<input id="nf-d" placeholder="What it is, for the team"></label>'+
'<div class="st-l">Departments required</div><div class="req" id="nf-deps">'+deps.map(function(d){return '<button type="button" data-dep="'+esc(d)+'" aria-pressed="true">'+esc(cap(d))+'</button>';}).join('')+'</div>'+
// Who it's for (the team): every department ticked assigned to them.
((META.team||[]).length?'<div class="st-l">Assigned to</div><div class="req" id="nf-who">'+META.team.map(function(p){return '<button type="button" data-who="'+esc(p)+'" aria-pressed="false">'+esc(p)+'</button>';}).join('')+'</div>':'')+
'<p class="st-w" id="nf-name"></p><p class="why" id="nf-why" hidden></p>'+
'<div class="acts"><button class="btn" id="nf-cancel">Cancel</button><button class="btn primary" id="nf-go">Plan it</button></div></div>';
dl.hidden=false;dl.onclick=function(e){if(e.target===dl)dl.hidden=true;};$('nf-n').focus();
// Its name as it'll be: sq030_sh090, ch_bob.
var label=function(){var v=$('nf-n').value.trim();if(shot){if(!/^\d+(-\d+)*$/.test(v))return '';return g+'_'+SH.prefix+v.split('-').map(function(x){return pad(+x,SH.digits);}).join('-');}
var nm=v.toLowerCase().replace(/ /g,'-').replace(/[^a-z0-9-]/g,'').replace(/-{2,}/g,'-').replace(/^-|-$/g,'');return nm?g+'_'+nm:'';};
var show=function(){var l=label();$('nf-name').textContent=l?'Will be '+l:'';};$('nf-n').addEventListener('input',show);
dl.querySelectorAll('[data-dep]').forEach(function(b){b.onclick=function(){pick[b.dataset.dep]=!pick[b.dataset.dep];b.setAttribute('aria-pressed',String(pick[b.dataset.dep]));};});
var who={};dl.querySelectorAll('[data-who]').forEach(function(b){b.onclick=function(){who[b.dataset.who]=!who[b.dataset.who];b.setAttribute('aria-pressed',String(who[b.dataset.who]));};});
$('nf-cancel').onclick=function(){dl.hidden=true;};
$('nf-go').onclick=function(){var l=label(),why=$('nf-why');why.hidden=true;
var no=function(t){why.hidden=false;why.textContent=t;};
if(!l)return no(shot?'A shot number, or several joined by "-" for a block.':'A name: letters, digits and "-".');
if(D.some(function(it){return it.name===l;})||rv.creates.some(function(c){return c.label===l;}))return no(l+' exists already.');
var a=+($('nf-a')||{}).value||null,b=+($('nf-b')||{}).value||null;if(shot&&a&&b&&b<a)return no('The last frame comes after the first.');
var c={kind:shot?'shot':'asset',tab:state.tab,group:g,label:l,description:$('nf-d').value.trim(),departments:deps.filter(function(d){return pick[d];})};
var ppl=Object.keys(who).filter(function(p){return who[p];});c.assignees={};if(ppl.length)c.departments.forEach(function(d){c.assignees[d]=ppl;});
if(shot){c.sequence=g.slice(SQ.prefix.length);c.shot=$('nf-n').value.trim();c.frame_start=a;c.frame_end=b;}else{c.prefix=g;c.name=l.slice(g.length+1);}
rv.creates.push(c);save();dl.hidden=true;render();countBar();toast(l+' planned: made when the review is imported.');};}
// A group's figures, with the review's when it moves them.
function gPct(g,all,done,val){if(done==null)return '<span class="g-pct faint">not tracked</span>';
return '<span class="g-pct">'+withReview({done:done,valid:val},reviewedOf(all.filter(function(it){return it.tracked||rv.files[it.file];}),(rv.creates||[]).filter(function(c){return c.tab===state.tab&&c.group===g;})))+dv(done,val)+'</span>';}
function setTab(t){state.tab=t;drawTabs();render();barFade();}
$('seg').addEventListener('click',function(e){var b=e.target.closest('button');if(b)setTab(b.dataset.tab);});
$('depf').addEventListener('change',function(){state.dep=this.value;this.classList.toggle('on',!!state.dep);render();});
pick($('depf'));
document.querySelectorAll('.chipf[data-f]').forEach(function(b){b.addEventListener('click',function(){
if(b.dataset.f==='me'&&!me()&&!state.f.me){toast('Me: your name first -- Review asks it.');return;}
state.f[b.dataset.f]=!state.f[b.dataset.f];b.setAttribute('aria-pressed',!!state.f[b.dataset.f]);render();
if(state.f[b.dataset.f])b.scrollIntoView({inline:'nearest',block:'nearest'});barFade();});});
// The filters' line: faded on a side where some are scrolled out of
// sight; the wheel, over it, scrolls it sideways.
var barIn=document.querySelector('.bar-in');
function barFade(){if(!barIn)return;var x=barIn.scrollLeft;barIn.classList.toggle('scrolled',x>4);barIn.classList.toggle('more',x+barIn.clientWidth<barIn.scrollWidth-4);}
barIn.addEventListener('scroll',barFade,{passive:true});addEventListener('resize',barFade);
barIn.addEventListener('wheel',function(e){if(barIn.scrollWidth<=barIn.clientWidth||Math.abs(e.deltaX)>Math.abs(e.deltaY))return;
e.preventDefault();barIn.scrollLeft+=e.deltaY;},{passive:false});
var bar=$('bar');
addEventListener('scroll',function(){$('hdr').classList.toggle('stuck',scrollY>4);},{passive:true});
// The header and the filters stay at the top; the column names under them.
function barHeight(){var r=document.documentElement.style;r.setProperty('--hdr-h',$('hdr').offsetHeight+'px');r.setProperty('--bar-h',bar.offsetHeight+'px');}
addEventListener('resize',barHeight);

/* ---------- find: filters the list, and jumps to any file ---------- */
var sugg=$('sugg'),hi=-1,found=[];
function suggest(){var q=state.q;hi=-1;if(!q){sugg.hidden=true;return;}
found=D.filter(function(it){return it.name.toLowerCase().indexOf(q)>=0;}).slice(0,8);
if(!found.length){sugg.hidden=true;return;}
sugg.innerHTML=found.map(function(it,n){return '<li><button type="button" role="option" data-n="'+n+'"><span>'+nameHtml(it)+'</span><small>'+
TABS.filter(function(t){return t[0]===it.tab;})[0][1]+(it.omit?' · '+(it.omit.state==='cancelled'?'cancelled':'on hold'):'')+'</small></button></li>';}).join('');sugg.hidden=false;}
// Not "pick": the page's selects' pick() (below, same scope) took the name.
function goTo(n){var it=found[n];if(!it)return;sugg.hidden=true;$('q').blur();jump(it);}
function jump(it){if(it.tab!==state.tab)setTab(it.tab);var k=state.tab+it.group;if(state.open[k]===false)state.open[k]=true;
if(hiddenFile(it))state.untracked[k]=true;render();openPanel(it.i);}
$('q').addEventListener('input',function(){state.q=this.value.trim().toLowerCase();render();suggest();});
$('q').addEventListener('focus',suggest);
$('q').addEventListener('keydown',function(e){var b=sugg.querySelectorAll('button');
if(e.key==='ArrowDown'||e.key==='ArrowUp'){if(sugg.hidden)return;e.preventDefault();hi=(hi+(e.key==='ArrowDown'?1:-1)+b.length)%b.length;
b.forEach(function(x,n){x.classList.toggle('hi',n===hi);});}
else if(e.key==='Enter'){e.preventDefault();goTo(hi<0?0:hi);}});
sugg.addEventListener('mousedown',function(e){e.preventDefault();});
sugg.addEventListener('click',function(e){var b=e.target.closest('button');if(b)goTo(+b.dataset.n);});
$('q').addEventListener('blur',function(){setTimeout(function(){sugg.hidden=true;},150);});

/* ---------- menus ---------- */
var MENUS=[['more','morepop'],['helpb','helppop'],['rv-more','rv-morepop']];
// A select drawn by the page: the system's own list takes no style. The
// select stays, hidden, holding the value -- its change event, its
// options, untouched; sync() after setting it from code.
function pick(sel){if(sel._pick)return sel._pick;
var w=document.createElement('span'),b=document.createElement('button'),m=document.createElement('div');
w.className='pick-w';b.type='button';b.className=sel.className+' pick';b.setAttribute('aria-haspopup','listbox');b.setAttribute('aria-expanded','false');
if(sel.getAttribute('aria-label'))b.setAttribute('aria-label',sel.getAttribute('aria-label'));
m.className='pick-pop';m.hidden=true;m.setAttribute('role','listbox');
sel.parentNode.insertBefore(w,sel);w.appendChild(sel);w.appendChild(b);sel.hidden=true;sel.tabIndex=-1;
// Its list in the body: a bar moved by a transform would carry it off.
m._button=b;document.body.appendChild(m);
function sync(){var o=sel.options[sel.selectedIndex];b.textContent=o?(o.dataset.short||o.textContent):'';
['on','need'].forEach(function(c){b.classList.toggle(c,sel.classList.contains(c));});}
b.onclick=function(e){e.stopPropagation();var open=!m.hidden;closeMenus();closePicks();if(open)return;
m.innerHTML=[].map.call(sel.options,function(o,i){return '<button type="button" role="option" data-i="'+i+'" aria-selected="'+(i===sel.selectedIndex)+'">'+esc(o.textContent)+'</button>';}).join('');
// Fixed, from the button: a scrolling bar or a panel would clip it.
var r=b.getBoundingClientRect(),up=r.top>innerHeight/2;m.style.left=Math.max(8,Math.min(r.left,innerWidth-Math.max(r.width,200)-8))+'px';m.style.minWidth=r.width+'px';
m.style.top=up?'':(r.bottom+6)+'px';m.style.bottom=up?(innerHeight-r.top+6)+'px':'';
// Focused for the keys -- never on a touch screen, where a focus in a
// fixed layer scrolls the page on an iPad (and that scroll closed it).
m.hidden=false;b.setAttribute('aria-expanded','true');pickOpenedAt=Date.now();touchHold();
if(!touchPin.matches)(m.querySelector('[aria-selected="true"]')||m.firstChild).focus({preventScroll:true});};
m.onclick=function(e){var o=e.target.closest('[data-i]');if(!o)return;e.stopPropagation();sel.selectedIndex=+o.dataset.i;closePicks();
sel.dispatchEvent(new Event('change'));sync();if(!touchPin.matches)b.focus({preventScroll:true});};
m.onkeydown=function(e){var f=[].slice.call(m.children),k=f.indexOf(document.activeElement);
if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();var n=f[Math.max(0,Math.min(f.length-1,k+(e.key==='ArrowDown'?1:-1)))];if(n)n.focus({preventScroll:true});}
else if(e.key==='Escape'||e.key==='Tab'){if(e.key==='Escape'){e.preventDefault();e.stopPropagation();}closePicks();b.focus({preventScroll:true});}};
sel._pick={sync:sync,button:b};sync();return sel._pick;}
function closePicks(){document.querySelectorAll('.pick-pop').forEach(function(m){if(!m.hidden){m.hidden=true;m._button.setAttribute('aria-expanded','false');}});touchHold();}
// A touch screen: the page under an open list or menu is held still
// (lockPage, 'pop') -- not put back after an iPad scrolled it, each
// putting back a jump of its own. The list or menu closes on a tap
// elsewhere, not on a scroll.
var touchPin=matchMedia('(pointer:coarse)');
function touchHold(){var on=touchPin.matches&&([].some.call(document.querySelectorAll('.pick-pop'),function(m){return !m.hidden;})||
MENUS.some(function(m){return !$(m[1]).hidden;}));lockPage('pop',on);}
function sync(id){var s=$(id);if(s&&s._pick)s._pick.sync();}
// Turned, a list closes (its place is gone); a touch screen's height
// moving (the keyboard, the browser's bars) leaves it open.
var pickW=innerWidth;
document.addEventListener('click',closePicks);addEventListener('resize',function(){if(touchPin.matches&&innerWidth===pickW)return;pickW=innerWidth;closePicks();});
// A scroll closes an open list -- not one the browser makes as it opens
// (iOS scrolls on a focus all the same, sometimes).
var pickOpenedAt=0;
document.addEventListener('scroll',function(e){if(touchPin.matches||Date.now()-pickOpenedAt<400)return;if(!(e.target.closest&&e.target.closest('.pick-pop')))closePicks();},true);
function closeMenus(){MENUS.forEach(function(m){$(m[1]).hidden=true;$(m[0]).setAttribute('aria-expanded','false');});touchHold();}
MENUS.forEach(function(m){$(m[0]).addEventListener('click',function(e){e.stopPropagation();var open=$(m[1]).hidden;closeMenus();
$(m[1]).hidden=!open;this.setAttribute('aria-expanded',open);touchHold();});});
document.addEventListener('click',function(e){if(!e.target.closest('.menu-pop'))closeMenus();});

/* ---------- pictures and videos ---------- */
var hov=$('hover'),fine=matchMedia('(hover:hover) and (pointer:fine)');
// With a mouse only: a tap is not a hover, the picture would stay open.
document.addEventListener('mouseover',function(e){var t=e.target.closest('.row .thumb[data-zoom]');if(!t||!fine.matches)return;
hov.onload=function(){var r=t.getBoundingClientRect(),w=hov.offsetWidth,h=hov.offsetHeight;
hov.style.left=Math.max(8,Math.min(r.left,innerWidth-w-8))+'px';hov.style.top=(r.bottom+8+h<innerHeight?r.bottom+8:Math.max(8,r.top-8-h))+'px';};
hov.src=img(D[t.dataset.zoom].thumb);hov.style.display='block';});
document.addEventListener('mouseout',function(e){if(e.target.closest('.thumb'))hov.style.display='none';});
// The page under it holds still, and is back where it was once closed:
// on an iPad, starting a video scrolled it to the top.
function lightbox(html,cap){lockPage('lb',true);
$('lb-in').innerHTML=html;$('lb-cap').innerHTML=cap||'';$('lb').hidden=false;hov.style.display='none';}
function closeLb(){var v=$('lb-in').querySelector('video');if(v)v.pause();$('lb').hidden=true;$('lb-in').innerHTML='';
lockPage('lb',false);}
$('lb').addEventListener('click',function(e){if(e.target===this||e.target.closest('#lb-x')||e.target.tagName==='IMG')closeLb();});
document.addEventListener('click',function(e){var t=e.target.closest('[data-zoom]');if(!t)return;e.stopPropagation();var it=D[t.dataset.zoom];
lightbox('<img alt="" src="'+img(it.thumb)+'">',esc(it.name));},true);
// A render's video in the zip made with the snapshot (same name), unzipped
// beside this page: <zip>/sq060/sq060_sh070_v012-stable_001.mp4,
// <zip>/assets/env/env_sol-lac_v002-stable_001.mp4 (lib/preview.py).
// A render's videos, as zipped with the snapshot (its name) and unzipped
// beside this page (lib/preview.py zip_latest_videos()): one per shot
// for shots rendered apart -- <zip>/sq060/sq060_sh070_v012-stable_001.mp4
// --, one for a block rendered whole or anything else --
// <zip>/sq060/sq060_sh070-090-100_..., <zip>/assets/env/env_sol-lac_....
// The videos the page can play, by their paths under renders/ (each
// render line's video, lib/snapshot.py snapshot_videos()): in the
// snapshot's videos folder or zip, or in a folder chosen here -- the
// project's renders/ too.
var VNAMES={},PICKED=null;((META.videos||{}).files||[]).forEach(function(n){VNAMES[n]=1;});
function videoSrc(name){var f=null,parts=name.split('/');
// The longest tail found: a folder above, or below, renders/ alike. Its
// file name alone only from a phone's pick (the same in every version).
if(PICKED)for(var k=0;k<parts.length&&!f;k++)if(k<parts.length-1||PICKED[' flat'])f=PICKED[parts.slice(k).join('/')];
if(f)return {src:f.url||(f.url=URL.createObjectURL(f)),from:'picked'};
// Then the copy that came with the page (videos/, or the zip unzipped),
// then the render itself, in the project, relative to the page.
var V=META.videos||{},path=encodeURI(name);
if(VNAMES[name])return {src:V.base+'/'+path,from:V.mode};
return V.local?{src:V.local+'/'+path,from:'local'}:null;}
// A render line's video, one or none.
// Live: another version picked to watch (PICKV, by file and line).
var PICKV={};
function videosOf(it,r){var o=(PICKV[it.file]||{})[r.shots||''];if(o)r=Object.assign({},r,{video:o.video,folder:o.folder,first:o.first});var s=r.video&&videoSrc(r.video);
return s?[{file:it.name,shot:r.shots,shots:r.shot_list,first:r.shot_list[0],start:r.first,folder:r.folder,src:s.src,from:s.from,name:r.video}]:[];}
// Choose the videos' folder: each video known by its path's every tail, so
// the folder's own name, or one above it, doesn't matter. A phone with no
// folder picker gives the videos themselves, known by their names.
function pickVideos(files){var n=0;PICKED={};
[].forEach.call(files,function(f){if(!/\.mp4$/i.test(f.name))return;n++;
var parts=(f.webkitRelativePath||f.name).split('/');
if(parts.length<2)PICKED[' flat']=1;
for(var k=0;k<parts.length;k++){var key=parts.slice(k).join('/');if(!PICKED[key])PICKED[key]=f;}});
if(!n){PICKED=null;toast('No .mp4 in that folder.');return;}
var found=D.reduce(function(c,it){return c+allVideos(it).filter(function(v){return v.src.slice(0,5)==='blob:';}).length;},0);
toast(plural(n,'video')+' in that folder, '+found+' for this snapshot.');
if(cur!=null)refresh();else render();}
// Chrome, Edge: the folder opened, not read -- only the videos this page
// needs are looked for, by their paths, so even the project's renders/
// (hundreds of thousands of frames) is quick. Each path tried as is,
// under renders/, then without its first folders (a folder inside).
function pickFolder(){window.showDirectoryPicker({id:'mp-videos'}).then(function(dir){
var names={};D.forEach(function(it){it.renders.forEach(function(r){if(r.video)names[r.video]=1;});});
names=Object.keys(names);var found={},n=0,next=0,left=names.length;
if(!left){toast('No render of this snapshot has a video.');return;}
toast('Looking for '+plural(left,'video')+'…');
function open(parts){var h=Promise.resolve(dir);parts.slice(0,-1).forEach(function(p){h=h.then(function(d){return d.getDirectoryHandle(p);});});
return h.then(function(d){return d.getFileHandle(parts[parts.length-1]);}).then(function(f){return f.getFile();});}
function look(name){var parts=name.split('/'),tries=[parts,['renders'].concat(parts)];
for(var k=1;k<parts.length-1;k++)tries.push(parts.slice(k));
var at=0;function one(){if(at>=tries.length)return null;return open(tries[at++]).catch(one);}return Promise.resolve().then(one);}
function work(){if(next>=names.length)return Promise.resolve();var name=names[next++];
return look(name).then(function(f){if(f){found[name]=f;n++;}}).then(work);}
var pool=[];for(var w=0;w<8;w++)pool.push(work());
Promise.all(pool).then(function(){if(!n){toast('None of this snapshot\'s videos in '+dir.name+'.');return;}
PICKED=found;toast(n+' of '+plural(names.length,'video')+' found in '+dir.name+'.');if(cur!=null)refresh();else render();});
}).catch(function(e){if(e&&e.name!=='AbortError')toast('That folder could not be read.');});}
// The pickers are file inputs, for the browsers without it.
document.addEventListener('click',function(e){var l=e.target.closest('label');
if(!l||!window.showDirectoryPicker||!l.querySelector('.vid-pick'))return;e.preventDefault();e.stopPropagation();closeMenus();pickFolder();},true);
function pickLink(text){return '<label class="vpick">'+esc(text)+'<input type="file" class="vid-pick" webkitdirectory multiple accept="video/mp4,.mp4"></label>';}
document.addEventListener('change',function(e){var t=e.target;if(!t.classList||!t.classList.contains('vid-pick'))return;
var files=t.files;closeMenus();if(files&&files.length)pickVideos(files);t.value='';});
// Every video of the file, in its shots' order.
function allVideos(it){var out=[];it.renders.forEach(function(r){out=out.concat(videosOf(it,r));});
var rank=function(v){var k=it.shots.indexOf(v.first);return k<0?0:k;};return out.sort(function(a,b){return rank(a)-rank(b);});}
/* ---------- the player: in the panel, or Watch large ---------- */
// One player (PL): its video element, mounted with its controls in the
// panel's media (compact) or in Watch large (wide) -- moved, not made
// again, so a video goes on playing from one to the other. Its timeline
// carries the file's notes at their frames: a retake's red diamond, a
// range's blue bar; a click goes there. See NOTES.md, "Snapshot page v3".
function clock(t){t=Math.floor(+t||0);return two(Math.floor(t/3600))+':'+two(Math.floor(t/60)%60)+':'+two(t%60);}
var FPS=+META.fps||0,PL=null,MUTE_KEY='mp-snapshot:muted',MUTED=false;try{MUTED=localStorage.getItem(MUTE_KEY)==='1';}catch(e){}
function setMuted(on){MUTED=on;if(PL)PL.el.muted=on;try{localStorage.setItem(MUTE_KEY,on?'1':'');}catch(e){}upd();}
function idxOf(t){return Math.max(0,Math.floor(t*FPS+1e-3));}
function frameNo(v,t){return v.start!=null?v.start+idxOf(t):idxOf(t)+1;}
function fLabel(v,n){return (v.start!=null?'f':'#')+n;}
// The frames tagged on a video: the file's open notes ("f12", "f12-30")
// on its shot or on none, then this review's lines ([f12], [f12-30]).
function marksOf(it,v){var out=[],own=function(sh){return !sh||!v.shots||v.shots.indexOf(sh)>=0||v.shots.indexOf(sh.replace(/^[a-z]+/i,''))>=0;};
it.notes.forEach(function(n){if(n.closed)return;var m=/f(\d+)(?:-(\d+))?/.exec(n.frames||'');if(!m||!own(n.shot))return;
out.push({a:+m[1],b:m[2]?+m[2]:null,rtk:n.type==='rtk'&&n.done===false,text:n.text,who:author(n),type:n.type,id:n.id});});
var e=peek(it),lines=[];Object.keys(e.deps).forEach(function(d){if(e.deps[d].text)lines=lines.concat(e.deps[d].text.split(NL).map(function(l){return [d,l];}));});
(e.text||'').split(NL).forEach(function(l){lines.push(['',l]);});
lines.forEach(function(x){var m=/\[f(\d+)(?:-(\d+))?\]/.exec(x[1]);if(!m)return;
out.push({a:+m[1],b:m[2]?+m[2]:null,rtk:!noteOnly(x[1]),text:x[1].replace(/\[[^\]]*\]\s*/g,''),who:'you',type:noteOnly(x[1])?'note':'rtk',mine:true});});
return out.sort(function(p,q){return p.a-q.a;});}
// The controls, by where the player is.
function plHtml(mode){var many=PL.list.length>1||mode==='wide';
return '<div class="pv-slot"></div><div class="pv-msg" hidden></div>'+
'<div class="tl"><div class="tl-in"><i class="tl-fill"></i><span class="tl-marks"></span><i class="tl-head"></i></div><input type="range" class="tl-r" min="0" max="1000" value="0" aria-label="Position"></div>'+
'<div class="pc">'+(mode==='wide'?'<button type="button" class="vb" data-pv="prevv" aria-label="Previous video" title="Previous video (←)">'+ico('rew')+'</button>':'')+
'<button type="button" class="vb" data-pv="-1" aria-label="Previous frame" title="Previous frame (,)">'+ico('fprev')+'</button>'+
'<button type="button" class="vb play pp" data-pv="pp" aria-label="Play">'+ico('play')+'</button>'+
'<button type="button" class="vb" data-pv="1" aria-label="Next frame" title="Next frame (.)">'+ico('fnext')+'</button>'+
(mode==='wide'?'<button type="button" class="vb" data-pv="nextv" aria-label="Next video" title="Next video (→)">'+ico('ff')+'</button>':'')+
// Sound: renders may carry it (docs/plan-1.2.md); muted or not, kept.
'<button type="button" class="vb snd" data-pv="mute" aria-label="Sound" title="Sound on / off (M)"></button>'+
'<span class="pf"><b class="pf-n">f–</b><span class="pf-r"></span></span><span class="pc-gap"></span>'+
(mode==='wide'?'<span class="strip"></span><button type="button" class="vb" data-pv="fs" aria-label="Full screen" title="Full screen">'+ico('fsin')+'</button>':
(many?'<span class="pv-at"></span>':'')+'<button type="button" class="btn wl-b" data-pv="wide" title="Watch large: the video, the departments and the notes at their frames">'+ico('fsin')+'Watch large</button>')+'</div>';}
// A list of videos into a host: the panel's (paused on its first frame,
// the thumbnail over it) or Watch large's.
function playerFor(it){var list=allVideos(it);if(!list.length)return null;
if(PL&&PL.it===it)return PL;
// The one before let go: paused, the browser would go on downloading it.
if(PL){PL.el.pause();PL.el.removeAttribute('src');PL.el.load();}
var el=document.createElement('video');el.playsInline=true;el.preload='metadata';el.muted=MUTED;if(it.thumb)el.poster=img(it.thumb);
PL={it:it,list:list,at:0,el:el,host:null,mode:'',marks:[]};wire(PL);load(0);return PL;}
function load(at){var v=PL.list[at];PL.at=at;PL.v=v;PL.marks=marksOf(PL.it,v);PL.el.src=v.src;}
function mount(host,mode){if(!PL||!host)return;PL.host=host;PL.mode=mode;host.innerHTML=plHtml(mode);host.querySelector('.pv-slot').appendChild(PL.el);
host.classList.toggle('pv-wide',mode==='wide');drawMarks();upd();if(mode==='wide')drawStrip();}
function q(c){return PL&&PL.host?PL.host.querySelector(c):null;}
function total(){return PL.el.duration&&FPS?Math.max(1,Math.round(PL.el.duration*FPS)):0;}
function drawMarks(){var box=q('.tl-marks'),n=total(),v=PL.v;if(!box)return;if(!n||v.start==null){box.innerHTML='';return;}
var at=function(f){return Math.max(0,Math.min(100,(f-v.start)/n*100));};
box.innerHTML=PL.marks.map(function(m){var tip=esc(fLabel(v,m.a)+(m.b?'-'+m.b:'')+' · '+m.text+(m.who?' · '+m.who:''));
return m.b?'<i class="tl-rg'+(m.mine?' mine':'')+'" data-seek="'+m.a+'" style="left:'+at(m.a)+'%;width:'+Math.max(.6,at(m.b)-at(m.a))+'%" title="'+tip+'"></i>':
'<i class="tl-mk'+(m.rtk?'':' nt')+(m.mine?' mine':'')+'" data-seek="'+m.a+'" style="left:'+at(m.a)+'%" title="'+tip+'"></i>';}).join('');}
// What changes as it plays: the frame, the head, ▶ / ❚❚, the "+ f12" of
// the retake boxes.
function upd(){if(!PL)return;var el=PL.el,v=PL.v,n=total(),f=frameNo(v,el.currentTime),pct2=el.duration?el.currentTime/el.duration*100:0;
var pn=q('.pf-n');if(pn)pn.textContent=fLabel(v,f);
var pr=q('.pf-r');if(pr)pr.textContent=(n?' / '+fLabel(v,v.start!=null?v.start+n-1:n):'')+(PL.mode==='wide'?' · '+clock(el.currentTime):'')+(FPS?' · '+FPS+' fps':'');
var hd=q('.tl-head');if(hd)hd.style.left=pct2+'%';var fl=q('.tl-fill');if(fl)fl.style.width=pct2+'%';
var rg=q('.tl-r');if(rg&&!PL.seeking)rg.value=Math.round(pct2*10);
var sn=q('.snd');if(sn&&sn.dataset.st!==String(el.muted)){sn.dataset.st=el.muted;sn.innerHTML=ico(el.muted?'mute':'sound');sn.setAttribute('aria-pressed',String(!el.muted));}
var pp=q('.pp');if(pp&&pp.dataset.st!==String(el.paused)){pp.dataset.st=el.paused;pp.innerHTML=ico(el.paused?'play':'pause');pp.setAttribute('aria-label',el.paused?'Play':'Pause');}
var at=q('.pv-at');if(at)at.textContent=(v.shot?v.shot+' · ':'')+(PL.at+1)+' / '+PL.list.length;
document.querySelectorAll('.addf').forEach(function(b){b.textContent='+ '+fLabel(v,f);});
document.querySelectorAll('.addf-l').forEach(function(b){b.textContent=fLabel(v,f);});
var wf=$('wl-f');if(wf)wf.textContent=fLabel(v,f);}
function seekFrame(f){if(!PL||!FPS)return;var v=PL.v,k=v.start!=null?f-v.start:f-1;PL.el.pause();PL.el.currentTime=Math.max(0,(k+.5)/FPS);upd();}
function stepFrame(n){if(!PL||!FPS)return;var el=PL.el;el.pause();var k=Math.max(0,idxOf(el.currentTime)+n),t=(k+.5)/FPS;if(el.duration)t=Math.min(t,el.duration-.5/FPS);el.currentTime=t;upd();}
function nextVideo(n){var at=PL.at+n;if(at>=0&&at<PL.list.length){load(at);PL.el.play();return true;}
// Past the file's last (Watch large): the group's next file with a video.
if(PL.mode!=='wide')return false;var g=groupFiles(),k=g.indexOf(PL.it)+n;while(g[k]&&!allVideos(g[k]).length)k+=n;
if(!g[k])return false;openPanel(g[k].i);var p=playerFor(g[k]);if(n<0)load(p.list.length-1);mount($('wl-pv'),'wide');wlSide();p.el.play();return true;}
function wire(P){var el=P.el;
['timeupdate','play','pause','seeked','loadedmetadata'].forEach(function(k){el.addEventListener(k,function(){if(PL!==P)return;if(k==='loadedmetadata')drawMarks();upd();});});
if(el.requestVideoFrameCallback){var tick=function(){if(PL===P&&!el.paused)upd();el.requestVideoFrameCallback(tick);};el.requestVideoFrameCallback(tick);}
el.addEventListener('ended',function(){if(PL===P&&!nextVideo(1))upd();});
el.addEventListener('click',function(){if(el.paused)el.play();else el.pause();});
el.addEventListener('error',function(){if(PL!==P)return;var v=P.v,V=META.videos;
// The copy missing (a Folder snapshot opened without its folder): the
// render itself, in the project, if this machine reaches it.
if(v.from!=='local'&&v.from!=='picked'&&V&&V.local){v.from='local';v.src=V.local+'/'+encodeURI(v.name);el.src=v.src;return;}
// Said in place of the picture, the controls left out.
var m=q('.pv-msg');if(!m)return;P.host.classList.add('pv-err');m.hidden=false;
m.innerHTML=(v.from==='picked'?'This browser can\'t play this video\'s format (on an iPad or in Safari: an H.265 video compiled by an older add-on — compile it again).':
v.from==='zip'?'Video not found. Unzip <code>'+esc(V.base)+'.zip</code> next to this page, into a folder of the same name.':
v.from==='folder'?'Video not found: no <code>'+esc(V.base)+'</code> folder '+(V.base.indexOf('../')===0?'beside this page\'s folder (keep the snapshots folder whole)':'next to this page')+' — or this browser can\'t play its format.':
'Video not found in the project\'s renders — away from the project, its videos come with the snapshot (Folder or Zip, when exporting) — or this browser can\'t play its format.')+
(v.from==='picked'?'':' '+pickLink('Choose the videos folder…'))+'<br><small>Looked for <code>'+esc(v.name)+'</code></small>';});}
// The controls' clicks and the timeline's drag, wherever it's mounted.
document.addEventListener('click',function(e){var b=e.target.closest('[data-pv],[data-seek]');if(!b||!PL||!PL.host||!(PL.host.contains(b)||b.closest('#wl,.panel')))return;
if(b.dataset.seek){e.preventDefault();var f=+b.dataset.seek;if(b.dataset.sh){var it=PL.it,vs=PL.list;for(var k=0;k<vs.length;k++)if(vs[k].shots&&vs[k].shots.indexOf(b.dataset.sh)>=0&&k!==PL.at){load(k);break;}}
if(PL.el.readyState>=1)seekFrame(f);else PL.el.addEventListener('loadedmetadata',function o(){PL.el.removeEventListener('loadedmetadata',o);seekFrame(f);});return;}
var a=b.dataset.pv,el=PL.el;
if(a==='pp'){if(el.paused)el.play();else el.pause();}else if(a==='-1'||a==='1')stepFrame(+a);
else if(a==='mute')setMuted(!el.muted);else if(a==='prevv')nextVideo(-1);else if(a==='nextv')nextVideo(1);else if(a==='wide')openWatch(false);
else if(a==='fs'){var f2=$('wl').requestFullscreen||$('wl').webkitRequestFullscreen;if(document.fullscreenElement)document.exitFullscreen();else if(f2)f2.call($('wl'));}});
document.addEventListener('input',function(e){if(!e.target.classList.contains('tl-r')||!PL)return;PL.seeking=true;var el=PL.el;if(el.duration){el.pause();el.currentTime=e.target.value/1000*el.duration;}});
document.addEventListener('change',function(e){if(e.target.classList.contains('tl-r')&&PL){PL.seeking=false;upd();}});
/* ---------- Watch large: the player the whole window, the departments
and the notes at their frames beside it ---------- */
var wlDep=null;
function groupFiles(){var it=PL?PL.it:D[cur];return D.filter(function(x){return x.tab===it.tab&&x.group===it.group&&match(x);});}
function openWatch(autoplay){if(cur==null)return;var p=playerFor(D[cur]);if(!p)return;$('wl').hidden=false;lockPage('wl',true);document.body.classList.add('wl-open');
mount($('wl-pv'),'wide');wlSide();if(autoplay)p.el.play();$('wl-x').focus({preventScroll:true});}
function closeWatch(){if($('wl').hidden)return;if(document.fullscreenElement)document.exitFullscreen();$('wl').hidden=true;lockPage('wl',false);document.body.classList.remove('wl-open');
if(PL)PL.el.pause();var pv=$('pv');if(pv&&PL&&PL.it===D[cur])mount(pv,'panel');}
// The group's files along the bottom: a click plays one.
function drawStrip(){var st=q('.strip');if(!st)return;var g=groupFiles();
st.innerHTML='<span class="st-l">'+esc(PL.it.group)+' · '+plural(g.length,PL.it.kind==='shot'?'shot':'file')+'</span>'+g.map(function(x){var has=allVideos(x).length;
return '<button type="button" class="st-i'+(x===PL.it?' on':'')+'" data-wlf="'+x.i+'"'+(has?'':' disabled')+' title="'+esc(x.name)+(has?'':' · no video')+'"><span class="frame">'+(x.thumb?'<img alt="" src="'+img(x.thumb)+'">':'')+'</span>'+esc(x.name.slice(x.group.length+1)||x.name)+'</button>';}).join('');
var on=st.querySelector('.on');if(on)on.scrollIntoView({block:'nearest',inline:'center'});}
// The right column: the departments with ✓ / ✕, the notes at their
// frames (a click goes there), a retake written at the frame shown.
function wlSide(){if($('wl').hidden||cur==null)return;var it=D[cur],e=peek(it),rv=reviewing(),v=PL&&PL.v;
var deps=depsOf(it.kind).filter(function(d){return d in it.states;});if(deps.indexOf(wlDep)<0)wlDep=deps.filter(function(d){return (e.deps[d]||{}).no;})[0]||deps[0]||'';
$('wl-t').innerHTML=nameHtml(it);$('wl-s').innerHTML=(v?'<span>'+ico('render')+esc(v.folder||'')+'</span>':'')+(it.to_check?'<span>'+ico('eye')+'to check</span>':'');
var h='<div class="wl-h"><h4>Departments</h4>'+(it.tracked?dv(it.done,it.valid):'')+'</div>'+deps.map(function(d){var vv=e.deps[d],s=it.states[d],r=rtkTag(it,d);
return '<div class="wl-d'+(d===wlDep?' on':'')+'"><button type="button" class="wl-dn" data-wld="'+esc(d)+'" title="Write its retakes here">'+
'<span class="cell"><span class="cap"><span class="g '+symCls(it,d)+'">'+(validAt(it,d)?'✓':'')+'</span></span>'+(r?r[0]:'')+'</span>'+esc(cap(d))+'</button>'+
(rv?'<span class="rvb" data-d="'+esc(d)+'"><button class="ok-b" aria-pressed="'+!!(vv&&vv.ok)+'"'+(asTeam()||!isDone(s)?' disabled':'')+' aria-label="Validate '+esc(d)+'">✓</button>'+
'<button class="ko-b" aria-pressed="'+!!(vv&&vv.no)+'" aria-label="Retake '+esc(d)+'">✕</button></span>':'')+'</div>';}).join('');
var marks=PL?PL.marks:[];h+='<div class="wl-h"><h4>Notes at frames</h4><small>click to jump</small></div>'+(marks.length?marks.map(function(m){
return '<button type="button" class="wl-n" data-seek="'+m.a+'"><span class="ft'+(m.b?' rg':m.rtk?'':' nt')+'">'+esc(fLabel(v,m.a)+(m.b?'-'+m.b:''))+'</span>'+esc(m.text)+(m.who?'<small> · '+esc(m.who)+'</small>':'')+'</button>';}).join(''):'<p class="faint">No note at a frame on this video.</p>');
if(rv&&wlDep)h+='<div class="wl-w"><label for="wl-ta">Retake at <span class="addf-l">'+(v?esc(fLabel(v,frameNo(v,PL.el.currentTime))):'')+'</span> on '+esc(cap(wlDep))+'</label>'+
'<textarea id="wl-ta" rows="3" placeholder="Write while watching — Enter adds it"></textarea></div>';
else if(!rv)h+='<p class="faint wl-hint">Review to validate, send back and write at a frame.</p>';
$('wl-side').innerHTML=h;}
$('wl-x').addEventListener('click',closeWatch);
$('wl').addEventListener('click',function(ev){var t;
if((t=ev.target.closest('[data-wlf]'))){var x=D[+t.dataset.wlf];openPanel(x.i);var p=playerFor(x);mount($('wl-pv'),'wide');wlSide();p.el.play();return;}
if((t=ev.target.closest('[data-wld]'))){wlDep=t.dataset.wld;wlSide();var ta=$('wl-ta');if(ta)ta.focus();return;}
if((t=ev.target.closest('.rvb button'))&&!t.disabled){var it=D[cur],d=t.parentNode.dataset.d,e=entry(it),v=e.deps[d];
if(t.classList.contains('ok-b')){if(v&&v.ok)delete e.deps[d];else e.deps[d]={ok:1};}else{if(v&&v.no)delete e.deps[d];else e.deps[d]={no:1,text:''};wlDep=d;}
refresh();}});
// Enter adds the line at the frame shown to the department's retake.
$('wl').addEventListener('keydown',function(ev){var t=ev.target;if(t.id!=='wl-ta'||ev.key!=='Enter'||ev.shiftKey)return;ev.preventDefault();ev.stopPropagation();
var txt=t.value.trim();if(!txt||!PL||!wlDep)return;var it=D[cur],e=entry(it),v=e.deps[wlDep],f=frameNo(PL.v,PL.el.currentTime);
if(!v||!v.no)v=e.deps[wlDep]={no:1,text:''};v.text=(v.text?v.text.replace(/\s+$/,'')+NL:'')+'[f'+f+'] '+txt;t.value='';
PL.marks=marksOf(it,PL.v);drawMarks();refresh();var ta=$('wl-ta');if(ta)ta.focus();});
// A sequence's files, each one's videos in its shots' order, one after the other.
function groupVideos(g){return D.filter(function(it){return it.tab===state.tab&&it.group===g&&match(it);}).reduce(function(out,it){return out.concat(allVideos(it));},[]);}

/* ---------- progress details ---------- */
function stats(){var S=META.schedule,exp=S?S.expected:null,h='';
var line=exp!=null?'<i class="x" style="left:'+exp*100+'%"></i>':'';
function bars(title,rows){rows=rows.filter(function(r){return r[1]!=null;});if(!rows.length)return '';
return '<div class="card"><h4>'+title+(exp!=null?'<small>| expected '+pct(exp)+'</small>':'')+'</h4><div class="hb">'+rows.map(function(r){
// [label, done, tip, validated]: the validated share over the done one, in
// violet, as the cards and the groups show it.
var v=META.role&&r[3]!=null;
return '<span title="'+esc(r[2]||'')+'">'+esc(r[0])+'</span><span class="track"><i class="f" style="width:'+r[1]*100+'%"></i>'+(v?'<i class="v" style="width:'+Math.min(r[3],r[1])*100+'%"></i>':'')+line+'</span><span class="n">'+pct(r[1])+(v?' <span class="vv" title="Validated by '+esc(META.role)+'">'+pct(r[3])+'</span>':'')+'</span>';}).join('')+'</div></div>';}
[['shot','Shots','By sequence','Sequence'],['asset','Assets','By prefix','Prefix']].forEach(function(s){
var items=D.filter(function(it){return it.kind===s[0]&&it.tracked;});if(!items.length)return;
var deps=depsOf(s[0]).filter(function(d){return items.some(function(it){return d in it.scores;});});
var groups={},order=[];items.forEach(function(it){if(!groups[it.group]){groups[it.group]=[];order.push(it.group);}groups[it.group].push(it);});
var dep=function(list,d){return avg(list.map(function(it){return d in it.scores?it.scores[d]:null;}));};
var grid='<div class="card hm-card"><h4>'+s[3]+' × department</h4><table class="hm"><thead><tr><th></th>'+deps.map(function(d){return '<th>'+esc(cap(d))+'</th>';}).join('')+
'</tr></thead><tbody>'+order.map(function(g){return '<tr><th>'+esc(g)+'</th>'+deps.map(function(d){var v=dep(groups[g],d);
return v==null?'<td class="na">–</td>':'<td style="background:color-mix(in srgb,var(--done) '+Math.round(6+v*44)+'%,var(--surface))" title="'+esc(g+', '+cap(d)+': '+pct(v))+'">'+pct(v)+'</td>';}).join('')+'</tr>';}).join('')+'</tbody></table></div>';
h+='<div class="st-sec"><h3>'+s[1]+'</h3><div class="st-grid">'+
bars(s[2],order.map(function(g){return [g,avg(groups[g].map(function(i){return i.done;})),plural(groups[g].length,'file'),avg(groups[g].map(function(i){return i.valid;}))];}))+
bars('By department',deps.map(function(d){return [cap(d),dep(items,d),'',avg(items.map(function(it){return d in it.states?(validNow(it,d)?1:0):null;}))];}))+grid+'</div></div>';});
return scheduleCard()+h+'<p class="weights">'+esc($('weights').textContent)+'</p>';}

/* ---------- a file's panel ---------- */
var cur=null,lastFocus=null,showClosed=false,showNotes=null,editing={};
function reviewing(){return document.body.classList.contains('reviewing');}
// The panel's notes (NOTES.md, "Notes in review"): a thread one line that
// opens (<details>), filtered and sorted from the notes' bar, one header
// for an author's notes of a day; what your review adds on top of its
// department, written in a box opened under the department's header --
// its lines kept as the review's text ([sh040] [f12-30] note: ...).
var NF={f:'open',s:'new'},NOPEN={},fsetOpen=false;
try{NF.f=localStorage.getItem('mp-snapshot:notes-filter')||'open';NF.s=localStorage.getItem('mp-snapshot:notes-sort')||'new';NOPEN=JSON.parse(localStorage.getItem('mp-snapshot:notes-open')||'{}')||{};}catch(err){}
function keep(k,v){try{localStorage.setItem('mp-snapshot:'+k,typeof v==='string'?v:JSON.stringify(v));}catch(err){}}
var MAC=/Mac|iP(hone|ad|od)/.test(navigator.platform||''),SHOT_RE=/^\s*\[([a-z]*\d+)\]\s*/i;
function who(n){var a=(n.author||'').trim();return a&&a.toLowerCase()!=='unknown'?a:'';}
function avatar(name){return '<span class="av'+(name?'':' none')+'" aria-hidden="true">'+esc((name||'').charAt(0).toUpperCase())+'</span>';}
// A note's shot ("010") as the block names it: sh010.
function shotName(it,s){if(!s)return '';var k=String(s).replace(/^\D+/,'');return it.shots.filter(function(x){return x.replace(/^\D+/,'')===k;})[0]||(/^\d+$/.test(s)?'sh'+s:s);}
// A thread's open retakes or todos: its first entry or a reply in it (a
// retake answered "still to redo" is one) -- what Mark fixed closes.
function openIds(n){return [n].concat(n.replies||[]).filter(function(x){return x.id&&(x.type==='rtk'||x.type==='todo')&&x.done===false;}).map(function(x){return x.id;});}
function isRtk(n){return openIds(n).length>0;}
function kindTag(n){var k=n.type==='rtk'?'rtk':n.type==='todo'?'todo':'note';
return '<span class="tp tp-'+(k==='rtk'?(n.team?'team':'role'):k)+'" title="'+(k==='rtk'?(n.team?'A retake from the team':'A retake from '+esc(n.role||'a validation role')):k==='todo'?'Something to do':'A note')+'">'+k.toUpperCase()+'</span>';}
function frameTag(f,sh){var m=/f(\d+)(?:-(\d+))?/.exec(f||'');return m?'<button type="button" class="tf" data-seek="'+m[1]+'"'+(sh?' data-sh="'+esc(sh)+'"':'')+' title="Go to this frame">'+esc(f)+'</button>':'';}
function shotTag(it,s){var n=shotName(it,s);return n?'<button type="button" class="ts" data-shotsel="'+esc(n)+'" title="This shot\'s picture">'+esc(n)+'</button>':'';}
// Its .blend only when not the file's current one: "v001".
function verOf(it,n){if(n.render)return '<span title="Written watching this render">▶ '+esc(n.render)+'</span>';
var nv=(n.version||'').match(/v\d+(?=\D*$)/),fc=it.wip_v||it.stable_v;return n.version&&(!nv||nv[0]!==fc)?'<span title="'+esc(n.version)+'">'+esc(nv?nv[0]:n.version)+'</span>':'';}
function canReply(n){return reviewing()&&n.id&&!n.closed;}
function fixable(n){return canReply(n)&&isRtk(n);}
function fixedMine(it,n){var f=peek(it).fixed||{},ids=openIds(n);return ids.length>0&&ids.every(function(id){return f[id];});}
function replyMine(it,n){var r=(peek(it).replies||{})[n.id];return r&&r.trim()?r:'';}
// Mine: written or answered by me, or fixed in my review.
function mineThread(it,n){var m=me(),is=function(x){return m&&who(x).toLowerCase()===m;};return !!(fixedMine(it,n)||replyMine(it,n)||is(n)||(n.replies||[]).some(is));}
// Open by default: a reply of the last 7 days, or one of mine; then as
// left (kept in this browser).
function isOpen(it,n){if(editing['r:'+n.id])return true;var k=it.file+'|'+n.id;if(k in NOPEN)return NOPEN[k];var m=me();
return !!replyMine(it,n)||(n.replies||[]).some(function(r){return Date.now()-new Date(r.date)<7*864e5||(m&&who(r).toLowerCase()===m);});}
function threadHtml(it,n,grouped){var rv=reviewing(),fx=fixedMine(it,n),dl=n.type==='todo'?'done':'fixed',last=(n.replies||[]).slice(-1)[0]||n,nr=(n.replies||[]).length+(replyMine(it,n)?1:0);
var meta=fx?'<span class="yt yt-fix">✓ '+dl.toUpperCase()+' · YOU</span>':n.closed?'<span class="clo">'+ico('check')+esc(who(last))+(who(last)&&last.date?' · ':'')+fmtDate(last.date)+'</span>':
[grouped?'':esc(who(n)),grouped?'':fmtDate(n.date),verOf(it,n)].filter(Boolean).join(' · ');
if(nr)meta+='<span class="rcn" title="'+nr+(nr>1?' replies':' reply')+'">'+ico('text')+nr+'</span>';
var acts=rv&&canReply(n)?'<span class="tacts"><button type="button" class="mini" data-reply="'+esc(n.id)+'" aria-label="Reply" title="Reply (R)">'+ico('text')+'</button>'+
(fixable(n)?'<button type="button" class="mini fix'+(fx?' on':'')+'" data-fix="'+esc(openIds(n).join(','))+'" aria-label="'+(fx?'Undo ':'Mark ')+dl+'" title="'+(fx?'Marked '+dl+' in your review: tap to undo':'Mark '+dl+': done when your review is imported')+'">'+ico(fx?'check':'box')+'</button>':'')+'</span>':'';
var body=(n.replies||[]).map(function(r){return replyRow(it,r);}).join('')+myReply(it,n)+replyForm(it,n)+
(rv&&canReply(n)&&!editing['r:'+n.id]?'<div class="ta"><button type="button" class="act" data-reply="'+esc(n.id)+'">'+ico('text')+'Reply</button>'+
(fixable(n)?'<button type="button" class="act fix'+(fx?' on':'')+'" data-fix="'+esc(openIds(n).join(','))+'">'+ico(fx?'check':'box')+(fx?'Undo '+dl:'Mark '+dl)+'</button>':'')+'</div>':'');
var t=(n.text||'').trim();
return '<details class="th'+(n.closed?' closed':'')+(fx?' fixed':'')+(body?'':' bare')+'" data-th="'+esc(n.id)+'"'+(isOpen(it,n)?' open':'')+'><summary><span class="tgs">'+kindTag(n)+frameTag(n.frames,n.shot)+shotTag(it,n.shot)+'</span>'+
'<span class="tx'+(t?'':' blank')+'">'+(t?esc(t):'(no text)')+'</span><span class="meta">'+meta+'</span>'+acts+'</summary>'+(body?'<div class="tb">'+body+'</div>':'')+'</details>';}
function replyRow(it,r){return '<div class="rpl">'+avatar(who(r))+'<div><div class="who">'+[who(r)?'<b>'+esc(who(r))+'</b>':'',fmtDate(r.date),verOf(it,r)?'on '+verOf(it,r):''].filter(Boolean).join(' · ')+'</div><div class="rx">'+esc(r.text)+'</div></div></div>';}
// Your reply, as it'll be sent: ↩ YOU red a retake (still to redo), outlined a remark.
function myReply(it,n){var r=replyMine(it,n);if(!r)return '';var nt=noteOnly(r);
return '<div class="rpl my-r">'+avatar(rv.author)+'<div><div class="who"><span class="yt '+(nt?'yt-note':'yt-ko')+'" title="'+(nt?'A remark in its thread':'A retake in its thread: still to redo, its department sent back')+'">↩ YOU</span> reply to '+esc(who(n)||'the thread')+
'<button type="button" class="mini" data-unreply="'+esc(n.id)+'" aria-label="Take your reply back" title="Take it back">✕</button></div><div class="rx">'+esc(r.split(NL).map(function(l){return l.trim()?readLine(l).text:'';}).join(NL).trim())+'</div></div></div>';}
function replyForm(it,n){var f=editing['r:'+n.id];if(!f)return '';var nt=f.kind==='note';
return '<div class="rpl rp-f">'+avatar(rv.author)+'<div class="rp-w"><textarea rows="1" class="rp-t'+(nt?' is-note':'')+'" data-r="'+esc(n.id)+'" placeholder="'+(nt?'A remark, for the team':'Still to redo: what?')+'">'+esc(f.text)+'</textarea>'+
'<div class="cf"><span class="tseg" role="group" aria-label="Kind"><button type="button" data-rkind="rtk" data-r="'+esc(n.id)+'" aria-pressed="'+!nt+'" title="Still to redo: its department sent back">Retake</button><button type="button" data-rkind="note" data-r="'+esc(n.id)+'" aria-pressed="'+nt+'" title="A remark, nothing sent back">Note</button></span><span class="sp"></span>'+
'<button type="button" class="btn ghost" data-rcancel="'+esc(n.id)+'">Cancel</button><button type="button" class="btn'+(nt?'':' ko')+'" data-rsend="'+esc(n.id)+'">Reply</button></div></div></div>';}
// An author's notes of a day, one after the other: one header, the lines
// without who and when (not when sorted by frame: the timeline's order).
function dayKey(iso){var d=new Date(iso);return isNaN(d)?String(iso):d.toDateString();}
function groupsHtml(it,list){if(NF.s==='frame')return list.map(function(n){return threadHtml(it,n);}).join('');var out=[];
list.forEach(function(n){var g=out[out.length-1];if(g&&g.a&&g.a===who(n)&&dayKey(g.n.date)===dayKey(n.date))g.items.push(n);else out.push({a:who(n),n:n,items:[n]});});
return out.map(function(g){if(g.items.length<2)return threadHtml(it,g.n);var c={};g.items.forEach(function(n){var k=n.type==='rtk'?'retake':n.type;c[k]=(c[k]||0)+1;});
return '<div class="ag">'+avatar(g.a)+'<b>'+esc(g.a)+'</b><span>'+[g.n.team?'team':esc(g.n.role||''),fmtDate(g.n.date),Object.keys(c).map(function(k){return plural(c[k],k);}).join(', ')].filter(Boolean).join(' · ')+'</span></div>'+
'<div class="ag-body">'+g.items.map(function(n){return threadHtml(it,n,true);}).join('')+'</div>';}).join('');}
function sortNotes(list){var s=list.slice(),t=function(n){return Date.parse(n.date)||0;};
if(NF.s==='frame'){var f=function(n){var m=/f(\d+)/.exec(n.frames||'');return m?+m[1]:Infinity;};s.sort(function(a,b){return f(a)-f(b)||t(b)-t(a);});}else s.sort(function(a,b){return t(b)-t(a);});return s;}
// Where a thread lives in the panel: under its first department the file
// tracks, else under Whole file -- one place each.
function homeOf(it,n){var d=n.deps.filter(function(x){return x in it.states;})[0];return d||'';}
function threadsOf(it,d){var all=it.notes.filter(function(n){return !n.approval&&homeOf(it,n)===d;});return {all:all,open:all.filter(function(n){return !n.closed;}),closed:all.filter(function(n){return n.closed;})};}
var closedOpen={};
// Open: the open threads, the closed ones at the end once "N closed" is
// clicked; All: every one in its place; Mine: mine (mineThread()).
function threadsHtml(it,d){var t=threadsOf(it,d),k=d||'·',list=NF.f==='all'?t.all:NF.f==='mine'?t.all.filter(function(n){return mineThread(it,n);}):t.open,h=groupsHtml(it,sortNotes(list));
if(NF.f==='open'&&t.closed.length&&closedOpen[k])h+='<div class="clos">'+sortNotes(t.closed).map(function(n){return threadHtml(it,n);}).join('')+closedLink(it,d)+'</div>';return h;}
function closedLink(it,d){var n=threadsOf(it,d).closed.length,k=d||'·';return n&&NF.f==='open'?'<button type="button" class="lk" data-closed="'+esc(k)+'">'+n+' closed'+(closedOpen[k]?' · hide':'')+'</button>':'';}
// A department's (or the whole file's) line: its state, what's open, the
// closed ones a link.
function summaryOf(it,d,first){var t=threadsOf(it,d),r=t.open.filter(isRtk).length,o=t.open.length-r;
return first.concat([r?'<b>'+r+' RTK</b>':'',o?plural(o,'note'):'',closedLink(it,d)]).filter(Boolean).join(' · ');}
// What your review adds there: a line each, × to take it back -- a retake
// with no text, sent back as it is.
function myLines(it,key){var e=peek(it),v=key==='gen'?null:e.deps[key.slice(2)];return key==='gen'?e.text||'':v&&(v.no||v.ok)?v.text||'':null;}
function mineHtml(it,key){var t=myLines(it,key);if(t==null)return '';var h=t.split(NL).map(function(l,i){if(!l.trim())return '';var p=readLine(l);
return '<div class="my'+(p.note?' n':'')+'"><span class="tgs">'+(p.note?'<span class="yt yt-note">NOTE · YOU</span>':'<span class="yt yt-ko">✕ YOU</span>')+(p.frames?frameTag('f'+p.frames[0]+(p.frames[1]!=null?'-'+p.frames[1]:'')):'')+shotTag(it,p.shot)+'</span>'+
'<span class="tx">'+esc(p.text)+'</span><button type="button" class="mini" data-rm="'+esc(key)+'|'+i+'" aria-label="Take it back" title="Take it back">✕</button></div>';}).join('');
var v=key==='gen'?null:peek(it).deps[key.slice(2)];
if(!h&&v&&v.no&&sent(v))h='<div class="my"><span class="tgs"><span class="yt yt-ko">✕ YOU</span></span><span class="tx blank">(no text) · sent back'+(it.ok[key.slice(2)]?', its validation withdrawn':'')+'</span><button type="button" class="mini" data-rm="'+esc(key)+'|-1" aria-label="Take it back" title="Take it back">✕</button></div>';
return h;}
// The box to write in, under its header: the block's shots (the line's
// [sh040], both ways), the frame shown, retake or note.
function composer(it,key){var c=editing.cmp,nt=c.kind==='note',sh=lineShot(it,c.text,c.at||0);
var f=PL&&PL.it===it&&PL.v?'<button type="button" class="pk f addf" data-addf title="The frame shown, after the line\'s shot -- again on another frame: a range">+ '+esc(fLabel(PL.v,frameNo(PL.v,PL.el.currentTime)))+'</button>':'';
return '<div class="cmp'+(nt?' is-note':'')+'" data-k="'+esc(key)+'"><div class="trow">'+(it.shots.length>1?'<span class="onl">On</span>'+[''].concat(it.shots).map(function(s){return '<button type="button" class="pk" data-pk="'+esc(s)+'" aria-pressed="'+(s===sh)+'">'+(s?esc(s):'All')+'</button>';}).join(''):'')+f+
'<span class="sp"></span><span class="tseg" role="group" aria-label="Kind"><button type="button" data-kind="rtk" aria-pressed="'+!nt+'" title="Something to fix: its department sent back">Retake</button><button type="button" data-kind="note" aria-pressed="'+nt+'" title="A remark: nothing sent back, no validation withdrawn">Note</button></span></div>'+
'<textarea rows="2" class="cmp-t" placeholder="'+(nt?'A remark, for the team':key==='gen'?'What to fix, on no department in particular?':'What to fix in '+esc(key.slice(2))+'?')+'">'+esc(c.text)+'</textarea>'+
'<div class="cf"><span class="hint"><kbd>'+(MAC?'⌘':'Ctrl')+' ↵</kbd> add · <kbd>Esc</kbd> cancel · one '+(nt?'note':'retake')+' per line</span><button type="button" class="btn ghost" data-cmp="cancel">Cancel</button><button type="button" class="btn'+(nt?'':' ko')+'" data-cmp="add">Add '+(nt?'note':'retake')+'</button></div></div>';}
function lineAt(v,pos){var s=v.lastIndexOf(NL,pos-1)+1,e=v.indexOf(NL,pos);return [s,e<0?v.length:e];}
function lineShot(it,v,pos){var b=lineAt(v,pos),m=SHOT_RE.exec(v.slice(b[0],b[1]));return m&&it.shots.indexOf(m[1].toLowerCase())>=0?m[1].toLowerCase():'';}
// A department's assign menu: me, the team, nobody -- the people ticked,
// open while you tick (closed by a click elsewhere, as the page's lists).
// One for the page.
var asgPop=null;
function asgMenu(it,d,b){if(asgPop&&!asgPop.hidden&&asgPop._d===d){closePicks();return;}closePicks();
if(!asgPop){asgPop=document.createElement('div');asgPop.className='pick-pop asg-pop';asgPop.setAttribute('role','menu');document.body.appendChild(asgPop);
asgPop.addEventListener('click',function(ev){var o=ev.target.closest('[data-p]');if(!o)return;ev.stopPropagation();var it2=D[cur],d2=asgPop._d,e2=entry(it2);
var now=people(it2,d2).slice(),was=((it2.assignees||{})[d2]||[]).slice(),p2=o.dataset.p;
if(!p2)now=[];else if(now.indexOf(p2)>=0)now.splice(now.indexOf(p2),1);else now.push(p2);
// Back to as it was: no change left to send.
if(now.slice().sort().join()===was.slice().sort().join())delete e2.assign[d2];else e2.assign[d2]=now;
// The panel redrawn puts its scroll back: a scroll, which closes the
// lists -- this one just ticked, kept open on its new button.
pickOpenedAt=Date.now();refresh();if(state.f.me)render();var nb=$('p-body').querySelector('[data-asgmenu="'+CSS.escape(d2)+'"]');if(nb){asgPop._button=nb;nb.setAttribute('aria-expanded','true');place(nb);}fill();});}
asgPop._d=d;asgPop._button=b;
function fill(){var pp=people(D[cur],asgPop._d),m=me(),team=(META.team||[]).concat(pp.filter(function(p){return (META.team||[]).indexOf(p)<0;}));
if(m)team=[m].concat(team.filter(function(p){return p!==m;}));
asgPop.innerHTML=team.map(function(p){var on=pp.indexOf(p)>=0;return '<button type="button" role="menuitemcheckbox" aria-checked="'+on+'" data-p="'+esc(p)+'">'+avatar(p)+(p===m?'Me · ':'')+esc(p)+'</button>';}).join('')+
'<button type="button" role="menuitemradio" class="nob" aria-checked="'+!pp.length+'" data-p="">Nobody</button>';}
fill();place(b);asgPop.hidden=false;b.setAttribute('aria-expanded','true');pickOpenedAt=Date.now();touchHold();}
function place(b){var r=b.getBoundingClientRect(),up=r.bottom>innerHeight*0.6;
asgPop.style.left=Math.max(8,Math.min(r.left,innerWidth-228))+'px';asgPop.style.top=up?'':(r.bottom+6)+'px';asgPop.style.bottom=up?(innerHeight-r.top+6)+'px':'';}
// Rendered but nothing to play: say why, quietly, and offer to look elsewhere.
function noVideo(it){if(!it.renders.some(function(r){return r.folder;})||allVideos(it).length)return '';
var why=PICKED?'Not in the videos folder chosen.':!META.videos?'No video came with this snapshot (Videos, when exporting).':
it.kind==='shot'?'The videos of '+it.group+' didn\'t come with this snapshot.':'The assets\' videos didn\'t come with this snapshot.';
return '<p class="novid">'+esc(why)+' '+pickLink(PICKED?'Choose another…':'Choose the videos folder…')+'</p>';}
function rendersHtml(it){
if(!it.renders.length)return '<span class="faint">'+(it.kind==='shot'?'Not rendered yet':'No render')+'</span>';
// A line per video -- per shot for shots rendered apart, the same folder
// name or not --, each its ▶ Play (the panel's button plays them all).
// A single shot or an asset: no shot column, the version where the file's name starts.
var one=it.shots.length<2&&!it.renders.some(function(r){return r.shots;});
// Columns: [shot] department · version · state · ▶ -- the main render's
// department bold, the others' last renders on lines of their own under
// it ("newer" when made after it); a farm job with no line: "farm".
var cell=function(c,t,tip){return '<span class="'+c+'"'+(tip?' title="'+esc(tip)+'"':'')+'>'+t+'</span>';};
return '<div class="renders'+(one?' one':'')+'">'+it.renders.map(function(r,n){var vs=videosOf(it,r),v=vs.length;
var st=r.status?'<span class="ss'+(r.status.state==='failed'?' fail':'')+'" title="'+esc(r.status.tip)+'">'+esc(r.status.text)+'</span>':'';
var main=(one?'':cell('sh',esc(r.shots||'all shots')))+cell('rd main',esc(r.department||(r.pending?'farm':'')))+
cell(r.behind?'rv bh':'rv',(r.behind?'⚠ ':'')+esc(r.folder||r.pending||'not rendered')+(r.behind?'<small>stable is '+esc(it.stable_v)+'</small>':''),r.behind?'Rendered from an older version than the last stable':'')+
cell('rs',st)+(v?'<button type="button" class="pl" data-play="'+n+'" title="'+esc(vs[0].name)+'">▶ Play</button>':'<span></span>');
return main+(r.others||[]).map(function(o){return (one?'':'<span></span>')+cell('rd',esc(o.department||'no department'))+cell('rv oth',esc(o.folder||''))+
cell('rs',o.newer?'<span class="ss newer" title="Rendered after the main one">newer</span>':'')+'<span></span>';}).join('');}).join('')+'</div>';}
// A department: one line -- its mark, name, what your review says, its
// state and what's open, who it's assigned to, ✓ / ✕ --, then the box to
// write in (✕), what you added, its threads.
function depHtml(it,d,rv){var s=it.states[d],e=peek(it),v=e.deps[d],o=it.ok[d],via=!v&&e.all&&isDone(s),key='d:'+d,cm=rv&&editing.cmp&&editing.cmp.key===key,w=capWords(it,d);
var okd=o?'<span class="ok'+(o.old?' old':'')+'" title="'+esc(o.tip)+'">✓ '+esc(o.role)+(o.old?' on '+esc(o.seen)+', to review again':'')+'</span>':'';
// To redo (an earlier stage changed): Still done says its work holds.
var redo=((it.flags||{})[d]||{}).to_redo,sd=redo&&rv?'<button type="button" class="sd-b" data-sync="'+esc(d)+'" aria-pressed="'+!!e.synced[d]+'" title="To redo: '+esc(redo)+'. Still done: the work done holds -- not a validation">'+ico('check')+'Still done</button>':'';
var yt=you(it,d)+(e.synced[d]?'<span class="you sd" title="Still done in your review: its work holds">✓ YOU</span>':'');
return '<div class="dep" data-dep="'+esc(d)+'"><div class="dh">'+cell(it,d,true,true)+'<span class="nm">'+esc(cap(d))+'</span>'+(yt?'<span class="inl">'+yt+'</span>':'')+
'<span class="sm">'+summaryOf(it,d,[esc(w[0].toLowerCase()),w[1]?esc(w[1]):'',okd])+'</span>'+sd+asgHtml(it,d,rv)+
(rv?'<span class="rvb" data-d="'+esc(d)+'"><button class="ok-b'+(via?' via':'')+'" aria-pressed="'+!!(v&&v.ok)+'"'+(asTeam()?' disabled title="As the team: no validation — a validation role validates"':isDone(s)?' title="Validate it as your role"':' disabled title="Not done: nothing to validate yet"')+
' aria-label="Validate '+esc(d)+'">✓</button><button class="ko-b'+(verdict(it,d)==='note'?' as-note':'')+'" aria-pressed="'+!!(cm||verdict(it,d)==='no'||verdict(it,d)==='note')+'" aria-expanded="'+!!cm+'" aria-label="Retake '+esc(d)+'" title="Retake or note: write it under the department">✕</button></span>':'')+'</div>'+
(cm?composer(it,key):'')+'<div class="ths">'+(rv?mineHtml(it,key):'')+threadsHtml(it,d)+'</div></div>';}
// Who it's assigned to: a pill (their initial, name); reviewing with a
// team, a button -- a dashed ring with nobody --, its menu the team to
// tick (asgMenu(), the review's assign action).
function asgHtml(it,d,rv){var pp=people(it,d),chg=d in peek(it).assign,btn=rv&&(META.team||[]).length,tip=pp.length?'Assigned to '+pp.join(', '):'Assign it to someone of the team';
var inner=pp.length?avatar(pp[0])+'<span class="an">'+esc(pp[0])+(pp.length>1?' +'+(pp.length-1):'')+'</span>':ico('user');
if(btn)return '<button type="button" class="asg'+(pp.length?' set':'')+(chg?' chg':'')+'" data-asgmenu="'+esc(d)+'" aria-haspopup="true" aria-label="'+esc(tip)+'" title="'+esc(tip)+'">'+inner+'</button>';
return pp.length?'<span class="asg set" title="'+esc(tip)+'">'+inner+'</span>':'';}
// Whole file, first: the retakes on no department -- ✕ one more, ✓ every
// done department (V).
function wholeHtml(it,rv){var e=peek(it),t=threadsOf(it,''),cm=rv&&editing.cmp&&editing.cmp.key==='gen',anyDone=Object.keys(it.states).some(function(d){return isDone(it.states[d]);});
if(!rv&&!t.all.length)return '';var gy=e.text.trim()||answered(it).gen?(noteOnly(e.text)&&!answered(it).gen?youNote():'<span class="you n" title="A retake on no department, in your review">✕ YOU</span>'):'';
if(e.all&&!asTeam())gy+='<span class="you" title="Every done department validated in your review">✓ YOU</span>';
return '<div class="dep whole"><div class="dh"><span class="wf" aria-hidden="true">'+ico('movie')+'</span><span class="nm">Whole file</span>'+(gy?'<span class="inl">'+gy+'</span>':'')+
'<span class="sm">'+(summaryOf(it,'',[])?summaryOf(it,'',[])+' · ':'')+'on no department</span>'+
(rv?'<span class="rvb"><button class="ok-b" id="allok" aria-pressed="'+!!e.all+'"'+(asTeam()?' disabled title="As the team: no validation"':anyDone?' title="All done: validate every done department (V)"':' disabled title="Nothing done to validate yet"')+' aria-label="Validate every done department">✓</button>'+
'<button class="ko-b" id="add-gen" aria-pressed="'+!!(cm||e.text.trim())+'" aria-expanded="'+!!cm+'" aria-label="A retake on no department" title="A retake or a note on no department (X)">✕</button></span>':'')+'</div>'+
(cm?composer(it,'gen'):'')+'<div class="ths">'+(rv?mineHtml(it,'gen'):'')+threadsHtml(it,'')+'</div></div>';}
// The notes' bar, once per file: Open / All / Mine, Newest / By frame --
// the page's, kept in this browser.
function notesBar(it){var all=it.notes.filter(function(n){return !n.approval;}),c=function(t){return (t||'').split(NL).filter(function(l){return l.trim();}).length;},e=peek(it),mine=c(e.text);
Object.keys(e.deps).forEach(function(d){mine+=c(e.deps[d].text);});if(!all.length&&!mine)return '';
var b=function(f,l,n){return '<button type="button" data-nf="'+f+'" aria-pressed="'+(NF.f===f)+'">'+l+' <b>'+n+'</b></button>';};
return '<div class="nbar"><div class="nseg" role="group" aria-label="Which notes">'+b('open','Open',all.filter(function(n){return !n.closed;}).length+mine)+b('all','All',all.length+mine)+b('mine','Mine',all.filter(function(n){return mineThread(it,n);}).length+mine)+'</div><span class="sp"></span>'+
'<div class="nseg" role="group" aria-label="Order"><button type="button" data-ns="new" aria-pressed="'+(NF.s!=='frame')+'">Newest</button><button type="button" data-ns="frame" aria-pressed="'+(NF.s==='frame')+'">'+ico('range')+'By frame</button></div></div>';}
// Reviewing, the file itself, folded at the end: its departments
// required, set aside or not.
function fileSettings(it,e){var all=depsOf(it.kind),om=e.omit||{state:(it.omit||{}).state||'',reason:(it.omit||{}).reason||''},n=all.filter(function(d){return d in e.req?e.req[d]:d in it.states;}).length,chg=Object.keys(e.req).length||omitChanged(it,e);
var h='<div class="fset'+(fsetOpen?' on':'')+'"><button type="button" class="fset-b" id="fset" aria-expanded="'+fsetOpen+'">'+ico('settings')+'<b>File settings</b>'+(chg?'<span class="inl"><span class="you nt">✎ YOU</span></span>':'')+
'<span class="sm">sent with the review · '+n+' required · '+(om.state==='on_hold'?'on hold':om.state==='cancelled'?'cancelled':'active')+'</span><span class="chev" aria-hidden="true">▸</span></button>';
if(fsetOpen)h+='<div class="fset-c"><div class="st-l">Departments required</div><div class="req">'+
all.map(function(d){var on=d in e.req?e.req[d]:d in it.states;return '<button type="button" data-req="'+esc(d)+'" aria-pressed="'+on+'"'+(d in e.req?' class="chg"':'')+'>'+esc(cap(d))+'</button>';}).join('')+'</div>'+
'<div class="st-l">Set aside</div><div class="segb om">'+[['','Active'],['on_hold','On hold'],['cancelled','Cancelled']].map(function(o){return '<button type="button" data-omit="'+o[0]+'" aria-pressed="'+(om.state===o[0])+'">'+o[1]+'</button>';}).join('')+'</div>'+
(om.state?'<input class="om-why" id="om-why" placeholder="Why (for the team)" value="'+esc(om.reason||'')+'">':'')+'</div>';
return h+'</div>';}
function openPanel(i){
// The notes' fold is the page's, not a file's: kept from one file to the
// next, back to its default (open, folded in review) when review starts or ends.
var it=D[i],same=cur===i;if(!same){showClosed=false;editing={};}cur=i;$('p-open').hidden=true;
// A tablet: the file the whole screen -- a panel over the list hid its columns.
if(tablet.matches&&!document.body.classList.contains('panel-full'))setFull(true,false);if(!lastFocus)lastFocus=document.activeElement;
var rv=reviewing(),e=peek(it);if(showNotes===null)showNotes=!rv;
$('p-title').innerHTML=nameHtml(it);$('p-blend').hidden=!META.live;var nv=allVideos(it).length;$('p-play').hidden=true;$('p-play').title=nv>1?'Play the '+nv+' shots in a row':'Play the render';
$('p-sub').textContent=[it.kind==='shot'?'Shot':it.root==='library'?'Library':'Asset',it.versions,it.shots.length>1?plural(it.shots.length,'shot'):''].filter(Boolean).join(' · ');
// First what it is and how far along, big; then its departments; the
// rest after, quieter.
// Done and validated, as everywhere: the double bar, "84 % · 0 %".
$('p-kpi').innerHTML=kpiHtml(it);
$('p-flags').innerHTML=flags(it);
var deps=depsOf(it.kind).filter(function(d){return d in it.states;});
var nvid=allVideos(it).length;
var h='<div class="p-media">'+(nvid?'<div class="pv" id="pv"></div>':it.thumb?'<button type="button" class="big" id="bigb" aria-label="Full size"><img id="bigimg" alt="" src="'+img(it.thumb)+'"></button>':'<span class="thumb none"><span class="frame"></span></span>')+
// Each shot's picture; the block's own only when it's none of theirs (its
// first shot's, most often: the same picture twice).
(it.shot_thumbs.length?'<div class="shotsel">'+(it.thumb&&!it.shot_thumbs.some(function(s){return s[1]===it.thumb;})?[['whole block',it.thumb]]:[]).concat(it.shot_thumbs).map(function(s){
return '<button type="button" data-src="'+(s[1]?img(s[1]):'')+'" aria-pressed="'+(!!s[1]&&s[1]===it.thumb)+'"'+(s[1]?'':' disabled')+'><span class="frame">'+(s[1]?'<img alt="" src="'+img(s[1])+'">':'')+'</span>'+esc(s[0])+(s[1]?'':' · not rendered')+'</button>';}).join('')+'</div>':'')+
(function(){var n=allVideos(it).length;
// The file's videos: ▶ in the header. Reviewing, Last render is folded:
// each shot's video stays one tap away here.
return (n>1?'<div class="vlist review-only">'+it.renders.map(function(r,k){return [r,k];}).filter(function(x){return videosOf(it,x[0]).length;})
.sort(function(a,b){return it.shots.indexOf(a[0].shot_list[0])-it.shots.indexOf(b[0].shot_list[0]);})
.map(function(x){return '<button type="button" class="pl" data-play="'+x[1]+'">▶ '+esc(x[0].shots||'all shots')+'</button>';}).join('')+'</div>':'');})()+versionsHtml(it)+'</div>';
// The description first: what the file is.
if(rv&&(editing.desc||e.desc!==null))h+='<div class="p-block"><h4>Description<span class="h-sub">sent with the review</span></h4><textarea rows="1" id="desc-t" placeholder="What this file is, for the team">'+esc(e.desc!==null?e.desc:it.desc)+'</textarea></div>';
else{if(it.desc)h+='<p class="desc">'+esc(it.desc)+'</p>';
if(rv)h+='<button type="button" class="desc-edit" id="add-desc">✎ '+(it.desc?'Edit the description':'Add a description')+'</button>';}
// The notes' bar, Whole file (its retakes concern every department),
// the departments; reviewing, the file's settings folded at the end.
h+=notesBar(it)+'<div class="p-block major">'+wholeHtml(it,rv)+(deps.length?deps.map(function(d){return depHtml(it,d,rv);}).join(''):'<p class="faint">No department tracked on this file.</p>')+'</div>';
if(it.live)h+=checksHtml(it)+linksHtml(it);
if(rv)h+=fileSettings(it,e);
// Where it comes from: at the bottom, out of the way while reviewing.
h+='<dl class="view-only facts"><dt>Last render</dt><dd>'+rendersHtml(it)+noVideo(it)+'</dd><dt>Blender file</dt><dd class="fileline">'+esc(it.file)+'.blend</dd></dl>';
// The player's video kept as the panel is redrawn (moved, not made again).
if(PL&&PL.host&&PL.mode==='panel'&&PL.it===it)document.body.appendChild(PL.el).hidden=true;
$('p-body').innerHTML=h;$('p-body').querySelectorAll('textarea').forEach(grow);
// Another file: its content fades in (not at each redraw of the same one).
if(!same){var pb=$('p-body');pb.classList.remove('swap');void pb.offsetWidth;pb.classList.add('swap');}
if(nvid){if(PL&&PL.it!==it&&$('wl').hidden){PL.el.pause();PL=null;}
if($('wl').hidden){playerFor(it);PL.el.hidden=false;mount($('pv'),'panel');}else $('pv').innerHTML='<div class="pv-away">In Watch large</div>';}
document.body.classList.add('panel-open');lockPage('panel',phone.matches||document.body.classList.contains('panel-full'));fitBar();var p=$('panel');p.hidden=false;
requestAnimationFrame(function(){p.classList.add('on');$('scrim').classList.add('on');});
var pos=visible.indexOf(i);$('p-prev').disabled=$('m-prev').disabled=pos<=0;$('p-next').disabled=$('m-next').disabled=pos<0||pos>=visible.length-1;
document.querySelectorAll('.row.sel').forEach(function(x){x.classList.remove('sel');});
var s=$('list').querySelector('.row[data-i="'+i+'"]');if(s){s.classList.add('sel');
// Beside the list: the file shown stays in sight as ← → go through it
// (at once on a touch screen: iOS's smooth scroll went up, then down) --
// another file only: a tap in the panel (✓, ✕...) redraws it, and the
// list stays where it was read.
var r=s.getBoundingClientRect(),top=bar.getBoundingClientRect().bottom+40;if(!same&&lockY==null&&!phone.matches&&(r.top<top||r.bottom>innerHeight))scrollBy({top:r.top-top-(innerHeight-top)/3,behavior:touchPin.matches?'auto':'smooth'});}
p.setAttribute('aria-modal',phone.matches||document.body.classList.contains('panel-full')?'true':'false');
try{history.replaceState(null,'','#'+encodeURIComponent(it.name));}catch(err){}}
function refresh(){var y=$('p-body').scrollTop;openPanel(cur);$('p-body').scrollTop=y;renderRow(cur);save();fieldLeft();
if(PL&&PL.it===D[cur]){PL.marks=marksOf(PL.it,PL.v);drawMarks();}if(!$('wl').hidden)wlSide();}
// The page held still (fixed where it is, put back once let go): under
// the full-screen panel (a phone, panel-full), the lightbox, and on a
// touch screen an open list or menu, the dialog, a field being written
// in -- a drag on the panel's header, a field brought into view, a video
// started, scrolled it on iOS. Each reason holds it ({key: 1}), the last
// one let go puts it back.
var lockY=null,holds={};
function lockPage(k,on){if(on)holds[k]=1;else delete holds[k];var b=document.body.style,any=Object.keys(holds).length>0;
if(any&&lockY==null){lockY=scrollY;b.position='fixed';b.top=-lockY+'px';b.left=b.right='0';}
else if(!any&&lockY!=null){b.position=b.top=b.left=b.right='';scrollTo(0,lockY);lockY=null;}}
// Touch: a field in a fixed layer (panel, review bar, dialog) brings the
// keyboard up and iOS scrolls the page to it, then back as it goes:
// held from the field's focus (before iOS moves anything) until the
// keyboard is gone -- a scroll iOS makes then has nothing to move.
function inField(){var f=document.activeElement;return !!(f&&f.matches&&f.matches('input,textarea,select')&&f.closest('.panel,.rbar,.dlg')&&!f.closest('[hidden]'));}
var fieldT=null;
function fieldLeft(){if(!holds.field)return;clearTimeout(fieldT);fieldT=setTimeout(function(){if(!inField())lockPage('field',false);},450);}
// Touch, writing in the panel: the keyboard takes half the screen, the
// review bar and Previous / Next step aside for the text.
var coarse=matchMedia('(pointer:coarse)');
document.addEventListener('focusin',function(e){if(coarse.matches&&e.target.matches('input,textarea')&&e.target.closest('.panel'))document.body.classList.add('typing');});
document.addEventListener('focusout',function(){setTimeout(function(){var f=document.activeElement;
if(!(f&&f.matches&&f.matches('input,textarea')&&f.closest('.panel'))&&document.body.classList.contains('typing')){document.body.classList.remove('typing');fitBar();}},60);});
document.addEventListener('focusin',function(){if(coarse.matches&&inField()){clearTimeout(fieldT);lockPage('field',true);}});
document.addEventListener('focusout',function(){setTimeout(fieldLeft,60);});
// The dialog: the page under it held still on a touch screen; closed, a
// field of it is left.
new MutationObserver(function(){lockPage('dlg',coarse.matches&&!$('dlg').hidden);fieldLeft();}).observe($('dlg'),{attributes:true,attributeFilter:['hidden']});
// The keyboard up (a touch screen, a field of the panel or the dialog):
// the page held, iOS no longer scrolls it to the field -- the panel and
// the dialog are fitted to what the keyboard leaves (body.kb, --vv-h,
// --vv-top: the visual viewport), and the panel scrolls the field into
// that room, as it grows too.
var VV=window.visualViewport;
function revealField(){var f=document.activeElement,c=f&&f.closest&&f.closest('.p-body');if(!c||!inField())return;
var r=f.getBoundingClientRect(),cr=c.getBoundingClientRect();
if(r.bottom>cr.bottom-8)c.scrollTop+=Math.min(r.bottom-cr.bottom+16,r.top-cr.top-8);else if(r.top<cr.top+8)c.scrollTop-=cr.top-r.top+16;}
function fitKb(){if(!VV)return;var b=document.body,on=coarse.matches&&inField()&&VV.height<document.documentElement.clientHeight-80;
b.classList.toggle('kb',on);if(!on)return;var st=document.documentElement.style;
st.setProperty('--vv-h',Math.round(VV.height)+'px');st.setProperty('--vv-top',Math.round(VV.offsetTop)+'px');revealField();}
if(VV){VV.addEventListener('resize',fitKb);VV.addEventListener('scroll',fitKb);}
document.addEventListener('focusin',function(){if(!coarse.matches)return;fitKb();setTimeout(fitKb,350);});
document.addEventListener('focusout',function(){setTimeout(fitKb,80);});
$('p-body').addEventListener('input',function(){if(document.body.classList.contains('kb'))revealField();});
// The last file shown: the window edge's tab brings it back.
var lastShown=null;
function closePanel(){if(cur==null)return;closeWatch();if(PL)PL.el.pause();lastShown=cur;$('p-open').hidden=false;cur=null;
if(tablet.matches){var pf=false;try{pf=!!localStorage.getItem(PF_KEY);}catch(e){}setFull(pf,false);}
// A field of it left for good: hidden with the panel, iOS kept its focus
// (no focusout), the page stayed held -- nothing scrolled or answered.
var f=document.activeElement;if(f&&f.closest&&f.closest('.panel')&&f.blur)f.blur();clearTimeout(fieldT);lockPage('field',false);
document.body.classList.remove('panel-open','typing','kb');lockPage('panel',false);fitBar();var p=$('panel');p.classList.remove('on');$('scrim').classList.remove('on');
setTimeout(function(){if(cur==null)p.hidden=true;},220);document.querySelectorAll('.row.sel').forEach(function(x){x.classList.remove('sel');});
try{history.replaceState(null,'',location.pathname+location.search);}catch(err){}
if(lastFocus)lastFocus.focus({preventScroll:true});lastFocus=null;}
function step(n){var pos=visible.indexOf(cur);if(pos<0)return;var j=visible[pos+n];if(j!=null){openPanel(j);$('p-body').scrollTop=0;}}
$('p-close').addEventListener('click',closePanel);$('p-tab').addEventListener('click',closePanel);
$('p-open').addEventListener('click',function(){if(lastShown!=null)openPanel(lastShown);});$('scrim').addEventListener('click',closePanel);
$('p-prev').addEventListener('click',function(){step(-1);});$('p-next').addEventListener('click',function(){step(1);});
$('m-prev').addEventListener('click',function(){step(-1);});$('m-next').addEventListener('click',function(){step(1);});
$('p-play').addEventListener('click',function(){if(cur!=null)openWatch(true);});
$('p-blend').addEventListener('click',function(){if(cur!=null&&META.live)liveOpen(D[cur].file);});
$('p-link').addEventListener('click',function(){var u=location.href;
var ok=function(){toast('Link copied: it opens this file, once this page is where the link points.');};
if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(u).then(ok,function(){prompt('Link to this file',u);});else prompt('Link to this file',u);});
// A touch screen: swipe down from the panel's header to close (not from
// its text: scrolling it back up closed it), sideways for the next /
// previous file (not on the shots' strip nor in a field, which scroll or
// select).
var t0=null;$('panel').addEventListener('touchstart',function(e){var t=e.touches[0];
t0=e.target.closest('textarea,input,select,.shotsel')?null:{x:t.clientX,y:t.clientY,top:!!e.target.closest('.p-head')};},{passive:true});
$('panel').addEventListener('touchend',function(e){if(!t0)return;var t=e.changedTouches[0],dx=t.clientX-t0.x,dy=t.clientY-t0.y;
if(Math.abs(dx)>70&&Math.abs(dx)>2*Math.abs(dy))step(dx<0?1:-1);else if(t0.top&&dy>90&&dy>2*Math.abs(dx))closePanel();t0=null;});
// Focus stays in the open panel.
// The panel over the whole screen: a phone, a tablet upright.
var phone=matchMedia('(max-width:900px)'),tablet=matchMedia('(pointer:coarse) and (min-width:641px)');
// The panel's width, dragged by its left edge -- kept by this browser.
var PW_KEY='mp-snapshot:panel-width',PW_DEF=540;
function maxWidth(){return Math.min(innerWidth-360,innerWidth*0.8);}
function setWidth(w,keep){w=Math.round(Math.max(380,Math.min(w,maxWidth())));
document.documentElement.style.setProperty('--pw',w+'px');if(keep)try{localStorage.setItem(PW_KEY,String(w));}catch(e){}if(typeof fitBar==='function')fitBar();return w;}
// Dragged past its widest, the whole page (an iPad upright: the list is
// too narrow beside it); dragged back, beside the list. Kept too.
var PF_KEY='mp-snapshot:panel-full';
function setFull(on,keep){var b=document.body,was=b.classList.contains('panel-full');b.classList.toggle('panel-full',on);
if(keep)try{localStorage.setItem(PF_KEY,on?'1':'');}catch(e){}
if(on!==was&&cur!=null){lockPage('panel',on||phone.matches);
$('panel').setAttribute('aria-modal',on||phone.matches?'true':'false');}
if(typeof fitBar==='function')fitBar();}
function dragTo(w,keep){if(w>maxWidth()+60)setFull(true,keep);else{setFull(false,keep);setWidth(w,keep);}}
try{var pw=+localStorage.getItem(PW_KEY);if(pw)setWidth(pw);if(localStorage.getItem(PF_KEY))setFull(true);}catch(e){}
var rz=$('p-resize');
rz.addEventListener('pointerdown',function(e){e.preventDefault();rz.setPointerCapture(e.pointerId);document.body.classList.add('resizing');});
rz.addEventListener('pointermove',function(e){if(document.body.classList.contains('resizing'))dragTo(innerWidth-e.clientX,false);});
rz.addEventListener('pointerup',function(e){if(!document.body.classList.contains('resizing'))return;document.body.classList.remove('resizing');dragTo(innerWidth-e.clientX,true);});
rz.addEventListener('dblclick',function(){setFull(false,true);setWidth(PW_DEF,true);});
rz.addEventListener('keydown',function(e){if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return;e.preventDefault();e.stopPropagation();
var full=document.body.classList.contains('panel-full');
dragTo(full?(e.key==='ArrowLeft'?innerWidth:maxWidth()):$('panel').offsetWidth+(e.key==='ArrowLeft'?40:-40),true);});
$('panel').addEventListener('keydown',function(e){if(e.key!=='Tab'||!(phone.matches||document.body.classList.contains('panel-full')))return;var f=[].filter.call($('panel').querySelectorAll('button,textarea,[tabindex]'),function(x){return !x.disabled&&x.offsetParent;});
if(!f.length)return;var a=f[0],z=f[f.length-1];if(e.shiftKey&&document.activeElement===a){z.focus({preventScroll:true});e.preventDefault();}else if(!e.shiftKey&&document.activeElement===z){a.focus({preventScroll:true});e.preventDefault();}});
var FS=window.CSS&&CSS.supports('field-sizing','content');
// Measured at height auto, the panel's scroll put back in the same go:
// shrunk for a moment, the panel's text moved, and iOS scrolled again to
// the caret at each key (Safari has no field-sizing).
function grow(t){if(FS||!t)return;var p=t.closest('.p-body'),y=p?p.scrollTop:0;t.style.height='auto';t.style.height=Math.min(t.scrollHeight+2,innerHeight*.5)+'px';if(p&&p.scrollTop!==y)p.scrollTop=y;}
// The box to write in: one at a time, opened by ✕ (or X) under its
// header; nothing in the review until added.
function openCmp(key){if(editing.cmp&&editing.cmp.key===key)return closeCmp();var it=D[cur],t='',vs=PL&&PL.it===it&&PL.v&&PL.v.shots;
// A block: the shot the player shows, to start with.
if(it.shots.length>1&&vs&&vs.length===1&&it.shots.indexOf(vs[0])>=0)t='['+vs[0]+'] ';
editing.cmp={key:key,kind:'rtk',text:t,at:t.length};refresh();focusCmp();}
function closeCmp(force){var c=editing.cmp;if(!c)return;var go=function(){editing.cmp=null;refresh();};if(!force&&c.text.replace(SHOT_RE,'').trim())ask('Drop what you wrote?','Drop it',go);else go();}
function focusCmp(){var ta=$('p-body').querySelector('.cmp-t'),c=editing.cmp,y=scrollY;if(!ta||!c)return;ta.focus({preventScroll:true});ta.setSelectionRange(c.at,c.at);if(scrollY!==y)scrollTo(scrollX,y);grow(ta);inView(ta.closest('.cmp'));}
// Brought into the panel's view, the page itself left where it is.
function inView(el){var pb=$('p-body'),r=el.getBoundingClientRect(),b=pb.getBoundingClientRect();if(r.bottom>b.bottom)pb.scrollTop+=Math.min(r.bottom-b.bottom+12,r.top-b.top-12);else if(r.top<b.top)pb.scrollTop-=b.top-r.top+12;}
// Its lines into the review: a note's "note:" after their tags; nothing
// written on a department, a retake with no text (sent back), the box closed.
function cmpAdd(){var c=editing.cmp,it=D[cur];if(!c)return;var e=entry(it),ls=c.text.split(NL).filter(function(l){return l.replace(SHOT_RE,'').trim();});
if(c.kind==='note')ls=ls.map(function(l){return NOTE_RE.test(l)?l:l.replace(/^(\s*(?:\[[^\]]*\]\s*)*)/,'$1note: ');});
var add=function(t){return (t&&t.trim()?t.replace(/\s+$/,'')+NL:'')+ls.join(NL);};
if(c.key==='gen'){if(ls.length)e.text=add(e.text);else editing.cmp=null;}
else{var d=c.key.slice(2),v=e.deps[d];
// A note keeps your ✓; a retake replaces it.
if(!(v&&(v.no||(v.ok&&c.kind==='note'&&ls.length))))v=e.deps[d]={no:1,text:v&&v.text||''};
if(ls.length)v.text=add(v.text);else editing.cmp=null;}
if(editing.cmp){var keepShot=it.shots.length>1?(SHOT_RE.exec(c.text)||[''])[0]:'';c.text=keepShot;c.at=keepShot.length;}
refresh();if(PL&&PL.it===it){PL.marks=marksOf(it,PL.v);drawMarks();}focusCmp();}
// A line of yours taken back (-1: the retake with no text); none left, the
// department's verdict goes too (a ✓ stays).
function takeBack(key,i){var it=D[cur],e=entry(it),d=key.slice(2),v=key==='gen'?null:e.deps[d];
if(i<0){delete e.deps[d];return refresh();}var ls=(key==='gen'?e.text:v.text||'').split(NL);ls.splice(i,1);var t=ls.join(NL);
if(key==='gen')e.text=t.trim()?t:'';else if(t.trim())v.text=t;else if(v.ok)v.text='';else delete e.deps[d];
refresh();if(PL&&PL.it===it){PL.marks=marksOf(it,PL.v);drawMarks();}}
function startReply(id){var it=D[cur],n=it.notes.filter(function(x){return x.id===id;})[0];if(!n||!canReply(n))return;
editing['r:'+id]=editing['r:'+id]||{text:'',kind:isRtk(n)?'rtk':'note'};refresh();var ta=$('p-body').querySelector('.rp-t[data-r="'+CSS.escape(id)+'"]');if(ta){ta.focus({preventScroll:true});inView(ta);}}
function sendReply(id){var f=editing['r:'+id],it=D[cur];if(!f)return;var ls=f.text.split(NL).filter(function(l){return l.trim();});
if(ls.length){var e=entry(it),old=e.replies[id];if(f.kind==='note')ls=ls.map(function(l){return NOTE_RE.test(l)?l:'note: '+l;});e.replies[id]=(old&&old.trim()?old.replace(/\s+$/,'')+NL:'')+ls.join(NL);}
delete editing['r:'+id];NOPEN[it.file+'|'+id]=true;refresh();}
function cancelReply(id){var f=editing['r:'+id],go=function(){delete editing['r:'+id];refresh();};if(f&&f.text.trim())ask('Drop this reply?','Drop it',go);else go();}
function validateAll(){var it=D[cur];if(asTeam()||!Object.keys(it.states).some(function(d){return isDone(it.states[d]);}))return;var e=entry(it);e.all=!e.all;refresh();}
function generalRetake(){if(reviewing())openCmp('gen');}
$('p-body').addEventListener('click',function(ev){var t,it=D[cur];
// A touch screen, a tap that opens a box to write in (✕, ↩, ✎, a shot):
// the page held from the tap, before the panel is redrawn and the box
// focused -- let go as any field, unless the box took the focus.
if(coarse.matches&&ev.target.closest('.rvb .ko-b,#add-gen,[data-reply],#add-desc')){clearTimeout(fieldT);lockPage('field',true);setTimeout(fieldLeft,0);}
// A render line's ▶: that video in the player, playing.
if((t=ev.target.closest('[data-play]'))){var vv=videosOf(it,it.renders[+t.dataset.play])[0],p=playerFor(it);if(!vv||!p)return;
for(var k=0;k<p.list.length;k++)if(p.list[k].name===vv.name){if(k!==p.at)load(k);break;}p.el.play();var pv=$('pv');if(pv)pv.scrollIntoView({block:'nearest'});return;}
if(ev.target.closest('#bigb'))return lightbox('<img alt="" src="'+$('bigimg').src+'">',esc(it.name));
if((t=ev.target.closest('.shotsel button'))){$('bigimg').src=t.dataset.src;t.parentNode.querySelectorAll('button').forEach(function(x){x.setAttribute('aria-pressed',x===t);});return;}
// A thread's line: its buttons act, they don't open it; the line itself
// opens or closes it, kept so in this browser.
var sm=ev.target.closest('summary');if(sm&&ev.target.closest('button'))ev.preventDefault();
else if(sm){var dt=sm.parentNode;NOPEN[it.file+'|'+dt.dataset.th]=!dt.open;keep('notes-open',NOPEN);}
if((t=ev.target.closest('[data-shotsel]'))){var sb=[].filter.call($('p-body').querySelectorAll('.shotsel button'),function(x){return x.textContent.indexOf(t.dataset.shotsel)===0;})[0];if(sb)sb.click();return;}
if((t=ev.target.closest('[data-nf]'))){NF.f=t.dataset.nf;keep('notes-filter',NF.f);return refresh();}
if((t=ev.target.closest('[data-ns]'))){NF.s=t.dataset.ns;keep('notes-sort',NF.s);return refresh();}
if(ev.target.closest('#fset')){fsetOpen=!fsetOpen;return refresh();}
if(ev.target.closest('#chk-t')){chkOpen=!chkOpen;return refresh();}
if(ev.target.closest('#lnk-t')){lnkOpen=!lnkOpen;return refresh();}
if((t=ev.target.closest('[data-goto]')))return jump(D[+t.dataset.goto]);
// A render to check: watched in the player; Checked, sent to Blender at once.
if((t=ev.target.closest('[data-chkplay]'))){var V2=it.live.versions||{},wv=t.dataset.chkplay;Object.keys(V2).some(function(k){var hit=V2[k].filter(function(x){return x.video===wv;})[0];if(hit)pickVersion(it,k,hit);return !!hit;});return;}
if((t=ev.target.closest('[data-chk]'))){t.disabled=true;var push=!!($('chk-push')||{}).checked;
livePost('action',{author:rv.author,role:rv.role,review_date:isoNow(),actions:[{type:'checked',file:it.file,key:t.dataset.chk,push:push}]})
.then(function(res){toast(res.ok?'Checked'+(push?', pushed to editing':'')+'.':'Not checked: '+(res.error||'?'));}).catch(function(){t.disabled=false;toast('Blender doesn\'t answer.');});return;}
if((t=ev.target.closest('[data-rm]'))){var rm=t.dataset.rm.split('|');return takeBack(rm[0],+rm[1]);}
if((t=ev.target.closest('[data-cmp]'))){if(t.dataset.cmp==='add')cmpAdd();else closeCmp();return;}
if((t=ev.target.closest('[data-kind]'))&&editing.cmp){editing.cmp.kind=t.dataset.kind;refresh();return focusCmp();}
if((t=ev.target.closest('[data-pk]'))&&editing.cmp){var c=editing.cmp,b0=lineAt(c.text,c.at),line=c.text.slice(b0[0],b0[1]),m0=SHOT_RE.exec(line),has=m0&&it.shots.indexOf(m0[1].toLowerCase())>=0,rest=has?line.slice(m0[0].length):line.replace(/^\s+/,''),pre=t.dataset.pk?'['+t.dataset.pk+'] ':'';
c.text=c.text.slice(0,b0[0])+pre+rest+c.text.slice(b0[1]);c.at=b0[0]+pre.length+rest.length;refresh();return focusCmp();}
if((t=ev.target.closest('[data-rkind]'))){var rf=editing['r:'+t.dataset.r];if(rf){rf.kind=t.dataset.rkind;refresh();var rt=$('p-body').querySelector('.rp-t[data-r="'+CSS.escape(t.dataset.r)+'"]');if(rt){rt.focus({preventScroll:true});rt.setSelectionRange(rt.value.length,rt.value.length);}}return;}
if((t=ev.target.closest('[data-rsend]')))return sendReply(t.dataset.rsend);
if((t=ev.target.closest('[data-rcancel]')))return cancelReply(t.dataset.rcancel);
if((t=ev.target.closest('[data-unreply]'))){delete entry(it).replies[t.dataset.unreply];return refresh();}
if((t=ev.target.closest('[data-closed]'))){closedOpen[t.dataset.closed]=!closedOpen[t.dataset.closed];return refresh();}
if((t=ev.target.closest('[data-sync]'))){var se=entry(it);if(se.synced[t.dataset.sync])delete se.synced[t.dataset.sync];else se.synced[t.dataset.sync]=1;return refresh();}
// A department required or not: back to as it was, or changed.
if((t=ev.target.closest('[data-asgmenu]'))){ev.stopPropagation();return asgMenu(it,t.dataset.asgmenu,t);}
if((t=ev.target.closest('[data-req]'))){var re=entry(it),rd=t.dataset.req,was=rd in it.states,now2=rd in re.req?re.req[rd]:was;
if(!now2===was)delete re.req[rd];else re.req[rd]=!now2;refresh();render();return;}
if((t=ev.target.closest('[data-omit]'))){var oe=entry(it),cur0=oe.omit||{state:(it.omit||{}).state||'',reason:(it.omit||{}).reason||''};
oe.omit={state:t.dataset.omit,reason:cur0.reason};refresh();var ow=$('om-why');if(ow&&t.dataset.omit)ow.focus({preventScroll:true});return;}
// "+ f12": the frame shown, after the line's shot; again on another
// frame, the two a range ([f12-30]); once more, a new start.
if((t=ev.target.closest('[data-addf]'))&&PL&&editing.cmp){var c2=editing.cmp,f=frameNo(PL.v,PL.el.currentTime),b2=lineAt(c2.text,c2.at),m2=SHOT_RE.exec(c2.text.slice(b2[0],b2[1])),at2=b2[0]+(m2&&it.shots.indexOf(m2[1].toLowerCase())>=0?m2[0].length:0),tg='[f'+f+'] ';
var fm=/^\[f(\d+)(?:-(\d+))?\]\s*/i.exec(c2.text.slice(at2,b2[1])),was=fm?fm[0].length:0;if(fm&&!fm[2]&&+fm[1]!==f)tg='[f'+Math.min(+fm[1],f)+'-'+Math.max(+fm[1],f)+'] ';
c2.text=c2.text.slice(0,at2)+tg+c2.text.slice(at2+was);c2.at=c2.at>=at2+was?c2.at+tg.length-was:c2.at>=at2?at2+tg.length:c2.at;refresh();if(PL&&PL.it===it){PL.marks=marksOf(it,PL.v);drawMarks();}return focusCmp();}
if(ev.target.closest('#add-gen'))return generalRetake();
if((t=ev.target.closest('[data-reply]')))return startReply(t.dataset.reply);
if((t=ev.target.closest('[data-fix]'))){var fe=entry(it),fids=t.dataset.fix.split(','),fall=fids.every(function(id){return fe.fixed[id];});fids.forEach(function(id){if(fall)delete fe.fixed[id];else fe.fixed[id]=1;});refresh();return;}
if(ev.target.closest('#add-desc')){editing.desc=true;entry(it).desc=it.desc;refresh();return $('desc-t').focus({preventScroll:true});}
if(ev.target.closest('#allok'))return validateAll();
if((t=ev.target.closest('.rvb button'))&&!t.disabled){var d=t.parentNode.dataset.d,e=entry(it),v=e.deps[d];
if(t.classList.contains('ok-b')){if(v&&v.ok)delete e.deps[d];else e.deps[d]={ok:1};refresh();}
else openCmp('d:'+d);}});
$('p-body').addEventListener('change',function(ev){var t=ev.target;if(!t.dataset||t.dataset.vline==null)return;var it=D[cur],k=t.dataset.vline;
pickVersion(it,k,t.value===''?null:((it.live.versions||{})[k]||[])[+t.value]);});
$('p-body').addEventListener('input',function(ev){var t=ev.target,it=D[cur],e=entry(it);if(t.tagName!=='TEXTAREA'&&t.id!=='om-why')return;if(t.tagName==='TEXTAREA')grow(t);
// The box being written: kept as typed, its shot buttons following the
// line; "note:" typed at its start makes it a note.
if(t.classList.contains('cmp-t')&&editing.cmp){var c=editing.cmp;c.text=t.value;c.at=t.selectionStart;
var nm=/^(\s*(?:\[[^\]]*\]\s*)*)(?:note|n)\s*:\s*/i.exec(t.value);if(nm&&c.kind!=='note'){c.kind='note';c.text=t.value.replace(nm[0],nm[1]);c.at=Math.max(0,c.at-(nm[0].length-nm[1].length));refresh();return focusCmp();}
syncPk(t);return;}
if(t.classList.contains('rp-t')){var rf=editing['r:'+t.dataset.r];if(rf)rf.text=t.value;return;}
if(t.id==='desc-t')e.desc=t.value;
else if(t.id==='om-why'&&e.omit)e.omit.reason=t.value;
$('p-flags').innerHTML=flags(it);$('p-kpi').innerHTML=kpiHtml(it);var row=$('list').querySelector('.row[data-i="'+cur+'"]');
if(row){var fl=row.querySelector('.flags');if(fl)fl.innerHTML=flags(it);
// Its tint as you type: a general retake or a description counts once written.
row.classList.toggle('rv-mine',changes(it)>0);var grp=row.closest('.group');if(grp)grp.classList.toggle('rv-all',allReviewed(it.group));if(changes(it))row.title='In your review';else row.removeAttribute('title');}
countBar();save();});

function syncPk(ta){var c=ta.closest('.cmp');if(!c||!editing.cmp)return;editing.cmp.at=ta.selectionStart;var sh=lineShot(D[cur],ta.value,ta.selectionStart);
c.querySelectorAll('[data-pk]').forEach(function(b){b.setAttribute('aria-pressed',b.dataset.pk===sh);});}
['keyup','click'].forEach(function(k){$('p-body').addEventListener(k,function(ev){if(ev.target.classList&&ev.target.classList.contains('cmp-t'))syncPk(ev.target);});});
$('p-body').addEventListener('keydown',function(ev){var t=ev.target;if(!t.classList||!(t.classList.contains('cmp-t')||t.classList.contains('rp-t')))return;
var send=ev.key==='Enter'&&(ev.ctrlKey||ev.metaKey);if(!send&&ev.key!=='Escape')return;ev.preventDefault();ev.stopPropagation();
if(t.classList.contains('cmp-t')){if(send)cmpAdd();else closeCmp();}else if(send)sendReply(t.dataset.r);else cancelReply(t.dataset.r);});
/* ---------- keys, as the page before ---------- */
document.addEventListener('keydown',function(e){var t=e.target;
if(t.matches&&t.matches('input,textarea,select')){if(e.key==='Escape'){t.blur();e.preventDefault();}
else if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){t.blur();e.preventDefault();}return;}
if(e.altKey||e.ctrlKey||e.metaKey)return;
if(!$('lb').hidden){if(e.key==='Escape'){closeLb();e.preventDefault();}
else if(e.key==='ArrowLeft'||e.key==='ArrowRight'){var nb=$('lb').querySelector('[data-lb="'+(e.key==='ArrowLeft'?-1:1)+'"]');if(nb&&!nb.disabled){nb.click();e.preventDefault();}}
return;}
// Watch large: Esc back to the panel; Space, , . and ← → the videos.
if(!$('wl').hidden){var kk=e.key;if(kk==='Escape')closeWatch();else if(kk===' '&&PL){if(PL.el.paused)PL.el.play();else PL.el.pause();}
else if(kk===','||kk==='.')stepFrame(kk===','?-1:1);else if(kk==='m'&&PL)setMuted(!PL.el.muted);else if(kk==='ArrowLeft'||kk==='ArrowRight')nextVideo(kk==='ArrowLeft'?-1:1);else return;e.preventDefault();return;}
if(!$('dlg').hidden){if(e.key==='Escape'){$('dlg').hidden=true;e.preventDefault();}return;}
// "/": go to a file.
if(e.key==='/'&&!e.ctrlKey&&!e.metaKey&&!e.altKey){e.preventDefault();$('q').focus();return;}
if(e.key==='Escape'&&MENUS.some(function(m){return !$(m[1]).hidden;})){closeMenus();return;}
if(cur==null)return;var k=e.key.toLowerCase();
if(PL&&PL.mode==='panel'&&PL.it===D[cur]&&(k===' '||k===','||k==='.'||k==='m')){if(k===' '){if(PL.el.paused)PL.el.play();else PL.el.pause();}else if(k==='m')setMuted(!PL.el.muted);else stepFrame(k===','?-1:1);}
else if(k==='arrowleft')step(-1);else if(k==='arrowright')step(1);else if(k==='escape')closePanel();
else if(reviewing()&&k==='v')validateAll();else if(reviewing()&&k==='x')generalRetake();
else if(reviewing()&&k==='r'&&document.activeElement&&document.activeElement.closest&&document.activeElement.closest('#p-body details.th'))startReply(document.activeElement.closest('details.th').dataset.th);
else return;e.preventDefault();});

/* ---------- review: the bar, the download, loading one back ---------- */
// Only the files this review touched, in the list -- on the tab that has
// some, if this one has none.
// Every file of a group (this tab's, filters aside) touched by the review.
function allReviewed(g){var all=D.filter(function(it){return it.tab===state.tab&&it.group===g;});return all.length>0&&all.every(function(it){return changes(it)>0;});}
function showMine(){state.f.mine=true;document.querySelector('.chipf[data-f="mine"]').setAttribute('aria-pressed','true');
if(!D.some(function(it){return it.tab===state.tab&&changes(it);})){var t=D.filter(function(it){return changes(it);})[0];if(t){setTab(t.tab);return;}}
render();$('bar').scrollIntoView({block:'start'});}
$('rv-n').addEventListener('click',function(){if(state.f.mine){state.f.mine=false;document.querySelector('.chipf[data-f="mine"]').setAttribute('aria-pressed','false');render();}else showMine();});
var toastT;function toast(t){var el=$('toast');el.textContent=t;el.classList.add('on');clearTimeout(toastT);toastT=setTimeout(function(){el.classList.remove('on');},4200);}
(META.roles||[]).forEach(function(r){var o=document.createElement('option');o.value=r;o.textContent=r;$('role').appendChild(o);});
// The team: its own retakes and notes, no validation (none of the roles is called that).
if((META.roles||[]).indexOf('team')<0){var to=document.createElement('option');to.value='team';to.textContent='team (no validation)';to.dataset.short='team';$('role').appendChild(to);}
pick($('role'));
function countBar(){var c=summary();$('rv-n').textContent=c.files?plural(c.files,'file')+' reviewed':'Nothing reviewed yet';$('rv-n').disabled=!c.files;
// "Your review" among the filters while there's one; off with it.
var mb=document.querySelector('.chipf[data-f="mine"]');mb.hidden=!c.files;if(!c.files&&state.f.mine){state.f.mine=false;mb.setAttribute('aria-pressed','false');}
document.querySelector('#rv-dl .cnt').textContent=c.files||'';$('rv-fabn').textContent=c.files||'';
summaryCards();
// The header while reviewing: who, as what, how much -- then Send.
$('rv-sum').innerHTML=ico('review')+'<span>'+esc(META.live?[rv.author,rv.role,LIVE_OUT.say].filter(Boolean).join(' · '):[rv.author||'Your name',rv.role,c.files?plural(c.files,'file'):c.creates?'':'nothing yet',c.creates?c.creates+' new':''].filter(Boolean).join(' · '))+'</span>';}
// The bar folds into a round button (remembered by this browser), never
// while it still needs a name.
var FOLD=KEY+':folded';
function fold(on){document.body.classList.toggle('rb-folded',on);try{localStorage.setItem(FOLD,on?'1':'');}catch(e){}
if(!on)$('rv-dl').focus({preventScroll:true});}
// Too narrow for it beside the panel (the panel widened, a small window):
// it folds by itself, ✎ bringing it back over everything until folded again.
function fitBar(){var b=document.body,bar=document.querySelector('.rbar');
if(!b.classList.contains('reviewing')||phone.matches){b.classList.remove('rb-auto','rb-peek');return;}
// Hidden while typing (and the keyboard resizing the page): nothing to
// measure then -- it would read 0 and unfold it. Again once done.
if(b.classList.contains('typing'))return;
var room=innerWidth-(b.classList.contains('panel-open')?$('panel').offsetWidth:0)-32;
var auto=b.classList.contains('rb-auto');b.classList.remove('rb-auto');
var need=bar.scrollWidth;if(auto)b.classList.add('rb-auto');
b.classList.toggle('rb-auto',need>room);if(need<=room)b.classList.remove('rb-peek');}
addEventListener('resize',fitBar);
$('rv-min').addEventListener('click',function(){if(document.body.classList.contains('rb-peek'))document.body.classList.remove('rb-peek');else fold(true);});
$('rv-fab').addEventListener('click',function(){if(document.body.classList.contains('rb-auto')&&!document.body.classList.contains('rb-folded'))document.body.classList.add('rb-peek');else fold(false);});
function setReview(on){document.body.classList.toggle('reviewing',on);
var folded=false;try{folded=localStorage.getItem(FOLD)==='1';}catch(e){}
document.body.classList.toggle('rb-folded',on&&folded&&!!$('author').value.trim());showNotes=null;editing={};if(on&&!$('author').value&&!matchMedia('(pointer:coarse)').matches)$('author').focus({preventScroll:true});render();if(cur!=null)openPanel(cur);fitBar();}
/* Review: start (or go on), first -- who, as what, what to go through. */
// Each role, said: what reviewing as it does.
function roleWords(r){return r==='team'?'Retakes and notes: no validation.':r===META.role?'Validates as the top role: what the figures count.':'Validates as '+r+': the top role validates after.';}
var GO=[['tovalid','To validate','the done departments not validated yet'],['open','Open retakes and notes','what\'s waiting for an answer'],['all','Everything, in order','every file of this tab'],['shown','What the filters show','the list as it is now']];
// The roles to review as: the snapshot's, and the team.
function roleList(){return [].map.call($('role').options,function(o){return o.value;}).filter(Boolean);}
var ROLE_KEY='mp-snapshot:role';
function openStart(){var c=summary(),dl=$('dlg'),roles=roleList(),last='';try{last=localStorage.getItem(ROLE_KEY)||'';}catch(e){}
var pickRole=[rv.role,last,META.role].filter(function(r){return r&&roles.indexOf(r)>=0;})[0]||'',go='tovalid',vr=roles.filter(function(r){return r!=='team';});
var kept=c.files>0&&!reviewing();
dl.innerHTML='<div class="dlg-in start" role="dialog" aria-modal="true" aria-labelledby="st-t"><h3 id="st-t">'+(reviewing()?'Your review':'Review this snapshot')+'</h3>'+
(kept?'<button type="button" class="btn st-cont" id="st-cont">'+ico('review')+'<span><b>Continue your review</b><small>'+esc([rv.author,rv.role,plural(c.files,'file')].filter(Boolean).join(' · '))+'</small></span></button><p class="st-or">or start again with</p>':'')+
'<div class="row2"><label>Your name<input id="st-author" value="'+esc(rv.author)+'" autocomplete="name"></label><label>Review date'+dateField('st-date',rv.date||today())+'</label></div>'+
'<div class="st-l">Role</div><div class="segb" role="group" aria-label="Role">'+roles.map(function(r){return '<button type="button" data-role="'+esc(r)+'" aria-pressed="'+(r===pickRole)+'">'+esc(r==='team'?'team':r)+'</button>';}).join('')+'</div>'+
'<p class="st-w" id="st-w">'+(pickRole?esc(roleWords(pickRole)):'Pick the role you review as.')+'</p>'+
(vr.length?'<p class="st-hint">'+esc(vr.join(' and ')+' validate and ask for retakes · team asks for retakes, can’t validate')+'</p>':'')+
(reviewing()?'':'<div class="st-l">Go through</div><div class="st-go">'+GO.map(function(g){return '<button type="button" data-go="'+g[0]+'" aria-pressed="'+(g[0]===go)+'"><b>'+esc(g[1])+'</b><small>'+esc(g[2])+'</small></button>';}).join('')+'</div>')+
'<p class="why" id="st-why" hidden></p><div class="acts"><label class="btn link">'+ico('import')+'Load a review file…<input type="file" class="rv-load" accept=".json,application/json" hidden></label>'+
'<button class="btn" id="st-cancel">Cancel</button><button class="btn primary" id="st-go">'+(reviewing()?'Done':'Start')+'</button></div></div>';
dl.hidden=false;wireDates(dl);dl.onclick=function(e){if(e.target===dl)dl.hidden=true;};
dl.querySelector('.rv-load').addEventListener('change',function(){dl.hidden=true;loadReview(this);});
$(rv.author||touchPin.matches?'st-go':'st-author').focus({preventScroll:true});
dl.querySelectorAll('[data-role]').forEach(function(b){b.onclick=function(){pickRole=b.dataset.role;dl.querySelectorAll('[data-role]').forEach(function(x){x.setAttribute('aria-pressed',String(x===b));});$('st-w').textContent=roleWords(pickRole);};});
dl.querySelectorAll('[data-go]').forEach(function(b){b.onclick=function(){go=b.dataset.go;dl.querySelectorAll('[data-go]').forEach(function(x){x.setAttribute('aria-pressed',String(x===b));});};});
$('st-cancel').onclick=function(){dl.hidden=true;};
if($('st-cont'))$('st-cont').onclick=function(){dl.hidden=true;setReview(true);};
$('st-go').onclick=function(){var a=$('st-author').value.trim();
if(!a){$('st-why').hidden=false;$('st-why').textContent='Your name: the notes and retakes are signed with it.';$('st-author').focus();return;}
var was=reviewing();rv.author=a;rv.role=pickRole;rv.date=$('st-date').value;try{localStorage.setItem(ROLE_KEY,pickRole);}catch(e){}$('author').value=a;$('role').value=pickRole;sync('role');save();dl.hidden=true;
if(was){countBar();render();if(cur!=null)refresh();return;}
setReview(true);goThrough(go);};}
// What to go through: the filters set for it, its first file opened.
function goThrough(go){if(go!=='shown'){state.f={};state.q='';$('q').value='';if(go==='tovalid')state.f.tovalid=true;else if(go==='open')state.f.notes=true;
document.querySelectorAll('.chipf[data-f]').forEach(function(b){b.setAttribute('aria-pressed',String(!!state.f[b.dataset.f]));});}
if(state.tab==='breakdown')setTab(tabs[0][0]);else render();
if(visible.length)openPanel(visible[0]);else toast('Nothing to go through here: the filters show no file.');}
// Live: the name and role are Blender's (Preferences): no window to ask them.
$('rv').addEventListener('click',function(){if(META.live)return setReview(true);openStart();});$('rv-sum').addEventListener('click',function(){if(!META.live)openStart();});$('rv-send').addEventListener('click',openSend);
$('rv-exit').addEventListener('click',function(){closeMenus();setReview(false);toast('Review left: it stays in this browser, ✎ Review takes it back.');});
// Asked in the page, not with confirm(): an app's viewer (Documents, on an
// iPad) may show no confirm() at all -- it answers no, and nothing was
// cleared. then() once the button is pressed.
function ask(text,ok,then){var dl=$('dlg');dl.innerHTML='<div class="dlg-in" role="alertdialog" aria-modal="true" aria-labelledby="ask-t"><p id="ask-t" class="ask">'+esc(text)+'</p>'+
'<div class="acts"><button class="btn" id="ask-no">Cancel</button><button class="btn primary" id="ask-ok">'+esc(ok)+'</button></div></div>';
dl.hidden=false;$('ask-ok').focus({preventScroll:true});dl.onclick=function(e){if(e.target===dl)dl.hidden=true;};
$('ask-no').onclick=function(){dl.hidden=true;};$('ask-ok').onclick=function(){dl.hidden=true;then();};}
// Cleared: what was written for each file, here and in this browser's
// copy -- the name and the role stay.
function clearReview(){rv.files={};rv.creates=[];BOX={};editing={};save();render();if(cur!=null)openPanel(cur);toast('Review cleared.');}
$('rv-clear').addEventListener('click',function(){closeMenus();if(!summary().files)clearReview();
else ask('Clear this review? What you wrote here is lost (a downloaded file is kept).','Clear it',clearReview);});
$('author').addEventListener('input',function(){this.classList.remove('need');rv.author=this.value;save();});
$('role').addEventListener('change',function(){this.classList.remove('need');rv.role=this.value;save();sync('role');
// As the team or not: the ✓ and what's yours change.
render();if(cur!=null)refresh();});
// The review as typed actions (lib/review_import.py ACTION_TYPES): what
// each file's ✓ / ✕, boxes, replies, fixes and description ask. A box's
// lines read here -- [sh020] [f12-40] at their start, "note:" a remark.
var BULLET=/^\s*(?:[-*•–]|\d+[.)])\s+/;
function readLine(l){var rest=l.replace(BULLET,'').trim(),shot='',frames=null,m;
while((m=/^\[\s*([a-z]*)\s*(\d+)(?:\s*-\s*(\d+))?\s*\]\s*/i.exec(rest))){var w=m[1].toLowerCase();
if(w==='f'&&!frames&&!(m[3]&&+m[3]<+m[2]))frames=[+m[2],m[3]?+m[3]:null];else if(w&&w!=='f'&&!shot&&!m[3])shot=m[2];else break;rest=rest.slice(m[0].length);}
var note=/^(?:note|n)\s*:\s*/i.test(rest);rest=rest.replace(/^(?:note|n)\s*:\s*/i,'').trim();
// Tags alone: nothing to note, the line as typed.
if(!rest)return {text:l.replace(BULLET,'').trim(),shot:'',frames:null,note:false};
return {text:rest,shot:shot,frames:frames,note:note};}
function exportActions(){var out=[],team=asTeam();D.forEach(function(it){if(!changes(it))return;var e=rv.files[it.file],f=it.file,seen=it.stable||'',ref=it.render_ref||'';
var lines=function(text,deps){(text||'').split(NL).forEach(function(l){if(!l.trim())return;var p=readLine(l);
out.push({type:p.note?'note':'rtk',file:f,departments:deps,text:p.text,shot:p.shot,frames:p.frames,render:ref});});};
var said={};
Object.keys(e.deps).forEach(function(d){var v=e.deps[d];if(!sent(v))return;said[d]=1;
if(v.ok){out.push({type:'validate',file:f,department:d,seen:seen});return;}
var t=(v.text||'').trim();
// A retake withdraws the validation; remarks alone leave it.
if(!team&&(!t||!noteOnly(t)))out.push({type:'unvalidate',file:f,department:d,seen:seen});
lines(t,[d]);});
// A reply to a department's open RTK: still to redo, its validation withdrawn.
if(!team)Object.keys(answered(it).deps).forEach(function(d){if(!said[d]){said[d]=1;out.push({type:'unvalidate',file:f,department:d,seen:seen});}});
if(e.all&&!team)Object.keys(it.states).forEach(function(d){if(isDone(it.states[d])&&!said[d])out.push({type:'validate',file:f,department:d,seen:seen});});
lines(e.text,[]);
if(e.desc!==null&&e.desc.trim()&&e.desc.trim()!==it.desc)out.push({type:'description',file:f,old:it.desc||'',new:e.desc.trim()});
Object.keys(e.fixed||{}).forEach(function(id){out.push({type:'fixed',file:f,id:id});});
replies(e).forEach(function(id){out.push({type:'reply',file:f,to:id,text:e.replies[id].trim()});});
Object.keys(e.synced||{}).forEach(function(d){out.push({type:'still_done',file:f,department:d,text:''});});
var add=Object.keys(e.req||{}).filter(function(d){return e.req[d];}),rem=Object.keys(e.req||{}).filter(function(d){return !e.req[d];});
if(add.length||rem.length)out.push({type:'departments',file:f,add:add,remove:rem});
if(omitChanged(it,e))out.push({type:'omit',file:f,state:e.omit.state,reason:e.omit.state?e.omit.reason||'':''});
Object.keys(e.assign||{}).forEach(function(d){out.push({type:'assign',file:f,department:d,people:e.assign[d]});});});
(rv.creates||[]).forEach(function(c){out.push(Object.assign({type:'create',file:c.label},c));});return out;}
// A review file read back into the page: its actions as the boxes,
// ✓ / ✕, replies and fixes they came from.
function fromActions(actions){var unknown={};(actions||[]).forEach(function(a){if(a.type==='create')return;var it=byFile[a.file];if(!it){unknown[a.file]=1;return;}var e=entry(it);
var tag=function(){return (a.shot?'[sh'+a.shot+'] ':'')+(a.frames?'[f'+a.frames[0]+(a.frames[1]!=null?'-'+a.frames[1]:'')+'] ':'')+(a.type==='note'?'note: ':'');};
var add=function(t,line){return (t?t.replace(/\s+$/,'')+NL:'')+line;};
if(a.type==='validate')e.deps[a.department]={ok:1};
else if(a.type==='unvalidate'){if(!e.deps[a.department])e.deps[a.department]={no:1,text:''};}
else if(a.type==='rtk'||a.type==='note'){var line=tag()+a.text,d=(a.departments||[])[0];
if(d){var v=e.deps[d];if(!v||!v.no)v=e.deps[d]={no:1,text:''};v.text=add(v.text,line);}else e.text=add(e.text,line);}
else if(a.type==='reply')e.replies[a.to]=String(a.text||'');
else if(a.type==='fixed')e.fixed[a.id]=1;
else if(a.type==='description')e.desc=a.new;
else if(a.type==='still_done')e.synced[a.department]=1;
else if(a.type==='departments'){(a.add||[]).forEach(function(d){e.req[d]=true;});(a.remove||[]).forEach(function(d){e.req[d]=false;});}
else if(a.type==='omit')e.omit={state:a.state||'',reason:a.reason||''};
else if(a.type==='assign')e.assign[a.department]=a.people||[];});
(actions||[]).forEach(function(a){if(a.type==='create'){var c=Object.assign({},a);delete c.type;delete c.file;c.label=a.file;rv.creates.push(c);}});return Object.keys(unknown).length;}
// <project>_review_<YYYY-MM-DD_HH-MM>_<role>_<author>.json: two reviewers'
// files side by side on a drive, never one over the other.
function slug(t){return String(t||'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'');}
function reviewName(){var d=new Date(),stamp=d.getFullYear()+'-'+two(d.getMonth()+1)+'-'+two(d.getDate())+'_'+two(d.getHours())+'-'+two(d.getMinutes());
return [META.review_base+'_review_'+stamp,slug(rv.role),slug(rv.author)].filter(Boolean).join('_')+'.json';}
function today(){var d=new Date();return d.getFullYear()+'-'+two(d.getMonth()+1)+'-'+two(d.getDate());}
// Files to the share sheet: a touch screen whose browser can (Safari and
// Documents' viewer on an iPad, a phone's).
var SHARE=!!(navigator.share&&navigator.canShare&&matchMedia('(pointer:coarse)').matches&&
(function(){try{return navigator.canShare({files:[new File(['{}'],'t.json',{type:'application/json'})]})||navigator.canShare({files:[new File(['{}'],'t.json',{type:'text/plain'})]});}catch(e){return false;}})());
// Send: who, as what and when; what it holds, file by file, with the
// list's symbols; the file's name; then the file -- downloaded, or the
// share sheet on a tablet or a phone. The page itself sends nothing.
function sendRecap(actions){var files=[],by={};actions.forEach(function(a){if(!by[a.file]){by[a.file]=[];files.push(a.file);}by[a.file].push(a);});
var fl=function(a){return a.frames?'f'+a.frames[0]+(a.frames[1]!=null?'-'+a.frames[1]:'')+' ':'';};
return files.map(function(f){var it=byFile[f],acts=by[f],parts=[],deps={};
if(acts[0].type==='create'){var c=acts[0];return '<div class="rc"><b class="rc-n">'+esc(f)+'</b><span class="rc-p"><span class="rc-x">'+ico('review')+'new '+c.kind+(c.frame_start!=null?' · f'+c.frame_start+'-'+(c.frame_end!=null?c.frame_end:'?'):'')+(c.departments.length?' · '+esc(c.departments.map(cap).join(', ')):'')+(Object.keys(c.assignees||{}).length?' · → '+esc(c.assignees[Object.keys(c.assignees)[0]].join(', ')):'')+(c.description?' · '+esc(c.description):'')+'</span></span></div>';}
acts.forEach(function(a){if(a.type==='validate')deps[a.department]={ok:1};else if(a.type==='unvalidate'){deps[a.department]=deps[a.department]||{no:1,lines:[]};}
else if((a.type==='rtk'||a.type==='note')){var d=(a.departments||[])[0]||' whole';(deps[d]=deps[d]&&deps[d].lines?deps[d]:{no:1,lines:[]}).lines.push(fl(a)+(a.type==='note'?'note: ':'')+a.text);}});
Object.keys(deps).forEach(function(d){var v=deps[d],nm=d===' whole'?'Whole file':cap(d);
parts.push(v.ok?'<span class="rc-ok"><span class="m s-prod">✓</span>'+esc(nm)+' · ✓ validated</span>':
'<span class="rc-no"><span class="pi pi-role">✕</span>'+esc(nm)+'<small>'+(v.lines.length?esc(v.lines.map(function(l){return /note: /.test(l)?'✎ '+l:'✕ retake: '+l;}).join(' · ')):'✕ validation withdrawn')+'</small></span>');});
var n=function(t){return acts.filter(function(a){return a.type===t;}).length;};
if(n('description'))parts.push('<span class="rc-x">'+ico('review')+'description</span>');
if(n('fixed'))parts.push('<span class="rc-x">'+ico('check')+n('fixed')+' fixed</span>');
if(n('reply'))parts.push('<span class="rc-x">'+ico('reply')+n('reply')+(n('reply')>1?' replies':' reply')+'</span>');
acts.forEach(function(a){if(a.type==='still_done')parts.push('<span class="rc-x">'+ico('check')+esc(cap(a.department))+': still done</span>');
else if(a.type==='departments')parts.push('<span class="rc-x">'+ico('filter')+esc([a.add.length?'+ '+a.add.map(cap).join(', '):'',a.remove.length?'− '+a.remove.map(cap).join(', '):''].filter(Boolean).join(' · '))+'</span>');
else if(a.type==='assign')parts.push('<span class="rc-x">'+ico('user')+esc(cap(a.department))+' → '+esc((a.people||[]).join(', ')||'nobody')+'</span>');
else if(a.type==='omit')parts.push('<span class="rc-x">'+ico('time')+esc(a.state==='on_hold'?'On hold':a.state==='cancelled'?'Cancelled':'Active again')+(a.reason?': '+a.reason:'')+'</span>');});
return '<div class="rc"><b class="rc-n">'+(it?nameHtml(it):esc(f))+'</b><span class="rc-p">'+parts.join('')+'</span></div>';}).join('');}
function openSend(){var rows=exportActions();
if(!rows.length){toast('Nothing to send yet: validate or write a retake first.');return;}
var c=summary(),needsRole=rows.some(function(a){return a.type!=='description';});
var dl=$('dlg');dl.innerHTML='<div class="dlg-in send" role="dialog" aria-modal="true" aria-labelledby="dlg-t"><div class="send-h"><h3 id="dlg-t">Send your review</h3>'+
'<span class="faint">'+plural(c.files,'file')+' · '+[c.ok?c.ok+' validated':'',c.rt?plural(c.rt,'retake'):'',c.notes?plural(c.notes,'note'):''].filter(Boolean).join(' · ')+'</span>'+
'<button class="btn link" id="d-see" title="Only the files this review touched, in the list">Show the changes</button></div>'+
'<div class="row2"><label>Your name<input id="d-author" value="'+esc(rv.author)+'" autocomplete="name"></label>'+
'<label>Review date'+dateField('d-date',rv.date||today())+'</label></div>'+
'<div class="st-l">Role</div><div class="segb" id="d-role" role="group" aria-label="Role">'+roleList().map(function(r){return '<button type="button" data-role="'+esc(r)+'" aria-pressed="'+(r===rv.role)+'">'+esc(r)+'</button>';}).join('')+'</div>'+
'<div class="recap">'+sendRecap(rows)+'</div>'+
'<p class="send-f">'+ico('export')+'<code id="d-name"></code></p>'+
'<p class="send-why">The page sends nothing itself: download the file and send it to the studio (mail, SwissTransfer).'+(SHARE?' Here, the share sheet opens: Save to Files, AirDrop, Mail…':' On an iPad, the share sheet opens.')+'</p>'+
'<p class="why" id="d-why" hidden></p><div class="acts"><button class="btn link" id="d-clear">'+ico('trash')+'Clear this review…</button><button class="btn" id="d-cancel">Keep reviewing</button>'+
'<button class="btn primary" id="d-go">'+ico('export')+(SHARE?'Save or send…':'Download')+'</button></div></div>';
var dRole=rv.role;
var nm=function(){var a=rv.author,r=rv.role;rv.author=$('d-author').value.trim();rv.role=dRole;$('d-name').textContent=reviewName();rv.author=a;rv.role=r;};
dl.querySelectorAll('[data-role]').forEach(function(b){b.onclick=function(){dRole=b.dataset.role;$('d-role').classList.remove('need');
dl.querySelectorAll('[data-role]').forEach(function(x){x.setAttribute('aria-pressed',String(x===b));});nm();};});
nm();dl.hidden=false;wireDates(dl);
$('d-author').addEventListener('input',nm);
// A touch screen: no keyboard brought up unasked (the page scrolled to it).
$(rv.author||touchPin.matches?'d-go':'d-author').focus({preventScroll:true});
$('d-cancel').onclick=function(){dl.hidden=true;};$('d-see').onclick=function(){dl.hidden=true;showMine();};dl.onclick=function(e){if(e.target===dl)dl.hidden=true;};
$('d-clear').onclick=function(){ask('Clear this review? What you downloaded keeps it.','Clear it',clearReview);};
$('d-go').onclick=function(){rv.author=$('d-author').value.trim();var was=rv.role;rv.role=dRole;rv.date=$('d-date').value;try{localStorage.setItem(ROLE_KEY,rv.role);}catch(e){}
$('author').value=rv.author;$('role').value=rv.role;sync('role');save();
// The role changed here: what's sent with it (the team sends no validation).
if(rv.role!==was){render();if(cur!=null)refresh();rows=exportActions();
if(!rows.length){$('d-why').hidden=false;$('d-why').textContent='As the team, nothing to send: the team doesn\'t validate — write a retake or a note.';return;}}
if(needsRole&&!rv.role){$('d-why').hidden=false;$('d-why').textContent='Pick your role: your validations and retakes are recorded under it.';$('d-role').classList.add('need');return;}
var data={format:META.format,schema_version:META.schema_version,project:META.project,snapshot:META.snapshot,author:rv.author,role:rv.role,
review_date:rv.date,written_at:isoNow(),actions:rows};
var text=JSON.stringify(data,null,2),name=reviewName();
function download(){var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'application/json'}));a.download=name;
document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},1000);dl.hidden=true;
toast('Downloaded ('+name+'): send it, Import review reads it.');}
// A tablet, a phone: the share sheet (Save to Files picks the folder).
var file=shareFile(text,name);
if(!file)return download();
navigator.share({files:[file],title:name}).then(function(){dl.hidden=true;toast('Review saved or sent: Import review reads it.');},
function(err){if(err&&err.name==='AbortError')return;download();});};}
$('rv-dl').addEventListener('click',openSend);
// The review as a file the share sheet takes: JSON, else as plain text
// (same .json name) where a browser shares only some types. null: none.
function shareFile(text,name){if(!SHARE)return null;
for(var i=0,types=['application/json','text/plain'];i<types.length;i++){var f=new File([text],name,{type:types[i]});
try{if(navigator.canShare({files:[f]}))return f;}catch(e){}}return null;}
document.querySelectorAll('.rv-load').forEach(function(inp){inp.addEventListener('change',function(){loadReview(this);});});
function loadReview(inp){(function(){var file=inp.files[0];inp.value='';closeMenus();if(!file)return;
var rd=new FileReader();rd.onload=function(){var data;try{data=JSON.parse(rd.result);}catch(e){toast('Not a review file.');return;}
if(data.format!==META.format){toast('Not a review downloaded from a snapshot page.');return;}
// Another version's review: refused, as by the import (NOTES.md, "Review import: this version's reviews only").
if(data.schema_version!==META.schema_version){toast('This review comes from another version of the snapshot: it can\'t be loaded here.');return;}
var go=function(){if(summary().files)ask('Replace the review in progress with this one?','Replace it',load);else load();};
if(data.project!==META.project)ask('This review is for '+data.project+', not '+META.project+'. Load it anyway?','Load it',go);else go();
function load(){rv={author:data.author||'',role:data.role||'',date:data.review_date||'',files:{},creates:[]};var unknown=fromActions(data.actions);
$('author').value=rv.author;$('role').value=rv.role;sync('role');save();setReview(true);render();
toast('Review of '+(rv.author||'?')+' loaded: '+plural(summary().files,'file')+(unknown?', '+unknown+' not on this page (renamed, or another snapshot)':'')+'.');}};
rd.readAsText(file);})();}

/* ---------- start ---------- */
try{var kept=JSON.parse(localStorage.getItem(KEY)||'null');if(kept&&kept.files){rv=kept;rv.date=rv.date||'';rv.creates=rv.creates||[];
$('author').value=rv.author||'';$('role').value=rv.role||'';sync('role');
if(summary().files){document.body.classList.add('reviewing');try{if(localStorage.getItem(FOLD)==='1'&&rv.author)document.body.classList.add('rb-folded');}catch(e){}setTimeout(function(){toast('Your review in progress is back (kept in this browser).');},300);}}}catch(e){}
// The opening's motions (page.css "small motions"), once: not at each redraw.
document.body.classList.add('intro');setTimeout(function(){document.body.classList.remove('intro');},1400);
summaryCards();drawTabs();render();barHeight();
/* ---------- live: served by Blender (lib/live.py) ---------- */
// The page asks "anything new since version N?"; Blender answers at once
// when there is, else after 20 s. The new data replaces the page's -- the
// file shown, its video playing and your review kept; not while a field
// is being written in (once left). Disconnected: tried again every 2 s.
/* ---------- live: the panel's own sections ---------- */
// To check: the renders the team hasn't watched -- ▶ in the player,
// Checked takes one off (pushed to the edit if ticked); open by default.
// Linked files: what it links (a newer stable said), what links it.
var chkOpen=true,lnkOpen=false;
function fold2(id,open,icon,title,sum,body){return '<div class="fset'+(open?' on':'')+'"><button type="button" class="fset-b" id="'+id+'" aria-expanded="'+open+'">'+ico(icon)+'<b>'+title+'</b><span class="sm">'+sum+'</span><span class="chev" aria-hidden="true">▸</span></button>'+(open?'<div class="fset-c">'+body+'</div>':'')+'</div>';}
function checksHtml(it){var c=it.live.checks||[];if(!c.length)return '';
return fold2('chk-t',chkOpen,'eye','To check',plural(c.length,'render')+' not watched by the team yet',c.map(function(x){
return '<div class="chk"><span class="chk-l">'+esc([x.shot,x.department,x.folder].filter(Boolean).join(' · '))+'</span>'+(x.video&&videoSrc(x.video)?'<button type="button" class="act" data-chkplay="'+esc(x.video)+'">'+ico('play')+'Play</button>':'')+
'<button type="button" class="act fix" data-chk="'+esc(x.key)+'" title="Watched: out of To check">'+ico('check')+'Checked</button></div>';}).join('')+
'<label class="chk-push"><input type="checkbox" id="chk-push"> Push to editing when checked</label>');}
function itemAt(key){return key&&byKey[key];}
function linksHtml(it){var L=it.live,links=L.links||[],by=L.linked_by||[];if(!links.length&&!by.length)return '';var old=links.filter(function(x){return x.newer;}).length;
var to=function(t,file){return t?'<button type="button" class="lk" data-goto="'+t.i+'">'+esc(t.name)+'</button>':'<span>'+esc(file)+'</span>';};
return fold2('lnk-t',lnkOpen,'link','Linked files',[plural(links.length,'link'),old?old+' to update':'','linked by '+by.length].filter(Boolean).join(' · '),
(links.length?'<div class="st-l">Links</div>'+links.map(function(x){return '<div class="lnk">'+to(itemAt(x.key),x.file)+'<span class="lf">'+esc(x.file)+'</span>'+(x.newer?'<span class="tg tg-old" title="A newer stable of it exists">'+ico('warn')+esc(x.newer)+'</span>':'')+'</div>';}).join(''):'')+
(by.length?'<div class="st-l">Linked by</div>'+by.map(function(k){return '<div class="lnk">'+to(itemAt(k),k)+'</div>';}).join(''):''));}
// Live: every version with a video, to watch instead of the main render.
function versionsHtml(it){if(!it.live)return '';var V=it.live.versions||{};
return it.renders.filter(function(r){return (V[r.shots||'']||[]).length>1||((V[r.shots||'']||[]).length&&V[r.shots||''][0].video!==r.video);}).map(function(r){var k=r.shots||'',o=(PICKV[it.file]||{})[k];
return '<label class="vsel">'+(k?'<span>'+esc(k)+'</span>':'')+'<select data-vline="'+esc(k)+'" aria-label="Version to watch"><option value="">Main · '+esc([r.folder,r.department].filter(Boolean).join(' · '))+'</option>'+
V[k].map(function(v,n){return '<option value="'+n+'"'+(o&&o.video===v.video?' selected':'')+'>'+esc([v.folder,v.department,fmtDay(new Date(v.at*1000))].filter(Boolean).join(' · '))+'</option>';}).join('')+'</select></label>';}).join('');}
function pickVersion(it,line,v){var p=PICKV[it.file]=PICKV[it.file]||{};if(v)p[line]=v;else delete p[line];
if(PL&&PL.it===it){PL.el.pause();PL.el.removeAttribute('src');PL.el.load();PL=null;}refresh();
var pl=PL&&PL.it===it?PL:null,want=v?v.video:null;if(pl){for(var k=0;k<pl.list.length;k++)if(!want||pl.list[k].name===want){if(k!==pl.at)load(k);break;}pl.el.play();}}
function livePost(path,body){return fetch(path+'?t='+encodeURIComponent(META.live.token),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(function(r){return r.json();});}
// Open a file in Blender: the question when Blender's has unsaved changes.
function liveOpen(file,save){livePost('open',{file:file,save:save||''}).then(function(res){if(res.ask)return askOpen(file,res.current);
toast(res.ok?'Opening '+res.opened+' in Blender…':'Not opened: '+res.error);}).catch(function(){toast('Blender doesn\'t answer.');});}
function askOpen(file,current){var dl=$('dlg');dl.innerHTML='<div class="dlg-in" role="alertdialog" aria-modal="true" aria-labelledby="ask-t"><p id="ask-t" class="ask">'+esc(current)+' has unsaved changes in Blender.</p>'+
'<div class="acts"><button class="btn" data-o="">Cancel</button><button class="btn" data-o="discard">Don\'t save</button><button class="btn primary" data-o="save">Save, then open</button></div></div>';
dl.hidden=false;dl.querySelector('[data-o="save"]').focus({preventScroll:true});dl.onclick=function(e){var b=e.target.closest('[data-o]');if(e.target!==dl&&!b)return;dl.hidden=true;if(b&&b.dataset.o)liveOpen(file,b.dataset.o);};}
/* ---------- live: what you do, sent to Blender ---------- */
// Applied there as an imported review would be (the same checks; sent
// twice, it changes nothing): once the data showing it is back, it leaves
// your review -- its YOU tags with it. Not while the description or a
// reason is being typed (once left); a change made while one is on its
// way is sent after, what went already left out.
function liveSay(t){LIVE_OUT.say=t;if(reviewing())countBar();}
function liveSend(){clearTimeout(LIVE_OUT.t);LIVE_OUT.t=setTimeout(liveFlush,300);}
function liveFlush(){if(LIVE_OUT.busy){LIVE_OUT.again=true;return;}
var a=document.activeElement;if(a&&(a.id==='desc-t'||a.id==='om-why'))return;
var acts=exportActions().filter(function(x){return !(LIVE_OUT.sent[x.file]||{})[JSON.stringify(x)];});if(!acts.length)return;
var snap={},creates=(rv.creates||[]).map(function(c){return c.label;});Object.keys(rv.files).forEach(function(f){snap[f]=JSON.stringify(rv.files[f]);});
LIVE_OUT.busy=true;liveSay('sending…');
fetch('action?t='+encodeURIComponent(META.live.token),{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({author:rv.author,role:rv.role,review_date:isoNow(),actions:acts})}).then(function(r){return r.json();}).then(function(res){LIVE_OUT.busy=false;
if(!res.ok){liveSay('not sent');toast('Not applied by Blender: '+(res.error||'no answer')+' -- sent again in a moment.');setTimeout(liveSend,4000);return;}
var done=function(quiet){Object.keys(snap).forEach(function(f){if(!rv.files[f])return;
if(JSON.stringify(rv.files[f])===snap[f]){delete rv.files[f];delete LIVE_OUT.sent[f];}
else{var s2=LIVE_OUT.sent[f]=LIVE_OUT.sent[f]||{};acts.forEach(function(x){if(x.file===f)s2[JSON.stringify(x)]=1;});}});
rv.creates=(rv.creates||[]).filter(function(c){return creates.indexOf(c.label)<0;});store();LIVE_OUT.say='live';if(!quiet){countBar();render();if(cur!=null)refresh();}};
if((META.live.version||0)>=res.version)done();else LIVE_OUT.after={v:res.version,fn:done};
if(res.skipped&&res.skipped.length)toast('Blender left out: '+res.skipped.map(function(x){return x[0]+' ('+x[1]+')';}).join(', '));
if(LIVE_OUT.again){LIVE_OUT.again=false;liveSend();}})
.catch(function(){LIVE_OUT.busy=false;liveSay('not sent');setTimeout(liveSend,4000);});}
document.addEventListener('focusout',function(e){if(META.live&&e.target&&(e.target.id==='desc-t'||e.target.id==='om-why'))liveSend();});
var pend=null;
function applyData(nd){var a=document.activeElement,box=a&&a.classList&&(a.classList.contains('cmp-t')?'cmp':a.classList.contains('rp-t')?a.dataset.r:'');
// A box to write in kept as it was (its text is the page's); any other
// field: once left.
if(!box&&a&&a.matches&&a.matches('textarea,input:not([type=checkbox]):not([type=radio])')){pend=nd;return;}pend=null;
var curFile=cur!=null&&D[cur]?D[cur].file:null,plFile=PL&&PL.it?PL.it.file:null,y=scrollY;
// The file shown gone (archived, renamed): its panel closed first.
if(curFile&&!nd.items.some(function(x){return x.file===curFile;})){closePanel();curFile=null;}
Object.keys(nd.images||{}).forEach(function(k){DATA.images[k]=nd.images[k];});
DATA.items=nd.items;DATA.meta=nd.meta;META=nd.meta;D=nd.items;W=META.weights;prepare();
if(PL&&plFile&&byFile[plFile])PL.it=byFile[plFile];
// What was sent, now shown by the data: out of your review, before drawing.
if(LIVE_OUT.after&&(META.live.version||0)>=LIVE_OUT.after.v){var fn=LIVE_OUT.after.fn;LIVE_OUT.after=null;fn(true);}
cur=curFile&&byFile[curFile]?byFile[curFile].i:null;summaryCards();drawTabs();stamp();render();scrollTo(scrollX,y);
if(cur!=null)refresh();
if(box==='cmp')focusCmp();else if(box){var rt=$('p-body').querySelector('.rp-t[data-r="'+CSS.escape(box)+'"]');if(rt){rt.focus({preventScroll:true});rt.setSelectionRange(rt.value.length,rt.value.length);}}}
document.addEventListener('focusout',function(){setTimeout(function(){if(pend)applyData(pend);},0);});
if(META.live)(function(){var T=META.live.token,v=META.live.version||0,st='';document.body.classList.add('live');
var pill=document.createElement('span');pill.setAttribute('role','status');$('h-when').after(pill);
function status(s){if(s===st)return;st=s;pill.className='lvp '+s;pill.textContent=s==='on'?'connected':s==='busy'?'Blender busy':'disconnected';
pill.title=s==='on'?'Served by Blender on this machine, kept up to date':s==='busy'?'Blender is busy (a long task): the page waits for it':'Blender doesn\'t answer (closed, or the page stopped): trying again';}


function poll(){fetch('data?t='+encodeURIComponent(T)+'&since='+v,{cache:'no-store'}).then(function(r){if(!r.ok)throw r.status;return r.json();})
.then(function(d){status(d.busy?'busy':'on');if(d.data&&d.version!==v){v=d.version;applyData(d.data);}poll();})
.catch(function(){status('off');setTimeout(poll,2000);});}
status('on');poll();
rv.author=META.live.user||rv.author;rv.role=META.live.role||'team';store();setReview(true);countBar();if(Object.keys(rv.files).length||(rv.creates||[]).length)liveSend();})();
// A link to a file (#its name) opens it.
var want=decodeURIComponent(location.hash.slice(1));if(want&&byName[want])jump(byName[want]);
})();
// The status bar's room (page.css --sat): the largest the screen has had,
// in this orientation, kept by this browser -- its bar shown or hidden
// (Documents' viewer, at each tap), the page stays where it is.
(function(){var K='mp-snapshot:safe-top:',pr=document.createElement('div'),max={};
pr.style.cssText='position:fixed;top:0;left:0;width:1px;height:env(safe-area-inset-top,0px);visibility:hidden;pointer-events:none';
document.body.appendChild(pr);
function set(){var o=innerWidth>innerHeight?'l':'p',h=pr.offsetHeight;
if(max[o]==null)try{max[o]=+localStorage.getItem(K+o)||0;}catch(e){max[o]=0;}
if(h>max[o]){max[o]=h;try{localStorage.setItem(K+o,String(h));}catch(e){}}
document.documentElement.style.setProperty('--sat',max[o]?'max(env(safe-area-inset-top,0px),'+max[o]+'px)':'env(safe-area-inset-top,0px)');}
set();if(window.ResizeObserver)new ResizeObserver(set).observe(pr);addEventListener('resize',set);})();
// The ⋯ menu's theme: the system's, or light / dark whatever it is --
// html[data-theme], kept by this browser (read again in page.html's head,
// before the page shows: no flash of the other one).
(function(){var KEY='mp-snapshot:theme';
function sync(){var t=document.documentElement.dataset.theme||'';
document.querySelectorAll('[data-theme-set]').forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.themeSet===t));});}
document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('[data-theme-set]');if(!b)return;e.stopPropagation();
var t=b.dataset.themeSet;if(t)document.documentElement.dataset.theme=t;else delete document.documentElement.dataset.theme;
try{if(t)localStorage.setItem(KEY,t);else localStorage.removeItem(KEY);}catch(err){}sync();},true);
sync();})();
