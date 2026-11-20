/* ---------- Farm ---------- */
/* A job's states: words, colour (the states' own), icon. */
const JS = [
  ['running', T('In progress'), 'var(--st-you)', 'b-play'],
  ['waiting', T('Waiting'), 'var(--st-wait)', 'b-sorttime'],
  ['failed', T('Failed'), 'var(--st-rtk)', 'b-x'],
  ['finished', T('Finished'), 'var(--st-done)', 'b-checkmark']
];
const jst = s => {
  const x = JS.find(a => a[0] === s) || JS[1];
  return `<span class="jst ${x[0]}" style="background:${x[2]}" title="${x[1]}">${ic(x[3])}</span>`;
};
const jobItem = j => items.find(i => j.file.startsWith(i.name + '_'));
function farmJobs() {
  return F.jobs.filter(
    j =>
      !j.archived &&
      (!S.ff.s || j.state === S.ff.s) &&
      (!S.ff.mine || j.user === M.live.user) &&
      (!S.ff.q || (j.file + ' ' + j.shot).toLowerCase().includes(S.ff.q))
  );
}
function renderFarmQuick() {
  const n = s => F.jobs.filter(j => !j.archived && (!s || j.state === s)).length;
  $('#quick').innerHTML =
    `<span class="join">${[['', T('All')], ...JS].map(([k, l]) => `<button class="btn" data-ffs="${k}" aria-pressed="${S.ff.s === k}">${l}<span class="n">${n(k)}</span></button>`).join('')}</span>
    <button class="btn ${S.ff.mine ? '' : 'tool'}" data-ffm aria-pressed="${S.ff.mine}">${ic('b-user')}${T('Mine')}</button>
    ${F.left ? `<span class="faint" style="font-size:var(--fs-s)" title="${T('The machine time the jobs have left, on the workers alive')}">${esc(F.left)}</span>` : ''}
    <button class="btn tool live-only" data-pushall title="${T("Each shot's latest video, and the assets', into editing/rushes/")}">${ic('b-export')}${T('Push rushes…')}</button>`;
}
/* Render here (farm/local.py): rendered by its own machine, outside the queue; viewport, drawn by its 3D view. */
const jobTags = j =>
  (j.tags || [])
    .map(
      t =>
        `<span class="tag" title="${t === 'local' ? T('Rendered on its own machine, outside the queue') : T("Drawn by the file's 3D view: its overlays included")}">${t === 'local' ? T('local') : T('viewport')}</span>`
    )
    .join('');
