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

## figmaconnecttry branch — Push to FigJam (write integration)

**Date:** 18 September 2026
**Time spent:** Not tracked precisely this session.
**Approx. tokens used:** Exact token usage unavailable in session.

### What shipped
- Added a real write path from the FigJam Research Agent to an actual FigJam
  board, on top of the existing (demo-data-only) read path from the earlier
  FigJam agent build:
  - `webapp/backend/figjam/figma_mcp_client.py`: a genuine MCP stdio client
    (using the official `mcp` Python SDK) that spawns `npx -y
    figma-console-mcp@latest` and calls its real tools: `figjam_create_section`,
    `figjam_create_stickies`, `figjam_auto_arrange`, plus `list_tools()` as a
    connectivity check.
  - `webapp/backend/figjam/figma_layout.py`: deterministic (non-LLM) logic
    that maps the agent's analysis output (themes/insights/contradictions/
    research gaps/design opportunities) into one real FigJam section per
    group, each containing a grid of colored sticky notes.
  - `POST /api/figjam/push-to-figjam` in `app.py`, and a **Push to FigJam**
    button on the results page.
  - Installed Node.js (`winget install OpenJS.NodeJS.LTS`) and the `mcp`
    Python SDK, since the community MCP server is an npm package spawned as
    a subprocess.
  - Updated `webapp/.env.example` and `requirements.txt` for `FIGMA_ACCESS_TOKEN`
    and the `mcp` dependency.
  - Expanded `FIGMA_CONNECT.md` (new section 7) and `test_figjam.py` (2 new
    tests) to cover this feature honestly.

### What broke / what changed
- Initially assumed (based on Figma's own help docs and a third-party docs
  site) that no write-capable Figma/FigJam MCP existed at all, and separately
  that no FigJam "section" tool existed. Both assumptions were wrong:
  - A real write path exists via the community "Figma Console MCP" project,
    confirmed via web search and doc fetches.
  - `figjam_create_section` does exist. It's simply undocumented on the pages
    fetched during initial research. The exact schema (`name`, `x`, `y`,
    `width`, `height`, `fillColor`) was pulled directly from the live running
    server's tool list, not trusted from any written doc, once code correctly
    used it in place of the earlier planned workaround (a plain shape with
    text standing in for a section).
  - Third-party docs also stated sticky `color` accepts arbitrary hex codes;
    the live server's schema showed it's actually a fixed enum (`YELLOW`,
    `BLUE`, `GREEN`, `PINK`, `ORANGE`, `PURPLE`, `RED`, `LIGHT_GRAY`, `GRAY`).
    Code was corrected to use the enum before any real tool call was attempted.
  - Figma's *official* remote MCP server was investigated first and ruled
    out: it only allowlists specific IDE clients (Claude Code, Cursor, VS
    Code), and connecting a custom backend requires joining a developer
    waitlist, so it isn't a usable path for this feature.
- This build environment had neither Node.js nor the `mcp` Python SDK
  installed; both were added before any of this code could even import.

### Test evidence
- `python webapp/backend/test_figjam.py`: 9 checks, all passing (7 prior +
  2 new: layout-plan section skipping/color-enum correctness, and empty
  analysis producing no sections).
- **Live, real MCP handshake test** (not mocked): the client successfully
  spawned `figma-console-mcp`, completed the MCP `initialize` handshake, and
  listed all 121 real tools the server registers, confirming
  `figjam_create_section` and `figjam_create_stickies` genuinely exist and
  pulling their exact JSON schemas directly from the live server.
- **Live write-attempt test**: called `create_section(...)` against the
  running server with no Figma Desktop/Bridge connected -> failed with a
  clear, specific error (not a crash or a hang), proving the failure path
  behaves correctly when the required live bridge isn't present.
- **Full HTTP route test**: started the Flask app, connected + analyzed via
  the mock provider to populate state, then called `POST
  /api/figjam/push-to-figjam` -> got the same clear 502 error end-to-end
  through the actual route (not just the underlying function), confirming
  the whole wiring (Flask -> asyncio -> layout builder -> MCP client ->
  subprocess -> real tool call) works correctly up to the point where a live
  Figma Desktop Bridge is genuinely required.
- **Not tested and cannot be tested from this environment:** an actual
  section or sticky note appearing on a real FigJam board. This build has no
  GUI and cannot run Figma Desktop or its plugin menu; that final visual
  confirmation has to happen on the user's own machine, documented step by
  step in `FIGMA_CONNECT.md` section 7.

## figmaconnecttry branch — Push to FigJam verified live, plugin vendored, reconnect bug fixed

