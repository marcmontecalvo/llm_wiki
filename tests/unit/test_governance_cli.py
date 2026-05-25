"""Tests for Story 1.15: govern status, run, report CLI commands and routing-failed area."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from llm_wiki.cli import main

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def wiki_base(tmp_path: Path) -> Path:
    """Minimal wiki_base with state/ and reports/ dirs."""
    (tmp_path / "state").mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "inbox" / "staging").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def wiki_with_jobs(wiki_base: Path) -> Path:
    """wiki_base with a pre-populated state/jobs.json."""
    jobs = {
        "lint": {
            "last_run": "2026-01-01T00:00:00+00:00",
            "outcome": "pass",
            "warning_count": 0,
            "error_count": 0,
        },
        "staleness": {
            "last_run": "2026-01-01T00:00:05+00:00",
            "outcome": "warnings",
            "warning_count": 2,
            "error_count": 0,
        },
    }
    (wiki_base / "state" / "jobs.json").write_text(json.dumps(jobs))
    return wiki_base


# ── govern status ─────────────────────────────────────────────────────────────


class TestGovernStatus:
    def test_status_json_with_jobs(self, runner: CliRunner, wiki_with_jobs: Path):
        result = runner.invoke(
            main, ["govern", "status", "--json", "--wiki-base", str(wiki_with_jobs)]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "lint" in data
        assert data["lint"]["outcome"] == "pass"
        assert "staleness" in data
        assert data["staleness"]["warning_count"] == 2

    def test_status_json_empty(self, runner: CliRunner, wiki_base: Path):
        result = runner.invoke(main, ["govern", "status", "--json", "--wiki-base", str(wiki_base)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == {}

    def test_status_human_readable(self, runner: CliRunner, wiki_with_jobs: Path):
        result = runner.invoke(main, ["govern", "status", "--wiki-base", str(wiki_with_jobs)])
        assert result.exit_code == 0
        assert "lint" in result.output
        assert "staleness" in result.output
        assert "outcome=pass" in result.output

    def test_status_only_shows_governance_keys(self, runner: CliRunner, wiki_base: Path):
        """Non-governance keys in jobs.json are excluded from govern status."""
        jobs = {
            "lint": {"last_run": "x", "outcome": "pass", "warning_count": 0, "error_count": 0},
            "inbox_scan": {"last_run": "x", "outcome": "pass"},
        }
        (wiki_base / "state" / "jobs.json").write_text(json.dumps(jobs))
        result = runner.invoke(main, ["govern", "status", "--json", "--wiki-base", str(wiki_base)])
        data = json.loads(result.output)
        assert "lint" in data
        assert "inbox_scan" not in data


# ── govern run ────────────────────────────────────────────────────────────────


class TestGovernRun:
    def test_run_lint_json(self, runner: CliRunner, wiki_base: Path):
        result = runner.invoke(
            main, ["govern", "run", "lint", "--json", "--wiki-base", str(wiki_base)]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "lint" in data
        assert data["lint"]["outcome"] in ("pass", "warnings", "errors")
        assert "last_run" in data["lint"]

    def test_run_lint_updates_jobs_json(self, runner: CliRunner, wiki_base: Path):
        runner.invoke(main, ["govern", "run", "lint", "--wiki-base", str(wiki_base)])
        jobs_path = wiki_base / "state" / "jobs.json"
        assert jobs_path.exists()
        data = json.loads(jobs_path.read_text())
        assert "lint" in data
        assert "outcome" in data["lint"]

    def test_run_staleness_json(self, runner: CliRunner, wiki_base: Path):
        result = runner.invoke(
            main, ["govern", "run", "staleness", "--json", "--wiki-base", str(wiki_base)]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "staleness" in data

    def test_run_lint_writes_json_report(self, runner: CliRunner, wiki_base: Path):
        runner.invoke(main, ["govern", "run", "lint", "--wiki-base", str(wiki_base)])
        reports = list((wiki_base / "reports").glob("governance_*.json"))
        assert len(reports) == 1

    def test_run_lock_prevents_concurrent(self, runner: CliRunner, wiki_base: Path):
        """Simulate a stale lock file — second run should fail with clear message."""
        import os

        lock_path = wiki_base / "state" / "governance.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Create a stale lock file
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        try:
            result = runner.invoke(main, ["govern", "run", "lint", "--wiki-base", str(wiki_base)])
            assert result.exit_code != 0
            assert (
                "already running" in result.output.lower()
                or "already running" in str(result.exception).lower()
            )
        finally:
            lock_path.unlink(missing_ok=True)

    def test_run_all_json(self, runner: CliRunner, wiki_base: Path):
        result = runner.invoke(
            main, ["govern", "run", "all", "--json", "--wiki-base", str(wiki_base)]
        )
        # all may warn about contradictions (LLM unavailable) but exit 0
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["jobs_run"] == ["lint", "staleness", "contradictions"]


# ── govern report ─────────────────────────────────────────────────────────────


class TestGovernReport:
    def test_report_includes_staging_items(self, runner: CliRunner, wiki_base: Path):
        staging = wiki_base / "inbox" / "staging"
        (staging / "mystery.md").write_text("orphaned content")

        result = runner.invoke(main, ["govern", "report", "--json", "--wiki-base", str(wiki_base)])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert "routing_failed" in data
        items = data["routing_failed"]
        assert len(items) == 1
        assert items[0]["status"] == "routing-failed"
        assert items[0]["source_name"] == "mystery.md"

    def test_report_empty_when_no_data(self, runner: CliRunner, wiki_base: Path):
        result = runner.invoke(main, ["govern", "report", "--json", "--wiki-base", str(wiki_base)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == {}

    def test_report_reads_latest_json_report(self, runner: CliRunner, wiki_base: Path):
        reports_dir = wiki_base / "reports"
        # Write an older and a newer report
        (reports_dir / "governance_20260101_000000.json").write_text(
            json.dumps({"generated": "old", "lint": {"outcome": "pass", "warning_count": 0}})
        )
        (reports_dir / "governance_20260201_000000.json").write_text(
            json.dumps({"generated": "new", "lint": {"outcome": "warnings", "warning_count": 5}})
        )
        result = runner.invoke(main, ["govern", "report", "--json", "--wiki-base", str(wiki_base)])
        data = json.loads(result.output)
        assert data["generated"] == "new"
        assert data["lint"]["warning_count"] == 5

    def test_report_domain_filter_on_staging(self, runner: CliRunner, wiki_base: Path):
        staging = wiki_base / "inbox" / "staging"
        (staging / "general_doc.md").write_text("content")
        (staging / "tech_note.md").write_text("content")

        result = runner.invoke(
            main,
            ["govern", "report", "--domain", "general", "--json", "--wiki-base", str(wiki_base)],
        )
        data = json.loads(result.output)
        items = data.get("routing_failed", [])
        assert all("general" in item["source_path"] for item in items)

    def test_report_human_readable_staging(self, runner: CliRunner, wiki_base: Path):
        staging = wiki_base / "inbox" / "staging"
        (staging / "orphan.md").write_text("content")

        result = runner.invoke(main, ["govern", "report", "--wiki-base", str(wiki_base)])
        assert result.exit_code == 0
        assert "routing" in result.output.lower() or "staging" in result.output.lower()


# ── Routing-failed area (InboxWatcher) ────────────────────────────────────────


class TestRoutingFailedArea:
    def test_content_falls_back_to_general_via_classifier(self, tmp_path: Path):
        """Unmatched content falls back to 'general' domain via heuristic classifier."""
        from unittest.mock import MagicMock

        from llm_wiki.adapters.base import AdapterRegistry
        from llm_wiki.ingest.normalizer import NormalizationPipeline

        # Build a pipeline with a mock adapter
        registry = AdapterRegistry()
        pipeline = NormalizationPipeline.__new__(NormalizationPipeline)
        pipeline.adapter_registry = registry
        pipeline._wiki_base = tmp_path
        # Set _classifier to None so Classifier is used instead
        pipeline._classifier = MagicMock()
        pipeline._classifier.classify.return_value = "general"

        # Mock adapter
        mock_adapter = MagicMock()
        mock_adapter.process.return_value = ({}, "# Content")
        registry.get_adapter = MagicMock(return_value=mock_adapter)

        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        output_path = pipeline.process_file(test_file)
        assert output_path.exists()
        content = output_path.read_text()
        assert "domain: general" in content

    def test_watcher_moves_unroutable_to_staging(self, tmp_path: Path):
        """InboxWatcher moves a file to inbox/staging/ when RoutingError is raised."""
        from unittest.mock import MagicMock

        from llm_wiki.ingest.normalizer import RoutingError
        from llm_wiki.ingest.watcher import InboxWatcher

        inbox_dir = tmp_path / "inbox"
        watcher = InboxWatcher(inbox_dir=inbox_dir)

        # Put a file in new/
        test_file = watcher.new_dir / "orphan.md"
        test_file.write_text("content without domain")

        # Patch pipeline to raise RoutingError
        watcher.pipeline = MagicMock()
        watcher.pipeline.process_file.side_effect = RoutingError("no domain matched")

        stats = watcher.scan()

        # File should NOT be in failed/ or new/ — it should be in staging/
        assert stats["failed"] == 0
        assert not (watcher.failed_dir / "orphan.md").exists()
        assert (watcher.staging_dir / "orphan.md").exists()

    def test_watcher_writes_routing_failed_jsonl(self, tmp_path: Path):
        """InboxWatcher appends a routing-failed JSONL entry for each staged file."""
        from unittest.mock import MagicMock

        from llm_wiki.ingest.normalizer import RoutingError
        from llm_wiki.ingest.watcher import InboxWatcher

        inbox_dir = tmp_path / "inbox"
        watcher = InboxWatcher(inbox_dir=inbox_dir)

        test_file = watcher.new_dir / "mystery.md"
        test_file.write_text("unroutable content")

        watcher.pipeline = MagicMock()
        watcher.pipeline.process_file.side_effect = RoutingError("no match")

        watcher.scan()

        wiki_base = inbox_dir.parent
        log_path = wiki_base / "reports" / "routing-failed.jsonl"
        assert log_path.exists()
        entry = json.loads(log_path.read_text().strip())
        assert entry["status"] == "routing-failed"
        assert "mystery.md" in entry["source_name"]
        assert "arrived_at" in entry

    def test_watcher_staging_dir_created_on_init(self, tmp_path: Path):
        """InboxWatcher creates inbox/staging/ on initialization."""
        from llm_wiki.ingest.watcher import InboxWatcher

        inbox_dir = tmp_path / "inbox"
        watcher = InboxWatcher(inbox_dir=inbox_dir)
        assert watcher.staging_dir.exists()


# ── ingest file staging passthrough ──────────────────────────────────────────


class TestIngestFileStagingPassthrough:
    def test_ingest_file_moves_from_staging(self, runner: CliRunner, wiki_base: Path):
        """ingest file <path> moves a staging file to inbox/new/ for daemon pickup."""
        staging = wiki_base / "inbox" / "staging"
        staging.mkdir(parents=True, exist_ok=True)
        staged_file = staging / "pending.md"
        staged_file.write_text("# Pending page")

        result = runner.invoke(
            main,
            ["ingest", "file", str(staged_file), "--wiki-base", str(wiki_base)],
        )
        assert result.exit_code == 0, result.output
        assert "staging" in result.output or "inbox/new" in result.output

        # File should now be in inbox/new/
        assert (wiki_base / "inbox" / "new" / "pending.md").exists()
        # File should no longer be in staging
        assert not staged_file.exists()

    def test_ingest_file_staging_injects_domain(self, runner: CliRunner, wiki_base: Path):
        """ingest file --domain injects domain into frontmatter so daemon can route it (AC:9)."""
        staging = wiki_base / "inbox" / "staging"
        staging.mkdir(parents=True, exist_ok=True)
        staged_file = staging / "unrouted.md"
        staged_file.write_text("# Unrouted Page\n\nContent with no routing rule.")

        result = runner.invoke(
            main,
            [
                "ingest",
                "file",
                str(staged_file),
                "--domain",
                "general",
                "--wiki-base",
                str(wiki_base),
            ],
        )
        assert result.exit_code == 0, result.output

        dest = wiki_base / "inbox" / "new" / "unrouted.md"
        assert dest.exists(), "File should have moved to inbox/new/"
        assert not staged_file.exists(), "File should no longer be in staging"
        content = dest.read_text()
        assert "domain: general" in content, "Domain must be injected so daemon routes it correctly"

    def test_ingest_regular_file_unchanged(
        self, runner: CliRunner, tmp_path: Path, wiki_base: Path
    ):
        """ingest file for a non-staging file still copies to inbox/ as before."""
        source = tmp_path / "regular.md"
        source.write_text("# Regular file")

        result = runner.invoke(
            main,
            ["ingest", "file", str(source), "--wiki-base", str(wiki_base)],
        )
        assert result.exit_code == 0, result.output
        assert (wiki_base / "inbox" / "regular.md").exists()
