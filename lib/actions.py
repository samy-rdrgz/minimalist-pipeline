from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class PipelineAction:
    """A detected condition the addon proposes to the artist. Core pattern:
    Detect -> Inform -> Propose -> Execute -- every feature creates one of
    these, a single operator (pipeline.action_popup) displays them all.
    severity: "info" (status bar) | "warning" | "critical" (both modal).
    choices: list of (label, callback) or (label, callback, tooltip). Usage:
    set_pending_action(action), then bpy.ops.pipeline.action_popup('INVOKE_DEFAULT').
    on_dismiss: run by action_popup's cancel() when the popup is dismissed
    without clicking a choice (Escape / click-away) -- for cleanup that must
    happen regardless of which button (if any) was clicked, e.g. releasing a
    resource acquired before the popup was opened."""

    title: str = ""
    message: str = ""
    severity: str = "info"
    choices: list[tuple[str, Callable] | tuple[str, Callable, str]] = field(
        default_factory=list
    )
    on_dismiss: Callable[[], None] | None = None
    explanation: str = ""
    """Beginner-mode-only concept explanation, drawn below message() as a
    dimmed, capped block (see draw_box_tip() in core.py) -- action_popup
    renders it itself, callers just fill this in like any other field."""


# Shared copy for the popups that repeat across more than one call site
# (open-time and save-time both hit the same stable/read-only/locked
# conditions) -- defined once here so the wording can't drift between them.
STABLE_FILE_EXPLANATION = (
    "This is a stable, validated version. Saving over it would change "
    "what other files rely on. Increment to keep working safely, or "
    "overwrite only if you really mean to."
)

READ_ONLY_EXPLANATION = (
    "This file opens read-only. Increment to get your own writable "
    "version instead of waiting."
)

LOCKED_FILE_EXPLANATION = (
    "Another machine has this file open right now. You can view it, "
    "but not save, until they close it. This stops two people from "
    "overwriting each other."
)


_pending_action: PipelineAction | None = None


def set_pending_action(action: PipelineAction | None):
    """Store action for the popup operator."""
    global _pending_action
    _pending_action = action


def get_pending_action(clear=True) -> PipelineAction | None:
    """Retrieve and clear the pending action."""
    global _pending_action
    action = _pending_action
    if clear:
        _pending_action = None
    return action
