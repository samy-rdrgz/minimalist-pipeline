/* ---------- The list ---------- */
function renderQuick() {
  if (S.ws === 'farm') {
    renderFarmQuick();
    return;
  }
  if (S.ws === 'todo') {
    renderTodoQuick();
    return;
  }
  if (S.ws === 'links') {
    $('#quick').innerHTML = `<span class="dim">${T('Who links what: assets → shots')}</span>`;
    return;
  }
  const pool = items.filter(i => i.kind === (S.ws === 'asset' ? 'asset' : 'shot'));
  if (LIVE && S.quick === 'mine') S.quick = null;
  const q = [];
  if (S.review && !LIVE) q.push(['mine', T('My review'), pool.filter(touched).length, glyph('val', 'you')]);
  q.push(
    ['rtk', T('Retakes'), pool.filter(i => openRtk(i)).length, glyph('done', 'rtk', 1)],
    ['notes', T('Notes'), pool.filter(i => openNotes(i)).length, ic('i-note')],
    ['val', T('To validate'), pool.filter(toValidate).length, glyph('done')]
  );
  const nm = S.more.size + (S.dept ? 1 : 0);
  // On a narrow screen the filters fold behind one button (the active ones counted on it).
  const on = (S.quick ? 1 : 0) + nm;
  $('#quick').classList.toggle('folded', S.ws !== 'synth' && S.qFold !== false);
  $('#quick').innerHTML =
    S.ws === 'synth'
      ? `<span class="dim">${T('What a cell says')}</span><span class="join">${[
          ['done', T('Done')],
          ['val', T('Validated')],
          ['rtk', T('Retakes')]
        ]
          .map(
            ([k, l]) => `<button class="btn" data-smode="${k}" aria-pressed="${S.smode === k}">${l}</button>`
          )
          .join(
            ''
          )}</span><span class="faint sx-hint" title="${T('Click a sequence: its files, in the list.')}">${T('Click a sequence: its files, in the list.')}</span><button class="btn tool" data-weights aria-expanded="${S.weights}">${ic('b-info')}${T("How it's counted")}</button><button class="btn tool" data-export title="${T('Sequences, shots, assets, retakes, to validate: a spreadsheet (.xlsx)')}">${ic('b-export')}${T('Export…')}</button>`
      : `<button class="btn qfold only-phone" data-qfold aria-expanded="${S.qFold === false}">${ic('b-filter')}${T('Filters')}${on ? ` <span class="n">${on}</span>` : ''}${ic(S.qFold === false ? 'b-downarrow_hlt' : 'b-rightarrow')}</button><span class="join">${q.map(([k, l, n, g]) => `<button class="btn" data-quick="${k}" aria-pressed="${S.quick === k}">${g.replace('class="g"', 'class="g" style="width:18px;height:18px"')}<span>${l}</span><span class="n">${n}</span></button>`).join('')}</span>
    <span class="anchor"><button class="btn ${nm ? '' : 'tool'}" data-menu="m-more" aria-haspopup="true" aria-expanded="false" ${nm ? 'aria-pressed="true"' : ''}>${ic('b-filter')}${T('Filters')}${nm ? ` <span class="n">${nm}</span>` : ''}${ic('b-downarrow_hlt')}</button>
    <div class="menu" id="m-more" hidden role="menu">
      <div class="menu-h">${T('Department')}</div>
      ${DEPTS[S.ws].map(d => `<button class="mi" role="menuitemradio" aria-checked="${S.dept === d}" data-dept="${d}"><span class="ck">${S.dept === d ? ic('b-checkmark') : ''}</span><span class="lbl">${LBL[d]}</span></button>`).join('')}
      <div class="msep"></div>
      ${[['me', T('Me'), T('assigned to {who}', { who: me() })], ...(LIVE ? [['farm', T('In the farm'), T('rendering, queued, failed')]] : []), ['tocheck', T('To check'), T('rendered, not checked yet')], ['unfinished', T('Not finished'), T('a department not done yet')], ['outdated', T('Render outdated'), T('rendered before the last stable')], ['tracked', T('Tracked only'), T('hides the files with no department')]].map(([k, l, h]) => `<button class="mi" role="menuitemcheckbox" aria-checked="${S.more.has(k)}" data-more="${k}"><span class="ck">${S.more.has(k) ? ic('b-checkmark') : ''}</span><span class="lbl">${l}</span><span class="k">${h}</span></button>`).join('')}
      ${nm ? '<div class="msep"></div><button class="mi" data-act="clear-more"><span class="ck"></span><span class="lbl">' + T('Clear all') + '</span></button>' : ''}
    </div></span>${colsMenu()}`;
}
/* The list's columns, shown or not: the thumbnails, each department, Progress (Farm). */
const shownDepts = kind => DEPTS[kind].filter(d => !S.hideCols.has(d));
/* Farm: a column of its own, picked in Columns shown ("+farm": hidden unless asked), or by Filters › In the farm. */
/* Renders: the file's job in the farm, a render to check, one outdated -- shown by the eye, or by the filters on them. */
const farmCol = () => S.hideCols.has('+farm') || ['farm', 'tocheck', 'outdated'].some(k => S.more.has(k));
function colsMenu() {
  const n = S.hideCols.size,
    mi = (k, l) =>
      `<button class="mi" role="menuitemcheckbox" aria-checked="${!S.hideCols.has(k)}" data-col="${esc(k)}"><span class="ck">${S.hideCols.has(k) ? '' : ic('b-checkmark')}</span><span class="lbl">${l}</span></button>`;
  return `<span class="anchor"><button class="btn icon ${n ? '' : 'tool'}" data-menu="m-cols" aria-haspopup="true" aria-expanded="false" ${n ? 'aria-pressed="true"' : ''} aria-label="${T('Columns shown')}" title="${T('Columns shown')}">${ic('b-hide_off')}</button>
    <div class="menu" id="m-cols" hidden role="menu"><div class="menu-h">${T('Columns shown')}</div>${mi('thumb', T('Thumbnails'))}<div class="msep"></div>${DEPTS[S.ws].map(d => mi(d, esc(LBL[d]))).join('')}<div class="msep"></div>${mi('prog', T('Progress'))}<button class="mi" role="menuitemcheckbox" aria-checked="${farmCol()}" data-col="+farm" title="${T('The farm, to check, outdated')}"><span class="ck">${farmCol() ? ic('b-checkmark') : ''}</span><span class="lbl">${T('Renders')}</span></button></div></span>`;
}
function renderList() {
  const L = $('#list');
  L.classList.toggle('graphmode', S.ws === 'links');
  if (S.ws === 'synth') {
    renderSynth();
    return;
  }
  if (S.ws === 'todo') {
    renderTodo();
    return;
  }
  if (S.ws === 'farm') {
    renderFarm();
    return;
  }
  if (S.ws === 'links') {
    renderGraph();
    return;
  }
  const dl = shownDepts(S.ws);
  L.style.setProperty('--nd', dl.length);
  L.classList.toggle('nothumb', S.hideCols.has('thumb'));
  L.classList.toggle('noprog', S.hideCols.has('prog'));
  L.classList.toggle('farmcol', farmCol());
  const vis = visible();
  if (!vis.length) {
    L.innerHTML =
      `<div class="empty">${T('No file matches the filters.')}<button class="btn" data-act="clear">${T('Clear the filters')}</button></div>` +
      otherHTML();
    return;
  }
  L.innerHTML =
    [...new Set(vis.map(groupOf))]
      .map(g => {
        const all = vis.filter(i => groupOf(i) === g),
          act = all.filter(i => !omitted(i) && i.done != null),
          hid = all.filter(omitted),
          filt = S.q || S.quick || S.more.size || S.dept,
          showH = S.showAside[g] || filt,
          its = showH ? all : all.filter(i => !omitted(i));
        const ad = act.length ? act.reduce((a, i) => a + i.done, 0) / act.length : null,
          av = act.length ? act.reduce((a, i) => a + valOf(i), 0) / act.length : null;
        return `<div class="grp ${S.closed.has(g) ? 'closed' : ''}" data-g="${g}">
      <div class="grp-h"><button class="ttl" data-fold="${g}" aria-expanded="${!S.closed.has(g)}">${ic('b-downarrow_hlt', 'i tri open')}${ic('b-rightarrow', 'i tri shut')}<b>${g}</b><span class="cnt">${S.ws === 'shot' ? T('{n} shot|{n} shots', { n: its.length }) : T('{n} file|{n} files', { n: its.length })}</span></button>
        ${S.ws === 'shot' ? `<button class="btn sm play" data-seq="${g}" title="${T('The last videos of {seq}, one after the other', { seq: g })}">${ic('b-play')}${T('Play the sequence')}</button>` : ''}${S.review ? `<button class="btn sm tool" data-plan="${g}" data-k="${S.ws}" title="${S.ws === 'shot' ? T('A new shot in {seq}, made when the review is imported', { seq: g }) : T('A new file {prefix}_…, made when the review is imported', { prefix: g })}">${ic('b-add')}${S.ws === 'shot' ? T('shot') : T('asset')}</button>` : ''}
        <span class="prog"><span class="bar" style="--p:${(ad || 0) * 100}%;--c:var(--st-done)" title="${T('Done')} ${pct(ad)}"><span class="bl">${T('Done')}</span><i></i><span>${pct(ad)}</span></span><span class="bar" style="--p:${(av || 0) * 100}%;--c:var(--st-val)" title="${T('Validated')} ${pct(av)}"><span class="bl">${T('Validated')}</span><i></i><span>${pct(av)}</span></span></span></div>
      <div class="rows"><div class="cols"><span class="c-th"></span><span>${T('File')}</span>${dl.map(d => `<span class="cd" title="${LBL[d]}">${LBL[d]}</span>`).join('')}<span class="c-prog">${T('Progress')}</span>${farmCol() ? `<span class="c-fm">${T('Renders')}</span>` : ''}</div>
      ${its.map(rowHTML).join('')}${S.planned.map((p, n) => (p.g === g && p.kind === S.ws ? plannedRow(p, n) : '')).join('')}${
        hid.length && !filt
          ? `<button class="aside-t" data-aside="${g}">${T('{n} set aside', { n: hid.length })} · ${hid
              .map(i => (omitted(i) === 'cancelled' ? T('cancelled') : T('on hold')))
              .filter((x, k, a) => a.indexOf(x) === k)
              .join(', ')} · ${S.showAside[g] ? T('hide') + ' ⌃' : T('show') + ' ⌄'}</button>`
          : ''
      }</div></div>`;
      })
      .join('') + otherHTML();
}
function plannedRow(p, n) {
  return `<div class="row planned"><span class="thumb"></span><span class="fname"><span class="n">${esc(p.name)}</span>${p.desc ? `<span class="d">${esc(p.desc)}</span>` : ''}<span class="m"><span class="tag you">${T('new · made at the import')}</span></span></span>
  <span class="depts">${shownDepts(p.kind).map(d => `<span class="cell ${p.deps.includes(d) ? '' : 'na'}">${glyph(p.deps.includes(d) ? 'todo' : 'na')}<span class="ab">${AB[d]}</span><span class="tx"><span class="l">${p.deps.includes(d) ? T('To do') : ''}</span></span></span>`).join('')}</span>
  <span class="bars"><button class="btn sm flat" data-unplan="${n}" title="${T('Take this new file out of the review')}">${ic('b-x')}${T('Remove')}</button></span></div>`;
}
function otherHTML() {
  if (!S.q) return '';
  const o = S.ws === 'shot' ? 'asset' : 'shot',
    n = items.filter(i => i.kind === o && (i.name + ' ' + i.desc).toLowerCase().includes(S.q)).length;
  return n
    ? `<button class="other-t" data-other="${o}">${o === 'shot' ? T('{n} result in Shots|{n} results in Shots', { n }) : T('{n} result in Assets|{n} results in Assets', { n })} ›</button>`
    : '';
}
function rowHTML(it) {
  const dl = shownDepts(it.kind),
    nn = openNotes(it),
    om = it.setAside !== undefined ? it.setAside : it.omit,
    fv = valOf(it);
  const tags = [];
  if (om && om.state)
    tags.push(
      `<span class="tag omit" title="${T('Set aside: out of the figures')}">${om.state === 'cancelled' ? T('Cancelled') : T('On hold')}${om.reason ? ' · ' + esc(om.reason) : ''}</span>`
    );
  if (nn) tags.push(`<span class="tag">${ic('i-note')}${nn}</span>`);
  if (it.toCheck && !farmCol())
    tags.push(
      `<span class="tag tochk" title="${T('Rendered, not checked by the team yet')}">${ic('b-hide_off')}${T('to check')}</span>`
    );
  if (it.outdated && !farmCol()) tags.push(`<span class="tag check">${ic('b-error')}${T('render outdated')}</span>`);
  if (it.farm && !farmCol())
    tags.push(
      `<span class="tag ${it.farm.state === 'failed' ? 'fail' : ''}" title="${T('In the farm: {what}', { what: esc(TS(it.farm.tip)) })}">${ic(it.farm.state === 'waiting' ? 'b-time' : 'b-file_movie')}farm ${esc(TS(it.farm.text))}${it.farm.department ? ' · ' + esc(LBL[it.farm.department] || it.farm.department) : ''}</span>`
    );
  if (touched(it)) tags.push(`<span class="tag you">${T('you')}</span>`);
  return `<div class="row ${S.sel === it.name ? 'sel' : ''} ${om && om.state ? 'omit' : ''} ${touched(it) ? 'mine' : ''}" data-n="${it.name}" tabindex="-1">
    <span class="thumb" ${it.thumb ? `data-zoom="${it.name}" title="${T('See it large')}"` : ''}>${it.thumb ? `<img src="${it.thumb}" alt="" loading="lazy" decoding="async">` : ''}</span>
    <span class="fname"><span class="n" title="${it.name}">${it.name}</span>${it.desc ? `<span class="d" title="${esc(it.desc)}">${esc(it.desc)}</span>` : ''}
      <span class="m"><span class="ver">${[it.wip, it.stable && 'stable ' + it.stable].filter(Boolean).join(' · ')}${it.shots && it.shots.length ? ' · ' + T('{n} shot|{n} shots', { n: it.shots.length }) : ''}</span>${tags.join('')}</span></span>
    <span class="depts">${dl.map(d => cellHTML(it, d)).join('')}</span>
    <span class="bars"><span class="bar bare" style="--p:${(it.done || 0) * 100}%;--c:var(--st-done)" title="${T('Done')} ${pct(it.done)}"><i></i><span>${pct(it.done)}</span></span><span class="bar bare" style="--p:${(fv || 0) * 100}%;--c:var(--st-val)" title="${T('Validated')} ${pct(fv)}"><i></i><span>${pct(fv)}</span></span></span>${farmCol() ? farmCell(it) : ''}
  </div>`;
}
/* The Farm column: a file's job -- its state, and while it
   renders its frames done ("rendering 41/72") as a bar. */
