"""Addon data: preferences and property groups."""

import bpy

from .lib import draw_addon_keys, save_settings, validation_roles


class PipelineProjectItem(bpy.types.PropertyGroup):
    """A project in the opened projects list."""

    name: bpy.props.StringProperty(name="Project name")
    path: bpy.props.StringProperty(name="Project path")


def _role_search(self, context, edit_text):
    """The active project's validation roles, for the role field."""
    return [r["name"] for r in validation_roles()]


class PipelineAddonPreferences(bpy.types.AddonPreferences):
    """Addon preferences: active project, settings, user identity."""

    bl_idname = __package__

    active_project_root: bpy.props.StringProperty(
        name="Active project",
        default="",
        description="Active project root path.",
    )

    machine_id: bpy.props.StringProperty(
        name="Machine ID",
        default="",
        description="Unique id by machine.",
    )

    opened_projects: bpy.props.CollectionProperty(type=PipelineProjectItem)

    silent_auto_increment: bpy.props.BoolProperty(
        name="Silent auto-increment",
        description="On the first file open of the day (already on the latest "
        "version), increment silently instead of asking for confirmation.",
        default=False,
        update=save_settings,
    )

    user_name: bpy.props.StringProperty(
        name="User name",
        default="",
        description="Your name (used in logs).",
        update=save_settings,
    )

    user_role: bpy.props.StringProperty(
        name="Validation role",
        default="",
        description="The validation role you review as (e.g. sup, prod -- "
        "Edit project lists them): your notes are marked with it, and you can "
        "validate departments for it. Empty: a team member",
        search=_role_search,
        update=save_settings,
    )

    auto_worker_on_open: bpy.props.BoolProperty(
        name="Auto-launch worker",
        description="Automatically make this machine a farm worker when a "
        "project becomes active (on Blender startup, or when switching projects).",
        default=False,
        update=save_settings,
    )
    always_read_only: bpy.props.BoolProperty(
        name="Always open read-only",
        description="Always open project files as read-only, regardless of "
        "file lock or -stable tag. Safe default for review/playblast machines.",
        default=False,
        update=save_settings,
    )

    ffmpeg_path: bpy.props.StringProperty(
        name="FFmpeg path",
        subtype="FILE_PATH",
        default="",
        description="Optional: explicit path to the ffmpeg binary, for setups "
        "where it isn't found on Blender's PATH (e.g. Blender launched through "
        "a sandboxed runtime such as Steam's). Leave blank to auto-detect.",
        update=save_settings,
    )

    # The preferences' Shortcuts section, folded by default: UI state only.
    show_shortcuts: bpy.props.BoolProperty(name="Shortcuts", default=False)

    onboarding_seen: bpy.props.BoolProperty(
        name="Onboarding seen",
        description="Internal: the first-launch popup has already been shown.",
        default=False,
        update=save_settings,
    )

    experience_level: bpy.props.EnumProperty(
        name="Experience level",
        description="Beginner shows short inline explanations of pipeline "
        "concepts (versions, stable, links...) next to the relevant buttons.",
        items=[
            ("BEGINNER", "Beginner", "Show inline concept explanations"),
            ("ADVANCED", "Advanced", "Hide inline concept explanations"),
        ],
        default="BEGINNER",
        update=save_settings,
    )

    def draw(self, context):
        layout = self.layout

        prefs = layout.row()

        col_toggles = prefs.column()
        col_toggles.label(text="Pipeline Automations:")

        col_toggles.prop(self, "silent_auto_increment")
        col_toggles.prop(self, "auto_worker_on_open")
        col_toggles.prop(self, "always_read_only")
        col_toggles.prop(self, "ffmpeg_path")

        col_infos = prefs.column()
        col_infos.label(text="User Infos:")

        col_infos.prop(self, "user_name")
        col_infos.prop(self, "user_role")
        ro = col_infos.column()
        ro.active = False
        ro.enabled = False
        ro.prop(self, "machine_id")
        ro.prop(self, "active_project_root")

        layout.separator()

        layout.label(text="Known projects:")
        col = layout.column()
        col.active = False
        col.enabled = False
        if self.opened_projects:
            for p in self.opened_projects:
                col.prop(p, "path", text=" • " + p.name)
        else:
            col.label(text=" • No projects")

        layout.separator()
        fold = layout.row()
        fold.alignment = "LEFT"
        fold.prop(
            self,
            "show_shortcuts",
            icon="DISCLOSURE_TRI_DOWN" if self.show_shortcuts else "DISCLOSURE_TRI_RIGHT",
            emboss=False,
        )
        if self.show_shortcuts:
            keys = layout.box()
            tip = keys.row()
            tip.active = False
            tip.label(
                text="Tick a shortcut to use it; click its key to change it.",
                icon="INFO",
            )
            draw_addon_keys(context, keys)

        layout.separator(type="LINE")
        row = layout.row()
        row.prop(self, "experience_level", expand=True)
        row.operator(
            "m_pipeline.onboarding_popup",
            text="What this addon does",
            icon="QUESTION",
        )
