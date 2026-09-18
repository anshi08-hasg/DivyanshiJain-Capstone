"""Pluggable LLM backend for the standalone ResearchMate webapp.

The Pattern Analyzer logic (pattern_analyzer.py) talks to whatever provider
is returned by get_provider() and never imports a specific vendor SDK
directly, so the webapp can run against Claude, OpenAI, or fully offline
(MockProvider) without any code changes elsewhere.
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


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name=model, system_instruction=None)
        self._system_prompt_cache = None
        self._model_name = model
        self._genai = genai

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        # Rebuild the model only when the system prompt changes, since Gemini
        # takes system_instruction at model-construction time, not per-call.
        if system_prompt != self._system_prompt_cache:
            self._model = self._genai.GenerativeModel(
                model_name=self._model_name, system_instruction=system_prompt
            )
            self._system_prompt_cache = system_prompt

        response = self._model.generate_content(user_prompt)
        return response.text


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content


class MockProvider(LLMProvider):
    """Offline stand-in used when no LLM API key is configured.

    Lets the frontend, backend wiring, and human-review flow be exercised
    end to end with no external dependency or API key at all.
    """

    def complete(self, system_prompt: str, user_prompt: str) -> str:
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

    if provider_name == "gemini" or (not provider_name and os.environ.get("GEMINI_API_KEY")):
        return GeminiProvider(
            api_key=os.environ["GEMINI_API_KEY"],
            model=os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"),
        )

    if provider_name in ("", "mock"):
        return MockProvider()

    raise ValueError(f"Unknown LLM_PROVIDER: {provider_name!r} (expected anthropic, openai, gemini, or mock)")
