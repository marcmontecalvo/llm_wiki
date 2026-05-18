"""Shared FastAPI dependency functions.

Provides DI helpers that routes and services use to access the wiki
singleton and optional profile identifier.
"""

from fastapi import Header, Request

from llm_wiki.query.search import WikiQuery


async def get_wiki(request: Request) -> WikiQuery:
    """Return the :class:`WikiQuery` singleton stored on ``app.state``.

    Every route that shares the same FastAPI app receives the exact same
    instance — no new :class:`WikiQuery` is constructed per request.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The :class:`WikiQuery` singleton.
    """
    return request.app.state.wiki  # type: ignore[no-any-return]


async def get_profile_id(x_profile_id: str | None = Header(default=None)) -> str | None:
    """Return the ``X-Profile-ID`` header value if provided.

    Args:
        x_profile_id: Value of the X-Profile-ID request header.

    Returns:
        The profile ID string, or ``None``.
    """
    return x_profile_id
