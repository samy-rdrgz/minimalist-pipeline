/* ---------- Resizable side panels ----------
   1200 px and over: the outliner and the detail; 861 to 1200 (a tablet held upright): the detail. Widths kept
   per browser (pz-v1). Either side can take the whole width: the list folded (the detail alone, MPPanes.main())
   or the detail folded (the list alone, MPPanes.props()). Nothing on a phone, nor under 861 px. */
(function () {
  var clamp = function (v, a, b) {
    return Math.max(a, Math.min(b, v));
  };
  var screen = document.querySelector('.screen'),
    outl = document.getElementById('outliner'),
    props = document.getElementById('props');
  if (!screen || !outl || !props) return;

  var R = {
    out: { min: 180, max: 420, def: 230, el: outl, side: 'l' },
    props: { min: 320, max: 680, def: 420, el: props, side: 'r' }
  };
  var pz;
  try {
    pz = JSON.parse(localStorage.getItem('pz-v1'));
  } catch (e) {}
  pz = Object.assign(
    { out: { w: 230, open: true }, props: { w: 420, open: true }, main: { open: true } },
    pz || {}
  );
  var wide = window.matchMedia('(min-width:1201px)'),
    mid = window.matchMedia('(min-width:861px)'),
    port = window.matchMedia('(orientation:portrait)');
  // The list folds only on a screen held upright (a tablet): side by side, the detail has room enough.
  function mOpen() {
    return pz.main.open || !port.matches;
  }
  var paneCss = document.createElement('style');
  paneCss.id = 'panes-live';
  document.head.appendChild(paneCss);
  var chev = { l: 'M4 2l4 4-4 4', r: 'M8 2 4 6l4 4' };
  var H = {},
    TAB = {};
  ['out', 'props'].forEach(function (k) {
    var h = document.createElement('div');
    h.className = 'pz-h';
    h.setAttribute('role', 'separator');
    h.setAttribute('aria-orientation', 'vertical');
    h.setAttribute('aria-label', k === 'out' ? T('Resize the outliner') : T('Resize the detail panel'));
    h.tabIndex = 0;
    h.title = T('Drag to resize · double-click: default width');
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'pz-tab ' + R[k].side;
    b.setAttribute(
      'aria-label',
      k === 'out' ? T('Show the outliner again') : T('Show the detail panel again')
    );
    b.innerHTML =
      '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="' +
      chev[R[k].side] +
      '" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    b.addEventListener('click', function () {
      pz[k].open = true;
      if (pz[k].w < R[k].min) pz[k].w = R[k].def;
      apply();
    });
    document.body.appendChild(h);
    document.body.appendChild(b);
    H[k] = h;
    TAB[k] = b;
    h.addEventListener('dblclick', function () {
      pz[k] = { w: R[k].def, open: true };
      apply();
    });
    h.addEventListener('keydown', function (e) {
      var d = e.key === 'ArrowLeft' ? -16 : e.key === 'ArrowRight' ? 16 : 0;
      if (!d) return;
      e.preventDefault();
      if (k === 'props') d = -d;
      pz[k].w = clamp(pz[k].w + d, R[k].min, R[k].max);
      apply();
    });
    h.addEventListener('pointerdown', function (e) {
      e.preventDefault();
      h.setPointerCapture(e.pointerId);
      h.classList.add('drag');
      document.body.classList.add('pz-dragging');
      var x0 = e.clientX,
        w0 = pz[k].w,
        sc = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--scale')) || 1;
      function mv(ev) {
        var dx = (ev.clientX - x0) / sc;
        if (k === 'props') dx = -dx;
        var w = w0 + dx;
        h.classList.toggle('warn', w < R[k].min - 40);
        pz[k].w = clamp(w, R[k].min, R[k].max);
        pz[k].pending = w < R[k].min - 40;
        apply(true);
      }
      function up() {
        h.removeEventListener('pointermove', mv);
        h.removeEventListener('pointerup', up);
        h.removeEventListener('pointercancel', up);
        h.classList.remove('drag', 'warn');
        document.body.classList.remove('pz-dragging');
        if (pz[k].pending) {
          pz[k].open = false;
          pz[k].w = w0;
        }
        delete pz[k].pending;
        apply();
      }
      h.addEventListener('pointermove', mv);
      h.addEventListener('pointerup', up);
      h.addEventListener('pointercancel', up);
    });
  });
  var resetBtn = document.getElementById('pz-reset');
  if (resetBtn)
    resetBtn.addEventListener('click', function () {
      pz = { out: { w: R.out.def, open: true }, props: { w: R.props.def, open: true } };
      apply();
    });

  function apply(live) {
    var o = pz.out,
      p = pz.props,
      m = pz.main;
    if (!m.open) p.open = true;
    // The grid at a width: the outliner (1200 px and over), the list, the detail -- the whole width to the one left.
    function grid(withOut, mo) {
      var cols = [],
        areas = [],
        m = { open: mo };
      if (withOut && o.open) {
        cols.push('calc(' + o.w + 'px*var(--scale))');
        areas.push('out');
      }
      if (m.open) {
        cols.push('minmax(0,1fr)');
        areas.push('main');
      }
      if (p.open) {
        cols.push(m.open ? 'calc(' + p.w + 'px*var(--scale))' : 'minmax(0,1fr)');
        areas.push('props');
      }
      return (
        '.screen{grid-template-columns:' +
        cols.join(' ') +
        '!important;grid-template-areas:"' +
        areas.join(' ') +
        '"!important}' +
        (withOut && !o.open ? '#outliner{display:none!important}' : '') +
        (p.open ? '' : '#props{display:none!important}') +
        (m.open ? '' : '#main{display:none!important}')
      );
    }
    paneCss.textContent =
      '@media (min-width:1201px) and (orientation:landscape){' +
      grid(true, true) +
      '}@media (min-width:1201px) and (orientation:portrait){' +
      grid(true, pz.main.open) +
      '}' +
      '@media (min-width:861px) and (max-width:1200px) and (orientation:landscape){' +
      grid(false, true) +
      '}@media (min-width:861px) and (max-width:1200px) and (orientation:portrait){' +
      grid(false, pz.main.open) +
      '}';
    if (!live)
      LS.set(
        'pz-v1',
        JSON.stringify({
          out: { w: o.w, open: o.open },
          props: { w: p.w, open: p.open },
          main: { open: m.open }
        })
      );
    place();
    sync();
  }
  // The buttons that fold a side: the list's (in its header), the detail's (in its header, drawn with it).
  function sync() {
    var b = document.getElementById('pz-side');
    if (b) {
      var open = pz.props.open;
      b.setAttribute('aria-pressed', String(!open));
      b.title = b.ariaLabel = open ? T('Hide the detail: the list on the whole width') : T('Show the detail');
      b.innerHTML = '<svg class="i"><use href="#b-' + (open ? 'tria_right' : 'tria_left') + '"/></svg>';
    }
    document.querySelectorAll('[data-pmax]').forEach(function (x) {
      x.setAttribute('aria-pressed', String(!pz.main.open));
      x.title = x.ariaLabel = pz.main.open ? T('The detail on the whole width') : T('Show the list again');
      x.innerHTML =
        '<svg class="i"><use href="#b-' +
        (pz.main.open ? 'fullscreen_enter' : 'fullscreen_exit') +
        '"/></svg>';
    });
  }
  window.MPPanes = {
    main: function () {
      pz.main.open = !pz.main.open;
      apply();
    },
    props: function () {
      pz.props.open = !pz.props.open;
      if (!pz.props.open) pz.main.open = true;
      else if (pz.props.w < R.props.min) pz.props.w = R.props.def;
      apply();
    },
    sync: sync
  };
  function place() {
    var sr = screen.getBoundingClientRect(),
      gap = parseFloat(getComputedStyle(screen).columnGap) || 0;
    ['out', 'props'].forEach(function (k) {
      // The outliner's handle from 1200 px, the detail's from 861; none while the list is folded.
      var on = (k === 'out' ? wide.matches : mid.matches) && !isMob() && mOpen();
      var h = H[k],
        b = TAB[k],
        open = pz[k].open,
        el = R[k].el;
      h.style.display = on && open ? 'block' : 'none';
      b.style.display = on && !open ? 'flex' : 'none';
      if (!on) return;
      if (open) {
        var r = el.getBoundingClientRect();
        h.style.top = r.top + 'px';
        h.style.height = r.height + 'px';
        h.style.left = (k === 'out' ? r.right + gap / 2 - 5 : r.left - gap / 2 - 5) + 'px';
      } else {
        b.style.top = sr.top + sr.height * 0.28 + 'px';
        if (k === 'out') {
          b.style.left = sr.left + 'px';
          b.style.right = '';
        } else {
          b.style.right = window.innerWidth - sr.right + 'px';
          b.style.left = '';
        }
      }
    });
  }
  window.addEventListener('resize', place);
  if (wide.addEventListener) {
    wide.addEventListener('change', place);
    mid.addEventListener('change', place);
    port.addEventListener('change', place);
  }
  if (window.ResizeObserver) new ResizeObserver(place).observe(screen);
  apply();
})();
