# ResearchMate Webapp — Pattern Analyzer (standalone)

A standalone HTML/JS + Flask app that runs the Pattern Analyzer pipeline
stage (`.claude/skills/pattern-analyzer/SKILL.md`, orchestrated in Claude
Code by `.claude/agents/researchmate-agent.md`) as a normal web app, with no
dependency on Claude Code itself.

The LLM backend is pluggable (`backend/llm_providers.py`): Anthropic, OpenAI,
or a built-in offline mock, selected via environment variables. Only the
Pattern Analyzer stage is implemented; the rest of the MVP pipeline (Quote
Extractor, Interview Analyzer, Theme Mapper, Insight Generator) is not yet
built here.

## Setup

```bash
cd webapp/backend
pip install -r requirements.txt
```

Configure a provider by copying `webapp/.env.example` into the repo root's
`.env` file and filling in a key — or leave it unset to use the offline mock
provider (returns a canned example so you can exercise the full UI/review
flow with no API key at all).

## Run

```bash
cd webapp/backend
python app.py
```

Open http://localhost:5000 — Flask serves the frontend directly, so there's
nothing else to start.

## Flow

1. Paste per-participant research notes (pain points/needs/behaviours/etc.,
   ideally with quote IDs) for 2+ participants and run analysis.
2. Review each candidate pattern and single-participant finding — approve,
   edit, or reject. Nothing is final until you finalize.
3. Finalize to generate a combined, evidence-linked markdown report of only
   the approved output, downloadable as `.md`.

This mirrors the researchmate-agent's Perceive → Act → Observe → Human
Review workflow, minus the re-run-on-violation loop (Steps 5-6 in the
agent's spec), which isn't reimplemented here.
