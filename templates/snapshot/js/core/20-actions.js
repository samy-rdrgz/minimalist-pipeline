/* ---------- The review's actions (shared by both views) ----------
   The only functions that change the files. Desktop and phone call them, then refresh().
   None touches the DOM. Each is an action of lib/monitoring/review_import.py (named at the line's end). */
const canVal = (it, d) => !!S.review && S.review.role !== TEAM && isDone(stOf(it, d)) && !it.ok[d];
/* Done on the stable, no new version: one forgotten when it was made. Anyone reviewing may (it's not a validation). */
/* A note sent already that this reviewer wrote: theirs to change or delete. */
const ownNote = n =>
  !!S.review &&
  !n.mine &&
  !!n.author &&
  String(n.author).trim().toLowerCase() ===
    String(me() || '')
      .trim()
      .toLowerCase();
const canMark = (it, d) => !!S.review && !!it.stableFile && !omitted(it) && !isDone(it.states[d] || 'todo');
/* The frames written: Blender's numbers (fNo), a range from I to the frame shown. */
const rangeStr = () =>
  !curRendered()
    ? ''
    : S.rangeStart != null && S.rangeStart !== S.frame
      ? 'f' + fNo(Math.min(S.rangeStart, S.frame)) + '-' + fNo(Math.max(S.rangeStart, S.frame))
      : 'f' + fNo(S.frame);
