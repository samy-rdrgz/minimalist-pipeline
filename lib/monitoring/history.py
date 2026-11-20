"""A shot's or asset's history, for the page's History tab: its versions
as a chain (each .wipmeta and .stablemeta -- made when, from which, who
saved it last, its sessions, a stable's done departments, validations and
conflict) and its renders (render_history.json: when, which department
and preset, frames, by whom, how long, how it ended).

Read for one folder at a time: the live page asks for it when the tab is
opened (POST /history, the server's thread), a snapshot carries every
folder's (its export, on its reading thread). Pure os/json."""

from pathlib import Path

from ..core import read_json_quiet
from . import legacy

_KEEP_RENDERS = 60  # the latest ones: a long-lived shot's history stays light


def _stem(value) -> str:
    return Path(str(value or "")).stem


def _sessions(data: dict) -> list:
    out = []
    for s in (legacy.wip_read(dict(data)).get(legacy.SESSIONS) or {}).values():
        if isinstance(s, dict):
            out.append({"by": s.get("by") or "", "at": s.get("saved_at") or "", "departments": list(s.get("departments") or [])})
        elif isinstance(s, list):
            out.append({"by": data.get("edited_by") or "", "at": data.get("edited_at") or "", "departments": list(s)})
    return sorted(out, key=lambda s: s["at"])


def _version(name: str, data: dict, stable: bool) -> dict:
    v = {
        "file": _stem(data.get("file")) or name,
        "stable": stable,
        "at": data.get("created_at") or "",
        "from": _stem(data.get("created_from")),
        "saved_at": data.get("edited_at") or "",
        "saved_by": data.get("edited_by") or "",
        "sessions": _sessions(data),
    }
    if stable:
        data = legacy.stable_read(dict(data))
        v.update(
            done=sorted(d for d, ok in (data.get("departments_done") or {}).items() if ok),
            worked=list(data.get("departments_worked") or []),
            approvals={
                d: sorted(roles) for d, roles in (data.get("approvals") or {}).items() if isinstance(roles, dict) and roles
            },
            conflict=data.get("conflict_warning") or "",
        )
    else:
        v["mode"] = data.get("creation_mode") or ""
    return v


def file_history(owner: Path) -> dict:
    """{"versions": [...] oldest first, "renders": [...] latest first}."""
    pipe = Path(owner) / ".pipeline"
    versions = []
    try:
        names = sorted(p.name for p in pipe.iterdir())
    except OSError:
        names = []
    for name in names:
        for suffix, stable in ((".wipmeta", False), (".stablemeta", True)):
            if name.endswith(suffix):
                data = read_json_quiet(pipe / name)
                if isinstance(data, dict):
                    versions.append(_version(name[: -len(suffix)], data, stable))
    versions.sort(key=lambda v: (v["at"], v["file"]))
    renders = []
    for e in (read_json_quiet(pipe / "render_history.json") or {}).get("entries") or []:
        if not isinstance(e, dict) or e.get("status") == "split":
            continue
        out = Path(str(e.get("output_path") or ""))
        renders.append(
            {
                "at": e.get("completed_at") or "",
                "status": e.get("status") or "",
                "department": e.get("department") or "",
                "preset": e.get("prerender_script") or "",
                "frames": e.get("frame_range_rendered") or None,
                "by": e.get("user") or "",
                "seconds": e.get("duration_seconds") or 0,
                "machines": len(e.get("machines_used") or []) if isinstance(e.get("machines_used"), list) else e.get("machines_used") or 0,
                "source": _stem(e.get("source_file")),
                "folder": out.name if out.name else "",
                "shot": e.get("shot_override") or "",
                # Render here: "local", "viewport" (farm/queue.py construct_history()).
                "tags": [t for t in e.get("tags") or [] if isinstance(t, str)],
            }
        )
    renders.sort(key=lambda r: r["at"], reverse=True)
    return {"versions": versions, "renders": renders[:_KEEP_RENDERS]}
