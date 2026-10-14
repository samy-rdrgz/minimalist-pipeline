"""Production snapshot: one self-contained HTML page of the project's state
for people outside the studio, with a review spreadsheet embedded in it that
they fill in and send back (see NOTES.md, "Production snapshot")."""

import base64
import hashlib
import html
import io
import os
import re
import threading
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from .core import json_get, now, read_json_quiet
from .errors import PipelineError
from .preview import latest_render_dir, render_root
from .tracking import (
    _DATA_ROOTS,
    _collect_folder,
    _pipeline_entries,
    _status_from_raw,
    _walk_owner_dirs,
    create_entry,
    filter_review_boxes,
    find_file_by_name,
    tracking_json_path,
    valid_department,
)
from .thumbnails import (
    owner_render_dir,
    run_thumbnail_jobs,
    thumbnail_jobs,
    thumbnail_path,
)

# Bumped whenever the review template's columns change -- the import refuses
# a template made by a newer addon.
SCHEMA_VERSION = 1

ENTRY_TYPES = ("note", "todo", "rtk")

# Department state -> (label, css class). "rework" is validated at the last
# stable AND worked since: never shown as plain "validated".
STATES = {
    "done": ("Validated", "st-done"),
    "rework": ("Validated, reworked since", "st-rework"),
    "wip": ("Work in progress", "st-wip"),
    "todo": ("Not started", "st-todo"),
}

# Entry "source" stamped on every note imported from a review template.
REVIEW_SOURCE = "prod_review"

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------


def read_snapshot_raw(root: Path) -> list[tuple[str, Path, dict, list[str]]]:
    """(kind, owner folder, _collect_folder() data, .blend names) for every
    tracked folder. Disk only, pure os/json: thread-safe."""
    out = []
    for top in _DATA_ROOTS:
        kind = "shot" if top == "shots" else "asset"
        for owner in _walk_owner_dirs(root / top):
            raw = _collect_folder(owner, _pipeline_entries(owner))
            if raw is None:
                continue
            try:
                blends = [
                    e.name for e in os.scandir(owner) if e.name.endswith(".blend")
                ]
            except OSError:
                blends = []
            out.append((kind, owner, raw, blends))
    return out


def _owner_shots(owner: Path) -> list[str]:
    """A shot folder's shots: ["sh040"], or ["sh040", "sh050", "sh060"] for
    a block "sh040-050-060". Name parsing only, no config."""
    first, *rest = owner.name.split("-")
    m = re.match(r"(\D*)(\d+)$", first)
    if not m:
        return [owner.name]
    return [first] + [f"{m[1]}{n.zfill(len(m[2]))}" for n in rest]


def read_render_state(root: Path, kind: str, owner: Path, v_prefix: str = "v") -> list:
    """What was last rendered for an asset/shot folder, per shot (a block
    has several, anything else one): [{"shot", "file", "folder"}]. From the
    folder's render_history.json -- its last finished render of that shot,
    file = the .blend it rendered -- else (entries older than source_file,
    or no history) from the latest render folder's own name
    (renders/<seq>/<shot>/v004-stable_002). Pure os/json: thread-safe."""
    history = read_json_quiet(owner / ".pipeline" / "render_history.json") or {}
    finished = [
        e
        for e in history.get("entries", [])
        if isinstance(e, dict) and e.get("status") == "finished" and e.get("source_file")
    ]
    base = render_root(root, owner)
    shots = _owner_shots(owner) if kind == "shot" else [""]
    block = len(shots) > 1
    out = []
    for shot in shots:
        # A block's history holds every shot it rendered, told apart by
        # shot_override; a mono shot's or an asset's is all its own.
        mine = [e for e in finished if not block or e.get("shot_override") == shot]
        if mine:
            output = mine[-1].get("output_path")
            out.append(
                {
                    "shot": shot,
                    "file": Path(mine[-1]["source_file"]).name,
                    "folder": Path(output).parent.name if output else None,
                }
            )
            continue
        latest = latest_render_dir(base.with_name(shot) if shot else base, v_prefix)
        out.append({"shot": shot, "file": None, "folder": latest.name if latest else None})
    return out


def read_snapshot_data(
    root: Path, thumbnails: dict | None = None, v_prefix: str = "v"
) -> dict:
    """read_snapshot_raw() plus each folder's last render
    (read_render_state()) and thumbnails: those missing or older than
    their latest render are remade first (one headless Blender, waited on
    -- run this on a thread). thumbnails: {"v_prefix", "blender",
    "ffmpeg"}, None to skip them. Returns {"raws", "renders": {owner:
    [...]}, "thumbs": {owner: base64 JPEG}, "thumb_warnings": [...]}."""
    raws = read_snapshot_raw(root)
    renders = {
        str(owner): read_render_state(root, kind, owner, v_prefix)
        for kind, owner, raw, _ in raws
        if not raw["tracking"].get("archived")
    }
    thumbs, warnings = {}, []
    if thumbnails is not None:
        dirs = {}
        for _, owner, raw, _ in raws:
            if not raw["tracking"].get("archived"):
                dirs[str(owner)] = owner_render_dir(root, owner)
        jobs = thumbnail_jobs(dirs.values(), thumbnails.get("v_prefix", "v"))
        results = run_thumbnail_jobs(
            jobs, thumbnails["blender"], thumbnails.get("ffmpeg")
        )
        for owner, d in dirs.items():
            dst = thumbnail_path(d)
            if results.get(str(dst), "ok") != "ok":
                warnings.append(f"{dst.name}: {results[str(dst)]}")
            try:  # an older thumbnail still beats none
                thumbs[owner] = base64.b64encode(dst.read_bytes()).decode("ascii")
            except OSError:
                pass
    return {
        "raws": raws,
        "renders": renders,
        "thumbs": thumbs,
        "thumb_warnings": warnings,
    }


