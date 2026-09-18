"""Standalone Flask backend for the ResearchMate Pattern Analyzer stage.

Serves the plain HTML/JS frontend and exposes the Perceive/Act/Observe/Human
Review flow (researchmate-agent.md) as two HTTP endpoints, so the pipeline
stage can run as a normal web app instead of through Claude Code.
"""

import asyncio
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from pattern_analyzer import analyze_patterns
from report import build_report
from figjam.research_agent import FigJamAgentError, analyze_research, ask_question, connect_board
from figjam.figma_layout import push_layout_to_figjam
from figjam.figma_mcp_client import FigmaMCPError, request_pairing_code

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

app = Flask(__name__, static_folder="../frontend", static_url_path="")

# In-memory, single-session state for the experimental FigJam agent (same
# pattern as the Pattern Analyzer's module-level state: no DB for this MVP).
_figjam_state: dict = {"context": None, "analysis": None, "activity": []}


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/figjam")
def figjam_page():
    return app.send_static_file("figjam.html")


@app.get("/api/provider")
def provider():
    name = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if not name:
        name = "gemini" if os.environ.get("GEMINI_API_KEY") else (
            "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else (
                "openai" if os.environ.get("OPENAI_API_KEY") else "mock"
            )
        )
    return jsonify({"provider": name})


@app.post("/api/analyze")
def analyze():
    data = request.get_json(force=True, silent=True) or {}
    participants = [
        p for p in data.get("participants", [])
        if p.get("participant_id", "").strip() and p.get("notes", "").strip()
    ]

    if len(participants) < 2:
        return jsonify({"error": "Pattern analysis needs material from at least 2 participants."}), 400

    try:
        result = analyze_patterns(participants)
    except Exception as exc:  # noqa: BLE001 - surface any provider/parse error to the UI
        return jsonify({"error": str(exc)}), 502

    return jsonify(result)


@app.post("/api/finalize")
def finalize():
    data = request.get_json(force=True, silent=True) or {}
    patterns = [p for p in data.get("patterns", []) if p.get("decision") == "approve"]
    findings = [f for f in data.get("single_participant_findings", []) if f.get("decision") == "approve"]

    report_markdown = build_report(patterns, findings)
    return jsonify({
        "report_markdown": report_markdown,
        "approved_patterns": patterns,
        "approved_findings": findings,
    })


@app.post("/api/figjam/connect")
def figjam_connect():
    data = request.get_json(force=True, silent=True) or {}
    board_ref = data.get("board_ref", "").strip() or "default"

    try:
        result = connect_board(board_ref)
    except FigJamAgentError as exc:
        return jsonify({"error": str(exc)}), 502

    context = result["context"]
    _figjam_state["context"] = context
    _figjam_state["analysis"] = None
    _figjam_state["activity"] = result["activity"]

    return jsonify({
        "overview": context.overview(),
        "activity": result["activity"],
        "is_demo": result["is_demo"],
        "items": [i.to_dict() for i in context.items],
    })


@app.post("/api/figjam/analyze")
def figjam_analyze():
    context = _figjam_state.get("context")
    if context is None:
        return jsonify({"error": "Connect a FigJam board before running analysis."}), 400

    try:
        result = analyze_research(context)
    except FigJamAgentError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:  # noqa: BLE001 - surface any unexpected provider error to the UI
        return jsonify({"error": f"Gemini analysis failed: {exc}"}), 502

    _figjam_state["analysis"] = result
    _figjam_state["activity"] = _figjam_state["activity"] + result["activity"]

    return jsonify({
        "themes": result["themes"],
        "insights": result["insights"],
        "contradictions": result["contradictions"],
        "research_gaps": result["research_gaps"],
        "design_opportunities": result["design_opportunities"],
        "activity": _figjam_state["activity"],
    })


@app.post("/api/figjam/ask")
def figjam_ask():
    data = request.get_json(force=True, silent=True) or {}
    question = data.get("question", "").strip()

    context = _figjam_state.get("context")
    if context is None:
        return jsonify({"error": "Connect a FigJam board before asking questions."}), 400
    if not question:
        return jsonify({"error": "Enter a question first."}), 400

    try:
        result = ask_question(context, _figjam_state.get("analysis"), question)
    except FigJamAgentError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Gemini failed to answer: {exc}"}), 502

    return jsonify(result)


@app.get("/api/figjam/mode")
def figjam_mode():
    """Lets the frontend know whether the Desktop Bridge plugin needs local
    (automatic) or cloud (pairing code) connection, so it only shows the
    Pair with FigJam step when it's actually relevant."""
    return jsonify({"mode": os.environ.get("FIGJAM_MCP_MODE", "local").strip().lower()})


@app.post("/api/figjam/pair")
def figjam_pair():
    """Cloud mode only: generates a one-time pairing code for the Desktop
    Bridge plugin's Cloud Mode toggle. Not needed in local mode (the default),
    where the plugin connects to localhost automatically."""
    try:
        result = asyncio.run(request_pairing_code())
    except FigmaMCPError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Could not generate a pairing code: {exc}"}), 502

    return jsonify(result)


@app.post("/api/figjam/push-to-figjam")
def figjam_push():
    analysis = _figjam_state.get("analysis")
    if analysis is None:
        return jsonify({"error": "Run analysis before pushing to FigJam."}), 400

    try:
        result = asyncio.run(push_layout_to_figjam(analysis))
    except FigmaMCPError as exc:
        return jsonify({"error": str(exc)}), 502
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 - surface any unexpected MCP/subprocess error to the UI
        return jsonify({"error": f"Push to FigJam failed: {exc}"}), 502

    _figjam_state["activity"] = _figjam_state["activity"] + [{"label": a, "at": ""} for a in result["activity"]]

    return jsonify(result)


if __name__ == "__main__":
    # Only reached if something runs `python app.py` directly instead of the
    # Procfile's waitress-serve command (confirmed happening on Railway with
    # the Railpack builder, which appears not to read the Procfile at all).
    # Binds 0.0.0.0 and respects $PORT so it's at least reachable and on the
    # right port if that happens again, and debug defaults off so a stray
    # direct run in production doesn't expose the Werkzeug debugger/PIN.
    debug = os.environ.get("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, host="0.0.0.0", port=port)
