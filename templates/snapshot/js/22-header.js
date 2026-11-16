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
var W=META.weights;
$('weights').textContent='Each required department counts the same: not started 0 %, in progress '+W.wip+' %, done but reworked since '+W.rework+
' %, done with an open RTK '+W.rtk+' %, done 100 %. A file averages its departments — a retake on no department counts as an RTK on one of its done departments —, a group its files.'+
(META.role?' Validated, apart: the share of the required departments '+META.role+' (or an equivalent role) validated at the stable shown — a newer stable needs it again.':'');

