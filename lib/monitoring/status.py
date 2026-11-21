"""The state engine: a department's state, its share done and a file's,
from the facts lib/monitoring/tracking.py's _status_from_raw() gathers (validated at
the latest stable, worked since, started before). Pure, no bpy, no disk:
every view asks it -- the sidebar, the snapshot and the live page. Phase 3
of dev/plan-1.2.md grew it (Waiting, To redo, On hold).
No disk, no bpy call: tests/test_status.py.
See NOTES.md, "State engine"."""

from ..core import EARLIEST, json_get, parse_iso

# Share of a department counted as done per state, in % -- the project's
# "snapshot.progress" (Edit project) overrides each. Validated counts 100,
# not started 0. "rtk": validated, with an open RTK.
PROGRESS_WEIGHTS = {"wip": 33, "rework": 67, "rtk": 67}

# A file set aside (tracking.json "omit"): its words. Kept in the lists,
# out of the shares done, the filters and the stages. See NOTES.md, "On
# hold and Cancelled".
OMIT_STATES = {"on_hold": "On hold", "cancelled": "Cancelled"}

def department_state(status: dict, department: str) -> str:
    """done / rework (validated at the latest stable, worked since or not),
    wip (worked since, or started before: validated at an earlier stable or
    worked before the latest one), todo (never)."""
    validated = department in status.get("validated_departments", {})
    worked = department in status.get("worked_departments", {})
    if validated:
        return "rework" if worked else "done"
    started = department in status.get("started_departments", ())
    return "wip" if worked or started else "todo"


def omitted(facts: dict) -> dict | None:
    """A file's On hold / Cancelled marker ({"state", "at", "by", "reason"}),
    None when it counts."""
    mark = facts.get("omit")
    return mark if isinstance(mark, dict) and mark.get("state") in OMIT_STATES else None


def department_score(state: str, open_rtk: bool, weights: dict) -> float:
    """One department's share done, 0..1: validated 1 (its "rtk" weight
    with an open RTK), not started 0, else its state's weight."""
    if state == "done":
        return weights["rtk"] / 100 if open_rtk else 1.0
    return weights.get(state, 0) / 100


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


def file_progress(item: dict, weights: dict) -> float | None:
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


# ---------------------------------------------------------------------------
# Stages: Waiting and To redo (dev/plan-1.2.md 2.2)
# ---------------------------------------------------------------------------


def parse_departments(text: str) -> tuple[list[str], dict[str, int]]:
    """Edit project's departments field, "layout > animation > fx,
    lighting > render": the departments as written, and their stages
    {department: stage} from 1 -- ">" the next stage, "," the same one (in
    parallel). Commas only (one stage): no stages, {}."""
    departments, stages = [], {}
    for i, part in enumerate(p for p in str(text or "").split(">") if p.strip()):
        for d in part.split(","):
            d = d.strip()
            if d and d.lower() not in stages:
                departments.append(d)
                stages[d.lower()] = i + 1
    return departments, stages if len(set(stages.values())) > 1 else {}


def preset_department(preset: str, departments) -> str:
    """The department a render preset's name gives: the longest of the
    departments its name starts with, then "_", "-" or nothing, any case
    ("look_dev_hd": look_dev). "" for none. See NOTES.md, "Renders by
    department"."""
    name, best = str(preset or "").lower(), ""
    for d in departments or ():
        d = str(d).strip().lower()
        if d and len(d) > len(best) and name.startswith(d) and name[len(d):len(d) + 1] in ("", "_", "-"):
            best = d
    return best


def departments_text(departments: list, stages: dict) -> str:
    """parse_departments()'s field back: by stage, each stage's in the
    list's order; commas only without stages. One the stages leave out
    goes with the first."""
    if not stages:
        return ", ".join(str(d) for d in departments)
    by_stage: dict[int, list] = {}
    for d in departments:
        by_stage.setdefault(int(stages.get(str(d).lower(), 1)), []).append(str(d))
    return " > ".join(", ".join(by_stage[s]) for s in sorted(by_stage))


def stage_flags(facts: dict, stages: dict) -> dict[str, dict]:
    """{department: {"waiting": reason} and/or {"to_redo": reason, "since":
    ISO}} of a file's required departments, from its facts (the status
    _status_from_raw() gives) and its kind's stages. Information only,
    nothing is blocked. See NOTES.md, "Waiting and To redo".

    - Waiting: an earlier stage has an open RTK ("layout RTK") or isn't
      started ("layout not started"), the nearest stage first.
    - To redo: a started department whose earlier stage changed after its
      last update -- an RTK on it closed, or the latest stable made with it
      worked while this one, already started, wasn't worked with it. Its
      last update: its latest session saved, its Still done
      (departments_synced); for an RTK closed, the latest stable too, once
      it was started then (a frozen version holds it).
    """
    required = [d for d in facts.get("departments_required") or [] if d in stages]
    if not required or omitted(facts):
        return {}
    entries = [e for e in facts.get("entries") or [] if isinstance(e, dict)]
    rtks = [e for e in entries if e.get("type") == "rtk"]
    open_on = {d for e in rtks if e.get("done") is False for d in e.get("departments") or []}
    stable = facts.get("stable_info") or {}
    stable_at = parse_iso(stable.get("created_at"))
    stable_worked = set(facts.get("stable_worked") or [])
    stable_started = set(facts.get("started_departments") or [])
    synced = facts.get("departments_synced") or {}
    last_worked = facts.get("last_worked_at") or {}

    flags: dict[str, dict] = {}
    for d in required:
        upstream = sorted(
            (u for u in required if stages[u] < stages[d]), key=lambda u: -stages[u]
        )
        if not upstream:
            continue
        out = {}
        blocking = next((u for u in upstream if u in open_on), None)
        if blocking:
            out["waiting"] = f"{blocking} RTK"
        else:
            idle = next((u for u in upstream if department_state(facts, u) == "todo"), None)
            if idle:
                out["waiting"] = f"{idle} not started"
        if department_state(facts, d) != "todo":
            # Its own updates since the latest stable (a session, Still done).
            own = max(
                (u for u in (parse_iso(last_worked.get(d)),
                             parse_iso((synced.get(d) or {}).get("at"))) if u),
                default=None,
            )
            # An earlier stage's RTK closed after its last update -- the
            # latest stable counting as one once it was started then.
            base = stable_at if stable_at and (d in stable_worked or d in stable_started) else None
            last = max((u for u in (own, base) if u), default=EARLIEST)
            later = [
                (at, u)
                for e in rtks
                if e.get("done") is True and (at := parse_iso(e.get("done_at"))) and at > last
                for u in e.get("departments") or []
                if u in upstream
            ]
            # The latest stable made with an earlier stage worked, this one
            # started before it but not worked with it, nor since.
            if stable_at and d in stable_started and d not in stable_worked and not (own and own > stable_at):
                later += [(stable_at, u) for u in upstream if u in stable_worked]
            if later:
                at, u = max(later, key=lambda c: c[0])
                out["to_redo"] = f"{u} changed on {at:%d/%m}"
                out["since"] = at.isoformat(timespec="seconds")
        if out:
            flags[d] = out
    return flags


def project_stages(config: dict, kind: str) -> dict[str, int]:
    """The project's stages for a kind ("shots" / "assets"; a library's
    are the assets'), {} without any."""
    stages = (config or {}).get("department_stages") or {}
    return {str(d).lower(): int(s) for d, s in (stages.get(kind) or {}).items()}
