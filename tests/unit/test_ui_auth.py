"""Tests for UI auth module (UI basic auth, password generation, user lookup)."""

import base64
import os
from contextlib import contextmanager

from llm_wiki.api.ui_auth import (
    generate_password,
    get_ui_password,
    get_ui_user,
    verify_ui_auth,
)


def _make_conn(auth_header: str | None):
    """Create an HTTPConnection with the given Authorization header.

    Uses scope dict with lowercase headers as starlette expects.
    """
    from starlette.requests import HTTPConnection

    headers: list[tuple[bytes, bytes]] = []
    if auth_header is not None:
        headers.append((b"authorization", auth_header.encode()))
    scope = {"type": "http", "headers": headers}
    return HTTPConnection(scope)


@contextmanager
def _env_override(**overrides):
    """Temporarily override environment variables (supporting removal)."""
    previous = {}
    for key, value in overrides.items():
        if value is None:
            previous[key] = os.environ.pop(key, None)
        else:
            previous[key] = os.environ.get(key)
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class TestGeneratePassword:
    def test_returns_non_empty_string(self):
        pw = generate_password()
        assert isinstance(pw, str)
        assert len(pw) > 0

    def test_returns_url_safe_string(self):
        pw = generate_password()
        assert set(pw) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=")

    def test_returns_unique_values(self):
        a = generate_password()
        b = generate_password()
        assert a != b


class TestGetUiUser:
    def test_default_user(self):
        with _env_override(WIKI_UI_USER=None):
            assert get_ui_user() == "admin"

    def test_custom_user(self):
        with _env_override(WIKI_UI_USER="operator"):
            assert get_ui_user() == "operator"


class TestGetUiPassword:
    def test_default_empty(self):
        with _env_override(WIKI_UI_PASSWORD=None):
            assert get_ui_password() == ""

    def test_custom_env(self):
        with _env_override(WIKI_UI_PASSWORD="my-secret"):
            assert get_ui_password() == "my-secret"


class TestVerifyUiAuth:
    def _basic_header(self, user: str, password: str) -> str:
        encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
        return f"Basic {encoded}"

    def test_valid_credentials(self):
        conn = _make_conn(self._basic_header("admin", "secret"))
        assert verify_ui_auth(conn, "secret") is True

    def test_wrong_password(self):
        conn = _make_conn(self._basic_header("admin", "wrong"))
        assert verify_ui_auth(conn, "secret") is False

    def test_wrong_username(self):
        conn = _make_conn(self._basic_header("operator", "secret"))
        assert verify_ui_auth(conn, "secret") is False

    def test_missing_header(self):
        conn = _make_conn(None)
        assert verify_ui_auth(conn, "secret") is False

    def test_empty_header(self):
        conn = _make_conn("")
        assert verify_ui_auth(conn, "secret") is False

    def test_bad_base64(self):
        conn = _make_conn("Basic notbase64!!")
        assert verify_ui_auth(conn, "secret") is False

    def test_no_colon_in_decoded(self):
        header = self._basic_header("no-colon-here", "")
        conn = _make_conn(header)
        assert verify_ui_auth(conn, "secret") is False

    def test_custom_user(self):
        with _env_override(WIKI_UI_USER="operator"):
            conn = _make_conn(self._basic_header("operator", "secret"))
            assert verify_ui_auth(conn, "secret") is True

    def test_empty_password_match(self):
        conn = _make_conn(self._basic_header("admin", ""))
        assert verify_ui_auth(conn, "") is True
