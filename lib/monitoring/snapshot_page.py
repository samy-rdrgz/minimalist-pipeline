"""The production snapshot's page: build_snapshot()'s dict as one offline
HTML file. Python only shapes the data (page_data()); the page itself --
templates/snapshot/: page.html, its stylesheet (css/, CSS_PARTS) and its
script (js/, JS_PARTS) and the logo -- draws it in the
browser. Pure: thread-safe."""

import base64
import hashlib
import json
import re
from pathlib import Path

from ..config import covering_role
from ..core import parse_iso, time_key
from .review_import import REVIEW_JSON_FORMAT
from .snapshot import (
    SCHEMA_VERSION,
    _owner_shots,
    _render_ref,
    group_renders,
    shots_label,
    snapshot_filename,
)

PAGE_DIR = Path(__file__).resolve().parents[2] / "templates" / "snapshot"

# The page's sources, in this order (templates/snapshot/css/, js/): one
# stylesheet and one script in the page, the script inside one function
# (page.html). js/core/ holds the data, the state and the actions, shared
# by the desktop's views (js/desktop/) and the phone's (js/mobile/); the
# component sheet (tools/snapshot_kit.py, tools/snapshot_kit_src/) is built from the same
# parts, without the events and the start.
CSS_PARTS = ("10-tokens.css", "20-components.css", "22-panes.css", "25-theme.css", "30-mobile.css")
JS_PARTS = (
    "core/00-data.js",
    "core/01-i18n.js",
    "i18n/fr.js",
    "core/02-lang.js",
    "core/03-status.js",
    "core/05-mode.js",
    "core/10-status.js",
    "core/20-actions.js",
    "core/25-search.js",
    "core/26-xlsx.js",
    "core/30-review-file.js",
    "core/40-player.js",
    "core/42-videos.js",
    "desktop/20-top-tree.js",
    "desktop/21-list.js",
    "desktop/21-activity.js",
    "desktop/21-projection.js",
    "desktop/21-todo.js",
    "desktop/21-export.js",
    "desktop/22-detail.js",
    "desktop/22-history.js",
    "desktop/23-farm.js",
    "desktop/24-links.js",
    "desktop/25-wide.js",
    "desktop/26-shell.js",
    "desktop/27-review.js",
    "desktop/28-dialogs.js",
    "desktop/29-events.js",
    "desktop/30-panes.js",
    "mobile/50-mobile.js",
    "live/60-live.js",
    "live/61-share.js",
    "boot.js",
)


def _parts(folder: str, names) -> str:
    """The parts read and put end to end, each on its own lines."""
    out = []
    for name in names:
        text = (PAGE_DIR / folder / name).read_text(encoding="utf-8")
        out.append(text if text.endswith("\n") else text + "\n")
    return "".join(out)


_PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
_VIEWBOX = re.compile(r'viewBox="([^"]+)"')
_PATH = re.compile(r'<path[^>]*\sd="([^"]+)"')
# The stylesheet's comments, left out of every page (no string of it
# holds "/*"). The script's stay: its template strings span lines.
_CSS_COMMENTS = re.compile(r"/\*.*?\*/\n?", re.S)
# Blender's icons (templates/snapshot/icons, tools/clean_icons.py).
_ICON = re.compile(r'<svg[^>]*\sviewBox="([^"]+)"[^>]*>(.*)</svg>', re.S)


def icon_sprite(text: str) -> str:
    """The Blender icons the page names ("b-play": its file icons/play.svg)
    as <symbol>s, drawn by <use href="#b-play"> -- those named only."""
    symbols = []
    for path in sorted((PAGE_DIR / "icons").glob("*.svg")):
        if f"b-{path.stem}" in text:
            view, body = _ICON.search(path.read_text(encoding="utf-8")).groups()
            symbols.append(f'<symbol id="b-{path.stem}" viewBox="{view}">{body}</symbol>')
    return '<svg width="0" height="0" style="position:absolute" aria-hidden="true">' + "".join(symbols) + "</svg>"


