/* ---------- Videos: where a render's video is played from ----------
   By its path under renders/ (lib/monitoring/snapshot.py snapshot_videos()): a folder chosen here first,
   then the copy that came with the page (meta.videos: its videos/ folder or zip), then the
   project's renders/ relative to the page; live, through Blender's server. */
let PICKED = null;
const VNAMES = () => {
  const s = new Set((M.videos || {}).files || []);
  return s;
};
function videoSrc(name) {
  if (!name) return null;
  const parts = name.split('/');
  let f = null;
  // The longest tail found: a folder above or below renders/ alike; a file's name alone only from a phone's pick.
  if (PICKED)
    for (let k = 0; k < parts.length && !f; k++)
      if (k < parts.length - 1 || PICKED[' flat']) f = PICKED[parts.slice(k).join('/')];
  if (f) return f.url || (f.url = URL.createObjectURL(f));
  const V = M.videos || {},
    path = encodeURI(name);
  if (V.base && VNAMES().has(name)) return V.base + '/' + path;
  return V.local ? V.local + '/' + path : null;
}
const allVideoNames = () => [...new Set(items.flatMap(it => it.versions.map(v => v.video).filter(Boolean)))];
/* A folder's videos, each known by every tail of its path (a phone gives the videos themselves). */
function pickedFiles(files) {
  let n = 0;
  PICKED = {};
  [...files].forEach(f => {
    if (!/\.mp4$/i.test(f.name)) return;
    n++;
    const parts = (f.webkitRelativePath || f.name).split('/');
    if (parts.length < 2) PICKED[' flat'] = 1;
    for (let k = 0; k < parts.length; k++) {
      const key = parts.slice(k).join('/');
      if (!PICKED[key]) PICKED[key] = f;
    }
  });
  if (!n) {
    PICKED = null;
    toast(T('No .mp4 in that folder.'));
    return;
  }
  const found = allVideoNames().filter(v => (videoSrc(v) || '').startsWith('blob:')).length;
  toast(
    T(
      '{n} video in that folder, {found} for this snapshot.|{n} videos in that folder, {found} for this snapshot.',
      { n, found }
    )
  );
  renderAll();
}
/* Chrome, Edge: the folder opened, not read -- only the videos the page needs looked for, by their paths. */
function pickVideos() {
  if (!window.showDirectoryPicker) {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.multiple = true;
    inp.setAttribute('webkitdirectory', '');
    inp.accept = 'video/mp4,.mp4';
    inp.onchange = () => {
      if (inp.files && inp.files.length) pickedFiles(inp.files);
    };
    inp.click();
    return;
  }
  window
    .showDirectoryPicker({ id: 'mp-videos' })
    .then(dir => {
      const names = allVideoNames();
      if (!names.length) {
        toast(T('No render of this snapshot has a video.'));
        return;
      }
      toast(T('Looking for {n} video…|Looking for {n} videos…', { n: names.length }));
      const found = {};
      let n = 0,
        next = 0;
      const open = parts => {
        let h = Promise.resolve(dir);
        parts.slice(0, -1).forEach(p => {
          h = h.then(d => d.getDirectoryHandle(p));
        });
        return h.then(d => d.getFileHandle(parts[parts.length - 1])).then(f => f.getFile());
      };
      const look = name => {
        const parts = name.split('/'),
          tries = [parts, ['renders', ...parts]];
        for (let k = 1; k < parts.length - 1; k++) tries.push(parts.slice(k));
        let at = 0;
        const one = () => (at >= tries.length ? null : open(tries[at++]).catch(one));
        return Promise.resolve().then(one);
      };
      const work = () => {
        if (next >= names.length) return Promise.resolve();
        const name = names[next++];
        return look(name)
          .then(f => {
            if (f) {
              found[name] = f;
              n++;
            }
          })
          .then(work);
      };
      Promise.all(Array.from({ length: 8 }, work)).then(() => {
        if (!n) {
          toast(T("None of this snapshot's videos in {folder}.", { folder: dir.name }));
          return;
        }
        PICKED = found;
        toast(T('{found} of {n} videos found in {folder}.', { found: n, n: names.length, folder: dir.name }));
        renderAll();
      });
    })
    .catch(e => {
      if (e && e.name !== 'AbortError') toast(T('That folder could not be read.'));
    });
}
