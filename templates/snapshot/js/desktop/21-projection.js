/* ---------- Breakdown › Projection: where the pace leads ----------
   The days logged (Over time's), then a cone: each figure carried on between two paces --
   its last 30 days' and its last 90's (a straight line fitted to each) -- the slower as
   its lower edge, the faster as its upper: a wide cone, an uneven pace. Never down (a
   pace falling: none), Validated never above Done, nothing dated past a year from today
   (too hypothetical to say), the cones blurring as they go. The schedule's even pace
   dotted, its end marked. Months, never a day: an estimate. */
const PJ_SHORT = 30,
  PJ_LONG = 90,
  PJ_HORIZON = 365; // days: no date past it
/* A figure's pace over its last `days` days: a line fitted to them, {slope (a day), at
   (its value on the last day)}; null with fewer than 7 points. */
function pjPace(pts, k, days) {
  const last = pts.length ? Date.parse(pts[pts.length - 1].day) : 0,
    use = pts.filter(p => p[k] != null && !p.now && last - Date.parse(p.day) <= days * 864e5); // logged days only
  if (use.length < 7) return null;
  const xs = use.map(p => (Date.parse(p.day) - last) / 864e5),
    ys = use.map(p => p[k]),
    n = xs.length,
    mx = xs.reduce((a, x) => a + x, 0) / n,
    my = ys.reduce((a, y) => a + y, 0) / n;
  let num = 0,
    den = 0;
  xs.forEach((x, i) => {
    num += (x - mx) * (ys[i] - my);
    den += (x - mx) * (x - mx);
  });
  const slope = den ? num / den : 0;
  return { slope, at: Math.min(1, Math.max(0, my - slope * mx)) };
}
/* A figure's cone: {at (its last logged value), lo, hi (a day, never below 0)}; null
   without a week of points; lo = hi = 0 when it doesn't move up. */
