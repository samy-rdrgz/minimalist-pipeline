"""Pipeline core library: re-exports all public symbols for backward compatibility."""

from .actions import (
    PipelineAction,
    get_pending_action,
    set_pending_action,
)
from .batch import (
    asset_batch_exists,
    launch_batch_create_entry,
    parse_asset_batch_csv,
    parse_shot_batch_csv,
    read_batch_result,
    resolve_batch_departments,
    shot_batch_exists,
)
from .browser import (
    asset_department_items,
    asset_folder_items,
    department_filter_items,
    dir_version_items,
    entry_version_items,
    file_department_items,
    get_folder,
    prefix_items,
    sequence_items,
    shot_department_items,
    shot_items,
    shot_tag_items,
    tracked_department_items,
    version_items,
)
from .config import (
    ConfigCache,
    file_in_active_project,
    find_known_project_for_file,
    find_project_root,
    format_camera_name,
    format_shot_segment,
    get_active_project_root,
    get_base_filename,
    get_config_filepath,
    parse_camera_name,
    parse_filename,
    prefix_to_parent_folder,
    read_project_config,
    sanitize_name,
    set_daemon_active_project_root,
    shots_in_segment,
    to_absolute,
    to_relative,
    type_by_folder,
)
from .core import (
    addon_pref,
    draw_box_tip,
    get_addon_version,
    get_machine_id,
    json_get,
    lines_budget,
    list_to_labels,
    locked_json,
    now,
    path_reachable,
    read_csv,
    region_char_budget,
    resolve_bpy_path,
    responsive_layout,
    text_to_lines,
)
from .creation import (
    DEFAULT_ASSET_DEPARTMENTS,
    DEFAULT_SHOT_DEPARTMENTS,
    create_asset_file,
    create_shot_file,
    resolve_timeline,
)
from .errors import PipelineError
from .handlers import (
    heartbeat_30s,
    on_quit_handler,
    post_load_handler,
    refresh_read_only_flag,
    register_handlers,
    unregister_handlers,
)
from .libraries import clean_append_and_relink
from .logs import log
from .operators import (
    PIPELINE_OT_action_popup,
    PIPELINE_OT_auto_version,
    PIPELINE_OT_current_frame,
    PIPELINE_OT_onboarding_popup,
    PIPELINE_OT_text_popup,
    WM_OT_open_folder,
)
from .presets import (
    apply_asset_preset,
    build_shot_scene,
    derive_shot_subranges,
    install_default_ffmpeg_preset,
    install_default_preset,
)
from .preview import (
    latest_shot_mp4,
    resolve_block_sources,
    resolve_sequence_sources,
)
from .saving import WM_OT_safe_save, get_save_shortcut
from .session import (
    close_session,
    get_opened_as_read_only,
    get_read_only_reason,
    get_user,
    get_user_data,
    load_project_data,
    save_project_data,
    scan_sessions,
    session_update,
    set_active_project_root,
    set_opened_as_read_only,
)
from .tracking import (
    RecentFilesCache,
    TrackingStatusCache,
    WorkTimeCache,
    active_shot_owners,
    archive_folder,
    copy_entries,
    create_entry,
    create_stablemeta,
    create_tracking,
    create_wipmeta,
    delete_entry,
    department_status_tooltip,
    edit_entry,
    filter_review_boxes,
    format_duration,
    get_current_departments,
    get_departments_required,
    get_description,
    get_entries,
    get_entries_grouped,
    get_last_stable,
    get_session_worked_departments,
    group_entries_by_review,
    is_block_archived,
    list_active_blocks,
    set_department_validated,
    set_description,
    toggle_entry_task,
    upload_csv,
    wipmeta_add_link,
    wipmeta_add_work,
)
from .versioning import (
    get_last_version_number,
    get_version_number,
    save_as,
)

classes = (
    PIPELINE_OT_action_popup,
    PIPELINE_OT_auto_version,
    PIPELINE_OT_onboarding_popup,
    PIPELINE_OT_text_popup,
    WM_OT_safe_save,
    WM_OT_open_folder,
    PIPELINE_OT_current_frame,
)

__all__ = ["classes"]
