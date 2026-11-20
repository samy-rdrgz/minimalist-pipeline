/* ---------- Breakdown › Projection: where the pace leads ----------
   The days logged (Over time's), then, dashed, each figure carried on at the pace of its
   last 30 days (a straight line fitted to them) up to 100 %; the schedule's even pace
   dotted (Edit project › Schedule), its end marked. A month, not a day: an estimate. */
const PJ_DAYS = 30;
/* A figure's pace: a line fitted to its last PJ_DAYS days, {slope (a day), at (its value
   on the last day)}; null with fewer than 7 points. */
function pjPace(pts, k) {
  const last = pts.length ? Date.parse(pts[pts.length - 1].day) : 0,
    use = pts.filter(p => p[k] != null && !p.now && last - Date.parse(p.day) <= PJ_DAYS * 864e5); // logged days only
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
function projection() {
  const o = S.ot,
    pts = otPoints(),
    sch = M.schedule;
  const head = `<div class="ot-h"><b>${T('Projection')}</b><span class="join">${['shot', 'asset'].map(k => `<button class="btn sm" data-otk="${k}" aria-pressed="${o.kind === k}">${k === 'shot' ? T('Shots') : T('Assets')}</button>`).join('')}</span>
    <span class="ot-lg"><i style="--c:var(--st-done)"></i>${T('Done')}<i style="--c:var(--st-val)"></i>${T('Validated')}${sch ? `<i class="pj-sch"></i>${T('Schedule')}` : ''}</span></div>`;
  const month = t => new Date(t).toLocaleDateString(DTL(), { month: 'long', year: 'numeric' });
  const pace = { done: pjPace(pts, 'done'), val: pjPace(pts, 'val') };
  const today = pts.length ? Date.parse(pts[pts.length - 1].day) : Date.now();
  const reach = p => (p && p.slope > 0 ? today + ((1 - p.at) / p.slope) * 864e5 : null);
  const rd = reach(pace.done),
    rv = reach(pace.val);
  const say = [
    rd
      ? T('At the pace of the last {n} days, Done reaches 100 % around {when}.', {
          n: PJ_DAYS,
          when: month(rd)
        })
      : pace.done
        ? T('Done hasn’t moved over the last {n} days: no projection.', { n: PJ_DAYS })
        : '',
    rv ? T('Validated, around {when}.', { when: month(rv) }) : '',
    sch ? T('The schedule ends in {when}.', { when: month(Date.parse(sch.end)) }) : ''
  ]
    .filter(Boolean)
    .join(' ');
  if (!pace.done)
    return `<div class="ot pj">${head}<p class="faint ot-empty">${T('A week of points at least: the projection follows the curve.')}</p></div>`;
  const W = 720,
    H = 200,
    pl = 40,
    pr = 92,
    pt = 12,
    pb = 26;
  const t0 = Math.min(Date.parse(pts[0].day), sch ? Date.parse(sch.start) : Infinity),
    horizon = today + 730 * 864e5, // two years at most
    // Done's 100 % and the schedule's end in view; Validated may run off the edge.
    t1 = Math.min(horizon, Math.max(today + 14 * 864e5, rd || 0, sch ? Date.parse(sch.end) : 0) + 20 * 864e5),
    X = t => pl + ((t - t0) / (t1 - t0 || 1)) * (W - pl - pr),
    Y = v => pt + (1 - v) * (H - pt - pb);
  const line = k =>
    pts
      .filter(p => p[k] != null)
      .map((p, i) => (i ? 'L' : 'M') + X(Date.parse(p.day)).toFixed(1) + ' ' + Y(p[k]).toFixed(1))
      .join(' ');
  const ahead = (p, r) => {
    if (!p) return '';
    const end = r ? Math.min(r, t1) : t1,
      v = Math.min(1, p.at + (p.slope * (end - today)) / 864e5);
    return `M${X(today).toFixed(1)} ${Y(p.at).toFixed(1)} L${X(end).toFixed(1)} ${Y(v).toFixed(1)}`;
  };
  const fmt = t => new Date(t).toLocaleDateString(DTL(), { month: 'short', year: 'numeric' });
  const ticks = [t0, today, t1];
  const svg = `<svg class="ot-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${T('Projection')}">
    ${[0, 0.5, 1].map(v => `<line class="ot-grid" x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ot-ax" x="${pl - 6}" y="${Y(v) + 4}" text-anchor="end">${v * 100} %</text>`).join('')}
    ${ticks.map((t, i) => `<text class="ot-ax" x="${X(t)}" y="${H - 6}" text-anchor="${i === 0 ? 'start' : i === 2 ? 'end' : 'middle'}">${i === 1 ? T('today') : fmt(t)}</text>`).join('')}
    <line class="pj-now" x1="${X(today)}" x2="${X(today)}" y1="${pt}" y2="${H - pb}"/>
    ${sch ? `<path class="pj-even" d="M${X(Date.parse(sch.start)).toFixed(1)} ${Y(0)} L${X(Date.parse(sch.end)).toFixed(1)} ${Y(1)}"/><line class="pj-end" x1="${X(Date.parse(sch.end))}" x2="${X(Date.parse(sch.end))}" y1="${pt}" y2="${H - pb}"/><text class="ot-ax" x="${X(Date.parse(sch.end)) + 5}" y="${H - pb - 6}">${T('end')} · ${fmt(Date.parse(sch.end))}</text>` : ''}
    <path class="ot-l" style="--c:var(--st-val)" d="${line('val')}"/><path class="ot-l" style="--c:var(--st-done)" d="${line('done')}"/>
    <path class="pj-l" style="--c:var(--st-val)" d="${ahead(pace.val, rv)}"/><path class="pj-l" style="--c:var(--st-done)" d="${ahead(pace.done, rd)}"/>
    ${rd && rd <= t1 ? `<circle class="ot-end" style="--c:var(--st-done)" cx="${X(rd)}" cy="${Y(1)}" r="4"/><text class="ot-lab" x="${X(rd) + 8}" y="${Y(1) + 4}">${fmt(rd)}</text>` : ''}
    </svg>`;
  return `<div class="ot pj">${head}<p class="faint ac-say">${say}</p><div class="pj-box">${svg}</div></div>`;
}
