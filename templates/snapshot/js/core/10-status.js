/* ---------- A state's glyph: a base shape, a corner badge, its words ---------- */
const BASE = {
  todo: ['--st-todo', ''],
  wip: ['--st-wip', 'dots'],
  done: ['--st-done', ''],
  rework: ['--st-done', 'back'],
  val: ['--st-val', 'check'],
  sup: ['--st-sup', 'check'],
  old: ['--st-old', 'check']
};
/* rdot: its own render after its latest session (1, a dot) or before (0, the dot faint); none: never rendered. */
function glyph(base, corner, cnt, note, rdot) {
  if (base === 'na')
    return `<svg class="g" viewBox="0 0 22 22" aria-hidden="true"><path d="M6 12h8" style="stroke:var(--line-3)" stroke-width="2" stroke-linecap="round"/></svg>`;
  const [c, inner] = BASE[base];
  let s = `<svg class="g" viewBox="0 0 22 22" aria-hidden="true"><path d="M10 4.5 17.5 12 10 19.5 2.5 12z" style="fill:var(${c})"/>`;
  if (inner === 'dots')
    s += `<g style="fill:var(--on-st)"><circle cx="7" cy="12" r="1.15"/><circle cx="10" cy="12" r="1.15"/><circle cx="13" cy="12" r="1.15"/></g>`;
  /* Reworked since its stable: the done diamond, an arrow back in it (to redo, an earlier stage changed: the orange corner). */
  if (inner === 'back')
    s += `<path d="M12.6 10.4H8.4M9.9 8.7 8.2 10.4l1.7 1.7M8.4 10.4h3.4a1.9 1.9 0 0 1 0 3.8H9.6" fill="none" style="stroke:var(--on-st)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>`;
  if (inner === 'check')
    s += `<path d="M7 12.2 9.1 14.3 13.2 10.2" fill="none" style="stroke:var(--on-st)" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>`;
  if (corner) {
    const cc = {
      rtk: '--st-rtk',
      wait: '--st-wait',
      redo: '--st-wip',
      you: '--st-you',
      'you-rtk': '--st-you'
    }[corner];
    s += `<circle cx="17" cy="5.5" r="5.2" style="fill:var(${cc});stroke:var(--area)" stroke-width="1.6"/>`;
    if (corner === 'rtk')
      s += `<text x="17" y="8.3" text-anchor="middle" font-size="8" font-weight="700" font-family="Inter,sans-serif" fill="#fff">${cnt > 9 ? '9+' : cnt || '!'}</text>`;
    if (corner === 'wait')
      s += `<path d="M14.6 2.8h4.8M14.6 8.2h4.8M15.2 2.8 17 5.5l-1.8 2.7M18.8 2.8 17 5.5l1.8 2.7" style="stroke:var(--on-st)" stroke-width="1.1" fill="none"/>`;
    if (corner === 'redo')
      s += `<path d="M19.1 4.4A2.4 2.4 0 1 0 19.4 6.4" style="stroke:var(--on-st)" stroke-width="1.3" fill="none" stroke-linecap="round"/><path d="M19.6 2.7v2.2h-2.2" style="stroke:var(--on-st)" stroke-width="1.3" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`;
    if (corner === 'you')
      s += `<path d="M14.8 5.6 16.4 7.2 19.3 4.2" style="stroke:var(--on-st)" stroke-width="1.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`;
    if (corner === 'you-rtk')
      s += `<path d="M15.2 3.7 18.8 7.3M18.8 3.7 15.2 7.3" style="stroke:var(--on-st)" stroke-width="1.4" stroke-linecap="round"/>`;
  }
  if (rdot != null)
    s += `<circle cx="3.6" cy="18.4" r="2.6" style="fill:var(--text);stroke:var(--area)" stroke-width="1.4"${rdot ? '' : ' opacity="0.35"'}/>`;
  if (note)
    s += `<path d="M13.6 14.6h6.6a1.3 1.3 0 0 1 1.3 1.3v3.2a1.3 1.3 0 0 1-1.3 1.3h-3.6l-2.2 1.7v-1.7h-.8a1.3 1.3 0 0 1-1.3-1.3v-3.2a1.3 1.3 0 0 1 1.3-1.3z" style="fill:var(--text-2);stroke:var(--area)" stroke-width="1.3"/>`;
  return s + '</svg>';
}
/* A department's state, a review's "done on the stable" (marked) over it. */
const isDone = st => st === 'done' || st === 'rework';
const stOf = (it, d) => {
  const m = (it.marked || {})[d],
    st = it.states[d] || 'todo';
  return m === true && !isDone(st) ? 'done' : m === false && isDone(st) ? 'wip' : st;
};
const required = it => (it.req ? Object.keys(it.req).filter(d => it.req[d]) : Object.keys(it.states));
const rtkNotes = (it, d) =>
  it.notes.filter(n => n.type === 'rtk' && !n.done && (d == null ? true : n.deps.includes(d)));
