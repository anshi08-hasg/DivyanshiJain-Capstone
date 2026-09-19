"""FigJam board retrieval, abstracted behind an adapter interface so the rest
of the agent never depends on a specific MCP tool being available.

MCPFigJamAdapter is now a real, live implementation, wired to
figma_mcp_client (the same client already used for Push to FigJam) via its
figjam_get_board_contents tool. Confirmed live, using real board content
created during this build (see BUILD_LOG.md): it correctly returns 0 nodes
for a genuinely empty page and real node data once something exists.

Hard constraint confirmed live: figjam_get_board_contents has no board/page
selector parameter at all - it only ever reads whatever page is currently
active/focused in Figma Desktop at the moment of the call, not a specific
board chosen remotely. This is a real limitation of the underlying tool, not
a shortcut taken here; there is no way to read a board that isn't the one
the user currently has open and focused.

DemoFigJamAdapter still exists as the fallback when FIGMA_ACCESS_TOKEN isn't
configured at all, so the pipeline remains exercisable with zero setup.
"""

from __future__ import annotations

import abc
import os
import re
from typing import Any


class FigJamUnavailableError(Exception):
    """Raised when no working FigJam data source can serve a board."""


class FigJamAdapter(abc.ABC):
    @abc.abstractmethod
    def is_available(self) -> bool:
        """Whether this adapter can actually serve board data right now."""

    @abc.abstractmethod
    async def fetch_board(self, board_ref: str) -> dict[str, Any]:
        """Return raw board data: {"board_name": str, "raw_items": [...]}."""


def _find_containing_section(sections: list[dict[str, Any]], x: float, y: float) -> str | None:
    """No parent/child linkage is returned by figjam_get_board_contents (a
    SECTION node only reports its own childCount, not which nodes are in
    it), so section membership is inferred geometrically: whichever
    SECTION's bounding box contains this node's position."""
    for s in sections:
        sx, sy = s.get("x", 0), s.get("y", 0)
        sw, sh = s.get("width", 0), s.get("height", 0)
        if sx <= x <= sx + sw and sy <= y <= sy + sh:
            return s.get("name")
    return None


_PARTICIPANT_PATTERN = re.compile(r"^\s*\[?(P\d+)\b", re.IGNORECASE)


def _map_board_data_to_raw_items(board_data: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = board_data.get("nodes", [])
    sections = [n for n in nodes if n.get("type") == "SECTION"]

    raw_items: list[dict[str, Any]] = []
    for node in nodes:
        node_type = node.get("type")
        node_id = str(node.get("id"))

        if node_type == "SECTION":
            name = node.get("name", "")
            raw_items.append({"id": node_id, "type": "section", "content": name, "section": name})
            continue

        x, y = node.get("x", 0), node.get("y", 0)
        text = node.get("text") or node.get("name") or ""
        section_name = _find_containing_section(sections, x, y)

        metadata: dict[str, Any] = {}
        match = _PARTICIPANT_PATTERN.match(text)
        if match:
            metadata["participant"] = match.group(1).upper()

        item_type = {"STICKY": "sticky", "TEXT": "text"}.get(node_type, "unknown")
        raw_items.append({
            "id": node_id,
            "type": item_type,
            "content": text,
            "section": section_name,
            "position": {"x": x, "y": y},
            "metadata": metadata,
        })

    return raw_items


class MCPFigJamAdapter(FigJamAdapter):
    """Reads the currently active FigJam page in Figma Desktop, live, via
    figma_mcp_client (the same MCP client Push to FigJam uses)."""

    def is_available(self) -> bool:
        return bool(os.environ.get("FIGMA_ACCESS_TOKEN", "").strip())

    async def fetch_board(self, board_ref: str) -> dict[str, Any]:
        from . import figma_mcp_client as mcp_client

        try:
            async with mcp_client.session() as sess:
                board_data = await mcp_client.get_board_contents(sess)
        except mcp_client.FigmaMCPError as exc:
            raise FigJamUnavailableError(
                f"Could not read the live FigJam board ({exc}). Make sure Figma Desktop is "
                "open with the target board as the active/focused page, and the Desktop "
                "Bridge plugin is connected (local mode: launched; cloud mode: paired via "
                "POST /api/figjam/pair)."
            ) from exc

        page = board_data.get("page", "the current page")
        raw_items = _map_board_data_to_raw_items(board_data)
        return {"board_name": f"Live FigJam board: {page}", "raw_items": raw_items}


class DemoFigJamAdapter(FigJamAdapter):
    """Fixed sample research board, clearly not live FigJam data. Used only
    when FIGMA_ACCESS_TOKEN isn't configured at all."""

    def is_available(self) -> bool:
        return True

    async def fetch_board(self, board_ref: str) -> dict[str, Any]:
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
    """Prefers the real, live MCPFigJamAdapter whenever FIGMA_ACCESS_TOKEN is
    configured; falls back to DemoFigJamAdapter only when it isn't, so the
    pipeline still works with zero setup."""
    mcp_adapter = MCPFigJamAdapter()
    if mcp_adapter.is_available():
        return mcp_adapter
    return DemoFigJamAdapter()
