"""Persona synthesis stage of the FigJam Research Agent.

Extends the existing Retrieve -> Normalize -> Analyze -> Critique pipeline
(research_agent.py) with one more Gemini reasoning step: cluster the same
retrieved-and-verified research items into a small number of evidence-backed
personas. Reuses research_agent.py's evidence verification and confidence
computation rather than reimplementing them, so a persona's evidence is held
to exactly the same "must cite a real item id or it's dropped" standard as
every theme/insight/contradiction already is.

Two things code enforces here, the same split as the rest of the pipeline:
- Evidence ids: verified against the real board (code, not trusted from the
  model) - a persona with zero verified evidence is dropped entirely rather
  than shown as if it were grounded.
- The representative quote's "verbatim" claim: only trusted if the quoted
  text actually appears in one of the persona's own verified evidence items;
  otherwise downgraded to "synthesized" regardless of what the model claimed.

Everything else (persona prose: goals, behaviours, pain points, needs,
motivations, profile fields) is model-authored text grounded by prompt
instruction only, the same trust level already extended to a theme's "name"
or an insight's "statement" elsewhere in this pipeline - this is not a new,
weaker guarantee, it's parity with the existing design.
"""

from __future__ import annotations

from typing import Any

from llm_providers import get_provider

from .models import FigJamResearchContext
from .research_agent import (
    FigJamAgentError,
    _evidence_confidence,
    _parse_json,
    _step,
    _verify_evidence,
)

PERSONA_SYSTEM_PROMPT = """You are the Persona Synthesist stage of a FigJam research agent.

You receive structured research items (sticky notes, text) retrieved from a
FigJam board, each with a stable id and, where known, a participant tag.
Group participants into a SMALL number of meaningful personas (2 to 4) based
on genuine similarities in goals, behaviours, motivations, pain points, and
needs actually expressed in the research. Do not create a persona per
participant, and do not create a persona for a group of one unless the
material genuinely supports no one else being similar.

This is not "write a plausible persona for this topic." Every persona must
be built ONLY from the research items given to you below. Do not use general
UX knowledge, demographic assumptions, or what a typical user of this kind
of product might be like.

Rules:
- "evidence" must list the exact item ids (e.g. "N3") that support this
  persona as a group. Never invent an id, a participant, or a quote that was
  not given to you.
- Every profile field (age, role, location, digital_behaviour) must be
  `null` unless the given research explicitly states or clearly implies it.
  Do not fill a field with a plausible guess. A persona with mostly-null
  profile fields is expected and correct if the research doesn't cover
  demographics - do not invent them to make the card look complete.
- goals, behaviours, pain_points, needs, motivations: each is a short list
  (2-4 items) of what the research actually shows, in your own words, not a
  copy of your general knowledge of this topic.
- representative_quote.text should be an actual quote from one of this
  persona's evidence items where possible (set is_verbatim true and
  source_id to that item's id). If no single quote represents the group
  well, you may write a short synthesized statement instead, but then set
  is_verbatim false and source_id null.
- If the research does not support forming any meaningful persona at all
  (e.g. too little material, or everyone is too dissimilar to group), return
  an empty "personas" list rather than forcing one.

Respond with ONLY a single valid JSON object, no markdown fences, no
commentary, matching exactly this schema:

{
  "personas": [
    {
      "id": "PERSONA1",
      "name": "string, realistic but clearly fictional",
      "short_description": "string, 1-2 sentences",
      "profile": {
        "role": "string or null",
        "age": "string or null",
        "location": "string or null",
        "digital_behaviour": "string or null"
      },
      "goals": ["string"],
      "behaviours": ["string"],
      "pain_points": ["string"],
      "needs": ["string"],
      "motivations": ["string"],
      "representative_quote": {"text": "string", "is_verbatim": true, "source_id": "N2 or null"},
      "evidence": ["N2", "N3"]
    }
  ]
}
"""


