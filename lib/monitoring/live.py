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
import html
import json
import mimetypes
import os
import queue
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import bpy

from ..core import get_addon_version, now
from ..logs import log
from ..preview import browser_video, render_department, render_root
from .snapshot import _folder_frames, _owner_shots, _rushes_by_name, _video_name, build_snapshot, folder_links, read_render_state
from .snapshot_page import page_data, render_page
from .status import project_stages
from . import progress_log
from ..thumbnails import owner_shot_render_dirs, owner_thumbnail_dirs, thumbnail_path
from .tracking import (
    _DATA_ROOTS,
    _collect_folder,
    _current_link_files,
    _outdated_links_of,
    _pipeline_entries,
    _walk_owner_dirs,
    to_check_entries,
    work_times,
)

VERSIONS_SHOWN = 15  # a shot's render versions offered to watch, newest first

PORTS = range(8765, 8776)  # fixed: a page left open finds its server again
TICK = 0.1  # the main thread's turn
READ_EVERY = 4.0  # seconds between two passes over the project...
IDLE_AFTER = 30.0  # ...while a page asked for something this recently
BUSY_AFTER = 1.5  # no turn for this long: the page says "Blender busy"
POLL = 20.0  # a page waiting for news is answered after this, news or not
FIRST_BATCH = 1.0  # the first read: a page of what's read after this long (a small project: none)...
BATCH_EVERY = 2.0  # ...then again this often, until it's whole
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
        self.thumbs = {}  # its thumbnails' bytes, by hash: /thumb/<token>/<hash>
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

# --- a phone: guests ------------------------------------------------------------
# An access for someone on the studio's network (a phone, a tablet): their
# token, name, role, until when -- the page served on this machine's
# network address too, only while one is valid. See NOTES.md, "Live page:
# a phone".
GUEST_MAX_HOURS = 7 * 24
_guests: dict[str, dict] = {}  # token: {"name", "role", "until" (epoch), "made", "ip", "farm"}
_guests_lock = threading.Lock()
_lan = {"servers": {}, "error": ""}  # {ip: server}: one per address a guest uses
_config_dir: Path | None = None  # Blender's config folder, read on the main thread


def _guests_file() -> Path | None:
    return _config_dir / "minimalist_pipeline_live_guests.json" if _config_dir else None


def _load_guests() -> None:
    path = _guests_file()
    try:
        raw = json.loads(path.read_text()) if path and path.is_file() else {}
    except (OSError, ValueError):
        raw = {}
    with _guests_lock:
        _guests.clear()
        _guests.update({t: g for t, g in raw.items() if isinstance(g, dict) and _until(g) > time.time()})


def _until(guest: dict) -> float:
    """A guest's end (epoch); 0 when the file says nothing readable."""
    try:
        return float(guest.get("until") or 0)
    except (TypeError, ValueError):
        return 0.0


def _save_guests() -> None:
    path = _guests_file()
    if not path:
        return
    with _guests_lock:
        raw = {t: g for t, g in _guests.items() if g["until"] > time.time()}
    try:
        path.write_text(json.dumps(raw))
    except OSError as e:
        log("WARNING", "live", f"Live page: guests not saved: {e}")


def guest_of(token: str) -> dict | None:
    """The guest this token is, still valid; None otherwise."""
    with _guests_lock:
        for t, g in _guests.items():
            if hmac.compare_digest(token or "", t):
                return g if g["until"] > time.time() else None
    return None


def _guest_list() -> list:
    with _guests_lock:
        return sorted(
            ({"token": t, "name": g["name"], "role": g["role"], "until": _iso(g["until"]), "ip": g.get("ip", ""), "farm": bool(g.get("farm"))} for t, g in _guests.items() if g["until"] > time.time()),
            key=lambda g: g["until"],
        )


# The ranges a studio's network uses, and mesh VPNs' (Tailscale's and
# others'): the machine's address in each is the one a datagram to that
# range would leave from. No packet is sent -- a UDP socket only picks its route.
_VPN = "100.64.0.0/10"
_RANGES = ("192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12", _VPN)


def _routed_from(range_: str) -> str | None:
    """This machine's address toward range_ (its last host), if it has a route there."""
    import ipaddress

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((str(ipaddress.ip_network(range_)[-2]), 1))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def _host_addresses() -> list[str]:
    """The addresses this machine's name has (every network it is on, on Windows and macOS)."""
    try:
        return [i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        return []


def _addresses() -> list[dict]:
    """This machine's addresses a phone may reach: [{"ip", "kind"}] --
    "local network" (the studio's Wi-Fi), "VPN" (100.64.0.0/10, Tailscale's and other mesh VPNs':
    the phone on Tailscale too, from anywhere), "network" otherwise."""
    import ipaddress

    out = []
    for ip in [_routed_from(r) for r in _RANGES] + _host_addresses():
        if not ip or ip.startswith("127.") or ip.startswith("169.254.") or ip == "0.0.0.0" or any(a["ip"] == ip for a in out):
            continue
        addr = ipaddress.ip_address(ip)
        kind = "VPN" if addr in ipaddress.ip_network(_VPN) else "local network" if addr.is_private else "network"
        out.append({"ip": ip, "kind": kind})
    # The local network first: a phone on the studio's Wi-Fi needs nothing more.
    return sorted(out, key=lambda a: a["kind"] != "local network")


_lan_lock = threading.Lock()


def _sync_lan(sh: "_Shared") -> None:
    """The page on the network while a guest is valid, never otherwise.
    From Blender's turn and from a request: one at a time."""
    with _lan_lock:
        _sync_lan_locked(sh)


def _sync_lan_locked(sh: "_Shared") -> None:
    with _guests_lock:
        for t in [t for t, g in _guests.items() if g["until"] <= time.time()]:
            del _guests[t]
        wanted = {g.get("ip") for g in _guests.values() if g.get("ip")}
    servers = _lan["servers"]
    for ip in [ip for ip in servers if ip not in wanted]:
        server = servers.pop(ip)
        server.shutdown()
        server.server_close()
        log("INFO", "live", f"Live page: no guest left on {ip}, no longer served there")
    if _server is None:
        return
    for ip in wanted - set(servers):
        try:
            server = ThreadingHTTPServer((ip, _server.server_address[1]), _handler(sh))
        except OSError as e:
            _lan["error"] = f"not served on {ip}: {e}"
            log("WARNING", "live", f"Live page: {_lan['error']}")
            continue
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, name=f"pipeline-live-{ip}", daemon=True).start()
        servers[ip] = server
        _lan["error"] = ""
        log("INFO", "live", f"Live page: served on http://{ip}:{_server.server_address[1]}/ too (guests)")


