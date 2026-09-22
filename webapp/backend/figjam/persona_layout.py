"""Turns ResearchMate's persona-synthesis output into a FigJam layout and
pushes it via figma_mcp_client, the same MCP client and
figjam_create_section / figjam_create_stickies tools already used by
figma_layout.py for Themes/Insights/Contradictions. Extends that
architecture rather than duplicating it: no new FigJam connection, no new
MCP client, only a persona-shaped layout plan built from the same two write
primitives.

Persona card layout (per persona, one FigJam section = one card):

  HEADER (name + short description)
  PROFILE (role / age / location / digital behaviour)
  GOALS          | PAIN POINTS   (two columns)
  BEHAVIOURS     | NEEDS         (two columns)
  MOTIVATIONS
  REPRESENTATIVE QUOTE
  RESEARCH EVIDENCE

Cards are placed left to right with a fixed gap, matching the ASCII layout
the capstone spec asked for ("arrange horizontally... not stacked
randomly"), not a random scatter of stickies.
"""

from __future__ import annotations

from typing import Any

from . import figma_mcp_client as mcp_client

_CARD_WIDTH = 640
_CARD_GAP = 80
_PADDING = 32
_COLUMN_WIDTH = 260
_COLUMN_GAP = _CARD_WIDTH - _PADDING * 2 - _COLUMN_WIDTH * 2
_BULLET_HEIGHT = 90
_HEADER_HEIGHT = 130
_PROFILE_HEIGHT = 90
_MOTIVATIONS_ROW_HEIGHT = 90
_QUOTE_HEIGHT = 130
_EVIDENCE_HEIGHT = 70
_BLOCK_GAP = 24

_HEADER_COLOR = "LIGHT_GRAY"
_PROFILE_COLOR = "GRAY"
_GOALS_COLOR = "GREEN"
_PAIN_POINTS_COLOR = "RED"
_BEHAVIOURS_COLOR = "BLUE"
_NEEDS_COLOR = "PURPLE"
_MOTIVATIONS_COLOR = "ORANGE"
_QUOTE_COLOR = "YELLOW"
_EVIDENCE_COLOR = "PINK"

_NOT_IDENTIFIED = "Not identified in research"


def _profile_line(profile: dict[str, Any]) -> str:
    parts = []
    for label, key in (("Role", "role"), ("Age", "age"), ("Location", "location"), ("Digital behaviour", "digital_behaviour")):
        value = profile.get(key) or _NOT_IDENTIFIED
        parts.append(f"{label}: {value}")
    return "\n".join(parts)


def _quote_text(quote: dict[str, Any]) -> str:
    text = quote.get("text", "").strip()
    if not text:
        return '"No representative quote identified in research."'
    if quote.get("is_verbatim"):
        return f'"{text}"\n— {quote.get("source_id", "")}'
    return f'"{text}"\n(synthesized statement, not a direct quote)'


def _two_column_block(
    left_items: list[str], left_label: str, left_color: str,
    right_items: list[str], right_label: str, right_color: str,
    x: float, y: float,
) -> tuple[list[dict[str, Any]], float]:
    """Returns (stickies, block_height). Each column is its own list of
    bullet stickies stacked vertically; the block height is the taller of
    the two columns so both columns stay visually aligned under the section
    even when one list has more items than the other."""
    stickies: list[dict[str, Any]] = []

    left_x = x
    right_x = x + _COLUMN_WIDTH + _COLUMN_GAP

    stickies.append({"text": left_label.upper(), "x": left_x, "y": y, "color": left_color})
    stickies.append({"text": right_label.upper(), "x": right_x, "y": y, "color": right_color})
    label_height = 40

    for i, text in enumerate(left_items or [_NOT_IDENTIFIED]):
        stickies.append({"text": text, "x": left_x, "y": y + label_height + i * _BULLET_HEIGHT, "color": left_color})
    for i, text in enumerate(right_items or [_NOT_IDENTIFIED]):
        stickies.append({"text": text, "x": right_x, "y": y + label_height + i * _BULLET_HEIGHT, "color": right_color})

    rows = max(len(left_items) or 1, len(right_items) or 1)
    block_height = label_height + rows * _BULLET_HEIGHT
    return stickies, block_height


