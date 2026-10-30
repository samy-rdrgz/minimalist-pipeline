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
var OKS=['ok','yes','oui','v','x','✓','✔','valid','validé','valide'],NOS=['no','non'];
var FIXED=['group','filename','description','description_exported','stable_version','wip_version','render','global'];
var NL=String.fromCharCode(10);
var esc=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});};
var cap=function(s){return s.charAt(0).toUpperCase()+s.slice(1);};
var pct=function(v){return v==null?'–':Math.round(v*100)+' %';};
function isDone(s){return s==='done'||s==='rework';}
function plural(n,w){return n+' '+w+(n===1?'':'s');}

/* ---------- images: each stored once (#data images), turned into blob URLs
once -- short src strings, however often the list is redrawn ---------- */
var urls={};
function img(id){if(!id)return '';if(urls[id])return urls[id];
try{var b=atob(DATA.images[id]),a=new Uint8Array(b.length);for(var i=0;i<b.length;i++)a[i]=b.charCodeAt(i);
urls[id]=URL.createObjectURL(new Blob([a],{type:'image/jpeg'}));}
catch(e){urls[id]='data:image/jpeg;base64,'+DATA.images[id];}return urls[id];}

/* ---------- items ---------- */
var byFile={},byName={};
D.forEach(function(it,i){it.i=i;byFile[it.file]=it;byName[it.name]=it;
it.tab=it.root==='library'?'library':it.kind;
it.tracked=Object.keys(it.states).length>0;
var open=it.notes.filter(function(n){return !n.closed;});
// Open threads, by where the page shows them: an open RTK under its
// department (none: the general retakes), the rest as notes.
it.rtkNotes={};it.genRtks=[];it.otherNotes=[];
open.forEach(function(n){if(n.type==='rtk'&&n.done===false){
if(n.deps.length)n.deps.forEach(function(d){(it.rtkNotes[d]=it.rtkNotes[d]||[]).push(n);});else it.genRtks.push(n);}});
it.todos={};open.forEach(function(n){if(n.type==='todo'&&n.done===false)n.deps.forEach(function(d){it.todos[d]=(it.todos[d]||0)+1;});});
it.openNotes=open.filter(function(n){return !(n.type==='rtk'&&n.done===false)&&!n.approval;});});
var tabs=TABS.filter(function(t){return D.some(function(it){return it.tab===t[0];});});
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
function mark(s){return s?'<i class="m '+s+'" title="'+LABEL[s]+'"></i>':'<i class="m na" title="Not required"></i>';}
// Under a department, one ◆ per kind of open entry, its colour saying
// whose: red a validation role's retake, orange the team's, grey a todo.
// The details are in its tip and in the file's panel.
function dia(cls,tip){return '<span class="rk'+cls+'" title="'+tip+'">◆</span>';}
function rkTag(it,d){var h='',r=it.rtk[d];
if(r)h+=dia(r==='team'?' team':'','An open retake on '+cap(d)+(r==='team'?', from the team':', from a validation role'));
else if(it.genRtks.length&&isDone(it.states[d])){var t=it.genRtks.every(function(n){return n.team;});
h+=dia(t?' team':'','A retake on no department'+(t?', from the team':', from a validation role')+': it holds back every done department');}
if((it.todos[d]||0)>0)h+=dia(' todo',plural(it.todos[d],'open todo')+' on '+cap(d));
return h;}
function okTag(it,d){var o=it.ok[d];if(!o)return '';
return '<span class="ok'+(o.old?' old':'')+'" title="'+esc(o.tip)+'">✓ '+esc(o.role)+'</span>';}
function under(it,d){var k=rkTag(it,d);return (k?'<span class="dias">'+k+'</span>':'')+okTag(it,d)+you(it,d);}

/* ---------- review state: as the page before (same key, same shape) ---------- */
var rv={author:'',role:'',date:'',files:{}};
var KEY='mp-review:'+META.project+':'+META.snapshot;
function entry(it){return rv.files[it.file]||(rv.files[it.file]={deps:{},all:false,text:'',desc:null});}
function peek(it){return rv.files[it.file]||{deps:{},all:false,text:'',desc:null};}
function changes(it){var e=rv.files[it.file];if(!e)return 0;
var n=Object.keys(e.deps).length+(e.all?1:0)+(e.text.trim()?1:0);
if(e.desc!==null&&e.desc.trim()&&e.desc.trim()!==it.desc)n++;return n;}
// What this review says of a department: 'ok' (its own ✓, or all done), 'no', or ''.
function verdict(it,d){var e=peek(it),v=e.deps[d];if(v)return v.ok?'ok':'no';
return e.all&&isDone(it.states[d])?'ok':'';}
function you(it,d){var v=verdict(it,d);if(!v)return '';
return v==='ok'?'<span class="you y" title="Validated in your review">✓ you</span>':
'<span class="you n" title="Sent back in your review">✕ you</span>';}
function retakes(t){return t.split(NL).filter(function(l){var w=l.trim().split(' ').filter(function(x){return x&&x.charAt(0)!=='[';});
return w.length&&w[0].toLowerCase().indexOf('note:')!==0;}).length;}
function summary(){var c={files:0,ok:0,rt:0,out:0,desc:0};D.forEach(function(it){if(!changes(it))return;var e=rv.files[it.file];c.files++;
Object.keys(e.deps).forEach(function(d){var v=e.deps[d];if(v.ok)c.ok++;else if(v.text.trim())c.rt+=retakes(v.text);else c.out++;});
if(e.all)Object.keys(it.states).forEach(function(d){if(isDone(it.states[d])&&!e.deps[d])c.ok++;});
c.rt+=retakes(e.text);if(e.desc!==null&&e.desc.trim()&&e.desc.trim()!==it.desc)c.desc++;});return c;}
function save(){try{localStorage.setItem(KEY,JSON.stringify(rv));}catch(e){}}

