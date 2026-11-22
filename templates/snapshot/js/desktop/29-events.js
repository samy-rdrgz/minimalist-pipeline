function v6Click(t) {
  const tou = t.closest('[data-tour]');
  if (tou) {
    tou.dataset.tour === 'next' ? tour(tourAt + 1) : tour(-1);
    return true;
  }
  if (t.closest('[data-tourstart]')) {
    $('#dlg').hidden = true;
    closeMenus();
    setTimeout(() => tour(0), 50);
    return true;
  }
  const th = t.closest('[data-theme]');
  if (th) {
    setTheme(th.dataset.theme);
    return true;
  }
  const nb = t.closest('#news-b');
  if (nb) {
    newsPop(nb);
    return true;
  }
  const shs = t.closest('[data-shot]');
  if (shs) {
    S.shot[S.sel] = shs.dataset.shot;
    S.ver[S.sel] = 0;
    renderProps();
    renderWide();
    return true;
  }
  if (t.closest('[data-render]')) {
    renderDlg();
    return true;
  }
  const rf = t.closest('[data-rf]');
  if (rf) {
    rform(cur())[rf.dataset.rf] = rf.dataset.v;
    renderDlg();
    return true;
  }
  const rsw = t.closest('[data-rfsw]');
  if (rsw) {
    const f = rform(cur());
    f.sound = f.sound === 'off' ? 'on' : 'off';
    renderDlg();
    return true;
  }
  const ns = t.closest('#notif-sys');
  if (ns) {
    notifSys(ns, !S.notifSys);
    return true;
  }
  if (t.closest('[data-rft]')) {
    const f = rform(cur());
    f.frames = !f.frames;
    if (!f.frames) {
      f.start = '';
      f.end = '';
    }
    renderDlg();
    return true;
  }
  const rp = t.closest('[data-rprio]');
  if (rp) {
    rform(cur()).prio += +rp.dataset.rprio;
    renderDlg();
    return true;
  }
  const rs = t.closest('[data-rshot]');
  if (rs) {
    const f = rform(cur());
    f.off[rs.dataset.rshot] = !f.off[rs.dataset.rshot];
    renderDlg();
    return true;
  }
  const rdp = t.closest('[data-rdept]');
  if (rdp) {
    const f = rform(cur());
    f.dept = rdp.dataset.rdept;
    f.preset = deptPreset(cur(), f.dept);
    closeMenus();
    renderDlg();
    return true;
  }
  const rpp = t.closest('[data-rpreset]');
  if (rpp) {
    rform(cur()).preset = rpp.dataset.rpreset;
    closeMenus();
    renderDlg();
    return true;
  }
  if (t.closest('[data-rprev]')) {
    $('#dlg').hidden = true;
    renderSend(cur(), true);
    return true;
  }
  if (t.closest('[data-rsend]')) {
    $('#dlg').hidden = true;
    renderSend(cur());
    return true;
  }
  const pa = t.closest('[data-plan]');
  if (pa) {
    planDlg(pa.dataset.plan, pa.dataset.k);
    return true;
  }
  const pd = t.closest('[data-pld]');
  if (pd) {
    pd.setAttribute('aria-pressed', pd.getAttribute('aria-pressed') !== 'true');
    return true;
  }
  const po = t.closest('[data-plok]');
  if (po) {
    const name = $('#pl-n').value.trim();
    if (!name) return true;
    A.plan({
      name,
      g: po.dataset.plok,
      kind: po.dataset.plk,
      desc: $('#pl-d').value.trim(),
      deps: [...document.querySelectorAll('[data-pld][aria-pressed=true]')].map(b => b.dataset.pld)
    });
    $('#dlg').hidden = true;
    refresh();
    msg(T('{name}: made when your review is imported', { name }));
    return true;
  }
  const pu = t.closest('[data-unplan]');
  if (pu) {
    A.unplan(+pu.dataset.unplan);
    refresh();
    return true;
  }
  if (t.closest('[data-bulk]')) {
    closeMenus();
    bulkDlg();
    return true;
  }
  const bk = t.closest('[data-bk]');
  if (bk) {
    const o = S.bulk;
    const k = bk.dataset.bk,
      v = bk.dataset.v;
    if (k === 'kind') {
      o.kind = v;
      o.g = '';
      o.d = DEPTS[v][0];
    } else if (k === 'on') o.on = v === '1';
    else o[k] = v;
    bulkDlg();
    return true;
  }
  const ckd = t.closest('[data-ckd]');
  if (ckd && !ckd.disabled) {
    const s = S.chk.on,
      d = ckd.dataset.ckd;
    s.has(d) ? s.delete(d) : s.add(d);
    checkedDlg();
    return true;
  }
  if (t.closest('[data-ckpush]')) {
    S.chk.push = !S.chk.push;
    checkedDlg();
    return true;
  }
  if (t.closest('[data-ckok]')) {
    checkedGo();
    return true;
  }
  if (t.closest('[data-bkok]')) {
    const o = S.bulk;
    let n = 0;
    items
      .filter(i => i.kind === o.kind && (!o.g || groupOf(i) === o.g))
      .forEach(i => {
        if (required(i).includes(o.d) === o.on) return;
        A.setReq(i, o.d, o.on);
        n++;
      });
    $('#dlg').hidden = true;
    refresh();
    msg(
      o.on
        ? T('{n} files: {dept} required', { n, dept: LBL[o.d] })
        : T('{n} files: {dept} not required', { n, dept: LBL[o.d] })
    );
    return true;
  }
  if (t.closest('[data-desc]')) {
    S.editDesc = true;
    renderProps();
    setTimeout(() => $('#desc-in')?.focus(), 0);
    return true;
  }
  if (t.closest('[data-descok]')) {
    const it = cur(),
      v = $('#desc-in').value.trim();
    A.desc(it, v);
    S.editDesc = false;
    refresh();
    return true;
  }
  if (t.closest('[data-desccancel]')) {
    S.editDesc = false;
    renderProps();
    return true;
  }
  const asd = t.closest('[data-aside]');
  if (asd) {
    const g = asd.dataset.aside;
    S.showAside[g] = !S.showAside[g];
    renderList();
    return true;
  }
  const ot = t.closest('[data-other]');
  if (ot) {
    S.ws = ot.dataset.other;
    renderAll();
    return true;
  }
  if (t.closest('[data-weights]')) {
    S.weights = !S.weights;
    renderQuick();
    renderList();
    return true;
  }
  return false;
}
/* A sent entry of a file, a note or a reply, by its id. */
const sentEntry = (it, id) => {
  for (const n of it.notes) {
    if (n.id === id) return n;
    const r = (n.replies || []).find(x => x.id === id);
    if (r) return r;
  }
  return null;
};
/* A touch screen, no keyboard to speak of: no keys shown. */
const TOUCH = () => matchMedia('(hover:none) and (pointer:coarse)').matches;
function helpDlg() {
  const L = [
    ['todo', null, T('To do'), T('not started')],
    ['wip', null, T('In progress'), T('dots')],
    ['done', null, T('Done'), T('full')],
    ['rework', null, T('Done, reworked'), T('reworked since the stable: the arrow in the diamond')],
    ['done', 'redo', T('To redo'), T('an earlier stage changed: the orange corner')],
    ['done', 'wait', T('Waiting'), T("an earlier stage isn't ready")],
    ['sup', null, T('Validated by a role'), T('tick, light')],
    ['val', null, T('Validated by the top role'), T('tick, {role}', { role: M.role || '' })],
    ['old', null, T('To review again'), T('validated on an older stable')],
    ['wip', 'rtk', T('Open retake'), T('the number: how many RTK')],
    ['val', 'rtk', T('Validated, then a retake'), T('read the corner with the shape')],
    ['val', 'you', T('You: validated'), T('not sent yet')],
    ['done', 'you-rtk', T('You: retake'), T('not sent yet')],
    ['done', null, T('Open note'), T('bubble at the bottom right'), 'n'],
    ['na', null, T('Not required'), T('dash')]
  ];
  const dl = $('#dlg');
  dl.hidden = false;
  dl.innerHTML = `<div class="dlg-in" role="dialog" aria-modal="true" aria-labelledby="hl-t"><h3 id="hl-t">${TOUCH() ? T('Legend') : T('Legend and keys')}</h3>
    <p class="faint" style="margin:0">${T('The diamond says the state, the corner what comes on top. The words beside it always say it again.')}</p>
    <ul class="legend-list">${L.map(([b, c, l, s, n]) => `<li>${glyph(b, c, 2, !!n)}<span>${l}<small>${s}</small></span></li>`).join('')}</ul>
    <div class="legend-keys"><div class="sec-h">${T('Keys')}</div>
    <ul class="legend-list" style="gap:6px">${[
      ['↑ ↓', T('previous / next file')],
      ['/', T('go to a file')],
      ['Ctrl K', T('search everything')],
      ['W', T('watch large')],
      ['← →', T('large: previous / next file')],
      [', .', T('one frame back / on')],
      [T('Space'), T('play')],
      ['C', T('compare: version A / version B, same frame')],
      ['M', T('sound')],
      ['I', T("large, reviewing: a range's start")],
      ['V', T('reviewing: validate all the done')],
      ['X', T('reviewing: a retake or remark on no department')],
      ['R', T('reply')],
      [T('Ctrl+Enter'), T('done writing')],
      [T('Esc'), T('close')]
    ]
      .map(
        ([k, l]) =>
          `<li style="grid-template-columns:110px 1fr"><span class="kbd" style="justify-self:start">${k}</span><span>${l}</span></li>`
      )
      .join('')}</ul>
    </div><div class="acts"><button class="btn" data-tourstart>${T('Guided tour')}</button><span style="flex:1"></span><button class="btn" data-dclose>${T('Close')}</button></div></div>`;
}
document.addEventListener('click', e => {
  const t = e.target;
  const lg = t.closest('[data-lang]');
  if (lg) {
    const l = lg.dataset.lang;
    MPI18n.choose(l);
    try {
      const u = new URL(location.href);
      if (l) u.searchParams.set('lang', l);
      else u.searchParams.delete('lang');
      location.replace(u.href);
    } catch (_) {
      location.reload();
    }
    return;
  }
  const mb = t.closest('[data-menu]');
  if (mb) {
    const m = document.getElementById(mb.dataset.menu);
    const o = m.hidden;
    closeMenus();
    m.hidden = !o;
    mb.setAttribute('aria-expanded', o);
    if (o) placeMenu(mb, m);
    return;
  }
  if (!t.closest('.menu')) closeMenus();
  if (
    !t.closest('.pop') &&
    !t.closest('#rv-open,#rv-open-w') &&
    !t.closest('[data-settings]') &&
    !t.closest('#news-b')
  )
    document.querySelectorAll('.pop').forEach(p => p.remove());
  const a = t.closest('[data-act]');
  if (a) {
    const k = a.dataset.act;
    closeMenus();
    if (k === 'videos') pickVideos();
    if (k === 'player') {
      const it = cur(),
        m = it && mVer(it),
        v = m && m.V[m.i];
      if (LIVE) livePlay(v && v.video);
      else if (v && v.video) {
        const u = videoSrc(v.video);
        if (u) open(u, '_blank');
        else toast(T('Video not found: choose the videos folder (Menu).'));
      }
    }
    if (k === 'share') {
      shareDialog();
      return;
    }
    if (k === 'snapshot') {
      livePost('open', { snapshot: 1 })
        .then(res =>
          toast(
            res.ok
              ? T("Blender opens the snapshot's export: confirm there")
              : T('Not opened: {error}', { error: TS(res.error) || '?' })
          )
        )
        .catch(noAnswer);
      return;
    }
    if (k === 'blender') {
      const it = cur();
      if (it) liveOpen(it.file);
    }
    if (k === 'blendfolder') {
      const it = cur();
      if (it) liveFolder({ folder: 'blend', file: it.file });
    }
    if (k === 'renderfolder') {
      const it = cur(),
        m = it && mVer(it),
        v = m && m.V[m.i];
      if (it)
        liveFolder({
          folder: 'render',
          file: it.file,
          path: v && v.video ? v.video.split('/').slice(0, -1).join('/') : ''
        });
    }
    if (k === 'folder')
      farmPost({ action: 'open', job_id: S.farmSel, value: 'folder' }, T('opens the folder'));
    if (k === 'log') farmPost({ action: 'open', job_id: S.farmSel, value: 'log:0' }, T('opens the log'));
    if (k === 'copy') {
      const u = location.href.split('#')[0] + '#' + S.sel;
      copyText(u, T('Link copied'));
    }
    if (k === 'collapse') {
      items.forEach(i => S.closed.add(groupOf(i)));
      renderTree();
      renderList();
    }
    if (k === 'expand') {
      S.closed.clear();
      renderTree();
      renderList();
    }
    if (k === 'clear') {
      S.quick = null;
      S.q = '';
      S.more.clear();
      S.dept = null;
      $('#q').value = '';
      renderQuick();
      renderList();
    }
    if (k === 'clear-more') {
      S.more.clear();
      S.dept = null;
      renderQuick();
      renderList();
    }
    return;
  }
  const tg = t.closest('[data-tg]');
  if (tg) {
    const g = tg.dataset.tg;
    S.closedTree.has(g) ? S.closedTree.delete(g) : S.closedTree.add(g);
    renderTree();
    return;
  }
  const fs = t.closest('[data-ffs]');
  if (fs) {
    S.ff.s = fs.dataset.ffs;
    renderQuick();
    renderList();
    renderTree();
    return;
  }
  if (t.closest('[data-ffm]')) {
    S.ff.mine = !S.ff.mine;
    renderQuick();
    renderList();
    renderTree();
    return;
  }
  const jb = t.closest('[data-job]');
  if (jb) {
    S.farmSel = jb.dataset.job;
    document.querySelectorAll('.job.sel').forEach(e => e.classList.remove('sel'));
    jb.classList.add('sel');
    renderProps();
    if (narrow()) document.body.classList.add('props-open');
    return;
  }
  const wk = t.closest('[data-wk]');
  if (wk) {
    S.farmSel = 'w:' + wk.dataset.wk;
    document.querySelectorAll('.job.sel').forEach(e => e.classList.remove('sel'));
    wk.classList.add('sel');
    renderProps();
    if (narrow()) document.body.classList.add('props-open');
    return;
  }
  const fa = t.closest('[data-farm]');
  if (fa) {
    farmAction(fa.dataset.farm, fa);
    return;
  }
  const pr = t.closest('[data-prio]');
  if (pr) {
    const j = F.jobs.find(x => x.id === S.farmSel);
    if (j)
      farmPost(
        { action: 'priority', job_id: j.id, value: j.priority + +pr.dataset.prio },
        T('priority {n}', { n: j.priority + +pr.dataset.prio })
      );
    return;
  }
  const nv = t.closest('[data-nver]');
  if (nv) {
    S.noteVer[S.sel] = nv.dataset.nver;
    closeMenus();
    refresh();
    renderWide();
    return;
  }
  if (t.closest('[data-wframe]')) {
    S.wframe = !S.wframe;
    renderWide();
    return;
  }
  const wnt = t.closest('[data-wnt]');
  if (wnt) {
    S.wnt = wnt.dataset.wnt;
    renderWide();
    return;
  }
  const vr = t.closest('[data-ver]');
  if (vr) {
    S.ver[S.sel] = +vr.dataset.ver;
    closeMenus();
    if (S.tab === 'renders' && !S.wide) S.tab = 'plan'; // Last renders' ▶: watched in the player
    renderProps();
    renderWide();
    return;
  }
  const ps = t.closest('[data-preset]');
  if (ps) {
    S.preset = ps.dataset.preset;
    closeMenus();
    renderProps();
    return;
  }
  const as = t.closest('[data-assign]');
  if (as) {
    const it = cur(),
      d = as.dataset.assign,
      a = A.assignToggle(it, d, as.dataset.p);
    closeMenus();
    refresh();
    msg(LBL[d] + ': ' + (a.join(', ') || T('nobody')));
    return;
  }
  if (t.closest('[data-relink]')) {
    const it = cur();
    if (it) relinkSend([it.file]);
    return;
  }
  const ga = t.closest('[data-gall]');
  if (ga) {
    S.gAll = ga.dataset.gall === '1';
    renderList();
    return;
  }
  if (t.closest('[data-gopen]')) {
    S.gOpen = !S.gOpen;
    renderList();
    return;
  }
  if (t.closest('[data-gclear]')) {
    S.gFocus = null;
    renderList();
    return;
  }
  const gs = t.closest('[data-gsort]');
  if (gs) {
    S.gSort = gs.dataset.gsort;
    renderList();
    return;
  }
  if (t.closest('[data-gwires]')) {
    S.gWires = !S.gWires;
    renderList();
    return;
  }
  if (t.closest('[data-gseqall]')) {
    S.gSeqAll = !S.gSeqAll;
    if (!S.gSeqAll) S.gSeq = new Set();
    renderList();
    return;
  }
  const gq = t.closest('[data-gseq]');
  if (gq) {
    const g = gq.dataset.gseq;
    if (!S.gSeq) S.gSeq = new Set();
    if (S.gSeq.has(g) || gq.classList.contains('gcap-b')) {
      S.gSeq.delete(g);
      const f = items.find(i => i.name === S.gFocus);
      if (f && f.kind === 'shot' && f.group === g) S.gFocus = null;
    } else S.gSeq.add(g);
    renderList();
    return;
  }
  const gn = t.closest('[data-gn]');
  if (gn) {
    const n = gn.dataset.gn;
    S.gFocus = S.gFocus === n ? null : n;
    S.sel = n;
    S.tab = 'links';
    renderList();
    renderProps();
    renderTree();
    if (narrow() && S.gFocus) document.body.classList.add('props-open');
    return;
  }
  const wd = t.closest('[data-wdep]');
  if (wd) {
    S.wdep = wd.dataset.wdep;
    renderWide();
    $('#w-ta')?.focus();
    return;
  }
  const wo = t.closest('[data-wok]');
  if (wo && !wo.disabled) {
    A.toggleVal(cur(), wo.dataset.wok);
    refresh();
    return;
  }
  const wk2 = t.closest('[data-wko]');
  if (wk2) {
    const d = wk2.dataset.wko;
    A.toggleRtk(cur(), d);
    S.wdep = d;
    S.wtype = 'rtk';
    refresh();
    $('#w-ta')?.focus();
    return;
  }
  const wt = t.closest('[data-wtype]');
  if (wt) {
    const tx = $('#w-ta')?.value || '';
    S.wtype = wt.dataset.wtype;
    renderWide();
    if ($('#w-ta')) {
      $('#w-ta').value = tx;
      $('#w-ta').focus();
    }
    return;
  }
  const sl = t.closest('[data-still]');
  if (sl) {
    A.still(cur(), sl.dataset.still);
    refresh();
    return;
  }
  const mkb = t.closest('[data-mark]');
  if (mkb) {
    A.mark(cur(), mkb.dataset.mark);
    refresh();
    return;
  }
  const fx = t.closest('[data-fix]');
  if (fx) {
    A.fixed(cur(), fx.dataset.fix, fx.hasAttribute('data-reopen'));
    refresh();
    return;
  }
  const zm = t.closest('[data-zoom]');
  if (zm) {
    const it = items.find(i => i.name === zm.dataset.zoom);
    const dl = $('#dlg');
    dl.hidden = false;
    dl.innerHTML = `<div class="dlg-in zoom" role="dialog" aria-modal="true" aria-label="${T('{name}, large', { name: it.name })}"><img src="${it.thumb}" alt="${it.name}"><div class="acts"><span class="mono" style="flex:1">${it.name}</span><button class="btn" data-dclose>${T('Close')}</button></div></div>`;
    return;
  }
  const actm = t.closest('[data-actm]');
  if (actm) {
    S.act = actm.dataset.actm;
    renderList();
    return;
  }
  const otk = t.closest('[data-otk]');
  if (otk) {
    S.ot = { kind: otk.dataset.otk, dept: '' };
    renderList();
    return;
  }
  if (t.closest('[data-otreload]')) {
    livePost('open', { progress: 1 })
      .then(r =>
        toast(r.ok ? T('Reading the project again…') : T('Not updated: {error}', { error: TS(r.error) }))
      )
      .catch(noAnswer);
    return;
  }
  const otd = t.closest('[data-otd]');
  if (otd) {
    S.ot.dept = otd.dataset.otd;
    closeMenus();
    renderList();
    return;
  }
  const sm = t.closest('[data-smode]');
  if (sm) {
    S.smode = sm.dataset.smode;
    renderQuick();
    renderList();
    return;
  }
  const tdk = t.closest('[data-tdk]');
  if (tdk) {
    S.td.kind = tdk.dataset.tdk;
    S.td.dept = '';
    renderAll();
    return;
  }
  const tdd = t.closest('[data-tdd]');
  if (tdd) {
    closeMenus();
    S.td.dept = tdd.dataset.tdd;
    renderAll();
    return;
  }
  const tdo = t.closest('[data-tdo]');
  if (tdo) {
    S.td.order = tdo.dataset.tdo;
    renderAll();
    return;
  }
  const tds = t.closest('[data-tdst]');
  if (tds) {
    S.td.st = tds.dataset.tdst;
    renderAll();
    return;
  }
  const tdw = t.closest('[data-tdw]');
  if (tdw) {
    closeMenus();
    S.td.who = tdw.dataset.tdw;
    renderAll();
    return;
  }
  if (t.closest('[data-tdcopy]')) {
    const c = todoText();
    copyText(c.text, T('Copied: {n} file|Copied: {n} files', { n: c.n }));
    return;
  }
  const sg = t.closest('[data-sgo]');
  if (sg) {
    S.ws = sg.dataset.skind;
    S.closed.clear();
    S.q = '';
    $('#q').value = '';
    const f = items.find(i => i.kind === S.ws && groupOf(i) === sg.dataset.sgo);
    S.sel = f.name;
    S.tab = 'plan';
    renderAll();
    document
      .querySelector(`.grp[data-g="${CSS.escape(sg.dataset.sgo)}"]`)
      ?.scrollIntoView({ block: 'start' });
    return;
  }
  const gz = t.closest('[data-gz]');
  if (gz) {
    const k = +gz.dataset.gz;
    if (k) zoomG(k > 0 ? 1.25 : 0.8);
    else fitG();
    drawGraph();
    return;
  }
  const ab = t.closest('[data-ab]');
  if (ab) {
    S.m.side = ab.dataset.ab;
    refresh();
    return;
  }
  const vb = t.closest('[data-verb]');
  if (vb) {
    S.m.b[S.sel] = +vb.dataset.verb;
    S.m.side = 'B';
    closeMenus();
    refresh();
    return;
  }
  const dv = t.closest('[data-demo-view]');
  if (dv) {
    closeMenus();
    setView(dv.dataset.demoView);
    return;
  }
  if (v6Click(t)) return;
  const ws = t.closest('[data-ws]');
  if (ws) {
    S.ws = ws.dataset.ws;
    S.quick = null;
    S.dept = null;
    if ((S.ws === 'shot' || S.ws === 'asset') && cur()?.kind !== S.ws)
      S.sel = items.find(i => i.kind === S.ws).name;
    if (S.ws === 'links') S.tab = 'links';
    else if (S.tab === 'links' && S.ws !== 'synth') S.tab = 'plan';
    renderAll();
    return;
  }
  if (t.closest('#rv-open')) {
    reviewPop(t.closest('#rv-open'));
    return;
  }
  if (t.closest('#rv-open-w')) {
    reviewPop(t.closest('#rv-open-w'));
    return;
  }
  if (t.closest('#rv-stop')) {
    S.review = null;
    LV.rv = null; // the next review, its own id
    S.form = null;
    S.reply = null;
    if (S.quick === 'mine') S.quick = null;
    renderAll();
    msg(T('Review left: your changes are kept in this browser.'));
    return;
  }
  if (t.closest('#rv-send')) {
    sendDialog();
    return;
  }
  if (t.closest('#help-b')) {
    helpDlg();
    return;
  }
  const psh = t.closest('[data-push]');
  if (psh) {
    const it = cur();
    pushRender(it, it && it.versions[+psh.dataset.push]);
    return;
  }
  if (t.closest('[data-pushall]')) {
    pushAllDlg();
    return;
  }
  if (t.closest('[data-export]')) {
    exportBreakdown();
    return;
  }
  if (t.closest('#search-b')) {
    searchDlg();
    return;
  }
  const sgf = t.closest('[data-sgofile]');
  if (sgf) {
    searchGo(sgf.dataset.sgofile, sgf.dataset.stab);
    return;
  }
  if (t.closest('[data-dclose]') || t.id === 'dlg') {
    $('#dlg').hidden = true;
    return;
  }
  if (t.closest('[data-rvgo]')) {
    $('#dlg').hidden = true;
    deliverReview();
    return;
  }
  if (t.closest('[data-rvclear]')) {
    if (!twice(t.closest('[data-rvclear]'), T('Sure? Click again: all cleared'))) return;
    clearReview();
    $('#dlg').hidden = true;
    if (S.m) S.m.sheet = null;
    renderAll();
    toast(T('Review cleared'));
    return;
  }
  if (t.closest('[data-qfold]')) {
    S.qFold = S.qFold === false;
    renderQuick();
    return;
  }
  const q = t.closest('[data-quick]');
  if (q) {
    S.quick = S.quick === q.dataset.quick ? null : q.dataset.quick;
    renderQuick();
    renderList();
    return;
  }
  const dp = t.closest('[data-dept]');
  if (dp) {
    S.dept = S.dept === dp.dataset.dept ? null : dp.dataset.dept;
    renderQuick();
    renderList();
    return;
  }
  const co = t.closest('[data-col]');
  if (co) {
    const k = co.dataset.col;
    S.hideCols.has(k) ? S.hideCols.delete(k) : S.hideCols.add(k);
    LS.set('mp-snapshot:cols', [...S.hideCols].join(','));
    renderQuick();
    renderList();
    // The menu stays open: several columns are often changed in a row.
    const b = document.querySelector('[data-menu="m-cols"]'),
      m = $('#m-cols');
    if (b && m) {
      m.hidden = false;
      b.setAttribute('aria-expanded', 'true');
      placeMenu(b, m);
    }
    return;
  }
  const mo = t.closest('[data-more]');
  if (mo) {
    const k = mo.dataset.more;
    S.more.has(k) ? S.more.delete(k) : S.more.add(k);
    if (k === 'tracked') LS.set('mp-snapshot:tracked', S.more.has(k) ? '1' : '');
    renderQuick();
    renderList();
    return;
  }
  const fo = t.closest('[data-fold]');
  if (fo) {
    const g = fo.dataset.fold;
    S.closed.has(g) ? S.closed.delete(g) : S.closed.add(g);
    renderTree();
    renderList();
    return;
  }
  const sq = t.closest('[data-seq]');
  if (sq) {
    const f = visible().find(i => i.group === sq.dataset.seq) || items.find(i => i.group === sq.dataset.seq);
    S.sel = f.name;
    S.wide = true;
    S.frame = 1;
    S.seqPlay = true;
    renderAll();
    if (!S.playing) togglePlay();
    msg(T('Playing {seq}: the shots one after the other', { seq: sq.dataset.seq }));
    return;
  }
  const tr = t.closest('.heat tr[data-g]');
  if (tr) {
    S.ws = 'shot';
    S.closed.clear();
    S.sel = items.find(i => i.group === tr.dataset.g).name;
    renderAll();
    return;
  }
  const fl = t.closest('[data-film]');
  if (fl) {
    select(fl.dataset.film, { open: false });
    return;
  }
  const gf = t.closest('[data-goto-file]');
  if (gf) {
    const n = gf.dataset.gotoFile,
      it = items.find(i => i.name === n);
    if (it) {
      if (it.kind !== S.ws) {
        S.ws = it.kind;
        S.sel = n;
        S.tab = 'plan';
        renderAll();
      } else select(n, { open: false });
    } else toast(T("{name} isn't in this snapshot", { name: n }));
    return;
  }
  const row = t.closest('.row[data-n],.tree li[data-n]');
  if (row) {
    select(row.dataset.n);
    return;
  }
  const tab = t.closest('[data-tab]');
  if (tab) {
    S.tab = tab.dataset.tab;
    renderProps();
    return;
  }
  const nf = t.closest('[data-nf]');
  if (nf) {
    S.noteFilter = nf.dataset.nf;
    refresh();
    return;
  }
  const go = t.closest('[data-goto]');
  if (go) {
    setFrame(fIdx(+go.dataset.goto));
    if (LIVE) liveFrame(cur(), +go.dataset.goto);
    if (S.tab !== 'plan' && !S.wide) {
      S.tab = 'plan';
      renderProps();
    }
    return;
  }
  const tp = t.closest('[data-tp]');
  if (tp && !tp.disabled) {
    const k = tp.dataset.tp;
    if (k === 'fprev') setFrame(S.frame - 1);
    if (k === 'fnext') setFrame(S.frame + 1);
    if (k === 'play') togglePlay();
    if (k === 'sprev' || k === 'snext') step(k === 'snext' ? 1 : -1);
    if (k === 'snd') {
      S.muted = !S.muted;
      PV.muted = S.muted;
      document.querySelectorAll('[data-tp="snd"]').forEach(b => {
        b.innerHTML = ic(S.muted ? 'b-mute_ipo_off' : 'b-mute_ipo_on');
        b.setAttribute('aria-pressed', !S.muted);
      });
    }
    if (k === 'in') {
      S.rangeStart = S.rangeStart == null ? S.frame : null;
      refresh();
    }
    return;
  }
  if (t.closest('[data-wide]')) {
    S.wide = true;
    renderWide();
    return;
  }
  if (t.closest('[data-wclose]')) {
    wideFull(false);
    S.wide = false;
    S.seqPlay = false;
    if (S.playing) togglePlay();
    renderWide();
    renderProps();
    return;
  }
  const wsS = t.closest('[data-wstep]');
  if (wsS) {
    step(+wsS.dataset.wstep);
    return;
  }
  if (t.closest('[data-wside]') || t.closest('[data-whead]')) {
    if (t.closest('[data-wside]')) S.wside = !S.wside;
    else S.whead = !S.whead;
    renderWide();
    return;
  }
  if (t.closest('[data-full]')) {
    wideFull(!S.wfull);
    return;
  }
  const v = t.closest('[data-val]');
  if (v && !v.disabled) {
    A.validate(cur(), v.dataset.val);
    refresh();
    return;
  }
  if (t.closest('[data-valall]')) {
    validateAll();
    return;
  }
  const u = t.closest('[data-undo]');
  if (u) {
    A.undo(cur(), u.dataset.undo);
    refresh();
    return;
  }
  const rk = t.closest('[data-rtk]');
  if (rk) {
    S.form = newForm(rk.dataset.rtk);
    refresh();
    document.getElementById('f-txt')?.focus();
    return;
  }
  if (t.closest('[data-gen]')) {
    S.form = newForm('');
    refresh();
    document.getElementById('f-txt')?.focus();
    return;
  }
  const fd = t.closest('[data-fdep]'),
    fsh = t.closest('[data-fshot]');
  if ((fd || fsh) && S.form) {
    const tx = $('#f-txt').value,
      l = fd ? S.form.deps : S.form.shots,
      x = fd ? fd.dataset.fdep : fsh.dataset.fshot;
    if (fsh && !x) S.form.shots = [];
    else if (l.includes(x)) l.splice(l.indexOf(x), 1);
    else l.push(x);
    // Every shot ticked: the same as All shots (one note, no shot named), not a note per shot.
    if (fsh && x && S.form.shots.length === (cur().shots || []).length) S.form.shots = [];
    refresh();
    $('#f-txt').value = tx;
    $('#f-txt').focus();
    return;
  }
  const ft = t.closest('[data-ftype]');
  if (ft) {
    const tx = $('#f-txt').value;
    S.form.type = ft.dataset.ftype;
    refresh();
    $('#f-txt').value = tx;
    $('#f-txt').focus();
    return;
  }
  if (t.closest('[data-fcancel]')) {
    S.form = null;
    refresh();
    return;
  }
  if (t.closest('[data-fok]')) {
    submitForm();
    return;
  }
  const rp = t.closest('[data-reply]');
  if (rp && !rp.disabled) {
    S.reply = rp.dataset.reply;
    refresh();
    document.getElementById('r-txt')?.focus();
    return;
  }
  if (t.closest('[data-rcancel]')) {
    S.reply = null;
    refresh();
    return;
  }
  const ro = t.closest('[data-rok]');
  if (ro) {
    A.reply(cur(), ro.dataset.rok, $('#r-txt').value.trim());
    S.reply = null;
    refresh();
    return;
  }
  const ur = t.closest('[data-unreply]');
  if (ur) {
    A.unreply(cur(), ur.dataset.unreply);
    refresh();
    return;
  }
  const ne = t.closest('[data-nedit]');
  if (ne) {
    S.nedit = ne.dataset.nedit;
    refresh();
    const ta = document.getElementById('ne-txt');
    if (ta) {
      ta.focus();
      ta.setSelectionRange(ta.value.length, ta.value.length);
    }
    return;
  }
  if (t.closest('[data-necancel]')) {
    S.nedit = null;
    refresh();
    return;
  }
  /* The key: m<at> a note not sent, r<note id>:<k> a reply not sent, else a sent entry's id (a note or a reply). */
  const ns = t.closest('[data-nesave]');
  if (ns) {
    const k = ns.dataset.nesave,
      v = wordsOf($('#ne-txt'));
    if (!v) return;
    const it = cur();
    if (k[0] === 'm' && !it.notes.some(x => x.id === k)) A.editMine(it, k.slice(1), v);
    else if (/^r.+:\d+$/.test(k) && !sentEntry(it, k)) {
      const [id, n] = k.slice(1).split(':');
      const r = (it.myReplies[id] || [])[+n];
      if (r) r.text = v;
    } else {
      const e = sentEntry(it, k);
      A.edit(it, k, e && e.text === v ? undefined : v);
    }
    S.nedit = null;
    refresh();
    return;
  }
  const nd = t.closest('[data-ndel]');
  if (nd) {
    if (!twice(nd, T('Sure? Click again'))) return;
    A.edit(cur(), nd.dataset.ndel, null);
    S.nedit = null;
    refresh();
    return;
  }
  const nu = t.closest('[data-neundo]');
  if (nu) {
    A.edit(cur(), nu.dataset.neundo, undefined);
    refresh();
    return;
  }
  const un = t.closest('[data-unnote]');
  if (un) {
    A.unnote(cur(), un.dataset.unnote);
    refresh();
    return;
  }
  const st = t.closest('[data-settings]');
  if (st) {
    settingsPop(st);
    return;
  }
  const rq = t.closest('[data-req]');
  if (rq && !rq.disabled) {
    const it = cur();
    A.toggleReq(it, rq.dataset.req);
    rq.setAttribute('aria-checked', required(it).includes(rq.dataset.req));
    renderList();
    renderTop();
    renderQuick();
    return;
  }
  const om = t.closest('[data-omit]');
  if (om && !om.disabled) {
    const it = cur();
    A.omit(it, om.dataset.omit);
    document.querySelector('.pop.set')?.remove();
    refresh();
    return;
  }
  if (t.closest('[data-fmopen]')) {
    fmDlg();
    return;
  }
  const ckw = t.closest('[data-ckwatch]');
  if (ckw) {
    const it = cur(),
      c = it && checksOf(it).find(x => x.key === ckw.dataset.ckwatch);
    if (!c) return;
    S.shot[it.name] = c.shot || '';
    const n = versOf(it).findIndex(v => v.folder === c.folder && (!c.department || !v.dept || v.dept === c.department));
    S.ver[it.name] = Math.max(0, n);
    S.m.side = 'A';
    renderProps();
    renderWide();
    return;
  }
  if (t.closest('[data-checked]')) {
    checkedDlg(t.closest('[data-checked]').dataset.checked);
    return;
  }
  if (t.closest('#pp-prev')) {
    step(-1);
    return;
  }
  if (t.closest('#pp-next')) {
    step(1);
    return;
  }
  if (t.closest('#pp-close')) {
    document.body.classList.remove('props-open');
    return;
  }
  if (t.closest('#pz-side')) {
    MPPanes.props();
    return;
  }
  if (t.closest('[data-pmax]')) {
    MPPanes.main();
    return;
  }
  if (t.closest('#out-toggle')) {
    document.body.classList.toggle('out-open');
    return;
  }
  if (t.closest('#scrim')) {
    document.body.classList.remove('out-open');
    return;
  }
});
/* What's new, Notify me in the system too: a switch, turned back off if the browser says no. */
function notifSys(b, on) {
  const set = v => {
    S.notifSys = v;
    b.setAttribute('aria-checked', v);
  };
  set(on);
  if (!on) return;
  if (!window.Notification) {
    set(false);
    toast(T('This browser has no notifications'));
    return;
  }
  Promise.resolve(Notification.requestPermission())
    .then(p => {
      if (p !== 'granted') {
        set(false);
        toast(T('Notifications refused here: the bell stays up to date'));
      }
    })
    .catch(() => set(false));
}
document.addEventListener('change', e => {
  const rn = e.target.closest && e.target.closest('[data-rfn]');
  if (rn) rform(cur())[rn.dataset.rfn] = e.target.value;
});
document.addEventListener('input', e => {
  if (e.target.id === 'om-why') {
    A.omitReason(cur(), e.target.value);
    renderList();
  }
});
document.addEventListener('keydown', e => {
  const typing = e.target.matches('input,textarea');
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' && !isMob()) {
    e.preventDefault();
    searchDlg();
    return;
  }
  if (e.target.id === 'w-ta' && e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    wideAdd();
    return;
  }
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    if (S.form && document.getElementById('f-txt')) {
      submitForm();
      return;
    }
    if (S.reply) {
      document.querySelector('[data-rok]')?.click();
      return;
    }
    if (S.nedit) {
      document.querySelector('[data-nesave]')?.click();
      return;
    }
  }
  if (e.key === 'Escape' && tourAt >= 0) {
    tour(-1);
    return;
  }
  if (e.key === 'Escape') {
    if (!$('#dlg').hidden) {
      $('#dlg').hidden = true;
      return;
    }
    if (S.wfull && !document.querySelector('.pop')) {
      wideFull(false);
      return;
    }
    if (S.form || S.reply || S.nedit) {
      S.form = null;
      S.reply = null;
      S.nedit = null;
      refresh();
      return;
    }
    if (document.querySelector('.pop')) {
      document.querySelectorAll('.pop').forEach(p => p.remove());
      return;
    }
    closeMenus();
    if (typing) {
      e.target.blur();
      return;
    }
    if (S.wide) {
      S.wide = false;
      S.seqPlay = false;
      if (S.playing) togglePlay();
      renderWide();
      renderProps();
      return;
    }
    if (document.body.classList.contains('props-open')) document.body.classList.remove('props-open');
    else document.body.classList.remove('out-open');
    return;
  }
  if (typing || !$('#dlg').hidden) return;
  const k = e.key;
  if (k === '/') {
    e.preventDefault();
    $('#q').focus();
    return;
  }
  if (k === '?') {
    helpDlg();
    return;
  }
  if (k === 'ArrowDown' && !S.wide) {
    e.preventDefault();
    step(1);
  }
  if (k === 'ArrowUp' && !S.wide) {
    e.preventDefault();
    step(-1);
  }
  if (S.wide && k === 'ArrowRight' && !e.target.closest('[data-scrub]')) {
    step(1);
  }
  if (S.wide && k === 'ArrowLeft' && !e.target.closest('[data-scrub]')) {
    step(-1);
  }
  if (e.target.closest('[data-scrub]') && (k === 'ArrowRight' || k === 'ArrowLeft')) {
    e.preventDefault();
    setFrame(S.frame + (k === 'ArrowRight' ? 1 : -1));
  }
  if (k === 'w' || k === 'W') {
    if (cur()) {
      S.wide = !S.wide;
      renderWide();
      renderProps();
    }
  }
  if (k === ',') {
    setFrame(S.frame - 1);
  }
  if (k === '.') {
    setFrame(S.frame + 1);
  }
  if (k === ' ' && (S.wide || S.tab === 'plan')) {
    e.preventDefault();
    togglePlay();
  }
  if ((k === 'c' || k === 'C') && cur() && versOf(cur()).length > 1) {
    S.m.side = S.m.side === 'A' ? 'B' : 'A';
    refresh();
  }
  if (k === 'm' || k === 'M') {
    document.querySelector('[data-tp="snd"]')?.click();
  }
  if (!S.review) return;
  if (k === 'v' || k === 'V') validateAll();
  if (k === 'x' || k === 'X') {
    e.preventDefault();
    if (S.wide) {
      S.wtype = 'rtk';
      renderWide();
      $('#w-ta')?.focus();
      return;
    }
    S.tab = 'plan';
    S.form = newForm('');
    refresh();
    document.getElementById('f-txt')?.focus();
  }
  if ((k === 'i' || k === 'I') && S.wide) {
    S.rangeStart = S.rangeStart == null ? S.frame : null;
    refresh();
  }
  if (k === 'r' || k === 'R') {
    const b = document.querySelector('[data-reply]:not([disabled])');
    if (b) {
      e.preventDefault();
      b.click();
    }
  }
});
$('#q').addEventListener('input', e => {
  S.q = e.target.value.trim().toLowerCase();
  S.ff.q = S.q;
  renderList();
});
$('#q').addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    const f = visible()[0];
    if (f) {
      select(f.name);
      e.target.blur();
    }
  }
});
$('#tree-q').addEventListener('input', e => {
  S.tq = e.target.value.trim().toLowerCase();
  renderTree();
});
/* Menu › Interface scale: a slider, 0.5 to 1.5 in nine steps -- applied once let go (the page
   drawn again at each step made dragging it jerky), its figure shown while dragging. */
