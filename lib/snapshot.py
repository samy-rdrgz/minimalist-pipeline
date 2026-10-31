"""Production snapshot: one self-contained HTML page of the project's state
for people outside the studio, with a review spreadsheet embedded in it that
they fill in and send back (see NOTES.md, "Production snapshot")."""

import base64
import os
import re
import threading
from datetime import datetime
from pathlib import Path

from .background import background_work
from .config import (
    covering_role,
    validation_roles,
)
from .core import json_get, now, read_json_quiet
from .preview import _first_mp4, latest_render_dir, render_root
from .schedule import project_schedule, schedule_progress
from .thumbnails import (
    owner_shot_render_dirs,
    owner_thumbnail_dirs,
    run_thumbnail_jobs,
    thumbnail_jobs,
    thumbnail_path,
    thumbnail_size,
)
from .tracking import (
    APPROVAL_SOURCE,
    _DATA_ROOTS,
    _collect_folder,
    _pipeline_entries,
    _status_from_raw,
    _walk_owner_dirs,
    entry_departments,
    owner_key,
    render_to_check_label,
)

# Bumped whenever the review template's columns change -- the import refuses
# a template made by a newer addon.
SCHEMA_VERSION = 5  # 2: hidden description_exported column; 3: role, "valid <dept>"; 4: a sheet per section, a cell per department; 5: the render watched

ENTRY_TYPES = ("note", "todo", "rtk")

# Share of a department counted as done per state, in % -- the project's
# "snapshot.progress" (Edit project) overrides each. Validated counts 100,
# not started 0. "rtk": validated, with an open RTK.
PROGRESS_WEIGHTS = {"wip": 33, "rework": 67, "rtk": 67}

# Entry "source" stamped on every note imported from a review template.
REVIEW_SOURCE = "prod_review"

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------


def read_snapshot_raw(root: Path) -> list[tuple[str, Path, dict, list[str]]]:
    """(kind, owner folder, _collect_folder() data, .blend names) for every
    tracked folder. Disk only, pure os/json: thread-safe."""
    out = []
    for top in _DATA_ROOTS:
        kind = "shot" if top == "shots" else "asset"
        for owner in _walk_owner_dirs(root / top):
            raw = _collect_folder(owner, _pipeline_entries(owner))
            if raw is None:
                continue
            try:
                blends = [
                    e.name for e in os.scandir(owner) if e.name.endswith(".blend")
                ]
            except OSError:
                blends = []
            out.append((kind, owner, raw, blends))
    return out


def _owner_shots(owner: Path) -> list[str]:
    """A shot folder's shots: ["sh040"], or ["sh040", "sh050", "sh060"] for
    a block "sh040-050-060". Name parsing only, no config."""
    first, *rest = owner.name.split("-")
    m = re.match(r"(\D*)(\d+)$", first)
    if not m:
        return [owner.name]
    return [first] + [f"{m[1]}{n.zfill(len(m[2]))}" for n in rest]


def read_render_state(root: Path, kind: str, owner: Path, v_prefix: str = "v") -> list:
    """What was last rendered for an asset/shot folder, per shot (a block
    has several, anything else one): [{"shot", "file", "folder", "path",
    "frame_machines", "machine_seconds"}] (the last two None without them),
    path the render folder's absolute path. From the
    folder's render_history.json -- its last finished render of that shot,
    file = the .blend it rendered -- else (no such entry, or an entry from
    before source_file came after it) from the latest render folder's own
    name (renders/<seq>/<shot>/v004-stable_002). Pure os/json: thread-safe."""
    history = read_json_quiet(owner / ".pipeline" / "render_history.json") or {}
    finished = [
        e
        for e in history.get("entries", [])
        if isinstance(e, dict) and e.get("status") == "finished"
    ]
    base = render_root(root, owner)
    shots = _owner_shots(owner) if kind == "shot" else [""]
    block = len(shots) > 1

    def last_render(shot: str, mine: list, folder_dir: Path) -> dict:
        # An older version's entry (no source_file, no shot_override) after
        # it may be a newer render of this shot: the folder name knows.
        if mine and all(e.get("source_file") for e in finished[mine[-1] + 1 :]):
            last = finished[mine[-1]]
            output = last.get("output_path")
            folder = (Path(root) / output).parent if output else None
            return {
                "shot": shot,
                "file": Path(last["source_file"]).name,
                "folder": folder.name if folder else None,
                "path": str(folder) if folder else None,
                # Which machine wrote each frame, and their pace
                # (farm queue._note_frames()): File details' lookup.
                "frame_machines": last.get("frame_machines"),
                "machine_seconds": last.get("machine_seconds"),
            }
        latest = latest_render_dir(folder_dir, v_prefix)
        return {
            "shot": shot,
            "file": None,
            "folder": latest.name if latest else None,
            "path": str(latest) if latest else None,
        }

    out = []
    for shot in shots:
        # A block's history holds every shot it rendered, told apart by
        # shot_override; a mono shot's or an asset's is all its own.
        mine = [
            i
            for i, e in enumerate(finished)
            if e.get("source_file") and (not block or e.get("shot_override") == shot)
        ]
        out.append(last_render(shot, mine, base.with_name(shot) if shot else base))
    if block:
        # The block rendered whole (no split per shot: renders/<seq>/
        # sh030-040/...): each shot's last render is the newer of its own
        # and that one ("whole": the to-check label is the folder alone).
        mine = [
            i
            for i, e in enumerate(finished)
            if e.get("source_file") and not e.get("shot_override")
        ]
        whole = last_render("", mine, base)
        if whole["path"]:
            out = [
                dict(whole, shot=r["shot"], whole=True)
                if _render_order(whole["folder"]) > _render_order(r["folder"])
                else r
                for r in out
            ]
    return out


