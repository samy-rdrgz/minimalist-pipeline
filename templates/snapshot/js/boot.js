restoreReview();
/* A link to a file (#its name, or its .blend's: any version of it) opens it; #farm, the Farm. */
{const h=decodeURIComponent(location.hash.slice(1)),it=h&&(items.find(i=>i.name===h||i.file===h||i.stableFile===h)||items.find(i=>i.name===h.replace(/_v\d+.*$/i,'')));
  if(it){S.sel=it.name;S.ws=it.kind}else if(h==='farm'&&LIVE)S.ws='farm'}
try{const t=localStorage.getItem('mp-snapshot:theme');if(t)S.theme=t}catch(_){}
setTheme(S.theme);matchMedia('(prefers-color-scheme: light)').addEventListener?.('change',()=>{if(S.theme==='system')setTheme('system')});
MOB_Q.addEventListener?.('change',()=>renderAll());
if(!LIVE&&S.ws==='farm')S.ws='shot';
/* The video follows each view drawn: into the stage it shows. */
renderProps=(f=>function(){const r=f.apply(this,arguments);mountVideo();return r})(renderProps);
renderWide=(f=>function(){const r=f.apply(this,arguments);mountVideo();return r})(renderWide);
mRender=(f=>function(){const r=f.apply(this,arguments);mountVideo();return r})(mRender);
renderAll();
liveStart();
/* For tests and the console: the page's state and actions. */
window.MPPage={S,items,A,reviewFile,reviewActions,fromActions,refresh,renderAll};
