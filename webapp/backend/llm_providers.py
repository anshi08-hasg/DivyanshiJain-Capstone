"""Pluggable LLM backend for the standalone ResearchMate webapp.

The Pattern Analyzer logic (pattern_analyzer.py) talks to whatever provider
is returned by get_provider() and never imports a specific vendor SDK
directly, so the webapp can run against Claude, OpenAI, Groq, or fully
offline (MockProvider) without any code changes elsewhere.

Groq is served through OpenAIProvider itself (Groq's API is
OpenAI-compatible; only the base_url and default model differ), not a
separate provider class, per the existing "no duplicated provider logic"
design - see get_provider() below.
"""

import abc
import os


class LLMProvider(abc.ABC):
    @abc.abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return the model's raw text response for a single-turn completion."""


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAIProvider(LLMProvider):
    """Talks to any OpenAI-compatible chat completions API. Used directly
    for real OpenAI, and reused as-is for Groq (get_provider() just passes a
    different base_url/model) since Groq's API is a drop-in-compatible
    superset of the same client library - a separate GroqProvider class
    would only duplicate this exact request/response shape."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        # json_object mode makes the response reliably parseable JSON rather
        # than trusting the model to follow the "respond with ONLY a JSON
        # object" instruction unaided - every system prompt in this project
        # already contains the word "json" (required by this mode) as part
        # of its own output-format instructions.
        response = self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content


class MockProvider(LLMProvider):
    """Offline stand-in used when no LLM API key is configured.

    Lets the frontend, backend wiring, and human-review flow be exercised
    end to end with no external dependency or API key at all. Branches on a
    marker in the system prompt so each caller (Pattern Analyzer, FigJam
    agent's Pattern Finder / Research Critic / Q&A) gets canned data shaped
    like its own schema, instead of silently returning empty results.
    """

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if "Persona Synthesist" in system_prompt:
            return _MOCK_FIGJAM_PERSONAS_RESPONSE
        if "Research Critic" in system_prompt:
            return _MOCK_FIGJAM_CRITIC_RESPONSE
        if "FigJam Research Agent answering" in system_prompt:
            return _MOCK_FIGJAM_ASK_RESPONSE
        if "FigJam board" in system_prompt:
            return _MOCK_FIGJAM_ANALYZE_RESPONSE
        return _MOCK_RESPONSE


_MOCK_RESPONSE = """
{
  "patterns": [
    {
      "id": "PAT01",
      "label": "Difficulty finding quiet study space during exam weeks",
      "category": "pain point",
      "evidence": [
        {"participant_id": "P1", "source_id": "P1-PP02", "source_type": "transcript quote", "text": "During finals I basically camp outside the silent room at 7am because if I don't, there's nowhere quiet left by 9."},
        {"participant_id": "P3", "source_id": "P3-PP01", "source_type": "transcript quote", "text": "Exam week is the worst, every table is taken by 10am and group projects are talking everywhere."},
        {"participant_id": "P4", "source_id": "P4-PP03", "source_type": "transcript quote", "text": "I've started studying in my dorm instead because the library is just too loud when everyone's cramming."}
      ],
      "participant_coverage": "3/4 participants: P1, P3, P4",
      "evidence_strength": "strong: 3/4 participants, consistent wording around exam-week crowding and noise",
      "interpretation": "Demand for quiet space appears to spike sharply during exam periods, suggesting current quiet-seating capacity is sized for average, not peak, demand. (inference)",
      "contradictions": []
    },
    {
      "id": "PAT02",
      "label": "Preference for booking group rooms in advance",
      "category": "preference",
      "evidence": [
        {"participant_id": "P2", "source_id": "P2-PP04", "source_type": "transcript quote", "text": "I always try to book the group room online the night before, otherwise we just end up wandering the floor looking for space."},
        {"participant_id": "P4", "source_id": "P4-PP01", "source_type": "transcript quote", "text": "Booking ahead is the only way I've found to guarantee we actually get a room for project meetings."}
      ],
      "participant_coverage": "2/4 participants: P2, P4",
      "evidence_strength": "moderate: 2/4 participants, similar wording",
      "interpretation": null,
      "contradictions": [
        {"participant_id": "P3", "source_id": "P3-PP04", "text": "I never book ahead, I just show up and take whatever's free. Booking feels like more effort than it's worth."}
      ]
    }
  ],
  "single_participant_findings": [
    {"participant_id": "P1", "source_id": "P1-PP05", "category": "need", "text": "I wish there were more power outlets near the windows on the third floor.", "note": "not a cross-participant pattern"}
  ],
  "flags": []
}
"""


_MOCK_FIGJAM_ANALYZE_RESPONSE = """
{
  "themes": [
    {"id": "TH1", "name": "Noise during exam periods disrupts study space use", "evidence": ["N2", "N3", "N4"], "strength": "strong", "rationale": "Three separate participants describe the same crowding/noise pattern in different words. (inference)"},
    {"id": "TH2", "name": "Accessible entrance is hard to find", "evidence": ["N7", "N8"], "strength": "medium", "rationale": null}
  ],
  "insights": [
    {"id": "INS1", "statement": "Quiet-seating capacity is undersized for exam-period demand.", "evidence": ["N2", "N3", "N4"], "strength": "strong"},
    {"id": "INS2", "statement": "Users strongly prefer personalized booking over walk-in access.", "evidence": ["N11"], "strength": "weak"}
  ],
  "contradictions": [
    {"id": "CON1", "description": "P2 and P4 book group rooms in advance, but P3 explicitly avoids booking ahead.", "evidence": ["N11", "N12", "N13"]}
  ],
  "research_gaps": [
    "No research item covers whether the accessible-entrance signage issue affects wheelchair users differently from ambulatory visitors."
  ],
  "design_opportunities": [
    "Add temporary overflow quiet-study signage or seating during exam weeks.",
    "Add directional signage for the accessible entrance visible from the parking lot."
  ]
}
"""

_MOCK_FIGJAM_CRITIC_RESPONSE = """
{
  "verdicts": [
    {"insight_id": "INS1", "verdict": "validated", "note": "Three participants (P1, P3, P4) independently describe the same exam-week crowding/noise pattern with no contradicting item in the board."},
    {"insight_id": "INS2", "verdict": "weak", "note": "Only one item (N11) supports this; N13 directly contradicts a strong booking preference. Treat as a hypothesis, not a validated insight."}
  ]
}
"""

_MOCK_FIGJAM_PERSONAS_RESPONSE = """
{
  "personas": [
    {
      "id": "PERSONA1",
      "name": "Priya, the Early Arriver",
      "short_description": "A student who treats quiet study space as something you have to claim early, not something that's simply available.",
      "profile": {"role": "Student", "age": null, "location": null, "digital_behaviour": null},
      "goals": ["Find a quiet, reliable place to study during exam weeks", "Avoid wasting time hunting for space"],
      "behaviours": ["Arrives very early (around 7am) to secure a spot", "Moves to a different location (dorm) when the usual space is too loud"],
      "pain_points": ["Quiet rooms fill up fast during exams", "Study spaces get crowded and noisy during high-demand periods"],
      "needs": ["Predictable availability of quiet space", "More capacity during exam periods specifically"],
      "motivations": ["Wants to avoid the stress of not finding a seat", "Values a consistent, distraction-free environment"],
      "representative_quote": {"text": "I always camp outside the silent room at 7am during finals, otherwise there's nowhere quiet left by 9.", "is_verbatim": true, "source_id": "N2"},
      "evidence": ["N2", "N3", "N4"]
    },
    {
      "id": "PERSONA2",
      "name": "Devraj, the Planner",
      "short_description": "A student who books group spaces ahead of time rather than risk showing up to nothing available.",
      "profile": {"role": "Student", "age": null, "location": null, "digital_behaviour": "Books rooms online in advance"},
      "goals": ["Guarantee a group room is available for project meetings"],
      "behaviours": ["Books the group room online the night before"],
      "pain_points": ["Without booking ahead, the group ends up wandering the floor looking for space"],
      "needs": ["A reliable booking system for group rooms"],
      "motivations": ["Wants certainty over convenience"],
      "representative_quote": {"text": "Booking ahead is the only way I've found to guarantee we actually get a room for project meetings.", "is_verbatim": true, "source_id": "N12"},
      "evidence": ["N11", "N12"]
    }
  ]
}
"""

_MOCK_FIGJAM_ASK_RESPONSE = """
{
  "answer": "The strongest recurring pattern is exam-period noise and crowding in the study space, reported independently by three participants (N2, N3, N4). A second, weaker pattern involves the accessible entrance being hard to find (N7, N8).",
  "evidence": ["N2", "N3", "N4", "N7", "N8"],
  "grounded": true
}
"""


_GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def get_provider() -> LLMProvider:
    provider_name = os.environ.get("LLM_PROVIDER", "").strip().lower()

    if provider_name == "anthropic" or (not provider_name and os.environ.get("ANTHROPIC_API_KEY")):
        return AnthropicProvider(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5"),
        )

    if provider_name == "openai" or (not provider_name and os.environ.get("OPENAI_API_KEY")):
        return OpenAIProvider(
            api_key=os.environ["OPENAI_API_KEY"],
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        )

    if provider_name == "groq" or (not provider_name and os.environ.get("GROQ_API_KEY")):
        if not os.environ.get("GROQ_API_KEY", "").strip():
            raise ValueError(
                "LLM_PROVIDER is set to 'groq' but GROQ_API_KEY is not set. "
                "Get a key from console.groq.com and set GROQ_API_KEY in .env "
                "(or as a Railway service variable in production)."
            )
        return OpenAIProvider(
            api_key=os.environ["GROQ_API_KEY"],
            model=os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
            base_url=_GROQ_BASE_URL,
        )

    if provider_name in ("", "mock"):
        return MockProvider()

    raise ValueError(f"Unknown LLM_PROVIDER: {provider_name!r} (expected anthropic, openai, groq, or mock)")
