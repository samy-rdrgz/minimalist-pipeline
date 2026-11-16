/* ---------- Liens : canvas ---------- */
function renderGraph(){
  const L=$('#list');const linked=new Set();items.forEach(i=>{if(i.links.length||i.linkedBy.length)linked.add(i.name)});
  const show=i=>(S.gAll||linked.has(i.name))&&(!S.q||i.name.toLowerCase().includes(S.q));
  const assets=items.filter(i=>i.kind==='asset'&&show(i)),shots=items.filter(i=>i.kind==='shot'&&show(i));
  const focus=S.gFocus,near=new Set();if(focus){const f=items.find(i=>i.name===focus);near.add(focus);f.links.forEach(l=>near.add(l.name));f.linkedBy.forEach(n=>near.add(n))}
  const node=i=>{const dim=focus&&!near.has(i.name);
    return `<div class="node gnode ${i.kind==='shot'?'shot':''} ${focus===i.name?'cur':''} ${dim?'dim':''}" data-gn="${i.name}" data-k="${i.kind}" title="${i.name}">
      <div class="nh">${ic(i.kind==='shot'?'b-camera_data':'b-asset_manager')}<span>${i.name}</span><span class="dt" style="background:${DOT[worst(i)]}"></span></div><div class="nb">
      ${i.links.map(l=>`<div class="sock in ${l.newer?'bad':''}" data-gi="${l.name}"><i></i>${l.name} · ${verOf(l.file)}${l.newer?' (ancien)':''}</div>`).join('')}
      ${i.linkedBy.length?`<div class="sock out" data-go="${i.name}"><i></i>lié par ${i.linkedBy.length}</div>`:''}
      ${!i.links.length&&!i.linkedBy.length?'<div class="sock faint">aucun lien</div>':''}</div></div>`};
  const groups=[...new Set(shots.map(i=>i.group))];
  const nOld=items.reduce((a,i)=>a+i.links.filter(l=>l.newer).length,0);
  L.innerHTML=`<div class="gcanvas" id="gcanvas"><div class="gview" id="gview"><svg class="wires" id="gwires"></svg>
      ${[...assets,...shots].map(node).join('')}
    </div>
    <div class="gtools tl"><span class="dim">${linked.size} fichiers liés sur ${items.length}</span>${nOld?`<span class="tag rtk">${nOld} lien${nOld>1?'s':''} vers un ancien stable</span>`:''}
      <span class="join"><button class="btn sm" data-gall="0" aria-pressed="${!S.gAll}">Fichiers liés</button><button class="btn sm" data-gall="1" aria-pressed="${!!S.gAll}">Tous</button></span>
      ${focus?`<button class="btn sm" data-gclear>${ic('b-x')}${esc(focus)}</button>`:''}</div>
    <div class="gtools br"><span class="join"><button class="btn sm icon" data-gz="-1" aria-label="Dézoomer" title="Dézoomer">−</button><button class="btn sm" data-gz="0" title="Tout voir">${Math.round(S.g.z*100)} %</button><button class="btn sm icon" data-gz="1" aria-label="Zoomer" title="Zoomer">+</button></span></div>
    <div class="ghint">Glisser le fond : se déplacer · molette : zoomer · clic : ses liens · double clic : sa fiche</div></div>`;
  layoutGraph();applyG();if(!S.g.init){S.g.init=true;requestAnimationFrame(()=>fitG())}else requestAnimationFrame(drawGraph);
}
function layoutGraph(){
  const v=$('#gview');if(!v)return;const nodes=[...v.querySelectorAll('.gnode')],by=n=>v.querySelector(`[data-gn="${CSS.escape(n)}"]`);
  const shots=nodes.filter(n=>n.dataset.k==='shot').map(n=>n.dataset.gn),assets=nodes.filter(n=>n.dataset.k==='asset').map(n=>n.dataset.gn);
  const itm=n=>items.find(i=>i.name===n);const seqs=[...new Set(shots.map(n=>itm(n).group))];
  let sOrder={},aOrder={};shots.forEach((n,i)=>sOrder[n]=i);assets.forEach((n,i)=>aOrder[n]=i);
  const bary=(list,adj,ord)=>{const r={};list.forEach(n=>{const a=adj(n).filter(x=>x in ord);r[n]=a.length?a.reduce((s,x)=>s+ord[x],0)/a.length:1e6+(ord[n]||0)});return r};
  for(let k=0;k<4;k++){
    const ba=bary(assets,n=>itm(n).linkedBy,sOrder);assets.sort((a,b)=>ba[a]-ba[b]);assets.forEach((n,i)=>aOrder[n]=i);
    const bs=bary(shots,n=>itm(n).links.map(l=>l.name),aOrder);
    const sk=g=>{const xs=shots.filter(n=>itm(n).group===g).map(n=>bs[n]).filter(x=>x<1e6);return xs.length?xs.reduce((a,b)=>a+b,0)/xs.length:1e6};
    seqs.sort((a,b)=>sk(a)-sk(b));shots.sort((a,b)=>seqs.indexOf(itm(a).group)-seqs.indexOf(itm(b).group)||bs[a]-bs[b]);shots.forEach((n,i)=>sOrder[n]=i);
  }
  const W=Math.max(...nodes.map(n=>n.offsetWidth),200),GX=200,GY=18,CAP=34,x2=W+GX;let y=CAP,center={};
  v.querySelectorAll('.gcap').forEach(c=>c.remove());
  const cap=(t,x,yy)=>{const c=document.createElement('div');c.className='gcap';c.textContent=t;c.style.left=x+'px';c.style.top=yy+'px';v.appendChild(c)};
  let lastG=null;shots.forEach(n=>{const g=itm(n).group;if(g!==lastG){if(lastG)y+=16;cap(g,x2,y-24);lastG=g}const e=by(n);e.style.left=x2+'px';e.style.top=y+'px';center[n]=y+e.offsetHeight/2;y+=e.offsetHeight+GY});
  const tgt={};assets.forEach(n=>{const e=by(n),c=itm(n).linkedBy.filter(x=>x in center).map(x=>center[x]);tgt[n]=(c.length?c.reduce((a,b)=>a+b,0)/c.length:1e9)-e.offsetHeight/2});
  let ya=CAP;cap('Assets',0,CAP-24);assets.forEach(n=>{const e=by(n);const t=tgt[n]>=1e8?ya:Math.max(ya,tgt[n]);e.style.left='0px';e.style.top=t+'px';ya=t+e.offsetHeight+GY});
  v.style.width=(x2+W+20)+'px';v.style.height=(Math.max(y,ya)+20)+'px';
}
function applyG(){const v=$('#gview'),c=$('#gcanvas');if(!v)return;v.style.transform=`translate(${S.g.x}px,${S.g.y}px) scale(${S.g.z})`;
  const s=20*S.g.z;c.style.backgroundSize=`${s}px ${s}px`;c.style.backgroundPosition=`${S.g.x}px ${S.g.y}px`;const z=document.querySelector('[data-gz="0"]');if(z)z.textContent=Math.round(S.g.z*100)+' %'}
