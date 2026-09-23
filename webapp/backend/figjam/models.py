"""Normalized research data types for the FigJam Research Agent.

Mirrors the ResearchItem / FigJamResearchContext shapes from the task spec,
adapted to this project's existing plain-dataclass style (the rest of the
backend uses dicts and dataclass-free functions, so these stay simple and
JSON-serializable rather than pulling in a schema library).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Optional

ResearchItemType = Literal["sticky", "text", "section", "group", "unknown"]

# Section names ResearchMate itself creates when pushing its own output back
# to the board (figma_layout.py's _SECTION_TITLES, persona_layout.py's
# "User personas" section). Confirmed live: after a Push to FigJam or Push
# Personas, re-connecting to the same board reads those sections back as if
# they were ordinary research - without this filter, a later Analyze or
# Generate Personas call would be fed its own prior output as "evidence"
# alongside the real participant research, silently compounding on itself.
# "Persona: " is kept for backwards compatibility with boards that already
# have per-persona sections from before personas were grouped into one
# "User personas" section.
_RESEARCHMATE_OWN_SECTION_NAMES = {
    "Themes", "Insights", "Contradictions", "Research Gaps", "Design Opportunities",
    "User personas",
}
_RESEARCHMATE_OWN_SECTION_PREFIX = "Persona: "


def _is_researchmate_own_section(name: str | None) -> bool:
    if not name:
        return False
    return name in _RESEARCHMATE_OWN_SECTION_NAMES or name.startswith(_RESEARCHMATE_OWN_SECTION_PREFIX)


@dataclass
class ResearchItem:
    id: str
    type: ResearchItemType
    content: str
    section: Optional[str] = None
    position: Optional[dict[str, float]] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FigJamResearchContext:
    board_name: str
    items: list[ResearchItem]
    sections: list[str]
    participant_quotes: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "board_name": self.board_name,
            "items": [i.to_dict() for i in self.items],
            "sections": self.sections,
            "participant_quotes": self.participant_quotes,
            "themes": self.themes,
        }

    def primary_research_items(self) -> list[ResearchItem]:
        """Items that are genuine participant research, excluding anything
        that lives inside (or is itself) a section ResearchMate created from
        its own prior output. Analysis and persona synthesis must both read
        from this, not `self.items` directly, or a board that's already had
        something pushed to it feeds the model its own earlier output as if
        it were new evidence."""
        return [
            item for item in self.items
            if not (item.type == "section" and _is_researchmate_own_section(item.content))
            and not _is_researchmate_own_section(item.section)
        ]

    def overview(self) -> dict[str, Any]:
        participants = {
            i.metadata.get("participant")
            for i in self.items
            if i.metadata.get("participant")
        }
        return {
            "board_name": self.board_name,
            "research_items": len(self.items),
            "sections": len(self.sections),
            "participants": len(participants) if participants else None,
        }