function farmCell(it) {
  const f = it.farm,
    out = [];
  if (f) {
    const m = String(f.text || '').match(/(\d+)\/(\d+)/),
      p = m ? +m[1] / +m[2] : null;
    out.push(
      `<span class="fj ${f.state === 'failed' ? 'bad' : ''}" title="${esc(TS(f.tip || f.text))}">${ic(f.state === 'waiting' ? 'b-time' : f.state === 'failed' ? 'b-error' : 'b-render_animation')}<span class="w">${esc(TS(f.text).replace(/\s*\d+\/\d+$/, ''))}${f.department ? ' · ' + esc(LBL[f.department] || f.department) : ''}</span></span>${p != null ? `<span class="bar bare" style="--p:${p * 100}%;--c:var(--st-done)"><i></i><span>${m[1]}/${m[2]}</span></span>` : ''}`
    );
  }
  if (it.toCheck)
    out.push(`<span class="fj chk" title="${T('Rendered, not checked by the team yet')}">${ic('b-hide_off')}<span class="w">${T('to check')}</span></span>`);
  if (it.outdated)
    out.push(`<span class="fj old" title="${T('rendered before the last stable')}">${ic('b-error')}<span class="w">${T('outdated')}</span></span>`);
  return `<span class="bars farmc">${out.join('') || '<span class="faint">–</span>'}</span>`;
}
/* A bar's figure sits on its colour from this share up. */
const IN = 0.62;
/* A department's share done, 0..1, as Blender counts it (lib/monitoring/status.py department_score()), from
   its state as the page shows it: done 1 (the "rtk" weight with an open retake), in progress, reworked
   their weights, not started 0. */
