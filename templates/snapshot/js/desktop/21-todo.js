/* ---------- To do: what isn't validated yet, file by file ----------
   Each file's required departments not validated on the stable shown (nor by the
   review going on), with why one waits; the files set aside left out. Two halves:
   to validate (done, nothing asked of it: waits for a reviewer) and to work on (the
   rest: not done, a retake, to redo). Copy: the same, as text, in the clipboard. */
const toCheck = (it, d) => {
  const x = info(it, d);
  return ['done', 'rework', 'old'].includes(x.base) && x.tone !== 'rtk' && x.tone !== 'redo';
};
const TD_ST = () => [
  ['', T('Everything')],
  ['work', T('To work on')],
  ['val', T('To validate')]
];
function todoOf(it) {
  const t = S.td;
  return required(it).filter(
    d =>
      !(it.ok[d] && !it.ok[d].old) &&
      it.mine[d] !== 'val' &&
      (!t.st || (t.st === 'val') === toCheck(it, d)) &&
      (!t.dept || d === t.dept) &&
      (!t.me || !me() || assignOf(it, d).includes(me()))
  );
}
function todoFiles(kind) {
  return items
    .filter(it => it.kind === kind && !omitted(it))
    .filter(
      it =>
        (!S.tq || it.name.toLowerCase().includes(S.tq)) &&
        (!S.q || (it.name + ' ' + it.desc).toLowerCase().includes(S.q))
    )
    .map(it => ({ it, ds: todoOf(it) }))
    .filter(r => r.ds.length);
}
/* Why a department waits, or what holds it: the state engine's words (info()), only those. */
const todoWhy = (it, d) => {
  const x = info(it, d);
  return ['wait', 'redo', 'rtk'].includes(x.tone) ? x.s : '';
};
function renderTodoQuick() {
  const t = S.td,
    n = k => todoFiles(k).length;
  $('#quick').classList.remove('folded');
  $('#quick').innerHTML = `<span class="join td-j">${[
    ['shot', T('Shots')],
    ['asset', T('Assets')]
  ]
    .map(
      ([k, l]) =>
        `<button class="btn" data-tdk="${k}" aria-pressed="${t.kind === k}">${l}<span class="n">${n(k)}</span></button>`
    )
    .join('')}</span>
    <span class="join td-j">${TD_ST()
      .map(([k, l]) => `<button class="btn" data-tdst="${k}" aria-pressed="${t.st === k}">${l}</button>`)
      .join('')}</span>
    <span class="anchor"><button class="btn ${t.dept ? '' : 'tool'}" data-menu="m-tdd" aria-haspopup="true" aria-expanded="false" ${t.dept ? 'aria-pressed="true"' : ''}>${ic('b-filter')}${t.dept ? esc(LBL[t.dept]) : T('All departments')}${ic('b-tria_down')}</button>
    <div class="menu" id="m-tdd" hidden role="menu">${[
      ['', T('All departments')],
      ...DEPTS[t.kind].map(d => [d, LBL[d]])
    ]
      .map(
        ([d, l]) =>
          `<button class="mi" role="menuitemradio" aria-checked="${t.dept === d}" data-tdd="${d}"><span class="ck">${t.dept === d ? ic('b-checkmark') : ''}</span><span class="lbl">${esc(l)}</span></button>`
      )
      .join('')}</div></span>
    ${me() ? `<button class="btn" data-tdme aria-pressed="${t.me}" title="${T('assigned to {who}', { who: me() })}">${ic('b-user')}${T('Me')}</button>` : ''}
    <button class="btn tool icon" data-tdcopy aria-label="${T('Copy')}" title="${T('Copy')} · ${T('This list as text, in the clipboard')}">${ic('b-file')}</button>`;
}
function renderTodo() {
  const L = $('#list'),
    rows = todoFiles(S.td.kind);
  if (!rows.length) {
    L.innerHTML = `<div class="empty">${S.td.dept || S.td.me || S.tq ? T('Nothing left to validate here.') : T('Everything is validated.')}</div>`;
    return;
  }
  L.innerHTML = [...new Set(rows.map(r => groupOf(r.it)))]
    .map(g => {
      const its = rows.filter(r => groupOf(r.it) === g);
      return `<div class="grp" data-g="${esc(g)}"><div class="grp-h"><b>${esc(g)}</b><span class="cnt">${T('{n} file|{n} files', { n: its.length })}</span></div>
      <div class="rows">${its
        .map(
          ({ it, ds }) =>
            `<div class="row td ${S.sel === it.name ? 'sel' : ''}" data-n="${esc(it.name)}"><span class="mono nm">${esc(it.name)}</span><span class="td-ds">${ds
              .map(d => {
                const x = info(it, d),
                  why = todoWhy(it, d);
                return `<span class="td-d" title="${esc(LBL[d])}: ${esc(x.l)}${x.s ? ' · ' + esc(x.s) : ''}">${glyph(x.base, x.corner, x.cnt)}<b>${esc(LBL[d])}</b>${why ? `<span class="s ${x.tone}">${esc(why)}</span>` : ''}</span>`;
              })
              .join('')}</span></div>`
        )
        .join('')}</div></div>`;
    })
    .join('');
}
/* What the list shows, as text: a line per file, its departments, why one waits. */
function todoText() {
  const k = S.td.kind,
    rows = todoFiles(k),
    out = [
      [
        T('To do'),
        M.project,
        k === 'shot' ? T('Shots') : T('Assets'),
        S.td.st && TD_ST().find(x => x[0] === S.td.st)[1],
        S.td.dept && LBL[S.td.dept],
        S.td.me && me(),
        fmtD(M.snapshot)
      ]
        .filter(Boolean)
        .join(' · ')
    ];
  [...new Set(rows.map(r => groupOf(r.it)))].forEach(g => {
    out.push('', g);
    rows
      .filter(r => groupOf(r.it) === g)
      .forEach(({ it, ds }) =>
        out.push(
          '  ' +
            it.name +
            ' : ' +
            ds
              .map(d => {
                const why = todoWhy(it, d);
                return LBL[d] + (why ? ' (' + why + ')' : '');
              })
              .join(', ')
        )
      );
  });
  return { text: out.join('\n'), n: rows.length };
}