function setScale(s) {
  S.scaleV = s;
  document.documentElement.style.setProperty('--scale', s);
  LS.set('mp-snapshot:scale', s);
  const i = $('#scale-in');
  if (i) {
    i.value = s;
    $('#scale-v').textContent = s.toFixed(2);
  }
  requestAnimationFrame(drawWires);
}
try {
  const s = parseFloat(localStorage.getItem('mp-snapshot:scale'));
  if (s >= 0.5 && s <= 1.5) setScale(s);
} catch (_) {}
$('#scale-in').addEventListener('input', e => ($('#scale-v').textContent = (+e.target.value).toFixed(2)));
$('#scale-in').addEventListener('change', e => setScale(+e.target.value));
new ResizeObserver(() => drawWires()).observe($('#pbody'));
new ResizeObserver(() => {
  if (S.ws === 'links') drawGraph();
}).observe($('#list'));
document.addEventListener(
  'scroll',
  e => {
    if (!e.target.closest || !e.target.closest('.menu')) closeMenus();
  },
  true
);
addEventListener('resize', () => {
  closeMenus();
  document.querySelectorAll('.pop.fx').forEach(p => p.remove());
});
document.addEventListener('dblclick', e => {
  const gn = e.target.closest('[data-gn]');
  if (gn) {
    const it = items.find(i => i.name === gn.dataset.gn);
    if (!it) return;
    S.ws = it.kind;
    S.sel = it.name;
    S.tab = 'plan';
    S.gFocus = null;
    renderAll();
  }
});
document.addEventListener('change', e => {
  if (e.target.matches && e.target.matches('.rv-load')) {
    const f = e.target.files[0];
    e.target.value = '';
    closeMenus();
    loadReview(f);
  }
});