function jobRow(j) {
  const p = j.total ? j.done / j.total : 0;
  return `<div class="job ${S.farmSel === j.id ? 'sel' : ''}" data-job="${j.id}" tabindex="-1">${jst(j.state)}<span class="jt"><span class="f">${esc(j.file)}</span><span class="s">${esc([j.shot, j.text].filter(Boolean).join(' · '))}${j.priority !== 10 ? ' · ' + T('priority {n}', { n: j.priority }) : ''}${jobTags(j)}</span></span>
    <span class="jbar">${j.total ? `<i style="--p:${p * 100}%"></i><span>${j.done} / ${j.total} frames</span>` : ''}</span>
    <span class="meta">${[j.machines ? T('{n} machine|{n} machines', { n: j.machines }) : '', esc(j.user), fmtD(j.at)].filter(Boolean).join(' · ')}</span></div>`;
}
function renderFarm() {
  const L = $('#list'),
    me = F.me,
    shown = farmJobs();
  const st =
    { dead: T('stopped'), running: T('running'), stale: T('stuck'), ok: T('running') }[F.status] || F.status;
  let h = `<div class="fme">${jst(me.worker ? 'running' : 'waiting')}<span class="t"><b>${me.worker ? (me.rendering ? T('This machine: worker · rendering') : T('This machine: worker · idle')) : T('This machine: not a worker')}</b>
      <span class="faint">${T('Farm host: {host}', { host: esc(me.host ? T('this machine') : me.host_name || T('none')) })} · <span class="${F.status === 'dead' ? 'bad' : ''}">${T('monitor {state}', { state: st })}</span></span></span>
    ${monitorBtn()}<button class="btn ${me.worker ? '' : 'primary'}" data-farm="worker">${me.worker ? T('Stop being a worker') : T('Make it a worker')}</button></div>`;
  h += JS.map(([s, l]) => {
    const js = shown.filter(j => j.state === s);
    if (!js.length) return '';
    return `<div class="grp"><div class="grp-h"><b>${l}</b><span class="cnt">${js.length}</span><span style="flex:1"></span>${s === 'failed' || s === 'finished' ? `<button class="btn sm tool" data-farm="archive_all" data-v="${s}">${s === 'failed' ? T('Archive the failed') : T('Archive the finished')}</button>` : ''}</div><div class="jobs">${js.map(jobRow).join('')}</div></div>`;
  }).join('');
  if (!shown.length)
    h += `<div class="empty">${F.jobs.some(j => !j.archived) ? T('No job matches.') : T('No job in the farm.')}</div>`;
  h += machinesHTML();
  L.innerHTML = h;
}
function renderFarmDetail(H, B) {
  const id = S.farmSel;
  if (id && id.startsWith('w:')) {
    const w = F.workers.find(x => 'w:' + x.uuid === id);
    if (w) {
      H.innerHTML = `<span class="phead"><span class="pname">${esc(w.name)}</span><span class="d">${T('Machine')}</span></span>`;
      B.innerHTML = `<div class="sec"><dl class="dl"><dt>${T('State')}</dt><dd>${w.status === 'silent' ? T('silent') : esc(w.status)}</dd><dt>${T('Since')}</dt><dd>${fmtD(w.since)}</dd><dt>${T('File')}</dt><dd>${esc(w.file || '–')}</dd><dt>${T('This machine')}</dt><dd>${w.mine ? T('yes') : T('no')}</dd><dt>${T('Host')}</dt><dd>${w.host ? T('yes') : T('no')}</dd></dl>
      <div class="pacts">${w.status !== 'silent' ? `<button class="btn alert" data-farm="stop">${T('Stop')}</button>` : ''}${w.status === 'silent' ? `<button class="btn" data-farm="forget">${T('Forget this machine')}</button>` : ''}</div></div>`;
      return;
    }
  }
  const j = F.jobs.find(x => x.id === id && !x.archived);
  if (!j) {
    H.innerHTML = `<span class="phead"><span class="pname">Farm</span><span class="d">${T('Pick a job or a machine')}</span></span>`;
    B.innerHTML = `<div class="empty">${T("A job's detail shows here: steps, frames, machines, priority and actions.")}</div>`;
    return;
  }
  const it = jobItem(j),
    live = j.state === 'running' || j.state === 'waiting',
    x = JS.find(a => a[0] === j.state);
  H.innerHTML = `<span class="phead"><span class="pname">${esc(j.file)}</span><span class="d">${x[1]} · ${esc(j.text)}</span></span>`;
  B.innerHTML = `<div class="sec">${j.total ? `<span class="jbar big"><i style="--p:${(j.done / j.total) * 100}%"></i><span>${j.done} / ${j.total} frames</span></span>` : ''}
    <dl class="dl"><dt>${T('State')}</dt><dd>${jst(j.state)} ${esc(j.text)}</dd><dt>${T('Step')}</dt><dd class="mono">${esc(j.stage)}</dd>${j.preset || j.department ? `<dt>${T('Script')}</dt><dd>${esc([j.preset, j.department].filter(Boolean).join(' · '))}</dd>` : ''}
    <dt>${T('Frames')}</dt><dd>${j.range ? j.range.join(' – ') : '–'}${j.shot ? ' · ' + esc(j.shot) : ''}</dd><dt>${T('Machines')}</dt><dd class="mono">${j.names.length ? esc(j.names.join(', ')) : T('none')}</dd>
    <dt>${T('Sent by')}</dt><dd>${esc(j.user)} · ${fmtD(j.at)}</dd>
    <dt>${T('Priority')}</dt><dd>${live && !j.pending ? `<span class="prio"><button class="btn sm icon" data-prio="-1" aria-label="${T('Lower')}">−</button><b>${j.priority}</b><button class="btn sm icon" data-prio="1" aria-label="${T('Higher')}">+</button><span class="faint">${T('the highest goes first')}</span></span>` : j.priority}</dd>
    <dt>Job</dt><dd class="mono">${esc(j.id)}</dd></dl>
    <div class="pacts">${it ? `<button class="btn" data-goto-file="${it.name}">${ic('b-file')}${T('The file')}</button>` : ''}
      ${j.removable ? `<button class="btn alert" data-farm="remove">${T('Remove from the queue')}</button>` : live ? `<button class="btn alert" data-farm="cancel">${T('Cancel')}</button>` : ''}
      ${j.retry ? `<button class="btn primary" data-farm="retry">${T('Retry')}</button>` : ''}${j.recompile ? `<button class="btn" data-farm="recompile">${T('Compile again')}</button>` : ''}
      ${j.state === 'failed' || j.state === 'finished' ? `<button class="btn" data-farm="archive">${T('Archive')}</button>` : ''}
      <button class="btn" data-act="folder">${ic('b-file_folder')}${T('Its folder')}</button><button class="btn" data-act="log">${ic('b-file')}${T('Logs')}</button></div></div>`;
}
/* What a job's action did, said after Blender's done it. */
const JOB_SAY = {
  remove: () => T('removed from the queue'),
  archive: () => T('archived'),
  cancel: () => T('cancelled'),
  retry: () => T('retried'),
  recompile: () => T('compiling again')
};
/* The farm itself (its monitor), as Farm monitoring's Launch / Kill: launched on this machine,
   taken over when the one running is stuck, stopped wherever it runs -- asked twice. */
