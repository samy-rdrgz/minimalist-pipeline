"""Editing rushes: push the latest videos into editing/rushes/ under their
unversioned names (lib/rushes.py), by hand or when a render is checked."""

import os
from pathlib import Path

import bpy

from ..lib import (
    ConfigCache,
    SnapshotJob,
    get_active_project_root,
    get_user,
    log,
    push_rushes,
    push_sequence_rushes,
)


def report_push(result: dict) -> str:
    """Log a push's outcome (lib.push_rushes() / push_sequence_rushes()),
    one line per refused copy, and sum it up in one line."""
    for name, reason in result["failed"]:
        log("WARNING", "rushes", f"{name} not pushed: {reason}")
    for label, overlap in result.get("dropped") or []:
        log(
            "WARNING",
            "rushes",
            f"{label} not pushed: {', '.join(overlap)} has its own render.",
        )
    copied = result["copied"]
    if copied:
        log("INFO", "rushes", f"Pushed to editing: {', '.join(copied)}")
    summary = f"Rushes: {len(copied)} updated, {result['unchanged']} unchanged"
    if result["failed"]:
        summary += f", {len(result['failed'])} not pushed (see log)"
    if result.get("empty"):
        summary += f" -- nothing rendered in {', '.join(result['empty'])}"
    return summary


def push_in_background(fn, *args) -> None:
    """Run a push on a thread (gigabytes over the share), polled by a timer:
    its summary in the log, and a popup if a copy was refused -- a rush
    open in the editing software keeps its old video."""
    job = SnapshotJob(fn, *args)

    def poll():
        if not job.done:
            return 0.5
        if job.error:
            log("ERROR", "rushes", f"Push to editing failed: {job.error}")
            return None
        summary = report_push(job.result)
        if job.result["failed"]:
            lines = [f"{name}: {reason}" for name, reason in job.result["failed"]]
            try:
                bpy.ops.m_pipeline.text_popup(
                    "INVOKE_DEFAULT",
                    title="Rushes not all pushed",
                    message="\n".join([summary, "", *lines[:12]]),
                    icon="ERROR",
                )
            except RuntimeError:
                pass  # no window to show it in: the log has it
        return None

    bpy.app.timers.register(poll, first_interval=0.5)


def checked_render_videos(entries: list) -> list[Path]:
    """The videos of renders just marked checked ("to_check" entries:
    their compiled video, else the first mp4 of their render folder)."""
    root = get_active_project_root()
    videos = []
    for info in entries:
        if not isinstance(info, dict):
            continue
        video = info.get("video")
        if video and (root / video).is_file():
            videos.append(root / video)
            continue
        folder = root / (info.get("render") or "")
        try:
            mp4s = sorted(
                e.path for e in os.scandir(folder) if e.name.lower().endswith(".mp4")
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
        )
        self.report({"INFO"}, "Pushing rushes to editing (see the log when done)...")
        return {"FINISHED"}


def push_checked_renders(context, entries: list) -> None:
    """Push the renders just marked checked (M_PIPELINE_OT_render_checked)."""
    videos = checked_render_videos(entries)
    if videos:
        push_in_background(
            push_rushes, get_active_project_root(), videos, get_user(context)
        )
