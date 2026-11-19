"""Production snapshot: one self-contained HTML page of the project's state
for people outside the studio, with a review they write on it and send back (see NOTES.md, "Production snapshot")."""

import base64
import os
import re
import threading
from pathlib import Path

from ..background import background_work
from ..config import (
    RELINK_TAGS,
    covering_role,
    validation_roles,
)
from ..core import (
    iso_timestamp,
    json_get,
    now,
    parse_iso,
    read_json_quiet,
    time_key,
)
from .status import (
    department_score,
    department_state,
    file_progress,
    omitted,
    progress_weights,
    project_stages,
)
from ..preview import LD_DIR, browser_video, ensure_ld, main_render_dir, render_root
from .schedule import project_schedule, schedule_progress
from ..thumbnails import (
    owner_shot_render_dirs,
    owner_thumbnail_dirs,
    run_thumbnail_jobs,
    thumbnail_jobs,
    thumbnail_path,
    thumbnail_size,
)
from .tracking import (
    _DATA_ROOTS,
    APPROVAL_SOURCE,
    _collect_folder,
    _current_link_files,
    _outdated_links_of,
    _path_key,
    _pipeline_entries,
    _session_folder_key,
    _status_from_raw,
    _walk_owner_dirs,
    entry_departments,
    owner_key,
    work_times,
    render_to_check_label,
    to_check_entries,
)

# Bumped whenever the review's columns change: the import reads this one
# only (review_import._check_schema()). History in NOTES.md, "Review import:
# this version's reviews only".
SCHEMA_VERSION = 8

# Entry "source" stamped on every note imported from a review template.
REVIEW_SOURCE = "prod_review"
# A review written as the team (its role "team", no validation role):
# team RTKs, never tagged "prod review".
TEAM_REVIEW_SOURCE = "team_review"
TEAM_ROLE = "team"


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
            raw["render_presets"] = _render_presets(owner)
            try:
                blends = [
                    e.name for e in os.scandir(owner) if e.name.endswith(".blend")
                ]
            except OSError:
                blends = []
            out.append((kind, owner, raw, blends))
    return out


def _render_presets(owner: Path) -> dict:
    """The Render form's start for this folder: {"department": its last
    render's, "by": {department: the preset its last render for it used}}
    (render_history.json, finished and failed renders). Pure os/json."""
    by, last = {}, ""
    for e in (read_json_quiet(owner / ".pipeline" / "render_history.json") or {}).get("entries") or []:
        if not isinstance(e, dict) or e.get("status") == "split":
            continue
        d = str(e.get("department") or "").lower()
        last = d
        if d:
            by[d] = e.get("prerender_script") or ""
    return {"department": last, "by": by}


def _owner_shots(owner: Path) -> list[str]:
    """A shot folder's shots: ["sh040"], or ["sh040", "sh050", "sh060"] for
    a block "sh040-050-060". Name parsing only, no config."""
    first, *rest = owner.name.split("-")
    m = re.match(r"(\D*)(\d+)$", first)
    if not m:
        return [owner.name]
    return [first] + [f"{m[1]}{n.zfill(len(m[2]))}" for n in rest]


