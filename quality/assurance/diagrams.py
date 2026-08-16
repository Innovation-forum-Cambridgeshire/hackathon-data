"""The architecture drawings: a crow's-foot ERD per challenge, and the pipeline
as swimlanes.

WHY THESE ARE HAND-DRAWN SVG
Graphviz and Mermaid both do this better than the code below. Neither is
available: mermaid needs a browser or a node toolchain and would have to be
fetched at render time, which is exactly the external dependency the rest of
this report avoids, and graphviz is a system package this repository does not
otherwise need. Since the diagrams are small and fixed — five ERDs of two or
three entities each, one swimlane — a few hundred lines of SVG generation buys
brand-exact output, deterministic bytes (so the diagrams do not churn in git),
and no dependency at all.

Determinism matters more than it looks: these files are committed, and a layout
engine that reflows on a version bump would produce a diff on every unrelated
build.

NOTATION
    Crow's foot, drawn the usual way round: the fan is at the MANY end, a single
    bar is at the ONE end. Read a line as "one <parent> has many <child>".

    A dashed line with a struck-through end is not a relationship. It is a
    HAZARD — a join a participant will reasonably attempt that the data does not
    support. c05's weather-to-alerts gap is the important one and it is drawn
    like this rather than omitted, because an ERD that simply lacks the line
    reads as an oversight instead of as a decision.

Accessibility: every diagram carries <title> and <desc>, relationships are
distinguished by line STYLE as well as colour, and the hazard markers are
shapes. The colours come from brand.py so the drawings match the site.
"""

from __future__ import annotations

import html
from typing import Any

from . import brand

# --- geometry ---------------------------------------------------------------
ENTITY_W = 268
ROW_H = 19
HEADER_H = 42
GRAIN_H = 15
PAD_X = 34
PAD_Y = 30
COL_GAP = 96
FONT = 12


def _esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def _text(x: float, y: float, s: str, size: float = FONT, weight: str = "400",
          fill: str = brand.TEXT, family: str | None = None, anchor: str = "start",
          opacity: float = 1.0) -> str:
    fam = family or brand.FONT_BODY
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family={_q(fam)} font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"'
        + (f' opacity="{opacity}"' if opacity != 1.0 else "")
        + f">{_esc(s)}</text>"
    )


def _q(value: str) -> str:
    return '"' + value.replace('"', "'") + '"'


