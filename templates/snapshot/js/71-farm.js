/* ---------- live: the Farm tab ---------- */
// Its jobs by state, as Farm monitoring's: a job's file opens its panel;
// then the machines -- this one, the host, the silent ones.
function dur(s){if(s==null)return '';s=Math.round(s);return s<90?s+' s':s<5400?Math.round(s/60)+' min':(s/3600).toFixed(1)+' h';}
function guest(){return !!(META.live&&META.live.guest);}
function farmHtml(){var F=DATA.farm||{},jobs=F.jobs||[],me=F.me||{},h='<div class="farm'+(guest()?' ro':'')+'">';
// This machine first: worker or not, the farm host or not -- a worker in a click.
h+='<div class="fme"><span class="fme-l">'+ico('render')+'<b>This machine</b> '+(me.worker?'worker'+(me.rendering?' · rendering':' · idle'):'not a worker')+(me.host?' · the farm host':'')+'</span>'+
'<span class="fme-h">Farm host: '+esc(me.host?'this machine':me.host_name||'none')+' · '+esc(F.status||'unknown')+'</span>'+
'<button type="button" class="act'+(me.worker?'':' fix')+'" data-farm="worker" data-v="'+(me.worker?'':'1')+'">'+(me.worker?'Stop being a worker':'Make it a worker')+'</button></div>';
// Filters, as Farm monitoring's: a state, mine, a name; the time left.
var seg=function(v,l){return '<button type="button" data-ffs="'+v+'" aria-pressed="'+(FF.s===v)+'">'+l+'</button>';};
h+='<div class="ffl"><div class="seg" role="group" aria-label="State">'+seg('','All')+JOB_STATES.map(function(st){return seg(st[0],st[1]);}).join('')+'</div>'+
'<button type="button" class="chipf" data-ffm aria-pressed="'+FF.mine+'">'+ico('user')+'<span class="cl">Mine</span></button>'+
'<input class="ffq" type="search" placeholder="Find a job…" aria-label="Find a job by its file" value="'+esc(FF.q)+'">'+(F.left?'<span class="fleft" title="The machine time the jobs still need, over the live workers">'+esc(F.left)+'</span>':'')+'</div>';
var shown=jobs.filter(function(j){return (!FF.s||j.state===FF.s)&&(!FF.mine||j.mine)&&(!FF.q||(j.file+' '+j.shot).toLowerCase().indexOf(FF.q)>=0);});
JOB_STATES.forEach(function(st){var js=shown.filter(function(j){return j.state===st[0];});if(!js.length)return;
var bulk=st[0]==='finished'||st[0]==='failed'?'<button type="button" class="act mini2" data-farm="archive_all" data-v="'+st[0]+'">Archive all '+st[1].toLowerCase()+' ('+js.length+')</button>':'';
h+='<section class="fgrp"><h3>'+st[1]+' <span>'+js.length+'</span>'+bulk+'</h3>'+js.map(function(j){return jobRow(j,st);}).join('')+'</section>';});
if(!shown.length)h+='<p class="faint">'+(jobs.length?'No job matches.':'No job in the farm.')+'</p>';
var W=F.workers||[];h+='<section class="fgrp"><h3>Machines <span>'+W.length+'</span></h3>'+(W.length?W.map(workerRow).join(''):'<p class="faint">No worker: Make it a worker above, on each machine that renders.</p>')+'</section>';
return h+'</div>';}
// A machine: one line, opened on its detail (read from Blender on demand)
// -- Stop a live one, Forget a silent one.
function workerRow(w){var sl=w.status==='silent',d=(WD[w.uuid]||{}).d;
return '<details class="job wk'+(sl?' sl':'')+'"'+(WOPEN[w.uuid]?' open':'')+' data-wk="'+esc(w.uuid)+'"><summary><i class="m '+(sl?'na':w.file?'s-wip':w.status==='idle'?'s-done':'s-todo')+'"></i><span class="jf">'+esc(w.name)+'</span>'+
'<span class="js">'+(w.mine?'<span class="tg">this machine</span>':'')+(w.host?'<span class="tg">farm host</span>':'')+(sl?'silent since '+fmtDate(w.since)+' -- crashed, closed or asleep?':esc([w.status,w.file].filter(Boolean).join(' · ')))+'</span></summary>'+
(WOPEN[w.uuid]?'<div class="jd">'+(d?'<dl>'+jdRows(d.rows)+'</dl><div class="ta">'+(d.stop?'<button type="button" class="act ko" data-wstop="'+(d.busy?1:'')+'">Stop</button>':'')+(d.forget?'<button type="button" class="act" data-farm="forget_worker">Forget</button>':'')+'</div>':'<p class="faint">Reading…</p>')+'</div>':'')+'</details>';}
function jdRows(rows){return rows.map(function(r){return '<dt>'+esc(r[0])+'</dt><dd'+(r[2]?' class="al"':'')+'>'+esc(r[1])+'</dd>';}).join('');}
// A job: one line that opens on its detail -- what, where, by whom; then,
// read from its file on demand, what Farm monitoring's details say, who
// rendered which frame, its logs and stages -- and what's done to it.
function jobRow(j,st){var it=j.key&&byKey[j.key],p=j.total?j.done/j.total:0,live=st[0]==='running'||st[0]==='waiting',open=JOPEN[j.id],d=(JD[j.id]||{}).d;
var row=function(k,v){return v?'<dt>'+k+'</dt><dd>'+v+'</dd>':'';};
var h='<details class="job"'+(open?' open':'')+' data-job="'+esc(j.id)+'"><summary><i class="m '+(st[2]==='fail'?'s-fail':'s-'+st[2])+'"></i>'+
'<span class="jf">'+esc(j.file)+'</span><span class="js">'+esc([j.shot,j.text,j.compile!=null?Math.round(j.compile*100)+' %':''].filter(Boolean).join(' · '))+'</span>'+
'<span class="jp">'+(j.total?'<span class="bar2'+(st[0]==='running'?' run':'')+'"><i data-w="'+p*100+'" style="width:'+(JW[j.id]!=null?JW[j.id]:p*100)+'%"></i></span><small>'+j.done+'/'+j.total+(j.left?' · '+dur(j.left)+' left':'')+'</small>':j.estimate?'<small title="At its last render\'s pace">'+esc(j.estimate)+'</small>':'')+'</span>'+
'<span class="jm">'+[j.machines?plural(j.machines,'machine'):'',esc(j.user),fmtDate(j.at)].filter(Boolean).join(' · ')+'</span></summary>';
if(!open)return h+'</details>';
h+='<div class="jd"><dl>'+row('Stage',esc(j.text))+row('Preset',esc([j.preset,j.department].filter(Boolean).join(' · ')))+row('Frames',j.range?esc(j.range.join('-'))+(j.total?' · '+j.done+'/'+j.total+' rendered':''):'')+
row('Machines',esc((j.names||[]).join(', ')))+row('Sent',[esc(j.user),fmtDate(j.at)].filter(Boolean).join(' · '))+
row('Priority',live&&!j.pending?'<span class="prio"><button type="button" class="mini" data-prio="-1" aria-label="Lower">−</button><b>'+j.priority+'</b><button type="button" class="mini" data-prio="1" aria-label="Higher">+</button><small>higher goes first</small></span>':esc(String(j.priority)))+
row('Job',esc(j.id))+(d?jdRows(d.rows):'')+'</dl>';
if(d&&d.lookup){var L=d.lookup;h+='<div class="flk"><label>Which machine rendered frame <input type="number" class="rnum" data-lk="'+esc(j.id)+'" min="'+L.start+'" max="'+(L.start+L.frames.length-1)+'" value="'+(LKF[j.id]!=null?LKF[j.id]:L.start)+'"></label><span class="flk-r">'+esc(lookupText(L,LKF[j.id]!=null?LKF[j.id]:L.start))+'</span></div>';}
if(!d)h+='<p class="faint">Reading its file…</p>';
h+='<div class="ta">'+(it?'<button type="button" class="act" data-goto="'+it.i+'">Open its file details</button>':'')+
(j.removable?'<button type="button" class="act ko" data-farm="remove">Remove from queue</button>':live?'<button type="button" class="act ko" data-farm="cancel">Cancel</button>':'')+
(j.retry||d&&d.retry?'<button type="button" class="act fix" data-farm="retry">Retry</button>':'')+(j.recompile||d&&d.recompile?'<button type="button" class="act" data-farm="recompile" title="Make its video again from its frames">Recompile</button>':'')+
(st[0]==='failed'||st[0]==='finished'?'<button type="button" class="act" data-farm="archive">Archive</button>':'')+
(d&&d.folder?'<button type="button" class="act" data-open="folder">'+ico('folder')+'Its folder</button>':'')+(d?'<button type="button" class="act" data-open="file">Its job file</button>':'')+
(d?d.logs.map(function(l,n){return '<button type="button" class="act" data-open="log:'+n+'" title="Open this log">'+ico('text')+esc(l)+'</button>';}).join(''):'')+'</div>';
if(d&&d.stages.length)h+='<details class="stg"><summary>Stages <span>'+d.stages.length+'</span></summary><dl>'+d.stages.map(function(x){return '<dt>'+esc(x[0])+'</dt><dd>'+esc(x[1])+'</dd>';}).join('')+'</dl></details>';
return h+'</div></details>';}
// Who rendered frame f: its machine, the frames around it it wrote too, its pace.
function lookupText(L,f){f=+f;var i=f-L.start;if(isNaN(f)||i<0||i>=L.frames.length)return 'not in this render ('+L.start+'-'+(L.start+L.frames.length-1)+')';
var c=L.frames[i],a=i,b=i;while(a>0&&L.frames[a-1]===c)a--;while(b<L.frames.length-1&&L.frames[b+1]===c)b++;var m=L.machines[c]||['machine not recorded',''];
return [m[0],a===b?'this frame only':'frames '+(L.start+a)+'-'+(L.start+b)+' in a row',m[1]].filter(Boolean).join(' · ');}
// A job's bar drawn at its last width, then grown to the new one.
function growBars(){var bs=$('list').querySelectorAll('.job[data-job] .bar2 i[data-w]');
requestAnimationFrame(function(){bs.forEach(function(i){var id=i.closest('.job').dataset.job;i.style.width=i.dataset.w+'%';JW[id]=+i.dataset.w;});});
farmDetails();}
// The details open, read again once the data has moved (a new version).
function farmDetails(){if(!META.live)return;var v=META.live.version;
var get=function(box,key,action,value){var c=box[key]=box[key]||{};if(c.busy||c.v===v)return;c.busy=true;
livePost('farm',{action:action,job_id:action==='detail'?key:'',value:value}).then(function(res){c.busy=false;c.v=v;c.d=res.detail||null;if(state.tab==='farm')render();}).catch(function(){c.busy=false;});};
Object.keys(JOPEN).forEach(function(id){if(JOPEN[id])get(JD,id,'detail');});Object.keys(WOPEN).forEach(function(u){if(WOPEN[u])get(WD,u,'worker_detail',u);});}
function farmPost(action,job,value,extra){var body={action:action,job_id:job||'',value:value};Object.keys(extra||{}).forEach(function(k){body[k]=extra[k];});
return livePost('farm',body).then(function(res){toast(res.ok?'Done.'+(res.note?' '+res.note:''):'Not done: '+(res.error||'?'));}).catch(function(){toast('Blender doesn\'t answer.');});}
