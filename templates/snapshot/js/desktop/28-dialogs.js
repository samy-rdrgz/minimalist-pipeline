/* ---------- Dialogs and popovers ---------- */
/* A menu under its button, as tall as its items while the window has the room: above the button when
   there's more room there; scrolled only past the window's height. */
function placeMenu(b, m) {
  m.classList.add('fx');
  m.style.left = '0px';
  m.style.top = '0px';
  m.style.maxHeight = '';
  const r = b.getBoundingClientRect(),
    w = m.offsetWidth,
    h = m.scrollHeight + (m.offsetHeight - m.clientHeight),
    below = innerHeight - 8 - (r.bottom + 4),
    above = r.top - 4 - 8;
  let x = m.classList.contains('right') ? r.right - w : r.left;
  x = Math.max(8, Math.min(x, innerWidth - w - 8));
  let y;
  if (h <= below || below >= above) {
    y = r.bottom + 4;
    if (h > below) m.style.maxHeight = Math.max(120, below) + 'px';
  } else {
    if (h > above) m.style.maxHeight = above + 'px';
    y = r.top - 4 - Math.min(h, above);
  }
  m.style.left = x + 'px';
  m.style.top = y + 'px';
}
/* A popover by its button: under it, its right edge on the button's, held inside the window (a button at the
   window's right edge or left edge alike); above it when there's no room below. */
function placePop(p, b) {
  p.classList.add('fx');
  const r = b.getBoundingClientRect(),
    w = p.offsetWidth,
    h = p.offsetHeight;
  let x = r.right - w;
  if (x < 8) x = r.left;
  x = Math.max(8, Math.min(x, innerWidth - w - 8));
  let y = r.bottom + 8;
  if (y + h > innerHeight - 8) y = r.top - h - 8 >= 8 ? r.top - h - 8 : Math.max(8, innerHeight - 8 - h);
  p.style.left = x + 'px';
  p.style.top = y + 'px';
}
const stillHTML = (it, d) => {
  const f = it.flags[d] || {};
  if (!S.review || !f.to_redo)
    return it.still && it.still[d] ? '<span class="tag you">' + T('still done · you') + '</span>' : '';
  return `<button class="btn sm ${it.still[d] ? '' : 'tool'}" data-still="${d}" aria-pressed="${!!it.still[d]}" title="${T("To redo: {why}. Still done: the work holds, it's not a validation", { why: esc(f.to_redo) })}">${ic('b-checkmark')}${T('Still done')}</button>`;
};
const fixHTML = (it, n) => {
  if (!S.review || n.mine || n.type === 'note') return '';
  if (n.done) {
    // Closed: opened again (it counts as open once sent).
    const re = it.fixed[n.id] === 'reopen';
    return `<button class="btn sm ${re ? '' : 'flat'}" data-fix="${n.id}" data-reopen aria-pressed="${re}" title="${re ? T('Cancel') : T('Open it again: applied when your review is imported')}">${ic('b-loop_back')}${re ? T('Reopened · you') : T('Reopen')}</button>`;
  }
  const on = !!it.fixed[n.id];
  return `<button class="btn sm ${on ? 'ok' : 'flat'}" data-fix="${n.id}" aria-pressed="${on}" title="${on ? T('Cancel') : n.type === 'rtk' ? T('Mark fixed: applied when your review is imported') : T('Mark done: applied when your review is imported')}">${ic('b-checkmark')}${on ? T('Fixed · you') : n.type === 'rtk' ? T('Mark fixed') : T('Mark done')}</button>`;
};
/* The sub-shots of a block with a video of their own, in its order (a whole-block render
   plays them all at once: none then). */
const ownShots = it =>
  it.versions.some(v => !(v.shot || '')) ? [] : (it.shots || []).filter(s => it.versions.some(v => v.shot === s));
/* Next at a video's end (Watch large): a block's next sub-shot, else the next file of the list
   as filtered (To check, a search... -- across sequences); Play the sequence stops at its own. */
