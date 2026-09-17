"""Builds the combined, evidence-linked markdown report from researcher-approved
Pattern Analyzer output, matching the traceability format described in the
capstone plan (Section 5.3): every claim shows the exact evidence behind it.
"""


def _format_evidence(evidence: list[dict]) -> str:
    lines = []
    for item in evidence:
        lines.append(
            f"  - [{item.get('participant_id')} / {item.get('source_id')}, "
            f"{item.get('source_type')}]: \"{item.get('text')}\""
        )
    return "\n".join(lines)


def _format_contradictions(contradictions: list[dict]) -> str:
    if not contradictions:
        return ""
    lines = ["- **Contradictions:**"]
    for item in contradictions:
        lines.append(f"  - [{item.get('participant_id')} / {item.get('source_id')}]: \"{item.get('text')}\"")
    return "\n".join(lines)


def build_report(patterns: list[dict], findings: list[dict]) -> str:
    parts = ["# ResearchMate — Pattern Analysis Report", ""]
    parts.append(f"_{len(patterns)} approved pattern(s), {len(findings)} approved single-participant finding(s)._")
    parts.append("")

    parts.append("## Patterns")
    if not patterns:
        parts.append("_No patterns approved._")
    for p in patterns:
        parts.append(f"### {p.get('id')} — {p.get('label')}")
        parts.append(f"- **Category:** {p.get('category')}")
        parts.append(f"- **Participant coverage:** {p.get('participant_coverage')}")
        parts.append(f"- **Evidence strength:** {p.get('evidence_strength')}")
        parts.append("- **Evidence:**")
        parts.append(_format_evidence(p.get("evidence", [])))
        if p.get("interpretation"):
            parts.append(f"- **Interpretation (inference):** {p.get('interpretation')}")
        contradictions_block = _format_contradictions(p.get("contradictions", []))
        if contradictions_block:
            parts.append(contradictions_block)
        parts.append("")

    parts.append("## Single-participant findings")
    if not findings:
        parts.append("_None approved._")
    for f in findings:
        parts.append(
            f"- [{f.get('participant_id')} / {f.get('source_id')}, {f.get('category')}]: "
            f"\"{f.get('text')}\" _(not a cross-participant pattern)_"
        )

    return "\n".join(parts)
