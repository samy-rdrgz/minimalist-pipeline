/* ---------- Breakdown › Export: the whole project as a spreadsheet (.xlsx) ----------
   Sequences (the Breakdown's figures, each department done and validated), Shots and
   Assets (a line per file: its figures, each department's state, who it's assigned to),
   Retakes (every open one), To validate (each department done waiting for a reviewer) and
   Over time (a line a day: the figures, the hours, the files worked by department).
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
  // Over time: a line a day -- the finished figures and what was worked (progress.json).
  const sd = DEPTS.shot || [],
    ad = DEPTS.asset || [];
  const time = [
    [
      T('Day'),
      T('Shots') + ' · ' + T('Done'),
      T('Shots') + ' · ' + T('Validated'),
      T('Assets') + ' · ' + T('Done'),
      T('Assets') + ' · ' + T('Validated'),
      T('Hours'),
      T('People'),
      ...sd.map(d => T('Shots') + ' · ' + LBL[d] + ' · ' + T('files')),
      ...ad.map(d => T('Assets') + ' · ' + LBL[d] + ' · ' + T('files'))
    ]
  ];
  Object.entries(M.history || {})
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .forEach(([day, p]) => {
      const s = p.shots || {},
        a = p.assets || {},
        w = p.worked || {};
      time.push([
        day,
        P(s.done),
        P(s.validated),
        P(a.done),
        P(a.validated),
        'seconds' in p ? Math.round(p.seconds / 1800) / 2 : null, // to the half hour: an estimate
        'people' in p ? p.people : null,
        ...sd.map(d => ('worked' in p ? (w.shots || {})[d] || 0 : null)),
        ...ad.map(d => ('worked' in p ? (w.assets || {})[d] || 0 : null))
      ]);
    });
  return [
    { name: T('Sequences'), cols: [10, 14, 7, 9, 10, 12, ...Array(allDeps).fill(14)], rows: seq },
    fileSheet('shot', T('Shots')),
    fileSheet('asset', T('Assets')),
    { name: T('Retakes'), cols: [8, 26, 22, 60, 14, 10, 16, 10], rows: rtk },
    { name: T('To validate'), cols: [8, 26, 18, 40, 20], rows: val },
    {
      name: T('Over time'),
      cols: [12, 12, 12, 12, 12, 8, 8, ...sd.map(() => 16), ...ad.map(() => 16)],
      rows: time
    }
  ];
}
function exportBreakdown() {
  const day = new Date().toISOString().slice(0, 10),
    name = `${M.project}_breakdown_${day}.xlsx`.replace(/[\\/:*?"<>|]/g, '_');
  saveBlob(XLSX.book(exportBook()), name);
  toast(T('Downloaded ({name})', { name }));
}
