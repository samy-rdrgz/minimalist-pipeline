# Minimalist Pipeline 2.0

The biggest release so far: the project now lives in a **web page** that Blender serves, always up to date, where the whole team follows the work, reviews it and drives the farm. Blender keeps the tools to work; the page becomes the place to look, decide and comment.

## Before you update

- **Update every machine at the same time.** 2.0 stores its data differently, and a 1.x machine would read a 2.0 project wrong. The farm refuses a machine left on another version and says so.
- **Run *Migrate old data* once per project** (Edit project › Maintenance). It shows what it will change before writing anything and backs up every file it touches. It can also rebuild the project's progress history from before 2.0.

---

## The project's page

***Monitor in browser*** (Project panel, Pipeline menu) opens the project in your browser. What you do there (validate, write a retake, reply, assign, add a shot) is saved into the project at once, under your name. It opens straight away, filling in while the project is read.

### The list of shots and assets

- Each department's state at a glance, with the open retakes, the renders to check and what's on the farm.
- Filters: by department, retakes, open notes, to validate, *To check*, in the farm, outdated render, *Me* (your work), tracked only.
- A **Renders** column: the farm job with its frames, a render waiting to be checked, a render that's out of date.
- A quieter screen: figures, words and buttons that aren't needed at rest show up when the mouse passes over them, with a soft animation.
- **What's new** (the bell): notes, retakes, validations and renders that arrived while the page was open.
- **Search everything** (Ctrl+K): names, descriptions, notes, replies, assignees, departments, render presets.

### A file's panel

- **The player**: the render's video, its timeline with the notes placed at their frames, frame by frame, A/B comparison of two versions at the same frame, a version menu, sound.
- **Watch large**: the video, the departments and the notes side by side. In full screen, the panel lies over the video, blurred behind; a tab folds it away and another hides the header.
- **Notes**: retakes, remarks and to-dos, with their replies. Notes sent together in one review are grouped in one box under their author. Filter them by open / at a frame / all, and by the version they were written on.
- Clicking a note's frame also moves **Blender** to that frame when it has the file open.
- **Renders to check**: each render waiting to be watched, with *Watch* (that version in the player) and *Checked…*, which asks which departments the render shows done or validated and whether to send its video to editing. An animation playblast and a lighting render are checked separately, by the people concerned.
- **Versions**: the chain of the file's versions, who saved them, when, which departments they worked on. **Render history**: every render, by version, department, preset, who launched it and how it ended.
- **Which machine…**: give a render version and a frame, learn which machine rendered it.
- Open the file in Blender, its folder, its render folder, or the full video in this machine's player. If its shot or asset is already open in another Blender, the page says who and where before opening.
- **Push to the edit**: any render, WIP or stable, into `editing/rushes/`, replacing the previous one without breaking the edit's link.
- **Linked files**: what the file links and who links it, with old links shown, and *Update links* to move them to the latest version.
- The file's work time, to the half hour.

### Breakdown

- Progress per sequence and per department, as percentages, states, counts or retakes, beside the project's schedule.
- **Over time**: Done and Validated, day after day.
- **Activity**: the files worked and the hours spent each day, the team together, never per person.
- **Projection**: where the current pace leads, in months, as a cone that widens with uncertainty, looking ahead only a quarter of the time already spent.
- **Export…**: the whole project as a spreadsheet.

### To do

- What's left to work on or to validate, file by file, yours by default. *Oldest first* puts the files waiting the longest on top. *Copy* gives it as text.

### Reviewing

- Start a review, then ✓ / ✕ per department, retakes with their frame or range, remarks, to-dos, replies, *Mark fixed*, *Mark done*, *Reopen*.
- In *Watch large*, write as you watch: Enter adds the note at the current frame; ranges in one key; tick off a retake or a to-do from its line.
- Your own notes can be edited or taken back after sending.
- **Departments of several files** at once: every shot, a sequence, a prefix.
- *Validate the done* in one click.

### The Farm tab

- Launch or stop the farm, send a file or a sequence to render, set priorities, cancel, retry, archive.
- Which machine renders which frame, and the time left.
- **Machines**: each machine, the project files open in its Blenders, and what its worker is doing.
- *Push rushes…*: every sequence's and asset's latest render into the edit at once.

### Everywhere

- **Light or dark theme**, English or French, and a layout for tablets and phones. On a phone the page goes full screen at the first touch, with Review, To do and Farm tabs, swipe between shots, and retakes, remarks and to-dos written there too.
- **Share** the page with someone through a QR code or a link, valid from an hour to a week, under their name and role. Nothing ever opens on your machine from a guest's page, and you cut the access in a click. With a VPN, it makes remote follow-up of the project and the farm easy.
- A guided tour for beginners.

---

## The snapshot

- A self-contained page of the project (thumbnails, videos, notes, progress) to send outside the studio. It opens without Blender and without a network, on a tablet too.
- Reviewed in the page itself; the review downloads as one file, and *Import review* applies it to the project. An imported review can be reverted.

## Team and tracking

- **The team** (Edit project › Team): pick your name, assign departments to people (also at creation or from a CSV). Nothing measures anyone's time, on purpose.
- **Done and validated**: the team marks a department *Done*; validation roles (sup, prod…) validate it. A department can be marked done again without a new stable version.
- **On hold / Cancelled**: pause or drop a shot with a reason, without deleting it.
- **Stages**: an order between departments (layout › animation › lighting), so the page knows what waits on what.
- **Schedule**: start, end, worked days and days off, shown with the progress.
- **Delete** a shot or an asset cleanly; **Clean old renders** frees space while keeping the ones that matter.
- Dates keep their time zone: someone working from elsewhere sees the right times.

## The farm

- **More reliable**: a machine dropping out no longer fails a render, a stuck render moves to another machine, a frame taking far too long is caught, bad frames are rendered again, a Blender crash no longer leaves jobs to resubmit.
- Renders cut into **chunks of frames** shared between free machines, with priorities and a maximum of machines per job.
- **Renders by department**: each render preset says which department it serves, and each department has its own renders to check. Render presets can be renamed everywhere at once.
- **Render here**: render the open file on this machine, right now, outside the farm's queue: as a playblast, or through the 3D viewport with its overlays (rigs…).
- **Sequence previews**: the shots' videos end to end, compiled on a free machine.
- **Sound** in the renders and the sequence previews.
- A **light copy** of each video for the browser; H.265 plays on phones and tablets.
- A worker keeps its machine awake while rendering and can start by itself a few seconds after Blender.
- Assets and library files render too.

## In Blender

- **Ctrl+Alt+S** (Save Incremental) uses the pipeline's own versioning inside a project.
- Right-click menus, shortcuts you can change, and a "?" help beside the project settings' fields.
- A welcome window to get started; the pipeline log in its own window.
- The sidebar no longer lags on a network drive.
- Batch shot creation from a CSV handles multishot blocks and assignees.

## Removed

- The **Project monitoring** and **Farm monitoring** windows: the page replaces them.
- The **review spreadsheet** to fill in and import back: reviews are made in the page. (*Export…* still writes a spreadsheet, to read.)
- Render presets in `.json`: only Python presets remain; *Migrate old data* converts the old ones.
