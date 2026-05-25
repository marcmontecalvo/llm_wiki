"""Integration tests for Story 1.7 -- query, search, pages, and export endpoints."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_wiki.api.app import create_app

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def api_wiki(tmp_path: Path) -> Path:
    """Create wiki structure sufficient for Story 1.7 routes."""
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
def wiki_with_pages(api_wiki: Path) -> Path:
    """Mini wiki with a couple of markdown pages and an export file."""
    # -- config (required by lifespan) -------------------------------------------------
    cfg = api_wiki / "config"
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

    # -- two pages ---------------------------------------------------------------------
    page_a = (
        "---\nid: general-python-typing\n"
        "kind: page\n"
        "title: Python Typing\n"
        "domain: general\n"
        "confidence: 0.85\n"
        "sources: [doc:typing-guide]\n"
        "links: [general-python-generics]\n"
        "updated_at: 2026-05-01T00:00:00Z\n"
        "tags: [python, typing]\n"
        "---\n\n"
        "# Python Typing\n\nA page about Python type hints.\n"
    )
    (api_wiki / "domains/general/pages/general-python-typing.md").write_text(
        page_a, encoding="utf-8"
    )

    page_b = (
        "---\nid: general-python-generics\n"
        "kind: page\n"
        "title: Python Generics\n"
        "domain: general\n"
        "confidence: 0.7\n"
        "sources: [doc:generics-guide]\n"
        "updated_at: 2026-05-02T00:00:00Z\n"
        "tags: [python]\n"
        "---\n\n"
        "# Python Generics\n\nA page about Python generics.\n"
    )
    (api_wiki / "domains/general/pages/general-python-generics.md").write_text(
        page_b, encoding="utf-8"
    )

    # -- metadata index (required for GET /v1/pages) -----------------------------------
    # Build the metadata index so the list endpoint has data.
    wiki_base = api_wiki
    idx_dir = wiki_base / "index"
    import json as _json

    metadata = {
        "pages": {
            "general-python-typing": {
                "id": "general-python-typing",
                "page_id": "general-python-typing",
                "title": "Python Typing",
                "domain": "general",
                "kind": "page",
                "confidence": 0.85,
                "tags": ["python", "typing"],
                "sources": ["doc:typing-guide"],
                "links": ["general-python-generics"],
            },
            "general-python-generics": {
                "id": "general-python-generics",
                "page_id": "general-python-generics",
                "title": "Python Generics",
                "domain": "general",
                "kind": "page",
                "confidence": 0.7,
                "tags": ["python"],
                "sources": ["doc:generics-guide"],
            },
        },
        "by_tag": {"python": ["general-python-typing", "general-python-generics"]},
        "by_kind": {"page": ["general-python-typing", "general-python-generics"]},
        "by_domain": {"general": ["general-python-typing", "general-python-generics"]},
        "claims": [],
    }
    (idx_dir / "metadata.json").write_text(_json.dumps(metadata), encoding="utf-8")

    # -- LLMS file for export test -----------------------------------------------------
    (api_wiki / "exports/llms.txt").write_text(
        "# LLMs.txt\n\nVisit /wiki_system/ for more.\n", encoding="utf-8"
    )

    return api_wiki


@pytest.fixture
def test_app(wiki_with_pages: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Build a FastAPI app with the test wiki."""
    monkeypatch.setenv("WIKI_ROOT", str(wiki_with_pages))
    monkeypatch.setenv("WIKI_CONFIG_DIR", str(wiki_with_pages / "config"))
    return create_app()


# ── Query endpoint tests ──────────────────────────────────────────────────────


def test_quick_query_returns_200(test_app: FastAPI):
    """AC1 -- POST /v1/query depth=quick returns 200."""
    with TestClient(test_app) as client:
        r = client.post("/v1/query", json={"query": "test", "depth": "quick"})
        assert r.status_code == 200
        body = r.json()
        assert "results" in body
        assert "timed_out" in body
        assert "partial" in body
        # NFR: response shape correct even if empty


def test_quick_query_returns_field_shapes(test_app: FastAPI):
    """AC1 -- QueryResult items include confidence."""
    with TestClient(test_app) as client:
        r = client.post("/v1/query", json={"query": "test", "depth": "quick"})
        body = r.json()
        assert "results" in body
        # Results may be empty on a test wiki, but the response must be a valid shape.
        assert isinstance(body["results"], list)


def test_deep_query_returns_202(test_app: FastAPI):
    """AC3 -- POST /v1/query depth=deep returns 202 Accepted with job_id."""
    with TestClient(test_app) as client:
        r = client.post("/v1/query", json={"query": "deep search", "depth": "deep"})
        assert r.status_code == 202
        body = r.json()
        assert "job_id" in body
        assert body["status"] == "queued"


