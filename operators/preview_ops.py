"""Preview compilation operator: resolves which shots/mp4s go into a block
or sequence preview and submits the request to the farm."""

from pathlib import Path

import bpy

from ..farm import request_preview_compile
from ..lib import (
    ConfigCache,
    PipelineError,
    get_active_project_root,
    get_base_filename,
    get_user,
    log,
    now,
    parse_filename,
    resolve_block_sources,
    resolve_sequence_sources,
)


def submit_preview(
    scope: str,
    scope_name: str,
    sequence_label: str,
    label: str,
    sources: list,
    user: str,
    priority: int = 10,
) -> None:
    """Send a preview compile request: renders/<seq>/_preview/<scope_name>_
    <date>.mp4 from sources ((shot_label, mp4) pairs), at this farm
    priority. Raises PipelineError."""
    project_root = get_active_project_root()
    date_label = now(False).strftime("%Y%m%d-%H%M")
    output_path = (
        project_root
        / "renders"
        / sequence_label
        / "_preview"
        / f"{scope_name}_{date_label}.mp4"
    )
    request_preview_compile(
        user=user,
        scope=scope,
        label=label,
        sources=sources,
        output_path=output_path,
        priority=priority,
    )


def request_sequence_preview(
    sequence_label: str, user: str, priority: int = 10, dropped: list | None = None
) -> list:
    """A sequence's preview ("sq030"): every shot's latest video, end to
    end. Returns its sources -- empty: nothing rendered, nothing sent. A
    block rendered whole but left out (one of its shots has its own render)
    is added to dropped, see resolve_sequence_sources(). Raises
    PipelineError."""
    project_root = get_active_project_root()
    sources = resolve_sequence_sources(sequence_label, project_root, dropped=dropped)
    if sources:
        submit_preview(
            "sequence",
            sequence_label,
            sequence_label,
            str(project_root / "shots" / sequence_label),
            sources,
            user,
            priority,
        )
    return sources


def dropped_message(dropped: list) -> str:
    """The blocks a sequence preview left out (request_sequence_preview()'s
    dropped), each logged, in one line for the status bar -- "" if none."""
    for label, overlap in dropped:
        log(
            "WARNING",
            "compile_preview",
            f"{label} left out of the preview: {', '.join(overlap)} has its own render.",
        )
    if not dropped:
        return ""
    names = ", ".join(
        f"{label} ({', '.join(overlap)} rendered alone)" for label, overlap in dropped
    )
    return f"Left out: {names}."


class M_PIPELINE_OT_compile_preview(bpy.types.Operator):
    """Compile a disposable preview mp4 for a block or a whole sequence."""

    bl_idname = "m_pipeline.compile_preview"
    bl_label = "Compile preview"

    scope: bpy.props.EnumProperty(
        items=[("block", "Block", ""), ("sequence", "Sequence", "")],
        default="block",
    )
    filepath: bpy.props.StringProperty(default="")
    custom_tooltip: bpy.props.StringProperty()
    # Same as the Render dialog's: back to 10 on every compile, else a rush
    # priority sticks to the next ones.
    priority: bpy.props.IntProperty(
        name="Priority",
        default=10,
        description="Higher goes first (10 by default); same priority: oldest first",
        options={"SKIP_SAVE"},
    )

    @classmethod
    def description(cls, context, properties):
        return properties.custom_tooltip or (
            "Concat the latest rendered mp4 per shot into one disposable preview."
        )

    def invoke(self, context, event):
        # The priority asked first; a scripted call (execute) keeps its own.
        return context.window_manager.invoke_props_dialog(
            self, width=260, confirm_text="Compile"
        )

    def draw(self, context):
        layout = self.layout
        what = "block" if self.scope == "block" else "sequence"
        layout.label(text=f"Preview of this {what}", icon="SEQUENCE")
        layout.prop(self, "priority")

    def execute(self, context):
        filepath = Path(self.filepath or bpy.data.filepath)
        project_root = get_active_project_root()
        if not str(filepath) or not project_root:
            self.report({"ERROR"}, "No file/project to resolve a preview from.")
            return {"CANCELLED"}

        # A caller can pass a shot's own folder instead of a specific
        # version (the tracking monitor's file details only knows the
        # folder, via TrackingStatusCache) -- parse_filename() below needs
        # a real "..._vNNN.blend" name, so resolve to any one inside it;
        # sequence/shot don't vary by version.
        if filepath.is_dir():
            candidates = sorted(
                f for f in filepath.glob("*.blend") if parse_filename(f.name)
            )
            if not candidates:
                self.report({"ERROR"}, "No versioned file found in this folder.")
                return {"CANCELLED"}
            filepath = candidates[-1]

        config = ConfigCache.get()
        naming = config.get("naming", {})
        parsed = parse_filename(filepath.name)
        if not parsed or not naming:
            self.report({"ERROR"}, "File doesn't match the naming convention.")
            return {"CANCELLED"}
        sequence_label = f"{naming['sequence']['prefix']}{parsed['sequence']}"

        dropped = []
        try:
            if self.scope == "block":
                sources = resolve_block_sources(filepath, project_root, config)
                if sources:
                    submit_preview(
                        "block",
                        get_base_filename(filepath.name) or filepath.stem,
                        sequence_label,
                        str(filepath),
                        sources,
                        get_user(context),
                        self.priority,
                    )
            else:
                sources = request_sequence_preview(
                    sequence_label, get_user(context), self.priority, dropped
                )
        except PipelineError as e:
            log(e.level, "compile_preview", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}
        if not sources:
            self.report(
                {"WARNING"}, "No rendered shot found to compile a preview from."
            )
            return {"CANCELLED"}

        message = f"Preview compile requested ({len(sources)} shot(s))."
        left_out = dropped_message(dropped)
        self.report(
            {"WARNING" if left_out else "INFO"}, f"{message} {left_out}".strip()
        )
        return {"FINISHED"}
