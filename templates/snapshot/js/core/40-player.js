/* ---------- The player: one <video>, moved into the stage shown (detail, Watch large, phone) ----------
   S.frame: the video's frame, 1..NF. Shown and written as Blender's own number when the render
   says its first frame (fNo), else as is. With no video (not rendered, not found): the thumbnail. */
const FPS=()=>+M.fps||24;
let FIRST=null;
const fNo=i=>FIRST!=null?FIRST+i-1:i;
const fIdx=n=>FIRST!=null?n-FIRST+1:n;
const PV=document.createElement('video');PV.playsInline=true;PV.preload='auto';PV.className='pv';
PV.muted=S.muted;
function curVideo(){const it=typeof cur==='function'?cur():null;if(!it)return null;const m=mVer(it),v=m.V[m.i];return v&&v.video?{it,v,src:videoSrc(v.video)}:null}
function stageEl(){return S.wide?document.querySelector('#wide .w-stage'):isMob()?document.getElementById('m-player'):document.querySelector('#pbody .stage')}
function mountVideo(){const st=stageEl(),c=curVideo();
  if(!st||!c||!c.src){if(PV.parentNode)PV.remove();if(!PV.paused)PV.pause();FIRST=null;return}
  FIRST=c.v.first??null;
  const img=st.querySelector('img,.noimg');if(img)img.hidden=true;
  if(PV.parentNode!==st)st.insertBefore(PV,st.firstChild);
  if(PV.dataset.src!==c.src){const t=PV.dataset.src?(S.frame-1+.5)/FPS():0;PV.dataset.src=c.src;PV.src=c.src;PV.currentTime=t}
  PV.muted=S.muted;syncFrame()}
PV.addEventListener('loadedmetadata',()=>{if(PV.duration&&isFinite(PV.duration)){NF=Math.max(2,Math.round(PV.duration*FPS()));refreshPlayerUI()}});
PV.addEventListener('error',()=>{if(PV.dataset.src){toast('Vidéo introuvable : choisissez le dossier des vidéos (Affichage).');PV.removeAttribute('src');delete PV.dataset.src;PV.remove();FIRST=null}});
PV.addEventListener('ended',()=>{S.playing=false;syncPlay();if(isMob()){mEnd();return}if(S.seqPlay&&S.wide)seqNext()});
const tickV=()=>{if(!PV.paused){S.frame=Math.min(NF,Math.floor(PV.currentTime*FPS()+1e-3)+1);syncFrame()}PV.requestVideoFrameCallback?PV.requestVideoFrameCallback(tickV):null};
if(PV.requestVideoFrameCallback)PV.requestVideoFrameCallback(tickV);else PV.addEventListener('timeupdate',()=>{S.frame=Math.min(NF,Math.floor(PV.currentTime*FPS()+1e-3)+1);syncFrame()});
/* What shows the frame: its number (Blender's), the playhead, a range being written. */
function syncFrame(){document.querySelectorAll('[data-f]').forEach(e=>e.textContent=fNo(S.frame));
  document.querySelectorAll('[data-scrub]').forEach(s=>{s.setAttribute('aria-valuenow',S.frame);const ph=s.querySelector('.ph');if(ph)ph.style.left=((S.frame-1)/(NF-1)*100)+'%';const r=s.querySelector('#rng-sel');
    if(r&&S.rangeStart!=null){r.style.left=((Math.min(S.rangeStart,S.frame)-1)/(NF-1)*100)+'%';r.style.width=(Math.abs(S.frame-S.rangeStart)/(NF-1)*100)+'%'}})}
function syncPlay(){document.querySelectorAll('[data-tp="play"]').forEach(b=>b.innerHTML=ic(S.playing?'b-pause':'b-play'))}
/* The frame count known once the video says its length: what was drawn with the old count, again. */
function refreshPlayerUI(){if(isMob())mRender();else{renderProps();if(S.wide)renderWide()}}
function setFrame(f){S.frame=Math.min(NF,Math.max(1,f));if(PV.parentNode&&PV.dataset.src){PV.pause();S.playing=false;syncPlay();PV.currentTime=(S.frame-1+.5)/FPS()}syncFrame()}
/* No video: the thumbnail, its frames counted at the project's rate. */
let playT;function togglePlay(){S.playing=!S.playing;clearInterval(playT);
  if(PV.parentNode&&PV.dataset.src){if(S.playing){if(S.frame>=NF)PV.currentTime=0;PV.play().catch(()=>{S.playing=false;syncPlay()})}else PV.pause();syncPlay();return}
  if(S.playing)playT=setInterval(()=>{if(S.frame>=NF){if(isMob()){mEnd();return}if(S.seqPlay&&S.wide){seqNext();return}setFrame(1)}else{S.frame++;syncFrame()}},1000/FPS());
  syncPlay()}
let drag=null;
document.addEventListener('pointerdown',e=>{const s=e.target.closest('[data-scrub]');if(!s||e.target.closest('.mk'))return;drag=s;s.setPointerCapture(e.pointerId);sx(s,e.clientX)});
document.addEventListener('pointermove',e=>{if(drag)sx(drag,e.clientX)});
document.addEventListener('pointerup',()=>drag=null);
function sx(s,x){const r=s.getBoundingClientRect();setFrame(Math.round(1+(x-r.left)/r.width*(NF-1)))}


/* ---------- Comparer A / B ----------
   Deux versions du même fichier, la même frame. A = S.ver[nom] (le choix de version habituel), B = S.m.b[nom].
   S.m.side dit laquelle on regarde. Partagé par le bureau (détail, En grand) et le mobile. */
S.m={tab:'review',side:'A',b:{},filter:'',kind:'shot',sheet:null,ctype:'rtk',cdept:null,loop:false};
function mVer(it){const V=versOf(it),a=Math.min(S.ver[it.name]||0,Math.max(0,V.length-1));
  let b=S.m.b[it.name];if(b==null||b>=V.length)b=V.length>1?(a===0?1:0):a;return {V,a,b,i:S.m.side==='B'&&V.length>1?b:a}}
