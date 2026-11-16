/* ---------- live: the panel's own sections ---------- */
// To check: the renders the team hasn't watched -- ▶ in the player,
// Checked takes one off (pushed to the edit if ticked); open by default.
// Linked files: what it links (a newer stable said), what links it.
function fold2(id,open,icon,title,sum,body){return '<div class="fset'+(open?' on':'')+'"><button type="button" class="fset-b" id="'+id+'" aria-expanded="'+open+'">'+ico(icon)+'<b>'+title+'</b><span class="sm">'+sum+'</span><span class="chev" aria-hidden="true">▸</span></button>'+(open?'<div class="fset-c">'+body+'</div>':'')+'</div>';}
function checksHtml(it){var c=it.live.checks||[];if(!c.length)return '';
return fold2('chk-t',chkOpen,'eye','To check',plural(c.length,'render')+' not watched by the team yet',c.map(function(x){
return '<div class="chk"><span class="chk-l">'+esc([x.shot,x.department,x.folder].filter(Boolean).join(' · '))+'</span>'+(x.video&&videoSrc(x.video)?'<button type="button" class="act" data-chkplay="'+esc(x.video)+'">'+ico('play')+'Play</button>':'')+
'<button type="button" class="act fix" data-chk="'+esc(x.key)+'" title="Watched: out of To check">'+ico('check')+'Checked</button></div>';}).join('')+
(guest()?'':'<label class="chk-push"><input type="checkbox" id="chk-push"> Push to editing when checked</label>'));}
function itemAt(key){return key&&byKey[key];}
// Render: the file sent to the farm as the Render dialog sends it -- its
// version, preset, priority, mode, a block's shots --, or its sequence's
// preview. Kept per file while the page is open.
function rform(it){var F=DATA.farm||{};return RF[it.file]=RF[it.file]||{ver:it.stable?'stable':'last',preset:F.preset||'',prio:10,mode:'all',off:{},start:'',end:''};}
function renderHtml(it){var F=DATA.farm||{},f=rform(it),seg=function(k,v,l){return '<button type="button" data-rf="'+k+'" data-v="'+v+'" aria-pressed="'+(f[k]===v)+'">'+l+'</button>';};
var job=(F.jobs||[]).filter(function(j){return j.key===(it.live||{}).key&&(j.state==='running'||j.state==='waiting');})[0];
var b='';if(it.stable&&it.stable!==it.file)b+='<div class="st-l">Version</div><div class="segb om">'+seg('ver','stable','Last stable · '+esc(it.stable_v||''))+seg('ver','last','Last · '+esc(it.wip_v||''))+'</div>';
b+='<div class="st-l">Preset</div><select class="rsel" data-rf="preset" aria-label="Pre-render preset">'+(F.presets||[]).map(function(p){return '<option value="'+esc(p[0])+'"'+(p[0]===f.preset?' selected':'')+'>'+esc(p[1])+'</option>';}).join('')+'</select>';
// Frames: rarely changed -- folded, open by itself once one is set.
var fo=f.frames||f.start||f.end;b+='<button type="button" class="rf-t" data-rft aria-expanded="'+!!fo+'">'+(fo?'▾':'▸')+' Frames <small>'+(f.start||f.end?esc((f.start||'file\'s')+' – '+(f.end||'file\'s')):'the file\'s own')+'</small></button>'+
(fo?'<div class="rrow rfr"><label>Start <input type="number" class="rnum" data-rfn="start" value="'+esc(f.start)+'" placeholder="file\'s"></label><label>End <input type="number" class="rnum" data-rfn="end" value="'+esc(f.end)+'" placeholder="file\'s"></label><small class="faint">frame numbers, as in Blender</small></div>':'');
b+='<div class="rrow"><span class="prio"><span class="st-l">Priority</span><button type="button" class="mini" data-rprio="-1" aria-label="Lower">−</button><b>'+f.prio+'</b><button type="button" class="mini" data-rprio="1" aria-label="Higher">+</button></span>'+
'<div class="segb om">'+seg('mode','all','All machines')+seg('mode','single','Single')+'</div></div>';
if(it.shots.length>1)b+='<div class="st-l">Shots</div><div class="req">'+it.shots.map(function(x){return '<button type="button" data-rshot="'+esc(x)+'" aria-pressed="'+!f.off[x]+'">'+esc(x)+'</button>';}).join('')+'</div>';
b+='<div class="ta"><button type="button" class="act fix" id="r-send">'+ico('render')+'Send to the farm</button>'+(it.kind==='shot'&&it.group?'<button type="button" class="act" id="r-prev" title="Each shot\'s latest video of '+esc(it.group)+', end to end">Preview '+esc(it.group)+'</button>':'')+'</div>';
return fold2('rnd-t',rndOpen,'render','Render',job?'in the farm: '+esc(job.text)+(job.total?' · '+job.done+'/'+job.total:''):'send it to the farm',b);}
function renderSend(it,preview){var f=rform(it),body=preview?{action:'preview',sequence:it.group,priority:f.prio}:
{action:'render',file:f.ver==='stable'&&it.stable?it.stable:it.file,preset:f.preset,priority:f.prio,mode:f.mode,start:f.start,end:f.end,shots:it.shots.length>1?it.shots.filter(function(x){return !f.off[x];}):null};
return livePost('farm',body).then(function(res){toast(res.ok?'Sent: '+res.sent+'.'+(res.note?' '+res.note:''):'Not sent: '+(res.error||'?'));}).catch(function(){toast('Blender doesn\'t answer.');});}
function linksHtml(it){var L=it.live,links=L.links||[],by=L.linked_by||[];if(!links.length&&!by.length)return '';var old=links.filter(function(x){return x.newer;}).length;
var to=function(t,file){return t?'<button type="button" class="lk" data-goto="'+t.i+'">'+esc(t.name)+'</button>':'<span>'+esc(file)+'</span>';};
return fold2('lnk-t',lnkOpen,'link','Linked files',[plural(links.length,'link'),old?old+' to update':'','linked by '+by.length].filter(Boolean).join(' · '),
(links.length?'<div class="st-l">Links</div>'+links.map(function(x){return '<div class="lnk">'+to(itemAt(x.key),x.file)+'<span class="lf">'+esc(x.file)+'</span>'+(x.newer?'<span class="tg tg-old" title="A newer stable of it exists">'+ico('warn')+esc(x.newer)+'</span>':'')+'</div>';}).join(''):'')+
(by.length?'<div class="st-l">Linked by</div>'+by.map(function(k){return '<div class="lnk">'+to(itemAt(k),k)+'</div>';}).join(''):''));}
// Live: every version with a video, to watch instead of the main render.
function versionsHtml(it){if(!it.live)return '';var V=it.live.versions||{};
var seen={};
return it.renders.filter(function(r){var k=r.shots||'';if(seen[k])return false;seen[k]=1;return (V[k]||[]).length>1||((V[r.shots||'']||[]).length&&V[r.shots||''][0].video!==r.video);}).map(function(r){var k=r.shots||'',o=(PICKV[it.file]||{})[k];
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
