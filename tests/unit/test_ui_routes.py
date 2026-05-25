"""Tests for Web UI routes (status codes, auth, routing)."""

import base64
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_wiki.api.ui_routes import router


@pytest.fixture
def mock_wiki():
    """Minimal mock WikiQuery with attributes used by ui_browse."""
    wiki = MagicMock()
    wiki.wiki_base = Path("/tmp/mock-wiki")
    wiki._wiki_config = None
    wiki.list_pages.return_value = ([], None)
    wiki.metadata_index = MagicMock()
    wiki.metadata_index.by_domain = {}
    return wiki


@pytest.fixture
def app(mock_wiki) -> FastAPI:
    """Build a minimal FastAPI app with UI routes mounted."""
    app = FastAPI()
    app.state.ui_password = "test-password"
    app.state.wiki = mock_wiki
    app.include_router(router)
    return app


def _header(user: str, password: str) -> dict[str, str]:
    encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


class TestUIRoutes:
    def test_home(self, app):
        client = TestClient(app)
        resp = client.get("/ui/", headers=_header("admin", "test-password"))
        assert resp.status_code in (200, 501)  # 200 if template exists, 501 "coming soon"

    def test_search(self, app):
        client = TestClient(app)
        resp = client.get("/ui/search", headers=_header("admin", "test-password"))
        assert resp.status_code in (200, 501)

    def test_browse(self, app):
        client = TestClient(app)
        resp = client.get("/ui/browse", headers=_header("admin", "test-password"))
        assert resp.status_code in (200, 501)

    def test_dashboard(self, app):
        client = TestClient(app)
        resp = client.get("/ui/dashboard", headers=_header("admin", "test-password"))
        assert resp.status_code in (200, 501)

    def test_issues(self, app):
        client = TestClient(app)
        resp = client.get("/ui/issues", headers=_header("admin", "test-password"))
        assert resp.status_code in (200, 501)

    def test_page_detail(self, app):
        client = TestClient(app)
        resp = client.get("/ui/page/test-page-id", headers=_header("admin", "test-password"))
        assert resp.status_code in (200, 501)

    def test_no_auth_returns_401(self, app):
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/ui/")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Authentication required"
        assert resp.headers.get("www-authenticate") == "Basic"

    def test_wrong_password_returns_401(self, app):
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/ui/", headers=_header("admin", "wrong-password"))
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Authentication required"
        assert resp.headers.get("www-authenticate") == "Basic"

    def test_empty_password_header_returns_401(self, app):
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/ui/", headers={"Authorization": ""})
        assert resp.status_code == 401

    def test_missing_authorization_returns_401(self, app):
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/ui/")
        assert resp.status_code == 401

    def test_no_password_configured_returns_500(self, monkeypatch):
        """If ui_password is not set, routes return 500 (not configured)."""
        tmp = Path("/tmp/ui-test-noconfig")
        (tmp / "state").mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("WIKI_ROOT", str(tmp))
        monkeypatch.setattr(
            Path,
            "read_text",
            lambda s, encoding="utf-8": (_ for _ in ()).throw(FileNotFoundError()),
        )
        app = FastAPI()
        app.state.ui_user = "admin"
        app.include_router(router)
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/ui/", headers=_header("admin", "anything"))
        assert resp.status_code == 500
        assert "not configured" in resp.json()["detail"].lower()

    def test_bad_base64_header_returns_401(self, app):
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/ui/", headers={"Authorization": "Basic not-valid!!=="})
        assert resp.status_code == 401

    def test_no_colon_in_decoded_returns_401(self, app):
        client = TestClient(app, follow_redirects=False)
        raw = base64.b64encode(b"nocolonhere").decode()
        resp = client.get("/ui/", headers={"Authorization": f"Basic {raw}"})
        assert resp.status_code == 401
