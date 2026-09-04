# Sessions and locking

*[← Documentation index](README.md) · [Version française](sessions-and-locking_fr.md)*

---

On opening a file from the active project (outside background mode), the addon:
1. Writes `config/.sessions/.session_{pid}.json` — who has which file open, since when, last ping.
2. Attempts a lock on the `.blend` itself (`.{name}.blend.lock`); if already held, the file opens read-only with a popup showing who holds it.

As long as the file stays open normally (not read-only), the 30s heartbeat refreshes both the session and this lock — so it won't expire while the session is active. Lock staleness is checked against 90s (3x the heartbeat interval — a margin so a single missed/delayed beat can't get a still-live lock stolen by another machine). The lock is, however, never *explicitly* released on close: it expires on its own (90s without a heartbeat) if Blender crashes or the addon is disabled without quitting Blender — which remains how an abandoned lock frees itself without a central arbiter to query. The general rationale for this expiration-based approach (no central server) is in [Design choices](design.md).

Every session end is logged to its own `config/logs/sessions_log.jsonl`, work duration included — kept separate from the general pipeline log so it stays simple to parse for time tracking. There's no separate session-start line: everything it could tell you (who, which file, when) is already recoverable from the end line alone (its timestamp minus the duration), so logging both would just be two lines for one fact. Switching to a different file, or quitting Blender outright, closes the previous file's session cleanly either way. See [Design choices](design.md#work-duration-is-logged-never-surfaced-per-person) for what this log does and doesn't get used for.

Which departments were worked on isn't asked for through a popup on close/quit anymore — a modal dialog queued that late isn't guaranteed to render (Blender is already tearing down its window manager by the time `exit_pre` fires). Instead, the asset/shot panel shows a toggle button per required department right on the file, writable at any point during the session; each click writes straight to that version's `.wipmeta` (see [Versions: wip and stable](versions.md)). Nothing is assumed worked on by default — an untouched file simply records nothing. Hidden entirely on a read-only file (a `-stable` version, or the "always read-only" profile setting): a stable version has no `.wipmeta` of its own to write to, only a `.stablemeta`.

---

**See also**: [Versions: wip and stable](versions.md) for how the "worked this session" toggles feed the increment/mark-stable popup · [Rendering (farm)](farm.md) for the worker/monitor heartbeats, which follow the same expiration logic.
