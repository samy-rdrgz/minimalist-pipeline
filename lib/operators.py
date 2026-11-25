"""Core Blender operators and app handlers."""

from datetime import date, datetime
from pathlib import Path

import bpy

from .actions import PipelineAction, get_pending_action
from .core import (
    addon_pref,
    draw_box_tip,
    region_char_budget,
    text_to_lines,
)
from .errors import PipelineError
from .logs import log, report_error
from .session import get_user
from .monitoring.tracking import create_wipmeta, get_last_wipmeta
from .versioning import (
    get_last_version_number,
    get_version_number,
    save_as,
)


class M_PIPELINE_OT_action_popup(bpy.types.Operator):
    """Generic popup that displays any PipelineAction."""

    bl_idname = "m_pipeline.action_popup"
    bl_label = "Pipeline"

    _POPUP_WIDTH = 300  # invoke_popup()'s own width param, real pixels
    _action: PipelineAction | None = None
    choice_index: bpy.props.IntProperty(default=-1)

    @classmethod
    def description(cls, context, properties):
        action = get_pending_action(clear=False)
        if not action or not (0 <= properties.choice_index < len(action.choices)):
            return ""
        choice = action.choices[properties.choice_index]
        return choice[2] if len(choice) > 2 else ""

    def invoke(self, context, event):
        self._action = get_pending_action(clear=False)
        if not self._action:
            return {"CANCELLED"}
        if self._action.severity == "info" and not self._action.choices:
            self.report({"INFO"}, self._action.message)
            return {"FINISHED"}
        # A dialog, not invoke_popup(): a popup closes as soon as the mouse
        # leaves it, and these were missed (append warning...) -- a dialog
        # stays until a button or Escape. Its own footer (Close / Cancel)
        # both just close it, like Escape; cancel_default so Enter never
        # picks anything. See NOTES.md, "Action popups: dialogs".
        return context.window_manager.invoke_props_dialog(
            self,
            width=self._POPUP_WIDTH,
            title="Pipeline",
            confirm_text="Close",
            cancel_default=True,
        )

    def cancel(self, context):
        """Dismissed without a choice: clear the pending action (as
        execute() does) and run its on_dismiss, if any."""
        self._dismiss(self._action)

    @staticmethod
    def _dismiss(action) -> None:
        """Closed without a choice (Escape, Cancel, Close): clear it and run
        its on_dismiss -- unless a choice already ran."""
        get_pending_action(clear=True)
        if action and action.on_dismiss and not action.resolved:
            action.resolved = True
            try:
                action.on_dismiss()
            except Exception as e:
                log("ERROR", "action_popup", str(e))

    @staticmethod
    def _force_close(context):
        """invoke_popup doesn't auto-close just because a button inside it
        ran an operator to completion -- known Blender quirk, not specific
        to this addon (https://blender.stackexchange.com/q/202550).
        Reassigning the window's screen to itself forces the UI refresh that
        actually drops the popup."""
        context.window.screen = context.window.screen

    def draw(self, context):
        layout = self.layout
        if not self._action:
            layout.label(text="No action available", icon="ERROR")
            return

        title = layout.row()
        icon = {"info": "INFO", "warning": "ERROR", "critical": "ERROR"}.get(
            self._action.severity, "INFO"
        )
        critical = self._action.severity == "critical"
        title.alert = critical  # red: can't be missed
        title.label(text=self._action.title.upper(), icon=icon)
        if self._action.message:
            layout.separator()
            text_layout = layout.column(align=True)
            text_layout.alert = critical
            text_layout.scale_y = 0.7
            for line in self._action.message.split("\n"):
                text_to_lines(
                    text_layout,
                    line,
                    max_width=region_char_budget(context, width_px=self._POPUP_WIDTH),
                )

        if self._action.explanation:
            draw_box_tip(
                layout, context, self._action.explanation, width_px=self._POPUP_WIDTH
            )

        layout.separator()
        ops = layout.row() if len(self._action.choices) < 3 else layout.column()
        ops.operator_context = "EXEC_DEFAULT"

        # No "OK" nor "Cancel" of our own: the dialog's footer (Cancel /
        # Close) closes it, running on_dismiss -- a "Cancel" choice only
        # doubled it.
        for i, choice in enumerate(self._action.choices):
            label = choice[0]
            op = ops.operator("m_pipeline.action_popup", text=label)
            op.choice_index = i

    def execute(self, context):
        if self.choice_index < 0:
            # The dialog's own "Close": same as dismissing it.
            self._dismiss(self._action or get_pending_action(clear=False))
            return {"FINISHED"}
        action = get_pending_action(clear=True)
        if not action:
            self._force_close(context)
            return {"CANCELLED"}

        action.resolved = True  # the dialog closing next won't dismiss it
        choice = action.choices[self.choice_index]
        callback = choice[1]
        if callback:
            try:
                callback()
            except PipelineError as e:
                log(e.level, "action_popup", e.message)
                self.report({e.level}, e.message)
                self._force_close(context)
                return {"CANCELLED"}
        self._force_close(context)
        return {"FINISHED"}


