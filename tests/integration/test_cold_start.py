"""Container cold start integration test.

Starts the full Docker stack against a fresh empty volume and verifies
that GET /v1/health returns HTTP 200 within 30 seconds (NFR-O1).

Requires Docker. Skip automatically when Docker is unavailable.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests

pytestmark = pytest.mark.integration


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _compose_command() -> list[str] | None:
    for command in (["docker-compose"], ["docker", "compose"]):
        try:
            result = subprocess.run(
                [*command, "version"],
                capture_output=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return command
    return None


_DOCKER_AVAILABLE = _docker_available()
_COMPOSE_COMMAND = _compose_command() if _DOCKER_AVAILABLE else None

docker_required = pytest.mark.skipif(
    not _DOCKER_AVAILABLE or _COMPOSE_COMMAND is None,
    reason="Docker/Compose is not available — skipping container integration tests",
)


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get_mapped_port(env: dict[str, str]) -> int:
    """Get the host port from WIKI_PORT env var (default 3050)."""
    return int(env.get("WIKI_PORT", 3050))


@docker_required
def test_container_cold_start_within_30s(tmp_path: Path) -> None:
    """Container must serve /v1/health within 30s of cold start (NFR-O1)."""
    wiki_volume = tmp_path / "wiki"
    wiki_volume.mkdir()

    compose_file = Path(__file__).parent.parent.parent / "docker-compose.yml"
    assert compose_file.exists(), f"docker-compose.yml not found at {compose_file}"

    env: dict[str, str] = {
        **os.environ,
        "COMPOSE_PROJECT_NAME": f"llm_wiki_cold_start_{tmp_path.name}",
        "WIKI_PORT": str(_free_tcp_port()),
        "WIKI_VOLUME": str(wiki_volume),
    }

    assert _COMPOSE_COMMAND is not None
    up_result = subprocess.run(
        [*_COMPOSE_COMMAND, "-f", str(compose_file), "up", "--build", "-d"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert up_result.returncode == 0, f"docker-compose up failed:\n{up_result.stderr}"

    try:
        host_port = _get_mapped_port(env)
        health_url = f"http://localhost:{host_port}/v1/health"

        deadline = time.monotonic() + 30
        response: requests.Response | None = None
        while time.monotonic() < deadline:
            try:
                response = requests.get(health_url, timeout=2)
                if response.status_code == 200:
                    break
            except requests.ConnectionError:
                pass
            time.sleep(1)

        assert response is not None and response.status_code == 200, (
            "GET /v1/health did not return 200 within 30s"
        )

        # AC:3 — verify required health response fields
        data: dict[str, object] = response.json()
        assert "daemon_running" in data, "Missing daemon_running field"
        assert "index_loaded" in data, "Missing index_loaded field"
        assert "llm_extraction_enabled" in data, "Missing llm_extraction_enabled field"
        assert "vector_search_enabled" not in data, (
            "vector_search_enabled must not be present — vector search is always on"
        )
        assert isinstance(data["daemon_running"], bool)
        assert isinstance(data["index_loaded"], bool)
        assert isinstance(data["llm_extraction_enabled"], bool)

    finally:
        subprocess.run(
            [*_COMPOSE_COMMAND, "-f", str(compose_file), "down", "-v"],
            env=env,
            capture_output=True,
            timeout=30,
        )
