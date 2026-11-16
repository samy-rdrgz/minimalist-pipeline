/* ---------- Watch large: the player the whole window, the departments
and the notes at their frames beside it ---------- */
var wlDep=null;
function groupFiles(){var it=PL?PL.it:D[cur];return D.filter(function(x){return x.tab===it.tab&&x.group===it.group&&match(x);});}
function openWatch(autoplay){if(cur==null)return;var p=playerFor(D[cur]);if(!p)return;$('wl').hidden=false;lockPage('wl',true);document.body.classList.add('wl-open');
mount($('wl-pv'),'wide');wlSide();if(autoplay)p.el.play();$('wl-x').focus({preventScroll:true});}
function closeWatch(){if($('wl').hidden)return;if(document.fullscreenElement)document.exitFullscreen();$('wl').hidden=true;lockPage('wl',false);document.body.classList.remove('wl-open');
if(PL)PL.el.pause();var pv=$('pv');if(pv&&PL&&PL.it===D[cur])mount(pv,'panel');}
// The group's files along the bottom: a click plays one.
function drawStrip(){var st=q('.strip');if(!st)return;var g=groupFiles();
st.innerHTML='<span class="st-l">'+esc(PL.it.group)+' · '+plural(g.length,PL.it.kind==='shot'?'shot':'file')+'</span>'+g.map(function(x){var has=allVideos(x).length;
return '<button type="button" class="st-i'+(x===PL.it?' on':'')+'" data-wlf="'+x.i+'"'+(has?'':' disabled')+' title="'+esc(x.name)+(has?'':' · no video')+'"><span class="frame">'+(x.thumb?'<img alt="" src="'+img(x.thumb)+'">':'')+'</span>'+esc(x.name.slice(x.group.length+1)||x.name)+'</button>';}).join('');
var on=st.querySelector('.on');if(on)on.scrollIntoView({block:'nearest',inline:'center'});}
// The right column: the departments with ✓ / ✕, the notes at their
// frames (a click goes there), a retake written at the frame shown.
function wlSide(){if($('wl').hidden||cur==null)return;var it=D[cur],e=peek(it),rv=reviewing(),v=PL&&PL.v;
var deps=depsOf(it.kind).filter(function(d){return d in it.states;});if(deps.indexOf(wlDep)<0)wlDep=deps.filter(function(d){return (e.deps[d]||{}).no;})[0]||deps[0]||'';
$('wl-t').innerHTML=nameHtml(it);$('wl-s').innerHTML=(v?'<span>'+ico('render')+esc(v.folder||'')+'</span>':'')+(it.to_check?'<span>'+ico('eye')+'to check</span>':'');
var h='<div class="wl-h"><h4>Departments</h4>'+(it.tracked?dv(it.done,it.valid):'')+'</div>'+deps.map(function(d){var vv=e.deps[d],s=it.states[d],r=rtkTag(it,d);
return '<div class="wl-d'+(d===wlDep?' on':'')+'"><button type="button" class="wl-dn" data-wld="'+esc(d)+'" title="Write its retakes here">'+
'<span class="cell"><span class="cap"><span class="g '+symCls(it,d)+'">'+(validAt(it,d)?'✓':'')+'</span></span>'+(r?r[0]:'')+'</span>'+esc(cap(d))+'</button>'+
(rv?'<span class="rvb" data-d="'+esc(d)+'"><button class="ok-b" aria-pressed="'+!!(vv&&vv.ok)+'"'+(asTeam()||!isDone(s)?' disabled':'')+' aria-label="Validate '+esc(d)+'">✓</button>'+
'<button class="ko-b" aria-pressed="'+!!(vv&&vv.no)+'" aria-label="Retake '+esc(d)+'">✕</button></span>':'')+'</div>';}).join('');
var marks=PL?PL.marks:[];h+='<div class="wl-h"><h4>Notes at frames</h4><small>click to jump</small></div>'+(marks.length?marks.map(function(m){
return '<button type="button" class="wl-n" data-seek="'+m.a+'"><span class="ft'+(m.b?' rg':m.rtk?'':' nt')+'">'+esc(fLabel(v,m.a)+(m.b?'-'+m.b:''))+'</span>'+esc(m.text)+(m.who?'<small> · '+esc(m.who)+'</small>':'')+'</button>';}).join(''):'<p class="faint">No note at a frame on this video.</p>');
if(rv&&wlDep)h+='<div class="wl-w"><label for="wl-ta">Retake at <span class="addf-l">'+(v?esc(fLabel(v,frameNo(v,PL.el.currentTime))):'')+'</span> on '+esc(cap(wlDep))+'</label>'+
'<textarea id="wl-ta" rows="3" placeholder="Write while watching — Enter adds it"></textarea></div>';
else if(!rv)h+='<p class="faint wl-hint">Review to validate, send back and write at a frame.</p>';
$('wl-side').innerHTML=h;}
$('wl-x').addEventListener('click',closeWatch);
$('wl').addEventListener('click',function(ev){var t;
if((t=ev.target.closest('[data-wlf]'))){var x=D[+t.dataset.wlf];openPanel(x.i);var p=playerFor(x);mount($('wl-pv'),'wide');wlSide();p.el.play();return;}
if((t=ev.target.closest('[data-wld]'))){wlDep=t.dataset.wld;wlSide();var ta=$('wl-ta');if(ta)ta.focus();return;}
if((t=ev.target.closest('.rvb button'))&&!t.disabled){var it=D[cur],d=t.parentNode.dataset.d,e=entry(it),v=e.deps[d];
if(t.classList.contains('ok-b')){if(v&&v.ok)delete e.deps[d];else e.deps[d]={ok:1};}else{if(v&&v.no)delete e.deps[d];else e.deps[d]={no:1,text:''};wlDep=d;}
refresh();}});
// Enter adds the line at the frame shown to the department's retake.
$('wl').addEventListener('keydown',function(ev){var t=ev.target;if(t.id!=='wl-ta'||ev.key!=='Enter'||ev.shiftKey)return;ev.preventDefault();ev.stopPropagation();
var txt=t.value.trim();if(!txt||!PL||!wlDep)return;var it=D[cur],e=entry(it),v=e.deps[wlDep],f=frameNo(PL.v,PL.el.currentTime);
if(!v||!v.no)v=e.deps[wlDep]={no:1,text:''};v.text=(v.text?v.text.replace(/\s+$/,'')+NL:'')+'[f'+f+'] '+txt;t.value='';
PL.marks=marksOf(it,PL.v);drawMarks();refresh();var ta=$('wl-ta');if(ta)ta.focus();});
// A sequence's files, each one's videos in its shots' order, one after the other.
function groupVideos(g){return D.filter(function(it){return it.tab===state.tab&&it.group===g&&match(it);}).reduce(function(out,it){return out.concat(allVideos(it));},[]);}

