"""Honcho integration — detect, push, and pull with Honcho conversational memory.

Detection tries http://localhost:8000 (Honcho's default) and returns
availability + connection metadata. This is used by the REST /v1/honcho/status
endpoint and the daemon job scheduler.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

HONCHO_ENVIRONMENTS = {
    "local": "http://localhost:8000",
    "production": "https://api.honcho.dev",
}


def detect_honcho(base_url: str | None = None) -> dict:
    """Detect if Honcho is running and return connection info.

    Args:
        base_url: Honcho server URL. Defaults to HONCHO_URL env or localhost:8000.

    Returns:
        Dict with keys: available, url, status, response.
    """
    url = base_url or os.environ.get("HONCHO_URL") or HONCHO_ENVIRONMENTS["local"]

    try:
        resp = httpx.get(f"{url}/health", timeout=3.0)
        return {
            "available": True,
            "url": url,
            "status": resp.status_code,
            "response": resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else resp.text,
        }
    except httpx.HTTPError as e:
        logger.debug("Honcho detect failed at %s: %s", url, e)
        return {
            "available": False,
            "url": url,
            "status": 0,
            "response": {"error": str(e)},
        }
