"""Lightweight checks for the FigJam Research Agent (no pytest dependency,
run directly: `python test_figjam.py`), covering the cases called out in the
task spec: normalization, empty research, malformed responses, evidence
mapping, adapter/agent failure handling, and FigJam layout-plan building.
"""

import asyncio
import os
import sys

from figjam.adapter import MCPFigJamAdapter, _map_board_data_to_raw_items
from figjam.normalize import normalize_board
from figjam.research_agent import FigJamAgentError, _parse_json, _verify_evidence, _evidence_confidence, connect_board
from figjam.figma_layout import build_layout_plan
from figjam import personas as personas_module
from figjam.personas import generate_personas
from figjam.persona_layout import build_persona_layout_plan, _validate_layout, _build_card as _build_card_for_test
from figjam.layout_geometry import Rect, rects_overlap, find_overlap, assert_no_overlaps, bounding_box, grid_positions
from llm_providers import OpenAIProvider, get_provider

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "frontend"))
from server import _normalize_backend_url
import app as app_module
from app import _normalize_origin


def test_normalize_typical_board():
    raw = {
        "board_name": "Test board",
        "raw_items": [
            {"id": "N1", "type": "section", "content": "Study Space"},
            {"id": "N2", "type": "sticky", "content": "Too loud.", "section": "Study Space", "metadata": {"participant": "P1"}},
            {"id": "N3", "type": "sticky", "content": "Too loud too.", "section": "Study Space", "metadata": {"participant": "P2"}},
            {"id": "N4", "type": "something-figma-specific", "content": "Unrecognized node type"},
        ],
    }
    context = normalize_board(raw)
    assert len(context.items) == 4
    assert context.sections == ["Study Space"]
    assert len(context.participant_quotes) == 2
    unknown = [i for i in context.items if i.id == "N4"][0]
    assert unknown.type == "unknown", "unsupported FigJam node types must normalize to 'unknown', not crash"
    overview = context.overview()
    assert overview["research_items"] == 4
    assert overview["sections"] == 1
    assert overview["participants"] == 2


def test_normalize_empty_board():
    context = normalize_board({"board_name": "Empty", "raw_items": []})
    assert context.items == []
    assert context.overview()["research_items"] == 0


def test_primary_research_items_excludes_researchmates_own_pushed_output():
    # Confirmed live: re-connecting to a board that already had "Push to
    # FigJam" or "Push Personas" run on it reads those sections back as
    # ordinary sticky/text items with no distinguishing marker - without
    # this filter, a later Analyze or Generate Personas call would be fed
    # ResearchMate's own prior output as if it were new participant research.
    context = normalize_board({
        "board_name": "Test",
        "raw_items": [
            {"id": "N1", "type": "sticky", "content": "real participant research", "metadata": {"participant": "P1"}},
            {"id": "N2", "type": "section", "content": "Themes"},
            {"id": "N3", "type": "sticky", "content": "TH1: some prior AI-generated theme", "section": "Themes"},
            {"id": "N4", "type": "section", "content": "Persona: Devraj, the Planner"},
            {"id": "N5", "type": "sticky", "content": "GOALS", "section": "Persona: Devraj, the Planner"},
        ],
    })

    primary = context.primary_research_items()
    primary_ids = {i.id for i in primary}
    assert primary_ids == {"N1"}, "only genuine participant research should remain, not the app's own prior sections/output"


def test_connect_board_rejects_empty_board(monkeypatch):
    import figjam.research_agent as agent_module

    class EmptyAdapter:
        async def fetch_board(self, board_ref):
            return {"board_name": "Empty", "raw_items": []}

    monkeypatch.setattr(agent_module, "get_adapter", lambda: EmptyAdapter())
    try:
        asyncio.run(connect_board("default"))
        raise AssertionError("connect_board should reject an empty board")
    except FigJamAgentError as exc:
        assert "empty" in str(exc).lower()


def test_connect_board_demo_succeeds(monkeypatch):
    # Force the demo path regardless of whether FIGMA_ACCESS_TOKEN happens to
    # be set in this process's environment (importing app.py above triggers
    # load_dotenv, which could otherwise make get_adapter() prefer the real,
    # network-calling MCPFigJamAdapter here - tests must not depend on that).
    import figjam.adapter as adapter_module
    monkeypatch.setattr(adapter_module.MCPFigJamAdapter, "is_available", lambda self: False)

    result = asyncio.run(connect_board("default"))
    assert result["is_demo"] is True
    assert len(result["context"].items) > 0
    assert any("Retrieved" in step["label"] for step in result["activity"])


