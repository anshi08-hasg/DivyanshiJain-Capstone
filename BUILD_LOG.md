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

## figmaconnecttry branch — Real Railway deployment fixes (from actual deploy attempts)

**Date:** 18 September 2026
**Time spent:** Not tracked precisely this session.
**Approx. tokens used:** Exact token usage unavailable in session.

### What shipped
- Fixed `webapp/backend/app.py`'s `if __name__ == "__main__"` block to bind
  `0.0.0.0` and read `$PORT` (was hardcoded `127.0.0.1:5000`), with debug
  mode only on via an explicit `FLASK_DEBUG` env var (was always `True`).
- Moved `webapp/frontend/` to `webapp/backend/frontend/` (`git mv`) and
  changed `app.py`'s `static_folder` from `"../frontend"` to `"frontend"`,
  so the whole app is self-contained under the directory Railway's Root
  Directory setting actually deploys, instead of depending on a sibling
  directory outside it.
- Updated `FIGMA_CONNECT.md` (new subsection under section 8) documenting
  three real deployment failures hit on actual Railway infrastructure and
  their fixes, in detail, since none of these could have been predicted or
  caught without a live deploy attempt.

### What broke / what changed (this is the whole point of this entry)
- **First deploy attempt failed at build time.** Railway's actual build logs
  (user-provided) showed its builder ("Railpack", not Nixpacks as assumed
  when `nixpacks.toml` was written) could only see `BUILD_LOG.md` and
  `DivyanshiJain_capstone_plan.md` - i.e. it was building from the repo root,
  not `webapp/backend`, because Root Directory hadn't actually been set in
  Railway's UI yet (this doc said to set it; it just hadn't been done). Not
  a code bug - a setup step not yet completed.
- **Second attempt built and "succeeded" per Railway's UI, but the site
  returned "Application failed to respond."** User-provided runtime logs
  showed Flask's own dev server banner (`Debug mode: on`, `Running on
  http://127.0.0.1:5000`), meaning Railpack ran `python app.py` directly and
  ignored the `Procfile`'s `waitress-serve` command entirely. Binding to
  `127.0.0.1` is unreachable from outside the container, which is exactly
  the symptom seen. This was not something local testing could have caught,
  since locally the exact `waitress-serve` command was tested directly, not
  Railway's actual builder-chosen start command.
- **Third issue: backend responded, but the frontend showed nothing.**
  Reasoned through this one before waiting for more logs: Root Directory
  scopes Railway's entire build context to `webapp/backend`, and
  `webapp/frontend/` was a sibling directory outside it - almost certainly
  not included in the deployed image at all, even though it exists locally
  and worked in every local test this session. Fixed by restructuring rather
  than guessing at Railway-specific config to reach outside the Root
  Directory.

### Test evidence
- Re-ran the local server after both `app.py` fixes and the frontend move:
  `/`, `/app.js`, `/style.css`, `/figjam`, `/figjam.js`, `/api/provider` all
  returned `200`, confirming the restructure didn't break anything that was
  working before.
- Explicitly checked `webapp/README.md` for any hardcoded old frontend path
  references before considering the doc updates complete - found none.
