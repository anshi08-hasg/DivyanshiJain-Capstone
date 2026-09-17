"""FigJam board retrieval, abstracted behind an adapter interface so the rest
of the agent never depends on a specific MCP tool being available.

Status at build time: this environment exposes an unauthenticated
"claude.ai Figma" MCP connector (visible only as a name requiring OAuth in
the harness's server list) and no callable Figma/FigJam tool of any kind
(confirmed by searching the available tool catalog). No FigJam-board-reading
tool exists to call, authorized or not, so MCPFigJamAdapter below is a real
interface with no working implementation, not a stub pretending to work.

DemoFigJamAdapter exists only so the rest of the pipeline (normalize,
analyze, critique, frontend) can be exercised end to end without a live
connection. Every place its data surfaces in the UI is labeled as demo data.
"""

from __future__ import annotations

import abc
from typing import Any


class FigJamUnavailableError(Exception):
    """Raised when no working FigJam data source can serve a board."""


class FigJamAdapter(abc.ABC):
    @abc.abstractmethod
    def is_available(self) -> bool:
        """Whether this adapter can actually serve board data right now."""

    @abc.abstractmethod
    def fetch_board(self, board_ref: str) -> dict[str, Any]:
        """Return raw board data: {"board_name": str, "raw_items": [...]}."""


class MCPFigJamAdapter(FigJamAdapter):
    """Intended integration point for the official Figma MCP server.

    Once a Figma/FigJam MCP tool is authorized and exposed to this agent
    (e.g. a tool that reads FigJam node content: sticky notes, text, sections,
    groups, and their metadata), this method should call it and map its
    response into the raw_items shape DemoFigJamAdapter already produces
    below, then hand off to figjam.normalize.normalize_board() unchanged.

    Not implemented: no such tool is currently available to call.
    """

    def is_available(self) -> bool:
        return False

    def fetch_board(self, board_ref: str) -> dict[str, Any]:
        raise FigJamUnavailableError(
            "No Figma/FigJam MCP tool is available in this environment. "
            "The 'claude.ai Figma' connector requires authorization (see your "
            "claude.ai connector settings), and even once authorized it is not "
            "confirmed to expose FigJam board/sticky-note content specifically. "
            "Connect using the demo board instead, or wire a real MCP tool into "
            "MCPFigJamAdapter.fetch_board() once one is available."
        )


class DemoFigJamAdapter(FigJamAdapter):
    """Fixed sample research board, clearly not live FigJam data."""

    def is_available(self) -> bool:
        return True

    def fetch_board(self, board_ref: str) -> dict[str, Any]:
        return {"board_name": "Demo board: Library redesign research (sample data, not live FigJam)", "raw_items": _DEMO_ITEMS}


_DEMO_ITEMS: list[dict[str, Any]] = [
    {"id": "N1", "type": "section", "content": "Study Space", "section": "Study Space"},
    {"id": "N2", "type": "sticky", "content": "I always camp outside the silent room at 7am during finals, otherwise there's nowhere quiet left by 9.", "section": "Study Space", "position": {"x": 40, "y": 120}, "metadata": {"participant": "P1"}},
    {"id": "N3", "type": "sticky", "content": "Exam week is the worst, every table is taken by 10am and group projects are talking everywhere.", "section": "Study Space", "position": {"x": 220, "y": 120}, "metadata": {"participant": "P3"}},
    {"id": "N4", "type": "sticky", "content": "I've started studying in my dorm instead because the library is just too loud when everyone's cramming.", "section": "Study Space", "position": {"x": 400, "y": 120}, "metadata": {"participant": "P4"}},
    {"id": "N5", "type": "sticky", "content": "Honestly the library is fine for me, I just go early and grab a spot.", "section": "Study Space", "position": {"x": 580, "y": 120}, "metadata": {"participant": "P6"}},

    {"id": "N6", "type": "section", "content": "Wayfinding", "section": "Wayfinding"},
    {"id": "N7", "type": "sticky", "content": "There's no signage pointing to the accessible entrance from the parking lot.", "section": "Wayfinding", "position": {"x": 40, "y": 320}, "metadata": {"participant": "P2"}},
    {"id": "N8", "type": "sticky", "content": "I circled the building twice looking for the accessible entrance, there's no sign.", "section": "Wayfinding", "position": {"x": 220, "y": 320}, "metadata": {"participant": "P5"}},
    {"id": "N9", "type": "text", "content": "Floor directory near the main entrance is outdated, still lists the old cafe location.", "section": "Wayfinding", "position": {"x": 400, "y": 320}, "metadata": {"participant": "P7"}},

    {"id": "N10", "type": "section", "content": "Booking & Group Rooms", "section": "Booking & Group Rooms"},
    {"id": "N11", "type": "sticky", "content": "I always try to book the group room online the night before, otherwise we end up wandering the floor looking for space.", "section": "Booking & Group Rooms", "position": {"x": 40, "y": 520}, "metadata": {"participant": "P2"}},
    {"id": "N12", "type": "sticky", "content": "Booking ahead is the only way I've found to guarantee we actually get a room for project meetings.", "section": "Booking & Group Rooms", "position": {"x": 220, "y": 520}, "metadata": {"participant": "P4"}},
    {"id": "N13", "type": "sticky", "content": "I never book ahead, I just show up and take whatever's free, booking feels like more effort than it's worth.", "section": "Booking & Group Rooms", "position": {"x": 400, "y": 520}, "metadata": {"participant": "P3"}},

    {"id": "N14", "type": "sticky", "content": "I wish there were more power outlets near the windows on the third floor.", "section": "Study Space", "position": {"x": 760, "y": 120}, "metadata": {"participant": "P1"}},
    {"id": "N15", "type": "group", "content": "Group: recurring complaints about noise during exam periods (N2, N3, N4)", "section": "Study Space", "metadata": {"groups": ["N2", "N3", "N4"]}},
]


def get_adapter() -> FigJamAdapter:
    """Always returns DemoFigJamAdapter for now.

    Kept as a factory (rather than importing DemoFigJamAdapter directly
    elsewhere) so swapping in MCPFigJamAdapter once a real tool exists is a
    one-line change here, not a change everywhere it's used.
    """
    mcp_adapter = MCPFigJamAdapter()
    if mcp_adapter.is_available():
        return mcp_adapter
    return DemoFigJamAdapter()