function seqNext() {
  const it = cur(),
    sh = ownShots(it),
    k = sh.indexOf(shotOf(it));
  if (k >= 0 && k < sh.length - 1) {
    S.playing = false;
    S.shot[it.name] = sh[k + 1];
    S.ver[it.name] = 0;
    S.frame = 1;
    renderProps();
    renderWide();
    togglePlay();
    return;
  }
  const only = typeof S.seqPlay === 'string' ? S.seqPlay : null,
    L = playList(it).filter(i => !omitted(i) && (!only || groupOf(i) === only)),
    n = L.findIndex(i => i.name === it.name);
  if (n < 0 || n >= L.length - 1) {
    // The last one: stopped there (the choice Next kept for the next time).
    clearInterval(playT);
    S.playing = false;
    syncPlay();
    msg(only ? T('End of the sequence {seq}', { seq: only }) : T('End of the list'));
    renderWide();
    return;
  }
  // The next one from its start (a block: its first sub-shot), playing on.
  const nx = L[n + 1];
  delete S.shot[nx.name];
  S.ver[nx.name] = 0;
  S.playing = false;
  select(nx.name, { open: false });
  togglePlay();
}
const RF = {};
const rform = it =>
  (RF[it.name] = RF[it.name] || {
    // A newer wip than the stable: its own choice; else the stable is the latest.
    ver: it.stable ? 'stable' : 'last',
    dept: startDept(it),
    preset: deptPreset(it, startDept(it)),
    prio: 10,
    mode: 'all',
    sound: 'on',
    off: {},
    start: '',
    end: '',
    frames: false
  });
