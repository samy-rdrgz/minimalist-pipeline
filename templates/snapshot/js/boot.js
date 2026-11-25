/* The page's own words (page.html): its data-t texts and its labels, in the page's language. */
document.querySelectorAll('[data-t]').forEach(e => {
  e.textContent = T(e.textContent.trim());
});
document.querySelectorAll('body [title],body [aria-label],body [placeholder]').forEach(e =>
  ['title', 'aria-label', 'placeholder'].forEach(a => {
    const v = e.getAttribute(a);
    if (v) e.setAttribute(a, T(v));
  })
);
document.querySelectorAll('[data-lang]').forEach(b =>
  b.setAttribute(
    'aria-checked',
    String(
      b.dataset.lang ===
        (() => {
          try {
            return (
              new URLSearchParams(location.search).get('lang') ||
              localStorage.getItem('mp-snapshot.lang') ||
              ''
            );
          } catch (_) {
            return '';
          }
        })()
    )
  )
);
restoreReview();
/* A link to a file (#its name, or its .blend's: any version of it) opens it; #farm, the Farm. */
{
  const h = decodeURIComponent(location.hash.slice(1)),
    it =
      h &&
      (items.find(i => i.name === h || i.file === h || i.stableFile === h) ||
        items.find(i => i.name === h.replace(/_v\d+.*$/i, '')));
  if (it) {
    S.sel = it.name;
    S.ws = it.kind;
  } else if (h === 'farm' && LIVE) S.ws = 'farm';
  else if (['todo', 'links', 'synth'].includes(h)) S.ws = h;
  else if (h === 'share' && LIVE && !guest()) setTimeout(shareDialog, 0);
}
document.documentElement.dataset.guest = guest() ? '1' : '';
document.documentElement.dataset.gfarm = guest() && M.live.farm ? '1' : '';
try {
  const t = localStorage.getItem('mp-snapshot.theme');
  if (t) S.theme = t;
} catch (_) {}
setTheme(S.theme);
matchMedia('(prefers-color-scheme: light)').addEventListener?.('change', () => {
  if (S.theme === 'system') setTheme('system');
});
MOB_Q.addEventListener?.('change', () => renderAll());
if (!LIVE && S.ws === 'farm') S.ws = 'shot';
/* The video follows each view drawn: into the stage it shows. */
/* F5 keeps where you were: the file (or the workspace) in the address (#its name, #farm),
   the detail's tab for this browser tab (sessionStorage) -- set as each view is drawn. */
try {
  const t = sessionStorage.getItem('mp-snapshot.tab');
  if (t && S.sel) S.tab = t;
} catch (_) {}
function syncPlace() {
  const h = (S.ws === 'shot' || S.ws === 'asset') && S.sel ? S.sel : S.ws;
  if (decodeURIComponent(location.hash.slice(1)) !== h)
    try {
      history.replaceState(null, '', location.pathname + location.search + '#' + encodeURIComponent(h));
    } catch (_) {}
  try {
    sessionStorage.setItem('mp-snapshot.tab', S.tab || '');
  } catch (_) {}
}
renderProps = (f =>
  function () {
    const r = f.apply(this, arguments);
    mountVideo();
    syncPlace();
    return r;
  })(renderProps);
renderWide = (f =>
  function () {
    const r = f.apply(this, arguments);
    mountVideo();
    return r;
  })(renderWide);
mRender = (f =>
  function () {
    const r = f.apply(this, arguments);
    mountVideo();
    syncPlace();
    return r;
  })(mRender);
renderAll();
liveStart();
/* The tab's icon: Blender's logo in the brand's blue. */
(() => {
  const sym = document.getElementById('b-blender');
  if (!sym) return;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${sym.getAttribute('viewBox')}"><g fill="#639bff">${sym.innerHTML}</g></svg>`,
    l = document.createElement('link');
  l.rel = 'icon';
  l.href = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
  document.head.appendChild(l);
})();
/* For tests and the console: the page's state and actions. */
window.MPPage = { S, items, A, reviewFile, reviewActions, fromActions, refresh, renderAll };
