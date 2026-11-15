"""The live page (plan 2.8, phase 4b): Blender serves the snapshot page to
this machine's browser, kept up to date; what's done on it (validate, a
retake, a reply...) sent back as the review's typed actions, applied at
once as an imported review would be. See NOTES.md, "Live page".

- A server (ThreadingHTTPServer) on 127.0.0.1 only, its token in every
  URL, the Host checked: no other site open in the browser can call it.
- Its state in this module, not bpy.app.driver_namespace -- emptied when
  a file is opened, which left the prototype's server orphaned on its port.
- A reader thread goes over the project while a page is open (two stats a
  folder, a folder changed read again); the main thread's timer builds the
  page's data from it (build_snapshot() reads ConfigCache) and bumps the
  version when it changed. The server's threads only hand out what's ready.
- Videos served from renders/ with Range (to seek), never a path out of it.
- Actions: POSTed, queued, applied on Blender's turn by import_review()
  (idempotent: one sent twice changes nothing), then a pass over the
  project; answered once the data showing them is ready, with its version.
"""

import base64
import hmac
import json
import mimetypes
import os
import queue
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import bpy

from .core import get_addon_version, now
from .logs import log
from .preview import browser_video, render_department, render_root
from .snapshot import _folder_frames, _owner_shots, _video_name, build_snapshot, read_render_state
from .snapshot_page import page_data, render_page
from .status import project_stages
from .thumbnails import owner_shot_render_dirs, owner_thumbnail_dirs, thumbnail_path
from .tracking import (
    _DATA_ROOTS,
    _collect_folder,
    _current_link_files,
    _outdated_links_of,
    _path_key,
    _pipeline_entries,
    _walk_owner_dirs,
    to_check_entries,
)

VERSIONS_SHOWN = 15  # a shot's render versions offered to watch, newest first

PORTS = range(8765, 8776)  # fixed: a page left open finds its server again
TICK = 0.1  # the main thread's turn
READ_EVERY = 4.0  # seconds between two passes over the project...
IDLE_AFTER = 30.0  # ...while a page asked for something this recently
BUSY_AFTER = 1.5  # no turn for this long: the page says "Blender busy"
POLL = 20.0  # a page waiting for news is answered after this, news or not
CHUNK = 64 * 1024


class _Shared:
    """What the main thread prepares and the server's threads hand out."""

    def __init__(self, root: Path, token: str):
        self.root = root
        self.token = token
        self.lock = threading.Lock()
        self.changed = threading.Condition(self.lock)
        self.version = 0
        self.data = None  # page_data(), as the page loads it
        self.body = b""  # the same, encoded: /data
        self.last_tick = time.monotonic()
        self.last_seen = time.monotonic()  # a page's last request
        self.stopped = False


class _Pending:
    """A page's actions, from the server's thread to Blender's turn and back."""

    def __init__(self, review: dict, kind: str = "review"):
        self.review = review
        self.kind = kind  # "review" (answered after a pass) or "open" (at once)
        self.done = threading.Event()
        self.result: dict = {}


_actions: queue.SimpleQueue = queue.SimpleQueue()
_shared: _Shared | None = None
_server = None
_reader = {"thread": None, "result": None, "at": 0.0, "farm_at": 0.0, "cache": {}, "farm": None, "compare": None, "ready": False,
           "waiting": [], "in_pass": []}


def running() -> bool:
    return _server is not None


def url() -> str:
    if not _server:
        return ""
    return f"http://127.0.0.1:{_server.server_address[1]}/?t={_shared.token}"


# --- the reader thread ---------------------------------------------------------


def _b64(path: Path) -> str | None:
    try:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None


