# Link vs Append

*[← Documentation index](README.md) · [Version française](linking_fr.md)*

---

Link is the pipeline's native mode (the rig links the model, the shot links the assets — no data copying). After a Blender import (`File > Append` or `Link`), the addon detects which one happened and proposes a consistent action: clean up and re-link an append, or move+relink a link external to the project. A normal link *within* the project is just quietly noted in the current version's `.wipmeta` (see [Versions: wip and stable](versions.md)), no popup.

On file open, the addon also compares every linked library against the latest `-stable` version available in its folder, and proposes a batch update if a newer one exists.

---

**See also**: [Versions: wip and stable](versions.md) — a link always points at a specific stable version, never a floating "latest".