function pjCone(pts, k) {
  const a = pjPace(pts, k, PJ_SHORT),
    b = pjPace(pts, k, PJ_LONG) || a;
  if (!a) return null;
  const last = [...pts].reverse().find(p => p[k] != null && !p.now) || pts[pts.length - 1];
  const s = [Math.max(0, a.slope), Math.max(0, b.slope)];
  return { at: last[k], lo: Math.min(...s), hi: Math.max(...s) };
}
function projection() {
  const o = S.ot,
    pts = otPoints(),
    sch = M.schedule;
  const head = `<div class="ot-h"><b>${T('Projection')}</b><span class="join">${['shot', 'asset'].map(k => `<button class="btn sm" data-otk="${k}" aria-pressed="${o.kind === k}">${k === 'shot' ? T('Shots') : T('Assets')}</button>`).join('')}</span>
    <span class="ot-lg"><i style="--c:var(--st-done)"></i>${T('Done')}<i style="--c:var(--st-val)"></i>${T('Validated')}${sch ? `<i class="pj-sch"></i>${T('Schedule')}` : ''}</span></div>`;
  const done = pjCone(pts, 'done'),
    val = pjCone(pts, 'val');
  if (!done)
    return `<div class="ot pj">${head}<p class="faint ot-empty">${T('A week of points at least: the projection follows the curve.')}</p></div>`;
  const month = t => new Date(t).toLocaleDateString(DTL(), { month: 'long', year: 'numeric' });
  const today = Date.parse((pts.filter(p => !p.now).pop() || pts[pts.length - 1]).day),
    horizon = today + PJ_HORIZON * 864e5;
  // When a pace reaches 100 % (Infinity: never, at that pace).
  const reach = (c, s) => (s > 0 ? today + ((1 - c.at) / s) * 864e5 : Infinity);
  const range = (c, name) => {
    if (!c || c.at >= 1) return '';
    if (c.hi <= 0) return T('{what}: no headway lately, no projection.', { what: name });
    const soon = reach(c, c.hi),
      late = reach(c, c.lo);
    if (soon > horizon) return T('{what}: not within a year at this pace, too far to date.', { what: name });
    if (late > horizon)
      return T('{what}: not before {when}; the slower pace dates nothing.', {
        what: name,
        when: month(soon)
      });
    return month(soon) === month(late)
      ? T('{what}: 100 % around {when}.', { what: name, when: month(soon) })
      : T('{what}: 100 % between {a} and {b}.', { what: name, a: month(soon), b: month(late) });
  };
  const say = [
    range(done, T('Done')),
    range(val, T('Validated')),
    sch ? T('The schedule ends in {when}.', { when: month(Date.parse(sch.end)) }) : ''
  ]
    .filter(Boolean)
    .join(' ');
  const W = 720,
    H = 200,
    pl = 40,
    pr = 92,
    pt = 12,
    pb = 26;
  const soonDone = done.hi > 0 ? reach(done, done.hi) : 0;
  const t0 = Math.min(Date.parse(pts[0].day), sch ? Date.parse(sch.start) : Infinity),
    // Done's earliest 100 % and the schedule's end in view, never past the horizon.
    t1 = Math.min(
      horizon,
      Math.max(today + 30 * 864e5, soonDone, sch ? Date.parse(sch.end) : 0) + 20 * 864e5
    ),
    X = t => pl + ((t - t0) / (t1 - t0 || 1)) * (W - pl - pr),
    Y = v => pt + (1 - v) * (H - pt - pb);
  const line = k =>
    pts
      .filter(p => p[k] != null)
      .map((p, i) => (i ? 'L' : 'M') + X(Date.parse(p.day)).toFixed(1) + ' ' + Y(p[k]).toFixed(1))
      .join(' ');
  // A cone's edges, sampled from today to the chart's end; cap: the values it may not
  // pass (Validated's: Done's edges).
  const N = 24,
    ts = [...Array(N + 1)].map((_, i) => today + ((t1 - today) * i) / N),
    edge = (c, s, cap) => ts.map((t, i) => Math.min(1, c.at + (s * (t - today)) / 864e5, cap ? cap[i] : 1));
  const dLo = edge(done, done.lo),
    dHi = edge(done, done.hi);
  const cone = (c, lo, hi, col) => {
    if (!c || c.hi <= 0 || c.at >= 1) return '';
    const up = ts.map((t, i) => `${X(t).toFixed(1)} ${Y(hi[i]).toFixed(1)}`),
      down = ts.map((t, i) => `${X(t).toFixed(1)} ${Y(lo[i]).toFixed(1)}`);
    return `<path class="pj-c" style="--c:${col}" d="M${up.join(' L')} L${[...down].reverse().join(' L')} Z"/>
      <path class="pj-l" style="--c:${col}" d="M${up.join(' L')}"/><path class="pj-l" style="--c:${col}" d="M${down.join(' L')}"/>`;
  };
  const fmt = t => new Date(t).toLocaleDateString(DTL(), { month: 'short', year: 'numeric' });
  /* The cones the further the blurrier: the same drawing in layers each more blurred
     (0, 0.4, 1.2, 3.5, 9: growing ever faster -- sharp a while, then fast lost), each
     seen over its stretch of the way -- masks fading one into the
     next (they add up to one everywhere), from today (sharp) to the chart's end. */
  const blurred = (marks, x0, x1) => {
    if (!marks) return '';
    const B = [0, 0.4, 1.2, 3.5, 9],
      n = B.length - 1;
    const defs = B.map(
      (b, k) =>
        `<linearGradient id="pjg${k}" gradientUnits="userSpaceOnUse" x1="${x0}" x2="${x1}" y1="0" y2="0">${B.map((_, j) => `<stop offset="${j / n}" stop-color="#fff" stop-opacity="${j === k ? 1 : 0}"/>`).join('')}</linearGradient>
        <mask id="pjm${k}" maskUnits="userSpaceOnUse" x="0" y="0" width="${W}" height="${H}"><rect x="0" y="0" width="${W}" height="${H}" fill="url(#pjg${k})"/>${k === 0 ? `<rect x="0" y="0" width="${x0}" height="${H}" fill="#fff"/>` : ''}${k === n ? `<rect x="${x1}" y="0" width="${W - x1}" height="${H}" fill="#fff"/>` : ''}</mask>
        ${b ? `<filter id="pjf${k}" filterUnits="userSpaceOnUse" x="-30" y="-40" width="${W + 60}" height="${H + 80}"><feGaussianBlur stdDeviation="${b}"/></filter>` : ''}`
    ).join('');
    return `<defs>${defs}</defs>${B.map((b, k) => `<g mask="url(#pjm${k})"><g ${b ? `filter="url(#pjf${k})"` : ''}>${marks}</g></g>`).join('')}`;
  };
  const ticks = [t0, today, t1];
  const sEnd = sch ? Date.parse(sch.end) : 0,
    sStart = sch ? Date.parse(sch.start) : 0,
    sTo = Math.min(t1, sEnd);
  const svg = `<svg class="ot-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${T('Projection')}">
    ${[0, 0.5, 1].map(v => `<line class="ot-grid" x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ot-ax" x="${pl - 6}" y="${Y(v) + 4}" text-anchor="end">${v * 100} %</text>`).join('')}
    ${ticks.map((t, i) => `<text class="ot-ax" x="${X(t)}" y="${H - 6}" text-anchor="${i === 0 ? 'start' : i === 2 ? 'end' : 'middle'}">${i === 1 ? T('today') : fmt(t)}</text>`).join('')}
    <line class="pj-now" x1="${X(today)}" x2="${X(today)}" y1="${pt}" y2="${H - pb}"/>
    ${sch ? `<path class="pj-even" d="M${X(sStart).toFixed(1)} ${Y(0)} L${X(sTo).toFixed(1)} ${Y(Math.min(1, (sTo - sStart) / (sEnd - sStart || 1)))}"/>` : ''}
    ${sch && sEnd <= t1 ? `<line class="pj-end" x1="${X(sEnd)}" x2="${X(sEnd)}" y1="${pt}" y2="${H - pb}"/><text class="ot-ax" x="${X(sEnd) + 5}" y="${H - pb - 6}">${T('end')} · ${fmt(sEnd)}</text>` : ''}
    ${blurred((val ? cone(val, edge(val, val.lo, dLo), edge(val, val.hi, dHi), 'var(--st-val)') : '') + cone(done, dLo, dHi, 'var(--st-done)'), X(today), X(t1))}
    <path class="ot-l" style="--c:var(--st-val)" d="${line('val')}"/><path class="ot-l" style="--c:var(--st-done)" d="${line('done')}"/>
    </svg>`;
  return `<div class="ot pj">${head}<p class="faint ac-say">${say}</p><div class="pj-box">${svg}</div></div>`;
}
