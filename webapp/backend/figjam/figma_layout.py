"""Turns ResearchMate's FigJam-agent analysis output into a FigJam layout and
pushes it via figma_mcp_client. Deterministic layout math is plain Python
(code = reliable data operations); the actual board writes go through the
real figjam_create_section / figjam_create_stickies MCP tools, confirmed live
against a running figma-console-mcp instance (see FIGMA_CONNECT.md for the
exact tool schemas discovered).
"""

from __future__ import annotations

from typing import Any

from . import figma_mcp_client as mcp_client
from .layout_geometry import Rect, assert_no_overlaps, grid_positions

# figjam_create_stickies only accepts this fixed color enum (confirmed via the
# live tool schema), not arbitrary hex values.
_SECTION_COLORS = {
    "themes": "YELLOW",
    "insights": "GREEN",
    "contradictions": "RED",
    "research_gaps": "PURPLE",
    "design_opportunities": "BLUE",
}

_SECTION_FILL_HEX = {
    "themes": "#FFF9DB",
    "insights": "#E6F4EA",
    "contradictions": "#FCE8E6",
    "research_gaps": "#F1E6FA",
    "design_opportunities": "#E6F0FA",
}

_SECTION_TITLES = {
    "themes": "Themes",
    "insights": "Insights",
    "contradictions": "Contradictions",
    "research_gaps": "Research Gaps",
    "design_opportunities": "Design Opportunities",
}

# Confirmed live against the real figjam_create_stickies tool: a sticky note
# is ALWAYS a fixed 240x240 square - passing width/height is silently
# ignored. The previous constants here (220 wide, 140 tall) were both wrong,
# which is exactly why stickies visually overlapped: rows spaced 140px apart
# with 240px-tall stickies overlap by 100px, and columns spaced 220px apart
# with 240px-wide stickies overlap by 20px.
STICKY_SIZE = 240
H_GAP = 24
V_GAP = 24
STICKIES_PER_ROW = 3
SECTION_PADDING = 48
SECTION_HEADER_HEIGHT = 0  # figjam_create_section renders its own title bar; content starts at section (x, y)
SECTION_GAP = 80


def _item_text(section_key: str, item: Any) -> str:
    if section_key == "themes":
        return f"{item.get('id', '')}: {item.get('name', '')}\n\nEvidence: {', '.join(item.get('evidence', [])) or 'none'}"
    if section_key == "insights":
        verdict = item.get("verdict", "").upper()
        return f"{item.get('id', '')} [{verdict}]: {item.get('statement', '')}"
    if section_key == "contradictions":
        return f"{item.get('id', '')}: {item.get('description', '')}"
    return str(item)


def build_layout_plan(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Returns a list of section plans: [{key, title, color, x, y, width, height, items, sticky_rects}].
    Section width/height and every sticky's rect are derived from the real,
    fixed 240x240 sticky size, and each section's x is offset by the
    previous section's actual computed width (not a fixed guess), so this
    still produces a non-overlapping layout regardless of how many items any
    given section ends up with."""
    plan: list[dict[str, Any]] = []
    cursor_x = 0.0

    for key in ("themes", "insights", "contradictions", "research_gaps", "design_opportunities"):
        raw_items = analysis.get(key, [])
        if not raw_items:
            continue

        if key in ("research_gaps", "design_opportunities"):
            texts = [str(item) for item in raw_items]
        else:
            texts = [_item_text(key, item) for item in raw_items]

        columns = min(len(texts), STICKIES_PER_ROW)
        rows = -(-len(texts) // STICKIES_PER_ROW)  # ceil division
        width = SECTION_PADDING * 2 + columns * STICKY_SIZE + max(columns - 1, 0) * H_GAP
        height = SECTION_PADDING * 2 + rows * STICKY_SIZE + max(rows - 1, 0) * V_GAP

        # Section-relative coordinates (origin at the section's own top-left,
        # not the board origin) - push_layout_to_figjam adds section["x"]/["y"]
        # when creating the actual stickies, so this must NOT also include
        # cursor_x or it would be added twice.
        sticky_rects = grid_positions(
            count=len(texts),
            columns=STICKIES_PER_ROW,
            cell_width=STICKY_SIZE,
            cell_height=STICKY_SIZE,
            h_gap=H_GAP,
            v_gap=V_GAP,
            origin_x=SECTION_PADDING,
            origin_y=SECTION_PADDING,
        )

        plan.append({
            "key": key,
            "title": _SECTION_TITLES[key],
            "sticky_color": _SECTION_COLORS[key],
            "fill_color": _SECTION_FILL_HEX[key],
            "x": cursor_x,
            "y": 0,
            "width": width,
            "height": height,
            "items": texts,
            "sticky_rects": sticky_rects,
        })
        cursor_x += width + SECTION_GAP

    return plan


async def push_layout_to_figjam(analysis: dict[str, Any]) -> dict[str, Any]:
    """Creates a real FigJam section per group, with a grid of stickies inside
    it, on the connected board. Returns a summary for the Agent Activity log."""
    plan = build_layout_plan(analysis)
    if not plan:
        raise ValueError("Nothing to push: run analysis first, there are no themes/insights/etc. yet.")

    # Sections are checked separately from their own stickies (a sticky is
    # expected to sit inside its own section, that's not a collision) but no
    # two DIFFERENT sections' content may overlap.
    assert_no_overlaps([Rect(s["x"], s["y"], s["width"], s["height"]) for s in plan], label="sections")
    for section in plan:
        assert_no_overlaps(section["sticky_rects"], label=f"stickies in '{section['title']}'")

    activity: list[str] = []
    created_stickies = 0

    async with mcp_client.session() as sess:
        await mcp_client.wait_for_bridge(sess)
        activity.append("Connected to Figma Desktop Bridge")

        for section in plan:
            await mcp_client.create_section(
                sess,
                name=section["title"],
                x=section["x"],
                y=section["y"],
                width=section["width"],
                height=section["height"],
                fill_color=section["fill_color"],
            )
            activity.append(f"Created section '{section['title']}'")

            stickies = [
                {
                    "text": text,
                    "x": section["x"] + rect.x,
                    "y": section["y"] + rect.y,
                    "color": section["sticky_color"],
                }
                for text, rect in zip(section["items"], section["sticky_rects"])
            ]
            await mcp_client.create_stickies(sess, stickies)
            created_stickies += len(stickies)
            activity.append(f"Created {len(stickies)} sticky note(s) in '{section['title']}'")

    return {
        "sections": [s["title"] for s in plan],
        "stickies_created": created_stickies,
        "activity": activity,
    }