def test_mcp_adapter_availability_reflects_token(monkeypatch):
    adapter = MCPFigJamAdapter()
    monkeypatch.delenv("FIGMA_ACCESS_TOKEN", raising=False)
    assert adapter.is_available() is False
    monkeypatch.setenv("FIGMA_ACCESS_TOKEN", "figd_test_token")
    assert adapter.is_available() is True


def test_map_board_data_infers_section_and_participant_geometrically():
    # Confirmed live: figjam_get_board_contents returns a flat node list with
    # no parent/child linkage, so section membership must be inferred from
    # each node's position against each SECTION's bounding box.
    board_data = {
        "nodes": [
            {"id": 1, "type": "SECTION", "name": "Study Space", "x": 0, "y": 0, "width": 500, "height": 500},
            {"id": 2, "type": "STICKY", "text": "P1: too loud during finals", "x": 10, "y": 10},
            {"id": 3, "type": "STICKY", "text": "no participant tag here", "x": 900, "y": 900},
        ]
    }
    items = _map_board_data_to_raw_items(board_data)

    section_item = next(i for i in items if i["id"] == "1")
    assert section_item["type"] == "section"

    inside_item = next(i for i in items if i["id"] == "2")
    assert inside_item["section"] == "Study Space"
    assert inside_item["metadata"]["participant"] == "P1"

    outside_item = next(i for i in items if i["id"] == "3")
    assert outside_item["section"] is None
    assert "participant" not in outside_item["metadata"]


def test_map_board_data_extracts_participant_from_full_header_line():
    # Confirmed live against a real FigJam board: researchers often write a
    # full "Participant P1 - Name" header rather than a bare "P1: ..." tag -
    # the participant regex must recognize this too, not just the terse form,
    # otherwise every real sticky's participant metadata comes back empty
    # even though the participant is clearly named in the text.
    board_data = {
        "nodes": [
            {"id": 4, "type": "STICKY", "text": "Participant P1 — Aditi\nAge: 20\nQ1. ...", "x": 0, "y": 0},
            {"id": 5, "type": "STICKY", "text": "[P2] prefers EDM", "x": 0, "y": 0},
        ]
    }
    items = _map_board_data_to_raw_items(board_data)
    assert next(i for i in items if i["id"] == "4")["metadata"]["participant"] == "P1"
    assert next(i for i in items if i["id"] == "5")["metadata"]["participant"] == "P2"


def test_evidence_confidence_reflects_count_and_participant_diversity():
    # Confidence must come from code, not the LLM's self-reported "strength" -
    # a model saying "strong" is not evidence of anything, so this is computed
    # purely from how many verified items exist and how many distinct
    # participants they span.
    context = normalize_board({
        "board_name": "Test",
        "raw_items": [
            {"id": "N1", "type": "sticky", "content": "a", "metadata": {"participant": "P1"}},
            {"id": "N2", "type": "sticky", "content": "b", "metadata": {"participant": "P2"}},
            {"id": "N3", "type": "sticky", "content": "c", "metadata": {"participant": "P2"}},
            {"id": "N4", "type": "sticky", "content": "d"},
        ],
    })

    result = _evidence_confidence(context, [])
    assert result["confidence"] == "insufficient"
    assert result["participant_coverage"] == []
    assert result["evidence_count"] == 0

    result = _evidence_confidence(context, ["N1"])
    assert result["confidence"] == "limited"
    assert result["participant_coverage"] == ["P1"]

    result = _evidence_confidence(context, ["N1", "N4"])
    assert result["confidence"] == "medium", "2 items but only 1 with a participant should not reach 'strong'"

    result = _evidence_confidence(context, ["N1", "N2", "N3"])
    assert result["confidence"] == "strong"
    assert result["participant_coverage"] == ["P1", "P2"], "must be distinct participants, not one per item"


def test_parse_json_handles_fenced_and_malformed():
    fenced = '```json\n{"a": 1}\n```'
    assert _parse_json(fenced) == {"a": 1}

    try:
        _parse_json("not json at all")
        raise AssertionError("malformed JSON should raise FigJamAgentError")
    except FigJamAgentError:
        pass


def test_evidence_verification_drops_invented_ids():
    context = normalize_board({
        "board_name": "Test",
        "raw_items": [{"id": "N1", "type": "sticky", "content": "real item"}],
    })
    verified, unsupported = _verify_evidence(context, ["N1", "N99-invented"])
    assert verified == ["N1"]
    assert unsupported is False

    verified2, unsupported2 = _verify_evidence(context, ["N99-invented"])
    assert verified2 == []
    assert unsupported2 is True


