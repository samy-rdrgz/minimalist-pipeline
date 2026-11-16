/* ---------- progress details: the Breakdown ---------- */
// Per type: five figures, then one table -- groups × departments, their
// totals on the right and in the All row --, a switch for what a cell
// says (% · Status · Count · RTK & notes), kept in this browser. A cell
// opens the list filtered on its group and department.
var BD_MODES=[['pct','%'],['status','Status'],['count','Count'],['notes','RTK & notes','RTK']],bdMode='pct';
try{bdMode=localStorage.getItem('mp-snapshot:bd-mode')||'pct';}catch(err){}
function setAside(it){return !!(it.omit&&it.omit.state);}
// A file read as it is, or as your review would leave it.
function bdView(it,withRv){var r=withRv&&reviewState(it);
if(!r)return {states:it.states,rtk:function(d){return !!it.rtk[d];},ok:function(d){return baseOk(it,d);},score:function(d){return it.scores[d];},done:it.done,valid:it.valid};
if(r.omit)return null;var f=reviewed(it);
return {states:r.states,rtk:function(d){return r.rtk.indexOf(d)>=0;},ok:r.ok,score:function(d){return MPStatus.departmentScore(r.states[d],r.rtk.indexOf(d)>=0,W);},done:f.done,valid:f.valid};}
// A cell's figures over files, on department d ('' : all theirs).
function bdSum(list,d,withRv){var c={files:0,req:0,v:0,dn:0,w:0,t:0,rtk:0,wait:0,notes:0,sc:[],vs:[]};
list.forEach(function(it){var x=bdView(it,withRv);if(!x)return;var ds=d?(d in x.states?[d]:[]):Object.keys(x.states);if(!ds.length)return;
c.files++;var waits=false,rks={},nt={},lone=0;
ds.forEach(function(k){var st=x.states[k],ok=x.ok(k),rk=x.rtk(k);c.req++;
if(ok)c.v++;else if(st==='done'&&!rk)c.dn++;else if(st==='wip'||st==='rework'||st==='done')c.w++;else c.t++;
// A thread on several departments: once in a total.
var ns=it.rtkNotes[k]||[];if(ns.length)ns.forEach(function(n){rks[n.id]=1;});else if(it.rtk[k])lone++;if(((it.flags||{})[k]||{}).waiting)waits=true;
it.openNotes.forEach(function(n){if(n.deps.indexOf(k)>=0)nt[n.id]=1;});
if(d){c.sc.push(x.score(k));c.vs.push(ok);}});
if(waits)c.wait++;c.rtk+=Object.keys(rks).length+lone;c.notes+=Object.keys(nt).length;
if(!d){c.rtk+=it.genRtks.length;c.notes+=it.openNotes.filter(function(n){return !n.deps.length;}).length;c.sc.push(x.done);c.vs.push(x.valid);}});
c.p=avg(c.sc);c.pv=META.role?avg(c.vs):null;return c;}
// A split bar: its parts there are only (an empty one kept its 1 px gap: a notch at an end).
function sbar(parts,cls){return '<span class="sb'+(cls?' '+cls:'')+'">'+parts.filter(function(p){return p[1]>1e-6;}).map(function(p){return '<i class="'+p[0]+'" style="flex:'+p[1]+'"></i>';}).join('')+'</span>';}
function bdTip(g,d,c){return g+' · '+(d?cap(d):'every department')+': '+c.v+c.dn+' done of '+c.req+(META.role?', '+c.v+' validated':'')+(c.rtk?', '+plural(c.rtk,'open RTK'):'')+(c.wait?', '+c.wait+' waiting':'')+(c.notes?', '+plural(c.notes,'open note'):'')+(c.p!=null?' -- '+pct(c.p)+' done':'');}
function bdCell(c,r,attrs,tip){if(!c.req)return '<span class="mx-c na" aria-label="not required">–</span>';
var h='',chg=function(a,b){return a!=null&&b!=null&&Math.round(a*100)!==Math.round(b*100);};
if(bdMode==='pct'){var v=c.pv||0;h=sbar([['sv',v],['sd',(c.p||0)-v],['sn',1-(c.p||0)]])+
(r&&(chg(r.p,c.p)||chg(r.pv,c.pv))?'<span class="mx-t mx-r2"><b>✎ '+pct(r.p||0)+'</b>'+(r.pv?' · '+pct(r.pv):'')+'</span>':'<span class="mx-t"><b>'+pct(c.p||0)+'</b>'+(c.pv?'<span class="mx-v">· '+pct(c.pv)+'</span>':'')+'</span>');
if(r&&(chg(r.p,c.p)||chg(r.pv,c.pv)))tip+='\nWith your review: '+pct(r.p||0)+(r.pv!=null?' · '+pct(r.pv)+' validated':'');}
else if(bdMode==='status')h=sbar([['sv',c.v],['sd',c.dn],['sw',c.w],['sn',c.t]],'st');
else if(bdMode==='count'){var cc=r&&(r.v+r.dn!==c.v+c.dn||r.v!==c.v),x=cc?r:c;h='<span class="mx-t'+(cc?' mx-r2':'')+'"><b>'+(cc?'✎ ':'')+(x.v+x.dn)+'</b>/'+x.req+(x.v?'<span class="mx-v">· '+x.v+' ✓</span>':'')+'</span>';
if(cc)tip+='\nWith your review: '+(r.v+r.dn)+'/'+r.req+(r.v?', '+r.v+' validated':'');}
else h='<span class="mx-t bdgs">'+(c.rtk?'<span class="bdg rk">'+c.rtk+' RTK</span>':'')+(c.wait?'<span class="bdg wt">'+ico('time')+c.wait+'</span>':'')+(c.notes?'<span class="bdg nt">'+ico('text')+c.notes+'</span>':'')+(c.rtk||c.wait||c.notes?'':'<span class="faint">·</span>')+'</span>';
return '<button type="button" class="mx-c" '+attrs+' title="'+esc(tip)+'">'+h+'</button>';}
function bdLegend(){var k={pct:'<i class="lg sd"></i>done'+(META.role?'<i class="lg sv"></i>validated':'')+'<span>in progress counts '+W.wip+' %, reworked '+W.rework+' %</span>',
status:(META.role?'<i class="lg sv"></i>validated':'')+'<i class="lg sd"></i>done<i class="lg sw"></i>in progress · reworked · done with an open RTK<i class="lg"></i>not started',
count:'<span>done / required</span>'+(META.role?'<span class="mx-v">· 2 ✓</span><span>validated</span>':''),notes:'<span class="bdg rk">2 RTK</span>open retakes<span class="bdg wt">'+ico('time')+'3</span>files waiting<span class="bdg nt">'+ico('text')+'4</span>open notes'}[bdMode];
// Reviewing: a value in violet after ✎ is the one with your review (now: in its tip).
if(reviewing()&&(bdMode==='pct'||bdMode==='count'))k+='<span class="lg-rv">✎ 48 %</span><span>with your review -- now, in its tip</span>';
return '<div class="mx-k">'+k+'<span class="sp"></span><span>click a cell → the list, filtered</span></div>';}
function bdTable(kind,label,items,deps,groups,order){var rv0=reviewing(),many=deps.length>7;
var sw='<div class="seg mx-sw" role="group" aria-label="What a cell says">'+BD_MODES.map(function(m){return '<button type="button" data-bdm="'+m[0]+'" aria-pressed="'+(bdMode===m[0])+'"><span class="full">'+m[1]+'</span><span class="ab">'+(m[2]||m[1])+'</span></button>';}).join('')+'</div>';
var cols='minmax(7em,150px) repeat('+deps.length+','+(many?'minmax(96px,1fr)':'minmax(0,1fr)')+') minmax(84px,'+(bdMode==='notes'?'160px':'110px')+')';
var row=function(name,sub,list,tot){var all=bdSum(list,'',false);
return '<div class="mx-r'+(tot?' tot':'')+'"><span class="mx-n"><b>'+esc(name)+'</b><small>'+sub+'</small><small class="np">'+(all.p!=null?pct(all.p):'')+'</small></span>'+
deps.map(function(d){var c=bdSum(list,d,false);return bdCell(c,rv0?bdSum(list,d,true):null,'data-bdg="'+esc(tot?'':name)+'" data-bdd="'+esc(d)+'" data-bdk="'+kind+'"',bdTip(name,d,c));}).join('')+
'<span class="ttc">'+bdCell(all,rv0?bdSum(list,'',true):null,'data-bdg="'+esc(tot?'':name)+'" data-bdd="" data-bdk="'+kind+'"',bdTip(name,'',all))+'</span></div>';};
return '<div class="card mx'+(many?' many':'')+'" data-m="'+bdMode+'"><div class="mx-top"><strong>'+label+' × department</strong><span class="sp"></span>'+sw+'</div>'+
'<div class="mx-sc"><div class="mx-in" style="--cols:'+cols+';--colsm:minmax(4.5em,72px) repeat('+deps.length+',minmax(0,1fr))"><div class="mx-h"><span></span>'+deps.map(function(d){return '<span><span class="full">'+esc(cap(d))+'</span><span class="ab">'+esc(d.slice(0,3).toUpperCase())+'</span></span>';}).join('')+'<span class="ttc">Total</span></div>'+
order.map(function(g){return row(g,plural(groups[g].length,'file'),groups[g]);}).join('')+row('All',plural(items.length,'file'),items,true)+'</div></div>'+bdLegend()+'</div>';}
// The five figures of a type.
function bdTiles(kind,items){var S=META.schedule,exp=S?S.expected:null,done=META.progress[kind],val=(META.validation||{})[kind],h='';
if(done==null)done=avg(items.map(function(it){return it.done;}));
var tile=function(cls,icon,label,big,sub,extra){return '<div class="bk-t'+(cls?' '+cls:'')+'"><span class="kl">'+icon+label+'</span><span class="kv">'+big+'</span>'+(extra||'')+'<span class="ks">'+sub+'</span></div>';};
var pts=exp!=null&&done!=null?Math.round((done-exp)*100):null;
h+=tile('','','Done',pct(done||0),pts==null?'the mean of '+plural(items.length,'file'):pts===0?'on schedule':Math.abs(pts)+' point'+(Math.abs(pts)===1?'':'s')+' '+(pts>0?'ahead of':'behind')+' schedule',
'<span class="bk-tr"><i class="sd" style="width:'+(done||0)*100+'%"></i>'+(exp!=null?'<i class="exp" style="left:'+exp*100+'%" title="Expected: '+pct(exp)+'"></i>':'')+'</span>');
var nv=0;items.forEach(function(it){nv+=Object.keys(it.states).filter(function(d){return baseOk(it,d);}).length;});
var mine=reviewing()?withReview({done:done,valid:val},reviewedOf(items,(rv.creates||[]).filter(function(c){return c.kind===kind;})),true):'';
h+=META.role?tile('vl','','Validated',pct(val||0),nv?plural(nv,'department')+' validated by '+esc(META.role):'nothing validated yet','<span class="bk-tr"><i class="sv" style="width:'+(val||0)*100+'%"></i></span>'+mine):tile('','','Validated','–','no validation role in the project');
var rt=0,rf=0,gen=0;items.forEach(function(it){var n=bdSum([it],'',false).rtk;rt+=n;if(n)rf++;gen+=it.genRtks.length;});
h+=tile(rt?'hot':'','<span class="bdg rk">RTK</span>','open',rt,rt?'in '+plural(rf,'file')+(gen?' · '+gen+' general':''):'none open');
var wt=items.filter(function(it){return Object.keys(it.flags||{}).some(function(d){return (it.flags[d]||{}).waiting;});}).length;
h+=tile('',ico('time'),'Waiting',wt,wt===1?'file waiting on an earlier stage':'files waiting on an earlier stage');
if(kind==='shot'){var tc=items.filter(function(it){return it.to_check;}).length,fm=items.filter(function(it){return it.farm;}).length;
h+=tile('rn',ico('render'),'Renders',tc,'to check'+(fm?' · '+fm+' on the farm':''));}
return '<div class="bk-row k'+(kind==='shot'?5:4)+'">'+h+'</div>';}
function schedPill(){var S=META.schedule;if(!S)return '';
return '<span class="sch" title="Schedule: '+esc(fmtDay(new Date(S.start),true))+' to '+esc(fmtDay(new Date(S.end),true))+', on '+esc(fmtDay(snapDate))+'"><span class="sl">Schedule</span><b>Day '+S.elapsed_days+'</b><small>/ '+S.total_days+'</small><span class="bk-tr"><i class="sch-f" style="width:'+S.expected*100+'%"></i></span><span>'+pct(S.expected)+' <span class="full">expected</span><span class="ab">exp.</span></span></span>';}
var bdMore=false;
function bdCounted(){var t=function(l,v){return '<span class="wt"><span>'+l+'</span><b>'+v+'</b></span>';};
return '<div class="hic'+(bdMore?' on':'')+'"><button type="button" class="hic-b" id="bd-more" aria-expanded="'+bdMore+'">'+ico('help')+'<b>How it\'s counted</b><span class="wts">'+t('not started',0)+t('in progress',W.wip)+t('reworked',W.rework)+t('done + open RTK',W.rtk)+t('done',100)+'</span>'+
'<span class="sm">a file = the mean of its departments'+(META.role?' · validated apart ('+esc(META.role)+', at the stable shown)':'')+'</span><span class="mo">More <span class="chev">▸</span></span></button>'+(bdMore?'<p class="weights">'+esc($('weights').textContent)+'</p>':'')+'</div>';}
function stats(){var h='<div class="sch-m">'+schedPill()+'</div>';
[['shot','Shots','Sequence'],['asset','Assets','Prefix']].forEach(function(s){
var all=D.filter(function(it){return it.kind===s[0]&&it.tracked;});if(!all.length)return;
var items=all.filter(function(it){return !setAside(it);}),out={};all.forEach(function(it){if(setAside(it))out[it.omit.state]=(out[it.omit.state]||0)+1;});
var aside=Object.keys(out).map(function(k){return out[k]+' '+(k==='on_hold'?'on hold':k);}).join(' · ');
var deps=depsOf(s[0]).filter(function(d){return items.some(function(it){return d in it.states;});});
var groups={},order=[];items.forEach(function(it){if(!groups[it.group]){groups[it.group]=[];order.push(it.group);}groups[it.group].push(it);});
h+='<div class="st-sec"><h3>'+s[1]+' <small>'+plural(items.length,'file')+(aside?' · '+aside+', not counted':'')+'</small></h3>'+bdTiles(s[0],items)+(deps.length?bdTable(s[0],s[2],items,deps,groups,order):'')+'</div>';});
return h+bdCounted();}
// A cell: the list, filtered on its group (its files' names start with it) and department.
$('list').addEventListener('click',function(e){var b=e.target.closest('.bd [data-bdm]');
if(b){bdMode=b.dataset.bdm;keep('bd-mode',bdMode);return render();}
if(e.target.closest('#bd-more')){bdMore=!bdMore;return render();}
if(!(b=e.target.closest('.bd .mx-c[data-bdk]')))return;
var g=b.dataset.bdg;state.tab=b.dataset.bdk;state.dep=b.dataset.bdd;state.q=g?(g+'_').toLowerCase():'';$('q').value=state.q;
if(bdMode==='notes'&&b.querySelector('.bdg.rk'))state.f.rtk=true;drawTabs();render();scrollTo(0,0);});

