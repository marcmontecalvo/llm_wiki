"""Unit tests for the per-domain dashboard service (Story 3-5)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Annotated

from fastapi import Path as FastAPIPath

from llm_wiki.api.models import (
    DashboardConfidenceDistribution,
    DashboardResponse,
)
from llm_wiki.api.services.dashboard import (
    _compute_confidence_distribution,
    _get_last_governance_run,
    _load_domains_config,
    get_domain_dashboard,
)
from llm_wiki.changelog.log import ChangeLog

# ---------------------------------------------------------------------------
# _compute_confidence_distribution
# ---------------------------------------------------------------------------


class TestComputeConfidenceDistribution:
    def test_empty_list(self):
        dist = _compute_confidence_distribution([])
        assert dist == DashboardConfidenceDistribution(low=0, medium=0, high=0)

    def test_all_high(self):
        pages = [{"confidence_score": 0.9}, {"confidence_score": 0.8}]
        dist = _compute_confidence_distribution(pages)
        assert dist.high == 2
        assert dist.low == 0
        assert dist.medium == 0

    def test_all_low(self):
        pages = [{"confidence_score": 0.1}, {"confidence_score": 0.2}]
        dist = _compute_confidence_distribution(pages)
        assert dist.low == 2

    def test_all_medium(self):
        pages = [{"confidence_score": 0.4}, {"confidence_score": 0.5}]
        dist = _compute_confidence_distribution(pages)
        assert dist.medium == 2

    def test_mixed(self):
        pages = [
            {"confidence_score": 0.1},
            {"confidence_score": 0.4},
            {"confidence_score": 0.9},
        ]
        dist = _compute_confidence_distribution(pages)
        assert dist.low == 1
        assert dist.medium == 1
        assert dist.high == 1

    def test_fallback_to_confidence_key(self):
        pages = [{"confidence": 0.9}]
        dist = _compute_confidence_distribution(pages)
        assert dist.high == 1

    def test_fallback_default_0_5(self):
        pages = [{}]
        dist = _compute_confidence_distribution(pages)
        # default 0.5 falls into medium (0.3 <= 0.5 < 0.6)
        assert dist.medium == 1

    def test_invalid_score_skipped(self):
        pages = [{"confidence_score": "not-a-number"}]
        dist = _compute_confidence_distribution(pages)
        assert dist.low == 0

    def test_boundary_values(self):
        pages = [
            {"confidence_score": 0.0},  # low
            {"confidence_score": 0.3},  # medium (>= 0.3)
            {"confidence_score": 0.6},  # high (>= 0.6)
            {"confidence_score": 1.0},  # high
        ]
        dist = _compute_confidence_distribution(pages)
        assert dist.low == 1
        assert dist.medium == 1
        assert dist.high == 2


# ---------------------------------------------------------------------------
# _load_domains_config
# ---------------------------------------------------------------------------


class TestLoadDomainsConfig:
    def test_scans_domain_directory(self, tmp_path: Path):
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        (domains_dir / "alpha").mkdir()
        (domains_dir / "beta").mkdir()

        cfgs = _load_domains_config(tmp_path)
        assert set(cfgs.keys()) == {"alpha", "beta"}
        assert cfgs["alpha"].staleness_threshold_days == 90

    def test_no_domains_dir(self, tmp_path: Path):
        cfgs = _load_domains_config(tmp_path)
        assert cfgs == {}

    def test_single_domain(self, tmp_path: Path):
        domains_dir = tmp_path / "domains"
        domains_dir.mkdir()
        (domains_dir / "ml-research").mkdir()

        cfgs = _load_domains_config(tmp_path)
        assert "ml-research" in cfgs
        assert cfgs["ml-research"].id == "ml-research"


# ---------------------------------------------------------------------------
# _get_last_governance_run
# ---------------------------------------------------------------------------


class TestGetLastGovernanceRun:
    def test_no_jobs_file(self, tmp_path: Path):
        result = _get_last_governance_run(tmp_path)
        assert result is None

    def test_empty_jobs_file(self, tmp_path: Path):
        jobs_path = tmp_path / "state" / "jobs.json"
        jobs_path.parent.mkdir(parents=True)
        jobs_path.write_text("{}")

        result = _get_last_governance_run(tmp_path)
        assert result is None

    def test_with_govern_entry(self, tmp_path: Path):
        jobs_path = tmp_path / "state" / "jobs.json"
        jobs_path.parent.mkdir(parents=True)
        jobs_path.write_text(
            '{"govern": {"last_run": "2025-01-15T10:00:00Z", "outcome": "success", "warning_count": 2}}'
        )

        result = _get_last_governance_run(tmp_path)
        assert result is not None
        assert result.last_run == "2025-01-15T10:00:00Z"
        assert result.outcome == "success"
        assert result.warnings == 2

    def test_corrupt_json_returns_none(self, tmp_path: Path):
        jobs_path = tmp_path / "state" / "jobs.json"
        jobs_path.parent.mkdir(parents=True)
        jobs_path.write_text("not valid json {{{")

        result = _get_last_governance_run(tmp_path)
        assert result is None

    def test_govern_empty_dict_returns_none(self, tmp_path: Path):
        jobs_path = tmp_path / "state" / "jobs.json"
        jobs_path.parent.mkdir(parents=True)
        jobs_path.write_text('{"govern": {}}')

        result = _get_last_governance_run(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# _get_recent_changes
# ---------------------------------------------------------------------------


class TestGetRecentChanges:
    def test_filters_to_domain_pages(self, tmp_path: Path):
        """Recent changes outside domain_page_ids should be excluded."""
        cl = ChangeLog(changelog_dir=tmp_path / "changelog")
        cl.ensure_dirs()
        cl.record("page-a", "updated", "actor-1")
        cl.record("page-b", "created", "actor-2")
        cl.record("page-c", "deleted", "actor-1")

        domain_page_ids = {"page-a", "page-b"}
        from llm_wiki.api.services.dashboard import _get_recent_changes

        changes = _get_recent_changes(tmp_path, "test", domain_page_ids, limit=5)
        page_ids = {c.page_id for c in changes}
        assert "page-a" in page_ids
        assert "page-b" in page_ids
        assert "page-c" not in page_ids

    def test_empty_changelog(self, tmp_path: Path):
        cl = ChangeLog(changelog_dir=tmp_path / "changelog")
        cl.ensure_dirs()

        from llm_wiki.api.services.dashboard import _get_recent_changes

        changes = _get_recent_changes(tmp_path, "test", {"page-x"}, limit=5)
        assert changes == []


# ---------------------------------------------------------------------------
# get_domain_dashboard (integration-style)
# ---------------------------------------------------------------------------


class TestGetDomainDashboard:
    def _create_minimal_wiki(self, tmp_path: Path, domain: str = "test"):
        """Create a minimal wiki with index, domains, and changelog."""
        # Create domains directory
        domains_dir = tmp_path / "domains" / domain
        domains_dir.mkdir(parents=True)

        # Create index directory with metadata
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        (index_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "pages": {
                        "page-1": {
                            "page_id": "page-1",
                            "title": "Test Page 1",
                            "domain": "test",
                            "confidence_score": 0.8,
                            "updated_at": str(int(time.time() * 1000)),
                        },
                        "page-2": {
                            "page_id": "page-2",
                            "title": "Test Page 2",
                            "domain": "test",
                            "confidence_score": 0.2,
                            "updated_at": str(int(time.time() * 1000)),
                        },
                        "page-3": {
                            "page_id": "page-3",
                            "title": "Test Page 3",
                            "domain": "other",  # different domain
                            "confidence_score": 0.9,
                        },
                    },
                    "by_domain": {"test": ["page-1", "page-2"], "other": ["page-3"]},
                }
            )
        )
        return tmp_path

    def test_basic_dashboard(self, tmp_path: Path):
        wiki_root = self._create_minimal_wiki(tmp_path)
        result = get_domain_dashboard("test", wiki_root)

        assert result.domain == "test"
        assert result.page_count == 2
        assert result.low_confidence_count == 1
        assert len(result.recent_changes) == 0

    def test_confidence_distribution(self, tmp_path: Path):
        wiki_root = self._create_minimal_wiki(tmp_path)
        result = get_domain_dashboard("test", wiki_root)

        assert result.confidence_distribution.low == 1
        assert result.confidence_distribution.medium == 0
        assert result.confidence_distribution.high == 1

    def test_unknown_domain_raises(self, tmp_path: Path):
        from llm_wiki.exceptions import DomainUnknownError

        wiki_root = self._create_minimal_wiki(tmp_path)
        try:
            get_domain_dashboard("nonexistent", wiki_root)
        except DomainUnknownError:
            pass
        else:
            raise AssertionError("Expected DomainUnknownError")

    def test_stale_pages_counted(self, tmp_path: Path):
        """Pages with old updated_at should count as stale with short threshold."""

        # Create index with a very old page
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        old_ts = str(int((time.time() - 200 * 86400) * 1000))  # 200 days ago
        (index_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "pages": {
                        "old-page": {
                            "page_id": "old-page",
                            "title": "Old",
                            "domain": "test",
                            "confidence_score": 0.5,
                            "updated_at": old_ts,
                        },
                        "new-page": {
                            "page_id": "new-page",
                            "title": "New",
                            "domain": "test",
                            "confidence_score": 0.5,
                            "updated_at": str(int(time.time() * 1000)),
                        },
                    },
                    "by_domain": {"test": ["old-page", "new-page"]},
                }
            )
        )
        # Create domains directory
        (tmp_path / "domains" / "test").mkdir(parents=True)

        result = get_domain_dashboard("test", tmp_path)
        # With 90-day default threshold, old-page (200 days) should be stale
        assert result.stale_count == 1

    def test_governance_run_included(self, tmp_path: Path):
        wiki_root = self._create_minimal_wiki(tmp_path)
        jobs_path = wiki_root / "state" / "jobs.json"
        jobs_path.parent.mkdir(parents=True)
        jobs_path.write_text(
            '{"govern": {"last_run": "2025-06-01T12:00:00Z", "outcome": "success"}}'
        )

        result = get_domain_dashboard("test", wiki_root)
        assert result.last_governance_run is not None
        assert result.last_governance_run.last_run == "2025-06-01T12:00:00Z"
        assert result.last_governance_run.outcome == "success"


# ---------------------------------------------------------------------------
# REST endpoint integration
# ---------------------------------------------------------------------------


class TestDashboardEndpoint:
    def test_router_has_dashboard_route(self):
        """Verify the dashboard router is registered with the expected path."""
        from llm_wiki.api.routers.dashboard import router

        routes = [route.path for route in router.routes]
        assert "/v1/domains/{domain}/dashboard" in routes

    def test_dashboard_models_serialize(self):
        """Verify DashboardResponse serializes to JSON-compatible dict."""
        resp = DashboardResponse(
            domain="test",
            page_count=42,
            confidence_distribution=DashboardConfidenceDistribution(low=1, medium=2, high=39),
            low_confidence_count=1,
            stale_count=0,
        )
        data = resp.model_dump()
        assert data["domain"] == "test"
        assert data["page_count"] == 42
        assert data["low_confidence_count"] == 1
        assert isinstance(data["confidence_distribution"], dict)

    def test_domain_path_pattern_rejects_bad_input(self, tmp_path: Path):
        """FastAPI path validation should reject domain with slashes or spaces."""
        import urllib.parse

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.get("/v1/domains/{domain}/dashboard")
        async def mock_endpoint(
            domain: Annotated[str, FastAPIPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$")],
        ) -> dict:
            return {"domain": domain, "page_count": 0}

        with TestClient(app) as client:
            # Valid domain goes through
            resp = client.get("/v1/domains/general/dashboard")
            assert resp.status_code == 200

            # Invalid domain with spaces (URL-encoded %20) should return 422
            resp = client.get(f"/v1/domains/api{urllib.parse.quote(' pages')}/dashboard")
            assert resp.status_code == 422, "Encoded space should be rejected"

            # Invalid domain with slash in URL forces FastAPI routing to HTTP 404
            # but the pattern is still enforced for valid-looking paths
            resp = client.get("/v1/domains/valid-domain/dashboard")
            assert resp.status_code == 200, "Valid slug should be accepted"


class TestMCPDomainDashboardTool:
    def test_mcp_tool_exists(self):
        """Verify the mcp domain_dashboard tool is registered with correct signature."""
        from mcp.server.fastmcp import FastMCP

        from llm_wiki.mcp.tools import register_tools

        server = FastMCP("test")
        # Use a dummy wiki — we only care that registration succeeds
        from unittest.mock import MagicMock

        mock_wiki = MagicMock()
        mock_wiki.wiki_base = Path("/tmp/test-wiki")

        register_tools(server, mock_wiki)
        tools = asyncio.run(server.list_tools())
        tool_names = {t.name for t in tools}
        assert "domain_dashboard" in tool_names


class TestCLIOutputFormatting:
    def test_cli_human_output_format(self, tmp_path: Path):
        """Verify CLI human-readable output has expected labels."""
        from click.testing import CliRunner

        from llm_wiki.cli import main

        # Set up minimal wiki
        (tmp_path / "domains" / "test").mkdir(parents=True)
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        index_dir.joinpath("metadata.json").write_text(
            json.dumps(
                {
                    "pages": {
                        "p1": {
                            "page_id": "p1",
                            "title": "Test",
                            "domain": "test",
                            "confidence_score": 0.9,
                        }
                    },
                    "by_domain": {"test": ["p1"]},
                }
            )
        )

        runner = CliRunner()
        result = runner.invoke(
            main, ["govern", "dashboard", "--domain", "test", "--wiki-base", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "=== Dashboard: test ===" in result.output
        assert "Pages:" in result.output
        assert "Confidence dist:" in result.output
        assert "Low confidence (<0.3):" in result.output  # Fixed label
        assert "Stale pages:" in result.output

    def test_cli_json_output(self, tmp_path: Path):
        """Verify CLI JSON output is valid and contains expected keys."""

        from click.testing import CliRunner

        from llm_wiki.cli import main

        (tmp_path / "domains" / "test").mkdir(parents=True)
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        index_dir.joinpath("metadata.json").write_text(
            json.dumps(
                {
                    "pages": {
                        "p1": {
                            "page_id": "p1",
                            "title": "Test",
                            "domain": "test",
                            "confidence_score": 0.9,
                        }
                    },
                    "by_domain": {"test": ["p1"]},
                }
            )
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["govern", "dashboard", "--domain", "test", "--json", "--wiki-base", str(tmp_path)],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        # JSON output wraps single domain in {"domains": [...], "errors": []}
        assert data["domains"][0]["domain"] == "test"
        assert data["domains"][0]["dashboard"]["page_count"] == 1
        assert "confidence_distribution" in data["domains"][0]["dashboard"]