def test_layout_plan_skips_empty_sections_and_uses_valid_sticky_colors():
    analysis = {
        "themes": [{"id": "TH1", "name": "Noise", "evidence": ["N1", "N2"]}],
        "insights": [],
        "contradictions": [{"id": "CON1", "description": "P1 vs P2", "evidence": ["N1"]}],
        "research_gaps": [],
        "design_opportunities": [],
    }
    plan = build_layout_plan(analysis)
    keys = [s["key"] for s in plan]
    assert keys == ["themes", "contradictions"], "empty sections (insights, gaps, opportunities) must be skipped"

    valid_colors = {"YELLOW", "BLUE", "GREEN", "PINK", "ORANGE", "PURPLE", "RED", "LIGHT_GRAY", "GRAY"}
    for section in plan:
        assert section["sticky_color"] in valid_colors, "must use the real figjam_create_stickies color enum, not arbitrary hex"
        assert section["width"] > 0 and section["height"] > 0


def test_layout_plan_empty_analysis_produces_no_sections():
    assert build_layout_plan({}) == []


def test_layout_plan_uses_real_sticky_size_no_overlaps():
    # Confirmed live against the real figjam_create_stickies tool: a sticky
    # is ALWAYS a fixed 240x240 square (width/height params are silently
    # ignored). The previous constants here (220 wide, 140 tall) were both
    # smaller than reality, which is exactly why stickies visually
    # overlapped - rows spaced 140px apart with 240px-tall stickies overlap
    # by 100px. This locks in the corrected, measured size.
    from figjam.figma_layout import STICKY_SIZE
    assert STICKY_SIZE == 240

    analysis = {
        "themes": [{"id": f"TH{i}", "name": f"Theme {i}", "evidence": []} for i in range(8)],
        "insights": [{"id": f"INS{i}", "statement": f"Insight {i}", "verdict": "weak"} for i in range(12)],
        "contradictions": [{"id": f"CON{i}", "description": f"Con {i}"} for i in range(5)],
        "research_gaps": [f"Gap {i}" for i in range(6)],
        "design_opportunities": [f"Opp {i}" for i in range(7)],
    }
    plan = build_layout_plan(analysis)

    section_rects = [Rect(s["x"], s["y"], s["width"], s["height"]) for s in plan]
    assert find_overlap(section_rects) is None, "sections must never overlap regardless of item count"

    for section in plan:
        assert find_overlap(section["sticky_rects"]) is None, f"stickies in '{section['title']}' overlap"
        for rect in section["sticky_rects"]:
            assert rect.width == 240 and rect.height == 240


def test_layout_geometry_rects_overlap_and_grid():
    a = Rect(0, 0, 100, 100)
    b = Rect(50, 50, 100, 100)
    c = Rect(200, 0, 100, 100)
    assert rects_overlap(a, b) is True
    assert rects_overlap(a, c) is False

    touching = Rect(100, 0, 100, 100)
    assert rects_overlap(a, touching, margin=0) is False, "edge-touching rects with no margin must not count as overlapping"
    assert rects_overlap(a, touching, margin=10) is True, "a margin must catch near-touching rects too"

    bbox = bounding_box([a, c])
    assert bbox == Rect(0, 0, 300, 100)
    assert bounding_box([]) is None

    grid = grid_positions(5, columns=2, cell_width=100, cell_height=50, h_gap=10, v_gap=10)
    assert len(grid) == 5
    assert find_overlap(grid) is None
    assert_no_overlaps(grid)  # must not raise


class _FakePersonaProvider:
    """Stands in for llm_providers.get_provider() in persona tests, the same
    approach the rest of this pipeline uses to test evidence verification
    without a real LLM call - the point of these tests is the code-side
    validation, not the model's own output."""

    def __init__(self, response: dict):
        import json
        self._raw = json.dumps(response)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return self._raw


_PERSONA_TEST_BOARD = {
    "board_name": "Test",
    "raw_items": [
        {"id": "N1", "type": "sticky", "content": "P1: camps out early for quiet space", "metadata": {"participant": "P1"}},
        {"id": "N2", "type": "sticky", "content": "P3: exam week is the worst for finding space", "metadata": {"participant": "P3"}},
        {"id": "N3", "type": "sticky", "content": "P4: studies in dorm because library is loud", "metadata": {"participant": "P4"}},
    ],
}


def test_persona_grouping_produces_evidence_backed_personas(monkeypatch):
    context = normalize_board(_PERSONA_TEST_BOARD)
    monkeypatch.setattr(personas_module, "get_provider", lambda: _FakePersonaProvider({
        "personas": [{
            "id": "PERSONA1", "name": "Test Persona", "short_description": "grounded",
            "profile": {"role": "Student", "age": None, "location": None, "digital_behaviour": None},
            "goals": ["g1"], "behaviours": ["b1"], "pain_points": ["p1"], "needs": ["n1"], "motivations": ["m1"],
            "representative_quote": {"text": "camps out early for quiet space", "is_verbatim": True, "source_id": "N1"},
            "evidence": ["N1", "N2", "N3"],
        }],
    }))

    result = generate_personas(context, None)
    assert len(result["personas"]) == 1
    persona = result["personas"][0]
    assert persona["evidence"] == ["N1", "N2", "N3"]
    assert persona["confidence"] == "strong"


