"""Small drawing blocks shared by the panels and windows: a details line
(its key greyed in a narrow column, its value), a list of them, a row of
buttons or a menu. Memory only: draw()-safe."""

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


def choice(layout, data, prop: str, items: list, max_buttons: int = 4, text: str = "") -> None:
    """data.prop as a row of buttons for a few choices, else a menu."""
    if len(items) <= max_buttons:
        layout.row(align=True).prop(data, prop, expand=True)
    else:
        layout.prop(data, prop, text=text)


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
    in order, then its tooltip. Returns the operator's properties."""
    op = layout.operator(idname, text=text, icon=icon, emboss=emboss)
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