def _share(raw: dict, sh: "_Shared") -> dict:
    """The host's page: a guest made ({"name", "role", "hours" or "eod",
    "farm": may drive the farm -- an artist away, following their renders}),
    one revoked ({"revoke": token}), or the list ({}). Answers the list,
    and for one made its link and QR code."""
    from datetime import datetime

    from .qr import qr_svg

    out: dict = {}
    if raw.get("revoke"):
        with _guests_lock:
            gone = _guests.pop(str(raw["revoke"]), None)
        if gone:
            log("INFO", "live", f"Live page: {gone['name']}'s access revoked")
        _save_guests()
    elif raw.get("name"):
        name = str(raw["name"]).strip()[:40]
        roles = set((sh.data or {}).get("meta", {}).get("roles") or []) | {"team"}
        role = str(raw.get("role") or "team")
        if role not in roles:
            return {"ok": False, "error": f"no role {role!r} in this project"}
        if raw.get("hours") == "eod":
            end = datetime.now().replace(hour=23, minute=59, second=59).timestamp()
        else:
            try:
                end = time.time() + 3600 * max(1, min(GUEST_MAX_HOURS, int(raw.get("hours") or 1)))
            except (TypeError, ValueError):
                return {"ok": False, "error": "a duration in hours"}
        addresses = [a["ip"] for a in _addresses()]
        ip = str(raw.get("ip") or (addresses[0] if addresses else ""))
        if ip not in addresses:
            return {"ok": False, "error": "this machine is on no network" if not addresses else f"{ip} isn't one of this machine's addresses"}
        token = secrets.token_urlsafe(18)
        with _guests_lock:
            _guests[token] = {"name": name, "role": role, "until": end, "made": time.time(), "ip": ip, "farm": bool(raw.get("farm"))}
        _save_guests()
        _sync_lan(sh)
        if ip not in _lan["servers"]:
            with _guests_lock:
                _guests.pop(token, None)
            _save_guests()
            return {"ok": False, "error": _lan["error"] or f"not served on {ip}"}
        link = f"http://{ip}:{_server.server_address[1]}/?t={token}"
        via = next((a["kind"] for a in _addresses() if a["ip"] == ip), "")
        out.update(link=link, qr=qr_svg(link), until=_iso(end), name=name, role=role, via=via, farm=bool(raw.get("farm")))
        log("INFO", "live", f"Live page: an access for {name} ({role}) until {_iso(end)}")
    return {"ok": True, "guests": _guest_list(), "addresses": _addresses(), **out}


def _beginner() -> bool:
    """The addon's Experience level is Beginner (its default). Never raises."""
    try:
        from ..core import addon_pref

        return getattr(addon_pref(), "experience_level", "BEGINNER") == "BEGINNER"
    except Exception:
        return True


def _as_guest(data: dict, token: str, guest: dict) -> dict:
    """The page's data as a guest gets it: their name, role, token (its
    videos' path too), marked a guest."""
    meta = dict(data["meta"])
    # A guest: new to the page, most often -- its tour shown once on their phone.
    meta["live"] = {**meta["live"], "token": token, "user": guest["name"], "role": guest["role"], "guest": True, "until": _iso(guest["until"]), "beginner": True, "farm": bool(guest.get("farm"))}
    meta["videos"] = {**(meta.get("videos") or {}), "local": f"media/{token}/renders"}
    meta["thumbs"] = f"thumb/{token}"
    return {**data, "meta": meta}
# partial: the first read's latest batch, (root, cache, done, total), for the
# page while the rest is read; progress: (done, total) for the waiting page.
_reader = {"thread": None, "result": None, "at": 0.0, "farm_at": 0.0, "cache": {}, "farm": None, "compare": None, "ready": False,
           "waiting": [], "in_pass": [], "partial": None, "progress": None}


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


def read_live(root: Path, cache: dict, config: dict, v_prefix: str, on_progress=None) -> tuple[dict, bool]:
    """Every tracked folder as read_snapshot_data() gives it, a folder read
    again only when its .pipeline/, its tracking.json or its own listing
    (a .blend saved) changed since cache. Returns (cache, changed).
    on_progress(out, done, total): before each folder, what's read so far
    -- the first read's batches. Pure os/json: thread-safe."""
    out, changed = {}, False
    mtimes: dict = {}
    owners = [
        ("shot" if top == "shots" else "asset", owner)
        for top in _DATA_ROOTS
        for owner in _walk_owner_dirs(root / top, mtimes=mtimes)
    ]
    for i, (kind, owner) in enumerate(owners):
        if on_progress:
            on_progress(out, i, len(owners))
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
    "versions", "checks"} -- the links as a snapshot has them
    (lib/monitoring/snapshot.py folder_links())."""
    out = folder_links(root, {k: e.get("links") or [] for k, e in cache.items()}, outdated)
    for key, e in cache.items():
        out[key].update(versions=e.get("versions") or {}, checks=e.get("checks") or [])
    return out


def _as_data(cache: dict, extras: dict | None = None, work: dict | None = None, rushes: dict | None = None) -> dict:
    """read_live()'s cache as read_snapshot_data()'s result."""
    entries = list(cache.values())
    return {
        "live": extras or {},
        "work": work or {},
        "rushes": rushes or {},
        "raws": [(e["kind"], e["owner"], e["raw"], e["blends"]) for e in entries],
        "renders": {str(e["owner"]): e["renders"] for e in entries if e["renders"] is not None},
        "thumbs": {str(e["owner"]): e["thumb"] for e in entries if e["thumb"]},
        "shot_thumbs": {str(e["owner"]): e["shot_thumbs"] for e in entries if e["shot_thumbs"]},
        "thumb_warnings": [],
    }


def _read(root, cache, config, v_prefix, extras, first=False):
    """A pass over the project (the reader's thread). The first one (no page
    yet): what it has read published as it goes -- a batch after
    FIRST_BATCH, then every BATCH_EVERY -- the page shown at once, filling
    in. See NOTES.md, "Live page: the first read in batches"."""
    started, last = time.monotonic(), [0.0]

    def progress(out, done, total):
        _reader["progress"] = (done, total)
        t = time.monotonic()
        if t - started >= FIRST_BATCH and t - last[0] >= BATCH_EVERY and out:
            last[0] = t
            _reader["partial"] = (root, dict(out), done, total)

    try:
        new, changed = read_live(root, cache, config, v_prefix, on_progress=progress if first else None)
        if changed or extras is None:
            # Links to a newer stable: one listing per folder linked.
            currents = {k: e.get("links") or [] for k, e in new.items()}
            extras = _live_extras(root, new, _outdated_links_of(root, [Path(k) for k in new], currents, v_prefix))
        # Work time: a session ended elsewhere changes no folder -- its own
        # news (one stat a pass, the log read again only when it changed).
        work = work_times(root)
        changed = changed or work != _reader.get("work")
        # What the edit has (editing/rushes/rushes.json): a push changes no folder either.
        rushes = {"rushes": _rushes_by_name(root), "presence": presence(root)}
        changed = changed or rushes != _reader.get("rushes")
        _reader["result"] = (root, new, changed, extras, work, rushes)
    except Exception as e:  # never die silently: the next pass tries again
        log("WARNING", "live", f"Live page: project not read: {e!r}")
        _reader["result"] = (root, cache, False, extras, _reader.get("work"), _reader.get("rushes"))


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
    from ..config import ConfigCache, get_active_project_root

    root = get_active_project_root()
    if root and Path(root) != sh.root:
        # Another project made active: the page follows it -- told it's
        # being read (it reloads on the waiting page), then its data.
        sh.root = Path(root)
        _reader.update(cache={}, result=None, compare=None, farm=None, ready=False, extras=None, work=None, at=0.0, partial=None, progress=None, shown=None)
        with sh.changed:
            sh.version += 1
            sh.data, sh.body = None, b""
            sh.changed.notify_all()
        log("INFO", "live", f"Live page: now {sh.root.name}")
    clock = time.monotonic()
    if clock - _lan.get("checked", 0.0) > 5.0:
        _lan["checked"] = clock
        _sync_lan(sh)  # a guest's access ended: off the network
    page_open = clock - sh.last_seen < IDLE_AFTER
    if page_open:
        # The farm's jobs and machines, read as the Farm tab does --
        # its window closed, nothing else would read them.
        from ...farm.loop import refresh_step

        refresh_step()
    # Update links running in the background: one done, its new version
    # read at once (a pass), its state shown.
    from .. import relink

    if relink.poll():
        _reader["at"] = 0.0
        _rebuild(sh, force=True)
    # The page's actions, applied now; answered after the next pass.
    while True:
        try:
            pending = _actions.get_nowait()
        except queue.Empty:
            break
        # Whatever an action raises, the page is answered (else its request
        # waits the whole minute) and the rest of the turn still runs.
        try:
            if pending.kind == "relink":
                pending.result = _relink(sh.root, pending.review)
                pending.done.set()
                continue
            if pending.kind in ("open", "farm", "play"):
                pending.result = {"open": _open, "farm": _farm_action, "play": _play}[pending.kind](pending.review)
                pending.done.set()
                if pending.kind == "farm":
                    from ...farm.loop import refresh_step

                    refresh_step(soon=True)  # the farm read again now: its change shown
                continue
            pending.result = _apply(sh.root, pending.review)
        except Exception as e:
            log("ERROR", "live", f"Live page: its {pending.kind} action failed: {e!r}")
            pending.result = {"ok": False, "error": f"failed in Blender: {e}"}
            pending.done.set()
            continue
        _reader["waiting"].append(pending)
    thread = _reader["thread"]
    if _reader["result"] is not None and not (thread and thread.is_alive()) and _reader["result"][0] != sh.root:
        _reader["result"] = None  # the project before: dropped
    if _reader["result"] is not None and not (thread and thread.is_alive()):
        _, cache, changed, _reader["extras"], _reader["work"], _reader["rushes"] = _reader["result"]
        _reader["result"] = None
        _reader["cache"] = cache
        _reader["ready"] = True
        _reader["partial"] = _reader["progress"] = _reader["shown"] = None
        _rebuild(sh, force=changed)
        for pending in _reader["in_pass"]:
            pending.result["version"] = sh.version
            pending.done.set()
        _reader["in_pass"] = []
    elif not _reader["ready"] and _reader["partial"] is not None:
        # The first read under way: its latest batch shown, the page filling in.
        root_of, part, done, total = _reader["partial"]
        _reader["partial"] = None
        if root_of == sh.root:
            _reader["shown"] = part  # a file's history found in it meanwhile
            _rebuild(sh, force=True, partial=(part, done, total))
    elif clock - _reader["farm_at"] > 0.5 and page_open:
        # The farm moves on its own -- looked at only while a page is open:
        # with none (its tab closed), nothing but this check every turn.
        _reader["farm_at"] = clock
        _rebuild(sh, force=False)
    if (thread is None or not thread.is_alive()) and _reader["result"] is None and (
        clock - _reader["at"] >= READ_EVERY and page_open
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
                not _reader["ready"],
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
    (lib/monitoring/review_import.py: the same checks, the same idempotence), its
    descriptions and new files too. {"ok", "imported", "validated",
    "fixed", "replies", "changed", "skipped": [[label, reason]]} or
    {"ok": False, "error"}."""
    from ..errors import PipelineError
    from .windows import status_changed
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
        # The page's sitting: its notes under one review header (NOTES.md, "One review id a sitting").
        "review_id": rid if re.fullmatch(r"[0-9a-f]{4,16}", rid := str(raw.get("review_id") or "")) else None,
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
    from ...operators.rushes_ops import push_checked_renders
    from ...operators.tracking_ops import _archive_checked_job
    from ..errors import PipelineError
    from .windows import status_changed
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


