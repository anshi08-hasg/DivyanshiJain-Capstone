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

## Commit 4 — UI Redesign + Em Dash Cleanup

**Date:** 17 September 2026
**Time spent:** Not tracked precisely this session.
**Approx. tokens used:** Exact token usage unavailable in session (no per-task metering tool exposed to the assistant).

### What shipped
- Redesigned the standalone webapp's frontend as a proper product UI, not just a functional form:
  - `webapp/frontend/index.html`: branded header with a live LLM-provider indicator pill, a 3-step progress tracker (research material, review patterns, final report), restructured panels per stage, and cleaner participant input cards.
  - `webapp/frontend/style.css`: rebuilt from scratch as a small design system, color tokens, spacing/radius/shadow scale, category/coverage/strength badges, color-coded approve/edit/reject card states, button variants (primary/secondary/ghost), loading spinner, responsive breakpoint.
  - `webapp/frontend/app.js`: updated to match the new markup, drives the step indicator based on pipeline progress, fetches and displays which provider is actually configured.
- Added `GET /api/provider` to `webapp/backend/app.py` so the UI can show the researcher which LLM backend is live (reads `LLM_PROVIDER` / whichever API key is present, falls back to "mock").
- Removed every em dash across the webapp (source, mock sample data, README), replaced with colons, commas, or periods depending on context, per user's style preference.

### What broke / what changed
- Nothing broke; this was a presentation-layer change on top of already-tested endpoints. Re-verified the analyze/finalize contract still matched the new frontend's expected field names after the rewrite (see test evidence).

### Test evidence
Restarted the Flask server and re-verified via PowerShell against `http://127.0.0.1:5000`:
1. **Static serving:** `GET /`, `GET /style.css`, `GET /app.js` → all `200 OK` after the rewrite.
2. **New endpoint:** `GET /api/provider` → returned `{"provider": "gemini"}`, matching the `.env` configuration from Commit 3.
3. **Live Gemini regression check:** posted a fresh, previously-untested scenario (missing accessible-entrance signage) to `/api/analyze` → Gemini returned a correctly-shaped pattern (`PAT01`, `participant_coverage: "2/2 participants: P1, P2"`, populated `evidence`/`interpretation`/`evidence_strength` fields) confirming the redesigned frontend's expected JSON shape still matches the backend's actual response after the UI changes.
4. **Em dash sweep:** `grep -rn "—" webapp/` across `.py`, `.js`, `.html`, `.css`, `.md` returned no matches.

Not tested: the visual redesign itself (layout, colors, step indicator, badges, hover states) was not exercised in an actual browser, only the underlying HTML/CSS/JS files and the API contract they depend on were verified directly.

## Commit 5 — Copy Polish: "Per-participant" Rewording

**Date:** 17 September 2026
**Time spent:** Not tracked precisely this session.
**Approx. tokens used:** Exact token usage unavailable in session (no per-task metering tool exposed to the assistant).

### What shipped
- Reworded the "Per-participant research material" panel heading in `webapp/frontend/index.html` to "Participant research notes": reads as a proper section label instead of a technical modifier, consistent with how the rest of the copy already refers to "each participant."
- Applied the same phrasing fix for consistency across the product's voice, not just the one UI string:
  - `webapp/backend/pattern_analyzer.py`: reworded the Gemini system prompt ("compare each participant's qualitative research findings...") and the prompt-builder's context header ("Each participant's research notes follow, one section per participant.").
  - `webapp/README.md`: reworded step 1 of the Flow section ("Paste each participant's research notes...").

### What broke / what changed
- Nothing broke; this was a copy-only change with no logic or schema changes.

### Test evidence
- `grep -rni "per-participant" webapp/frontend/ webapp/backend/pattern_analyzer.py webapp/README.md` → zero matches, confirming the old phrasing was fully replaced in all three files.

Not tested: did not restart the Flask server or reload the page in a browser to visually confirm the new heading renders, since this was a plain static-text change with no templating logic that could alter it at render time.

