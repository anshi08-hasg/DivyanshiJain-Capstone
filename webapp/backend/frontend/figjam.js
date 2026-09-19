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

const askSection = document.getElementById("ask-section");
const askTranscript = document.getElementById("ask-transcript");
const askInput = document.getElementById("ask-input");
const askBtn = document.getElementById("ask-btn");
const askError = document.getElementById("ask-error");

let state = { themes: [], insights: [], contradictions: [], gaps: [], opportunities: [] };

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
    return `<span class="badge">Unsupported / needs verification</span>`;
  }
  return ids.map((id) => `<span class="badge">${escapeHtml(id)}</span>`).join(" ");
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
      <span class="badge">strength: ${escapeHtml(theme.strength)}</span>
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
      <span class="badge">strength: ${escapeHtml(insight.strength)}</span>
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
    <div class="meta">${evidenceChips(con.evidence)}</div>
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
