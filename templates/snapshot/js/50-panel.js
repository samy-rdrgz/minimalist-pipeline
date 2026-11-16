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
$('p-title').innerHTML=nameHtml(it);$('p-blend').hidden=!META.live||guest();var nv=allVideos(it).length;$('p-play').hidden=true;$('p-play').title=nv>1?'Play the '+nv+' shots in a row':'Play the render';
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
if(it.live)h+=(guest()?'':renderHtml(it))+checksHtml(it)+linksHtml(it);
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
if(ev.target.closest('#rnd-t')){rndOpen=!rndOpen;return refresh();}
if((t=ev.target.closest('[data-rf][data-v]'))){rform(it)[t.dataset.rf]=t.dataset.v;return refresh();}
if(ev.target.closest('[data-rft]')){var rf1=rform(it);rf1.frames=!(rf1.frames||rf1.start||rf1.end);if(!rf1.frames){rf1.start='';rf1.end='';}return refresh();}
if((t=ev.target.closest('[data-rprio]'))){var rf0=rform(it);rf0.prio=Math.max(0,Math.min(100,rf0.prio+(+t.dataset.rprio)));return refresh();}
if((t=ev.target.closest('[data-rshot]'))){var off=rform(it).off;if(off[t.dataset.rshot])delete off[t.dataset.rshot];else off[t.dataset.rshot]=1;return refresh();}
if((t=ev.target.closest('#r-send,#r-prev'))){t.disabled=true;renderSend(it,t.id==='r-prev').then(function(){t.disabled=false;});return;}
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
$('p-body').addEventListener('change',function(ev){var t=ev.target;if(t.dataset&&t.dataset.rf==='preset'){rform(D[cur]).preset=t.value;return;}if(!t.dataset||t.dataset.vline==null)return;var it=D[cur],k=t.dataset.vline;
pickVersion(it,k,t.value===''?null:((it.live.versions||{})[k]||[])[+t.value]);});
$('p-body').addEventListener('input',function(ev){var t=ev.target,it=D[cur],e=entry(it);if(t.dataset&&t.dataset.rfn){rform(it)[t.dataset.rfn]=t.value.trim();return;}if(t.tagName!=='TEXTAREA'&&t.id!=='om-why')return;if(t.tagName==='TEXTAREA')grow(t);
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