/* A row scrolled sideways (.join, .filters, .ws): a fade on the side where more is hidden; a mouse wheel scrolls it. */
const SX = '.join,.filters,.ws';
function sxFade(el) {
  const l = el.scrollLeft > 1,
    r = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
  el.classList.toggle('sx-l', l);
  el.classList.toggle('sx-r', r);
}
let sxT = 0;
const sxAll = () => {
  if (sxT) return;
  sxT = requestAnimationFrame(() => {
    sxT = 0;
    document.querySelectorAll(SX).forEach(sxFade);
  });
};
document.addEventListener(
  'scroll',
  e => {
    if (e.target.matches && e.target.matches(SX)) sxFade(e.target);
  },
  true
);
document.addEventListener(
  'wheel',
  e => {
    const el = e.target.closest && e.target.closest(SX);
    if (!el || el.scrollWidth <= el.clientWidth + 1 || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
    e.preventDefault();
    el.scrollLeft += e.deltaY;
  },
  { passive: false }
);
new MutationObserver(sxAll).observe(document.body, { childList: true, subtree: true });
addEventListener('resize', sxAll);
sxAll();

/* Over time's hover (Breakdown). */
document.addEventListener('pointermove', e => {
  if (e.target.closest && e.target.closest('.ot-box')) otHover(e);
  if (e.target.closest && e.target.closest('.ac-box')) actHover(e);
});
document.addEventListener('pointerout', e => {
  if (e.target.closest && e.target.closest('.ot-box') && !e.relatedTarget?.closest?.('.ot-box')) otLeave(e);
  if (e.target.closest && e.target.closest('.ac-box') && !e.relatedTarget?.closest?.('.ac-box')) actLeave(e);
});
