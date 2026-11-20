/* ---------- Dialogs and popovers ---------- */
function placeMenu(b, m) {
  m.classList.add('fx');
  m.style.left = '0px';
  m.style.top = '0px';
  const r = b.getBoundingClientRect(),
    w = m.offsetWidth,
    h = m.offsetHeight;
  let x = m.classList.contains('right') ? r.right - w : r.left;
  x = Math.max(8, Math.min(x, innerWidth - w - 8));
  let y = r.bottom + 4;
  if (y + h > innerHeight - 8) y = Math.max(8, r.top - h - 4);
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
  if (!S.review || n.mine || n.done || n.type === 'note') return '';
  const on = !!it.fixed[n.id];
  return `<button class="btn sm ${on ? 'ok' : 'flat'}" data-fix="${n.id}" aria-pressed="${on}" title="${on ? T('Cancel') : n.type === 'rtk' ? T('Mark fixed: applied when your review is imported') : T('Mark done: applied when your review is imported')}">${ic('b-checkmark')}${on ? T('Fixed · you') : n.type === 'rtk' ? T('Mark fixed') : T('Mark done')}</button>`;
};
function seqNext() {
  const it = cur(),
    sib = items.filter(i => i.kind === it.kind && groupOf(i) === groupOf(it) && !omitted(i));
  const n = sib.findIndex(i => i.name === it.name);
  if (n < 0 || n >= sib.length - 1) {
    S.seqPlay = false;
    togglePlay();
    msg(T('End of the sequence {seq}', { seq: groupOf(it) }));
    renderWide();
    return;
  }
  S.frame = 1;
  select(sib[n + 1].name, { open: false });
}
const RF = {};
const rform = it =>
  (RF[it.name] = RF[it.name] || {
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
    ${job ? `<p class="tag check" style="align-self:flex-start">${T('Already in the farm: {what}', { what: esc(job.text) + (job.total ? ' · ' + job.done + '/' + job.total : '') })}</p>` : ''}
    <div class="prop"><span class="k">${T('Version')}</span><span class="v"><span class="join full" style="flex:1">${it.stable ? seg('ver', 'stable', T('Last stable · {v}', { v: esc(it.stable) })) : ''}${seg('ver', 'last', T('Latest · {v}', { v: esc(it.wip || it.stable || '') }))}</span></span></div>
    <div class="prop"><span class="k">${T('Department')}</span><span class="v"><span class="anchor" style="flex:1;min-width:0"><button class="enum" style="width:100%" data-menu="m-rdept" aria-haspopup="true" aria-expanded="false"><span class="lb">${f.dept ? esc(f.dept) : T('No department')}</span>${ic('b-tria_down')}</button>
      <div class="menu" id="m-rdept" hidden role="menu">${['', ...(DEPTS[it.kind] || [])].map(d => `<button class="mi" data-rdept="${esc(d)}"><span class="ck">${d === f.dept ? ic('b-checkmark') : ''}</span><span class="lbl">${d ? esc(d) : T('No department')}</span></button>`).join('')}</div></span></span></div>
    <div class="prop"><span class="k">${T('Pre-render script')}</span><span class="v"><span class="anchor" style="flex:1;min-width:0"><button class="enum" style="width:100%" data-menu="m-rpreset" aria-haspopup="true" aria-expanded="false"><span class="lb">${esc(pr[1])}</span>${ic('b-tria_down')}</button>
      <div class="menu" id="m-rpreset" hidden role="menu">${presetsFor(f.dept)
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
  const IC = { rtk: '--st-rtk', note: '--text-2', render: '--st-done', ok: '--st-val' };
  p.innerHTML = `<h4>${T("What's new")}</h4>${NEWS.length ? NEWS.map(x => `<button class="newsi" data-goto-file="${x.n}"><span class="dt" style="background:var(${IC[x.k]})"></span><span class="tx"><span class="h"><b>${esc(x.n)}</b><span class="faint">${x.at}</span></span>${esc(x.h)}<small>${esc(x.x)}</small></span></button>`).join('') : `<p class="hint">${T('Nothing new since the page opened: notes, retakes, validations and renders come here.')}</p>`}
    <button class="swi" role="switch" id="notif-sys" aria-checked="${!!S.notifSys}"><span class="lbl">${T('Notify me in the system too')}</span><span class="tg"></span></button>`;
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
  ['#ptabs', T('The detail'), T('Shot, Notes, Links, Files and renders: the file selected, in tabs.')],
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
    matchMedia('(pointer:coarse)').matches &&
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
  LS.set('mp-snapshot:theme', t);
  const sys = matchMedia('(prefers-color-scheme: light)').matches;
  const ui = t === 'light' || (t === 'system' && sys) ? 'light' : 'dark';
  document.documentElement.dataset.ui = ui;
  document.documentElement.removeAttribute('style');
  document.documentElement.style.setProperty('--scale', S.scaleV || 1);
  fitViewport();
  closeMenus();
  if (S.ws === 'links') requestAnimationFrame(drawGraph);
}
function planDlg(g, kind) {
  const its = items.filter(i => i.kind === kind && groupOf(i) === g);
  let next = '';
  if (kind === 'shot') {
    const nums = its
      .flatMap(i => [i.name, ...(i.shots || []).map(s => g + '_' + s)])
      .map(n => +(n.match(/sh(\d+)/) || [])[1] || 0)
      .concat(S.planned.filter(p => p.g === g).map(p => +(p.name.match(/sh(\d+)/) || [])[1] || 0));
    next = g + '_sh' + String(Math.max(0, ...nums) + 10).padStart(3, '0');
  } else next = g + '_';
  const dl = $('#dlg');
  dl.hidden = false;
  dl.innerHTML = `<div class="dlg-in" role="dialog" aria-modal="true" aria-labelledby="pl-t"><h3 id="pl-t">${kind === 'shot' ? T('New shot in {seq}', { seq: g }) : T('New file {prefix}_…', { prefix: g })}</h3>
    <p class="faint" style="margin:0">${T('Made in the project when your review is imported, with its folders.')}</p>
    <div class="prop"><span class="k">${T('Name')}</span><span class="v"><label class="field" style="flex:1"><input id="pl-n" value="${next}" aria-label="${T('Name')}"></label></span></div>
    <div class="prop"><span class="k">${T('Description')}</span><span class="v"><label class="field" style="flex:1"><input id="pl-d" placeholder="${T('What it shows')}" aria-label="${T('Description')}"></label></span></div>
    <div class="prop"><span class="k">${T('Departments')}</span><span class="v"><span class="join">${DEPTS[kind].map(d => `<button class="btn sm" data-pld="${d}" aria-pressed="true">${LBL[d]}</button>`).join('')}</span></span></div>
    <div class="acts"><button class="btn" data-dclose>${T('Cancel')}</button><button class="btn primary" data-plok="${g}" data-plk="${kind}">${ic('b-add')}${T('Add to my review')}</button></div></div>`;
  setTimeout(() => $('#pl-n').focus(), 0);
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
