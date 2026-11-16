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