def build_snapshot(data, config: dict, meta: dict) -> dict:
    """Neutral snapshot dict from read_snapshot_data()'s result (or a bare
    read_snapshot_raw() list): {"meta", "assets", "shots", "notes"}.
    Memory only, main thread (_status_from_raw() reads ConfigCache)."""
    if isinstance(data, list):
        data = {"raws": data, "thumbs": {}, "thumb_warnings": []}
    raws = data["raws"]
    v_prefix = json_get(config, "naming.version.prefix", "v")
    version_re = re.compile(rf"_{re.escape(v_prefix)}(\d+)(-[a-z]+)?\.blend$")
    folder_re = re.compile(rf"^{re.escape(v_prefix)}(\d+)(-[a-z]+)?_\d+$")
    items = {"asset": [], "shot": []}
    notes = []
    for kind, owner, raw, blends in raws:
        status = _status_from_raw(raw)
        if status.get("archived"):
            continue
        name = status.get("file_name") or owner.name
        wips = [
            (int(m[1]), b)
            for b in blends
            if (m := version_re.search(b)) and not m[2]
        ]
        stable_file = (status.get("stable_info") or {}).get("file")
        stable_name = Path(stable_file).name if stable_file else None
        stable_m = version_re.search(stable_name or "")
        stable_n = int(stable_m[1]) if stable_m else -1
        wip_n, wip_name = max(wips) if wips else (-1, None)
        item = {
            "name": name,
            "kind": kind,
            "group": name.split("_", 1)[0],
            "description": status.get("description", ""),
            "departments_required": list(status.get("departments_required", [])),
            "departments": {
                d: _department_state(status, d)
                for d in status.get("departments_required", [])
            },
            "wip_version": wip_name,
            "stable_version": stable_name,
            # What the prod sees and what its notes get anchored on: the
            # most recent of the two (a stable can be newer than any wip).
            "current_version": wip_name if wip_n > stable_n else stable_name or wip_name,
            "thumbnail": data["thumbs"].get(str(owner)),
        }
        # Two versions per render, never mixed up: the render's own (its
        # output folder, v003_002 -- a new increment per render) and the
        # .blend version it was rendered from (v003). The folder's name
        # starts with the latter, the fallback when the history doesn't say.
        renders = []
        for r in data.get("renders", {}).get(str(owner), []):
            m = version_re.search(r["file"] or "") or folder_re.match(r["folder"] or "")
            renders.append(
                {
                    "shot": r["shot"],
                    "folder": r["folder"],
                    "file_version": f"{v_prefix}{m[1]}{m[2] or ''}" if m else None,
                    "file_number": int(m[1]) if m else None,
                    "file": r["file"],
                }
            )
        item["renders"] = renders
        # What the prod must see: a render made from an older .blend than
        # the last stable -- the picture lags the validated work.
        item["stable_number"] = stable_n
        item["render_behind"] = stable_n >= 0 and any(
            r["file_number"] is not None and r["file_number"] < stable_n
            for r in renders
        )
        threads = [
            _thread_dict(name, t)
            for box in filter_review_boxes(
                status.get("entries_grouped", []), hide_done=True
            )
            for t in box["threads"]
        ]
        item["open_rtk"] = sum(
            1
            for t in threads
            for e in [t, *t["replies"]]
            if e["type"] == "rtk" and e["done"] is False
        )
        item["open_notes"] = len(threads)
        items[kind].append(item)
        notes.extend(threads)

    for k in items:
        items[k].sort(key=lambda i: i["name"])
    notes.sort(key=lambda n: (n["item"], n["last_activity"]), reverse=False)
    meta = dict(meta)
    meta.setdefault("schema_version", SCHEMA_VERSION)
    meta["thumbnail_warnings"] = list(data["thumb_warnings"])
    meta["asset_departments"] = _columns(
        json_get(config, "assets_departments", []), items["asset"]
    )
    meta["shot_departments"] = _columns(
        json_get(config, "shots_departments", []), items["shot"]
    )
    return {"meta": meta, "assets": items["asset"], "shots": items["shot"], "notes": notes}


def collect_snapshot(
    root: Path, config: dict, meta: dict, thumbnails: dict | None = None
) -> dict:
    """read_snapshot_data() + build_snapshot() in one go (no thread)."""
    meta = {"scan_started_at": now(), **meta}
    return build_snapshot(read_snapshot_data(root, thumbnails), config, meta)


def _department_state(status: dict, department: str) -> str:
    validated = department in status.get("validated_departments", {})
    worked = department in status.get("worked_departments", {})
    if validated:
        return "rework" if worked else "done"
    return "wip" if worked else "todo"


def _columns(configured: list, items: list) -> list:
    """Config's department order, plus any department an item requires that
    the config no longer lists."""
    cols = list(configured)
    for item in items:
        for d in item["departments_required"]:
            if d not in cols:
                cols.append(d)
    return cols


def _entry_dict(e: dict) -> dict:
    version = e.get("referenced_version")
    return {
        "type": e.get("type", "note"),
        "text": e.get("text", ""),
        "author": e.get("author", ""),
        "date": e.get("created_at", ""),
        "department": e.get("department", ""),
        "version": Path(version).name if version else "",
        "shot": e.get("shot", ""),
        "done": e.get("done"),
        "from_review": e.get("source") == REVIEW_SOURCE,
    }


def _thread_dict(item_name: str, thread: dict) -> dict:
    return {
        "item": item_name,
        **_entry_dict(thread["root"]),
        "replies": [_entry_dict(r) for r in thread["replies"]],
        "last_activity": thread["meta"]["date_end"],
    }


class SnapshotJob:
    """Run fn(*args) on a thread, polled from the main thread (done/result/
    error). The export runs two: the disk read, then render+write -- only
    build_snapshot() runs on the main thread, memory only."""

    def __init__(self, fn, *args):
        self.started_at = now()
        self.result = None
        self.error = None
        self.done = False
        self._thread = threading.Thread(
            target=self._run, args=(fn, args), daemon=True, name="pipeline-snapshot"
        )
        self._thread.start()

    def _run(self, fn, args) -> None:
        try:
            self.result = fn(*args)
        except Exception as e:  # reported by the caller
            self.error = repr(e)
        self.done = True


def write_snapshot(snapshot: dict, filepath: Path) -> Path:
    """render_html() written to filepath. Pure: thread-safe."""
    Path(filepath).write_text(render_html(snapshot), encoding="utf-8")
    return Path(filepath)


