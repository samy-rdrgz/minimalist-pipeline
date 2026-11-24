/* ---------- Scroll fades ----------
   A box that scrolls says what's hidden past its edges: a gradient to its ground at the bottom (and at the
   top), shown while something is out of sight there. Laid over the box, not a mask on it: a mask would cut
   the menus and popovers it holds. Under the list's stuck group header (the top) and over the writer's
   band in Watch large (the bottom), the gradient starts where the content is hidden. */
const FADE_SEL = '#outliner .area-body, #list, #pbody, #wide .w-main, #wide .w-side';
function fadeGround(el) {
  for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
    const c = getComputedStyle(e).backgroundColor;
    const m = c && c.match(/rgba?\(([^)]+)\)/);
    if (m && (m[1].split(',')[3] == null || parseFloat(m[1].split(',')[3]) > 0.05)) return c;
  }
  return getComputedStyle(document.body).backgroundColor;
}
function scrollFades() {
  if (isMob()) return;
  // The side tabs under the list's sequence header: drawn with the list.
  if (window.MPPanes && MPPanes.place) MPPanes.place();
  document.querySelectorAll(FADE_SEL).forEach(sc => {
    let F = sc._fd;
    const p = sc.parentElement;
    if (!F || F.t.parentElement !== p) {
      F = sc._fd = {
        t: Object.assign(document.createElement('mp-fade'), { className: 'sfade t' }),
        b: Object.assign(document.createElement('mp-fade'), { className: 'sfade b' })
      };
      F.t.setAttribute('aria-hidden', 'true');
      F.b.setAttribute('aria-hidden', 'true');
      // At the end of its box: a redraw of the box (morph()) drops them, keeping the rest in place.
      p.append(F.t, F.b);
    }
    const r = sc.getBoundingClientRect();
    const vis = r.width > 0 && r.height > 0;
    let top = r.top + sc.clientTop,
      bot = top + sc.clientHeight;
    // A stuck header holds the top; the writer's band, held at the bottom, the bottom.
    // Every group scrolled past is marked stuck: the one held at the top is the last of them.
    const hs = sc.querySelectorAll('.grp-h.stuck'),
      h = hs[hs.length - 1];
    if (h) top = Math.max(top, h.getBoundingClientRect().bottom);
    const band = sc.querySelector(':scope > .wsec');
    if (band) {
      const br = band.getBoundingClientRect();
      if (br.top < bot && br.bottom >= bot - 24) bot = br.top;
    }
    const up = vis && sc.scrollTop > 1,
      down = vis && sc.scrollTop + sc.clientHeight < sc.scrollHeight - 1,
      g = fadeGround(sc);
    [
      [F.t, up, top],
      [F.b, down, bot]
    ].forEach(([f, on, y], i) => {
      f.classList.toggle('on', on);
      if (!vis) return;
      const op = f.offsetParent || document.body,
        o = op.getBoundingClientRect();
      const hh = f.offsetHeight;
      f.style.left = r.left + sc.clientLeft - o.left - op.clientLeft + op.scrollLeft + 'px';
      f.style.width = sc.clientWidth + 'px';
      f.style.top = (i ? y - hh : y) - o.top - op.clientTop + op.scrollTop + 'px';
      f.style.setProperty('--fg', g);
    });
  });
}
{
  let raf = 0;
  const later = () => {
    if (!raf)
      raf = requestAnimationFrame(() => {
        raf = 0;
        scrollFades();
      });
  };
  document.addEventListener('scroll', later, { capture: true, passive: true });
  window.addEventListener('resize', later);
  // A section opened, a tab changed, a list redrawn: its height changed.
  // Its own gradients' changes left out (each draw would call the next).
  new MutationObserver(rs => {
    if (rs.some(m => !(m.target.classList && m.target.classList.contains('sfade')))) later();
  }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'hidden', 'open'] });
  window.MPFades = later;
  later();
}
