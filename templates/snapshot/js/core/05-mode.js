/* ---------- Mode : snapshot ou live ----------
   snapshot : le fichier HTML exporté, ouvert hors ligne, avec le dossier des vidéos à côté. Revue seule.
   live     : la page servie par Blender (lib/live.py). Revue + Farm + actions envoyées à Blender.
   L'addon n'écrit meta.live qu'en live.
   Tout ce qui n'existe qu'en live porte la classe .live-only (cachée par le CSS en snapshot). */
const Q=new URLSearchParams(location.search);
/* meta.live: only on the page Blender serves. */
const MODE=RAW.meta&&RAW.meta.live?'live':'snapshot',LIVE=MODE==='live';
if(!M.live)M.live={user:'',role:''};
document.documentElement.dataset.mode=MODE;
/* Affichage : desktop (souris, ou tablette en paysage) ou mobile (tactile ET étroit). Même état, mêmes actions. */
const MOB_Q=matchMedia('(pointer:coarse) and (max-width:900px)');
let VIEW=Q.get('view');  // 'mobile' | 'desktop' | null (automatique)
const isMob=()=>VIEW==='mobile'||(VIEW!=='desktop'&&MOB_Q.matches);
function setView(v){VIEW=v;S.m.sheet=null;renderAll()}
