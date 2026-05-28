"""UI authentication for /ui/* routes.

Uses HTTP Basic Auth with credentials from environment:
  - username: WIKI_UI_USER env var (default: admin)
  - password: WIKI_UI_PASSWORD env var (required)
"""

import base64
import os
import secrets

from starlette.requests import HTTPConnection


def generate_password() -> str:
    """Generate a random URL-safe password.

    Uses ``secrets`` for cryptographically secure randomness.
    """
    return secrets.token_urlsafe(16)


def get_ui_user() -> str:
    """Get the configured UI username."""
    return os.environ.get("WIKI_UI_USER", "admin")


def get_ui_password() -> str:
    """Get the configured UI password from environment."""
    return os.environ.get("WIKI_UI_PASSWORD", "")


def verify_ui_auth(conn: HTTPConnection, ui_password: str) -> bool:
    """Verify HTTP Basic Auth credentials against the configured password.

    Args:
        conn: FastAPI Request (Starlette HTTPConnection)
        ui_password: The expected password from app.state.ui_password

    Returns:
        True if credentials match, False otherwise
    """
    auth_header = conn.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        return False

    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (UnicodeDecodeError, ValueError):
        return False

    expected_user = get_ui_user()
    return secrets.compare_digest(username, expected_user) and secrets.compare_digest(
        password, ui_password
    )