def _relink(root: Path, raw: dict) -> dict:
    """Update links on the page's files ({"files": [file names]}): each one
    a new -relink version, written without opening it (lib/relink.py)."""
    from .. import relink
    from .review_import import _review_file

    owners, unknown = [], []
    for name in raw.get("files") or []:
        path = _review_file(str(name))
        if path is None or not path.is_file():
            unknown.append([str(name), "file not found"])
        elif path.parent not in owners:
            owners.append(path.parent)
    res = relink.start(root, owners)
    res["skipped"] = unknown + res["skipped"]
    res["ok"] = bool(res["started"])
    if not res["ok"]:
        res["error"] = "; ".join(f"{n}: {why}" for n, why in res["skipped"]) or "nothing to update"
    return res


def _open(raw: dict) -> dict:
    """Open a file of the project in this Blender, as the page asks: its
    question when its shot or asset is open in another Blender
    ({"elsewhere": [...]}, then "anyway"), when the file open has unsaved
    changes ({"ask": True}), then saved first or not ("save": "save" /
    "discard"). Opened on a timer of
    its own: the load replaces every datablock, this turn ends first."""
    from .review_import import _review_file

    if raw.get("folder"):
        return _open_folder(raw)
    if raw.get("push"):
        return _push_rushes(raw)
    if raw.get("snapshot"):
        return _open_snapshot_export()
    if raw.get("frame") is not None:
        return _frame(raw)
    if raw.get("progress"):
        # Breakdown's reload: a pass over the project now, today's progress point
        # with it (_rebuild()); the page gets both with the new data.
        _reader["at"] = 0.0
        return {"ok": True, "opened": "progress"}
    filepath = _review_file(str(raw.get("file") or ""))
    if not filepath or not filepath.is_file():
        return {"ok": False, "error": "file not found"}
    if not raw.get("anyway"):
        # Its shot or asset open in another Blender: the page asks first
        # (open all the same: "anyway").
        from ..session import open_elsewhere

        others = open_elsewhere(str(filepath), root=_shared.root)
        if others:
            return {"ok": False, "elsewhere": others, "file": filepath.name}
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


def _frame(raw: dict) -> dict:
    """A frame picked on the page (a note's, a retake's) set in this Blender
    too, when it has that file open (its WIP or its stable); else nothing."""
    from .review_import import _review_file

    if not bpy.data.filepath:
        return {"ok": False, "error": "not open"}
    here = Path(bpy.data.filepath).resolve()
    files = [_review_file(str(f)) for f in (raw.get("files") or [])[:2] if f]
    if not any(f and f.resolve() == here for f in files):
        return {"ok": False, "error": "not open"}
    try:
        frame = int(raw["frame"])
    except (TypeError, ValueError):
        return {"ok": False, "error": "no frame"}
    windows = bpy.context.window_manager.windows
    scene = windows[0].scene if windows else bpy.context.scene
    scene.frame_set(frame)
    return {"ok": True, "frame": frame}


def _open_snapshot_export() -> dict:
    """The snapshot's export, asked from the page: its dialog opened in
    this Blender (videos, where to), confirmed there. On a timer: a file
    browser wants Blender's own turn."""

    def show():
        try:
            _with_window(bpy.ops.m_pipeline.export_snapshot, "INVOKE_DEFAULT")
        except Exception as e:
            log("WARNING", "live", f"Live page: the snapshot's export not opened: {e}")
        return None

    bpy.app.timers.register(show, first_interval=0.05)
    return {"ok": True, "opened": "snapshot"}


