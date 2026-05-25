"""Honcho integration REST endpoints — /v1/honcho/*."""

from __future__ import annotations

from fastapi import APIRouter

from llm_wiki.honcho import detect_honcho

router = APIRouter(prefix="/v1/honcho", tags=["honcho"])


@router.get("/status")
async def honcho_status() -> dict:
    """Return Honcho availability and connection info.

    Returns {"available": bool, "url": str, "status": int, "response": dict}
    or a placeholder explaining integration is not enabled when not available.
    """
    result = detect_honcho()
    if not result.get("available"):
        result["status_message"] = (
            "LLM Wiki–Honcho integration not yet enabled. "
            "Install the honcho package and configure HONCHO_URL."
        )
    return result
