/* ---------- Detail ---------- */
function marks(it) {
  const out = [];
  [...it.notes.filter(n => !n.done), ...it.myNotes].forEach(n => {
    if (!n.frames) return;
    const m = String(n.frames).match(/(\d+)(?:-(\d+))?/);
    if (m) out.push({ a: +m[1], b: m[2] ? +m[2] : null, rtk: n.type === 'rtk', n });
  });
  return out;
}
const fmtDay = sec => {
  const d = new Date(sec * 1000);
  return d.toLocaleDateString(DTL(), { day: '2-digit', month: '2-digit' });
};
const verLab = v =>
  [v.shot, v.folder, v.dept ? LBL[v.dept] || v.dept : '', v.at ? fmtDay(v.at) : '']
    .filter(Boolean)
    .join(' · ');
function shotsHTML(it) {
  if (!it.shots || it.shots.length < 2) return '';
  const c = shotOf(it);
  return `<div class="shotsel"><span class="faint">${T('Shot of the block')}</span><span class="join">${['', ...it.shots].map(x => `<button class="btn sm" data-shot="${x}" aria-pressed="${c === x}">${x || T('Whole block')}</button>`).join('')}</span></div>`;
}
/* A block's renders, one shot at a time: the shot chosen ('' its renders made whole), else the first that has any.
   A and B are always two versions of that same shot. */
