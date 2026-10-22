"""Pipeline UI panels."""

from .farm_panel import (
    M_PIPELINE_PT_farm_panel,
    draw_farm_job_details,
    draw_farm_jobs,
    draw_farm_worker_details,
    draw_farm_workers,
)
from .file_panel import M_PIPELINE_PT_file_panel
from .logs_panel import (
    draw_pipeline_logs,
    load_pipeline_log,
    log_read_at,
    log_values,
)
from .monitoring_panel import M_PIPELINE_PT_farm_monitoring, M_PIPELINE_PT_monitoring
from .project_panel import M_PIPELINE_PT_project_panel
from .tracking_panel import (
    TYPE_ICON,
    draw_entries,
    draw_file_details,
    draw_monitor_table,
    draw_tracking_data,
    load_file_renders,
    load_file_thumbnail,
    popup_width,
    unregister_thumbnail_previews,
)

classes = (
    M_PIPELINE_PT_file_panel,
    M_PIPELINE_PT_project_panel,
    M_PIPELINE_PT_farm_panel,
    M_PIPELINE_PT_monitoring,
    M_PIPELINE_PT_farm_monitoring,
)

__all__ = ["classes"]
