"""The team (Edit project's Team): picking one's user name from it, and
assigning a file's departments to its people. See NOTES.md, "Team and
assignees"."""

from pathlib import Path

import bpy

from ..lib import (
    PipelineError,
    TrackingStatusCache,
    addon_pref,
    project_team,
    report_error,
    set_department_assignees,
    status_changed,
)


def _team() -> list[str]:
    """The active project's team, [] with no project (Preferences)."""
    try:
        return project_team()
    except Exception:
        return []


class M_PIPELINE_OT_pick_user_name(bpy.types.Operator):
    """Your user name: this team member's"""

    bl_idname = "m_pipeline.pick_user_name"
    bl_label = "Pick your name"
    bl_options = {"INTERNAL"}

    name: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        prefs = addon_pref(context)
        if prefs:
            prefs.user_name = self.name
        return {"FINISHED"}


class M_PIPELINE_MT_team_names(bpy.types.Menu):
    """The active project's team, to pick one's user name from."""

    bl_idname = "M_PIPELINE_MT_team_names"
    bl_label = "Team"

    def draw(self, context):
        team = _team()
        if not team:
            self.layout.label(text="No team set: Edit project > Team", icon="INFO")
            return
        prefs = addon_pref(context)
        mine = (prefs.user_name if prefs else "").lower()
        for name in team:
            self.layout.operator(
                "m_pipeline.pick_user_name",
                text=name,
                icon="CHECKMARK" if name == mine else "USER",
            ).name = name


def draw_user_name(layout, prefs, text: str = "") -> None:
    """The user name's field, then a menu to pick it from the team -- and a
    warning when the project has a team it isn't in (the "Me" filter, the
    assignments, go by it)."""
    row = layout.row(align=True)
    row.prop(prefs, "user_name", text=text)
    team = _team()
    if team:
        row.menu("M_PIPELINE_MT_team_names", text="", icon="COMMUNITY")
        if prefs.user_name.lower() not in team:
            warn = layout.row()
            warn.alert = True
            warn.label(text="Not in the project's team: pick your name", icon="ERROR")


class M_PIPELINE_OT_toggle_assignee(bpy.types.Operator):
    """Assign this department to them, or not any more"""

    bl_idname = "m_pipeline.toggle_assignee"
    bl_label = "Assign"
    bl_options = {"INTERNAL"}

    filepath: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    department: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    person: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        status = TrackingStatusCache.get(filepath=self.filepath) or {}
        people = list((status.get("assignees") or {}).get(self.department) or [])
        if self.person in people:
            people.remove(self.person)
        else:
            people.append(self.person)
        try:
            set_department_assignees(Path(self.filepath), self.department, people)
        except PipelineError as e:
            return report_error(self, "assign", e)
        status_changed(self.filepath)
        return {"FINISHED"}


class M_PIPELINE_OT_assign_department(bpy.types.Operator):
    """Assign this department: the team, each ticked or not"""

    bl_idname = "m_pipeline.assign_department"
    bl_label = "Assign"
    bl_options = {"INTERNAL"}

    filepath: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    department: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    custom_tooltip: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        return properties.custom_tooltip or cls.__doc__

    def invoke(self, context, event):
        team = _team()
        status = TrackingStatusCache.get(filepath=self.filepath) or {}
        people = (status.get("assignees") or {}).get(self.department) or []
        # Someone assigned who left the team: still listed, to unassign.
        names = team + [p for p in people if p not in team]
        filepath, department = self.filepath, self.department

        def draw(menu, _context):
            if not names:
                menu.layout.label(text="No team set: Edit project > Team", icon="INFO")
                return
            for name in names:
                op = menu.layout.operator(
                    "m_pipeline.toggle_assignee",
                    text=name,
                    icon="CHECKBOX_HLT" if name in people else "CHECKBOX_DEHLT",
                )
                op.filepath, op.department, op.person = filepath, department, name

        context.window_manager.popup_menu(draw, title=f"{department.capitalize()}: assigned to", icon="COMMUNITY")
        return {"FINISHED"}

    def execute(self, context):
        return {"FINISHED"}


classes = (
    M_PIPELINE_OT_pick_user_name,
    M_PIPELINE_MT_team_names,
    M_PIPELINE_OT_toggle_assignee,
    M_PIPELINE_OT_assign_department,
)
