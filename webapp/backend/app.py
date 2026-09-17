"""Standalone Flask backend for the ResearchMate Pattern Analyzer stage.

Serves the plain HTML/JS frontend and exposes the Perceive/Act/Observe/Human
Review flow (researchmate-agent.md) as two HTTP endpoints, so the pipeline
stage can run as a normal web app instead of through Claude Code.
"""

import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from pattern_analyzer import analyze_patterns
from report import build_report

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

app = Flask(__name__, static_folder="../frontend", static_url_path="")


@app.get("/")
def index():
    return app.send_static_file("index.html")


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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
