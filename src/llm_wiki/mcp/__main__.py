"""Run MCP server over stdio transport.

Used when a harness spawns the service as a subprocess:
    python -m llm_wiki.mcp.server
"""

import asyncio

from llm_wiki.deps import WikiQuery
from llm_wiki.mcp.server import run_stdio_server


def main() -> None:
    """Entry point for stdio transport."""
    wiki = WikiQuery()
    asyncio.run(run_stdio_server(wiki))


if __name__ == "__main__":
    main()
