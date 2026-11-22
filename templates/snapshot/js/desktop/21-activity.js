/* ---------- Breakdown › Activity: what was worked, beside what was finished ----------
   lib/monitoring/progress_log.py's days: "worked" ({shots|assets: {department: files}}, a
   file counted for a department on a day a session with it ticked was saved) and
   "seconds" (everyone's sessions that day). Two views: Files worked and Time, a column of
   diamonds a day -- the state glyph's shape -- each diamond some files, or some hours:
   the scale (1, 2, 3, 5, 10…) the one that fits the busiest day. An estimate on purpose,
   not a count to the minute (work time watched closely turns sour). Departments in
   colour, the 7 most worked over the whole project past 8 (the rest "Others", grey).
   Past four months, a column a week: a day's mean for files, the week's total for time.
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
/* The departments in colour: all up to 8; past, the 7 most worked over the whole project
   (worked so far: a colour that doesn't move with the view), in the project's order. */
const ACT_OTHER = 'var(--st-todo)';
function actColors(kind) {
  const deps = DEPTS[kind] || [];
  let shown = deps;
  if (deps.length > 8) {
    const sum = {};
    Object.values(M.history || {}).forEach(p =>
      Object.entries(((p || {}).worked || {})[kind + 's'] || {}).forEach(
        ([d, n]) => (sum[d] = (sum[d] || 0) + n)
      )
    );
    const top = [...deps]
      .sort((a, b) => (sum[b] || 0) - (sum[a] || 0) || deps.indexOf(a) - deps.indexOf(b))
      .slice(0, 7);
    shown = deps.filter(d => top.includes(d));
  }
  const c = {};
  deps.forEach(d => (c[d] = shown.includes(d) ? `var(--cat-${shown.indexOf(d) + 1})` : ACT_OTHER));
  return { c, shown, others: deps.filter(d => !shown.includes(d)) };
}
/* A diamond's worth: the smallest step that fits the busiest column in `room` diamonds. */
function actStep(top, room, steps) {
  return steps.find(k => Math.ceil(top / k) <= room) || Math.ceil(top / room);
}
const ACT = {};
function activity() {
  const kind = S.ot.kind,
    mode = S.act,
    { bars, week } = actBuckets(kind),
    deps = DEPTS[kind] || [],
    col = actColors(kind);
  const W = 720,
    H = 170,
    pl = 12,
    pr = 12,
    pt = 8,
    pb = 26;
  const total = b => (mode === 'files' ? Object.values(b.worked).reduce((a, n) => a + n, 0) : b.hours);
  const slot = bars.length ? (W - pl - pr) / bars.length : 1,
    // A diamond: as wide as its column allows, never under 6 or over 12 units.
    fit = Math.max(6, Math.min(12, slot - 2)),
    room = Math.max(1, Math.floor((H - pt - pb) / fit)),
    top = Math.max(0, ...bars.map(total)),
    step = actStep(top, room, mode === 'files' ? [1, 2, 3, 5, 10, 20, 50, 100] : [1, 2, 4, 8, 16, 40, 80]),
    // Then as big as the busiest column leaves room for (16 at most).
    size = Math.max(6, Math.min(16, slot - 2, (H - pt - pb) / Math.max(1, Math.ceil(top / step))));
  const unit =
    mode === 'files'
      ? T('◆ = {n} file|◆ = {n} files', { n: step })
      : T('◆ = {n} hour|◆ = {n} hours', { n: step });
  const legend =
    mode === 'files'
      ? [
          ...col.shown.map(d => `<span><i class="dm" style="--c:${col.c[d]}"></i>${esc(LBL[d])}</span>`),
          ...(col.others.length
            ? [
                `<span title="${esc(col.others.map(d => LBL[d]).join(', '))}"><i class="dm" style="--c:${ACT_OTHER}"></i>${T('Others')}</span>`
              ]
            : [])
        ].join('')
      : `<span><i class="dm" style="--c:var(--brand)"></i>${T('Hours')}</span>`;
  const head = `<div class="ot-h"><b>${T('Activity')}</b><span class="join">${[
    ['files', T('Files worked')],
    ['time', T('Time')]
  ]
    .map(([k, l]) => `<button class="btn sm" data-actm="${k}" aria-pressed="${mode === k}">${l}</button>`)
    .join('')}</span>${
    mode === 'files'
      ? `<span class="join">${['shot', 'asset'].map(k => `<button class="btn sm" data-otk="${k}" aria-pressed="${kind === k}">${k === 'shot' ? T('Shots') : T('Assets')}</button>`).join('')}</span>`
      : ''
  }<span class="ot-lg ac-lg">${legend}</span></div>
    <p class="faint ac-say">${bars.length ? `<b class="ac-unit">${unit}</b> · ` : ''}${
      mode === 'files'
        ? week
          ? T('files with a session saved, department by department: a day’s mean, week by week.')
          : T('files with a session saved that day, department by department (Working on).')
        : week
          ? T('everyone’s sessions, saved ones, week by week: an estimate.')
          : T('everyone’s sessions, saved ones, day by day: an estimate.')
    }</p>`;
  if (!bars.length)
    return `<div class="ot act">${head}<p class="faint ot-empty">${T('Nothing logged yet: written each morning for the day before, and by Migrate old data for the days before.')}</p></div>`;
  const base = H - pb,
    f = n => n.toFixed(1);
  // Each column's diamonds, bottom up: its departments in the project's order, "Others"
  // last; counted on the running total, rounded (the column's total right, a small
  // department may get none); at least one when anything was done.
  const marks = bars
    .map((b, i) => {
      const parts =
        // Nothing that day (a weekend at 0 h): no diamond -- the "at least one" is for a day with some.
        (mode === 'time'
          ? [['var(--brand)', b.hours]]
          : [
              ...col.shown.filter(d => b.worked[d]).map(d => [col.c[d], b.worked[d]]),
              [ACT_OTHER, col.others.reduce((a, d) => a + (b.worked[d] || 0), 0)]
            ]
        ).filter(x => x[1] > 0);
      if (!parts.length) return '';
      let run = 0,
        done = 0,
        out = '';
      const cx = pl + i * slot + slot / 2,
        r = (size * 0.86) / 2;
      parts.forEach(([c, v], k) => {
        run += v;
        let upto = Math.round(run / step);
        if (k === parts.length - 1 && upto === 0) upto = 1;
        for (; done < upto; done++) {
          const cy = base - size * (done + 0.5);
          out += `<path style="fill:${c}" d="M${f(cx)} ${f(cy - r)}L${f(cx + r)} ${f(cy)}L${f(cx)} ${f(cy + r)}L${f(cx - r)} ${f(cy)}Z"/>`;
        }
      });
      return out;
    })
    .join('');
  const fmt = d => new Date(d + 'T12:00:00').toLocaleDateString(DTL(), { day: 'numeric', month: 'short' });
  const ticks = [0, Math.floor((bars.length - 1) / 2), bars.length - 1].filter(
    (v, i, a) => a.indexOf(v) === i
  );
  const svg = `<svg class="ot-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${T('Activity')} · ${esc(unit)}">
    <line class="ot-grid" x1="${pl}" x2="${W - pr}" y1="${base + 2}" y2="${base + 2}"/>
    ${ticks.map(i => `<text class="ot-ax" x="${pl + i * slot + slot / 2}" y="${H - 6}" text-anchor="${i === 0 ? 'start' : i === bars.length - 1 ? 'end' : 'middle'}">${fmt(bars[i].day)}</text>`).join('')}
    <rect class="ac-hv" hidden y="${pt}" height="${H - pt - pb + 4}" rx="4"/>
    ${marks}
    <rect class="ot-hit" x="${pl}" y="0" width="${W - pl - pr}" height="${H}" fill="transparent"/></svg>`;
  Object.assign(ACT, { bars, week, kind, mode, col, geo: { W, pl, slot } });
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
    rows = `<span><i class="dm" style="--c:var(--brand)"></i>${T('about {h} h', { h: Math.round(b.hours * 2) / 2 })} · ${T('{n} person|{n} people', { n: b.people })}</span>`;
  else {
    const ds = (DEPTS[ACT.kind] || []).filter(d => b.worked[d]).reverse();
    rows = ds.length
      ? ds
          .map(
            d =>
              `<span><i class="dm" style="--c:${ACT.col.c[d]}"></i>${esc(LBL[d])} <b>${n(b.worked[d])}</b></span>`
          )
          .join('')
      : `<span>${T('Nothing worked')}</span>`;
  }
  tip.hidden = false;
  tip.innerHTML = `<b>${when}</b>${rows}`;
  tip.classList.toggle('two', (rows.match(/<span>/g) || []).length > 5);
  const left = ((g.pl + (i + 1) * g.slot) / g.W) * r.width;
  tip.style.left = Math.min(Math.max(left + 8, 0), r.width - tip.offsetWidth) + 'px';
}
function actLeave(e) {
  const box = e.target.closest('.ac-box');
  if (!box) return;
  box.querySelector('.ac-hv').hidden = true;
  box.querySelector('.ot-tip').hidden = true;
}
