"""Pipeline operators."""

from .asset_ops import PIPELINE_OT_create_asset
from .batch_ops import PIPELINE_OT_batch_create
from .browser_ops import PIPELINE_OT_open_file, PIPELINE_OT_open_file_version
from .farm_ops import (
    PIPELINE_OT_farm_add_self_worker,
    PIPELINE_OT_farm_add_to_list,
    PIPELINE_OT_farm_archive_job,
    PIPELINE_OT_farm_cancel_job,
    PIPELINE_OT_farm_kill_monitor,
    PIPELINE_OT_farm_kill_self_worker,
    PIPELINE_OT_farm_launch_monitor,
    PIPELINE_OT_farm_list_delete,
    PIPELINE_OT_farm_monitor,
    PIPELINE_OT_farm_request_render,
    PIPELINE_PG_farm_list_item,
    PIPELINE_PG_render_subshot_item,
)
from .file_ops import PIPELINE_OT_increment_version
from .preview_ops import PIPELINE_OT_compile_preview
from .project_ops import (
    PIPELINE_OT_create_project,
    PIPELINE_OT_edit_project,
    PIPELINE_OT_find_project,
    PIPELINE_OT_remove_project,
    PIPELINE_OT_set_active_project,
    PIPELINE_OT_unset_active_project,
)
from .shot_ops import (
    PIPELINE_OT_add_multishot_item,
    PIPELINE_OT_branch_shot,
    PIPELINE_OT_create_shot,
    PIPELINE_OT_remove_multishot_item,
    PipelineShotItem,
)
from .tracking_ops import (
    TYPE_ICON,
    PIPELINE_OT_add_entry_line,
    PIPELINE_OT_create_entry,
    PIPELINE_OT_delete_entry,
    PIPELINE_OT_department_status_info,
    PIPELINE_OT_edit_description,
    PIPELINE_OT_edit_entry,
    PIPELINE_OT_generic_entry_button,
    PIPELINE_OT_remove_entry_line,
    PIPELINE_OT_toggle_entry_task,
    PIPELINE_OT_toggle_validated_department,
    PIPELINE_OT_toggle_worked_department,
    PIPELINE_OT_tracking_file_details,
    PIPELINE_OT_tracking_monitor,
    PIPELINE_OT_upload_csv,
    PipelineEntryItem,
)

classes = (
    PIPELINE_OT_create_project,
    PIPELINE_OT_find_project,
    PIPELINE_OT_set_active_project,
    PipelineShotItem,
    PIPELINE_OT_remove_project,
    PIPELINE_OT_compile_preview,
    PIPELINE_OT_create_asset,
    PIPELINE_OT_create_shot,
    PIPELINE_OT_branch_shot,
    PIPELINE_OT_add_multishot_item,
    PIPELINE_OT_remove_multishot_item,
    PIPELINE_OT_batch_create,
    PIPELINE_OT_increment_version,
    PIPELINE_OT_open_file,
    PIPELINE_OT_edit_project,
    PIPELINE_OT_unset_active_project,
    PIPELINE_OT_farm_add_to_list,
    PIPELINE_OT_farm_kill_monitor,
    PIPELINE_OT_farm_launch_monitor,
    PIPELINE_OT_farm_request_render,
    PIPELINE_PG_farm_list_item,
    PIPELINE_PG_render_subshot_item,
    PIPELINE_OT_farm_list_delete,
    PIPELINE_OT_toggle_worked_department,
    PIPELINE_OT_toggle_validated_department,
    PIPELINE_OT_department_status_info,
    PIPELINE_OT_create_entry,
    PIPELINE_OT_delete_entry,
    PIPELINE_OT_edit_description,
    PIPELINE_OT_edit_entry,
    PIPELINE_OT_toggle_entry_task,
    PIPELINE_OT_upload_csv,
    PIPELINE_OT_tracking_monitor,
    PIPELINE_OT_open_file_version,
    PIPELINE_OT_tracking_file_details,
    PIPELINE_OT_farm_add_self_worker,
    PIPELINE_OT_farm_monitor,
    PIPELINE_OT_farm_kill_self_worker,
    PIPELINE_OT_farm_cancel_job,
    PIPELINE_OT_farm_archive_job,
    PipelineEntryItem,
    PIPELINE_OT_add_entry_line,
    PIPELINE_OT_remove_entry_line,
    PIPELINE_OT_generic_entry_button,
)

__all__ = ["classes"]
