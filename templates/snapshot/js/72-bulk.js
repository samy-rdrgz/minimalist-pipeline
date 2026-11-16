/* ---------- several files' departments at once (review) ---------- */
// A department required, or not, on every file of a kind -- or those of a
// sequence / prefix, or those with another department --: what File
// settings does to one, done to each (your review; the live page sends it).
function bulkTargets(o){return D.filter(function(it){if(it.kind!==o.kind)return false;if(o.scope==='group'&&it.group!==o.group)return false;
if(o.scope==='with'&&!(o.other in it.states))return false;var e=peek(it),has=o.dep in e.req?e.req[o.dep]:o.dep in it.states;return has!==o.on;});}
function bulkDialog(){var tab=state.tab==='asset'||state.tab==='library'?'asset':'shot',o={kind:tab,dep:depsOf(tab)[0]||'',on:true,scope:'all',group:'',other:''};
var dl=$('dlg');var draw=function(){var deps=depsOf(o.kind),groups=[],seen={};D.forEach(function(it){if(it.kind===o.kind&&!seen[it.group]){seen[it.group]=1;groups.push(it.group);}});
if(deps.indexOf(o.dep)<0)o.dep=deps[0]||'';if(o.scope==='group'&&groups.indexOf(o.group)<0)o.group=groups[0]||'';if(o.scope==='with'&&(deps.indexOf(o.other)<0||o.other===o.dep))o.other=deps.filter(function(d){return d!==o.dep;})[0]||'';
var opt=function(list,v,lab){return list.map(function(x){return '<option value="'+esc(x)+'"'+(x===v?' selected':'')+'>'+esc(lab?lab(x):x)+'</option>';}).join('');};
var n=bulkTargets(o).length;
dl.innerHTML='<div class="dlg-in sh-dlg" role="dialog" aria-modal="true" aria-labelledby="bk-t"><h3 id="bk-t">Departments of several files</h3><form class="sh-form" onsubmit="return false">'+
'<label>Files <select data-bk="kind">'+opt(['shot','asset'],o.kind,function(k){return k==='shot'?'Shots':'Assets';})+'</select></label>'+
'<label>Department <select data-bk="dep">'+opt(deps,o.dep,cap)+'</select></label>'+
'<label>Make it <select data-bk="on">'+opt(['1','0'],o.on?'1':'0',function(v){return v==='1'?'required':'not required';})+'</select></label>'+
'<label>On <select data-bk="scope">'+opt(['all','group','with'],o.scope,function(v){return v==='all'?'every file':v==='group'?(o.kind==='shot'?'a sequence':'a prefix'):'the files with…';})+'</select></label>'+
(o.scope==='group'?'<label>'+(o.kind==='shot'?'Sequence':'Prefix')+' <select data-bk="group">'+opt(groups,o.group)+'</select></label>':'')+
(o.scope==='with'?'<label>With <select data-bk="other">'+opt(deps.filter(function(d){return d!==o.dep;}),o.other,cap)+'</select></label>':'')+
'</form><p class="sh-note">'+(n?plural(n,'file')+' to change -- in your review'+(META.live?', sent to Blender a moment after':', sent with it')+'; File settings shows each.':'Nothing to change: every one of them already is.')+'</p>'+
'<div class="acts"><button class="btn" data-bkx>Cancel</button><button class="btn primary" data-bkgo'+(n?'':' disabled')+'>'+(o.on?'Require':'Make not required')+(n?' on '+plural(n,'file'):'')+'</button></div></div>';};
draw();dl.hidden=false;
dl.onchange=function(e){var k=e.target.dataset.bk;if(!k)return;o[k]=k==='on'?e.target.value==='1':e.target.value;draw();};
dl.onclick=function(e){if(e.target===dl||e.target.closest('[data-bkx]')){dl.hidden=true;dl.onchange=null;return;}
if(!e.target.closest('[data-bkgo]'))return;var list=bulkTargets(o);
list.forEach(function(it){var re=entry(it),was=o.dep in it.states;if(o.on===was)delete re.req[o.dep];else re.req[o.dep]=o.on;});
dl.hidden=true;dl.onchange=null;save();render();if(cur!=null)refresh();toast(cap(o.dep)+(o.on?' required':' not required')+' on '+plural(list.length,'file')+'.');};}
var bkb=$('bulk-dep');if(bkb)bkb.addEventListener('click',function(){closeMenus();bulkDialog();});
