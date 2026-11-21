/* ---------- Phone view ----------
   Touch AND narrow (< 900 px wide, or < 500 px high: a phone held wide; a tablet held wide stays desktop). Two uses only:
   · Review (snapshot and live): a shot at a time, two versions compared at the same frame,
     validate, retake, assign, add a department, write a note at the frame.
   · To do: what isn't validated yet, file by file (desktop/21-todo.js), Copy.
   · Farm (live only): the farm's state, the jobs and their %, retry, render a shot.
   The rest (links, breakdown, outliner, file settings) isn't here: the desktop version.
   Reads the same state S, the same selectors (info, versOf, marks…) and calls the same actions A. */
const mSib = () =>
  items.filter(
    i =>
      i.kind === S.m.kind &&
      !omitted(i) &&
      (!S.m.filter ||
        (S.m.filter === 'val' ? toValidate(i) : S.m.filter === 'rtk' ? openRtk(i) > 0 : openNotes(i) > 0))
  );
const mF = { '': T('Everything'), val: T('To validate'), rtk: T('Retakes'), note: T('Notes') };
const mShort = it => (it.kind === 'shot' ? it.name.replace(it.group + '_', '') : it.name);
const mGl = it =>
  DEPTS[it.kind]
    .filter(d => required(it).includes(d))
    .map(d => {
      const x = info(it, d);
      return glyph(x.base, x.corner, x.cnt, x.note);
    })
    .join('');

