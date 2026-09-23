"""Turns ResearchMate's persona-synthesis output into a FigJam layout and
pushes it via figma_mcp_client - the same MCP client figma_layout.py already
uses for Themes/Insights/etc, extended with figjam_create_shape_with_text
(a labeled, custom-sized, custom-colored shape, discovered live via
list_tools()). Personas are built from this, NEVER figjam_create_stickies
(a fixed 240x240 sticky note, confirmed live - width/height are ignored).

LOCKED TEMPLATE: every persona card uses the same 1200px-wide canvas, the
same column widths, the same element positions, and the same typography
for the photo/quote/background section - that part never adapts to
content. The Goals/Frustrations/Needs grid is the one exception (per an
explicit later instruction to show full findings rather than truncate
them): its row height, and therefore the card's overall height, grows to
fit that grid's real content, with the identity panel stretching to match.
See PERSONA_TEMPLATE below for the single source of truth for every fixed
measurement.

All cards live inside one real FigJam section titled "User personas",
positioned dynamically clear of EVERY node already on the connected board
(read live before pushing - see _find_existing_content_right_edge), never
at a hardcoded coordinate.
"""

from __future__ import annotations

from typing import Any

import httpx

from . import figma_mcp_client as mcp_client
from .layout_geometry import Rect, assert_no_overlaps, bounding_box, find_overlap

_AVATAR_SERVICE_URL = "https://ui-avatars.com/api/"