def snapshot_filename(snapshot: dict, ext: str = "html", kind: str = "snapshot") -> str:
    """<project>_<kind>_<YYYY-MM-DD>.<ext>, dated from the scan's start."""
    meta = snapshot["meta"]
    project = re.sub(r"[^\w\-]+", "_", meta.get("project") or "").strip("_") or "project"
    day = (meta.get("scan_started_at") or now())[:10]
    return f"{project}_{kind}_{day}.{ext}"


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def _e(value) -> str:
    return html.escape(str(value or ""), quote=True)


def render_html(snapshot: dict) -> str:
    """The whole snapshot as one offline HTML page (CSS/JS inline, review
    template embedded as a data: link)."""
    meta = snapshot["meta"]
    # Wrapped like a mail attachment: a URL's newlines are dropped by the
    # browser, the raw source stays readable.
    xlsx = base64.encodebytes(render_review_xlsx(snapshot)).decode("ascii").strip()
    xlsx_name = snapshot_filename(snapshot, "xlsx", "review")
    scan_date = (meta.get("scan_started_at") or "").replace("T", " ")
    legend = "".join(
        f'<span class="pill {cls}">{_e(label)}</span>' for label, cls in STATES.values()
    ) + '<span class="pill st-none">Not required</span>'

    body = [
        "<header>",
        f"<h1>{_e(meta.get('project'))}</h1>",
        '<dl class="meta">',
        f"<div><dt>Snapshot</dt><dd>{_e(scan_date)}</dd></div>",
        f"<div><dt>Exported by</dt><dd>{_e(meta.get('exported_by'))}</dd></div>",
        f"<div><dt>Addon</dt><dd>Minimalist Pipeline {_e(meta.get('addon_version'))}</dd></div>",
        "</dl>",
        '<div class="review">',
        f'<a class="btn" download="{_e(xlsx_name)}" '
        f'href="data:{XLSX_MIME};base64,\n{xlsx}\n">Download the review template (.xlsx)</a>',
        "<p>Fill in your name and the review date at the top, write your notes "
        "in the <b>text</b> column of each asset/shot — <b>one line per note</b>, "
        "Alt+Enter for the next one — pick a department and a type, then send "
        "the file back as is.</p>",
        "</div>",
        "</header>",
        "<nav>",
        '<div class="links"><a href="#assets">Assets <span id="c-assets">'
        f'{len(snapshot["assets"])}</span></a><a href="#shots">Shots <span id="c-shots">'
        f'{len(snapshot["shots"])}</span></a><a href="#notes">Open notes <span id="c-notes">'
        f'{len(snapshot["notes"])}</span></a></div>',
        _render_filters(snapshot),
        "</nav>",
        f'<p class="legend">{legend}</p>',
        _render_table("assets", "Assets", snapshot["assets"], meta["asset_departments"]),
        _render_table("shots", "Shots", snapshot["shots"], meta["shot_departments"]),
        _render_notes(snapshot["notes"], snapshot["assets"] + snapshot["shots"]),
    ]
    title = f"{meta.get('project') or 'Project'} snapshot {scan_date[:10]}"
    # One element per line: readable/diffable raw source, same rendering.
    nl = "\n"
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title>\n<style>{_CSS}</style>\n</head>"
        f"<body>\n{nl.join(body)}\n<script>{_JS}</script>\n</body></html>\n"
    )


def _render_filters(snapshot: dict) -> str:
    """Filter bar: name, group, department + state, RTK / notes toggles.
    Applied client-side to table rows and note cards alike (_JS)."""

    def options(values):
        return "".join(f'<option value="{_e(v)}">{_e(v)}</option>' for v in values)

    groups = "".join(
        f'<optgroup label="{label}">{options(dict.fromkeys(i["group"] for i in items))}</optgroup>'
        for label, items in (("Assets", snapshot["assets"]), ("Shots", snapshot["shots"]))
        if items
    )
    meta = snapshot["meta"]
    departments = dict.fromkeys(meta["asset_departments"] + meta["shot_departments"])
    states = "".join(
        f'<option value="{k}">{_e(label)}</option>' for k, (label, _) in STATES.items()
    )
    return (
        '<div class="filters">'
        '<input id="f-name" type="search" placeholder="Name…" aria-label="Filter by name">'
        f'<select id="f-group" aria-label="Group"><option value="">All groups</option>{groups}</select>'
        '<select id="f-dep" aria-label="Department"><option value="">Any department</option>'
        f"{options(departments)}</select>"
        f'<select id="f-state" aria-label="State"><option value="">Any state</option>{states}</select>'
        '<label><input id="f-rtk" type="checkbox"> Open RTK</label>'
        '<label><input id="f-notes" type="checkbox"> Has open notes</label>'
        '<button id="f-reset" type="button">Reset</button>'
        "</div>"
    )


def _slug(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name)


def _item_attrs(item: dict) -> str:
    """data-* the filter script matches on -- same for a row and its notes card."""
    states = " ".join(f"{d}:{st}" for d, st in item["departments"].items())
    return (
        f'data-name="{_e(item["name"].lower())}" data-group="{_e(item["group"])}" '
        f'data-states="{_e(states)}" data-rtk="{item["open_rtk"]}" '
        f'data-notes="{item["open_notes"]}"'
    )


