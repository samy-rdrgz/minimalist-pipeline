/* ---------- Breakdown › Export: the whole project as a spreadsheet (.xlsx) ----------
   Sequences (the Breakdown's figures, each department done and validated), Shots and
   Assets (a line per file: its figures, each department's state, who it's assigned to),
   Retakes (every open one) and To validate (each department done waiting for a reviewer).
   As the page shows them: the review going on counted, the page's language. */
function exportBook() {
  const P = v => (v == null ? null : { v: Math.round(v * 1000) / 1000, pct: true });
  const kinds = [
    ['shot', T('Shots')],
    ['asset', T('Assets')]
  ];
  const seq = [
    [
      T('Kind'),
      T('Sequence'),
      T('Files'),
      T('Done'),
      T('Validated'),
      T('Open retakes'),
      ...kinds
        .flatMap(([k]) => DEPTS[k])
        .filter((d, i, a) => a.indexOf(d) === i)
        .flatMap(d => [LBL[d] + ' · ' + T('Done'), LBL[d] + ' · ' + T('Validated')])
    ]
  ];
  const allDeps = seq[0].length - 6;
  const deps = kinds.flatMap(([k]) => DEPTS[k]).filter((d, i, a) => a.indexOf(d) === i);
  kinds.forEach(([k, l]) => {
    const pool = items.filter(i => i.kind === k);
    [...new Set(pool.map(groupOf))].forEach(g => {
      const its = pool.filter(i => groupOf(i) === g),
        all = synthCell(its, null);
      seq.push([
        l,
        g,
        its.length,
        P(MPStatus.average(its.filter(i => !omitted(i)).map(i => i.done))),
        P(MPStatus.average(its.filter(i => !omitted(i)).map(valOf))),
        all ? all.rtk : 0,
        ...deps.flatMap(d => {
          const c = DEPTS[k].includes(d) ? synthCell(its, d) : null;
          return c ? [P(c.done), P(c.val)] : [null, null];
        })
      ]);
    });
  });
  const fileSheet = (k, l) => {
    const dl = DEPTS[k];
    const rows = [
      [
        k === 'shot' ? T('Sequence') : T('Prefix'),
        T('File'),
        T('Description'),
        T('Set aside'),
        T('Done'),
        T('Validated'),
        T('Open retakes'),
        T('Open notes'),
        T('Stable'),
        T('Latest'),
        ...dl.map(d => LBL[d]),
        ...dl.map(d => T('Assigned to') + ' · ' + LBL[d])
      ]
    ];
    items
      .filter(i => i.kind === k)
      .forEach(it => {
        const om = omitted(it);
        rows.push([
          groupOf(it),
          it.name,
          it.descEdit !== undefined ? it.descEdit : it.desc,
          om ? String(om) : '',
          P(it.done),
          P(valOf(it)),
          openRtk(it),
          openNotes(it),
          it.stable,
          it.wip || it.stable,
          ...dl.map(d => {
            const x = info(it, d);
            return x.base === 'na' ? '' : x.l + (x.s ? ' · ' + x.s : '');
          }),
          ...dl.map(d => assignOf(it, d).join(', '))
        ]);
      });
    return {
      name: l,
      cols: [12, 26, 34, 10, 8, 10, 10, 10, 18, 18, ...dl.map(() => 26), ...dl.map(() => 16)],
      rows
    };
  };
  const rtk = [
    [T('Kind'), T('File'), T('Departments'), T('Retake'), T('By'), T('Role'), T('Date'), T('Frames')]
  ];
  items.forEach(it =>
    rtkNotes(it).forEach(n =>
      rtk.push([
        it.kind === 'shot' ? T('shot') : T('asset'),
        it.name,
        (n.deps || []).map(d => LBL[d] || d).join(', '),
        n.text,
        n.author,
        n.team ? T('team') : n.role || T('team'),
        n.date ? fmtD(n.date) : '',
        n.frames || ''
      ])
    )
  );
  const val = [[T('Kind'), T('File'), T('Department'), T('State'), T('Assigned to')]];
  items
    .filter(it => !omitted(it))
    .forEach(it =>
      required(it)
        .filter(d => !(it.ok[d] && !it.ok[d].old) && it.mine[d] !== 'val' && toCheck(it, d))
        .forEach(d => {
          const x = info(it, d);
          val.push([
            it.kind === 'shot' ? T('shot') : T('asset'),
            it.name,
            LBL[d],
            x.l + (x.s ? ' · ' + x.s : ''),
            assignOf(it, d).join(', ')
          ]);
        })
    );
  return [
    { name: T('Sequences'), cols: [10, 14, 7, 9, 10, 12, ...Array(allDeps).fill(14)], rows: seq },
    fileSheet('shot', T('Shots')),
    fileSheet('asset', T('Assets')),
    { name: T('Retakes'), cols: [8, 26, 22, 60, 14, 10, 16, 10], rows: rtk },
    { name: T('To validate'), cols: [8, 26, 18, 40, 20], rows: val }
  ];
}
function exportBreakdown() {
  const day = new Date().toISOString().slice(0, 10),
    name = `${M.project}_breakdown_${day}.xlsx`.replace(/[\\/:*?"<>|]/g, '_');
  saveBlob(XLSX.book(exportBook()), name);
  toast(T('Downloaded ({name})', { name }));
}
