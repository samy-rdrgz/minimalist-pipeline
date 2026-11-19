/* ---------- Selection ---------- */
const narrow = () => matchMedia('(max-width:860px)').matches;
function select(n, { open = true } = {}) {
  S.sel = n;
  S.form = null;
  S.reply = null;
  S.rangeStart = null;
  if (S.ws === 'links') {
    S.gFocus = n;
    S.tab = 'links';
    renderList();
    renderTree();
    renderProps();
    requestAnimationFrame(() => centerG(n));
    if (narrow()) document.body.classList.add('props-open');
    document.body.classList.remove('out-open');
    return;
  }
  document.querySelectorAll('.row.sel,.tree li.sel').forEach(e => e.classList.remove('sel'));
  document
    .querySelectorAll(`.row[data-n="${CSS.escape(n)}"],.tree li[data-n="${CSS.escape(n)}"]`)
    .forEach(e => e.classList.add('sel'));
  document.querySelector(`.row[data-n="${CSS.escape(n)}"]`)?.scrollIntoView({ block: 'nearest' });
  renderProps();
  renderWide();
  if (open && narrow() && !S.wide) document.body.classList.add('props-open');
  document.body.classList.remove('out-open');
}
function step(dir) {
  if (S.ws === 'farm' || S.ws === 'links' || S.ws === 'synth') return;
  const v = S.wide
    ? items.filter(i => i.kind === cur().kind && groupOf(i) === groupOf(cur()))
    : visible().filter(i => !S.closed.has(groupOf(i)));
  if (!v.length) return;
  let i = v.findIndex(x => x.name === S.sel);
  i = i < 0 ? 0 : Math.min(v.length - 1, Math.max(0, i + dir));
  select(v[i].name, { open: false });
}

