"""Converts raw board data (from any FigJamAdapter) into a FigJamResearchContext.

Deterministic, non-LLM logic only: this is application code, not reasoning,
per the "code = reliable data operations" split in the agent design.
"""

from __future__ import annotations

from typing import Any

from .models import FigJamResearchContext, ResearchItem

_VALID_TYPES = {"sticky", "text", "section", "group"}


def normalize_board(raw_board: dict[str, Any]) -> FigJamResearchContext:
    raw_items = raw_board.get("raw_items", [])

    items: list[ResearchItem] = []
    sections: list[str] = []
    quotes: list[str] = []

    for raw in raw_items:
        item_type = raw.get("type") if raw.get("type") in _VALID_TYPES else "unknown"
        item = ResearchItem(
            id=raw["id"],
            type=item_type,
            content=raw.get("content", ""),
            section=raw.get("section"),
            position=raw.get("position"),
            metadata=raw.get("metadata", {}) or {},
        )
        items.append(item)

        if item.type == "section" and item.content and item.content not in sections:
            sections.append(item.content)
        if item.type in ("sticky", "text") and item.content:
            quotes.append(item.content)

    return FigJamResearchContext(
        board_name=raw_board.get("board_name", "Untitled board"),
        items=items,
        sections=sections,
        participant_quotes=quotes,
    )
