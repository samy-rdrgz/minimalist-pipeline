"""Legacy: the 1.x forms still written beside the 2.0 ones, so a 1.1.x
working on the same project keeps reading it (a team updating one machine
at a time, or going back to 1.1.10).

Two so far, the same way:
- a stable's done departments: "departments_done" since 2.0,
  "departments_validated" in 1.x (the same {department: bool}) --
  stable_written() / stable_read();
- a version's sessions: "sessions" since 2.0, "departments_worked" in 1.x
  (the same {session id: {"departments", "saved_at", "by"}}) -- the name
  a .stablemeta gives the work since the stable before (a list), so
  renamed in the .wipmeta -- wip_written() / wip_read().
_written(): called on every such file 2.0 writes, the old key kept equal
to the new one. _read(): called on every one 2.0 reads. 2.0 always
writes both equal, so the two differing means a 1.x wrote it last (it
only knows the old key): the old key's values win.

Kept through 2.1 and 2.2, no longer written from 2.3 (announced in the
CHANGELOG): a team has two minor versions to update every machine.
To drop it: delete this file and its calls
(grep "legacy."), and tests/test_migration.py's legacy part.
"""

V1_DONE = "departments_validated"
DONE = "departments_done"


def stable_read(data: dict | None) -> dict | None:
    """data (a .stablemeta's) with "departments_done" as last written, by a
    2.0 or a 1.x. Changed in place, returned."""
    if not isinstance(data, dict):
        return data
    old = data.get(V1_DONE)
    if isinstance(old, dict):
        new = data.get(DONE)
        if not isinstance(new, dict):
            data[DONE] = dict(old)
        elif new != old:
            data[DONE] = {**new, **old}
    return data


def stable_written(data: dict) -> dict:
    """data (a .stablemeta about to be written) with the 1.x key beside the
    new one, equal. Changed in place, returned."""
    if isinstance(data.get(DONE), dict):
        data[V1_DONE] = dict(data[DONE])
    return data


V1_SESSIONS = "departments_worked"
SESSIONS = "sessions"


def wip_read(data: dict | None) -> dict | None:
    """data (a .wipmeta's) with "sessions" as last written, by a 2.0 or a
    1.x (a session it added, or saved again: its entry wins). Changed in
    place, returned."""
    if not isinstance(data, dict):
        return data
    old = data.get(V1_SESSIONS)
    if isinstance(old, dict):
        new = data.get(SESSIONS)
        if not isinstance(new, dict):
            data[SESSIONS] = dict(old)
        elif new != old:
            data[SESSIONS] = {**new, **old}
    return data


def wip_written(data: dict) -> dict:
    """data (a .wipmeta about to be written) with the 1.x key beside the
    new one, equal. Changed in place, returned."""
    if isinstance(data.get(SESSIONS), dict):
        data[V1_SESSIONS] = dict(data[SESSIONS])
    return data