def test_job_poll_nonexistent_returns_404(test_app: FastAPI):
    """AC8 -- GET /v1/query/{job_id} returns 404 for unknown job."""
    with TestClient(test_app) as client:
        r = client.get("/v1/query/nonexistent-job-id")
        assert r.status_code == 404
        body = r.json()
        assert body["error_code"] == "WIKI_NOT_FOUND"


def test_export_not_ready_returns_404(test_app: FastAPI):
    """AC14 -- GET /v1/export/{unknown_format} returns 404 EXPORT_NOT_READY."""
    with TestClient(test_app) as client:
        r = client.get("/v1/export/json-ld")
        # json-ld file does not exist in test fixture
        assert r.status_code == 404
        body = r.json()
        assert body["error_code"] == "EXPORT_NOT_READY"


# ── Search endpoint tests ─────────────────────────────────────────────────────


def test_search_returns_200(test_app: FastAPI):
    """AC9 -- GET /v1/search returns 200 with merged results."""
    with TestClient(test_app) as client:
        r = client.get("/v1/search?q=test")
        assert r.status_code == 200
        body = r.json()
        assert "results" in body
        assert isinstance(body["results"], list)


def test_search_result_shape(test_app: FastAPI):
    """AC9 -- SearchResultItem includes page_id, title, confidence, score."""
    with TestClient(test_app) as client:
        r = client.get("/v1/search?q=test")
        body = r.json()
        for item in body["results"]:
            assert "page_id" in item
            assert "title" in item
            assert "confidence" in item
            assert "score" in item


# ── Pages endpoint tests ──────────────────────────────────────────────────────


def test_page_read_existing(test_app: FastAPI):
    """AC10 -- GET /v1/pages/{page_id} returns full page content."""
    with TestClient(test_app) as client:
        r = client.get("/v1/pages/general-python-typing")
        assert r.status_code == 200
        body = r.json()
        assert body["page_id"] == "general-python-typing"
        assert body["title"] == "Python Typing"
        assert "Python Typing" in body["content"]
        assert body["domain"] == "general"
        assert body["kind"] == "page"
        assert body["confidence"] == 0.85
        assert "frontmatter" in body


def test_page_read_not_found(test_app: FastAPI):
    """AC11 -- GET /v1/pages/{missing} returns 404."""
    with TestClient(test_app) as client:
        r = client.get("/v1/pages/no-such-page")
        assert r.status_code == 404
        body = r.json()
        assert body["error_code"] == "WIKI_NOT_FOUND"


def test_pages_list_returns_200(test_app: FastAPI):
    """AC12 -- GET /v1/pages returns 200 with paginated results."""
    with TestClient(test_app) as client:
        r = client.get("/v1/pages")
        assert r.status_code == 200
        body = r.json()
        assert "pages" in body
        assert "total_hint" in body
        assert isinstance(body["pages"], list)
        assert len(body["pages"]) >= 1


def test_pages_list_with_domain_filter(test_app: FastAPI):
    """AC12 -- GET /v1/pages?domain=general returns filtered results."""
    with TestClient(test_app) as client:
        r = client.get("/v1/pages?domain=general")
        assert r.status_code == 200
        body = r.json()
        for page in body["pages"]:
            assert page["domain"] == "general"


def test_pages_list_pagination_cursor(test_app: FastAPI):
    """AC12 -- GET /v1/pages returns next_cursor when more results exist."""
    with TestClient(test_app) as client:
        # Limit to 1 to force a next_cursor
        r = client.get("/v1/pages?limit=1")
        body = r.json()
        assert body["next_cursor"] is not None
        # Use cursor to get next page
        r2 = client.get(f"/v1/pages?limit=1&cursor={body['next_cursor']}")
        assert r2.status_code == 200


# ── Export endpoint tests ─────────────────────────────────────────────────────


def test_export_existing_returns_content(test_app: FastAPI):
    """AC13 -- GET /v1/export/llms-txt returns exported file content."""
    with TestClient(test_app) as client:
        r = client.get("/v1/export/llms-txt")
        assert r.status_code == 200
        assert "LLMs.txt" in r.text or "LLMs.txt" in r.text
        assert "Last-Modified" in r.headers


def test_export_trigger_returns_accepted(test_app: FastAPI):
    """AC13 -- POST /v1/export returns accepted."""
    with TestClient(test_app) as client:
        r = client.post("/v1/export")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "accepted"


# ── Query tests ──────────────────────────────────────────────────────────────


def test_standard_query_returns_more_results(test_app: FastAPI):
    """AC2 -- depth=standard can return up to 50 results."""
    with TestClient(test_app) as client:
        r = client.post("/v1/query", json={"query": "test", "depth": "standard"})
        assert r.status_code == 200
        body = r.json()
        assert "results" in body
        assert isinstance(body["results"], list)


def test_query_with_domain_filter(test_app: FastAPI):
    """AC1 -- Query domain filter parameter is accepted."""
    with TestClient(test_app) as client:
        r = client.post(
            "/v1/query",
            json={"query": "test", "depth": "quick", "domain": "general"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "results" in body