/* ---------- badges: only what the row shows nowhere else ---------- */
function flags(it){var h='',e=peek(it);
if(it.genRtks.length){var tm=it.genRtks.every(function(n){return n.team;});
h+='<span class="badge '+(tm?'b-team':'b-rtk')+'" title="An open retake on no department: it holds back every department">◆ General RTK'+(it.genRtks.length>1?' ×'+it.genRtks.length:'')+'</span>';}
if(e.text.trim())h+='<span class="badge b-rtk">✕ you · general retake</span>';
if(it.outdated)h+='<span class="badge b-check" title="Rendered from an older version than the last stable">⚠ Render outdated</span>';
if(it.to_check)h+='<span class="badge b-check" title="Rendered, not checked by the team yet">Render to check</span>';
if(e.desc!==null&&e.desc.trim()&&e.desc.trim()!==it.desc)h+='<span class="badge b-rev">✎ description</span>';
return h;}
function subline(it){var p=['<span class="vers">'+esc(it.versions||'not saved yet')+'</span>'];
if(it.shots.length>1)p.push('<span>'+plural(it.shots.length,'shot')+'</span>');
if(it.openNotes.length){var t=it.openNotes.some(function(n){return n.type==='todo';});
p.push('<span class="nn'+(t?' todo':'')+'">'+plural(it.openNotes.length,'open note')+'</span>');}
if(it.farm)p.push('<span class="farm'+(it.farm.state==='failed'?' fail':'')+'" title="In the farm: '+esc(it.farm.tip)+'">farm '+esc(it.farm.text)+'</span>');
return p.join('<i class="sep"> · </i>');}
/* ---------- header and summary ---------- */
var snapDate=new Date(META.snapshot);
var DAYS=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function fmtDay(d,year){return d.getDate()+' '+MONTHS[d.getMonth()]+(year?' '+d.getFullYear():'');}
function two(n){return ('0'+n).slice(-2);}
$('h-project').innerHTML=esc(META.project).replace(/([_-])/g,'$1<wbr>');
$('h-when').textContent=DAYS[snapDate.getDay()]+' '+fmtDay(snapDate,true)+', '+two(snapDate.getHours())+':'+two(snapDate.getMinutes());
$('h-by').textContent=META.exported_by?'exported by '+META.exported_by:'';
$('f-ver').textContent='v'+META.addon_version+' · one self-contained file, nothing loaded from the web';
document.title=META.project+' · snapshot '+fmtDay(snapDate,true);
(function(){var days=Math.floor((Date.now()-snapDate.getTime())/864e5);
if(days>=1){var a=$('age');a.hidden=false;a.textContent=days===1?'1 day old':days+' days old';
a.title='This page shows the project as it was then: it may have moved since.';}})();
// A Done's pace (done / expected): its band, as a progress spreadsheet's.
function band(done,exp){if(!exp)return null;var p=done/exp;
return p>=1.05?['ahead','ahead']:p>=1?['ontrack','on track']:p>=0.9?['slip','slightly behind']:['behind','behind'];}
function summaryCards(){var S=META.schedule,exp=S?S.expected:null,h='';
[['shot','Shots','shot'],['asset','Assets & libraries','file']].forEach(function(s){var done=META.progress[s[0]];if(done==null)return;
var n=D.filter(function(it){return it.kind===s[0];}).length,val=(META.validation||{})[s[0]],note='';
if(S){var b=band(done,exp),at=(S.at||{})[s[0]],pts=Math.round((done-exp)*100),cls=b?b[0]:'ontrack';
var word=pts>=0?'ahead':'behind',days=at?Math.abs(at.days):0;
note+=pts||days?'<span class="d-'+cls+'">'+(pts>=0?'▲ ':'▼ ')+plural(days,'working day')+' '+word+'</span>':'<span class="d-ontrack">on schedule</span>';
if(b)note+='<span class="pace p-'+cls+'" title="Done / expected: 105 % and more ahead, 100 to 105 % on track, 90 to 100 % slightly behind, under 90 % behind">Pace '+
Math.round(done/exp*100)+' %, '+b[1]+'</span>';}
note+='<span>'+plural(n,s[2])+'</span>';
h+='<div class="card"><div class="k-label">'+s[1]+'</div><div class="k-row"><span class="k-big">'+Math.round(done*100)+'<small> %</small></span>'+
(META.role&&val!=null?'<span class="k-valid" title="Validated by '+esc(META.role)+' (or an equivalent role) at the stable shown">'+pct(val)+' validated</span>':'')+'</div>'+
'<div class="track" title="Done '+pct(done)+(val!=null?' · validated '+pct(val):'')+(S?' · expected '+pct(exp):'')+'"><i class="f" style="width:'+done*100+'%"></i>'+
(val!=null?'<i class="v" style="width:'+Math.min(val,done)*100+'%"></i>':'')+(S?'<i class="x" style="left:'+exp*100+'%"></i>':'')+'</div>'+
'<div class="k-note">'+note+'</div></div>';});
if(S){var a=new Date(S.start),b2=new Date(S.end),y=a.getFullYear()!==b2.getFullYear();
h+='<div class="card sched"><div class="k-label">Schedule, on '+fmtDay(snapDate)+'</div><div class="k-row"><span class="k-big">Day '+S.elapsed_days+
'<small> / '+S.total_days+'</small></span><span style="font-size:14px;color:var(--ink-2)">'+pct(exp)+' expected</span></div>'+
'<div class="track"><i class="f" style="width:'+exp*100+'%"></i></div><div class="ends"><span>'+fmtDay(a,y)+'</span><span>'+fmtDay(b2,y)+'</span></div></div>';}
$('summary').innerHTML=h;}
var W=META.weights;
$('weights').textContent='Each required department counts the same: not started 0 %, in progress '+W.wip+' %, done but reworked since '+W.rework+
' %, done with an open RTK '+W.rtk+' %, done 100 %. A file averages its departments, a group its files.'+
(META.role?' Validated, apart: the share of the required departments '+META.role+' (or an equivalent role) validated at the stable shown -- a newer stable needs it again.':'');

