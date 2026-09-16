---
name: pattern-analyzer
description: Finds and structures recurring cross-participant patterns (behaviours, needs, pain points, motivations, preferences) from qualitative UX research (transcripts, observation notes, research images), strictly separating evidence, pattern, and interpretation, with stable graph-ready IDs. Use for the ResearchMate Pattern Finder pipeline stage — after per-participant analysis is available, before theming.
---

# Pattern Analyzer

## Purpose

Compare per-participant qualitative research findings to surface **recurring cross-participant patterns** — not to interpret their meaning, theme them, or act on them. This Skill is the "Pattern Finder" stage of the ResearchMate pipeline: it sits between per-participant analysis and theming, and its output must be traceable and graph-ready per the evidence schema in `DivyanshiJain_capstone plan.md` (Section 5.3).

## Input

Qualitative primary research, already carrying stable participant/transcript/quote IDs:
- Interview transcripts (raw or per-participant analyzed output: pain points, needs, behaviours, motivations, preferences, each citing quote IDs)
- Observation notes
- Research images (e.g., photos of workspaces, artifacts, sketches, environments)

If any input item lacks a participant ID or source citation, do not fabricate one — flag it as missing evidence rather than inventing an ID.

## Process

1. **Read every participant's material individually first.** Do not skim or aggregate before understanding each participant's own material on its own terms.
2. **Compare across participants** to find items that recur — the same or semantically similar behaviour, need, pain point, motivation, or preference expressed by more than one participant, even in different words. Do not rely on exact text matching only; recognize paraphrases of the same underlying finding.
3. **Distinguish recurring patterns from single-participant findings.** A finding held by only one participant is not a pattern — record it explicitly as a single-participant finding, not folded into a pattern with inflated coverage.
4. **Preserve exact quotes and participant IDs** for every piece of evidence cited. Never paraphrase, translate, or lightly edit a quote when citing it as evidence — cite it exactly as it appears in the source (including non-English quotes verbatim, per the capstone plan's translation-drift mitigation).
5. **Keep Evidence, Pattern, and Interpretation in strictly separate fields** for every pattern (see Output schema). Evidence is what was said/observed, verbatim. Pattern is the neutral, descriptive label for what recurs. Interpretation is any inference about *why* it recurs or what it might mean — interpretation must never be presented as if it were evidence, and must be clearly labeled as inference.
6. **Record participant coverage and evidence strength** for every pattern: how many participants support it, out of how many total, and a qualitative strength note (e.g., "strong: 5/6 participants, consistent wording" vs. "weak: 2/6 participants, indirectly implied"). Do not produce a numeric confidence/certainty score — evidence strength is about *how much support exists*, not a probability that the claim is "true."
7. **Surface contradictions and important differences.** When participants disagree, or a pattern holds for most but is explicitly contradicted by another participant, record that contradiction alongside the pattern rather than smoothing it over or omitting it.
8. **Keep image-derived observations separate.** When research images are part of the input, record what is directly observed in the image (objects, layout, visible behaviour/artifacts) as its own evidence type, distinct from both interpretation and from claims already supported by transcript/note evidence. Do not blend an image observation into a text-based pattern's evidence list as if it were the same kind of evidence — cite it as its own evidence item, linked to the pattern it supports.
9. **Assign every pattern a stable, unique ID** (e.g., `PAT01`, `PAT02`, ...) and make it graph-ready: each pattern must explicitly list the IDs of every supporting evidence item (quote IDs, observation IDs, image-observation IDs) and every contributing per-participant analysis item ID it cites, per the plan's evidence chain (`Pattern (PAT03, cites [P1-PP02, P3-PP01, P4-PP04])`). Do not introduce a pattern that cites no upstream ID.

## Output structure

For each pattern, produce:
- `id`: stable pattern ID (e.g., `PAT01`)
- `label`: short, neutral, descriptive name (not an interpretation, not a theme name)
- `category`: one of behaviour / need / pain point / motivation / preference
- `evidence`: list of items, each with participant ID, quote ID or observation ID, exact quote text or observation description, and source type (transcript quote / observation note / image observation)
- `participant_coverage`: e.g., "4/6 participants: P1, P2, P4, P5"
- `evidence_strength`: qualitative note tied to coverage and consistency (not a numeric score)
- `interpretation`: optional, clearly labeled inference about why the pattern might exist — never mixed into `evidence`
- `contradictions`: any participant(s) whose evidence conflicts with this pattern, with their quote/observation ID and what they said/showed

Separately, list **single-participant findings** that did not recur, with the same evidence rigor (participant ID, quote/observation ID, verbatim text) but explicitly labeled as not a cross-participant pattern.

## Hard rules

- Do not generate personas.
- Do not generate How Might We (HMW) statements.
- Do not generate ideas, recommendations, or opportunity areas.
- Do not theme or group patterns into higher-level categories — that is the next pipeline stage (Theme / Affinity Mapper), not this Skill.
- Do not invent a quote, participant, or ID that is not present in the input.
- Do not present interpretation as evidence, or evidence as interpretation.
- Do not claim a pattern is "recurring" without at least two distinct participants' evidence supporting it.
