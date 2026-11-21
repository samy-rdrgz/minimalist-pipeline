"""A farm job's and a machine's details as plain data -- what Farm
monitoring drew, kept apart from its panel: the live page's Farm tab
reads them (lib/monitoring/live.py). Memory and json reads only, no bpy UI."""

from pathlib import Path

from ..lib import ConfigCache, format_duration, format_pace, get_addon_version, get_active_project_root, now, parse_iso, read_json_quiet
from .chunks import chunk_frames
from .monitor import get_monitor_cache
from .queue import failed_stage, recompilable
from .workers import FARM_PROTOCOL


def pace_source(pace: dict) -> str:
    """Where an estimate's pace comes from (history_pace(), farm/loop.py):
    "" for the file's own render with this preset, else said."""
    basis = pace.get("basis")
    if basis == "project":
        n = pace.get("renders") or 0
        return f"average of {n} {pace.get('preset') or 'default'} render{'s' if n > 1 else ''}"
    if basis == "other":
        return f"from a {pace.get('other_preset') or 'default'} render"
    return ""


def estimate_label(job: dict, cache: dict) -> str:
    """ "≃ 1h00m with 4 workers" for a job waiting for a worker: its frames
    at the pace history_pace() (farm/loop.py) found -- the file's last
    render with this pre-render script, else that script's project
    average, else the file's last render -- shared by the live workers.
    "" without any past render to go by."""
    pace = job.get("history_pace")
    frames = job.get("frames_to_render") or 0
    if not pace or not frames:
        return ""
    workers = max(1, len(cache.get("workers") or {}))
    total = frames * pace["seconds_per_frame"] / workers
    plural = "s" if workers > 1 else ""
    text = f"≃ {format_duration(total)} with {workers} worker{plural}"
    source = pace_source(pace)
    return f"{text}, {source}" if source else text


# Stages before the render: their frames aren't known yet (not set up).
NOT_SET_UP = ("pending", "queued", "setup_start")


def render_left_label(jobs: list, cache: dict) -> str:
    """ " - ≃ 3h20m of rendering left with 4 workers": the machine time the
    jobs still need -- a render's frames left at its own pace, a job
    waiting for a worker at its estimate's (estimate_label()) -- shared by
    the live workers. The ones it can't tell (not set up yet, nothing timed
    yet, never rendered before) are counted apart. "" if none's left."""
    machine_time, unknown = 0.0, 0
    for j in jobs:
        stage = j.get("stage", "")
        if stage == "render_start" and j.get("frames_total"):
            pace = j.get("seconds_per_frame")
            if pace:
                machine_time += (j["frames_total"] - j["frames_done"]) * pace
            else:
                unknown += 1
        elif j.get("frames_to_render"):
            pace = j.get("history_pace")
            if pace:
                machine_time += j["frames_to_render"] * pace["seconds_per_frame"]
            else:
                unknown += 1
        elif stage in NOT_SET_UP:
            unknown += 1
    if not machine_time:
        return f" - {unknown} not estimated yet" if unknown else ""
    workers = max(1, len(cache.get("workers") or {}))
    text = (
        f" - ≃ {format_duration(machine_time / workers)} of rendering left with "
        f"{workers} worker{'s' if workers > 1 else ''}"
    )
    if unknown:
        text += f" (+{unknown} not estimated)"
    return text


def machine_label(uuid: str, recorded: str = "") -> str:
    """A machine as people know it: its worker's user and id ("Alice
    (a1b2c3d4)") -- a machine is only ever named by its id, no hostname
    read. Else the name recorded with the render, else the id. Memory
    only (the monitor cache's workers): draw()-safe."""
    worker = (get_monitor_cache().get("workers") or {}).get(uuid) or {}
    if worker.get("user"):
        return f"{worker['user']} ({worker.get('machine') or uuid[:8]})"
    return worker.get("machine") or recorded or uuid[:8]


def same_machine_run(record: dict, frame: int) -> tuple[int, int]:
    """(first, last) of the frames around frame written by the same machine
    in a row: its chunk, or several of them."""
    letters, start = record["frames"], int(record.get("start", 0))
    i = j = frame - start
    while i > 0 and letters[i - 1] == letters[i]:
        i -= 1
    while j < len(letters) - 1 and letters[j + 1] == letters[j]:
        j += 1
    return start + i, start + j