def _open_folder(raw: dict) -> dict:
    """A file's folder in this machine's file browser: its .blend's
    ("folder": "blend"), or its renders' ("render": the render the page
    shows, "path" under renders/ -- else the file's whole render folder).
    Never a folder out of the project's."""
    from .review_import import _review_file

    root = _shared.root
    filepath = _review_file(str(raw.get("file") or ""))
    if raw.get("folder") == "render":
        renders = (root / "renders").resolve()
        rel = str(raw.get("path") or "")
        target = (renders / rel).resolve() if rel else None
        if target is None or renders not in target.parents or not target.is_dir():
            target = render_root(root, filepath.parent) if filepath else None
        if target is None or not target.is_dir():
            return {"ok": False, "error": "nothing rendered yet"}
        if target.name == "ld":
            target = target.parent  # a light copy's folder: the render's own
    else:
        if not filepath or not filepath.is_file():
            return {"ok": False, "error": "file not found"}
        target = filepath.parent
    _with_window(bpy.ops.wm.path_open, filepath=str(target))
    return {"ok": True, "opened": target.name}


_PRESENCE_ALIVE = 90  # seconds since a session's last ping: still open (it pings every 30)


def presence(root: Path) -> list:
    """Every Blender with a project file open now (config/.sessions/, each
    session's file): [{"user", "machine" (its id's start), "uuid", "file"
    (the .blend's name, no extension), "saved" (saved this session)}] --
    no time: who's on what, not since when. Pure os/json: the reader's
    thread."""
    from ..core import read_json_quiet, seconds_since

    out = []
    try:
        files = sorted((Path(root) / "config" / ".sessions").glob(".session_*.json"))
    except OSError:
        return out
    for f in files:
        data = read_json_quiet(f)
        if not isinstance(data, dict) or not data.get("filepath"):
            continue
        age = seconds_since(data.get("last_ping"))
        if age is None or age > _PRESENCE_ALIVE:
            continue
        out.append({
            "user": data.get("user") or "",
            "machine": data.get("machine") or str(data.get("uuid") or "")[:8],
            "uuid": data.get("uuid") or "",
            "file": Path(str(data["filepath"]).replace("\\", "/")).stem,
            "saved": bool(data.get("saved")),
        })
    return out


def _history(name: str) -> dict:
    """A shot's or asset's history (lib/monitoring/history.py), found by its
    name among the folders the live page read. Pure os/json: the server's
    thread."""
    from .history import file_history

    for e in list((_reader.get("cache") or _reader.get("shown") or {}).values()):
        owner = Path(e["owner"])
        if ((e.get("raw") or {}).get("tracking") or {}).get("file_name", owner.name) == name or owner.name == name:
            return {"ok": True, **file_history(owner)}
    return {"ok": False, "error": "file not found"}


def _push_rushes(raw: dict) -> dict:
    """Into the edit (editing/rushes/, lib/rushes.py), as the page asks:
    one render's video, whatever its version, wip or stable ({"push":
    "render", "path": its folder under renders/}), or every sequence's and
    asset's latest ({"push": "all", "sequences": [...] or all, "assets"}).
    On a thread; its outcome in the log, a popup here if a copy was
    refused (a rush open in the edit)."""
    from ...operators.rushes_ops import push_in_background
    from ..config import ConfigCache
    from ..preview import _first_mp4
    from ..rushes import push_rushes, push_sequence_rushes
    from ..session import get_user

    root = _shared.root
    user = get_user(bpy.context)
    if raw.get("push") == "all":
        try:
            every = sorted(e.name for e in os.scandir(root / "shots") if e.is_dir())
        except OSError:
            every = []
        wanted = raw.get("sequences")
        sequences = [s for s in every if wanted is None or s in wanted]
        push_in_background(push_sequence_rushes, root, sequences, bool(raw.get("assets", True)), ConfigCache.get(), user)
        log("INFO", "live", f"Live page: rushes pushed to editing ({len(sequences)} sequence(s))")
        return {"ok": True, "pushing": "all"}
    renders = (root / "renders").resolve()
    target = (renders / str(raw.get("path") or "")).resolve()
    if renders not in target.parents or not target.is_dir():
        return {"ok": False, "error": "render not found"}
    if target.name == "ld":
        target = target.parent  # a light copy's: the render's own video
    mp4 = _first_mp4(target)
    if mp4 is None:
        return {"ok": False, "error": "no video in this render"}
    push_in_background(push_rushes, root, [mp4], user)
    log("INFO", "live", f"Live page: {target.name} pushed to editing")
    return {"ok": True, "pushing": target.name}


def _play(raw: dict) -> dict:
    """A render's video in this machine's own player -- the full one: the
    page may play its light copy (ld/), never this."""
    from ..preview import _first_mp4

    rel = str(raw.get("video") or "")
    root = (_shared.root / "renders").resolve()
    path = (_shared.root / "renders" / rel).resolve()
    if root not in path.parents or not path.is_file():
        return {"ok": False, "error": "video not found"}
    if path.parent.name == "ld":
        path = _first_mp4(path.parent.parent) or path
    _with_window(bpy.ops.wm.path_open, filepath=str(path))
    return {"ok": True, "opened": path.name}


FINISHED_SHOWN = 20  # the farm's finished jobs listed, newest first