def read_live(root: Path, cache: dict, config: dict, v_prefix: str) -> tuple[dict, bool]:
    """Every tracked folder as read_snapshot_data() gives it, a folder read
    again only when its .pipeline/, its tracking.json or its own listing
    (a .blend saved) changed since cache. Returns (cache, changed). Pure
    os/json: thread-safe."""
    out, changed = {}, False
    for top in _DATA_ROOTS:
        kind = "shot" if top == "shots" else "asset"
        mtimes: dict = {}
        for owner in _walk_owner_dirs(root / top, mtimes=mtimes):
            key = str(owner)
            try:
                stamp = (os.stat(owner / ".pipeline").st_mtime, mtimes.get(key), os.stat(owner).st_mtime)
            except OSError:
                continue
            old = cache.get(key)
            if old and old["stamp"] == stamp:
                out[key] = old
                continue
            entries = _pipeline_entries(owner)
            raw = _collect_folder(owner, entries)
            if raw is None:
                continue
            try:
                blends = [e.name for e in os.scandir(owner) if e.name.endswith(".blend")]
            except OSError:
                blends = []
            renders, thumb, shot_thumbs, versions, checks = None, None, [], {}, []
            if not raw["tracking"].get("archived"):
                versions = _versions(root, kind, owner, v_prefix)
                checks = _checks(root, raw["tracking"])
                renders = read_render_state(root, kind, owner, v_prefix, project_stages(config, f"{kind}s"))
                for r in renders:
                    for x in (r, *(r.get("others") or [])):
                        x["video"] = _video_name(root, browser_video(Path(x["path"])) if x.get("path") else None)
                thumb = next((b for d in owner_thumbnail_dirs(root, owner) if (b := _b64(thumbnail_path(d)))), None)
                found = [(label, _b64(thumbnail_path(d))) for label, d in owner_shot_render_dirs(root, owner)]
                shot_thumbs = found if any(b for _, b in found) else []
            out[key] = {
                "stamp": stamp, "kind": kind, "owner": owner, "raw": raw, "blends": blends,
                "renders": renders, "thumb": thumb, "shot_thumbs": shot_thumbs,
                "versions": versions, "checks": checks, "links": _current_link_files(entries, root),
            }
            changed = True
    return out, changed or set(out) != set(cache)