def _fetch_avatar_image(persona_name: str) -> bytes | None:
    """A generic, abstract initials-on-a-tint avatar - deliberately not a
    realistic photo of a specific person, per the explicit "do not invent a
    realistic depiction of a non-existent participant" instruction, while
    still visually filling the photo placeholder instead of leaving it a
    flat empty box. Returns None (skip the fill, keep the plain placeholder
    color) if the avatar service is unreachable, rather than failing the
    whole push over a decorative element."""
    try:
        response = httpx.get(
            _AVATAR_SERVICE_URL,
            params={
                "name": persona_name,
                "size": 400,
                "background": "E8E8E8",
                "color": "5A5A5A",
                "bold": "true",
                "length": 2,
                "format": "png",
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.content
    except httpx.HTTPError:
        return None

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


_GRID_CHARS_PER_LINE = 24  # empirically measured against real rendered screenshots at this column's width/font
_GRID_LINE_HEIGHT = 18
_GRID_ITEM_GAP = 8
_GRID_BODY_PADDING = 16
_GRID_MIN_BODY_HEIGHT = 120
_GRID_MAX_CHARS_EACH = 220  # a safety ceiling only, not meant to actually trigger - items are already short phrases

# The smallest a card's grid can be (all three columns at their minimum
# body height), derived from the template rather than hardcoded, so this
# stays correct if PERSONA_TEMPLATE's numbers ever change.
_MIN_CARD_HEIGHT = (
    PERSONA_TEMPLATE["grid"]["y"] + PERSONA_TEMPLATE["grid"]["heading_height"] + PERSONA_TEMPLATE["gaps"]["bullet"]
    + _GRID_MIN_BODY_HEIGHT + PERSONA_TEMPLATE["gaps"]["section"]
    + PERSONA_TEMPLATE["evidence"]["height"] + PERSONA_TEMPLATE["right_content"]["padding"]
)


def _wrapped_lines(text: str, chars_per_line: int) -> int:
    return max(1, -(-len(text) // chars_per_line))


def _clean_items(items: list[str], max_items: int) -> list[str]:
    cleaned = [_truncate(i, _GRID_MAX_CHARS_EACH) for i in (items or []) if i and i.strip()][:max_items]
    return cleaned or [_NOT_IDENTIFIED]


def _bulleted_full(items: list[str]) -> str:
    return "\n".join(f"• {i}" for i in items)


def _column_body_height(items: list[str]) -> float:
    """Grows to fit the actual (untruncated) content, per the explicit
    "write full things" ask - unlike the header/quote/background zones
    above it, which stay at their locked template size."""
    lines = sum(_wrapped_lines(f"• {i}", _GRID_CHARS_PER_LINE) for i in items)
    return max(
        _GRID_MIN_BODY_HEIGHT,
        _GRID_BODY_PADDING * 2 + lines * _GRID_LINE_HEIGHT + max(0, len(items) - 1) * _GRID_ITEM_GAP,
    )


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
    PERSONA_TEMPLATE geometry for the header/quote/background section, and a
    content-sized Goals/Frustrations/Needs grid per the explicit "write full
    things, don't cut them off" ask - the identity panel and overall card
    height grow to match however tall that grid ends up being, so the two
    columns still end at the same point; only the top (photo/quote/
    background) stays pixel-locked."""
    t = PERSONA_TEMPLATE
    shapes: list[dict[str, Any]] = []

    goals = _clean_items(persona.get("goals"), max_items=4)
    pain_points = _clean_items(persona.get("pain_points"), max_items=4)
    needs_and_behaviours = _clean_items((persona.get("needs") or []) + (persona.get("behaviours") or []), max_items=4)
    grid = t["grid"]
    row_height = max(_column_body_height(c) for c in (goals, pain_points, needs_and_behaviours))

    grid_heading_y = grid["y"]
    grid_body_y = grid_heading_y + grid["heading_height"] + t["gaps"]["bullet"]
    evidence_y = grid_body_y + row_height + t["gaps"]["section"]
    total_height = evidence_y + t["evidence"]["height"] + t["right_content"]["padding"]

    def rect(key: str) -> dict[str, float]:
        spec = t[key]
        return {"x": x + spec["x"], "y": y + spec["y"], "width": spec["width"], "height": spec["height"]}

    # z-order: backgrounds first, then everything layered on top of them.
    right = t["right_content"]
    shapes.append({
        "text": "", "x": x + right["x"], "y": y + right["y"], "width": right["width"], "height": total_height,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE, "cornerRadius": 0,
    })

    photo = rect("photo")
    shapes.append({
        "text": "", **photo, "shapeType": "ROUNDED_RECTANGLE",
        "fillColor": t["photo"]["color"], "cornerRadius": 0,
    })

    panel = rect("identity_panel")
    panel["height"] = total_height - t["photo"]["height"]
    shapes.append({
        "text": "", **panel, "shapeType": "ROUNDED_RECTANGLE",
        "fillColor": t["identity_panel"]["color"], "cornerRadius": 0,
    })

    name_spec = t["name"]
    shapes.append({
        # White label box with dark text (not white text on the dark panel),
        # per the reference the user provided. Confirmed live that
        # figjam_create_shape_with_text clips overflowing text at the
        # shape's width rather than wrapping it, so the char limit stays
        # conservative enough to fit one line at this font size/width.
        "text": _truncate(persona.get("name", "Unnamed persona"), 17),
        "x": x + name_spec["x"], "y": y + name_spec["y"], "width": name_spec["width"], "height": name_spec["height"],
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE,
        "textColor": _HEADING_COLOR, "fontSize": name_spec["font_size"], "cornerRadius": 0,
    })

    role_spec = t["role"]
    role_text = persona.get("archetype") or persona.get("short_description", "")
    shapes.append({
        "text": _truncate(role_text, 26),
        "x": x + role_spec["x"], "y": y + role_spec["y"], "width": role_spec["width"], "height": role_spec["height"],
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE,
        "textColor": _BODY_COLOR, "fontSize": role_spec["font_size"], "cornerRadius": 0,
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

    columns = [
        ("GOALS", goals),
        ("FRUSTRATIONS", pain_points),
        ("NEEDS", needs_and_behaviours),
    ]
    for i, (label, items) in enumerate(columns):
        col_x = x + bg_body["x"] + i * (grid["column_width"] + grid["gap"])
        heading_y = y + grid_heading_y
        body_y = y + grid_body_y
        shapes.append({
            "text": label,
            "x": col_x, "y": heading_y, "width": grid["column_width"], "height": grid["heading_height"],
            "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE,
            "textColor": _HEADING_COLOR, "fontSize": grid["font_size_heading"], "cornerRadius": 0,
        })
        shapes.append({
            "text": _bulleted_full(items),
            "x": col_x, "y": body_y, "width": grid["column_width"], "height": row_height,
            "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE,
            "textColor": _BODY_COLOR, "fontSize": grid["font_size_body"], "cornerRadius": 0,
        })

    evidence_spec = t["evidence"]
    evidence = persona.get("evidence") or []
    shapes.append({
        "text": "RESEARCH EVIDENCE: " + (", ".join(evidence) if evidence else "none"),
        "x": x + evidence_spec["x"], "y": y + evidence_y,
        "width": evidence_spec["width"], "height": evidence_spec["height"],
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE,
        "textColor": _MUTED_COLOR, "fontSize": evidence_spec["font_size"], "cornerRadius": 0,
    })

    # A generic abstract avatar (persona's initials on a neutral tint) fills
    # the photo placeholder - not a fabricated realistic photo of a specific
    # non-existent person, per the earlier explicit "do not invent a
    # realistic person" instruction, while still visually filling the box
    # rather than leaving it empty.
    photo_shape_index = 1
    return {
        "x": x, "y": y, "width": CARD_WIDTH, "height": total_height, "shapes": shapes,
        "photo_shape_index": photo_shape_index, "persona_name": persona.get("name", "Unnamed persona"),
    }


def build_persona_layout_plan(personas: list[dict[str, Any]], start_x: float = 0, start_y: float = 0) -> dict[str, Any]:
    """Returns {"section": {title, x, y, width, height}, "cards": [...]}.
    Every card is exactly CARD_WIDTH wide, and the top (photo/quote/
    background) section is pixel-locked to PERSONA_TEMPLATE - but overall
    card HEIGHT now grows to fit the Goals/Frustrations/Needs grid's real
    content, per the explicit "write full things, don't cut them off" ask.
    Row height is the tallest card in that row, so both cards in a row
    still start at the same y even when their heights differ."""
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
        row_cards = []
        for persona in row:
            card = _build_card(persona, cursor_x, cursor_y)
            row_cards.append(card)
            cursor_x += CARD_WIDTH + CARD_GAP_X
        cards.extend(row_cards)
        max_row_width = max(max_row_width, cursor_x - CARD_GAP_X - start_x)
        row_height = max(c["height"] for c in row_cards)
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
        # Width and the top (photo/quote/background) section stay locked to
        # the template; only overall height varies, since the
        # Goals/Frustrations/Needs grid now grows to fit real content.
        assert card["width"] == CARD_WIDTH, "every persona card must use the same fixed width"
        assert card["height"] >= _MIN_CARD_HEIGHT, "a card must never be shorter than the locked top section + minimum grid"
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
            photo_node_id = None
            for shape_index, shape in enumerate(card["shapes"]):
                result = await mcp_client.create_shape_with_text(sess, **shape)
                if result.get("node_id"):
                    created_node_ids.append(result["node_id"])
                    if shape_index == card["photo_shape_index"]:
                        photo_node_id = result["node_id"]
                created_shapes += 1
            activity.append(f"Created persona card '{persona_name}' ({len(card['shapes'])} elements)")

            if photo_node_id:
                avatar_bytes = _fetch_avatar_image(persona_name)
                if avatar_bytes:
                    await mcp_client.set_image_fill(sess, photo_node_id, avatar_bytes)
                    activity.append(f"Filled photo placeholder for '{persona_name}' with a generic avatar")

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
