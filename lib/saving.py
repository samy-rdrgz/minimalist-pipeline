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
from .session import (
    get_machine_id,
    get_opened_as_read_only,
    note_read_only_saved,
    read_only_unchanged_on_disk,
)


def _save_and_release(filepath: str, uuid: str):
    """Save in place, then release the lock (uuid empty -- none was held)."""
    try:
        bpy.ops.wm.save_mainfile("EXEC_DEFAULT")
        note_read_only_saved(filepath)
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


addon_keymaps = []


def _save_key(km_window, incremental: bool) -> dict:
    """The keys of Blender's own Save (or Save Incremental) in the active
    keyconfig -- as the user set them --, else its defaults."""
    for kmi in km_window.keymap_items if km_window else ():
        if (
            kmi.idname == "wm.save_mainfile"
            and kmi.active
            and bool(getattr(kmi.properties, "incremental", False)) == incremental
        ):
            return {k: getattr(kmi, k) for k in ("type", "ctrl", "alt", "shift", "oskey")}
    return {"type": "S", "ctrl": True, "alt": incremental, "shift": False, "oskey": False}


def override_shortcut():
    """Ctrl+S and Ctrl+Alt+S (Save Incremental) on the addon's guarded
    save and Increment -- the File menu's buttons are left as they are (see
    NOTES.md, "Save Incremental: its key, not its button")."""
    for cls in (WM_OT_safe_save, WM_OT_safe_save_incremental):
        try:
            bpy.utils.register_class(cls)
        except Exception:
            pass

    wm = bpy.context.window_manager
    kc_active = wm.keyconfigs.active
    kc_addon = wm.keyconfigs.addon
    if not (kc_active and kc_addon):
        return
    km_window = kc_active.keymaps.get("Window")
    km = kc_addon.keymaps.get(
        "Window", kc_addon.keymaps.new(name="Window", space_type="EMPTY")
    )
    for cls, incremental in ((WM_OT_safe_save, False), (WM_OT_safe_save_incremental, True)):
        kmi = km.keymap_items.new(
            cls.bl_idname, value="PRESS", **_save_key(km_window, incremental)
        )
        addon_keymaps.append((km, kmi))


def unoverride_shortcut():
    """Remove the save keymap overrides and unregister their operators."""
    try:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)
        addon_keymaps.clear()

    except Exception:
        pass
    for cls in (WM_OT_safe_save, WM_OT_safe_save_incremental):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


class WM_OT_safe_save_incremental(bpy.types.Operator):
    """Save Incremental's key: the addon's Increment in the active project
    (Blender's would copy a -stable tag onto the next number), Blender's
    own outside it."""

    bl_idname = "wm.safe_save_incremental"
    bl_label = "Save Incremental (pipeline)"

    def invoke(self, context, event):
        filepath = bpy.data.filepath
        if filepath and file_in_active_project(filepath):
            return bpy.ops.m_pipeline.increment_version("INVOKE_DEFAULT", tag="NONE")
        # Its images dialog: an option from Blender 5.0 on (4.2 has none).
        props = bpy.ops.wm.save_mainfile.get_rna_type().properties
        extra = (
            {"show_save_modified_images_dialog": True}
            if "show_save_modified_images_dialog" in props
            else {}
        )
        return bpy.ops.wm.save_mainfile("INVOKE_DEFAULT", incremental=True, **extra)

    def execute(self, context):
        return self.invoke(context, None)


class WM_OT_safe_save(bpy.types.Operator):
    """Allow or not user to save his file, depending of file tag (-stable), or session tag (read-only)."""

    bl_idname = "wm.safe_save"
    bl_label = "Save Mainfile safely"

    filepath: bpy.props.StringProperty(default="")
    uuid: bpy.props.StringProperty(default="")

    def invoke(self, context, event):
        """Save directly outside the active project; inside it, gate on the
        read-only flag, then the file lock, then the -stable tag. Callbacks
        use plain locals, never self (see NOTES.md, "Small gotchas, out of
        the docstrings")."""
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
                lines = ["File is locked by another user:"] + [
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
                        ],
                        on_dismiss=partial(_release_only, filepath, uuid),
                        explanation=STABLE_FILE_EXPLANATION,
                    )
                )
                self._open_popup()
                return {"FINISHED"}

            else:
                choices = [
                    (
                        "Save & Increment",
                        partial(_increment_and_release, filepath, uuid),
                        "Save as a new version instead of overwriting.",
                    )
                ]
                # Saving over it is only offered while nobody saved it since
                # it was opened: else it would wipe out their work.
                if read_only_unchanged_on_disk(filepath):
                    message = (
                        "This file was opened read-only.\n"
                        "Nobody saved it since: you can save over it, or as a "
                        "new version."
                    )
                    choices.append(
                        (
                            "Save",
                            partial(_save_and_release, filepath, uuid),
                            "Save over it: nobody saved it since you opened it.",
                        )
                    )
                else:
                    message = (
                        "This file was opened read-only, and saved by someone "
                        "else since.\nSaving over it would lose their work: "
                        "save as a new version."
                    )
                set_pending_action(
                    PipelineAction(
                        title="Read-Only Origin",
                        message=message,
                        severity="warning",
                        choices=choices,
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
