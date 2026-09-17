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

// In-memory state for the current analysis run, keyed by item id so edits
// and decisions survive re-rendering.
let state = { patterns: [], findings: [], flags: [] };

function addParticipantBlock() {
  const node = participantTemplate.content.cloneNode(true);
  node.querySelector(".remove-participant").addEventListener("click", (e) => {
    e.target.closest(".participant-block").remove();
  });
  participantsContainer.appendChild(node);
}

document.getElementById("add-participant").addEventListener("click", addParticipantBlock);

// Start with two participants — pattern-finding requires at least two.
addParticipantBlock();
addParticipantBlock();

function collectParticipants() {
  return [...participantsContainer.querySelectorAll(".participant-block")].map((block) => ({
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
  return `<div class="contradictions"><strong>Contradictions:</strong>${items}</div>`;
}

function makeDecisionRow(item, onChange) {
  const row = document.createElement("div");
  row.className = "decision-row";

  ["approve", "edit", "reject"].forEach((decision) => {
    const btn = document.createElement("button");
    btn.textContent = decision[0].toUpperCase() + decision.slice(1);
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
    <h4>${pattern.id} — ${escapeHtml(pattern.label)}</h4>
    <div class="meta">
      Category: ${escapeHtml(pattern.category)} ·
      Coverage: ${escapeHtml(pattern.participant_coverage)} ·
      Strength: ${escapeHtml(pattern.evidence_strength)}
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
    <div class="meta">${finding.participant_id} / ${finding.source_id} · ${escapeHtml(finding.category)}</div>
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
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

document.getElementById("run-analysis").addEventListener("click", async () => {
  inputError.hidden = true;
  const participants = collectParticipants();

  if (participants.length < 2) {
    inputError.textContent = "Add research notes for at least 2 participants — pattern-finding needs cross-participant comparison.";
    inputError.hidden = false;
    return;
  }

  const runButton = document.getElementById("run-analysis");
  runButton.disabled = true;
  runButton.textContent = "Analyzing...";

  try {
    const res = await fetch("/api/analyze", {
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
  } catch (err) {
    inputError.textContent = err.message;
    inputError.hidden = false;
  } finally {
    runButton.disabled = false;
    runButton.textContent = "Run Pattern Analysis";
  }
});

document.getElementById("finalize").addEventListener("click", async () => {
  const payload = {
    patterns: state.patterns,
    single_participant_findings: state.findings,
  };

  const res = await fetch("/api/finalize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();

  reportOutput.textContent = data.report_markdown;
  reportSection.hidden = false;
  reportSection.scrollIntoView({ behavior: "smooth" });
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