def _farm_data(root: Path) -> dict:
    """The Farm tab's: {"status", "jobs": [{"id", "file", "key" (its
    folder under the project: the page's link to it), "shot", "state",
    "text", "done", "total", "left" (seconds, None not timed), "pace",
    "elapsed", "per_machine" (_per_machine()), "machines", "user", "at"}],
    "workers":
    [{"name", "status", "file", "mine", "host", "since"}], "me", "presets",
    "preset"}, from the monitor cache. Memory only."""
    from ...farm.details import estimate_label, render_left_parts
    from ...farm.loop import _STAGE_WORDS, entry_state
    from ...farm.monitor import REMOVABLE_STAGES, get_monitor_cache
    from ...farm.queue import RETRYABLE_STAGES
    from ..session import get_user

    cache = get_monitor_cache()
    user = get_user(bpy.context)
    compiling = cache.get("ffmpeg_progress") or {}
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
            # Its detail on the page.
            "stage": stage,
            "priority": j.get("priority", 10),
            "preset": j.get("prerender_script") or "",
            "department": j.get("department") or "",
            "range": j.get("frame_range"),
            "names": [_machine(cache, u) for u in j.get("machines") or []],
            "pending": stage == "pending",
            # the Farm tab's buttons, where they apply.
            "retry": stage in RETRYABLE_STAGES,
            "recompile": stage == "finished" and bool(j.get("output_dir")),
            "removable": stage == "pending" or stage in REMOVABLE_STAGES,
            "mine": (j.get("user") or "") == user,
            # Waiting for a worker: what it'll take, at its last pace.
            "estimate": estimate_label(j, cache) if j.get("frames_to_render") and stage != "render_start" else "",
            "compile": compiling.get(j.get("job_id")),
            # Its pace: seconds a frame (the machines' mean), how long in
            # this step, each machine's own pace and the frame it's on.
            "pace": j.get("seconds_per_frame"),
            "elapsed": j.get("elapsed_seconds") or 0,
            "per_machine": _per_machine(cache, j),
            # Render here: on its own machine, outside the queue; drawn by its 3D view.
            "tags": [t for t in ("local", "viewport") if j.get(t)],
        }
        (finished if state == "finished" else jobs).append(row)
    finished.sort(key=lambda r: r["at"], reverse=True)
    from ...farm.monitor import is_blender_monitor
    from ...farm.workers import is_blender_worker, worker_rendering
    from ..core import get_machine_id

    mine = get_machine_id() or ""
    host = cache.get("lock_machine") or ""
    silent = cache.get("silent_workers") or {}
    workers = [
        {
            "uuid": uuid,
            "name": _machine({"workers": {uuid: w}}, uuid),
            "status": "silent" if uuid in silent else w.get("status") or "",
            "file": Path(w.get("current_file") or "").stem,
            "mine": uuid == mine,
            "host": bool(host) and (w.get("machine") or uuid[:8]) == host,
            # Kept for its own renders (Render here): the farm sends it nothing.
            "local": bool(w.get("local_only")),
            # Silent: its last heartbeat -- crashed, closed, asleep?
            "since": _iso(w.get("last_heartbeat")) if uuid in silent else "",
        }
        for uuid, w in sorted(
            [*(cache.get("workers") or {}).items(), *((u, w) for u, w in silent.items() if u not in (cache.get("workers") or {}))],
            key=lambda kv: (kv[0] not in (cache.get("workers") or {}), str(kv[1].get("user") or "")),
        )
        if isinstance(w, dict)
    ]

    me = {
        "worker": is_blender_worker(),
        "rendering": worker_rendering(),
        "host": is_blender_monitor(),
        "host_name": " ".join(x for x in (cache.get("lock_user") or "", f"({cache.get('lock_machine')})" if cache.get("lock_machine") else "") if x),
        "host_now": _host_now(jobs, workers),
    }
    return {
        "status": cache.get("status") or "unknown",
        "jobs": jobs + finished[:FINISHED_SHOWN],
        "workers": workers,
        "me": me,
        # The machine time the jobs still need, over the live workers.
        # Said by the page, in its language: {"seconds", "workers", "unknown"}.
        "left": render_left_parts([j for j in cache.get("jobs") or [] if entry_state(j) != "finished"], cache),
        **_presets(),
    }


# The stages the farm host runs itself (a Blender or an ffmpeg of its own).
_HOST_STAGES = ("setup_start", "checks_images_start", "compilation_start")


def _host_now(jobs: list, workers: list) -> list[dict]:
    """What the farm host is doing right now, for the Farm tab's head:
    [{"what" (_STAGE_WORDS' words, said by the page), "file"}] -- its own
    steps (a setup, a frame check, a video), its worker's render. [] for
    nothing."""
    doing = [
        {"what": j["text"], "file": j["file"]}
        for j in jobs
        if j["stage"] in _HOST_STAGES and "local" not in j["tags"]
    ]
    doing += [{"what": "rendering", "file": w["file"]} for w in workers if w["host"] and w["status"] == "rendering"]
    return doing


def _presets() -> dict:
    """The page's Render form: {"presets": [[name, label]], "preset" (with
    no department: none)} -- the Render dialog's picker."""
    from ...operators.farm_ops import _NO_SCRIPT, _get_pre_render_scripts
    from ..config import ConfigCache

    from .status import preset_department

    config = ConfigCache.get() or {}
    items = [list(i[:2]) for i in _get_pre_render_scripts(None, bpy.context) if i]
    departments = [*(config.get("shots_departments") or []), *(config.get("assets_departments") or [])]
    return {
        "presets": items,
        "preset": _NO_SCRIPT,
        # The department each preset's name gives, and the one set for each department
        # (Project settings > By department): the form's preset follows its department.
        "preset_deps": {n: preset_department(n, departments) for n, _ in items},
        "dept_presets": (config.get("farm") or {}).get("department_presets") or {},
    }


def _iso(value) -> str:
    """A heartbeat (an epoch, or already a date) as the page's dates."""
    if isinstance(value, (int, float)):
        from datetime import datetime

        return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")
    return str(value or "")


def _per_machine(cache: dict, job: dict) -> list[dict]:
    """A job's machines for its detail on the page: [{"name", "pace"
    (seconds a frame, None not timed yet), "frame" (the one it's on while
    the job renders, None)}] -- the machines it was given, then any that
    timed a frame on it."""
    paces = job.get("machine_seconds") or {}
    on = {}
    if job.get("stage") == "render_start":
        for claim in ((cache.get("claims") or {}).get(job.get("job_id")) or {}).values():
            if isinstance(claim, dict) and claim.get("machine"):
                on[claim["machine"]] = claim.get("frame_in_progress")
    uuids = list(dict.fromkeys([*(job.get("machines") or []), *paces, *on]))
    return [{"name": _machine(cache, u), "pace": paces.get(u), "frame": on.get(u)} for u in uuids]


def _machine(cache: dict, uuid: str) -> str:
    w = (cache.get("workers") or {}).get(uuid) or {}
    return f"{w['user']} ({w.get('machine') or uuid[:8]})" if w.get("user") else w.get("machine") or uuid[:8]


