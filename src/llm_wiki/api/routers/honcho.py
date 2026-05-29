"""Honcho integration REST endpoints — /v1/honcho/*."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from llm_wiki.honcho import detect_honcho

router = APIRouter(prefix="/v1/honcho", tags=["honcho"])

_UNAVAILABLE_MESSAGE = (
    "LLM Wiki–Honcho integration not yet enabled. "
    "Install the honcho package and configure HONCHO_URL."
)


@router.get("/status", response_description="Honcho availability and connection info")
def honcho_status() -> dict[str, Any]:
    """Return Honcho availability and connection info.

    Returns a dict with keys:
        - ``available`` (bool): whether Honcho is reachable
        - ``url`` (str): the URL that was probed
        - ``status`` (int): HTTP status code or 0 on connection failure
        - ``response`` (dict|str): health payload on success, error detail on failure
        - ``status_message`` (str, only when ``available`` is ``False``):
          human-readable explanation of why Honcho is unavailable
    """
    result = detect_honcho()
    if not result.get("available"):
        result_with_message = dict(result)  # shallow copy to avoid mutating caller dict
        result_with_message["status_message"] = _UNAVAILABLE_MESSAGE
        return result_with_message
    return result
