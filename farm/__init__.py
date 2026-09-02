"""Render farm: monitor/worker roles, job queue, dispatch, and post-render pipeline."""

from .dispatch import render_dispatch
from .loop import (
    _compute_snapshot,
    _refresh_tick,
    get_running_project,
    refresh_monitor_cache,
    register_popup_region,
    register_refresh_timer,
    stop_farm_role_for_project,
    unregister_refresh_timer,
)
from .monitor import (
    archive,
    get_monitor_cache,
    job_cancel_request,
    job_request,
    launch_monitor,
    monitor_request,
    register_farm_loop,
    request_monitor_kill,
    request_preview_compile,
    reset_monitor_cache,
    stop_monitor_loop,
)
from .post_render import checks_images, compilation, run_preview_compile
from .queue import (
    scan_processes,
    scan_queue,
    scan_requests,
)
from .setup import (
    compute_output_path,
    resolve_job_context,
    resolve_override_range,
    run_render_setup,
    run_render_setup_entry,
)
from .workers import (
    apply_custom_preset,
    is_blender_worker,
    kill_worker,
    launch_worker,
    scan_workers,
)
