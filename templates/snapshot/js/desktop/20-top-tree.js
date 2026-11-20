/* ---------- Topbar ---------- */
function renderTop() {
  const n = k => items.filter(i => i.kind === k).length;
  $('#ws').innerHTML = [
    ['shot', T('Shots'), 'b-camera_data', n('shot')],
    ['asset', T('Assets'), 'b-asset_manager', n('asset')],
    ['links', T('Links'), 'b-linked', ''],
    ['todo', T('To do'), 'b-checkmark', ''],
    ['synth', T('Breakdown'), 'b-spreadsheet', ''],
    ...(LIVE
      ? [
          [
            'farm',
            T('Farm'),
            'b-render_animation',
            F.jobs.filter(j => !j.archived && (j.state === 'running' || j.state === 'waiting')).length
          ]
        ]
      : [])
  ]
    .map(
      ([k, l, i, c]) =>
        `<button role="tab" data-ws="${k}" aria-selected="${S.ws === k}" title="${l}">${ic(i)}<span class="lbl">${l}</span>${c !== '' ? `<span class="n">${c}</span>` : ''}</button>`
    )
    .join('');
  $('#p-name').textContent = M.project;
  $('#p-live').title = T('Connected to Blender · {user}', { user: M.live.user });
  $('#p-date').textContent =
    (LIVE ? 'live · ' + fmtD(M.snapshot) : T('snapshot of {date}', { date: fmtD(M.snapshot) })) +
    ' · ' +
    M.exported_by;
  const n2 = items.filter(touched).length;
  $('#review-slot').innerHTML = !S.review
    ? `<button class="btn primary" id="rv-open" aria-haspopup="dialog">${ic('b-greasepencil')}<span class="only-wide">${T('Review')}</span></button>`
    : `<span class="review-chip"><span class="who">${esc(S.review.name)} · ${S.review.role}</span>${LIVE ? `<span class="rv-sync" data-state="${LV.say}" title="${T('Each change goes to Blender by itself')}">${SAY[LV.say]()}</span>` : `<button class="btn primary" id="rv-send" title="${T('What it holds, then the file to send')}">${ic('b-export')}<span class="only-wide">${T('Send…')}</span><span class="n">${n2}</span></button>`}<button class="btn flat icon" id="rv-stop" aria-label="${T('Leave the review')}" title="${T('Leave the review')}">${ic('b-x')}</button></span>`;
}
/* Started from the top bar, or from Watch large (it stays open, on the file watched). */
function reviewPop(btn) {
  const old = document.querySelector('.pop.rv');
  if (old) {
    old.remove();
    return;
  }
  btn = btn || $('#rv-open');
  const host = S.wide ? $('#wide') : $('#review-slot');
  const p = document.createElement('div');
  p.className = 'pop rv';
  p.setAttribute('role', 'dialog');
  p.setAttribute('aria-label', T('Start a review'));
  const sh = items.filter(i => i.kind === 'shot'),
    r0 = role0();
  p.innerHTML = `<h4>${T('Start a review')}</h4>
    <div class="prop"><span class="k">${T('Name')}</span><span class="v"><label class="field" style="flex:1"><input id="rv-name" value="${esc(M.live.user || '')}" aria-label="${T('Your name')}"></label></span></div>
    <div class="prop"><span class="k">${T('Role')}</span><span class="v"><span class="join full" style="flex:1">${M.roles.map(r => `<button class="btn" data-role="${r}" aria-pressed="${r === r0}">${r}</button>`).join('')}<button class="btn" data-role="team" aria-pressed="${r0 === TEAM}">team</button></span></span></div>
    <p class="hint" id="rv-help">${esc(roleHelp(r0))}</p>
    <div class="prop" style="align-items:start"><span class="k" style="padding-top:5px">${T('Path')}</span><span class="v" style="flex-direction:column;align-items:stretch">
      <button class="btn" data-path="val" aria-pressed="true">${T('To validate')} <span class="n">${sh.filter(toValidate).length}</span></button>
      <button class="btn" data-path="rtk" aria-pressed="false">${T('Open retakes')} <span class="n">${sh.filter(i => openRtk(i)).length}</span></button>
      <button class="btn" data-path="" aria-pressed="false">${T('Everything, in order')}</button></span></div>
    <button class="btn primary" id="rv-go">${T('Start')}</button>`;
  host.appendChild(p);
  if (btn) placePop(p, btn);
  p.addEventListener('click', e => {
    const r = e.target.closest('[data-role]');
    if (r) {
      p.querySelectorAll('[data-role]').forEach(b => b.setAttribute('aria-pressed', b === r));
      $('#rv-help').textContent = roleHelp(r.dataset.role);
    }
    const pa = e.target.closest('[data-path]');
    if (pa) p.querySelectorAll('[data-path]').forEach(b => b.setAttribute('aria-pressed', b === pa));
    if (e.target.closest('#rv-go')) {
      startReview($('#rv-name').value, p.querySelector('[data-role][aria-pressed=true]').dataset.role);
      S.quick = p.querySelector('[data-path][aria-pressed=true]').dataset.path || null;
      if (!S.wide) {
        S.ws = 'shot';
        const f = visible()[0];
        if (f) S.sel = f.name;
      }
      p.remove();
      renderAll();
      msg(T('Reviewing: V validates the done departments, X writes a retake.'));
    }
  });
  setTimeout(() => $('#rv-name')?.select(), 0);
}