/* ---------- Review ---------- */
function validateAll() {
  const it = cur();
  if (!it || !S.review || S.review.role === TEAM) return;
  const n = A.validateAll(it);
  refresh();
  msg(
    n
      ? T('{n} department validated on {name}|{n} departments validated on {name}', { n, name: it.name })
      : T('Nothing done to validate on {name}', { name: it.name })
  );
}
function submitForm() {
  const it = cur(),
    f = S.form,
    t = $('#f-txt').value.trim(),
    fr = $('#f-fr').value.trim().replace(/^f/, '');
  if (!t) {
    $('#f-txt').focus();
    msg(T('Write what to change first.'));
    return;
  }
  const shots = f.shots.length ? f.shots : [''];
  shots.forEach(x =>
    A.note(it, { type: f.type, deps: f.deps, text: t, frames: fr ? 'f' + fr : '', shot: digits(x) })
  );
  S.form = null;
  S.rangeStart = null;
  refresh();
  msg(
    f.type === 'rtk'
      ? T('Retake written on {name}', { name: it.name })
      : T('Remark written on {name}', { name: it.name })
  );
}
function sendDialog() {
  const ch = A.changes(),
    acts = reviewActions(),
    team = asTeam();
  const dl = $('#dlg');
  dl.hidden = false;
  dl.innerHTML = `<div class="dlg-in" role="dialog" aria-modal="true" aria-labelledby="sd-t"><h3 id="sd-t">${T('Send the review')}</h3>
    <p class="faint" style="margin:0">${esc(S.review.name)} · ${esc(S.review.role)} · ${T('{n} change|{n} changes', { n: ch.length })}</p>
    ${ch.length ? `<ul>${ch.map(c => `<li>${esc(c)}</li>`).join('')}</ul>` : `<p class="dim" style="margin:0">${T('Nothing in this review yet.')}</p>`}
    ${team && ch.length && !acts.length ? `<p class="dim" style="margin:0">${T("As the team, nothing to send: the team doesn't validate -- write a retake or a remark.")}</p>` : ''}
    <p class="faint" style="margin:0;font-size:var(--fs-s)">${LIVE ? T('Applied in Blender at once, as an imported review.') : T('The file {name}, to import in Blender: Pipeline › Import review.', { name: `<span class="mono">${esc(reviewName())}</span>` })}</p>
    <div class="acts"><button class="btn" data-rvclear ${ch.length ? '' : 'disabled'} title="${T('Clear the whole review in progress? A file already downloaded keeps what it holds.')}">${T('Clear the review…')}</button><span style="flex:1"></span><button class="btn" data-dclose>${T('Go on reviewing')}</button>
    <button class="btn primary" data-rvgo ${acts.length ? '' : 'disabled'}>${ic('b-export')}${LIVE ? T('Send to Blender') : T('Download')}</button></div></div>`;
}
/* The review out: to Blender (live), else its file -- the share sheet on a tablet or a phone, else downloaded. */
function deliverReview() {
  const data = reviewFile();
  if (!data.actions.length) return;
  if (LIVE) {
    liveQueue();
    return;
  }
  const text = JSON.stringify(data, null, 2),
    name = reviewName();
  const download = () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 1000);
    toast(T('Downloaded ({name}): Import review reads it.', { name }));
  };
  const file = shareFile(text, name);
  if (!file) return download();
  navigator.share({ files: [file], title: name }).then(
    () => toast(T('Review saved or sent: Import review reads it.')),
    err => {
      if (!err || err.name !== 'AbortError') download();
    }
  );
}
/* The share sheet takes it as JSON, else as plain text (same .json name). null: no share sheet. */
function shareFile(text, name) {
  if (!(navigator.share && navigator.canShare && matchMedia('(pointer:coarse)').matches)) return null;
  for (const type of ['application/json', 'text/plain']) {
    const f = new File([text], name, { type });
    try {
      if (navigator.canShare({ files: [f] })) return f;
    } catch (_) {}
  }
  return null;
}
/* A review file downloaded from this page, read back to go on with it. */
function loadReview(file) {
  if (!file) return;
  const rd = new FileReader();
  rd.onload = () => {
    let data;
    try {
      data = JSON.parse(rd.result);
    } catch (_) {
      toast(T('Not a review file.'));
      return;
    }
    if (data.format !== M.format) {
      toast(T('Not a review downloaded from a snapshot page.'));
      return;
    }
    if (data.schema_version !== M.schema_version) {
      toast(T("This review comes from another version of the snapshot: it can't be loaded here."));
      return;
    }
    const go = () => {
      clearReview();
      S.review = { name: data.author || '', role: data.role || '' };
      const unknown = fromActions(data.actions);
      refresh();
      renderAll();
      toast(
        T('Review of {who} loaded', { who: data.author || '?' }) +
          (unknown.length
            ? ' · ' + T('{n} file not on this page|{n} files not on this page', { n: unknown.length })
            : '')
      );
    };
    if (
      data.project !== M.project &&
      !confirm(T('This review is for {a}, not {b}. Load it anyway?', { a: data.project, b: M.project }))
    )
      return;
    if (items.some(touched) && !confirm(T('Replace the review in progress with this one?'))) return;
    go();
  };
  rd.readAsText(file);
}
function settingsPop(btn) {
  const old = document.querySelector('.pop.set');
  if (old) {
    old.remove();
    return;
  }
  const it = cur(),
    p = document.createElement('div');
  p.className = 'pop set';
  const om = (it.setAside !== undefined ? it.setAside : it.omit) || {};
  const dis = S.review ? '' : 'disabled';
  p.innerHTML = `<h4>${T('File settings')}</h4><p class="hint">${S.review ? T('Sent with your review.') : T('Start a review to change them.')}</p>
    <div class="sec-h">${T('Required departments')}</div><div class="swis">${DEPTS[it.kind].map(d => `<button class="swi" role="switch" data-req="${d}" aria-checked="${required(it).includes(d)}" ${dis}><span class="lbl">${esc(LBL[d])}</span><span class="tg"></span></button>`).join('')}</div>
    <div class="sec-h">${T('Set aside')}</div><span class="join full">${[
      ['', T('Active')],
      ['on_hold', T('On hold')],
      ['cancelled', T('Cancelled')]
    ]
      .map(
        ([k, l]) =>
          `<button class="btn sm" data-omit="${k}" aria-pressed="${(om.state || '') === k}" ${dis}>${l}</button>`
      )
      .join('')}</span>
    ${om.state ? `<label class="field"><input id="om-why" value="${esc(om.reason || '')}" placeholder="${T('Why (for the team)')}" ${dis} aria-label="${T('Reason')}"></label>` : ''}
    <p class="hint">${T('Set aside: out of the figures, still in the list.')}</p>`;
  btn.parentElement.appendChild(p);
  placePop(p, btn);
}