def render_html(snapshot: dict) -> str:
    """The whole snapshot as one offline HTML page (render_page())."""
    return render_page(page_data(snapshot))


def render_page(data: dict) -> str:
    """page.html with the stylesheet, the script, the logo, the Blender icons it names and data (page_data()) put in, in one
    pass (a value is never read again for placeholders). The live page's
    too (lib/monitoring/live.py)."""
    logo = (PAGE_DIR / "logo.svg").read_text(encoding="utf-8")
    viewbox = _VIEWBOX.search(logo)[1]
    width, height = viewbox.split()[2:]
    title = f"{data['meta'].get('project') or 'Project'} {'live' if data['meta'].get('live') else 'snapshot'}"
    data = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    values = {
        "TITLE": _escape(title),
        "CSS": _CSS_COMMENTS.sub("", _parts("css", CSS_PARTS)),
        # Kept whole: its template strings may hold a line starting "//".
        "JS": _parts("js", JS_PARTS),
        "LOGO_VB": viewbox,
        # The <use> of a symbol draws it from 0 0: its box, not the source's.
        "LOGO_VB0": f"0 0 {width} {height}",
        "LOGO_PATH": _PATH.search(logo)[1],
        # Inside <script>: no "</" may close it early.
        "DATA": data.replace("</", "<\\/"),
    }
    shell = (PAGE_DIR / "page.html").read_text(encoding="utf-8")
    values["ICONS"] = icon_sprite(shell + values["JS"])
    return _PLACEHOLDER.sub(lambda m: values[m[1]], shell)


def _stem(filename: str | None) -> str | None:
    return Path(filename).stem if filename else None


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def page_data(snapshot: dict, thumbs: dict | None = None) -> dict:
    """What page.js draws: {"meta", "items", "images"}. images: each
    thumbnail once, by the hash of its bytes -- a block's thumbnail is also
    its first shot's -- as the URL an <img> shows. thumbs (the live page):
    the thumbnails' bytes put there by hash instead, images only naming
    them (1), the page asking Blender's server for each (meta.thumbs)."""
    meta = snapshot["meta"]
    roles = meta.get("validation_roles") or []
    images: dict[str, str] = {}

    def image(b64: str | None) -> str | None:
        if not b64:
            return None
        key = hashlib.sha1(b64.encode("ascii")).hexdigest()[:12]
        if thumbs is not None:
            if key not in thumbs:
                thumbs[key] = base64.b64decode(b64)
            images[key] = 1
        else:
            images.setdefault(key, "data:image/jpeg;base64," + b64)
        return key

    notes: dict[str, list] = {}
    for thread in snapshot["notes"]:
        notes.setdefault(thread["item"], []).append(thread)
    items = [
        _item(item, notes.get(item["name"], []), roles, image)
        for item in snapshot["shots"] + snapshot["assets"]
    ]
    return {"meta": _meta(snapshot), "items": items, "images": images}


def _meta(snapshot: dict) -> dict:
    meta = snapshot["meta"]
    schedule = meta.get("schedule")
    return {
        "project": meta.get("project") or "",
        "snapshot": meta.get("scan_started_at") or "",
        "exported_by": meta.get("exported_by") or "",
        "addon_version": meta.get("addon_version") or "",
        # Blender's interface language: the page's, unless chosen in it.
        "lang": meta.get("lang") or "",
        "roles": [r["name"] for r in meta.get("validation_roles") or []],
        "role": meta.get("validation_role"),
        "weights": meta.get("progress_weights") or {},
        "progress": meta.get("progress") or {},
        "validation": meta.get("validation") or {},
        # One point a day (progress_log.py): Breakdown's Over time.
        "history": meta.get("history") or {},
        "naming": meta.get("naming") or {},
        "team": meta.get("team") or [],
        "departments": {
            "shot": meta.get("shot_departments") or [],
            "asset": meta.get("asset_departments") or [],
        },
        "schedule": {
            k: schedule[k]
            for k in ("start", "end", "expected", "elapsed_days", "total_days", "at")
        }
        if schedule
        else None,
        "format": REVIEW_JSON_FORMAT,
        "schema_version": SCHEMA_VERSION,
        # A downloaded review's name starts with it (page.js reviewName()).
        "review_base": snapshot_filename(snapshot, "json", "review").split("_review_")[0],
        # The videos zipped next to the snapshot ({"zip", "sequences",
        # "assets"}), set by the export; None: no zip.
        "videos": meta.get("videos"),
        # Its videos' frame rate: the player's frame number (page.js).
        "fps": meta.get("fps"),
        # Served by Blender (lib/monitoring/live.py): {"token", "version"}; None, a file.
        "live": meta.get("live"),
        # Live: where the thumbnails are asked for (thumb/<token>), none inline.
        **({"thumbs": meta["thumbs"]} if meta.get("thumbs") else {}),
        # Live: who has which file open (the Farm tab's machines); a first read
        # under way, {"done", "total"} folders: the figures still partial.
        **({"presence": meta["presence"]} if meta.get("presence") else {}),
        **({"reading": meta["reading"]} if meta.get("reading") else {}),
    }


