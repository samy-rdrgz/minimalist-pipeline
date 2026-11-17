"""Blender's active theme as the snapshot page's colours: {css variable:
"#rrggbb"}, written at the export (meta.theme) so a custom theme gives a
page to match (templates/snapshot/css/10-tokens.css names each variable's
field). The states' colours never follow it: they stay the same from one
machine to another. read_theme() needs bpy: main thread only; the rest is
pure (tests/test_snapshot_theme.py)."""

# css variable -> the theme's field, as "area.attribute" under
# preferences.themes[0] (the first that exists wins).
FIELDS = {
    "--screen": ("user_interface.editor_border", "user_interface.editor_outline"),
    "--area": ("properties.space.back",),
    "--head": ("properties.space.header",),
    "--box": ("user_interface.wcol_box.inner",),
    "--box-2": ("user_interface.wcol_box.inner_sel",),
    "--line": ("user_interface.wcol_box.outline",),
    "--btn": ("user_interface.wcol_regular.inner",),
    "--btn-line": ("user_interface.wcol_regular.outline",),
    "--tool": ("user_interface.wcol_tool.inner",),
    "--field": ("user_interface.wcol_text.inner",),
    "--track": ("user_interface.wcol_progress.inner",),
    "--sel": ("user_interface.wcol_regular.inner_sel",),
    "--row-sel": ("outliner.selected_highlight",),
    "--stripe-a": ("outliner.space.back",),
    "--stripe-b": ("outliner.row_alternate",),
    "--canvas": ("node_editor.space.back",),
    "--dot": ("node_editor.grid",),
    "--text": ("user_interface.wcol_regular.text",),
    "--text-2": ("properties.space.text",),
    "--on-sel": ("user_interface.wcol_regular.text_sel",),
    "--play": ("sequence_editor.movie_strip",),
    "--node-asset": ("node_editor.converter_node",),
}
# Derived: (variable, from, lightness change) -- a hover 6 % lighter...
DERIVED = (
    ("--btn-hi", "--btn", 0.06),
    ("--tool-hi", "--tool", 0.06),
    ("--sel-hover", "--sel", 0.06),
    ("--sel-hi", "--sel", 0.2),
    ("--row-hover", "--stripe-a", 0.03),
    ("--sunk", "--area", -0.03),
    ("--play-hi", "--play", 0.06),
)
# Text on its ground: under this, the theme isn't used (the page's own).
MIN_CONTRAST = 4.5


def hex_color(rgb) -> str:
    """A theme colour (floats 0..1, alpha ignored) as #rrggbb."""
    r, g, b = (max(0, min(255, round(float(c) * 255))) for c in list(rgb)[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def _rgb(hex_: str) -> tuple:
    return tuple(int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5))


def shade(hex_: str, amount: float) -> str:
    """Lighter (amount > 0, towards white) or darker (towards black)."""
    target = 1.0 if amount > 0 else 0.0
    return hex_color(c + (target - c) * abs(amount) for c in _rgb(hex_))


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio of two colours."""

    def lum(h):
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in _rgb(h)]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def theme_vars(get) -> dict:
    """The page's variables from a theme: get(path) gives a field's colour
    or None. {} when the text wouldn't read on its ground."""
    out = {}
    for var, paths in FIELDS.items():
        for path in paths:
            value = get(path)
            if value is not None:
                out[var] = hex_color(value)
                break
    for var, base, amount in DERIVED:
        if base in out:
            out[var] = shade(out[base], amount)
    if "--text" in out and "--area" in out and contrast(out["--text"], out["--area"]) < MIN_CONTRAST:
        return {}
    return out


def read_theme() -> dict:
    """The active theme's variables (theme_vars()); {} without one."""
    try:
        import bpy

        theme = bpy.context.preferences.themes[0]
    except Exception:  # noqa: BLE001 -- no preferences: the page's own colours
        return {}

    def get(path):
        node = theme
        for part in path.split("."):
            node = getattr(node, part, None)
            if node is None:
                return None
        try:
            return tuple(node)
        except TypeError:
            return None

    return theme_vars(get)
