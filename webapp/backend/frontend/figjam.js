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

function makeDecisionRow(item, onChange) {
  const row = document.createElement("div");
  row.className = "decision-row";
  ["approve", "edit", "challenge", "reject"].forEach((decision) => {
    const btn = document.createElement("button");
    btn.textContent = decision[0].toUpperCase() + decision.slice(1);
    btn.dataset.decision = decision;
    btn.className = item.decision === decision ? "active" : "";
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

function renderInsightCard(insight) {
  const card = document.createElement("div");
  card.className = `card decision-${insight.decision || "pending"}`;
  card.innerHTML = `
    <h4>${escapeHtml(insight.id)}: ${escapeHtml(insight.statement)}</h4>
    <div class="meta">
      ${verdictBadge(insight)}
      ${confidenceBadge(insight)}
      ${evidenceChips(insight.evidence)}
    </div>
    <div class="critic-note"><strong>Research Critic:</strong> ${escapeHtml(insight.verdict_note || "")}</div>
  `;

  if (insight.decision === "edit") {
    const editArea = document.createElement("textarea");
    editArea.className = "edit-field";
    editArea.rows = 2;
    editArea.value = insight.statement;
    editArea.addEventListener("input", () => { insight.statement = editArea.value; });
    card.appendChild(editArea);
  }

  card.appendChild(makeDecisionRow(insight, (decision) => {
    insight.decision = decision;
    renderInsights();
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

runAnalysisBtn.addEventListener("click", async () => {
  analyzeError.hidden = true;
  setBusy(runAnalysisBtn, true, "Analyze with Gemini");

  try {
    const res = await fetch(apiUrl("/api/figjam/analyze"), { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Analysis failed.");

    state.themes = data.themes || [];
    state.insights = (data.insights || []).map((i) => ({ ...i, decision: null }));
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

    renderActivity(data.activity);
    resultsSection.hidden = false;
    personasSection.hidden = false;
    askSection.hidden = false;
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    analyzeError.textContent = err.message;
    analyzeError.hidden = false;
  } finally {
    setBusy(runAnalysisBtn, false, "Analyze with Gemini");
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
    <div class="meta">${confidenceBadge(persona)}${evidenceChips(persona.evidence)}</div>
  `;
  return card;
}

function appendStatusStep(label) {
  personasStatusList.hidden = false;
  const li = document.createElement("li");
  li.innerHTML = `${escapeHtml(label)}<span class="activity-time"></span>`;
  personasStatusList.appendChild(li);
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
    appendStatusStep("→ Sending to Gemini for behavioural clustering...");

    const res = await fetch(apiUrl("/api/figjam/generate-personas"), { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not generate personas.");

    // Replace the optimistic pre-request steps with the backend's real,
    // just-executed activity trail (counts of candidates/drops are computed
    // server-side from the actual Gemini response, not guessed here).
    personasStatusList.innerHTML = "";
    (data.activity || []).slice(-4).forEach((entry) => appendStatusStep(`✓ ${entry.label}`));

    state.personas = data.personas || [];
    state.personas.forEach((p) => personasList.appendChild(renderPersonaCard(p)));

    pushPersonasBar.hidden = false;
  } catch (err) {
    appendStatusStep(`✗ ${err.message}`);
    personasError.textContent = err.message;
    personasError.hidden = false;
  } finally {
    setBusy(generatePersonasBtn, false, "Generate Personas in FigJam");
  }
});

pushPersonasBtn.addEventListener("click", async () => {
  pushPersonasError.hidden = true;
  pushPersonasSuccess.hidden = true;
  setBusy(pushPersonasBtn, true, "Push Personas to FigJam");

  try {
    appendStatusStep("Creating FigJam layout...");
    const res = await fetch(apiUrl("/api/figjam/push-personas"), { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not push personas to FigJam.");

    appendStatusStep("Pushed to FigJam ✓");
    pushPersonasSuccess.textContent = `Created ${data.stickies_created} element(s) across ${data.personas.length} persona card(s): ${data.personas.join(", ")}.`;
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
