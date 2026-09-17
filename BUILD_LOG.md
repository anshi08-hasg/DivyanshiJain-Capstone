ResearchMate — Build Log
Commit 1 — Capstone Plan

Date: 11 September 2026 Time spent: Tokens used: 3,189,624 total this session (70,388 output tokens; remainder is cached/reused context) — pulled directly from this session's usage log What shipped:

Drafted plan.md: capstone idea, problem statement, target users, Master Agent + Skills architecture, MVP scope, final goals, AI-involvement level (High) with rationale, expected inputs/outputs, success criteria, risks/assumptions, and development sequence.
Refined the plan: added an Example Use Case; renamed "Quote Cleaner" to "Quote Extractor & Cleaner" (identify → select → lightly clean → preserve source, including keeping non-English quotes like Hindi verbatim); moved Persona Generator into an MVP+ milestone so core MVP is 5 skills (Quote Extractor & Cleaner → Interview Analyzer → Pattern Finder → Theme Mapper → Insight Generator).
Made the human-in-the-loop checkpoint pattern and evidence-traceability model explicit, including a "why did ResearchMate say this?" check, and replaced "confidence" language with "evidence-strength."
Added notes confirming no external APIs are needed for MVP, and on anonymizing participant data before upload.

## Commit 2 — Pattern Analyzer + ResearchMate Agent

**Date:** 16 September 2026
**Time spent:** 8 hours (4 hours in class + 4 hours outside class)
**Approx. tokens used:** Exact token usage unavailable in session.

### What shipped
- Finalized and refined the Pattern Analyzer Skill (`.claude/skills/pattern-analyzer/SKILL.md`): improved output structure and evidence handling, added graph-ready IDs/relationships, contradictions/differences, evidence strength, and clearer image-evidence rules.
- Created the project-level ResearchMate Agent (`.claude/agents/researchmate-agent.md`), connected to the existing Pattern Analyzer Skill.
- Defined the Agent's Perceive → Reason → Act → Observe → Human Review workflow, scoped to orchestrate only the Pattern Analysis stage (no personas, ideas, HMWs, or recommendations).
- Tested the Agent on the research workflow; pattern synthesis was successfully generated from the primary research.

### What broke / what changed
- Claude Code initially could not find the research files because they were not present in the project directory / were located separately — repeated Perceive checks of the project folder found no `research` folder or transcripts.
- Confirmed the research is available through Google Drive in the Claude environment, resolving the file-location/access issue.

## Commit 3 — Standalone Pattern Analyzer Webapp + Gemini Integration

**Date:** 17 September 2026
**Time spent:** Not tracked precisely this session.
**Approx. tokens used:** Exact token usage unavailable in session (no per-task metering tool exposed to the assistant; the "tokens left" counter surfaced in system reminders does not behave as a reliable cumulative figure across turns).

### What shipped
- Built a standalone web app (`webapp/`) so the Pattern Analyzer pipeline stage can run outside Claude Code, in a browser, with no dependency on Claude Code as the interface:
  - `webapp/backend/app.py` — Flask backend serving the frontend and exposing `/api/analyze` and `/api/finalize`.
  - `webapp/backend/pattern_analyzer.py` — reimplements the `pattern-analyzer` Skill's rules (`.claude/skills/pattern-analyzer/SKILL.md`) as a standalone LLM system prompt with a strict JSON output schema.
  - `webapp/backend/llm_providers.py` — pluggable LLM layer (`get_provider()`) supporting Anthropic, OpenAI, Gemini, and an offline `MockProvider` (canned response, no API key needed), selected via `LLM_PROVIDER` in `.env`.
  - `webapp/backend/report.py` — builds the final evidence-linked markdown report from only the researcher-approved patterns/findings.
  - `webapp/frontend/` (plain HTML/CSS/JS) — paste per-participant notes → run analysis → approve/edit/reject each candidate pattern and single-participant finding → finalize → downloadable `.md` report. Mirrors the researchmate-agent's Perceive → Act → Observe → Human Review flow (minus its re-run-on-violation correction loop, not reimplemented here).
- Added root `.gitignore` (none existed before) to keep `.env` out of version control.
- Added `webapp/.env.example` documenting expected environment variables for each provider.
- Wired up Gemini as the live provider per user's request: added `GeminiProvider` to `llm_providers.py`, added `google-generativeai` to `requirements.txt`, and set `LLM_PROVIDER=gemini` / `GEMINI_MODEL` in `.env` (pointing at the user's own `GEMINI_API_KEY`, already present in `.env`).

### What broke / what changed
- This machine had no working Python interpreter (only a non-functional Windows Store `python` stub alias) — installed a real Python 3.12 via `winget install Python.Python.3.12` before anything could be run.
- `pattern_analyzer.py` originally used bare `list[dict]` type-hint subscripting, which fails on Python <3.9; added `from __future__ import annotations` for compatibility.
- First live Gemini call failed with `404 ... models/gemini-2.0-flash is no longer available`; corrected `GEMINI_MODEL` to `gemini-3.6-flash` in `.env`, `.env.example`, and the code default, then confirmed a real (non-cached) response.
- Noted a minor model-behavior issue (not a code bug): on one test, Gemini duplicated evidence already used in a cross-participant pattern into the single-participant-findings list too, which the Skill's rules say shouldn't happen — flagged for awareness, not yet corrected in the prompt.

### Test evidence
Ran the backend directly (no browser automation available in this environment) via PowerShell `Invoke-RestMethod` / `Invoke-WebRequest` against the running Flask server (`http://127.0.0.1:5000`):
1. **Static serving:** `GET /`, `GET /app.js`, `GET /style.css` → all `200 OK`, correct content returned.
2. **`/api/analyze` (mock provider):** posted 2-participant sample input → received the expected canned JSON (`PAT01`, `PAT02`, 1 single-participant finding, empty `flags`), confirming the endpoint, JSON parsing, and schema wiring all work.
3. **`/api/finalize`:** posted one `decision: approve` pattern and one `decision: reject` finding → returned a correctly filtered markdown report (rejected finding excluded, approved pattern included with its evidence).
4. **Validation path:** posted only 1 participant → correctly returned `400` with `{"error": "Pattern analysis needs material from at least 2 participants."}`.
5. **Live Gemini call:** after wiring the real API key and fixing the model name, posted a novel test case (gym water fountains — not in the mock's canned data) → Gemini returned analysis specific to that input (`PAT01` about water fountain proximity, correctly scoped `participant_coverage: "2/2 participants: P1, P2"`), confirming the app is genuinely calling the configured LLM rather than serving cached/mock output.

Not tested: the frontend's interactive review flow (approve/edit/reject button clicks, download) was not exercised in an actual browser — only the underlying API contract it depends on was verified directly.

