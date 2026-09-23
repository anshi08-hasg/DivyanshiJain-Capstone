"""Client for the community "Figma Console MCP" server (southleft/figma-console-mcp),
used to push ResearchMate's analysis output into FigJam as real sticky notes.

This is a genuinely different capability from figjam/adapter.py: adapter.py is
about *reading* a FigJam board (currently unavailable, served by a demo
fixture instead). This module is about *writing* to FigJam.

Two transport modes, selected via FIGJAM_MCP_MODE in .env:

- "local" (default): spawns `npx -y figma-console-mcp@1.40.0` as a local
  stdio server. The Desktop Bridge plugin connects to it over
  ws://localhost:9223. Only works when the backend and Figma Desktop are on
  the SAME machine - this breaks entirely once the backend is hosted
  remotely (e.g. Railway), because "localhost" from the plugin's point of
  view is never the remote host.
- "cloud": connects over HTTPS to the community project's own hosted relay
  at figma-console-mcp.southleft.com/mcp (a different service from Figma's
  own official remote MCP - confirmed by testing both directly: Figma's
  official server returns 403 on client registration for any non-allowlisted
  client, while this community relay accepts a plain Figma personal access
  token as Bearer auth). The plugin pairs to this relay once via a 6-char
  code from figma_pair_plugin; confirmed live that the connection then
  persists (a write succeeded again 90+ seconds later with no re-pairing),
  so this is a one-time setup per plugin session, not a recurring one. This
  is the mode to use when the backend is hosted somewhere the plugin can't
  reach via localhost.

Setup required on the user's machine before any call here can succeed:
1. Figma Desktop app open, with the target FigJam board open.
2. Plugins > Development > Figma Desktop Bridge, launched.
   - Local mode: connects automatically.
   - Cloud mode: toggle "Cloud Mode" in the plugin and enter the pairing
     code from POST /api/figjam/pair (see app.py).
3. FIGMA_ACCESS_TOKEN set wherever this runs (repo root .env locally, or a
   Railway service variable in production) - a Figma personal access token,
   starts with "figd_".
4. Local mode only: Node.js installed (to run `npx`).

Docs consulted while building this (see FIGMA_CONNECT.md for the write-up):
- https://docs.figma-console-mcp.southleft.com/figjam
- https://docs.figma-console-mcp.southleft.com/tools
- https://docs.figma-console-mcp.southleft.com/setup
- https://docs.figma-console-mcp.southleft.com/mode-comparison
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


class FigmaMCPError(Exception):
    """Raised for any failure talking to the Figma Console MCP server."""


# Pinned to match the Desktop Bridge plugin vendored at webapp/figma-plugin/
# (copied from a running 1.40.0 server). Using "@latest" here while the plugin
# is a frozen copy could silently drift out of sync with a newer server
# version; bump both together if the plugin is ever re-copied from a newer run.
_SERVER_PACKAGE = "figma-console-mcp@1.40.0"
_CLOUD_URL = "https://figma-console-mcp.southleft.com/mcp"


def _get_token() -> str:
    token = os.environ.get("FIGMA_ACCESS_TOKEN", "").strip()
    if not token:
        raise FigmaMCPError(
            "FIGMA_ACCESS_TOKEN is not set. Create a personal access token at Figma's "
            "token management page (Settings > Security) and set FIGMA_ACCESS_TOKEN=figd_... "
            "(repo root .env locally, or a service variable on Railway)."
        )
    return token


def _mode() -> str:
    return os.environ.get("FIGJAM_MCP_MODE", "local").strip().lower()


def _server_params() -> StdioServerParameters:
    token = _get_token()
    return StdioServerParameters(
        command="npx",
        args=["-y", _SERVER_PACKAGE],
        env={**os.environ, "FIGMA_ACCESS_TOKEN": token},
    )


def _find_figma_error(exc: BaseException) -> FigmaMCPError | None:
    """anyio's TaskGroup wraps exceptions raised inside `yield sess` in
    (possibly nested) BaseExceptionGroups by the time they propagate back out
    through stdio_client's/ClientSession's __aexit__. A plain
    `except FigmaMCPError` doesn't match those anymore, which was silently
    replacing specific tool errors with the generic "could not connect"
    message. This digs through any nesting to find the original error."""
    if isinstance(exc, FigmaMCPError):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            found = _find_figma_error(sub)
            if found:
                return found
    return None


@asynccontextmanager
async def _local_transport():
    params = _server_params()
    async with stdio_client(params) as (read, write):
        yield read, write


@asynccontextmanager
async def _cloud_transport():
    token = _get_token()
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as http_client:
        async with streamable_http_client(_CLOUD_URL, http_client=http_client) as (read, write):
            yield read, write


@asynccontextmanager
async def session():
    """One shared MCP session, for a whole logical operation (e.g. an entire
    board push) rather than one process spawn per tool call. A live Desktop
    Bridge plugin connection is only useful if it can stay paired with a
    single server instance for multiple calls in a row, not reconnect to a
    brand-new subprocess (and likely a different port) after every call.

    Uses local (stdio, spawns npx) or cloud (HTTPS relay) transport based on
    FIGJAM_MCP_MODE - see the module docstring for when to use which."""
    transport = _cloud_transport() if _mode() == "cloud" else _local_transport()
    try:
        async with transport as (read, write):
            async with ClientSession(read, write) as sess:
                await sess.initialize()
                yield sess
    except Exception as exc:  # noqa: BLE001 - surface subprocess/handshake/tool errors clearly
        specific = _find_figma_error(exc)
        if specific:
            raise specific from exc
        if _mode() == "cloud":
            raise FigmaMCPError(
                f"Could not connect to the Figma Console MCP cloud relay ({exc}). Check that: "
                "FIGMA_ACCESS_TOKEN is a valid Figma personal access token, and the Desktop "
                "Bridge plugin has been paired via Cloud Mode (POST /api/figjam/pair for a code)."
            ) from exc
        raise FigmaMCPError(
            f"Could not connect to the Figma Console MCP server ({exc}). Check that: "
            "Node.js/npx is installed, Figma Desktop is open with the target FigJam "
            "board, and the Figma Desktop Bridge plugin is running "
            "(Plugins > Development > Figma Desktop Bridge)."
        ) from exc


async def request_pairing_code() -> dict[str, Any]:
    """Cloud mode only: generates a one-time pairing code for the Desktop
    Bridge plugin's Cloud Mode toggle. Confirmed live that pairing persists
    after the code is redeemed (not a recurring requirement) - the 5-minute
    expiry only applies to the unredeemed code itself."""
    async with session() as sess:
        result = await sess.call_tool("figma_pair_plugin", {})
        unwrapped = _unwrap(result)
        try:
            return json.loads(unwrapped["raw_text"])
        except (KeyError, json.JSONDecodeError):
            return unwrapped


async def list_tools() -> list[str]:
    """Connectivity check: completes the MCP handshake and lists available tools,
    without requiring the Desktop Bridge plugin to be connected."""
    async with session() as sess:
        result = await sess.list_tools()
        return [t.name for t in result.tools]


async def wait_for_bridge(sess: ClientSession, timeout: float = 30, poll_interval: float = 2) -> None:
    """Local mode only: every push spawns a brand-new server process (see
    session() above), so even an already-open Desktop Bridge plugin needs
    several seconds to notice the new instance and reconnect its WebSocket.
    Calling a write tool immediately after opening a session fails with
    "Cannot connect to Figma Desktop" even when the plugin is genuinely
    running, purely due to this reconnect delay - confirmed live: a manual
    20s wait let a real write succeed right after the same call failed
    instantly. This polls figma_get_status(probe=true) until the bridge
    reports a working roundtrip, instead of guessing a fixed sleep.

    Cloud mode doesn't need this at all and this function is a no-op there:
    pairing establishes a persistent relay (a Cloudflare Durable Object) that
    stays connected independently of any particular client connection, so
    each new HTTPS request talks to an already-live relay immediately -
    confirmed live, and confirmed that figma_get_status isn't even a
    registered tool on the cloud endpoint (95 tools there vs 121 locally),
    so calling it here for cloud mode would just fail outright, not merely
    poll pointlessly."""
    if _mode() == "cloud":
        return

    elapsed = 0.0
    last_error = "no response yet"
    while elapsed < timeout:
        result = await sess.call_tool("figma_get_status", {"probe": True})
        text = next((b.text for b in result.content if getattr(b, "type", None) == "text"), "{}")
        try:
            status = json.loads(text)
        except json.JSONDecodeError:
            status = {}

        probe = status.get("setup", {}).get("probeResult", {})
        if probe.get("success"):
            return
        last_error = probe.get("error") or status.get("setup", {}).get("message") or "not connected yet"

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    raise FigmaMCPError(
        f"Timed out after {timeout:.0f}s waiting for the Figma Desktop Bridge plugin to connect "
        f"(last status: {last_error}). Make sure Figma Desktop is open with the target FigJam "
        "board, and Plugins > Development > Figma Desktop Bridge has been launched."
    )


async def create_stickies(sess: ClientSession, stickies: list[dict[str, Any]]) -> dict[str, Any]:
    """stickies: list of {"text": str, "x": float, "y": float, "color": "YELLOW|BLUE|..."}.
    Pass an already-open `session()` so multiple calls share one live connection."""
    result = await sess.call_tool("figjam_create_stickies", {"stickies": stickies})
    return _unwrap(result)


async def create_shape_with_text(
    sess: ClientSession, text: str, x: float, y: float, width: float, height: float,
    shapeType: str = "ROUNDED_RECTANGLE", fillColor: str | None = None,
    textColor: str | None = None, fontSize: float | None = None,
    cornerRadius: float | None = None,
) -> dict[str, Any]:
    """A real, editable shape with embedded text - unlike figjam_create_stickies
    (a fixed 240x240 sticky note, confirmed live width/height are ignored),
    this genuinely respects custom width/height, so it's used for persona
    cards where a fixed sticky size can't hold a structured multi-zone
    layout. shapeType options confirmed live: ROUNDED_RECTANGLE (default),
    DIAMOND, ELLIPSE, TRIANGLE_UP, TRIANGLE_DOWN, PARALLELOGRAM_RIGHT,
    PARALLELOGRAM_LEFT, ENG_DATABASE, ENG_QUEUE, ENG_FILE, ENG_FOLDER.
    fillColor/textColor, if given, must be "#RRGGBB" hex strings.
    cornerRadius=0 gives ROUNDED_RECTANGLE sharp (non-rounded) corners."""
    args: dict[str, Any] = {
        "text": text, "x": x, "y": y, "width": width, "height": height, "shapeType": shapeType,
    }
    if fillColor:
        args["fillColor"] = fillColor
    if textColor:
        args["textColor"] = textColor
    if fontSize:
        args["fontSize"] = fontSize
    if cornerRadius is not None:
        # Confirmed live: this parameter is silently ignored by
        # figjam_create_shape_with_text - a shape created with cornerRadius=0
        # still comes back with cornerRadius=80 when read back via
        # figma_execute. Kept here as a harmless hint in case the server
        # starts honoring it, but callers needing real sharp corners must
        # also call zero_corner_radius() after creation.
        args["cornerRadius"] = cornerRadius
    result = await sess.call_tool("figjam_create_shape_with_text", args)
    unwrapped = _unwrap(result)
    try:
        unwrapped["node_id"] = json.loads(unwrapped["raw_text"])["data"]["id"]
    except (KeyError, json.JSONDecodeError):
        pass
    return unwrapped


async def apply_card_finish(sess: ClientSession, node_ids: list[str]) -> dict[str, Any]:
    """Forces sharp (non-rounded) corners and removes the default stroke on
    the given nodes via figma_execute (direct Figma Plugin API access).
    Confirmed live: figjam_create_shape_with_text's cornerRadius parameter
    is silently ignored (a shape created with cornerRadius=0 still comes
    back reporting cornerRadius=80), and every shape carries a visible
    default gray stroke that fillColor alone doesn't remove - both need
    fixing directly through the plugin API after creation. Batches every id
    into one figma_execute call rather than one round trip per shape."""
    if not node_ids:
        return {}
    ids_json = json.dumps(node_ids)
    code = f"""
    const ids = {ids_json};
    let updated = 0;
    for (const id of ids) {{
      const node = await figma.getNodeByIdAsync(id);
      if (node) {{
        if ("cornerRadius" in node) node.cornerRadius = 0;
        if ("strokes" in node) node.strokes = [];
        updated++;
      }}
    }}
    return {{ requested: ids.length, updated }};
    """
    result = await sess.call_tool("figma_execute", {"code": code})
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


async def get_board_contents(sess: ClientSession, node_types: list[str] | None = None, max_nodes: int = 500) -> dict[str, Any]:
    """Reads whatever page is currently active/focused in Figma Desktop -
    confirmed live there is no board/page selector parameter, so this always
    reflects the page the user has open at call time, not a specific board
    chosen remotely. Real response shape confirmed live:
    {"nodes": [{"id", "type", "name", "x", "y", "width", "height", "text"?,
    "color"?, "childCount"? (SECTION only)}, ...], "totalFound", "truncated",
    "page"}."""
    args: dict[str, Any] = {"maxNodes": max_nodes}
    if node_types:
        args["nodeTypes"] = node_types
    result = await sess.call_tool("figjam_get_board_contents", args)
    unwrapped = _unwrap(result)
    try:
        parsed = json.loads(unwrapped["raw_text"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise FigmaMCPError(f"Unexpected response reading the board: {unwrapped}") from exc
    if not parsed.get("success"):
        raise FigmaMCPError(f"Figma Console MCP could not read the board: {parsed}")
    return parsed["data"]


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