function deptScore(i, x) {
  const w = { wip: 33, rework: 67, rtk: 67, ...(M.weights || {}) },
    st = i.states[x];
  if (st === 'done') return rtkNotes(i, x).length ? w.rtk / 100 : 1;
  return (w[st] || 0) / 100;
}
/* A sequence's figures, one department or all (d null): Done, its files' mean -- one department's
   score, or the file's Done (the mean of its required departments, as the list shows it); Validated,
   the share of their required departments validated; their open RTKs. Null if none. The Breakdown's
   cells, its export too. */
function synthCell(its, d) {
  const r = its.filter(i => !omitted(i) && (d ? required(i).includes(d) : true));
  if (!r.length) return null;
  let n = 0,
    val = 0,
    rtk = 0,
    done = 0,
    nd = 0;
  r.forEach(i => {
    const f = d ? deptScore(i, d) : i.done;
    if (f != null) {
      done += f;
      nd++;
    }
    (d ? [d] : required(i)).forEach(x => {
      n++;
      if (i.ok[x] || i.mine[x] === 'val') val++;
      rtk += rtkNotes(i, x).length;
    });
  });
  return n ? { done: nd ? done / nd : 0, val: val / n, rtk, n: r.length } : null;
}
function renderSynth() {
  const L = $('#list'),
    mode = S.smode;
  const sumCell = synthCell;
  const field = c => {
    if (!c) return '<span class="sf na">–</span>';
    if (mode === 'rtk') {
      const p = Math.min(1, c.rtk / 6);
      return `<span class="sf ${p >= IN ? 'in' : ''}" style="--p:${p * 100}%;--c:var(--st-rtk)"><b class="v">${c.rtk ? c.rtk + ' RTK' : '–'}</b></span>`;
    }
    const p = mode === 'val' ? c.val : c.done;
    return `<span class="sf ${p >= IN ? 'in' : ''}" style="--p:${p * 100}%;--c:${mode === 'val' ? 'var(--st-val)' : 'var(--st-done)'}"><b class="v">${Math.round(p * 100)} %</b></span>`;
  };
  const table = (kind, title) => {
    const dl = DEPTS[kind],
      pool = items.filter(i => i.kind === kind),
      groups = [...new Set(pool.map(groupOf))];
    return `<div class="grp"><div class="grp-h"><b>${title}</b><span class="cnt">${pool.length}</span></div>
      <div class="stab" style="--nd:${dl.length}"><span class="sh"></span>${dl.map(d => `<span class="sh">${LBL[d]}</span>`).join('')}<span class="sh">${T('Total')}</span>
      ${groups
        .map(g => {
          const its = pool.filter(i => groupOf(i) === g);
          return `<button class="sn" data-sgo="${g}" data-skind="${kind}" title="${T('Open {name}', { name: g })}">${ic('b-rightarrow', 'i rot')}<span class="mono">${g}</span><span class="faint">${its.length}</span></button>${dl.map(d => field(sumCell(its, d))).join('')}${field(sumCell(its, null))}`;
        })
        .join('')}</div></div>`;
  };
  // The figure in black: on the bar's colour when it reaches it, else on a small white pill (a small share).
  const bar = (p, c, l) =>
    `<span class="sf ${p >= IN ? 'in' : ''}" style="--p:${p * 100}%;--c:${c}"><span class="lab ${p >= 0.45 ? 'on' : ''}">${l}</span><b class="v">${pct(p)}</b></span>`;
  const kp = (t, p, v) =>
    `<div class="kpi"><span class="t">${t}</span>${bar(p, 'var(--st-done)', T('Done'))}${bar(v, 'var(--st-val)', T('Validated'))}</div>`;
  L.innerHTML = `<div class="kpis">${kp(T('Shots'), M.progress.shot, M.validation.shot)}${kp(T('Assets'), M.progress.asset, M.validation.asset)}
    <div class="kpi"><span class="t">${T('Open retakes')}</span><span class="big">${items.reduce((a, i) => a + openRtk(i), 0)}</span><span class="faint">${T('on {n} file|on {n} files', { n: items.filter(openRtk).length })}</span></div>
    ${M.schedule ? `<div class="kpi"><span class="t">${T('Schedule · day {d} / {total}', { d: M.schedule.elapsed_days, total: M.schedule.total_days })}</span><span class="sf sch ${M.progress.shot >= IN ? 'in' : ''}" style="--p:${M.progress.shot * 100}%;--c:var(--st-done);--e:${M.schedule.expected * 100}%" title="${T('The line: where the shots should be today')}"><span class="lab ${M.progress.shot >= 0.45 ? 'on' : ''}">${T('Shots done')}</span><b class="v">${pct(M.progress.shot)}</b><i class="mk2"></i></span><span class="faint">${T('expected {pct}', { pct: pct(M.schedule.expected) })} · ${M.progress.shot < M.schedule.expected ? '<span class="bad">' + T('{n} points behind', { n: Math.round((M.schedule.expected - M.progress.shot) * 100) }) + '</span>' : T('on time')}</span></div>` : ''}
    <div class="kpi"><span class="t">${T('Set aside')}</span><span class="big">${items.filter(omitted).length}</span><span class="faint">${T('on hold or cancelled, out of the figures')}</span></div></div>
  ${S.weights ? `<p class="weights">${T("A department counts 0 % not started, {wip} % in progress, {rework} % reworked, {rtk} % done with an open retake, 100 % done. A file is the mean of its required departments, a sequence the mean of its files. Files set aside don't count. Validated is counted apart: by the role {role}, on the stable shown.", { wip: (M.weights || {}).wip ?? 33, rework: (M.weights || {}).rework ?? 67, rtk: (M.weights || {}).rtk ?? 67, role: esc(M.role) })}</p>` : ''}
  ${table('shot', T('Shots'))}${table('asset', T('Assets'))}${overTime()}${projection()}${activity()}`;
}
/* Over time: one point a day (lib/monitoring/progress_log.py), Done and Validated of the shots
   or the assets, all or one department; today's from the page's own figures when not logged yet. */
