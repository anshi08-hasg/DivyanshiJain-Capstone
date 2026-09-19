"""Orchestrates the FigJam Research Agent pipeline.

Retrieve (adapter) -> Normalize (normalize.py, code) -> Analyze (Gemini) ->
Critique (Gemini, second pass) -> Structure (code, evidence verification).

Deterministic bookkeeping (counting items, verifying citation IDs actually
exist, building the activity log) is done in plain Python. Gemini is only
used for the two reasoning steps: synthesizing themes/insights and
critiquing them, per the "code = data, Gemini = reasoning" split.
"""

from __future__ import annotations

import json
import time
from typing import Any

from llm_providers import get_provider

from .adapter import FigJamUnavailableError, get_adapter
from .models import FigJamResearchContext
from .normalize import normalize_board


class FigJamAgentError(Exception):
    """Raised for any pipeline failure that should surface as a clear message."""


def _step(label: str) -> dict[str, Any]:
    return {"label": label, "at": time.strftime("%H:%M:%S")}


async def connect_board(board_ref: str) -> dict[str, Any]:
    """Runs Retrieve + Normalize. Returns {context, activity, is_demo}."""
    activity: list[dict[str, Any]] = []
    adapter = get_adapter()
    is_demo = adapter.__class__.__name__ == "DemoFigJamAdapter"

    try:
        raw = await adapter.fetch_board(board_ref)
    except FigJamUnavailableError as exc:
        raise FigJamAgentError(str(exc)) from exc

    activity.append(_step(f"FigJam connection established ({raw.get('board_name')})"))

    context = normalize_board(raw)
    if not context.items:
        raise FigJamAgentError(
            "Board connected but no research items were found (empty board). "
            "Add sticky notes, text, or sections to the board and reconnect."
        )

    activity.append(_step(f"Retrieved {len(context.items)} research item(s)"))
    activity.append(_step("Normalized research data"))
    activity.append(_step(f"Grouped research by section ({len(context.sections)} section(s))"))

    return {"context": context, "activity": activity, "is_demo": is_demo}


ANALYZE_SYSTEM_PROMPT = """You are the Pattern Finder stage of a FigJam research agent.

You receive structured research items (sticky notes, text, sections, groups)
retrieved from a FigJam board, each with a stable id. Synthesize themes,
insights, contradictions, research gaps, and design opportunities.

Rules:
- Use ONLY the research items given to you below. Do not draw on general UX
  knowledge, common research patterns, or what this topic "usually" involves.
  If the board is about a topic you don't recognize, that is fine - analyze
  what is actually written, not what a typical study on that topic would say.
- Every theme, insight, and contradiction must cite the exact item ids
  (e.g. "N3") that support it. Never invent an id, a participant, or a quote
  that was not given to you.
- A theme or insight needs at least two distinct supporting items to be
  called "recurring"; a single-item finding should still be reported but
  with only one id cited, not inflated.
- Keep evidence separate from interpretation: "evidence" fields cite ids and
  should not contain your own inference; put inference in the "rationale" field.
- Research gaps and design opportunities do not need evidence citations, but
  should be grounded in what is (or is not) present in the given material.
- If the given material does not contain enough for a theme or insight you
  were about to propose, do not include it rather than filling the gap with
  a plausible-sounding but unsupported claim.

Respond with ONLY a single valid JSON object, no markdown fences, no
commentary, matching exactly this schema:

{
  "themes": [
    {"id": "TH1", "name": "string", "evidence": ["N2", "N3"], "strength": "weak | medium | strong", "rationale": "string or null"}
  ],
  "insights": [
    {"id": "INS1", "statement": "string", "evidence": ["N2", "N3"], "strength": "weak | medium | strong"}
  ],
  "contradictions": [
    {"id": "CON1", "description": "string", "evidence": ["N11", "N13"]}
  ],
  "research_gaps": ["string"],
  "design_opportunities": ["string"]
}
"""

CRITIC_SYSTEM_PROMPT = """You are the Research Critic stage of a FigJam research agent.

You receive the same research items given to the Pattern Finder, plus the
insights it produced. Your job is to challenge those insights, not restate them.

For each insight, decide:
- "validated": directly and adequately supported by its cited evidence.
- "weak": supported by too little evidence, or overgeneralized beyond what
  the cited items actually say.
- "contradictory": other research items in the board conflict with it.

Be specific: name the evidence count, and if contradictory, cite the
conflicting item id(s) even if the Pattern Finder didn't.

Respond with ONLY a single valid JSON object, no markdown fences, no
commentary, matching exactly this schema:

{
  "verdicts": [
    {"insight_id": "INS1", "verdict": "validated | weak | contradictory", "note": "string, specific and evidence-based"}
  ]
}
"""

ASK_SYSTEM_PROMPT = """You are the FigJam Research Agent answering a researcher's question about
their own connected research board. You are given the full set of research
items (with ids) and the themes/insights/contradictions already found.

Answer ONLY using this material. If the material does not support an answer,
say so explicitly rather than guessing or using general knowledge. Cite item
ids for any claim you make.

Respond with ONLY a single valid JSON object, no markdown fences, no
commentary, matching exactly this schema:

{
  "answer": "string, cites item ids inline like (N2, N3)",
  "evidence": ["N2", "N3"],
  "grounded": true
}

Set "grounded" to false if you could not find support in the given material,
and in that case "answer" should say what's missing rather than speculate.
"""


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FigJamAgentError(f"Gemini returned malformed JSON ({exc}). Raw output:\n{raw}") from exc


