"""The project's schedule: working days, and where the production should
be by now (the snapshot's pace). Pure date arithmetic, no bpy."""

import math
from datetime import date, datetime, timedelta

from .core import json_get
from .errors import PipelineError


def parse_day(value: str) -> date:
    """A date typed day first -- 20/10/2026, 20-10-2026, 20.10.2026 -- or
    year first (2026-10-20, 2026/10/20). Raises PipelineError otherwise."""
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise PipelineError(f"'{value}' is not a date (DD/MM/YYYY).")


# ISO weekday numbers (1 Monday .. 7 Sunday) a schedule works by default.
WORK_WEEK = (1, 2, 3, 4, 5)


def project_schedule(config: dict) -> dict | None:
    """The project's "snapshot.schedule" (Edit project): {"start", "end",
    "days_off" (dates), "worked_days" (ISO weekday numbers, WORK_WEEK when
    unset)}. None unless start and end are both set, in order, and some
    day of the week is worked."""
    raw = json_get(config, "snapshot.schedule", {}) or {}
    try:
        start = date.fromisoformat(raw["start"])
        end = date.fromisoformat(raw["end"])
    except (KeyError, TypeError, ValueError):
        return None
    if end < start:
        return None
    days_off = set()
    for day in raw.get("days_off") or []:
        try:
            days_off.add(date.fromisoformat(day))
        except (TypeError, ValueError):
            pass
    try:
        weekdays = sorted(
            {int(d) for d in raw.get("worked_days", WORK_WEEK)} & set(range(1, 8))
        )
    except (TypeError, ValueError):
        weekdays = list(WORK_WEEK)
    if not weekdays:
        return None
    return {"start": start, "end": end, "days_off": days_off, "worked_days": weekdays}


def _is_working_day(schedule: dict, day: date) -> bool:
    """Whether day counts in the schedule: a worked weekday, not a day off."""
    return (
        day.isoweekday() in schedule["worked_days"] and day not in schedule["days_off"]
    )


def working_days(schedule: dict, start: date, end: date) -> int:
    """The schedule's working days from start to end, both included: its
    worked days of the week, its days off left out -- a spreadsheet's
    NETWORKDAYS.INTL(). 0 when end is before start."""
    count, day = 0, start
    while day <= end:
        count += _is_working_day(schedule, day)
        day += timedelta(days=1)
    return count


def nth_working_day(schedule: dict, n: int) -> date:
    """The schedule's n-th working day (1: the first), its end past the last."""
    count, day = 0, schedule["start"]
    while day < schedule["end"]:
        count += _is_working_day(schedule, day)
        if count >= max(n, 1):
            return day
        day += timedelta(days=1)
    return schedule["end"]


def schedule_progress(schedule: dict, today: date, progress: dict) -> dict:
    """meta["schedule"]: the schedule (ISO dates) and where the project
    should be on today at an even pace -- "expected" (0..1), its working
    days so far, today included ("elapsed_days"), over all of them
    ("total_days"). "at": per section of progress ({kind: Done or None}),
    the day an even pace reaches its Done and how many working days ahead
    (+) or behind (-) of today that is."""
    start, end = schedule["start"], schedule["end"]
    total = working_days(schedule, start, end)
    elapsed = working_days(schedule, start, min(today, end))
    at = {}
    for kind, done in progress.items():
        if done is not None:
            days = done * total
            at[kind] = {
                "date": nth_working_day(schedule, math.ceil(days)).isoformat(),
                "days": round(days - elapsed),
            }
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "worked_days": list(schedule["worked_days"]),
        "days_off": sorted(d.isoformat() for d in schedule["days_off"]),
        "expected": elapsed / total if total else float(today >= end),
        "elapsed_days": elapsed,
        "total_days": total,
        "at": at,
    }
