# templates/worker_render_entry.py
import importlib
import os
import sys
import time

import addon_utils
import bpy

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
job_id = argv[argv.index("--job-id") + 1]
preset = argv[argv.index("--preset") + 1]
# Real (possibly namespaced) module name, passed by execute_render_request()
# -- see NOTES.md, "CSV batch: the subprocess couldn't import itself".
addon_module = argv[argv.index("--addon-module") + 1]
saved_file = argv[argv.index("--saved-file") + 1] if "--saved-file" in argv else ""
dispatch_id = argv[argv.index("--dispatch-id") + 1] if "--dispatch-id" in argv else ""
stop_file = argv[argv.index("--stop-file") + 1] if "--stop-file" in argv else ""
yield_file = argv[argv.index("--yield-file") + 1] if "--yield-file" in argv else ""
chunk_size = int(argv[argv.index("--chunk-size") + 1])
machine = argv[argv.index("--machine") + 1]

# Fresh subprocess: Blender's own extension loader already makes the addon
# importable, no manual sys.path edit needed here.
addon_utils.enable(addon_module, default_set=False, persistent=False)
farm = importlib.import_module(f"{addon_module}.farm")
chunks = importlib.import_module(f"{addon_module}.farm.chunks")
lib = importlib.import_module(f"{addon_module}.lib")

scene = bpy.context.scene

# strict: a preset that can't be applied raises -- Blender exits with
# --python-exit-code before rendering anything, and the worker reports the
# render as failed. Never render with the .blend's own settings instead.
farm.apply_custom_preset(preset, scene, job_id, strict=True)


def record_saved(frame: int) -> None:
    """After each frame written: one line, so the monitor knows which
    machine wrote it, and when (this machine's clock): the time between two
    lines is what a frame took (frame_seconds(), farm/workers.py)."""
    try:
        with open(saved_file, "a", encoding="utf-8") as f:
            f.write(f"{dispatch_id} {frame} {time.time():.1f}\n")
    except OSError:
        pass


# The render's range and every frame's final file -- the naming the frame
# check and the compilation expect (-o, -F, the output's #### and
# extension) -- read before render_frame()'s settings change them.
START, END = scene.frame_start, scene.frame_end
FINALS = {
    f: bpy.path.abspath(scene.render.frame_path(frame=f)) for f in range(START, END + 1)
}
FOLDER = os.path.dirname(FINALS[START])

# Blender writes each frame itself, to a hidden .tmp of this render's own:
# a name that never ends with the image's extension (never counted as a
# frame) nor clashes with another machine's.
scene.render.use_placeholder = False
scene.render.use_overwrite = True
scene.render.use_file_extension = False
scene.render.filepath = os.path.join(FOLDER, f".{machine}_{os.getpid()}_#####.tmp")


def frame_file(frame: int) -> str:
    """The frame's final file."""
    return FINALS[frame]


def tmp_file(frame: int) -> str:
    """Where Blender writes the frame before it's renamed onto frame_file()."""
    return bpy.path.abspath(scene.render.frame_path(frame=frame))


def files_in(folder: str) -> set[str]:
    """Names in folder, one listing (a round trip on the share, not a stat
    per frame)."""
    try:
        return {entry.name for entry in os.scandir(folder)}
    except FileNotFoundError:
        return set()


def render_frame(frame: int, final: str) -> None:
    """Render one frame, written whole under its final name: Blender's own
    animation render over a one-frame range -- what -a writes, File Output
    nodes numbering their files (a plain render() writes them unnumbered,
    each frame over the last) -- to tmp_file(), then renamed: a file under
    a frame's name is a finished frame."""
    scene.frame_start = scene.frame_end = frame
    bpy.ops.render.render(animation=True)
    lib.retry_shared_io(os.replace, tmp_file(frame), final)


def stop_asked() -> bool:
    """The worker asked this render to stop after its frame
    (stop_worker(kill_render=False))."""
    return bool(stop_file) and os.path.exists(stop_file)


