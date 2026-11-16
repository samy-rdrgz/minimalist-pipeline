const h=decodeURIComponent(location.hash.slice(1));if(h&&items.some(i=>i.name===h)){S.sel=h;S.ws=items.find(i=>i.name===h).kind}
try{const t=localStorage.getItem('mp-snapshot:theme');if(t)S.theme=t}catch(_){}
setTheme(S.theme);matchMedia('(prefers-color-scheme: light)').addEventListener?.('change',()=>{if(S.theme==='system')setTheme('system')});
MOB_Q.addEventListener?.('change',()=>renderAll());
if(!LIVE&&S.ws==='farm')S.ws='shot';
renderAll();
