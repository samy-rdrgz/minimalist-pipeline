/* ---------- live: a phone -- an access for someone on the network ---------- */
// Their name, role, how long (a week at most): a link and its QR code,
// Copy link beside; the accesses running, each revoked in a click.
// An end: its time today, else its day and time.
function fmtUntil(iso){var d=new Date(iso);if(isNaN(d))return esc(iso||'');var t=two(d.getHours())+':'+two(d.getMinutes());return d.toDateString()===new Date().toDateString()?t:fmtDay(d)+' '+t;}
function shareDialog(made){var dl=$('dlg');dl.innerHTML='<div class="dlg-in sh-dlg" role="dialog" aria-modal="true" aria-labelledby="sh-t"><h3 id="sh-t">Share with a phone</h3><div id="sh-body"><p class="faint">Reading…</p></div><div class="acts"><button class="btn" data-shx>Done</button></div></div>';dl.hidden=false;
dl.onclick=function(e){if(e.target===dl||e.target.closest('[data-shx]')){dl.hidden=true;return;}
var b=e.target.closest('[data-shrev]');if(b)return shareSend({revoke:b.dataset.shrev});
if(e.target.closest('#sh-make')){var n=$('sh-name').value.trim();if(!n){$('sh-name').focus();return;}var ipSel=$('sh-ip');if(ipSel)SHARE_IP=ipSel.value;return shareSend({name:n,role:$('sh-role').value,hours:$('sh-time').value,ip:SHARE_IP});}
if(e.target.closest('#sh-copy'))copyLink($('sh-link').value);};
shareSend({});}
function shareSend(body){var late=setTimeout(function(){var b=$('sh-body');if(b&&!b.querySelector('form'))b.innerHTML='<p class="faint">Blender doesn\'t answer -- busy, or this page is open in many tabs (each holds a connection): close the others.</p>';},10000);
livePost('share',body).then(function(res){clearTimeout(late);if(!res.ok){toast('Not shared: '+(res.error||'?'));if(!$('sh-body').querySelector('form'))shareDraw(res);return;}shareDraw(res);})
.catch(function(){clearTimeout(late);toast('Blender doesn\'t answer.');});}
function shareDraw(res){var roles=['team'].concat((META.roles||[]).filter(function(r){return r!=='team';})),h='';
if(res.link)h+='<div class="sh-made"><div class="sh-qr">'+res.qr+'</div><div class="sh-info"><b>'+esc(res.name)+'</b> · '+esc(res.role)+'<br><small>until '+fmtUntil(res.until)+'</small>'+
'<p class="faint">'+(res.via==='Tailscale'?'Scan it on a phone with Tailscale on, wherever it is':'Scan it on the same network (the studio\'s Wi-Fi)')+' -- or send the link:</p><input id="sh-link" readonly value="'+esc(res.link)+'"><button type="button" class="act fix" id="sh-copy">'+ico('link')+'Copy link</button></div></div>';
h+='<form class="sh-form" onsubmit="return false"><label>Name <input id="sh-name" maxlength="40" placeholder="Who it is for" autocomplete="off"></label>'+
'<label>Role <select id="sh-role">'+roles.map(function(r){return '<option'+(r==='team'?' selected':'')+'>'+esc(r)+'</option>';}).join('')+'</select></label>'+
(function(){var ad=res.addresses||[];if(ad.length)SHARE_IP=SHARE_IP&&ad.some(function(a){return a.ip===SHARE_IP;})?SHARE_IP:ad[0].ip;
return ad.length>1?'<label>Reached through <select id="sh-ip">'+ad.map(function(a){return '<option value="'+esc(a.ip)+'"'+(a.ip===SHARE_IP?' selected':'')+'>'+esc(a.kind)+' · '+esc(a.ip)+'</option>';}).join('')+'</select></label>':'';})()+
'<label>For <select id="sh-time">'+SHARE_TIMES.map(function(t){return '<option value="'+t[0]+'"'+(t[0]==='eod'?' selected':'')+'>'+t[1]+'</option>';}).join('')+'</select></label>'+
'<button type="button" class="btn primary" id="sh-make">Make the access</button></form>'+
'<p class="faint sh-note">They review as that name and role -- notes, validations, assignees; the farm read only; nothing opened on this machine. Blender stays open here for it to work.</p>';
var g=res.guests||[];if(g.length)h+='<div class="st-l">Running</div>'+g.map(function(x){return '<div class="sh-g"><span><b>'+esc(x.name)+'</b> · '+esc(x.role)+' · until '+fmtUntil(x.until)+(x.ip?' <small class="faint">'+esc(x.ip)+'</small>':'')+'</span><button type="button" class="act ko" data-shrev="'+esc(x.token)+'">Revoke</button></div>';}).join('');
$('sh-body').innerHTML=h;}
function copyLink(t){var done=function(){toast('Link copied.');};
if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(t).then(done,function(){var i=$('sh-link');i.select();toast('Selected: copy it with Ctrl+C.');});
else{var i=$('sh-link');i.select();toast('Selected: copy it with Ctrl+C.');}}
// Two answers or more: [[label, then, primary]].
function askMany(text,choices){var dl=$('dlg');dl.innerHTML='<div class="dlg-in" role="alertdialog" aria-modal="true" aria-labelledby="ask-t"><p id="ask-t" class="ask">'+esc(text)+'</p><div class="acts"><button class="btn" data-o="-1">Cancel</button>'+
choices.map(function(c,n){return '<button class="btn'+(c[2]?' primary':'')+'" data-o="'+n+'">'+esc(c[0])+'</button>';}).join('')+'</div></div>';dl.hidden=false;
dl.onclick=function(e){var b=e.target.closest('[data-o]');if(e.target!==dl&&!b)return;dl.hidden=true;if(b&&+b.dataset.o>=0)choices[+b.dataset.o][1]();};}
$('list').addEventListener('click',function(e){var b=e.target.closest('.farm [data-goto]');if(b){e.preventDefault();return jump(D[+b.dataset.goto]);}
if((b=e.target.closest('.farm [data-ffs]'))){FF.s=b.dataset.ffs;return render();}
if(e.target.closest('.farm [data-ffm]')){FF.mine=!FF.mine;return render();}
var sm=e.target.closest('.farm details.job>summary');if(sm&&!e.target.closest('button')){e.preventDefault();var dj=sm.parentNode;
if(dj.dataset.wk!=null)WOPEN[dj.dataset.wk]=!WOPEN[dj.dataset.wk];else JOPEN[dj.dataset.job]=!JOPEN[dj.dataset.job];return render();}
var wk=e.target.closest('.farm [data-wk]'),uuid=wk?wk.dataset.wk:'',wd=(WD[uuid]||{}).d;
if((b=e.target.closest('[data-wstop]'))&&wk){var name=wk.querySelector('.jf').textContent;
if(!b.dataset.wstop)return farmPost('stop_worker','',uuid);
return askMany(name+' is rendering right now. After this frame: the frame it\'s on is written, then it stops. Stop now: its frame in progress is lost, freed for another machine.',
[['After this frame',function(){farmPost('stop_worker','',uuid,{now:false});}],['Stop now',function(){farmPost('stop_worker','',uuid,{now:true});},true]]);}
var j=e.target.closest('.farm [data-job]'),id=j?j.dataset.job:'',job=(DATA.farm.jobs||[]).filter(function(x){return x.id===id;})[0];
if((b=e.target.closest('[data-prio]'))&&job){e.preventDefault();var pv=Math.max(0,job.priority+(+b.dataset.prio));job.priority=pv;b.parentNode.querySelector('b').textContent=pv;return farmPost('priority',id,pv);}
if((b=e.target.closest('.farm [data-open]'))&&id)return farmPost('open',id,b.dataset.open);
if(!(b=e.target.closest('.farm [data-farm]')))return;e.preventDefault();var act=b.dataset.farm;
if(act==='worker'){var on=!!b.dataset.v,me=DATA.farm.me||{};if(!on&&me.rendering)return ask('This machine is rendering: stop its render now? Its frame in progress is lost, sent to another machine.','Stop now',function(){farmPost('worker','',false);});return farmPost('worker','',on);}
if(act==='forget_worker')return farmPost('forget_worker','',uuid);
if(act==='archive_all')return ask('Archive every '+b.dataset.v+' job?','Archive them',function(){farmPost('archive_all','',b.dataset.v);});
if(act==='cancel')return ask('Cancel the render of '+job.file+'?','Cancel it',function(){farmPost('cancel',id);});
if(act==='remove')return ask('Take '+job.file+' out of the queue? Nothing of it rendered yet.','Remove it',function(){farmPost('remove',id,!!job.pending);});
farmPost(act,id);});
$('list').addEventListener('input',function(e){var t=e.target;
if(t.classList.contains('ffq')){FF.q=t.value.trim().toLowerCase();render();var q=$('list').querySelector('.ffq');if(q){q.focus();q.setSelectionRange(q.value.length,q.value.length);}return;}
if(t.dataset.lk!=null){LKF[t.dataset.lk]=t.value;var L=((JD[t.dataset.lk]||{}).d||{}).lookup;if(L)t.closest('.flk').querySelector('.flk-r').textContent=lookupText(L,t.value);}});
