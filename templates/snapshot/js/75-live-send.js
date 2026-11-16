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
if(!box&&a&&a.matches&&a.matches('textarea,input:not([type=checkbox]):not([type=radio]):not(.ffq)')){pend=nd;return;}pend=null;
// Another project made active in Blender: its page, as it loads.
if(nd.meta.live&&META.live&&nd.meta.live.root!==META.live.root)return location.reload();
var curFile=cur!=null&&D[cur]?D[cur].file:null,plFile=PL&&PL.it?PL.it.file:null,y=scrollY;
// The file shown gone (archived, renamed): its panel closed first.
if(curFile&&!nd.items.some(function(x){return x.file===curFile;})){closePanel();curFile=null;}
Object.keys(nd.images||{}).forEach(function(k){DATA.images[k]=nd.images[k];});
DATA.items=nd.items;DATA.meta=nd.meta;DATA.farm=nd.farm;META=nd.meta;D=nd.items;W=META.weights;prepare();
if(PL&&plFile&&byFile[plFile])PL.it=byFile[plFile];
// What was sent, now shown by the data: out of your review, before drawing.
if(LIVE_OUT.after&&(META.live.version||0)>=LIVE_OUT.after.v){var fn=LIVE_OUT.after.fn;LIVE_OUT.after=null;fn(true);}
cur=curFile&&byFile[curFile]?byFile[curFile].i:null;summaryCards();drawTabs();stamp();render();scrollTo(scrollX,y);
if(cur!=null)refresh();
if(a&&a.classList&&a.classList.contains('ffq')){var q2=$('list').querySelector('.ffq');if(q2){q2.focus();q2.setSelectionRange(q2.value.length,q2.value.length);}}
if(box==='cmp')focusCmp();else if(box){var rt=$('p-body').querySelector('.rp-t[data-r="'+CSS.escape(box)+'"]');if(rt){rt.focus({preventScroll:true});rt.setSelectionRange(rt.value.length,rt.value.length);}}}
document.addEventListener('focusout',function(){setTimeout(function(){if(pend)applyData(pend);},0);});
if(META.live)(function(){var T=META.live.token,v=META.live.version||0,st='';document.body.classList.add('live');
var pill=document.createElement('span');pill.setAttribute('role','status');$('h-when').after(pill);
function status(s){if(s===st)return;st=s;pill.className='lvp '+s;pill.textContent=s==='on'?'connected':s==='busy'?'Blender busy':'disconnected';
if(s==='on'&&guest())pill.textContent='connected · guest until '+fmtUntil(META.live.until);
pill.title=s==='on'?(guest()?'Served by '+(META.exported_by||'Blender')+'\'s Blender, as '+META.live.user+' ('+META.live.role+')':'Served by Blender on this machine, kept up to date'):s==='busy'?'Blender is busy (a long task): the page waits for it':'Blender doesn\'t answer (closed, or the page stopped): trying again';}


// A tab in the background asks nothing: the browser gives a server 6
// connections, each tab's wait for news holds one -- tabs piling up (each
// Blender button opens one) left a click waiting. Back in front, it asks again.
var ab=null,polling=false;
function poll(){if(document.hidden){polling=false;return;}polling=true;ab=window.AbortController?new AbortController():null;
fetch('data?t='+encodeURIComponent(T)+'&since='+v,{cache:'no-store',signal:ab?ab.signal:undefined}).then(function(r){if(!r.ok)throw r.status;return r.json();})
.then(function(d){if(d.reading)return location.reload();status(d.busy?'busy':'on');if(d.data&&d.version!==v){v=d.version;applyData(d.data);}poll();})
.catch(function(e){if(e&&e.name==='AbortError'){polling=false;return;}status('off');setTimeout(poll,2000);});}
document.addEventListener('visibilitychange',function(){if(document.hidden){if(ab)ab.abort();}else if(!polling)poll();});
status('on');poll();
rv.author=META.live.user||rv.author;rv.role=META.live.role||'team';store();setReview(true);countBar();if(Object.keys(rv.files).length||(rv.creates||[]).length)liveSend();})();
var boot=$('boot');if(boot)boot.remove();
// A link to a file (#its name, its .blend's: any version of it) opens it; #farm, the Farm tab.
var want=decodeURIComponent(location.hash.slice(1)),wit=want&&(byName[want]||byFile[want]||byName[want.replace(/_v\d+.*$/i,'')]);
if(wit)jump(wit);else if(want==='farm'&&DATA.farm)setTab('farm');else if(want==='share'&&META.live&&!guest())shareDialog();
var shb=$('sh-open');if(shb){shb.hidden=!META.live||guest();shb.addEventListener('click',function(){closeMenus();shareDialog();});}
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
