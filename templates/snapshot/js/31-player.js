/* ---------- the player: in the panel, or Watch large ---------- */
// One player (PL): its video element, mounted with its controls in the
// panel's media (compact) or in Watch large (wide) -- moved, not made
// again, so a video goes on playing from one to the other. Its timeline
// carries the file's notes at their frames: a retake's red diamond, a
// range's blue bar; a click goes there. See NOTES.md, "Snapshot page v3".
function clock(t){t=Math.floor(+t||0);return two(Math.floor(t/3600))+':'+two(Math.floor(t/60)%60)+':'+two(t%60);}
var FPS=+META.fps||0,PL=null,MUTE_KEY='mp-snapshot:muted',MUTED=false;try{MUTED=localStorage.getItem(MUTE_KEY)==='1';}catch(e){}
function setMuted(on){MUTED=on;if(PL)PL.el.muted=on;try{localStorage.setItem(MUTE_KEY,on?'1':'');}catch(e){}upd();}
function idxOf(t){return Math.max(0,Math.floor(t*FPS+1e-3));}
function frameNo(v,t){return v.start!=null?v.start+idxOf(t):idxOf(t)+1;}
function fLabel(v,n){return (v.start!=null?'f':'#')+n;}
// The frames tagged on a video: the file's open notes ("f12", "f12-30")
// on its shot or on none, then this review's lines ([f12], [f12-30]).
function marksOf(it,v){var out=[],own=function(sh){return !sh||!v.shots||v.shots.indexOf(sh)>=0||v.shots.indexOf(sh.replace(/^[a-z]+/i,''))>=0;};
it.notes.forEach(function(n){if(n.closed)return;var m=/f(\d+)(?:-(\d+))?/.exec(n.frames||'');if(!m||!own(n.shot))return;
out.push({a:+m[1],b:m[2]?+m[2]:null,rtk:n.type==='rtk'&&n.done===false,text:n.text,who:author(n),type:n.type,id:n.id});});
var e=peek(it),lines=[];Object.keys(e.deps).forEach(function(d){if(e.deps[d].text)lines=lines.concat(e.deps[d].text.split(NL).map(function(l){return [d,l];}));});
(e.text||'').split(NL).forEach(function(l){lines.push(['',l]);});
lines.forEach(function(x){var m=/\[f(\d+)(?:-(\d+))?\]/.exec(x[1]);if(!m)return;
out.push({a:+m[1],b:m[2]?+m[2]:null,rtk:!noteOnly(x[1]),text:x[1].replace(/\[[^\]]*\]\s*/g,''),who:'you',type:noteOnly(x[1])?'note':'rtk',mine:true});});
return out.sort(function(p,q){return p.a-q.a;});}
// The controls, by where the player is.
function plHtml(mode){var many=PL.list.length>1||mode==='wide';
return '<div class="pv-slot"></div><div class="pv-msg" hidden></div>'+
'<div class="tl"><div class="tl-in"><i class="tl-fill"></i><span class="tl-marks"></span><i class="tl-head"></i></div><input type="range" class="tl-r" min="0" max="1000" value="0" aria-label="Position"></div>'+
'<div class="pc">'+(mode==='wide'?'<button type="button" class="vb" data-pv="prevv" aria-label="Previous video" title="Previous video (←)">'+ico('rew')+'</button>':'')+
'<button type="button" class="vb" data-pv="-1" aria-label="Previous frame" title="Previous frame (,)">'+ico('fprev')+'</button>'+
'<button type="button" class="vb play pp" data-pv="pp" aria-label="Play">'+ico('play')+'</button>'+
'<button type="button" class="vb" data-pv="1" aria-label="Next frame" title="Next frame (.)">'+ico('fnext')+'</button>'+
(mode==='wide'?'<button type="button" class="vb" data-pv="nextv" aria-label="Next video" title="Next video (→)">'+ico('ff')+'</button>':'')+
// Sound: renders may carry it (docs/plan-1.2.md); muted or not, kept.
'<button type="button" class="vb snd" data-pv="mute" aria-label="Sound" title="Sound on / off (M)"></button>'+
'<span class="pf"><b class="pf-n">f–</b><span class="pf-r"></span></span><span class="pc-gap"></span>'+
(META.live&&!META.live.guest?'<button type="button" class="vb" data-pv="ext" aria-label="Open in this machine\'s player" title="Open in this machine\'s player -- the full video, not the page\'s light copy">'+ico('movie')+'</button>':'')+
(mode==='wide'?'<span class="strip"></span><button type="button" class="vb" data-pv="fs" aria-label="Full screen" title="Full screen">'+ico('fsin')+'</button>':
(many?'<span class="pv-at"></span>':'')+'<button type="button" class="btn wl-b" data-pv="wide" title="Watch large: the video, the departments and the notes at their frames">'+ico('fsin')+'Watch large</button>')+'</div>';}
// A list of videos into a host: the panel's (paused on its first frame,
// the thumbnail over it) or Watch large's.
function playerFor(it){var list=allVideos(it);if(!list.length)return null;
if(PL&&PL.it===it)return PL;
// The one before let go: paused, the browser would go on downloading it.
if(PL){PL.el.pause();PL.el.removeAttribute('src');PL.el.load();}
var el=document.createElement('video');el.playsInline=true;el.preload='metadata';el.muted=MUTED;if(it.thumb)el.poster=img(it.thumb);
PL={it:it,list:list,at:0,el:el,host:null,mode:'',marks:[]};wire(PL);load(0);return PL;}
function load(at){var v=PL.list[at];PL.at=at;PL.v=v;PL.marks=marksOf(PL.it,v);PL.el.src=v.src;}
function mount(host,mode){if(!PL||!host)return;PL.host=host;PL.mode=mode;host.innerHTML=plHtml(mode);host.querySelector('.pv-slot').appendChild(PL.el);
host.classList.toggle('pv-wide',mode==='wide');drawMarks();upd();if(mode==='wide')drawStrip();}
function q(c){return PL&&PL.host?PL.host.querySelector(c):null;}
function total(){return PL.el.duration&&FPS?Math.max(1,Math.round(PL.el.duration*FPS)):0;}
function drawMarks(){var box=q('.tl-marks'),n=total(),v=PL.v;if(!box)return;if(!n||v.start==null){box.innerHTML='';return;}
var at=function(f){return Math.max(0,Math.min(100,(f-v.start)/n*100));};
box.innerHTML=PL.marks.map(function(m){var tip=esc(fLabel(v,m.a)+(m.b?'-'+m.b:'')+' · '+m.text+(m.who?' · '+m.who:''));
return m.b?'<i class="tl-rg'+(m.mine?' mine':'')+'" data-seek="'+m.a+'" style="left:'+at(m.a)+'%;width:'+Math.max(.6,at(m.b)-at(m.a))+'%" title="'+tip+'"></i>':
'<i class="tl-mk'+(m.rtk?'':' nt')+(m.mine?' mine':'')+'" data-seek="'+m.a+'" style="left:'+at(m.a)+'%" title="'+tip+'"></i>';}).join('');}
// What changes as it plays: the frame, the head, ▶ / ❚❚, the "+ f12" of
// the retake boxes.
function upd(){if(!PL)return;var el=PL.el,v=PL.v,n=total(),f=frameNo(v,el.currentTime),pct2=el.duration?el.currentTime/el.duration*100:0;
var pn=q('.pf-n');if(pn)pn.textContent=fLabel(v,f);
var pr=q('.pf-r');if(pr)pr.textContent=(n?' / '+fLabel(v,v.start!=null?v.start+n-1:n):'')+(PL.mode==='wide'?' · '+clock(el.currentTime):'')+(FPS?' · '+FPS+' fps':'');
var hd=q('.tl-head');if(hd)hd.style.left=pct2+'%';var fl=q('.tl-fill');if(fl)fl.style.width=pct2+'%';
var rg=q('.tl-r');if(rg&&!PL.seeking)rg.value=Math.round(pct2*10);
var sn=q('.snd');if(sn&&sn.dataset.st!==String(el.muted)){sn.dataset.st=el.muted;sn.innerHTML=ico(el.muted?'mute':'sound');sn.setAttribute('aria-pressed',String(!el.muted));}
var pp=q('.pp');if(pp&&pp.dataset.st!==String(el.paused)){pp.dataset.st=el.paused;pp.innerHTML=ico(el.paused?'play':'pause');pp.setAttribute('aria-label',el.paused?'Play':'Pause');}
var at=q('.pv-at');if(at)at.textContent=(v.shot?v.shot+' · ':'')+(PL.at+1)+' / '+PL.list.length;
document.querySelectorAll('.addf').forEach(function(b){b.textContent='+ '+fLabel(v,f);});
document.querySelectorAll('.addf-l').forEach(function(b){b.textContent=fLabel(v,f);});
var wf=$('wl-f');if(wf)wf.textContent=fLabel(v,f);}
function seekFrame(f){if(!PL||!FPS)return;var v=PL.v,k=v.start!=null?f-v.start:f-1;PL.el.pause();PL.el.currentTime=Math.max(0,(k+.5)/FPS);upd();}
function stepFrame(n){if(!PL||!FPS)return;var el=PL.el;el.pause();var k=Math.max(0,idxOf(el.currentTime)+n),t=(k+.5)/FPS;if(el.duration)t=Math.min(t,el.duration-.5/FPS);el.currentTime=t;upd();}
function nextVideo(n){var at=PL.at+n;if(at>=0&&at<PL.list.length){load(at);PL.el.play();return true;}
// Past the file's last (Watch large): the group's next file with a video.
if(PL.mode!=='wide')return false;var g=groupFiles(),k=g.indexOf(PL.it)+n;while(g[k]&&!allVideos(g[k]).length)k+=n;
if(!g[k])return false;openPanel(g[k].i);var p=playerFor(g[k]);if(n<0)load(p.list.length-1);mount($('wl-pv'),'wide');wlSide();p.el.play();return true;}
function wire(P){var el=P.el;
// Its box takes the video's own shape.
el.addEventListener('loadedmetadata',function(){if(el.videoWidth&&el.videoHeight)el.style.setProperty('--ar',el.videoWidth+'/'+el.videoHeight);});
['timeupdate','play','pause','seeked','loadedmetadata'].forEach(function(k){el.addEventListener(k,function(){if(PL!==P)return;if(k==='loadedmetadata')drawMarks();upd();});});
if(el.requestVideoFrameCallback){var tick=function(){if(PL===P&&!el.paused)upd();el.requestVideoFrameCallback(tick);};el.requestVideoFrameCallback(tick);}
el.addEventListener('ended',function(){if(PL===P&&!nextVideo(1))upd();});
el.addEventListener('click',function(){if(el.paused)el.play();else el.pause();});
el.addEventListener('error',function(){if(PL!==P)return;var v=P.v,V=META.videos;
// The copy missing (a Folder snapshot opened without its folder): the
// render itself, in the project, if this machine reaches it.
if(v.from!=='local'&&v.from!=='picked'&&V&&V.local){v.from='local';v.src=V.local+'/'+encodeURI(v.name);el.src=v.src;return;}
// Said in place of the picture, the controls left out.
var m=q('.pv-msg');if(!m)return;P.host.classList.add('pv-err');m.hidden=false;
m.innerHTML=(v.from==='picked'?'This browser can\'t play this video\'s format (on an iPad or in Safari: an H.265 video compiled by an older add-on — compile it again).':
v.from==='zip'?'Video not found. Unzip <code>'+esc(V.base)+'.zip</code> next to this page, into a folder of the same name.':
v.from==='folder'?'Video not found: no <code>'+esc(V.base)+'</code> folder '+(V.base.indexOf('../')===0?'beside this page\'s folder (keep the snapshots folder whole)':'next to this page')+' — or this browser can\'t play its format.':
'Video not found in the project\'s renders — away from the project, its videos come with the snapshot (Folder or Zip, when exporting) — or this browser can\'t play its format.')+
(v.from==='picked'?'':' '+pickLink('Choose the videos folder…'))+'<br><small>Looked for <code>'+esc(v.name)+'</code></small>';});}
// The controls' clicks and the timeline's drag, wherever it's mounted.
document.addEventListener('click',function(e){var b=e.target.closest('[data-pv],[data-seek]');if(!b||!PL||!PL.host||!(PL.host.contains(b)||b.closest('#wl,.panel')))return;
if(b.dataset.seek){e.preventDefault();var f=+b.dataset.seek;if(b.dataset.sh){var it=PL.it,vs=PL.list;for(var k=0;k<vs.length;k++)if(vs[k].shots&&vs[k].shots.indexOf(b.dataset.sh)>=0&&k!==PL.at){load(k);break;}}
if(PL.el.readyState>=1)seekFrame(f);else PL.el.addEventListener('loadedmetadata',function o(){PL.el.removeEventListener('loadedmetadata',o);seekFrame(f);});return;}
var a=b.dataset.pv,el=PL.el;
if(a==='pp'){if(el.paused)el.play();else el.pause();}else if(a==='-1'||a==='1')stepFrame(+a);
else if(a==='ext'){el.pause();livePost('play',{video:PL.v.name}).then(function(res){toast(res.ok?'Opening '+res.opened+'…':'Not opened: '+(res.error||'?'));}).catch(function(){toast('Blender doesn\'t answer.');});}
else if(a==='mute')setMuted(!el.muted);else if(a==='prevv')nextVideo(-1);else if(a==='nextv')nextVideo(1);else if(a==='wide')openWatch(false);
else if(a==='fs'){var f2=$('wl').requestFullscreen||$('wl').webkitRequestFullscreen;if(document.fullscreenElement)document.exitFullscreen();else if(f2)f2.call($('wl'));}});
document.addEventListener('input',function(e){if(!e.target.classList.contains('tl-r')||!PL)return;PL.seeking=true;var el=PL.el;if(el.duration){el.pause();el.currentTime=e.target.value/1000*el.duration;}});
document.addEventListener('change',function(e){if(e.target.classList.contains('tl-r')&&PL){PL.seeking=false;upd();}});