def _versions(root: Path, kind: str, owner: Path, v_prefix: str) -> dict:
    """{line: [{"folder", "department", "video", "first", "at"}]}: each
    render folder with a video a browser plays, newest first -- line ""
    the folder's own renders (a shot, a block rendered whole, an asset),
    a shot's name for a block's shots rendered apart. What the page offers
    to watch besides the main render. Thread-safe."""
    base = render_root(root, owner)
    dirs = [("", base)]
    shots = _owner_shots(owner) if kind == "shot" else []
    if len(shots) > 1:
        dirs += [(s, base.with_name(s)) for s in shots]
    out = {}
    for line, folder in dirs:
        try:
            found = sorted(
                (e for e in os.scandir(folder) if e.is_dir() and e.name.startswith(v_prefix)),
                key=lambda e: e.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            continue
        rows = []
        for e in found:
            video = _video_name(root, browser_video(Path(e.path)))
            if not video:
                continue
            rows.append({
                "folder": e.name,
                "department": render_department(Path(e.path)),
                "video": video,
                "first": (_folder_frames(Path(e.path)) or [None])[0],
                "at": e.stat().st_mtime,
            })
            if len(rows) >= VERSIONS_SHOWN:
                break
        if rows:
            out[line] = rows
    return out


def _checks(root: Path, tracking: dict) -> list:
    """Its renders to check: [{"key", "shot", "department", "folder",
    "video"}] -- Checked takes one off by its key."""
    out = []
    for key, info in to_check_entries(tracking):
        render = Path(info.get("render") or "")
        folder = render if render.is_absolute() else Path(root) / render
        out.append({
            "key": key,
            "shot": info.get("shot") or "",
            "department": info.get("department") or "",
            "folder": folder.name,
            "video": _video_name(root, browser_video(folder)) if folder.name else None,
        })
    return out


def _live_extras(root: Path, cache: dict, outdated: dict) -> dict:
    """Per folder, what only the live page shows: {"key" (its path under
    the project), "links": [{"key", "file", "newer"}], "linked_by": [keys],
    "versions", "checks"}."""
    rel = {}
    for key in cache:
        try:
            rel[_path_key(Path(key))] = Path(key).relative_to(root).as_posix()
        except ValueError:
            pass
    by_target: dict[str, list[str]] = {}
    out = {}
    for key, e in cache.items():
        me = rel.get(_path_key(Path(key)))
        newer = dict(outdated.get(key) or [])
        links = []
        for f in e.get("links") or []:
            path = Path(f) if Path(f).is_absolute() else Path(root) / f
            target = rel.get(_path_key(path.parent), "")
            links.append({"key": target, "file": path.name, "newer": newer.get(path.name, "")})
            if target and me:
                by_target.setdefault(target, []).append(me)
        out[key] = {"key": me, "links": links, "versions": e.get("versions") or {}, "checks": e.get("checks") or []}
    for key, extra in out.items():
        extra["linked_by"] = sorted(set(by_target.get(extra["key"], [])))
    return out


def _as_data(cache: dict, extras: dict | None = None) -> dict:
    """read_live()'s cache as read_snapshot_data()'s result."""
    entries = list(cache.values())
    return {
        "live": extras or {},
        "raws": [(e["kind"], e["owner"], e["raw"], e["blends"]) for e in entries],
        "renders": {str(e["owner"]): e["renders"] for e in entries if e["renders"] is not None},
        "thumbs": {str(e["owner"]): e["thumb"] for e in entries if e["thumb"]},
        "shot_thumbs": {str(e["owner"]): e["shot_thumbs"] for e in entries if e["shot_thumbs"]},
        "thumb_warnings": [],
    }


def _read(root, cache, config, v_prefix, extras):
    try:
        new, changed = read_live(root, cache, config, v_prefix)
        if changed or extras is None:
            # Links to a newer stable: one listing per folder linked.
            currents = {k: e.get("links") or [] for k, e in new.items()}
            extras = _live_extras(root, new, _outdated_links_of(root, [Path(k) for k in new], currents, v_prefix))
        _reader["result"] = (new, changed, extras)
    except Exception as e:  # never die silently: the next pass tries again
        log("WARNING", "live", f"Live page: project not read: {e!r}")
        _reader["result"] = (cache, False, extras)


# --- the main thread -------------------------------------------------------------


def _tick():
    """Blender's turn: a pass started while a page is open, its result
    turned into the page's data, the version bumped when it changed."""
    sh = _shared
    if sh is None or sh.stopped:
        return None
    try:
        _turn(sh)
    except Exception as e:
        log("WARNING", "live", f"Live page: {e!r}")
    with sh.lock:
        sh.last_tick = time.monotonic()
    return TICK


def _turn(sh: _Shared) -> None:
    from .config import ConfigCache, get_active_project_root

    root = get_active_project_root()
    if root and Path(root) != sh.root:
        # Another project made active: the page follows it.
        sh.root = Path(root)
        _reader.update(cache={}, result=None, compare=None, ready=False, extras=None)
    clock = time.monotonic()
    # The page's actions, applied now; answered after the next pass.
    while True:
        try:
            pending = _actions.get_nowait()
        except queue.Empty:
            break
        if pending.kind == "open":
            pending.result = _open(pending.review)
            pending.done.set()
            continue
        pending.result = _apply(sh.root, pending.review)
        _reader["waiting"].append(pending)
    thread = _reader["thread"]
    if _reader["result"] is not None and not (thread and thread.is_alive()):
        cache, changed, _reader["extras"] = _reader["result"]
        _reader["result"] = None
        _reader["cache"] = cache
        _reader["ready"] = True
        _rebuild(sh, force=changed)
        for pending in _reader["in_pass"]:
            pending.result["version"] = sh.version
            pending.done.set()
        _reader["in_pass"] = []
    elif clock - _reader["farm_at"] > 1.0:
        _reader["farm_at"] = clock
        _rebuild(sh, force=False)  # the farm moves on its own
    if (thread is None or not thread.is_alive()) and _reader["result"] is None and (
        clock - _reader["at"] >= READ_EVERY and clock - sh.last_seen < IDLE_AFTER
        or sh.data is None
        or _reader["waiting"]
    ):
        _reader["in_pass"] += _reader["waiting"]
        _reader["waiting"] = []
        config = ConfigCache.get() or {}
        _reader["at"] = clock
        _reader["thread"] = threading.Thread(
            target=_read,
            args=(
                sh.root,
                dict(_reader["cache"]),
                config,
                (config.get("naming") or {}).get("version", {}).get("prefix", "v"),
                _reader.get("extras"),
            ),
            daemon=True,
            name="pipeline-live-read",
        )
        _reader["thread"].start()


def _with_window(op, *args, **kwargs):
    """An operator from a timer: no window in its context, give it one."""
    windows = bpy.context.window_manager.windows
    if not windows:
        return op(*args, **kwargs)
    with bpy.context.temp_override(window=windows[0]):
        return op(*args, **kwargs)


def _apply(root: Path, raw: dict) -> dict:
    """A page's actions, written into the project as an imported review's
    (lib/review_import.py: the same checks, the same idempotence), its
    descriptions and new files too. {"ok", "imported", "validated",
    "fixed", "replies", "changed", "skipped": [[label, reason]]} or
    {"ok": False, "error"}."""
    from .errors import PipelineError
    from .monitoring import status_changed
    from .review_import import _action, _review_file, create_rows, import_review, parse_review_date
    from .snapshot import SCHEMA_VERSION
    from .tracking import ProjectScan, set_description

    raw_actions = [a for a in raw.get("actions") or [] if isinstance(a, dict)]
    checked = _checked([a for a in raw_actions if a.get("type") == "checked"])
    actions = [a for a in map(_action, raw_actions) if a]
    review = {
        "schema_version": SCHEMA_VERSION,
        "author": str(raw.get("author") or "").strip(),
        "role": str(raw.get("role") or "").strip().lower(),
        "review_date": parse_review_date(str(raw.get("review_date") or "")),
        "actions": actions,
    }
    try:
        out = import_review(Path("live page"), review)
    except PipelineError as e:
        if actions:
            log(e.level, "live", f"Live page: not applied: {e.message}")
            return {"ok": False, "error": e.message}
        # Only renders checked: no review to read.
        out = {"imported": 0, "validated": 0, "fixed": 0, "replies": 0, "changed": 0, "skipped": []}
    out["changed"] += checked["changed"]
    out["skipped"] += checked["skipped"]
    for a in actions:
        if a["type"] == "description" and a.get("new") and a["new"] != a["old"]:
            filepath = _review_file(a["file"])
            if filepath:
                try:
                    set_description(filepath, a["new"])
                    status_changed(filepath)
                    out["changed"] += 1
                except PipelineError as e:
                    out["skipped"].append((a["file"], e.message))
    for kind, rows in create_rows(review).items():
        if rows:
            _with_window(bpy.ops.m_pipeline.batch_create, "EXEC_DEFAULT", kind=kind, rows_json=json.dumps(rows))
    ProjectScan.start(root)
    log(
        "INFO",
        "live",
        f"Live page, {review['author'] or '?'} ({review['role'] or 'team'}): {out['imported']} note(s), "
        f"{out['validated']} validation(s), {out['fixed']} fixed, {out['replies']} reply(ies), "
        f"{out['changed']} change(s), {len(out['skipped'])} skipped",
    )
    return {"ok": True, **{k: out[k] for k in ("imported", "validated", "fixed", "replies", "changed")},
            "skipped": [list(s) for s in out["skipped"]]}


def _checked(actions: list) -> dict:
    """Renders marked checked from the page ({"file", "key", "push"}): out
    of "to check", their farm job archived, pushed to the edit if asked --
    as Render checked does (its departments: the page's ✓ / ✕)."""
    from ..operators.rushes_ops import push_checked_renders
    from ..operators.tracking_ops import _archive_checked_job
    from .errors import PipelineError
    from .monitoring import status_changed
    from .review_import import _review_file
    from .tracking import clear_render_to_check

    out = {"changed": 0, "skipped": []}
    for a in actions:
        filepath = _review_file(str(a.get("file") or ""))
        if not filepath or not isinstance(a.get("key"), str):  # "": a render of before 1.2
            out["skipped"].append((str(a.get("file")), "render checked: file not found"))
            continue
        try:
            dropped = clear_render_to_check(filepath, str(a["key"]))
        except PipelineError as e:
            out["skipped"].append((str(a.get("file")), e.message))
            continue
        status_changed(filepath)
        for info in dropped:
            if info.get("job_id"):
                _archive_checked_job(info["job_id"])
        if dropped and a.get("push"):
            _with_window(push_checked_renders, bpy.context, dropped)
        out["changed"] += len(dropped)
    return out


def _open(raw: dict) -> dict:
    """Open a file of the project in this Blender, as the page asks: its
    question when the file open has unsaved changes ({"ask": True}), then
    saved first or not ("save": "save" / "discard"). Opened on a timer of
    its own: the load replaces every datablock, this turn ends first."""
    from .review_import import _review_file

    filepath = _review_file(str(raw.get("file") or ""))
    if not filepath or not filepath.is_file():
        return {"ok": False, "error": "file not found"}
    choice = raw.get("save")
    if bpy.data.is_dirty and choice not in ("save", "discard"):
        return {"ok": False, "ask": True, "current": Path(bpy.data.filepath).name or "an unsaved file"}
    if choice == "save":
        if not bpy.data.filepath:
            return {"ok": False, "error": "the file open in Blender was never saved: save it there"}
        _with_window(bpy.ops.wm.save_mainfile)

    def load():
        try:
            _with_window(bpy.ops.wm.open_mainfile, filepath=str(filepath))
            log("INFO", "live", f"Live page: opened {filepath.name}")
        except Exception as e:
            log("WARNING", "live", f"Live page: {filepath.name} not opened: {e}")
        return None

    bpy.app.timers.register(load, first_interval=0.05)
    return {"ok": True, "opened": filepath.name}


FINISHED_SHOWN = 20  # the farm's finished jobs listed, newest first


def _farm_data(root: Path) -> dict:
    """The Farm tab's: {"status", "jobs": [{"id", "file", "key" (its
    folder under the project: the page's link to it), "shot", "state",
    "text", "done", "total", "left", "machines", "user", "at"}], "workers":
    [{"name", "status", "file"}]}, from the monitor cache. Memory only."""
    from ..farm.loop import _STAGE_WORDS, entry_state
    from ..farm.monitor import get_monitor_cache

    cache = get_monitor_cache()
    jobs, finished = [], []
    for j in cache.get("jobs") or []:
        stage = j.get("stage") or ""
        path = Path(j.get("filepath") or "")
        if path.is_absolute():
            try:
                path = path.relative_to(root)
            except ValueError:
                pass
        state = entry_state(j)
        row = {
            "id": j.get("job_id") or "",
            "file": path.stem if path.suffix == ".blend" else str(path),
            "key": path.parent.as_posix() if path.suffix == ".blend" else "",
            "shot": j.get("shot_override") or "",
            "state": state,
            "text": "waiting for a worker" if j.get("no_machine") else _STAGE_WORDS.get(stage, stage.replace("_", " ")),
            "done": j.get("frames_done") or 0,
            "total": j.get("frames_total") or 0,
            "left": j.get("time_left"),
            "machines": len(j.get("machines") or []),
            "user": j.get("user") or "",
            "at": j.get("submitted_at") or "",
        }
        (finished if state == "finished" else jobs).append(row)
    finished.sort(key=lambda r: r["at"], reverse=True)
    workers = [
        {
            "name": f"{w.get('user')} ({w.get('machine') or uuid[:8]})" if w.get("user") else w.get("machine") or uuid[:8],
            "status": w.get("status") or "",
            "file": Path(w.get("current_file") or "").stem,
        }
        for uuid, w in sorted((cache.get("workers") or {}).items(), key=lambda kv: str(kv[1].get("user") or ""))
        if isinstance(w, dict)
    ]
    return {"status": cache.get("status") or "unknown", "jobs": jobs + finished[:FINISHED_SHOWN], "workers": workers}


def _rebuild(sh: _Shared, force: bool) -> None:
    """The page's data from the last pass and the farm's jobs (memory
    only): a new version when it differs."""
    from ..farm.loop import farm_activity
    from .config import ConfigCache
    from .session import get_user, get_user_role

    if not _reader["ready"]:
        return  # nothing read yet: no empty page
    farm = farm_activity()
    jobs = _farm_data(sh.root)
    if not force and (farm, jobs) == _reader["farm"]:
        return
    _reader["farm"] = (farm, jobs)
    config = ConfigCache.get() or {}
    meta = {
        "project": config.get("project_name") or sh.root.name,
        "scan_started_at": now(),
        "exported_by": get_user(bpy.context),
        "addon_version": get_addon_version(),
        # Who writes from the page: Blender's user and role (Preferences).
        "live": {"token": sh.token, "user": get_user(bpy.context), "role": get_user_role(bpy.context) or "team"},
        # Played from the project, through the server.
        "videos": {"mode": "live", "base": None, "files": [], "local": f"media/{sh.token}/renders"},
    }
    data = page_data(build_snapshot(_as_data(_reader["cache"], _reader.get("extras")), config, meta, farm=farm))
    # Its Farm tab: the farm as Farm monitoring shows it.
    data["farm"] = jobs
    # Compared without its date: a pass finding nothing new is no news.
    compare = json.dumps({**data, "meta": {**data["meta"], "snapshot": ""}}, ensure_ascii=False, separators=(",", ":"))
    if compare == _reader["compare"]:
        return
    _reader["compare"] = compare
    with sh.changed:
        sh.version += 1
        data["meta"]["live"]["version"] = sh.version
        sh.data = data
        sh.body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        sh.changed.notify_all()


# --- the server's threads -------------------------------------------------------------


def _handler(sh: _Shared):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _allowed(self, token: str) -> bool:
            # The token: no other site may call us. The Host: no DNS
            # rebinding (a site's name pointed at 127.0.0.1).
            port = self.server.server_address[1]
            if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                return False
            return hmac.compare_digest(token or "", sh.token)

        def _send(self, code: int, body: bytes, kind: str):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            media = re.match(r"/media/([^/]+)/(.+)$", parsed.path)
            if not self._allowed(media[1] if media else q.get("t", "")):
                return self._send(403, b"forbidden", "text/plain")
            with sh.lock:
                sh.last_seen = time.monotonic()
            try:
                if parsed.path == "/":
                    self._page()
                elif parsed.path == "/data":
                    self._data(int(q.get("since", -1)))
                elif media:
                    self._media(unquote(media[2]))
                else:
                    self._send(404, b"not found", "text/plain")
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser let go (a seek, another video): normal

        def do_POST(self):
            parsed = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            if not self._allowed(q.get("t", "")):
                return self._send(403, b"forbidden", "text/plain")
            if parsed.path not in ("/action", "/open"):
                return self._send(404, b"not found", "text/plain")
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length < 4 * 1024 * 1024 or "json" not in (self.headers.get("Content-Type") or ""):
                return self._send(400, b"bad request", "text/plain")
            try:
                raw = json.loads(self.rfile.read(length))
            except ValueError:
                return self._send(400, b"bad request", "text/plain")
            with sh.lock:
                sh.last_seen = time.monotonic()
            pending = _Pending(raw if isinstance(raw, dict) else {}, "open" if parsed.path == "/open" else "review")
            _actions.put(pending)
            # Blender's turn, then a pass over the project: the data that
            # shows them. Blender busy longer: the page sends them again
            # (applying twice changes nothing).
            if not pending.done.wait(60):
                return self._send(504, json.dumps({"ok": False, "error": "Blender didn't answer"}).encode(), "application/json")
            self._send(200, json.dumps(pending.result).encode(), "application/json")

        def _page(self):
            with sh.changed:
                sh.changed.wait_for(lambda: sh.data is not None or sh.stopped, timeout=30)
                data = sh.data
            if data is None:
                return self._send(503, b"The project is still being read: reload in a moment.", "text/plain")
            self._send(200, render_page(data).encode("utf-8"), "text/html; charset=utf-8")

        def _data(self, since: int):
            # Long poll: answered as soon as there's a new version, else
            # after POLL -- with "busy" if Blender has had no turn for a while.
            with sh.changed:
                sh.changed.wait_for(lambda: sh.version != since or sh.stopped, timeout=POLL)
                busy = time.monotonic() - sh.last_tick > BUSY_AFTER
                head = {"version": sh.version, "busy": busy}
                body = sh.body if sh.version != since else b""
            out = json.dumps(head).encode()
            if body:
                out = out[:-1] + b',"data":' + body + b"}"
            self._send(200, out, "application/json")

        def _media(self, rel: str):
            base = (sh.root / "renders").resolve()
            path = (sh.root / rel).resolve()
            if base not in path.parents or not path.is_file():
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
            self.send_response(206 if ask else 200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if ask:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
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

    return Handler


# --- start / stop -------------------------------------------------------------------------


def _token() -> str:
    """Kept from one Blender session to the next: a page left open
    reconnects. In Blender's config folder, this machine's only."""
    folder = Path(bpy.utils.user_resource("CONFIG", create=True))
    path = folder / "minimalist_pipeline_live_token"
    try:
        token = path.read_text().strip()
        if len(token) >= 20:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(24)
    try:
        path.write_text(token)
    except OSError:
        pass
    return token


def start(root: Path) -> str:
    """The server for root, started if it isn't (another project: switched).
    Returns its URL. Raises OSError when no port is free."""
    global _shared, _server
    if _server is not None:
        return url()
    sh = _Shared(Path(root), _token())
    server = None
    for port in PORTS:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), _handler(sh))
            break
        except OSError:
            continue
    if server is None:
        raise OSError(f"no free port among {PORTS.start}-{PORTS.stop - 1}")
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="pipeline-live", daemon=True).start()
    _shared, _server = sh, server
    _reader.update(thread=None, result=None, at=0.0, farm_at=0.0, cache={}, farm=None, compare=None, ready=False,
                   waiting=[], in_pass=[], extras=None)
    # persistent: kept when a file is opened.
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.0, persistent=True)
    log("INFO", "live", f"Live page served at {url()}")
    return url()


def stop() -> bool:
    """Stop the server (the addon's unregister() too). False: none ran."""
    global _shared, _server
    if _server is None:
        return False
    with _shared.changed:
        _shared.stopped = True
        _shared.changed.notify_all()
    _server.shutdown()
    _server.server_close()
    _shared, _server = None, None
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    log("INFO", "live", "Live page stopped")
    return True