/* ---------- the list ---------- */
var state={tab:tabs.length?tabs[0][0]:'shot',q:'',f:{},dep:'',open:{},untracked:{}};
var FILTERS={
rtk:function(it,d){return d?!!it.rtk[d]||it.genRtks.length>0:Object.keys(it.rtk).length>0||it.genRtks.length>0;},
notes:function(it){return it.openNotes.length>0||it.genRtks.length>0||Object.keys(it.rtkNotes).length>0;},
outdated:function(it){return it.outdated;},
tovalid:function(it,d){return d?isDone(it.states[d])&&!validNow(it,d):Object.keys(it.states).some(function(x){return isDone(it.states[x])&&!validNow(it,x);});},
todo:function(it,d){return d?it.states[d]&&!isDone(it.states[d]):it.tracked&&it.done<100;}};
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
'<span>'+D.filter(function(it){return it.tab===t[0];}).length+'</span></button>';}).join('');
var deps=depsOf(state.tab).filter(function(d){return D.some(function(it){return it.tab===state.tab&&d in it.states;});});
if(deps.indexOf(state.dep)<0)state.dep='';
$('depf').innerHTML='<option value="">All departments</option>'+deps.map(function(d){return '<option value="'+esc(d)+'"'+(d===state.dep?' selected':'')+'>'+esc(cap(d))+'</option>';}).join('');
$('depf').classList.toggle('on',!!state.dep);}
function render(){
document.querySelectorAll('.chipf').forEach(function(b){b.querySelector('b').textContent=D.filter(function(it){
return it.tab===state.tab&&(!state.dep||state.dep in it.states)&&FILTERS[b.dataset.f](it,state.dep);}).length;});
var items=D.filter(function(it){return match(it);});
var deps=depsOf(state.tab).filter(function(d){return items.some(function(it){return d in it.states;});});
// Many departments: narrower columns, never past the page.
var w=deps.length>7?56:deps.length>5?64:76;
var cols='112px minmax(0,1fr) '+deps.map(function(){return w+'px';}).join(' ')+' 84px';
var groups={},order=[];
items.forEach(function(it){if(!groups[it.group]){groups[it.group]=[];order.push(it.group);}groups[it.group].push(it);});
visible=[];var filt=filtering();
var h=order.map(function(g){
var all=groups[g],tr=all.filter(function(it){return it.tracked;}),un=all.filter(function(it){return !it.tracked;});
var done=avg(tr.map(function(i){return i.done;})),val=avg(tr.map(function(i){return i.valid;}));
var key=state.tab+g,closed=state.open[key]===false||(state.open[key]===undefined&&!tr.length&&!filt);
var rows=tr.concat(state.untracked[key]||filt?un:[]);
if(!closed)rows.forEach(function(it){visible.push(it.i);});
var head='<div class="thead" style="--cols:'+cols+'"><span></span><span></span>'+deps.map(function(d){return '<span class="d" title="'+esc(cap(d))+'">'+esc(cap(d))+'</span>';}).join('')+
'<span style="text-align:right">Done</span></div>';
var body=rows.map(function(it){
return '<div class="row" role="button" tabindex="0" data-i="'+it.i+'" style="--cols:'+cols+'">'+thumb(it)+
'<span class="r-name">'+nameHtml(it)+'<small>'+subline(it)+'</small><span class="flags">'+flags(it)+'</span></span>'+
deps.map(function(d){return '<span class="d">'+mark(it.states[d])+under(it,d)+'</span>';}).join('')+
'<span class="r-pct">'+(it.tracked?Math.round(it.done*100)+' %'+(META.role?'<span class="vv'+(it.valid?'':' z')+'">'+pct(it.valid)+' valid.</span>':''):'<span class="faint">–</span>')+'</span>'+
(it.tracked?'<span class="dl">'+deps.filter(function(d){return d in it.states;}).map(function(d){return '<span><b class="dn s-'+it.states[d]+'" title="'+LABEL[it.states[d]]+'">'+esc(cap(d))+'</b>'+under(it,d)+'</span>';}).join('')+'</span>':'')+'</div>';}).join('');
if(un.length&&!state.untracked[key]&&!filt)body+='<button class="untracked" data-g="'+esc(g)+'">+ '+plural(un.length,'file')+' with no tracked department</button>';
return '<div class="group'+(closed?' closed':'')+'"><button class="g-h" data-g="'+esc(g)+'"><span class="g-name"><i class="caret"></i>'+esc(g)+'<small>'+plural(all.length,'file')+'</small></span>'+
(done!=null?'<span class="tw"><span class="track"><i class="f" style="width:'+done*100+'%"></i>'+(META.role?'<i class="v" style="width:'+Math.min(val,done)*100+'%"></i>':'')+'</span></span>'+
'<span class="g-pct"><b>'+pct(done)+'</b>'+(META.role?' · <span style="color:var(--valid)">'+pct(val)+' valid.</span>':'')+'</span>':'<span></span><span class="g-pct faint">not tracked</span>')+
'</button><div class="rows">'+(tr.length?head:'')+body+'</div></div>';}).join('');
var others=filt?tabs.filter(function(t){return t[0]!==state.tab;}).map(function(t){return [t,D.filter(function(it){return it.tab===t[0]&&match(it,true);}).length];}).filter(function(x){return x[1];}):[];
$('list').innerHTML=(h||'<div class="empty">Nothing here.</div>')+others.map(function(x){return '<button class="untracked" data-other="'+x[0][0]+'" style="text-align:center">'+
plural(x[1],'match')+' in '+x[0][1].toLowerCase()+' ›</button>';}).join('');
if(cur!=null){var s=$('list').querySelector('.row[data-i="'+cur+'"]');if(s)s.classList.add('sel');}
countBar();}
$('list').addEventListener('click',function(e){var t;
if(e.target.closest('[data-zoom]'))return;
if((t=e.target.closest('[data-other]')))return setTab(t.dataset.other);
if((t=e.target.closest('.row')))return openPanel(+t.dataset.i);
if((t=e.target.closest('.untracked'))){state.untracked[state.tab+t.dataset.g]=true;return render();}
if((t=e.target.closest('.g-h'))){state.open[state.tab+t.dataset.g]=t.parentNode.classList.contains('closed');render();}});
$('list').addEventListener('keydown',function(e){var r=e.target.closest('.row');if(r&&(e.key==='Enter'||e.key===' ')){e.preventDefault();openPanel(+r.dataset.i);}});
function setTab(t){state.tab=t;drawTabs();render();}
$('seg').addEventListener('click',function(e){var b=e.target.closest('button');if(b)setTab(b.dataset.tab);});
$('depf').addEventListener('change',function(){state.dep=this.value;this.classList.toggle('on',!!state.dep);render();});
document.querySelectorAll('.chipf').forEach(function(b){b.addEventListener('click',function(){
state.f[b.dataset.f]=!state.f[b.dataset.f];b.setAttribute('aria-pressed',!!state.f[b.dataset.f]);render();});});
var bar=$('bar');
new IntersectionObserver(function(e){bar.classList.toggle('stuck',e[0].intersectionRatio<1);},{threshold:[1],rootMargin:'-1px 0px 0px 0px'}).observe(bar);
function barHeight(){document.documentElement.style.setProperty('--bar-h',bar.offsetHeight+'px');}
addEventListener('resize',barHeight);

/* ---------- find: filters the list, and jumps to any file ---------- */
var sugg=$('sugg'),hi=-1,found=[];
function suggest(){var q=state.q;hi=-1;if(!q){sugg.hidden=true;return;}
found=D.filter(function(it){return it.name.toLowerCase().indexOf(q)>=0;}).slice(0,8);
if(!found.length){sugg.hidden=true;return;}
sugg.innerHTML=found.map(function(it,n){return '<li><button type="button" role="option" data-n="'+n+'"><span>'+nameHtml(it)+'</span><small>'+
TABS.filter(function(t){return t[0]===it.tab;})[0][1]+'</small></button></li>';}).join('');sugg.hidden=false;}
function pick(n){var it=found[n];if(!it)return;sugg.hidden=true;$('q').blur();jump(it);}
function jump(it){if(it.tab!==state.tab)setTab(it.tab);var k=state.tab+it.group;if(state.open[k]===false)state.open[k]=true;
if(!it.tracked)state.untracked[k]=true;render();openPanel(it.i);}
$('q').addEventListener('input',function(){state.q=this.value.trim().toLowerCase();render();suggest();});
$('q').addEventListener('focus',suggest);
$('q').addEventListener('keydown',function(e){var b=sugg.querySelectorAll('button');
if(e.key==='ArrowDown'||e.key==='ArrowUp'){if(sugg.hidden)return;e.preventDefault();hi=(hi+(e.key==='ArrowDown'?1:-1)+b.length)%b.length;
b.forEach(function(x,n){x.classList.toggle('hi',n===hi);});}
else if(e.key==='Enter'){e.preventDefault();pick(hi<0?0:hi);}});
sugg.addEventListener('mousedown',function(e){e.preventDefault();});
sugg.addEventListener('click',function(e){var b=e.target.closest('button');if(b)pick(+b.dataset.n);});
$('q').addEventListener('blur',function(){setTimeout(function(){sugg.hidden=true;},150);});

/* ---------- menus ---------- */
var MENUS=[['more','morepop'],['helpb','helppop'],['rv-more','rv-morepop']];
function closeMenus(){MENUS.forEach(function(m){$(m[1]).hidden=true;$(m[0]).setAttribute('aria-expanded','false');});}
MENUS.forEach(function(m){$(m[0]).addEventListener('click',function(e){e.stopPropagation();var open=$(m[1]).hidden;closeMenus();
$(m[1]).hidden=!open;this.setAttribute('aria-expanded',open);});});
document.addEventListener('click',function(e){if(!e.target.closest('.menu-pop'))closeMenus();});

