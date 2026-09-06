"""Pipeline UI panels."""

from .farm_panel import M_PIPELINE_PT_farm_panel, draw_farm_jobs, draw_farm_workers
from .file_panel import M_PIPELINE_PT_file_panel
from .project_panel import M_PIPELINE_PT_project_panel
from .tracking_panel import (
    TYPE_ICON,
    draw_entries,
    draw_file_details,
    draw_monitor_table,
    draw_tracking_data,
)

classes = (
    M_PIPELINE_PT_file_panel,
    M_PIPELINE_PT_project_panel,
    M_PIPELINE_PT_farm_panel,
)

__all__ = ["classes"]
