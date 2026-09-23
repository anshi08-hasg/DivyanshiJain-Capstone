"""Turns ResearchMate's persona-synthesis output into a FigJam layout and
pushes it via figma_mcp_client - the same MCP client figma_layout.py already
uses for Themes/Insights/etc, extended with figjam_create_shape_with_text
(a labeled, custom-sized, custom-colored shape, discovered live via
list_tools()). Personas are built from this, NEVER figjam_create_stickies
(a fixed 240x240 sticky note, confirmed live - width/height are ignored).

LOCKED TEMPLATE: every persona card uses the exact same 1200x660 canvas,
the same column widths, the same element positions, and the same
typography, regardless of how much content a given persona has. Only the
CONTENT varies (per explicit instruction: "the layout does NOT adapt to
the content" - content is summarized/truncated to fit the fixed template
instead of the template growing to fit the content). See PERSONA_TEMPLATE
below for the single source of truth for every measurement.

All cards live inside one real FigJam section titled "User personas",
positioned dynamically clear of EVERY node already on the connected board
(read live before pushing - see _find_existing_content_right_edge), never
at a hardcoded coordinate.
"""

from __future__ import annotations

from typing import Any

from . import figma_mcp_client as mcp_client
from .layout_geometry import Rect, assert_no_overlaps, bounding_box, find_overlap

_NOT_IDENTIFIED = "Not identified in research"

# Single source of truth for every persona-card measurement. Fixed per the
# explicit "same template every time" requirement - nothing here is derived
# from how much content a persona happens to have.
PERSONA_TEMPLATE: dict[str, Any] = {
    "width": 1200,
    "height": 660,
    "left_column_width": 420,
    "right_column_width": 780,
    "photo": {"x": 0, "y": 0, "width": 420, "height": 413, "color": "#E8E8E8"},
    "identity_panel": {"x": 0, "y": 413, "width": 420, "height": 247, "color": "#111111"},
    "name": {"x": 34, "y": 480, "width": 352, "height": 44, "font_size": 28},
    "role": {"x": 34, "y": 535, "width": 352, "height": 28, "font_size": 17},
    "right_content": {"x": 420, "y": 0, "width": 780, "height": 660, "padding": 42},
    "quote": {"x": 462, "y": 38, "width": 690, "height": 167, "font_size": 26},
    "divider": {"x": 462, "y": 205, "width": 690, "height": 2, "color": "#D9D9D9"},
    "background_heading": {"x": 462, "y": 215, "width": 690, "height": 24, "font_size": 18},
    "background_body": {"x": 462, "y": 247, "width": 690, "height": 90, "font_size": 15},
    "grid": {"y": 362, "column_width": 205, "gap": 25, "heading_height": 24, "body_height": 190, "font_size_heading": 17, "font_size_body": 14},
    "evidence": {"x": 462, "y": 598, "width": 690, "height": 20, "font_size": 13},
    "gaps": {"persona_to_persona": 80, "section": 25, "bullet": 10},
}

_HEADING_COLOR = "#222222"
_BODY_COLOR = "#333333"
_MUTED_COLOR = "#8A8A8A"
_WHITE = "#FFFFFF"

CARD_WIDTH = PERSONA_TEMPLATE["width"]
CARD_HEIGHT = PERSONA_TEMPLATE["height"]
CARDS_PER_ROW = 2
CARD_GAP_X = PERSONA_TEMPLATE["gaps"]["persona_to_persona"]
CARD_GAP_Y = PERSONA_TEMPLATE["gaps"]["persona_to_persona"]
SECTION_PADDING = 48
SECTION_GAP = 120  # clearance kept between existing board content and the new Personas section

_PERSONAS_SECTION_TITLE = "User personas"


def _truncate(text: str, max_chars: int) -> str:
    """Content is shortened to fit the fixed template rather than resizing
    the template to fit the content, per the explicit "first shorten the
    content intelligently, do NOT shrink font, do NOT change card
    dimensions" rule. Cuts at a word boundary where possible."""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return (cut or text[:max_chars]).rstrip(",.;:") + "…"


def _bulleted(items: list[str], max_items: int, max_chars_each: int) -> str:
    items = [i for i in (items or []) if i and i.strip()][:max_items] or [_NOT_IDENTIFIED]
    return "\n".join(f"• {_truncate(i, max_chars_each)}" for i in items)