const A = {
  validate(it, d) {
    it.mine[d] = 'val';
  }, // validate
  toggleVal(it, d) {
    if (it.mine[d] === 'val') delete it.mine[d];
    else it.mine[d] = 'val';
  }, // validate / unvalidate
  validateAll(it) {
    let n = 0;
    required(it).forEach(d => {
      if (canVal(it, d) && !it.rtk[d] && !it.mine[d]) {
        it.mine[d] = 'val';
        n++;
      }
    });
    return n;
  },
  undo(it, d) {
    delete it.mine[d];
    it.myNotes = it.myNotes.filter(n => n.dept !== d || n.type !== 'rtk');
  },
  toggleRtk(it, d) {
    if (it.mine[d] === 'rtk') {
      A.undo(it, d);
      return false;
    }
    it.mine[d] = 'rtk';
    return true;
  }, // rtk
  note(it, { type, dept, deps, text, frames, shot }) {
    // note (frames, departments, a block's shot)
    deps = deps || (dept ? [dept] : []);
    it.myNotes.unshift({
      type,
      deps,
      dept: deps[0] || null,
      text,
      frames: frames || '',
      shot: shot || '',
      author: S.review.name,
      date: new Date().toISOString(),
      replies: [],
      at: Date.now() + Math.random()
    });
    if (type === 'rtk') deps.forEach(d => (it.mine[d] = 'rtk'));
  },
  unnote(it, at) {
    const n = it.myNotes.find(x => String(x.at) === String(at));
    it.myNotes = it.myNotes.filter(x => x !== n);
    if (n && n.type === 'rtk')
      (n.deps || [n.dept]).filter(Boolean).forEach(d => {
        if (!it.myNotes.some(x => x.type === 'rtk' && (x.deps || [x.dept]).includes(d))) delete it.mine[d];
      });
  },
  reply(it, id, text) {
    if (!text) return;
    (it.myReplies[id] = it.myReplies[id] || []).push({
      text,
      author: S.review.name,
      date: new Date().toISOString()
    });
  }, // reply
  unreply(it, id) {
    it.myReplies[id]?.pop();
    if (!it.myReplies[id]?.length) delete it.myReplies[id];
  },
  fixed(it, id) {
    if (it.fixed[id]) delete it.fixed[id];
    else it.fixed[id] = true;
  }, // fixed
  /* A note sent already, its author's: its words changed (text), or deleted (null); undefined takes it back. */
  edit(it, id, t) {
    if (t === undefined) delete it.edits[id];
    else it.edits[id] = t;
  }, // edit / delete
  editMine(it, at, t) {
    const n = it.myNotes.find(x => String(x.at) === String(at));
    if (n && t) n.text = t;
  },
  mark(it, d) {
    if (d in it.marked) {
      delete it.marked[d];
      if (it.mine[d] === 'val') delete it.mine[d];
    } else it.marked[d] = !isDone(it.states[d] || 'todo');
  }, // done
  still(it, d) {
    if (it.still[d]) delete it.still[d];
    else it.still[d] = true;
  }, // still_done
  assignToggle(it, d, p) {
    let a = [...assignOf(it, d)];
    a = !p ? [] : a.includes(p) ? a.filter(x => x !== p) : [...a, p]; // assign
    it.assign = it.assign || {};
    it.assign[d] = a;
    if (JSON.stringify(a) === JSON.stringify(it.assignees[d] || [])) {
      delete it.assign[d];
      if (!Object.keys(it.assign).length) it.assign = null;
    }
    return a;
  },
  setReq(it, d, on) {
    if (!it.req) {
      it.req = {};
      DEPTS[it.kind].forEach(x => (it.req[x] = x in it.states));
    }
    it.req[d] = on;
  }, // departments (add / remove)
  toggleReq(it, d) {
    A.setReq(it, d, !required(it).includes(d));
  },
  omit(it, state, reason = '') {
    it.setAside = state ? { state, reason } : null;
  }, // omit (on_hold / cancelled)
  omitReason(it, r) {
    it.setAside = { ...(it.setAside || it.omit || {}), reason: r };
  },
  desc(it, v) {
    if (v !== it.desc) it.descEdit = v;
    else delete it.descEdit;
  }, // description
  plan(p) {
    S.planned.push(p);
  },
  unplan(i) {
    S.planned.splice(i, 1);
  }, // create (shot / asset)
  /* What the review holds, in words. */
  changes() {
    const ch = [];
    items.filter(touched).forEach(it => {
      Object.entries(it.mine).forEach(([d, v]) =>
        ch.push(`${it.name} · ${LBL[d]}: ${v === 'val' ? T('validated') : T('retake')}`)
      );
      it.myNotes.forEach(n =>
        ch.push(
          `${it.name} · ${n.type === 'rtk' ? 'retake' : 'remarque'}${n.dept ? ' ' + LBL[n.dept] : ''}${n.frames ? ' ' + n.frames : ''}`
        )
      );
      Object.values(it.myReplies)
        .flat()
        .forEach(() => ch.push(`${it.name} · ${T('reply')}`));
      if (it.setAside !== undefined)
        ch.push(
          `${it.name} · ${it.setAside && it.setAside.state ? (it.setAside.state === 'cancelled' ? T('cancelled') : T('on hold')) : T('active again')}`
        );
      if (it.req) ch.push(`${it.name} · ${T('required departments changed')}`);
      Object.keys(it.still).forEach(d => ch.push(`${it.name} · ${LBL[d]}: ${T('still done')}`));
      Object.entries(it.edits || {}).forEach(([, t]) =>
        ch.push(`${it.name} · ${t === null ? T('note deleted') : T('note edited')}`)
      );
      Object.entries(it.marked || {}).forEach(([d, v]) =>
        ch.push(`${it.name} · ${LBL[d]}: ${v ? T('done on the stable') : T('not done')}`)
      );
      Object.keys(it.fixed).forEach(() => ch.push(`${it.name} · ${T('note marked fixed')}`));
      if (it.assign)
        Object.entries(it.assign).forEach(([d, a]) =>
          ch.push(`${it.name} · ${LBL[d]} → ${a.join(', ') || T('nobody')}`)
        );
      if (it.descEdit !== undefined) ch.push(`${it.name} · description`);
    });
    S.planned.forEach(p => ch.push(`${p.name} · ${p.kind === 'shot' ? T('new shot') : T('new file')}`));
    return ch;
  }
};