def _render_table(anchor: str, title: str, items: list, columns: list) -> str:
    nl = "\n"
    if not items:
        return (
            f'<section id="{anchor}"><h2>{title}</h2>'
            '<p class="empty">Nothing tracked yet.</p></section>'
        )
    with_thumbs = any(i.get("thumbnail") for i in items)
    head = (
        ("<th></th>" if with_thumbs else "")
        + "<th>Name</th>"
        + '<th title="Latest work-in-progress and stable versions of the .blend">'
        "Blender file</th>"
        + '<th title="Its output folder (a new one per render), and the .blend '
        'version it was rendered from">Last render</th>'
        + "".join(f"<th>{_e(c.capitalize())}</th>" for c in columns)
    )
    rows = []
    group = None
    for item in items:
        if item["group"] != group:
            group = item["group"]
            rows.append(
                f'<tr class="group" data-group="{_e(group)}">'
                f'<th colspan="{len(columns) + 3 + with_thumbs}">{_e(group)}</th></tr>'
            )
        cells = []
        for c in columns:
            state = item["departments"].get(c)
            if state is None:
                cells.append('<td><span class="na" title="Not required">–</span></td>')
            else:
                label, cls = STATES[state]
                cells.append(f'<td><span class="pill {cls}">{_e(label)}</span></td>')
        versions = " · ".join(
            label + _short_version(item["name"], v)
            for label, v in (("wip ", item["wip_version"]), ("stable ", item["stable_version"]))
            if v
        )
        flags = (
            f'<span class="flag">{item["open_rtk"]} RTK</span>' if item["open_rtk"] else ""
        )
        n = item["open_notes"]
        jump = (
            f'<a class="jump" href="#n-{_e(_slug(item["name"]))}">'
            f'{n} note{"" if n == 1 else "s"} ↓</a>'
            if n
            else ""
        )
        thumb = ""
        if with_thumbs:
            thumb = (
                f'<td class="th"><img class="thumb" alt="" '
                f'src="data:image/jpeg;base64,{item["thumbnail"]}"></td>'
                if item.get("thumbnail")
                else '<td class="th"><div class="nothumb"></div></td>'
            )
        rows.append(
            f'<tr class="item" id="i-{_e(_slug(item["name"]))}" {_item_attrs(item)}>'
            f'{thumb}<td class="name"><b>{_e(item["name"])}</b>{flags}{jump}'
            f'<small>{_e(item["description"])}</small></td>'
            f'<td class="ver">{_e(versions)}</td>'
            f'<td class="ver">{_render_cell(item)}</td>{"".join(cells)}</tr>'
        )
    return (
        f'<section id="{anchor}"><h2>{title}</h2>'
        '<p class="empty nomatch" hidden>Nothing matches the filters.</p>'
        '<div class="scroll"><table>'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>\n{nl.join(rows)}\n</tbody></table></div></section>"
    )


def _render_cell(item: dict) -> str:
    """ "Last render" cell: the output folder (the render's own version,
    v003_002) over "from v003" (the .blend it was rendered from), the
    latter flagged when older than the last stable. One line per shot when
    a block's shots differ. "not rendered" for a shot never rendered,
    empty for an asset never rendered (most never are)."""
    renders = [r for r in item.get("renders") or [] if r["folder"] or r["file_version"]]
    if not renders:
        return '<span class="norender">not rendered</span>' if item["kind"] == "shot" else ""
    stable = _short_version(item["name"], item["stable_version"] or "")
    same = len({(r["folder"], r["file_version"]) for r in item["renders"]}) == 1
    lines = []
    for r in item["renders"][:1] if same else item["renders"]:
        shot = "" if same else f'<span class="shot">{_e(r["shot"])}</span> '
        if not (r["folder"] or r["file_version"]):
            lines.append(f'<div>{shot}<span class="norender">not rendered</span></div>')
            continue
        source = f"from .blend {r['file_version'] or '?'}"
        if r["file_number"] is not None and r["file_number"] < item["stable_number"]:
            source = (
                f'<span class="behind" title="Rendered from an older .blend than '
                f'the last stable ({_e(stable)})">⚠ {_e(source)}, stable is {_e(stable)}</span>'
            )
        else:
            source = f"<small>{_e(source)}</small>"
        title = f' title="{_e(r["file"])}"' if r["file"] else ""
        lines.append(
            f'<div{title}>{shot}<span class="rv">{_e(r["folder"] or "?")}</span> {source}</div>'
        )
    return "".join(lines)


def _short_version(name: str, filename: str) -> str:
    """"ch_bob_v004-stable.blend" -> "v004" (the stable label says the rest)."""
    stem = filename[: -len(".blend")] if filename.endswith(".blend") else filename
    stem = stem[len(name) + 1 :] if stem.startswith(name + "_") else stem
    return stem.split("-", 1)[0]


def _render_entry(e: dict, reply: bool = False) -> str:
    tags = [f'<span class="type t-{_e(e["type"])}">{_e(e["type"])}</span>']
    if e["done"] is True:
        tags.append('<span class="tag">done</span>')
    if e["from_review"]:
        tags.append('<span class="tag">prod review</span>')
    for key in ("department", "shot", "version"):
        if e[key]:
            tags.append(f'<span class="tag">{_e(e[key])}</span>')
    who = f'{_e(e["author"])} · {_e(e["date"][:10])}'
    return (
        f'<li class="{"reply" if reply else "root"}"><div class="head">'
        f'{"".join(tags)}<span class="who">{who}</span></div>'
        f'<p>{_e(e["text"])}</p></li>'
    )


def _render_notes(notes: list, items: list) -> str:
    if not notes:
        return (
            '<section id="notes"><h2>Open notes</h2>'
            '<p class="empty">No open notes.</p></section>'
        )
    attrs = {i["name"]: _item_attrs(i) for i in items}
    by_item: dict[str, list] = {}
    for n in notes:
        by_item.setdefault(n["item"], []).append(n)
    cards = []
    for name, threads in by_item.items():
        threads = sorted(threads, key=lambda t: t["last_activity"], reverse=True)
        lis = "\n".join(
            "\n".join([_render_entry(t)] + [_render_entry(r, True) for r in t["replies"]])
            for t in threads
        )
        slug = _e(_slug(name))
        cards.append(
            f'<article class="item" id="n-{slug}" data-threads="{len(threads)}" '
            f'{attrs.get(name, "")}><h3>{_e(name)}'
            f'<a class="back" href="#i-{slug}" title="Back to its row">↑</a></h3>'
            f"<ul>\n{lis}\n</ul></article>"
        )
    return (
        '<section id="notes"><h2>Open notes</h2>'
        '<p class="empty nomatch" hidden>Nothing matches the filters.</p>'
        + "\n".join(cards)
        + "</section>"
    )