/* ---------- pictures and videos ---------- */
var hov=$('hover'),fine=matchMedia('(hover:hover) and (pointer:fine)');
// With a mouse only: a tap is not a hover, the picture would stay open.
document.addEventListener('mouseover',function(e){var t=e.target.closest('.row .thumb[data-zoom]');if(!t||!fine.matches)return;
hov.onload=function(){var r=t.getBoundingClientRect(),w=hov.offsetWidth,h=hov.offsetHeight;
hov.style.left=Math.max(8,Math.min(r.left,innerWidth-w-8))+'px';hov.style.top=(r.bottom+8+h<innerHeight?r.bottom+8:Math.max(8,r.top-8-h))+'px';};
hov.src=img(D[t.dataset.zoom].thumb);hov.style.display='block';});
document.addEventListener('mouseout',function(e){if(e.target.closest('.thumb'))hov.style.display='none';});
function lightbox(html,cap){$('lb-in').innerHTML=html;$('lb-cap').innerHTML=cap||'';$('lb').hidden=false;hov.style.display='none';}
function closeLb(){var v=$('lb-in').querySelector('video');if(v)v.pause();$('lb').hidden=true;$('lb-in').innerHTML='';}
$('lb').addEventListener('click',function(e){if(e.target===this||e.target.closest('#lb-x')||e.target.tagName==='IMG')closeLb();});
document.addEventListener('click',function(e){var t=e.target.closest('[data-zoom]');if(!t)return;e.stopPropagation();var it=D[t.dataset.zoom];
lightbox('<img alt="" src="'+img(it.thumb)+'">',esc(it.name));},true);
// A render's video in the zip made with the snapshot (same name), unzipped
// beside this page: <zip>/sq060/sq060_sh070_v012-stable_001.mp4,
// <zip>/assets/env/env_sol-lac_v002-stable_001.mp4 (lib/preview.py).
function videoOf(it,r){var V=META.videos;if(!V||!r.folder)return null;
if(it.kind==='shot'){if(V.sequences.indexOf(it.group)<0)return null;
var seg=r.whole||it.shots.length<2?it.name.slice(it.group.length+1):r.shot_list[0];
return V.zip+'/'+it.group+'/'+it.group+'_'+seg+'_'+r.folder+'.mp4';}
if(!V.assets)return null;return V.zip+'/'+it.root+'/'+it.group+'/'+it.name+'_'+r.folder+'.mp4';}
// One render, or a block's renders in a row (its shots' order): each
// video starts the next once ended, ‹ › skip.
function play(it,n,all){var list=all?it.renders.map(function(r,k){return k;}).filter(function(k){return videoOf(it,it.renders[k]);}):[n];
var at=Math.max(0,list.indexOf(n));
function show(){var k=list[at],r=it.renders[k],src=videoOf(it,r);
lightbox('<video controls autoplay playsinline src="'+esc(src)+'"></video>',
(list.length>1?'<button type="button" class="lbn" data-lb="-1"'+(at?'':' disabled')+' aria-label="Previous render">‹</button> ':'')+
esc(it.name)+(r.shots?' · <b>'+esc(r.shots)+'</b>':'')+' · '+esc(r.folder)+(list.length>1?' ('+(at+1)+' / '+list.length+')':'')+
(list.length>1?' <button type="button" class="lbn" data-lb="1"'+(at<list.length-1?'':' disabled')+' aria-label="Next render">›</button>':''));
var v=$('lb-in').querySelector('video');
v.addEventListener('ended',function(){if(at<list.length-1){at++;show();}});
v.addEventListener('error',function(){$('lb-in').innerHTML='';
$('lb-cap').innerHTML='Video not found. Unzip <code>'+esc(META.videos.zip)+'.zip</code> next to this page, into a folder of the same name, then try again.'+
'<br><span style="opacity:.7">Looked for <code>'+esc(src)+'</code></span>';});}
$('lb-cap').onclick=function(e){var b=e.target.closest('[data-lb]');if(!b||b.disabled)return;e.stopPropagation();at+=+b.dataset.lb;show();};
show();}

/* ---------- progress details ---------- */
function stats(){var S=META.schedule,exp=S?S.expected:null,h='';
var line=exp!=null?'<i class="x" style="left:'+exp*100+'%"></i>':'';
function bars(title,rows){rows=rows.filter(function(r){return r[1]!=null;});if(!rows.length)return '';
return '<div class="card"><h4>'+title+(exp!=null?'<small>| expected '+pct(exp)+'</small>':'')+'</h4><div class="hb">'+rows.map(function(r){
return '<span title="'+esc(r[2]||'')+'">'+esc(r[0])+'</span><span class="track"><i class="f" style="width:'+r[1]*100+'%"></i>'+line+'</span><span class="n">'+pct(r[1])+'</span>';}).join('')+'</div></div>';}
[['shot','Shots','By sequence','Sequence'],['asset','Assets & libraries','By prefix','Prefix']].forEach(function(s){
var items=D.filter(function(it){return it.kind===s[0]&&it.tracked;});if(!items.length)return;
var deps=depsOf(s[0]).filter(function(d){return items.some(function(it){return d in it.scores;});});
var groups={},order=[];items.forEach(function(it){if(!groups[it.group]){groups[it.group]=[];order.push(it.group);}groups[it.group].push(it);});
var dep=function(list,d){return avg(list.map(function(it){return d in it.scores?it.scores[d]:null;}));};
var grid='<div class="card hm-card"><h4>'+s[3]+' × department</h4><table class="hm"><thead><tr><th></th>'+deps.map(function(d){return '<th>'+esc(cap(d))+'</th>';}).join('')+
'</tr></thead><tbody>'+order.map(function(g){return '<tr><th>'+esc(g)+'</th>'+deps.map(function(d){var v=dep(groups[g],d);
return v==null?'<td class="na">–</td>':'<td style="background:color-mix(in srgb,var(--done) '+Math.round(6+v*44)+'%,var(--surface))" title="'+esc(g+', '+cap(d)+': '+pct(v))+'">'+pct(v)+'</td>';}).join('')+'</tr>';}).join('')+'</tbody></table></div>';
h+='<div class="st-sec"><h3>'+s[1]+'</h3><div class="st-grid">'+
bars(s[2],order.map(function(g){return [g,avg(groups[g].map(function(i){return i.done;})),plural(groups[g].length,'file')];}))+
bars('By department',deps.map(function(d){return [cap(d),dep(items,d)];}))+grid+'</div></div>';});
$('stats').innerHTML=h+'<p class="weights">'+esc($('weights').textContent)+'</p>';}