function otPoints() {
  const o = S.ot,
    key = o.kind === 'shot' ? 'shots' : 'assets';
  const pts = Object.entries(M.history || {})
    .map(([day, p]) => {
      const k = (p || {})[key] || {},
        x = o.dept ? (k.departments || {})[o.dept] || {} : k;
      return { day, done: x.done ?? null, val: x.validated ?? null };
    })
    .filter(p => p.done != null || p.val != null);
  const today = new Date().toISOString().slice(0, 10);
  if (!o.dept && !pts.some(p => p.day === today) && M.progress[o.kind] != null)
    pts.push({ day: today, done: M.progress[o.kind], val: M.validation[o.kind] ?? null, now: true });
  return pts.sort((a, b) => (a.day < b.day ? -1 : 1));
}
function overTime() {
  const o = S.ot,
    pts = otPoints(),
    W = 720,
    H = 200,
    pl = 40,
    pr = 92,
    pt = 12,
    pb = 26;
  const deps = DEPTS[o.kind] || [];
  const head = `<div class="ot-h"><b>${T('Over time')}</b><span class="join">${['shot', 'asset'].map(k => `<button class="btn sm" data-otk="${k}" aria-pressed="${o.kind === k}">${k === 'shot' ? T('Shots') : T('Assets')}</button>`).join('')}</span>
    <span class="anchor"><button class="enum" data-menu="m-otd" aria-haspopup="true" aria-expanded="false"><span class="lb">${o.dept ? esc(LBL[o.dept]) : T('All departments')}</span>${ic('b-downarrow_hlt')}</button><div class="menu" id="m-otd" hidden role="menu">${['', ...deps].map(d => `<button class="mi" data-otd="${esc(d)}"><span class="ck">${d === o.dept ? ic('b-checkmark') : ''}</span><span class="lbl">${d ? esc(LBL[d]) : T('All departments')}</span></button>`).join('')}</div></span>
    <button class="btn flat icon live-only" data-otreload aria-label="${T('Read the project again')}" title="${T("Read the project again: today's point brought up to date")}">${ic('b-file_refresh')}</button>
    <span class="ot-lg"><i style="--c:var(--st-done)"></i>${T('Done')}<i style="--c:var(--st-val)"></i>${T('Validated')}</span></div>`;
  if (pts.length < 2)
    return `<div class="ot">${head}<p class="faint ot-empty">${T('One point a day, from the snapshots and the live page: the curve starts with the second day.')}</p></div>`;
  const t0 = Date.parse(pts[0].day),
    t1 = Date.parse(pts[pts.length - 1].day),
    X = d => pl + ((Date.parse(d) - t0) / (t1 - t0 || 1)) * (W - pl - pr),
    Y = v => pt + (1 - v) * (H - pt - pb);
  const line = k =>
    pts
      .filter(p => p[k] != null)
      .map((p, i) => (i ? 'L' : 'M') + X(p.day).toFixed(1) + ' ' + Y(p[k]).toFixed(1))
      .join(' ');
  const last = k => [...pts].reverse().find(p => p[k] != null);
  const fmt = d => new Date(d + 'T12:00:00').toLocaleDateString(DTL(), { day: 'numeric', month: 'short' });
  const ticks = [0, Math.floor((pts.length - 1) / 2), pts.length - 1].filter((v, i, a) => a.indexOf(v) === i);
  // The two end labels never on each other: pushed apart when closer than a line.
  const ld = last('done'),
    lv = last('val');
  let yd = ld ? Y(ld.done) : 0,
    yv = lv ? Y(lv.val) : 0;
  if (ld && lv && Math.abs(yd - yv) < 14) {
    const m = (yd + yv) / 2,
      up = yd <= yv ? -7 : 7;
    yd = m + up;
    yv = m - up;
  }
  const svg = `<svg class="ot-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${T('Over time')}">
    ${[0, 0.5, 1].map(v => `<line class="ot-grid" x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ot-ax" x="${pl - 6}" y="${Y(v) + 4}" text-anchor="end">${v * 100} %</text>`).join('')}
    ${ticks.map(i => `<text class="ot-ax" x="${X(pts[i].day)}" y="${H - 6}" text-anchor="${i === 0 ? 'start' : i === pts.length - 1 ? 'end' : 'middle'}">${fmt(pts[i].day)}</text>`).join('')}
    <path class="ot-l" style="--c:var(--st-val)" d="${line('val')}"/><path class="ot-l" style="--c:var(--st-done)" d="${line('done')}"/>
    ${ld ? `<circle class="ot-end" style="--c:var(--st-done)" cx="${X(ld.day)}" cy="${Y(ld.done)}" r="4"/><text class="ot-lab" x="${X(ld.day) + 10}" y="${yd + 4}">${T('Done')} ${pct(ld.done)}</text>` : ''}
    ${lv ? `<circle class="ot-end" style="--c:var(--st-val)" cx="${X(lv.day)}" cy="${Y(lv.val)}" r="4"/><text class="ot-lab" x="${X(lv.day) + 10}" y="${yv + 4}">${T('Validated')} ${pct(lv.val)}</text>` : ''}
    <g class="ot-hv" hidden><line class="ot-x" y1="${pt}" y2="${H - pb}"/><circle class="ot-d" style="--c:var(--st-done)" r="4"/><circle class="ot-v" style="--c:var(--st-val)" r="4"/></g>
    <rect class="ot-hit" x="${pl}" y="0" width="${W - pl - pr}" height="${H}" fill="transparent"/></svg>`;
  OT.pts = pts;
  OT.geo = { X, Y, W, pl, pr };
  return `<div class="ot">${head}<div class="ot-box">${svg}<div class="ot-tip" hidden></div></div></div>`;
}
const OT = {};
/* The hover: the nearest day's two figures, a line through them. */
function otHover(e) {
  const box = e.target.closest('.ot-box');
  if (!box || !OT.pts) return;
  const svg = box.querySelector('svg'),
    r = svg.getBoundingClientRect(),
    g = OT.geo,
    x = ((e.clientX - r.left) / r.width) * g.W;
  let best = OT.pts[0];
  OT.pts.forEach(p => {
    if (Math.abs(g.X(p.day) - x) < Math.abs(g.X(best.day) - x)) best = p;
  });
  const hv = svg.querySelector('.ot-hv'),
    tip = box.querySelector('.ot-tip'),
    bx = g.X(best.day);
  hv.hidden = false;
  hv.querySelector('.ot-x').setAttribute('x1', bx);
  hv.querySelector('.ot-x').setAttribute('x2', bx);
  [
    ['.ot-d', best.done],
    ['.ot-v', best.val]
  ].forEach(([c, v]) => {
    const el = hv.querySelector(c);
    el.style.display = v == null ? 'none' : '';
    if (v != null) {
      el.setAttribute('cx', bx);
      el.setAttribute('cy', g.Y(v));
    }
  });
  tip.hidden = false;
  tip.innerHTML = `<b>${new Date(best.day + 'T12:00:00').toLocaleDateString(DTL(), { weekday: 'short', day: 'numeric', month: 'short' })}${best.now ? ' · ' + T('now') : ''}</b><span><i style="--c:var(--st-done)"></i>${T('Done')} <b>${pct(best.done)}</b></span><span><i style="--c:var(--st-val)"></i>${T('Validated')} <b>${pct(best.val)}</b></span>`;
  const left = (bx / g.W) * r.width;
  tip.style.left = Math.min(Math.max(left + 12, 0), r.width - tip.offsetWidth) + 'px';
}
function otLeave(e) {
  const box = e.target.closest('.ot-box');
  if (!box) return;
  box.querySelector('.ot-hv').hidden = true;
  box.querySelector('.ot-tip').hidden = true;
}
