"""Ctrl+S override: route saves through the read-only / stable / lock guards."""

from functools import partial
from pathlib import Path

import bpy

from .actions import (
    LOCKED_FILE_EXPLANATION,
    READ_ONLY_EXPLANATION,
    STABLE_FILE_EXPLANATION,
    PipelineAction,
    set_pending_action,
)
from .config import file_in_active_project, parse_filename
from .core import acquire_lock, locked_json, release_lock
from .session import get_machine_id, get_opened_as_read_only


def _save_and_release(filepath: str, uuid: str):
    """Save in place, then release the lock (uuid empty -- none was held)."""
    try:
        bpy.ops.wm.save_mainfile("EXEC_DEFAULT")
    finally:
        if uuid:
            release_lock(Path(filepath), uuid)


def _release_only(filepath: str, uuid: str):
    """Cancel / dismiss: release the lock without saving."""
    if uuid:
        release_lock(Path(filepath), uuid)


def _increment_and_release(filepath: str, uuid: str):
    """Increment instead of overwriting, then release the lock. Deferred one
    timer tick -- see NOTES.md, "Popup-chaining"."""
    try:
        bpy.app.timers.register(
            lambda: bpy.ops.m_pipeline.increment_version("INVOKE_DEFAULT"),
            first_interval=0.05,
        )
    finally:
        if uuid:
            release_lock(Path(filepath), uuid)


def get_save_shortcut():
    """Return the active wm.save_mainfile keymap item's key combo, or None."""
    kc = bpy.context.window_manager.keyconfigs.active
    km = kc.keymaps.get("Window")
    if km:
        for kmi in km.keymap_items:
            if kmi.idname == "wm.save_mainfile" and kmi.active:
                return {
                    "type": kmi.type,  # ex: 'S'
                    "ctrl": kmi.ctrl,  # True / False
                    "alt": kmi.alt,  # True / False
                    "shift": kmi.shift,  # True / False
                    "oskey": kmi.oskey,  # Cmd on macOS
                }
    return None


addon_keymaps = []


def override_shortcut():
    """Replace basic Saving on Ctrl+S by custom safe_save ops. /!\\ Save btn is not overide."""
    try:
        bpy.utils.register_class(WM_OT_safe_save)
    except Exception:
        pass

    wm = bpy.context.window_manager
    kc_active = wm.keyconfigs.active
    kc_addon = wm.keyconfigs.addon

    if kc_active and kc_addon:
        km_window = kc_active.keymaps.get("Window")
        target_kmi = None

        if km_window:
            for kmi in km_window.keymap_items:
                if kmi.idname == "wm.save_mainfile" and kmi.active:
                    target_kmi = kmi
                    break

        k_type = target_kmi.type if target_kmi else "S"
        k_ctrl = target_kmi.ctrl if target_kmi else True
        k_alt = target_kmi.alt if target_kmi else False
        k_shift = target_kmi.shift if target_kmi else False
        k_oskey = target_kmi.oskey if target_kmi else False

        km = kc_addon.keymaps.get(
            "Window", kc_addon.keymaps.new(name="Window", space_type="EMPTY")
        )
        new_kmi = km.keymap_items.new(
            WM_OT_safe_save.bl_idname,
            type=k_type,
            value="PRESS",
            ctrl=k_ctrl,
            alt=k_alt,
            shift=k_shift,
            oskey=k_oskey,
        )
        addon_keymaps.append((km, new_kmi))


def unoverride_shortcut():
    """Remove the safe_save keymap override and unregister its operator."""
    try:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)
        addon_keymaps.clear()

    except Exception:
        pass
    try:
        bpy.utils.unregister_class(WM_OT_safe_save)
    except Exception:
        pass


