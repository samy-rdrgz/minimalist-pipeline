# Shot blocks (multishot)

*[← Documentation index](README.md) · [Version française](multishot_fr.md)*

---

A **block** isn't "several shots in one file" in a generic sense — it's for the specific case of camera cuts on **one continuous piece of animation** that can't be split into separate files without breaking the motion/contact at the seams: same decor, same lighting, one department/person working on it at a time. It's a real need, but a rare one — the addon never pushes it forward in the UI, and a single shot stays the default even solo. If two cuts have different needs (fx on one, different lighting on the other), that's not a block, that's two shots.

- **Creating one**: same "New shot" dialog, but pick several shots from the current sequence instead of one (never typed by hand — the name is generated from the selection, so padding/order can't drift). The result is one file, one name: `sq040_sh030-040-045-050_v001.blend`.
- **What actually marks the cuts**: cameras and timeline markers inside the file, named after their own shot (`cam_sq040_sh045`). The file's name is a *plan* (which shots this block is meant to cover); the markers are the *live state* — they're allowed to differ while you're still working. It only gets reconciled when it matters, at render time (below), and never silently: a marker that doesn't match a shot in the name just gets folded into the previous one instead of being dropped.
- **Rendering**: submit the block once, same "Render" button as any file. The farm splits it into one ordinary render job per shot automatically — each lands in its own output folder (`renders/sq040/sh045/...`), so a note from review on a single shot means re-rendering just that one, not the whole block. A checklist lets you submit only some of the block's shots if that's all you need. Full mechanics in [Rendering (farm)](farm.md).
- **Preview**: "Preview block" / "Preview sequence" compile the latest rendered clip of each shot into one throwaway video (`renders/sq040/_preview/..._{date}.mp4`) — never authoritative, never regenerated on its own, always a manual click.
- **Changing which shots belong together**: "Branch block" — the old composition is flagged archived (not deleted, not moved — still right there if you need to check it) and a new file takes over with the new shot selection, continuing the same version lineage and carrying its notes/todos forward.
- Notes/todos can carry an optional shot tag, picked from a dropdown built from the block's own shot numbers (`[sh045] the foot slides`) — not a filter, just a label on the entry. See [Tracking & reviews](tracking-and-reviews.md).

---

**See also**: [Naming convention](project-and-naming.md#naming-convention) for how a block's filename is built · [Known current limitations](limitations.md) for the current state of Preview/Branch testing and the theoretical Windows path-length risk on very long blocks · [NOTES.md](../NOTES.md) (repo root, "Multishot blocks" section) for the dev-facing design rationale behind this feature.