def _valid_ids(context: FigJamResearchContext) -> set[str]:
    return {item.id for item in context.items}


def _verify_evidence(context: FigJamResearchContext, evidence_ids: list[str]) -> tuple[list[str], bool]:
    """Returns (verified_ids, unsupported). Drops any id Gemini invented that
    doesn't exist in the actual retrieved board, per "do not allow Gemini to
    invent evidence" - this is enforced in code, not trusted from the model."""
    valid = _valid_ids(context)
    verified = [i for i in evidence_ids if i in valid]
    return verified, len(verified) == 0


def _evidence_confidence(context: FigJamResearchContext, verified_ids: list[str]) -> dict[str, Any]:
    """Confidence is computed in code from the amount and diversity of
    verified evidence, never from Gemini's own self-assessment - a model
    saying "strong" is not evidence of anything."""
    items_by_id = {item.id: item for item in context.items}
    participants = sorted({
        items_by_id[i].metadata.get("participant")
        for i in verified_ids
        if i in items_by_id and items_by_id[i].metadata.get("participant")
    })

    if not verified_ids:
        confidence = "insufficient"
    elif len(verified_ids) >= 3 and len(participants) >= 2:
        confidence = "strong"
    elif len(verified_ids) >= 2:
        confidence = "medium"
    else:
        confidence = "limited"

    return {
        "confidence": confidence,
        "participant_coverage": participants,
        "evidence_count": len(verified_ids),
    }


def _context_prompt(context: FigJamResearchContext) -> str:
    lines = [f"Board: {context.board_name}", ""]
    for item in context.items:
        section = f" [{item.section}]" if item.section else ""
        lines.append(f"{item.id} ({item.type}){section}: {item.content}")
    return "\n".join(lines)


def analyze_research(context: FigJamResearchContext) -> dict[str, Any]:
    """Runs Analyze (Gemini) + Critique (Gemini) + evidence verification (code)."""
    activity: list[dict[str, Any]] = []
    provider = get_provider()
    user_prompt = _context_prompt(context)

    activity.append(_step("Sent research context to Gemini (Pattern Finder)"))
    raw = provider.complete(ANALYZE_SYSTEM_PROMPT, user_prompt)
    findings = _parse_json(raw)

    themes = findings.get("themes", [])
    insights = findings.get("insights", [])
    contradictions = findings.get("contradictions", [])
    research_gaps = findings.get("research_gaps", [])
    design_opportunities = findings.get("design_opportunities", [])

    for bucket in (themes, insights, contradictions):
        for entry in bucket:
            verified, unsupported = _verify_evidence(context, entry.get("evidence", []))
            entry["evidence"] = verified
            entry["unsupported"] = unsupported
            entry.update(_evidence_confidence(context, verified))

    activity.append(_step(f"Detected {len(themes)} theme(s)"))
    activity.append(_step(f"Found {len(contradictions)} contradiction(s)"))
    activity.append(_step(f"Identified {len(research_gaps)} research gap(s)"))
    activity.append(_step("Generated research opportunities"))

    activity.append(_step("Sent candidate insights to Gemini (Research Critic)"))
    critic_prompt = user_prompt + "\n\n## Candidate insights\n" + json.dumps(insights, indent=2)
    raw_critic = provider.complete(CRITIC_SYSTEM_PROMPT, critic_prompt)
    critique = _parse_json(raw_critic)

    verdicts = {v["insight_id"]: v for v in critique.get("verdicts", []) if "insight_id" in v}
    for insight in insights:
        verdict = verdicts.get(insight.get("id"))
        if insight.get("unsupported"):
            insight["verdict"] = "weak"
            insight["verdict_note"] = "No cited evidence id was found among the retrieved research items."
        elif verdict:
            insight["verdict"] = verdict.get("verdict", "weak")
            insight["verdict_note"] = verdict.get("note", "")
        else:
            insight["verdict"] = "weak"
            insight["verdict_note"] = "Research Critic did not return a verdict for this insight."

    activity.append(_step("Research Critic returned verdicts"))

    return {
        "themes": themes,
        "insights": insights,
        "contradictions": contradictions,
        "research_gaps": research_gaps,
        "design_opportunities": design_opportunities,
        "activity": activity,
    }


def ask_question(context: FigJamResearchContext, analysis: dict[str, Any] | None, question: str) -> dict[str, Any]:
    provider = get_provider()
    parts = [_context_prompt(context)]
    if analysis:
        parts.append(
            "\n## Findings so far\n"
            + json.dumps(
                {
                    "themes": analysis.get("themes", []),
                    "insights": analysis.get("insights", []),
                    "contradictions": analysis.get("contradictions", []),
                },
                indent=2,
            )
        )
    parts.append(f"\n## Question\n{question}")

    raw = provider.complete(ASK_SYSTEM_PROMPT, "\n".join(parts))
    result = _parse_json(raw)
    verified, unsupported = _verify_evidence(context, result.get("evidence", []))
    result["evidence"] = verified
    if unsupported:
        result["grounded"] = False
    return result