def read_render_state(
    root: Path,
    kind: str,
    owner: Path,
    v_prefix: str = "v",
    stages: dict | None = None,
    latest: bool = False,
) -> list:
    """What was last rendered for an asset/shot folder, one line per shot:
    [{"shot", "file", "folder", "path", "frames", "frame_machines",
    "machine_seconds", "department", "others"}], frames its [first, last]
    (None unknown). Each shot's main render (_main_first(): its highest
    stage's department, by stages {department: stage}; latest: the most
    recent), its other departments' last ones in "others" ({"department",
    "file", "folder", "path", "newer": made after the main}). From
    render_history.json's finished renders of that shot whose folder is
    still there, else the latest render folder's name. Pure os/json: thread-safe. See NOTES.md,
    "Renders by department"."""
    stages = stages or {}
    history = read_json_quiet(owner / ".pipeline" / "render_history.json") or {}
    # A render with no output_path names no folder (one from before 1.0.11
    # the migration couldn't match): not a render to show.
    finished = [
        e
        for e in history.get("entries", [])
        if isinstance(e, dict) and e.get("status") == "finished" and e.get("output_path")
    ]
    base = render_root(root, owner)
    shots = _owner_shots(owner) if kind == "shot" else [""]
    block = len(shots) > 1

    def one(shot: str, last: dict) -> dict:
        folder = (Path(root) / last["output_path"]).parent
        return {
                "_when": iso_timestamp(last.get("completed_at")) or _mtime(folder),
                "shot": shot,
                "department": str(last.get("department") or "").lower(),
                "file": Path(last.get("source_file") or "").name or None,
                "folder": folder.name,
                "path": str(folder),
                "frames": _frame_pair(last.get("frame_range_rendered"))
                or _folder_frames(folder),
                # Which machine wrote each frame, and their pace
                # (farm queue._note_frames()): File details' lookup.
                "frame_machines": last.get("frame_machines"),
                "machine_seconds": last.get("machine_seconds"),
        }

    def last_render(shot: str, mine: list, folder_dir: Path) -> dict:
        # Each department's last whose folder is still there (renders/
        # cleaned, or a project copied without it: the history says more
        # than the disk has).
        by_dep: dict[str, int] = {}
        for i in reversed(mine):
            dep = str(finished[i].get("department") or "").lower()
            if dep not in by_dep and (Path(root) / finished[i]["output_path"]).parent.is_dir():
                by_dep[dep] = i
        if by_dep:
            # The main one, the others under it.
            lasts = [one(shot, finished[i]) for i in sorted(by_dep.values())]
            main = lasts[0]
            for r in lasts[1:]:
                if _main_first(r, main, stages, latest):
                    main = r
            main["others"] = [
                {k: r[k] for k in ("department", "file", "folder", "path")}
                | {"newer": _newer(r, main)}
                for r in sorted(lasts, key=lambda r: (-stages.get(r["department"], 0), r["department"]))
                if r is not main
            ]
            return main
        newest = main_render_dir(folder_dir, v_prefix)
        return {
            "_when": _mtime(newest),
            "shot": shot,
            "department": "",
            "others": [],
            "file": None,
            "folder": newest.name if newest else None,
            "path": str(newest) if newest else None,
            "frames": _folder_frames(newest) if newest else None,
        }

    out = []
    for shot in shots:
        # A block's history holds every shot it rendered, told apart by
        # shot_override; a mono shot's or an asset's is all its own.
        mine = [
            i
            for i, e in enumerate(finished)
            if not block or e.get("shot_override") == shot
        ]
        out.append(last_render(shot, mine, base.with_name(shot) if shot else base))
    if block:
        # The block rendered whole: each shot's last render is the newer of
        # its own and that one, by when it finished (the two folders number
        # their renders apart).
        mine = [i for i, e in enumerate(finished) if not e.get("shot_override")]
        whole = last_render("", mine, base)
        if whole["path"]:
            out = [
                dict(whole, shot=r["shot"], whole=True)
                if _main_first(whole, r, stages, latest)
                else r
                for r in out
            ]
    for r in out:
        r.pop("_when", None)
    return out


def _mtime(folder) -> float | None:
    """A render folder's last change (its frames, its video written): when
    a render with no history entry finished, near enough."""
    try:
        return os.stat(folder).st_mtime if folder else None
    except OSError:
        return None


def _main_first(a: dict, b: dict, stages: dict, latest: bool) -> bool:
    """Render a the main one rather than b (read_render_state()): one with
    a department before one without (from before 1.2), then the higher
    stage's department, then the newer -- latest: the newer only."""
    if not b.get("path"):
        return bool(a.get("path"))
    if not latest and a.get("path"):
        ka = (bool(a.get("department")), stages.get(a.get("department") or "", 0))
        kb = (bool(b.get("department")), stages.get(b.get("department") or "", 0))
        if ka != kb:
            return ka > kb
    return _newer(a, b)


def _newer(a: dict, b: dict) -> bool:
    """Render a finished after render b (read_render_state()): by when --
    the history's completed_at, else its folder's time --, by folder name
    (version, increment) only when that's unknown or the same."""
    if not b.get("path"):
        return bool(a.get("path"))
    wa, wb = a.get("_when"), b.get("_when")
    if wa is not None and wb is not None and wa != wb:
        return wa > wb
    return _render_order(a["folder"]) > _render_order(b["folder"])