_CSS = """
:root{--bg:#f7f7f5;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e2e1dc;
--accent:#3d5afe;--done:#2e7d32;--done-bg:#e3f2e4;--wip:#8a5a00;--wip-bg:#fff1d6;
--todo:#6b6b66;--rtk:#c62828;--rtk-bg:#fde7e7;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;
--fg:#ecebe6;--muted:#a3a29c;--card:#20201e;--line:#34332f;--accent:#8c9eff;
--done:#81c784;--done-bg:#1d3320;--wip:#ffcc80;--wip-bg:#3a2c12;--todo:#a3a29c;
--rtk:#ef9a9a;--rtk-bg:#3a1c1c}}
:root[data-theme="dark"]{--bg:#161615;--fg:#ecebe6;--muted:#a3a29c;--card:#20201e;
--line:#34332f;--accent:#8c9eff;--done:#81c784;--done-bg:#1d3320;--wip:#ffcc80;
--wip-bg:#3a2c12;--todo:#a3a29c;--rtk:#ef9a9a;--rtk-bg:#3a1c1c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header,section,.legend{max-width:1200px;margin:0 auto;padding:0 16px}
header{padding-top:28px}
h1{margin:0 0 8px;font-size:26px}
h2{margin:32px 0 12px;font-size:19px}
h3{margin:0 0 8px;font-size:15px}
.meta{display:flex;flex-wrap:wrap;gap:6px 24px;margin:0 0 16px;color:var(--muted)}
.meta div{display:flex;gap:6px}.meta dt{font-weight:600}.meta dd{margin:0}
.review{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:14px 16px}
.review p{margin:8px 0 0;color:var(--muted)}
.btn{display:inline-block;background:var(--accent);color:#fff;padding:8px 14px;
border-radius:7px;text-decoration:none;font-weight:600}
nav{z-index:2;display:flex;flex-direction:column;gap:8px;margin-top:20px;
padding:10px max(16px,calc((100% - 1200px)/2 + 16px));
background:var(--bg);border-bottom:1px solid var(--line)}
@media (min-width:700px){nav{position:sticky;top:0}}
.links,.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.links a{color:var(--fg);text-decoration:none;padding:4px 10px;border-radius:6px;
border:1px solid var(--line);background:var(--card)}
.links a span{color:var(--muted);margin-left:4px}
.filters input[type=search],.filters select,.filters button{font:inherit;min-width:0;
padding:4px 8px;border-radius:6px;border:1px solid var(--line);background:var(--card);
color:var(--fg)}
.filters input[type=search]{flex:0 1 180px}
.filters label{display:flex;gap:4px;align-items:center;color:var(--muted);white-space:nowrap}
.filters button{cursor:pointer;color:var(--muted)}
.filters.active button{color:var(--accent);border-color:var(--accent)}
[id]{scroll-margin-top:var(--nav-h,16px)}
tr:target td{background:color-mix(in srgb,var(--accent) 12%,transparent)}
article:target{outline:2px solid var(--accent);outline-offset:-1px}
.jump{display:inline-block;margin-left:8px;font-size:11px;color:var(--accent);
text-decoration:none;white-space:nowrap}
.jump:hover,.back:hover{text-decoration:underline}
.back{margin-left:8px;font-weight:400;color:var(--accent);text-decoration:none}
.legend{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.scroll{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
thead th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr.group th{background:var(--bg);font-size:12px;color:var(--muted)}
td.name{min-width:200px}td.name small{display:block;color:var(--muted);white-space:pre-line}
td.ver{color:var(--muted);font-size:12px;white-space:nowrap}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;
white-space:nowrap;border:1px solid transparent}
.st-done{background:var(--done-bg);color:var(--done)}
.st-rework{background:var(--done-bg);color:var(--wip);border-color:var(--wip)}
.st-wip{background:var(--wip-bg);color:var(--wip)}
.st-todo{color:var(--todo);border-color:var(--line)}
.st-none{color:var(--muted);border:1px dashed var(--line)}
.na{color:var(--muted);opacity:.5}
.behind{color:var(--rtk);font-weight:600}.norender{opacity:.6}
td.ver .rv{color:var(--fg)}td.ver small{font-size:inherit}td.ver .shot{font-weight:600}
td.th{width:1px;padding-right:0}
/* Any aspect ratio: shown whole inside a fixed box, never cropped. */
.thumb{display:block;width:112px;height:63px;object-fit:contain;border-radius:4px;
background:var(--bg);transition:transform .15s}
.nothumb{width:112px}
img.thumb:hover{transform:scale(2.4);transform-origin:left top;position:relative;
z-index:3;box-shadow:0 4px 18px rgba(0,0,0,.35)}
.flag{margin-left:8px;font-size:11px;font-weight:600;color:var(--rtk);
background:var(--rtk-bg);padding:1px 6px;border-radius:999px}
article{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:12px 16px;margin-bottom:12px}
article ul{list-style:none;margin:0;padding:0}
article li{padding:8px 0;border-top:1px solid var(--line)}
article li.reply{margin-left:24px}
article li p{margin:4px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}
.head{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.who{margin-left:auto;color:var(--muted);font-size:12px}
.type,.tag{font-size:11px;padding:1px 7px;border-radius:999px;border:1px solid var(--line)}
.type{font-weight:600;text-transform:uppercase}
.t-rtk{color:var(--rtk);background:var(--rtk-bg);border-color:transparent}
.t-todo{color:var(--wip);background:var(--wip-bg);border-color:transparent}
.empty{color:var(--muted)}
section:last-of-type{padding-bottom:40px}
@media print{nav,.review,.jump,.back{display:none}.scroll{overflow:visible}}
"""