def popup(title: str, message: str, icon: str = "INFO", explanation: str = "") -> None:
    """The message in M_PIPELINE_OT_text_popup; nothing when there's no window to show it in (the log
    has it)."""
    try:
        bpy.ops.m_pipeline.text_popup(
            "INVOKE_DEFAULT", title=title, message=message, icon=icon, explanation=explanation
        )
    except RuntimeError:
        pass


class M_PIPELINE_OT_text_popup(bpy.types.Operator):
    """Simple modal popup for messages (temporary, replaced by PipelineAction)."""

    bl_idname = "m_pipeline.text_popup"
    bl_label = "Info"

    icon: bpy.props.StringProperty(default="INFO")
    title: bpy.props.StringProperty(default="INFO")
    message: bpy.props.StringProperty(default="")
    explanation: bpy.props.StringProperty(default="")

    _popup_width: int = 400  # set for real in invoke(); see draw()'s note

    def draw(self, context):
        _valid_icons = {"INFO", "ERROR", "CHECKMARK", "QUESTION", "CANCEL"}
        col = self.layout.column()
        col.scale_y = 0.7
        icon = self.icon if self.icon in _valid_icons else "INFO"
        col.label(text=self.title.upper(), icon=icon)
        if self.message:
            col.separator(factor=0.5)
            for line in self.message.split("\n"):
                col.label(text=line)
        if self.explanation:
            # This popup's width is computed below (message-dependent), not
            # a fixed class constant -- stashed on self in invoke() so draw()
            # can pass the real value through to region_char_budget().
            draw_box_tip(
                self.layout, context, self.explanation, width_px=self._popup_width
            )

    def invoke(self, context, event):
        if self.icon == "INFO":
            self.report({"INFO"}, self.message)
            return {"FINISHED"}
        max_line = max((len(line) for line in self.message.split("\n")), default=0) * 8
        title_w = len(self.title) * 9 + 23
        width = min(max(max_line, title_w), 400)
        if self.explanation:
            width = max(width, 320)
        self._popup_width = width
        return context.window_manager.invoke_popup(self, width=width)

    def execute(self, context):
        return {"FINISHED"}


class M_PIPELINE_OT_onboarding_popup(bpy.types.Operator):
    """First-launch intro: what the addon does, how it works, what it needs,
    the one rule. Also from the main panel's Help icon; dismissible."""

    bl_idname = "m_pipeline.onboarding_popup"
    bl_label = "Welcome"

    _POPUP_WIDTH = 520  # invoke_popup()'s own width param, real pixels

    # Short on purpose: read once, at the first launch.
    _SECTIONS = (
        ("What it does", "NAMES, VERSIONS and TRACKS your files; RENDERS them on the farm."),
        ("How", "It PROPOSES, YOU DECIDE. Assets are LINKED, never copied."),
        ("What it needs", "A SHARED DRIVE (NAS, SMB) -- not Dropbox, Google Drive or OneDrive."),
        ("One rule", "NEVER rename, move or edit project files BY HAND: use the buttons."),
    )

    def invoke(self, context, event):
        # onboarding_seen is set by _deferred_onboarding only (the Help icon
        # opens it too). A window like the monitoring ones, else the popup.
        from .monitoring.windows import (
            bring_monitoring_to_front,
            monitoring_windows,
            open_monitoring_window,
        )

        if monitoring_windows("welcome"):
            if bring_monitoring_to_front(context, "welcome"):
                return {"FINISHED"}
        elif open_monitoring_window(context, "welcome", size=(0.36, 0.7)):
            return {"FINISHED"}
        return context.window_manager.invoke_popup(self, width=self._POPUP_WIDTH)

    def draw(self, context):
        draw_onboarding(self.layout, context)

    def execute(self, context):
        return {"FINISHED"}