def build_persona_layout_plan(personas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Returns a list of card plans: [{persona_id, title, x, y, width, height, stickies}]."""
    plan = []
    card_x = 0

    for persona in personas:
        stickies: list[dict[str, Any]] = []
        cursor_y = _PADDING

        stickies.append({
            "text": f"{persona.get('name', 'Unnamed persona')}\n\n{persona.get('short_description', '')}",
            "x": _PADDING, "y": cursor_y, "color": _HEADER_COLOR,
        })
        cursor_y += _HEADER_HEIGHT + _BLOCK_GAP

        stickies.append({"text": _profile_line(persona.get("profile", {})), "x": _PADDING, "y": cursor_y, "color": _PROFILE_COLOR})
        cursor_y += _PROFILE_HEIGHT + _BLOCK_GAP

        block, height = _two_column_block(
            persona.get("goals", []), "Goals", _GOALS_COLOR,
            persona.get("pain_points", []), "Pain points", _PAIN_POINTS_COLOR,
            _PADDING, cursor_y,
        )
        stickies.extend(block)
        cursor_y += height + _BLOCK_GAP

        block, height = _two_column_block(
            persona.get("behaviours", []), "Behaviours", _BEHAVIOURS_COLOR,
            persona.get("needs", []), "Needs", _NEEDS_COLOR,
            _PADDING, cursor_y,
        )
        stickies.extend(block)
        cursor_y += height + _BLOCK_GAP

        motivations = persona.get("motivations") or [_NOT_IDENTIFIED]
        stickies.append({"text": "MOTIVATIONS", "x": _PADDING, "y": cursor_y, "color": _MOTIVATIONS_COLOR})
        stickies.append({"text": "\n".join(f"- {m}" for m in motivations), "x": _PADDING + _COLUMN_WIDTH + _COLUMN_GAP, "y": cursor_y, "color": _MOTIVATIONS_COLOR})
        cursor_y += _MOTIVATIONS_ROW_HEIGHT + _BLOCK_GAP

        stickies.append({"text": _quote_text(persona.get("representative_quote", {})), "x": _PADDING, "y": cursor_y, "color": _QUOTE_COLOR})
        cursor_y += _QUOTE_HEIGHT + _BLOCK_GAP

        evidence = persona.get("evidence") or []
        stickies.append({
            "text": "RESEARCH EVIDENCE\n" + (", ".join(evidence) if evidence else "none"),
            "x": _PADDING, "y": cursor_y, "color": _EVIDENCE_COLOR,
        })
        cursor_y += _EVIDENCE_HEIGHT + _PADDING

        for sticky in stickies:
            sticky["x"] += card_x

        plan.append({
            "persona_id": persona.get("id"),
            "title": f"Persona: {persona.get('name', 'Unnamed persona')}",
            "x": card_x,
            "y": 0,
            "width": _CARD_WIDTH,
            "height": cursor_y,
            "stickies": stickies,
        })
        card_x += _CARD_WIDTH + _CARD_GAP

    return plan


async def push_personas_to_figjam(personas: list[dict[str, Any]]) -> dict[str, Any]:
    """Creates one real FigJam section per persona, laid out as a structured
    card (not a scatter of stickies), on the connected board."""
    plan = build_persona_layout_plan(personas)
    if not plan:
        raise ValueError("Nothing to push: generate personas first, there are none yet.")

    activity: list[str] = []
    created_stickies = 0

    async with mcp_client.session() as sess:
        await mcp_client.wait_for_bridge(sess)
        activity.append("Connected to Figma Desktop Bridge")

        for card in plan:
            await mcp_client.create_section(
                sess, name=card["title"], x=card["x"], y=card["y"],
                width=card["width"], height=card["height"],
            )
            activity.append(f"Created persona card '{card['title']}'")

            await mcp_client.create_stickies(sess, card["stickies"])
            created_stickies += len(card["stickies"])
            activity.append(f"Laid out {len(card['stickies'])} element(s) for '{card['title']}'")

    return {
        "personas": [c["title"] for c in plan],
        "stickies_created": created_stickies,
        "activity": activity,
    }
