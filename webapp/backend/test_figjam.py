"""Lightweight checks for the FigJam Research Agent (no pytest dependency,
run directly: `python test_figjam.py`), covering the cases called out in the
task spec: normalization, empty research, malformed responses, evidence
mapping, and adapter/agent failure handling.
"""

from figjam.adapter import DemoFigJamAdapter, MCPFigJamAdapter, FigJamUnavailableError
from figjam.normalize import normalize_board
from figjam.research_agent import FigJamAgentError, _parse_json, _verify_evidence, connect_board


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


def test_connect_board_rejects_empty_board(monkeypatch):
    import figjam.research_agent as agent_module

    class EmptyAdapter:
        def fetch_board(self, board_ref):
            return {"board_name": "Empty", "raw_items": []}

    monkeypatch.setattr(agent_module, "get_adapter", lambda: EmptyAdapter())
    try:
        connect_board("default")
        raise AssertionError("connect_board should reject an empty board")
    except FigJamAgentError as exc:
        assert "empty" in str(exc).lower()


def test_connect_board_demo_succeeds():
    result = connect_board("default")
    assert result["is_demo"] is True
    assert len(result["context"].items) > 0
    assert any("Retrieved" in step["label"] for step in result["activity"])


def test_mcp_adapter_is_honest_about_being_unavailable():
    adapter = MCPFigJamAdapter()
    assert adapter.is_available() is False
    try:
        adapter.fetch_board("anything")
        raise AssertionError("MCPFigJamAdapter.fetch_board should raise until a real MCP tool exists")
    except FigJamUnavailableError as exc:
        assert "MCP" in str(exc)


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


def _run_all():
    import inspect
    import sys

    class FakeMonkeypatch:
        def __init__(self):
            self._restore = []

        def setattr(self, obj, name, value):
            self._restore.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def undo(self):
            for obj, name, value in self._restore:
                setattr(obj, name, value)

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