def _item(item: dict, threads: list, roles: list, image) -> dict:
    shots = [t[0] for t in item.get("shot_thumbnails") or []]
    if not shots and item["kind"] == "shot" and "-" in item["name"]:
        shots = _owner_shots(Path(item["name"].split("_", 1)[-1]))
    return {
        **({"live": item["live"]} if item.get("live") else {}),
        "name": item["name"],
        "kind": item["kind"],
        "root": item.get("root") or ("shots" if item["kind"] == "shot" else "assets"),
        "group": item["group"],
        "desc": item["description"] or "",
        # What a review row names and checks (page.js exportRows()).
        "file": _stem(item["current_version"]) or item["name"],
        "stable": _stem(item["stable_version"]) or "",
        "render_ref": _render_ref(item.get("renders") or []),
        # The Render form's start: its last render's department, each department's last preset.
        "rp": item.get("render_presets") or {},
        # ...the furthest department worked or done first (status.py furthest_department()).
        **({"rdept": item["render_department"]} if item.get("render_department") else {}),
        "versions": _versions(item),
        "stable_v": _short_version(item["name"], item["stable_version"] or ""),
        "stable_at": item.get("stable_at") or "",
        # The wip's, when newer than the stable: a state's capsule (page.js).
        "wip_v": _short_version(item["name"], item["wip_version"])
        if item.get("wip_version") and item.get("wip_after_stable", True)
        else "",
        "states": dict(item["departments"]),
        # Waiting / To redo with their reasons (lib/monitoring/status.py stage_flags()).
        "flags": item.get("flags") or {},
        # Its own render after its latest session (1) or before (0), with when it started.
        "rf": {d: [1 if r["fresh"] else 0, r["at"]] for d, r in (item.get("render_fresh") or {}).items()},
        "assignees": item.get("assignees") or {},
        "omit": item.get("omit"),
        "scores": dict(item["scores"]),
        "rtk": _rtk_kinds(threads),
        "ok": {
            d: mark
            for d in item["departments"]
            if (mark := _approval(item, d, roles)) is not None
        },
        "done": item["progress"],
        "valid": item.get("validation"),
        # Its departments the top role validated at the stable shown: the
        # Breakdown's validated share (it.ok is the highest mark, any role).
        "validated": sorted(d for d, v in (item.get("validated") or {}).items() if v),
        "shots": shots,
        "thumb": image(item.get("thumbnail")),
        "shot_thumbs": [
            [label, image(b64)] for label, b64 in item.get("shot_thumbnails") or []
        ],
        "renders": _render_lines(item),
        "outdated": bool(item.get("render_behind")),
        "to_check": bool(item.get("to_check")),
        "farm": _farm_summary(item.get("farm") or []),
        "notes": [_thread(t) for t in sorted(threads, key=lambda t: time_key(t["last_activity"]), reverse=True)],
        # Seconds: shown small at the panel's bottom (page.js dur()).
        "work": round(item["work_seconds"]) if item.get("work_seconds") else 0,
        # In the edit (editing/rushes/): which render, pushed by whom, when.
        "rush": item.get("rush") or None,
        # The History tab's (a snapshot's; the live page asks for it).
        **({"hist": item["history"]} if item.get("history") else {}),
        # Its latest version's last save: by whom, when.
        "saved": {"by": item.get("saved_by") or "", "at": item.get("saved_at") or ""},
    }