const shotOf = it => {
  const c = S.shot[it.name];
  if (c != null) return c;
  const has = s => it.versions.some(v => (v.shot || '') === s);
  return has('') || !it.versions.length ? '' : ((it.shots || []).find(has) ?? (it.versions[0].shot || ''));
};
const versOf = it => {
  const c = shotOf(it);
  return it.versions.filter(v => (v.shot || '') === c);
};
/* Compare A / B: the switch and B's pick, under the version's (A). Key C. */
function abHTML(it, ctx) {
  const { V, b } = mVer(it);
  if (V.length < 2) return '';
  return `<div class="ctl abrow"><span class="join" role="group" aria-label="${T('Version shown')}"><button class="btn" data-ab="A" aria-pressed="${S.m.side === 'A'}" title="${T('Version A (C)')}">A</button><button class="btn" data-ab="B" aria-pressed="${S.m.side === 'B'}" title="${T('Version B, same frame (C)')}">B</button></span>
    <span class="anchor vpick"><button class="enum" data-menu="m-verb-${ctx}" aria-haspopup="true" aria-expanded="false" title="${T('The version to compare (B)')}"><b class="ab b">B</b><span class="lb">${esc(verLab(V[b]))}</span>${ic('b-tria_down')}</button>
    <div class="menu" id="m-verb-${ctx}" hidden role="menu"><div class="menu-h">${T('Compare with')}</div>${V.map((x, n) => `<button class="mi" role="menuitemradio" aria-checked="${n === b}" data-verb="${n}"><span class="ck">${n === b ? ic('b-checkmark') : ''}</span><span class="lbl">${esc(verLab(x))}</span>${n === 0 ? '<span class="k">' + T('latest') + '</span>' : ''}</button>`).join('')}</div></span></div>`;
}
function verHTML(it, ctx) {
  const V = versOf(it);
  if (!V.length) return `<span class="vro faint">${T('Not rendered yet')}</span>`;
  const i = Math.min(S.ver[it.name] || 0, V.length - 1);
  if (V.length < 2)
    return `<span class="vro">${ic('b-file_movie')}<span class="lb">${esc(verLab(V[0]))}</span></span>`;
  return `<span class="anchor vpick"><button class="enum" data-menu="m-ver-${ctx}" aria-haspopup="true" aria-expanded="false" title="${T('The render version to watch (A)')}"><b class="ab">A</b><span class="lb">${esc(verLab(V[i]))}</span><span class="n">${i + 1}/${V.length}</span>${ic('b-tria_down')}</button>
    <div class="menu" id="m-ver-${ctx}" hidden role="menu"><div class="menu-h">${T('Version to watch')}</div>${V.map((x, n) => `<button class="mi" role="menuitemradio" aria-checked="${n === i}" data-ver="${n}"><span class="ck">${n === i ? ic('b-checkmark') : ''}</span><span class="lbl">${esc(verLab(x))}</span>${n === 0 ? '<span class="k">' + T('latest') + '</span>' : ''}</button>`).join('')}</div></span>`;
}
function stageHTML(it) {
  const V = versOf(it),
    v = V[mVer(it).i];
  const mk = marks(it)
    .map(f => {
      const x = ((fIdx(f.a) - 1) / (NF - 1)) * 100;
      return (
        (f.b ? `<span class="rng" style="left:${x}%;width:${((f.b - f.a) / (NF - 1)) * 100}%"></span>` : '') +
        `<button class="mk ${f.rtk ? '' : 'n'}" style="left:${x}%" data-goto="${f.a}" title="${f.rtk ? 'RTK' : T('Note')} f${f.a}${f.b ? '-' + f.b : ''} : ${esc(f.n.text || T('(no text)'))}"></button>`
      );
    })
    .join('');
  return `${shotsHTML(it)}<div class="stage ${S.m.side === 'B' && V.length > 1 ? 'is-b' : ''}">${it.thumb ? `<img src="${it.thumb}" alt="${T('Picture of {name}', { name: it.name })}">` : `<span class="noimg">${T('Not rendered yet')}</span>`}
      <span class="hud">${V.length > 1 ? `<b class="ab">${S.m.side}</b> ` : ''}${shotOf(it) ? shotOf(it) + ' · ' : ''}${v ? esc(v.folder) + ' · f <span data-f>' + fNo(S.frame) + '</span>' : T('Not rendered yet')}</span></div>
    <div class="scrub ${rendered(it) ? '' : 'off'}" data-scrub role="slider" tabindex="0" aria-label="${T('Frame')}" aria-valuemin="1" aria-valuemax="${NF}" aria-valuenow="${S.frame}">${mk}<span class="ph" style="left:${((S.frame - 1) / (NF - 1)) * 100}%"></span></div>
    <div class="ctl">
      <span class="join"><button class="btn icon" data-tp="vprev" aria-label="${T('Previous version')}" title="${T('Previous version')}" ${V.length > 1 ? '' : 'disabled'}>${ic('b-back')}</button><button class="btn icon" data-tp="fprev" ${pOff(it)} aria-label="${T('Previous frame')}" title="${T('Previous frame (,)')}">${ic('b-frame_prev')}</button><button class="btn icon play" data-tp="play" ${pOff(it)} aria-label="${T('Play')}" title="${T('Play (Space)')}">${ic(S.playing ? 'b-pause' : 'b-play')}</button><button class="btn icon" data-tp="fnext" ${pOff(it)} aria-label="${T('Next frame')}" title="${T('Next frame (.)')}">${ic('b-frame_next')}</button><button class="btn icon" data-tp="vnext" aria-label="${T('Next version')}" title="${T('Next version')}" ${V.length > 1 ? '' : 'disabled'}>${ic('b-forward')}</button></span>
      <span class="join"><button class="btn icon" data-tp="snd" aria-label="${T('Sound')}" title="${T('Sound (M)')}" aria-pressed="${!S.muted}">${ic(S.muted ? 'b-mute_ipo_off' : 'b-mute_ipo_on')}</button><button class="btn icon" data-act="player" ${V.length ? '' : 'disabled'} aria-label="${T("This machine's player")}" title="${T("Open the original video in this machine's player")}">${ic('b-file_movie')}</button></span>
      ${rendered(it) ? `<span class="fr">f <span data-f>${fNo(S.frame)}</span> / ${fNo(NF)}</span>` : ''}</div>
    <div class="ctl">${verHTML(it, 'p')}<button class="btn" data-wide title="${T('Watch large: the video, the departments and the notes at their frames (W)')}">${ic('b-window')}${T('Watch large')}</button></div>${abHTML(it, 'p')}`;
}
const assignOf = (it, d) => (it.assign && d in it.assign ? it.assign[d] : it.assignees[d] || []);
function assignHTML(it, d, ctx) {
  const a = assignOf(it, d),
    chg = it.assign && d in it.assign;
  if (!S.review)
    return a.length
      ? `<span class="assign ro" title="${T('Assigned to')}">${ic('b-user')}${esc(a.join(', '))}</span>`
      : '';
  return `<span class="anchor"><button class="assign ${a.length ? '' : 'none'} ${chg ? 'chg' : ''}" data-menu="m-as-${ctx}-${d}" aria-haspopup="true" aria-expanded="false" title="${T('Assign {dept}', { dept: LBL[d] })}">${ic('b-user')}${a.length ? esc(a.join(', ')) : T('Assign')}${ic('b-tria_down')}</button>
    <div class="menu right" id="m-as-${ctx}-${d}" hidden role="menu"><div class="menu-h">${T('{dept}: assigned to', { dept: LBL[d] })}</div>${M.team.map(p => `<button class="mi" role="menuitemcheckbox" aria-checked="${a.includes(p)}" data-assign="${d}" data-p="${esc(p)}"><span class="ck">${a.includes(p) ? ic('b-checkmark') : ''}</span><span class="lbl">${esc(p)}</span>${p === M.live.user ? '<span class="k">moi</span>' : ''}</button>`).join('')}
    <div class="msep"></div><button class="mi" data-assign="${d}" data-p=""><span class="ck"></span><span class="lbl">${T('Nobody')}</span></button></div></span>`;
}
function deptHTML(it, d, ctx = 'p') {
  const x = info(it, d);
  if (x.base === 'na') return '';
  const f = it.flags[d] || {},
    rv = S.review,
    team = rv && rv.role === TEAM;
  const canVal = rv && !team && isDone(stOf(it, d)) && !it.ok[d] && !it.mine[d] && !it.rtk[d];
  const mk =
    rv && (d in it.marked || canMark(it, d))
      ? `<button class="btn sm ${d in it.marked ? '' : 'tool'}" data-mark="${d}" aria-pressed="${d in it.marked}" title="${T('Done at {stable}: forgotten when it was made, no new version', { stable: esc(it.stable || '') })}">${ic('b-checkmark')}${T('Mark done')}</button>`
      : '';
  const acts = rv
    ? `<span class="acts">${
        it.mine[d]
          ? `<button class="btn sm tool" data-undo="${d}" title="${T('Take my change back')}">${ic('b-loop_back')}${T('Take back')}</button>`
          : `${team ? '' : `<button class="btn sm ok icon" data-val="${d}" ${canVal ? '' : 'disabled'} aria-label="${T('Validate {dept}', { dept: LBL[d] })}" title="${canVal ? T('Validate as {role}', { role: rv.role }) : T('Nothing done to validate')}">${ic('b-checkmark')}</button>`}<button class="btn sm alert" data-rtk="${d}" title="${T('Write a retake under this department')}">Retake</button>`
      }</span>`
    : '';
  const ex = [
    f.waiting && x.tone !== 'wait'
      ? `<span class="wait">${ic('b-sorttime')} ${T('waiting: {why}', { why: esc(f.waiting) })}</span>`
      : '',
    f.to_redo && x.tone !== 'redo'
      ? `<span class="redo">↻ ${T('to redo: {why}', { why: esc(f.to_redo) })}</span>`
      : ''
  ]
    .filter(Boolean)
    .join('');
  // Who validated, said once with the role: "Validated prod · valerie".
  const lab = it.ok[d] && !it.mine[d] && it.ok[d].by ? x.l + ' · ' + it.ok[d].by : x.l;
  const frm = S.form && S.form.dept === d ? formHTML(d) : '';
  return `<div class="dept">${glyph(x.base, x.corner, x.cnt, x.note)}<span class="nm"><b>${LBL[d]}</b><span class="s ${x.tone}">${esc(lab)}${x.s ? ' · ' + esc(x.s) : ''}</span></span>${acts}<span class="extra">${assignHTML(it, d, ctx)}${ex}${stillHTML(it, d)}${mk}</span>${frm}</div>`;
}
/* A note being written: under a department (d) or none; the block's shot shown, if one is. */
function newForm(d) {
  const it = cur(),
    c = it && it.shots && it.shots.length > 1 ? shotOf(it) : '';
  return { dept: d, type: 'rtk', deps: d ? [d] : [], shots: c ? [c] : [] };
}
function formHTML(d) {
  const types = [
      ['rtk', 'Retake'],
      ['note', T('Remark')],
      ['todo', T('To do')]
    ],
    it = cur(),
    f = S.form,
    deps = DEPTS[it.kind].filter(x => required(it).includes(x)),
    sh = it.shots && it.shots.length > 1 ? it.shots : [];
  // Which departments, which shots of a block: several of each (a note per shot).
  const chips = deps.length
    ? `<div class="r chips"><span class="faint">${T('Departments')}</span>${deps.map(x => `<button class="btn sm" data-fdep="${x}" aria-pressed="${f.deps.includes(x)}">${esc(LBL[x])}</button>`).join('')}</div>`
    : '';
  const shots = sh.length
    ? `<div class="r chips"><span class="faint">${T('Shots')}</span><button class="btn sm" data-fshot="" aria-pressed="${!f.shots.length}">${T('Whole block')}</button>${sh.map(x => `<button class="btn sm" data-fshot="${esc(x)}" aria-pressed="${f.shots.includes(x)}">${esc(x)}</button>`).join('')}</div>`
    : '';
  return `<div class="form"><span class="join">${types.map(([k, l]) => `<button class="btn sm" data-ftype="${k}" aria-pressed="${f.type === k}">${l}</button>`).join('')}</span>
    ${chips}${shots}
    <label class="field ta"><textarea id="f-txt" rows="2" placeholder="${f.type === 'rtk' ? (f.deps.length === 1 ? T("What's wrong on {dept}…", { dept: LBL[f.deps[0]] }) : T("What's wrong…")) : T('A remark, nothing sent back…')}" aria-label="${T('Text')}"></textarea></label>
    <div class="r"><label class="field" style="width:calc(110px*var(--scale))"><span class="faint">f</span><input id="f-fr" value="${!rendered(it) ? '' : S.rangeStart != null ? fNo(Math.min(S.rangeStart, S.frame)) + '-' + fNo(Math.max(S.rangeStart, S.frame)) : fNo(S.frame)}" aria-label="${T('Frame or range')}"></label>
    <span class="faint" style="font-size:var(--fs-s)">${T('Ctrl+Enter')}</span><span style="flex:1"></span><button class="btn sm" data-fcancel>${T('Cancel')}</button><button class="btn sm ${f.type === 'rtk' ? 'alert' : 'primary'}" data-fok>${T('Write')}</button></div></div>`;
}
function notesHTML(it) {
  let ns = [...it.myNotes.map(n => ({ ...n, mine: 1 })), ...it.notes];
  if (S.noteFilter === 'open') ns = ns.filter(n => !n.done);
  if (S.noteFilter === 'frame')
    ns = ns.filter(n => n.frames).sort((a, b) => parseInt(a.frames.slice(1)) - parseInt(b.frames.slice(1)));
  const gen = S.form && S.form.dept === '' ? `<div class="dept">${formHTML('')}</div>` : '';
  return `<div class="sec"><div class="sec-h">${T('Notes')}<span class="n">${openNotes(it)}</span><span class="sp"></span>
      <span class="join">${[
        ['open', T('Open')],
        ['frame', T('At a frame')],
        ['all', T('All')]
      ]
        .map(
          ([k, l]) =>
            `<button class="btn sm" data-nf="${k}" aria-pressed="${S.noteFilter === k}">${l}</button>`
        )
        .join('')}</span>
      ${S.review ? `<button class="btn sm" data-gen title="${T('A retake or a remark on no department (X)')}">${ic('b-add')}${T('Note')}</button>` : ''}</div>${gen}
    ${ns.length ? ns.map(n => noteHTML(it, n)).join('') : `<span class="faint">${S.noteFilter === 'all' ? T('No note.') : S.noteFilter === 'frame' ? T('No note at a frame.') : T('No open note.')}</span>`}</div>`;
}
/* An entry of mine, sent or not (a note, a reply): a small pencil by its date opens it to edit, Delete inside (asked twice).
   Sent ones change through the review (edit / delete, by their author); not sent yet, they change at once. */
