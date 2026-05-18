"""Integration tests for the FastAPI app skeleton using TestClient."""

from fastapi.testclient import TestClient

from llm_wiki.api.app import create_app


def _build_test_app():
    """Build the test app. Mini-wikis are not initialized during import so
    the lifespan can fail (FAISS missing). We test with the raw create_app
    to avoid triggering the lifespan before importing test dependencies."""
    app = create_app()
    return app


def test_health_returns_200():
    app = _build_test_app()
    client = TestClient(app)
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert "running" in r.json()


def test_version_header_present():
    app = _build_test_app()
    client = TestClient(app)
    r = client.get("/v1/health")
    assert "X-LLM-Wiki-Version" in r.headers


def test_version_header_value():
    app = _build_test_app()
    client = TestClient(app)
    r = client.get("/v1/health")
    assert r.headers["X-LLM-Wiki-Version"] == "0.1.0"


def test_unknown_route_returns_404():
    app = _build_test_app()
    client = TestClient(app)
    r = client.get("/v1/nonexistent")
    assert r.status_code == 404


def test_health_response_has_config_dir():
    app = _build_test_app()
    client = TestClient(app)
    r = client.get("/v1/health")
    data = r.json()
    assert "config_dir" in data
    assert isinstance(data["config_dir"], str)
