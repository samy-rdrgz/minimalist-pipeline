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
(t[0]==='breakdown'?'':t[0]==='farm'?'<span>'+(DATA.farm.jobs||[]).filter(function(j){return j.state!=='finished';}).length+'</span>':'<span>'+D.filter(function(it){return it.tab===t[0];}).length+'</span>')+'</button>';}).join('');
var deps=depsOf(state.tab).filter(function(d){return D.some(function(it){return it.tab===state.tab&&d in it.states;});});
if(deps.indexOf(state.dep)<0)state.dep='';
$('depf').innerHTML='<option value="" data-short="All depts.">All departments</option>'+deps.map(function(d){return '<option value="'+esc(d)+'"'+(d===state.dep?' selected':'')+'>'+esc(cap(d))+'</option>';}).join('');
$('depf').classList.toggle('on',!!state.dep);sync('depf');}
function chipCounts(){var fb=document.querySelector('.chipf[data-f="farm"]');if(fb)fb.hidden=!D.some(function(it){return it.farm;});
// Me: only with a team (Edit project).
var fm=document.querySelector('.chipf[data-f="me"]');if(fm)fm.hidden=!(META.team||[]).length;document.querySelectorAll('.chipf[data-f]').forEach(function(b){b.querySelector('b').textContent=D.filter(function(it){
return it.tab===state.tab&&(!state.dep||state.dep in it.states)&&FILTERS[b.dataset.f](it,state.dep);}).length;});}
// A row of the list (render(): its departments' columns).
var rowDeps=[],rowCols='',rowFarm=false;
// A file's farm at a glance: its job's state (a click: the Farm tab on it),
// a render to check (a click: its panel, on To check).
function farmCell(it){var h='';
if(it.farm){var k=it.farm.state==='failed'?'fail':it.farm.state==='waiting'?'wait':'run';
h+='<button type="button" class="fcb fc-'+k+'" data-farmof="'+esc(it.file)+'" title="In the farm: '+esc(it.farm.tip)+'" aria-label="In the farm: '+esc(it.farm.text)+'">'+ico(k==='fail'?'cancel':k==='wait'?'time':'render')+'</button>';}
if(it.to_check)h+='<button type="button" class="fcb fc-chk" data-tocheck="'+it.i+'" title="A render to check: watch it" aria-label="A render to check">'+ico('eye')+'</button>';
return h;}
function rowHtml(it){var deps=rowDeps,cols=rowCols;
// Tinted once this review touched it: where you've been, at a glance.
return '<div class="row'+((omitChanged(it,peek(it))?peek(it).omit.state:it.omit)?' omit':'')+(changes(it)?' rv-mine':'')+(it.i===cur?' sel':'')+'" role="button" tabindex="0" data-i="'+it.i+'" style="--cols:'+cols+'"'+(changes(it)?' title="In your review"':'')+'>'+thumb(it)+
'<span class="r-name">'+nameHtml(it)+'<small>'+subline(it)+'</small><span class="flags">'+flags(it)+'</span></span>'+
deps.map(function(d){return '<span class="d">'+cell(it,d)+'</span>';}).join('')+(rowFarm?'<span class="fc">'+farmCell(it)+'</span>':'')+
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
document.body.classList.toggle('tab-bd',state.tab==='breakdown'||state.tab==='farm');
$('sch-bar').innerHTML=state.tab==='breakdown'?schedPill():'';
if(state.tab==='breakdown'){visible=[];$('list').innerHTML='<div class="bd">'+stats()+'</div>';countBar();return;}
if(state.tab==='farm'){visible=[];$('list').innerHTML=farmHtml();growBars();countBar();return;}
var items=D.filter(function(it){return match(it);});
var deps=depsOf(state.tab).filter(function(d){return items.some(function(it){return d in it.states||peek(it).req[d];});});
// Many departments: narrower columns, never past the page.
var w=deps.length>7?56:deps.length>5?68:84;
// The Farm column: once a file of the list is in the farm or has a render to check.
rowFarm=items.some(function(it){return it.farm||it.to_check;});
var cols='104px minmax(0,1fr) '+deps.map(function(){return w+'px';}).join(' ')+(rowFarm?' 56px':'')+' 96px;--n:'+deps.length;
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
(rowFarm?'<span class="fc-h" title="In the farm, or a render to check">Farm</span>':'')+'<span style="text-align:right">Done</span></div>';
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
$('list').addEventListener('click',function(e){var b=e.target.closest('[data-tocheck],[data-farmof]');if(!b)return;e.stopPropagation();e.preventDefault();
if(b.dataset.tocheck!=null){chkOpen=true;openPanel(+b.dataset.tocheck);setTimeout(function(){var c=$('chk-t');if(c)c.scrollIntoView({block:'start',behavior:'smooth'});},60);return;}
if(!DATA.farm){var fi=byFile[b.dataset.farmof];if(fi)openPanel(fi.i);return;}// a snapshot: no Farm tab
FF.q=b.dataset.farmof.toLowerCase();FF.s='';setTab('farm');},true);
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

