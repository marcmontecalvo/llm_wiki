"""Tests for Honcho detectability module.

Tests the honcho_status endpoint and the detect_honcho function.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── detect_honcho unit tests ───────────────────────────────────────────────


def test_detect_honcho_available():
    """When Honcho returns 200 from /health, return available=True."""
    from llm_wiki.honcho import detect_honcho  # noqa: PLC0415

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {"status": "ok"}

    with patch("llm_wiki.honcho.httpx.get", return_value=mock_resp):
        result = detect_honcho("http://test-honcho:8000")
        assert result["available"] is True
        assert result["url"] == "http://test-honcho:8000"
        assert result["status"] == 200
        assert result["response"] == {"status": "ok"}


def test_detect_honcho_unavailable():
    """When Honcho is unreachable, return available=False."""
    import httpx  # noqa: PLC0415

    from llm_wiki.honcho import detect_honcho  # noqa: PLC0415

    with patch("llm_wiki.honcho.httpx.get", side_effect=httpx.ConnectError("refused")):
        result = detect_honcho("http://nohoncho:9999")
        assert result["available"] is False
        assert result["url"] == "http://nohoncho:9999"
        assert result["status"] == 0
        assert "error" in result["response"]


def test_detect_honcho_env_url():
    """Honcho detect honors HONCHO_URL env var."""
    import httpx  # noqa: PLC0415

    from llm_wiki.honcho import detect_honcho  # noqa: PLC0415

    with patch.dict(os.environ, {"HONCHO_URL": "http://fromenv:8000"}):
        with patch("llm_wiki.honcho.httpx.get", side_effect=httpx.ConnectError("refused")):
            result = detect_honcho()  # no explicit URL
            assert result["url"] == "http://fromenv:8000"


def test_detect_honcho_default_url(monkeypatch):
    """Honcho detect defaults to localhost:8000."""
    import httpx  # noqa: PLC0415

    from llm_wiki.honcho import detect_honcho  # noqa: PLC0415

    monkeypatch.delenv("HONCHO_URL", raising=False)
    with patch("llm_wiki.honcho.httpx.get", side_effect=httpx.ConnectError("refused")):
        result = detect_honcho()
        assert result["url"] == "http://localhost:8000"


# ── /v1/honcho/status REST endpoint ────────────────────────────────────────


@pytest.fixture
def app():
    app = FastAPI()
    from llm_wiki.api.routers.honcho import router  # noqa: PLC0415

    app.include_router(router)
    return app


def test_honcho_status_endpoint_available(app, monkeypatch):
    monkeypatch.setenv("HONCHO_URL", "http://test:8000")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {"status": "ok"}
    monkeypatch.setattr("llm_wiki.honcho.httpx.get", lambda *a, **k: mock_resp)

    client = TestClient(app)
    resp = client.get("/v1/honcho/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True


def test_honcho_status_endpoint_unavailable(app, monkeypatch):
    import httpx  # noqa: PLC0415

    monkeypatch.setenv("HONCHO_URL", "http://noplaces:1234")

    def raise_error(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr("llm_wiki.honcho.httpx.get", raise_error)
    client = TestClient(app)
    resp = client.get("/v1/honcho/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert "status_message" in data