function mRender() {
  const R = $('#mob');
  if (!LIVE && S.m.tab === 'farm') S.m.tab = 'review';
  const ta = $('#m-ta'),
    keep = ta ? ta.value : '',
    foc = document.activeElement === ta,
    top = $('#m-body')?.scrollTop || 0;
  const n2 = items.filter(touched).length + S.planned.length,
    nn = NEWS.length - newsSeen;
  R.innerHTML = `<header class="m-top"><span class="m-brand"><b>${esc(M.project)}</b><small>${LIVE ? 'live' : T('snapshot of {date}', { date: fmtD(M.snapshot) })}${S.review ? ' · ' + esc(S.review.name) + ' · ' + S.review.role : ''}</small></span><span class="sp"></span>
      ${LIVE ? `<button class="m-ib" data-msheet="news" aria-label="${T("What's new")}">${ic('i-bell')}${nn ? `<span class="cnt">${nn}</span>` : ''}</button>` : ''}
      ${S.review && LIVE ? `<span class="rv-sync" data-state="${LV.say}">${SAY[LV.say]()}</span>` : ''}${S.review && !LIVE ? `<button class="btn primary" data-msheet="send">${ic('b-export')}${T('Send')}<span class="n">${n2}</span></button>` : ''}
      <button class="m-ib" data-msheet="search" aria-label="${T('Search everything')}">${ic('b-viewzoom')}</button>
      <button class="m-ib" data-msheet="menu" aria-label="Menu">${ic('b-preferences')}</button></header>
    <main class="m-body" id="m-body">${S.m.tab === 'farm' ? mFarm() : S.m.tab === 'todo' ? mTodo() : mReview()}</main>
    ${S.m.tab === 'review' ? mComposer() : ''}
    <nav class="m-nav" role="tablist"><button role="tab" data-mtab="review" aria-selected="${S.m.tab === 'review'}">${ic('b-file_movie')}<span>${T('Review')}</span></button>
      <button role="tab" data-mtab="todo" aria-selected="${S.m.tab === 'todo'}">${ic('b-checkmark')}<span>${T('To do')}</span></button>
      ${LIVE ? `<button role="tab" data-mtab="farm" aria-selected="${S.m.tab === 'farm'}">${ic('b-render_animation')}<span>Farm</span>${F.jobs.some(j => !j.archived && j.state === 'failed') ? '<span class="dot bad"></span>' : ''}</button>` : ''}</nav>
    ${S.m.sheet ? mSheet() : ''}`;
  const nb = $('#m-body');
  if (nb) nb.scrollTop = top;
  const t2 = $('#m-ta');
  if (t2) {
    t2.value = keep;
    if (foc) t2.focus();
  }
}

/* ----- To do: the files not validated yet, a tap opens one in Review ----- */
function mTodo() {
  const rows = todoFiles(S.td.kind);
  return `<span class="join full">${[
    ['shot', T('Shots')],
    ['asset', T('Assets')]
  ]
    .map(
      ([k, l]) =>
        `<button class="btn" data-tdk="${k}" aria-pressed="${S.td.kind === k}">${l}<span class="n">${todoFiles(k).length}</span></button>`
    )
    .join('')}</span>
    <span class="join full">${TD_ST()
      .map(([k, l]) => `<button class="btn" data-tdst="${k}" aria-pressed="${tdSt() === k}">${l}</button>`)
      .join('')}</span>
    <button class="btn m-wide" data-tdcopy>${ic('b-file')}${T('Copy')}</button>
    ${
      rows.length
        ? [...new Set(rows.map(r => groupOf(r.it)))]
            .map(g => {
              const its = rows.filter(r => groupOf(r.it) === g);
              return `<section class="m-sec"><div class="m-sec-h">${esc(g)}<span class="n">${its.length}</span></div>${its
                .map(
                  ({ it, ds }) =>
                    `<button class="m-job m-td" data-mgo="${esc(it.name)}"><span class="gl">${ds
                      .map(d => {
                        const x = info(it, d);
                        return glyph(x.base, x.corner, x.cnt);
                      })
                      .join(
                        ''
                      )}</span><span class="jt"><b>${esc(mShort(it))}</b><small>${esc(ds.map(d => LBL[d] + (todoWhy(it, d) ? ' (' + todoWhy(it, d) + ')' : '')).join(', '))}</small></span></button>`
                )
                .join('')}</section>`;
            })
            .join('')
        : `<div class="empty">${T('Everything is validated.')}</div>`
    }`;
}

/* ----- Review: one shot ----- */
function mReview() {
  const it = cur();
  if (!it) return '<div class="empty">' + T('No file.') + '</div>';
  const sib = mSib(),
    k = sib.findIndex(i => i.name === it.name),
    { V, a, b, i } = mVer(it),
    v = V[i],
    rv = S.review;
  const mk = marks(it);
  const mkH = mk
    .map(f => {
      const x = ((fIdx(f.a) - 1) / (NF - 1)) * 100;
      return (
        (f.b ? `<span class="rng" style="left:${x}%;width:${((f.b - f.a) / (NF - 1)) * 100}%"></span>` : '') +
        `<button class="mk ${f.rtk ? '' : 'n'}" style="left:${x}%" data-goto="${f.a}" aria-label="${f.rtk ? 'Retake' : T('Note')} f${f.a}"></button>`
      );
    })
    .join('');
  const rng =
    S.rangeStart != null
      ? `<span class="rng sel" id="rng-sel" style="left:${((Math.min(S.rangeStart, S.frame) - 1) / (NF - 1)) * 100}%;width:${(Math.abs(S.frame - S.rangeStart) / (NF - 1)) * 100}%"></span>`
      : '';
  const req = DEPTS[it.kind].filter(d => required(it).includes(d));
  const notes = [...it.myNotes.map(n => ({ ...n, mine: true })), ...it.notes.filter(n => !n.done)];
  return `<div class="m-shotnav"><button class="m-ib" data-mstep="-1" aria-label="${T('Previous shot')}" ${k <= 0 ? 'disabled' : ''}>${ic('b-tria_left')}</button>
      <button class="m-pick" data-msheet="pick" aria-label="${T('Choose the shot')}"><span class="t"><b>${esc(mShort(it))}</b><small>${esc(groupOf(it))} · ${k < 0 ? 'hors filtre' : k + 1 + ' / ' + sib.length}${S.m.filter ? ' · ' + mF[S.m.filter] : ''}</small></span><span class="gls">${mGl(it)}</span>${ic('b-tria_down')}</button>
      <button class="m-ib" data-mstep="1" aria-label="${T('Next shot')}" ${k < 0 || k >= sib.length - 1 ? 'disabled' : ''}>${ic('b-tria_right')}</button></div>
    ${it.desc || it.descEdit ? `<p class="m-desc">${esc(it.descEdit ?? it.desc)}</p>` : ''}
    <div class="m-player ${S.m.side === 'B' && V.length > 1 ? 'is-b' : ''}" id="m-player">${it.thumb ? `<img src="${it.thumb}" alt="${T('Picture of {name}', { name: esc(it.name) })}" draggable="false">` : `<span class="noimg">${T('Not rendered yet')}</span>`}
      <span class="m-hud">${V.length > 1 ? `<b class="ab">${S.m.side}</b>` : ''}${v ? esc(verLab(v)) : T('no version')}</span><span class="m-fr">f <span data-f>${fNo(S.frame)}</span></span></div>
    <div class="scrub big ${rendered(it) ? '' : 'off'}" data-scrub role="slider" tabindex="0" aria-label="${T(T('Frame'))}" aria-valuemin="1" aria-valuemax="${NF}" aria-valuenow="${S.frame}">${mkH}${rng}<span class="ph" style="left:${((S.frame - 1) / (NF - 1)) * 100}%"></span></div>
    <div class="m-tp"><button class="btn icon" data-tp="fprev" ${pOff(it)} aria-label="${T('Previous frame')}">${ic('b-frame_prev')}</button><button class="btn icon play" data-tp="play" ${pOff(it)} aria-label="${T('Play')}">${ic(S.playing ? 'b-pause' : 'b-play')}</button><button class="btn icon" data-tp="fnext" ${pOff(it)} aria-label="${T('Next frame')}">${ic('b-frame_next')}</button><button class="btn icon" data-mloop aria-pressed="${S.m.loop}" aria-label="${T('Loop this shot')}" title="${S.m.loop ? T('Plays this shot again and again') : T("Plays the path's shots one after the other")}">${ic('b-file_refresh')}</button>
      ${V.length > 1 ? `<span class="join m-ab" role="group" aria-label="${T('Version shown')}"><button class="btn" data-mside="A" aria-pressed="${S.m.side === 'A'}">A</button><button class="btn" data-mside="B" aria-pressed="${S.m.side === 'B'}">B</button></span>` : ''}</div>
    ${
      V.length > 1
        ? `<div class="m-vers"><button class="m-vchip ${S.m.side === 'A' ? 'on' : ''}" data-msheet="verA"><b>A</b><span class="lb">${esc(verLab(V[a]))}</span>${ic('b-tria_down')}</button><button class="m-vchip ${S.m.side === 'B' ? 'on' : ''}" data-msheet="verB"><b>B</b><span class="lb">${esc(verLab(V[b]))}</span>${ic('b-tria_down')}</button></div>
      `
        : ''
    }<p class="m-hint">${S.m.loop ? T('Loop: this shot plays again.') : T("Play: the path's shots one after the other.")}${V.length > 1 ? ' ' + T('A / B: same frame, another version.') : ''} ${T('Swipe the picture: next shot.')}</p>
    <section class="m-sec"><div class="m-sec-h">${T('Departments')}<span class="sp"></span>${rv ? `<button class="btn tool" data-msheet="depts">${ic('b-add')}${T('Department')}</button>` : ''}</div>
      ${rv && rv.role !== TEAM && req.some(d => canVal(it, d) && !it.rtk[d] && !it.mine[d]) ? `<button class="btn ok m-wide" data-mvalall>${ic('b-checkmark')}${T('Validate all the done')}</button>` : ''}
      ${req.map(d => mDept(it, d)).join('') || '<p class="m-hint">' + T('No department required.') + '</p>'}</section>
    <section class="m-sec"><div class="m-sec-h">${T(T('Notes'))}<span class="n">${notes.length}</span></div>
      ${
        notes
          .map(
            n => `<div class="m-note">${n.frames ? `<button class="ft ${/-/.test(n.frames) ? 'rg' : n.type === 'rtk' ? '' : 'nt'}" data-goto="${(String(n.frames).match(/\d+/) || [1])[0]}">${esc(n.frames)}</button>` : `<span class="ft ${n.type === 'rtk' ? '' : 'nt'}">${n.type === 'rtk' ? 'RTK' : 'note'}</span>`}
        <span class="tx">${esc(n.text || T('(no text)'))}<small>${esc(((n.deps || []).map(d => LBL[d] || d).join(', ') || T('no department')) + ' · ' + (n.mine ? T('you, not sent yet') : n.author || ''))}</small></span>
        ${n.mine ? `<button class="m-ib" data-unnote="${n.at}" aria-label="${T('Remove')}">${ic('b-loop_back')}</button>` : ''}</div>`
          )
          .join('') || '<p class="m-hint">' + T('No open note.') + '</p>'
      }</section>`;
}
function mDept(it, d) {
  const x = info(it, d),
    m = it.mine[d],
    a = assignOf(it, d),
    rv = S.review,
    f = it.flags[d] || {};
  return `<div class="m-dept ${m ? 'mine' : ''}"><div class="m-dh">${glyph(x.base, x.corner, x.cnt, x.note)}<span class="nm"><b>${LBL[d]}</b><span class="s ${x.tone}">${esc(x.l)}${x.s ? ' · ' + esc(x.s) : ''}</span></span>
      ${rv ? `<button class="m-as ${a.length ? '' : 'none'} ${it.assign && d in it.assign ? 'chg' : ''}" data-msheet="as:${d}">${ic('b-user')}<span>${a.length ? esc(a.join(', ')) : T('Assign')}</span></button>` : a.length ? `<span class="m-as ro">${ic('b-user')}<span>${esc(a.join(', '))}</span></span>` : ''}</div>
    ${
      rv
        ? `<div class="m-da"><button class="btn ok" data-mval="${d}" aria-pressed="${m === 'val'}" ${rv.role === TEAM || !canVal(it, d) ? 'disabled' : ''}>${ic('b-checkmark')}${m === 'val' ? T('Validated') : T('Validate')}</button>
      <button class="btn alert" data-mrtk="${d}" aria-pressed="${m === 'rtk'}">${ic('b-x')}${m === 'rtk' ? T('Retake · you') : 'Retake'}</button>
      ${d in it.marked || canMark(it, d) ? `<button class="btn ${d in it.marked ? 'ok' : 'tool'} m-span" data-mark="${d}" aria-pressed="${d in it.marked}">${ic('b-checkmark')}${T('Mark done')} <small>${esc(it.stable || '')}</small></button>` : ''}
      ${f.to_redo ? `<button class="btn ${it.still[d] ? 'ok' : 'tool'} m-span" data-still="${d}" aria-pressed="${!!it.still[d]}">${ic('b-checkmark')}${T('Still done')} <small>${esc(f.to_redo)}</small></button>` : ''}</div>`
        : ''
    }</div>`;
}
function mComposer() {
  if (!S.review)
    return `<div class="m-comp"><button class="btn primary m-wide" data-msheet="start">${ic('b-greasepencil')}${T('Start the review')}</button></div>`;
  const it = cur(),
    req = DEPTS[it.kind].filter(d => required(it).includes(d));
  if (S.m.cdept && !req.includes(S.m.cdept)) S.m.cdept = null;
  return `<div class="m-comp"><div class="m-cr"><span class="join m-ct"><button class="btn icon" data-mct="rtk" aria-pressed="${S.m.ctype === 'rtk'}" aria-label="Retake" title="Retake">${ic('b-x')}</button><button class="btn icon" data-mct="note" aria-pressed="${S.m.ctype === 'note'}" aria-label="${T('Remark')}" title="${T('Remark')}">${ic('i-note')}</button></span>
      <button class="m-chip" data-msheet="cdept"><span>${S.m.cdept ? LBL[S.m.cdept] : T('No dept.')}</span>${ic('b-tria_down')}</button>
      <button class="m-chip ${S.rangeStart != null ? 'on' : ''}" data-tp="in" ${pOff(it)} aria-pressed="${S.rangeStart != null}" title="${T('A range: its start here')}">${S.rangeStart != null ? 'f' + S.rangeStart + ' →' : '⇤'} f<span data-f>${fNo(S.frame)}</span></button></div>
    <div class="m-cr"><label class="field ta"><textarea id="m-ta" rows="1" placeholder="${S.m.ctype === 'rtk' ? T('Retake at this frame…') : T('Remark at this frame…')}" aria-label="${T("The note's text")}"></textarea></label>
      <button class="btn primary icon m-send" data-msend aria-label="${T('Add to my review')}">${ic('b-export')}</button></div></div>`;
}

/* ----- Farm: watch, retry, render ----- */
function mFarm() {
  const W = F.workers,
    act = W.filter(w => w.status !== 'silent'),
    busy = W.filter(w => w.file && w.status !== 'silent');
  const st =
      { dead: T('stopped'), running: T('running'), stale: T('stuck'), ok: T('running') }[F.status] ||
      F.status,
    bad = F.status === 'dead' || F.status === 'stale';
  const js = F.jobs.filter(j => !j.archived);
  return `<div class="m-card ${bad ? 'bad' : ''}">${jst(bad ? 'failed' : 'running')}<span class="t"><b>${T('Monitor {state}', { state: st })}</b><small>${T('{n} machine online|{n} machines online', { n: act.length })} · ${T('{n} rendering', { n: busy.length })}${W.length - act.length ? ' · ' + T('{n} silent', { n: W.length - act.length }) : ''}</small>
      ${F.left ? `<small>${esc(F.left)}</small>` : ''}</span></div>
    <span class="live-only">${monitorBtn('m-wide')}</span>
    <button class="btn primary m-wide" data-msheet="render">${ic('b-render_animation')}${T('Render a shot…')}</button>
    ${JS.map(([s, l]) => {
      const g = js.filter(j => j.state === s);
      if (!g.length) return '';
      return `<section class="m-sec"><div class="m-sec-h">${l}<span class="n">${g.length}</span></div>${(s ===
      'finished'
        ? g.slice(0, 5)
        : g
      )
        .map(j => {
          const p = j.total ? j.done / j.total : 0;
          return `<button class="m-job" data-msheet="job:${j.id}">${jst(j.state)}<span class="jt"><b>${esc(j.file)}</b><small>${esc([j.text, j.user].filter(Boolean).join(' · '))}</small>
          ${j.total ? `<span class="jbar"><i style="--p:${p * 100}%"></i></span>` : ''}</span><span class="pc">${j.total ? Math.round(p * 100) + ' %' : ''}</span></button>`;
        })
        .join('')}
        ${s === 'finished' && g.length > 5 ? `<p class="m-hint">${T('and {n} more: the desktop version.', { n: g.length - 5 })}</p>` : ''}</section>`;
    }).join('')}
    <section class="m-sec"><div class="m-sec-h">${T('Machines')}<span class="n">${W.length}</span></div>${W.map(w => `<div class="m-job ro">${jst(w.status === 'silent' ? 'waiting' : w.file ? 'running' : 'finished')}<span class="jt"><b>${esc(w.name)}</b><small>${w.status === 'silent' ? T('silent since {date}', { date: fmtD(w.since) }) : esc([w.status, w.file].filter(Boolean).join(' · '))}</small></span></div>`).join('')}</section>`;
}

/* ----- Bottom sheets: one component for every choice ----- */
function mSheet() {
  const k = S.m.sheet,
    it = cur();
  let t = '',
    h = '',
    foot = '';
  const opt = (attr, on, lbl, sub = '', extra = '') =>
    `<button class="m-opt" ${attr} role="menuitemradio" aria-checked="${on}"><span class="ck">${on ? ic('b-checkmark') : ''}</span><span class="lbl">${lbl}${sub ? `<small>${sub}</small>` : ''}</span>${extra}</button>`;
  if (k === 'pick') {
    t = T('Choose a file');
    const sib = mSib(),
      gs = [...new Set(sib.map(groupOf))];
    const cnt = f =>
      items.filter(
        i =>
          i.kind === S.m.kind &&
          !omitted(i) &&
          (!f || (f === 'val' ? toValidate(i) : f === 'rtk' ? openRtk(i) > 0 : openNotes(i) > 0))
      ).length;
    h = `<span class="join full">${[
      ['shot', T('Shots')],
      ['asset', 'Assets']
    ]
      .map(([x, l]) => `<button class="btn" data-mkind="${x}" aria-pressed="${S.m.kind === x}">${l}</button>`)
      .join('')}</span>
      <div class="m-filters">${Object.entries(mF)
        .map(
          ([x, l]) =>
            `<button class="m-chip ${S.m.filter === x ? 'on' : ''}" data-mfilter="${x}">${l}<span class="n">${cnt(x)}</span></button>`
        )
        .join('')}</div>
      ${
        gs
          .map(
            g =>
              `<div class="m-grp">${esc(g)}</div>${sib
                .filter(i => groupOf(i) === g)
                .map(i =>
                  opt(
                    `data-mgo="${i.name}"`,
                    i.name === S.sel,
                    `<span class="mono">${esc(mShort(i))}</span>`,
                    esc(i.descEdit ?? i.desc ?? ''),
                    `<span class="gls">${mGl(i)}</span>`
                  )
                )
                .join('')}`
          )
          .join('') || '<p class="m-hint">' + T('Nothing matches this filter.') + '</p>'
      }`;
  }
  if (k === 'verA' || k === 'verB') {
    const { V, a, b } = mVer(it),
      cur2 = k === 'verA' ? a : b;
    t = 'Version ' + k.slice(3);
    h = V.map((x, n) =>
      opt(`data-mver="${n}"`, n === cur2, esc(verLab(x)), n === 0 ? T('the latest') : '')
    ).join('');
  }
  if (k && k.startsWith('as:')) {
    const d = k.slice(3),
      a = assignOf(it, d);
    t = T('{dept}: assigned to', { dept: LBL[d] });
    h =
      M.team
        .map(p =>
          opt(
            `data-massign="${d}" data-p="${esc(p)}"`,
            a.includes(p),
            esc(p),
            p === M.live.user ? T('me') : ''
          )
        )
        .join('') + opt(`data-massign="${d}" data-p=""`, !a.length, T('Nobody'));
    foot = `<button class="btn m-wide" data-mclose>${T('Done')}</button>`;
  }
  if (k === 'depts') {
    t = T('Departments of {name}', { name: mShort(it) });
    h =
      `<p class="m-hint">${T("A required department counts in the shot's figures. Sent with your review.")}</p>` +
      DEPTS[it.kind]
        .map(d => {
          const on = required(it).includes(d);
          return `<button class="m-opt sw" data-mreq="${d}" role="switch" aria-checked="${on}"><span class="lbl">${LBL[d]}<small>${on ? T('required') : T('not required')}${it.req && it.req[d] !== d in it.states ? ' · ' + T('you') : ''}</small></span><span class="tg"></span></button>`;
        })
        .join('');
    foot = `<button class="btn m-wide" data-mclose>${T('Done')}</button>`;
  }
  if (k === 'cdept') {
    t = T('The note is on');
    const req = DEPTS[it.kind].filter(d => required(it).includes(d));
    h =
      req.map(d => opt(`data-mcd="${d}"`, S.m.cdept === d, LBL[d])).join('') +
      opt('data-mcd=""', !S.m.cdept, T('No department'), T('the whole shot'));
  }
  if (k === 'start') {
    t = T('Start the review');
    h = `<label class="field"><input id="m-name" value="${esc(M.live.user || '')}" placeholder="${T('Your name')}" aria-label="${T('Your name')}" autocomplete="name"></label>
      <span class="join full">${[...M.roles, TEAM].map(r => `<button class="btn" data-mrole="${r}" aria-pressed="${r === (S.m.role || role0())}">${r}</button>`).join('')}</span>
      <p class="m-hint">${esc(roleHelp(S.m.role || role0()))}</p>
      <div class="m-sec-h">${T('Path')}</div>${Object.entries(mF)
        .map(([x, l]) =>
          opt(`data-mfilter="${x}" data-keep`, S.m.filter === x, l, x === '' ? T('every shot, in order') : '')
        )
        .join('')}`;
    foot = `<button class="btn primary m-wide" data-mstart>${ic('b-greasepencil')}${T('Start')}</button>`;
  }
  if (k === 'send') {
    t = T('Send the review');
    const ch = A.changes();
    h = `<p class="m-hint">${esc(S.review.name)} · ${S.review.role} · ${T('{n} change|{n} changes', { n: ch.length })}</p>${ch.length ? `<ul class="m-list">${ch.map(c => `<li>${esc(c)}</li>`).join('')}</ul>` : '<p class="m-hint">' + T('Nothing in this review yet.') + '</p>'}
      <p class="m-hint">${LIVE ? T('Sent straight to Blender, which imports it.') : T('The file {name}, to import in Blender: Pipeline › Import review.', { name: esc(reviewName()) })}</p>`;
    foot = `${ch.length && !LIVE ? `<button class="btn m-wide" data-rvclear>${T('Clear the review…')}</button>` : ''}<button class="btn m-wide" data-mstop>${T('Leave the review')}</button><button class="btn primary m-wide" data-msendgo ${ch.length ? '' : 'disabled'}>${ic('b-export')}${LIVE ? T('Send to Blender') : T('Download the file')}</button>`;
  }
  if (k === 'news') {
    t = T("What's new");
    newsSeen = NEWS.length;
    const IC = { rtk: '--st-rtk', render: '--st-done', ok: '--st-val' };
    h = NEWS.length
      ? NEWS.map(
          x =>
            `<button class="m-opt" data-mgo="${x.n}"><span class="dt" style="background:var(${IC[x.k]})"></span><span class="lbl"><span class="mono">${esc(x.n)}</span> · ${esc(x.h)}<small>${esc(x.x)} · ${x.at}</small></span></button>`
        ).join('')
      : '<p class="m-hint">' + T('Nothing new since the page opened.') + '</p>';
  }
  if (k === 'search') {
    t = T('Search everything');
    h = `<label class="field"><input id="sr-q" value="${esc(S.sq || '')}" placeholder="${T('Search everything…')}" autocomplete="off" enterkeyhint="search"></label>
      <div class="sr-list" id="sr-list">${searchResultsHTML(S.sq || '')}</div>`;
  }
  if (k === 'menu') {
    t = 'Menu';
    h = `<div class="m-sec-h">${T('Theme')}</div><span class="join full">${[
      ['dark', T('Dark')],
      ['light', T('Light')],
      ['system', T('System')]
    ]
      .map(([x, l]) => `<button class="btn" data-theme="${x}" aria-pressed="${S.theme === x}">${l}</button>`)
      .join('')}</span>
      <div class="m-sec-h">${T('Legend')}</div><ul class="legend-list">${[
        ['done', null, T('Done')],
        ['wip', 'rtk', T('Open retake')],
        ['val', null, T('Validated by the top role')],
        ['done', 'wait', T('Waiting')],
        ['rework', null, T('Done, reworked')],
        ['done', 'redo', T('To redo')],
        ['val', 'you', T('You: validated')],
        ['done', 'you-rtk', T('You: retake')],
        ['done', null, T('Open note'), 'n']
      ]
        .map(([b, c, l, n]) => `<li>${glyph(b, c, 1, !!n)}<span>${l}</span></li>`)
        .join('')}</ul>
      <p class="m-hint">${T('Links, breakdown, file settings and more filters: the desktop version.')}</p>
      <a class="brand-f" href="https://extensions.blender.org/add-ons/minimalist-pipeline/" target="_blank" rel="noopener"><svg viewBox="${document.querySelector('.statusbar .brand-f svg').getAttribute('viewBox')}" aria-hidden="true"><use href="#mp"/></svg><span class="wm">minimalist pipeline</span><span class="v">${esc(M.addon_version || '')}</span></a>`;
    foot = `${S.review ? '<button class="btn m-wide" data-mstop>' + T('Leave the review') + '</button>' : ''}<button class="btn m-wide" data-mview="desktop">${T('Desktop version')}</button>`;
  }
  if (k && k.startsWith('job:')) {
    const j = F.jobs.find(x => x.id === k.slice(4));
    if (!j) {
      S.m.sheet = null;
      return '';
    }
    const live = j.state === 'running' || j.state === 'waiting',
      x = JS.find(a => a[0] === j.state);
    t = j.file;
    h = `${j.total ? `<span class="jbar big"><i style="--p:${(j.done / j.total) * 100}%"></i><span>${j.done} / ${j.total} frames · ${Math.round((j.done / j.total) * 100)} %</span></span>` : ''}
      <dl class="dl"><dt>${T('State')}</dt><dd>${jst(j.state)} ${x[1]} · ${esc(j.text)}</dd><dt>${T('Machines')}</dt><dd>${j.names.length ? esc(j.names.join(', ')) : T('none')}</dd><dt>${T('Sent')}</dt><dd>${esc(j.user)} · ${fmtD(j.at)}</dd>
      <dt>${T('Priority')}</dt><dd>${live && !j.pending ? `<span class="prio"><button class="btn icon" data-mprio="-1" aria-label="${T('Lower')}">−</button><b>${j.priority}</b><button class="btn icon" data-mprio="1" aria-label="${T('Higher')}">+</button></span>` : j.priority}</dd></dl>`;
    foot = `${j.retry ? '<button class="btn primary m-wide" data-mjob="retry">' + T('Retry') + '</button>' : ''}${j.removable ? '<button class="btn alert m-wide" data-mjob="remove">' + T('Remove from the queue') + '</button>' : live ? '<button class="btn alert m-wide" data-mjob="cancel">' + T('Cancel the render') + '</button>' : ''}${j.state === 'failed' || j.state === 'finished' ? '<button class="btn m-wide" data-mjob="archive">' + T('Archive') + '</button>' : ''}`;
  }
  if (k === 'render') {
    t = T('Render a shot');
    const f = (S.m.rf = S.m.rf || {
      file: it.name,
      ver: it.stable ? 'stable' : 'last',
      dept: startDept(it),
      preset: deptPreset(it, startDept(it)),
      prio: 10
    });
    const rf = items.find(i => i.name === f.file) || it;
    h = `<label class="m-lab">${T('File')}<select class="m-select" data-mrf="file">${[
      ...new Set(items.map(groupOf))
    ]
      .map(
        g =>
          `<optgroup label="${esc(g)}">${items
            .filter(i => groupOf(i) === g)
            .map(
              i => `<option value="${i.name}" ${i.name === f.file ? 'selected' : ''}>${esc(i.name)}</option>`
            )
            .join('')}</optgroup>`
      )
      .join('')}</select></label>
      <div class="m-lab">${T('Version')}<span class="join full">${rf.stable ? `<button class="btn" data-mrv="stable" aria-pressed="${f.ver === 'stable'}">Stable · ${esc(rf.stable)}</button>` : ''}<button class="btn" data-mrv="last" aria-pressed="${f.ver === 'last' || !rf.stable}">${T('Latest · {v}', { v: esc(rf.wip || rf.stable || '') })}</button></span></div>
      <label class="m-lab">${T('Department')}<select class="m-select" data-mrf="dept">${['', ...(DEPTS[rf.kind] || [])].map(d => `<option value="${esc(d)}" ${d === f.dept ? 'selected' : ''}>${d ? esc(d) : T('No department')}</option>`).join('')}</select></label>
      <label class="m-lab">${T('Pre-render script')}<select class="m-select" data-mrf="preset">${presetsFor(
        f.dept
      )
        .map(p => `<option value="${esc(p[0])}" ${p[0] === f.preset ? 'selected' : ''}>${esc(p[1])}</option>`)
        .join('')}</select></label>
      <label class="m-lab">${T('Sound')}<select class="m-select" data-mrf="sound"><option value="on" ${f.sound !== 'off' ? 'selected' : ''}>${T('With sound')}</option><option value="off" ${f.sound === 'off' ? 'selected' : ''}>${T('Without sound')}</option></select></label>
      <div class="m-lab">${T('Priority')}<span class="prio"><button class="btn icon" data-mrp="-1" aria-label="${T('Lower')}">−</button><b>${f.prio}</b><button class="btn icon" data-mrp="1" aria-label="${T('Higher')}">+</button><span class="m-hint">${T('the highest goes first')}</span></span></div>
      <p class="m-hint">${T("Frames, machines, a block's shots: the desktop version.")}</p>`;
    foot = `<button class="btn primary m-wide" data-mrender>${ic('b-export')}${T('Send to the farm')}</button>`;
  }
  return `<div class="m-sheet" data-mclose-bg><div class="m-sheet-in" role="dialog" aria-modal="true" aria-label="${esc(t)}"><div class="m-sheet-h"><b>${esc(t)}</b><span class="sp"></span><button class="m-ib" data-mclose aria-label="${T('Close')}">${ic('b-x')}</button></div>
    <div class="m-sheet-b">${h}</div>${foot ? `<div class="m-sheet-f">${foot}</div>` : ''}</div></div>`;
}

/* ----- Phone events (data-tp, data-goto, data-unnote, data-still, data-theme: the desktop's) ----- */
function mGo(n, keep) {
  if (!n) return;
  const it = items.find(i => i.name === n);
  if (!it) return;
  S.sel = n;
  S.m.kind = it.kind;
  S.frame = 1;
  S.rangeStart = null;
  if (S.playing && !keep) togglePlay();
  S.m.sheet = null;
  mRender();
  $('#m-body').scrollTop = 0;
}
/* The video played to its end: loop, or the path's next shot (playing on), or stop at the end. */
function mEnd() {
  if (S.m.loop) {
    setFrame(1);
    return;
  }
  const sib = mSib(),
    k = sib.findIndex(i => i.name === S.sel),
    n = sib[k + 1];
  if (!n) {
    togglePlay();
    setFrame(1);
    toast(T('End of the path'));
    return;
  }
  mGo(n.name, true);
}
function mStep(d) {
  const sib = mSib(),
    k = sib.findIndex(i => i.name === S.sel),
    n = sib[k + d];
  if (n) mGo(n.name);
}
$('#mob').addEventListener('click', e => {
  const t = e.target,
    q = s => t.closest(s);
  let x;
  if ((x = q('[data-sgofile]'))) {
    S.m.tab = 'review';
    mGo(x.dataset.sgofile);
    return;
  }
  if (t.matches('[data-mclose-bg]') || q('[data-mclose]')) {
    S.m.sheet = null;
    mRender();
    return;
  }
  if ((x = q('[data-msheet]'))) {
    S.m.sheet = x.dataset.msheet;
    if (S.m.sheet === 'render') S.m.rf = null;
    if (S.m.sheet === 'start') S.m.role = null;
    mRender();
    return;
  }
  if ((x = q('[data-mview]'))) {
    setView(x.dataset.mview);
    return;
  }
  if (q('[data-theme]')) {
    setTimeout(mRender, 0);
    return;
  }
  if ((x = q('[data-mtab]'))) {
    S.m.tab = x.dataset.mtab;
    mRender();
    return;
  }
  if ((x = q('[data-mstep]'))) {
    mStep(+x.dataset.mstep);
    return;
  }
  if ((x = q('[data-tdk]'))) {
    S.td.kind = x.dataset.tdk;
    S.td.dept = '';
    mRender();
    return;
  }
  if ((x = q('[data-tdst]'))) {
    S.td.st = x.dataset.tdst;
    mRender();
    return;
  }
  if (q('[data-tdcopy]')) {
    const c = todoText();
    copyText(c.text, T('Copied: {n} file|Copied: {n} files', { n: c.n }));
    return;
  }
  if ((x = q('[data-mgo]'))) {
    if (S.m.tab !== 'review') S.m.tab = 'review';
    mGo(x.dataset.mgo);
    return;
  }
  if ((x = q('[data-mkind]'))) {
    S.m.kind = x.dataset.mkind;
    mRender();
    return;
  }
  if ((x = q('[data-mfilter]'))) {
    S.m.filter = x.dataset.mfilter;
    if (!x.hasAttribute('data-keep')) {
      const f = mSib()[0];
      if (f && !mSib().some(i => i.name === S.sel)) S.sel = f.name;
    }
    mRender();
    return;
  }
  if (q('[data-mloop]')) {
    S.m.loop = !S.m.loop;
    mRender();
    return;
  }
  if ((x = q('[data-mside]'))) {
    S.m.side = x.dataset.mside;
    mRender();
    return;
  }
  if ((x = q('[data-mver]'))) {
    const it = cur();
    if (S.m.sheet === 'verA') S.ver[it.name] = +x.dataset.mver;
    else S.m.b[it.name] = +x.dataset.mver;
    S.m.side = S.m.sheet === 'verA' ? 'A' : 'B';
    S.m.sheet = null;
    mRender();
    return;
  }
  if ((x = q('[data-massign]'))) {
    const a = A.assignToggle(cur(), x.dataset.massign, x.dataset.p);
    if (!x.dataset.p) S.m.sheet = null;
    mRender();
    toast(LBL[x.dataset.massign] + ': ' + (a.join(', ') || T('nobody')));
    return;
  }
  if ((x = q('[data-mreq]'))) {
    A.toggleReq(cur(), x.dataset.mreq);
    mRender();
    return;
  }
  if ((x = q('[data-mcd]'))) {
    S.m.cdept = x.dataset.mcd || null;
    S.m.sheet = null;
    mRender();
    $('#m-ta')?.focus();
    return;
  }
  if ((x = q('[data-mct]'))) {
    S.m.ctype = x.dataset.mct;
    mRender();
    return;
  }
  if ((x = q('[data-mval]'))) {
    if (x.disabled) return;
    A.toggleVal(cur(), x.dataset.mval);
    mRender();
    return;
  }
  if (q('[data-mvalall]')) {
    const n = A.validateAll(cur());
    mRender();
    toast(T('{n} department validated|{n} departments validated', { n }));
    return;
  }
  if ((x = q('[data-mrtk]'))) {
    const d = x.dataset.mrtk;
    if (A.toggleRtk(cur(), d)) {
      S.m.ctype = 'rtk';
      S.m.cdept = d;
      mRender();
      $('#m-ta')?.focus();
    } else mRender();
    return;
  }
  if (q('[data-msend]')) {
    const it = cur(),
      ta = $('#m-ta'),
      txt = wordsOf(ta, toast);
    if (!txt) return;
    A.note(it, { type: S.m.ctype, dept: S.m.cdept, text: txt, frames: rangeStr() });
    ta.value = '';
    S.rangeStart = null;
    mRender();
    toast(S.m.ctype === 'rtk' ? T('Retake added to your review') : T('Remark added to your review'));
    return;
  }
  if ((x = q('[data-mrole]'))) {
    S.m.role = x.dataset.mrole;
    mRender();
    return;
  }
  if (q('[data-mstart]')) {
    startReview($('#m-name').value, S.m.role);
    S.m.sheet = null;
    const f = mSib()[0];
    if (f && !mSib().some(i => i.name === S.sel)) S.sel = f.name;
    mRender();
    return;
  }
  if (q('[data-mstop]')) {
    S.review = null;
    S.m.sheet = null;
    mRender();
    toast(T('Review left: your changes are kept in this browser.'));
    return;
  }
  if (q('[data-msendgo]')) {
    S.m.sheet = null;
    mRender();
    deliverReview();
    return;
  }
  if ((x = q('[data-mjob]'))) {
    const j = F.jobs.find(y => y.id === S.m.sheet.slice(4)),
      k = x.dataset.mjob;
    S.m.sheet = null;
    mRender();
    if (j) farmPost({ action: k, job_id: j.id }, JOB_SAY[k]() + ' · ' + j.file);
    return;
  }
  if ((x = q('[data-mprio]'))) {
    const j = F.jobs.find(y => y.id === S.m.sheet.slice(4));
    if (j)
      farmPost(
        { action: 'priority', job_id: j.id, value: j.priority + +x.dataset.mprio },
        T('priority {n}', { n: j.priority + +x.dataset.mprio })
      );
    return;
  }
  if ((x = q('[data-mrv]'))) {
    S.m.rf.ver = x.dataset.mrv;
    mRender();
    return;
  }
  if ((x = q('[data-mrp]'))) {
    S.m.rf.prio += +x.dataset.mrp;
    mRender();
    return;
  }
  if (q('[data-mrender]')) {
    const f = S.m.rf,
      it = items.find(i => i.name === f.file);
    S.m.sheet = null;
    mRender();
    if (it)
      farmPost({
        action: 'render',
        file: f.ver === 'stable' && it.stableFile ? it.stableFile : it.file,
        department: f.dept || '',
        preset: f.preset,
        priority: f.prio,
        mode: 'all',
        start: '',
        end: '',
        sound: f.sound !== 'off',
        shots: null
      });
    return;
  }
});
$('#mob').addEventListener('change', e => {
  const r = e.target.closest('[data-mrf]');
  if (r) {
    S.m.rf[r.dataset.mrf] = r.value;
    const rf = items.find(i => i.name === S.m.rf.file);
    if (r.dataset.mrf === 'file') {
      S.m.rf.ver = rf.stable ? 'stable' : 'last';
      S.m.rf.dept = startDept(rf);
    }
    if (r.dataset.mrf === 'file' || r.dataset.mrf === 'dept') S.m.rf.preset = deptPreset(rf, S.m.rf.dept);
    mRender();
  }
});
$('#mob').addEventListener('input', e => {
  if (e.target.id === 'sr-q') {
    S.sq = e.target.value;
    $('#sr-list').innerHTML = searchResultsHTML(S.sq);
    return;
  }
  if (e.target.id === 'm-ta') {
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
  }
});
/* Swipe the picture sideways: next / previous shot. */
let mSw = null;
$('#mob').addEventListener('pointerdown', e => {
  if (e.target.closest('#m-player')) mSw = { x: e.clientX, y: e.clientY };
});
$('#mob').addEventListener('pointerup', e => {
  if (!mSw) return;
  const dx = e.clientX - mSw.x,
    dy = e.clientY - mSw.y;
  mSw = null;
  if (Math.abs(dx) > 60 && Math.abs(dy) < 50) mStep(dx < 0 ? 1 : -1);
});
$('#mob').addEventListener('pointercancel', () => (mSw = null));
