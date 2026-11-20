/* ---------- The data: page_data() (lib/monitoring/snapshot_page.py), as the views read it ----------
   The export's own shape, read once here (and again on each live update, applyData()):
   the views read items, M, DEPTS and F, never the raw data. */
const RAW = JSON.parse(document.getElementById('data').textContent);
const M = {},
  DEPTS = { shot: [], asset: [] },
  items = [],
  F = { status: '', jobs: [], workers: [], me: {}, left: '', presets: [], preset: '' };
const $ = s => document.querySelector(s);
/* This browser's storage, never throwing (a private window, storage blocked): get → null;
   set with nothing ('' or null) removes the key. */
const LS = {
  get(k) {
    try {
      return localStorage.getItem(k);
    } catch (_) {
      return null;
    }
  },
  set(k, v) {
    try {
      if (v == null || v === '') localStorage.removeItem(k);
      else localStorage.setItem(k, v);
    } catch (_) {}
  }
};
const esc = s =>
  String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const ic = (id, cls = 'i') => `<svg class="${cls}" aria-hidden="true"><use href="#${id}"/></svg>`;
const pct = v => (v == null ? '–' : Math.round(v * 100) + ' %');
/* A department's name as the project writes it, a capital first; short, its first four letters. */
const LBL = new Proxy(
  {},
  { get: (_, d) => (typeof d === 'string' ? d.charAt(0).toUpperCase() + d.slice(1) : d) }
);
const AB = new Proxy(
  {},
  {
    get: (_, d) =>
      typeof d === 'string' ? (d.length > 5 ? d.charAt(0).toUpperCase() + d.slice(1, 4) : LBL[d]) : d
  }
);
/* Thumbnails: each stored once (images, by hash), a blob URL once. */
const IMG = {},
  URLS = {};
function img(id) {
  if (!id) return '';
  if (URLS[id]) return URLS[id];
  const b64 = IMG[id];
  if (!b64) return '';
  try {
    const b = atob(b64),
      a = new Uint8Array(b.length);
    for (let i = 0; i < b.length; i++) a[i] = b.charCodeAt(i);
    URLS[id] = URL.createObjectURL(new Blob([a], { type: 'image/jpeg' }));
  } catch (_) {
    URLS[id] = 'data:image/jpeg;base64,' + b64;
  }
  return URLS[id];
}
/* Dates in the page's language: 16/11 19:10. */
/* Dates and times: day before month, a 24-hour clock, in every language (English as British English writes them). */
const DTL = () => (LOCALE() === 'en' ? 'en-GB' : LOCALE());
const HM = { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' };
const fmtD = iso => {
  const d = new Date(iso);
  return isNaN(d)
    ? ''
    : d.toLocaleDateString(DTL(), { day: '2-digit', month: '2-digit' }) +
        ' ' +
        d.toLocaleTimeString(DTL(), HM);
};
const LOCALE = () => (typeof MPI18n !== 'undefined' ? MPI18n.lang : 'en');
/* The frames a video has when it says nothing (no fps, no length known yet). */
let NF = 120;
/* What a review left on a file (A.*): fresh for each file, kept across live updates by name. */
const fresh = () => ({
  edits: {},
  marked: {},
  mine: {},
  myNotes: [],
  myReplies: {},
  setAside: undefined,
  req: null,
  assign: null,
  still: {},
  fixed: {}
});
/* One file of page_data() as the views read it. */
function adapt(r, keyName) {
  const L = r.live || {};
  const versions = [];
  if (L.versions)
    Object.entries(L.versions).forEach(([line, rows]) =>
      rows.forEach(v =>
        versions.push({
          shot: line,
          folder: v.folder,
          dept: v.department || '',
          at: v.at || 0,
          video: v.video || null,
          first: v.first ?? null
        })
      )
    );
  else
    (r.renders || [])
      .filter(l => l.folder)
      .forEach(l =>
        versions.push({
          shot: (l.shot_list || []).length === 1 && !l.whole ? l.shot_list[0] : '',
          folder: l.folder,
          dept: l.department || '',
          at: 0,
          video: l.video || null,
          first: l.first ?? null,
          behind: !!l.behind,
          status: l.status || null
        })
      );
  return Object.assign(r, {
    kind: r.kind === 'shot' ? 'shot' : 'asset',
    stableFile: r.stable || '',
    stable: r.stable_v || '',
    wip: r.wip_v || '',
    render: r.render_ref || '',
    toCheck: !!r.to_check,
    thumb: img(r.thumb),
    thumbKey: r.thumb,
    versions,
    work: r.work ?? null,
    links: (L.links || []).map(l => ({ name: keyName[l.key] || '', file: l.file, newer: l.newer || '' })),
    linkedBy: (L.linked_by || []).map(k => keyName[k]).filter(Boolean)
  });
}
/* The whole data in: first load, then each live update (the review left on each file kept). */
function loadData(raw) {
  const kept = {};
  items.forEach(it => {
    kept[it.name] = {
      edits: it.edits,
      marked: it.marked,
      mine: it.mine,
      myNotes: it.myNotes,
      myReplies: it.myReplies,
      setAside: it.setAside,
      req: it.req,
      assign: it.assign,
      still: it.still,
      fixed: it.fixed,
      descEdit: it.descEdit
    };
  });
  Object.assign(IMG, raw.images || {});
  Object.keys(M).forEach(k => delete M[k]);
  Object.assign(M, raw.meta || {});
  DEPTS.shot = (M.departments || {}).shot || [];
  DEPTS.asset = (M.departments || {}).asset || [];
  if (!M.live) M.live = { user: '', role: '' };
  const keyName = {};
  (raw.items || []).forEach(r => {
    if (r.live && r.live.key) keyName[r.live.key] = r.name;
  });
  items.splice(
    0,
    items.length,
    ...(raw.items || []).map(r => Object.assign(adapt(r, keyName), fresh(), kept[r.name] || {}))
  );
  const f = raw.farm || {};
  Object.assign(F, { status: '', jobs: [], workers: [], me: {}, left: '', presets: [], preset: '' }, f);
  F.jobs.forEach(j => {
    if (j.archived == null) j.archived = false;
  });
}
loadData(RAW);
const first = items.find(i => i.kind === 'shot') || items[0];
const S = {
  ws: first ? first.kind : 'shot',
  sel: first ? first.name : '',
  quick: null,
  more: new Set(),
  dept: null,
  q: '',
  tq: '',
  tab: 'plan',
  closed: new Set(),
  review: null,
  noteFilter: 'open',
  frame: 1,
  playing: false,
  muted: true,
  form: null,
  reply: null,
  rangeStart: null,
  wide: false,
  wfull: false,
  closedTree: new Set(),
  ver: {},
  wdep: null,
  wtype: 'rtk',
  g: { x: 0, y: 0, z: 1, init: false },
  smode: 'done',
  ot: { kind: 'shot', dept: '' },
  act: 'files', // Activity: files worked, or time
  td: { kind: 'shot', st: null, dept: '', me: false }, // st null: tdSt() by the role
  shot: {},
  seqPlay: false,
  planned: [],
  showAside: {},
  theme: 'dark',
  notifSys: false,
  editDesc: false,
  weights: false,
  scaleV: 1,
  bulk: null,
  ff: { s: '', mine: false, q: '' },
  farmSel: null,
  preset: F.preset || 'NONE',
  gAll: false,
  gFocus: null
};
/* Tracked only (Filters): remembered by this browser. */
if (LS.get('mp-snapshot:tracked')) S.more.add('tracked');