def _farm_action(raw: dict) -> dict:
    """The Farm tab's buttons, as the Farm tab's: "cancel", "retry",
    "archive" a job, its "priority" (the job file's: the queue reads it
    each tick), "worker" this machine (on / off: a render it's on stopped
    after its frame or now, as the page's two buttons ask: _stop_self());
    "render" / "preview": _farm_submit()."""
    from ..config import ConfigCache
    from ..core import locked_json
    from ..errors import PipelineError

    action, job = str(raw.get("action") or ""), str(raw.get("job_id") or "")
    if job and not re.fullmatch(r"job_[A-Za-z0-9_-]+", job):
        # A job's id names its file: nothing else reaches a path.
        return {"ok": False, "error": f"no job {job!r}"}
    if action in ("render", "preview"):
        try:
            return _farm_submit(action, raw)
        except PipelineError as e:
            return {"ok": False, "error": e.message}
    ops = {
        "cancel": bpy.ops.m_pipeline.farm_cancel_job,
        "retry": bpy.ops.m_pipeline.farm_retry_job,
        "archive": bpy.ops.m_pipeline.farm_archive_job,
        "recompile": bpy.ops.m_pipeline.farm_recompile_job,
    }
    from ...farm.details import job_detail, job_path, worker_detail

    try:
        # Read on demand: a job's file, a machine's from the monitor cache.
        if action == "detail" and job:
            return {"ok": True, "detail": job_detail(job)}
        if action == "worker_detail":
            return {"ok": True, "detail": worker_detail(str(raw.get("value") or ""))}
        if action == "open" and job:
            path = job_path(job, str(raw.get("value") or ""))
            if not path or not path.exists():
                return {"ok": False, "error": "not found"}
            _with_window(bpy.ops.wm.path_open, filepath=str(path))
            return {"ok": True}
        if action == "remove" and job:
            from ...farm.monitor import remove_waiting_job

            # Pending: its request not claimed yet, still in incomings/ (the
            # page doesn't say; the file does).
            pending = (ConfigCache.get_path("farm_incomings") / f"{job}.json").is_file()
            if not remove_waiting_job(job, pending):
                return {"ok": False, "error": "it started meanwhile: cancel it instead"}
            log("INFO", "farm", f"Job {job} removed from the queue from the live page.")
            return {"ok": True}
        if action == "archive_all" and raw.get("value") in ("finished", "failed"):
            done = _with_window(bpy.ops.m_pipeline.farm_archive_jobs, "EXEC_DEFAULT", state=raw["value"])
            return {"ok": "FINISHED" in done}
        if action in ("stop_worker", "forget_worker"):
            from ...farm.workers import forget_worker, request_worker_stop
            from ..core import get_machine_id
            from ..session import get_user

            uuid = str(raw.get("value") or "")
            if not uuid:
                return {"ok": False, "error": "no machine"}
            if action == "forget_worker":
                return {"ok": True} if forget_worker(uuid) else {"ok": False, "error": "it's back: not forgotten"}
            if uuid == get_machine_id():
                return _stop_self(bool(raw.get("now")))
            request_worker_stop(uuid, bool(raw.get("now")), get_user(bpy.context))
            return {"ok": True, "note": "on its next tick (about 10 s)"}
        if action in ops and job:
            done = _with_window(ops[action], "EXEC_DEFAULT", job_id=job)
            return {"ok": "FINISHED" in done}
        if action == "priority" and job:
            path = ConfigCache.get_path("farm_actives") / f"{job}.json"
            if not path.is_file():
                return {"ok": False, "error": "not in the queue yet: try again in a moment"}
            with locked_json(path) as box:
                data = box["data"] or {}
                try:
                    data["priority"] = max(0, min(100, int(raw.get("value", 10))))
                except (TypeError, ValueError):
                    return {"ok": False, "error": "a priority is a number"}
                box["action"] = "to_write"
            log("INFO", "live", f"Live page: job {job} priority {data['priority']}")
            return {"ok": True}
        if action in ("launch_monitor", "kill_monitor"):
            return _farm_monitor(action, bool(raw.get("force")))
        if action == "worker":
            if not raw.get("value"):
                return _stop_self(bool(raw.get("now")))
            done = _with_window(bpy.ops.m_pipeline.farm_add_self_worker, "EXEC_DEFAULT")
            return {"ok": "FINISHED" in done}
    except (PipelineError, RuntimeError, ValueError, OSError) as e:
        return {"ok": False, "error": getattr(e, "message", None) or str(e)}
    return {"ok": False, "error": f"unknown action {action!r}"}


def _stop_self(now: bool) -> dict:
    """This machine's worker stopped from the page: on a render, after its
    frame or now (the page's two buttons, Blender's popup's two choices);
    idle, its role given up (farm_kill_self_worker)."""
    from ...farm.workers import stop_worker, worker_rendering

    if worker_rendering():
        outcome = stop_worker(kill_render=now)
        return {"ok": True, "note": "once its frame is written" if outcome == "draining" else ""}
    done = _with_window(bpy.ops.m_pipeline.farm_kill_self_worker, "EXEC_DEFAULT")
    return {"ok": "FINISHED" in done}


def _farm_monitor(action: str, force: bool) -> dict:
    """The Farm tab's Launch / Stop the farm, as the Farm tab's: launched
    here (force: the page confirmed taking over a stuck one), refused while
    another runs or without FFmpeg (its checks would fail every job); a
    stop asked of the monitor, wherever it runs, for its next tick."""
    from ...farm import launch_monitor, refresh_monitor_status, request_monitor_kill
    from ...farm.loop import monitor_age_status, monitor_last_tick
    from ..config import ConfigCache, get_active_project_root
    from ..core import EARLIEST, read_json_quiet, resolve_ffmpeg
    from ..session import get_user

    user = get_user(bpy.context)
    lock = ConfigCache.get_path("monitor_file")
    data = read_json_quiet(lock) if lock.exists() else None
    running = data is not None and monitor_age_status(monitor_last_tick(lock, data) or EARLIEST) == "running"
    if action == "kill_monitor":
        if data is None:
            return {"ok": False, "error": "no farm running"}
        request_monitor_kill(user)
        log("INFO", "live", f"Live page: farm stop asked by {user}")
        return {"ok": True, "note": "on its next tick (about 10 s)"}
    if running:
        return {"ok": False, "error": f"already running, by {data.get('user', '?')} on {data.get('machine', '?')}"}
    if data is not None and not force:
        return {"ok": False, "error": "a stuck farm holds it: take it over"}
    if not resolve_ffmpeg():
        return {"ok": False, "error": "FFmpeg not found on this machine (Preferences > FFmpeg path)"}
    launch_monitor(get_active_project_root(), user, force=data is not None)
    refresh_monitor_status()
    log("INFO", "live", f"Live page: farm launched by {user}")
    return {"ok": True}


def _farm_submit(action: str, raw: dict) -> dict:
    """The page's Render: a file sent to the farm as the Render dialog
    sends it ("file", "preset", "priority", "mode" all / single, "start"
    / "end" frames -- absolute, empty: the file's --, "shots" of a block
    ticked), or its sequence's preview ("sequence")."""
    from ...farm.monitor import job_request
    from ...operators.farm_ops import _NO_SCRIPT
    from ...operators.preview_ops import dropped_message, request_sequence_preview
    from ..config import get_active_project_root
    from .review_import import _review_file
    from ..session import get_user

    user = get_user(bpy.context)
    try:
        priority = max(0, min(100, int(raw.get("priority", 10))))
    except (TypeError, ValueError):
        priority = 10
    if action == "preview":
        sequence = str(raw.get("sequence") or "")
        root = get_active_project_root()
        # A folder's name, nothing that climbs out of shots/ (.., \\, /).
        if not re.fullmatch(r"[\w-]+", sequence) or not root or not (Path(root) / "shots" / sequence).is_dir():
            return {"ok": False, "error": f"no sequence {sequence!r}"}
        dropped: list = []
        if not request_sequence_preview(sequence, user, priority, dropped):
            return {"ok": False, "error": f"nothing rendered yet in {sequence}"}
        log("INFO", "live", f"Live page: preview of {sequence} requested")
        return {"ok": True, "sent": f"preview of {sequence}", "note": dropped_message(dropped)}
    filepath = _review_file(str(raw.get("file") or ""))
    if not filepath or not filepath.is_file():
        return {"ok": False, "error": "file not found"}
    names = {n for n, _ in _presets()["presets"]}
    preset = str(raw.get("preset") or "")
    if preset not in names:
        return {"ok": False, "error": f"no preset {preset!r}"}
    shots = None
    if isinstance(raw.get("shots"), list):
        shots = sorted({int(d) for x in raw["shots"] if (d := re.sub(r"\D", "", str(x)))})
        if not shots:
            return {"ok": False, "error": "no shot ticked"}
    # The frames: the file's own, or absolute ones (the dialog's "a").
    frames = []
    for key in ("start", "end"):
        value = str(raw.get(key) or "").strip()
        if not value:
            frames.append("n")
            continue
        try:
            frames.append(f"a{int(value)}")
        except ValueError:
            return {"ok": False, "error": f"{key} frame {value!r} isn't a number"}
    if all(f != "n" for f in frames) and int(frames[0][1:]) > int(frames[1][1:]):
        return {"ok": False, "error": "the start frame is after the end one"}
    job_request(
        filepath,
        user=user,
        priority=priority,
        render_mode="single" if raw.get("mode") == "single" else "all",
        increment=True,
        prerender_script="" if preset == _NO_SCRIPT else preset,
        overrided_frame_range=tuple(frames),
        only_shots=shots,
        sound=raw.get("sound") is not False,
        # The department picked in the form ("" none); absent (an older page): its preset's name's.
        department=_render_department(filepath, raw.get("department")),
    )
    log("INFO", "live", f"Live page: {filepath.name} sent to the farm")
    return {"ok": True, "sent": filepath.name}