_JS = """
(function(){
var $=function(id){return document.getElementById(id);};
var nav=document.querySelector('nav'),bar=document.querySelector('.filters');
var ctl=['f-name','f-group','f-dep','f-state','f-rtk','f-notes'].map($);
function navHeight(){var sticky=getComputedStyle(nav).position==='sticky';
document.documentElement.style.setProperty('--nav-h',
(sticky?nav.offsetHeight:0)+16+'px');}
function match(el){
var q=ctl[0].value.trim().toLowerCase(),g=ctl[1].value,d=ctl[2].value,st=ctl[3].value;
if(q&&el.dataset.name.indexOf(q)<0)return false;
if(g&&el.dataset.group!==g)return false;
if(ctl[4].checked&&el.dataset.rtk==='0')return false;
if(ctl[5].checked&&el.dataset.notes==='0')return false;
if(d||st){var states=el.dataset.states.split(' ').filter(Boolean).map(function(x){
return x.split(':');});
if(!states.some(function(p){return(!d||p[0]===d)&&(!st||p[1]===st);}))return false;}
return true;}
function apply(){
var on=ctl.some(function(c){return c.type==='checkbox'?c.checked:c.value;});
bar.classList.toggle('active',on);
['assets','shots','notes'].forEach(function(id){
var sec=$(id),n=0,items=sec.querySelectorAll('.item');
items.forEach(function(el){el.hidden=!match(el);
if(!el.hidden)n+=id==='notes'?+el.dataset.threads:1;});
sec.querySelectorAll('tr.group').forEach(function(row){
var next=row.nextElementSibling,any=false;
while(next&&!next.classList.contains('group')){if(!next.hidden)any=true;
next=next.nextElementSibling;}row.hidden=!any;});
var none=sec.querySelector('.nomatch'),table=sec.querySelector('.scroll');
if(none)none.hidden=!items.length||n>0;if(table)table.hidden=items.length&&!n;
$('c-'+id).textContent=n;});}
ctl.forEach(function(c){c.addEventListener('input',apply);
c.addEventListener('change',apply);});
$('f-reset').addEventListener('click',function(){ctl.forEach(function(c){
if(c.type==='checkbox')c.checked=false;else c.value='';});apply();});
window.addEventListener('resize',navHeight);navHeight();apply();
})();
"""


# ---------------------------------------------------------------------------
# Review template (XLSX)
# ---------------------------------------------------------------------------

# Columns of the review sheet, in order. Hidden ones are written by the
# addon for the import, never meant to be edited.
_REVIEW_COLUMNS = (
    # (header, width, hidden)
    ("group", 13, False),
    ("filename", 30, False),
    ("description", 30, False),
    ("department", 14, False),
    ("type", 8, False),
    ("shot", 8, False),
    ("text", 70, False),
    ("wip_version", 10, True),
    ("stable_version", 10, True),
)
_COL = {h: chr(65 + i) for i, (h, _, _) in enumerate(_REVIEW_COLUMNS)}
_HEADER_ROW = 6
_META_COL = chr(65 + len(_REVIEW_COLUMNS))  # hidden cell holding schema_version=N

# cellXfs indexes in _STYLES_XML
_S_TITLE, _S_LABEL, _S_HINT, _S_HEADER, _S_LOCKED, _S_LOCKED_MUTED = 1, 2, 3, 4, 5, 6
_S_INPUT, _S_INPUT_DATE, _S_INPUT_TEXT, _S_GROUP = 7, 8, 9, 10

_XML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _col(n: int) -> str:
    """0-based column index -> letters."""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref: str, value, style: int = 0) -> str:
    if value in (None, ""):
        return f'<c r="{ref}" s="{style}"/>'
    text = xml_escape(_XML_ILLEGAL.sub("", str(value)))
    return (
        f'<c r="{ref}" s="{style}" t="inlineStr">'
        f'<is><t xml:space="preserve">{text}</t></is></c>'
    )


def _stem(filename: str | None) -> str | None:
    """"ch_bob_v004.blend" -> "ch_bob_v004" (the import adds .blend back)."""
    return filename[: -len(".blend")] if filename and filename.endswith(".blend") else filename