def since(iso: str) -> tuple[str, float | None]:
    """("21/10 13:41" or "13:41" today, seconds ago) of an ISO time, ("-",
    None) if there's none."""
    at = parse_iso(iso)
    if at is None:
        return "-", None
    today = at.date() == now(False).date()
    when = f"{at:%H:%M}" if today else f"{at:%d/%m %H:%M}"
    return when, (now(False) - at).total_seconds()


_addon_version: list = []


def addon_version_once() -> str:
    """get_addon_version(), once: it walks addon_utils.modules(), too much
    for every redraw."""
    if not _addon_version:
        _addon_version.append(get_addon_version())
    return _addon_version[0]


def chunk_label(job: dict, k) -> str:
    """ "frames 11-15" for chunk k of job (its chunk_size and range)."""
    try:
        start, end = (int(x) for x in job["resolved_frame_range"])
        first, last = chunk_frames(start, end, int(job["chunk_size"]), int(k))
    except (KeyError, TypeError, ValueError):
        return f"chunk {k}"
    return f"frames {first}-{last}"


def claim_progress(claim: dict) -> str:
    """ "on frame 13" / "starting" from a claim (frame in progress, done)."""
    if claim.get("frame_in_progress") is not None:
        return f"on frame {claim['frame_in_progress']}"
    if claim.get("frames_done"):
        return f"frame {claim['frames_done'][-1]} done"
    return "starting"




def _names(uuids, recorded: dict) -> str:
    return ", ".join(machine_label(u, recorded.get(u, "")) for u in uuids or []) or "-"


def job_files(job_id: str) -> tuple[Path | None, list[Path]]:
    """A job's file -- active, else archived -- and its logs: this
    machine's stages (request_<job>.log), each worker's render
    (request_<job>_<uuid>.log)."""
    path = None
    for folder in ("farm_actives", "farm_archives"):
        candidate = ConfigCache.get_path(folder) / f"{job_id}.json"
        if candidate.is_file():
            path = candidate
            break
    logs = sorted(
        log_file
        for folder in ("farm_requests", "farm_archives")
        for log_file in ConfigCache.get_path(folder).glob(f"request_{job_id}*.log")
    )
    return path, logs


