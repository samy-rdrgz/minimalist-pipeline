"""The production snapshot's page: build_snapshot()'s dict as one offline
HTML file. Python only shapes the data (page_data()); the page itself --
templates/snapshot/: page.html, page.css, page.js, the logo and the
wordmark's font -- draws it in the browser. Pure: thread-safe."""

import base64
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .config import covering_role
from .snapshot import (
    REVIEW_JSON_FORMAT,
    SCHEMA_VERSION,
    _owner_shots,
    _render_ref,
    _stem,
    group_renders,
    render_review_xlsx,
    shots_label,
    snapshot_filename,
)

PAGE_DIR = Path(__file__).resolve().parent.parent / "templates" / "snapshot"

_PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
_VIEWBOX = re.compile(r'viewBox="([^"]+)"')
_PATH = re.compile(r'<path[^>]*\sd="([^"]+)"')


def render_html(snapshot: dict) -> str:
    """The whole snapshot as one offline HTML page: page.html with the
    stylesheet, the script, the logo, the wordmark's font, the review
    spreadsheet and page_data() put in, in one pass (a value is never
    read again for placeholders)."""
    logo = (PAGE_DIR / "logo.svg").read_text(encoding="utf-8")
    viewbox = _VIEWBOX.search(logo)[1]
    width, height = viewbox.split()[2:]
    data = json.dumps(page_data(snapshot), ensure_ascii=False, separators=(",", ":"))
    values = {
        "TITLE": _escape(f"{snapshot['meta'].get('project') or 'Project'} snapshot"),
        "CSS": (PAGE_DIR / "page.css").read_text(encoding="utf-8"),
        "JS": (PAGE_DIR / "page.js").read_text(encoding="utf-8"),
        "FONT": base64.b64encode((PAGE_DIR / "wordmark.ttf").read_bytes()).decode("ascii"),
        "LOGO_VB": viewbox,
        # The <use> of a symbol draws it from 0 0: its box, not the source's.
        "LOGO_VB0": f"0 0 {width} {height}",
        "LOGO_PATH": _PATH.search(logo)[1],
        "XLSX": base64.b64encode(render_review_xlsx(snapshot)).decode("ascii"),
        "XLSX_NAME": _escape(snapshot_filename(snapshot, "xlsx", "review")),
        # Inside <script>: no "</" may close it early.
        "DATA": data.replace("</", "<\\/"),
    }
    shell = (PAGE_DIR / "page.html").read_text(encoding="utf-8")
    return _PLACEHOLDER.sub(lambda m: values[m[1]], shell)


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def page_data(snapshot: dict) -> dict:
    """What page.js draws: {"meta", "items", "images"}. images: each
    thumbnail once, by the hash of its bytes -- a block's thumbnail is also
    its first shot's."""
    meta = snapshot["meta"]
    roles = meta.get("validation_roles") or []
    images: dict[str, str] = {}

    def image(b64: str | None) -> str | None:
        if not b64:
            return None
        key = hashlib.sha1(b64.encode("ascii")).hexdigest()[:12]
        images.setdefault(key, b64)
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
        "roles": [r["name"] for r in meta.get("validation_roles") or []],
        "role": meta.get("validation_role"),
        "weights": meta.get("progress_weights") or {},
        "progress": meta.get("progress") or {},
        "validation": meta.get("validation") or {},
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
    }


def _item(item: dict, threads: list, roles: list, image) -> dict:
    shots = [t[0] for t in item.get("shot_thumbnails") or []]
    if not shots and item["kind"] == "shot" and "-" in item["name"]:
        shots = _owner_shots(Path(item["name"].split("_", 1)[-1]))
    return {
        "name": item["name"],
        "kind": item["kind"],
        "root": item.get("root") or ("shots" if item["kind"] == "shot" else "assets"),
        "group": item["group"],
        "desc": item["description"] or "",
        # What a review row names and checks (page.js exportRows()).
        "file": _stem(item["current_version"]) or item["name"],
        "stable": _stem(item["stable_version"]) or "",
        "render_ref": _render_ref(item.get("renders") or []),
        "versions": _versions(item),
        "stable_v": _short_version(item["name"], item["stable_version"] or ""),
        "states": dict(item["departments"]),
        "scores": dict(item["scores"]),
        "rtk": _rtk_kinds(threads),
        "ok": {
            d: mark
            for d in item["departments"]
            if (mark := _approval(item, d, roles)) is not None
        },
        "done": item["progress"],
        "valid": item.get("validation"),
        "shots": shots,
        "thumb": image(item.get("thumbnail")),
        "shot_thumbs": [
            [label, image(b64)] for label, b64 in item.get("shot_thumbnails") or []
        ],
        "renders": _render_lines(item),
        "outdated": bool(item.get("render_behind")),
        "to_check": bool(item.get("to_check")),
        "farm": _farm_summary(item.get("farm") or []),
        "notes": [_thread(t) for t in sorted(threads, key=lambda t: t["last_activity"], reverse=True)],
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
    """{department: "role" | "team"} for every department with an open RTK
    -- "role" as soon as one comes from a validation role (red), "team"
    when all are the team's own (orange)."""
    out: dict[str, str] = {}
    for t in threads:
        if t["closed"]:
            continue
        for e in [t, *t["replies"]]:
            if e["type"] != "rtk" or e["done"] is not False:
                continue
            for d in e["departments"]:
                out[d] = "role" if e.get("role") or out.get(d) == "role" else "team"
    return out


def _day(iso: str) -> str:
    try:
        return f"{datetime.fromisoformat(iso):%d/%m/%Y}"
    except ValueError:
        return iso


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
                lines.append(
                    f"{role['name']}: validated by {info.get('by', '?')} ({_day(info.get('at') or '')})"
                )
            elif cover:
                lines.append(f"{role['name']}: covered by {cover}")
            else:
                lines.append(f"{role['name']}: not validated")
        return {"role": known[-1][1], "tip": "\n".join(lines), "old": False, "seen": ""}
    previous = item["approvals_previous"].get(department) or {}
    old = sorted((levels[r], r) for r in previous if r in levels)
    if old:
        role = old[-1][1]
        seen = _short_version(item["name"], Path(previous[role].get("file") or "").name)
        return {
            "role": role,
            "tip": f"Validated by {role} on {seen}: a newer stable since, to review again",
            "old": True,
            "seen": seen,
        }
    return None


_FARM_TEXT = {"waiting": "queued", "failed": "failed"}


def _farm_status(job: dict) -> dict:
    """A job still in the farm: "queued" whatever it waits for, its step
    ("rendering 45/120", "compiling"...), "failed" -- the exact step in the tip."""
    return {
        "state": job["state"],
        "text": _FARM_TEXT.get(job["state"], job["text"]),
        "tip": job["text"],
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
                "whole": bool(r.get("whole")),
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
    }