def _quote_text(quote: dict[str, Any]) -> str:
    text = (quote or {}).get("text", "").strip()
    if not text:
        return "“ No representative statement identified in research. ”"
    body = _truncate(text, 180)
    if quote.get("is_verbatim"):
        return f"“ {body} ”\n— {quote.get('source_id', '')}"
    return f"“ {body} ”\n(synthesized statement, not a direct quote)"


def _build_card(persona: dict[str, Any], x: float, y: float) -> dict[str, Any]:
    """Returns {"x", "y", "width", "height", "shapes": [...]} using the fixed
    PERSONA_TEMPLATE geometry - x, y is the card's own origin; every element
    below is that origin plus a fixed template offset, never a value derived
    from this persona's own content length."""
    t = PERSONA_TEMPLATE
    shapes: list[dict[str, Any]] = []

    def rect(key: str) -> dict[str, float]:
        spec = t[key]
        return {"x": x + spec["x"], "y": y + spec["y"], "width": spec["width"], "height": spec["height"]}

    # z-order: backgrounds first, then everything layered on top of them.
    right = t["right_content"]
    shapes.append({
        "text": "", "x": x + right["x"], "y": y + right["y"], "width": right["width"], "height": right["height"],
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE, "cornerRadius": 0,
    })

    photo = rect("photo")
    shapes.append({
        "text": "", **photo, "shapeType": "ROUNDED_RECTANGLE",
        "fillColor": t["photo"]["color"], "cornerRadius": 0,
    })

    panel = rect("identity_panel")
    shapes.append({
        "text": "", **panel, "shapeType": "ROUNDED_RECTANGLE",
        "fillColor": t["identity_panel"]["color"], "cornerRadius": 0,
    })

    name_spec = t["name"]
    shapes.append({
        # Confirmed live: figjam_create_shape_with_text clips overflowing
        # text at the shape's width rather than wrapping it, so the char
        # limit must be conservative enough to actually fit one line at
        # this font size within this width, not just "reasonably short".
        "text": _truncate(persona.get("name", "Unnamed persona"), 17),
        "x": x + name_spec["x"], "y": y + name_spec["y"], "width": name_spec["width"], "height": name_spec["height"],
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": t["identity_panel"]["color"],
        "textColor": _WHITE, "fontSize": name_spec["font_size"], "cornerRadius": 0,
    })

    role_spec = t["role"]
    role_text = persona.get("archetype") or persona.get("short_description", "")
    shapes.append({
        "text": _truncate(role_text, 26),
        "x": x + role_spec["x"], "y": y + role_spec["y"], "width": role_spec["width"], "height": role_spec["height"],
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": t["identity_panel"]["color"],
        "textColor": _WHITE, "fontSize": role_spec["font_size"], "cornerRadius": 0,
    })

    quote_spec = t["quote"]
    shapes.append({
        "text": _quote_text(persona.get("representative_quote") or {}),
        "x": x + quote_spec["x"], "y": y + quote_spec["y"], "width": quote_spec["width"], "height": quote_spec["height"],
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE, "fontSize": quote_spec["font_size"], "cornerRadius": 0,
    })

    divider = rect("divider")
    shapes.append({
        "text": "", **divider, "shapeType": "ROUNDED_RECTANGLE",
        "fillColor": t["divider"]["color"], "cornerRadius": 0,
    })

    bg_heading = t["background_heading"]
    shapes.append({
        "text": "BACKGROUND",
        "x": x + bg_heading["x"], "y": y + bg_heading["y"], "width": bg_heading["width"], "height": bg_heading["height"],
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE,
        "textColor": _HEADING_COLOR, "fontSize": bg_heading["font_size"], "cornerRadius": 0,
    })

    bg_body = t["background_body"]
    shapes.append({
        "text": _truncate(persona.get("short_description", ""), 75),
        "x": x + bg_body["x"], "y": y + bg_body["y"], "width": bg_body["width"], "height": bg_body["height"],
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE,
        "textColor": _BODY_COLOR, "fontSize": bg_body["font_size"], "cornerRadius": 0,
    })

    grid = t["grid"]
    needs_and_behaviours = (persona.get("needs") or []) + (persona.get("behaviours") or [])
    columns = [
        ("GOALS", persona.get("goals") or []),
        ("FRUSTRATIONS", persona.get("pain_points") or []),
        ("NEEDS", needs_and_behaviours),
    ]
    for i, (label, items) in enumerate(columns):
        col_x = x + bg_body["x"] + i * (grid["column_width"] + grid["gap"])
        heading_y = y + grid["y"]
        body_y = heading_y + grid["heading_height"] + t["gaps"]["bullet"]
        shapes.append({
            "text": label,
            "x": col_x, "y": heading_y, "width": grid["column_width"], "height": grid["heading_height"],
            "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE,
            "textColor": _HEADING_COLOR, "fontSize": grid["font_size_heading"], "cornerRadius": 0,
        })
        shapes.append({
            "text": _bulleted(items, max_items=3, max_chars_each=32),
            "x": col_x, "y": body_y, "width": grid["column_width"], "height": grid["body_height"],
            "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE,
            "textColor": _BODY_COLOR, "fontSize": grid["font_size_body"], "cornerRadius": 0,
        })

    evidence_spec = t["evidence"]
    evidence = persona.get("evidence") or []
    shapes.append({
        "text": "RESEARCH EVIDENCE: " + (", ".join(evidence) if evidence else "none"),
        "x": x + evidence_spec["x"], "y": y + evidence_spec["y"],
        "width": evidence_spec["width"], "height": evidence_spec["height"],
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE,
        "textColor": _MUTED_COLOR, "fontSize": evidence_spec["font_size"], "cornerRadius": 0,
    })

    return {"x": x, "y": y, "width": CARD_WIDTH, "height": CARD_HEIGHT, "shapes": shapes}