def _check(col, ok: bool, text: str) -> None:
    """One line of the welcome's checks: ticked and greyed, or a warning (red)."""
    row = col.row()
    row.alert = not ok
    row.active = not ok
    row.label(text=text, icon="CHECKMARK" if ok else "ERROR")


def _field(col, label: str):
    """A labelled line of the welcome: the label, then the column its field
    goes in -- the same split for every one, so they line up."""
    split = col.split(factor=0.25, align=True)
    split.label(text=label)
    return split.column(align=True)


def draw_onboarding(layout, context, max_width: int = 120, level_hint: bool = True) -> None:
    """The welcome: a project to start or join, who you are, what's ready
    (checked, not explained), where to follow the project, the four things
    to know. In its window (panels/monitoring_panel.py), or the popup when
    no window could open. Short: read once."""
    from .config import get_active_project_root
    from .core import cloud_synced, is_placeholder_name, resolve_ffmpeg

    prefs = addon_pref(context)
    root = get_active_project_root()
    col = layout.column(align=True)

    # 1. A project: everything else needs one.
    box = col.box().column(align=True)
    box.label(text="START", icon="EVENT_RIGHT_ARROW")
    if root:
        box.label(text=f"Project: {Path(root).name}", icon="CHECKMARK")
    else:
        row = box.row(align=True)
        row.scale_y = 1.4
        row.operator("m_pipeline.create_project", text="New project", icon="ADD")
        row.operator("m_pipeline.find_project", text="Join a project", icon="FILEBROWSER")
        hint = box.row()
        hint.active = False
        hint.label(text="Joining a team: Join a project, never a new one.", icon="INFO")
    col.separator(factor=2)

    # 2. Who you are: your notes, renders and validations go by it.
    if prefs:
        box = col.box().column(align=True)
        box.label(text="YOU", icon="USER")
        from ..operators.team_ops import draw_user_name

        placeholder = is_placeholder_name(prefs.user_name)
        name = _field(box, "Name")
        name.alert = placeholder
        draw_user_name(name, prefs)
        if placeholder:
            name.label(text="A random name: type your own.", icon="ERROR")
        # Optional: only who validates (sup, prod...) needs one -- greyed while empty.
        role = box.column(align=True)
        role.active = bool(prefs.user_role)
        _field(role, "Role (optional)").prop(prefs, "user_role", text="")
        if not prefs.user_role:
            _field(role, "").label(text="Only to validate: sup, prod...")
        col.separator(factor=2)

        # 3. What's ready -- checked, nothing to read when it all is.
        box = col.box().column(align=True)
        box.label(text="READY?", icon="CHECKBOX_HLT")
        _check(box, not placeholder, "Your name")
        _check(box, bool(root), "A project")
        _check(box, bool(resolve_ffmpeg()), "FFmpeg (videos)" + ("" if resolve_ffmpeg() else ": set its path in Preferences"))
        if root:
            service = cloud_synced(root)
            _check(box, not service, f"On a shared drive{f': not {service}' if service else ''}")
        col.separator(factor=2)

        # 4. Where to follow it: the live page.
        box = col.box().column(align=True)
        box.label(text="FOLLOW THE PROJECT", icon="DESKTOP")
        row = box.row()
        button = row.row()
        button.enabled = bool(root)
        button.operator("m_pipeline.open_live_page", text="Monitor in browser", icon="URL")
        row.prop(prefs, "auto_open_live_page", text="Open it by itself each time Blender starts")
        col.separator(factor=2)

    # 5. The four things to know, a line each: its title, its words.
    box = col.box().column(align=True)
    for title, body in M_PIPELINE_OT_onboarding_popup._SECTIONS:
        line = _field(box, title.upper())
        line.active = False
        text_to_lines(line, body, max_width=max(40, max_width * 3 // 4), max_lines=2)
    if level_hint:  # the window has the switch itself
        col.box().label(
            text="You're familiar with the add-on? Hide tooltips in the add-on's preferences.",
            icon="HIDE_OFF",
        )


class M_PIPELINE_OT_auto_version(bpy.types.Operator):
    """Check file date on load, propose version increment."""

    bl_idname = "m_pipeline.auto_version"
    bl_label = "Auto Versioning"

    skip_confirm: bpy.props.BoolProperty(default=False)
    is_branch: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        try:
            original = Path(bpy.data.filepath)
            result = save_as()
            if result:
                mode = "branch_from" if self.is_branch else "auto_increment"
                create_wipmeta(
                    filepath=Path(result),
                    original_filepath=original,
                    creation_mode=mode,
                )
                self.report({"INFO"}, f"New version: {Path(result).name}")
                return {"FINISHED"}
            return {"CANCELLED"}
        except PipelineError as e:
            return report_error(self, "auto_version", e)

    def invoke(self, context, event):
        filepath = bpy.data.filepath
        if not filepath:
            return {"CANCELLED"}

        mod_date = datetime.fromtimestamp(Path(filepath).stat().st_mtime).date()
        today = date.today()

        if self.skip_confirm:
            return self.execute(context)

        current_v = get_version_number()
        last_v = get_last_version_number()

        if current_v == last_v:
            if mod_date < today:
                self.is_branch = False
                prefs = addon_pref(context)
                if prefs and prefs.silent_auto_increment:
                    return self.execute(context)
                return context.window_manager.invoke_confirm(
                    self,
                    event,
                    title="New version?",
                    message="First time opening this file today.\nCreate a new version?",
                    confirm_text="Increment",
                    icon="QUESTION",
                )
            # Already worked on today -- but was it someone else? Always ask
            # (ignores silent_auto_increment: a collision with someone
            # else's same-day work is worth interrupting for either way).
            wip = get_last_wipmeta(Path(filepath))
            other_user = wip.get("edited_by") if wip else None
            if other_user and other_user != get_user(context):
                self.is_branch = True
                return context.window_manager.invoke_confirm(
                    self,
                    event,
                    title="Already worked on today",
                    message=f"{other_user} already saved a version today.\nBranch your own version?",
                    confirm_text="Create a new version",
                    icon="QUESTION",
                )
            return {"CANCELLED"}
        else:
            self.is_branch = True
            log(
                "WARNING",
                "auto_version",
                f"{Path(filepath).name} is not the latest version.",
            )
            return context.window_manager.invoke_confirm(
                self,
                event,
                title="Create a new version?",
                message="Not the latest version.\nCreate from this file?",
                icon="QUESTION",
            )


import subprocess
import sys

import bpy


class WM_OT_open_folder(bpy.types.Operator):
    """Open filepath in the system's file browser."""

    bl_idname = "wm.open_folder"
    bl_label = "Open Folder"
    bl_description = "Open this folder in the system's file browser"

    filepath: bpy.props.StringProperty()
    custom_tooltip: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        return properties.custom_tooltip or cls.bl_description

    def execute(self, context):
        path = Path(self.filepath)
        if not path.exists():
            self.report({"ERROR"}, "Le dossier n'existe pas")
            return {"CANCELLED"}

        if sys.platform.startswith("win"):
            import os

            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:  # Linux
            subprocess.Popen(["xdg-open", str(path)])

        return {"FINISHED"}


class M_PIPELINE_OT_current_frame(bpy.types.Operator):
    """Jump to specified frame"""

    bl_idname = "m_pipeline.current_frame"
    bl_label = ""

    frame: bpy.props.IntProperty()
    custom_tooltip: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        if properties.custom_tooltip:
            return properties.custom_tooltip
        return "Jump to specified frame"

    def execute(self, context):
        context.scene.frame_current = self.frame
        return {"FINISHED"}