function renderDlg() {
  const it = cur(),
    f = rform(it),
    dl = $('#dlg');
  const seg = (k, v, l) =>
    `<button class="btn sm" data-rf="${k}" data-v="${v}" aria-pressed="${f[k] === v}">${l}</button>`;
  const job = F.jobs.find(
    j => !j.archived && (j.state === 'running' || j.state === 'waiting') && j.file.startsWith(it.name + '_')
  );
  const pr = F.presets.find(p => p[0] === f.preset) || F.presets[0];
  dl.hidden = false;
  dl.innerHTML = `<div class="dlg-in rnd" role="dialog" aria-modal="true" aria-labelledby="rd-t"><h3 id="rd-t">${ic('b-render_animation')} ${T('Render {name}', { name: esc(it.name) })}</h3>
    ${job ? `<p class="tag check" style="align-self:flex-start">${T('Already in the farm: {what}', { what: esc(TS(job.text)) + (job.total ? ' · ' + job.done + '/' + job.total : '') })}</p>` : ''}
    <div class="prop"><span class="k">${T('Version')}</span><span class="v"><span class="join full" style="flex:1">${it.stable ? seg('ver', 'stable', it.wip ? T('Last stable · {v}', { v: esc(it.stable) }) : T('Latest, stable · {v}', { v: esc(it.stable) })) : ''}${it.wip || !it.stable ? seg('ver', 'last', T('Latest · {v}', { v: esc(it.wip || it.stable || '') })) : ''}</span></span></div>
    <div class="prop"><span class="k">${T('Department')}</span><span class="v"><span class="anchor" style="flex:1;min-width:0"><button class="enum" style="width:100%" data-menu="m-rdept" aria-haspopup="true" aria-expanded="false"><span class="lb">${f.dept ? esc(f.dept) : T('No department')}</span>${ic('b-downarrow_hlt')}</button>
      <div class="menu" id="m-rdept" hidden role="menu">${['', ...(DEPTS[it.kind] || [])].map(d => `<button class="mi" data-rdept="${esc(d)}"><span class="ck">${d === f.dept ? ic('b-checkmark') : ''}</span><span class="lbl">${d ? esc(d) : T('No department')}</span></button>`).join('')}</div></span></span></div>
    <div class="prop"><span class="k">${T('Pre-render script')}</span><span class="v"><span class="anchor" style="flex:1;min-width:0"><button class="enum" style="width:100%" data-menu="m-rpreset" aria-haspopup="true" aria-expanded="false"><span class="lb">${esc(pr[1])}</span>${ic('b-downarrow_hlt')}</button>
      <div class="menu" id="m-rpreset" hidden role="menu">${presetsFor(f.dept, it.kind)
        .map(
          p =>
            `<button class="mi" data-rpreset="${esc(p[0])}"><span class="ck">${p[0] === f.preset ? ic('b-checkmark') : ''}</span><span class="lbl">${esc(p[1])}</span></button>`
        )
        .join('')}</div></span></span></div>
    <div class="prop"><span class="k">Frames</span><span class="v">${f.frames ? `<label class="field" style="width:96px"><span class="faint">${T('from')}</span><input data-rfn="start" value="${esc(f.start)}" placeholder="${T('file')}" aria-label="${T('First frame')}"></label><label class="field" style="width:96px"><span class="faint">${T('to')}</span><input data-rfn="end" value="${esc(f.end)}" placeholder="${T('file')}" aria-label="${T('Last frame')}"></label><button class="btn sm flat" data-rft>${T("the file's own")}</button>` : `<span class="dim">${T("the file's own")}</span><button class="btn sm tool" data-rft>${T('Choose')}</button>`}</span></div>
    <div class="prop"><span class="k">${T('Priority')}</span><span class="v"><span class="prio"><button class="btn sm icon" data-rprio="-1" aria-label="${T('Lower')}">−</button><b>${f.prio}</b><button class="btn sm icon" data-rprio="1" aria-label="${T('Higher')}">+</button><span class="faint">${T('the highest goes first')}</span></span></span></div>
    <div class="prop"><span class="k">${T('Machines')}</span><span class="v"><span class="join">${seg('mode', 'all', T('All'))}${seg('mode', 'single', T('Only one'))}</span></span></div>
    <div class="prop"><span class="k">${T('Sound')}</span><span class="v"><button class="swi" role="switch" data-rfsw="sound" aria-checked="${f.sound !== 'off'}" title="${T("The scene's sound (sequencer, speakers) in the video")}"><span class="lbl">${f.sound !== 'off' ? T('With sound') : T('Without sound')}</span><span class="tg"></span></button></span></div>
    ${it.shots && it.shots.length > 1 ? `<div class="prop"><span class="k">${T('Shots')}</span><span class="v"><span class="join">${it.shots.map(x => `<button class="btn sm" data-rshot="${x}" aria-pressed="${!f.off[x]}">${x}</button>`).join('')}</span></span></div>` : ''}
    <div class="acts">${it.kind === 'shot' ? `<button class="btn" data-rprev title="${T('The last videos of each shot of {seq}, end to end', { seq: it.group })}">${T('Preview {seq}', { seq: it.group })}</button>` : ''}<span style="flex:1"></span><button class="btn" data-dclose>${T('Cancel')}</button><button class="btn primary" data-rsend>${ic('b-export')}${T('Send to the farm')}</button></div></div>`;
}
const NEWS = [];
let newsSeen = 0;
/* What's new (live): a change seen in the data Blender sends (applyData()). */
function pushNews(k, n, h, x) {
  NEWS.unshift({ k, n, h, x, at: new Date().toLocaleTimeString(DTL(), HM) });
  renderNewsBtn();
  if (S.notifSys && window.Notification && Notification.permission === 'granted') {
    try {
      new Notification(n + ' · ' + h, { body: x });
    } catch (_) {}
  }
}
function renderNewsBtn() {
  if (isMob()) {
    if (!S.m.sheet) mRender();
    return;
  }
  const b = $('#news-b');
  if (!b) return;
  const n = NEWS.length - newsSeen;
  b.querySelector('.cnt').textContent = n;
  b.querySelector('.cnt').hidden = !n;
}
/* The pop's content: each line its own cross (deleted from the list), all at once at the top. */
function newsHTML() {
  const IC = { rtk: '--st-rtk', note: '--text-2', render: '--st-done', ok: '--st-val' };
  return `<h4>${T("What's new")}${NEWS.length ? `<button class="btn sm flat" data-newsclr>${T('Clear all')}</button>` : ''}</h4>${NEWS.length ? NEWS.map((x, k) => `<div class="newsr"><button class="newsi" data-goto-file="${x.n}"><span class="dt" style="background:var(${IC[x.k]})"></span><span class="tx"><span class="h"><b>${esc(x.n)}</b><span class="faint">${x.at}</span></span>${esc(x.h)}<small>${esc(x.x)}</small></span></button><button class="btn sm flat icon newsx" data-newsx="${k}" aria-label="${T('Delete')}" title="${T('Delete')}">${ic('b-x')}</button></div>`).join('') : `<p class="hint">${T('Nothing new since the page opened: notes, retakes, validations and renders come here.')}</p>`}
    <button class="swi" role="switch" id="notif-sys" aria-checked="${!!S.notifSys}"><span class="lbl">${T('Notify me in the system too')}</span><span class="tg"></span></button>`;
}
/* One line out of What's new (k: its place), or all of them (k null): the list redrawn where it is. */
function newsDel(k) {
  if (k == null) NEWS.length = 0;
  else NEWS.splice(k, 1);
  newsSeen = NEWS.length;
  renderNewsBtn();
  const p = document.querySelector('.pop.news');
  if (p) p.innerHTML = newsHTML();
}
function newsPop(btn) {
  const old = document.querySelector('.pop.news');
  if (old) {
    old.remove();
    return;
  }
  newsSeen = NEWS.length;
  renderNewsBtn();
  const p = document.createElement('div');
  p.className = 'pop news';
  p.setAttribute('role', 'dialog');
  p.setAttribute('aria-label', T("What's new"));
  p.innerHTML = newsHTML();
  btn.parentElement.appendChild(p);
  placePop(p, btn);
}
const TOUR = [
  ['#ws', T('The spaces'), T('Shots, Assets, Links, Breakdown and Farm: a click changes the whole page.')],
  [
    '#quick',
    T('The filters'),
    T('Retakes, notes, to validate: a click filters the list. "Filters" opens the rest.')
  ],
  [
    '#list .row',
    T('A file'),
    T('Each diamond is a department: its shape says its state, its corner what comes on top.')
  ],
  ['#ptabs', T('The detail'), T('Shot, Notes, Links, Versions, Render history: the file selected, in tabs.')],
  [
    '[data-wide]',
    T('Watch large'),
    T('The video large, the departments beside it: retakes written as you watch.')
  ],
  [
    '#review-slot',
    T('Reviewing'),
    T('Your name and your role, then validate, send back, assign. Send… gives the file to import in Blender.')
  ],
  ['#help-b', T('The legend'), T('The states, the keys, and this tour.')]
];
let tourAt = -1;
function tour(n) {
  document.querySelectorAll('.tour-hl').forEach(e => e.classList.remove('tour-hl'));
  $('#tour')?.remove();
  if (n < 0 || n >= TOUR.length) {
    tourAt = -1;
    return;
  }
  let el = document.querySelector(TOUR[n][0]);
  if (!el || !el.offsetParent) {
    if (n < TOUR.length - 1) return tour(n + 1);
    return tour(-1);
  }
  tourAt = n;
  el.scrollIntoView({ block: 'nearest' });
  el.classList.add('tour-hl');
  const r = el.getBoundingClientRect();
  const b = document.createElement('div');
  b.id = 'tour';
  b.className = 'tour';
  b.setAttribute('role', 'dialog');
  b.setAttribute('aria-live', 'polite');
  b.innerHTML = `<b>${TOUR[n][1]}</b><p>${TOUR[n][2]}</p><div class="acts"><span class="faint">${n + 1} / ${TOUR.length}</span><span style="flex:1"></span>${n < TOUR.length - 1 ? '<button class="btn sm flat" data-tour="end">' + T('Skip') + '</button><button class="btn sm primary" data-tour="next">' + T('Next') + '</button>' : '<button class="btn sm primary" data-tour="end">' + T('Done') + '</button>'}</div>`;
  document.body.appendChild(b);
  const w = b.offsetWidth,
    h = b.offsetHeight;
  let x = Math.min(Math.max(8, r.left), innerWidth - w - 8),
    y = r.bottom + 10;
  if (y + h > innerHeight - 8) y = Math.max(8, r.top - h - 10);
  b.style.left = x + 'px';
  b.style.top = y + 'px';
}
/* A phone's keyboard: the page set to what stays visible above it (visualViewport), so the keyboard raises the
   bottom only (the writing box) and the top stays where it is -- not the whole page pushed up. */
