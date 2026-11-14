"""Small drawing blocks shared by the panels and windows: a details line
(its key greyed in a narrow column, its value), a list of them, a row of
buttons or a menu. Memory only: draw()-safe."""

from .icons import icon_kw

# A details line's key column, as a share of the width: Job details', Worker
# details', File details'.
DETAIL_KEY_COLUMN = 0.4 / 3


def key_value(col, label: str, value=None, icon: str = "NONE", alert: bool = False, factor: float = DETAIL_KEY_COLUMN):
    """One details line: label greyed, then value (with its icon, red if
    alert). Returns the value's row, for buttons after it -- or to draw the
    value itself, value None."""
    split = col.split(factor=factor)
    left = split.row()
    left.active = False
    left.label(text=label)
    right = split.row()
    right.alert = alert
    if value is not None:
        right.label(text=str(value), icon=icon)
    return right


def key_values(col, rows, factor: float = DETAIL_KEY_COLUMN) -> None:
    """key_value() for each row of rows: (label, value[, icon[, alert]]); a
    falsy row (a line that doesn't apply) is skipped."""
    for row in rows:
        if row:
            key_value(col, *row, factor=factor)


def choice(layout, data, prop: str, count: int, limit: int = 10) -> None:
    """data.prop as a button per choice while it has fewer than limit
    (count), else a menu."""
    if count < limit:
        layout.prop(data, prop, expand=True)
    else:
        layout.prop(data, prop, text="")


def details_header(layout, back_op: str, title: str, icon: str):
    """A details view's first line: ← back (back_op with no target), its
    title. Returns the row for its actions, on the right."""
    header = layout.row()
    back = header.row()
    back.alignment = "LEFT"
    back.operator(back_op, text="", icon="BACK", emboss=False)
    header.label(text=title, icon=icon)
    actions = header.row(align=True)
    actions.alignment = "RIGHT"
    return actions


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


def link_rows(col, title: str, links: list, indent: float = 1.5) -> None:
    """A titled list of flat links, one per row, indented: links as
    (operator, text, icon, props) -- props set on each, its tooltip under
    "custom_tooltip" among them."""
    col.label(text=title, icon="LINKED")
    for idname, text, icon, props in links:
        row = col.row(align=True)
        row.alignment = "LEFT"
        row.separator(factor=indent)
        row.alert = props.pop("alert", False)
        tooltip = props.pop("custom_tooltip", "")
        icon_button(row, idname, icon, tooltip, text=text, **props)


def draw_items(layout, items, context=None) -> None:
    """A column of buttons from a list: (operator, text, icon, props) a
    button -- props set on it, "greyed": True for a rarely used one (still
    clickable) --, None a separator, ("tip", text) a box tip, a list of
    buttons side by side when the region is wide enough. A falsy item (one
    that doesn't apply) is skipped."""
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
