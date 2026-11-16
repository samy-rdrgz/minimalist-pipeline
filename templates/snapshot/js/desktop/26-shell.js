/* ---------- Status ---------- */
function renderStatus(){
  $('#sb-stats').innerHTML=`Plans ${pct(M.progress.shot)} fait · ${pct(M.validation.shot)} validé <span class="faint">· Assets ${pct(M.progress.asset)} · ${pct(M.validation.asset)} · Minimalist Pipeline ${M.addon_version}</span>`;
  $('#sb-rv').style.display=S.review?'':'none';
}
let mt;function msg(t){if(isMob())return toast(t);$('#sb-msg').textContent=t;clearTimeout(mt);mt=setTimeout(()=>$('#sb-msg').textContent='',7000)}
function toast(t){const e=document.createElement('div');e.className='toast';e.setAttribute('role','status');e.textContent=t;document.body.appendChild(e);setTimeout(()=>e.remove(),2800)}
function renderAll(){storeReview();document.documentElement.classList.toggle('is-mob',isMob());if(isMob())return mRender();renderTop();renderQuick();renderTree();renderList();renderProps();renderWide();renderStatus()}
function refresh(){storeReview();if(isMob())return mRender();renderTop();renderQuick();renderTree();renderList();renderProps();renderWide()}

function closeMenus(){document.querySelectorAll('.menu').forEach(m=>m.hidden=true);document.querySelectorAll('[data-menu]').forEach(b=>b.setAttribute('aria-expanded','false'))}