/* A touch screen's keyboard open (the visible part much shorter than the window, a field focused): the page held to what's
   visible -- only the bottom pushed up, not the whole window -- and the footer hidden. Nothing changes otherwise: a body
   held fixed all the time would stop the page scrolling and the menus placed by it. */
function fitViewport() {
  const vv = window.visualViewport,
    R = document.documentElement,
    a = document.activeElement;
  const kb =
    !!vv &&
    matchMedia('(pointer: coarse)').matches &&
    vv.height < innerHeight * 0.85 &&
    !!a &&
    a.matches &&
    a.matches('textarea,input:not([type=checkbox]):not([type=radio]):not([type=range]),[contenteditable]');
  R.classList.toggle('vv', kb);
  R.classList.toggle('kb', kb);
  if (kb) {
    R.style.setProperty('--vv-h', vv.height + 'px');
    R.style.setProperty('--vv-top', vv.offsetTop + 'px');
  } else {
    R.style.removeProperty('--vv-h');
    R.style.removeProperty('--vv-top');
  }
}
['focusin', 'focusout'].forEach(ev => document.addEventListener(ev, () => setTimeout(fitViewport, 60)));
if (window.visualViewport) {
  visualViewport.addEventListener('resize', fitViewport);
  visualViewport.addEventListener('scroll', fitViewport);
}
function setTheme(t) {
  if (t === 'blender') t = 'dark'; // Blender's theme, offered by the first 2.0 builds: the blue one now
  S.theme = t;
  LS.set('mp-snapshot.theme', t);
  const sys = matchMedia('(prefers-color-scheme: light)').matches;
  const ui = t === 'light' || (t === 'system' && sys) ? 'light' : 'dark';
  document.documentElement.dataset.ui = ui;
  document.documentElement.removeAttribute('style');
  document.documentElement.style.setProperty('--scale', S.scaleV || 1);
  fitViewport();
  closeMenus();
  if (S.ws === 'links') requestAnimationFrame(drawGraph);
}
/* A new shot or asset, as Blender's New shot / New asset: the sequence (or prefix) fixed by where it's
   asked, the shot prefix the project's; a shot's numbers each with its start frame, the end, the name
   that makes, what clashes. PL: the dialog's state while open. */