const farmUp = () => F.status === 'running' || F.status === 'ok';
const monitorBtn = (cls = '') =>
  farmUp()
    ? `<button class="btn alert ${cls}" data-farm="kill_monitor" title="${T('Stops the monitor on its next tick; the renders running finish, the queue is kept')}">${T('Stop the farm')}</button>`
    : `<button class="btn primary ${cls}" data-farm="launch_monitor" title="${T('This machine becomes the farm host')}">${F.status === 'stale' ? T('Take the farm over') : T('Launch the farm')}</button>`;
function farmAction(k, el) {
  if (k === 'kill_monitor') {
    if (!twice(el, T('Sure? Click again'))) return;
    farmPost({ action: 'kill_monitor' }, T('stopping the farm'));
  }
  if (k === 'launch_monitor') {
    if (F.status === 'stale' && !twice(el, T('Stuck: take it over? Click again'))) return;
    farmPost({ action: 'launch_monitor', force: F.status === 'stale' }, T('launching the farm'));
  }
  const j = F.jobs.find(x => x.id === S.farmSel),
    w = F.workers.find(x => 'w:' + x.uuid === S.farmSel);
  if (k === 'worker')
    farmPost(
      { action: 'worker', value: !F.me.worker },
      F.me.worker ? T('this machine is no longer a worker') : T('this machine becomes a worker')
    );
  if (k === 'archive_all')
    farmPost(
      { action: 'archive_all', value: el.dataset.v },
      el.dataset.v === 'failed' ? T('archiving the failed jobs') : T('archiving the finished jobs')
    );
  if (k === 'submit') {
    const it = cur();
    if (it) renderSend(it);
  }
  if (j && ['remove', 'archive', 'cancel', 'retry', 'recompile'].includes(k))
    farmPost({ action: k, job_id: j.id }, JOB_SAY[k]() + ' · ' + j.file);
  if (w && k === 'forget') farmPost({ action: 'forget_worker', value: w.uuid }, T('machine forgotten'));
  if (w && k === 'stop')
    farmPost({ action: 'stop_worker', value: w.uuid }, T('stopping {name}', { name: w.name }));
}

/* Machines: a node each -- its name on top (who, its id's start), the project files open
   in its Blenders under it (a click: that file), then its worker's state. Every machine
   with a file open or a worker (lib/monitoring/live.py presence(), the farm's workers);
   nothing about since when. */
function machinesHTML() {
  const by = {};
  const node = (uuid, label) => (by[uuid] = by[uuid] || { uuid, label, files: [], worker: null });
  (M.presence || []).forEach(p => node(p.uuid || p.machine, `${p.user} (${p.machine})`).files.push(p));
  F.workers.forEach(w => (node(w.uuid, w.name).worker = w));
  const ms = Object.values(by).sort((a, b) => (a.label < b.label ? -1 : 1));
  const name = f => items.find(i => i.file === f || f.startsWith(i.name + '_'))?.name;
  const wk = w =>
    !w
      ? `<span class="faint">${T('not a worker')}</span>`
      : `<button class="mn-w" data-wk="${w.uuid}">${jst(w.status === 'silent' ? 'waiting' : w.file ? 'running' : 'finished')}<span>${w.status === 'silent' ? T('worker silent since {date}', { date: fmtD(w.since) }) : w.file ? T('worker · rendering {file}', { file: esc(w.file) }) : T('worker · idle')}${w.local ? ` <span class="tag" title="${T('Kept for its own renders: the farm sends it nothing meanwhile')}">${T('local')}</span>` : ''}</span></button>`;
  return `<div class="grp"><div class="grp-h"><b>${T('Machines')}</b><span class="cnt">${ms.length}</span><span class="faint" style="font-size:var(--fs-s)">${T('who has which file open, and the workers')}</span></div>
    ${
      ms.length
        ? `<div class="mnodes">${ms
            .map(
              m => `<div class="mn ${S.farmSel === 'w:' + m.uuid ? 'sel' : ''}"><div class="mn-h">${ic('b-user')}<b>${esc(m.label)}</b></div>
        <div class="mn-b">${
          m.files.length
            ? m.files
                .map(f => {
                  const n = name(f.file);
                  return `<button class="mn-f" ${n ? `data-sgofile="${esc(n)}" data-stab="plan"` : 'disabled'}>${ic('b-blender')}<span class="mono">${esc(f.file)}</span>${f.saved ? '' : `<span class="faint">${T('not saved yet')}</span>`}</button>`;
                })
                .join('')
            : `<span class="faint">${T('no file open')}</span>`
        }
        ${wk(m.worker)}</div></div>`
            )
            .join('')}</div>`
        : `<div class="empty">${T('No Blender has a project file open, no worker.')}</div>`
    }</div>`;
}
