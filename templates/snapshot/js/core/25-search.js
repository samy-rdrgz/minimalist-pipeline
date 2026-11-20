/* ---------- Search everything: every text the page holds, file by file ----------
   A file's name and description, its notes, retakes and to-dos (their text, author,
   departments), their replies, the assignees, the departments required and why one
   waits, the render presets its renders used; with a review going on, its own notes and
   replies too. Each word typed must be found in the file (anywhere in it); each place
   holding one is listed under it, the words marked. Desktop (Ctrl+K, the top bar) and
   phone (its menu). */
const SEARCH_MAX = 60;
/* A file's texts: [where, text, then] -- then: the tab that shows it (notes, or the plan). */
function searchTexts(it) {
  const out = [
    [T('File'), it.name, 'plan'],
    [T('Description'), it.descEdit !== undefined ? it.descEdit : it.desc, 'plan']
  ];
  const kind = n => (n.type === 'rtk' ? 'RTK' : n.type === 'todo' ? T('to do') : T('Note'));
  const deps = n => ((n.deps || []).length ? ' · ' + n.deps.map(d => LBL[d] || d).join(', ') : '');
  (it.notes || []).forEach(n => {
    out.push([kind(n) + deps(n) + ' · ' + (n.author || ''), n.text, 'notes']);
    (n.replies || []).forEach(r => out.push([T('A reply') + ' · ' + (r.author || ''), r.text, 'notes']));
  });
  (it.myNotes || []).forEach(n =>
    out.push([kind(n) + (n.dept ? ' · ' + (LBL[n.dept] || n.dept) : '') + ' · ' + T('you'), n.text, 'notes'])
  );
  Object.values(it.myReplies || {}).forEach(rs =>
    rs.forEach(r => out.push([T('A reply') + ' · ' + T('you'), r.text, 'notes']))
  );
  required(it).forEach(d => {
    const a = assignOf(it, d),
      x = info(it, d);
    out.push([T('Department'), LBL[d] + (x.s ? ' · ' + x.s : ''), 'plan']);
    if (a.length) out.push([T('Assigned to') + ' · ' + LBL[d], a.join(', '), 'plan']);
  });
  const rp = it.rp || {};
  const presets = [...new Set([...(rp.used || []), ...Object.values(rp.by || {})].filter(Boolean))];
  if (presets.length) out.push([T('Render presets'), presets.join(', '), 'plan']);
  return out.filter(x => x[1]);
}
const searchNorm = s =>
  String(s || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');
/* The files holding every word of q: [{it, whole, hits: [[where, text, tab]]}], at most SEARCH_MAX. */
function searchAll(q) {
  const phrase = searchNorm(q).trim(),
    words = phrase.split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const out = [];
  for (const it of items) {
    const texts = searchTexts(it).map(x => [...x, searchNorm(x[1]) + ' ' + searchNorm(x[0])]);
    if (!words.every(w => texts.some(x => x[3].includes(w)))) continue;
    // First the files where the words come together, as typed, in one place.
    const whole = texts.some(x => x[3].includes(phrase));
    out.push({
      it,
      whole,
      hits: texts
        .filter(x => words.some(w => x[3].includes(w)))
        // In the text itself first, then in its label only (an author, a department).
        .map(x => [x, words.filter(w => searchNorm(x[1]).includes(w)).length])
        .sort((a, b) => b[1] - a[1])
        .map(([x]) => x.slice(0, 3))
    });
  }
  return out.sort((a, b) => b.whole - a.whole).slice(0, SEARCH_MAX);
}
/* text cut around its first word found, the words marked (escaped). */
function searchSnippet(text, q, room = 90) {
  const words = searchNorm(q).split(/\s+/).filter(Boolean),
    n = searchNorm(text);
  let at = Math.min(...words.map(w => n.indexOf(w)).filter(i => i >= 0));
  if (!isFinite(at)) at = 0;
  const from = Math.max(0, at - 30),
    to = Math.min(text.length, from + room);
  const part = text.slice(from, to),
    pn = n.slice(from, to);
  // Marked by position in the normalized text (same length: accents removed one for one).
  const marks = new Array(part.length).fill(false);
  words.forEach(w => {
    for (let i = pn.indexOf(w); i >= 0; i = pn.indexOf(w, i + 1))
      for (let k = 0; k < w.length; k++) marks[i + k] = true;
  });
  let h = '',
    on = false;
  for (let i = 0; i < part.length; i++) {
    if (marks[i] !== on) {
      h += marks[i] ? '<mark>' : '</mark>';
      on = marks[i];
    }
    h += esc(part[i]);
  }
  if (on) h += '</mark>';
  return (from ? '…' : '') + h + (to < text.length ? '…' : '');
}
function searchResultsHTML(q) {
  if (!q.trim())
    return `<p class="faint">${T('Names, descriptions, notes, replies, assignees, departments, render presets.')}</p>`;
  const res = searchAll(q);
  if (!res.length) return `<p class="faint">${T('Nothing found.')}</p>`;
  return (
    res
      .map(
        ({ it, hits }) =>
          `<button class="sr" data-sgofile="${esc(it.name)}" data-stab="${hits.some(h => h[2] === 'notes') ? 'notes' : 'plan'}"><span class="sr-h"><b class="mono">${esc(it.name)}</b><span class="faint">${it.kind === 'shot' ? T('shot') : T('asset')}</span></span>${hits
            .slice(0, 4)
            .map(
              ([w, t]) =>
                `<span class="sr-l"><span class="k">${searchSnippet(w, q, 200)}</span><span class="t">${searchSnippet(t, q)}</span></span>`
            )
            .join(
              ''
            )}${hits.length > 4 ? `<span class="faint sr-more">${T('and {n} more', { n: hits.length - 4 })}</span>` : ''}</button>`
      )
      .join('') +
    (res.length >= SEARCH_MAX
      ? `<p class="faint">${T('The first {n}: type more words.', { n: SEARCH_MAX })}</p>`
      : '')
  );
}