def _render_department(filepath: Path, picked) -> str | None:
    """The department the page's Render form picked, if one of the file's
    kind's ("" none); None (an older page, no field): its preset's name's."""
    from ...operators.farm_ops import _file_departments

    if not isinstance(picked, str):
        return None
    picked = picked.strip().lower()
    return picked if picked in [d.lower() for d in _file_departments(str(filepath))] else ""


def _rebuild(sh: _Shared, force: bool, partial: tuple | None = None) -> None:
    """The page's data from the last pass and the farm's jobs (memory
    only): a new version when it differs. partial: (cache, done, total),
    the first read's batch -- its folders only, no work times, no links to
    a newer stable yet, nothing logged (today's progress: the whole
    project's), the page told it's partial (meta "reading")."""
    from ...farm.loop import farm_activity
    from ..config import ConfigCache
    from ..session import get_user, get_user_role, ui_language

    if not _reader["ready"] and partial is None:
        return  # nothing read yet: no empty page
    farm = farm_activity()
    jobs = _farm_data(sh.root)
    from .. import relink

    relinks = relink.states()
    config = ConfigCache.get() or {}
    # The project's preferences (its team, roles, departments...) and this
    # Blender's user and role: changed in Blender, the page follows on the
    # next turn -- not only once a file changes.
    prefs = (
        json.dumps(config, sort_keys=True, default=str),
        get_user(bpy.context),
        get_user_role(bpy.context),
        ui_language(),
    )
    if not force and (farm, jobs, relinks, prefs) == _reader["farm"]:
        return
    if partial is None:
        _reader["farm"] = (farm, jobs, relinks, prefs)
    meta = {
        "project": config.get("project_name") or sh.root.name,
        "scan_started_at": now(),
        "exported_by": get_user(bpy.context),
        "addon_version": get_addon_version(),
        "lang": ui_language(),
        # Who writes from the page: Blender's user and role (Preferences).
        # root: another project made active, the page reloads.
        # beginner: the addon's Experience level -- the page's tour shown once.
        "live": {"token": sh.token, "user": get_user(bpy.context), "role": get_user_role(bpy.context) or "team", "root": str(sh.root), "beginner": _beginner()},
        # Played from the project, through the server.
        "videos": {"mode": "live", "base": None, "files": [], "local": f"media/{sh.token}/renders"},
        # Thumbnails too, by their hash: none inline in the page.
        "thumbs": f"thumb/{sh.token}",
    }
    side = _reader.get("rushes") or {}
    # Who has which file open (the Farm tab's machines; a file's detail).
    meta["presence"] = side.get("presence") or []
    if partial is None:
        data = _as_data(_reader["cache"], _reader.get("extras"), _reader.get("work"), side.get("rushes"))
    else:
        part, done, total = partial
        meta["reading"] = {"done": done, "total": total}
        data = _as_data(part, _live_extras(sh.root, part, {}))
    snap = build_snapshot(data, config, meta, farm=farm)
    # Today's progress point while the page runs (written only when it changes), the days for the page.
    if partial is None:
        progress_log.record_today(sh.root, snap)
    snap["meta"]["history"] = progress_log.days(sh.root)
    thumbs: dict[str, bytes] = {}
    data = page_data(snap, thumbs)
    # Its Farm tab: the farm as the Farm tab shows it.
    data["farm"] = jobs
    # Update links under way or just ended, by folder (lib/relink.py).
    data["relink"] = relinks
    # Compared without its date: a pass finding nothing new is no news.
    compare = json.dumps({**data, "meta": {**data["meta"], "snapshot": ""}}, ensure_ascii=False, separators=(",", ":"))
    if compare == _reader["compare"]:
        return
    _reader["compare"] = compare
    with sh.changed:
        sh.version += 1
        data["meta"]["live"]["version"] = sh.version
        sh.data = data
        sh.thumbs = thumbs
        sh.body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        sh.changed.notify_all()


# --- the server's threads -------------------------------------------------------------


