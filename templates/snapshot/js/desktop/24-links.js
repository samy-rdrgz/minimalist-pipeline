/* ---------- Links: canvas ---------- */
/* A sequence of several shots, folded (the default): one group node, Blender's group node -- its inputs every asset its
   shots link, each once ("×n": how many of its shots), so one wire where there were n. Clicked, it unfolds into its shots;
   its caption folds it back. A shot looked at (the one clicked, or linked to the one clicked) unfolds its sequence. */
const GRP = 'grp:',
  gKey = g => GRP + g;
const gIsGrp = n => String(n).startsWith(GRP);
let GMAP = {};
function renderGraph() {
  const L = $('#list');
  const linked = new Set();
  items.forEach(i => {
    if (i.links.length || i.linkedBy.length) linked.add(i.name);
  });
  const show = i => (S.gAll || linked.has(i.name)) && (!S.q || i.name.toLowerCase().includes(S.q));
  const assets = items.filter(i => i.kind === 'asset' && show(i)),
    shots = items.filter(i => i.kind === 'shot' && show(i));
  const focus = S.gFocus,
    near = new Set();
  if (focus) {
    const f = items.find(i => i.name === focus);
    if (f) {
      near.add(focus);
      f.links.forEach(l => near.add(l.name));
      f.linkedBy.forEach(n => near.add(n));
    }
  }
  if (!S.gSeq) S.gSeq = new Set();
  const groups = [...new Set(shots.map(i => i.group))];
  // Open: unfolded by hand, all unfolded, or holding a shot looked at.
  const open = g =>
    S.gSeqAll ||
    S.gSeq.has(g) ||
    shots.filter(i => i.group === g).length < 2 ||
    shots.some(
      i =>
        i.group === g &&
        focus &&
        near.has(i.name) &&
        (i.name === focus || items.find(x => x.name === focus)?.kind === 'shot')
    );
  GMAP = {};
  const shown = [];
  groups.forEach(g => {
    const its = shots.filter(i => i.group === g);
    if (open(g)) {
      shown.push(...its);
      return;
    }
    const by = {};
    its.forEach(i =>
      i.links.forEach(l => {
        const b = (by[l.name] = by[l.name] || { name: l.name, n: 0, bad: false });
        b.n++;
        if (l.newer) b.bad = true;
      })
    );
    const o = {
      name: gKey(g),
      group: g,
      kind: 'shot',
      grp: true,
      shots: its,
      links: Object.values(by).sort((a, b) => b.n - a.n || a.name.localeCompare(b.name)),
      linkedBy: []
    };
    GMAP[o.name] = o;
    shown.push(o);
  });
  // Where a shot is drawn: itself, or its folded sequence.
  const at = {};
  shown.forEach(o => {
    if (o.grp) o.shots.forEach(i => (at[i.name] = o.name));
    else at[o.name] = o.name;
  });
  GMAP.__at = at;
  // An asset clicked: the shots show only its socket (the others counted), not every file they link.
  const fA = focus && (items.find(x => x.name === focus) || {}).kind === 'asset' ? focus : null;
  const only = (ls, i) => {
    if (!fA || i.kind === 'asset') return [ls, 0];
    const k = ls.filter(l => l.name === fA);
    return [k, ls.length - k.length];
  };
  const more = n => (n ? `<div class="sock faint more">${T('+ {n} other|+ {n} others', { n })}</div>` : '');
  const node = i => {
    const dim = focus && !near.has(i.name) && !(i.grp && i.shots.some(x => near.has(x.name))),
      fold = !S.gOpen && !(focus && (near.has(i.name) || (i.grp && i.shots.some(x => near.has(x.name)))));
    if (i.grp) {
      const w = worstOf(i.shots);
      return `<div class="node gnode shot grp ${dim ? 'dim' : ''} ${fold ? 'fold' : ''}" data-gn="${esc(i.name)}" data-gseq="${esc(i.group)}" data-k="shot" title="${esc(T('{seq}: {n} shots, folded -- click to unfold', { seq: i.group, n: i.shots.length }))}">
        <div class="nh">${ic('b-outliner')}<span>${esc(i.group)}</span><span class="gcount">${T('{n} shots', { n: i.shots.length })}</span><span class="dt" style="background:${DOT[w]}"></span></div><div class="nb">
        ${(([ls, m]) => ls.map(l => `<div class="sock in ${l.bad ? 'bad' : ''}" data-gi="${esc(l.name)}"><i></i>${esc(l.name)}${l.n > 1 ? ` <b class="mult">×${l.n}</b>` : ''}</div>`).join('') + more(m))(only(i.links, i))}
        ${!i.links.length ? '<div class="sock faint">' + T('no link') + '</div>' : ''}</div></div>`;
    }
    return `<div class="node gnode ${i.kind === 'shot' ? 'shot' : ''} ${focus === i.name ? 'cur' : ''} ${dim ? 'dim' : ''} ${fold ? 'fold' : ''}" data-gn="${i.name}" data-k="${i.kind}" title="${i.name}">
      <div class="nh">${ic(i.kind === 'shot' ? 'b-camera_data' : 'b-asset_manager')}<span>${i.name}</span><span class="dt" style="background:${DOT[worst(i)]}"></span></div><div class="nb">
      ${(([ls, m]) => ls.map(l => `<div class="sock in ${l.newer ? 'bad' : ''}" data-gi="${l.name}"><i></i>${l.name} · ${verOf(l.file)}${l.newer ? ' (' + T('older') + ')' : ''}</div>`).join('') + more(m))(only(i.links, i))}
      ${i.linkedBy.length ? `<div class="sock out" data-go="${i.name}"><i></i>${T('linked by {n}', { n: i.linkedBy.length })}</div>` : ''}
      ${!i.links.length && !i.linkedBy.length ? '<div class="sock faint">' + T('no link') + '</div>' : ''}</div></div>`;
  };
  const nOld = items.reduce((a, i) => a + i.links.filter(l => l.newer).length, 0),
    nGrp = groups.filter(g => shots.filter(i => i.group === g).length > 1).length;
  L.innerHTML = `<div class="gcanvas" id="gcanvas"><div class="gview" id="gview"><svg class="wires" id="gwires"></svg>
      ${[...assets, ...shown].map(node).join('')}
    </div>
    <div class="gtools tl"><span class="dim">${T('{n} linked files of {total}', { n: linked.size, total: items.length })}</span>${nOld ? `<span class="tag rtk">${T('{n} link to an older stable|{n} links to an older stable', { n: nOld })}</span>` : ''}
      <span class="join"><button class="btn sm" data-gall="0" aria-pressed="${!S.gAll}">${T('Linked files')}</button><button class="btn sm" data-gall="1" aria-pressed="${!!S.gAll}">${T('All')}</button></span>
      <span class="join" title="${T('How the assets are ordered')}"><button class="btn sm" data-gsort="type" aria-pressed="${S.gSort !== 'links'}">${T('By type')}</button><button class="btn sm" data-gsort="links" aria-pressed="${S.gSort === 'links'}">${T('By links')}</button></span>
      <button class="btn sm" data-gwires aria-pressed="${!!S.gWires}" title="${T("Every wire, not only the hovered or clicked node's")}">${T('All wires')}</button>
      ${nGrp ? `<button class="btn sm" data-gseqall aria-pressed="${!S.gSeqAll}" title="${T('A sequence as one node: the assets its shots link, each once')}">${ic('b-outliner')}${T('Sequences grouped')}</button>` : ''}
      <button class="btn sm" data-gopen aria-pressed="${!!S.gOpen}" title="${T("Show every node's links, not only the clicked one's")}">${T('Unfold all')}</button>
      ${focus ? `<button class="btn sm" data-gclear>${ic('b-x')}${esc(focus)}</button>` : ''}</div>
    <div class="gtools br"><span class="join"><button class="btn sm icon" data-gz="-1" aria-label="${T('Zoom out')}" title="${T('Zoom out')}">−</button><button class="btn sm" data-gz="0" title="${T('See everything')}">${Math.round(S.g.z * 100)} %</button><button class="btn sm icon" data-gz="1" aria-label="${T('Zoom in')}" title="${T('Zoom in')}">+</button></span></div>
    <div class="ghint">${T('Drag the background: move · wheel: zoom · click: its links · double click: the file')}</div></div>`;
  layoutGraph();
  applyG();
  if (!S.g.init) {
    S.g.init = true;
    requestAnimationFrame(() => fitG());
  } else requestAnimationFrame(drawGraph);
}
/* A sequence's dot: its worst shot's. */
const RANK = ['omit', 'val', 'done', 'wip', 'todo', 'rtk'];
function worstOf(its) {
  return its.map(worst).sort((a, b) => RANK.indexOf(b) - RANK.indexOf(a))[0] || 'todo';
}
/* Columns: assets left, shots right by sequence; both sorted by barycentre (a few passes, crossings fewer), then each asset
   brought level with the middle of what links it -- the most shared ones end up in the middle, their wires short. */