def test_persona_evidence_traceability_multiple_participants(monkeypatch):
    # A persona is meant to represent a GROUP, so its evidence should be able
    # to span multiple distinct participants, not just repeat one person.
    context = normalize_board(_PERSONA_TEST_BOARD)
    monkeypatch.setattr(personas_module, "get_provider", lambda: _FakePersonaProvider({
        "personas": [{
            "id": "PERSONA1", "name": "Test Persona", "short_description": "grounded",
            "profile": {}, "goals": [], "behaviours": [], "pain_points": [], "needs": [], "motivations": [],
            "representative_quote": {"text": "", "is_verbatim": False, "source_id": None},
            "evidence": ["N1", "N2", "N3"],
        }],
    }))

    result = generate_personas(context, None)
    persona = result["personas"][0]
    assert persona["participant_coverage"] == ["P1", "P3", "P4"], "must trace back to all distinct contributing participants"


def test_persona_with_no_verifiable_evidence_is_dropped(monkeypatch):
    context = normalize_board(_PERSONA_TEST_BOARD)
    monkeypatch.setattr(personas_module, "get_provider", lambda: _FakePersonaProvider({
        "personas": [{
            "id": "PERSONA1", "name": "Invented Persona", "short_description": "not grounded",
            "profile": {}, "goals": [], "behaviours": [], "pain_points": [], "needs": [], "motivations": [],
            "representative_quote": {"text": "made up", "is_verbatim": False, "source_id": None},
            "evidence": ["N99-invented"],
        }],
    }))

    try:
        generate_personas(context, None)
        raise AssertionError("a persona with zero verifiable evidence must not be returned")
    except FigJamAgentError as exc:
        message = str(exc).lower()
        assert "evidence-backed" in message
        # The failure must explain WHY (actual participant/item/candidate
        # counts), not just repeat a generic "couldn't form a persona" line,
        # so a real failure is diagnosable from the error message alone.
        assert "3 participant(s)" in str(exc)
        assert "1 candidate persona(s)" in str(exc)


def test_persona_empty_board_gives_a_specific_reason_not_a_generic_one(monkeypatch):
    context = normalize_board(_PERSONA_TEST_BOARD)
    monkeypatch.setattr(personas_module, "get_provider", lambda: _FakePersonaProvider({"personas": []}))

    try:
        generate_personas(context, None)
        raise AssertionError("an empty candidate list must still raise")
    except FigJamAgentError as exc:
        assert "did not propose any persona groupings" in str(exc)
        assert "3 participant(s)" in str(exc)


def test_persona_unsupported_demographic_claim_is_omitted(monkeypatch):
    # Profile fields the model leaves null must render as omitted/"not
    # identified", never silently invented - this is enforced by
    # _clean_profile only ever trusting a real, non-empty string.
    context = normalize_board(_PERSONA_TEST_BOARD)
    monkeypatch.setattr(personas_module, "get_provider", lambda: _FakePersonaProvider({
        "personas": [{
            "id": "PERSONA1", "name": "Test Persona", "short_description": "grounded",
            "profile": {"role": "Student", "age": "", "location": None, "digital_behaviour": 42},
            "goals": [], "behaviours": [], "pain_points": [], "needs": [], "motivations": [],
            "representative_quote": {"text": "", "is_verbatim": False, "source_id": None},
            "evidence": ["N1"],
        }],
    }))

    result = generate_personas(context, None)
    profile = result["personas"][0]["profile"]
    assert profile["role"] == "Student"
    assert profile["age"] is None, "empty string must not pass through as a real value"
    assert profile["location"] is None
    assert profile["digital_behaviour"] is None, "a non-string value must not pass through as a real value"


def test_persona_false_verbatim_claim_is_downgraded(monkeypatch):
    context = normalize_board(_PERSONA_TEST_BOARD)
    monkeypatch.setattr(personas_module, "get_provider", lambda: _FakePersonaProvider({
        "personas": [{
            "id": "PERSONA1", "name": "Test Persona", "short_description": "grounded",
            "profile": {}, "goals": [], "behaviours": [], "pain_points": [], "needs": [], "motivations": [],
            "representative_quote": {"text": "this exact sentence was never said by anyone", "is_verbatim": True, "source_id": "N1"},
            "evidence": ["N1"],
        }],
    }))

    result = generate_personas(context, None)
    quote = result["personas"][0]["representative_quote"]
    assert quote["is_verbatim"] is False, "a claimed verbatim quote not actually present in its cited item must be downgraded"
    assert quote["source_id"] is None


