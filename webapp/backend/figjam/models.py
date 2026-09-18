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
