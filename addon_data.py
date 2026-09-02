"""Addon data: preferences and property groups."""

import bpy


class PipelineProjectItem(bpy.types.PropertyGroup):
    """A project in the opened projects list."""

    name: bpy.props.StringProperty(name="Project name")
    path: bpy.props.StringProperty(name="Project path")


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
    )

    user_name: bpy.props.StringProperty(
        name="User name",
        default="",
        description="Your name (used in logs).",
    )

    auto_worker_on_open: bpy.props.BoolProperty(
        name="Auto-launch worker",
        description="Automatically make this machine a farm worker when a "
        "project becomes active (on Blender startup, or when switching projects).",
        default=False,
    )
    always_read_only: bpy.props.BoolProperty(
        name="Always open read-only",
        description="Always open project files as read-only, regardless of "
        "file lock or -stable tag. Safe default for review/playblast machines.",
        default=False,
    )

    onboarding_seen: bpy.props.BoolProperty(
        name="Onboarding seen",
        description="Internal: the first-launch popup has already been shown.",
        default=False,
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
    )

    def draw(self, context):
        layout = self.layout

        prefs = layout.row()

        col_toggles = prefs.column()
        col_toggles.label(text="Pipeline Automations:")

        col_toggles.prop(self, "silent_auto_increment")
        col_toggles.prop(self, "auto_worker_on_open")
        col_toggles.prop(self, "always_read_only")

        col_infos = prefs.column()
        col_infos.label(text="User Infos:")

        col_infos.prop(self, "user_name")
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

        layout.separator(type="LINE")
        row = layout.row()
        row.prop(self, "experience_level", expand=True)
        row.operator(
            "pipeline.onboarding_popup",
            text="What this addon does",
            icon="QUESTION",
        )
