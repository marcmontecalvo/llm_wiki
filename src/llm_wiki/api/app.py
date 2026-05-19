"""FastAPI application entry point and lifespan management.

Populated by Story 1.4 (FastAPI skeleton), Story 1.6 (health/daemon/ingest),
and Story 1.8 (MCP + REST endpoints).
The lifespan creates a single WikiQuery singleton that is shared across all
REST and MCP surfaces.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, Request

from llm_wiki.api.errors import register_exception_handlers
from llm_wiki.deps import get_wiki
from llm_wiki.initializer import _maybe_init_wiki_root
from llm_wiki.query.search import WikiQuery

if TYPE_CHECKING:
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

logger = logging.getLogger(__name__)

# PID file written by WikiDaemon so FastAPI can check if it is alive.
_DAEMON_PID_FILE = "/wiki/state/daemon.pid"

# Router imports added in Story 1.6 (lazy, inside create_app to avoid shadowing)


def _daemon_running() -> bool:
    """Return True if the daemon PID file exists and the PID is alive."""
    try:
        pid = Path(_DAEMON_PID_FILE).read_text().strip()
        if not pid:
            return False
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the wiki root, config, and WikiQuery singleton.

    Order matters:
      1. _maybe_init_wiki_root() — creates directories if empty volume
      2. load_config() — loads YAML config
      3. WikiQuery() — builds all indexes (FAISS loads here)
      4. MCP session manager started via run() context
    """
    wiki_root = Path(os.environ.get("WIKI_ROOT", "wiki_system"))
    config_dir = Path(os.environ.get("WIKI_CONFIG_DIR", "config"))

    # MUST be first — WikiConfig.load() raises FileNotFoundError on empty volume
    _maybe_init_wiki_root(wiki_root)

    # Load config from WIKI_CONFIG_DIR env var (default /config or config/).
    # The config will be used by routes in Story 1.6.
    _wiki_config = None
    try:
        from llm_wiki.config.loader import load_config

        _wiki_config = load_config(config_dir)
    except Exception as e:
        logger.warning("Config load failed (non-fatal for startup): %s", e)

    app.state.wiki = WikiQuery(wiki_base=wiki_root, index_dir=wiki_root / "index")
    if _wiki_config is not None:
        app.state.wiki_config = _wiki_config  # Make config available to routes

    # UserJobStore persists ingest jobs to disk (Story 1.6)
    user_jobs_path = wiki_root / "state"
    from llm_wiki.api.user_jobs import UserJobStore  # noqa: E303

    app.state.user_job_store = UserJobStore(state_dir=user_jobs_path)

    # Initialize deep query job tracking
    app.state.deep_jobs = {}  # type: ignore[assignment]

    # Create MCP server, mount it, and start the session manager
    mcp_mgr: StreamableHTTPSessionManager | None = None
    try:
        from llm_wiki.mcp.server import create_mcp_server

        _mcp_server, mcp_asgi, mcp_mgr = create_mcp_server(app.state.wiki)
        app.mount("/mcp", mcp_asgi)
    except Exception as e:
        logger.warning("MCP server init failed (non-fatal): %s", e)
        mcp_mgr = None

    # Session manager lifespan — start before yield, cancel after
    if mcp_mgr is not None:
        async with mcp_mgr.run():
            yield
    else:
        yield

    # Shutdown
    logger.info("LLM Wiki service shutting down")


def create_app() -> FastAPI:
    """Factory function to create the FastAPI application.

    Returns:
        Configured FastAPI application.
    """
    from llm_wiki import __version__

    app = FastAPI(
        title="LLM Wiki",
        version=__version__,
        lifespan=lifespan,
    )

    # Register exception handlers before adding other middleware
    register_exception_handlers(app)

    # Version header middleware
    @app.middleware("http")
    async def add_version_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-LLM-Wiki-Version"] = __version__
        return response

    # Mount routers added in Story 1.6
    from llm_wiki.api.routers import domains as _domains  # noqa: E303
    from llm_wiki.api.routers import health as _health
    from llm_wiki.api.routers import ingest as _ingest

    app.include_router(_health.router)
    app.include_router(_ingest.router)
    app.include_router(_domains.router)

    # Legacy inline health check endpoint (story 1.6 routes at /v1/health are primary)

    @app.get("/v1/health-legacy")
    async def _legacy_health(wiki: WikiQuery = Depends(get_wiki)) -> dict:
        daemon_running = False
        pid_file = wiki.wiki_base / "state" / "daemon.pid"
        if await asyncio.to_thread(pid_file.exists):
            try:
                pid_text = await asyncio.to_thread(pid_file.read_text)
                pid = int(pid_text.strip())
                os.kill(pid, 0)
                daemon_running = True
            except (ValueError, ProcessLookupError, PermissionError, OSError):
                daemon_running = False
        llm_enabled = False
        config = getattr(app.state, "wiki_config", None)
        if config is not None:
            llm_enabled = config.daemon.daemon.features.llm_extraction
        return {
            "running": True,
            "daemon_running": daemon_running,
            "llm_extraction_enabled": llm_enabled,
        }

    return app


# Module-level app instance for service gateways (e.g. Docker HEALTHCHECK).
app = create_app()
