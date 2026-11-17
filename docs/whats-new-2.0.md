# What's new in 2.0

*[← Documentation index](README.md) · [Version française](whats-new-2.0_fr.md)*

Everything that came since 1.0.0, in short. The details, version by version, are in the CHANGELOG.

---

## Before you update

- **Update every machine at once.** 2.0 writes its data differently: a 1.x opening a project moved to 2.0 would get it wrong. The farm turns away a machine left on another version by itself, with a clear message.
- **Run *Migrate old data* once per project** (Edit project > Maintenance). It shows what it will change before writing anything, and backs up every file it changes under `backup/` at the project's root. It also offers to rename the render presets whose name doesn't say which department they serve.

---

## The project's page, in the browser

The big change in 2.0: **you follow the project in a web page**, instead of the Project monitoring and Farm monitoring windows.

- ***Monitor in browser*** (Project panel, Pipeline menu): Blender serves the project's page to your browser, always up to date. What you do there (validate, add a retake, write a note, reply, assign, add a shot) is saved in the project at once, under your name.
- **The list of assets and shots**: where each department stands, open retakes, renders to check, what's on the farm. Filters by department, retakes, open notes, "my work". A click on a file opens its panel: its notes, its renders to watch (the frame shown, the notes placed on it), its links, and a button to open it in Blender.
- **Breakdown**: progress per sequence and per department, as %, states, counts or retakes, with the project's schedule.
- **Farm tab**: the renders and the machines; send a file to render, set its priority, cancel, retry, archive; see which machine rendered which frame and how long is left.
- **Light / dark theme**, and the page fits tablets and phones.
- **Remote access, secondary**: someone gets the same page through a QR code or a link, valid from an hour to a week, under their name and role; nothing opens on your machine, and you cut the access in a click. Combined with a VPN (Tailscale, for example), it gives easy remote monitoring of the project and the farm from outside the studio.

## Reviews

- **The production snapshot**: a self-contained HTML page of the project (thumbnails, videos, notes, progress) to send to someone outside the studio. It opens without Blender and without a network, on a tablet too.
- **Review in the page itself**, live or snapshot: ✓ / ✕ per department, retakes with their frames, notes, replies, "mark fixed". From a snapshot the review downloads as one file, and *Import review* applies it to the project (several at once if needed).
- **Done and validated**: the team ticks *Done* when a department is finished; validation roles (sup, prod…) then validate. A role's notes and retakes are marked as such.
- **Change the departments of many files at once** (every shot, a sequence, a prefix, those that already have a given department).

## The team and tracking

- **The team** (Edit project > Team): pick your name from the list, assign a department to someone (also at creation or by CSV), and the "Me" filter shows your work. Nothing measures anyone's time, on purpose.
- **On hold / Cancelled**: pause or drop a shot, with a reason, without deleting it.
- **Stages**: an order between departments (layout > anim > lighting), to know what waits on what.
- **Schedule**: the project's start, end, worked days and days off, shown with the progress.
- **Delete** a shot or an asset cleanly, and **Clean old renders** to free space while keeping the renders that matter.
- Dates keep their time zone: someone working from elsewhere sees the right times.

## The farm

- **More reliable**: a machine dropping out no longer fails the render, a stuck render moves to another machine, a frame taking far too long is caught, bad frames are rendered again, and a Blender crash no longer leaves jobs to resubmit by hand.
- **Renders cut into chunks of frames**, shared between free machines, with a priority (the highest takes machines from the lowest) and a maximum of machines per job.
- **Renders to check**: each finished render waits to be watched. *Checked* can validate departments at the same time and send the render to editing.
- **Renders by department**: the render preset says which department it serves (`animation_hd`, `lighting_hd`…), and each department has its own renders to check.
- **Sequence previews**: the shots' videos put end to end, compiled on a free machine.
- **Rushes for editing**: *Push rushes to editing* copies each shot's latest video into `editing/rushes/` under a fixed name: the edit picks up the new version with no relinking.
- **Sound in the renders**: the shot file's own sound (sequencer, speakers) goes in its video and in the sequence previews.
- **A light copy** of each video for the browser, and H.265 plays on phones and tablets too.
- A worker keeps its machine awake while it renders, and starts a few seconds after Blender when set to.
- Rendering an asset or a library file works too.

## In Blender

- **Ctrl+Alt+S** (Save Incremental) runs the addon's increment inside a project.
- Right-click menus, shortcuts you can change in the preferences, a "?" help beside the project settings' fields.
- A welcome window to get started, and the pipeline log in a window of its own.
- The sidebar no longer lags on a network drive.
- Batch shot creation by CSV takes multishot blocks and assignees.

## Removed

- The **Project monitoring** and **Farm monitoring** windows: the project's page replaces them. Blender's sidebar keeps everything else.
- The **review spreadsheet** (.xlsx): the review is made in the page.
- Render presets in `.json`: only Python presets remain (*Migrate old data* converts the old ones).
