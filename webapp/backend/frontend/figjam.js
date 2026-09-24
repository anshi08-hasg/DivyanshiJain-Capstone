const connectBtn = document.getElementById("connect-btn");
const connectError = document.getElementById("connect-error");

const overviewSection = document.getElementById("overview-section");
const overviewGrid = document.getElementById("overview-grid");

const activitySection = document.getElementById("activity-section");
const activityList = document.getElementById("activity-list");
const runAnalysisBtn = document.getElementById("run-analysis-btn");
const analyzeError = document.getElementById("analyze-error");

const resultsSection = document.getElementById("results-section");
const themesList = document.getElementById("themes-list");
const insightsList = document.getElementById("insights-list");
const contradictionsList = document.getElementById("contradictions-list");
const gapsList = document.getElementById("gaps-list");
const opportunitiesList = document.getElementById("opportunities-list");

const personasSection = document.getElementById("personas-section");
const personasList = document.getElementById("personas-list");
const personasStatusList = document.getElementById("personas-status-list");
const generatePersonasBtn = document.getElementById("generate-personas-btn");
const personasError = document.getElementById("personas-error");
const pushPersonasBar = document.getElementById("push-personas-bar");
const pushPersonasBtn = document.getElementById("push-personas-btn");
const pushPersonasError = document.getElementById("push-personas-error");
const pushPersonasSuccess = document.getElementById("push-personas-success");

const personaPreviewsSection = document.getElementById("persona-previews-section");
const personaPreviewsList = document.getElementById("persona-previews-list");
const personaPreviewsError = document.getElementById("persona-previews-error");

const askSection = document.getElementById("ask-section");
const askTranscript = document.getElementById("ask-transcript");
const askInput = document.getElementById("ask-input");
const askBtn = document.getElementById("ask-btn");
const askError = document.getElementById("ask-error");

let state = { themes: [], insights: [], contradictions: [], gaps: [], opportunities: [], items: {}, personas: [] };

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function setBusy(button, busy, idleLabel) {
  const label = button.querySelector(".btn-label");
  const spinner = button.querySelector(".spinner");
  button.disabled = busy;
  spinner.hidden = !busy;
  label.textContent = busy ? "Working" : idleLabel;
}

function renderActivity(activity) {
  activityList.innerHTML = activity.map((entry) =>
    `<li>${escapeHtml(entry.label)}<span class="activity-time">${escapeHtml(entry.at)}</span></li>`
  ).join("");
}

// Shared by the "Connect / Select FigJam" click handler and the page-load
// rehydration path below (init()) - a successful connect (or a rehydrated
// prior connection) resets analysis/personas display state, since any
// results already on screen from a different connection are now stale.
function applyConnectResult(data) {
  resultsSection.hidden = true;
  personasSection.hidden = true;
  askSection.hidden = true;
  personasList.innerHTML = "";
  personasStatusList.innerHTML = "";
  personasStatusList.hidden = true;
  pushPersonasBar.hidden = true;
  personaPreviewsSection.hidden = true;
  personaPreviewsList.innerHTML = "";
  personaPreviewsError.hidden = true;
  state.personas = [];

  overviewGrid.innerHTML = [
    ["Board", data.overview.board_name],
    ["Research items", data.overview.research_items],
    ["Sections", data.overview.sections],
    ["Participants", data.overview.participants ?? "n/a"],
  ].map(([label, value]) =>
    `<div class="overview-tile"><div class="value">${escapeHtml(String(value))}</div><div class="label">${escapeHtml(label)}</div></div>`
  ).join("");

  overviewSection.hidden = false;
  activitySection.hidden = false;
  renderActivity(data.activity);

  state.items = {};
  (data.items || []).forEach((item) => { state.items[item.id] = item; });
  renderDebugPanel(data.items || []);

  const statusPill = document.getElementById("board-status-pill");
  const statusLabel = document.getElementById("board-status-label");
  if (statusPill && statusLabel) {
    statusPill.classList.toggle("is-demo", data.is_demo);
    statusPill.classList.toggle("is-live", !data.is_demo);
    statusLabel.textContent = data.is_demo ? "Demo board" : "Live FigJam board";
    statusPill.hidden = false;
  }
}

