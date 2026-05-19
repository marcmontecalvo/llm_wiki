"""Integration tests for Story 1.6 -- health, daemon, ingest, domain endpoints."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_wiki.api.app import create_app

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def minimal_wiki(tmp_path: Path) -> Path:
    """Create minimal wiki structure needed for API routes."""
    wiki = tmp_path / "wiki_system"
    for d in [
        "domains/general/pages",
        "domains/tech/pages",
        "index",
        "exports",
        "inbox/new",
        "state",
        "domains/.shared",
        "shared/concepts",
        "shared/entities",
        "shared/synthesis",
    ]:
        (wiki / d).mkdir(parents=True, exist_ok=True)
    return wiki


@pytest.fixture
def wiki_with_config(minimal_wiki: Path) -> Path:
    """Mini wiki with config YAML files."""
    cfg = minimal_wiki / "config"
    cfg.mkdir()

    (cfg / "domains.yaml").write_text(
        "domains:\n"
        "  - id: general\n    title: General\n    description: General domain\n"
        "    owners: []\n    promote_to_shared: true\n"
        "  - id: tech\n    title: Tech\n    description: Tech domain\n"
        "    owners: []\n    promote_to_shared: true\n",
        encoding="utf-8",
    )
    (cfg / "daemon.yaml").write_text(
        "daemon:\n"
        "  inbox_poll_seconds: 15\n"
        "  migrate_queue_every_minutes: 15\n"
        "  retry_failed_ingests_every_minutes: 30\n"
        "  rebuild_index_every_minutes: 30\n"
        "  lint_every_minutes: 60\n"
        "  stale_check_every_hours: 24\n"
        "  export_every_minutes: 60\n"
        "  promotion_every_hours: 24\n"
        "  duplicates_check_every_hours: 24\n"
        "  max_parallel_jobs: 2\n"
        "  log_level: INFO\n"
        "  review_queue_enabled: true\n"
        "  review_queue_every_minutes: 30\n"
        "  review_queue_min_page_quality: 0.4\n"
        "  review_queue_min_claim_confidence: 0.5\n"
        "  review_queue_max_pending: 1000\n"
        "  review_queue_retention_days: 30\n"
        "  promotion:\n"
        "    enabled: true\n"
        "    auto_promote_threshold: 10.0\n"
        "    suggest_promote_threshold: 5.0\n"
        "    min_quality_score: 0.6\n"
        "    min_cross_domain_refs: 2\n"
        "    require_approval: true\n"
        "  duplicates:\n"
        "    enabled: true\n"
        "    detection_interval: 86400\n"
        "    duplicates_check_every_hours: 24\n"
        "    min_score_to_flag: 0.5\n"
        "    auto_merge_threshold: 0.9\n"
        "    require_review: true\n"
        "    check_domains: []\n"
        "    exclude_kinds: [source]\n"
        "  features:\n"
        "    llm_extraction: false\n"
        "    synthesis_cache: false\n"
        "    cross_domain_promotion: false\n",
        encoding="utf-8",
    )
    (cfg / "routing.yaml").write_text(
        "routing:\n"
        "  fallback_domain: general\n"
        "  confidence_threshold: 0.75\n"
        "  explicit_override_frontmatter_key: domain\n"
        "  source_rules: []\n",
        encoding="utf-8",
    )
    (cfg / "models.yaml").write_text(
        "models:\n"
        "  extraction:\n"
        "    provider: local\n"
        "    model: test-model\n"
        "    temperature: 0.1\n"
        "    max_tokens: 4096\n"
        "    timeout: 30\n"
        "contracts:\n"
        "  require_schema_validation: true\n"
        "  allow_freeform_page_writes: false\n",
        encoding="utf-8",
    )
    return minimal_wiki


@pytest.fixture
def test_app(wiki_with_config: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Build a FastAPI app with the test wiki_root and full app setup.

    Uses create_app() which includes routers and middleware, then yields
    it via TestClient to trigger the lifespan.
    """
    monkeypatch.setenv("WIKI_ROOT", str(wiki_with_config))
    monkeypatch.setenv("WIKI_CONFIG_DIR", str(wiki_with_config / "config"))
    app = create_app()
    return app


# ── Health endpoint tests ────────────────────────────────────────────────────