- **Not verified:** whether these fixes actually resolve the issue on real
  Railway infrastructure - no Railway access in this environment. The user
  needs to redeploy and confirm; recommended they also explicitly override
  Railway's Start Command to `waitress-serve --host=0.0.0.0 --port=$PORT
  app:app` rather than relying solely on the `app.py` safety-net fix, since
  a real production WSGI server is preferable to Flask's dev server even
  with the binding fix applied.

## figmaconnecttry branch — Two-service Railway deployment (CORS + config.js)

**Date:** 19 September 2026
**Time spent:** Not tracked precisely this session.
**Approx. tokens used:** Exact token usage unavailable in session.

### What shipped
- Fixed a real crash: `int(os.environ.get("PORT", 5000))` only falls back to
  the default when `PORT` is unset, not when it's set but empty; this
  machine's local `.env` had a leftover `PORT=` from earlier testing and
  reproduced the exact crash. Fixed to treat both cases the same.
- Discovered (from the user) that they had split the deployment into two
  separate Railway services (frontend, backend) on their own, which cannot
  work with the existing frontend code: `app.js`/`figjam.js` used relative
  `fetch("/api/...")` calls, which resolve against whichever origin serves
  the page, so from a separate frontend service they'd hit that service's
  own (API-less) origin instead of the backend.
- Built real two-service support rather than just recommending against it:
  - `webapp/backend/frontend/server.py`: a second, minimal Flask app that
    serves the static frontend files plus a dynamic `/config.js` route,
    which injects `window.API_BASE_URL` from that service's own
    `BACKEND_URL` env var.
  - `webapp/backend/frontend/Procfile` and `requirements.txt` (much smaller
    than the backend's - just `flask` + `waitress`, no LLM/MCP deps) for
    that service.
  - Added a matching `/config.js` route to the main `app.py` (empty
    `API_BASE_URL`), so the existing single-service setup is completely
    unaffected - `apiUrl()` builds the same relative URLs as before when
    `API_BASE_URL` is empty.
  - Changed all 9 `fetch("/api/...")` call sites across `app.js` and
    `figjam.js` to `fetch(apiUrl("/api/..."))`.
  - Added `flask_cors.CORS` to `app.py`, scoped to `/api/*` only, controlled
    by a new `FRONTEND_ORIGIN` env var (defaults to `*` if unset).
  - Documented both deployment options (one service vs. two) in
    `FIGMA_CONNECT.md` section 8, including exact Root Directory/Build
    Command/Start Command/env vars for each service in the two-service case.

### What broke / what changed
- The empty-`PORT` crash was found by simply trying to run the server
  locally after an unrelated change - not something that needed Railway logs
  to catch, just running the actual command.
- The two-service CORS/config.js work exists entirely because the user had
  already tried the naive two-service split and hit exactly the failure mode
  predicted (pages rendered, nothing functional) - this wasn't built
  speculatively, it was built in direct response to a real, already-observed
  failure.

### Test evidence
- Ran the real backend (`app.py`, port 5000) and the real frontend server
  (`server.py`, port 5010, `BACKEND_URL=http://127.0.0.1:5000`) as two
  separate local processes simultaneously:
  - `GET http://127.0.0.1:5010/config.js` returned the correctly injected
    `API_BASE_URL`.
  - A request to `http://127.0.0.1:5000/api/provider` with `Origin:
    http://127.0.0.1:5010` returned `200` with `Access-Control-Allow-Origin:
    http://127.0.0.1:5010` set correctly - the actual header a browser
    checks before allowing the frontend's JS to read the response.
  - A full FigJam flow (`connect` then `analyze`) succeeded end to end with
    that same cross-origin header present on every request.
- Re-verified the single-service setup (`app.py` alone) still works
  unaffected: `/config.js` returns an empty `API_BASE_URL`, and `/`,
  `/app.js`, `/figjam`, `/figjam.js`, `/api/provider` all still return `200`.
- `python webapp/backend/test_figjam.py`: all 9 checks still passing.
- **Not tested:** two actual separate Railway services communicating over
  the real network - only two local processes on different ports, which
  exercises the identical CORS/config.js code path but isn't a substitute
  for the real infrastructure. The user still needs to deploy both services
  and confirm.

## figmaconnecttry branch — Real two-service Railway deployment debugging

**Date:** 19 September 2026
**Time spent:** Not tracked precisely this session.
**Approx. tokens used:** Exact token usage unavailable in session.

### What shipped
- Fixed a second instance of the missing-scheme bug: `FRONTEND_ORIGIN` (used
  to configure CORS on the backend) was set to a bare Railway hostname, same
  mistake as the earlier `BACKEND_URL` bug. Added `_normalize_origin()` in
  `app.py`, mirroring `server.py`'s `_normalize_backend_url()`, so a missing
  `https://` is auto-added before being passed to `flask_cors.CORS()`.
- Added copy-to-clipboard for FigJam pairing codes: auto-copies as soon as
  the code is generated, plus a manual "Copy" button that shows "Copy
  failed, select manually" if clipboard access is blocked, so the failure
  is visible rather than silent.
- Added 2 new tests (`test_normalize_origin_adds_missing_scheme`,
  building on the existing `test_normalize_backend_url_adds_missing_scheme`
  pattern) - 11 checks total now, all passing.

### What broke / what changed (all found on real Railway infrastructure, none of it reproducible locally beforehand)
- **Both services individually looked "successfully deployed" while being
  completely unreachable.** Root cause, found from actual deploy + HTTP
  network logs the user pulled: each service's **Public Networking target
  port** didn't match the port the container actually listened on. The
  frontend needed `8080` (Railway's own default `$PORT`, confirmed from its
  deploy log: `Serving on http://0.0.0.0:8080`); the backend's domain was
  still configured for `5000` (a leftover from local-dev assumptions) while
  its container also listened on `8080`. Every request hit Railway's edge
  proxy, which had nothing to route to, and returned a fast, uniform `502`
  on every single path (including plain `GET /`) - a pattern that, in
  hindsight, is the signature of a routing/port mismatch rather than an
  app-level crash (a real crash would vary in latency and, in this app's
  case, only affect specific broken code paths, not literally every route
  including static assets that had never changed).
- Confirmed Railpack *can* pick up `Procfile` correctly (contradicting an
  earlier build attempt) - once Root Directory was actually set correctly,
  the build log explicitly showed `Found web command in Procfile` and
  `Deploy: waitress-serve --host=0.0.0.0 --port=$PORT app:app`, and the
  container logs confirmed `waitress` really was serving, not Flask's dev
  server. The earlier "ran `python app.py` directly" failure mode from a
  previous session was most likely caused by the Root Directory
  misconfiguration at the time, not a fundamental Railpack/Procfile
  incompatibility as originally assumed and documented.
- **The "Pair with FigJam" box was invisible on the deployed frontend even
  after both services were reachable and the copy button had shipped.**
  Root-caused by directly curling the backend's `/api/figjam/mode` endpoint
  with the exact `Origin` header a real browser sends: it returned `200`
  with the correct body, but with no `Access-Control-Allow-Origin` header
  at all. A second curl with no `Origin` header at all returned the raw,
  schemeless `FRONTEND_ORIGIN` value reflected directly, which is what
  revealed the actual misconfigured value without needing dashboard access.
  This confirms the earlier `BACKEND_URL` scheme bug was not a one-off typo
  but a pattern this Railway setup makes easy to hit (its UI shows generated
  domains without their scheme, inviting exactly this mistake), which is why
  both instances got a defensive code fix rather than only a "fix your env
  var" instruction.

### Test evidence
- User confirmed live: the full Pattern Analyzer flow (Run Pattern Analysis,
  Finalize approved output) works end to end on the deployed two-service
  setup after the port fixes.
- User confirmed live: a real FigJam Desktop Bridge plugin pairing,
  including generating a fresh code via the deployed backend's
  `/api/figjam/pair` and seeing prior real pushed content
  (Themes/Insights/Contradictions/Research Gaps/Design Opportunities
  sections) already present on their actual FigJam board from earlier
  sessions.
- Verified live, directly against the deployed backend: `curl` with the
  exact browser-sent `Origin` header got no CORS header (confirming the
  bug); `curl` with no `Origin` header reflected the raw misconfigured
  value (revealing what it actually was set to); after the code fix,
  reproduced the identical scenario locally with `FRONTEND_ORIGIN` set to
  that exact schemeless value and confirmed `Access-Control-Allow-Origin`
  now correctly includes the scheme.
- `python webapp/backend/test_figjam.py`: 11 checks, all passing.
- **Not yet confirmed:** whether the `FRONTEND_ORIGIN` fix resolves the
  pairing box's visibility on the actual deployed frontend - fixed and
  verified against the exact real-world value, but the user still needs to
  wait for the backend to redeploy and check the live page.

## figmaconnecttry branch — Real FigJam board reading (replaces demo-only "Connect FigJam")

**Date:** 19 September 2026
**Time spent:** Not tracked precisely this session.
**Approx. tokens used:** Exact token usage unavailable in session.

### What shipped
- Implemented `MCPFigJamAdapter.fetch_board()` for real, using the same
  `figma_mcp_client` session already built for Push to FigJam. Added
  `get_board_contents()` to `figma_mcp_client.py` (calls
  `figjam_get_board_contents`) and `_map_board_data_to_raw_items()` /
  `_find_containing_section()` to `adapter.py`, mapping real Figma node data
  into the existing evidence schema.
- `MCPFigJamAdapter.is_available()` now reflects whether `FIGMA_ACCESS_TOKEN`
  is configured (previously always `False`); `get_adapter()` already
  preferred it automatically once available, so no dispatch logic needed to
  change, only the adapter's own honesty about its capability.
- Made `connect_board()`, `FigJamAdapter.fetch_board()`, and
  `/api/figjam/connect` async throughout, since the real read path needs the
  same `asyncio`/MCP session machinery as the write path.
- Updated the frontend's experimental banner and connect handler to state
  whether the connected board is real or demo, based on the actual
  `is_demo` flag, instead of a fixed "always demo" claim.
- Added 2 new tests replacing the now-outdated
  `test_mcp_adapter_is_honest_about_being_unavailable` (which asserted
  permanent unavailability, no longer true): one confirming
  `is_available()` tracks the token, one confirming the geometric
  section/participant-inference mapping against real-shaped node data.

### What broke / what changed
- Discovered live that `figjam_get_board_contents` has no board/page
  selector parameter at all - it always reads whichever page is currently
  active/focused in Figma Desktop. First attempt against a board that
  looked populated on screen returned `0` nodes; root-caused (with the
  user's help confirming what was actually focused) to a different
  page/file being focused at that moment, not a bug in the read call.
- To get the real response shape rather than guess from documentation,
  created a real sticky and a real section on the user's live board via the
  already-working write path, then read them back immediately - this
  revealed the real shape (`{id, type, name, x, y, width, height, text?,
  color?, childCount?}`) and, critically, that there is **no parent/child
  linkage** returned for section membership (a `SECTION` node only reports
  its own `childCount`), which is why section assignment had to be inferred
  geometrically (bounding-box containment) instead of read directly.
- Fixed 3 tests broken by making `fetch_board`/`connect_board` async
  (`coroutine was never awaited` / `'coroutine' object is not subscriptable`
  errors) and by `MCPFigJamAdapter.is_available()` no longer always
  returning `False` - `test_connect_board_demo_succeeds` now explicitly
  forces the demo path via monkeypatching, since it would otherwise be
  affected by whatever `FIGMA_ACCESS_TOKEN` happens to be in the test
  process's environment (which is loaded from the real `.env` as a side
  effect of `test_figjam.py` importing `app.py` for an unrelated test).

### Test evidence
- `python webapp/backend/test_figjam.py`: 12 checks, all passing.
- **Live, end to end, through the real Flask route:** `POST
  /api/figjam/connect` returned `is_demo: false`, a real board name ("Live
  FigJam board: Page 1"), and the exact 2 real items that existed on the
  board at that moment, with correct type/section/id mapping.
- Ran `/api/figjam/analyze` against this real data immediately afterward:
  the mock LLM provider's canned response cited evidence ids from the old
  demo dataset that don't exist among the real board's actual item ids, and
  the existing evidence-verification code correctly caught this and marked
  every theme/insight/contradiction `unsupported: true` - confirming the
  evidence-integrity check works correctly against genuinely real input,
  not just the fixture data it was originally tested against.
- **Not tested:** real Gemini reasoning over real board content end to end
  (the deployed/local `.env` currently has `LLM_PROVIDER=mock`); only the
  mock-provider path was verified against real board data this session.

## figmaconnecttry branch — Frontend polish: formatted reports, FigJam CTA highlighting

### What shipped
- Replaced the Pattern Analyzer's raw-markdown report display (a `<pre>`
  block showing literal `#`/`**`/`- ` characters, which read as source code
  rather than a finished report) with a hand-written `renderMarkdown()` in
  `app.js` that turns headings, bold labels, and flat/nested evidence
  bullets into real `<h2>/<h3>/<h4>/<ul>/<li>/<strong>/<em>` elements,
  styled with new prose typography in `style.css` (`.report-output`). The
  original markdown string is preserved separately for the "Download as
  .md" button, since `.innerHTML` no longer round-trips to the source text.
- Removed the red "Experimental branch..." banner paragraph from
  `figjam.html`, replaced with a calm `.pill`-based status indicator
  (`#board-status-pill`, generalized from the Pattern Analyzer's existing
  provider pill) that shows "Demo board" vs "Live FigJam board" once
  connected, instead of an alarming full-width warning box.
- Gave "Generate pairing code" and "Push to FigJam" a new `.btn-featured`
  style (solid accent fill, soft halo shadow) so the two actions that
  actually move the pipeline forward are visually distinct from secondary
  actions.

### What broke / what changed
- Nothing broke; this was presentation-only on top of already-tested
  endpoints. Re-ran the full backend test suite after the change (see test
  evidence) to confirm no regressions, since none were expected from a
  frontend-only change.

### Test evidence
- `python webapp/backend/test_figjam.py`: 12/12 passing, unchanged.
- Extracted `renderMarkdown`/`escapeHtml` from `app.js` via Node and ran
  them against a realistic `build_report()`-shaped sample: headings,
  bold labels, and nested evidence bullets all mapped to the correct
  HTML tags with the `nested` class applied only to indented bullets.
- Started the Flask server locally and confirmed via `curl` that the
  served `figjam.html` no longer contains `experiment-banner`, both CTA
  buttons carry `btn-featured`, and the served `app.js` contains
  `renderMarkdown`.

## figmaconnecttry branch — Fixed a cloud-mode pairing dead end

### What shipped
- Found and fixed a real UX dead end reported live by the user: in cloud
  mode, reading the live board requires the Desktop Bridge plugin to
  already be paired to the cloud relay, but the "Generate pairing code"
  button lived inside the results section (`#pair-figjam-box`), which only
  becomes visible after a successful connect + analyze. A first-time user
  in cloud mode had no way to ever generate a pairing code, since the
  button needed for pairing was gated behind the very connection pairing
  was supposed to unlock. Moved the pairing box into the connect section,
  directly above "Connect / Select FigJam", so it's the natural first step.

### What broke / what changed
- Root-caused a follow-up deploy issue reported by the user (same red error
  box, no pairing box visible even after the fix was pushed): compared the
  `Last-Modified` header of the deployed `figjam.html` against the pushed
  commit's timestamp and found the served file predated the push by ~20
  minutes, meaning the frontend Railway service had rebuilt but from a
  stale commit, not a caching issue. User confirmed and fixed the
  service's Source branch setting in the Railway dashboard; re-checked
  `Last-Modified` afterward and it matched the push exactly.

### Test evidence
- `python webapp/backend/test_figjam.py`: 12/12 passing (frontend-only
  change).
- `curl` against the live Railway deployment before and after the branch
  fix: `pair-figjam-box` moved from after `connect-btn` in the DOM to
  before it, confirmed via line-number `grep` on the served HTML both
  times.

## figmaconnecttry branch — Grounded FigJam analysis in real board data, not model self-report

### What shipped
- User reported (with screenshots) that after connecting a real FigJam
  board full of primary research (music/DJ-control interview stickies,
  participants P1-P6), the app's Themes/Insights panel showed content
  about "noise during exam periods" and "accessible entrance" instead -
  unrelated to the connected board. Investigated per the user's own
  A-F checklist (how FigJam data is retrieved, what's actually retrieved,
  how it's converted to research items, where the analysis prompt is
  built, whether mock data mixes with real data, where themes/insights are
  generated) before changing anything.
- **Found and fixed a real extraction bug** (not a prompt/hallucination
  issue): connected live to the user's actual board and found every
  item's `metadata.participant` was empty, even though the sticky notes
  clearly read "Participant P1 - Aditi...". `_PARTICIPANT_PATTERN` in
  `adapter.py` only matched a terse leading `P1:`/`[P1]` tag, not the full
  "Participant P1 - Name" header format the real board actually uses.
  Fixed the regex to recognize both forms.
- Replaced trust in Gemini's self-reported `strength` field with a new
  `_evidence_confidence()` in `research_agent.py`, computed entirely in
  code from the verified evidence count and the number of distinct
  participants it spans (`strong` needs 3+ items across 2+ participants,
  `medium` needs 2+ items, `limited` is a single item, `insufficient` is
  zero) - a model claiming "strong" is not itself evidence of anything.
  Themes/insights/contradictions with zero verified evidence now surface
  explicitly as "Insufficient evidence" in the UI instead of a
  plausible-looking but unsupported label.
- Added a "FigJam data received" debug panel to `figjam.html`/`figjam.js`
  (collapsible, under the overview) listing every retrieved item's id,
  type, section, participant, and original text verbatim, so the actual
  board content can be diff'd against what the AI analyzed, per the
  user's explicit ask for an extraction-debugging view.
- Evidence chips (`evidenceChips()` in `figjam.js`) now show the
  participant id and the original quote (as a hover tooltip) instead of a
  bare node id, using the full item list the connect endpoint was already
  returning but the frontend was previously discarding.
- Strengthened `ANALYZE_SYSTEM_PROMPT` to explicitly forbid drawing on
  general UX knowledge or "what a typical study on this topic would say"
  in place of the given material, and to omit a theme/insight entirely
  rather than fill a gap with a plausible-sounding unsupported claim.

### What broke / what changed
- While testing the fix live, confirmed the existing evidence-verification
  layer already does the hard part correctly: with the local mock LLM
  provider (unrelated to this fix, `LLM_PROVIDER=mock` in this machine's
  `.env`) returning its fixed canned "library noise" response against the
  real music-research board, every cited evidence id failed verification
  (they don't exist among the real board's actual Figma node ids) and the
  new confidence computation correctly marked everything `insufficient`
  rather than displaying it as grounded. This confirmed the validation
  layer the user asked for was already implemented and working; the actual
  defect was upstream, in extraction (the participant regex), not in
  prompt-time hallucination protection.
- Did not implement the full 10-stage extract/normalize/cluster/validate
  prompt pipeline requested; the existing 2-stage design (Pattern Finder +
  Research Critic) plus code-side evidence verification already enforces
  the same non-negotiable (nothing shown without a real, existing item id
  behind it) without multiplying LLM calls/cost. Flagged to the user as a
  deliberate scope decision, not an oversight.

### Test evidence
- Added `test_map_board_data_extracts_participant_from_full_header_line`
  confirming both the terse (`P1: ...`, `[P2] ...`) and full
  ("Participant P1 - Name") formats now extract correctly.
- Added `test_evidence_confidence_reflects_count_and_participant_diversity`
  covering all four confidence tiers and confirming participant coverage
  counts distinct participants, not one per evidence item.
- `python webapp/backend/test_figjam.py`: 14/14 passing.
- **Live, against the user's real connected board:** `POST
  /api/figjam/connect` returned `is_demo: false` and, after the regex fix,
  correct `{"participant": "P1"}` through `"P5"` metadata for the real
  interview stickies (previously all empty). Ran `/api/figjam/analyze`
  against this real data with the mock provider and confirmed every
  resulting theme/insight showed `confidence: "insufficient"` with empty
  evidence, correctly rejecting the mock's out-of-topic canned claims
  rather than displaying them.
- **Not tested:** real Gemini reasoning end to end against this real board
  (same `LLM_PROVIDER=mock` local-environment limitation as the prior
  commit); only the mock-provider path plus the evidence-verification/
  confidence logic around it was exercised against real board data.