function entryEd(it, e, key) {
  const ed = !e.mine && e.id && e.id in it.edits ? it.edits[e.id] : undefined;
  // Its author's to change -- or anyone's under a validation role (not the team's).
  const anyRole = !!(S.review && S.review.role !== TEAM && e.id);
  return {
    key,
    ed,
    del: ed === null,
    txt: typeof ed === 'string' ? ed : e.text,
    own: e.mine || ownNote(e) || anyRole
  };
}
const penHTML = x =>
  x.own && !x.del && S.nedit !== x.key
    ? `<button class="btn flat icon xs" data-nedit="${esc(x.key)}" aria-label="${T('Edit')}" title="${T('Edit (or delete)')}">${ic('b-greasepencil')}</button>`
    : '';
const edFormHTML = (x, sent) =>
  `<div class="form"><label class="field ta"><textarea id="ne-txt" rows="3" aria-label="${T('Text')}">${esc(x.txt || '')}</textarea></label><div class="r">${sent ? `<button class="btn sm alert" data-ndel="${esc(x.key)}" title="${T('Delete it (a note: its replies too)')}">${ic('b-x')}${T('Delete')}</button>` : ''}<span style="flex:1"></span><button class="btn sm" data-necancel>${T('Cancel')}</button><button class="btn sm primary" data-nesave="${esc(x.key)}">${T('Save')}</button></div></div>`;
