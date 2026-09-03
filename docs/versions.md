# Versions: wip and stable

*[← Documentation index](README.md) · [Version française](versions_fr.md)*

---

Publishing = tagging `-stable`, not a separate file to overwrite. Links point to a specific stable version; moving to a more recent one is an explicit action (see [Link vs Append](linking.md)).

- **`-stable` is the only tag with real pipeline behavior** (forces read-only on open, guards on save). Other tags you add to the config (`tocheck`, `tovalid`...) are purely informational.
- **Opening a read-only file** (`-stable`, `always_read_only`, or already read-only earlier this session) flags it silently — no popup, just the top bar's red READ-ONLY indicator (see [Interface](interface.md)), click it any time for why and a one-click Increment. Opening a file another machine already has locked is the one case that still interrupts with a popup right away, since who's holding it is live information the indicator can't carry on its own.
- **Auto-version on open**: if the opened file is the latest version *and* dates from before today, the addon silently increments it (no work lost, no interruption). If a more recent version than the one opened already exists, a popup proposes branching from this older file (`branch_from`) instead of incrementing into a void.
- **Increment / mark stable**: same operator (`pipeline.increment_version`), with or without a tag. The popup pre-checks "worked this session" from whatever's already toggled in the asset/shot panel (see [Sessions and locking](sessions-and-locking.md)), and the departments likely finished (validated at the last stable, untouched since). The sidebar hides "Mark as stable" when the open file already is the stable version — tagging it stable again would be a no-op.
- **Save guard** (Ctrl+S, shortcut overridden by the addon): if the file is locked read-only for this session — because it's `-stable`, because another machine already has it open, or because `always_read_only` is on — the direct save is intercepted and replaced with a popup (Save / Increment / Cancel on a stable file, Save & Increment / Cancel otherwise).

---

## Data structures: `.wipmeta` and `.stablemeta`

Every asset/shot has a `.pipeline/` folder next to its `.blend` files, holding one of these per version (see [Tracking & reviews](tracking-and-reviews.md) for the third file in that folder, `tracking.json`).

**`.pipeline/ch_bob_v004.wipmeta`** — one per work version:

```json
{
  "file": "assets/ch/ch_bob/ch_bob_v004.blend",
  "created_from": "assets/ch/ch_bob/ch_bob_v003.blend",
  "creation_mode": "manual_incrementation",
  "created_at": "2026-03-25T16:00:00",
  "edited_at": "2026-03-25T18:42:00",
  "departments_worked": {"84213_a1b2c3d4e5f6": ["rigging"]},
  "linked": [
    {"file": "library/mat/mat_wood-dark/mat_wood-dark_v002-stable.blend", "type": "MATERIAL", "name": "wood_dark"}
  ]
}
```

`creation_mode` is `creation` (first version), `auto_increment` / `branch_from` (proposed on open), or `manual_incrementation`. `departments_worked` is indexed by session (`pid_machine_id`) so it aggregates correctly even if a file is worked on by several people the same day.

<br>

**`.pipeline/ch_bob_v005-stable.stablemeta`** — one per version marked stable:

```json
{
  "file": "assets/ch/ch_bob/ch_bob_v005-stable.blend",
  "created_from": "assets/ch/ch_bob/ch_bob_v004.blend",
  "created_at": "2026-03-26T10:00:00",
  "departments_validated": {"modeling": true, "rigging": true, "texturing": false},
  "linked": [],
  "conflict_warning": ""
}
```

This is the file that serves as the reference point: the whole "what's been touched since the last stable" calculation (shown in the Tracking panel and project monitoring) compares the `.wipmeta` files newer than `created_at` against this `departments_validated`.

---

**See also**: [Rendering (farm)](farm.md) for how a job's output relates to the file's version · [Design choices](design.md) for why this is JSON instead of a database.