_RENDER_FOLDER = re.compile(r"(\d+)(?:-[a-z]+)?_(\d+)$")


def _render_order(folder: str | None) -> tuple[int, int]:
    """A render folder's (version, increment) -- v004-stable_002 -> (4, 2);
    (-1, -1) for none."""
    m = _RENDER_FOLDER.search(folder or "")
    return (int(m[1]), int(m[2])) if m else (-1, -1)


def group_renders(renders: list, key: str = "folder") -> list[tuple[list, dict]]:
    """A folder's last renders (read_render_state()) grouped by render:
    [(its shots, the render)], in the block's order -- five shots of one
    render are one line, not five. key "folder": the same folder name is
    the same render (a split render writes one per shot -- the snapshot);
    "path": the very same folder (File details, whose buttons open it)."""
    groups: dict = {}
    for r in renders:
        groups.setdefault((r.get(key), bool(r.get("whole"))), (r, []))[1].append(
            r["shot"]
        )
    return [(shots, r) for r, shots in groups.values()]


def snapshot_videos(
    snapshot: dict, root: Path, sequences: list[str], assets: bool
) -> tuple[list[tuple[Path, str]], list[str]]:
    """The videos of the last renders the snapshot shows -- its shots' of
    these sequences, and with assets every asset/library's --, as
    [(mp4, its path under renders/)], each once: what Export snapshot
    copies or zips, under those names, and what the page plays. Also the
    sequences (and "assets/libraries") with none. No disk access."""
    renders = Path(root) / "renders"
    out, seen, found = [], set(), set()
    for item in snapshot["shots"] + snapshot["assets"]:
        shot = item["kind"] == "shot"
        if not (item["group"] in sequences if shot else assets):
            continue
        for r in item.get("renders") or []:
            name = r.get("video")
            if name and name not in seen:
                seen.add(name)
                out.append((renders / name, name))
                found.add(item["group"] if shot else "assets/libraries")
    wanted = list(sequences) + (["assets/libraries"] if assets else [])
    return out, [w for w in wanted if w not in found]


def _render_ref(renders: list, per_shot: bool = False) -> str:
    """The last render a review row was made on, as its "render" field:
    "v007-stable_001", or per shot when a block's differ (or per_shot) --
    "sh110=v007-stable_001 sh120=v006_002". "" if never rendered."""
    done = [r for r in renders if r.get("folder")]
    if len({r["folder"] for r in done}) == 1 and not per_shot:
        return done[0]["folder"]
    return " ".join(f"{r['shot']}={r['folder']}" for r in done)


def render_of_note(render: str, shot: str | None) -> str | None:
    """The render folder a review note is about, from its row's "render"
    (_render_ref()): its shot's ("110" matches "sh110"), else the row's
    one render; a note on the whole block, the newest of its shots'. None
    for a shot of a block with no render of its own there (never
    rendered, or rendered again after the snapshot), or without any (a
    review from before schema 5)."""
    default, per_shot = None, {}
    for token in (render or "").split():
        label, _, folder = token.rpartition("=")
        if label:
            digits = re.sub(r"\D", "", label)
            per_shot[int(digits) if digits else label] = folder
        else:
            default = folder
    if default:
        return default
    if shot is not None:
        return per_shot.get(int(shot)) if shot.isdigit() else None
    return max(per_shot.values(), key=_render_order, default=None)