def build_persona_layout_plan(personas: list[dict[str, Any]], start_x: float = 0, start_y: float = 0) -> dict[str, Any]:
    """Returns {"section": {title, x, y, width, height}, "cards": [...]}.
    Every card is exactly CARD_WIDTH x CARD_HEIGHT (the fixed template) -
    row height is simply CARD_HEIGHT, never computed from content, since
    content no longer affects card size at all."""
    if not personas:
        return {"section": None, "cards": []}

    rows: list[list[dict[str, Any]]] = [
        personas[i:i + CARDS_PER_ROW] for i in range(0, len(personas), CARDS_PER_ROW)
    ]

    cards: list[dict[str, Any]] = []
    cursor_y = start_y + SECTION_PADDING
    max_row_width = 0.0

    for row in rows:
        cursor_x = start_x + SECTION_PADDING
        for persona in row:
            cards.append(_build_card(persona, cursor_x, cursor_y))
            cursor_x += CARD_WIDTH + CARD_GAP_X
        max_row_width = max(max_row_width, cursor_x - CARD_GAP_X - start_x)
        cursor_y += CARD_HEIGHT + CARD_GAP_Y

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
        assert card["width"] == CARD_WIDTH and card["height"] == CARD_HEIGHT, \
            "every persona card must use the exact same fixed template dimensions"
        # The first shape (right-content background) and the photo/identity
        # panel are deliberately layered under other shapes on purpose -
        # only shapes sharing the SAME background color are exempt from the
        # "must not overlap" check, since those are intentional backgrounds
        # with foreground text/dividers placed on top of them by design.
        foreground = [s for s in card["shapes"] if s["text"]]
        zone_rects = [Rect(s["x"], s["y"], s["width"], s["height"]) for s in foreground]
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
    clear of whatever content already exists on the connected board. Cards
    are built from figjam_create_shape_with_text (real, editable shapes),
    never figjam_create_stickies, using the fixed PERSONA_TEMPLATE geometry
    for every persona regardless of content amount."""
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
            if existing_right_edge > 0 else "No existing content found; starting a fresh layout"
        )

        plan = build_persona_layout_plan(personas, start_x=start_x)
        _validate_layout(plan)

        section = plan["section"]
        await mcp_client.create_section(
            sess, name=section["title"], x=section["x"], y=section["y"],
            width=section["width"], height=section["height"],
        )
        activity.append(f"Created section '{section['title']}'")

        created_node_ids: list[str] = []
        for i, card in enumerate(plan["cards"]):
            persona_name = personas[i].get("name", "Unnamed persona")
            for shape in card["shapes"]:
                result = await mcp_client.create_shape_with_text(sess, **shape)
                if result.get("node_id"):
                    created_node_ids.append(result["node_id"])
                created_shapes += 1
            activity.append(f"Created persona card '{persona_name}' ({len(card['shapes'])} elements)")

        # figjam_create_shape_with_text's cornerRadius param is silently
        # ignored, and every shape carries a visible default stroke
        # (confirmed live); fix both on every shape just created via the
        # real plugin API instead, one batched call.
        if created_node_ids:
            await mcp_client.apply_card_finish(sess, created_node_ids)
            activity.append(f"Applied sharp corners and removed default strokes on {len(created_node_ids)} element(s)")

    return {
        "personas": [p.get("name", "Unnamed persona") for p in personas],
        "elements_created": created_shapes,
        "activity": activity,
    }
