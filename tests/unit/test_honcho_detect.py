"""Tests for Honcho detectability module.

Tests the honcho_status endpoint and the detect_honcho function.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── helpers ────────────────────────────────────────────────────────────────


def _make_json_response(status: int = 200, body: object = None) -> MagicMock:
    """Build a mock httpx.Response-compatible object for JSON responses."""
    mock = MagicMock()
    mock.status_code = status
    mock.headers = {"content-type": "application/json"}
    mock.json.return_value = body
    mock.text = "" if status == 200 else "Not Found"
    return mock


def _make_text_response(status: int = 200) -> MagicMock:
    """Build a mock httpx.Response-compatible object for text responses."""
    mock = MagicMock()
    mock.status_code = status
    mock.headers = {"content-type": "text/plain; charset=utf-8"}

    def _json_fail():
        raise ValueError("Could not decode response")

    mock.json.side_effect = _json_fail
    mock.text = "ok"
    return mock


# ── fixtures ───────────────────────────────────────────────────────────────

RESPONSE_200_JSON = _make_json_response(200, {"status": "ok"})
RESPONSE_404 = _make_json_response(404, "Not Found")
RESPONSE_500 = _make_json_response(500, "Internal Server Error")
RESPONSE_200_TEXT = _make_text_response(200)

# Mock clients that return a response on .get()
_CLIENT_200_JSON = MagicMock(get=MagicMock(return_value=RESPONSE_200_JSON))
_CLIENT_404 = MagicMock(get=MagicMock(return_value=RESPONSE_404))
_CLIENT_500 = MagicMock(get=MagicMock(return_value=RESPONSE_500))
_CLIENT_200_TEXT = MagicMock(get=MagicMock(return_value=RESPONSE_200_TEXT))


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    """Reset the shared detector client so mocks don't leak between tests."""
    import llm_wiki.honcho

    llm_wiki.honcho._detector_client = None  # type: ignore[attr-defined]
    yield
    llm_wiki.honcho._detector_client = None  # type: ignore[attr-defined]


def _set_client_mock(mock_client: MagicMock) -> None:
    """Replace the module-level detector client with a MagicMock."""
    import llm_wiki.honcho

    llm_wiki.honcho._detector_client = mock_client  # type: ignore[assignment]


# ── detect_honcho unit tests ───────────────────────────────────────────────


def test_detect_honcho_available(_reset_client: None) -> None:
    """When Honcho returns 200 from /health, return available=True."""
    from llm_wiki.honcho import detect_honcho

    _set_client_mock(_CLIENT_200_JSON)
    result = detect_honcho("http://test-honcho:8000")

    assert result["available"] is True
    assert result["url"] == "http://test-honcho:8000"
    assert result["status"] == 200
    assert result["response"] == {"status": "ok"}


def test_detect_honcho_404_treated_as_unavailable(_reset_client: None) -> None:
    """A 404 response should be treated as unavailable (not True)."""
    from llm_wiki.honcho import detect_honcho

    _set_client_mock(_CLIENT_404)
    result = detect_honcho("http://nohoncho:8000")

    assert result["available"] is False
    assert result["status"] == 404
    assert result["response"] == {"error": "HTTP 404"}


def test_detect_honcho_500_treated_as_unavailable(_reset_client: None) -> None:
    """A 500 response should be treated as unavailable."""
    from llm_wiki.honcho import detect_honcho

    _set_client_mock(_CLIENT_500)
    result = detect_honcho("http://broken:8000")

    assert result["available"] is False
    assert result["status"] == 500
    assert result["response"] == {"error": "HTTP 500"}


def test_detect_honcho_unavailable(_reset_client: None) -> None:
    """When Honcho is unreachable (connection error), return available=False."""
    import llm_wiki.honcho
    from llm_wiki.honcho import detect_honcho

    mock_client = MagicMock()
    mock_client.get.side_effect = httpx.ConnectError("refused")
    llm_wiki.honcho._detector_client = mock_client  # type: ignore[assignment]
    result = detect_honcho("http://nohoncho:9999")

    assert result["available"] is False
    assert result["url"] == "http://nohoncho:9999"
    assert result["status"] == 0
    assert "error" in result["response"]


def test_detect_honcho_env_url(_reset_client: None) -> None:
    """Honcho detect honors HONCHO_URL env var."""
    import llm_wiki.honcho
    from llm_wiki.honcho import detect_honcho

    with patch.dict("os.environ", {"HONCHO_URL": "http://fromenv:8000"}):
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("refused")
        llm_wiki.honcho._detector_client = mock_client  # type: ignore[assignment]
        result = detect_honcho()  # no explicit URL

    assert result["url"] == "http://fromenv:8000"


def test_detect_honcho_default_url(_reset_client: None) -> None:
    """Honcho detect defaults to localhost:8000."""
    import llm_wiki.honcho
    from llm_wiki.honcho import detect_honcho

    with patch.dict("os.environ", {}, clear=True):
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("refused")
        llm_wiki.honcho._detector_client = mock_client  # type: ignore[assignment]
        result = detect_honcho()

    assert result["url"] == "http://localhost:8000"


def test_detect_honcho_non_json_response(_reset_client: None) -> None:
    """Honcho returns plain text body — should return raw text, not crash."""
    from llm_wiki.honcho import detect_honcho

    _set_client_mock(_CLIENT_200_TEXT)
    result = detect_honcho("http://text:8000")

    assert result["available"] is True
    assert result["response"] == "ok"
    assert isinstance(result["response"], str)


# ── /v1/honcho/status REST endpoint ────────────────────────────────────────


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    from llm_wiki.api.routers.honcho import router  # noqa: PLC0415

    application.include_router(router)
    return application


def test_honcho_status_endpoint_available(_reset_client: None, app: FastAPI) -> None:
    """Honcho returns 200 — endpoint reports available=True, no status_message."""
    with patch.dict("os.environ", {"HONCHO_URL": "http://test:8000"}):
        _set_client_mock(_CLIENT_200_JSON)
        client = TestClient(app)
        resp = client.get("/v1/honcho/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True
    assert "status_message" not in data


def test_honcho_status_endpoint_unavailable(_reset_client: None, app: FastAPI) -> None:
    """Honcho unreachable — endpoint reports available=False with status_message."""
    with patch.dict("os.environ", {"HONCHO_URL": "http://noplaces:1234"}):
        import llm_wiki.honcho

        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("refused")
        llm_wiki.honcho._detector_client = mock_client  # type: ignore[assignment]
        client = TestClient(app)
        resp = client.get("/v1/honcho/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert "status_message" in data
    assert "not yet enabled" in data["status_message"]


def test_honcho_status_endpoint_404_returns_error(_reset_client: None, app: FastAPI) -> None:
    """A 404 from Honcho is treated as unavailable — status_message present."""
    _set_client_mock(_CLIENT_404)
    client = TestClient(app)
    resp = client.get("/v1/honcho/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["status"] == 404
    assert "status_message" in data


def test_honcho_status_message_not_on_success(_reset_client: None, app: FastAPI) -> None:
    """Success path should NOT include status_message."""
    _set_client_mock(_CLIENT_200_JSON)
    data = TestClient(app).get("/v1/honcho/status").json()

    assert "status_message" not in data


def test_honcho_env_staging_exists() -> None:
    """HONCHO_ENVIRONMENTS should contain a staging entry."""
    from llm_wiki.honcho import HONCHO_ENVIRONMENTS

    assert "staging" in HONCHO_ENVIRONMENTS
    assert HONCHO_ENVIRONMENTS["staging"] == "https://staging.honcho.dev"