function fitG(){const v=$('#gview'),c=$('#gcanvas');if(!v||!c)return;const cw=c.clientWidth,ch=c.clientHeight,vw=v.offsetWidth,vh=v.offsetHeight;
  S.g.z=Math.max(.35,Math.min(1,(cw-40)/vw,(ch-90)/vh));S.g.x=(cw-vw*S.g.z)/2;S.g.y=Math.max(56,(ch-vh*S.g.z)/2);applyG();drawGraph()}
function zoomG(f,cx,cy){const c=$('#gcanvas');if(!c)return;const r=c.getBoundingClientRect();cx=cx??r.width/2;cy=cy??r.height/2;
  const z=Math.max(.3,Math.min(2.5,S.g.z*f));S.g.x=cx-(cx-S.g.x)*z/S.g.z;S.g.y=cy-(cy-S.g.y)*z/S.g.z;S.g.z=z;applyG()}
function centerG(n){const c=$('#gcanvas'),e=document.querySelector(`[data-gn="${CSS.escape(n)}"]`);if(!c||!e)return;
  const cr=c.getBoundingClientRect(),er=e.getBoundingClientRect();S.g.x+=cr.left+cr.width/2-(er.left+er.width/2);S.g.y+=cr.top+cr.height/2-(er.top+er.height/2);applyG()}
function drawGraph(){
  const box=$('#gview');if(!box)return;const R=box.getBoundingClientRect(),z=S.g.z;let p='';const focus=S.gFocus;
  const pt=e=>{const r=e.getBoundingClientRect();return [(r.left+r.width/2-R.left)/z,(r.top+r.height/2-R.top)/z]};
  box.querySelectorAll('[data-gi]').forEach(n=>{const src=n.dataset.gi,o=box.querySelector(`[data-go="${src}"] i`);if(!o)return;
    const tgt=n.closest('[data-gn]').dataset.gn,hot=!focus||focus===src||focus===tgt;
    const [x1,y1]=pt(o),[x2,y2]=pt(n.querySelector('i'));const no=o.closest('.node'),nn=n.closest('.node');
    const ym=((Math.min(no.getBoundingClientRect().bottom,nn.getBoundingClientRect().bottom)+Math.max(no.getBoundingClientRect().top,nn.getBoundingClientRect().top))/2-R.top)/z;
    const c=n.classList.contains('bad')?'#e5575f':'#9a9a9a',d=wirePath(x1,y1,x2,y2,ym);
    p+=`<path d="${d}" fill="none" stroke="#111" stroke-width="4.5" opacity="${hot?1:.25}"/><path d="${d}" fill="none" stroke="${c}" stroke-width="2.4" opacity="${hot?1:.18}"/>`});
  const w=$('#gwires');w.setAttribute('width',box.offsetWidth);w.setAttribute('height',box.offsetHeight);w.innerHTML=p;
}
let gDrag=null;
document.addEventListener('pointerdown',e=>{const c=e.target.closest('#gcanvas');if(!c||e.target.closest('.node,.gtools,button'))return;gDrag={x:e.clientX,y:e.clientY,ox:S.g.x,oy:S.g.y,id:e.pointerId};c.setPointerCapture(e.pointerId);c.classList.add('grab')});
document.addEventListener('pointermove',e=>{if(!gDrag)return;S.g.x=gDrag.ox+e.clientX-gDrag.x;S.g.y=gDrag.oy+e.clientY-gDrag.y;applyG()});
document.addEventListener('pointerup',()=>{if(gDrag){gDrag=null;$('#gcanvas')?.classList.remove('grab')}});
document.addEventListener('wheel',e=>{const c=e.target.closest('#gcanvas');if(!c)return;e.preventDefault();const r=c.getBoundingClientRect();
  if(e.ctrlKey||Math.abs(e.deltaY)>Math.abs(e.deltaX)&&!e.shiftKey)zoomG(Math.exp(-e.deltaY*.0015),e.clientX-r.left,e.clientY-r.top);else{S.g.x-=e.deltaX;S.g.y-=e.deltaY;applyG()}},{passive:false});

