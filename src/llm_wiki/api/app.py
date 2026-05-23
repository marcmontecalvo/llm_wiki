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
from llm_wiki.initializer import boot_wiki
from llm_wiki.query.log import QueryLogStore
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

    Uses :func:`boot_wiki` to ensure HTTP and stdio paths are identical.
    """
    wiki_root = Path(os.environ.get("WIKI_ROOT", "wiki_system"))
    config_dir = Path(os.environ.get("WIKI_CONFIG_DIR", "config"))

    wiki, _wiki_config, user_job_store, deep_jobs = boot_wiki(wiki_root, config_dir)
    app.state.wiki = wiki
    if _wiki_config is not None:
        app.state.wiki_config = _wiki_config
    app.state.user_job_store = user_job_store
    app.state.deep_jobs = deep_jobs  # type: ignore[assignment]
    try:
        app.state.query_log = QueryLogStore(wiki_root / "state" / "query_log.db")  # type: ignore[assignment]  # noqa: E501 PLR2004
        app.state.query_log_error = False  # type: ignore[assignment]
    except Exception as e:
        logger.error("Query log init failed (api logging degraded): %s", e)
        app.state.query_log = None  # type: ignore[assignment]
        app.state.query_log_error = True  # type: ignore[assignment]
        # Wire init failure signal into OTel metrics (Story 1.12.5)
        try:
            from llm_wiki.observability.metrics import set_init_failed

            set_init_failed(str(e))
        except Exception:
            pass

    # Create MCP server, mount it, and start the session manager
    mcp_mgr: StreamableHTTPSessionManager | None = None
    try:
        from llm_wiki.mcp.server import create_mcp_server

        _mcp_server, mcp_asgi, mcp_mgr = create_mcp_server(
            wiki, wiki_config=_wiki_config, query_log=app.state.query_log
        )  # type: ignore[attr-defined]
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

    # Start deep query TTL cleanup task
    async def _cleanup_deep_jobs():
        while True:
            await asyncio.sleep(60)
            expired = [
                jid
                for jid, j in app.state.deep_jobs.items()  # type: ignore[attr-defined]
                if j.is_expired
            ]
            for jid in expired:
                del app.state.deep_jobs[jid]  # type: ignore[attr-defined]

    asyncio.create_task(_cleanup_deep_jobs())

    # Shutdown
    logger.info("LLM Wiki service shutting down")

    # Shutdown OTel SDK (flush pending spans/metrics/logs)
    from llm_wiki.observability import sdk as _sdk

    _sdk.shutdown()


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
        openapi_url="/v1/openapi.json",
        openapi_version="3.1.0",
    )

    # OTel SDK init (Story 1.12.5)
    from llm_wiki.observability import sdk

    sdk.initialize()

    # FastAPI auto-instrumentation — instruments every HTTP request with a span
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)

    # Register OTel logging handler (injects trace_id/span_id into log records)
    from llm_wiki.observability import logging as otel_logging

    otel_logging.setup_otel_logging()

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

    # Mount routers added in Story 1.7
    from llm_wiki.api.routers import export as _export  # noqa: E303
    from llm_wiki.api.routers import pages as _pages  # noqa: E303
    from llm_wiki.api.routers import query as _query  # noqa: E303
    from llm_wiki.api.routers import search as _search  # noqa: E303

    app.include_router(_query.router)
    app.include_router(_search.router)
    app.include_router(_pages.router)
    app.include_router(_export.router)

    # Mount routers added in Story 3.4 (Synthesis Cache)
    from llm_wiki.api.routers import synthesis as _synthesis  # noqa: E303

    app.include_router(_synthesis.router)

    # Mount routers added in Story 3.5 (Per-Domain Dashboards)
    from llm_wiki.api.routers import dashboard as _dashboard  # noqa: E303

    app.include_router(_dashboard.router)

    # Mount routers added in Story 3.6 (Topic Archive Lifecycle)
    from llm_wiki.api.routers import archive as _archive  # noqa: E303

    app.include_router(_archive.router)

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
