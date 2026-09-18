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

_COLUMN_WIDTH = 900
_STICKY_WIDTH = 220
_ROW_HEIGHT = 140
_STICKIES_PER_ROW = 4
_SECTION_PADDING = 60


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
    """Returns a list of section plans: [{key, title, color, x, y, width, height, items}]."""
    plan = []
    column_x = 0

    for key in ("themes", "insights", "contradictions", "research_gaps", "design_opportunities"):
        raw_items = analysis.get(key, [])
        if not raw_items:
            continue

        if key in ("research_gaps", "design_opportunities"):
            texts = [str(item) for item in raw_items]
        else:
            texts = [_item_text(key, item) for item in raw_items]

        rows = -(-len(texts) // _STICKIES_PER_ROW)  # ceil division
        width = _SECTION_PADDING * 2 + min(len(texts), _STICKIES_PER_ROW) * _STICKY_WIDTH
        height = _SECTION_PADDING * 2 + rows * _ROW_HEIGHT

        plan.append({
            "key": key,
            "title": _SECTION_TITLES[key],
            "sticky_color": _SECTION_COLORS[key],
            "fill_color": _SECTION_FILL_HEX[key],
            "x": column_x,
            "y": 0,
            "width": width,
            "height": height,
            "items": texts,
        })
        column_x += _COLUMN_WIDTH

    return plan


async def push_layout_to_figjam(analysis: dict[str, Any]) -> dict[str, Any]:
    """Creates a real FigJam section per group, with a grid of stickies inside
    it, on the connected board. Returns a summary for the Agent Activity log."""
    plan = build_layout_plan(analysis)
    if not plan:
        raise ValueError("Nothing to push: run analysis first, there are no themes/insights/etc. yet.")

    activity: list[str] = []
    created_stickies = 0

    async with mcp_client.session() as sess:
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
                    "x": section["x"] + _SECTION_PADDING + (i % _STICKIES_PER_ROW) * _STICKY_WIDTH,
                    "y": section["y"] + _SECTION_PADDING + (i // _STICKIES_PER_ROW) * _ROW_HEIGHT,
                    "color": section["sticky_color"],
                }
                for i, text in enumerate(section["items"])
            ]
            await mcp_client.create_stickies(sess, stickies)
            created_stickies += len(stickies)
            activity.append(f"Created {len(stickies)} sticky note(s) in '{section['title']}'")

    return {
        "sections": [s["title"] for s in plan],
        "stickies_created": created_stickies,
        "activity": activity,
    }