/* ---------- a file's panel ---------- */
var cur=null,lastFocus=null,showClosed=false,showNotes=null,editing={};
function reviewing(){return document.body.classList.contains('reviewing');}
// A retake's box. A block's: one for all its shots, then one per shot
// opened by its button -- written back as one text, each line of a
// shot's box tagged "[sh040] ", as the import reads it.
var BOX={};
function boxOf(it,key,text){var k=it.file+'|'+key,b=BOX[k];if(b&&b.text===text)return b;
b={all:[],per:{},open:{},text:text};(text||'').split(NL).forEach(function(l){var m=l.match(/^\s*\[([a-z]*\d+)\]\s?(.*)$/i),sh=m&&m[1].toLowerCase();
if(sh&&it.shots.indexOf(sh)>=0){(b.per[sh]=b.per[sh]||[]).push(m[2]);b.open[sh]=true;}else b.all.push(l);});
b.all=b.all.join(NL);Object.keys(b.per).forEach(function(sh){b.per[sh]=b.per[sh].join(NL);});return BOX[k]=b;}
function joinBox(it,b){var out=b.all.split(NL).filter(function(l){return l.trim();});
it.shots.forEach(function(sh){if(b.open[sh]&&b.per[sh])b.per[sh].split(NL).forEach(function(l){if(l.trim())out.push('['+sh+'] '+l);});});
return b.text=out.join(NL);}
function retakeBox(it,key,text,ph){
if(it.shots.length<2)return '<textarea class="rtk-t" data-k="'+esc(key)+'"'+(key==='gen'?' id="gen-t"':'')+' placeholder="'+esc(ph)+'">'+esc(text)+'</textarea>';
var b=boxOf(it,key,text);
return '<div class="rbox"><textarea class="rtk-t" data-k="'+esc(key)+'" data-s=""'+(key==='gen'?' id="gen-t"':'')+' placeholder="'+esc(ph)+' -- all its shots">'+esc(b.all)+'</textarea>'+
'<div class="tags" data-k="'+esc(key)+'"><span>One shot:</span>'+it.shots.map(function(sh){return '<button type="button" data-shot="'+esc(sh)+'" aria-pressed="'+!!b.open[sh]+'">'+esc(sh)+'</button>';}).join('')+'</div>'+
it.shots.filter(function(sh){return b.open[sh];}).map(function(sh){return '<label class="shotbox"><span>'+esc(sh)+'</span><textarea class="rtk-t" data-k="'+esc(key)+'" data-s="'+esc(sh)+'" placeholder="What to fix in '+esc(sh)+'?">'+esc(b.per[sh]||'')+'</textarea></label>';}).join('')+'</div>';}
function syntax(it){return '<p class="syntax">One retake per line · <code>[f12-40]</code> frames · <code>note:</code> a remark, not a retake</p>';}
function noteHtml(n,reply){var type=n.done===true?'<span class="badge b-done" title="Done">✓ '+esc(n.type)+'</span>':
'<span class="badge '+(n.type==='rtk'?(n.team?'b-team':'b-rtk'):n.type==='todo'?'b-todo':'b-note')+'">'+esc(n.type)+(n.type==='rtk'&&n.team?' · team':'')+'</span>';
var tags=[];if(n.role)tags.push('<span class="tg role" title="Written as '+esc(n.role)+'">'+esc(n.role)+'</span>');
if(n.review)tags.push('<span class="tg">prod review</span>');
n.deps.forEach(function(d){tags.push('<span class="tg">'+esc(d)+'</span>');});
if(n.shot)tags.push('<span class="tg">'+esc(n.shot)+'</span>');if(n.frames)tags.push('<span class="tg">'+esc(n.frames)+'</span>');
if(n.render)tags.push('<span class="tg" title="Written watching this render">▶ '+esc(n.render)+'</span>');else if(n.version)tags.push('<span class="tg">'+esc(n.version)+'</span>');
return '<div class="note'+(n.closed?' closed':'')+(reply?' reply':'')+(n.role?' by-role':'')+'"><div class="h">'+type+tags.join('')+
'<span class="who">'+esc(n.author)+' · '+esc((n.date||'').slice(0,10))+'</span></div><p>'+esc(n.text)+'</p></div>'+
(n.replies||[]).map(function(r){return noteHtml(Object.assign({closed:n.closed},r),true);}).join('');}
function rtkLine(n){var where=[n.shot,n.frames].filter(Boolean).join(' · ');
return '<div class="rtkl'+(n.team?' team':'')+'">'+(where?'<b>'+esc(where)+'</b> ':'')+esc(n.text)+'<small>'+(n.team?'team · ':esc(n.role||'')+' · ')+esc(n.author)+' · '+esc((n.date||'').slice(0,10))+'</small></div>';}
function rendersHtml(it){
if(!it.renders.length)return '<span class="faint">'+(it.kind==='shot'?'Not rendered yet':'No render')+'</span>';
return '<div class="renders">'+it.renders.map(function(r,n){var v=videoOf(it,r);
var st=r.status?'<span class="ss'+(r.status.state==='failed'?' fail':'')+'" title="'+esc(r.status.tip)+'">'+esc(r.status.text)+'</span>':'';
return '<span class="sh">'+esc(r.shots||(it.kind==='shot'?'all shots':''))+'</span><span'+(r.behind?' class="bh" title="Rendered from an older version than the last stable">⚠ ':'>')+
esc(r.folder||r.pending||'not rendered')+(r.behind?'<small>stable is '+esc(it.stable_v)+'</small>':'')+st+'</span>'+
(v?'<button type="button" class="pl" data-play="'+n+'">▶ Play</button>':'<span></span>');}).join('')+'</div>';}
function depHtml(it,d,rv){var s=it.states[d],e=peek(it),v=e.deps[d],o=it.ok[d],via=!v&&e.all&&isDone(s);
var okd=o?(o.old?'<span class="ok old" title="'+esc(o.tip)+'">✓ '+esc(o.role)+' on '+esc(o.seen)+'</span><span class="faint" style="font-size:12px">to review again</span>':
'<span class="ok" title="'+esc(o.tip)+'">✓ '+esc(o.role)+'</span>'):'';
return '<div class="dep"><div class="dep-l">'+mark(s)+'<span class="mid"><span class="nm">'+esc(cap(d))+'</span><span class="st">'+LABEL[s]+'</span>'+rkTag(it,d)+okd+you(it,d)+'</span>'+
'<span class="rvb" data-d="'+esc(d)+'"><button class="ok-b'+(via?' via':'')+'" aria-pressed="'+!!(v&&v.ok)+'"'+(isDone(s)?' title="Validate it as your role"':' disabled title="Not done: nothing to validate yet"')+
' aria-label="Validate '+esc(d)+'">✓</button><button class="ko-b" aria-pressed="'+!!(v&&v.no)+'" aria-label="Retake '+esc(d)+'" title="Retake: write what to fix (or nothing, to withdraw a validation)">✕</button></span></div>'+
((it.rtkNotes[d]||[]).length?'<div class="rtks">'+it.rtkNotes[d].map(rtkLine).join('')+'</div>':'')+
(rv&&v&&v.no?'<div class="rt">'+retakeBox(it,'d:'+d,v.text,'What to fix in '+d+'? Empty: just withdraw its validation')+syntax(it)+'</div>':'')+'</div>';}
function openPanel(i){
var it=D[i];if(cur!==i){showClosed=false;showNotes=null;editing={};}cur=i;if(!lastFocus)lastFocus=document.activeElement;
var rv=reviewing(),e=peek(it);if(showNotes===null)showNotes=!rv;
$('p-title').innerHTML=nameHtml(it);
$('p-sub').textContent=[it.kind==='shot'?'Shot':it.root==='library'?'Library':'Asset',it.versions,it.shots.length>1?plural(it.shots.length,'shot'):''].filter(Boolean).join(' · ');
// First what it is and how far along, big; then its departments; the
// rest after, quieter.
$('p-kpi').innerHTML=it.tracked?'<span class="kd">'+Math.round(it.done*100)+'<small> %</small></span><span class="kl">done</span>'+
(META.role?'<span class="kv">'+pct(it.valid)+'</span><span class="kl">validated</span>':'')+
'<span class="track"><i class="f" style="width:'+it.done*100+'%"></i>'+(META.role?'<i class="v" style="width:'+Math.min(it.valid,it.done)*100+'%"></i>':'')+'</span>':'';
$('p-flags').innerHTML=flags(it);
var deps=depsOf(it.kind).filter(function(d){return d in it.states;});
var h='<div class="p-media">'+(it.thumb?'<button type="button" class="big" id="bigb" aria-label="Full size"><img id="bigimg" alt="" src="'+img(it.thumb)+'"></button>':'<span class="thumb none"><span class="frame"></span></span>')+
(it.shot_thumbs.length?'<div class="shotsel">'+[['whole block',it.thumb]].concat(it.shot_thumbs).map(function(s,n){
return '<button type="button" data-src="'+(s[1]?img(s[1]):'')+'" aria-pressed="'+(n===0)+'"'+(s[1]?'':' disabled')+'><span class="frame">'+(s[1]?'<img alt="" src="'+img(s[1])+'">':'')+'</span>'+esc(s[0])+(s[1]?'':' · not rendered')+'</button>';}).join('')+'</div>':'')+
(function(){var n=it.renders.filter(function(r){return videoOf(it,r);}).length;
return !n?'':n===1?'<button type="button" class="play" data-play="'+it.renders.map(function(r){return !!videoOf(it,r);}).indexOf(true)+'">▶ Play the render</button>':
'<button type="button" class="play" data-playall="1" title="Each shot\'s render, in the block\'s order">▶ Play the '+n+' renders in a row</button>';})()+'</div>';
// The description first: what the file is.
if(rv&&(editing.desc||e.desc!==null))h+='<div class="p-block"><h4>Description<span class="h-sub">sent with the review</span></h4><textarea id="desc-t" placeholder="What this file is, for the team">'+esc(e.desc!==null?e.desc:it.desc)+'</textarea></div>';
else{if(it.desc)h+='<p class="desc">'+esc(it.desc)+'</p>';
if(rv)h+='<button type="button" class="desc-edit" id="add-desc">✎ '+(it.desc?'Edit the description':'Add a description')+'</button>';}
// The departments, between two rows of the same buttons: "All done" (✓
// every done one, V) on top, "Whole file" (✕ a retake on no department,
// X) at the bottom -- with the open ones on no department.
var anyDone=deps.some(function(d){return isDone(it.states[d]);}),genOpen=editing.gen||!!e.text;
h+='<div class="p-block major">'+
(rv&&anyDone?'<div class="dep all"><div class="dep-l"><span class="mid"><span class="nm">All done</span><span class="st">validate every done department · V</span></span>'+
'<span class="rvb"><button class="ok-b" id="allok" aria-pressed="'+e.all+'" aria-label="Validate every done department">✓</button><span class="rvb-gap"></span></span></div></div>':'')+
(deps.length?deps.map(function(d){return depHtml(it,d,rv);}).join(''):'<p class="faint">No department tracked on this file.</p>')+
(rv||it.genRtks.length?'<div class="dep whole"><div class="dep-l"><span class="mid"><span class="nm">Whole file</span><span class="st">a retake on no department'+(rv?' · X':'')+'</span></span>'+
'<span class="rvb"><span class="rvb-gap"></span><button class="ko-b" id="add-gen" aria-pressed="'+genOpen+'" aria-label="A retake on no department">✕</button></span></div>'+
(it.genRtks.length?'<div class="rtks">'+it.genRtks.map(rtkLine).join('')+'</div>':'')+
(rv&&genOpen?'<div class="rt">'+retakeBox(it,'gen',e.text,'What to fix, on no department in particular?')+syntax(it)+'</div>':'')+'</div>':'')+
'</div>';
// Notes: the rest, open first; the closed ones on demand.
var closed=it.notes.filter(function(n){return n.closed;}),shown=it.openNotes.concat(showClosed?closed:[]);
// No open note: one quiet line to show the closed ones, no heading.
if(!it.openNotes.length&&closed.length&&!showClosed)h+='<div class="p-block"><button type="button" class="more-notes quiet" id="tog-closed">'+plural(closed.length,'closed note')+' ›</button></div>';
else if(it.openNotes.length||closed.length){h+='<div class="p-block"><button type="button" class="fold" id="tog-notes" aria-expanded="'+showNotes+'">'+
(it.openNotes.length?plural(it.openNotes.length,'open note'):'Notes')+(closed.length?' · '+closed.length+' closed':'')+'</button>';
if(showNotes)h+=shown.map(function(n){return noteHtml(n);}).join('')+(closed.length?'<button type="button" class="more-notes" id="tog-closed">'+(showClosed?'Hide the closed ones':'Show the '+closed.length+' closed')+'</button>':'');
h+='</div>';}
// Where it comes from: at the bottom, out of the way while reviewing.
h+='<dl class="view-only facts"><dt>Last render</dt><dd>'+rendersHtml(it)+'</dd><dt>Blender file</dt><dd class="fileline">'+esc(it.file)+'.blend</dd></dl>';
$('p-body').innerHTML=h;$('p-body').querySelectorAll('textarea').forEach(grow);
document.body.classList.add('panel-open');var p=$('panel');p.hidden=false;
requestAnimationFrame(function(){p.classList.add('on');$('scrim').classList.add('on');});
var pos=visible.indexOf(i);$('p-prev').disabled=$('m-prev').disabled=pos<=0;$('p-next').disabled=$('m-next').disabled=pos<0||pos>=visible.length-1;
document.querySelectorAll('.row.sel').forEach(function(x){x.classList.remove('sel');});
var s=$('list').querySelector('.row[data-i="'+i+'"]');if(s){s.classList.add('sel');
// Beside the list: the file shown stays in sight as ← → go through it.
var r=s.getBoundingClientRect(),top=bar.getBoundingClientRect().bottom+40;if(!phone.matches&&(r.top<top||r.bottom>innerHeight))scrollBy({top:r.top-top-(innerHeight-top)/3,behavior:'smooth'});}
p.setAttribute('aria-modal',phone.matches?'true':'false');
try{history.replaceState(null,'','#'+encodeURIComponent(it.name));}catch(err){}}
function refresh(){var y=$('p-body').scrollTop;openPanel(cur);$('p-body').scrollTop=y;render();save();}
function closePanel(){if(cur==null)return;cur=null;document.body.classList.remove('panel-open');var p=$('panel');p.classList.remove('on');$('scrim').classList.remove('on');
setTimeout(function(){if(cur==null)p.hidden=true;},220);document.querySelectorAll('.row.sel').forEach(function(x){x.classList.remove('sel');});
try{history.replaceState(null,'',location.pathname+location.search);}catch(err){}
if(lastFocus)lastFocus.focus({preventScroll:true});lastFocus=null;}
function step(n){var pos=visible.indexOf(cur);if(pos<0)return;var j=visible[pos+n];if(j!=null){openPanel(j);$('p-body').scrollTop=0;}}
$('p-close').addEventListener('click',closePanel);$('scrim').addEventListener('click',closePanel);
$('p-prev').addEventListener('click',function(){step(-1);});$('p-next').addEventListener('click',function(){step(1);});
$('m-prev').addEventListener('click',function(){step(-1);});$('m-next').addEventListener('click',function(){step(1);});
$('p-link').addEventListener('click',function(){var u=location.href;
var ok=function(){toast('Link copied: it opens this file, once this page is where the link points.');};
if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(u).then(ok,function(){prompt('Link to this file',u);});else prompt('Link to this file',u);});
// A phone: swipe down from the top to close, sideways for the next / previous file
// (not on the shots' strip nor in a field, which scroll or select).
var t0=null;$('panel').addEventListener('touchstart',function(e){var t=e.touches[0];
t0=e.target.closest('textarea,input,select,.shotsel')?null:{x:t.clientX,y:t.clientY,top:$('p-body').scrollTop<=0};},{passive:true});
$('panel').addEventListener('touchend',function(e){if(!t0)return;var t=e.changedTouches[0],dx=t.clientX-t0.x,dy=t.clientY-t0.y;
if(Math.abs(dx)>70&&Math.abs(dx)>2*Math.abs(dy))step(dx<0?1:-1);else if(t0.top&&dy>90&&dy>2*Math.abs(dx))closePanel();t0=null;});
// Focus stays in the open panel.
var phone=matchMedia('(max-width:640px)');
// The panel's width, dragged by its left edge -- kept by this browser.
var PW_KEY='mp-snapshot:panel-width',PW_DEF=540;
function setWidth(w,keep){w=Math.round(Math.max(380,Math.min(w,innerWidth-360,innerWidth*0.8)));
document.documentElement.style.setProperty('--pw',w+'px');if(keep)try{localStorage.setItem(PW_KEY,String(w));}catch(e){}return w;}
try{var pw=+localStorage.getItem(PW_KEY);if(pw)setWidth(pw);}catch(e){}
var rz=$('p-resize');
rz.addEventListener('pointerdown',function(e){e.preventDefault();rz.setPointerCapture(e.pointerId);document.body.classList.add('resizing');});
rz.addEventListener('pointermove',function(e){if(document.body.classList.contains('resizing'))setWidth(innerWidth-e.clientX,false);});
rz.addEventListener('pointerup',function(e){if(!document.body.classList.contains('resizing'))return;document.body.classList.remove('resizing');setWidth(innerWidth-e.clientX,true);});
rz.addEventListener('dblclick',function(){setWidth(PW_DEF,true);});
rz.addEventListener('keydown',function(e){if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return;e.preventDefault();e.stopPropagation();
setWidth($('panel').offsetWidth+(e.key==='ArrowLeft'?40:-40),true);});
$('panel').addEventListener('keydown',function(e){if(e.key!=='Tab'||!phone.matches)return;var f=[].filter.call($('panel').querySelectorAll('button,textarea,[tabindex]'),function(x){return !x.disabled&&x.offsetParent;});
if(!f.length)return;var a=f[0],z=f[f.length-1];if(e.shiftKey&&document.activeElement===a){z.focus();e.preventDefault();}else if(!e.shiftKey&&document.activeElement===z){a.focus();e.preventDefault();}});
var FS=window.CSS&&CSS.supports('field-sizing','content');
function grow(t){if(FS||!t)return;t.style.height='auto';t.style.height=Math.min(t.scrollHeight+2,innerHeight*.5)+'px';}
function setText(it,key,text){var e=entry(it);if(key==='gen')e.text=text;else if(e.deps[key.slice(2)])e.deps[key.slice(2)].text=text;}
function validateAll(){var it=D[cur];if(!Object.keys(it.states).some(function(d){return isDone(it.states[d]);}))return;var e=entry(it);e.all=!e.all;refresh();}
function generalRetake(){var e=entry(D[cur]);if(editing.gen||e.text){if(!e.text.trim()||confirm('Drop this general retake?')){e.text='';editing.gen=false;refresh();}return;}
editing.gen=true;refresh();var g=$('gen-t');if(g)g.focus();}
$('p-body').addEventListener('click',function(ev){var t,it=D[cur];
if((t=ev.target.closest('[data-playall]')))return play(it,it.renders.map(function(r){return !!videoOf(it,r);}).indexOf(true),true);
if((t=ev.target.closest('[data-play]')))return play(it,+t.dataset.play);
if(ev.target.closest('#bigb'))return lightbox('<img alt="" src="'+$('bigimg').src+'">',esc(it.name));
if((t=ev.target.closest('.shotsel button'))){$('bigimg').src=t.dataset.src;t.parentNode.querySelectorAll('button').forEach(function(x){x.setAttribute('aria-pressed',x===t);});return;}
if((t=ev.target.closest('.tags [data-shot]'))){var key=t.parentNode.dataset.k,sh=t.dataset.shot,txt=key==='gen'?entry(it).text:(entry(it).deps[key.slice(2)]||{}).text||'',b=boxOf(it,key,txt);
if(b.open[sh]&&(b.per[sh]||'').trim()&&!confirm('Drop what you wrote for '+sh+'?'))return;
b.open[sh]=!b.open[sh];if(!b.open[sh])delete b.per[sh];setText(it,key,joinBox(it,b));refresh();
if(b.open[sh]){var ta3=$('p-body').querySelector('textarea[data-k="'+CSS.escape(key)+'"][data-s="'+CSS.escape(sh)+'"]');if(ta3)ta3.focus();}return;}
if(ev.target.closest('#tog-closed')){showClosed=!showClosed;showNotes=true;return refresh();}
if(ev.target.closest('#tog-notes')){showNotes=!showNotes;return refresh();}
if(ev.target.closest('#add-gen'))return generalRetake();
if(ev.target.closest('#add-desc')){editing.desc=true;entry(it).desc=it.desc;refresh();return $('desc-t').focus();}
if(ev.target.closest('#allok'))return validateAll();
if((t=ev.target.closest('.rvb button'))&&!t.disabled){var d=t.parentNode.dataset.d,e=entry(it),v=e.deps[d];
if(t.classList.contains('ok-b')){if(v&&v.ok)delete e.deps[d];else e.deps[d]={ok:1};refresh();}
else{if(v&&v.no)delete e.deps[d];else e.deps[d]={no:1,text:''};refresh();
if(e.deps[d]){var ta2=$('p-body').querySelector('textarea[data-k="'+CSS.escape('d:'+d)+'"]');if(ta2)ta2.focus();}}}});
$('p-body').addEventListener('input',function(ev){var t=ev.target,it=D[cur],e=entry(it);if(t.tagName!=='TEXTAREA')return;grow(t);
if(t.dataset.k){var k=t.dataset.k;if(t.dataset.s==null)setText(it,k,t.value);else{var b=boxOf(it,k,k==='gen'?e.text:(e.deps[k.slice(2)]||{}).text||'');
if(t.dataset.s)b.per[t.dataset.s]=t.value;else b.all=t.value;setText(it,k,joinBox(it,b));}}else if(t.id==='desc-t')e.desc=t.value;
$('p-flags').innerHTML=flags(it);var row=$('list').querySelector('.row[data-i="'+cur+'"] .flags');if(row)row.innerHTML=flags(it);countBar();save();});