def _versions(item: dict) -> str:
    """ "wip v004 · stable v003": the wip only when newer than the stable."""
    wip = item["wip_version"] if item.get("wip_after_stable", True) else None
    return " · ".join(
        label + _short_version(item["name"], v)
        for label, v in (("wip ", wip), ("stable ", item["stable_version"]))
        if v
    )


def _short_version(name: str, filename: str) -> str:
    """ "ch_bob_v004-stable.blend" -> "v004" (the stable label says the rest)."""
    stem = filename.removesuffix(".blend")
    stem = stem[len(name) + 1 :] if stem.startswith(name + "_") else stem
    return stem.split("-", 1)[0]


def _rtk_kinds(threads: list) -> dict:
    """{department: who} for every department with an open RTK: the
    validation roles that gave one ("prod", "prod, sup": red), else "team"
    when all are the team's own (orange)."""
    roles: dict[str, list] = {}
    for t in threads:
        if t["closed"]:
            continue
        for e in [t, *t["replies"]]:
            if e["type"] != "rtk" or e["done"] is not False:
                continue
            for d in e["departments"]:
                got = roles.setdefault(d, [])
                if e.get("role") and e["role"] not in got:
                    got.append(e["role"])
    return {d: ", ".join(got) or "team" for d, got in roles.items()}


def _day(iso: str) -> str:
    at = parse_iso(iso)
    return f"{at:%d/%m/%Y}" if at else iso


def _approval(item: dict, department: str, roles: list) -> dict | None:
    """A department's validation as the page shows it: its highest role at
    the stable shown (each role's say in the tip), else the last one given
    to an earlier stable ("old": to review again). None without either."""
    approvals = item["approvals"].get(department) or {}
    levels = {r["name"]: r["level"] for r in roles}
    known = sorted((levels[r], r) for r in approvals if r in levels)
    if known:
        lines = []
        for role in roles:
            cover = covering_role(approvals, role["name"], roles)
            info = approvals.get(cover) or {}
            if cover == role["name"]:
                since = info.get("carried_from")
                on = f" on {_short_version(item['name'], Path(since).name)}" if since else ""
                lines.append(
                    f"{role['name']}: validated by {info.get('by', '?')}{on} ({_day(info.get('at') or '')})"
                    + (", not worked since" if since else "")
                )
            elif cover:
                lines.append(f"{role['name']}: covered by {cover}")
            else:
                lines.append(f"{role['name']}: not validated")
        top = known[-1][1]
        return {"role": top, "by": (approvals.get(top) or {}).get("by", ""), "tip": "\n".join(lines), "old": False, "seen": ""}
    previous = item["approvals_previous"].get(department) or {}
    old = sorted((levels[r], r) for r in previous if r in levels)
    if old:
        role = old[-1][1]
        seen = _short_version(item["name"], Path(previous[role].get("file") or "").name)
        return {
            "role": role,
            "by": previous[role].get("by", ""),
            "tip": f"Validated by {role} on {seen}: a newer stable since, to review again",
            "old": True,
            "seen": seen,
        }
    return None


_FARM_TEXT = {"waiting": "queued", "failed": "failed"}


def _farm_status(job: dict) -> dict:
    """A job still in the farm: "queued" whatever it waits for, its step
    ("rendering 45/120", "compiling the video"...), "failed" -- the exact step in the tip;
    which render (its folder once set up, v003_001, else its .blend's version) and shot."""
    return {
        "state": job["state"],
        "text": _FARM_TEXT.get(job["state"], job["text"]),
        "tip": job["text"],
        "version": job.get("version") or "",
        "shot": job.get("shot") or "",
    }


