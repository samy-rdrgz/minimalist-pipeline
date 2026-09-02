"""Core Blender operators and app handlers."""

from datetime import date, datetime
from pathlib import Path

import bpy

from .actions import PipelineAction, get_pending_action
from .core import (
    addon_pref,
    draw_box_tip,
    lines_budget,
    text_to_lines,
)
from .errors import PipelineError
from .logs import log
from .session import get_user
from .tracking import create_wipmeta, get_last_wipmeta
from .versioning import (
    get_last_version_number,
    get_version_number,
    save_as,
)


class PIPELINE_OT_action_popup(bpy.types.Operator):
    """Generic popup that displays any PipelineAction."""

    bl_idname = "pipeline.action_popup"
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
        # invoke_popup, not invoke_props_dialog: draw() already draws every
        # choice as its own button -- invoke_props_dialog would also add its
        # own native Cancel/OK footer on top, duplicating "Cancel".
        return context.window_manager.invoke_popup(self, width=self._POPUP_WIDTH)

    def cancel(self, context):
        """Dismissed without clicking a choice (Escape / click-away): no
        choice callback ran, so clear the pending action ourselves (mirrors
        the choice_index < 0 path in execute()) and run the action's
        on_dismiss cleanup, if any, so it fires the same whether the popup
        was dismissed or a neutral choice was clicked. No _force_close here:
        Blender is already tearing the popup down to get here."""
        action = self._action
        get_pending_action(clear=True)
        if action and action.on_dismiss:
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
        title.label(text=self._action.title.upper(), icon=icon)
        if self._action.message:
            layout.separator()
            for line in self._action.message.split("\n"):
                layout.label(text=line)

        if self._action.explanation:
            draw_box_tip(
                layout, context, self._action.explanation, width_px=self._POPUP_WIDTH
            )

        layout.separator()
        ops = layout.row() if len(self._action.choices) < 3 else layout.column()
        ops.operator_context = "EXEC_DEFAULT"

        if self._action.choices:
            for i, choice in enumerate(self._action.choices):
                label = choice[0]
                op = ops.operator("pipeline.action_popup", text=label)
                op.choice_index = i
        else:
            op = ops.operator("pipeline.action_popup", text="OK")
            op.choice_index = -1

    def execute(self, context):
        if self.choice_index < 0:
            get_pending_action(clear=True)
            self._force_close(context)
            return {"FINISHED"}
        action = get_pending_action(clear=True)
        if not action:
            self._force_close(context)
            return {"CANCELLED"}

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


class PIPELINE_OT_text_popup(bpy.types.Operator):
    """Simple modal popup for messages (temporary, replaced by PipelineAction)."""

    bl_idname = "pipeline.text_popup"
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


class PIPELINE_OT_onboarding_popup(bpy.types.Operator):
    """First-launch intro: what the addon does, how it works, what it
    needs, and the one rule. Also reachable anytime from the main panel's
    header (Help icon). Non-blocking, dismissible, no step-by-step flow --
    a custom draw() rather than PipelineAction/action_popup, since the
    hook/detail contrast and the section layout below are one-off, not a
    shape any other popup in the addon reuses."""

    bl_idname = "pipeline.onboarding_popup"
    bl_label = "Welcome"

    _POPUP_WIDTH = 650  # invoke_popup()'s own width param, real pixels

    _SECTIONS = (
        (
            "What it does for you.",
            (
                "No more final_v2_REAL.blend: it NAMES, sorts and "
                "VERSIONS your files, RENDERS and COMPILES on the farm, "
                "and TRACKS, per shot, what's left to do and the "
                "RETAKES requested."
            ),
        ),
        (
            "How it works with you.",
            (
                "It NEVER acts SILENTLY. It detects, tells you, and "
                "proposes; YOU DECIDE. And it links assets instead of "
                "copying them in, so there's always a single source of "
                "truth."
            ),
        ),
        (
            "What it needs.",
            (
                "Nothing to install and NO NETWORK to configure, but it "
                "needs a real shared drive (NAS or SMB) to work as a "
                "team. Do not put the project on Dropbox, Google Drive "
                "or OneDrive: with those, the other machines may not "
                "see a lock update right away, and two people can end "
                "up saving over each other."
            ),
        ),
        (
            "One rule.",
            (
                "Never rename, move or hand-edit project files, names, "
                "or the config outside the addon. ALWAYS go through the "
                "BUTTUNS. The addon assumes it owns the structure; "
                "editing it by hand silently breaks the links and the "
                "tracking."
            ),
        ),
    )

    def invoke(self, context, event):
        # onboarding_seen isn't touched here: this operator also serves the
        # Help icon and the empty-state button, which must keep opening the
        # popup forever regardless of that flag. Only the startup timer
        # (_deferred_onboarding in __init__.py) marks it seen.
        return context.window_manager.invoke_popup(self, width=self._POPUP_WIDTH)

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)

        max_width = 120
        hook = (
            "Minimalist Pipeline NAMES and VERSIONS your files FOR YOU, "
            "proposes actions instead of forcing them, and runs "
            "entirely from your project folder, NO SERVEUR required."
        )
        text_to_lines(
            col.box(),
            hook,
            max_width=max_width,
            icon="OUTLINER_OB_LIGHT",
            max_lines=lines_budget(hook, base=3, cap=8),
        )
        col.separator(factor=3)

        for idx, text in enumerate(self._SECTIONS):
            title, body = text
            block = col.column(align=True)
            block.scale_y = 0.8
            block.active = True
            block.box().label(text=title.upper(), icon=f"EVENT_NDOF_BUTTON_{idx + 1}")
            text_box = block.box()
            text_row = text_box.row()
            text_row.separator(factor=0.7)
            text_row.active = False
            text_to_lines(
                text_row,
                body,
                max_width=max_width,
                max_lines=lines_budget(body, base=3, cap=8),
            )
            text_box.separator(factor=0.75)

        col.separator(factor=3)
        block = col.column(align=True)
        block.scale_y = 0.8
        block.box().label(text="HOW TO START.", icon="EVENT_RIGHT_ARROW")
        closing = (
            "New Project, then New Asset. Everything else is "
            "proposed when it's useful, so you don't have to memorize a "
            "procedure."
        )
        text_box = block.box()
        text_row = text_box.row()
        text_row.separator(factor=0.7)
        text_to_lines(
            text_row,
            closing,
            max_width=max_width,
            max_lines=lines_budget(closing, base=3, cap=8),
        )
        text_box.separator(factor=0.75)
        col.box().label(
            text="You're familiar with the add-on? Hide tooltips in the add-on's preferences.",
            icon="HIDE_OFF",
        )

    def execute(self, context):
        return {"FINISHED"}


class PIPELINE_OT_auto_version(bpy.types.Operator):
    """Check file date on load, propose version increment."""

    bl_idname = "pipeline.auto_version"
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
            log(e.level, "auto_version", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}

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
    bl_idname = "wm.open_folder"
    bl_label = "Open Folder"

    filepath: bpy.props.StringProperty()

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


class PIPELINE_OT_current_frame(bpy.types.Operator):
    """Jump to specified frame"""

    bl_idname = "pipeline.current_frame"
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
