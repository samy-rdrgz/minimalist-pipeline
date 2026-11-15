"""Prototype for plan 1.2, 4b.0: Blender serving a live page. Does the
dialogue work both ways, and does a video from the NAS play smoothly while
Blender is in use? Not part of the addon (tools/ is out of the package).

Run it in Blender: Text Editor > Open > this file > Run Script. The page
opens in the browser. Run it again to restart the server (the open page
reconnects by itself); set STOP_ONLY = True and run it to stop it.

What it changes: the frame, the selection, a text block "live_notes" in
the open file (unsaved), and the file opened if asked from the page.
Nothing else is written.

MEDIA_ROOT: the folder whose videos and images the page lists and plays --
the project's renders/ on the NAS, to test the real thing. Empty: the open
.blend's folder.
"""

import hmac
import json
import mimetypes
import os
import queue
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import bpy

MEDIA_ROOT = ""
STOP_ONLY = False
PORT = 8765  # fixed, so a page left open finds the server again (else any free port)
TICK = 0.25  # seconds between the main thread's turns
BUSY_AFTER = 1.5  # no turn for this long: the page says "Blender busy"
CHUNK = 64 * 1024  # a media file is sent by blocks of this size
MEDIA_EXT = {".mp4", ".webm", ".mov", ".mkv", ".png", ".jpg", ".jpeg"}
KEY = "mp_live_prototype"  # in bpy.app.driver_namespace: the running server
# The token stays the same from one run to the next, so the page left open
# can reconnect: a file in the temp folder, this machine's only.
TOKEN_FILE = Path(tempfile.gettempdir()) / "mp_live_prototype_token"