def _farm_summary(jobs: list) -> dict | None:
    """One line for the list: a failed job first, else a running one, else
    queued. None out of the farm."""
    if not jobs:
        return None
    order = {"failed": 0, "waiting": 2}
    job = min(jobs, key=lambda j: order.get(j["state"], 1))
    return _farm_status(job)


_TO_CHECK = {"state": "check", "text": "to check", "tip": "Rendered, not checked by the team yet"}


def _render_lines(item: dict) -> list:
    """ "Last render": one line per video (a block's shots rendered apart:
    one per shot, the same folder name or not) -- {"shots" (a block's
    label, "" for all), "shot_list", "folder" ("" not rendered), "video"
    (its path under renders/, None without one), "whole", "behind" (from
    an older .blend than the last stable), "status" (to check, or the
    farm's)}; then the farm's jobs for what has no line yet."""
    renders = item.get("renders") or []
    to_check = list(item.get("to_check") or [])
    lines = []
    if any(r["folder"] for r in renders):
        block = len(renders) > 1
        every = [r["shot"] for r in renders]
        # Its video tells a render apart; its folder name when it has none.
        keyed = [dict(r, line=r.get("video") or r["folder"]) for r in renders]
        for shots, r in group_renders(keyed, key="line"):
            labels = (
                {r["folder"] if r.get("whole") or not block else f"{s} {r['folder']}" for s in shots}
                if r["folder"]
                else set()
            )
            line = {
                "shots": shots_label(shots, every) if block else "",
                "shot_list": shots,
                "folder": r["folder"] or "",
                "video": r.get("video"),
                # Its video's first frame, the .blend's own number: the
                # player counts from it (None: unknown, counted from 1).
                "first": (r.get("frames") or [None])[0],
                "whole": bool(r.get("whole")),
                "department": r.get("department") or "",
                "others": r.get("others") or [],
                "behind": r["folder"] is not None
                and r["file_number"] is not None
                and r["file_number"] < item["stable_number"],
                "status": _TO_CHECK if labels & set(to_check) else None,
                "_labels": labels,
            }
            to_check = [label for label in to_check if label not in labels]
            lines.append(line)
    for job in item.get("farm") or []:
        label = f"{job['shot']} {job['version']}".strip()
        line = next((ln for ln in lines if label in ln["_labels"] and not ln["status"]), None)
        if line is None:
            # A first render of that shot: it takes its "not rendered" line.
            line = next(
                (ln for ln in lines if not ln["folder"] and job["shot"] in ln["shot_list"]),
                None,
            )
        if line is None:
            line = {
                "shots": job["shot"],
                "shot_list": [job["shot"]] if job["shot"] else [],
                "folder": "",
                "video": None,
                "first": None,
                "whole": False,
                "behind": False,
                "status": None,
                "_labels": {label},
            }
            lines.append(line)
        line["status"] = _farm_status(job)
        if not line["folder"]:
            line["pending"] = job["version"]
    for line in lines:
        del line["_labels"]
    return lines


def _thread(t: dict) -> dict:
    """A thread as page.js reads it: its root's fields, its replies'."""
    return {**_entry(t), "closed": t["closed"], "replies": [_entry(r) for r in t["replies"]]}


def _entry(e: dict) -> dict:
    return {
        "id": e.get("id") or "",
        "type": e["type"],
        "done": e["done"],
        # An RTK red from a validation role, orange from the team.
        "team": e["type"] == "rtk" and not e.get("role"),
        "role": e.get("role") or "",
        "text": e["text"],
        "author": e["author"],
        "date": e["date"],
        "deps": list(e["departments"]),
        "shot": e.get("shot") or "",
        "frames": e.get("frames") or "",
        "render": e.get("render") or "",
        "version": e.get("version") or "",
        "review": bool(e.get("from_review")),
        # A validation's own note, for the record: not a note to read.
        "approval": bool(e.get("approval")),
        "rid": e.get("review_id") or "",
    }
