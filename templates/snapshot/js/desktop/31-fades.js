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
/* A scrollbar laid over the content (Firefox, macOS: it takes no width) is drawn over the box's sticky
   header too. Over its lane, as tall as the header held at the top: the header's ground again (its tint,
   its blur, its line), over the list's -- the header over the bar, as the fades are. */
const BAR_LANE = 16;
function headOverBar(sc, h, r) {
  let c = sc._cap;
  const p = sc.parentElement;
  const over = sc.offsetWidth - sc.clientWidth - 2 * sc.clientLeft <= 0 && sc.scrollHeight > sc.clientHeight + 1;
  if (!h || !over) {
    if (c) c.hidden = true;
    return;
  }
  if (!c || c.parentElement !== p) {
    c = sc._cap = document.createElement('mp-fade');
    c.className = 'scap';
    c.setAttribute('aria-hidden', 'true');
    c.innerHTML = '<span></span>';
    p.append(c);
  }
  c.hidden = false;
  const hr = h.getBoundingClientRect(),
    hs = getComputedStyle(h),
    gs = getComputedStyle(h.parentElement), // its group: the card the glass header lets show
    rad = k => (parseFloat(hs[k]) ? hs[k] : gs[k]),
    op = c.offsetParent || document.body,
    o = op.getBoundingClientRect(),
    top = Math.max(r.top + sc.clientTop, hr.top),
    x = r.left + sc.clientLeft + sc.clientWidth - BAR_LANE;
  Object.assign(c.style, {
    left: x - o.left - op.clientLeft + 'px',
    top: top - o.top - op.clientTop + 'px',
    width: BAR_LANE + 'px',
    height: Math.max(0, hr.bottom - top) + 'px',
    background: fadeGround(sc)
  });
  // The header itself, placed where it is: only its part over the lane shows.
  Object.assign(c.firstChild.style, {
    left: hr.left - x + 'px',
    top: hr.top - top + 'px',
    width: hr.width + 'px',
    height: hr.height + 'px',
    backgroundColor: gs.backgroundColor,
    backgroundImage: `linear-gradient(${hs.backgroundColor}, ${hs.backgroundColor})`,
    borderBottom: hs.borderBottomWidth + ' ' + hs.borderBottomStyle + ' ' + hs.borderBottomColor,
    borderTopRightRadius: rad('borderTopRightRadius'),
    borderBottomRightRadius: hs.borderBottomRightRadius
  });
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
    // Every group scrolled past is marked stuck: the one held at the top is the last of them; none
    // scrolled past, the first group's header, at the top.
    const hs = sc.querySelectorAll('.grp-h.stuck'),
      h = hs[hs.length - 1] || sc.querySelector('.grp-h');
    const hr = h && h.getBoundingClientRect(),
      held = hr && hr.top <= top + 12 && hr.bottom > top + 1; // the first one, under the list's padding, too
    if (held) top = Math.max(top, hr.bottom);
    headOverBar(sc, held && h, r);
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
    if (rs.some(m => !(m.target.closest && m.target.closest('mp-fade')))) later();
  }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'hidden', 'open'] });
  window.MPFades = later;
  later();
}
