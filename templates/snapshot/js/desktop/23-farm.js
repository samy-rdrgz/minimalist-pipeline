/* ---------- Farm ---------- */
/* A job's states: words, colour (the states' own), icon. */
const JS = [
  ['running', T('In progress'), 'var(--st-you)', 'b-play'],
  ['waiting', T('Waiting'), 'var(--st-wait)', 'b-sorttime'],
  ['failed', T('Failed'), 'var(--st-rtk)', 'b-x'],
  ['finished', T('Finished'), 'var(--st-done)', 'b-checkmark']
];
/* The rendering time left (lib/monitoring/live.py, farm/details.py render_left_parts()):
   {seconds, workers, unknown}, said here in the page's language. */
const hMin = s => (s >= 3600 ? Math.floor(s / 3600) + ' h ' + String(Math.round((s % 3600) / 60)).padStart(2, '0') : T('{n} min', { n: Math.max(1, Math.round(s / 60)) }));
/* A frame's time: "8.5 s", "45 s", "2 min 05 s". */
const secs = s =>
  s < 60 ? T('{n} s', { n: s < 10 ? s.toFixed(1) : Math.round(s) }) : T('{m} min {s} s', { m: Math.floor(s / 60), s: String(Math.round(s % 60)).padStart(2, '0') });
