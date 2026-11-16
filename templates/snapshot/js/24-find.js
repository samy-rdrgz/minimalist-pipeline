/* ---------- find: filters the list, and jumps to any file ---------- */
var sugg=$('sugg'),hi=-1,found=[];
function suggest(){var q=state.q;hi=-1;if(!q){sugg.hidden=true;return;}
found=D.filter(function(it){return it.name.toLowerCase().indexOf(q)>=0;}).slice(0,8);
if(!found.length){sugg.hidden=true;return;}
sugg.innerHTML=found.map(function(it,n){return '<li><button type="button" role="option" data-n="'+n+'"><span>'+nameHtml(it)+'</span><small>'+
TABS.filter(function(t){return t[0]===it.tab;})[0][1]+(it.omit?' · '+(it.omit.state==='cancelled'?'cancelled':'on hold'):'')+'</small></button></li>';}).join('');sugg.hidden=false;}
// Not "pick": the page's selects' pick() (below, same scope) took the name.
function goTo(n){var it=found[n];if(!it)return;sugg.hidden=true;$('q').blur();jump(it);}
function jump(it){if(it.tab!==state.tab)setTab(it.tab);var k=state.tab+it.group;if(state.open[k]===false)state.open[k]=true;
if(hiddenFile(it))state.untracked[k]=true;render();openPanel(it.i);}
$('q').addEventListener('input',function(){state.q=this.value.trim().toLowerCase();render();suggest();});
$('q').addEventListener('focus',suggest);
$('q').addEventListener('keydown',function(e){var b=sugg.querySelectorAll('button');
if(e.key==='ArrowDown'||e.key==='ArrowUp'){if(sugg.hidden)return;e.preventDefault();hi=(hi+(e.key==='ArrowDown'?1:-1)+b.length)%b.length;
b.forEach(function(x,n){x.classList.toggle('hi',n===hi);});}
else if(e.key==='Enter'){e.preventDefault();goTo(hi<0?0:hi);}});
sugg.addEventListener('mousedown',function(e){e.preventDefault();});
sugg.addEventListener('click',function(e){var b=e.target.closest('button');if(b)goTo(+b.dataset.n);});
$('q').addEventListener('blur',function(){setTimeout(function(){sugg.hidden=true;},150);});