let PL = null;
const plSp = () => ((M.naming || {}).shot || {}).prefix || 'sh';
const plSd = () => ((M.naming || {}).shot || {}).digits || 3;
const plStart = () => +((M.naming || {}).frame_start ?? 1001);
const plStep = 50; // lib DEFAULT_MULTISHOT_STEP
/* An asset's name, as lib/config.py sanitize_name() makes it. */
const plSan = v =>
  String(v || '')
    .trim()
    .toLowerCase()
    .replace(/ /g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-{2,}/g, '-')
    .replace(/^-+|-+$/g, '');
/* The shot numbers taken in the sequence: {number: [the file's name, mono]} (planned ones too). */
function plOwners(g) {
  const out = {},
    sp = plSp();
  const add = (name, nums) => nums.forEach(n => (out[n] = [name, nums.length === 1]));
  items
    .filter(i => i.kind === 'shot' && groupOf(i) === g && !omitted(i))
    .forEach(i => {
      const seg = (i.name.split('_')[1] || '').slice(sp.length);
      add(i.name, seg.split('-').map(Number).filter(n => !isNaN(n)));
    });
  S.planned
    .filter(p => p.kind === 'shot' && p.g === g)
    .forEach(p => add(p.name, p.shots || (p.name.split('_')[1] || '').slice(sp.length).split('-').map(Number)));
  return out;
}
const plName = () =>
  PL.kind === 'shot'
    ? `${PL.g}_${plSp()}${[...new Set(PL.shots.map(x => x.n))].sort((a, b) => a - b).map(n => String(n).padStart(plSd(), '0')).join('-')}`
    : `${PL.g}_${plSan(PL.name) || '…'}`;
