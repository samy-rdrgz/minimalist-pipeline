/* ---------- Detail › Versions and Renders: a file's history ----------
   lib/monitoring/history.py's: a snapshot carries it (it.hist), the live page asks Blender
   for it when the tab opens (POST /history), kept for the page's life.
   Versions: a chain, newest on top -- each version its node (made when, saved last by
   whom, the departments its sessions worked; a stable's done departments, validations,
   conflict). A version made from another than the one before it branches off: an arc on
   the rail's left, from where it came. Renders: every render, latest first. */
const HIST = {}; // name: history, or 'wait' while asked
function histOf(it) {
  if (it.hist) return it.hist;
  if (!LIVE) return null;
  const h = HIST[it.name];
  if (h && h !== 'wait') return h;
  if (!h) {
    HIST[it.name] = 'wait';
    livePost('history', { name: it.name })
      .then(r => {
        HIST[it.name] = r.ok ? r : { versions: [], renders: [], error: r.error };
        if (cur() && cur().name === it.name && (S.tab === 'versions' || S.tab === 'renders')) renderProps();
      })
      .catch(() => delete HIST[it.name]);
  }
  return 'wait';
}
const vShort = (it, f) => {
  const m = String(f || '').match(/_(v\d+.*)$/);
  return m ? m[1] : f;
};
const dShort = iso =>
  iso ? new Date(iso).toLocaleDateString(DTL(), { day: 'numeric', month: 'short', year: 'numeric' }) : '';
function versionsHTML(it) {
  const h = histOf(it);
  if (h === 'wait') return `<p class="faint">${T('Reading…')}</p>`;
  if (!h || !h.versions.length) return `<p class="faint">${T('No version known.')}</p>`;
  const vs = h.versions,
    idx = {};
  vs.forEach((v, i) => (idx[v.file] = i));
  const nodes = vs
    .map((v, i) => {
      const parent = v.from && idx[v.from] != null ? idx[v.from] : null,
        branch = parent != null && parent !== i - 1;
      const worked = [...new Set(v.sessions.flatMap(s => s.departments))],
        people = [...new Set(v.sessions.map(s => s.by).filter(Boolean))];
      const dep = d => esc(LBL[d] || d);
      return `<div class="vn ${v.stable ? 'st' : ''} ${v.conflict ? 'cf' : ''}" data-vi="${i}" ${parent != null ? `data-vp="${parent}"` : ''} ${branch ? 'data-branch' : ''}>
        <span class="vd" aria-hidden="true"></span>
        <div class="vb"><div class="vh"><b class="mono">${esc(vShort(it, v.file))}</b>${branch ? `<span class="tag warn" title="${T('Made from {v}, not from the version before it', { v: esc(vShort(it, v.from)) })}">${T('from {v}', { v: esc(vShort(it, v.from)) })}</span>` : ''}<span class="vat faint">${dShort(v.at)}</span></div>
          ${v.note ? `<div class="vm vnote">${esc(v.note)}</div>` : ''}
          ${v.saved_by && v.saved_at && v.saved_at !== v.at ? `<div class="vm faint">${T('saved last by {who}, {date}', { who: esc(v.saved_by), date: dShort(v.saved_at) })}</div>` : ''}
          ${worked.length ? `<div class="vm"><i class="vk wip"></i>${T('Worked: {deps}', { deps: worked.map(dep).join(', ') })}${people.length ? ` <span class="faint">· ${people.map(esc).join(', ')}</span>` : ''}</div>` : ''}
          ${v.stable && v.done.length ? `<div class="vm"><i class="vk done"></i>${T('Done: {deps}', { deps: v.done.map(dep).join(', ') })}</div>` : ''}
          ${
            v.stable && Object.keys(v.approvals || {}).length
              ? `<div class="vm"><i class="vk val"></i>${T('Validated: {list}', {
                  list: Object.entries(v.approvals)
                    .map(([d, rs]) => dep(d) + ' (' + rs.map(esc).join(', ') + ')')
                    .join(', ')
                })}</div>`
              : ''
          }
          ${v.conflict ? `<div class="vm bad">${ic('b-error')}${T('Conflict: {why}', { why: esc(typeof v.conflict === 'string' ? v.conflict : T('two stables made from the same version')) })}</div>` : ''}
        </div></div>`;
    })
    .reverse()
    .join('');
  return `<div class="sec"><div class="sec-h">${T('Versions')}<span class="faint">${vs.length}</span></div>
    <p class="faint" style="margin:0;font-size:var(--fs-s)">${T('Newest on top. A version made from another than the one before it branches off: a conflict to look at.')}</p>
    <div class="vchain" id="vchain"><svg class="vwires" aria-hidden="true"></svg>${nodes}</div></div>`;
}
/* The rail: a line through the nodes, an arc from where a branched one came. */
function drawChain() {
  const box = $('#vchain');
  if (!box) return;
  const R = box.getBoundingClientRect(),
    dot = i => box.querySelector(`[data-vi="${i}"] .vd`);
  const at = el => {
    const r = el.getBoundingClientRect();
    return [r.left + r.width / 2 - R.left, r.top + r.height / 2 - R.top];
  };
  let p = '';
  box.querySelectorAll('[data-vp]').forEach(n => {
    const a = dot(n.dataset.vp),
      b = n.querySelector('.vd');
    if (!a || !b) return;
    const [x1, y1] = at(a),
      [x2, y2] = at(b);
    if (n.hasAttribute('data-branch')) {
      const bend = 14 + Math.min(18, Math.abs(y1 - y2) / 12);
      p += `<path class="vw br" d="M${x1} ${y1} C${x1 - bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}"/>`; // on the rail's left, clear of the nodes
    } else p += `<path class="vw" d="M${x1} ${y1} L${x2} ${y2}"/>`;
  });
  const svg = box.querySelector('.vwires');
  svg.setAttribute('width', R.width);
  svg.setAttribute('height', R.height);
  svg.innerHTML = p;
}
/* Renders: grouped by the version rendered, on the Versions' rail -- a node a version
   (newest render on top), its renders inside, latest first. An old entry without its
   source: the version read from its folder's name (v003-stable_002: v003-stable). */
