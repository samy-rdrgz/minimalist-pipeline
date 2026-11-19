/* ---------- Live: the page Blender serves (lib/monitoring/live.py) ----------
   Its data kept up to date (/data, waited on), the review sent (/action), the farm's
   and the files' actions (/farm, /open, /play). Each says what it sent, then what Blender did. */
function livePost(path, body) {
  return fetch(path + '?t=' + encodeURIComponent(M.live.token || ''), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(r => r.json());
}
const noAnswer = () => toast(T("Blender doesn't answer."));
const sentSay = what => T('Sent to Blender: {what}', { what });
/* Open a file in Blender: the question first when Blender's own has unsaved changes. */
function liveOpen(file, save) {
  livePost('open', { file, save: save || '' })
    .then(res => {
      if (res.ask) return askOpen(file, res.current);
      toast(
        res.ok
          ? sentSay(T('opening {file}', { file: res.opened }))
          : T('Not opened: {error}', { error: res.error })
      );
    })
    .catch(noAnswer);
}
function askOpen(file, current) {
  const dl = $('#dlg');
  dl.hidden = false;
  dl.innerHTML = `<div class="dlg-in" role="alertdialog" aria-modal="true" aria-labelledby="ask-t"><h3 id="ask-t">${esc(T('{file} has unsaved changes in Blender', { file: current }))}</h3>
    <div class="acts"><button class="btn" data-dclose>${T('Cancel')}</button><span style="flex:1"></span><button class="btn" data-open-save="discard">${T("Don't save")}</button><button class="btn primary" data-open-save="save">${T('Save, then open')}</button></div></div>`;
  dl.querySelector('[data-open-save="save"]').focus({ preventScroll: true });
  dl.onclick = e => {
    const b = e.target.closest('[data-open-save]');
    if (!b) return;
    dl.hidden = true;
    dl.onclick = null;
    liveOpen(file, b.dataset.openSave);
  };
}
/* A file's folder in this machine's file browser: its .blend's, its render's. */
function liveFolder(body) {
  livePost('open', body)
    .then(res =>
      toast(res.ok ? sentSay(T('opens the folder')) : T('Not opened: {error}', { error: res.error }))
    )
    .catch(noAnswer);
}
/* A render's full video in this machine's player. */
function livePlay(video) {
  if (!video) return toast(T('No video for this render.'));
  livePost('play', { video })
    .then(res =>
      toast(
        res.ok
          ? sentSay(T("opens the video in this machine's player"))
          : T('Not opened: {error}', { error: res.error })
      )
    )
    .catch(noAnswer);
}
/* The farm: a job's or a machine's action, a render, a sequence's preview. */
function farmPost(body, say) {
  return livePost('farm', body)
    .then(res => {
      toast(
        res.ok
          ? sentSay((say || res.sent || body.action) + (res.note ? ' · ' + res.note : ''))
          : T('Not done: {error}', { error: res.error || '?' })
      );
      return res;
    })
    .catch(noAnswer);
}
function renderSend(it, preview) {
  const f = rform(it);
  if (preview)
    return farmPost(
      { action: 'preview', sequence: it.group, priority: f.prio },
      T('preview of {seq}', { seq: it.group })
    );
  return farmPost({
    action: 'render',
    file: f.ver === 'stable' && it.stableFile ? it.stableFile : it.file,
    department: f.dept || '',
    preset: f.preset,
    priority: f.prio,
    mode: f.mode,
    start: f.start,
    end: f.end,
    sound: f.sound !== 'off',
    shots: it.shots && it.shots.length > 1 ? it.shots.filter(x => !f.off[x]) : null
  });
}
/* The review to Blender, as it's made: each change sent a moment after (300 ms), applied there as an
   imported review would be (the same checks; sent twice, it changes nothing). Not while a field is
   being typed in (once left). Once the data showing it is back, a file whose changes are all sent
   leaves the review; one changed meanwhile keeps its new changes, what went already never sent again. */
const LV = { busy: false, again: false, t: 0, sent: {}, pend: null, say: 'ok' };
/* Its state, said in the review's chip: ok (up to date), busy (sending), off (not sent). */
const SAY = { ok: () => T('up to date'), busy: () => T('sending…'), off: () => T('not sent') };
function liveSay(t) {
  LV.say = t;
  const e = document.querySelector('.rv-sync');
  if (e) {
    e.textContent = SAY[t]();
    e.dataset.state = t;
  }
}
function liveQueue() {
  if (!LIVE || !S.review) return;
  clearTimeout(LV.t);
  LV.t = setTimeout(liveFlush, 300);
}
const typing = () => {
  const a = document.activeElement;
  return !!(
    a &&
    a.matches &&
    a.matches('textarea,input:not([type=checkbox]):not([type=radio]):not([type=range])') &&
    a.closest('#props,#wide,#mob,.pop,#dlg')
  );
};
const sentKey = a => (a.type === 'create' ? 'create:' + a.file : JSON.stringify(a));
function liveFlush() {
  if (LV.busy) {
    LV.again = true;
    return;
  }
  if (typing()) return;
  const acts = reviewActions().filter(a => !(LV.sent[a.file] || {})[sentKey(a)]);
  if (!acts.length) {
    if (LV.say !== 'off') liveSay('ok');
    return;
  }
  const snap = {},
    files = new Set(acts.map(a => a.file));
  items.forEach(it => {
    if (files.has(it.file)) snap[it.name] = JSON.stringify(RV_FIELDS.map(k => it[k]));
  });
  const planned = S.planned.map(p => p.name).filter(n => files.has(n));
  LV.busy = true;
  liveSay('busy');
  const data = reviewFile();
  livePost('action', { author: data.author, role: data.role, review_date: data.written_at, actions: acts })
    .then(res => {
      LV.busy = false;
      if (!res.ok) {
        liveSay('off');
        toast(
          T('Not applied by Blender: {error} -- sent again in a moment.', {
            error: res.error || T('no answer')
          })
        );
        setTimeout(liveQueue, 4000);
        return;
      }
      const done = () => {
        items.forEach(it => {
          if (!(it.name in snap)) return;
          if (JSON.stringify(RV_FIELDS.map(k => it[k])) === snap[it.name]) {
            Object.assign(it, fresh(), { descEdit: undefined });
            delete LV.sent[it.file];
          } else {
            const s2 = (LV.sent[it.file] = LV.sent[it.file] || {});
            acts.forEach(a => {
              if (a.file === it.file) s2[sentKey(a)] = 1;
            });
          }
        });
        S.planned = S.planned.filter(p => !planned.includes(p.name));
        storeReview();
        liveSay('ok');
      };
      if ((M.live.version || 0) >= (res.version || 0)) done();
      else LV.pend = { v: res.version, fn: done };
      if (res.skipped && res.skipped.length)
        toast(
          T('Blender left out: {what}', { what: res.skipped.map(x => x[0] + ' (' + x[1] + ')').join(', ') })
        );
      if (LV.again) {
        LV.again = false;
        liveQueue();
      }
    })
    .catch(() => {
      LV.busy = false;
      liveSay('off');
      setTimeout(liveQueue, 4000);
    });
}
document.addEventListener('focusout', () =>
  setTimeout(() => {
    if (LIVE && !typing()) liveQueue();
  }, 0)
);
/* A render marked checked (live): out of "to check", as Render checked does in Blender. */
function liveChecked(it) {
  const keys = ((it.live || {}).checks || []).map(c => c.key);
  if (!keys.length) return;
  livePost('action', {
    author: M.live.user,
    role: M.live.role,
    review_date: isoNow(),
    actions: keys.map(key => ({ type: 'checked', file: it.file, key, push: false }))
  })
    .then(res => {
      if (!res.ok)
        toast(
          T('Not applied by Blender: {error} -- sent again in a moment.', {
            error: res.error || T('no answer')
          })
        );
    })
    .catch(noAnswer);
}
/* Never one's own doing: what this user wrote or validated isn't news to them. */
const own = who => !!who && String(who).toLowerCase() === String(M.live.user || '').toLowerCase();
/* What changed between two passes, for What's new: a note, a render, a validation. */
function newsOf(before, after) {
  const old = {};
  before.forEach(i => (old[i.name] = i));
  after.forEach(it => {
    const o = old[it.name];
    if (!o) return;
    const seen = new Set((o.notes || []).map(n => n.id));
    (it.notes || [])
      .filter(n => !seen.has(n.id) && !own(n.author))
      .forEach(n =>
        pushNews(
          n.type === 'rtk' ? 'rtk' : 'note',
          it.name,
          n.type === 'rtk'
            ? T('{who} wrote a retake', { who: n.author || '?' })
            : T('{who} wrote a note', { who: n.author || '?' }),
          (n.deps || []).map(d => LBL[d]).join(', ') + (n.frames ? ' · ' + n.frames : '') + ': ' + n.text
        )
      );
    if (it.render && it.render !== o.render) pushNews('render', it.name, T('New render'), it.render);
    Object.keys(it.ok || {}).forEach(d => {
      const a = it.ok[d],
        b = (o.ok || {})[d];
      if (a && !a.old && !own(a.by) && (!b || b.old || b.role !== a.role))
        pushNews('ok', it.name, T('{who} validated', { who: a.by || '?' }), LBL[d] + ' · ' + a.role);
    });
  });
}
/* New data from Blender: the views drawn again, the selection and the review kept. A field being typed in: once left. */
let pendData = null;
function applyData(nd) {
  const a = document.activeElement;
  if (a && a.matches && a.matches('textarea,input:not([type=checkbox]):not([type=radio])')) {
    pendData = nd;
    return;
  }
  pendData = null;
  if (nd.meta.live && M.live && nd.meta.live.root !== M.live.root) return location.reload();
  const before = items.map(i => ({ name: i.name, notes: i.notes, render: i.render, ok: i.ok }));
  loadData(nd);
  newsOf(before, items);
  if (S.review && S.review.auto && M.live.user)
    S.review = { name: M.live.user, role: M.live.role || TEAM, auto: true };
  if (!items.some(i => i.name === S.sel) && items[0]) S.sel = items[0].name;
  if (LV.pend && (M.live.version || 0) >= LV.pend.v) {
    const fn = LV.pend.fn;
    LV.pend = null;
    fn();
  }
  renderAll();
}
document.addEventListener('focusout', () =>
  setTimeout(() => {
    if (pendData) applyData(pendData);
  }, 0)
);
/* Waited on: Blender answers when something changed. A tab in the background asks nothing (a browser gives a server 6 connections). */
function liveStatus(s) {
  const p = $('#p-live');
  if (!p) return;
  p.dataset.state = s;
  p.title =
    s === 'on'
      ? T('Connected to Blender · {user}', { user: M.live.user || '' })
      : s === 'busy'
        ? T('Blender is busy: the page waits')
        : T("Blender doesn't answer: trying again");
  p.lastChild.textContent = s === 'on' ? 'live' : s === 'busy' ? T('busy') : T('disconnected');
}
let liveAb = null,
  polling = false;
function poll() {
  if (document.hidden) {
    polling = false;
    return;
  }
  polling = true;
  liveAb = window.AbortController ? new AbortController() : null;
  fetch('data?t=' + encodeURIComponent(M.live.token || '') + '&since=' + (M.live.version || 0), {
    cache: 'no-store',
    signal: liveAb ? liveAb.signal : undefined
  })
    .then(r => {
      if (!r.ok) throw r.status;
      return r.json();
    })
    .then(d => {
      if (d.reading) return location.reload();
      liveStatus(d.busy ? 'busy' : 'on');
      if (d.data && d.version !== (M.live.version || 0)) applyData(d.data);
      poll();
    })
    .catch(e => {
      if (e && e.name === 'AbortError') {
        polling = false;
        return;
      }
      liveStatus('off');
      setTimeout(poll, 2000);
    });
}
function liveStart() {
  if (!LIVE) return;
  /* Who writes is Blender's user and role (team when none is set there), not a review this browser kept from another page. */
  if (M.live.user && (!S.review || S.review.auto || M.live.guest)) {
    S.review = { name: M.live.user, role: M.live.role || TEAM, auto: true };
    renderAll();
  }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      if (liveAb) liveAb.abort();
    } else if (!polling) poll();
  });
  liveStatus('on');
  poll();
  liveQueue();
}