function info(it, d) {
  if (!required(it).includes(d)) return { base: 'na', l: T('Not required'), s: '', tone: '' };
  const st = stOf(it, d),
    ok = it.ok[d],
    mine = it.mine[d],
    f = it.flags[d] || {};
  let base = st === 'todo' ? 'todo' : st === 'wip' ? 'wip' : st === 'rework' ? 'rework' : 'done',
    l =
      { todo: T('To do'), wip: T('In progress'), done: T('Done'), rework: T('Done, reworked') }[st] ||
      T('To do');
  if (ok) {
    base = ok.old ? 'old' : ok.role === M.role ? 'val' : 'sup';
    l = ok.old ? T('To review again') : T('Validated {role}', { role: ok.role });
  }
  let corner = null,
    cnt = 0,
    s = '',
    tone = '';
  const rn = rtkNotes(it, d).length,
    rk = it.rtk[d];
  if (st === 'rework' && !ok) s = T('reworked since the stable');
  if (f.to_redo) {
    corner = 'redo';
    s = T('to redo: {why}', { why: f.to_redo });
    tone = 'redo';
  }
  if (f.waiting) {
    corner = 'wait';
    s = T('waiting: {why}', { why: f.waiting });
    tone = 'wait';
  }
  if (rk || rn) {
    corner = 'rtk';
    cnt = rn || 1;
    s = T('{n} RTK · {who}', { n: rn || 1, who: rk && rk !== 'team' ? rk : T('team') });
    tone = 'rtk';
  }
  if (d in (it.marked || {}) && !mine) {
    corner = 'you';
    s = it.marked[d] ? T('you: done on the stable, not sent yet') : T('you: not done, not sent yet');
    tone = 'you';
  }
  if (mine === 'val') {
    base = S.review && S.review.role !== M.role ? 'sup' : 'val';
    l = T('Validated {role}', { role: S.review ? S.review.role : '' });
    corner = 'you';
    s = T('you · not sent yet');
    tone = 'you';
  }
  if (mine === 'rtk') {
    corner = 'you-rtk';
    s = T('you: retake');
    tone = 'you';
  }
  const nn =
    it.notes.filter(n => n.type !== 'rtk' && !n.done && n.deps.includes(d)).length +
    it.myNotes.filter(n => n.type !== 'rtk' && n.dept === d).length;
  if (nn && !s) s = T('{n} note|{n} notes', { n: nn });
  // Its own render, after its latest session or not (snapshot.py render_freshness()): the dot, its words in the tooltip.
  const rf = (it.rf || {})[d],
    r = rf ? rf[0] : null,
    rt = rf ? T(rf[0] ? 'render up to date ({date})' : 'render older than its last session ({date})', { date: fmtD(rf[1]) }) : '';
  return { base, corner, cnt, l, s, tone, note: nn > 0, r, rt };
}
/* A department's tooltip: its state, what's on top, its render. */
const cellTitle = (d, x) => `${LBL[d]}: ${esc(x.l)}${x.s ? ' · ' + esc(x.s) : ''}${x.rt ? ' · ' + esc(x.rt) : ''}`;
const cellHTML = (it, d) => {
  const x = info(it, d);
  return `<span class="cell ${x.base === 'na' ? 'na' : ''}" title="${cellTitle(d, x)}">${glyph(x.base, x.corner, x.cnt, x.note, x.r)}<span class="ab">${AB[d]}</span><span class="tx"><span class="l">${esc(x.l)}</span>${x.s ? `<span class="s ${x.tone}">${esc(x.s)}</span>` : ''}</span></span>`;
};
const openRtk = it => rtkNotes(it).length + it.myNotes.filter(n => n.type === 'rtk').length;
// A validation's own line is a record, not a note: never counted.
const openNotes = it => it.notes.filter(n => !n.done && !n.approval).length + it.myNotes.length;
const omitted = it => (it.setAside !== undefined ? it.setAside : it.omit)?.state;
const toValidate = it =>
  !omitted(it) &&
  required(it).some(d => ['done', 'rework'].includes(it.states[d]) && !it.ok[d] && !it.rtk[d] && !it.mine[d]);