function rendersHTML(it) {
  const h = histOf(it);
  if (h === 'wait') return `<p class="faint">${T('Reading…')}</p>`;
  if (!h || !h.renders.length) return `<p class="faint">${T('No render.')}</p>`;
  const ok = { finished: 'finished', failed: 'failed', cancelled: 'cancelled' };
  const min = s => (s ? T('{n} min', { n: Math.max(1, Math.round(s / 60)) }) : '');
  const groups = [],
    by = {};
  h.renders.forEach(r => {
    const v = (r.source && vShort(it, r.source)) || String(r.folder || '').replace(/_\d+$/, '') || '?';
    if (!by[v]) groups.push((by[v] = { v, rs: [] }));
    by[v].rs.push(r);
  });
  // Its time on one machine: a frame's seconds there, every frame; without them, the time it took.
  const nFr = r => (r.frames ? r.frames[1] - r.frames[0] + 1 : 0),
    hm = s => (s >= 3600 ? T('{h} h {m}', { h: Math.floor(s / 3600), m: String(Math.round((s % 3600) / 60)).padStart(2, '0') }) : min(s)),
    took = r =>
      r.per_frame && nFr(r)
        ? T('{t} on one machine', { t: hm(r.per_frame * nFr(r)) })
        : r.seconds
          ? T('took {t}', { t: hm(r.seconds) })
          : '';
  const line =
    r => `<div class="rh">${jst(ok[r.status] || 'finished')}<div class="rl"><div class="vh">${r.department ? `<span class="tag">${esc(LBL[r.department] || r.department)}</span>` : ''}${r.status && r.status !== 'finished' ? `<span class="tag ${r.status === 'failed' ? 'fail' : ''}">${esc(r.status)}</span>` : ''}${jobTags(r)}<span class="faint">${esc(dShort(r.at))}</span></div>
        <div class="vm faint">${[r.by, r.preset, r.frames ? 'f' + r.frames.join('–') : '', r.shot, took(r)].filter(Boolean).map(esc).join(' · ')}</div></div></div>`;
  const nodes = groups
    .map(
      (
        g,
        i
      ) => `<div class="vn ${/stable/.test(g.v) ? 'st' : ''}" data-vi="${i}" ${i ? `data-vp="${i - 1}"` : ''}>
        <span class="vd" aria-hidden="true"></span>
        <div class="vb"><div class="vh"><b class="mono">${esc(g.v)}</b><span class="faint">${T('{n} render|{n} renders', { n: g.rs.length })}</span></div>${g.rs.map(line).join('')}</div></div>`
    )
    .join('');
  const fmb = h.renders.some(r => r.frame_machines && r.frame_machines.frames)
    ? `<span class="sp"></span><button class="btn sm" data-fmopen title="${T('A render, a frame: the machine that rendered it')}">${ic('b-viewzoom')}${T('Which machine…')}</button>`
    : '';
  return `<div class="sec"><div class="sec-h">${T('Renders')}<span class="faint">${h.renders.length}</span>${fmb}</div>
    <p class="faint" style="margin:0;font-size:var(--fs-s)">${T('By version rendered, the latest on top.')}</p>
    <div class="vchain" id="vchain"><svg class="vwires" aria-hidden="true"></svg>${nodes}</div></div>`;
}
/* Which machine rendered a frame (a render's frame_machines): a render picked, a frame (Blender's
   number) written -- its machine; under it, each machine's frames counted. */
