"""Turns ResearchMate's persona-synthesis output into a FigJam layout and
pushes it via figma_mcp_client - the same MCP client figma_layout.py already
uses for Themes/Insights/etc, extended with one more real tool discovered
live on the connected server: figjam_create_shape_with_text (a labeled,
custom-sized, custom-colored shape). Personas are built from this, NOT
figjam_create_stickies, per the explicit "persona = card, not sticky note"
requirement - a sticky note is a fixed 240x240 square (confirmed live,
width/height params are silently ignored), which can't hold a structured
multi-zone card layout at all.

Persona card = a left "identity" sidebar (name, description, profile - dark
accent fill, white text) spanning the card's full height, next to a
right-hand main content area (Quote, Goals, Pain points, Behaviours, Needs,
Motivations, Evidence) in restrained near-white zones - the one strong
accent color carries the hierarchy instead of a different pastel per zone,
matching professional persona-card references (identity panel + neutral
content) rather than a rainbow of category colors.

All cards live inside one real FigJam section titled "User personas",
positioned dynamically clear of EVERY node already on the connected board -
not just other ResearchMate sections, but the original primary-research
stickies too (read live before pushing - see
_find_existing_content_right_edge), never at a hardcoded coordinate.
"""

from __future__ import annotations

from typing import Any

from . import figma_mcp_client as mcp_client
from .layout_geometry import Rect, assert_no_overlaps, bounding_box, find_overlap

_NOT_IDENTIFIED = "Not identified in research"

# Card geometry. Two fixed columns per row, matching the exact layouts asked
# for (2 personas side by side, 3 as 2+1, 4 as 2x2) rather than a
# width-adaptive column count - simpler, predictable, and matches every
# example given.
CARD_WIDTH = 680
SIDEBAR_WIDTH = 220
CARD_PADDING = 24
COLUMN_GAP = 20
MAIN_AREA_WIDTH = CARD_WIDTH - CARD_PADDING * 2 - COLUMN_GAP - SIDEBAR_WIDTH
COLUMN_WIDTH = (MAIN_AREA_WIDTH - COLUMN_GAP) // 2
ROW_GAP = 16
CARDS_PER_ROW = 2
CARD_GAP_X = 60
CARD_GAP_Y = 60
SECTION_PADDING = 48
SECTION_GAP = 120  # clearance kept between existing board content and the new Personas section

_LINE_HEIGHT = 20
_ZONE_LABEL_HEIGHT = 24
_ZONE_PADDING = 16
_MIN_ZONE_HEIGHT = 80
_QUOTE_HEIGHT = 110
_EVIDENCE_HEIGHT = 60

# One strong accent (the sidebar) carries the hierarchy; every content zone
# stays a near-neutral off-white so the card reads as "restrained UX board",
# not "a different pastel per category" - reusing the product's own accent
# green (style.css's --accent/--accent-strong) rather than inventing a new
# persona-only color scheme.
_SIDEBAR_COLOR = "#1F6F4A"
_SIDEBAR_TEXT_COLOR = "#FFFFFF"
_ZONE_COLOR = "#FAFAFA"
_EVIDENCE_COLOR = "#F1F1F3"
_CARD_BACKGROUND_COLOR = "#FFFFFF"

_SIDEBAR_FONT_SIZE = 13
_ZONE_FONT_SIZE = 12
_QUOTE_FONT_SIZE = 13

_PERSONAS_SECTION_TITLE = "User personas"


def _zone_height(line_count: int) -> int:
    return max(_MIN_ZONE_HEIGHT, _ZONE_PADDING * 2 + _ZONE_LABEL_HEIGHT + line_count * _LINE_HEIGHT)


def _zone_text(label: str, lines: list[str]) -> str:
    body = "\n".join(f"- {line}" for line in (lines or [_NOT_IDENTIFIED]))
    return f"{label.upper()}\n{body}"


def _sidebar_text(persona: dict[str, Any]) -> str:
    profile = persona.get("profile") or {}
    lines = [
        persona.get("name", "Unnamed persona"),
        "",
        persona.get("short_description", ""),
        "",
        f"Role: {profile.get('role') or _NOT_IDENTIFIED}",
        f"Age: {profile.get('age') or _NOT_IDENTIFIED}",
        f"Location: {profile.get('location') or _NOT_IDENTIFIED}",
        f"Digital behaviour: {profile.get('digital_behaviour') or _NOT_IDENTIFIED}",
    ]
    return "\n".join(lines)


