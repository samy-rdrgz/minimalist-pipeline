"""The state engine: a department's state, its share done and a file's,
from the facts lib/tracking.py's _status_from_raw() gathers (validated at
the latest stable, worked since, started before). Pure, no bpy, no disk:
every view asks it -- the sidebar, Project monitoring, File details, the
snapshot. Phase 3 of docs/plan-1.2.md grows it (Waiting, To redo, Omit).
See NOTES.md, "State engine"."""

from .core import json_get

# Share of a department counted as done per state, in % -- the project's
# "snapshot.progress" (Edit project) overrides each. Validated counts 100,
# not started 0. "rtk": validated, with an open RTK.
PROGRESS_WEIGHTS = {"wip": 33, "rework": 67, "rtk": 67}

# A state's words, the same everywhere (page.js LABEL too).
STATE_LABELS = {
    "todo": "Not started",
    "wip": "In progress",
    "done": "Done",
    "rework": "Done, reworked since",
}


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