def shots_label(shots: list, every: list) -> str:
    """ "sh020-030-040", as a block's name -- "" when that's every shot."""
    if len(shots) == len(every) and len(every) > 1:
        return ""
    first, *rest = shots
    prefix = first.rstrip("0123456789")
    return "-".join(
        [first, *(s[len(prefix) :] if s.startswith(prefix) else s for s in rest)]
    )


def read_snapshot_data(
    root: Path, thumbnails: dict | None = None, v_prefix: str = "v"
) -> dict:
    """read_snapshot_raw() plus each folder's last render
    (read_render_state()) and thumbnails: those missing or older than
    their latest render are remade first (one headless Blender, waited on
    -- run this on a thread). thumbnails: {"size", "blender", "ffmpeg"},
    None to skip them. Returns {"raws", "renders": {owner:
    [... + "video", its mp4 under renders/ or None]}, "thumbs": {owner: base64 JPEG}, "shot_thumbs": {block owner:
    [(shot label, base64 JPEG or None)]}, "thumb_warnings": [...]}."""
    raws = read_snapshot_raw(root)
    renders = {
        str(owner): read_render_state(root, kind, owner, v_prefix)
        for kind, owner, raw, _ in raws
        if not raw["tracking"].get("archived")
    }
    # Each render's video, by its path under renders/: what the snapshot's
    # videos folder or zip holds, and what the page plays for that render.
    for shots in renders.values():
        for r in shots:
            mp4 = _first_mp4(Path(r["path"])) if r.get("path") else None
            try:
                r["video"] = mp4.relative_to(Path(root) / "renders").as_posix()
            except (AttributeError, ValueError):
                r["video"] = None
    thumbs, shot_thumbs, warnings = {}, {}, []
    if thumbnails is not None:
        dirs, shot_dirs = {}, {}
        for _, owner, raw, _ in raws:
            if not raw["tracking"].get("archived"):
                dirs[str(owner)] = owner_thumbnail_dirs(root, owner)
                # A block: every shot's own, to find one's way in the edit.
                if shots := owner_shot_render_dirs(root, owner):
                    shot_dirs[str(owner)] = shots
        size = thumbnails.get("size") or thumbnail_size({})
        every = dict.fromkeys(
            [
                *(d for candidates in dirs.values() for d in candidates),
                *(d for shots in shot_dirs.values() for _, d in shots),
            ]
        )
        jobs = thumbnail_jobs(every, v_prefix, size=size)
        results = run_thumbnail_jobs(
            jobs, thumbnails["blender"], thumbnails.get("ffmpeg"), size=size
        )
        warnings = [
            f"{Path(dst).name}: {why}" for dst, why in results.items() if why != "ok"
        ]

        def encoded(d: Path) -> str | None:
            try:  # an older thumbnail still beats none
                return base64.b64encode(thumbnail_path(d).read_bytes()).decode("ascii")
            except OSError:
                return None

        for owner, candidates in dirs.items():
            b64 = next((b for d in candidates if (b := encoded(d)) is not None), None)
            if b64 is not None:
                thumbs[owner] = b64
        for owner, shots in shot_dirs.items():
            found = [(label, encoded(d)) for label, d in shots]
            if any(b64 for _, b64 in found):
                shot_thumbs[owner] = found
    return {
        "raws": raws,
        "renders": renders,
        "thumbs": thumbs,
        "shot_thumbs": shot_thumbs,
        "thumb_warnings": warnings,
    }


