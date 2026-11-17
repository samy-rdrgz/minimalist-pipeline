/* ---------- Mode: snapshot or live ----------
   snapshot: the exported HTML file, opened offline, its videos folder beside it. The review only.
   live:     the page Blender serves (lib/live.py). The review, the Farm, actions sent to Blender.
   meta.live is only there live.
   What only exists live has the class .live-only (hidden by the CSS in a snapshot). */
const Q=new URLSearchParams(location.search);
/* meta.live: only on the page Blender serves. */
const MODE=RAW.meta&&RAW.meta.live?'live':'snapshot',LIVE=MODE==='live';
if(!M.live)M.live={user:'',role:''};
document.documentElement.dataset.mode=MODE;
/* View: desktop (a mouse, or a tablet held wide) or phone (touch AND narrow). The same state, the same actions. */
const MOB_Q=matchMedia('(pointer:coarse) and (max-width:900px), (pointer:coarse) and (max-height:500px)');
let VIEW=Q.get('view');  // 'mobile' | 'desktop' | null (automatique)
const isMob=()=>VIEW==='mobile'||(VIEW!=='desktop'&&MOB_Q.matches);
function setView(v){VIEW=v;S.m.sheet=null;renderAll()}