**Date:** 18 September 2026
**Time spent:** Not tracked precisely this session.
**Approx. tokens used:** Exact token usage unavailable in session.

### What shipped
- Vendored the Desktop Bridge plugin into `webapp/figma-plugin/` (copied from
  a running `figma-console-mcp` 1.40.0 server) so it imports straight from
  this repo instead of a hidden per-machine folder, and pinned the spawned
  server to the matching `1.40.0` version so the two can't silently drift
  apart.
- Refactored `figma_mcp_client.py` to share one MCP session across an entire
  push operation instead of opening/closing a fresh server process per tool
  call (`create_section`/`create_stickies`/`auto_arrange` now take an
  already-open session instead of opening their own).
- Fixed a real error-handling bug: anyio wraps exceptions raised during tool
  calls in nested `BaseExceptionGroup`s by the time they exit the session
  context manager, which was silently replacing specific tool errors (e.g.
  the actual "Cannot connect to Figma Desktop" reason) with a generic
  fallback message. Added `_find_figma_error()` to unwrap nesting and recover
  the real error.
- Added `wait_for_bridge()`, which polls the server's own
  `figma_get_status(probe=true)` tool until it reports a working roundtrip
  (up to 30s), instead of guessing a fixed sleep. Wired into
  `push_layout_to_figjam()` before any write is attempted.

