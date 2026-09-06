"""Pipeline operators."""

from .asset_ops import M_PIPELINE_OT_create_asset
from .batch_ops import M_PIPELINE_OT_batch_create
from .browser_ops import M_PIPELINE_OT_open_file, M_PIPELINE_OT_open_file_version
from .farm_ops import (
    M_PIPELINE_OT_farm_add_self_worker,
    M_PIPELINE_OT_farm_add_to_list,
    M_PIPELINE_OT_farm_archive_job,
    M_PIPELINE_OT_farm_cancel_job,
    M_PIPELINE_OT_farm_kill_monitor,
    M_PIPELINE_OT_farm_kill_self_worker,
    M_PIPELINE_OT_farm_launch_monitor,
    M_PIPELINE_OT_farm_list_delete,
    M_PIPELINE_OT_farm_monitor,
    M_PIPELINE_OT_farm_request_render,
    PIPELINE_PG_farm_list_item,
    PIPELINE_PG_render_subshot_item,
)
from .file_ops import M_PIPELINE_OT_increment_version
from .preview_ops import M_PIPELINE_OT_compile_preview
from .project_ops import (
    M_PIPELINE_OT_create_project,
    M_PIPELINE_OT_edit_project,
    M_PIPELINE_OT_find_project,
    M_PIPELINE_OT_remove_project,
    M_PIPELINE_OT_set_active_project,
    M_PIPELINE_OT_unset_active_project,
)
from .shot_ops import (
    M_PIPELINE_OT_add_multishot_item,
    M_PIPELINE_OT_create_shot,
    M_PIPELINE_OT_edit_block_structure,
    M_PIPELINE_OT_remove_multishot_item,
    PipelineShotItem,
)
from .tracking_ops import (
    M_PIPELINE_OT_add_entry_line,
    M_PIPELINE_OT_create_entry,
    M_PIPELINE_OT_delete_entry,
    M_PIPELINE_OT_department_status_info,
    M_PIPELINE_OT_edit_description,
    M_PIPELINE_OT_edit_entry,
    M_PIPELINE_OT_generic_entry_button,
    M_PIPELINE_OT_remove_entry_line,
    M_PIPELINE_OT_toggle_entry_task,
    M_PIPELINE_OT_toggle_validated_department,
    M_PIPELINE_OT_toggle_worked_department,
    M_PIPELINE_OT_tracking_file_details,
    M_PIPELINE_OT_tracking_monitor,
    M_PIPELINE_OT_upload_csv,
    PipelineEntryItem,
)

classes = (
    M_PIPELINE_OT_create_project,
    M_PIPELINE_OT_find_project,
    M_PIPELINE_OT_set_active_project,
    PipelineShotItem,
    M_PIPELINE_OT_remove_project,
    M_PIPELINE_OT_compile_preview,
    M_PIPELINE_OT_create_asset,
    M_PIPELINE_OT_create_shot,
    M_PIPELINE_OT_edit_block_structure,
    M_PIPELINE_OT_add_multishot_item,
    M_PIPELINE_OT_remove_multishot_item,
    M_PIPELINE_OT_batch_create,
    M_PIPELINE_OT_increment_version,
    M_PIPELINE_OT_open_file,
    M_PIPELINE_OT_edit_project,
    M_PIPELINE_OT_unset_active_project,
    M_PIPELINE_OT_farm_add_to_list,
    M_PIPELINE_OT_farm_kill_monitor,
    M_PIPELINE_OT_farm_launch_monitor,
    M_PIPELINE_OT_farm_request_render,
    PIPELINE_PG_farm_list_item,
    PIPELINE_PG_render_subshot_item,
    M_PIPELINE_OT_farm_list_delete,
    M_PIPELINE_OT_toggle_worked_department,
    M_PIPELINE_OT_toggle_validated_department,
    M_PIPELINE_OT_department_status_info,
    M_PIPELINE_OT_create_entry,
    M_PIPELINE_OT_delete_entry,
    M_PIPELINE_OT_edit_description,
    M_PIPELINE_OT_edit_entry,
    M_PIPELINE_OT_toggle_entry_task,
    M_PIPELINE_OT_upload_csv,
    M_PIPELINE_OT_tracking_monitor,
    M_PIPELINE_OT_open_file_version,
    M_PIPELINE_OT_tracking_file_details,
    M_PIPELINE_OT_farm_add_self_worker,
    M_PIPELINE_OT_farm_monitor,
    M_PIPELINE_OT_farm_kill_self_worker,
    M_PIPELINE_OT_farm_cancel_job,
    M_PIPELINE_OT_farm_archive_job,
    PipelineEntryItem,
    M_PIPELINE_OT_add_entry_line,
    M_PIPELINE_OT_remove_entry_line,
    M_PIPELINE_OT_generic_entry_button,
)

__all__ = ["classes"]
