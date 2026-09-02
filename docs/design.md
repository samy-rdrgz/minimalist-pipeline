# Design choices

*[← Documentation index](README.md) · [Version française](design_fr.md)*

---

## Everything in JSON, no database

No service to install or maintain. Any machine that can already open the project (has access to the shared folder) can read/write the pipeline without extra configuration. Readable and diffable without the addon — a `tracking.json` or a `.wipmeta` makes sense opened in a text editor. Writes go through a file lock (`acquire_lock`/`locked_json`) + atomic write (temp file then `os.replace`), to stay safe if two machines write at the same moment on the same NAS.

<br>

## Single file per asset, not one per department

An early version split an asset across one file per department (model, rig, texture...), linked together, with checksums (vertex/face/volume counts) to catch a downstream file going silently stale when whatever it depended on changed underneath it — the standard "who owns what, and did it change" problem a department-split pipeline has to solve for itself. That model was dropped for one file, one version lineage, per asset (see [Project structure, naming, batch creation](project-and-naming.md)): whoever has it open owns the whole thing for that session, and a link always points at one specific `-stable` version, never a moving target.

The checksums went with it, and not as a loss: with a single file and a single owner, there's no second file left to fall out of sync with — the question a checksum exists to answer ("did the thing I depend on change since I last looked") stops having an object to be asked about. Removing the condition that created a problem, rather than adding a mechanism to detect it, is the shape most of the choices on this page take.

<br>

## No SSH, "push-pull" coordination over the shared drive

The render farm never connects to any machine directly — no SSH keys, no IP to know, no port to open. All coordination goes through JSON files in `config/.farm/`, on the same network share that already hosts the project:

- The monitor **pushes** a render request into `queue/requests/request_{job}_{uuid}.json`, targeting a specific worker's uuid.
- Each worker **pulls** (polls its own timer) the requests targeting it and launches the render locally.

Direct consequence: any machine that can open the project can become a worker or monitor with one click, without a network admin touching anything. The price to pay: it's polling (latency on the order of ten seconds between stages), not real-time — acceptable for a team of 2-5, not designed to scale to a real studio farm. See [Rendering (farm)](farm.md) for the mechanics this enables.

The scope is also narrower than "render farm" might suggest, on purpose: each job is one machine finishing one full frame on its own — never several machines cooperating on the *same* frame (tile merging, split GPU passes). That's a simpler problem than what a dedicated multi-GPU render-distribution tool solves, and it's why building it in-house was worth it here instead of depending on one: no frame-level synchronization, no partial-result merging, nothing that needs its own protocol. If this ever grows into more than the addon around it can carry, splitting it into its own extension is the planned escape hatch — a choice made ahead of time, not one forced by outgrowing it unprepared.

<br>

## Central path table, not hand-built paths

Every file and folder inside a project — an asset's `.blend`, its `tracking.json`, a render output folder, a session lock, a farm queue entry — is resolved through one lookup table, never string-concatenated ad hoc at the point of use. Combined with the naming regex being rebuilt from config rather than hardcoded (see [Project structure, naming, batch creation](project-and-naming.md)), the project's actual shape — folder names, prefixes, digit counts — is data read from `project_config.json`, not logic scattered across the addon. Renaming a folder or changing a prefix in the config takes effect everywhere at once; nothing needs hunting down and updating by hand.

<br>

## One error type, and background code is never allowed to raise