def _frame_pair(value) -> list | None:
    """[first, last] from a job's frame range ([1001, 1100], strings too);
    None for none or (0, 0)."""
    try:
        first, last = (int(x) for x in value)
    except (TypeError, ValueError):
        return None
    return [first, last] if (first, last) != (0, 0) else None


_FRAME_FILE = re.compile(r"(\d+)\.(?:exr|png|jpe?g|tiff?|dpx|webp|bmp|tga)$", re.IGNORECASE)


def _folder_frames(folder: Path) -> list | None:
    """A render folder's [first, last] frame, from its images' numbers
    (name_1001.exr...): a render from before the history noted its range.
    None: no image, or the folder unreadable."""
    numbers = []
    try:
        with os.scandir(folder) as it:
            for f in it:
                if m := _FRAME_FILE.search(f.name):
                    numbers.append(int(m[1]))
    except OSError:
        return None
    return [min(numbers), max(numbers)] if numbers else None


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


def _video_name(root: Path, mp4: Path | None) -> str | None:
    """A video's path under renders/, as the snapshot names it; None for
    none, or one elsewhere."""
    try:
        return mp4.relative_to(Path(root) / "renders").as_posix()
    except (AttributeError, ValueError):
        return None


def ensure_snapshot_lds(
    data: dict,
    root: Path,
    sequences: list[str],
    assets: bool,
    ffmpeg: str,
    all_departments: bool = False,
) -> tuple[list[str], list[tuple[str, str]]]:
    """A light copy (preview.ensure_ld()) for each video of these sequences
    (and the assets, with them) a browser can't play and that has none yet,
    its "video" pointed at it -- the main renders', with all_departments the
    other departments' last ones too. Returns (made, [(video, why)] not
    made). Disk and ffmpeg: on a thread."""
    root = Path(root)
    made, failed = [], []
    for kind, owner, raw, _ in data["raws"]:
        if kind == "shot":
            try:
                wanted = owner.relative_to(root / "shots").parts[0] in sequences
            except (ValueError, IndexError):
                wanted = False
        else:
            wanted = assets
        if not wanted:
            continue
        for r in _with_others(data["renders"].get(str(owner), []), all_departments):
            name = r.get("video")
            if not name or f"/{LD_DIR}/" in f"/{name}":
                continue
            video = root / "renders" / name
            try:
                ld = ensure_ld(video, ffmpeg)
            except Exception as e:
                failed.append((name, str(e).strip().splitlines()[-1] if str(e).strip() else type(e).__name__))
                continue
            if ld is not None:
                r["video"] = _video_name(root, ld)
                made.append(r["video"])
    return sorted(set(made)), failed


def _with_others(renders: list, others: bool) -> list:
    """The main renders, and with others each one's other departments' last
    renders after it."""
    return [x for r in renders for x in (r, *((r.get("others") or []) if others else ()))]


def snapshot_videos(
    snapshot: dict,
    root: Path,
    sequences: list[str],
    assets: bool,
    all_departments: bool = False,
) -> tuple[list[tuple[Path, str]], list[str]]:
    """The videos of the last renders the snapshot shows -- its shots' of
    these sequences, and with assets every asset/library's; their main
    renders', with all_departments every department's last one --, as
    [(mp4, its path under renders/)], each once: what Export snapshot
    copies or zips, under those names, and what the page plays. Also the
    sequences (and "assets/libraries") with none. No disk access."""
    renders = Path(root) / "renders"
    out, seen, found = [], set(), set()
    for item in snapshot["shots"] + snapshot["assets"]:
        shot = item["kind"] == "shot"
        if not (item["group"] in sequences if shot else assets):
            continue
        for r in _with_others(item.get("renders") or [], all_departments):
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
    """The render folder a review note is about, from its row's
    render_watched (_render_ref()): its shot's, else the row's one render;
    on a whole block, the newest of its shots'. None when its shot has no
    render there."""
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


