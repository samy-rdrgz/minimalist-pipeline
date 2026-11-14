"""A job's stage_history: the one way a stage is added to it."""

from ..lib import locked_json, now


def add_stage(data: dict, stage: str, **fields) -> None:
    """Append stage to a job's stage_history, now, with its fields
    (resumed, machine, cancelled...). Mutates data (the caller writes it)."""
    data.setdefault("stage_history", []).append({"stage": stage, "at": now()} | fields)


def mark_stage(path, stage: str) -> None:
    """add_stage() to a job file, in its own locked transaction. No-op if
    the file is gone -- archived from Farm monitoring meanwhile (it raised
    "'NoneType' object is not subscriptable")."""
    with locked_json(path) as box:
        if not box["data"]:
            return
        add_stage(box["data"], stage)
        box["action"] = "to_write"