Every failure in the pipeline's core logic raises the same kind of error (a message + a severity), and each operator — an actual button or menu click — catches it once, logs it, and reports it through Blender's status bar or a popup. That's what "never act silently" (see [Who it's for, and why](../README.md#who-its-for-and-why)) means in code, not just in the popups: it's enforced at every call site, not left to chance feature by feature.

The rule cuts the other way too. Code that runs *without* a user action behind it — a file-open handler, a background timer, a panel's `draw()` — has no such catch point: Blender gives it no feedback channel, and an exception inside a timer callback silently kills that timer forever, with nothing telling you it stopped. Functions reachable from those contexts are written to never raise: they catch internally, log, and fall back to a safe default instead of surfacing an error nobody would see.

<br>

## Locking by expiration, not a central server

File locks (JSON, sessions, monitor, the `.blend` files themselves): a sibling `.lock` file with a timestamp, considered stale after a fixed delay (`LOCK_STALE_SECONDS`). No central arbiter to query, no single point of failure — if a machine crashes while holding a lock, it frees itself automatically after expiring instead of blocking others indefinitely. Locks held for a long time (session, an open `.blend` file) are refreshed periodically by the heartbeat so they don't expire during legitimate use; the ones that aren't are deliberately very short-lived (the time of one JSON write). See [Sessions and locking](sessions-and-locking.md) for this applied to file sessions.

<br>

## One single interaction pattern for everything: `PipelineAction`

Every detection (dated file, save on a stable...) builds the same object — title, message, severity, list of choices (label + callback, optionally a tooltip) — displayed by a single popup operator. No ad-hoc UI per feature: adding a new detection doesn't require new display code. Exception: the two proposals fired directly on file open (read-only notice, outdated library) use Blender's native confirm dialog instead — the shared popup only auto-closes reliably when opened from a real operator (a button, a keymap), not from a handler.

Backing out of a popup isn't a silent escape hatch either: dismissing one without picking a choice (Escape, clicking away) still runs whatever cleanup a real choice would have — releasing a lock taken for the save that triggered the popup, for instance — instead of leaving something half-done because the artist didn't explicitly pick "Cancel".

<br>

## Work duration is logged, never surfaced per person

Every session start/end writes its duration to `sessions_log.jsonl` (see [Sessions and locking](sessions-and-locking.md)) — the data exists, in plain JSONL, per machine and user name. Nothing in the addon reads it back. No panel, no dashboard, no per-person total, anywhere.

That's deliberate, not unfinished. Time tracking between people who trust each other creates a surveillance dynamic even without anyone asking for it or any hierarchy behind it — the simple existence of a visible "Alice: 24h32, Bob: 18h15" changes how people work, whether or not anyone ever actually looks at it that way. The addon's target (2-5 people, often friends or a small studio) is exactly the setting where that cost is highest and the upside lowest — nobody here needs a coordinator's dashboard.

There's a second, independent reason beyond the social one: the raw duration is solid (heartbeat-based wall-clock time), but attributing it to a *department* isn't — that needs the "worked this session" toggles (see [Sessions and locking](sessions-and-locking.md)), which are self-reported, optional, and trivially left unchecked mid-session. A breakdown built on that wouldn't just invite the dynamic above; it would dress up soft, self-toggled data as an objective per-department number nobody actually verified.

The log stays anyway, because logging costs nothing and forecloses nothing: a future per-person, opt-in view is still possible without changing what's already on disk. What's ruled out is a default, always-on breakdown nobody asked to see, appearing as a side effect the day someone adds a panel that reads the file. If that panel ever gets built, it has to be an explicit, opt-in choice — never a side effect of the data already being there.

What isn't ruled out: a plain **total** per asset/shot — every session's duration summed across everyone who touched it, no name attached to any part of the number. That sidesteps both objections above at once: nobody is singled out (no surveillance dynamic to create), and nothing is attributed to a department (no self-toggled data pretending to be precise) — it's just "this took N hours, total, across its whole history", which is real, useful for sanity-checking scope, and already fully computable from `session_end` entries (`filepath` + `duration_seconds`) grouped by asset/shot. Not built yet, but nothing above argues against it.

<br>

## Solo-first, team-compatible

Everything works with a single artist on a single machine without any notion of "team" coming into play — sessions, locks, and the farm are layers that activate themselves as soon as a second machine touches the same project, never a separate checkbox at install time.

---

**See also**: [Sessions and locking](sessions-and-locking.md) · [Rendering (farm)](farm.md) · [Project structure, naming, batch creation](project-and-naming.md) for the JSON this all sits on top of.