def build_snapshot(data, config: dict, meta: dict, farm: dict | None = None) -> dict:
    """Neutral snapshot dict from read_snapshot_data()'s result (or a bare
    read_snapshot_raw() list): {"meta", "assets", "shots", "notes"}. farm:
    the farm's jobs still to go by folder (farm_activity()). Memory only,
    main thread (_status_from_raw() reads ConfigCache)."""
    if isinstance(data, list):
        data = {"raws": data, "thumbs": {}, "thumb_warnings": []}
    raws = data["raws"]
    weights = progress_weights(config)
    roles = validation_roles(config)
    top_role = top_validation_role(roles)
    v_prefix = json_get(config, "naming.version.prefix", "v")
    version_re = re.compile(rf"_{re.escape(v_prefix)}(\d+)(-[a-z]+)?\.blend$")
    folder_re = re.compile(rf"^{re.escape(v_prefix)}(\d+)(-[a-z]+)?_\d+$")
    items = {"asset": [], "shot": []}
    notes = []
    for kind, owner, raw, blends in raws:
        status = _status_from_raw(raw)
        if status.get("archived"):
            continue
        name = status.get("file_name") or owner.name
        wips = [
            (int(m[1]), b) for b in blends if (m := version_re.search(b)) and not m[2]
        ]
        stable_file = (status.get("stable_info") or {}).get("file")
        stable_name = Path(stable_file).name if stable_file else None
        stable_m = version_re.search(stable_name or "")
        stable_n = int(stable_m[1]) if stable_m else -1
        wip_n, wip_name = max(wips) if wips else (-1, None)
        item = {
            "name": name,
            "kind": kind,
            "group": name.split("_", 1)[0],
            # assets/, library/ or shots/: the page's tab, the videos zip's folder.
            "root": next((p for p in reversed(owner.parts) if p in _DATA_ROOTS), kind),
            "description": status.get("description", ""),
            "departments_required": list(status.get("departments_required", [])),
            "departments": {
                d: _department_state(status, d)
                for d in status.get("departments_required", [])
            },
            "wip_version": wip_name,
            # Work on top of the last stable (a wip made after it), else none
            # to show: the Blender file column names the stable alone.
            "wip_after_stable": wip_n > stable_n,
            "stable_version": stable_name,
            # What the prod sees and what its notes get anchored on: the
            # most recent of the two (a stable can be newer than any wip).
            "current_version": wip_name
            if wip_n > stable_n
            else stable_name or wip_name,
            "thumbnail": data["thumbs"].get(str(owner)),
            # A block's shots, each its own thumbnail (None: not rendered).
            "shot_thumbnails": [
                list(t) for t in data.get("shot_thumbs", {}).get(str(owner), [])
            ],
        }
        # A render's folder is vXXX_YYY: XXX the .blend version rendered,
        # YYY the render increment. The history's source_file says XXX
        # first-hand; the folder name is the fallback.
        renders = []
        for r in data.get("renders", {}).get(str(owner), []):
            m = version_re.search(r["file"] or "") or folder_re.match(r["folder"] or "")
            renders.append(
                {
                    "shot": r["shot"],
                    "folder": r["folder"],
                    "whole": bool(r.get("whole")),
                    "file_number": int(m[1]) if m else None,
                    "video": r.get("video"),
                }
            )
        item["renders"] = renders
        # Rendered, not checked by the team yet / still in the farm.
        to_check = status.get("to_check")
        if not isinstance(to_check, dict):
            to_check = {}
        item["to_check"] = [
            render_to_check_label(shot, info)
            for shot, info in sorted(to_check.items())
            if isinstance(info, dict)
        ]
        item["farm"] = (farm or {}).get(owner_key(owner), [])
        # What the prod must see: a render made from an older .blend than
        # the last stable -- the picture lags the validated work.
        item["stable_number"] = stable_n
        item["render_behind"] = stable_n >= 0 and any(
            r["file_number"] is not None and r["file_number"] < stable_n
            for r in renders
        )
        # Every thread: the snapshot is a record. Closed ones are only
        # hidden by the page (_JS, "Show closed").
        threads = [
            _thread_dict(name, t, closed=_thread_closed(t))
            for box in status.get("entries_grouped", [])
            for t in box["threads"]
        ]
        open_threads = [t for t in threads if not t["closed"]]
        item["open_rtk"] = sum(
            1
            for t in open_threads
            for e in [t, *t["replies"]]
            if e["type"] == "rtk" and e["done"] is False
        )
        item["open_notes"] = len(open_threads)
        open_rtks = [
            e
            for t in open_threads
            for e in [t, *t["replies"]]
            if e["type"] == "rtk" and e["done"] is False
        ]
        rtk_departments = {d for e in open_rtks for d in e["departments"]}
        item["rtk_departments"] = sorted(rtk_departments)
        # On no department (a general retake): the "n RTK" flag by the name
        # is red-outlined; it weighs on Done as one department's RTK would
        # (_progress()), never on each department's.
        item["general_rtk"] = any(not e["departments"] for e in open_rtks)
        # Per done department: its validations at the stable shown, and the
        # last ones given to an earlier stable (to review again).
        item["approvals"] = {
            d: {r: dict(info) for r, info in roles.items()}
            for d, roles in (status.get("approvals") or {}).items()
        }
        item["approvals_previous"] = {
            d: {r: dict(info) for r, info in roles.items()}
            for d, roles in (status.get("approvals_previous") or {}).items()
            if d in item["departments"]
        }
        # Per department, then their mean: the footer averages the first.
        item["scores"] = {
            d: _department_score(st, d in rtk_departments, weights)
            for d, st in item["departments"].items()
        }
        item["progress"] = _progress(item, weights)
        # Apart from Done: the share of the required departments the top
        # role (or an equivalent one) validated at the stable shown.
        item["validated"] = {
            d: bool(
                top_role
                and covering_role(item["approvals"].get(d) or {}, top_role, roles)
            )
            for d in item["departments"]
        }
        valid = list(item["validated"].values())
        item["validation"] = sum(valid) / len(valid) if valid else None
        items[kind].append(item)
        notes.extend(threads)

    for k in items:
        items[k].sort(key=lambda i: i["name"])
    notes.sort(key=lambda n: (n["item"], n["last_activity"]), reverse=False)
    meta = dict(meta)
    meta.setdefault("schema_version", SCHEMA_VERSION)
    meta["thumbnail_warnings"] = list(data["thumb_warnings"])
    meta["thumbnail_size"] = thumbnail_size(config)
    meta["progress"] = {k: average_progress(v) for k, v in items.items()}
    meta["progress_weights"] = weights
    meta["validation_roles"] = roles
    meta["validation_role"] = top_role
    meta["validation"] = {
        k: average_progress(v, "validation") for k, v in items.items()
    }
    schedule = project_schedule(config)
    if schedule:
        today = datetime.fromisoformat(meta.get("scan_started_at") or now()).date()
        meta["schedule"] = schedule_progress(schedule, today, meta["progress"])
    meta["asset_departments"] = _columns(
        json_get(config, "assets_departments", []), items["asset"]
    )
    meta["shot_departments"] = _columns(
        json_get(config, "shots_departments", []), items["shot"]
    )
    return {
        "meta": meta,
        "assets": items["asset"],
        "shots": items["shot"],
        "notes": notes,
    }


