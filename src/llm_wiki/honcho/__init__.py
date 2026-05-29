"""Honcho integration — detect, push, and pull with Honcho conversational memory.

Detection uses a shared httpx.Client (created on first call) to avoid the
overhead of opening a new TCP connection for every health check.
This is used by the REST /v1/honcho/status endpoint and the daemon job scheduler.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

HONCHO_ENVIRONMENTS: dict[str, str] = {
    "local": "http://localhost:8000",
    "staging": "https://staging.honcho.dev",
    "production": "https://api.honcho.dev",
}

_detector_client: httpx.Client | None = None


def _get_detector_client() -> httpx.Client:
    """Return (creating lazily) a shared httpx.Client for health checks."""
    global _detector_client
    if _detector_client is None:
        _detector_client = httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0))
    return _detector_client


def _ok_result(url: str, status: int, response: object) -> dict:
    return {
        "available": True,
        "url": url,
        "status": status,
        "response": response,
    }


def _error_result(url: str, status: int, error_msg: str) -> dict:
    return {
        "available": False,
        "url": url,
        "status": status,
        "response": {"error": error_msg},
    }


def detect_honcho(base_url: str | None = None) -> dict:
    """Detect if Honcho is running and return connection info.

    Args:
        base_url: Honcho server URL. Defaults to HONCHO_URL env or localhost:8000.

    Returns:
        Dict with keys: ``available``, ``url``, ``status``, ``response``.
        When ``available`` is ``False``, a ``status_message`` key may be
        appended by the caller.
    """
    url = base_url or os.environ.get("HONCHO_URL") or HONCHO_ENVIRONMENTS["local"]

    try:
        client = _get_detector_client()
        resp = client.get(f"{url}/health")
        if 200 <= resp.status_code < 300:
            body: object
            if resp.headers.get("content-type", "").startswith("application/json"):
                body = resp.json()
            else:
                body = resp.text
            return _ok_result(url, resp.status_code, body)
        # Non-2xx is treated as unavailable (500, 404, etc.)
        return _error_result(url, resp.status_code, f"HTTP {resp.status_code}")
    except httpx.HTTPError as e:
        logger.debug("Honcho detect failed at %s: %s", url, e)
        return _error_result(url, 0, str(e))


def shutdown_detector_client() -> None:
    """Gracefully close the pooled detector client. Avoids lingering file handles after FastAPI shutdown."""
    global _detector_client
    if _detector_client is not None:
        _detector_client.close()
        _detector_client = None
