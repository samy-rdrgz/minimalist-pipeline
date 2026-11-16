/* ---------- Scrub & lecture ---------- */
function setFrame(f){S.frame=Math.min(NF,Math.max(1,f));document.querySelectorAll('[data-f]').forEach(e=>e.textContent=S.frame);
  document.querySelectorAll('[data-scrub]').forEach(s=>{s.setAttribute('aria-valuenow',S.frame);s.querySelector('.ph').style.left=((S.frame-1)/(NF-1)*100)+'%';const r=s.querySelector('#rng-sel');
    if(r&&S.rangeStart!=null){r.style.left=((Math.min(S.rangeStart,S.frame)-1)/(NF-1)*100)+'%';r.style.width=(Math.abs(S.frame-S.rangeStart)/(NF-1)*100)+'%'}})}
let playT;function togglePlay(){S.playing=!S.playing;clearInterval(playT);if(S.playing)playT=setInterval(()=>{if(S.frame>=NF){if(isMob()){mEnd();return}if(S.seqPlay&&S.wide){seqNext();return}setFrame(1)}else setFrame(S.frame+1)},1000/M.fps);
  document.querySelectorAll('[data-tp="play"]').forEach(b=>b.innerHTML=ic(S.playing?'b-pause':'b-play'))}
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
