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
  // Each bar's departments, bottom up: [{c (colour), v, y0, y1}].
  const segs = bars.map(b =>
    mode === 'time'
      ? b.hours
        ? [{ c: 'var(--brand)', v: b.hours, y0: Y(0), y1: Y(b.hours) }]
        : []
      : deps
          .filter(d => b.worked[d])
          .reduce((out, d) => {
            const base = out.length ? out[out.length - 1].top : 0;
            out.push({
              c: actColor(kind, d),
              v: b.worked[d],
              top: base + b.worked[d],
              y0: Y(base),
              y1: Y(base + b.worked[d])
            });
            return out;
          }, [])
  );
  const rects = actMarks(ACT_STYLE(), segs, {
    slot,
    gap,
    bw,
    pl,
    pt,
    H,
    pb,
    Y,
    max,
    order: mode === 'time' ? ['var(--brand)'] : deps.map(d => actColor(kind, d))
  });
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

/* The bars' look (one kept once chosen): rail, round, diamond or area. */
const ACT_STYLE = () => S.actStyle || 'round';
function actMarks(style, segs, g) {
  const f = n => n.toFixed(1),
    X = i => g.pl + i * g.slot + g.gap / 2;
  if (style === 'area') {
    // Each department a band through the bars' middles, stacked, its top edge drawn.
    const cx = i => g.pl + i * g.slot + g.slot / 2,
      order = [];
    segs.forEach(ss => ss.forEach(s => !order.includes(s.c) && order.push(s.c)));
    order.sort((a, b) => g.order.indexOf(a) - g.order.indexOf(b)); // the departments' own order, bottom up
    const below = segs.map(() => 0);
    let out = '';
    order.forEach(c => {
      const lo = below.slice(),
        hi = segs.map((ss, i) => lo[i] + ((ss.find(s => s.c === c) || {}).v || 0));
      const top = hi.map((v, i) => f(cx(i)) + ' ' + f(g.Y(v))).join(' L'),
        back = lo
          .map((v, i) => f(cx(i)) + ' ' + f(g.Y(v)))
          .reverse()
          .join(' L');
      out += `<path class="ac-a" style="--c:${c}" d="M${top} L${back} Z"/><path class="ac-al" style="--c:${c}" d="M${top}"/>`;
      hi.forEach((v, i) => (below[i] = v));
    });
    return out;
  }
  return segs
    .map((ss, i) => {
      const x = X(i),
        w = g.bw;
      if (!ss.length)
        return style === 'rail'
          ? `<rect class="ac-rail" x="${f(x)}" y="${g.pt}" width="${f(w)}" height="${g.H - g.pt - g.pb}" rx="${Math.min(4, w / 2)}"/>`
          : '';
      if (style === 'diamond') {
        // A file, a diamond: the state glyph's shape, stacked (a week's mean, rounded).
        const cell = g.Y(0) - g.Y(1),
          s = Math.min(w, cell) * 0.92;
        let k = 0,
          out = '';
        ss.forEach(seg =>
          [...Array(Math.round(seg.v))].forEach(() => {
            const cy = g.Y(0) - cell * (k + 0.5),
              cxx = x + w / 2,
              r = s / 2;
            out += `<path style="fill:${seg.c}" d="M${f(cxx)} ${f(cy - r)}L${f(cxx + r)} ${f(cy)}L${f(cxx)} ${f(cy + r)}L${f(cxx - r)} ${f(cy)}Z"/>`;
            k++;
          })
        );
        return out;
      }
      const gapv = 2,
        r = Math.min(3, w / 2);
      let out = '';
      if (style === 'rail') {
        const id = 'acr' + i;
        out += `<clipPath id="${id}"><rect x="${f(x)}" y="${g.pt}" width="${f(w)}" height="${g.H - g.pt - g.pb}" rx="${Math.min(4, w / 2)}"/></clipPath><rect class="ac-rail" x="${f(x)}" y="${g.pt}" width="${f(w)}" height="${g.H - g.pt - g.pb}" rx="${Math.min(4, w / 2)}"/><g clip-path="url(#${id})">`;
        ss.forEach((seg, k) => {
          const h = seg.y0 - seg.y1 - (k < ss.length - 1 && seg.y0 - seg.y1 > 3 ? 1 : 0);
          out += `<rect x="${f(x)}" y="${f(seg.y0 - (seg.y0 - seg.y1))}" width="${f(w)}" height="${f(Math.max(0, h))}" style="fill:${seg.c}"/>`;
        });
        return out + '</g>';
      }
      // round: the top department rounded, a 2 px surface gap between departments.
      ss.forEach((seg, k) => {
        const last = k === ss.length - 1,
          h = Math.max(0, seg.y0 - seg.y1 - (k ? gapv : 0)),
          y = seg.y1;
        if (!last || h < r * 2)
          out += `<rect x="${f(x)}" y="${f(y)}" width="${f(w)}" height="${f(h)}" style="fill:${seg.c}"/>`;
        else
          out += `<path style="fill:${seg.c}" d="M${f(x)} ${f(y + h)}V${f(y + r)}Q${f(x)} ${f(y)} ${f(x + r)} ${f(y)}H${f(x + w - r)}Q${f(x + w)} ${f(y)} ${f(x + w)} ${f(y + r)}V${f(y + h)}Z"/>`;
      });
      return out;
    })
    .join('');
}
