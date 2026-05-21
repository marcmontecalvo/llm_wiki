"""Performance test fixtures — 100-page seeded wiki, built once per session."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from llm_wiki.initializer import WikiInitializer


def _generate_pages(wiki_system: Path, count: int = 100) -> None:
    """Write synthetic pages to 3 domains. Use parents=True so no pre-init needed."""
    domains = ["household", "tech", "personal"]
    for i in range(count):
        domain = domains[i % 3]
        domain_dir = wiki_system / "domains" / domain / "pages"
        domain_dir.mkdir(parents=True, exist_ok=True)
        page = domain_dir / f"page-{i:04d}.md"
        page.write_text(
            f"---\n"
            f"id: page-{i:04d}\n"
            f"title: Test Page {i}\n"
            f"domain: {domain}\n"
            f"updated_at: 2026-05-17T00:00:00Z\n"
            f"confidence: 0.8\n"
            f"---\n\n"
            f"# Test Page {i}\n\n"
            f"This page contains content about topic {i % 20}. "
            f"It describes various aspects of the subject in domain {domain}. "
            f"The content is generated for performance testing purposes only.\n",
            encoding="utf-8",
        )


@pytest.fixture(scope="session")
def seeded_wiki_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create, seed, and index a 100-page wiki once per session.

    scope="session" is critical — rebuilding 100 pages per test blows every
    latency budget. The index is built once and reused across all performance tests.
    """
    wiki_system = tmp_path_factory.mktemp("perf_wiki")
    WikiInitializer.initialize(wiki_system)
    _generate_pages(wiki_system)

    from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob

    IndexRebuildJob(wiki_base=wiki_system).execute()
    return wiki_system


@pytest.fixture(scope="session")
def _wiki_env(seeded_wiki_path: Path) -> Generator[None, None, None]:
    """Point WIKI_ROOT at the seeded wiki for the duration of the session."""
    prev_root = os.environ.get("WIKI_ROOT")
    prev_cfg = os.environ.get("WIKI_CONFIG_DIR")
    os.environ["WIKI_ROOT"] = str(seeded_wiki_path)
    os.environ.pop("WIKI_CONFIG_DIR", None)  # no config → llm_extraction defaults to False
    yield
    if prev_root is None:
        os.environ.pop("WIKI_ROOT", None)
    else:
        os.environ["WIKI_ROOT"] = prev_root
    if prev_cfg is None:
        os.environ.pop("WIKI_CONFIG_DIR", None)
    else:
        os.environ["WIKI_CONFIG_DIR"] = prev_cfg


@pytest.fixture(scope="session")
def seeded_wiki_client(
    seeded_wiki_path: Path, _wiki_env: None
) -> Generator[TestClient, None, None]:
    """Sync TestClient for quick/standard latency tests.

    scope="session" keeps the lifespan (and its loaded indexes) alive for the
    entire test run — avoids paying startup cost on every test.

    A warm-up request is issued before yielding so that sentence-transformer
    model weights are loaded before any latency assertions are made.
    """
    from llm_wiki.api.app import create_app

    app = create_app()
    with TestClient(app) as client:
        # Warm up: preload sentence-transformer model weights and caches so the
        # first timed query doesn't include model-load overhead.
        client.post("/v1/query", json={"query": "warmup", "depth": "quick"})
        yield client


@pytest.fixture(scope="session")
def seeded_wiki_app(seeded_wiki_path: Path, _wiki_env: None):
    """FastAPI app with pre-wired state for the async deep query test.

    AsyncClient + ASGITransport does NOT trigger the ASGI lifespan, so we
    bootstrap app.state manually using boot_wiki(). This gives the deep query
    handler a working WikiQuery and deep_jobs dict while keeping the event
    loop available for asyncio.create_task() background work.
    """
    from llm_wiki.api.app import create_app
    from llm_wiki.initializer import boot_wiki

    app = create_app()
    wiki, wiki_config, user_job_store, deep_jobs = boot_wiki(seeded_wiki_path)
    app.state.wiki = wiki
    if wiki_config is not None:
        app.state.wiki_config = wiki_config
    app.state.user_job_store = user_job_store
    app.state.deep_jobs = deep_jobs
    app.state.query_log = None
    app.state.query_log_error = False
    return app
