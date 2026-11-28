"""Editing rushes: push the latest videos into editing/rushes/ under their
unversioned names (lib/rushes.py), by hand or when a render is checked."""

import os
from pathlib import Path

import bpy

from ..lib import (
    main_render_dir,
    ConfigCache,
    get_active_project_root,
    get_user,
    is_video,
    log,
    push_rushes,
    push_sequence_rushes,
    run_in_background,
)
from ..lib.operators import popup


def report_push(result: dict) -> str:
    """Log a push's outcome (lib.push_rushes() / push_sequence_rushes()),
    one line per refused copy, and sum it up in one line."""
    for name, reason in result["failed"]:
        log("WARNING", "rushes", f"{name} not pushed: {reason}")
    for label, newer in result.get("dropped") or []:
        log("WARNING", "rushes", f"{label} not pushed: {', '.join(newer)} more recent.")
    copied = result["copied"]
    if copied:
        log("INFO", "rushes", f"Pushed to editing: {', '.join(copied)}")
    summary = f"Rushes: {len(copied)} updated, {result['unchanged']} unchanged"
    if result["failed"]:
        summary += f", {len(result['failed'])} not pushed (see log)"
    if result.get("empty"):
        summary += f" -- nothing rendered in {', '.join(result['empty'])}"
    return summary


def push_in_background(fn, *args, task: str = "") -> None:
    """Run a push on a thread: its summary in the log, a popup if a copy
    was refused (a rush open in the edit keeps its old video). task: its
    label in the live page's footer (lib/monitoring/tasks.py), "" none."""
    from ..lib.monitoring import tasks

    tid = tasks.start("rushes", task) if task else 0

    def done(result):
        summary = report_push(result)
        if tid:
            tasks.end(tid, not result["failed"], summary)
        if not result["failed"]:
            return
        lines = [f"{name}: {reason}" for name, reason in result["failed"]]
        popup("Rushes not all pushed", "\n".join([summary, "", *lines[:12]]), "ERROR")

    def failed(error):
        if tid:
            tasks.end(tid, False, str(error))
        log("ERROR", "rushes", f"Push to editing failed: {error}")

    run_in_background(fn, args, done, failed, every=0.5)


def checked_render_videos(entries: list) -> list[Path]:
    """The videos of renders just marked checked ("to_check" entries:
    their compiled video, else the first mp4 of their render folder) --
    each its shot's main render only (main_render_dir()): an animation
    render checked after the lighting one doesn't replace it in the edit."""
    root = get_active_project_root()
    videos = []
    for info in entries:
        if not isinstance(info, dict):
            continue
        folder = root / (info.get("render") or "")
        if info.get("render") and main_render_dir(folder.parent) not in (None, folder):
            log("INFO", "rushes", f"{folder.name}: not its shot's main render, not pushed.")
            continue
        video = info.get("video")
        if video and (root / video).is_file():
            videos.append(root / video)
            continue
        folder = root / (info.get("render") or "")
        try:
            mp4s = sorted(
                e.path for e in os.scandir(folder) if is_video(e.name)
            )
        except OSError:
            mp4s = []
        if info.get("render") and mp4s:
            videos.append(Path(mp4s[0]))
    return videos


class M_PIPELINE_OT_push_rushes(bpy.types.Operator):
    """Copy the latest videos into editing/rushes/, unversioned names."""

    bl_idname = "m_pipeline.push_rushes"
    bl_label = "Push rushes to editing"
    bl_description = (
        "Copy each shot's latest video (and the assets') into editing/rushes/ "
        "under its name without version -- sq100/sq100_sh030.mp4 -- so the "
        "edit keeps its links. Only what changed is copied; rushes.json there "
        "says which render each one is"
    )

    assets: bpy.props.BoolProperty(
        name="Assets & libraries",
        default=True,
        description="Also every asset/library's latest video",
        options={"SKIP_SAVE"},
    )

    def invoke(self, context, event):
        root = get_active_project_root()
        if not root:
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        sequences = context.window_manager.rushes_sequences
        sequences.clear()
        try:
            names = sorted(e.name for e in os.scandir(root / "shots") if e.is_dir())
        except OSError:
            names = []
        for name in names:
            item = sequences.add()
            item.name = name
            item.include = True  # all: the first push fills the folder
        return context.window_manager.invoke_props_dialog(
            self, width=300, confirm_text="Push"
        )

    def draw(self, context):
        layout = self.layout
        box = layout.box().column(align=True)
        box.label(text="Sequences:", icon="SEQUENCE")
        for item in context.window_manager.rushes_sequences:
            box.row(align=True).prop(item, "include", text=item.name)
        box.separator()
        box.prop(self, "assets")
        info = layout.column(align=True)
        info.active = False
        info.label(text="Into editing/rushes/, names without", icon="INFO")
        info.label(text="version: only what changed is copied.", icon="BLANK1")

    def execute(self, context):
        root = get_active_project_root()
        if not root:
            self.report({"ERROR"}, "No active project.")
            return {"CANCELLED"}
        chosen = [s.name for s in context.window_manager.rushes_sequences if s.include]
        if not chosen and not self.assets:
            self.report({"WARNING"}, "Nothing selected.")
            return {"CANCELLED"}
        push_in_background(
            push_sequence_rushes,
            root,
            chosen,
            self.assets,
            ConfigCache.get(),
            get_user(context),
            # Its label (Blender's panel, the page's footer): the sequences, names.
            task=", ".join(chosen[:3]) + (f" +{len(chosen) - 3}" if len(chosen) > 3 else "") or "assets",
        )
        self.report({"INFO"}, "Pushing rushes to editing (see the log when done)...")
        return {"FINISHED"}


def push_checked_renders(context, entries: list) -> None:
    """Push the renders just marked checked (a render marked checked on the live page)."""
    videos = checked_render_videos(entries)
    if videos:
        push_in_background(
            push_rushes, get_active_project_root(), videos, get_user(context),
            task=videos[0].stem + (f" +{len(videos) - 1}" if len(videos) > 1 else ""),
        )