connectBtn.addEventListener("click", async () => {
  connectError.hidden = true;
  setBusy(connectBtn, true, "Connect / Select FigJam");

  try {
    const res = await fetch(apiUrl("/api/figjam/connect"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board_ref: "default" }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not connect to FigJam.");
    applyConnectResult(data);
  } catch (err) {
    connectError.textContent = err.message;
    connectError.hidden = false;
  } finally {
    setBusy(connectBtn, false, "Connect / Select FigJam");
  }
});

function verdictBadge(insight) {
  const verdict = insight.verdict || "weak";
  return `<span class="verdict-badge verdict-${verdict}">${verdict}</span>`;
}

function evidenceChips(ids) {
  if (!ids || ids.length === 0) {
    return `<span class="badge badge-insufficient">Insufficient evidence</span>`;
  }
  return ids.map((id) => {
    const item = state.items[id];
    const label = item && item.metadata && item.metadata.participant
      ? `${id} (${item.metadata.participant})`
      : id;
    const quote = item ? item.content : "";
    return `<span class="badge" title="${escapeHtml(quote)}">${escapeHtml(label)}</span>`;
  }).join(" ");
}

function confidenceBadge(entry) {
  const confidence = entry.confidence || "insufficient";
  const count = entry.evidence_count ?? (entry.evidence || []).length;
  const participants = entry.participant_coverage || [];
  const coverage = participants.length > 0 ? `, ${participants.join(", ")}` : "";
  return `<span class="badge confidence-${confidence}">confidence: ${escapeHtml(confidence)} (${count} item${count === 1 ? "" : "s"}${escapeHtml(coverage)})</span>`;
}

function renderDebugPanel(items) {
  const section = document.getElementById("debug-section");
  const list = document.getElementById("debug-items");
  const countEl = document.getElementById("debug-count");
  if (!section || !list) return;

  const researchNodes = items.filter((i) => i.type !== "section");
  countEl.textContent = `Total nodes: ${items.length} | Research nodes: ${researchNodes.length} | Sections: ${items.length - researchNodes.length}`;

  list.innerHTML = items.map((item) => `
    <tr>
      <td>${escapeHtml(item.id)}</td>
      <td>${escapeHtml(item.type)}</td>
      <td>${escapeHtml(item.section || "")}</td>
      <td>${escapeHtml((item.metadata && item.metadata.participant) || "")}</td>
      <td>${escapeHtml(item.content)}</td>
    </tr>
  `).join("");

  section.hidden = false;
}

// Maps a decision button's verb ("approve") to the past-tense status the
// backend actually stores ("approved") - "edit" is handled separately
// below, since clicking it only opens the editor, it doesn't submit a
// review by itself (that happens on "Save edit").
const DECISION_TO_STATUS = { approve: "approved", edit: "edited", challenge: "challenged", reject: "rejected" };

function makeDecisionRow(item, onChange) {
  const row = document.createElement("div");
  row.className = "decision-row";
  ["approve", "edit", "challenge"].forEach((decision) => {
    const btn = document.createElement("button");
    btn.textContent = decision[0].toUpperCase() + decision.slice(1);
    btn.dataset.decision = decision;
    btn.className = item.status === DECISION_TO_STATUS[decision] ? "active" : "";
    btn.addEventListener("click", () => onChange(decision));
    row.appendChild(btn);
  });
  return row;
}

function renderThemeCard(theme) {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <h4>${escapeHtml(theme.id)}: ${escapeHtml(theme.name)}</h4>
    <div class="meta">
      ${confidenceBadge(theme)}
      ${evidenceChips(theme.evidence)}
    </div>
    ${theme.rationale ? `<div class="interpretation">Rationale (inference): ${escapeHtml(theme.rationale)}</div>` : ""}
  `;
  return card;
}

const STATUS_LABELS = { approved: "Approved", edited: "Edited", challenged: "Challenged", rejected: "Rejected" };

// Persists a review decision to the backend (POST /api/figjam/insights/
// <id>/review) so it survives a page reload - the server-side analysis
// dict is the one source of truth, never just this in-memory JS object.
async function submitInsightReview(insight, errorEl, status, editedText) {
  errorEl.hidden = true;
  try {
    const res = await fetch(apiUrl(`/api/figjam/insights/${encodeURIComponent(insight.id)}/review`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, edited_text: editedText }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not save this review decision.");
    Object.assign(insight, data.insight);
    insight._editing = false;
    renderInsights();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  }
}

function renderInsightCard(insight) {
  const card = document.createElement("div");
  card.className = `card decision-${insight.status || "pending"}`;

  const effectiveText = insight.status === "edited" && insight.edited_statement ? insight.edited_statement : insight.statement;
  const statusLabel = STATUS_LABELS[insight.status];

  card.innerHTML = `
    <h4>${escapeHtml(insight.id)}: ${escapeHtml(effectiveText)}</h4>
    <div class="meta">
      ${statusLabel ? `<span class="badge status-badge status-${insight.status}">${escapeHtml(statusLabel.toUpperCase())}</span>` : ""}
      ${verdictBadge(insight)}
      ${confidenceBadge(insight)}
      ${evidenceChips(insight.evidence)}
    </div>
    ${insight.status === "edited" ? `<div class="edited-note">Researcher-edited &middot; originally: "${escapeHtml(insight.statement)}"</div>` : ""}
    <div class="critic-note"><strong>Research Critic:</strong> ${escapeHtml(insight.verdict_note || "")}</div>
    <p class="insight-review-error error-banner" hidden></p>
  `;

  const errorEl = card.querySelector(".insight-review-error");

  if (insight._editing) {
    const editArea = document.createElement("textarea");
    editArea.className = "edit-field";
    editArea.rows = 2;
    editArea.value = effectiveText;
    card.appendChild(editArea);

    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "btn btn-secondary";
    saveBtn.textContent = "Save edit";
    saveBtn.addEventListener("click", () => submitInsightReview(insight, errorEl, "edited", editArea.value));
    card.appendChild(saveBtn);
  }

  card.appendChild(makeDecisionRow(insight, (decision) => {
    if (decision === "edit") {
      insight._editing = true;
      renderInsights();
      return;
    }
    submitInsightReview(insight, errorEl, DECISION_TO_STATUS[decision], null);
  }));

  return card;
}

function renderContradictionCard(con) {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <h4>${escapeHtml(con.id)}</h4>
    <div>${escapeHtml(con.description)}</div>
    <div class="meta">${confidenceBadge(con)}${evidenceChips(con.evidence)}</div>
  `;
  return card;
}

function renderInsights() {
  insightsList.innerHTML = "";
  state.insights.forEach((i) => insightsList.appendChild(renderInsightCard(i)));
}

// Shared by the "Analyze research" click handler and the page-load
// rehydration path below (init()) - `data` is the same shape both
// /api/figjam/analyze and /api/figjam/state's "analysis" field return, so
// one function renders either. Insight review status (status/
// edited_statement) comes straight from the server now - it's no longer a
// frontend-only "decision" field that a reload would silently lose.
function applyAnalyzeResult(data) {
  state.themes = data.themes || [];
  state.insights = data.insights || [];
  state.contradictions = data.contradictions || [];
  state.gaps = data.research_gaps || [];
  state.opportunities = data.design_opportunities || [];

  themesList.innerHTML = "";
  state.themes.forEach((t) => themesList.appendChild(renderThemeCard(t)));

  renderInsights();

  contradictionsList.innerHTML = "";
  if (state.contradictions.length === 0) {
    contradictionsList.innerHTML = `<p class="panel-sub">None found.</p>`;
  } else {
    state.contradictions.forEach((c) => contradictionsList.appendChild(renderContradictionCard(c)));
  }

  gapsList.innerHTML = state.gaps.map((g) => `<li>${escapeHtml(g)}</li>`).join("") || `<li>None identified.</li>`;
  opportunitiesList.innerHTML = state.opportunities.map((o) => `<li>${escapeHtml(o)}</li>`).join("") || `<li>None identified.</li>`;

  resultsSection.hidden = false;
  personasSection.hidden = false;
  askSection.hidden = false;
}

runAnalysisBtn.addEventListener("click", async () => {
  analyzeError.hidden = true;
  setBusy(runAnalysisBtn, true, "Analyze research");

  try {
    const res = await fetch(apiUrl("/api/figjam/analyze"), { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Analysis failed.");

    applyAnalyzeResult(data);
    renderActivity(data.activity);
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    analyzeError.textContent = err.message;
    analyzeError.hidden = false;
  } finally {
    setBusy(runAnalysisBtn, false, "Analyze research");
  }
});

askBtn.addEventListener("click", async () => {
  const question = askInput.value.trim();
  askError.hidden = true;
  if (!question) return;

  const qTurn = document.createElement("div");
  qTurn.className = "ask-turn question";
  qTurn.textContent = question;
  askTranscript.appendChild(qTurn);
  askInput.value = "";

  askBtn.disabled = true;
  try {
    const res = await fetch(apiUrl("/api/figjam/ask"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not answer that question.");

    const aTurn = document.createElement("div");
    aTurn.className = `ask-turn answer${data.grounded ? "" : " not-grounded"}`;
    aTurn.innerHTML = `
      <div>${escapeHtml(data.answer)}</div>
      <div class="evidence-chips">${evidenceChips(data.evidence)}</div>
    `;
    askTranscript.appendChild(aTurn);
    askTranscript.scrollTop = askTranscript.scrollHeight;
  } catch (err) {
    askError.textContent = err.message;
    askError.hidden = false;
  } finally {
    askBtn.disabled = false;
  }
});

askInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") askBtn.click();
});

const pairFigjamBox = document.getElementById("pair-figjam-box");
const pairFigjamBtn = document.getElementById("pair-figjam-btn");
const pairFigjamResult = document.getElementById("pair-figjam-result");
const pairFigjamError = document.getElementById("pair-figjam-error");

fetch(apiUrl("/api/figjam/mode"))
  .then((res) => res.json())
  .then((data) => { pairFigjamBox.hidden = data.mode !== "cloud"; })
  .catch(() => {});

pairFigjamBtn.addEventListener("click", async () => {
  pairFigjamError.hidden = true;
  pairFigjamResult.hidden = true;
  setBusy(pairFigjamBtn, true, "Generate pairing code");

  try {
    const res = await fetch(apiUrl("/api/figjam/pair"), { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not generate a pairing code.");

    pairFigjamResult.innerHTML = `
      <strong>Code: <span id="pair-code-text">${escapeHtml(data.pairingCode)}</span></strong>
      <button type="button" id="pair-copy-btn" class="btn btn-ghost">Copy</button>
      (expires in ${escapeHtml(data.expiresIn)})<br>${data.instructions.map(escapeHtml).join("<br>")}
    `;
    pairFigjamResult.hidden = false;

    const copyBtn = document.getElementById("pair-copy-btn");
    const copyCode = async () => {
      try {
        await navigator.clipboard.writeText(data.pairingCode);
        copyBtn.textContent = "Copied!";
      } catch {
        copyBtn.textContent = "Copy failed, select manually";
      }
      setTimeout(() => { copyBtn.textContent = "Copy"; }, 2000);
    };
    copyBtn.addEventListener("click", copyCode);
    copyCode(); // also copy automatically as soon as the code is generated
  } catch (err) {
    pairFigjamError.textContent = err.message;
    pairFigjamError.hidden = false;
  } finally {
    setBusy(pairFigjamBtn, false, "Generate pairing code");
  }
});

const pushFigjamBtn = document.getElementById("push-figjam-btn");
const pushFigjamError = document.getElementById("push-figjam-error");
const pushFigjamSuccess = document.getElementById("push-figjam-success");

pushFigjamBtn.addEventListener("click", async () => {
  pushFigjamError.hidden = true;
  pushFigjamSuccess.hidden = true;
  setBusy(pushFigjamBtn, true, "Push to FigJam");

  try {
    const res = await fetch(apiUrl("/api/figjam/push-to-figjam"), { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not push to FigJam.");

    pushFigjamSuccess.textContent = `Created ${data.stickies_created} sticky note(s) across ${data.sections.length} section(s): ${data.sections.join(", ")}.`;
    pushFigjamSuccess.hidden = false;
    data.activity.forEach((label) => {
      const li = document.createElement("li");
      li.innerHTML = `${escapeHtml(label)}<span class="activity-time"></span>`;
      activityList.appendChild(li);
    });
  } catch (err) {
    pushFigjamError.textContent = err.message;
    pushFigjamError.hidden = false;
  } finally {
    setBusy(pushFigjamBtn, false, "Push to FigJam");
  }
});

function personaInitials(name) {
  return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
}

function personaList(items, emptyText) {
  const list = items && items.length ? items : [emptyText];
  return list.map((i) => `<li>${escapeHtml(i)}</li>`).join("");
}

// A short, human line that establishes the persona is research-backed
// without exposing raw evidence ids/participant counts as the headline -
// those live one click away in the "View Research Evidence" panel, using
// the same real evidence/confidence data, never a re-derived or invented
// summary of it.
function personaProvenanceLine(persona) {
  const participantCount = (persona.participant_coverage || []).length;
  if (participantCount > 0) {
    return `Research-backed · Based on ${participantCount} participant${participantCount === 1 ? "" : "s"}`;
  }
  return (persona.evidence || []).length > 0 ? "Research-backed" : "Evidence pending review";
}

function renderPersonaCard(persona) {
  const card = document.createElement("div");
  card.className = "persona-card";

  const profile = persona.profile || {};
  const profileParts = [
    ["Role", profile.role], ["Age", profile.age],
    ["Location", profile.location], ["Digital behaviour", profile.digital_behaviour],
  ].map(([label, value]) => `<span>${escapeHtml(label)}: ${escapeHtml(value || "Not identified in research")}</span>`);

  const quote = persona.representative_quote || {};
  const quoteHtml = quote.text
    ? `"${escapeHtml(quote.text)}"${quote.is_verbatim ? "" : `<span class="synthesized-tag">Synthesized statement, not a direct quote</span>`}`
    : `<em>No representative quote identified in research.</em>`;

  card.innerHTML = `
    <div class="persona-head">
      <div class="persona-avatar">${escapeHtml(personaInitials(persona.name))}</div>
      <div>
        <h4>${escapeHtml(persona.name || "Unnamed persona")}</h4>
        <p>${escapeHtml(persona.short_description || "")}</p>
      </div>
    </div>
    <div class="persona-profile">${profileParts.join("")}</div>
    <div class="persona-columns">
      <div><h5>Goals</h5><ul>${personaList(persona.goals, "Not identified in research")}</ul></div>
      <div><h5>Pain points</h5><ul>${personaList(persona.pain_points, "Not identified in research")}</ul></div>
    </div>
    <div class="persona-columns">
      <div><h5>Behaviours</h5><ul>${personaList(persona.behaviours, "Not identified in research")}</ul></div>
      <div><h5>Needs</h5><ul>${personaList(persona.needs, "Not identified in research")}</ul></div>
    </div>
    <div class="persona-block"><h5>Motivations</h5><ul>${personaList(persona.motivations, "Not identified in research")}</ul></div>
    <div class="persona-quote">${quoteHtml}</div>
    <div class="persona-provenance">
      <span class="provenance-line">${escapeHtml(personaProvenanceLine(persona))}</span>
      <button type="button" class="evidence-toggle" aria-expanded="false">View Research Evidence</button>
    </div>
    <div class="persona-evidence-panel" hidden>
      <div class="evidence-panel-row">
        <span class="evidence-panel-label">Evidence strength</span>
        ${confidenceBadge(persona)}
      </div>
      <div class="evidence-panel-row">
        <span class="evidence-panel-label">Supporting participants</span>
        <span>${escapeHtml((persona.participant_coverage || []).join(", ") || "Not identified in research")}</span>
      </div>
      <div class="evidence-panel-row">
        <span class="evidence-panel-label">Evidence</span>
        <span class="evidence-chip-list">${evidenceChips(persona.evidence)}</span>
      </div>
    </div>
  `;

  const evidenceToggle = card.querySelector(".evidence-toggle");
  const evidencePanel = card.querySelector(".persona-evidence-panel");
  evidenceToggle.addEventListener("click", () => {
    const expanded = evidenceToggle.getAttribute("aria-expanded") === "true";
    evidenceToggle.setAttribute("aria-expanded", String(!expanded));
    evidenceToggle.textContent = expanded ? "View Research Evidence" : "Hide Research Evidence";
    evidencePanel.hidden = expanded;
  });

  return card;
}

// Builds the downloadable persona image previews. This reuses the exact
// persona objects already returned by /api/figjam/generate-personas (the
// same data renderPersonaCard() above already displays) - no second Groq
// request, one canonical PersonaRenderer (persona_renderer.js) decides the
// visual design, the persona data only decides the content.
function renderPersonaPreviews(personas) {
  personaPreviewsList.innerHTML = "";
  personaPreviewsError.hidden = true;

  if (!personas || personas.length === 0) {
    personaPreviewsError.textContent = "Persona preview is unavailable because persona generation did not complete.";
    personaPreviewsError.hidden = false;
    personaPreviewsSection.hidden = false;
    return;
  }

  personas.forEach((persona) => {
    const card = document.createElement("div");
    card.className = "persona-preview-card";

    const title = document.createElement("h4");
    title.textContent = persona.name || "Unnamed persona";
    card.appendChild(title);

    const canvasWrap = document.createElement("div");
    canvasWrap.className = "persona-preview-canvas-wrap";
    const canvas = document.createElement("canvas");
    canvas.className = "persona-preview-canvas";
    canvasWrap.appendChild(canvas);
    card.appendChild(canvasWrap);

    try {
      renderPersonaToCanvas(persona, canvas);
    } catch (err) {
      canvasWrap.remove();
      const errorP = document.createElement("p");
      errorP.className = "persona-preview-card-error";
      errorP.textContent = "Persona preview is unavailable because persona generation did not complete.";
      card.appendChild(errorP);
      personaPreviewsList.appendChild(card);
      return;
    }

    const downloadBtn = document.createElement("button");
    downloadBtn.type = "button";
    downloadBtn.className = "btn btn-secondary";
    downloadBtn.textContent = "Download Persona PNG";
    downloadBtn.addEventListener("click", () => {
      canvas.toBlob((blob) => {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = sanitizePersonaFilename(persona.name);
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      }, "image/png");
    });
    card.appendChild(downloadBtn);

    personaPreviewsList.appendChild(card);
  });

  personaPreviewsSection.hidden = false;
}

function appendStatusStep(label) {
  personasStatusList.hidden = false;
  const li = document.createElement("li");
  li.innerHTML = `${escapeHtml(label)}<span class="activity-time"></span>`;
  personasStatusList.appendChild(li);
}

// Shared by the "Generate Personas in FigJam" click handler and the
// page-load rehydration path below (init()).
function applyPersonasResult(personas) {
  personasList.innerHTML = "";
  state.personas = personas || [];
  state.personas.forEach((p) => personasList.appendChild(renderPersonaCard(p)));
  renderPersonaPreviews(state.personas);
  if (state.personas.length) pushPersonasBar.hidden = false;
}

generatePersonasBtn.addEventListener("click", async () => {
  personasError.hidden = true;
  pushPersonasBar.hidden = true;
  personasList.innerHTML = "";
  personasStatusList.innerHTML = "";
  personasStatusList.hidden = true;
  setBusy(generatePersonasBtn, true, "Generate Personas in FigJam");

  const items = Object.values(state.items);
  const participantCount = new Set(
    items.map((i) => i.metadata && i.metadata.participant).filter(Boolean)
  ).size;
  const researchItemCount = items.filter((i) => i.type !== "section").length;

  try {
    appendStatusStep(`✓ Research loaded (${researchItemCount} research item(s))`);
    appendStatusStep(`✓ Participants identified (${participantCount})`);
    appendStatusStep("→ Sending to the LLM for behavioural clustering...");

    const res = await fetch(apiUrl("/api/figjam/generate-personas"), { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not generate personas.");

    // Replace the optimistic pre-request steps with the backend's real,
    // just-executed activity trail (counts of candidates/drops are computed
    // server-side from the actual LLM response, not guessed here).
    personasStatusList.innerHTML = "";
    (data.step_activity || []).forEach((entry) => appendStatusStep(`✓ ${entry.label}`));

    applyPersonasResult(data.personas);
  } catch (err) {
    appendStatusStep(`✗ ${err.message}`);
    personasError.textContent = err.message;
    personasError.hidden = false;
    personaPreviewsSection.hidden = true;
  } finally {
    setBusy(generatePersonasBtn, false, "Generate Personas in FigJam");
  }
});

pushPersonasBtn.addEventListener("click", async () => {
  pushPersonasError.hidden = true;
  pushPersonasSuccess.hidden = true;
  personasStatusList.innerHTML = "";
  setBusy(pushPersonasBtn, true, "Push Personas to FigJam");

  try {
    appendStatusStep("Creating FigJam layout...");
    const res = await fetch(apiUrl("/api/figjam/push-personas"), { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not push personas to FigJam.");

    appendStatusStep("Pushed to FigJam ✓");
    pushPersonasSuccess.textContent = `Created ${data.elements_created} element(s) across ${data.personas.length} persona card(s): ${data.personas.join(", ")}.`;
    pushPersonasSuccess.hidden = false;
    data.activity.forEach((label) => {
      const li = document.createElement("li");
      li.innerHTML = `${escapeHtml(label)}<span class="activity-time"></span>`;
      activityList.appendChild(li);
    });
  } catch (err) {
    pushPersonasError.textContent = err.message;
    pushPersonasError.hidden = false;
  } finally {
    setBusy(pushPersonasBtn, false, "Push Personas to FigJam");
  }
});

// Rehydrates the page from server-side session state on load, so a browser
// reload doesn't lose a connected board, its analysis (including every
// insight's researcher-review status), or generated personas - none of
// that ever lived only in this file's in-memory `state`, only the server's
// _figjam_state does, and this just re-fetches it. A fresh visit (nothing
// connected yet) leaves the page exactly at its normal starting state.
async function init() {
  try {
    const res = await fetch(apiUrl("/api/figjam/state"));
    const data = await res.json();
    if (!res.ok || !data.connected) return;

    applyConnectResult({
      overview: data.overview, activity: data.activity, is_demo: data.is_demo, items: data.items,
    });

    if (data.analysis) {
      applyAnalyzeResult(data.analysis);
    }

    if (data.personas && data.personas.length) {
      applyPersonasResult(data.personas);
    }
  } catch (err) {
    // A failed rehydration just leaves the page at its normal "Connect
    // FigJam" starting state - the researcher can always reconnect manually.
  }
}

init();
