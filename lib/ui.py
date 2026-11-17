"""Small drawing blocks shared by the panels and windows: a details line
(its key greyed in a narrow column, its value), a list of them, a row of
buttons or a menu. Memory only: draw()-safe."""

from .icons import icon_kw


def choice(layout, data, prop: str, count: int, limit: int = 10) -> None:
    """data.prop as a button per choice while it has fewer than limit
    (count), else a menu."""
    if count < limit:
        layout.prop(data, prop, expand=True)
    else:
        layout.prop(data, prop, text="")


def icon_button(layout, idname: str, icon: str, tooltip: str = "", text: str = "", emboss: bool = False, **props):
    """An operator button (an icon alone by default, flat): props set on it
    in order, then its tooltip. icon: Blender's, or a mark (lib/icons.py).
    Returns the operator's properties."""
    op = layout.operator(idname, text=text, emboss=emboss, **icon_kw(icon))
    for key, value in props.items():
        setattr(op, key, value)
    if tooltip:
        op.custom_tooltip = tooltip
    return op


def draw_items(layout, items, context=None) -> None:
    """A column of buttons from a list: (operator, text, icon, props) a
    button -- props set on it, "greyed": True for a rarely used one (still
    clickable) --, None a separator, ("tip", text) a box tip, a list of
    buttons side by side when the region is wide enough, ("row", [buttons])
    one row whatever the width (an icon-only button stays its icon's
    size). A falsy item (one that doesn't apply) is skipped."""
    from .core import SIDE_BY_SIDE_WIDTH, draw_box_tip, responsive_layout

    for item in items:
        if item is None:
            layout.separator()
        elif isinstance(item, list):
            pair = responsive_layout(context, layout, SIDE_BY_SIDE_WIDTH)
            for button in item:
                if button:
                    _item_button(pair, *button)
        elif item and item[0] == "tip":
            draw_box_tip(layout, context, item[1])
        elif item and item[0] == "row":
            row = layout.row(align=True)
            for button in item[1]:
                if button:
                    _item_button(row, *button)
        elif item:
            _item_button(layout, *item)


def _item_button(layout, idname: str, text: str, icon: str, props: dict | None = None):
    props = dict(props or {})
    if props.pop("greyed", False):
        layout = layout.column()
        layout.active = False
    op = layout.operator(idname, text=text, icon=icon)
    for key, value in props.items():
        setattr(op, key, value)
    return op


def titled_row(layout, text: str, icon: str = "NONE", factor: float = 0.35):
    """A dialog's line: its title on the left (factor of the width), the
    row for its field returned."""
    row = layout.split(factor=factor, align=True)
    row.label(text=text, icon=icon)
    return row


def draw_creation_fields(layout, op, factor: float) -> None:
    """New asset's and New shot's common fields: description, departments
    required, clean file -- then a line."""
    from .core import text_field

    text_field(titled_row(layout, "Description", "TEXT", factor), op, "description", initial_visible_lines=1)
    titled_row(layout, "Departments", "COLOR", factor).prop_menu_enum(op, "required_departments")
    titled_row(layout, "Clean file", "FILE_BLANK", factor).prop(op, "create_clean", text="")
    layout.separator(type="LINE", factor=3)


def draw_legend(layout, groups: list) -> None:
    """A legend in a menu (Project / Farm monitoring, the log): each group
    its greyed title, then its marks with their words. groups: [(title,
    [(icon, text)])] -- an icon Blender's or a mark."""
    for i, (title, group) in enumerate(groups):
        if i:
            layout.separator()
        heading = layout.row()
        heading.active = False
        heading.label(text=title)
        for icon, text in group:
            layout.label(text=text, **icon_kw(icon))

