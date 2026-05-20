"""Run MCP server over stdio transport.

Used when a harness spawns the service as a subprocess:
    python -m llm_wiki.mcp.server
"""

import asyncio
import os
from pathlib import Path

from llm_wiki.config.loader import load_config
from llm_wiki.mcp.server import run_stdio_server
from llm_wiki.query.search import WikiQuery


def main() -> None:
    """Entry point for stdio transport."""
    config_dir = Path(os.environ.get("WIKI_CONFIG_DIR", "config"))
    wiki_config = None
    try:
        wiki_config = load_config(config_dir)
    except Exception:
        pass  # MCP stdio can run without config; retry scoped search will fail-closed

    wiki = WikiQuery(wiki_config=wiki_config)
    asyncio.run(run_stdio_server(wiki))


if __name__ == "__main__":
    main()