def job_detail(job_id: str) -> dict | None:
    """What the Farm tab's job details show, as data: {"rows": [[key,
    value, alert]], "stages": [[when, what]], "lookup" (who rendered which
    frame: {"start", "frames" (a letter a frame), "machines": {letter:
    [label, pace]}}), "logs": [names], "folder", "retry", "recompile"}.
    None: no file for it."""
    path, logs = job_files(job_id)
    data = read_json_quiet(path) if path else None
    if not data:
        return None
    recorded = dict(data.get("machine_names") or {})
    recorded.update({u: n for u, n in (data.get("frame_machines") or {}).get("machines", {}).values()})
    cache = get_monitor_cache()
    jobs = [j for j in cache.get("jobs") or [] if j.get("job_id") == job_id]
    live = next(iter(jobs), {})
    waiting = next((j for j in jobs if j.get("frames_to_render")), None)
    estimate = estimate_label(waiting, cache) if waiting else ""
    pace = (waiting or {}).get("history_pace") or {}
    source = pace_source(pace) if estimate and pace.get("basis") != "other" else ""
    stage = ((data.get("stage_history") or [{}])[-1]).get("stage")
    claims = (cache.get("claims") or {}).get(job_id) or {} if stage == "render_start" else {}
    average = live.get("seconds_per_frame") or data.get("seconds_per_frame")
    rerendered = data.get("frames_rerendered") or []
    progress = (cache.get("ffmpeg_progress") or {}).get(job_id)
    names = lambda uuids: _names(uuids, recorded)  # noqa: E731
    rows = [
        ("Render mode", data.get("render_mode", "-")),
        estimate and ("Estimate", estimate),
        estimate and ("Pace", f"{format_pace(pace['seconds_per_frame'])} a frame"
                      + (f", as {pace['render']}" if pace.get("render") else "") + (f", {source}" if source else "")),
        ("Format", f"{data.get('output_extension', '-')} · {data.get('fps', '-')} fps"),
        ("Assigned to", names(data["assigned_machines"]) if data.get("assigned_machines") else "auto"),
        data.get("chunk_size") and ("Chunks", f"{data['chunk_size']} frames each"),
        progress is not None and ("Progress", f"{progress:.0%}"),
        *(
            ("In progress" if i == 0 else "", f"{chunk_label(data, k)}: "
             f"{names([claim['machine']]) if claim.get('machine') else 'a machine'}, {claim_progress(claim)}")
            for i, (k, claim) in enumerate(sorted(claims.items()))
        ),
        *(
            ("Failed chunk", f"{chunk_label(data, k)} on {names(m)}", True)
            for k, m in sorted((data.get("chunk_failures") or {}).items(), key=lambda kv: int(kv[0]))
        ),
        *(
            ("Why", f"{chunk_label(data, f.get('chunk'))} on {names([f.get('machine')])}: {f.get('reason')}", True)
            for f in data.get("failure_reasons") or []
        ),
        data.get("fail_reason") and ("Stopped", data["fail_reason"], True),
        data.get("left_machines") and ("Taken off", names(data["left_machines"])),
        data.get("rendered_by") and ("Rendered by", names(data["rendered_by"])),
        *(
            ("Stuck frame", f"{st.get('frame') or '?'} on {names([st.get('machine')])}: killed after "
             f"{(st.get('seconds') or 0) / 60:.0f} min (usually {st.get('usual') or '?'} s)", True)
            for st in data.get("stuck_frames") or []
        ),
        average and ("Per frame", f"{format_pace(average)} on average"),
    ]
    per_machine = live.get("machine_seconds") or data.get("machine_seconds") or {}
    record = data.get("frame_machines") or {}
    counts: dict = {}
    for letter in record.get("frames", ""):
        uuid = (record.get("machines", {}).get(letter) or [""])[0]
        if uuid:
            counts[uuid] = counts.get(uuid, 0) + 1
    if per_machine or counts:
        rec = {u: n for u, n in record.get("machines", {}).values()}

        def line(u):
            parts = [f"{counts[u]} frames"] if u in counts else []
            if u in per_machine:
                parts.append(f"{format_pace(per_machine[u])}/frame")
            return f"{machine_label(u, rec.get(u))} ({', '.join(parts)})"

        rows.append(("Per machine", ", ".join(line(u) for u in sorted(set(per_machine) | set(counts)))))
    rows += [
        data.get("failed_machines") and ("Failed on", names(data["failed_machines"])),
        data.get("frames_corrupted") and ("Corrupted frames", str(data["frames_corrupted"]), True),
        rerendered and ("Rendered again", ", ".join(str(f) for f in rerendered[:8]) + (f" (+{len(rerendered) - 8})" if len(rerendered) > 8 else "")),
        data.get("split_into") and ("Split into", ", ".join(data["split_into"])),
        data.get("skipped_shots") and ("Missing shots", ", ".join(data["skipped_shots"]), True),
        data.get("absorbed_shots") and ("Absorbed shots", ", ".join(data["absorbed_shots"])),
    ]
    stages, previous = [], None
    for entry in data.get("stage_history") or []:
        at = parse_iso(entry.get("at"))
        what = entry.get("stage", "?")
        detail = entry.get("resumed") or entry.get("reason") or ("cancelled" if entry.get("cancelled") else "")
        delta = f" +{format_duration((at - previous).total_seconds())}" if at and previous else ""
        stages.append([f"{at:%d/%m %H:%M:%S}{delta}" if at else "?", f"{what} ({detail})" if detail else what])
        previous = at or previous
    lookup = None
    if record.get("frames"):
        lookup = {
            "start": int(record.get("start", 0)),
            "frames": record["frames"],
            "machines": {
                letter: [machine_label(u, n), format_pace(per_machine[u]) + "/frame" if u in per_machine else "pace unknown"]
                if u else ["machine not recorded", ""]
                for letter, (u, n) in record.get("machines", {}).items()
            },
        }
    prefix = f"request_{job_id}_"
    return {
        "rows": [[r[0], str(r[1]), bool(r[2]) if len(r) > 2 else False] for r in rows if r],
        "stages": stages,
        "lookup": lookup,
        "logs": [names([f.stem[len(prefix):]]) if f.stem.startswith(prefix) else "farm host" for f in logs],
        "folder": bool(data.get("output_path")),
        "retry": bool(failed_stage(data)),
        "recompile": recompilable(data),
    }