function layoutGraph() {
  const v = $('#gview');
  if (!v) return;
  const nodes = [...v.querySelectorAll('.gnode')],
    by = n => v.querySelector(`[data-gn="${CSS.escape(n)}"]`);
  const shots = nodes.filter(n => n.dataset.k === 'shot').map(n => n.dataset.gn),
    assets = nodes.filter(n => n.dataset.k === 'asset').map(n => n.dataset.gn);
  const at = GMAP.__at || {},
    itm = n => GMAP[n] || items.find(i => i.name === n);
  const seqs = [...new Set(shots.map(n => itm(n).group))];
  // What links an asset, as drawn: its shots, or their folded sequences (each once).
  const users = n => [
    ...new Set(
      itm(n)
        .linkedBy.map(x => at[x])
        .filter(Boolean)
    )
  ];
  let sOrder = {},
    aOrder = {};
  shots.forEach((n, i) => (sOrder[n] = i));
  assets.forEach((n, i) => (aOrder[n] = i));
  const bary = (list, adj, ord) => {
    const r = {};
    list.forEach(n => {
      const a = adj(n).filter(x => x in ord);
      r[n] = a.length ? a.reduce((s, x) => s + ord[x], 0) / a.length : 1e6 + (ord[n] || 0);
    });
    return r;
  };
  const byType = S.gSort !== 'links',
    pre = n => n.split('_')[0];
  if (byType) {
    assets.sort((a, b) => pre(a).localeCompare(pre(b)) || a.localeCompare(b));
    shots.sort(
      (a, b) => seqs.indexOf(itm(a).group) - seqs.indexOf(itm(b).group) || String(a).localeCompare(String(b))
    );
  } else
    for (let k = 0; k < 6; k++) {
      const ba = bary(assets, users, sOrder);
      assets.sort((a, b) => ba[a] - ba[b]);
      assets.forEach((n, i) => (aOrder[n] = i));
      const bs = bary(shots, n => itm(n).links.map(l => l.name), aOrder);
      const sk = g => {
        const xs = shots
          .filter(n => itm(n).group === g)
          .map(n => bs[n])
          .filter(x => x < 1e6);
        return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 1e6;
      };
      seqs.sort((a, b) => sk(a) - sk(b));
      shots.sort((a, b) => seqs.indexOf(itm(a).group) - seqs.indexOf(itm(b).group) || bs[a] - bs[b]);
      shots.forEach((n, i) => (sOrder[n] = i));
    }
  const W = Math.max(...nodes.map(n => n.offsetWidth), 200),
    GX = 200,
    GY = S.gOpen ? 18 : 8,
    CAP = 34,
    x2 = W + GX;
  let y = CAP,
    center = {};
  v.querySelectorAll('.gcap').forEach(c => c.remove());
  const cap = (t, x, yy, g) => {
    const c = document.createElement(g ? 'button' : 'div');
    c.className = 'gcap' + (g ? ' gcap-b' : '');
    c.style.left = x + 'px';
    c.style.top = yy + 'px';
    if (g) {
      c.dataset.gseq = g;
      c.title = T('Fold {seq} into one node', { seq: g });
      c.innerHTML = ic('b-downarrow_hlt') + esc(t);
    } else c.textContent = t;
    v.appendChild(c);
  };
  let lastG = null;
  shots.forEach(n => {
    const o = itm(n),
      g = o.group;
    if (g !== lastG) {
      if (lastG) y += S.gOpen ? 16 : 28;
      const many = !o.grp && shots.filter(x => itm(x).group === g).length > 1 && !S.gSeqAll;
      if (!o.grp) cap(g, x2, y - 24, many ? g : null);
      else y -= 12;
      lastG = g;
    }
    const e = by(n);
    e.style.left = x2 + 'px';
    e.style.top = y + 'px';
    center[n] = y + e.offsetHeight / 2;
    y += e.offsetHeight + GY;
  });
  if (byType) {
    // By type: the assets in their prefix's block, one under the other, as the shots in their sequence's.
    let ya = CAP,
      lp = null;
    assets.forEach(n => {
      if (pre(n) !== lp) {
        if (lp) ya += S.gOpen ? 16 : 28;
        cap(pre(n), 0, ya - 24);
        lp = pre(n);
      }
      const e = by(n);
      e.style.left = '0px';
      e.style.top = ya + 'px';
      ya += e.offsetHeight + GY;
    });
    v.style.width = x2 + W + 20 + 'px';
    v.style.height = Math.max(y, ya) + 20 + 'px';
    return;
  }
  const tgt = {};
  assets.forEach(n => {
    const e = by(n),
      c = users(n)
        .filter(x => x in center)
        .map(x => center[x]);
    tgt[n] = (c.length ? c.reduce((a, b) => a + b, 0) / c.length : 1e9) - e.offsetHeight / 2;
  });
  // Each as near its target as the others leave room for: pushed down from the top, pushed up from the bottom, the mean
  // of both, then no overlap -- a crowd around a target spreads both ways instead of all below it.
  const h = n => by(n).offsetHeight,
    want = assets.map(n => tgt[n]),
    F = [],
    B = [],
    pos = {};
  assets.forEach((n, i) => {
    const w = want[i] >= 1e8 ? (i ? F[i - 1] + h(assets[i - 1]) + GY : CAP) : want[i];
    F[i] = Math.max(i ? F[i - 1] + h(assets[i - 1]) + GY : CAP, w);
  });
  for (let i = assets.length - 1; i >= 0; i--) {
    const w = want[i] >= 1e8 ? F[i] : want[i];
    B[i] = i === assets.length - 1 ? w : Math.min(w, B[i + 1] - h(assets[i]) - GY);
  }
  assets.forEach((n, i) => {
    let t = Math.max(CAP, (F[i] + B[i]) / 2);
    if (i) t = Math.max(t, pos[assets[i - 1]] + h(assets[i - 1]) + GY);
    pos[n] = t;
  });
  cap(T('Assets'), 0, CAP - 24);
  let ya = CAP;
  assets.forEach(n => {
    const e = by(n);
    e.style.left = '0px';
    e.style.top = pos[n] + 'px';
    ya = Math.max(ya, pos[n] + e.offsetHeight + GY);
  });
  v.style.width = x2 + W + 20 + 'px';
  v.style.height = Math.max(y, ya) + 20 + 'px';
}
function applyG() {
  const v = $('#gview'),
    c = $('#gcanvas');
  if (!v) return;
  v.style.transform = `translate(${S.g.x}px,${S.g.y}px) scale(${S.g.z})`;
  const s = 20 * S.g.z;
  c.style.backgroundSize = `${s}px ${s}px`;
  c.style.backgroundPosition = `${S.g.x}px ${S.g.y}px`;
  const z = document.querySelector('[data-gz="0"]');
  if (z) z.textContent = Math.round(S.g.z * 100) + ' %';
}
function fitG() {
  const v = $('#gview'),
    c = $('#gcanvas');
  if (!v || !c) return;
  const cw = c.clientWidth,
    ch = c.clientHeight,
    vw = v.offsetWidth,
    vh = v.offsetHeight;
  S.g.z = Math.max(0.35, Math.min(1, (cw - 40) / vw, (ch - 90) / vh));
  S.g.x = (cw - vw * S.g.z) / 2;
  S.g.y = Math.max(56, (ch - vh * S.g.z) / 2);
  applyG();
  drawGraph();
}
function zoomG(f, cx, cy) {
  const c = $('#gcanvas');
  if (!c) return;
  const r = c.getBoundingClientRect();
  cx = cx ?? r.width / 2;
  cy = cy ?? r.height / 2;
  const z = Math.max(0.3, Math.min(2.5, S.g.z * f));
  S.g.x = cx - ((cx - S.g.x) * z) / S.g.z;
  S.g.y = cy - ((cy - S.g.y) * z) / S.g.z;
  S.g.z = z;
  applyG();
}
function centerG(n) {
  const c = $('#gcanvas'),
    e = document.querySelector(`[data-gn="${CSS.escape(n)}"]`);
  if (!c || !e) return;
  const cr = c.getBoundingClientRect(),
    er = e.getBoundingClientRect();
  S.g.x += cr.left + cr.width / 2 - (er.left + er.width / 2);
  S.g.y += cr.top + cr.height / 2 - (er.top + er.height / 2);
  applyG();
}
function drawGraph() {
  const box = $('#gview');
  if (!box) return;
  const R = box.getBoundingClientRect(),
    z = S.g.z;
  let p = '';
  const focus = S.gFocus;
  // A folded node's sockets are hidden: its wires meet its title's edge (in: left, out: right).
  const pt = e => {
    const nd = e.closest('.node');
    if (nd.classList.contains('fold')) {
      const r = nd.querySelector('.nh').getBoundingClientRect(),
        out = !!e.closest('.out');
      return [((out ? r.right : r.left) - R.left) / z, (r.top + r.height / 2 - R.top) / z];
    }
    const r = e.getBoundingClientRect();
    return [(r.left + r.width / 2 - R.left) / z, (r.top + r.height / 2 - R.top) / z];
  };
  // At rest, no wire (All wires: every one): the hovered node's, else the clicked one's -- a shot's own, or its folded sequence's.
  const act = S.gHover || focus,
    actG = act && GMAP.__at ? GMAP.__at[act] : null,
    on = (a, b) => a === act || b === act || (actG && b === actG);
  box.querySelectorAll('[data-gi]').forEach(n => {
    const src = n.dataset.gi,
      o = box.querySelector(`[data-go="${src}"] i`);
    if (!o) return;
    const tgt = n.closest('[data-gn]').dataset.gn,
      hot = act ? on(src, tgt) : !!S.gWires;
    if (!S.gWires && !hot) return;
    const [x1, y1] = pt(o),
      [x2, y2] = pt(n.querySelector('i'));
    const no = o.closest('.node'),
      nn = n.closest('.node');
    const ym =
      ((Math.min(no.getBoundingClientRect().bottom, nn.getBoundingClientRect().bottom) +
        Math.max(no.getBoundingClientRect().top, nn.getBoundingClientRect().top)) /
        2 -
        R.top) /
      z;
    const c = n.classList.contains('bad') ? 'var(--st-rtk)' : 'var(--wire)',
      d = wirePath(x1, y1, x2, y2, ym);
    p += `<path d="${d}" fill="none" style="stroke:var(--wire-edge)" stroke-width="4.5" opacity="${hot ? 1 : 0.25}"/><path d="${d}" fill="none" style="stroke:${c}" stroke-width="2.4" opacity="${hot ? 1 : 0.18}"/>`;
  });
  const w = $('#gwires');
  w.setAttribute('width', box.offsetWidth);
  w.setAttribute('height', box.offsetHeight);
  w.innerHTML = p;
}
let gDrag = null;
document.addEventListener('pointerdown', e => {
  const c = e.target.closest('#gcanvas');
  if (!c || e.target.closest('.node,.gtools,button')) return;
  gDrag = { x: e.clientX, y: e.clientY, ox: S.g.x, oy: S.g.y, id: e.pointerId };
  c.setPointerCapture(e.pointerId);
  c.classList.add('grab');
});
document.addEventListener('pointermove', e => {
  if (!gDrag) return;
  S.g.x = gDrag.ox + e.clientX - gDrag.x;
  S.g.y = gDrag.oy + e.clientY - gDrag.y;
  applyG();
});
document.addEventListener('pointerup', () => {
  if (gDrag) {
    gDrag = null;
    $('#gcanvas')?.classList.remove('grab');
  }
});
document.addEventListener(
  'wheel',
  e => {
    const c = e.target.closest('#gcanvas');
    if (!c) return;
    e.preventDefault();
    const r = c.getBoundingClientRect();
    if (e.ctrlKey || (Math.abs(e.deltaY) > Math.abs(e.deltaX) && !e.shiftKey))
      zoomG(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
    else {
      S.g.x -= e.deltaX;
      S.g.y -= e.deltaY;
      applyG();
    }
  },
  { passive: false }
);

/* Hovered, a node shows its wires (none drawn at rest). */
document.addEventListener('pointerover', e => {
  const n = e.target.closest && e.target.closest('#gview .gnode');
  const k = n ? n.dataset.gn : null;
  if (k !== S.gHover) {
    S.gHover = k;
    drawGraph();
  }
});
