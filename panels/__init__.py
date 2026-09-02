"""Pipeline UI panels."""

from .farm_panel import PIPELINE_PT_farm_panel
from .file_panel import PIPELINE_PT_file_panel
from .project_panel import PIPELINE_PT_project_panel
from .tracking_panel import (
    TYPE_ICON,
    draw_entries,
    draw_file_details,
    draw_tracking_data,
)

classes = (
    PIPELINE_PT_file_panel,
    PIPELINE_PT_project_panel,
    PIPELINE_PT_farm_panel,
)

__all__ = ["classes"]
