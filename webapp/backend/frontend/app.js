const participantsContainer = document.getElementById("participants");
const participantTemplate = document.getElementById("participant-template");
const inputError = document.getElementById("input-error");

const resultsSection = document.getElementById("results-section");
const patternsList = document.getElementById("patterns-list");
const findingsList = document.getElementById("findings-list");
const flagsBox = document.getElementById("flags-box");
const flagsList = document.getElementById("flags-list");

const reportSection = document.getElementById("report-section");
const reportOutput = document.getElementById("report-output");

const steps = [...document.querySelectorAll(".step")];
const providerPill = document.getElementById("provider-pill");
const providerLabel = document.getElementById("provider-label");

// In-memory state for the current analysis run, keyed by item id so edits
// and decisions survive re-rendering.
let state = { patterns: [], findings: [], flags: [] };

function setStep(n) {
  steps.forEach((el) => {
    const i = Number(el.dataset.step);
    el.classList.toggle("is-active", i === n);
    el.classList.toggle("is-done", i < n);
  });
}

async function loadProvider() {
  try {
    const res = await fetch(apiUrl("/api/provider"));
    const data = await res.json();
    const name = data.provider || "mock";
    providerLabel.textContent = name === "mock" ? "Offline mock" : name[0].toUpperCase() + name.slice(1);
    providerPill.classList.toggle("is-mock", name === "mock");
    providerPill.classList.toggle("is-live", name !== "mock");
  } catch {
    providerLabel.textContent = "Provider unknown";
  }
}

loadProvider();

function addParticipantBlock() {
  const node = participantTemplate.content.cloneNode(true);
  node.querySelector(".remove-participant").addEventListener("click", (e) => {
    e.target.closest(".participant-card").remove();
  });
  participantsContainer.appendChild(node);
}

document.getElementById("add-participant").addEventListener("click", addParticipantBlock);

// Start with two participants: pattern-finding requires at least two.
addParticipantBlock();
addParticipantBlock();

function collectParticipants() {
  return [...participantsContainer.querySelectorAll(".participant-card")].map((block) => ({
    participant_id: block.querySelector(".participant-id").value.trim(),
    notes: block.querySelector(".participant-notes").value.trim(),
  })).filter((p) => p.participant_id && p.notes);
}

function renderEvidence(evidence) {
  return evidence.map((e) =>
    `<div class="evidence-item">[${e.participant_id} / ${e.source_id}, ${e.source_type}]: "${e.text}"</div>`
  ).join("");
}

function renderContradictions(contradictions) {
  if (!contradictions || contradictions.length === 0) return "";
  const items = contradictions.map((c) =>
    `<div class="contradiction">[${c.participant_id} / ${c.source_id}]: "${c.text}"</div>`
  ).join("");
  return `<div class="contradictions"><strong>Contradictions</strong>${items}</div>`;
}

function makeDecisionRow(item, onChange) {
  const row = document.createElement("div");
  row.className = "decision-row";

  ["approve", "edit", "reject"].forEach((decision) => {
    const btn = document.createElement("button");
    btn.textContent = decision[0].toUpperCase() + decision.slice(1);
    btn.dataset.decision = decision;
    btn.className = item.decision === decision ? "active" : "";
    btn.addEventListener("click", () => onChange(decision));
    row.appendChild(btn);
  });

  return row;
}

function renderPatternCard(pattern) {
  const card = document.createElement("div");
  card.className = `card decision-${pattern.decision || "pending"}`;

  const editableLabel = pattern.decision === "edit";

  card.innerHTML = `
    <h4>${pattern.id}: ${escapeHtml(pattern.label)}</h4>
    <div class="meta">
      <span class="badge">${escapeHtml(pattern.category)}</span>
      <span class="badge">${escapeHtml(pattern.participant_coverage)}</span>
      <span class="badge">${escapeHtml(pattern.evidence_strength)}</span>
    </div>
    <div class="evidence">${renderEvidence(pattern.evidence || [])}</div>
    ${pattern.interpretation ? `<div class="interpretation">Interpretation (inference): ${escapeHtml(pattern.interpretation)}</div>` : ""}
    ${renderContradictions(pattern.contradictions)}
  `;

  if (editableLabel) {
    const editArea = document.createElement("textarea");
    editArea.className = "edit-field";
    editArea.rows = 2;
    editArea.value = pattern.label;
    editArea.addEventListener("input", () => {
      pattern.label = editArea.value;
    });
    card.appendChild(editArea);
  }

  const decisionRow = makeDecisionRow(pattern, (decision) => {
    pattern.decision = decision;
    renderResults();
  });
  card.appendChild(decisionRow);

  return card;
}

function renderFindingCard(finding) {
  const card = document.createElement("div");
  card.className = `card decision-${finding.decision || "pending"}`;
  card.innerHTML = `
    <div class="meta">
      <span class="badge">${finding.participant_id} / ${finding.source_id}</span>
      <span class="badge">${escapeHtml(finding.category)}</span>
    </div>
    <div>"${escapeHtml(finding.text)}"</div>
  `;

  const decisionRow = makeDecisionRow(finding, (decision) => {
    finding.decision = decision;
    renderResults();
  });
  card.appendChild(decisionRow);

  return card;
}

function renderResults() {
  patternsList.innerHTML = "";
  state.patterns.forEach((p) => patternsList.appendChild(renderPatternCard(p)));

  findingsList.innerHTML = "";
  state.findings.forEach((f) => findingsList.appendChild(renderFindingCard(f)));

  if (state.flags.length > 0) {
    flagsBox.hidden = false;
    flagsList.innerHTML = state.flags.map((f) => `<li>${escapeHtml(f)}</li>`).join("");
  } else {
    flagsBox.hidden = true;
  }

  resultsSection.hidden = false;
  setStep(2);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

const runButton = document.getElementById("run-analysis");
const runButtonLabel = runButton.querySelector(".btn-label");
const runButtonSpinner = runButton.querySelector(".spinner");

document.getElementById("run-analysis").addEventListener("click", async () => {
  inputError.hidden = true;
  const participants = collectParticipants();

  if (participants.length < 2) {
    inputError.textContent = "Add research notes for at least 2 participants. Pattern-finding needs cross-participant comparison.";
    inputError.hidden = false;
    return;
  }

  runButton.disabled = true;
  runButtonLabel.textContent = "Analyzing";
  runButtonSpinner.hidden = false;

  try {
    const res = await fetch(apiUrl("/api/analyze"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ participants }),
    });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.error || "Analysis failed.");
    }

    state.patterns = (data.patterns || []).map((p) => ({ ...p, decision: null }));
    state.findings = (data.single_participant_findings || []).map((f) => ({ ...f, decision: null }));
    state.flags = data.flags || [];
    reportSection.hidden = true;
    renderResults();
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    inputError.textContent = err.message;
    inputError.hidden = false;
  } finally {
    runButton.disabled = false;
    runButtonLabel.textContent = "Run pattern analysis";
    runButtonSpinner.hidden = true;
  }
});

document.getElementById("finalize").addEventListener("click", async () => {
  const payload = {
    patterns: state.patterns,
    single_participant_findings: state.findings,
  };

  const res = await fetch(apiUrl("/api/finalize"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();

  reportOutput.textContent = data.report_markdown;
  reportSection.hidden = false;
  setStep(3);
  reportSection.scrollIntoView({ behavior: "smooth", block: "start" });
});

document.getElementById("download-report").addEventListener("click", () => {
  const blob = new Blob([reportOutput.textContent], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "researchmate-pattern-report.md";
  a.click();
  URL.revokeObjectURL(url);
});