def _truncate(s: str, limit: int) -> str:
    return s if len(s) <= limit else s[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# crow's-foot ends
# ---------------------------------------------------------------------------
def _crows_foot(x: float, y: float, facing: int, colour: str) -> str:
    """The 'many' end. `facing` is +1 to point right, -1 to point left."""
    d = 11 * facing
    s = 8
    return (
        f'<path d="M{x:.1f},{y:.1f} L{x + d:.1f},{y - s:.1f} '
        f'M{x:.1f},{y:.1f} L{x + d:.1f},{y:.1f} '
        f'M{x:.1f},{y:.1f} L{x + d:.1f},{y + s:.1f}" '
        f'stroke="{colour}" stroke-width="1.6" fill="none" stroke-linecap="round"/>'
    )


def _one_bar(x: float, y: float, facing: int, colour: str) -> str:
    """The 'one' end: a single perpendicular bar."""
    off = 9 * facing
    return (
        f'<path d="M{x + off:.1f},{y - 7:.1f} L{x + off:.1f},{y + 7:.1f}" '
        f'stroke="{colour}" stroke-width="1.6" stroke-linecap="round"/>'
    )


def _blocked_end(x: float, y: float, facing: int, colour: str) -> str:
    """A hazard end: a double strike, meaning 'this join does not exist'."""
    o1, o2 = 6 * facing, 12 * facing
    return (
        f'<path d="M{x + o1:.1f},{y - 8:.1f} L{x + o1:.1f},{y + 8:.1f} '
        f'M{x + o2:.1f},{y - 8:.1f} L{x + o2:.1f},{y + 8:.1f}" '
        f'stroke="{colour}" stroke-width="1.8" stroke-linecap="round"/>'
    )


# ---------------------------------------------------------------------------
# ERD
# ---------------------------------------------------------------------------
def _entity_height(n_columns: int) -> float:
    return HEADER_H + GRAIN_H + n_columns * ROW_H + 10


def _entity(x: float, y: float, table, key_columns: set[str], fk_columns: set[str]) -> str:
    h = _entity_height(len(table.columns))
    parts = [
        f'<g><rect x="{x:.1f}" y="{y:.1f}" width="{ENTITY_W}" height="{h:.1f}" '
        f'fill="#ffffff" stroke="{brand.TEXT}" stroke-width="1.2"/>',
        # header band
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{ENTITY_W}" height="{HEADER_H}" '
        f'fill="{brand.ACCENT_600}"/>',
        _text(x + 12, y + 18, table.name, 13.5, "600", "#ffffff", brand.FONT_HEADING),
        _text(x + 12, y + 33, f"{table.approx_rows:,} rows" if table.approx_rows else "",
              10.5, "400", "#ffffff", brand.FONT_MONO, opacity=0.85),
    ]
    gy = y + HEADER_H + 11
    parts.append(
        _text(x + 12, gy, _truncate(table.grain.split("—")[0].strip(), 46), 9.8, "400",
              brand.NEUTRAL_700, brand.FONT_BODY)
    )
    parts.append(
        f'<line x1="{x:.1f}" y1="{y + HEADER_H + GRAIN_H:.1f}" '
        f'x2="{x + ENTITY_W:.1f}" y2="{y + HEADER_H + GRAIN_H:.1f}" '
        f'stroke="{brand.NEUTRAL_300}" stroke-width="1"/>'
    )

    ry = y + HEADER_H + GRAIN_H + 15
    for col in table.columns:
        is_key, is_fk = col.name in key_columns, col.name in fk_columns
        if is_key:
            parts.append(
                f'<rect x="{x + 1:.1f}" y="{ry - 13:.1f}" width="{ENTITY_W - 2}" '
                f'height="{ROW_H - 2}" fill="{brand.ACCENT_100}"/>'
            )
        marker = "PK" if is_key else ("FK" if is_fk else "")
        if marker:
            parts.append(
                _text(x + 12, ry, marker, 8.6, "600",
                      brand.ACCENT_700 if is_key else brand.AQUA_700, brand.FONT_MONO)
            )
        parts.append(
            _text(x + 34, ry, _truncate(col.name, 26), 11, "600" if is_key else "400",
                  brand.TEXT, brand.FONT_MONO)
        )
        parts.append(
            _text(x + ENTITY_W - 12, ry, col.type, 9.6, "400", brand.NEUTRAL_600,
                  brand.FONT_BODY, anchor="end")
        )
        ry += ROW_H

    parts.append("</g>")
    return "\n".join(parts)


def erd(challenge, contract_cfg: dict[str, Any]) -> str:
    """Crow's-foot ERD for one challenge."""
    tables = challenge.tables
    if not tables:
        return ""

    key_by_table: dict[str, set[str]] = {}
    for t in tables:
        cfg = (contract_cfg or {}).get(t.name, {}) or {}
        key_by_table[t.name] = set(cfg.get("unique_key") or [])

    fk_by_table: dict[str, set[str]] = {t.name: set() for t in tables}
    for rel in challenge.relationships:
        fk_by_table.setdefault(rel.from_table, set()).update(rel.from_columns)

    # Entities in a row, tallest first is NOT used — declaration order is kept so
    # the drawing matches the catalogue and stays stable across builds.
    xs, heights = {}, {}
    x = PAD_X
    for t in tables:
        xs[t.name] = x
        heights[t.name] = _entity_height(len(t.columns))
        x += ENTITY_W + COL_GAP
    width = x - COL_GAP + PAD_X

    top = PAD_Y + 46
    body_h = max(heights.values())

    # Connector lane below the entities, so a relationship between non-adjacent
    # entities never crosses a box.
    lanes = challenge.relationships + [h for h in challenge.hazards if len(h.tables) == 2]
    lane_h = 34 * len(lanes) + (24 if lanes else 0)
    height = top + body_h + lane_h + PAD_Y + 30

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" '
        f'aria-labelledby="erd-title-{challenge.slug} erd-desc-{challenge.slug}">',
        f'<title id="erd-title-{challenge.slug}">Entity relationship diagram — {_esc(challenge.title)}</title>',
        f'<desc id="erd-desc-{challenge.slug}">'
        f'{len(tables)} tables, {len(challenge.relationships)} enforced relationships and '
        f'{len(challenge.hazards)} recorded join hazards. Crow\'s foot notation: the fan is '
        f'the many end, the bar is the one end. Dashed lines with struck ends are joins the '
        f'data does not support.</desc>',
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="{brand.BG}"/>',
        _text(PAD_X, PAD_Y + 6, challenge.title, 21, "600", brand.TEXT, brand.FONT_HEADING),
        _text(PAD_X, PAD_Y + 25, f"{challenge.slug}  ·  {challenge.domain}", 11, "400",
              brand.NEUTRAL_700, brand.FONT_MONO),
    ]

    for t in tables:
        parts.append(_entity(xs[t.name], top, t, key_by_table[t.name], fk_by_table[t.name]))

    # --- relationships -----------------------------------------------------
    # Each connector leaves its entity from a slightly different x, so two
    # connectors sharing an entity do not draw their vertical segments on top of
    # each other. Without this, c05's relationship and its hazard both drop from
    # the centre of alert_history and the red dashed line hides under the green
    # one — which loses exactly the distinction the drawing exists to make.
    attach_count: dict[str, int] = {}

    def attach_x(table_name: str) -> float:
        i = attach_count.get(table_name, 0)
        attach_count[table_name] = i + 1
        # Alternate either side of centre: 0, +22, -22, +44, ...
        step = ((i + 1) // 2) * 22 * (1 if i % 2 else -1)
        return xs[table_name] + ENTITY_W / 2 + (0 if i == 0 else step)

    lane_y = top + body_h + 26
    for rel in challenge.relationships:
        if rel.from_table not in xs or rel.to_table not in xs:
            continue
        x1 = attach_x(rel.from_table)
        x2 = attach_x(rel.to_table)
        colour = brand.ACCENT_600
        y1 = top + heights[rel.from_table]
        y2 = top + heights[rel.to_table]
        parts.append(
            f'<path d="M{x1:.1f},{y1:.1f} L{x1:.1f},{lane_y:.1f} L{x2:.1f},{lane_y:.1f} '
            f'L{x2:.1f},{y2:.1f}" stroke="{colour}" stroke-width="1.6" fill="none"/>'
        )
        # Child end is the MANY end, parent end is the ONE end. Both are rotated
        # 90 degrees because the connector leaves the box downwards.
        parts.append(
            f'<g transform="translate({x1:.1f},{y1:.1f}) rotate(90)">'
            + _crows_foot(0, 0, 1, colour)
            + "</g>"
        )
        parts.append(
            f'<g transform="translate({x2:.1f},{y2:.1f}) rotate(90)">'
            + (_one_bar(0, 0, 1, colour) if rel.cardinality in ("many-to-one", "one-to-one")
               else _crows_foot(0, 0, 1, colour))
            + "</g>"
        )
        label = f"{rel.name.replace('_', ' ')}  ·  {rel.cardinality}"
        parts.append(
            f'<rect x="{min(x1, x2) + 10:.1f}" y="{lane_y - 11:.1f}" '
            f'width="{abs(x2 - x1) - 20:.1f}" height="17" fill="{brand.BG}"/>'
        )
        parts.append(
            _text((x1 + x2) / 2, lane_y + 3.5, label, 10.5, "600", brand.ACCENT_700,
                  brand.FONT_BODY, anchor="middle")
        )
        lane_y += 34

    # --- hazards -----------------------------------------------------------
    for hz in challenge.hazards:
        if len(hz.tables) != 2 or any(t not in xs for t in hz.tables):
            continue
        a, b = hz.tables
        x1, x2 = attach_x(a), attach_x(b)
        colour = brand.FAIL if hz.severity == "high" else brand.WARN
        y1, y2 = top + heights[a], top + heights[b]
        parts.append(
            f'<path d="M{x1:.1f},{y1:.1f} L{x1:.1f},{lane_y:.1f} L{x2:.1f},{lane_y:.1f} '
            f'L{x2:.1f},{y2:.1f}" stroke="{colour}" stroke-width="1.6" fill="none" '
            f'stroke-dasharray="7 4"/>'
        )
        for xx, yy in ((x1, y1), (x2, y2)):
            parts.append(
                f'<g transform="translate({xx:.1f},{yy:.1f}) rotate(90)">'
                + _blocked_end(0, 0, 1, colour)
                + "</g>"
            )
        parts.append(
            f'<rect x="{min(x1, x2) + 10:.1f}" y="{lane_y - 11:.1f}" '
            f'width="{abs(x2 - x1) - 20:.1f}" height="17" fill="{brand.BG}"/>'
        )
        parts.append(
            _text((x1 + x2) / 2, lane_y + 3.5, "NO JOIN KEY — see the assessment", 10.5,
                  "600", colour, brand.FONT_BODY, anchor="middle")
        )
        lane_y += 34

    if not challenge.relationships and not any(len(h.tables) == 2 for h in challenge.hazards):
        parts.append(
            _text(PAD_X, top + body_h + 30,
                  "No cross-table key. These are three separate evidence bases about the "
                  "same problem, deliberately not joinable.",
                  11, "400", brand.NEUTRAL_700, brand.FONT_BODY)
        )

    parts.append("</svg>")
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# swimlanes
# ---------------------------------------------------------------------------
LANE_H = 96
STAGE_W = 186
STAGE_H = 60
LANE_LABEL_W = 132
STAGE_GAP = 40

KIND_STYLE = {
    "external": (brand.NEUTRAL_200, brand.NEUTRAL_600, "3 3"),
    "process": ("#ffffff", brand.TEXT, None),
    "control": (brand.ACCENT_100, brand.ACCENT_600, None),
    "artefact": (brand.AQUA_100, brand.AQUA_700, None),
}


def swimlanes(architecture: dict[str, Any]) -> str:
    """The pipeline, one lane per owner, left to right."""
    lanes = architecture.get("lanes") or []
    flows = architecture.get("flows") or []
    if not lanes:
        return ""

    stage_lane: dict[str, int] = {}
    stage_meta: dict[str, dict] = {}
    for li, lane in enumerate(lanes):
        for st in lane.get("stages") or []:
            stage_lane[st["id"]] = li
            stage_meta[st["id"]] = st

    # Column = longest path from any source, so a stage always sits to the right
    # of everything feeding it.
    incoming: dict[str, list[str]] = {s: [] for s in stage_meta}
    for f in flows:
        if f["to"] in incoming and f["from"] in stage_meta:
            incoming[f["to"]].append(f["from"])

    col: dict[str, int] = {}

    def depth(node: str, seen: frozenset = frozenset()) -> int:
        if node in col:
            return col[node]
        if node in seen or not incoming.get(node):
            return 0
        d = 1 + max(depth(p, seen | {node}) for p in incoming[node])
        return d

    for s in stage_meta:
        col[s] = depth(s)

    n_cols = max(col.values()) + 1 if col else 1
    width = LANE_LABEL_W + n_cols * (STAGE_W + STAGE_GAP) + PAD_X * 2
    height = PAD_Y + 58 + len(lanes) * LANE_H + PAD_Y

    def sx(sid: str) -> float:
        return PAD_X + LANE_LABEL_W + col[sid] * (STAGE_W + STAGE_GAP)

    def sy(sid: str) -> float:
        return PAD_Y + 58 + stage_lane[sid] * LANE_H + (LANE_H - STAGE_H) / 2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" '
        f'aria-labelledby="swim-title swim-desc">',
        '<title id="swim-title">Hackathon data pipeline, by owner</title>',
        f'<desc id="swim-desc">{len(lanes)} lanes from source to consumer. '
        f'Green boxes are controls, aqua boxes are artefacts, dashed grey boxes are '
        f'outside our control. Arrows run left to right in dependency order.</desc>',
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="{brand.BG}"/>',
        _text(PAD_X, PAD_Y + 8, "How challenge data reaches a participant", 21, "600",
              brand.TEXT, brand.FONT_HEADING),
        _text(PAD_X, PAD_Y + 28, "Every handoff is a place a guarantee can be lost silently.",
              11.5, "400", brand.NEUTRAL_700, brand.FONT_BODY),
    ]

    # lane bands
    for li, lane in enumerate(lanes):
        y = PAD_Y + 58 + li * LANE_H
        fill = "#ffffff" if li % 2 == 0 else brand.SURFACE
        parts.append(
            f'<rect x="{PAD_X:.1f}" y="{y:.1f}" width="{width - PAD_X * 2:.1f}" '
            f'height="{LANE_H}" fill="{fill}" stroke="{brand.NEUTRAL_300}" stroke-width="0.8"/>'
        )
        parts.append(
            f'<rect x="{PAD_X:.1f}" y="{y:.1f}" width="4" height="{LANE_H}" '
            f'fill="{brand.ACCENT}"/>'
        )
        parts.append(_text(PAD_X + 16, y + LANE_H / 2 - 3, lane["title"], 15, "600",
                           brand.TEXT, brand.FONT_HEADING))
        parts.append(_text(PAD_X + 16, y + LANE_H / 2 + 13, lane.get("owner", ""), 10,
                           "400", brand.NEUTRAL_600, brand.FONT_BODY))

    # arrows first, so boxes sit on top of the line ends
    parts.append(
        f'<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" '
        f'orient="auto"><path d="M0,1 L8,4.5 L0,8 Z" fill="{brand.NEUTRAL_600}"/></marker></defs>'
    )
    for f in flows:
        a, b = f["from"], f["to"]
        if a not in stage_meta or b not in stage_meta:
            continue
        ax, ay = sx(a) + STAGE_W, sy(a) + STAGE_H / 2
        bx, by = sx(b), sy(b) + STAGE_H / 2
        if col[b] == col[a]:  # same column, different lane: drop vertically
            ax, ay = sx(a) + STAGE_W / 2, sy(a) + STAGE_H
            bx, by = sx(b) + STAGE_W / 2, sy(b)
            d = f"M{ax:.1f},{ay:.1f} L{bx:.1f},{by:.1f}"
        else:
            mid = (ax + bx) / 2
            d = f"M{ax:.1f},{ay:.1f} L{mid:.1f},{ay:.1f} L{mid:.1f},{by:.1f} L{bx:.1f},{by:.1f}"
        parts.append(
            f'<path d="{d}" stroke="{brand.NEUTRAL_600}" stroke-width="1.3" fill="none" '
            f'marker-end="url(#arrow)"/>'
        )

    # stage boxes
    for sid, st in stage_meta.items():
        x, y = sx(sid), sy(sid)
        fill, stroke, dash = KIND_STYLE.get(st.get("kind", "process"), KIND_STYLE["process"])
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{STAGE_W}" height="{STAGE_H}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.3"'
            + (f' stroke-dasharray="{dash}"' if dash else "")
            + "/>"
        )
        parts.append(_text(x + 11, y + 21, _truncate(st["title"], 26), 12.5, "600",
                           brand.TEXT, brand.FONT_HEADING))
        detail = _truncate(st.get("detail", ""), 34)
        parts.append(_text(x + 11, y + 37, detail, 9.6, "400", brand.NEUTRAL_700,
                           brand.FONT_BODY))
        if st.get("kind") == "control":
            parts.append(_text(x + 11, y + 51, "CONTROL", 8.4, "600", brand.ACCENT_700,
                               brand.FONT_MONO))
        elif st.get("kind") == "artefact":
            parts.append(_text(x + 11, y + 51, "ARTEFACT", 8.4, "600", brand.AQUA_700,
                               brand.FONT_MONO))

    # legend
    ly = height - PAD_Y + 6
    lx = PAD_X + LANE_LABEL_W
    for label, kind in (("control", "control"), ("artefact", "artefact"),
                        ("process", "process"), ("outside our control", "external")):
        fill, stroke, dash = KIND_STYLE[kind]
        parts.append(
            f'<rect x="{lx:.1f}" y="{ly - 9:.1f}" width="14" height="11" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1"'
            + (f' stroke-dasharray="{dash}"' if dash else "")
            + "/>"
        )
        parts.append(_text(lx + 20, ly, label, 10, "400", brand.NEUTRAL_700, brand.FONT_BODY))
        lx += 34 + len(label) * 5.6

    parts.append("</svg>")
    return "\n".join(p for p in parts if p)
