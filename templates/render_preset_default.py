"""Render preset for {department}: applied by each farm worker to the scene
right before it renders -- on top of the file's own settings, never saved
into it. Its renders are {department}'s: the department comes from this
file's name ({department}_..., see the add-on's Farm docs). Copy it under
another name for another look ({department}_hd.py, {department}_ld.py).

override() raising fails that machine's render, rather than render with
the file's own settings.
"""


def override(scene, job_data):
    """scene: the scene to render. job_data: the job (read only) -- its
    "filepath", "shot_override", "resolved_frame_range"..."""
    # A few common ones, to uncomment:
    # scene.render.engine = "CYCLES"
    # scene.cycles.samples = 64
    # scene.render.resolution_percentage = 50
    # scene.render.use_stamp = True
    pass