def _department_state(status: dict, department: str) -> str:
    """done / rework (validated at the latest stable, worked since or not),
    wip (worked since, or started before: validated at an earlier stable or
    worked before the latest one), todo (never)."""
    validated = department in status.get("validated_departments", {})
    worked = department in status.get("worked_departments", {})
    if validated:
        return "rework" if worked else "done"
    started = department in status.get("started_departments", ())
    return "wip" if worked or started else "todo"


def progress_weights(config: dict) -> dict[str, int]:
    """PROGRESS_WEIGHTS with the project's own values, each kept 0..100."""
    out = {}
    for key, default in PROGRESS_WEIGHTS.items():
        try:
            value = int(json_get(config, f"snapshot.progress.{key}", default))
        except (TypeError, ValueError):
            value = default
        out[key] = max(0, min(100, value))
    return out


def _rtk_on(item: dict, department: str) -> bool:
    """An open RTK on that department, or on none (a general retake)."""
    return department in item["rtk_departments"] or item.get("general_rtk", False)


def _progress(item: dict, weights: dict) -> float | None:
    """A file's Done: its departments' mean, a general retake counting as
    an RTK on one of them -- a done one with none of its own (none such:
    it changes nothing, like an RTK on a department not done)."""
    scores = item["scores"]
    if not scores:
        return None
    total = sum(scores.values())
    if item.get("general_rtk") and any(
        st == "done" and d not in item["rtk_departments"]
        for d, st in item["departments"].items()
    ):
        total -= 1 - weights["rtk"] / 100
    return total / len(scores)


def _department_score(state: str, open_rtk: bool, weights: dict) -> float:
    """One department's share done, 0..1: validated 1 (its "rtk" weight
    with an open RTK), not started 0, else its state's weight."""
    if state == "done":
        return weights["rtk"] / 100 if open_rtk else 1.0
    return weights.get(state, 0) / 100


def top_validation_role(roles: list) -> str | None:
    """The role the "Validated" figures count: the highest level's (its
    equivalents cover it). None without any role."""
    return max(roles, key=lambda r: r["level"])["name"] if roles else None