def job_path(job_id: str, what: str) -> Path | None:
    """A job's thing to open on this machine: "file" (its job file),
    "folder" (its render folder), "log:<n>" (its n-th log)."""
    path, logs = job_files(job_id)
    if what == "file":
        return path
    if what.startswith("log:"):
        try:
            return logs[int(what[4:])]
        except (ValueError, IndexError):
            return None
    data = read_json_quiet(path) if path else None
    output = (data or {}).get("output_path")
    root = get_active_project_root()
    if what == "folder" and output and root:
        out = Path(output)
        return (out if out.is_absolute() else Path(root) / out).parent
    return None


def worker_detail(uuid: str) -> dict | None:
    """What the Farm tab's machine details show, as data: {"rows": [[key,
    value, alert]], "stop" (a live worker to stop), "busy", "forget" (a
    silent one), "job" (the job it's on)}. From the monitor cache only."""
    import re

    cache = get_monitor_cache()
    live = (cache.get("workers") or {}).get(uuid)
    m = live or (cache.get("silent_workers") or {}).get(uuid) or {}
    if not m:
        return None
    beat, beat_age = since(m.get("last_heartbeat"))
    status = m.get("status") or "-"
    if not live:
        status = f"silent since {beat} (crashed, closed or asleep?)"
    elif m.get("stopping"):
        status += " (stops after this frame)"
    rows = [("Machine id", uuid), ("Status", status, not live)]
    current = m.get("current_job_id")
    if current:
        job = next((j for j in cache.get("jobs") or [] if j.get("job_id") == current), {})
        name = Path(job.get("filepath") or m.get("current_file") or "").name
        rows.append(("Compiling" if m.get("status") == "compile" else "Rendering", name or current))
        claims = (cache.get("claims") or {}).get(current) or {}
        mine = next(((k, c) for k, c in sorted(claims.items()) if c.get("machine") == uuid), None)
        pace = (job.get("machine_seconds") or {}).get(uuid)
        rows += [
            mine and ("Chunk", f"{chunk_label(job, mine[0])}, {claim_progress(mine[1])}"),
            pace and ("Pace", f"{format_pace(pace)} a frame"),
        ]
    started, up = since(m.get("started_at"))
    blender = m.get("blender_version")
    mismatch = None
    if blender:
        want = re.findall(r"\d+", str(ConfigCache.get().get("blender_version") or ""))
        have = re.findall(r"\d+", blender)
        if len(want) >= 2 and len(have) >= 2 and want[:2] != have[:2]:
            mismatch = f"{want[0]}.{want[1]}"
    addon, here = m.get("addon_version"), addon_version_once()
    other = bool(addon and addon != here)
    rows += [
        up is not None and ("Active since", f"{started} ({format_duration(up)})"),
        ("Blender", f"{blender} (project: {mismatch})" if mismatch else blender or "-", bool(mismatch)),
        m.get("farm_protocol") != FARM_PROTOCOL and ("Farm", "another version: gets no render until updated", True),
        ("Addon", f"{addon} (this machine: {here})" if other else addon or "-", other),
        ("FFmpeg", m.get("ffmpeg_version") if m.get("ffmpeg") else "not found: compiles no video", not m.get("ffmpeg")),
        ("Since started", f"{m.get('renders_done', 0)} render(s) done, {m.get('renders_failed', 0)} failed"),
    ]
    result = m.get("last_job_result") or {}
    if result:
        if result.get("stuck"):
            st = result["stuck"]
            outcome = f"killed: stuck on {st.get('frame') or 'a frame'} {(st.get('seconds') or 0) / 60:.0f} min (usually {st.get('usual') or '?'} s)"
        elif result.get("success"):
            outcome = "done"
        else:
            outcome = next((k for k in ("cancelled", "stopped", "lost") if result.get(k)), "failed")
            if outcome == "failed" and result.get("reason"):
                outcome = f"failed: {result['reason']}"
        when, _ = since(result.get("at"))
        rows.append(("Last render", f"{result.get('job_id') or ''}: {outcome} ({when})", outcome not in ("done", "cancelled", "stopped")))
    return {
        "rows": [[r[0], str(r[1]), bool(r[2]) if len(r) > 2 else False] for r in rows if r],
        "stop": bool(live and m.get("status") not in ("stopped", None) and not m.get("stopping")),
        "busy": bool(live and m.get("status") != "idle"),
        "forget": not live,
        "job": current or "",
    }