/* What's wrong: [blocking, warnings] -- as operators/shot_ops.py (order, negatives, numbers taken). */
function plCheck() {
  const err = [],
    warn = [];
  if (PL.kind !== 'shot') {
    if (!plSan(PL.name)) err.push(T('A name: lowercase letters, digits and hyphens'));
    else if (items.some(i => i.name === plName()) || S.planned.some(p => p.name === plName())) err.push(T('{name} exists already', { name: plName() }));
    return [err, warn];
  }
  const ns = PL.shots.map(x => x.n),
    st = PL.shots.map(x => x.s);
  if (ns.some(n => !Number.isInteger(n) || n < 0) || st.some(n => !Number.isInteger(n) || n < 0) || !Number.isInteger(PL.end) || PL.end < 0)
    err.push(T("Shot numbers and frames: whole numbers, not negative"));
  else if (ns.join() !== [...new Set(ns)].sort((a, b) => a - b).join() || st.join() !== [...new Set(st)].sort((a, b) => a - b).join() || PL.end < st[st.length - 1])
    err.push(T('Inconsistent timeline: shot numbers or start frames not in order'));
  const own = plOwners(PL.g),
    mono = ns.length === 1;
  ns.forEach(n => {
    const o = own[n];
    if (!o) return;
    const lab = T('Shot {n} already used by {name}', { n: String(n).padStart(plSd(), '0'), name: o[0] });
    (mono && o[1] ? err : warn).push(lab);
  });
  return [err, warn];
}
function planDlg(g, kind) {
  if (kind === 'shot') {
    const own = Object.keys(plOwners(g)).map(Number);
    PL = { g, kind, shots: [{ n: Math.floor(Math.max(0, ...own) / 10) * 10 + 10, s: plStart() }], end: plStart() + 100, desc: '', deps: new Set(DEPTS[kind]), anyway: false };
  } else PL = { g, kind, name: '', desc: '', deps: new Set(DEPTS[kind]) };
  planDraw();
  setTimeout(() => $(kind === 'shot' ? '#pl-d' : '#pl-n')?.focus(), 0);
}
/* What the dialog shows that follows its fields: the name made, the warnings, Add's state. */
function planLive() {
  const [err, warn] = plCheck(),
    box = $('#pl-live');
  if (!box) return;
  box.innerHTML = `<div class="prop"><span class="k">${T('Name')}</span><span class="v"><span class="mono">${esc(plName())}</span></span></div>
    ${PL.kind === 'shot' && PL.shots.length > 1 ? `<p class="hint">${T('A block: one continuous action across several cameras, worked by one person at a time. Not one action? Separate shots.')}</p>` : ''}
    ${err.map(x => `<p class="tag fail pl-w">${ic('b-error')}${esc(x)}</p>`).join('')}${!err.length ? warn.map(x => `<p class="tag check pl-w">${ic('b-error')}${esc(x)}</p>`).join('') : ''}
    ${!err.length && warn.length ? `<button class="swi" role="switch" data-planyway aria-checked="${!!PL.anyway}"><span class="lbl">${T('Create anyway')}</span><span class="tg"></span></button>` : ''}`;
  const ok = $('[data-plok]');
  if (ok) ok.disabled = !!err.length || (!!warn.length && !PL.anyway);
}
function planDraw() {
  const dl = $('#dlg'),
    sh = PL.kind === 'shot';
  const rows = sh
    ? `<div class="prop"><span class="k">${T('Shots')}</span><span class="v pl-sh"><span class="pl-h"><span>${T('Number')}</span><span>${T('Start frame')}</span><span></span></span>${PL.shots
        .map(
          (x, k) =>
            `<span class="pl-r"><label class="field"><span class="faint mono">${esc(plSp())}</span><input type="number" min="0" step="10" data-pln="${k}" value="${x.n}" aria-label="${T('Shot number')}"></label><label class="field"><input type="number" min="0" data-pls="${k}" value="${x.s}" aria-label="${T('First frame')}"></label><button class="btn sm flat icon" data-plrm="${k}" ${PL.shots.length > 1 ? '' : 'disabled'} aria-label="${T('Remove')}" title="${T('Remove')}">${ic('b-x')}</button></span>`
        )
        .join('')}<span class="pl-r"><button class="btn sm tool" data-pladd title="${T('One more shot: a block')}">${ic('b-add')}${T('Shot')}</button><label class="field"><span class="faint">${T('end')}</span><input type="number" min="0" data-ple value="${PL.end}" aria-label="${T('Last frame')}"></label><span></span></span></span></div>`
    : `<div class="prop"><span class="k">${T('Name')}</span><span class="v"><label class="field" style="flex:1"><span class="faint mono">${esc(PL.g)}_</span><input id="pl-n" value="${esc(PL.name)}" aria-label="${T('Name')}" autocomplete="off"></label></span></div>`;
  dl.hidden = false;
  dl.innerHTML = `<div class="dlg-in pl" role="dialog" aria-modal="true" aria-labelledby="pl-t"><h3 id="pl-t">${sh ? T('New shot in {seq}', { seq: esc(PL.g) }) : T('New file {prefix}_…', { prefix: esc(PL.g) })}</h3>
    <p class="faint" style="margin:0">${T('Made in the project when your review is imported, with its folders.')}</p>
    ${rows}
    <div class="prop"><span class="k">${T('Description')}</span><span class="v"><label class="field" style="flex:1"><input id="pl-d" value="${esc(PL.desc)}" placeholder="${T('What it shows')}" aria-label="${T('Description')}"></label></span></div>
    <div class="prop"><span class="k">${T('Departments')}</span><span class="v"><span class="join">${DEPTS[PL.kind].map(d => `<button class="btn sm" data-pld="${d}" aria-pressed="${PL.deps.has(d)}">${LBL[d]}</button>`).join('')}</span></span></div>
    <div id="pl-live"></div>
    <div class="acts"><button class="btn" data-dclose>${T('Cancel')}</button><button class="btn primary" data-plok>${ic('b-add')}${T('Add to my review')}</button></div></div>`;
  planLive();
}
/* Its fields typed in: the state, then what follows them (the inputs themselves left as typed). */
document.addEventListener('input', e => {
  const t = e.target;
  if (!PL || !t.closest || !t.closest('.dlg-in.pl')) return;
  const v = t.value === '' ? NaN : +t.value;
  if (t.dataset.pln != null) PL.shots[+t.dataset.pln].n = v;
  else if (t.dataset.pls != null) PL.shots[+t.dataset.pls].s = v;
  else if (t.dataset.ple != null) PL.end = v;
  else if (t.id === 'pl-n') PL.name = t.value;
  else if (t.id === 'pl-d') PL.desc = t.value;
  planLive();
});
/* Render checked, as in Blender: what watching it says of the file's departments -- ticked, one not done
   marked done (on the stable), one done validated (a team member can't) -- and its video to the edit (live). */