### What broke / what changed
- Investigated (per user's explicit ask) whether Gemini could use Figma's
  *official* remote MCP server instead of the community one, to avoid the
  plugin requirement entirely. Verified empirically, not just from docs: a
  raw MCP handshake against `mcp.figma.com` returned a standard OAuth
  challenge, but attempting Dynamic Client Registration against Figma's own
  `registration_endpoint` returned `403 Forbidden` - confirmed via Figma's
  own support forum that PAT-based/headless auth "cannot be enabled" and
  custom (non-allowlisted) clients cannot register at all today. This
  confirms the plugin-based approach already built is the only currently
  working option, for this project or any third-party integration.
- First live push attempts failed with "Cannot connect to Figma Desktop"
  even with the plugin genuinely running, because each push spawns a brand
  new server process and the plugin needs several seconds to reconnect to
  it. Root-caused by manually holding a session open for 20 seconds, which
  let the exact same write succeed right after it had just failed instantly;
  fixed properly with `wait_for_bridge()` rather than leaving it as a
  "just wait and retry" manual step.
- The generic "unhandled errors in a TaskGroup" error message (seen
  repeatedly while diagnosing the above) was itself a bug: the real per-tool
  error was being swallowed by the session context manager's exception
  handling before this session's fix.

### Test evidence
- **Live, real write to an actual FigJam board, end to end, through the
  deployed Flask route:** `POST /api/figjam/push-to-figjam` created 5 real
  sections (Themes, Insights, Contradictions, Research Gaps, Design
  Opportunities) and 8 real sticky notes, confirmed by the user directly in
  their own FigJam board, with the Desktop Bridge plugin imported from
  `webapp/figma-plugin/manifest.json` and launched in Figma Desktop.
- Confirmed empirically (not just from documentation) that Figma's official
  remote MCP server cannot be used by a custom backend: a direct MCP
  `initialize` POST to `https://mcp.figma.com/mcp` returned `401` with a
  standard OAuth challenge; a Dynamic Client Registration attempt against
  `https://api.figma.com/v1/oauth/mcp/register` returned `403 Forbidden`.
- `python webapp/backend/test_figjam.py`: all 9 checks still passing after
  the client refactor and bug fixes.

Not tested: Cloud Mode (server hosted remotely, e.g. on Railway, with the
plugin pairing in via a 6-character code) was researched and explained to
the user as the closest available path for a Railway deployment, but not
implemented or tested this session; only Local Mode (everything on one
machine) was verified live.

## figmaconnecttry branch — Cloud Mode + Railway deployment prep

**Date:** 18 September 2026
**Time spent:** Not tracked precisely this session.
**Approx. tokens used:** Exact token usage unavailable in session.

### What shipped
- Added Cloud Mode support to `figma_mcp_client.py`: a `FIGJAM_MCP_MODE`
  env var (`local` default, `cloud`) switches the transport between spawning
  a local `npx` process and connecting over HTTPS to Figma Console MCP's
  hosted relay (`figma-console-mcp.southleft.com/mcp`) using
  `FIGMA_ACCESS_TOKEN` as Bearer auth. Local Mode cannot work once the
  backend is hosted remotely (the plugin can only reach its own machine's
  `localhost`), so Cloud Mode is what makes a Railway deployment viable at
  all for this feature.
- Added `request_pairing_code()` and `POST /api/figjam/pair` (calls the
  relay's `figma_pair_plugin` tool), `GET /api/figjam/mode`, and a
  **Generate pairing code** button in the frontend, shown automatically only
  when `FIGJAM_MCP_MODE=cloud`.
- Fixed `wait_for_bridge()` to no-op in cloud mode: `figma_get_status` (used
  to poll for a Local Mode reconnect) isn't even a registered tool on the
  cloud relay (95 tools there vs 121 locally), so calling it there failed
  outright; the cloud relay doesn't need the reconnect-delay workaround
  anyway, since pairing establishes a persistent connection, not a
  freshly-spawned one per push.
- Added Railway deployment plumbing: `webapp/backend/Procfile`
  (`waitress-serve`, chosen over `gunicorn` specifically so the exact command
  could be tested on this Windows dev machine too) and
  `webapp/backend/nixpacks.toml` (adds Node.js to the build image alongside
  Python, needed for Local Mode's `npx` spawn).

### What broke / what changed
- User pushed back on an earlier claim that Cloud Mode requires re-pairing
  every ~5 minutes. Re-investigated rather than accepting the original
  (AI-summarized) doc reading: confirmed the 5-minute window applies only to
  redeeming the *code itself* (like an OTP), not to the established
  connection. Verified live: a write succeeded immediately after pairing,
  and a second write succeeded again ~90 seconds later with zero re-pairing,
  confirming pairing is a one-time setup per plugin session.
- Investigated using Figma's *official* remote MCP server directly (to avoid
  the plugin entirely, per an explicit user request) before building Cloud
  Mode. Ruled out empirically, not just from docs: a raw MCP `initialize`
  POST to `mcp.figma.com` returned `401` with a standard OAuth challenge, and
  a Dynamic Client Registration attempt against its own registration
  endpoint returned `403 Forbidden` - Figma's own infrastructure rejects any
  non-allowlisted client outright. This ruled out the plugin-free approach
  entirely, for this project or anyone else, and justified building on the
  community relay instead.
- `figma_get_status` failing on the cloud relay (see above) initially
  produced the exact same generic "Timed out... last status: not connected
  yet" error as the earlier Local Mode timing bug, which looked identical
  and could have been mistaken for a recurrence of it; root-caused instead
  by directly calling `figma_get_status` on the cloud transport and getting
  `MCP error -32602: Tool figma_get_status not found` back, which is a
  different failure than a timing/reconnect issue and needed a different fix.

### Test evidence
- **Live end-to-end via Cloud Mode, through the actual Flask route:**
  `POST /api/figjam/push-to-figjam` with `FIGJAM_MCP_MODE=cloud` created all
  5 sections and 8 sticky notes on the real board, immediately, no wait -
  compare to Local Mode's 5-30s `wait_for_bridge` delay for the same push.
- **Persistence test:** wrote a real section via the cloud relay, waited
  ~90 seconds doing nothing, wrote again with the same pairing (no new code)
  - succeeded both times.
- **Ruled out Figma's official remote MCP empirically:** `401` on a raw
  `initialize` call to `mcp.figma.com`; `403 Forbidden` on Dynamic Client
  Registration against `api.figma.com/v1/oauth/mcp/register`.
- **Confirmed the community relay's own auth is separate and more open:**
  connecting to `figma-console-mcp.southleft.com/mcp` with a plain Figma
  personal access token as Bearer auth succeeded (95 tools listed), whereas
  the official server rejects unlisted clients regardless of token type.
- **Confirmed the pairing UI end-to-end:** `POST /api/figjam/pair` returned a
  real pairing code and instructions; entering it in the plugin's Cloud Mode
  toggle connected successfully; `GET /api/figjam/mode` correctly reports
  `cloud`, and the frontend correctly shows the pairing button only in that
  mode.
- Deliberately observed a disconnect during testing (from switching the
  plugin between Local/Cloud repeatedly) and confirmed the system surfaces a
  clear "No plugin connected to cloud relay" error rather than hanging.
- `python webapp/backend/test_figjam.py`: all 9 checks still passing.
- **Not tested:** the Procfile/nixpacks.toml combination on actual Railway
  infrastructure (no Railway CLI/account access in this environment). Only
  the exact Procfile command (`waitress-serve --host=0.0.0.0 --port=$PORT
  app:app`) was verified locally, and only the HTTPS/Cloud Mode transport
  (which is what Railway would actually need) was verified live - not the
  Railway build/deploy process itself.