/* ---------- keys, as the page before ---------- */
document.addEventListener('keydown',function(e){var t=e.target;
if(t.matches&&t.matches('input,textarea,select')){if(e.key==='Escape'){t.blur();e.preventDefault();}
else if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){t.blur();e.preventDefault();}return;}
if(e.altKey||e.ctrlKey||e.metaKey)return;
if(!$('lb').hidden){if(e.key==='Escape'){closeLb();e.preventDefault();}
else if(e.key==='ArrowLeft'||e.key==='ArrowRight'){var nb=$('lb-cap').querySelector('[data-lb="'+(e.key==='ArrowLeft'?-1:1)+'"]');if(nb&&!nb.disabled){nb.click();e.preventDefault();}}return;}
if(!$('dlg').hidden){if(e.key==='Escape'){$('dlg').hidden=true;e.preventDefault();}return;}
if(e.key==='Escape'&&MENUS.some(function(m){return !$(m[1]).hidden;})){closeMenus();return;}
if(cur==null)return;var k=e.key.toLowerCase();
if(k==='arrowleft')step(-1);else if(k==='arrowright')step(1);else if(k==='escape')closePanel();
else if(reviewing()&&k==='v')validateAll();else if(reviewing()&&k==='x')generalRetake();
else return;e.preventDefault();});