def _handler(sh: _Shared):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _allowed(self, token: str) -> bool:
            """Who's asking: self.guest None (this machine's page) or a
            guest's -- False for anyone else. The token: no other site may
            call us. The Host: no DNS rebinding (a site's name pointed at
            this address). On the network, guests only."""
            host, port = self.server.server_address[:2]
            self.guest = None
            if host == "127.0.0.1":
                if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                    return False
                if hmac.compare_digest(token or "", sh.token):
                    return True
            elif self.headers.get("Host") != f"{host}:{port}":
                return False
            self.guest = guest_of(token)
            self.token = token
            return self.guest is not None

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
            media = re.match(r"/(media|thumb)/([^/]+)/(.+)$", parsed.path)
            if not self._allowed(media[2] if media else q.get("t", "")):
                return self._send(403, b"forbidden", "text/plain")
            with sh.lock:
                sh.last_seen = time.monotonic()
            try:
                if parsed.path == "/":
                    self._page()
                elif parsed.path == "/data":
                    try:
                        since = int(q.get("since", -1))
                    except ValueError:
                        return self._send(400, b"bad request", "text/plain")
                    self._data(since)
                elif media and media[1] == "thumb":
                    self._thumb(media[3])
                elif media:
                    self._media(unquote(media[3]))
                else:
                    self._send(404, b"not found", "text/plain")
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser let go (a seek, another video): normal

        def do_POST(self):
            parsed = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            if not self._allowed(q.get("t", "")):
                return self._send(403, b"forbidden", "text/plain")
            if parsed.path not in ("/action", "/open", "/farm", "/play", "/share", "/relink", "/history"):
                return self._send(404, b"not found", "text/plain")
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if not 0 < length < 4 * 1024 * 1024 or "json" not in (self.headers.get("Content-Type") or ""):
                return self._send(400, b"bad request", "text/plain")
            try:
                raw = json.loads(self.rfile.read(length))
            except ValueError:
                return self._send(400, b"bad request", "text/plain")
            with sh.lock:
                sh.last_seen = time.monotonic()
            raw = raw if isinstance(raw, dict) else {}
            kind = parsed.path.strip("/").replace("action", "review")
            if self.guest is not None:
                # A guest reviews, as themselves; the farm read only unless
                # its access says it may drive it (launch, stop, renders,
                # priorities); never anything opened on this machine
                # (Blender, its player, a folder, a log, sharing).
                farm_ok = ("detail", "worker_detail") if not self.guest.get("farm") else None
                if kind in ("open", "play", "share", "relink") or kind == "farm" and (raw.get("action") == "open" or farm_ok is not None and raw.get("action") not in farm_ok):
                    return self._send(403, json.dumps({"ok": False, "error": "not from a guest's page"}).encode(), "application/json")
                if kind == "review":
                    raw["author"], raw["role"] = self.guest["name"], self.guest["role"]
                    for a in raw.get("actions") or []:
                        if isinstance(a, dict):
                            a.pop("push", None)
                    log("INFO", "live", f"Live page: {self.guest['name']} (guest, {self.guest['role']}): {len(raw.get('actions') or [])} action(s)")
            if kind == "share":
                return self._send(200, json.dumps(_share(raw, sh)).encode(), "application/json")
            if kind == "history":
                # Read only, on this thread: guests too.
                return self._send(200, json.dumps(_history(str(raw.get("name") or ""))).encode(), "application/json")
            pending = _Pending(raw, kind)
            _actions.put(pending)
            # Blender's turn, then a pass over the project: the data that
            # shows them. Blender busy longer: the page sends them again
            # (applying twice changes nothing).
            if not pending.done.wait(60):
                return self._send(504, json.dumps({"ok": False, "error": "Blender didn't answer"}).encode(), "application/json")
            self._send(200, json.dumps(pending.result).encode(), "application/json")

        def _page(self):
            with sh.lock:
                data, name = sh.data, sh.root.name
            if data is None:
                # Being read (opened, another project): a page that says so,
                # replaced by the project's once its data is there.
                return self._send(200, _waiting_page(name).encode("utf-8"), "text/html; charset=utf-8")
            if self.guest is not None:
                data = _as_guest(data, self.token, self.guest)
            self._send(200, render_page(data).encode("utf-8"), "text/html; charset=utf-8")

        def _data(self, since: int):
            # Long poll: answered as soon as there's a new version, else
            # after POLL -- with "busy" if Blender has had no turn for a while.
            with sh.changed:
                sh.changed.wait_for(lambda: sh.version != since or sh.stopped, timeout=POLL)
                busy = time.monotonic() - sh.last_tick > BUSY_AFTER
                head = {"version": sh.version, "busy": busy, "reading": sh.data is None}
                if sh.data is None and _reader.get("progress"):
                    head["read"] = list(_reader["progress"])  # the waiting page's x / y
                body = sh.body if sh.version != since else b""
                if body and self.guest is not None:
                    body = json.dumps(_as_guest(sh.data, self.token, self.guest), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            out = json.dumps(head).encode()
            if body:
                out = out[:-1] + b',"data":' + body + b"}"
            self._send(200, out, "application/json")

        def _thumb(self, key: str):
            # Named by the hash of its bytes: never another image at that address.
            with sh.lock:
                body = sh.thumbs.get(key)
            if body is None:
                return self._send(404, b"not found", "text/plain")
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "private, max-age=86400, immutable")
            self.end_headers()
            self.wfile.write(body)

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


def _waiting_page(project: str) -> str:
    """While the project is read: its name, a line moving, then the page."""
    name = html.escape(project)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{name} live</title>
<style>:root{{color-scheme:light dark;--bg:#f6f5f2;--fg:#24211d;--mu:#8a847b;--ac:#e0702e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1c1b19;--fg:#ecebe8;--mu:#8f8a82}}}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif}}
.b{{text-align:center;padding:0 16px}}h1{{font-size:20px;font-weight:600;margin:0 0 6px}}p{{margin:0;color:var(--mu)}}
.l{{width:180px;height:3px;margin:18px auto 0;border-radius:2px;background:color-mix(in srgb,var(--mu) 25%,transparent);overflow:hidden}}
.l i{{display:block;width:40%;height:100%;border-radius:2px;background:var(--ac);animation:m 1.1s ease-in-out infinite alternate}}
@keyframes m{{from{{transform:translateX(-10%)}}to{{transform:translateX(160%)}}}}
@media (prefers-reduced-motion:reduce){{.l i{{animation:none;width:100%;opacity:.5}}}}</style></head>
<body><div class="b" role="status"><h1>{name}</h1><p id="r">Blender is reading the project…</p><div class="l"><i></i></div></div>
<script>var T=new URLSearchParams(location.search).get("t")||"";
function go(v){{fetch("data?t="+encodeURIComponent(T)+"&since="+v,{{cache:"no-store"}}).then(function(r){{if(!r.ok)throw r.status;return r.json();}})
.then(function(d){{if(!d.reading)location.reload();else{{if(d.read&&d.read[1])document.getElementById("r").textContent="Blender is reading the project: "+d.read[0]+" / "+d.read[1];go(d.version);}}}}).catch(function(){{setTimeout(function(){{go(v);}},2000);}});}}go(-1);</script>
</body></html>"""


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
    global _config_dir
    _config_dir = Path(bpy.utils.user_resource("CONFIG", create=True))
    _load_guests()
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
                   waiting=[], in_pass=[], extras=None, work=None)
    # persistent: kept when a file is opened.
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=0.0, persistent=True)
    log("INFO", "live", f"Live page served at {url()}")
    return url()


def open_page(root: Path, anchor: str = "") -> str:
    """The server for root started (start()), its page opened in the
    browser, on anchor (a file's name, a tab) if given. Returns its URL.
    Raises OSError when no port is free."""
    import webbrowser
    from urllib.parse import quote

    address = start(root)
    webbrowser.open(f"{address}#{quote(anchor)}" if anchor else address)
    return address


def served_elsewhere() -> bool:
    """Another Blender on this machine serves the page already: one of
    PORTS (not this one's) knows this machine's token -- a thumbnail it
    hasn't is a 404 to it, a 403 to anyone else. Each port asked for an
    instant, nothing read."""
    import http.client

    try:
        token = _token()
    except OSError:
        return False
    own = _server.server_address[1] if _server is not None else None
    for port in PORTS:
        if port == own:
            continue
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=0.3)
        try:
            conn.request("GET", f"/thumb/{token}/none")
            if conn.getresponse().status == 404:
                return True
        except OSError:
            continue
        finally:
            conn.close()
    return False


def auto_open(root: Path) -> bool:
    """The page opened on its own (Preferences > Open the live page): when
    this Blender doesn't serve it yet and no other one on this machine
    does -- one tab, not one per Blender. True if it opened."""
    if running() or served_elsewhere():
        return False
    address = open_page(root)
    log("INFO", "live", f"Live page opened on its own: {address}")
    return True


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
    with _lan_lock:
        for server in _lan["servers"].values():
            server.shutdown()
            server.server_close()
        _lan["servers"].clear()
    # What the page asked and Blender never turned to: answered now, not
    # applied on the next start (a cancel, a priority long after).
    while True:
        try:
            pending = _actions.get_nowait()
        except queue.Empty:
            break
        pending.result = {"ok": False, "error": "the live page stopped"}
        pending.done.set()
    for pending in _reader["waiting"] + _reader["in_pass"]:
        pending.done.set()
    _reader["waiting"], _reader["in_pass"] = [], []
    _shared, _server = None, None
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    log("INFO", "live", "Live page stopped")
    return True