function chkRows(it, rd) {
  // A department's render shows its work and what came before it, not what comes after:
  // an animation render says nothing of the render department's (DEPTS's order).
  const dl = DEPTS[it.kind] || [],
    at = rd ? dl.indexOf(rd) : -1;
  return required(it).map(d => {
    const st = stOf(it, d),
      done = isDone(st);
    if (it.ok[d] || it.mine[d] === 'val') return { d, act: '', on: true, s: T('Validated') };
    if (at >= 0 && dl.indexOf(d) > at)
      return { d, act: '', on: done, s: info(it, d).l + ' · ' + T('after {dept}: not in this render', { dept: LBL[rd] || rd }) };
    if (done) return { d, act: canVal(it, d) ? 'val' : '', on: true, s: canVal(it, d) ? T('Done · ticked: validated') : T('Done') };
    return { d, act: canMark(it, d) ? 'mark' : '', on: false, s: canMark(it, d) ? info(it, d).l + ' · ' + T('ticked: done') : info(it, d).l };
  });
}
function checkedDlg(key) {
  const it = cur();
  if (!it) return;
  // Its render(s): one, a department's (a block's shots), all; their department, when they share one.
  const pick = k => {
    const cs = ckPick(it, k),
      deps = [...new Set(cs.map(x => x.department || ''))];
    return { cs, dep: deps.length === 1 ? deps[0] : '' };
  };
  if (!S.chk || S.chk.name !== it.name || (key != null && S.chk.key !== key)) {
    const { dep } = pick(key);
    // The render's own department ticked first; "render" without one.
    const rd = dep || 'render';
    S.chk = { name: it.name, key: key || '', push: false, on: new Set(chkRows(it, dep).filter(r => r.act && r.d === rd).map(r => r.d)) };
  }
  const o = S.chk,
    { cs, dep } = pick(o.key),
    c = cs.length === 1 ? cs[0] : null,
    rows = chkRows(it, dep);
  const dl = $('#dlg');
  dl.hidden = false;
  dl.innerHTML = `<div class="dlg-in" role="dialog" aria-modal="true" aria-labelledby="ck-t"><h3 id="ck-t">${T('Render checked')} · ${esc(it.name)}</h3>
    ${c ? `<p class="faint" style="margin:0">${esc(checkLabel(c))}</p>` : cs.length > 1 ? `<p class="faint" style="margin:0">${esc(cs.map(checkLabel).join(' · '))}</p>` : ''}
    <div class="sec-h">${T('Departments')}</div>
    ${rows.length ? `<div class="swis">${rows.map(r => `<button class="swi" role="switch" data-ckd="${r.d}" aria-checked="${r.act ? o.on.has(r.d) : r.on}" ${r.act ? '' : 'disabled'}><span class="lbl">${esc(LBL[r.d])}<small>${esc(r.s)}</small></span><span class="tg"></span></button>`).join('')}</div>` : `<span class="faint">${T('No department required.')}</span>`}
    <p class="hint">${S.review ? T("Not right? Leave it unticked and write a retake.") : T('Start a review to mark departments done or validate them.')}</p>
    ${LIVE ? `<div class="swis"><button class="swi" role="switch" data-ckpush aria-checked="${o.push}"><span class="lbl">${T('Push to editing')}<small>${T("Its video into editing/rushes/, replacing the previous one (the edit keeps its link)")}</small></span><span class="tg"></span></button></div>` : ''}
    <div class="acts"><button class="btn" data-dclose>${T('Cancel')}</button><button class="btn primary" data-ckok>${ic('b-checkmark')}${T('Mark checked')}</button></div></div>`;
}
function checkedGo() {
  const it = cur(),
    o = S.chk;
  if (!it || !o) return;
  const picked = ckPick(it, o.key),
    deps = [...new Set(picked.map(x => x.department || ''))],
    c0 = picked.length === 1 ? picked[0] : null;
  let n = 0;
  chkRows(it, deps.length === 1 ? deps[0] : '').forEach(r => {
    if (!r.act || !o.on.has(r.d)) return;
    if (r.act === 'val') A.validate(it, r.d);
    else A.mark(it, r.d);
    n++;
  });
  // This render only: the file stays to check while another one is.
  const done = picked,
    keys = done.map(c => c.key);
  (S.checkedKeys[it.name] = S.checkedKeys[it.name] || []).push(...done.map(ckId));
  if (!checksOf(it).length) it.toCheck = false;
  if (LIVE) liveChecked(it, o.push, keys);
  S.chk = null;
  $('#dlg').hidden = true;
  refresh();
  const left = checksOf(it).length;
  msg(
    (left
      ? T('Checked: {what} · {n} still to check', { what: c0 ? checkLabel(c0) : it.name, n: left })
      : T('Checked: {name} is no longer "to check"', { name: it.name })) +
      (n ? ' · ' + T('{n} department|{n} departments', { n }) : '') +
      (o.push ? ' · ' + T('pushed to editing') : '')
  );
}
function bulkDlg() {
  const o = (S.bulk = S.bulk || { kind: 'shot', g: '', d: DEPTS.shot[0], on: true });
  const pool = items.filter(i => i.kind === o.kind && (!o.g || groupOf(i) === o.g)),
    gs = [...new Set(items.filter(i => i.kind === o.kind).map(groupOf))];
  const n = pool.filter(i => required(i).includes(o.d) !== o.on).length;
  const dl = $('#dlg');
  dl.hidden = false;
  dl.innerHTML = `<div class="dlg-in" role="dialog" aria-modal="true" aria-labelledby="bk-t"><h3 id="bk-t">${T('Departments of several files')}</h3>
    <div class="prop"><span class="k">${T('Files')}</span><span class="v"><span class="join">${[
      ['shot', T('Shots')],
      ['asset', 'Assets']
    ]
      .map(
        ([k, l]) =>
          `<button class="btn sm" data-bk="kind" data-v="${k}" aria-pressed="${o.kind === k}">${l}</button>`
      )
      .join('')}</span></span></div>
    <div class="prop"><span class="k">${o.kind === 'shot' ? T('Sequence') : T('Prefix')}</span><span class="v"><span class="join">${['', ...gs].map(g => `<button class="btn sm" data-bk="g" data-v="${g}" aria-pressed="${o.g === g}">${g || T('All')}</button>`).join('')}</span></span></div>
    <div class="prop"><span class="k">${T('Department')}</span><span class="v"><span class="join">${DEPTS[o.kind].map(d => `<button class="btn sm" data-bk="d" data-v="${d}" aria-pressed="${o.d === d}">${LBL[d]}</button>`).join('')}</span></span></div>
    <div class="prop"><span class="k">${T('Make it')}</span><span class="v"><span class="join"><button class="btn sm" data-bk="on" data-v="1" aria-pressed="${o.on}">${T('required')}</button><button class="btn sm" data-bk="on" data-v="0" aria-pressed="${!o.on}">${T('not required')}</button></span></span></div>
    <p class="dim" style="margin:0">${T('{n} file of {total} changes.|{n} files of {total} change.', { n, total: pool.length })}</p>
    <div class="acts"><button class="btn" data-dclose>${T('Cancel')}</button><button class="btn primary" data-bkok ${n ? '' : 'disabled'}>${T('Apply to {n} file|Apply to {n} files', { n })}</button></div></div>`;
}
/* Search everything (core/25-search.js): Ctrl+K or the top bar; a result opens its file. */
function searchDlg() {
  const dl = $('#dlg');
  dl.hidden = false;
  dl.innerHTML = `<div class="dlg-in sr-dlg" role="dialog" aria-modal="true" aria-label="${T('Search everything')}">
    <label class="field"><svg class="i"><use href="#b-viewzoom"/></svg><input id="sr-q" value="${esc(S.sq || '')}" placeholder="${T('Search everything…')}" aria-label="${T('Search everything')}" autocomplete="off"><span class="kbd">Ctrl K</span></label>
    <div class="sr-list" id="sr-list">${searchResultsHTML(S.sq || '')}</div></div>`;
  const q = $('#sr-q');
  q.oninput = () => {
    S.sq = q.value;
    $('#sr-list').innerHTML = searchResultsHTML(S.sq);
  };
  q.onkeydown = e => {
    if (e.key === 'Enter') $('#sr-list .sr')?.click();
  };
  setTimeout(() => q.select(), 0);
}
/* A result: its file, in its list, on the tab that shows what was found. */
function searchGo(name, tab) {
  const it = items.find(i => i.name === name);
  if (!it) return;
  $('#dlg').hidden = true;
  S.ws = it.kind;
  S.q = '';
  $('#q').value = '';
  S.quick = null;
  S.dept = null;
  S.more.clear();
  S.closed.delete(groupOf(it));
  S.tab = tab;
  if (tab === 'notes') S.noteFilter = 'all';
  S.sel = name;
  renderAll();
  select(name);
}
