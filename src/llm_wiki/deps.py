"""Shared FastAPI dependency functions.

Provides DI helpers that routes and services use to access the wiki
singleton and optional profile identifier.

**Coding standard:** All routes MUST use ``Depends(get_wiki)`` to access the
``WikiQuery`` singleton. Never read ``request.app.state.wiki`` directly — that
pattern exists only inside the dependency functions themselves.

For ``UserProfile`` scoped access, use ``Depends(get_profile_id)`` to read the
``X-Profile-ID`` header.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Header, Request

from llm_wiki.api.user_jobs import UserJobStore
from llm_wiki.config.loader import WikiConfig
from llm_wiki.knowledge.storage import WorkspaceFactStore
from llm_wiki.query.search import WikiQuery


async def get_wiki(request: Request) -> WikiQuery:
    """Return the :class:`WikiQuery` singleton stored on ``app.state``.

    Every route that shares the same FastAPI app receives the exact same
    instance — no new :class:`WikiQuery` is constructed per request.
    """
    return request.app.state.wiki  # type: ignore[no-any-return]


async def get_wiki_config(request: Request) -> WikiConfig | None:
    """Return the :class:`WikiConfig` singleton stored on ``app.state``.

    Returns:
        The :class:`WikiConfig` singleton, or ``None`` if not configured.
    """
    return getattr(request.app.state, "wiki_config", None)  # type: ignore[return-value]


async def get_user_job_store(request: Request) -> UserJobStore:
    """Return the :class:`UserJobStore` singleton from app state."""
    return request.app.state.user_job_store  # type: ignore[no-any-return]


def get_user_job_store_sync(wiki_base: Path) -> UserJobStore:
    """Return the shared :class:`UserJobStore` for the given wiki base."""
    from llm_wiki.api import user_jobs  # noqa: PLC0414

    return user_jobs.get_user_job_store(wiki_base)


async def get_profile_id(x_profile_id: str | None = Header(default=None)) -> str | None:
    """Return the ``X-Profile-ID`` header value if provided."""
    return x_profile_id


async def get_knowledge_store(request: Request) -> WorkspaceFactStore:
    """Return the :class:`WorkspaceFactStore` singleton stored on ``app.state``."""
    return request.app.state.knowledge_store  # type: ignore[no-any-return]
