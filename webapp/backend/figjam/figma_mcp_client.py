"""Client for the community "Figma Console MCP" server (southleft/figma-console-mcp),
used to push ResearchMate's analysis output into FigJam as real sticky notes.

This is a genuinely different capability from figjam/adapter.py: adapter.py is
about *reading* a FigJam board (currently unavailable, served by a demo
fixture instead). This module is about *writing* to FigJam, which as of this
build is possible via a real, documented community MCP server, but only under
a hard constraint that cannot be worked around: the server relays tool calls
to a "Desktop Bridge" plugin that must be running live inside Figma Desktop,
with the target FigJam board open. There is no headless/API-token-only path
to writing FigJam content today; Figma's official remote MCP server exists,
but only allowlists a fixed set of IDE clients (not custom backends), and a
personal access token alone cannot create board content without that plugin
bridge.

Docs consulted while building this (see FIGMA_CONNECT.md for the write-up):
- https://docs.figma-console-mcp.southleft.com/figjam
- https://docs.figma-console-mcp.southleft.com/tools
- https://docs.figma-console-mcp.southleft.com/setup

Setup required on the user's machine before any call here can succeed:
1. Figma Desktop app open, with the target FigJam board open.
2. Plugins > Development > Figma Desktop Bridge, launched and connected.
3. FIGMA_ACCESS_TOKEN set in the repo root .env (a Figma personal access
   token, starts with "figd_").
4. Node.js installed (this client spawns `npx -y figma-console-mcp@latest`
   as a local MCP stdio server, per the "Local Mode" setup in the docs above).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class FigmaMCPError(Exception):
    """Raised for any failure talking to the Figma Console MCP server."""


# Pinned to match the Desktop Bridge plugin vendored at webapp/figma-plugin/
# (copied from a running 1.40.0 server). Using "@latest" here while the plugin
# is a frozen copy could silently drift out of sync with a newer server
# version; bump both together if the plugin is ever re-copied from a newer run.
_SERVER_PACKAGE = "figma-console-mcp@1.40.0"


def _server_params() -> StdioServerParameters:
    token = os.environ.get("FIGMA_ACCESS_TOKEN", "").strip()
    if not token:
        raise FigmaMCPError(
            "FIGMA_ACCESS_TOKEN is not set in .env. Create a personal access token "
            "at Figma's token management page (Settings > Security) and set "
            "FIGMA_ACCESS_TOKEN=figd_... in the repo root .env."
        )
    return StdioServerParameters(
        command="npx",
        args=["-y", _SERVER_PACKAGE],
        env={**os.environ, "FIGMA_ACCESS_TOKEN": token},
    )


@asynccontextmanager
async def session():
    """One shared MCP session, for a whole logical operation (e.g. an entire
    board push) rather than one process spawn per tool call. A live Desktop
    Bridge plugin connection is only useful if it can stay paired with a
    single server instance for multiple calls in a row, not reconnect to a
    brand-new subprocess (and likely a different port) after every call."""
    params = _server_params()
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as sess:
                await sess.initialize()
                yield sess
    except FigmaMCPError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface subprocess/handshake failures clearly
        raise FigmaMCPError(
            f"Could not connect to the Figma Console MCP server ({exc}). Check that: "
            "Node.js/npx is installed, Figma Desktop is open with the target FigJam "
            "board, and the Figma Desktop Bridge plugin is running "
            "(Plugins > Development > Figma Desktop Bridge)."
        ) from exc


async def list_tools() -> list[str]:
    """Connectivity check: completes the MCP handshake and lists available tools,
    without requiring the Desktop Bridge plugin to be connected."""
    async with session() as sess:
        result = await sess.list_tools()
        return [t.name for t in result.tools]


async def create_stickies(sess: ClientSession, stickies: list[dict[str, Any]]) -> dict[str, Any]:
    """stickies: list of {"text": str, "x": float, "y": float, "color": "YELLOW|BLUE|..."}.
    Pass an already-open `session()` so multiple calls share one live connection."""
    result = await sess.call_tool("figjam_create_stickies", {"stickies": stickies})
    return _unwrap(result)


async def create_section(
    sess: ClientSession, name: str, x: float, y: float, width: float = 1000, height: float = 800,
    fill_color: str | None = None,
) -> dict[str, Any]:
    """fill_color, if given, must be a "#RRGGBB" hex string."""
    args: dict[str, Any] = {"name": name, "x": x, "y": y, "width": width, "height": height}
    if fill_color:
        args["fillColor"] = fill_color
    result = await sess.call_tool("figjam_create_section", args)
    return _unwrap(result)


async def auto_arrange(sess: ClientSession, node_ids: list[str], mode: str = "grid", gap: float = 24) -> dict[str, Any]:
    result = await sess.call_tool(
        "figjam_auto_arrange",
        {"nodeIds": node_ids, "mode": mode, "gap": gap},
    )
    return _unwrap(result)


def _unwrap(result: Any) -> dict[str, Any]:
    if getattr(result, "is_error", False):
        text = "; ".join(getattr(block, "text", str(block)) for block in result.content)
        raise FigmaMCPError(f"Figma Console MCP returned an error: {text}")
    for block in result.content:
        if getattr(block, "type", None) == "text":
            return {"raw_text": block.text}
    return {"raw_text": str(result.content)}