/* A render's time left: what its machines' pace says (farm/loop.py _time_left()). */
const jobLeft = j => (j.left != null && j.state === 'running' && j.total ? T('≃ {time} left', { time: hMin(j.left) }) : '');
const farmLeft = L => {
  if (!L) return '';
  if (typeof L === 'string') return L; // a page served by an older Blender
  if (!L.seconds) return L.unknown ? T('{n} not estimated yet', { n: L.unknown }) : '';
  return (
    T('≃ {time} of rendering left with {n} worker|≃ {time} of rendering left with {n} workers', { time: hMin(L.seconds), n: L.workers }) +
    (L.unknown ? ' ' + T('(+{n} not estimated)', { n: L.unknown }) : '')
  );
};
const jst = s => {
  const x = JS.find(a => a[0] === s) || JS[1];
  return `<span class="jst ${x[0]}" style="background:${x[2]}" title="${x[1]}">${ic(x[3])}</span>`;
};
const jobItem = j => items.find(i => j.file.startsWith(i.name + '_'));
/* What the farm host does right now (lib/monitoring/live.py _host_now()): its own steps, its worker's render. */
const hostNow = d =>
  (d || []).length ? d.map(x => `${esc(TS(x.what))} <b>${esc(x.file)}</b>`).join(' · ') : T('nothing to do');
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
    <button class="btn tool live-only" data-pushall title="${T("Each shot's latest video, and the assets', into editing/rushes/")}">${ic('b-export')}${T('Push rushes…')}</button>`;
  renderStatus(); // the time left, in the status bar: fresh with the farm's data
}
/* The queue's rendering time left, for the status bar, with when it should all be done. */
function farmLeftHTML() {
  const t = farmLeft(F.left);
  if (!t) return `<span class="faint">${T('Nothing left to render')}</span>`;
  const end = F.left && F.left.seconds ? new Date(Date.now() + F.left.seconds * 1000) : null;
  return `<span title="${T('The machine time the jobs have left, on the workers alive')}">${esc(t)}${end ? ` <span class="faint">· ${T(F.left.unknown ? 'done around {time} at the earliest' : 'done around {time}', { time: String(end.getHours()).padStart(2, '0') + ':' + String(end.getMinutes()).padStart(2, '0') })}</span>` : ''}</span>`;
}
/* ↑ ↓ on the Farm tab: the jobs, in the list's order. */
function farmStep(dir) {
  const v = JS.flatMap(([s]) => farmJobs().filter(j => j.state === s));
  if (!v.length) return;
  let i = v.findIndex(j => j.id === S.farmSel);
  i = i < 0 ? 0 : Math.min(v.length - 1, Math.max(0, i + dir));
  S.farmSel = v[i].id;
  document.querySelectorAll('.job.sel').forEach(e => e.classList.remove('sel'));
  const row = document.querySelector(`.job[data-job="${v[i].id}"]`);
  if (row) {
    row.classList.add('sel');
    row.scrollIntoView({ block: 'nearest' });
  }
  renderProps();
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
  const p = j.total ? j.done / j.total : 0,
    meta = [j.machines ? T('{n} machine|{n} machines', { n: j.machines }) : '', esc(j.user), fmtD(j.at)]
      .filter(Boolean)
      .join(' · ');
  return `<div class="job ${S.farmSel === j.id ? 'sel' : ''}" data-job="${j.id}" tabindex="-1">${jst(j.state)}<span class="jt"><span class="f">${esc(j.file)}</span><span class="s">${esc([j.shot, TS(j.text)].filter(Boolean).join(' · '))}${j.priority !== 10 ? ' · ' + T('priority {n}', { n: j.priority }) : ''}${jobTags(j)}</span></span>
    <span class="jbar">${j.total ? `<i style="--p:${p * 100}%"></i><span title="${jobLeft(j)}">${j.done} / ${j.total} frames${jobLeft(j) ? ' · ≃ ' + hMin(j.left) : ''}</span>` : ''}</span>
    <span class="meta" title="${meta}">${meta}</span></div>`;
}
function renderFarm() {
  const L = $('#list'),
    me = F.me,
    shown = farmJobs();
  const st =
    { dead: T('stopped'), running: T('running'), stale: T('stuck'), ok: T('running') }[F.status] || F.status;
  let h = `<div class="fme">${jst(me.worker ? 'running' : 'waiting')}<span class="t"><b>${me.worker ? (me.rendering ? T('This machine: worker · rendering') : T('This machine: worker · idle')) : T('This machine: not a worker')}</b>
      <span class="faint">${T('Farm host: {host}', { host: esc(me.host ? T('this machine') : me.host_name || T('none')) })} · <span class="${F.status === 'dead' ? 'bad' : ''}">${T('monitor {state}', { state: st })}</span></span>
      ${F.status === 'dead' ? '' : `<span class="faint">${T('Now: {what}', { what: hostNow(me.host_now) })}</span>`}</span>
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
      B.innerHTML = `<div class="sec"><dl class="dl"><dt>${T('State')}</dt><dd>${w.status === 'silent' ? T('silent') : esc(TS(w.status))}</dd><dt>${T('Since')}</dt><dd>${fmtD(w.since)}</dd><dt>${T('File')}</dt><dd>${esc(w.file || '–')}</dd><dt>${T('This machine')}</dt><dd>${w.mine ? T('yes') : T('no')}</dd><dt>${T('Host')}</dt><dd>${w.host ? T('yes') : T('no')}</dd></dl>
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
  H.innerHTML = `<span class="phead"><span class="pname">${esc(j.file)}</span><span class="d">${x[1]} · ${esc(TS(j.text))}</span></span>`;
  B.innerHTML = `<div class="sec">${j.total ? `<span class="jbar big"><i style="--p:${(j.done / j.total) * 100}%"></i><span>${j.done} / ${j.total} frames</span></span>` : ''}
    <dl class="dl"><dt>${T('State')}</dt><dd>${jst(j.state)} ${esc(TS(j.text))}</dd><dt>${T('Step')}</dt><dd class="mono">${esc(j.stage)}</dd>${j.preset || j.department ? `<dt>${T('Script')}</dt><dd>${esc([j.preset, j.department].filter(Boolean).join(' · '))}</dd>` : ''}
    <dt>${T('Frames')}</dt><dd>${j.range ? j.range.join(' – ') : '–'}${j.shot ? ' · ' + esc(j.shot) : ''}</dd>${jobTimes(j)}<dt>${T('Machines')}</dt><dd>${machinesDD(j)}</dd>
    <dt>${T('Sent by')}</dt><dd>${esc(j.user)} · ${fmtD(j.at)}</dd>
    <dt>${T('Priority')}</dt><dd>${live && !j.pending ? `<span class="prio"><button class="btn sm icon" data-prio="-1" aria-label="${T('Lower')}">−</button><b>${j.priority}</b><button class="btn sm icon" data-prio="1" aria-label="${T('Higher')}">+</button><span class="faint">${T('the highest goes first')}</span></span>` : j.priority}</dd>
    <dt>Job</dt><dd class="mono">${esc(j.id)}</dd></dl>
    ${jobMore(j)}
    <div class="pacts">${it ? `<button class="btn" data-goto-file="${it.name}">${ic('b-file')}${T('The file')}</button>` : ''}
      ${j.removable ? `<button class="btn alert" data-farm="remove">${T('Remove from the queue')}</button>` : live ? `<button class="btn alert" data-farm="cancel">${T('Cancel')}</button>` : ''}
      ${j.retry ? `<button class="btn primary" data-farm="retry">${T('Retry')}</button>` : ''}${j.recompile ? `<button class="btn" data-farm="recompile">${T('Compile again')}</button>` : ''}
      ${j.state === 'failed' || j.state === 'finished' ? `<button class="btn" data-farm="archive">${T('Archive')}</button>` : ''}
      <button class="btn" data-act="folder">${ic('b-file_folder')}${T('Its folder')}</button><button class="btn" data-act="log">${ic('b-file')}${T('Logs')}</button></div></div>`;
}
/* What only its job file says (farm/details.py job_detail(), Blender's own job detail), read on
   demand (the farm action "detail"): what went wrong -- a chunk's failure and why, a frame stuck,
   the job stopped -- and its steps, each with the time since the one before. Again every 10 s
   while it's on; once for one that's over, again when its step changes. */
const JD = {};
const PROBLEMS = ['Stopped', 'Why', 'Failed chunk', 'Stuck frame', 'Failed on', 'Corrupted frames', 'Missing shots', 'Taken off', 'Rendered again'];
function jobMore(j) {
  if (!LIVE) return '';
  const key = j.stage + '|' + j.state,
    c = JD[j.id],
    on = j.state === 'running' || j.state === 'waiting';
  if (!c || (!c.busy && (c.key !== key || (on && Date.now() - c.at > 10000)))) {
    JD[j.id] = { ...(c || {}), key, at: Date.now(), busy: true };
    livePost('farm', { action: 'detail', job_id: j.id })
      .then(r => {
        JD[j.id] = { key, at: Date.now(), d: r.ok ? r.detail : null };
        if (S.ws === 'farm' && S.farmSel === j.id) renderProps();
      })
      .catch(() => (JD[j.id] = { key, at: Date.now(), d: (c || {}).d }));
  }
  const d = (JD[j.id] || {}).d;
  if (!d) return '';
  const bad = d.rows.filter(r => PROBLEMS.includes(r[0]));
  return (
    (bad.length
      ? `<div class="sec-h">${T('Problems')}</div><dl class="dl">${bad.map(([k, v, a]) => `<dt>${T(k)}</dt><dd class="${a ? 'bad' : ''}">${esc(v)}</dd>`).join('')}</dl>`
      : '') +
    (d.stages.length
      ? `<div class="sec-h">${T('Steps')}<span class="sp"></span><span class="faint" style="text-transform:none;letter-spacing:0">${T('+ the time since the step before')}</span></div>
    <dl class="dl">${d.stages
      .map(([when, what]) => {
        const [at, since] = when.split(' +');
        return `<dt class="mono">${esc(at)}</dt><dd><span class="mono">${esc(what)}</span>${since ? `<span class="faint">+${esc(since)}</span>` : ''}</dd>`;
      })
      .join('')}</dl>`
      : '')
  );
}
/* A job's times in its detail: left, the pace, how long in this step, the video's compile. */
function jobTimes(j) {
  const rows = [];
  if (j.state === 'running' && j.stage === 'render_start') {
    const end = new Date(Date.now() + (j.left || 0) * 1000);
    rows.push([
      T('Time left'),
      jobLeft(j)
        ? `≃ ${hMin(j.left)} <span class="faint">· ${T('done around {time}', { time: String(end.getHours()).padStart(2, '0') + ':' + String(end.getMinutes()).padStart(2, '0') })}</span>`
        : T('not timed yet: after the first frames')
    ]);
  }
  if (j.estimate) rows.push([T('Estimate'), esc(TS(j.estimate))]);
  if (j.pace) rows.push([T('Per frame'), T('{time} on average', { time: secs(j.pace) })]);
  if (j.state === 'running' && j.elapsed) rows.push([T('In this step for'), hMin(j.elapsed)]);
  if (j.compile != null) rows.push([T('Video'), T('compiling · {p}%', { p: Math.round(j.compile * 100) })]);
  return rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
}
/* Its machines, each with its pace and the frame it's on. */
function machinesDD(j) {
  const ms = j.per_machine || j.names.map(name => ({ name }));
  if (!ms.length) return T('none');
  return ms
    .map(
      m =>
        `<div><span class="mono">${esc(m.name)}</span>${m.pace ? ` <span class="faint">· ${T('{time} a frame', { time: secs(m.pace) })}</span>` : ''}${m.frame != null ? ` <span class="faint">· ${T('on frame {n}', { n: m.frame })}</span>` : ''}</div>`
    )
    .join('');
}
/* What a job's action did, said after Blender's done it. */
const JOB_SAY = {
  remove: () => T('removed from the queue'),
  archive: () => T('archived'),
  cancel: () => T('cancelled'),
  retry: () => T('retried'),
  recompile: () => T('compiling again')
};
/* The farm itself (its monitor), as the Farm tab's Launch / Kill: launched on this machine,
   taken over when the one running is stuck, stopped wherever it runs -- asked twice. */
const farmUp = () => F.status === 'running' || F.status === 'ok';
const monitorBtn = (cls = '') =>
  farmUp()
    ? `<button class="btn alert ${cls}" data-farm="kill_monitor" title="${T('Stops the monitor on its next tick; the renders running finish, the queue is kept')}">${T('Stop the farm')}</button>`
    : `<button class="btn primary ${cls}" data-farm="launch_monitor" title="${T('This machine becomes the farm host')}">${F.status === 'stale' ? T('Take the farm over') : T('Launch the farm')}</button>`;
/* A worker on a render: stopped once its frame is written, or now (its frame lost) -- asked in a
   popup, as Blender's Stop this worker asks (farm_kill_self_worker); go(now) sends it. */
function askStop(name, file, go, who) {
  const j = F.jobs.find(x => x.file === file && x.state === 'running'),
    m = j && (j.per_machine || []).find(x => x.name === who),
    facts = [
      m && m.frame != null ? T('on frame {n}', { n: m.frame }) : '',
      m && m.pace ? T('{time} a frame', { time: secs(m.pace) }) : '',
      j && jobLeft(j) ? T('the job: {left}', { left: jobLeft(j) }) : ''
    ].filter(Boolean);
  const dl = $('#dlg');
  dl.hidden = false;
  dl.innerHTML = `<div class="dlg-in" role="alertdialog" aria-modal="true" aria-labelledby="ask-t"><h3 id="ask-t">${esc(T('Stop {name}', { name }))}</h3>
    <p class="faint">${T('It is rendering {file}.', { file: `<span class="mono">${esc(file)}</span>` })}${facts.length ? '<br>' + facts.join(' · ') : ''}</p>
    <p class="faint">${esc(T('After this frame: the frame in progress is written, then the worker stops. Stop now: the render is interrupted, its frame lost. Either way its frames left go to the other machines.'))}</p>
    <div class="acts"><button class="btn" data-dclose>${T('Cancel')}</button><span style="flex:1"></span><button class="btn alert" data-stop-now="1">${T('Stop now')}</button><button class="btn primary" data-stop-now="0">${T('Stop after this frame')}</button></div></div>`;
  dl.querySelector('[data-stop-now="0"]').focus({ preventScroll: true });
  dl.onclick = e => {
    const b = e.target.closest('[data-stop-now]');
    if (!b) return;
    dl.hidden = true;
    dl.onclick = null;
    go(b.dataset.stopNow === '1');
  };
}
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
  if (k === 'worker') {
    const off = now =>
      farmPost(
        { action: 'worker', value: !F.me.worker, now },
        F.me.worker ? T('this machine is no longer a worker') : T('this machine becomes a worker')
      );
    const mine = F.workers.find(x => x.mine);
    if (F.me.worker && F.me.rendering) askStop(T('this machine'), (mine && mine.file) || '', off, mine && mine.name);
    else off(false);
  }
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
  if (w && k === 'stop') {
    const stop = now => farmPost({ action: 'stop_worker', value: w.uuid, now }, T('stopping {name}', { name: w.name }));
    if (w.file) askStop(w.name, w.file, stop, w.name);
    else stop(false);
  }
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
