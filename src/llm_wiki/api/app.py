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

from fastapi import FastAPI, Request

from llm_wiki.api.errors import register_exception_handlers
from llm_wiki.initializer import boot_wiki
from llm_wiki.query.log import QueryLogStore

if TYPE_CHECKING:
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

logger = logging.getLogger(__name__)


# Router imports added in Story 1.6 (lazy, inside create_app to avoid shadowing)


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

    # Knowledge fact store (Story HF.1)
    from llm_wiki.knowledge.storage import WorkspaceFactStore  # noqa: E303

    app.state.knowledge_store = WorkspaceFactStore(  # type: ignore[assignment]
        wiki_base=str(wiki_root),
    )
    logger.info("Knowledge fact store initialized (wiki_base=%s)", wiki_root)
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

    # Persist UI password to file for TUI reference (if writable)
    _pw_file = Path(wiki_root) / "state" / ".ui_password"
    try:
        _pw_file.write_text(app.state.ui_password)
    except Exception:
        pass  # non-fatal (may be read-only volume)

    # Mount UI router if webui is enabled
    _webui_enabled = False
    if _wiki_config is not None:
        _webui_enabled = _wiki_config.daemon.daemon.features.webui_enabled
    if _webui_enabled:
        from llm_wiki.api.ui_routes import router as _ui_router

        app.include_router(_ui_router)
        logger.info("UI routes mounted at /ui/* (webui_enabled=true)")
    else:
        logger.info("UI routes disabled (webui_enabled=false)")

    # Create MCP server, mount it, and start the session manager
    mcp_mgr: StreamableHTTPSessionManager | None = None
    try:
        from llm_wiki.mcp.server import create_mcp_server

        _mcp_server, mcp_asgi, mcp_mgr = create_mcp_server(
            wiki,
            wiki_config=_wiki_config,
            query_log=app.state.query_log,
            knowledge_store=app.state.knowledge_store,
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

    # Close the pooled honcho detector client
    from llm_wiki.honcho import shutdown_detector_client

    shutdown_detector_client()


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

    _ui_password = os.environ.get("WIKI_UI_PASSWORD", "")
    if not _ui_password:
        raise RuntimeError("UI auth requires WIKI_UI_PASSWORD environment variable")
    _ui_user = os.environ.get("WIKI_UI_USER", "admin")
    app.state.ui_password = _ui_password
    app.state.ui_user = _ui_user
    logger.info("UI auth — user: %s", _ui_user)

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

    # Mount routers added in Epic H (Honcho Integration)
    from llm_wiki.api.routers import honcho as _honcho  # noqa: E303

    app.include_router(_honcho.router)

    # Mount routers added in Epic HF (Homefront Facts)
    from llm_wiki.api.routers import facts as _facts  # noqa: E303

    app.include_router(_facts.router)

    # Mount routers added in Epic HF (Workspace-scoped Knowledge)
    from llm_wiki.api.routers import knowledge as _knowledge  # noqa: E303

    app.include_router(_knowledge.router)

    # Legacy inline health check endpoint removed — use /v1/health and /v1/daemon/status instead

    return app


# Module-level app instance for service gateways (e.g. Docker HEALTHCHECK).
app = create_app()
