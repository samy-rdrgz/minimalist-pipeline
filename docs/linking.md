# Link vs Append

*[← Documentation index](README.md) · [Version française](linking_fr.md)*

---

Link is the pipeline's native mode (the rig links the model, the shot links the assets — no data copying). After a Blender import (`File > Append` or `Link`), the addon detects which one happened and proposes a consistent action: clean up and re-link an append, or move+relink a link external to the project. A normal link *within* the project is just quietly noted in the current version's `.wipmeta` (see [Versions: wip and stable](versions.md)), no popup.

Links that never went through an import — a file migrated from outside the pipeline, a library repointed by hand or by a script — are picked up too: on file open and on every save, the addon scans the file's libraries and adds whatever the `.wipmeta` is missing. Only what the file uses directly is recorded, the same as a manual link would: linking one collection gives one entry, not one per object, material or armature it brings along. Assets nested inside another linked file (a prop inside a linked environment) belong to that file's own tracking and are left out, as are Blender's internal files and files outside the project. The scan only adds: a link you remove is cleaned up the usual way, not by the scan. A `-stable` file has no `.wipmeta`, so nothing is scanned there.

On file open, the addon also compares every linked library against the latest `-stable` version available in its folder, and proposes a batch update if a newer one exists.

---

**See also**: [Versions: wip and stable](versions.md) — a link always points at a specific stable version, never a floating "latest". · [Interface](interface.md) — the project monitoring window's "Links to" / "Linked by" is where these links are actually visible, file by file.
