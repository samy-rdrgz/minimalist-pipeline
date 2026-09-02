bl_info = {
    "name": "Minimalist Pipeline",
    "author": "Samy Rodriguez",
    "version": (1, 0, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Pipeline",
    "description": "Lightweight pipeline manager for solo/small team Blender projects.",
    "category": "Pipeline",
}

import getpass
import importlib
import sys
from pathlib import Path

import bpy

addon_name = "minimalist_pipeline"
if "bpy" in locals():
    # Addon already loaded: force every already-imported submodule to reload.
    for module_name in list(sys.modules):
        if module_name.startswith(addon_name + "."):
            try:
                importlib.reload(sys.modules[module_name])
            except Exception:
                pass

from . import addon_data, lib
from .farm.loop import (
    refresh_monitor_cache,
    set_running_project,
    unregister_refresh_timer,
)
from .lib.saving import override_shortcut, unoverride_shortcut
from .menus import classes as menu_classes
from .menus import register_topbar_menu, unregister_topbar_menu
from .operators import (
    PIPELINE_PG_farm_list_item,
    PIPELINE_PG_render_subshot_item,
    PipelineEntryItem,
    PipelineShotItem,
)
from .operators import classes as operator_classes
from .panels import classes as panel_classes


class PIPELINE_PT_main_panel(bpy.types.Panel):
    """Pipeline Manager main panel (header only; every other panel is a child of it)."""

    bl_label = "Pipeline Manager"
    bl_idname = "PIPELINE_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Pipeline"

    def draw(self, context):
        pass

    def draw_header(self, context):
        self.layout.operator(
            "pipeline.onboarding_popup", text="", icon="QUESTION", emboss=False
        )


# Registration order matters: addon_data before anything reading preferences,
# everything else before the topbar menu that references their operators.
classes = (
    *lib.classes,
    addon_data.PipelineProjectItem,
    addon_data.PipelineAddonPreferences,
    PIPELINE_PT_main_panel,
    *panel_classes,
    *operator_classes,
    *menu_classes,
)

# WindowManager/Scene properties this addon adds outside of the PropertyGroups
# above -- one declarative table, (un)registered by the same small loop below
# instead of ad hoc blocks per call site.
_WM_PROPS = {
    "projects_collapse": bpy.props.BoolProperty(name="", default=True),
    "entries_collapse": bpy.props.BoolProperty(name="", default=False),
    "pipeline_entry_buffer": bpy.props.CollectionProperty(type=PipelineEntryItem),
    "shots_list_creation": bpy.props.CollectionProperty(type=PipelineShotItem),
    "render_subshots": bpy.props.CollectionProperty(
        type=PIPELINE_PG_render_subshot_item
    ),
    "file_details_selected": bpy.props.StringProperty(),
    "file_selected_departments": bpy.props.StringProperty(),
    # entries_department_filter is the addon's one Scene/WM-level EnumProperty
    # used as a live filter (everything else here is a toggle/buffer) -- see
    # draw_entries() in panels/tracking_panel.py.
    "entries_hide_done": bpy.props.BoolProperty(name="", default=True),
    "entries_department_filter": bpy.props.EnumProperty(
        items=lib.department_filter_items
    ),
    "entries_min_version": bpy.props.IntProperty(name="", default=0, min=0),
}
_SCENE_PROPS = {
    "is_worker": bpy.props.BoolProperty(name="", default=False),
    "pipeline_farm_list": bpy.props.CollectionProperty(type=PIPELINE_PG_farm_list_item),
}


def _register_props(owner, props: dict):
    for name, prop in props.items():
        try:
            setattr(owner, name, prop)
        except Exception as e:
            print(f"[{addon_name}] could not register {owner.__name__}.{name}: {e}")


def _unregister_props(owner, props: dict):
    for name in props:
        try:
            delattr(owner, name)
        except Exception:
            pass


def _seed_user_name():
    """Seed user_name from the OS login on first register, so it's never
    silently blank -- get_user() falls back to the same getpass.getuser() at
    read time too, but only in memory; leaving the pref itself empty means
    the Preferences panel shows nothing configured, and a shared-machine
    login never gets a chance to be corrected to the actual person. getpass,
    not os.getlogin(): the latter needs a controlling terminal and reliably
    fails without one (desktop icon, Steam, the VS Code extension...). Only
    seeds once: never overwrites an already-set name."""
    try:
        prefs = lib.addon_pref()
        if prefs and not prefs.user_name:
            prefs.user_name = getpass.getuser()
    except Exception as e:
        print(e)


def _deferred_keymap():
    """Install the Ctrl+S override once the addon keyconfig exists (not ready at register() time)."""
    if bpy.context.window_manager.keyconfigs.addon:
        override_shortcut()


def _deferred_project_check():
    """Startup-only: deactivate the active project if its folder isn't
    reachable (NAS disconnected, drive unmapped). Otherwise farm_panel.py's
    poll() (needs no file open) redraws forever, each redraw resolving/
    stat-ing a path under the dead mount -- freezes Blender's UI thread solid.
    Doesn't protect against the NAS dropping mid-session, startup only."""
    try:
        prefs = lib.addon_pref()
        root = prefs.active_project_root if prefs else ""
        if root and not Path(root).exists():
            bpy.ops.pipeline.unset_active_project()
            lib.set_pending_action(
                lib.PipelineAction(
                    title="Active project unreachable",
                    message=(
                        f"Folder not found, deactivated:\n{root}\n\n"
                        "Reconnect it, then re-activate from the project list."
                    ),
                    severity="warning",
                )
            )
            bpy.ops.pipeline.action_popup("INVOKE_DEFAULT")
    except Exception as e:
        print(e)


def _deferred_auto_worker():
    """Launch the worker role on startup if auto_worker_on_open is on and a
    project is already active. Deferred like _deferred_keymap: bpy.context.scene
    (and the Scene.is_worker property registered above) aren't reliably ready
    at register() time. Runs after _deferred_project_check so a since-
    deactivated project never gets a worker launched for it."""
    try:
        prefs = lib.addon_pref()
        if prefs and prefs.auto_worker_on_open and prefs.active_project_root:
            from .farm.workers import launch_worker

            launch_worker()
    except Exception as e:
        print(e)


def _deferred_onboarding():
    """First launch only: show the welcome popup once, then never again on
    its own (still reachable anytime from the main panel's Help icon).
    Skipped in background mode (bpy.app.background) -- e.g. the farm's
    headless render workers load this addon too, and invoke_popup has no
    window to attach to there."""
    if bpy.app.background:
        return
    try:
        prefs = lib.addon_pref()
        if prefs and not prefs.onboarding_seen:
            # Marked seen here, not in the operator itself: invoke_popup()
            # gives no feedback on whether it actually rendered, so "seen"
            # really means "we tried once at startup" -- the empty-state
            # project panel and the header's Help icon stay available
            # regardless, as a reliable fallback if this attempt was missed
            # (behind another window, timing raced with another startup
            # popup, etc.).
            prefs.onboarding_seen = True
            bpy.ops.pipeline.onboarding_popup("INVOKE_DEFAULT")
    except Exception as e:
        print(e)


def register():
    """Register all classes, restore backed-up projects, and start handlers/timers."""
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            # Already registered (hot-reload or dual path)
            bpy.utils.unregister_class(cls)
            bpy.utils.register_class(cls)

    _register_props(bpy.types.WindowManager, _WM_PROPS)
    _register_props(bpy.types.Scene, _SCENE_PROPS)

    register_topbar_menu()
    lib.register_handlers()

    try:
        lib.load_project_data(lib.addon_pref())
        # load_project_data() bypasses set_active_project_root(), so the
        # monitor cache is still blank here -- refresh it once.
        refresh_monitor_cache()
    except lib.PipelineError:
        pass

    _seed_user_name()
    set_running_project(None)

    bpy.app.timers.register(_deferred_keymap, first_interval=0.1)
    bpy.app.timers.register(_deferred_project_check, first_interval=0.05)
    bpy.app.timers.register(_deferred_auto_worker, first_interval=0.1)
    # After the other startup popups (project_check can pop one of its own),
    # not concurrent with them -- Blender only really wants one invoke_popup
    # fighting for the window at a time.
    bpy.app.timers.register(_deferred_onboarding, first_interval=0.5)


def unregister():
    """Stop handlers/timers/farm roles, back up projects, and unregister all classes."""
    lib.unregister_handlers()
    unregister_topbar_menu()

    try:
        lib.save_project_data(lib.addon_pref())
    except Exception:
        pass

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

    _unregister_props(bpy.types.WindowManager, _WM_PROPS)
    _unregister_props(bpy.types.Scene, _SCENE_PROPS)

    try:
        unregister_refresh_timer()
        from .farm.loop import _farm_running_project
        from .farm.monitor import stop_monitor_loop
        from .farm.workers import is_blender_worker, kill_worker

        if _farm_running_project is not None:
            stop_monitor_loop()
        if is_blender_worker():
            kill_worker()
    except Exception as e:
        print(e)
    unoverride_shortcut()


if __name__ == "__main__":
    register()