def folder_links(root: Path, currents: dict, outdated: dict) -> dict:
    """Per folder (currents: {owner key: the project files it links, as
    stored}), its links as the page draws them: {"key" (its path under the
    project), "links": [{"key", "file", "newer"}], "linked_by": [keys]};
    outdated: _outdated_links_of()'s. The snapshot's and the live page's.
    Pure."""
    rel = {}
    for key in currents:
        try:
            rel[_path_key(Path(key))] = Path(key).relative_to(root).as_posix()
        except ValueError:
            pass
    by_target: dict[str, list[str]] = {}
    out = {}
    for key, files in currents.items():
        me = rel.get(_path_key(Path(key)))
        newer = dict(outdated.get(key) or [])
        links = []
        for f in files:
            path = Path(f) if Path(f).is_absolute() else Path(root) / f
            target = rel.get(_path_key(path.parent), "")
            links.append({"key": target, "file": path.name, "newer": newer.get(path.name, "")})
            if target and me:
                by_target.setdefault(target, []).append(me)
        out[key] = {"key": me, "links": links}
    for extra in out.values():
        extra["linked_by"] = sorted(set(by_target.get(extra["key"], [])))
    return out


def read_snapshot_data(
    root: Path, thumbnails: dict | None = None, v_prefix: str = "v"
) -> dict:
    """read_snapshot_raw() plus each folder's last render
    (read_render_state()) and thumbnails, remade first when missing or older
    than their render (one headless Blender, waited on: run it on a thread).
    thumbnails: {"size", "blender", "ffmpeg"}, None to skip. Returns
    {"raws", "renders", "thumbs", "shot_thumbs", "thumb_warnings", "work"}."""
    raws = read_snapshot_raw(root)
    config = read_json_quiet(Path(root) / "config" / "project_config.json") or {}
    renders = {
        str(owner): read_render_state(
            root, kind, owner, v_prefix, project_stages(config, f"{kind}s")
        )
        for kind, owner, raw, _ in raws
        if not raw["tracking"].get("archived")
    }
    # Each render's video, by its path under renders/: what the snapshot's
    # videos folder or zip holds, and what the page plays for that render
    # -- its light copy (ld/) when it has one.
    for shots in renders.values():
        for r in shots:
            for x in (r, *(r.get("others") or [])):
                x["video"] = _video_name(
                    root, browser_video(Path(x["path"])) if x.get("path") else None
                )
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
    # Who links what (the Links tab): each folder's latest metadata, one
    # listing per folder linked for a newer stable.
    currents = {
        str(owner): _current_link_files(_pipeline_entries(owner), root)
        for _, owner, raw, _ in raws
        if not raw["tracking"].get("archived")
    }
    links = folder_links(
        root, currents, _outdated_links_of(root, [Path(k) for k in currents], currents, v_prefix)
    )
    return {
        "raws": raws,
        "renders": renders,
        "thumbs": thumbs,
        "shot_thumbs": shot_thumbs,
        "thumb_warnings": warnings,
        "work": work_times(root),
        "live": links,
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
            (int(m[1]), b) for b in blends if (m := version_re.search(b)) and m[2] in (None, *(f"-{t}" for t in RELINK_TAGS))
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
            "render_presets": raw.get("render_presets") or {},
            "departments_required": list(status.get("departments_required", [])),
            "departments": {
                d: department_state(status, d)
                for d in status.get("departments_required", [])
            },
            "flags": status.get("flags") or {},
            # Who each department is assigned to (Edit project's team).
            "assignees": status.get("assignees") or {},
            # Set aside: listed, out of every share done (lib/monitoring/status.py).
            "omit": omitted(status),
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
            # The live page's own (lib/monitoring/live.py): its links, its renders to
            # check, every version's video.
            "live": (data.get("live") or {}).get(str(owner)),
            # Logged work time, every version and everyone (work_times()).
            "work_seconds": (data.get("work") or {}).get(_session_folder_key(owner)),
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
                    "frames": r.get("frames"),
                    # Renders by department: its own, the others' last.
                    "department": r.get("department") or "",
                    "others": [
                        {k: o.get(k) for k in ("department", "folder", "video", "newer")}
                        for o in r.get("others") or []
                    ],
                }
            )
        item["renders"] = renders
        # Rendered, not checked by the team yet / still in the farm.
        # Labelled as the render lines are ("sh040 v002"), its department
        # aside: matched against them (snapshot_page.py _render_lines()).
        item["to_check"] = [
            render_to_check_label(info["shot"], {**info, "department": ""})
            for _, info in to_check_entries(status if isinstance(status.get("to_check"), dict) else {})
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
        # (file_progress()), never on each department's.
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
            d: department_score(st, d in rtk_departments, weights)
            for d, st in item["departments"].items()
        }
        item["progress"] = None if item["omit"] else file_progress(item, weights)
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
        item["validation"] = sum(valid) / len(valid) if valid and not item["omit"] else None
        items[kind].append(item)
        notes.extend(threads)

    for k in items:
        items[k].sort(key=lambda i: i["name"])
    notes.sort(key=lambda n: (n["item"], time_key(n["last_activity"])))
    meta = dict(meta)
    meta.setdefault("schema_version", SCHEMA_VERSION)
    meta["thumbnail_warnings"] = list(data["thumb_warnings"])
    meta["thumbnail_size"] = thumbnail_size(config)
    meta["progress"] = {k: average_progress(v) for k, v in items.items()}
    meta["progress_weights"] = weights
    # The videos' frame rate (the farm compiles at the scene's; the
    # project's is the one known here): a video's frame from its time.
    meta["fps"] = json_get(config, "default_fps", 30)
    meta["validation_roles"] = roles
    meta["validation_role"] = top_role
    # What a new shot or asset may be called, created from the page.
    meta["team"] = list(config.get("team") or [])
    meta["naming"] = {
        "sequence": json_get(config, "naming.sequence", {"prefix": "sq", "digits": 3}),
        "shot": json_get(config, "naming.shot", {"prefix": "sh", "digits": 3}),
        "asset_prefixes": json_get(config, "structure.asset_prefixes", []),
        "library_prefixes": json_get(config, "structure.library_prefixes", []),
        "frame_start": json_get(config, "default_frame_start", 1001),
    }
    meta["validation"] = {
        k: average_progress(v, "validation") for k, v in items.items()
    }
    schedule = project_schedule(config)
    if schedule:
        today = (parse_iso(meta.get("scan_started_at")) or now(iso=False)).date()
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