function fmDlg() {
  const it = cur(),
    h = it && histOf(it);
  if (!h || h === 'wait') return;
  const rs = h.renders.filter(r => r.frame_machines && r.frame_machines.frames);
  if (!rs.length) return;
  const o = (S.fmq = S.fmq && S.fmq.name === it.name ? S.fmq : { name: it.name, i: 0, f: '' });
  const r = rs[Math.min(o.i, rs.length - 1)],
    fm = r.frame_machines,
    start = +fm.start || 1,
    end = start + fm.frames.length - 1,
    name = l => ((fm.machines || {})[l] || [])[1] || ((fm.machines || {})[l] || [])[0] || l,
    L = Object.keys(fm.machines || {}).sort(),
    count = l => fm.frames.split(l).length - 1;
  const lbl = x => [x.folder, x.department && (LBL[x.department] || x.department), x.shot, dShort(x.at)].filter(Boolean).join(' · ');
  const dl = $('#dlg');
  dl.hidden = false;
  dl.innerHTML = `<div class="dlg-in" role="dialog" aria-modal="true" aria-labelledby="fm-t"><h3 id="fm-t">${T('Which machine rendered a frame')}</h3>
    <div class="prop"><span class="k">${T('Which render')}</span><span class="v"><label class="field" style="flex:1"><select id="fm-r" aria-label="${T('Which render')}">${rs.map((x, k) => `<option value="${k}" ${k === o.i ? 'selected' : ''}>${esc(lbl(x))}</option>`).join('')}</select></label></span></div>
    <div class="prop"><span class="k">${T('Frame')}</span><span class="v"><label class="field" style="width:calc(120px*var(--scale))"><span class="faint">f</span><input id="fm-f" inputmode="numeric" value="${esc(o.f)}" placeholder="${start}" aria-label="${T('Frame')}"></label><span class="faint">${start} – ${end}</span></span></div>
    <p class="fm-a" id="fm-a"></p>
    <ul class="fm-lg">${L.map(l => `<li><span>${esc(name(l))}</span><span class="faint">${T('{n} frame|{n} frames', { n: count(l) })}</span></li>`).join('')}</ul>
    <div class="acts"><span style="flex:1"></span><button class="btn" data-dclose>${T('Close')}</button></div></div>`;
  const inp = $('#fm-f'),
    say = () => {
      o.f = inp.value.trim();
      const n = parseInt(o.f.replace(/^f/, ''), 10),
        a = $('#fm-a');
      if (!o.f) a.textContent = '';
      else if (!(n >= start && n <= end)) a.innerHTML = `<span class="faint">${T('Not a frame of this render ({a} – {b}).', { a: start, b: end })}</span>`;
      else a.innerHTML = `f${n} · <b>${esc(name(fm.frames[n - start]))}</b>`;
    };
  inp.oninput = say;
  $('#fm-r').onchange = e => {
    o.i = +e.target.value;
    fmDlg();
  };
  say();
  setTimeout(() => inp.focus(), 0);
}
