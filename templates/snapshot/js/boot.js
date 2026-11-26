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
/* The page's backdrop (--wbg): the selected file's picture, blurred under the screen's grey
   (css: body::before / ::after, #wide's own). */
/* Its colours kept, its light evened out: the picture made small (48 x 27), each pixel's hue
   and saturation kept, its lightness set to one value -- dark under a dark theme, light under a
   light one -- so what lies over it stays readable whatever the picture. Made once a picture
   and theme; a picture the canvas can't read (another origin): as it is. */
const BGN = {};
function evenBackdrop(src) {
  const ui = document.documentElement.dataset.ui || 'dark',
    k = ui + '|' + src;
  if (BGN[k] !== undefined) return BGN[k] === 'wait' ? '' : BGN[k];
  BGN[k] = 'wait';
  const im = new Image();
  im.onload = () => {
    try {
      const w = 48,
        h = 27,
        c = document.createElement('canvas');
      c.width = w;
      c.height = h;
      const x = c.getContext('2d');
      x.drawImage(im, 0, 0, w, h);
      const d = x.getImageData(0, 0, w, h),
        p = d.data,
        L = ui === 'light' ? 0.84 : 0.4,
        SMAX = 0.45; // pastel: its saturation capped
      for (let i = 0; i < p.length; i += 4) {
        const r = p[i] / 255,
          g = p[i + 1] / 255,
          b = p[i + 2] / 255,
          mx = Math.max(r, g, b),
          mn = Math.min(r, g, b),
          l = (mx + mn) / 2,
          dl = mx - mn;
        let hh = 0,
          s = 0;
        if (dl) {
          s = dl / (1 - Math.abs(2 * l - 1));
          hh = mx === r ? ((g - b) / dl) % 6 : mx === g ? (b - r) / dl + 2 : (r - g) / dl + 4;
        }
        // hsl -> rgb at the one lightness L
        const C = (1 - Math.abs(2 * L - 1)) * Math.min(SMAX, s),
          X = C * (1 - Math.abs((((hh % 6) + 6) % 6) % 2 - 1)),
          m = L - C / 2,
          q = [[C, X, 0], [X, C, 0], [0, C, X], [0, X, C], [X, 0, C], [C, 0, X]][Math.floor(((hh % 6) + 6) % 6)];
        p[i] = (q[0] + m) * 255;
        p[i + 1] = (q[1] + m) * 255;
        p[i + 2] = (q[2] + m) * 255;
      }
      x.putImageData(d, 0, 0);
      BGN[k] = c.toDataURL();
    } catch (_) {
      BGN[k] = src;
    }
    syncBackdrop();
  };
  im.onerror = () => (BGN[k] = '');
  im.src = src;
  return '';
}
/* On unless turned off in the Menu (this browser). */
const bdropOn = () => LS.get('mp-snapshot.backdrop') !== '0';
function syncBackdrop() {
  document.querySelectorAll('[data-bdrop]').forEach(b => b.setAttribute('aria-checked', String(bdropOn())));
  // The file selected; the Farm, the selected job's file.
  const job = S.ws === 'farm' && S.farmSel && !String(S.farmSel).startsWith('w:') ? F.jobs.find(j => j.id === S.farmSel) : null,
    it = S.ws === 'farm' ? job && jobItem(job) : cur(),
    raw = it && bdropOn() ? thumbOf(it) : '',
    bg = raw ? evenBackdrop(raw) : '';
  const v = bg ? `url("${bg}")` : '';
  if (document.documentElement.style.getPropertyValue('--wbg') !== v) {
    if (v) document.documentElement.style.setProperty('--wbg', v);
    else document.documentElement.style.removeProperty('--wbg');
  }
}
function syncPlace() {
  syncBackdrop();
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