const edSay = x =>
  x.ed !== undefined
    ? ` <span class="tag you">${x.del ? T('deleted, not sent yet') : T('edited, not sent yet')}</span><button class="btn flat icon xs" data-neundo="${esc(x.key)}" aria-label="${T('Take my change back')}" title="${T('Take my change back')}">${ic('b-loop_back')}</button>`
    : '';
function noteHTML(it, n) {
  const reps = [
    ...(n.replies || []),
    ...(it.myReplies[n.id] || []).map((r, k) => ({ ...r, mine: 1, rk: k }))
  ];
  const rf =
    S.reply === n.id
      ? `<div class="form"><label class="field ta"><textarea id="r-txt" rows="2" placeholder="${T('Your reply…')}" aria-label="${T('Reply')}"></textarea></label><div class="r"><span style="flex:1"></span><button class="btn sm" data-rcancel>${T('Cancel')}</button><button class="btn sm primary" data-rok="${n.id}">${T('Reply')}</button></div></div>`
      : '';
  const who = n.type === 'rtk' ? (n.team ? T('team') : n.role || T('team')) : '';
  const x = entryEd(it, n, n.mine ? 'm' + n.at : n.id);
  const repHTML = r => {
    const y = entryEd(it, r, r.mine ? 'r' + n.id + ':' + r.rk : r.id);
    return `<div class="${y.del ? 'gone' : ''}"><div class="h"><span class="who">${esc(r.author)}</span><span>${fmtD(r.date)}</span>${r.mine ? `<span class="tag you">${T('you')}</span><button class="btn flat icon xs" data-unreply="${n.id}" title="${T('Take my reply back')}">${ic('b-loop_back')}</button>` : ''}${penHTML(y)}</div>
      ${S.nedit === y.key ? edFormHTML(y, !r.mine) : `<div class="t">${esc(y.txt)}${edSay(y)}</div>`}</div>`;
  };
  return `<div class="nt ${n.type} ${n.done ? 'closed' : ''} ${n.mine ? 'mine' : ''} ${x.del ? 'gone' : ''} ${x.ed !== undefined ? 'chg' : ''}">
    <div class="h"><span class="type ${n.type}">${n.type === 'rtk' ? 'RTK' : n.type === 'todo' ? T('to do') : 'note'}</span>${(n.deps || []).length ? n.deps.map(d => LBL[d] || d).join(', ') : '<span>' + T('no department') + '</span>'}${who ? `<span>· ${esc(who)}</span>` : ''}
      ${n.frames ? `<button class="chip-frame" data-goto="${parseInt(String(n.frames).replace(/\D+/, ''))}" title="${T('Go to {frame}', { frame: esc(n.frames) })}">${esc(n.frames)}</button>` : ''}${n.mine ? '<span class="tag you">' + T('you') + '</span>' : ''}<span class="sp"></span><span class="who">${esc(n.author && n.author !== 'unknown' ? n.author : '')}</span><span>${fmtD(n.date)}</span>${n.done ? '<span>· ' + T('closed') + '</span>' : ''}${penHTML(x)}</div>
    ${S.nedit === x.key ? edFormHTML(x, !n.mine) : `<div class="t ${x.txt ? '' : 'empty'}">${x.txt ? esc(x.txt) : T('(no text)')}${edSay(x)}</div>`}
    ${reps.length ? `<div class="rep">${reps.map(repHTML).join('')}</div>` : ''}
    ${rf}
    <div class="f">${fixHTML(it, n)}${n.mine ? `<button class="btn sm flat" data-unnote="${n.at}" title="${T('Take back')}">${ic('b-loop_back')}${T('Take back')}</button>` : ''}${!n.mine && S.reply !== n.id ? `<button class="btn sm flat" data-reply="${n.id}" ${S.review ? '' : 'disabled'} title="${S.review ? T('Reply (R)') : T('Start a review to reply')}">${ic('b-file_parent')}${T('Reply')}</button>` : ''}</div>
  </div>`;
}
const verOf = f => (String(f).match(/_(v\d+(?:-stable)?)\.blend$/) || [])[1] || f;
function linksHTML(it) {
  const ins = it.links,
    by = it.linkedBy;
  const byOld = n => {
    const o = items.find(i => i.name === n);
    const l = o && o.links.find(x => x.name === it.name);
    return l && l.newer ? l : null;
  };
  const nodeA = l =>
    `<div class="node ${l.newer ? 'old' : ''}" data-goto-file="${l.name}" title="${T('Open {name}', { name: l.name })}"><div class="nh">${ic('b-asset_manager')}<span>${l.name}</span></div><div class="nb"><div class="sock">${verOf(l.file)}${l.newer ? ` · <b style="color:var(--st-rtk)">${T('{version} exists', { version: verOf(l.newer) })}</b>` : ''}</div><div class="sock out ${l.newer ? 'bad' : 'ok'}" data-o="${l.name}"><i></i>${T('Link')}</div></div></div>`;
  const target = `<div class="node shot cur"><div class="nh">${ic(it.kind === 'shot' ? 'b-camera_data' : 'b-asset_manager')}<span>${it.name}</span></div><div class="nb">
    ${ins.map(l => `<div class="sock in ${l.newer ? 'bad' : ''}" data-i="${l.name}"><i></i>${l.name}</div>`).join('')}${by.length ? `<div class="sock out" data-o="__cur"><i></i>${T('Linked by')}</div>` : ''}</div></div>`;
  const nodeB = n => {
    const o = byOld(n);
    return `<div class="node shot" data-goto-file="${n}" title="${T('Open {name}', { name: n })}"><div class="nh">${ic('b-camera_data')}<span>${n}</span></div><div class="nb"><div class="sock in ${o ? 'bad' : ''}" data-i="by:${n}"><i></i>${o ? T('links {version} (old)', { version: verOf(o.file) }) : T('up to date')}</div></div></div>`;
  };
  const old = ins.filter(l => l.newer).length + by.filter(byOld).length;
  const graph =
    !ins.length && !by.length
      ? `<div class="empty" style="padding:24px">${T('{name} links no file and no file links it.', { name: it.name })}</div>`
      : `<div class="nodes-wrap"><div class="nodes" id="nodes"><svg class="wires" id="wires"></svg>${ins.length ? `<div class="ncol">${ins.map(nodeA).join('')}</div>` : ''}<div class="ncol">${target}</div>${by.length ? `<div class="ncol">${by.map(nodeB).join('')}</div>` : ''}</div></div>`;
  return `<div class="sec"><div class="sec-h">${T('Links')}<span class="sp"></span><span class="faint" style="text-transform:none;letter-spacing:0">${T('{n} linked · linked by {m}', { n: ins.length, m: by.length })}</span></div>
    ${graph}<p class="faint" style="margin:0;font-size:var(--fs-s)">${T('Red wire: a newer stable exists. Click a node: opens the file.')}</p>
    ${old ? `<div class="pacts"><button class="btn primary live-only" data-relink title="${T('Makes a -relink version linking the last stables, without opening it, overwriting nothing')}">${ic('b-linked')}${T('Update the links ({n})', { n: old })}</button></div>` : ''}</div>`;
}
function wirePath(x1, y1, x2, y2, ym) {
  if (x2 >= x1 - 4) {
    const dx = Math.max(30, (x2 - x1) * 0.5);
    return `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
  }
  const k = 16;
  return `M${x1},${y1} C${x1 + k},${y1} ${x1 + k},${ym} ${x1},${ym} L${x2},${ym} C${x2 - k},${ym} ${x2 - k},${y2} ${x2},${y2}`;
}
function drawWires() {
  const box = $('#nodes');
  if (!box) return;
  const R = box.getBoundingClientRect();
  let p = '';
  const link = (o, n, c) => {
    if (!o || !n) return;
    const a = o.getBoundingClientRect(),
      b = n.getBoundingClientRect();
    const x1 = a.left + a.width / 2 - R.left,
      y1 = a.top + a.height / 2 - R.top,
      x2 = b.left + b.width / 2 - R.left,
      y2 = b.top + b.height / 2 - R.top;
    const no = o.closest('.node').getBoundingClientRect(),
      nn = n.closest('.node').getBoundingClientRect();
    const ym = (Math.min(no.bottom, nn.bottom) + Math.max(no.top, nn.top)) / 2 - R.top;
    const d = wirePath(x1, y1, x2, y2, ym);
    p += `<path d="${d}" fill="none" style="stroke:var(--wire-edge)" stroke-width="4.5"/><path d="${d}" fill="none" style="stroke:${c}" stroke-width="2.4"/>`;
  };
  box.querySelectorAll('[data-i]').forEach(n => {
    const k = n.dataset.i,
      c = n.classList.contains('bad') ? 'var(--st-rtk)' : 'var(--wire)';
    link(
      k.startsWith('by:') ? box.querySelector('[data-o="__cur"] i') : box.querySelector(`[data-o="${k}"] i`),
      n.querySelector('i'),
      c
    );
  });
  const w = $('#wires');
  if (w) w.innerHTML = p;
}
/* Who has a file open now (live): "léa (a1b2c3d4)". */
const openBy = it =>
  (M.presence || [])
    .filter(p => p.file === it.file || p.file.startsWith(it.name + '_'))
    .map(p => `${p.user} (${p.machine})`);
/* What the edit has of a file (editing/rushes/rushes.json): its render, by whom, when. */
const rushIs = (it, v) => !!(it.rush && v && v.folder && it.rush.render === v.folder.split('/').pop());
const rushSay = it =>
  it.rush
    ? T('In the edit since {date}, pushed by {who}', { date: fmtD(it.rush.at), who: it.rush.by || '?' })
    : '';
function filesHTML(it) {
  // To the half hour: an estimate, not a count to the minute.
  const w = it.work ? T('about {h} h', { h: Math.max(0.5, Math.round(it.work / 1800) / 2) }) : '–';
  const row = (k, v, btn = '') =>
    `<div class="prop"><span class="k">${k}</span><span class="v"><span class="ro" title="${esc(v)}">${esc(v || '–')}</span>${btn}</span></div>`;
  const pr = F.presets.find(p => p[0] === S.preset) || F.presets[0];
  return `<div class="sec"><div class="sec-h">${T('Files')}</div>
    ${row(T('Wip file'), it.file ? it.file + '.blend' : '')}${openBy(it).length ? row(T('Open now'), openBy(it).join(', ')) : ''}${it.saved && it.saved.by ? row(T('Saved last'), T('{who}, {date}', { who: it.saved.by, date: fmtD(it.saved.at) })) : ''}${row('Stable', it.stableFile ? it.stableFile + '.blend' : '')}
    ${row(T('Work time'), w)}<p class="faint" style="margin:0;font-size:var(--fs-s)">${T('Every session that saved, every version, everyone together.')}</p>
    ${it.shots && it.shots.length ? row(T('Shots of the block'), it.shots.join(' · ')) : ''}</div>
  <div class="sec"><div class="sec-h">${T('Renders')}</div>
    ${it.versions.length ? it.versions.map((v, n) => `<div class="prop"><span class="k">${n === 0 ? T('Last') : ''}</span><span class="v"><span class="ro">${esc(verLab(v))}</span><button class="btn icon" data-ver="${n}" aria-label="${T('Watch')}" title="${T('Watch this version')}">${ic('b-play')}</button><button class="btn icon" data-act="player" aria-label="${T("This machine's player")}" title="${T("Open in this machine's player")}">${ic('b-file_movie')}</button>${v.video ? `<button class="btn icon live-only ${rushIs(it, v) ? 'rush-on' : ''}" data-push="${n}" aria-pressed="${rushIs(it, v)}" aria-label="${T('Push to the edit')}" title="${rushIs(it, v) ? esc(rushSay(it)) + ' · ' + T('Push it again') : T('Push to the edit: editing/rushes/, under its name without version')}">${ic('b-export')}</button>` : ''}</span></div>`).join('') : '<span class="faint">' + T('No render.') + '</span>'}
    ${it.rush && !it.versions.some(v => rushIs(it, v)) ? row(T('In the edit'), it.rush.render, '') : ''}
    ${row('Farm', it.farm ? it.farm.text : T('no job'))}</div>
  <div class="pacts live-only"><button class="btn primary" data-render>${ic('b-render_animation')}${T('Render…')}</button></div>`;
}
function headHTML(it) {
  const d = it.descEdit !== undefined ? it.descEdit : it.desc;
  const desc = S.editDesc
    ? `<span class="desc-ed"><label class="field"><input id="desc-in" value="${esc(d)}" aria-label="${T('Description')}"></label><button class="btn sm primary" data-descok>OK</button><button class="btn sm" data-desccancel>${T('Cancel')}</button></span>`
    : `<span class="d" title="${esc(d)}">${esc(d || (S.review ? T('Add a description') : ''))}${it.descEdit !== undefined ? ' <span class="tag you">' + T('you') + '</span>' : ''}${S.review ? `<button class="ed" data-desc aria-label="${T('Edit the description')}" title="${T('Edit the description')}">${ic('b-greasepencil')}</button>` : ''}</span>`;
  return `<span class="phead"><span class="pname">${it.name}</span>${desc}</span>
    <button class="btn flat icon live-only" data-render aria-label="${T('Render')}" title="${T('Render: send to the farm, with its settings')}">${ic('b-render_animation')}</button>
    <button class="btn flat icon" data-act="copy" aria-label="${T('Copy a link to this file')}" title="${T('Copy a link to this file')}">${ic('b-linked')}</button>
    <span class="anchor"><button class="btn flat icon" data-settings aria-label="${T('File settings')}" title="${T('Settings: required departments, set aside')}">${ic('b-preferences')}</button></span>
    <button class="btn flat icon live-only" data-act="blender" aria-label="${T('Open in Blender')}" title="${T('Open in Blender')}">${ic('b-blender')}</button>
    <button class="btn flat icon live-only" data-act="blendfolder" aria-label="${T('Open its folder')}" title="${T("Its folder: the .blend's, in this machine's file browser")}">${ic('b-file_folder')}</button>
    ${(it.versions || []).length ? `<button class="btn flat icon live-only" data-act="renderfolder" aria-label="${T('Open its render folder')}" title="${T("Its render folder, in this machine's file browser")}">${ic('b-render_result')}</button>` : ''}
    <span class="join"><button class="btn icon" id="pp-prev" aria-label="${T('Previous file')}" title="${T('Previous (↑)')}">${ic('b-tria_up')}</button><button class="btn icon" id="pp-next" aria-label="${T('Next file')}" title="${T('Next (↓)')}">${ic('b-tria_down')}</button></span>
    <button class="btn flat icon only-mid only-port" data-pmax aria-label="${T('The detail on the whole width')}"></button>
    <button class="btn flat icon only-phone" id="pp-close" aria-label="${T('Close')}" title="${T('Close (Esc)')}">${ic('b-x')}</button>`;
}
function renderProps() {
  const H = $('#p-head'),
    TB = $('#ptabs'),
    B = $('#pbody');
  if (S.ws === 'farm') {
    TB.hidden = true;
    renderFarmDetail(H, B);
    return;
  }
  TB.hidden = false;
  const it = cur();
  if (!it) {
    H.innerHTML = '<span class="phead"><span class="pname">' + T('Nothing selected') + '</span></span>';
    TB.innerHTML = '';
    B.innerHTML = '<div class="empty">' + T('Pick a file in the list.') + '</div>';
    return;
  }
  H.innerHTML = headHTML(it);
  window.MPPanes && MPPanes.sync();
  const nr = openRtk(it),
    nn = openNotes(it),
    nl = it.links.length + it.linkedBy.length,
    lo = it.links.some(l => l.newer);
  TB.innerHTML = [
    [
      'plan',
      it.kind === 'shot' ? 'b-camera_data' : 'b-asset_manager',
      it.kind === 'shot' ? T('Shot') : T('Asset')
    ],
    ['notes', 'i-note', T('Notes'), nn, nr ? 'r' : ''],
    ['links', 'b-linked', T('Links'), nl, lo ? 'r' : ''],
    ['files', 'b-file', T('Files and renders')],
    ['versions', 'b-sorttime', T('Versions')],
    ['renders', 'b-render_result', T('Render history')]
  ]
    .map(
      ([k, i, l, n, c]) =>
        `<button class="vtab" role="tab" data-tab="${k}" aria-selected="${S.tab === k}" title="${l}" aria-label="${l}">${ic(i)}${n ? `<span class="cnt ${c || ''}">${n}</span>` : ''}</button>`
    )
    .join('');
  const om = it.setAside !== undefined ? it.setAside : it.omit;
  const tags = [
    om && om.state
      ? `<span class="tag omit">${om.state === 'cancelled' ? T('Cancelled') : T('On hold')}${om.reason ? ' · ' + esc(om.reason) : ''}</span>`
      : '',
    it.toCheck
      ? `<span class="tag check">${ic('b-hide_off')}${T('render to check')}</span><button class="btn sm" data-checked title="${T('Checked: no longer "to check"')}">${T('Checked')}</button>`
      : '',
    it.outdated ? `<span class="tag check">${ic('b-error')}${T('render outdated')}</span>` : '',
    it.farm
      ? `<span class="tag ${it.farm.state === 'failed' ? 'fail' : ''}">farm ${esc(it.farm.text)}</span>`
      : ''
  ]
    .filter(Boolean)
    .join('');
  let h = '';
  if (S.tab === 'plan') {
    const req = DEPTS[it.kind].filter(d => required(it).includes(d));
    h = `<div class="sec">${stageHTML(it)}${tags ? `<div class="pacts tags">${tags}</div>` : ''}</div>
     <div class="sec"><div class="sec-h">${T('Departments')}<span class="sp"></span>${S.review && S.review.role !== TEAM ? `<button class="btn sm ok" data-valall title="${T('Validate every done department (V)')}">${ic('b-checkmark')}${T('All the done')}</button>` : ''}</div>
     ${req.length ? req.map(d => deptHTML(it, d)).join('') : '<span class="faint">' + T('No department required.') + '</span>'}${!S.review ? '<p class="faint" style="margin:0;font-size:var(--fs-s)">' + T('Start a review to validate, ask for a retake or assign.') + '</p>' : ''}</div>
     <button class="notes-link" data-tab="notes">${ic('i-note')}<span>${T('Notes')}</span>${nr ? `<span class="tag rtk">${nr} RTK</span>` : ''}<span class="faint">${T('{n} open', { n: nn })}</span><span class="sp"></span>${ic('b-tria_right')}</button>`;
  }
  if (S.tab === 'notes') h = notesHTML(it);
  if (S.tab === 'links') h = linksHTML(it);
  if (S.tab === 'files') h = filesHTML(it);
  if (S.tab === 'versions') h = versionsHTML(it);
  if (S.tab === 'renders') h = rendersHTML(it);
  B.innerHTML = h;
  if (S.tab === 'links') requestAnimationFrame(drawWires);
  if (S.tab === 'versions') requestAnimationFrame(drawChain);
}
