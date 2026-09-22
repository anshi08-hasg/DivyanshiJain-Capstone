"""Standalone Flask backend for the ResearchMate Pattern Analyzer stage.

Serves the plain HTML/JS frontend and exposes the Perceive/Act/Observe/Human
Review flow (researchmate-agent.md) as two HTTP endpoints, so the pipeline
stage can run as a normal web app instead of through Claude Code.
"""

import asyncio
import os

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from pattern_analyzer import analyze_patterns
from report import build_report
from figjam.research_agent import FigJamAgentError, analyze_research, ask_question, connect_board
from figjam.figma_layout import push_layout_to_figjam
from figjam.figma_mcp_client import FigmaMCPError, request_pairing_code
from figjam.personas import generate_personas
from figjam.persona_layout import push_personas_to_figjam

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

app = Flask(__name__, static_folder="frontend", static_url_path="")

def _normalize_origin(raw: str) -> str:
    """Browsers always send a full scheme (e.g. "https://...") in the Origin
    header, so a bare hostname here (a Railway-generated domain pasted
    without its scheme, the same mistake already seen with BACKEND_URL in
    server.py) never matches, and flask-cors silently omits the CORS header
    for every real request - confirmed live: FRONTEND_ORIGIN was set to a
    schemeless host, and curl with the browser's actual Origin value got no
    Access-Control-Allow-Origin back at all, while a request with no Origin
    header got the raw schemeless value reflected (a flask-cors edge case
    that made the misconfiguration look harmless until a real browser hit it)."""
    value = raw.strip().rstrip("/")
    if value and value != "*" and not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value


# Only needed if the frontend is deployed as its own separate origin (see
# webapp/backend/frontend/server.py); harmless no-op in the normal
# single-service setup, where the frontend is same-origin and doesn't need
# CORS at all. FRONTEND_ORIGIN should be the frontend service's exact URL in
# production; "*" is fine for local dev / a low-stakes demo, not for
# anything handling real user data.
CORS(app, resources={r"/api/*": {"origins": _normalize_origin(os.environ.get("FRONTEND_ORIGIN", "*"))}})

# In-memory, single-session state for the experimental FigJam agent (same
# pattern as the Pattern Analyzer's module-level state: no DB for this MVP).
_figjam_state: dict = {"context": None, "analysis": None, "personas": None, "activity": []}


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/config.js")
def config_js():
    # Same-origin single-service setup: API_BASE_URL empty means the
    # frontend's apiUrl() helper builds relative URLs, same as before this
    # existed. Only webapp/backend/frontend/server.py (the standalone
    # frontend service) sets a real BACKEND_URL here.
    body = (
        "window.API_BASE_URL = \"\";\n"
        "window.apiUrl = function (path) { return (window.API_BASE_URL || \"\") + path; };\n"
    )
    return Response(body, mimetype="application/javascript")


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
        result = asyncio.run(connect_board(board_ref))
    except FigJamAgentError as exc:
        return jsonify({"error": str(exc)}), 502

    context = result["context"]
    _figjam_state["context"] = context
    _figjam_state["analysis"] = None
    _figjam_state["personas"] = None
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


@app.post("/api/figjam/generate-personas")
def figjam_generate_personas():
    context = _figjam_state.get("context")
    if context is None:
        return jsonify({"error": "Connect a FigJam board before generating personas."}), 400

    try:
        result = generate_personas(context, _figjam_state.get("analysis"))
    except FigJamAgentError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception as exc:  # noqa: BLE001 - surface any unexpected provider error to the UI
        return jsonify({"error": f"Persona synthesis failed: {exc}"}), 502

    _figjam_state["personas"] = result["personas"]
    _figjam_state["activity"] = _figjam_state["activity"] + result["activity"]

    return jsonify({
        "personas": result["personas"],
        "activity": _figjam_state["activity"],
    })


@app.post("/api/figjam/push-personas")
def figjam_push_personas():
    personas = _figjam_state.get("personas")
    if not personas:
        return jsonify({"error": "Generate personas before pushing to FigJam."}), 400

    try:
        result = asyncio.run(push_personas_to_figjam(personas))
    except FigmaMCPError as exc:
        return jsonify({"error": str(exc)}), 502
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 - surface any unexpected MCP/subprocess error to the UI
        return jsonify({"error": f"Push personas to FigJam failed: {exc}"}), 502

    _figjam_state["activity"] = _figjam_state["activity"] + [{"label": a, "at": ""} for a in result["activity"]]

    return jsonify(result)


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
    port = int(os.environ.get("PORT", "").strip() or 5000)
    app.run(debug=debug, host="0.0.0.0", port=port)