def render_review_xlsx(snapshot: dict) -> bytes:
    """Review template: one row per asset/shot, grouped by prefix/sequence
    in a merged left column, filename and known versions locked in,
    department/type dropdowns, Author/Review date at the top."""
    meta = snapshot["meta"]
    items = snapshot["assets"] + snapshot["shots"]
    first = _HEADER_ROW + 1
    last = _HEADER_ROW + max(1, len(items))

    title = f"{meta.get('project') or ''} review".strip()
    scan_date = (meta.get("scan_started_at") or "").replace("T", " ")
    intro = (
        f"Snapshot of {scan_date}. Write in the white cells. One line of text "
        "= one note (Alt+Enter for the next one); rows with an empty text are "
        "ignored."
    )
    rows = [
        '<row r="1">'
        + _cell("A1", title, _S_TITLE)
        + _cell(f"{_META_COL}1", f"schema_version={SCHEMA_VERSION}")
        + "</row>",
        '<row r="2">'
        + _cell("A2", "Author", _S_LABEL)
        + _cell("B2", "", _S_INPUT)
        + _cell("C2", 'Empty: "prod"', _S_HINT)
        + "</row>",
        '<row r="3">'
        + _cell("A3", "Review date", _S_LABEL)
        + _cell("B3", "", _S_INPUT_DATE)
        + _cell("C3", "Empty: the day the file is imported", _S_HINT)
        + "</row>",
        '<row r="4">' + _cell("A4", intro, _S_HINT) + "</row>",
        f'<row r="{_HEADER_ROW}">'
        + "".join(
            _cell(f"{_COL[h]}{_HEADER_ROW}", h, _S_HEADER) for h, _, _ in _REVIEW_COLUMNS
        )
        + "</row>",
    ]
    styles = {
        "group": _S_GROUP,
        "filename": _S_LOCKED,
        "description": _S_LOCKED_MUTED,
        "department": _S_INPUT,
        "type": _S_INPUT,
        "shot": _S_INPUT_TEXT,
        "text": _S_INPUT,
        "wip_version": _S_LOCKED,
        "stable_version": _S_LOCKED,
    }
    dep_lists: dict[str, list[str]] = {}
    merges = []
    group_start = None
    for n, item in enumerate(items):
        r = first + n
        new_group = n == 0 or item["group"] != items[n - 1]["group"]
        if new_group:
            if group_start is not None and r - 1 > group_start:
                merges.append(f"A{group_start}:A{r - 1}")
            group_start = r
        values = {
            # Only the merge's top cell holds the value.
            "group": item["group"] if new_group else None,
            "filename": _stem(item["current_version"]) or item["name"],
            "description": item["description"],
            "type": "rtk",
            "wip_version": _stem(item["wip_version"]),
            "stable_version": _stem(item["stable_version"]),
        }
        cells = "".join(
            _cell(f"{_COL[h]}{r}", values.get(h), styles[h]) for h, _, _ in _REVIEW_COLUMNS
        )
        rows.append(f'<row r="{r}">{cells}</row>')
        deps = ",".join(item["departments_required"])
        if deps and len(deps) <= 255:  # Excel's inline list limit
            dep_lists.setdefault(deps, []).append(f"{_COL['department']}{r}")
    if group_start is not None and last > group_start:
        merges.append(f"A{group_start}:A{last}")

    t = _COL["type"]
    validations = [
        f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" '
        f'sqref="{t}{first}:{t}{last}"><formula1>"{",".join(ENTRY_TYPES)}"</formula1>'
        "</dataValidation>"
    ] + [
        f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" '
        f'sqref="{" ".join(refs)}"><formula1>"{xml_escape(deps)}"</formula1>'
        "</dataValidation>"
        for deps, refs in dep_lists.items()
    ]
    cols = "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"'
        + (' hidden="1"' if hidden else "")
        + "/>"
        for i, (_, w, hidden) in enumerate(_REVIEW_COLUMNS)
    )
    meta_n = len(_REVIEW_COLUMNS) + 1
    cols += f'<col min="{meta_n}" max="{meta_n}" width="8" hidden="1"/>'
    filter_ref = f"A{_HEADER_ROW}:{_COL['text']}{last}"
    merge_xml = (
        f'<mergeCells count="{len(merges)}">'
        + "".join(f'<mergeCell ref="{m}"/>' for m in merges)
        + "</mergeCells>"
        if merges
        else ""
    )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>'
        f'<dimension ref="A1:{_META_COL}{last}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        f'<pane ySplit="{_HEADER_ROW}" topLeftCell="A{first}" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="B2" sqref="B2"/>'
        "</sheetView></sheetViews>"
        f"<cols>{cols}</cols>"
        f"<sheetData>{''.join(rows)}</sheetData>"
        # No password: this only stops accidental edits of the locked columns.
        '<sheetProtection sheet="1" objects="1" scenarios="1" formatCells="0" '
        'formatColumns="0" formatRows="0" autoFilter="0"/>'
        f'<autoFilter ref="{filter_ref}"/>'
        f"{merge_xml}"
        f'<dataValidations count="{len(validations)}">{"".join(validations)}</dataValidations>'
        '<pageMargins left="0.5" right="0.5" top="0.5" bottom="0.5" header="0.3" footer="0.3"/>'
        # Printed landscape, one page wide.
        '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>'
        "</worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Review" sheetId="1" r:id="rId1"/></sheets>'
        '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" '
        f'hidden="1">Review!$A${_HEADER_ROW}:${_COL["text"]}${last}</definedName></definedNames>'
        "</workbook>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        z.writestr("_rels/.rels", _RELS_XML)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS_XML)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/styles.xml", _STYLES_XML)
    return buf.getvalue()


_CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    "</Types>"
)
_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)
_WORKBOOK_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)
# One font, one size: weight and grey only. Grey fill = locked, white =
# to fill in. cellXfs: 0 default, 1 title, 2 label, 3 hint, 4 header,
# 5 locked, 6 locked muted, 7 input, 8 input date, 9 input text-format
# (keeps "045" a string), 10 group (merged left column).
_UNLOCK = '<protection locked="0"/>'
_TOP = '<alignment vertical="top"/>'
_TOP_WRAP = '<alignment vertical="top" wrapText="1"/>'
_STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy-mm-dd"/></numFmts>'
    '<fonts count="3">'
    '<font><sz val="11"/><color rgb="FF1F2328"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><color rgb="FF1F2328"/><name val="Calibri"/></font>'
    '<font><sz val="11"/><color rgb="FF6E7781"/><name val="Calibri"/></font>'
    "</fonts>"
    '<fills count="5">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFDDE3EA"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFF3F4F6"/></patternFill></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFE9EDF2"/></patternFill></fill>'
    "</fills>"
    '<borders count="2"><border/>'
    '<border><left style="thin"><color rgb="FFC8CED6"/></left><right style="thin"><color rgb="FFC8CED6"/></right>'
    '<top style="thin"><color rgb="FFC8CED6"/></top><bottom style="thin"><color rgb="FFC8CED6"/></bottom></border>'
    "</borders>"
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="11">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>'
    f'<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1">{_TOP}</xf>'
    f'<xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">{_TOP_WRAP}</xf>'
    f'<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1" applyProtection="1">{_TOP_WRAP}{_UNLOCK}</xf>'
    f'<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1" applyProtection="1"><alignment horizontal="left"/>{_UNLOCK}</xf>'
    f'<xf numFmtId="49" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1" applyProtection="1">{_TOP}{_UNLOCK}</xf>'
    '<xf numFmtId="0" fontId="1" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
    "</cellXfs>"
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    "</styleSheet>"
)


# ---------------------------------------------------------------------------
# Review import (XLSX)
# ---------------------------------------------------------------------------

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _first_sheet_path(z: zipfile.ZipFile) -> str:
    """Zip path of the workbook's first sheet (not always sheet1.xml once
    a spreadsheet app has re-saved it)."""
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rid = wb.find(f"{_NS}sheets/{_NS}sheet").get(f"{_REL_NS}id")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        for rel in rels.iter(f"{_PKG_REL_NS}Relationship"):
            if rel.get("Id") == rid:
                target = rel.get("Target")
                return target.lstrip("/") if target.startswith("/") else f"xl/{target}"
    except (KeyError, AttributeError, ET.ParseError):
        pass
    return "xl/worksheets/sheet1.xml"


def _string_item(si) -> str:
    """Text of a sharedStrings <si> (plain or rich text runs, never the
    phonetic <rPh> guide)."""
    parts = []
    for child in si:
        if child.tag == f"{_NS}t":
            parts.append(child.text or "")
        elif child.tag == f"{_NS}r":
            parts.extend(t.text or "" for t in child.iter(f"{_NS}t"))
    return "".join(parts)