def _make_test_personas(n, content_size=1):
    return [{
        "id": f"PERSONA{i}", "name": f"Persona {i}", "short_description": "desc",
        "profile": {"role": "Student", "age": None, "location": None, "digital_behaviour": None},
        "goals": [f"g{j}" for j in range(content_size)],
        "behaviours": [f"b{j}" for j in range(content_size)],
        "pain_points": [f"p{j}" for j in range(content_size)],
        "needs": [f"n{j}" for j in range(content_size)],
        "motivations": [f"m{j}" for j in range(content_size)],
        "representative_quote": {"text": "q", "is_verbatim": False, "source_id": None},
        "evidence": [f"R{i:03d}"],
    } for i in range(n)]


def test_persona_layout_plan_uses_shape_cards_not_stickies_and_positions_grid():
    # Personas must be built from figjam_create_shape_with_text (a real,
    # custom-sized shape) - NEVER figjam_create_stickies, confirmed live to
    # be a fixed 240x240 square that can't hold a structured card layout.
    plan = build_persona_layout_plan(_make_test_personas(4))
    assert len(plan["cards"]) == 4
    for card in plan["cards"]:
        assert "stickies" not in card
        for shape in card["shapes"]:
            assert "color" not in shape, "must use fillColor (hex), not the sticky color enum"
            assert shape["shapeType"] == "ROUNDED_RECTANGLE"

    # 4 personas -> 2x2 grid per the exact examples given: row 0 = cards 0,1; row 1 = cards 2,3.
    c0, c1, c2, c3 = plan["cards"]
    assert c1["x"] > c0["x"] and c1["y"] == c0["y"], "first row must be side by side"
    assert c2["y"] > c0["y"] and c2["x"] == c0["x"], "second row must start below the first, aligned left"
    assert c3["x"] > c2["x"] and c3["y"] == c2["y"]


def test_persona_layout_plan_empty_list_produces_no_cards():
    plan = build_persona_layout_plan([])
    assert plan["cards"] == []
    assert plan["section"] is None


def test_persona_card_locks_top_section_but_grows_grid_for_content():
    # The header/quote/background section stays pixel-locked regardless of
    # content. The Goals/Frustrations/Needs grid is the one deliberate
    # exception (explicit later ask: "write full things, don't cut them
    # off") - its height, and therefore the card's overall height, grows to
    # fit real content instead of truncating it.
    from figjam.persona_layout import PERSONA_TEMPLATE

    tiny = {
        "id": "P1", "name": "A", "archetype": "", "short_description": "",
        "profile": {}, "goals": [], "behaviours": [], "pain_points": [], "needs": [], "motivations": [],
        "representative_quote": {"text": "", "is_verbatim": False, "source_id": None}, "evidence": [],
    }
    maxed = _make_test_personas(1, content_size=10)[0]
    maxed["short_description"] = "x" * 500
    maxed["representative_quote"] = {"text": "y" * 400, "is_verbatim": False, "source_id": None}
    maxed["goals"] = ["A realistic-length research finding about what this persona actually wants to accomplish"]

    card_tiny = _build_card_for_test(tiny, 0, 0)
    card_maxed = _build_card_for_test(maxed, 0, 0)

    assert card_tiny["width"] == card_maxed["width"] == PERSONA_TEMPLATE["width"] == 1200
    assert card_maxed["height"] >= card_tiny["height"], "more content must never produce a shorter card"

    # Photo, name, role, quote, divider, and background stay at the exact
    # same position/size regardless of content - only their text may differ.
    locked_indices = (1, 3, 4, 5, 6, 7, 8, 9)  # photo, name, role, profile, quote, divider, bg_heading, bg_body
    for i in locked_indices:
        s1, s2 = card_tiny["shapes"][i], card_maxed["shapes"][i]
        assert s1["x"] == s2["x"] and s1["y"] == s2["y"]
        assert s1["width"] == s2["width"] and s1["height"] == s2["height"]

    # The header/quote/background zone's own text must still be truncated,
    # never left to overflow.
    for i in locked_indices:
        assert len(card_maxed["shapes"][i]["text"]) < 400

    # The grid's bullet text, by contrast, must NOT be aggressively cut -
    # "write full things" means the actual finding survives close to intact.
    long_goal = maxed["goals"][0]
    grid_body_text = card_maxed["shapes"][11]["text"]  # goals: [10]=heading "GOALS", [11]=body
    assert long_goal[:40] in grid_body_text, "grid content must not be truncated away, only the header section is"


def test_persona_card_photo_and_identity_panel_use_sharp_corners():
    card = _build_card_for_test(_make_test_personas(1)[0], 0, 0)
    for shape in card["shapes"]:
        assert shape.get("cornerRadius") == 0, "every persona-card shape must use sharp (non-rounded) corners"


