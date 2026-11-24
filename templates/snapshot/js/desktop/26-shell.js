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
  stuckHeads();
  renderProps();
  renderWide();
  renderStatus();
  keepHover();
}
function refresh() {
  storeReview();
  if (isMob()) return mRender();
  renderTop();
  renderQuick();
  renderTree();
  renderList();
  stuckHeads();
  renderProps();
  renderWide();
  renderStatus();
  keepHover();
}
/* What the mouse is on, said again after a redraw (the live page's data, every few seconds):
   the browser re-reads :hover on the next move only, so what shows on hover hid then came back --
   a blink under a still mouse. .hov on the new elements under it (CSS: with :hover), until it moves. */
let PTR = null,
  HOV = [];
document.addEventListener(
  'mousemove',
  e => {
    PTR = [e.clientX, e.clientY];
    if (HOV.length) {
      HOV.forEach(el => el.classList.remove('hov'));
      HOV = [];
    }
  },
  { passive: true }
);
document.documentElement.addEventListener('mouseleave', () => (PTR = null));
function keepHover() {
  if (!PTR) return;
  for (let el = document.elementFromPoint(PTR[0], PTR[1]); el && el !== document.body; el = el.parentElement) {
    if (!el.classList.contains('hov')) {
      el.classList.add('hov');
      HOV.push(el);
    }
  }
}

function closeMenus() {
  document.querySelectorAll('.menu').forEach(m => (m.hidden = true));
  document.querySelectorAll('[data-menu]').forEach(b => b.setAttribute('aria-expanded', 'false'));
  // Live data held while a menu was open: now.
  if (typeof pendData !== 'undefined' && pendData) setTimeout(() => pendData && applyData(pendData), 0);
}

/* A sequence's header stuck at the list's top: square (.stuck), a band across -- its block
   scrolled past its top. On scroll, and after each list drawn. */
function stuckHeads() {
  const L = $('#list');
  if (!L) return;
  const top = L.getBoundingClientRect().top;
  L.querySelectorAll('.grp > .grp-h').forEach(h => h.classList.toggle('stuck', h.parentElement.getBoundingClientRect().top < top - 0.5));
}
{
  let raf = 0;
  $('#list')?.addEventListener(
    'scroll',
    () => {
      if (!raf)
        raf = requestAnimationFrame(() => {
          raf = 0;
          stuckHeads();
        });
    },
    { passive: true }
  );
}
