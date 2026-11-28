/* ---------- Videos: where a render's video is played from ----------
   By its path under renders/ (lib/monitoring/snapshot.py snapshot_videos()): a folder chosen here first,
   then the copy that came with the page (meta.videos: its videos/ folder or zip), then the
   project's renders/ relative to the page; live, through Blender's server. */
let PICKED = null;
const VNAMES = () => {
  const s = new Set((M.videos || {}).files || []);
  return s;
};
/* The longest tail found: a folder above or below renders/ alike; a file's name alone only from a phone's pick. */
function pickedFile(name) {
  if (!PICKED || !name) return null;
  const parts = name.split('/');
  for (let k = 0; k < parts.length; k++)
    if (k < parts.length - 1 || PICKED[' flat']) {
      const f = PICKED[parts.slice(k).join('/')];
      if (f) return f;
    }
  return null;
}
function videoSrc(name) {
  if (!name) return null;
  const f = pickedFile(name);
  if (f) return f.url || (f.url = URL.createObjectURL(f));
  const V = M.videos || {},
    path = encodeURI(name);
  if (V.base && VNAMES().has(name)) return V.base + '/' + path;
  return V.local ? V.local + '/' + path : null;
}
const allVideoNames = () => [...new Set(items.flatMap(it => it.versions.map(v => v.video).filter(Boolean)))];
/* A folder's videos, each known by every tail of its path (a phone gives the videos themselves);
   a zip of them (Export snapshot's Zip: one file to bring to a phone) read for its videos, by their paths. */
function pickedFiles(files) {
  const zips = [...files].filter(f => /\.zip$/i.test(f.name));
  if (zips.length) {
    toast(T('Reading {zip}…', { zip: zips[0].name }));
    ZIP_PACKED = 0;
    Promise.all(zips.map(zipVideos))
      .then(lists => {
        const got = [...files].filter(f => /\.mp4$/i.test(f.name)).concat(...lists);
        // Zipped by hand (compressed): read only stored -- Export snapshot's own zip.
        if (!got.length && ZIP_PACKED)
          toast(
            T(
              "That zip's videos are compressed: export the snapshot with Videos: Zip, or choose the .mp4 files."
            )
          );
        else usePicked(got);
      })
      .catch(() => toast(T('That zip could not be read.')));
    return;
  }
  usePicked([...files]);
}
function usePicked(files) {
  let n = 0;
  PICKED = {};
  files.forEach(f => {
    if (!/\.mp4$/i.test(f.name)) return;
    n++;
    const parts = (f.zipPath || f.webkitRelativePath || f.name).split('/');
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
  const found = allVideoNames().filter(pickedFile).length;
  toast(
    T(
      '{n} video in that folder, {found} for this snapshot.|{n} videos in that folder, {found} for this snapshot.',
      { n, found }
    )
  );
  renderAll();
}
/* A zip's .mp4, each a slice of it (stored, never compressed: lib/preview.py zip_videos()), named by
   its path in it -- the zip not read whole, only its directory and each entry's header. Zip64 too
   (over 4 GB). Deflated entries left out: not one of ours. */
let ZIP_PACKED = 0;
function zipVideos(zip) {
  const rd = (a, b) =>
    zip
      .slice(a, b)
      .arrayBuffer()
      .then(x => new DataView(x));
  const big = (v, o) => v.getUint32(o, true) + v.getUint32(o + 4, true) * 2 ** 32;
  const tail = Math.min(zip.size, 65557);
  return rd(zip.size - tail, zip.size)
    .then(v => {
      let e = -1;
      for (let i = v.byteLength - 22; i >= 0; i--)
        if (v.getUint32(i, true) === 0x06054b50) {
          e = i;
          break;
        }
      if (e < 0) throw new Error('not a zip');
      const at = zip.size - tail + e,
        cdSize = v.getUint32(e + 12, true),
        cdOff = v.getUint32(e + 16, true);
      if (cdOff !== 0xffffffff && cdSize !== 0xffffffff) return [cdOff, cdSize];
      // Zip64: its end record, from the locator just before.
      return rd(at - 20, at).then(l => {
        if (l.getUint32(0, true) !== 0x07064b50) throw new Error('no zip64 locator');
        const r = big(l, 8);
        return rd(r, r + 56).then(z => [big(z, 48), big(z, 40)]);
      });
    })
    .then(([off, size]) => rd(off, off + size))
    .then(cd => {
      const ents = [];
      let i = 0;
      while (i + 46 <= cd.byteLength && cd.getUint32(i, true) === 0x02014b50) {
        const method = cd.getUint16(i + 10, true),
          nl = cd.getUint16(i + 28, true),
          xl = cd.getUint16(i + 30, true),
          cl = cd.getUint16(i + 32, true);
        let size = cd.getUint32(i + 20, true),
          usize = cd.getUint32(i + 24, true),
          loc = cd.getUint32(i + 42, true);
        const name = new TextDecoder().decode(new Uint8Array(cd.buffer, cd.byteOffset + i + 46, nl));
        // Zip64 extra field: the 64-bit values, in order, for those saturated.
        for (let x = i + 46 + nl; x + 4 <= i + 46 + nl + xl; ) {
          const id = cd.getUint16(x, true),
            len = cd.getUint16(x + 2, true);
          if (id === 1) {
            let y = x + 4;
            if (usize === 0xffffffff) ((usize = big(cd, y)), (y += 8));
            if (size === 0xffffffff) ((size = big(cd, y)), (y += 8));
            if (loc === 0xffffffff) loc = big(cd, y);
          }
          x += 4 + len;
        }
        if (/\.mp4$/i.test(name)) method === 0 ? ents.push({ name, size, loc }) : ZIP_PACKED++;
        i += 46 + nl + xl + cl;
      }
      return Promise.all(
        ents.map(en =>
          rd(en.loc, en.loc + 30).then(h => {
            const start = en.loc + 30 + h.getUint16(26, true) + h.getUint16(28, true);
            const f = zip.slice(start, start + en.size, 'video/mp4');
            f.name = en.name.split('/').pop();
            f.zipPath = en.name;
            return f;
          })
        )
      );
    });
}
/* Chrome, Edge: the folder opened, not read -- only the videos the page needs looked for, by their paths. */
function pickVideos() {
  // A phone: the files themselves -- the snapshot's zip, or its .mp4 -- from its file browser (an accept
  // of videos alone opens the gallery, which renames them); elsewhere, the folder.
  const phone = typeof isMob === 'function' && isMob();
  if (phone || !window.showDirectoryPicker) {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.multiple = true;
    if (!phone) inp.setAttribute('webkitdirectory', '');
    inp.accept = phone ? '.zip,.mp4,application/zip,application/x-zip-compressed' : 'video/mp4,.mp4';
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