def test_persona_card_name_is_not_a_participant_id():
    # "name" must be the behavioural archetype, never a raw participant id
    # like "P1" - this is enforced by the generation prompt (personas.py),
    # this test just locks in that the layout renders whatever name string
    # it's given without silently falling back to something participant-like.
    persona = _make_test_personas(1)[0]
    persona["name"] = "The Host"
    card = _build_card_for_test(persona, 0, 0)
    name_shape = card["shapes"][3]  # right_bg, photo, panel, name
    assert name_shape["text"] == "The Host"


def test_persona_card_name_and_role_are_white_label_boxes():
    # Per the reference the user provided: name/role render as white boxes
    # with dark text sitting on the dark panel, not white text directly on
    # the panel's own background.
    card = _build_card_for_test(_make_test_personas(1)[0], 0, 0)
    name_shape, role_shape = card["shapes"][3], card["shapes"][4]
    assert name_shape["fillColor"] == "#FFFFFF"
    assert role_shape["fillColor"] == "#FFFFFF"
    assert name_shape["textColor"] != "#FFFFFF", "text on a white box must be dark, not white-on-white"
    assert role_shape["textColor"] != "#FFFFFF"


def test_persona_card_includes_profile_fields_shown_in_webapp_preview():
    # The webapp preview already shows Role/Age/Location/Digital behaviour
    # (figjam.js's confidenceBadge/profile rendering) - the FigJam card had
    # dropped this zone entirely during the pixel-template rebuild; this
    # locks in that it's back and shows unsupported fields honestly rather
    # than inventing them.
    persona = _make_test_personas(1)[0]
    persona["profile"] = {"role": "Host", "age": "21", "location": None, "digital_behaviour": None}
    card = _build_card_for_test(persona, 0, 0)
    profile_shape = card["shapes"][5]  # right_bg, photo, panel, name, role, profile
    assert "Role: Host" in profile_shape["text"]
    assert "Age: 21" in profile_shape["text"]
    assert "Location: Not identified in research" in profile_shape["text"]
    assert "Digital behaviour: Not identified in research" in profile_shape["text"]


def test_persona_grid_body_grows_with_more_and_longer_content():
    from figjam.persona_layout import _column_body_height

    short = _column_body_height(["a", "b"])
    long_items = _column_body_height([
        "A much longer research finding that will need to wrap across multiple lines within the column",
        "Another substantial finding that also needs real space to display without being cut short",
        "A third distinct point raised independently by more than one participant in the research",
        "A fourth finding, since real personas can have up to four bullets per section here",
    ])
    assert long_items > short, "more/longer content must grow the body height, not get truncated to fit a fixed box"


def test_fetch_avatar_image_returns_none_on_network_failure(monkeypatch):
    import httpx
    from figjam import persona_layout as pl

    def _raise(*args, **kwargs):
        raise httpx.ConnectError("simulated network failure")

    monkeypatch.setattr(pl.httpx, "get", _raise)
    assert pl._fetch_avatar_image("Test Persona") is None, \
        "an avatar-service failure must not crash the push, just skip the fill"


def test_persona_layout_no_overlaps_at_scale():
    # The explicit scalability requirement: this must hold for any content
    # size, not just the current 6-participant board.
    for n in (1, 2, 3, 4, 5, 8):
        plan = build_persona_layout_plan(_make_test_personas(n, content_size=4))
        _validate_layout(plan)  # raises on any overlap

        card_rects = [Rect(c["x"], c["y"], c["width"], c["height"]) for c in plan["cards"]]
        assert find_overlap(card_rects) is None, f"{n} personas: cards overlap"
        for card in plan["cards"]:
            assert card["x"] >= 0 and card["y"] >= 0 and card["width"] > 0 and card["height"] > 0


def test_persona_layout_starts_clear_of_existing_content():
    # Part 2/9: the Personas section must never overlap existing synthesis
    # sections, positioned dynamically (not a hardcoded coordinate).
    plan_at_origin = build_persona_layout_plan(_make_test_personas(2), start_x=0)
    plan_offset = build_persona_layout_plan(_make_test_personas(2), start_x=5000)

    assert plan_at_origin["section"]["x"] == 0
    assert plan_offset["section"]["x"] == 5000
    for card in plan_offset["cards"]:
        assert card["x"] >= 5000, "cards must respect the requested start_x, not reset to 0"


def test_persona_cards_carry_evidence_ids_in_their_footer_shape():
    plan = build_persona_layout_plan(_make_test_personas(1))
    evidence_shape = plan["cards"][0]["shapes"][-1]
    assert "RESEARCH EVIDENCE" in evidence_shape["text"]
    assert "R000" in evidence_shape["text"]


