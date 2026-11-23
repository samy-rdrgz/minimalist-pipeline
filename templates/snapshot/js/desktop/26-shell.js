/* ---------- Status ---------- */
/* The status bar: the keys of the tab shown (the Farm's: its jobs; the others': the files,
   the review's), and what's counted on the right -- the farm's rendering time left on the
   Farm tab, the project's progress elsewhere. */
function renderStatus() {
  const farm = S.ws === 'farm',
    key = (ks, what) => `<span class="gk">${ks.map(k => `<span class="kbd">${k}</span>`).join('')}<span>${what}</span></span>`;
  $('#sb-keys').innerHTML = farm
    ? key(['↑', '↓'], T('Job')) + key(['?'], T('Keys'))
    : key(['↑', '↓'], T('File')) +
      key(['W'], T('Watch large')) +
      (S.review ? key(['V'], T('Validate the done')) + key(['X'], T('Retake')) : '') +
      key(['?'], T('Keys'));
  $('#sb-stats').innerHTML = farm
    ? farmLeftHTML()
    : (M.reading ? `<span class="tag warn">${T('partial')}</span> ` : '') +
      `${T('Shots {done} done · {valid} validated', { done: pct(M.progress.shot), valid: pct(M.validation.shot) })} <span class="faint">· Assets ${pct(M.progress.asset)} · ${pct(M.validation.asset)}</span>`;
  $('#sb-ver').textContent = M.addon_version || '';
}
let mt;
function msg(t) {
  if (isMob()) return toast(t);
  $('#sb-msg').textContent = t;
  clearTimeout(mt);
  mt = setTimeout(() => ($('#sb-msg').textContent = ''), 7000);
}
/* A step that can't be taken back, asked twice in the page itself (a browser's confirm() can be blocked: an app's viewer, a phone): the first click arms the button for 4 s. */
function twice(b, label) {
  if (b.dataset.armed) return true;
  b.dataset.armed = '1';
  const o = b.innerHTML,
    c = b.classList.contains('alert');
  b.innerHTML = label;
  b.classList.add('alert');
  setTimeout(() => {
    if (b.isConnected && b.dataset.armed) {
      delete b.dataset.armed;
      b.innerHTML = o;
      if (!c) b.classList.remove('alert');
    }
  }, 4000);
  return false;
}
function toast(t) {
  const e = document.createElement('div');
  e.className = 'toast';
  e.setAttribute('role', 'status');
  e.textContent = t;
  document.body.appendChild(e);
  setTimeout(() => e.remove(), 2800);
}
function renderAll() {
  storeReview();
  document.documentElement.classList.toggle('is-mob', isMob());
  if (isMob()) return mRender();
  renderTop();
  renderQuick();
  renderTree();
  renderList();
  renderProps();
  renderWide();
  renderStatus();
}
function refresh() {
  storeReview();
  if (isMob()) return mRender();
  renderTop();
  renderQuick();
  renderTree();
  renderList();
  renderProps();
  renderWide();
  renderStatus();
}

function closeMenus() {
  document.querySelectorAll('.menu').forEach(m => (m.hidden = true));
  document.querySelectorAll('[data-menu]').forEach(b => b.setAttribute('aria-expanded', 'false'));
}