def yield_asked() -> bool:
    """The farm host wants this machine on a higher-priority job: give way
    between two chunks (render_yield_path())."""
    return bool(yield_file) and os.path.exists(yield_file)


def update_claim(k: int, claim: dict) -> bool:
    """Rewrite chunk k's claim (its holder is its only writer). False if
    it's gone: the host took this machine for dead and freed it -- writing
    it back would hand the chunk to two machines."""
    if not os.path.exists(chunks.claim_path(job_id, k)):
        return False
    claim["updated_at"] = time.time()
    chunks.write_claim(job_id, k, claim)
    return True


def render_chunk(k: int, start: int, end: int, folder: str) -> str:
    """Chunk k: "" if it's done or held by another machine, "rendered"
    once this machine rendered what it was missing, else why the render
    stops. A frame that fails raises with its claim left in place: the host
    frees it once the worker reports the failure, and counts it against
    this machine."""
    first, last = chunks.chunk_frames(start, end, chunk_size, k)
    names = files_in(folder)
    missing = [
        f
        for f in range(first, last + 1)
        if os.path.basename(frame_file(f)) not in names
    ]
    if not missing:
        return ""
    claim = {
        "job_id": job_id,
        "dispatch_id": dispatch_id,
        "chunk": k,
        "machine": machine,
        "pid": os.getpid(),
        "frames_done": [],
        "frame_in_progress": None,
        "frame_in_progress_file": "",
        "frame_in_progress_tmp": "",
        "claimed_at": time.time(),
        "updated_at": time.time(),
    }
    if not chunks.try_claim(job_id, k, claim):
        return ""
    # The listing may be seconds old (SMB caches it): finished since?
    missing = [f for f in missing if not os.path.exists(frame_file(f))]
    for f in missing:
        if stop_asked():
            chunks.release_claim(job_id, k)
            return "stopped after a frame"
        final = frame_file(f)
        claim["frame_in_progress"] = f
        claim["frame_in_progress_file"] = final
        claim["frame_in_progress_tmp"] = tmp_file(f)
        if not update_claim(k, claim):
            return f"chunk {k}'s claim freed by the host"
        render_frame(f, final)
        record_saved(f)
        claim["frames_done"].append(f)
        claim["frame_in_progress"] = None
        claim["frame_in_progress_file"] = ""
        claim["frame_in_progress_tmp"] = ""
        if not update_claim(k, claim):
            return f"chunk {k}'s claim freed by the host"
    chunks.release_claim(job_id, k)
    return "rendered"


def render_chunks() -> str:
    """Walk the chunks from the first, rendering every one free, again and
    again while a pass rendered something: a chunk another machine let go
    behind this one (stopped mid-chunk) is picked up without a new Blender.
    Ends on a pass that found nothing to claim -- every chunk complete on
    disk or held elsewhere --, on a stop, or between two chunks when the
    farm host wants this machine on a higher-priority job. Returns why it
    stopped."""
    start, end, folder = START, END, FOLDER
    os.makedirs(folder, exist_ok=True)
    rendered = True
    while rendered:
        rendered = False
        for k in range(chunks.chunks_number(start, end, chunk_size)):
            if stop_asked():
                return "stopped after a frame"
            if yield_asked():
                return "gave way to a higher-priority job"
            outcome = render_chunk(k, start, end, folder)
            if outcome == "rendered":
                rendered = True
            elif outcome:
                return outcome
    return "nothing left to claim"


if saved_file:
    # A machine that left the render and came back appends to the same
    # record, same dispatch_id: this line keeps the time it was away out of
    # its first frame's (frame_seconds() starts again after it).
    try:
        with open(saved_file, "a", encoding="utf-8") as f:
            f.write(f"{dispatch_id} start {time.time():.1f}\n")
    except OSError:
        pass

print(f"Chunks of {job_id}: {render_chunks()}.")
sys.stdout.flush()
