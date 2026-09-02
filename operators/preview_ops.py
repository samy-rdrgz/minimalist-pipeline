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


class PIPELINE_OT_compile_preview(bpy.types.Operator):
    """Compile a disposable preview mp4 for a block or a whole sequence."""

    bl_idname = "pipeline.compile_preview"
    bl_label = "Compile preview"
    bl_description = (
        "Concat the latest rendered mp4 per shot into one disposable preview."
    )

    scope: bpy.props.EnumProperty(
        items=[("block", "Block", ""), ("sequence", "Sequence", "")],
        default="block",
    )
    filepath: bpy.props.StringProperty(default="")

    def execute(self, context):
        filepath = Path(self.filepath or bpy.data.filepath)
        project_root = get_active_project_root()
        if not str(filepath) or not project_root:
            self.report({"ERROR"}, "No file/project to resolve a preview from.")
            return {"CANCELLED"}

        config = ConfigCache.get()
        naming = config.get("naming", {})
        parsed = parse_filename(filepath.name)
        if not parsed or not naming:
            self.report({"ERROR"}, "File doesn't match the naming convention.")
            return {"CANCELLED"}
        sequence_label = f"{naming['sequence']['prefix']}{parsed['sequence']}"

        if self.scope == "block":
            sources = resolve_block_sources(filepath, project_root, config)
            scope_name = get_base_filename(filepath.name) or filepath.stem
            label = str(filepath)
        else:
            sources = resolve_sequence_sources(filepath, project_root, config)
            scope_name = sequence_label
            label = str(project_root / "shots" / sequence_label)

        if not sources:
            self.report(
                {"WARNING"}, "No rendered shot found to compile a preview from."
            )
            return {"CANCELLED"}

        date_label = now(False).strftime("%Y%m%d-%H%M")
        output_path = (
            project_root
            / "renders"
            / sequence_label
            / "_preview"
            / f"{scope_name}_{date_label}.mp4"
        )

        try:
            request_preview_compile(
                user=get_user(context),
                scope=self.scope,
                label=label,
                sources=sources,
                output_path=output_path,
            )
        except PipelineError as e:
            log(e.level, "compile_preview", e.message)
            self.report({e.level}, e.message)
            return {"CANCELLED"}

        self.report({"INFO"}, f"Preview compile requested ({len(sources)} shot(s)).")
        return {"FINISHED"}