def _sidebar_line_count(persona: dict[str, Any]) -> int:
    # name + blank + description + blank + 4 profile lines = 8, plus extra
    # lines if the description wraps beyond the width estimate below.
    description = persona.get("short_description", "")
    wrapped_lines = max(1, -(-len(description) // 28))  # ~28 chars/line at this width/font size
    return 4 + wrapped_lines + 4


def _quote_text(quote: dict[str, Any]) -> str:
    text = (quote or {}).get("text", "").strip()
    if not text:
        return "“ No representative quote identified in research. ”"
    if quote.get("is_verbatim"):
        return f'“ {text} ”\n— {quote.get("source_id", "")}'
    return f'“ {text} ”\n(synthesized statement, not a direct quote)'


def _build_card(persona: dict[str, Any], x: float, y: float) -> dict[str, Any]:
    """Returns {"x", "y", "width", "height", "shapes": [...]}. `shapes` is
    ordered background-first so later (foreground) shapes are created after
    it - FigJam stacks newly-created nodes above existing ones, so creation
    order doubles as z-order here.

    Layout: a left "identity" sidebar (name, description, profile - one
    strong accent color, white text) spans the card's full height next to a
    right-hand main content area (Quote, Goals/Pain points, Behaviours/Needs,
    Motivations, Evidence) in restrained near-white zones."""
    goals = persona.get("goals") or []
    pain_points = persona.get("pain_points") or []
    behaviours = persona.get("behaviours") or []
    needs = persona.get("needs") or []
    motivations = persona.get("motivations") or []

    row1_height = max(_zone_height(len(goals) or 1), _zone_height(len(pain_points) or 1))
    row2_height = max(_zone_height(len(behaviours) or 1), _zone_height(len(needs) or 1))
    motivations_height = _zone_height(len(motivations) or 1)

    main_content_height = (
        _QUOTE_HEIGHT + ROW_GAP + row1_height + ROW_GAP + row2_height + ROW_GAP
        + motivations_height + ROW_GAP + _EVIDENCE_HEIGHT
    )
    sidebar_height = max(main_content_height, _ZONE_PADDING * 2 + _sidebar_line_count(persona) * _LINE_HEIGHT)
    card_height = CARD_PADDING * 2 + max(main_content_height, sidebar_height)

    shapes = [{
        "text": "", "x": x, "y": y, "width": CARD_WIDTH, "height": card_height,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _CARD_BACKGROUND_COLOR,
    }]

    left_x = x + CARD_PADDING
    right_x = left_x + SIDEBAR_WIDTH + COLUMN_GAP
    right_col_x = right_x + COLUMN_WIDTH + COLUMN_GAP

    shapes.append({
        "text": _sidebar_text(persona), "x": left_x, "y": y + CARD_PADDING,
        "width": SIDEBAR_WIDTH, "height": card_height - CARD_PADDING * 2,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _SIDEBAR_COLOR,
        "textColor": _SIDEBAR_TEXT_COLOR, "fontSize": _SIDEBAR_FONT_SIZE,
    })

    cursor_y = y + CARD_PADDING
    shapes.append({
        "text": _quote_text(persona.get("representative_quote") or {}),
        "x": right_x, "y": cursor_y, "width": MAIN_AREA_WIDTH, "height": _QUOTE_HEIGHT,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _ZONE_COLOR, "fontSize": _QUOTE_FONT_SIZE,
    })
    cursor_y += _QUOTE_HEIGHT + ROW_GAP

    shapes.append({
        "text": _zone_text("Goals", goals), "x": right_x, "y": cursor_y,
        "width": COLUMN_WIDTH, "height": row1_height,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _ZONE_COLOR, "fontSize": _ZONE_FONT_SIZE,
    })
    shapes.append({
        "text": _zone_text("Pain points", pain_points), "x": right_col_x, "y": cursor_y,
        "width": COLUMN_WIDTH, "height": row1_height,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _ZONE_COLOR, "fontSize": _ZONE_FONT_SIZE,
    })
    cursor_y += row1_height + ROW_GAP

    shapes.append({
        "text": _zone_text("Behaviours", behaviours), "x": right_x, "y": cursor_y,
        "width": COLUMN_WIDTH, "height": row2_height,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _ZONE_COLOR, "fontSize": _ZONE_FONT_SIZE,
    })
    shapes.append({
        "text": _zone_text("Needs", needs), "x": right_col_x, "y": cursor_y,
        "width": COLUMN_WIDTH, "height": row2_height,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _ZONE_COLOR, "fontSize": _ZONE_FONT_SIZE,
    })
    cursor_y += row2_height + ROW_GAP

    shapes.append({
        "text": _zone_text("Motivations", motivations), "x": right_x, "y": cursor_y,
        "width": MAIN_AREA_WIDTH, "height": motivations_height,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _ZONE_COLOR, "fontSize": _ZONE_FONT_SIZE,
    })
    cursor_y += motivations_height + ROW_GAP

    evidence = persona.get("evidence") or []
    shapes.append({
        "text": "RESEARCH EVIDENCE\n" + (", ".join(evidence) if evidence else "none"),
        "x": right_x, "y": cursor_y, "width": MAIN_AREA_WIDTH, "height": _EVIDENCE_HEIGHT,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _EVIDENCE_COLOR, "fontSize": _ZONE_FONT_SIZE,
    })

    return {"x": x, "y": y, "width": CARD_WIDTH, "height": card_height, "shapes": shapes}


def build_persona_layout_plan(personas: list[dict[str, Any]], start_x: float = 0, start_y: float = 0) -> dict[str, Any]:
    """Returns {"section": {title, x, y, width, height}, "cards": [...]}.
    Cards are arranged in a fixed 2-column grid (row-major), each row's
    height set by its tallest card so both cards in a row still line up,
    even though card height varies with how much content each persona has."""
    if not personas:
        return {"section": None, "cards": []}

    rows: list[list[dict[str, Any]]] = [
        personas[i:i + CARDS_PER_ROW] for i in range(0, len(personas), CARDS_PER_ROW)
    ]

    cards: list[dict[str, Any]] = []
    cursor_y = start_y + SECTION_PADDING
    max_row_width = 0.0

    for row in rows:
        row_cards = []
        cursor_x = start_x + SECTION_PADDING
        for persona in row:
            row_cards.append(_build_card(persona, cursor_x, cursor_y))
            cursor_x += CARD_WIDTH + CARD_GAP_X
        row_height = max(c["height"] for c in row_cards)
        max_row_width = max(max_row_width, cursor_x - CARD_GAP_X - start_x)
        cards.extend(row_cards)
        cursor_y += row_height + CARD_GAP_Y

    section = {
        "title": _PERSONAS_SECTION_TITLE,
        "x": start_x,
        "y": start_y,
        "width": max_row_width + SECTION_PADDING,
        "height": cursor_y - CARD_GAP_Y + SECTION_PADDING - start_y,
    }
    return {"section": section, "cards": cards}


def _find_existing_content_right_edge(board_data: dict[str, Any]) -> float:
    """Rightmost edge of EVERY node currently on the board - not just
    ResearchMate's own sections. Confirmed live: the real primary-research
    stickies (P1-P6) sit loose on the page, not inside any section, so
    checking only reserved section names missed them entirely - a Personas
    section placed at x=0 would only avoid overlapping Themes/Insights,
    not the original research notes themselves.

    Placing every new element strictly to the right of this value (plus a
    gap) guarantees zero overlap regardless of any existing node's y
    position: two rects with disjoint x-ranges can never overlap in 2D,
    however different their vertical placement is."""
    max_right = 0.0
    for node in board_data.get("nodes", []):
        right = node.get("x", 0) + node.get("width", 0)
        max_right = max(max_right, right)
    return max_right


def _validate_layout(plan: dict[str, Any]) -> None:
    if not plan["cards"]:
        return

    card_rects = [Rect(c["x"], c["y"], c["width"], c["height"]) for c in plan["cards"]]
    assert_no_overlaps(card_rects, margin=CARD_GAP_X / 2, label="persona cards")

    for card in plan["cards"]:
        # The first shape is the card's own background - every other zone is
        # deliberately layered on top of it, so it's excluded from this
        # check; only the foreground zones must not overlap EACH OTHER.
        zone_rects = [Rect(s["x"], s["y"], s["width"], s["height"]) for s in card["shapes"][1:]]
        collision = find_overlap(zone_rects)
        if collision is not None:
            raise ValueError(f"persona card layout bug: zones {collision} overlap within a card")

    section = plan["section"]
    bbox = bounding_box(card_rects)
    if bbox is not None and (
        bbox.x < section["x"] or bbox.y < section["y"]
        or bbox.right > section["x"] + section["width"]
        or bbox.bottom > section["y"] + section["height"]
    ):
        raise ValueError("persona card layout bug: a card falls outside its own section's bounds")


async def push_personas_to_figjam(personas: list[dict[str, Any]]) -> dict[str, Any]:
    """Creates one real FigJam section containing every persona card, placed
    clear of whatever synthesis sections already exist on the connected
    board. Cards are built from figjam_create_shape_with_text (real,
    editable shapes), never figjam_create_stickies."""
    if not personas:
        raise ValueError("Nothing to push: generate personas first, there are none yet.")

    activity: list[str] = []
    created_shapes = 0

    async with mcp_client.session() as sess:
        await mcp_client.wait_for_bridge(sess)
        activity.append("Connected to Figma Desktop Bridge")

        board_data = await mcp_client.get_board_contents(sess)
        existing_right_edge = _find_existing_content_right_edge(board_data)
        start_x = existing_right_edge + SECTION_GAP if existing_right_edge > 0 else 0
        activity.append(
            f"Reserved space for the Personas section clear of existing content (x >= {start_x:.0f}px)"
            if existing_right_edge > 0 else "No existing synthesis content found; starting a fresh layout"
        )

        plan = build_persona_layout_plan(personas, start_x=start_x)
        _validate_layout(plan)

        section = plan["section"]
        await mcp_client.create_section(
            sess, name=section["title"], x=section["x"], y=section["y"],
            width=section["width"], height=section["height"],
        )
        activity.append(f"Created section '{section['title']}'")

        for i, card in enumerate(plan["cards"]):
            persona_name = personas[i].get("name", "Unnamed persona")
            for shape in card["shapes"]:
                await mcp_client.create_shape_with_text(sess, **shape)
                created_shapes += 1
            activity.append(f"Created persona card '{persona_name}' ({len(card['shapes'])} elements)")

    return {
        "personas": [p.get("name", "Unnamed persona") for p in personas],
        "elements_created": created_shapes,
        "activity": activity,
    }