def top_validation_role(roles: list) -> str | None:
    """The role the "Validated" figures count: the highest level's (its
    equivalents cover it). None without any role."""
    return max(roles, key=lambda r: r["level"])["name"] if roles else None


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
        # Its id: a retake marked fixed in the page's review is found by it.
        "id": e.get("id", ""),
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


def run_in_background(fn, args: tuple, on_done, on_error, every: float = 0.3) -> None:
    """fn(*args) on a SnapshotJob, polled by a timer (no modal handler: works
    with no window), then on_done(result) or on_error(error)."""
    import bpy

    job = SnapshotJob(fn, *args)

    def poll():
        if not job.done:
            return every
        if job.error:
            on_error(job.error)
        else:
            on_done(job.result)
        return None

    bpy.app.timers.register(poll, first_interval=every)


def write_snapshot(snapshot: dict, filepath: Path) -> Path:
    """render_html() written to filepath. Pure: thread-safe."""
    Path(filepath).write_text(render_html(snapshot), encoding="utf-8")
    return Path(filepath)


# snapshots/: a folder per month (2026-11/), the pages of before 1.2 left at
# its root (moved, their paths to the videos would break); one videos/
# shared by every month, and the reviews imported, kept by role and month.
# See NOTES.md, "Snapshots and reviews by month".
SNAPSHOT_VIDEOS = "videos"
REVIEWS_DIRNAME = "reviews"
_MONTH = re.compile(r"\d{4}-\d{2}$")


def month_folder(snapshots: Path, when=None) -> Path:
    """snapshots/<YYYY-MM>/ of when (an aware datetime; now if None)."""
    return Path(snapshots) / f"{(when or now(False)):%Y-%m}"


def snapshot_videos_folder(page: Path, snapshots: Path) -> Path:
    """Where Folder mode copies a page's videos: the project's
    snapshots/videos/ for a page in one of its month folders, shared by
    every month; videos/ beside a page saved anywhere else."""
    folder = Path(page).parent
    if _MONTH.match(folder.name) and _same_path(folder.parent, snapshots):
        return Path(snapshots) / SNAPSHOT_VIDEOS
    return folder / SNAPSHOT_VIDEOS


def _same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


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
    """The whole snapshot as one offline HTML page (lib/monitoring/snapshot_page.py)."""
    from .snapshot_page import render_html as page  # it imports this module

    return page(snapshot)