const touched = it =>
  Object.keys(it.edits || {}).length ||
  Object.keys(it.marked || {}).length ||
  Object.keys(it.mine).length ||
  it.myNotes.length ||
  Object.keys(it.myReplies).length ||
  it.setAside !== undefined ||
  it.req ||
  it.assign ||
  Object.keys(it.still).length ||
  Object.keys(it.fixed).length ||
  it.descEdit !== undefined;
function worst(it) {
  if (omitted(it)) return 'omit';
  const ds = required(it);
  if (ds.some(d => it.rtk[d] || it.mine[d] === 'rtk')) return 'rtk';
  if (!ds.length) return 'todo';
  if (ds.every(d => it.ok[d] || it.mine[d] === 'val')) return 'val';
  if (ds.every(d => ['done', 'rework'].includes(it.states[d]))) return 'done';
  if (ds.some(d => it.states[d] !== 'todo')) return 'wip';
  return 'todo';
}
const DOT = {
  omit: 'var(--line-3)',
  rtk: 'var(--st-rtk)',
  val: 'var(--st-val)',
  done: 'var(--st-done)',
  wip: 'var(--st-wip)',
  todo: 'var(--st-todo)'
};
const valOf = it => {
  const ds = required(it);
  if (!ds.length) return it.valid;
  return ds.filter(d => it.ok[d] || it.mine[d] === 'val').length / ds.length;
};
const me = () => (S.review && S.review.name) || M.live.user;
function visible() {
  return items
    .filter(it => it.kind === S.ws)
    .filter(it => {
      if (S.q && !(it.name + ' ' + it.desc).toLowerCase().includes(S.q)) return false;
      if (S.quick === 'rtk' && !openRtk(it)) return false;
      if (S.quick === 'notes' && !openNotes(it)) return false;
      if (S.quick === 'val' && !toValidate(it)) return false;
      if (S.quick === 'mine' && !touched(it)) return false;
      if (S.dept && !required(it).includes(S.dept)) return false;
      if (S.more.has('me') && !DEPTS[it.kind].some(d => assignOf(it, d).includes(me()))) return false;
      if (S.more.has('farm') && !it.farm) return false;
      if (S.more.has('unfinished') && !required(it).some(d => !['done', 'rework'].includes(it.states[d])))
        return false;
      if (S.more.has('tocheck') && !it.toCheck) return false;
      if (S.more.has('outdated') && !it.outdated) return false;
      if (S.more.has('tracked') && !required(it).length) return false;
      return true;
    });
}
const groupOf = it => (it.kind === 'shot' ? it.group : it.name.split('_')[0]);
const cur = () => items.find(i => i.name === S.sel);