class WM_OT_safe_save(bpy.types.Operator):
    """Allow or not user to save his file, depending of file tag (-stable), or session tag (read-only)."""

    bl_idname = "wm.safe_save"
    bl_label = "Save Mainfile safely"

    filepath: bpy.props.StringProperty(default="")
    uuid: bpy.props.StringProperty(default="")

    def invoke(self, context, event):
        """Save directly outside the active project; inside it, gate on the
        read-only flag, then on a file lock, then on the -stable tag.
        filepath/uuid are captured into plain locals for the popup's
        callbacks below: self.filepath/self.uuid are RNA properties, freed
        with this operator's StructRNA once invoke() returns -- reading them
        from a callback that runs later (popup choice, on_dismiss) raises
        ReferenceError, so callbacks close over the plain values instead."""
        filepath = bpy.data.filepath
        self.filepath = filepath

        if not filepath:
            # Never saved before -- see NOTES.md, "Popup-chaining".
            bpy.app.timers.register(
                lambda: bpy.ops.wm.save_mainfile("INVOKE_DEFAULT"),
                first_interval=0.05,
            )
            return {"FINISHED"}

        if not file_in_active_project(filepath):
            _save_and_release(filepath, "")
            return {"FINISHED"}

        ro = get_opened_as_read_only()
        ro = ro and ro == filepath

        if not ro:
            _save_and_release(filepath, "")
            return {"FINISHED"}
        else:
            path = Path(filepath)
            uuid = get_machine_id(context)
            self.uuid = uuid
            free = acquire_lock(path, uuid)
            if not free:
                with locked_json(path.parent / f".{path.name}.lock") as box:
                    data = box.get("data", {})
                lines = ["File is lock by another user :"] + [
                    f"{n} : {m}" for n, m in data.items()
                ]
                bpy.ops.m_pipeline.text_popup(
                    "INVOKE_DEFAULT",
                    title="Save Impossible",
                    message="\n".join(lines),
                    icon="ERROR",
                    explanation=LOCKED_FILE_EXPLANATION,
                )
                return {"CANCELLED"}

            parsed = parse_filename(path.name)
            if parsed and parsed["tag"] == "stable":
                set_pending_action(
                    PipelineAction(
                        title="You're on a stable file !",
                        message="Are you sure you want to save modifications\nwithout incrementation?",
                        severity="warning",
                        choices=[
                            (
                                "Save",
                                partial(_save_and_release, filepath, uuid),
                                "Overwrite this stable file in place.",
                            ),
                            (
                                "Increment",
                                partial(_increment_and_release, filepath, uuid),
                                "Save as a new version instead of overwriting.",
                            ),
                            (
                                "Cancel",
                                partial(_release_only, filepath, uuid),
                                "Don't save.",
                            ),
                        ],
                        on_dismiss=partial(_release_only, filepath, uuid),
                        explanation=STABLE_FILE_EXPLANATION,
                    )
                )
                self._open_popup()
                return {"FINISHED"}

            else:
                set_pending_action(
                    PipelineAction(
                        title="Read-Only Origin",
                        message="Are you sure you want to save modifications?\n(It will automatically increment)",
                        severity="warning",
                        choices=[
                            (
                                "Save & Increment",
                                partial(_increment_and_release, filepath, uuid),
                                "This file is read-only: save as a new version instead of overwriting.",
                            ),
                            (
                                "Cancel",
                                partial(_release_only, filepath, uuid),
                                "Don't save.",
                            ),
                        ],
                        on_dismiss=partial(_release_only, filepath, uuid),
                        explanation=READ_ONLY_EXPLANATION,
                    )
                )
                self._open_popup()
                return {"FINISHED"}

    def execute(self, context):
        """No-op: all the work happens in invoke()."""
        return {"FINISHED"}

    def _open_popup(self):
        """Defer opening action_popup by one timer tick -- see NOTES.md,
        "Popup-chaining"."""
        bpy.app.timers.register(
            lambda: bpy.ops.m_pipeline.action_popup("INVOKE_DEFAULT"),
            first_interval=0.05,
        )
