/* ---------- Breakdown › Activity: what was worked, beside what was finished ----------
   lib/monitoring/progress_log.py's days: "worked" ({shots|assets: {department: files}}, a
   file counted for a department on a day a session with it ticked was saved) and
   "seconds" (everyone's sessions that day). Two views: Files worked (a bar a day, its
   departments stacked, each its colour in the project's order) and Time (hours a day).
   Past four months, a bar a week: a day's mean for files, the week's total for time.
   Written for the days before today (the next morning's first Blender, Migrate old data). */
const ACT_WEEKS_AFTER = 120;
function actDays() {
  return Object.entries(M.history || {})
    .filter(([, p]) => p && ('worked' in p || 'seconds' in p))
    .sort((a, b) => (a[0] < b[0] ? -1 : 1));
}
/* The bars: [{day (its first), n (days in it), worked: {d: files}, hours, people}], weeks or days. */
function actBuckets(kind) {
  const days = actDays();
  const first = days.findIndex(
    ([, p]) => Object.keys((p.worked || {})[kind + 's'] || {}).length || p.seconds
  );
  if (first < 0) return { bars: [], week: false };
  const used = days.slice(first),
    span = (Date.parse(used[used.length - 1][0]) - Date.parse(used[0][0])) / 864e5,
    week = span > ACT_WEEKS_AFTER;
  const monday = d => {
    const t = new Date(d + 'T12:00:00'),
      k = (t.getDay() + 6) % 7;
    t.setDate(t.getDate() - k);
    return t.toISOString().slice(0, 10);
  };
  const bars = [],
    at = {};
  used.forEach(([day, p]) => {
    const key = week ? monday(day) : day;
    let b = at[key];
    if (!b) bars.push((b = at[key] = { day: key, n: 0, worked: {}, hours: 0, people: 0 }));
    b.n++;
    Object.entries((p.worked || {})[kind + 's'] || {}).forEach(
      ([d, n]) => (b.worked[d] = (b.worked[d] || 0) + n)
    );
    b.hours += (p.seconds || 0) / 3600;
    b.people = Math.max(b.people, p.people || 0);
  });
  // A week: files, a day's mean (its days counted, 7 once it's whole).
  if (week) bars.forEach(b => Object.keys(b.worked).forEach(d => (b.worked[d] /= Math.max(b.n, 1))));
  return { bars, week };
}
const actColor = (kind, d) => {
  const i = (DEPTS[kind] || []).indexOf(d);
  return i >= 0 && i < 8 ? `var(--cat-${i + 1})` : 'var(--st-todo)';
};
const ACT = {};
function activity() {
  const kind = S.ot.kind,
    mode = S.act,
    { bars, week } = actBuckets(kind),
    deps = DEPTS[kind] || [];
  const head = `<div class="ot-h"><b>${T('Activity')}</b><span class="join">${[
    ['files', T('Files worked')],
    ['time', T('Time')]
  ]
    .map(([k, l]) => `<button class="btn sm" data-actm="${k}" aria-pressed="${mode === k}">${l}</button>`)
    .join('')}</span>${
    mode === 'files'
      ? `<span class="join">${['shot', 'asset'].map(k => `<button class="btn sm" data-otk="${k}" aria-pressed="${kind === k}">${k === 'shot' ? T('Shots') : T('Assets')}</button>`).join('')}</span>`
      : ''
  }
    <span class="ot-lg ac-lg">${
      mode === 'files'
        ? deps.map(d => `<span><i style="--c:${actColor(kind, d)}"></i>${esc(LBL[d])}</span>`).join('')
        : `<span><i style="--c:var(--brand)"></i>${T('Hours')}</span>`
    }</span></div>
    <p class="faint ac-say">${
      mode === 'files'
        ? week
          ? T('Files with a session saved, department by department: a day’s mean, week by week.')
          : T('Files with a session saved that day, department by department (Working on).')
        : week
          ? T('Everyone’s sessions, saved ones: hours a week.')
          : T('Everyone’s sessions, saved ones: hours a day.')
    }</p>`;
  if (!bars.length)
    return `<div class="ot act">${head}<p class="faint ot-empty">${T('Nothing logged yet: written each morning for the day before, and by Migrate old data for the days before.')}</p></div>`;
  const W = 720,
    H = 170,
    pl = 40,
    pr = 12,
    pt = 10,
    pb = 26;
  const total = b => (mode === 'files' ? Object.values(b.worked).reduce((a, n) => a + n, 0) : b.hours);
  const top = Math.max(1, ...bars.map(total)),
    step =
      top <= 5
        ? 1
        : top <= 10
          ? 2
          : top <= 25
            ? 5
            : top <= 50
              ? 10
              : top <= 100
                ? 20
                : Math.ceil(top / 50) * 10,
    max = Math.ceil(top / step) * step;
  const slot = (W - pl - pr) / bars.length,
    gap = slot > 6 ? 2 : slot > 3 ? 1 : 0,
    bw = Math.max(1, slot - gap),
    Y = v => pt + (1 - v / max) * (H - pt - pb);
  const rects = bars
    .map((b, i) => {
      const x = pl + i * slot + gap / 2;
      if (mode === 'time')
        return b.hours
          ? `<rect class="ac-b" x="${x.toFixed(1)}" y="${Y(b.hours).toFixed(1)}" width="${bw.toFixed(1)}" height="${(Y(0) - Y(b.hours)).toFixed(1)}" style="fill:var(--brand)"/>`
          : '';
      let y0 = Y(0),
        out = '';
      deps.forEach(d => {
        const v = b.worked[d];
        if (!v) return;
        const h = Y(0) - Y(v),
          seg = Math.max(0, h - (h > 3 ? 1 : 0)); // a 1 px gap between departments
        out += `<rect class="ac-b" x="${x.toFixed(1)}" y="${(y0 - h).toFixed(1)}" width="${bw.toFixed(1)}" height="${seg.toFixed(1)}" style="fill:${actColor(kind, d)}"/>`;
        y0 -= h;
      });
      return out;
    })
    .join('');
  const fmt = d => new Date(d + 'T12:00:00').toLocaleDateString(DTL(), { day: 'numeric', month: 'short' });
  const ticks = [0, Math.floor((bars.length - 1) / 2), bars.length - 1].filter(
    (v, i, a) => a.indexOf(v) === i
  );
  const svg = `<svg class="ot-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${T('Activity')}">
    ${[0, max / 2, max].map(v => `<line class="ot-grid" x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ot-ax" x="${pl - 6}" y="${Y(v) + 4}" text-anchor="end">${Math.round(v * 10) / 10}${mode === 'time' ? ' h' : ''}</text>`).join('')}
    ${ticks.map(i => `<text class="ot-ax" x="${pl + i * slot + slot / 2}" y="${H - 6}" text-anchor="${i === 0 ? 'start' : i === bars.length - 1 ? 'end' : 'middle'}">${fmt(bars[i].day)}</text>`).join('')}
    <rect class="ac-hv" hidden y="${pt}" height="${H - pt - pb}"/>
    ${rects}
    <rect class="ot-hit" x="${pl}" y="0" width="${W - pl - pr}" height="${H}" fill="transparent"/></svg>`;
  Object.assign(ACT, { bars, week, kind, mode, geo: { W, pl, slot } });
  return `<div class="ot act">${head}<div class="ac-box">${svg}<div class="ot-tip" hidden></div></div></div>`;
}
/* The hover: the bar under the pointer, its figures. */
function actHover(e) {
  const box = e.target.closest('.ac-box');
  if (!box || !ACT.bars) return;
  const svg = box.querySelector('svg'),
    r = svg.getBoundingClientRect(),
    g = ACT.geo,
    x = ((e.clientX - r.left) / r.width) * g.W,
    i = Math.min(ACT.bars.length - 1, Math.max(0, Math.floor((x - g.pl) / g.slot))),
    b = ACT.bars[i],
    hv = svg.querySelector('.ac-hv'),
    tip = box.querySelector('.ot-tip');
  hv.hidden = false;
  hv.setAttribute('x', g.pl + i * g.slot);
  hv.setAttribute('width', g.slot);
  const when = ACT.week
    ? T('Week of {date}', {
        date: new Date(b.day + 'T12:00:00').toLocaleDateString(DTL(), { day: 'numeric', month: 'short' })
      })
    : new Date(b.day + 'T12:00:00').toLocaleDateString(DTL(), {
        weekday: 'short',
        day: 'numeric',
        month: 'short'
      });
  const n = v => (Math.round(v * 10) / 10).toString();
  let rows;
  if (ACT.mode === 'time')
    rows = `<span><i style="--c:var(--brand)"></i>${T('{h} h', { h: n(b.hours) })} · ${T('{n} person|{n} people', { n: b.people })}</span>`;
  else {
    const ds = (DEPTS[ACT.kind] || []).filter(d => b.worked[d]).reverse();
    rows = ds.length
      ? ds
          .map(
            d =>
              `<span><i style="--c:${actColor(ACT.kind, d)}"></i>${esc(LBL[d])} <b>${n(b.worked[d])}</b></span>`
          )
          .join('')
      : `<span>${T('Nothing worked')}</span>`;
  }
  tip.hidden = false;
  tip.innerHTML = `<b>${when}</b>${rows}`;
  const left = ((g.pl + (i + 1) * g.slot) / g.W) * r.width;
  tip.style.left = Math.min(Math.max(left + 8, 0), r.width - tip.offsetWidth) + 'px';
}
function actLeave(e) {
  const box = e.target.closest('.ac-box');
  if (!box) return;
  box.querySelector('.ac-hv').hidden = true;
  box.querySelector('.ot-tip').hidden = true;
}
