"""Minimal FastAPI application entry point.

Populated by Story 1.4 (FastAPI skeleton) and Story 1.8 (MCP + REST endpoints).
"""

import os
from pathlib import Path

from fastapi import FastAPI

app = FastAPI(title="LLM Wiki", version="0.1.0")


@app.get("/v1/health")
def health():
    """Health check for Docker HEALTHCHECK and supervisory tools."""
    config_dir = os.environ.get("WIKI_CONFIG_DIR", "config")
    wiki_config = Path(config_dir) if Path(config_dir).is_dir() else Path("config")
    running = wiki_config.is_dir() if wiki_config else False
    return {"running": running, "config_dir": str(wiki_config) if wiki_config else "unknown"}