def test_find_existing_content_right_edge_covers_every_node_not_just_sections():
    # Confirmed live: the real primary-research stickies (P1-P6) sit loose
    # on the page, not inside any section - checking only ResearchMate's own
    # reserved section names would miss them, letting a new Personas section
    # land right on top of the original research notes. Every node counts.
    from figjam.persona_layout import _find_existing_content_right_edge

    board_data = {"nodes": [
        {"type": "SECTION", "name": "Themes", "x": 0, "width": 900},
        {"type": "SECTION", "name": "Insights", "x": 950, "width": 900},
        {"type": "STICKY", "name": "P1: some research note", "x": 9999, "width": 240},
    ]}
    assert _find_existing_content_right_edge(board_data) == 10239

    assert _find_existing_content_right_edge({"nodes": []}) == 0


def test_generate_personas_route_step_activity_excludes_unrelated_prior_steps(monkeypatch):
    # Confirmed live (user report): the persona status feed showed leftover
    # "Created section 'Design Opportunities'" lines from an earlier, unrelated
    # Push to FigJam click. The route's "activity" field is the cumulative
    # session-wide log by design (used elsewhere for the main activity feed),
    # so the frontend must use a separate, call-scoped field instead of
    # slicing the cumulative one - this locks in that the route provides it.
    context = normalize_board(_PERSONA_TEST_BOARD)
    app_module._figjam_state["context"] = context
    app_module._figjam_state["analysis"] = None
    app_module._figjam_state["personas"] = None
    app_module._figjam_state["activity"] = [
        {"label": "Created section 'Design Opportunities'", "at": "10:00:00"},
        {"label": "Created 4 sticky note(s) in 'Design Opportunities'", "at": "10:00:01"},
    ]

    monkeypatch.setattr(personas_module, "get_provider", lambda: _FakePersonaProvider({
        "personas": [{
            "id": "PERSONA1", "name": "Test Persona", "short_description": "grounded",
            "profile": {}, "goals": [], "behaviours": [], "pain_points": [], "needs": [], "motivations": [],
            "representative_quote": {"text": "", "is_verbatim": False, "source_id": None},
            "evidence": ["N1"],
        }],
    }))

    client = app_module.app.test_client()
    res = client.post("/api/figjam/generate-personas")
    data = res.get_json()

    step_labels = [s["label"] for s in data["step_activity"]]
    assert "Design Opportunities" not in " ".join(step_labels), \
        "step_activity must not carry over unrelated activity from a prior action"
    assert any("Persona Synthesist" in label for label in step_labels)

    all_labels = [s["label"] for s in data["activity"]]
    assert any("Design Opportunities" in label for label in all_labels), \
        "the cumulative 'activity' field must still carry full session history for the main activity log"

    app_module._figjam_state["context"] = None
    app_module._figjam_state["personas"] = None


def test_normalize_backend_url_adds_missing_scheme():
    # Confirmed live: a bare host with no scheme silently breaks cross-origin
    # API calls (browser treats it as a relative path), producing
    # 'Unexpected token <, "<!doctype "... is not valid JSON' because the
    # request lands on the frontend's own 404 page instead of the backend.
    assert _normalize_backend_url("my-app.up.railway.app") == "https://my-app.up.railway.app"
    assert _normalize_backend_url("https://my-app.up.railway.app") == "https://my-app.up.railway.app"
    assert _normalize_backend_url("http://localhost:5000") == "http://localhost:5000"
    assert _normalize_backend_url("https://my-app.up.railway.app/") == "https://my-app.up.railway.app"
    assert _normalize_backend_url("") == ""
    assert _normalize_backend_url("   ") == ""


def test_normalize_origin_adds_missing_scheme():
    # Confirmed live: the identical mistake as BACKEND_URL above, but for
    # FRONTEND_ORIGIN/CORS - a schemeless value never matches the Origin
    # header a real browser sends (always includes the scheme), so
    # flask-cors silently omits Access-Control-Allow-Origin for every real
    # request while a request with no Origin header at all (e.g. curl
    # without -H "Origin: ...") gets the raw misconfigured value reflected,
    # making the bug look harmless until an actual browser hit it.
    assert _normalize_origin("my-app.up.railway.app") == "https://my-app.up.railway.app"
    assert _normalize_origin("https://my-app.up.railway.app") == "https://my-app.up.railway.app"
    assert _normalize_origin("my-app.up.railway.app/") == "https://my-app.up.railway.app"
    assert _normalize_origin("*") == "*"
    assert _normalize_origin("") == ""


def _clear_provider_env(mp):
    for key in ("LLM_PROVIDER", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "GROQ_MODEL", "GEMINI_API_KEY"):
        mp.delenv(key, raising=False)