def department_progress(items: list, department: str) -> float | None:
    """Mean of one department over the items requiring it, None if none
    does -- the snapshot table's per-department footer."""
    values = [i["scores"][department] for i in items if department in i["scores"]]
    return sum(values) / len(values) if values else None


def average_progress(items: list, key: str = "progress") -> float | None:
    """Mean progress of items (key "validation": their Validated), each
    weighing the same; those without any required department left out.
    None if none is left."""
    values = [i[key] for i in items if i.get(key) is not None]
    return sum(values) / len(values) if values else None


def _columns(configured: list, items: list) -> list:
    """Config's department order, plus any department an item requires that
    the config no longer lists."""
    cols = list(configured)
    for item in items:
        for d in item["departments_required"]:
            if d not in cols:
                cols.append(d)
    return cols


def _entry_dict(e: dict) -> dict:
    """An entry as the snapshot page shows it: plain fields, its departments
    joined for the tag."""
    version = e.get("referenced_version")
    return {
        "type": e.get("type", "note"),
        "text": e.get("text", ""),
        "author": e.get("author", ""),
        "date": e.get("created_at", ""),
        "department": ", ".join(entry_departments(e)),
        "departments": entry_departments(e),
        "version": Path(version).name if version else "",
        # The render a review note was written on (v007-stable_001).
        "render": e.get("render", ""),
        "shot": e.get("shot", ""),
        "frames": _frames_label(e),
        "done": e.get("done"),
        "from_review": e.get("source") == REVIEW_SOURCE,
        # The validation role it was written under, "" the team's own.
        "role": e.get("role") or "",
        # Written by a validation, for the record: no note to read.
        "approval": e.get("source") == APPROVAL_SOURCE,
    }


def _frames_label(e: dict) -> str:
    """ "f12-40" / "f12" for an entry tied to frames, "" otherwise."""
    start, end = e.get("frame_start"), e.get("frame_end")
    if start is None:
        return ""
    return f"f{start}-{end}" if end is not None else f"f{start}"


def _thread_closed(thread: dict) -> bool:
    """Done root and no reply still pending: what filter_review_boxes()'s
    hide_done drops (see its docstring)."""
    return thread["root"].get("done") is True and not any(
        r.get("done") is False for r in thread["replies"]
    )


def _thread_dict(item_name: str, thread: dict, closed: bool = False) -> dict:
    """A thread (root + replies) as the snapshot page shows it, tagged with
    its item and whether it's closed."""
    return {
        "item": item_name,
        **_entry_dict(thread["root"]),
        "replies": [_entry_dict(r) for r in thread["replies"]],
        "last_activity": thread["meta"]["date_end"],
        "closed": closed,
    }


class SnapshotJob:
    """Run fn(*args) on a thread, polled from the main thread (done/result/
    error). The export runs two: the disk read, then render+write -- only
    build_snapshot() runs on the main thread, memory only."""

    def __init__(self, fn, *args):
        self.started_at = now()
        self.result = None
        self.error = None
        self.done = False
        self._thread = threading.Thread(
            target=self._run, args=(fn, args), daemon=True, name="pipeline-snapshot"
        )
        self._thread.start()

    def _run(self, fn, args) -> None:
        try:
            with background_work():
                self.result = fn(*args)
        except Exception as e:  # reported by the caller
            self.error = repr(e)
        self.done = True


def write_snapshot(snapshot: dict, filepath: Path) -> Path:
    """render_html() written to filepath. Pure: thread-safe."""
    Path(filepath).write_text(render_html(snapshot), encoding="utf-8")
    return Path(filepath)


def snapshot_filename(snapshot: dict, ext: str = "html", kind: str = "snapshot") -> str:
    """<project>_<kind>_<YYYY-MM-DD>_<HH-MM>.<ext>, from the scan's start --
    several exports a day never overwrite each other."""
    meta = snapshot["meta"]
    project = (
        re.sub(r"[^\w\-]+", "_", meta.get("project") or "").strip("_") or "project"
    )
    stamp = (
        (meta.get("scan_started_at") or now())[:16].replace("T", "_").replace(":", "-")
    )
    return f"{project}_{kind}_{stamp}.{ext}"


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def render_html(snapshot: dict) -> str:
    """The whole snapshot as one offline HTML page (lib/snapshot_page.py)."""
    from .snapshot_page import render_html as page  # it imports this module

    return page(snapshot)
