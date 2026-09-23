"""Turns ResearchMate's persona-synthesis output into a FigJam layout and
pushes it via figma_mcp_client - the same MCP client figma_layout.py already
uses for Themes/Insights/etc, extended with figjam_create_shape_with_text
(a labeled, custom-sized, custom-colored shape, discovered live via
list_tools()). Personas are built from this, NEVER figjam_create_stickies
(a fixed 240x240 sticky note, confirmed live - width/height are ignored).

LOCKED DESIGN, CONTENT-AWARE HEIGHT: every persona card uses the same
1200px width, the same left/right column split, the same typography,
colors, and spacing rules (PERSONA_TEMPLATE is the single source of truth
for everything that IS fixed). Nothing is ever truncated, shortened, or
replaced with "..." to make it fit - each zone's height (and therefore the
card's overall height) is instead computed from its own real, complete
content, so a persona with more to say simply produces a taller card using
the identical layout rules, never a different design. See _build_card()
for the sequential, content-measuring layout and PERSONA_TEMPLATE for the
fixed measurements it builds from.

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

# Single source of truth for every persona-card measurement that's actually
# FIXED: width, column widths, photo size, typography, colors, spacing
# rules. Per-zone Y positions are no longer listed here - the right column
# is a sequential, content-aware stack (each zone's height depends on its
# own real content), so its zones are positioned by running a cursor down
# from the top rather than a fixed coordinate table. Design language (what
# things look like) is still fully locked; only vertical position/height is
# computed. See _build_card().
PERSONA_TEMPLATE: dict[str, Any] = {
    "width": 1200,
    "left_column_width": 420,
    "right_column_width": 780,
    "photo": {"x": 0, "y": 0, "width": 420, "height": 413, "color": "#E8E8E8"},
    "identity_panel": {"x": 0, "y": 413, "color": "#111111"},
    "name": {"x": 34, "y_offset": 67, "width": 352, "font_size": 28, "min_height": 44},
    "role": {"x": 34, "width": 352, "font_size": 17, "min_height": 28},
    "profile": {"x": 34, "width": 352, "font_size": 13},
    "right_content": {"x": 420, "y": 0, "width": 780, "padding": 42},
    "quote": {"width": 690, "font_size": 26, "min_height": 90},
    "divider": {"width": 690, "height": 2, "color": "#D9D9D9"},
    "background_heading": {"width": 690, "font_size": 18, "min_height": 24},
    "background_body": {"width": 690, "font_size": 15, "min_height": 40},
    "section_heading": {"font_size": 17, "min_height": 24},
    "grid": {"column_width": 205, "gap": 25, "min_body_height": 60, "font_size_body": 14},
    "full_width_body": {"font_size": 14, "min_height": 40},
    "evidence": {"width": 690, "font_size": 13, "min_height": 20},
    "confidence": {"width": 690, "font_size": 13, "min_height": 20},
    "gaps": {"persona_to_persona": 80, "section": 25, "bullet": 10, "block": 16},
}

_HEADING_COLOR = "#222222"
_BODY_COLOR = "#333333"
_MUTED_COLOR = "#8A8A8A"
_WHITE = "#FFFFFF"

CARD_WIDTH = PERSONA_TEMPLATE["width"]
CARDS_PER_ROW = 2
CARD_GAP_X = PERSONA_TEMPLATE["gaps"]["persona_to_persona"]
CARD_GAP_Y = PERSONA_TEMPLATE["gaps"]["persona_to_persona"]
SECTION_PADDING = 48
SECTION_GAP = 120  # clearance kept between existing board content and the new Personas section

_PERSONAS_SECTION_TITLE = "User personas"


# --- Content-aware sizing -------------------------------------------------
#
# NOTHING here truncates text. Every helper below only ESTIMATES how much
# vertical space a piece of real, complete content needs at a fixed font
# size/width (never guessed at 0 - the estimate is deliberately generous:
# better to leave a little extra whitespace than clip a single word).
# Typography (font size, color, width) stays exactly as locked in
# PERSONA_TEMPLATE; only each zone's HEIGHT, and therefore the overall card
# height, is derived from the actual content.

_AVG_CHAR_WIDTH_RATIO = 0.6  # empirically close to this font at 28px/352px (see BUILD_LOG); kept slightly
                             # conservative on purpose so a computed box is never smaller than what's needed
_LINE_HEIGHT_RATIO = 1.4
_BLOCK_PADDING = 16
_BULLET_ITEM_GAP = 8


def _chars_per_line(width: float, font_size: float) -> int:
    return max(8, int(width / (font_size * _AVG_CHAR_WIDTH_RATIO)))


def _wrapped_lines(text: str, chars_per_line: int) -> int:
    return max(1, -(-len(text) // chars_per_line)) if text else 1


def _text_block_height(text: str, width: float, font_size: float, min_height: float = 0) -> float:
    lines = _wrapped_lines(text, _chars_per_line(width, font_size))
    return max(min_height, _BLOCK_PADDING * 2 + lines * font_size * _LINE_HEIGHT_RATIO)


def _bullets_block_height(items: list[str], width: float, font_size: float, min_height: float = 0) -> float:
    if not items:
        return _text_block_height(_NOT_IDENTIFIED, width, font_size, min_height)
    chars_per_line = _chars_per_line(width, font_size)
    total_lines = sum(_wrapped_lines(f"• {i}", chars_per_line) for i in items)
    return max(
        min_height,
        _BLOCK_PADDING * 2 + total_lines * font_size * _LINE_HEIGHT_RATIO + max(0, len(items) - 1) * _BULLET_ITEM_GAP,
    )


def _clean_items(items: list[str]) -> list[str]:
    """Drops only empty/blank entries - never caps the count or shortens
    the text, per the explicit "do not drop the third item" rule. The
    LLM's own prompt already asks for a concise 2-4 items; this is not a
    second, silent content decision on top of that."""
    return [i.strip() for i in (items or []) if i and i.strip()]


def _bulleted_full(items: list[str]) -> str:
    return "\n".join(f"• {i}" for i in items) if items else f"• {_NOT_IDENTIFIED}"


def _profile_lines(profile: dict[str, Any]) -> list[str]:
    """Only fields the research actually supports - an unsupported field is
    OMITTED entirely (no "Not identified in research" placeholder line),
    per the explicit "do not fill the persona with useless placeholder
    text" instruction. Returns [] if nothing is supported at all, in which
    case the whole profile zone is skipped."""
    profile = profile or {}
    labels = (("role", "Role"), ("age", "Age"), ("location", "Location"), ("digital_behaviour", "Digital behaviour"))
    return [f"{label}: {profile[key]}" for key, label in labels if profile.get(key)]


def _quote_text(quote: dict[str, Any]) -> str:
    text = (quote or {}).get("text", "").strip()
    if not text:
        return "“ No representative statement identified in research. ”"
    if quote.get("is_verbatim"):
        return f"“ {text} ”\n— {quote.get('source_id', '')}"
    return f"“ {text} ”\n(synthesized statement, not a direct quote)"


def _build_card(persona: dict[str, Any], x: float, y: float) -> dict[str, Any]:
    """Returns {"x", "y", "width", "height", "shapes": [...], ...}. Design
    (widths, fonts, colors, spacing rules) is fixed to PERSONA_TEMPLATE for
    every persona; content determines every zone's real height, and the
    card's overall height is whatever the complete, untruncated content
    actually needs - per the explicit "same design, complete content, height
    can grow" requirement. Nothing here shortens or drops information; a
    persona with little to say simply produces a shorter card, one with a
    lot to say produces a taller one, both using the identical layout rules."""
    t = PERSONA_TEMPLATE
    shapes: list[dict[str, Any]] = []
    right = t["right_content"]
    right_x = x + right["x"]
    padding = right["padding"]
    block_gap = t["gaps"]["block"]
    section_gap = t["gaps"]["section"]
    bullet_gap = t["gaps"]["bullet"]

    def add(text: str, rel_x: float, height: float, width: float, **style) -> None:
        shapes.append({
            "text": text, "x": x + rel_x, "y": y + cursor_y, "width": width, "height": height,
            "shapeType": "ROUNDED_RECTANGLE", "cornerRadius": 0, **style,
        })

    # ---- Right column: sequential, content-aware stack ----
    cursor_y = padding

    quote_spec = t["quote"]
    quote_text = _quote_text(persona.get("representative_quote") or {})
    quote_height = _text_block_height(quote_text, quote_spec["width"], quote_spec["font_size"], quote_spec["min_height"])
    add(quote_text, right["x"], quote_height, quote_spec["width"], fillColor=_WHITE, fontSize=quote_spec["font_size"])
    cursor_y += quote_height + block_gap

    divider_spec = t["divider"]
    add("", right["x"], divider_spec["height"], divider_spec["width"], fillColor=divider_spec["color"])
    cursor_y += divider_spec["height"] + block_gap

    bg_heading_spec = t["background_heading"]
    add("BACKGROUND", right["x"], bg_heading_spec["min_height"], bg_heading_spec["width"],
        fillColor=_WHITE, textColor=_HEADING_COLOR, fontSize=bg_heading_spec["font_size"])
    cursor_y += bg_heading_spec["min_height"] + bullet_gap

    bg_body_spec = t["background_body"]
    bg_text = persona.get("short_description", "").strip() or _NOT_IDENTIFIED
    bg_height = _text_block_height(bg_text, bg_body_spec["width"], bg_body_spec["font_size"], bg_body_spec["min_height"])
    add(bg_text, right["x"], bg_height, bg_body_spec["width"], fillColor=_WHITE, textColor=_BODY_COLOR, fontSize=bg_body_spec["font_size"])
    cursor_y += bg_height + section_gap

    heading_spec = t["section_heading"]
    grid = t["grid"]
    col_width = grid["column_width"]
    right_col_x = right["x"] + col_width + grid["gap"]

    def add_two_column_row(left_label: str, left_items: list[str], right_label: str, right_items: list[str]) -> None:
        nonlocal cursor_y
        left_h = _bullets_block_height(left_items, col_width, grid["font_size_body"], grid["min_body_height"])
        right_h = _bullets_block_height(right_items, col_width, grid["font_size_body"], grid["min_body_height"])
        row_height = max(left_h, right_h)
        add(left_label, right["x"], heading_spec["min_height"], col_width, fillColor=_WHITE, textColor=_HEADING_COLOR, fontSize=heading_spec["font_size"])
        add(right_label, right_col_x, heading_spec["min_height"], col_width, fillColor=_WHITE, textColor=_HEADING_COLOR, fontSize=heading_spec["font_size"])
        cursor_y += heading_spec["min_height"] + bullet_gap
        add(_bulleted_full(left_items), right["x"], row_height, col_width, fillColor=_WHITE, textColor=_BODY_COLOR, fontSize=grid["font_size_body"])
        add(_bulleted_full(right_items), right_col_x, row_height, col_width, fillColor=_WHITE, textColor=_BODY_COLOR, fontSize=grid["font_size_body"])
        cursor_y += row_height + section_gap

    def add_full_width_block(label: str, items: list[str]) -> None:
        nonlocal cursor_y
        add(label, right["x"], heading_spec["min_height"], bg_body_spec["width"], fillColor=_WHITE, textColor=_HEADING_COLOR, fontSize=heading_spec["font_size"])
        cursor_y += heading_spec["min_height"] + bullet_gap
        body_spec = t["full_width_body"]
        body_height = _bullets_block_height(items, bg_body_spec["width"], body_spec["font_size"], body_spec["min_height"])
        add(_bulleted_full(items), right["x"], body_height, bg_body_spec["width"], fillColor=_WHITE, textColor=_BODY_COLOR, fontSize=body_spec["font_size"])
        cursor_y += body_height + section_gap

    add_two_column_row("GOALS", _clean_items(persona.get("goals")), "PAIN POINTS", _clean_items(persona.get("pain_points")))
    add_two_column_row("BEHAVIOURS", _clean_items(persona.get("behaviours")), "NEEDS", _clean_items(persona.get("needs")))

    motivations = _clean_items(persona.get("motivations"))
    if motivations:
        add_full_width_block("MOTIVATIONS", motivations)

    participants = persona.get("participant_coverage") or []
    if participants:
        participants_spec = t["evidence"]
        participants_text = "PARTICIPANTS: " + " · ".join(participants)
        p_height = _text_block_height(participants_text, participants_spec["width"], participants_spec["font_size"], participants_spec["min_height"])
        add(participants_text, right["x"], p_height, participants_spec["width"], fillColor=_WHITE, textColor=_MUTED_COLOR, fontSize=participants_spec["font_size"])
        cursor_y += p_height + bullet_gap

    evidence_spec = t["evidence"]
    evidence = persona.get("evidence") or []
    evidence_text = "RESEARCH EVIDENCE: " + (" · ".join(evidence) if evidence else "none")
    evidence_height = _text_block_height(evidence_text, evidence_spec["width"], evidence_spec["font_size"], evidence_spec["min_height"])
    add(evidence_text, right["x"], evidence_height, evidence_spec["width"], fillColor=_WHITE, textColor=_MUTED_COLOR, fontSize=evidence_spec["font_size"])
    cursor_y += evidence_height + bullet_gap

    confidence = persona.get("confidence")
    if confidence:
        confidence_spec = t["confidence"]
        count = persona.get("evidence_count", len(evidence))
        confidence_text = f"CONFIDENCE: {confidence.upper()} ({count} item{'s' if count != 1 else ''})"
        c_height = _text_block_height(confidence_text, confidence_spec["width"], confidence_spec["font_size"], confidence_spec["min_height"])
        add(confidence_text, right["x"], c_height, confidence_spec["width"], fillColor=_WHITE, textColor=_HEADING_COLOR, fontSize=confidence_spec["font_size"])
        cursor_y += c_height

    right_stack_height = cursor_y + padding

    # ---- Left column: photo (fixed) + sequential identity panel ----
    name_spec = t["name"]
    name_text = persona.get("name", "Unnamed persona").strip()
    name_height = _text_block_height(name_text, name_spec["width"], name_spec["font_size"], name_spec["min_height"])

    role_spec = t["role"]
    role_text = (persona.get("archetype") or "").strip() or "Behavioural archetype"
    role_height = _text_block_height(role_text, role_spec["width"], role_spec["font_size"], role_spec["min_height"])

    profile_lines = _profile_lines(persona.get("profile"))
    profile_text = "\n".join(profile_lines)
    profile_spec = t["profile"]
    profile_height = _text_block_height(profile_text, profile_spec["width"], profile_spec["font_size"]) if profile_lines else 0

    left_stack_height = (
        name_spec["y_offset"] + name_height + bullet_gap + role_height
        + (bullet_gap + profile_height if profile_lines else 0) + bullet_gap
    )
    photo_height = t["photo"]["height"]
    total_height = max(right_stack_height, photo_height + left_stack_height)

    # z-order: backgrounds first, then everything layered on top of them.
    photo = t["photo"]
    shapes.insert(0, {
        "text": "", "x": x + photo["x"], "y": y + photo["y"], "width": photo["width"], "height": photo["height"],
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": photo["color"], "cornerRadius": 0,
    })
    panel = t["identity_panel"]
    shapes.insert(1, {
        "text": "", "x": x + panel["x"], "y": y + panel["y"], "width": photo["width"], "height": total_height - photo["height"],
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": panel["color"], "cornerRadius": 0,
    })
    right_bg_height = total_height
    shapes.insert(0, {
        "text": "", "x": right_x, "y": y, "width": right["width"], "height": right_bg_height,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE, "cornerRadius": 0,
    })

    name_y = panel["y"] + name_spec["y_offset"]
    shapes.append({
        "text": name_text, "x": x + name_spec["x"], "y": y + name_y, "width": name_spec["width"], "height": name_height,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE, "textColor": _HEADING_COLOR,
        "fontSize": name_spec["font_size"], "cornerRadius": 0,
    })
    name_shape_index = len(shapes) - 1

    role_y = name_y + name_height + bullet_gap
    shapes.append({
        "text": role_text, "x": x + role_spec["x"], "y": y + role_y, "width": role_spec["width"], "height": role_height,
        "shapeType": "ROUNDED_RECTANGLE", "fillColor": _WHITE, "textColor": _BODY_COLOR,
        "fontSize": role_spec["font_size"], "cornerRadius": 0,
    })
    role_shape_index = len(shapes) - 1

    profile_shape_index = None
    if profile_lines:
        profile_y = role_y + role_height + bullet_gap
        shapes.append({
            "text": profile_text, "x": x + profile_spec["x"], "y": y + profile_y,
            "width": profile_spec["width"], "height": profile_height,
            "shapeType": "ROUNDED_RECTANGLE", "fillColor": panel["color"], "textColor": _WHITE,
            "fontSize": profile_spec["font_size"], "cornerRadius": 0,
        })
        profile_shape_index = len(shapes) - 1

    # A generic abstract avatar (persona's initials on a neutral tint) fills
    # the photo placeholder - not a fabricated realistic photo of a specific
    # non-existent person, per the earlier explicit "do not invent a
    # realistic person" instruction, while still visually filling the box
    # rather than leaving it empty.
    return {
        "x": x, "y": y, "width": CARD_WIDTH, "height": total_height, "shapes": shapes,
        "photo_shape_index": 1, "name_shape_index": name_shape_index,
        "role_shape_index": role_shape_index, "profile_shape_index": profile_shape_index,
        "persona_name": persona.get("name", "Unnamed persona"),
    }


def build_persona_layout_plan(personas: list[dict[str, Any]], start_x: float = 0, start_y: float = 0) -> dict[str, Any]:
    """Returns {"section": {title, x, y, width, height}, "cards": [...]}.
    Every card is exactly CARD_WIDTH wide; overall HEIGHT is whatever
    _build_card computed from that persona's complete, untruncated content.
    Row height is the tallest card in that row, so both cards in a row
    still start at the same y even when their heights differ - this is what
    keeps personas from overlapping now that height is no longer a fixed
    number (see PART 20/21 of the height-aware layout requirement)."""
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
        # Width and every design rule (fonts, colors, spacing) stay locked
        # to the template; only overall height varies, since every zone now
        # grows to fit its own complete, untruncated content.
        assert card["width"] == CARD_WIDTH, "every persona card must use the same fixed width"
        assert card["height"] > 0, "a card must have a real, positive height"
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
    never figjam_create_stickies, using the same fixed design for every
    persona - only each card's real, complete content differs."""
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
        profile_node_ids: list[str] = []
        for i, card in enumerate(plan["cards"]):
            persona_name = personas[i].get("name", "Unnamed persona")
            photo_node_id = None
            for shape_index, shape in enumerate(card["shapes"]):
                result = await mcp_client.create_shape_with_text(sess, **shape)
                if result.get("node_id"):
                    created_node_ids.append(result["node_id"])
                    if shape_index == card["photo_shape_index"]:
                        photo_node_id = result["node_id"]
                    if shape_index == card["profile_shape_index"]:
                        profile_node_ids.append(result["node_id"])
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

        # Same story for the profile zone's text color: textColor="#FFFFFF"
        # came back as black text at 0.8 opacity (confirmed live via
        # figma_execute inspection), nearly invisible against the dark
        # panel - fixed directly through the plugin API.
        if profile_node_ids:
            await mcp_client.set_text_fill(sess, profile_node_ids, "#FFFFFF")
            activity.append(f"Fixed profile text color on {len(profile_node_ids)} element(s)")
            activity.append(f"Applied sharp corners and removed default strokes on {len(created_node_ids)} element(s)")

    return {
        "personas": [p.get("name", "Unnamed persona") for p in personas],
        "elements_created": created_shapes,
        "activity": activity,
    }