def _ref_split(ref: str) -> tuple[str, int]:
    m = re.match(r"([A-Z]+)(\d+)", ref or "")
    return (m[1], int(m[2])) if m else ("", 0)


def read_xlsx_grid(path: Path) -> dict[int, dict[str, str]]:
    """First sheet of an .xlsx as {row number: {column letters: text}}.
    Text cells resolved through sharedStrings (t="s") or inline; numbers
    (dates included) kept as their raw text."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            shared = []
            if "xl/sharedStrings.xml" in names:
                sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
                shared = [_string_item(si) for si in sst.iter(f"{_NS}si")]
            sheet = ET.fromstring(z.read(_first_sheet_path(z)))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as e:
        raise PipelineError(f"Could not read {Path(path).name} as a spreadsheet: {e}")

    grid: dict[int, dict[str, str]] = {}
    row_n = 0
    for row in sheet.iter(f"{_NS}row"):
        row_n = int(row.get("r") or row_n + 1)
        col_n = -1
        for c in row.iter(f"{_NS}c"):
            col, _ = _ref_split(c.get("r"))
            if not col:
                col_n += 1
                col = _col(col_n)
            else:
                col_n = sum((ord(ch) - 64) * 26**i for i, ch in enumerate(reversed(col))) - 1
            t = c.get("t")
            v = c.find(f"{_NS}v")
            if t == "inlineStr":
                value = "".join(x.text or "" for x in c.iter(f"{_NS}t"))
            elif v is None or v.text is None:
                continue
            elif t == "s":
                value = shared[int(v.text)]
            else:
                value = v.text
            # Excel escapes a CR as _x000D_ in strings.
            value = value.replace("_x000D_", "").replace("\r\n", "\n")
            if value != "":
                grid.setdefault(row_n, {})[col] = value
    return grid


def parse_review_date(value: str) -> datetime | None:
    """A Review date cell: an Excel date serial (a typed date is stored as a
    number of days), or text in a common date format. None when empty."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime(1899, 12, 30) + timedelta(days=float(value))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise PipelineError(f"Review date '{value}' not understood (use YYYY-MM-DD).")


def read_review_xlsx(path: Path) -> dict:
    """{"schema_version", "author", "review_date", "rows"} from a filled
    review template; rows keyed by the header row's names."""
    grid = read_xlsx_grid(path)
    schema = None
    author = date = ""
    header_row = None
    for r in sorted(grid):
        cells = grid[r]
        for v in cells.values():
            m = re.fullmatch(r"schema_version=(\d+)", v.strip())
            if m:
                schema = int(m[1])
        label = cells.get("A", "").strip().lower()
        if label == "author":
            author = cells.get("B", "")
        elif label == "review date":
            date = cells.get("B", "")
        elif any(v.strip().lower() == "filename" for v in cells.values()):
            header_row = r
            break
    if schema is None or header_row is None:
        raise PipelineError(
            f"{Path(path).name} isn't a review template exported by this addon."
        )
    if schema > SCHEMA_VERSION:
        raise PipelineError(
            f"{Path(path).name} comes from a newer addon version (template "
            f"v{schema}); update the addon to import it."
        )
    header = {col: name.strip().lower() for col, name in grid[header_row].items()}
    rows = [
        {header[col]: v.strip() for col, v in grid[r].items() if col in header}
        for r in sorted(grid)
        if r > header_row
    ]
    return {
        "schema_version": schema,
        "author": author.strip(),
        "review_date": parse_review_date(date),
        "rows": rows,
    }


_BULLET = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+")


def import_review_xlsx(path: Path) -> dict:
    """Create one entry per line of each filled text cell of a review
    template, all sharing one review_id, stamped with the template's Author
    ("prod" if empty) and Review date (import time if empty), anchored on
    the version the snapshot showed. A line already imported (same file,
    text and author, from a review) is skipped, so re-importing a file --
    or a re-sent one with notes added -- never duplicates.
    Returns {"imported", "duplicates", "skipped": [(label, reason)]}."""
    review = read_review_xlsx(path)
    author = review["author"] or "prod"
    date = review["review_date"]
    created_at = date.isoformat(timespec="seconds") if date else None
    review_id = hashlib.sha1(f"{now()}{Path(path).name}".encode("utf-8")).hexdigest()[:5]
    result = {"imported": 0, "duplicates": 0, "skipped": []}
    for row in review["rows"]:
        if not row.get("filename"):
            continue
        # One line of a text cell = one entry (see NOTES.md, "Batched review
        # input, still one entry each"); a typed bullet is dropped.
        lines = [
            line
            for line in (_BULLET.sub("", l).strip() for l in row.get("text", "").split("\n"))
            if line
        ]
        if not lines:
            continue
        name = row["filename"]
        try:
            filepath = find_file_by_name(
                name if name.endswith(".blend") else f"{name}.blend"
            )
        except PipelineError:  # unknown prefix...
            filepath = None
        if not filepath:
            result["skipped"].extend(
                (f"{name}: {line[:40]}", "file not found (renamed, branched or archived?)")
                for line in lines
            )
            continue
        known = {
            e.get("text")
            for e in (read_json_quiet(tracking_json_path(filepath)) or {}).get("entries", [])
            if e.get("source") == REVIEW_SOURCE and e.get("author") == author
        }
        department = (row.get("department") or "").lower()
        try:
            department = valid_department(filepath, department) if department else ""
        except PipelineError:
            department = ""
        entry_type = (row.get("type") or "").lower()
        for line in lines:
            if line in known:
                result["duplicates"] += 1
                continue
            try:
                create_entry(
                    filepath,
                    text=line,
                    department=department,
                    author=author,
                    type=entry_type if entry_type in ENTRY_TYPES else "note",
                    shot=row.get("shot") or None,
                    review_id=review_id,
                    created_at=created_at,
                    referenced_version=str(filepath),
                    source=REVIEW_SOURCE,
                )
                known.add(line)
                result["imported"] += 1
            except PipelineError as e:
                result["skipped"].append((f"{name}: {line[:40]}", e.message))
    return result