class Shared:
    """What the main thread and the server's threads share. The main thread
    writes (its turns, tick()); the server only reads the prepared state and
    queues actions. Never bpy outside the main thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.changed = threading.Condition(self.lock)
        self.state = {}
        self.version = 0
        self.last_tick = time.monotonic()
        self.gaps = []  # (when, seconds since the turn before): Blender's hiccups
        self.hiccup = 0.0  # the longest of them, over 10 s
        self.actions = queue.SimpleQueue()
        self.results = []
        self.media_root = None
        self.served = 0  # media bytes sent
        self.ranges = 0  # partial requests answered (a video's seeks)
        self.stopped = False
        self.next_id = 0


# --- the main thread: Blender's side ---------------------------------------


def _read_blender(sh) -> dict:
    scene = bpy.context.scene
    layer = bpy.context.view_layer
    active = layer.objects.active if layer else None
    return {
        "file": bpy.data.filepath or "(unsaved)",
        "dirty": bool(bpy.data.is_dirty),
        "scene": scene.name,
        "frame": scene.frame_current,
        "active": active.name if active else "",
        "objects": sorted(o.name for o in scene.objects)[:40],
        "media_root": str(sh.media_root or "(none: save the file, or set MEDIA_ROOT)"),
    }


def _redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def _with_window(op, **kwargs):
    """An operator from a timer: no window in its context, give it one."""
    windows = bpy.context.window_manager.windows
    if not windows:
        return op(**kwargs)
    with bpy.context.temp_override(window=windows[0]):
        return op(**kwargs)


def _external_player(path: str):
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 -- the file's own player
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


def _apply(sh, action: dict) -> dict:
    """One action from the page, on the main thread. Its result goes back to
    the page in the next state."""
    kind, rid = action.get("type"), action.get("id")
    done = {"id": rid, "ok": True, "at": time.strftime("%H:%M:%S")}
    try:
        scene = bpy.context.scene
        if kind == "frame":
            scene.frame_set(int(action["frame"]))
            done["text"] = f"frame {scene.frame_current}"
        elif kind == "select":
            ob = scene.objects.get(action.get("name", ""))
            if ob is None:
                raise ValueError(f"no object {action.get('name')!r}")
            for other in bpy.context.selected_objects:
                other.select_set(False)
            ob.select_set(True)
            bpy.context.view_layer.objects.active = ob
            done["text"] = f"selected {ob.name}"
        elif kind == "note":
            text = bpy.data.texts.get("live_notes") or bpy.data.texts.new("live_notes")
            text.write(f"{time.strftime('%H:%M:%S')}  {action.get('text', '')}\n")
            done["text"] = "note written in the text block live_notes"
        elif kind == "busy":
            # Python on the main thread, as a long scan would: the worst case
            # for the server's threads, which share Python's lock with it.
            seconds = min(float(action.get("seconds", 5)), 30)
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                sum(i * i for i in range(20000))
            done["text"] = f"busy {seconds:.0f} s, done"
        elif kind == "play":
            _external_player(action["path"])
            done["text"] = f"external player: {Path(action['path']).name}"
        elif kind == "open":
            return _open(sh, action, done)
        else:
            raise ValueError(f"unknown action {kind!r}")
        _redraw()
    except Exception as e:  # reported to the page, never raised in a timer
        done.update(ok=False, text=f"{kind}: {e}")
    return done


def _open(sh, action: dict, done: dict) -> dict:
    path = (action.get("path") or "").strip().strip('"')
    if not path.lower().endswith(".blend") or not Path(path).is_file():
        return done | {"ok": False, "text": f"open: no .blend at {path!r}"}
    choice = action.get("save")
    if bpy.data.is_dirty and choice not in ("save", "discard"):
        # The page asks, not Blender: its dialog would open where nobody looks.
        return done | {"ok": False, "need_choice": True, "path": path, "text": "unsaved changes"}
    if choice == "save":
        if not bpy.data.filepath:
            return done | {"ok": False, "text": "open: this file was never saved, save it in Blender"}
        _with_window(bpy.ops.wm.save_mainfile)

    def load():
        # Out of this turn: the load replaces every datablock; the server and
        # the persistent tick() go on.
        try:
            _with_window(bpy.ops.wm.open_mainfile, filepath=path)
            text, ok = f"opened {Path(path).name}", True
        except Exception as e:
            text, ok = f"open failed: {e}", False
        with sh.lock:
            sh.results = (sh.results + [{"id": action.get("id"), "ok": ok, "text": text, "at": time.strftime("%H:%M:%S")}])[-15:]
        return None

    bpy.app.timers.register(load, first_interval=0.05)
    return done | {"text": f"opening {Path(path).name}..."}


def make_tick(sh):
    def tick():
        if sh.stopped:
            return None
        start = time.monotonic()
        while True:
            try:
                action = sh.actions.get_nowait()
            except queue.Empty:
                break
            result = _apply(sh, action)
            with sh.lock:
                sh.results = (sh.results + [result])[-15:]
        root = Path(MEDIA_ROOT) if MEDIA_ROOT else (Path(bpy.data.filepath).parent if bpy.data.filepath else None)
        try:
            state = _read_blender(sh)
        except Exception as e:  # between two files, during a load
            state = {"error": str(e)}
        now = time.monotonic()
        with sh.lock:
            sh.media_root = root
            sh.gaps = [g for g in sh.gaps if now - g[0] < 10] + [(start, start - sh.last_tick)]
            sh.last_tick = now
            # Not in the state: it would change it at every turn.
            sh.hiccup = round(max(g for _, g in sh.gaps), 2)
            state["results"] = list(sh.results)
            if state != sh.state:
                sh.state = state
                sh.version += 1
                sh.changed.notify_all()
        return TICK

    return tick


# --- the server's threads ----------------------------------------------------


def _inside(root: Path, rel: str) -> Path | None:
    """rel under root, or None: never a path out of it."""
    if root is None:
        return None
    base = root.resolve()
    path = (base / rel).resolve()
    return path if path == base or base in path.parents else None


def make_handler(sh, token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _query(self) -> dict:
            return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

        def _allowed(self) -> bool:
            # The token: no other site open in the browser may call us. The
            # Host: no DNS rebinding (a site's name pointed at 127.0.0.1).
            port = self.server.server_address[1]
            if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                return False
            return hmac.compare_digest(self._query().get("t", ""), token)

        def _send(self, code: int, body: bytes, kind: str):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, code: int = 200):
            self._send(code, json.dumps(data).encode(), "application/json")

        def do_GET(self):
            if not self._allowed():
                return self._send(403, b"forbidden", "text/plain")
            route, q = urlparse(self.path).path, self._query()
            try:
                if route == "/":
                    self._send(200, PAGE.replace("{{TOKEN}}", token).encode(), "text/html; charset=utf-8")
                elif route == "/state":
                    self._state(int(q.get("since", -1)))
                elif route == "/list":
                    self._list()
                elif route == "/media":
                    self._media(q.get("path", ""))
                else:
                    self._send(404, b"not found", "text/plain")
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser let go (a video's seek): normal

        def _state(self, since: int):
            # Long poll: answered as soon as the state changes, else after
            # 2 s -- with "busy" if Blender has had no turn for a while.
            with sh.changed:
                sh.changed.wait_for(lambda: sh.version != since or sh.stopped, timeout=2.0)
                body = {"version": sh.version, "state": sh.state}
                body["busy"] = time.monotonic() - sh.last_tick > BUSY_AFTER
                body["served_mb"] = round(sh.served / 1e6, 1)
                body["ranges"] = sh.ranges
                body["hiccup"] = sh.hiccup
            self._json(body)

        def _list(self):
            root = sh.media_root
            files = []
            if root and root.is_dir():
                for folder, dirs, names in os.walk(root):
                    if len(Path(folder).relative_to(root).parts) >= 3:
                        dirs[:] = []
                    for name in names:
                        if Path(name).suffix.lower() in MEDIA_EXT:
                            files.append((Path(folder) / name).relative_to(root).as_posix())
                    if len(files) > 300:
                        break
            self._json({"root": str(root), "files": sorted(files)[:300]})

        def _media(self, rel: str):
            path = _inside(sh.media_root, rel)
            if path is None or not path.is_file():
                return self._send(404, b"not found", "text/plain")
            size = path.stat().st_size
            start, end = 0, size - 1
            ask = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
            if ask and (ask[1] or ask[2]):
                if ask[1]:
                    start = int(ask[1])
                    end = min(int(ask[2]), size - 1) if ask[2] else size - 1
                else:  # bytes=-N: the last N
                    start = max(size - int(ask[2]), 0)
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
            partial = bool(ask)
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                with sh.lock:
                    sh.ranges += 1
            self.end_headers()
            left = end - start + 1
            with open(path, "rb") as f:
                f.seek(start)
                while left > 0:
                    block = f.read(min(CHUNK, left))
                    if not block:
                        break
                    self.wfile.write(block)
                    left -= len(block)
                    with sh.lock:
                        sh.served += len(block)

        def do_POST(self):
            if not self._allowed():
                return self._send(403, b"forbidden", "text/plain")
            if urlparse(self.path).path != "/action":
                return self._send(404, b"not found", "text/plain")
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length < 65536 or "json" not in (self.headers.get("Content-Type") or ""):
                return self._send(400, b"bad request", "text/plain")
            action = json.loads(self.rfile.read(length))
            if action.get("type") == "play":
                path = _inside(sh.media_root, action.get("path", ""))
                if path is None:
                    return self._json({"error": "not in the media folder"}, 400)
                action["path"] = str(path)
            with sh.lock:
                sh.next_id += 1
                action["id"] = sh.next_id
            sh.actions.put(action)  # applied on Blender's next turn
            self._json({"queued": action["id"]})

    return Handler


# --- start / stop ------------------------------------------------------------


def stop() -> bool:
    running = bpy.app.driver_namespace.pop(KEY, None)
    if not running:
        return False
    sh = running["shared"]
    with sh.lock:
        sh.stopped = True
        sh.changed.notify_all()
    running["server"].shutdown()
    running["server"].server_close()
    if bpy.app.timers.is_registered(running["tick"]):
        bpy.app.timers.unregister(running["tick"])
    print("Live prototype: stopped.")
    return True


def _token() -> str:
    try:
        token = TOKEN_FILE.read_text().strip()
        if len(token) >= 20:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(token)
    return token


def start() -> str:
    restarted = stop()
    sh, token = Shared(), _token()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), make_handler(sh, token))
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(sh, token))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="mp-live-prototype", daemon=True).start()
    tick = make_tick(sh)
    # persistent: kept when a file is opened, the page's own "open" included.
    bpy.app.timers.register(tick, first_interval=0.0, persistent=True)
    bpy.app.driver_namespace[KEY] = {"shared": sh, "server": server, "tick": tick}
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={token}"
    print(f"Live prototype: {url}")
    if not restarted:
        webbrowser.open(url)
    return url


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Live prototype</title>
<style>
:root{--bg:#f6f6f4;--card:#fff;--ink:#1d1d1f;--ink2:#6b6b70;--line:#e2e2e0;--on:#2e9b58;--busy:#d98a1c;--off:#d0473d;--accent:#3d6fd9}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1d;--card:#252528;--ink:#ececee;--ink2:#9c9ca3;--line:#36363a}}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,sans-serif}
header{display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid var(--line)}
h1{font-size:16px;margin:0;flex:1}
.pill{padding:3px 10px;border-radius:99px;color:#fff;font-weight:600;font-size:13px;background:var(--off)}
.pill.on{background:var(--on)}.pill.busy{background:var(--busy)}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px;padding:12px 16px;max-width:1200px}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--ink2);margin:0 0 8px}
dl{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;margin:0}dt{color:var(--ink2)}dd{margin:0;word-break:break-all}
.row{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
input{font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);min-width:0;flex:1}
button{font:inherit;padding:5px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);cursor:pointer}
button:hover{border-color:var(--accent)}button:disabled{opacity:.4;cursor:default}
.chips button{padding:2px 8px;font-size:13px}.chips .active{border-color:var(--accent);color:var(--accent)}
#log{font:12px/1.5 ui-monospace,monospace;max-height:220px;overflow:auto}.bad{color:var(--off)}
#files{max-height:180px;overflow:auto;font-size:13px}#files div{cursor:pointer;padding:2px 4px;border-radius:4px}
#files div:hover,#files .sel{background:var(--bg)}
video,img{width:100%;max-height:340px;background:#000;border-radius:6px;margin-top:6px}
.dlg{border:1px solid var(--busy);border-radius:8px;padding:8px;margin-top:6px}
small{color:var(--ink2)}
</style></head><body>
<header><h1>Live prototype</h1><span id="pill" class="pill">Disconnected</span></header>
<main>
<section><h2>Blender, live</h2><dl id="info"></dl><small id="hic"></small></section>
<section><h2>Actions to Blender</h2>
<div class="row"><input id="frame" type="number" placeholder="Frame"><button data-act="frame">Set frame</button></div>
<div class="row chips" id="objects"></div>
<div class="row"><input id="note" placeholder="A note, written in the text block live_notes"><button data-act="note">Write</button></div>
<div class="row"><input id="blend" placeholder="Full path of a .blend to open"><button data-act="open">Open in Blender</button></div>
<div id="choice"></div>
<div class="row"><button data-act="busy">Keep Blender busy 5 s</button>
<small>Python on its main thread, like a long scan: the pill turns orange, a video playing must not stutter.</small></div>
</section>
<section><h2>Media from Blender</h2>
<div class="row"><button id="listb">List the media folder</button><button id="extb" disabled>External player</button></div>
<div id="files"></div><div id="viewer"></div>
<small id="mstats"></small></section>
<section><h2>Results</h2><div id="log"></div><small id="rt"></small></section>
</main>
<script>
var T='{{TOKEN}}',version=-1,status='',sent={},asked={},picked='',stalls=0,lastServed=0,lastAt=Date.now();
function $(id){return document.getElementById(id);}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function sleep(ms){return new Promise(function(r){setTimeout(r,ms);});}
function setStatus(s){if(s===status)return;status=s;var p=$('pill');p.className='pill '+s;
p.textContent=s==='on'?'Connected':s==='busy'?'Blender busy: actions wait':'Disconnected: retrying';
document.querySelectorAll('button[data-act],#objects button').forEach(function(b){b.disabled=s==='';});}
function act(a){a.sentAt=Date.now();
return fetch('/action?t='+T,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(a)})
.then(function(r){return r.json();}).then(function(r){if(r.queued)sent[r.queued]=a;else alert(r.error||'refused');})
.catch(function(){alert('Blender is not there');});}
function draw(s){
if(s.error){$('info').innerHTML='<dt>error</dt><dd>'+esc(s.error)+'</dd>';return;}
$('info').innerHTML=[['File',s.file+(s.dirty?'  (unsaved changes)':'')],['Scene',s.scene],['Frame',s.frame],['Active',s.active||'-'],
['Media folder',s.media_root]].map(function(r){return '<dt>'+r[0]+'</dt><dd>'+esc(r[1])+'</dd>';}).join('');
if(document.activeElement!==$('frame'))$('frame').value=s.frame;
$('objects').innerHTML=s.objects.map(function(n){return '<button class="'+(n===s.active?'active':'')+'" data-name="'+esc(n)+'">'+esc(n)+'</button>';}).join('');
$('log').innerHTML=s.results.slice().reverse().map(function(r){return '<div class="'+(r.ok?'':'bad')+'">'+esc(r.at)+'  '+esc(r.text)+'</div>';}).join('');
s.results.forEach(function(r){var a=sent[r.id];if(!a)return;
if(!a.done){a.done=1;$('rt').textContent='Last action: '+(Date.now()-a.sentAt)+' ms from the click to its result shown here.';}
if(r.need_choice&&!asked[r.id]){asked[r.id]=1;choose(r.path);}});}
function choose(path){$('choice').innerHTML='<div class="dlg">The file open in Blender has unsaved changes.<div class="row">'+
'<button data-save="save">Save, then open</button><button data-save="discard">Don\'t save</button><button data-save="">Cancel</button></div></div>';
$('choice').onclick=function(e){var c=e.target.dataset.save;if(c===undefined)return;$('choice').innerHTML='';if(c)act({type:'open',path:path,save:c});};}
document.addEventListener('click',function(e){var b=e.target.closest('button');if(!b||b.disabled)return;
if(b.dataset.name)return act({type:'select',name:b.dataset.name});
var k=b.dataset.act;if(k==='frame')act({type:'frame',frame:+$('frame').value});
if(k==='note'){act({type:'note',text:$('note').value});$('note').value='';}
if(k==='open')act({type:'open',path:$('blend').value});
if(k==='busy')act({type:'busy',seconds:5});});
$('listb').onclick=function(){fetch('/list?t='+T).then(function(r){return r.json();}).then(function(d){
$('files').innerHTML=d.files.length?d.files.map(function(f){return '<div data-f="'+esc(f)+'">'+esc(f)+'</div>';}).join(''):'<small>No video or image in '+esc(d.root)+'</small>';});};
$('files').onclick=function(e){var f=e.target.dataset.f;if(!f)return;picked=f;$('extb').disabled=false;
document.querySelectorAll('#files div').forEach(function(d){d.classList.toggle('sel',d.dataset.f===f);});
var src='/media?t='+T+'&path='+encodeURIComponent(f);
$('viewer').innerHTML=/\.(png|jpe?g)$/i.test(f)?'<img src="'+src+'">':'<video controls autoplay preload="metadata" src="'+src+'"></video>';
var v=$('viewer').querySelector('video');if(v)v.addEventListener('waiting',function(){stalls++;});};
$('extb').onclick=function(){if(picked)act({type:'play',path:picked});};
function stats(r){var now=Date.now(),mbs=(r.served_mb-lastServed)/((now-lastAt)/1000);lastServed=r.served_mb;lastAt=now;
$('hic').textContent='Longest gap between two turns of Blender, last 10 s: '+r.hiccup+' s (0.25 when idle).';
$('mstats').textContent='Served '+r.served_mb+' MB ('+Math.max(mbs,0).toFixed(1)+' MB/s now), '+r.ranges+' partial requests (seeks), '+stalls+' stalls of the video.';}
(async function loop(){for(;;){try{var r=await fetch('/state?t='+T+'&since='+version,{cache:'no-store'});
if(!r.ok)throw r.status;var d=await r.json();setStatus(d.busy?'busy':'on');
if(d.version!==version){version=d.version;draw(d.state);}stats(d);}
catch(e){setStatus('');version=-1;await sleep(2000);}}})();
</script></body></html>"""


if STOP_ONLY:
    stop()
else:
    start()