/* ---------- review: the bar, the download, loading one back ---------- */
var toastT;function toast(t){var el=$('toast');el.textContent=t;el.classList.add('on');clearTimeout(toastT);toastT=setTimeout(function(){el.classList.remove('on');},4200);}
(META.roles||[]).forEach(function(r){var o=document.createElement('option');o.value=r;o.textContent=r;$('role').appendChild(o);});
function countBar(){var c=summary();$('rv-n').textContent=c.files?plural(c.files,'file')+' reviewed':'Nothing reviewed yet';
document.querySelector('#rv-dl .cnt').textContent=c.files||'';$('rv-fabn').textContent=c.files||'';}
// The bar folds into a round button (remembered by this browser), never
// while it still needs a name.
var FOLD=KEY+':folded';
function fold(on){document.body.classList.toggle('rb-folded',on);try{localStorage.setItem(FOLD,on?'1':'');}catch(e){}
if(!on)$('rv-dl').focus({preventScroll:true});}
$('rv-min').addEventListener('click',function(){fold(true);});
$('rv-fab').addEventListener('click',function(){fold(false);});
function setReview(on){document.body.classList.toggle('reviewing',on);
var folded=false;try{folded=localStorage.getItem(FOLD)==='1';}catch(e){}
document.body.classList.toggle('rb-folded',on&&folded&&!!$('author').value.trim());showNotes=null;editing={};if(on&&!$('author').value)$('author').focus();if(cur!=null)openPanel(cur);}
$('rv').addEventListener('click',function(){setReview(true);});
$('rv-exit').addEventListener('click',function(){closeMenus();setReview(false);toast('Review left: it stays in this browser, ✎ Review takes it back.');});
$('rv-clear').addEventListener('click',function(){closeMenus();if(!summary().files||confirm('Clear this review? What you wrote here is lost (a downloaded file is kept).')){
rv.files={};save();render();if(cur!=null)openPanel(cur);}});
$('author').addEventListener('input',function(){this.classList.remove('need');rv.author=this.value;save();});
$('role').addEventListener('change',function(){this.classList.remove('need');rv.role=this.value;save();});
function exportRows(){var out=[];D.forEach(function(it){if(!changes(it))return;var e=rv.files[it.file],
row={filename:it.file,stable_version:it.stable,description_exported:it.desc};if(it.render_ref)row.render=it.render_ref;
Object.keys(e.deps).forEach(function(d){var v=e.deps[d];row[d]=v.ok?'ok':(v.text.trim()||'no');});
if(e.all)Object.keys(it.states).forEach(function(d){if(isDone(it.states[d])&&!(d in row))row[d]='ok';});
if(e.text.trim())row.global=e.text.trim();
if(e.desc!==null&&e.desc.trim()&&e.desc.trim()!==it.desc)row.description=e.desc.trim();out.push(row);});return out;}
// <project>_review_<YYYY-MM-DD_HH-MM>_<role>_<author>.json: two reviewers'
// files side by side on a drive, never one over the other.
function slug(t){return String(t||'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'');}
function reviewName(){var d=new Date(),stamp=d.getFullYear()+'-'+two(d.getMonth()+1)+'-'+two(d.getDate())+'_'+two(d.getHours())+'-'+two(d.getMinutes());
return [META.review_base+'_review_'+stamp,slug(rv.role),slug(rv.author)].filter(Boolean).join('_')+'.json';}
function today(){var d=new Date();return d.getFullYear()+'-'+two(d.getMonth()+1)+'-'+two(d.getDate());}
// Download: what it holds first, with who, as what and when -- then the file.
$('rv-dl').addEventListener('click',function(){var rows=exportRows();
if(!rows.length){toast('Nothing to send yet: validate or write a retake first.');return;}
var c=summary(),needsRole=rows.some(function(row){return Object.keys(row).some(function(k){return FIXED.indexOf(k)<0||k==='global';});});
var dl=$('dlg');dl.innerHTML='<div class="dlg-in" role="dialog" aria-modal="true" aria-labelledby="dlg-t"><h3 id="dlg-t">Download the review</h3><dl>'+
'<dt>Files reviewed</dt><dd>'+c.files+'</dd><dt>Validated</dt><dd>'+c.ok+'</dd><dt>Retakes</dt><dd>'+c.rt+'</dd>'+
(c.out?'<dt>Validations withdrawn</dt><dd>'+c.out+'</dd>':'')+(c.desc?'<dt>Descriptions</dt><dd>'+c.desc+'</dd>':'')+'</dl>'+
'<label>Your name<input id="d-author" value="'+esc(rv.author)+'" autocomplete="name"></label><div class="row2">'+
'<label>Role<select id="d-role">'+$('role').innerHTML+'</select></label><label>Review date<input id="d-date" type="date" value="'+esc(rv.date||today())+'"></label></div>'+
'<p class="why" id="d-why" hidden></p><div class="acts"><button class="btn" id="d-cancel">Cancel</button><button class="btn primary" id="d-go">Download</button></div></div>';
$('d-role').value=rv.role;dl.hidden=false;$(rv.author?'d-go':'d-author').focus();
$('d-cancel').onclick=function(){dl.hidden=true;};dl.onclick=function(e){if(e.target===dl)dl.hidden=true;};
$('d-go').onclick=function(){rv.author=$('d-author').value.trim();rv.role=$('d-role').value;rv.date=$('d-date').value;
$('author').value=rv.author;$('role').value=rv.role;save();
if(needsRole&&!rv.role){$('d-why').hidden=false;$('d-why').textContent='Pick your role: your validations and retakes are recorded under it.';$('d-role').classList.add('need');return;}
var data={format:META.format,schema_version:META.schema_version,project:META.project,snapshot:META.snapshot,author:rv.author,role:rv.role,
review_date:rv.date,written_at:new Date().toISOString().slice(0,19),rows:rows};
var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.download=reviewName();
document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove();},1000);dl.hidden=true;
toast('Downloaded: send it, Import review reads it.');};});
document.querySelectorAll('.rv-load').forEach(function(inp){inp.addEventListener('change',function(){var file=this.files[0];this.value='';closeMenus();if(!file)return;
var rd=new FileReader();rd.onload=function(){var data;try{data=JSON.parse(rd.result);}catch(e){toast('Not a review file.');return;}
if(data.format!==META.format){toast('Not a review downloaded from a snapshot page.');return;}
if(data.project!==META.project&&!confirm('This review is for '+data.project+', not '+META.project+'. Load it anyway?'))return;
if(summary().files&&!confirm('Replace the review in progress with this one?'))return;
rv={author:data.author||'',role:data.role||'',date:data.review_date||'',files:{}};var unknown=0;
(data.rows||[]).forEach(function(row){var it=byFile[row.filename];if(!it){unknown++;return;}var e=entry(it);
Object.keys(row).forEach(function(k){if(FIXED.indexOf(k)>=0)return;var v=String(row[k]).trim(),l=v.toLowerCase();
if(OKS.indexOf(l)>=0)e.deps[k]={ok:1};else if(NOS.indexOf(l)>=0)e.deps[k]={no:1,text:''};else e.deps[k]={no:1,text:v};});
var gv=String(row.global||'').trim(),gl=gv.toLowerCase();
if(OKS.indexOf(gl)>=0)e.all=true;else if(NOS.indexOf(gl)>=0)Object.keys(it.states).forEach(function(d){if(isDone(it.states[d])&&!e.deps[d])e.deps[d]={no:1,text:''};});
else e.text=gv;if(row.description)e.desc=row.description;});
$('author').value=rv.author;$('role').value=rv.role;save();setReview(true);render();
toast('Review of '+(rv.author||'?')+' loaded: '+plural(summary().files,'file')+(unknown?', '+unknown+' not on this page (renamed, or another snapshot)':'')+'.');};
rd.readAsText(file);});});

/* ---------- start ---------- */
try{var kept=JSON.parse(localStorage.getItem(KEY)||'null');if(kept&&kept.files){rv=kept;rv.date=rv.date||'';
$('author').value=rv.author||'';$('role').value=rv.role||'';
if(summary().files){document.body.classList.add('reviewing');try{if(localStorage.getItem(FOLD)==='1'&&rv.author)document.body.classList.add('rb-folded');}catch(e){}setTimeout(function(){toast('Your review in progress is back (kept in this browser).');},300);}}}catch(e){}
summaryCards();drawTabs();render();stats();barHeight();
// A link to a file (#its name) opens it.
var want=decodeURIComponent(location.hash.slice(1));if(want&&byName[want])jump(byName[want]);
})();
