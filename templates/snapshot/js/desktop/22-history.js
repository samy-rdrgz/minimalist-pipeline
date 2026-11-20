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
        <div class="vb"><div class="vh"><b class="mono">${esc(vShort(it, v.file))}</b>${v.stable ? `<span class="tag">${T('stable')}</span>` : ''}${branch ? `<span class="tag warn" title="${T('Made from {v}, not from the version before it', { v: esc(vShort(it, v.from)) })}">${T('from {v}', { v: esc(vShort(it, v.from)) })}</span>` : ''}</div>
          <div class="vm faint">${[dShort(v.at), v.saved_by && v.saved_at && v.saved_at !== v.at ? T('saved last by {who}, {date}', { who: esc(v.saved_by), date: dShort(v.saved_at) }) : ''].filter(Boolean).join(' · ')}</div>
          ${worked.length ? `<div class="vm">${T('Worked: {deps}', { deps: worked.map(dep).join(', ') })}${people.length ? ` <span class="faint">· ${people.map(esc).join(', ')}</span>` : ''}</div>` : ''}
          ${v.stable && v.done.length ? `<div class="vm">${T('Done: {deps}', { deps: v.done.map(dep).join(', ') })}</div>` : ''}
          ${
            v.stable && Object.keys(v.approvals || {}).length
              ? `<div class="vm">${T('Validated: {list}', {
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
function rendersHTML(it) {
  const h = histOf(it);
  if (h === 'wait') return `<p class="faint">${T('Reading…')}</p>`;
  if (!h || !h.renders.length) return `<p class="faint">${T('No render.')}</p>`;
  const ok = { finished: 'finished', failed: 'failed', cancelled: 'cancelled' };
  const min = s => (s ? T('{n} min', { n: Math.max(1, Math.round(s / 60)) }) : '');
  return `<div class="sec"><div class="sec-h">${T('Renders')}<span class="faint">${h.renders.length}</span></div>${h.renders
    .map(
      r => `<div class="rh">${jst(ok[r.status] || 'finished')}<div class="rb"><div class="vh"><b class="mono">${esc(r.folder || vShort(it, r.source))}</b>${r.department ? `<span class="tag">${esc(LBL[r.department] || r.department)}</span>` : ''}${r.status && r.status !== 'finished' ? `<span class="tag ${r.status === 'failed' ? 'fail' : ''}">${esc(r.status)}</span>` : ''}</div>
        <div class="vm faint">${[dShort(r.at), r.by, r.preset, r.frames ? 'f' + r.frames.join('–') : '', r.shot, min(r.seconds) && T('{t} of machine', { t: min(r.seconds) }), r.machines ? T('{n} machine|{n} machines', { n: r.machines }) : ''].filter(Boolean).map(esc).join(' · ')}</div></div></div>`
    )
    .join('')}</div>`;
}
