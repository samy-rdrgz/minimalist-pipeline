# Minimalist Pipeline

*[Version française : README_fr.md](README_fr.md)*

Lightweight pipeline Blender addon for solo artists and small teams (2-5), full Blender, no server to install. FFmpeg is the one optional external dependency — only needed for the render farm's video compilation and image-check stages, everything else works without it.

**Author**: Samy Rodriguez · **Version**: 1.0.2 · **Blender**: 4.2+

---

## Table of contents

- [At a glance](#at-a-glance)
- [Who it's for, and why](#who-its-for-and-why)
- [Installation](#installation)
- [Concepts](#concepts)
- [Interface](#interface)
- [Design choices](#design-choices)
- [Known current limitations](#known-current-limitations)
- [Documentation](#documentation)

---

## At a glance

- Create an asset or shot and type a name — the addon builds the right filename, folder, and tracking file for you.
- Work and save (Ctrl+S) like you always do — versioning and the `-stable` safety net run underneath, only interrupting you when a real decision is needed.
- Submit a render from any machine that has the project open — no farm software to install, no server to configure.
- Everything lands as plain, human-readable JSON next to your files — nothing locked away in a database only the addon can read.

New here? **[Getting started](docs/getting-started.md)** walks through a first project click by click, no jargon. The sections below go deeper, concept by concept.

---

## Who it's for, and why

**Target**: solo 3D artists or small teams, without the budget/time for Shotgrid or a studio pipeline.

**Problem solved**: the gap between artisanal chaos (`finalversion_therealone02.blend`) and heavyweight studio machinery. The addon structures *storage* — naming, folders, versions, light locking — without imposing an artistic workflow.

**Philosophy**:
- **Detect → Inform → Propose → Execute if validated.** The addon never does anything silently, but never blocks work either. Every automation goes through a popup with an explicit choice.
- **Warning, not blocking.** Even on a `-stable` file, the artist can overwrite it if they really decide to.
- **Readable without the tool.** Everything is stored as human-readable JSON next to the `.blend` files. If the addon disappears tomorrow, filenames and history still make sense.

---

## Installation

Standard Blender addon: `Edit > Preferences > Add-ons > Install`, select the folder (or its zip), enable. `blender_manifest.toml` at the root describes the addon for Blender's Extensions platform (4.2+) — `bl_info` in `__init__.py` remains the source for the legacy addon system; the two version numbers have to be kept in sync manually.

**Actual minimum: Blender 4.2**, not 4.1: several panels and popups (`farm_ops.py`, `project_ops.py`, `tracking_ops.py`, `addon_data.py`, `file_panel.py`) use `UILayout.separator()`'s `type` parameter, added in 4.2 ([release notes](https://developer.blender.org/docs/release_notes/4.2/user_interface/), [PR #117310](https://projects.blender.org/blender/blender/pulls/117310)) — a real 4.1 install raises `TypeError` on the first panel that draws one. `invoke_props_dialog`'s `confirm_text` parameter (added in 4.1, [PR #117528](https://projects.blender.org/blender/blender/pulls/117528)) is a second dependency already satisfied by the 4.2 floor, not the binding one. Actively tested on 5.2 — not verified on a real 4.2–5.1 install.

Settings available in `Preferences > Add-ons > Minimalist Pipeline`:

| Setting | Effect |
|---|---|
| **User name** | Name used in logs and metadata (seeded with a locally-generated placeholder name on first launch, freely editable). |
| **Silent auto-increment** | On the first file open of the day (already on the latest version), increment silently instead of asking for confirmation. |
| **Auto-launch worker** | This machine automatically becomes a render worker when a project becomes active (on Blender startup, or when switching projects). |
| **Always open read-only** | Forces all project files to open read-only, regardless of their lock state. Useful on a review/playblast machine. |
| **Experience level** | *Beginner* shows short inline explanations of pipeline concepts (versions, stable, links...) next to the relevant buttons and popups; *Advanced* hides them. First launch also shows a one-time welcome popup, reopenable anytime from the main panel header's "?". |

Session, locking, library-update checks, and read-only gating always run whenever a project is active — there's no toggle to pause them as a block. *Silent auto-increment* only controls whether the day's-first-open version proposal is silent or asks for confirmation first.

---

## Concepts

Overview below — each links to a dedicated page with the full explanation, edge cases, and the JSON schema behind it.

- **[The project, naming, batch creation](docs/project-and-naming.md)** — a project is a folder with `config/project_config.json`; the file's prefix routes it to the right folder automatically. Naming is `{prefix}_{name}_v{number}[-{tag}]`, rebuilt from config, never hand-typed. Assets/shots can also be bulk-created from a CSV.
- **[Shot blocks (multishot)](docs/multishot.md)** — one file for camera cuts on a single continuous piece of animation that can't be split without breaking the seams. Splits automatically into one render job per shot.
- **[Versions: wip and stable](docs/versions.md)** — publishing = tagging `-stable`, not overwriting a file. Auto-increment on open, and a save guard keep you from silently clobbering a stable version.
- **[Sessions and locking](docs/sessions-and-locking.md)** — who has what open, right now; locks that self-expire instead of needing a central server to arbitrate.
- **[Tracking & reviews](docs/tracking-and-reviews.md)** — notes/todos/rtk per asset/shot, per-department validation, two project-wide monitoring popups.
- **[Link vs Append](docs/linking.md)** — link is the pipeline's native mode; an append gets detected and offered a cleanup.
- **[Rendering (farm)](docs/farm.md)** — a monitor + any number of workers coordinate render jobs over the shared project drive, no SSH or server required.

---

## Interface

All panels live in the 3D viewport sidebar (`N` > **Pipeline** tab) — Project, Asset, Shot, Tracking, Farm — plus a project-wide monitoring popup, a farm dashboard, and a "Pipeline" menu in the top bar for quick access without opening the sidebar. Full panel-by-panel reference: **[docs/interface.md](docs/interface.md)**.

---

## Design choices

A handful of deliberate calls shape the whole addon — everything in JSON rather than a database, one file per asset instead of one per department, push-pull coordination over the shared drive instead of SSH, work duration logged but never shown per person, and more in the same spirit. The reasoning behind each: **[docs/design.md](docs/design.md)**.

---

## Known current limitations

- Only Ctrl+S is guarded against saving over a read-only/stable file — the File menu's Save button and the top bar's save icon bypass the check entirely. A "READ-ONLY" warning in the top bar mitigates this (visible, doesn't block, click it for why and a one-click Increment).
- A NAS/drive disconnecting *while Blender is already running* isn't fully handled — only the startup check is.
- Multishot's Preview and Edit block structure aren't yet exercised in a real create → render → preview → branch run.
- Per-shot casting JSON (roadmap) isn't implemented yet.

Full list with details: **[docs/limitations.md](docs/limitations.md)**.

---

## Documentation

| | |
|---|---|
| **[docs/](docs/README.md)** | One page per theme above, in more depth, cross-linked. Start here for anything beyond a quick overview. |
| **[CODE.md](CODE.md)** | Dev-facing reference: module architecture (`lib/`, `farm/`, `operators/`, `panels/`), code patterns, roadmap v0.2–v0.4+. |
| **[graph.md](graph.md)** | Exhaustive diagram of every handler/timer/operator: what triggers what, in which order, under which conditions. |
| **[NOTES.md](NOTES.md)** | Dev design notes, feature by feature — the *why*, rejected alternatives, and architecture history that a code comment is too short to hold. Currently covers multishot; more sections land here over time. |
