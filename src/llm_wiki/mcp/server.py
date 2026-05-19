"""MCP server and transport.

Verified import paths for mcp==1.27.0:

    from mcp.server import Server
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from mcp.server.fastmcp.server import StreamableHTTPASGIApp

In the SDK, StreamableHTTPASGIApp is a thin wrapper that makes
session_manager.handle_request callable as an ASGI app. But the
session_manager MUST be started via its run() async context manager
before any requests are handled.

Approach: FastAPI lifespan starts the session manager via
async with session_manager.run(), and a custom ASGI app (MCPAsgiApp)
wraps handle_request for Mount compatibility.

stdio transport: ``run_stdio_server()`` + ``__main__.py`` enables
``python -m llm_wiki.mcp.server``.
"""

from __future__ import annotations

import logging

from mcp.server import FastMCP
from mcp.server.streamable_http_manager import (
    StreamableHTTPSessionManager,
)
from starlette.types import Receive, Scope, Send

from llm_wiki.mcp.tools import register_tools

logger = logging.getLogger(__name__)


class MCPAsgiApp:
    """ASGI wrapper for MCP session manager handle_request.

    Delegates each ASGI call to session_manager.handle_request().
    The session_manager must be running (via run() context manager)
    before any requests arrive -- provided by the FastAPI lifespan.
    """

    def __init__(self, session_manager) -> None:  # type: ignore[no-untyped-def]
        self.session_manager = session_manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.session_manager.handle_request(scope, receive, send)


def create_mcp_server(
    wiki,
    wiki_config=None,
    query_log=None,  # type: ignore[default-value]  # noqa: B006
) -> tuple[FastMCP, MCPAsgiApp, StreamableHTTPSessionManager]:
    """Create an MCP server and its ASGI mountable app.

    Args:
        wiki: WikiQuery singleton to share with MCP tools.
        wiki_config: Optional wiki configuration.
        query_log: Optional QueryLogStore singleton for logging queries.

    Returns:
        Tuple of (FastMCP instance, MCPAsgiApp mountable ASGI wrapper,
        StreamableHTTPSessionManager for lifespan management).
    """
    server = FastMCP("llm-wiki", stateless_http=True)
    register_tools(server, wiki, wiki_config=wiki_config, query_log=query_log)  # type: ignore[arg-type]

    # Access streamable_http_app to trigger internal session manager creation
    _ = server.streamable_http_app

    # The session manager was created internally by FastMCP
    mgr = server._session_manager  # type: ignore[attr-defined]
    assert mgr is not None

    asgi = MCPAsgiApp(mgr)

    return server, asgi, mgr


async def run_stdio_server(wiki, query_log=None) -> None:  # type: ignore[no-untyped-def]
    """Run the MCP server over stdio transport.

    Used when a harness spawns the service as a subprocess:
        python -m llm_wiki.mcp.server

    Args:
        wiki: WikiQuery singleton to share with MCP tools.
        query_log: Optional QueryLogStore singleton for logging queries.
    """
    server = FastMCP("llm-wiki", stateless_http=True)
    register_tools(server, wiki)  # stdio path has no config/query_log
    await server.run_stdio_async()