/* ---------- Outliner ---------- */
function renderTree() {
  if (S.ws === 'farm') {
    const n = s => F.jobs.filter(j => !j.archived && (!s || j.state === s)).length;
    $('#tree').innerHTML =
      [['', T('All jobs')], ...JS]
        .map(
          ([k, l]) =>
            `<li class="it ${S.ff.s === k ? 'sel' : ''}" data-ffs="${k}" style="padding-left:12px">${k ? jst(k) : ic('b-render_animation')}<span class="nm" style="font-family:var(--ui);font-size:var(--fs)">${l}</span><span class="pc">${n(k)}</span></li>`
        )
        .join('') +
      `<li class="it" data-ffm style="padding-left:12px">${ic('b-user')}<span class="nm" style="font-family:var(--ui);font-size:var(--fs)">${T('Mine')}</span><span class="pc">${F.jobs.filter(j => !j.archived && j.user === M.live.user).length}</span></li>`;
    $('#tree')
      .querySelectorAll('.jst')
      .forEach(e => {
        e.style.width = '16px';
        e.style.height = '16px';
      });
    return;
  }
  const kind = S.ws === 'synth' ? 'shot' : S.ws === 'todo' ? S.td.kind : S.ws;
  const vis = items.filter(
    i =>
      (S.ws === 'links' ? i.links.length || i.linkedBy.length || S.gAll : i.kind === kind) &&
      (!S.tq || i.name.toLowerCase().includes(S.tq))
  );
  $('#tree').innerHTML = [...new Set(vis.map(groupOf))]
    .map(g => {
      const its = vis.filter(i => groupOf(i) === g),
        cl = S.closedTree.has(g);
      const act = its.filter(i => !omitted(i) && i.done != null);
      const avg = act.length ? act.reduce((a, i) => a + i.done, 0) / act.length : null;
      return (
        `<li class="seq ${cl ? 'closed' : ''}" data-tg="${g}">${ic('b-downarrow_hlt', 'i tri open')}${ic('b-rightarrow', 'i tri shut')}<span class="nm">${g}</span><span class="pc">${pct(avg)}</span></li>` +
        (cl
          ? ''
          : its
              .map(
                i =>
                  `<li class="it ${(S.ws === 'links' ? S.gFocus === i.name : S.sel === i.name) ? 'sel' : ''} ${omitted(i) ? 'om' : ''}" data-n="${i.name}"><span style="width:8px;height:8px;border-radius:50%;flex:none;background:${DOT[worst(i)]}"></span><span class="nm">${i.kind === 'shot' ? i.name.replace(i.group + '_', '') : i.name}</span>${openNotes(i) ? `<span class="pc">${ic('i-note')}${openNotes(i)}</span>` : ''}</li>`
              )
              .join(''))
      );
    })
    .join('');
  $('#tree')
    .querySelectorAll('.pc svg')
    .forEach(s => {
      s.style.width = '11px';
      s.style.height = '11px';
    });
}