def _persona_context_prompt(context: FigJamResearchContext) -> str:
    lines = [f"Board: {context.board_name}", ""]
    for item in context.items:
        if item.type == "section":
            continue
        section = f" [{item.section}]" if item.section else ""
        participant = item.metadata.get("participant")
        tag = f" (participant: {participant})" if participant else ""
        lines.append(f"{item.id}{tag}{section}: {item.content}")
    return "\n".join(lines)


def _clean_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = profile or {}
    fields = ("role", "age", "location", "digital_behaviour")
    cleaned = {}
    for field in fields:
        value = profile.get(field)
        cleaned[field] = value if isinstance(value, str) and value.strip() else None
    return cleaned


def _verify_quote(quote: dict[str, Any] | None, context: FigJamResearchContext, verified_evidence: list[str]) -> dict[str, Any]:
    """Only trust an "is_verbatim" claim if the quoted text is actually
    substring-present in the item it's attributed to - code cannot verify
    general prose faithfulness, but a claimed verbatim quote is a specific,
    checkable claim, so it gets checked rather than trusted outright."""
    quote = quote or {}
    text = quote.get("text", "").strip()
    source_id = quote.get("source_id")
    is_verbatim = bool(quote.get("is_verbatim")) and source_id in verified_evidence

    if is_verbatim:
        items_by_id = {item.id: item for item in context.items}
        source_item = items_by_id.get(source_id)
        if not source_item or text.lower() not in source_item.content.lower():
            is_verbatim = False
            source_id = None

    if not is_verbatim:
        source_id = None

    return {"text": text, "is_verbatim": is_verbatim, "source_id": source_id}


def generate_personas(context: FigJamResearchContext, analysis: dict[str, Any] | None) -> dict[str, Any]:
    """Runs the Persona Synthesist (Gemini) + evidence verification (code).
    Returns {"personas": [...], "activity": [...]}. Personas with zero
    verified evidence are dropped, not shown as if grounded."""
    activity: list[dict[str, Any]] = []
    provider = get_provider()

    prompt_parts = [_persona_context_prompt(context)]
    if analysis:
        prompt_parts.append(
            "\n## Themes and insights already found\n"
            + "Themes: " + ", ".join(t.get("name", "") for t in analysis.get("themes", []))
            + "\nInsights: " + ", ".join(i.get("statement", "") for i in analysis.get("insights", []))
        )

    activity.append(_step("Sent research context to Gemini (Persona Synthesist)"))
    raw = provider.complete(PERSONA_SYSTEM_PROMPT, "\n".join(prompt_parts))
    parsed = _parse_json(raw)
    candidates = parsed.get("personas", [])

    personas: list[dict[str, Any]] = []
    dropped = 0
    for candidate in candidates:
        verified, unsupported = _verify_evidence(context, candidate.get("evidence", []))
        if unsupported:
            dropped += 1
            continue

        confidence = _evidence_confidence(context, verified)
        personas.append({
            "id": candidate.get("id", f"PERSONA{len(personas) + 1}"),
            "name": candidate.get("name", "Unnamed persona"),
            "short_description": candidate.get("short_description", ""),
            "profile": _clean_profile(candidate.get("profile")),
            "goals": [g for g in candidate.get("goals", []) if isinstance(g, str) and g.strip()],
            "behaviours": [b for b in candidate.get("behaviours", []) if isinstance(b, str) and b.strip()],
            "pain_points": [p for p in candidate.get("pain_points", []) if isinstance(p, str) and p.strip()],
            "needs": [n for n in candidate.get("needs", []) if isinstance(n, str) and n.strip()],
            "motivations": [m for m in candidate.get("motivations", []) if isinstance(m, str) and m.strip()],
            "representative_quote": _verify_quote(candidate.get("representative_quote"), context, verified),
            "evidence": verified,
            **confidence,
        })

    activity.append(_step(f"Identified {len(personas)} evidence-backed persona(s)"))
    if dropped:
        activity.append(_step(f"Dropped {dropped} candidate persona(s) with no verifiable evidence"))

    if not personas:
        raise FigJamAgentError(
            "Could not form any evidence-backed persona from the connected research. "
            "This usually means there isn't enough research yet, or the participants "
            "in it are too dissimilar to group meaningfully."
        )

    return {"personas": personas, "activity": activity}
