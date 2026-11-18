"""Legacy: the 1.x forms still written beside the 2.0 ones, so a 1.1.x
working on the same project keeps reading it (a team updating one machine
at a time, or going back to 1.1.10).

Only one so far: a stable's done departments, "departments_done" since
2.0, "departments_validated" in 1.x (the same {department: bool}).
- stable_written(): called on every .stablemeta 2.0 writes, the old key
  kept equal to the new one.
- stable_read(): called on every .stablemeta 2.0 reads. 2.0 always writes
  both equal, so the two differing means a 1.x wrote it last (it only knows
  the old key): the old key's values win.

To drop it once no 1.x is left: delete this file and its calls
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