def test_health_returns_200(test_app: FastAPI):
    """AC1 -- GET /v1/health returns 200."""
    with TestClient(test_app) as client:
        r = client.get("/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert "daemon_running" in body
        assert "index_loaded" in body
        assert "scheduler_state" in body
        assert "llm_extraction_enabled" in body
        # AC1 -- no vector_search_enabled field
        assert "vector_search_enabled" not in body


def test_health_fields_are_correct_types(test_app: FastAPI):
    """Health response has correct type for each field."""
    with TestClient(test_app) as client:
        r = client.get("/v1/health")
        body = r.json()
        assert isinstance(body["daemon_running"], bool)
        assert isinstance(body["index_loaded"], bool)
        assert isinstance(body["scheduler_state"], str)
        assert isinstance(body["llm_extraction_enabled"], bool)


def test_version_header_in_health(test_app: FastAPI):
    """AC9 -- X-LLM-Wiki-Version header present."""
    with TestClient(test_app) as client:
        r = client.get("/v1/health")
        assert "X-LLM-Wiki-Version" in r.headers
        assert r.headers["X-LLM-Wiki-Version"] == "0.1.0"


# ── Daemon status tests ──────────────────────────────────────────────────────


def test_daemon_status_returns_200(test_app: FastAPI):
    """AC2 -- GET /v1/daemon/status returns 200."""
    with TestClient(test_app) as client:
        r = client.get("/v1/daemon/status")
        assert r.status_code == 200
        body = r.json()
        assert "jobs" in body
        assert isinstance(body["jobs"], list)


def test_daemon_jobs_returns_200(test_app: FastAPI):
    """AC3 -- GET /v1/daemon/jobs returns 200."""
    with TestClient(test_app) as client:
        r = client.get("/v1/daemon/jobs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ── Ingest endpoint tests ───────────────────────────────────────────────────


def test_ingest_post_returns_queued(test_app: FastAPI):
    """AC5 -- POST /v1/ingest queues ingest job and returns queued status."""
    with TestClient(test_app) as client:
        r = client.post(
            "/v1/ingest",
            json={"content": "# Test\n\nSome content.", "domain": "general"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "queued"
        assert "job_id" in body
        assert body["domain"] == "general"


def test_ingest_get_unknown_returns_404(test_app: FastAPI):
    """AC7 -- GET /v1/ingest/{unknown} returns 404 with WIKI_NOT_FOUND."""
    with TestClient(test_app) as client:
        r = client.get("/v1/ingest/does-not-exist")
        assert r.status_code == 404
        body = r.json()
        assert body["error_code"] == "WIKI_NOT_FOUND"


def test_ingest_post_then_get(test_app: FastAPI):
    """AC5+6 -- POST then GET returns job status."""
    with TestClient(test_app) as client:
        r1 = client.post(
            "/v1/ingest",
            json={"content": "# Test", "domain": "general"},
        )
        assert r1.status_code == 200
        job_id = r1.json()["job_id"]

        r2 = client.get(f"/v1/ingest/{job_id}")
        assert r2.status_code == 200
        body = r2.json()
        assert body["job_id"] == job_id
        assert body["status"] == "queued"


def test_ingest_persists_to_disk(test_app: FastAPI):
    """AC8 -- ingest jobs are persisted to state/user_jobs.json."""
    with TestClient(test_app) as client:
        client.post("/v1/ingest", json={"content": "# Test"})
        wiki_base = Path(test_app.state.wiki.wiki_base)
        user_jobs_file = wiki_base / "state" / "user_jobs.json"
        assert user_jobs_file.exists()
        data = json.loads(user_jobs_file.read_text())
        assert len(data) >= 1


# ── Index rebuild endpoint tests ─────────────────────────────────────────────


def test_index_rebuild_triggers_async(test_app: FastAPI):
    """AC4 -- POST /v1/daemon/jobs/index-rebuild returns queued immediately."""
    with TestClient(test_app) as client:
        r = client.post("/v1/daemon/jobs/index-rebuild")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "queued"
        assert "job_id" in body


# ── Domains endpoint tests ──────────────────────────────────────────────────


def test_domains_returns_list(test_app: FastAPI):
    """AC8 -- GET /v1/domains returns domain list."""
    with TestClient(test_app) as client:
        r = client.get("/v1/domains")
        assert r.status_code == 200
        body = r.json()
        assert "domains" in body
        assert isinstance(body["domains"], list)
        assert len(body["domains"]) > 0
        first = body["domains"][0]
        assert "name" in first
        assert "page_count" in first
        assert "last_updated" in first


def test_domains_version_header(test_app: FastAPI):
    """AC9 -- X-LLM-Wiki-Version header on domains response."""
    with TestClient(test_app) as client:
        r = client.get("/v1/domains")
        assert "X-LLM-Wiki-Version" in r.headers