def test_get_provider_selects_groq_via_explicit_llm_provider(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")

    provider = get_provider()
    assert isinstance(provider, OpenAIProvider)
    assert str(provider._client.base_url) == "https://api.groq.com/openai/v1/"
    assert provider._model == "openai/gpt-oss-120b", "must use a sensible default Groq model when GROQ_MODEL isn't set"


def test_get_provider_selects_groq_via_key_presence_when_unset(monkeypatch):
    # Same auto-detect convenience already extended to anthropic/openai:
    # if LLM_PROVIDER is left blank but a Groq key is present, Groq is used
    # without requiring the user to also set LLM_PROVIDER explicitly.
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")

    provider = get_provider()
    assert isinstance(provider, OpenAIProvider)
    assert str(provider._client.base_url) == "https://api.groq.com/openai/v1/"


def test_get_provider_respects_custom_groq_model(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")

    provider = get_provider()
    assert provider._model == "openai/gpt-oss-20b"


def test_get_provider_missing_groq_api_key_raises_clear_error(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "groq")

    try:
        get_provider()
        raise AssertionError("must raise when LLM_PROVIDER=groq but GROQ_API_KEY is missing")
    except ValueError as exc:
        assert "GROQ_API_KEY" in str(exc)


def test_get_provider_rejects_gemini_as_unknown_provider(monkeypatch):
    # Gemini is fully removed - explicitly requesting it must fail loudly,
    # not silently fall back to anything.
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")

    try:
        get_provider()
        raise AssertionError("LLM_PROVIDER=gemini must no longer be accepted")
    except ValueError as exc:
        message = str(exc)
        assert "gemini" not in message.lower().replace("unknown llm_provider: 'gemini'", "")
        assert "groq" in message.lower()


def test_get_provider_gemini_api_key_alone_has_no_effect(monkeypatch):
    # A leftover GEMINI_API_KEY in the environment (e.g. from before this
    # migration) must not activate any hidden Gemini-shaped path - there is
    # no code left that even looks at this variable.
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "leftover-value-should-be-ignored")

    provider = get_provider()
    assert provider.__class__.__name__ == "MockProvider"


def test_extract_failed_generation_recovers_groq_json_validate_failed(monkeypatch):
    # Confirmed live: Groq's openai/gpt-oss-120b occasionally rejects its own
    # json_object output with code "json_validate_failed" even when the
    # generated text is valid JSON on inspection. The openai SDK's
    # exc.body is the FLAT error object (code/failed_generation at the top
    # level), not wrapped in {"error": {...}} - only str(exc)'s human-text
    # wraps it that way. This must match the real shape, not the display text.
    from llm_providers import _extract_failed_generation

    class FakeGroqError(Exception):
        def __init__(self, body):
            self.body = body

    real_shape = FakeGroqError({
        "message": "Failed to validate JSON. Please adjust your prompt.",
        "type": "invalid_request_error",
        "code": "json_validate_failed",
        "failed_generation": '{"themes": [{"id": "TH1", "name": "x", "evidence": [], "strength": "weak", "rationale": null}]}',
    })
    assert _extract_failed_generation(real_shape) == real_shape.body["failed_generation"]

    assert _extract_failed_generation(FakeGroqError({"code": "json_validate_failed", "failed_generation": ""})) is None, \
        "an empty failed_generation has nothing to recover"
    assert _extract_failed_generation(FakeGroqError({"code": "rate_limit_exceeded", "failed_generation": "x"})) is None, \
        "must only recover this specific error code, not swallow unrelated failures"
    assert _extract_failed_generation(ValueError("not an API error, no .body at all")) is None


def _run_all():
    import inspect
    import sys

    class FakeMonkeypatch:
        def __init__(self):
            self._restore = []

        def setattr(self, obj, name, value):
            self._restore.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def setenv(self, key, value):
            self._restore.append(("env", key, os.environ.get(key)))
            os.environ[key] = value

        def delenv(self, key, raising=True):
            self._restore.append(("env", key, os.environ.get(key)))
            os.environ.pop(key, None)

        def undo(self):
            for kind, name, value in reversed(self._restore):
                if kind == "env":
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value
                else:
                    setattr(kind, name, value)

    tests = [
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and inspect.isfunction(fn)
    ]

    failures = []
    for name, fn in tests:
        mp = FakeMonkeypatch()
        try:
            if "monkeypatch" in inspect.signature(fn).parameters:
                fn(mp)
            else:
                fn()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failures.append(name)
            print(f"FAIL  {name}: {exc}")
        finally:
            mp.undo()

    if failures:
        print(f"\n{len(failures)} failing: {', '.join(failures)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} checks passed.")


if __name__ == "__main__":
    _run_all()
