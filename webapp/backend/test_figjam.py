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
from figjam.persona_layout import build_persona_layout_plan

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "frontend"))
from server import _normalize_backend_url
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


def test_persona_layout_plan_uses_valid_colors_and_positions_cards_horizontally():
    personas = [
        {
            "id": "PERSONA1", "name": "Alex", "short_description": "desc",
            "profile": {"role": "Student", "age": None, "location": None, "digital_behaviour": None},
            "goals": ["g1", "g2"], "behaviours": ["b1"], "pain_points": ["p1"], "needs": ["n1"],
            "motivations": ["m1"], "representative_quote": {"text": "q", "is_verbatim": False, "source_id": None},
            "evidence": ["N1"],
        },
        {
            "id": "PERSONA2", "name": "Sam", "short_description": "desc",
            "profile": {}, "goals": [], "behaviours": [], "pain_points": [], "needs": [],
            "motivations": [], "representative_quote": {"text": "", "is_verbatim": False, "source_id": None},
            "evidence": ["N2"],
        },
    ]
    plan = build_persona_layout_plan(personas)
    assert len(plan) == 2
    assert plan[1]["x"] > plan[0]["x"], "cards must be arranged left to right, not stacked at the same position"
    assert plan[0]["x"] == 0

    valid_colors = {"YELLOW", "BLUE", "GREEN", "PINK", "ORANGE", "PURPLE", "RED", "LIGHT_GRAY", "GRAY"}
    for card in plan:
        assert card["width"] > 0 and card["height"] > 0
        for sticky in card["stickies"]:
            assert sticky["color"] in valid_colors


def test_persona_layout_plan_empty_list_produces_no_cards():
    assert build_persona_layout_plan([]) == []


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
