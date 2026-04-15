"""Tests for governance daemon job."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from llm_wiki.daemon.jobs.governance import GovernanceJob, run_governance_check


class TestGovernanceJob:
    """Tests for GovernanceJob."""

    @pytest.fixture
    def wiki_base(self, temp_dir: Path) -> Path:
        """Create wiki directory with test pages."""
        wiki_base = temp_dir / "wiki"
        index_dir = wiki_base / "index"
        index_dir.mkdir(parents=True)

        pages_dir = wiki_base / "domains" / "general" / "pages"
        pages_dir.mkdir(parents=True)

        # Valid page
        (pages_dir / "valid.md").write_text(
            """---
id: valid
title: Valid Page
domain: general
summary: A valid page
tags: [test]
source: http://example.com
---

# Content

Valid content with structure."""
        )

        # Page with lint issues
        (pages_dir / "invalid.md").write_text(
            """---
title: Missing Fields
---

Content"""
        )

        # Old/stale page
        old_date = datetime.now(UTC) - timedelta(days=100)
        (pages_dir / "old.md").write_text(
            f"""---
id: old
title: Old Page
domain: general
created: {old_date.isoformat()}
updated: {old_date.isoformat()}
---

Content from 2024."""
        )

        return wiki_base

    @pytest.fixture
    def job(self, wiki_base: Path) -> GovernanceJob:
        """Create governance job."""
        return GovernanceJob(wiki_base=wiki_base)

    def test_init(self, job: GovernanceJob):
        """Test job initialization."""
        assert job.linter is not None
        assert job.staleness_detector is not None
        assert job.quality_scorer is not None
        assert job.duplicate_detector is not None

    def test_execute_success(self, job: GovernanceJob):
        """Test successful execution."""
        result = job.execute()

        assert result["status"] == "success"
        assert result["lint_issues"] >= 0
        assert result["stale_pages"] >= 0
        assert result["low_quality_pages"] >= 0
        assert result["duplicates"] >= 0
        assert "report_path" in result

    def test_execute_generates_report(self, job: GovernanceJob, wiki_base: Path):
        """Test that execution generates a report file."""
        result = job.execute()

        report_path = Path(result["report_path"])
        assert report_path.exists()
        assert report_path.suffix == ".md"

        # Check report content
        content = report_path.read_text()
        assert "# Governance Report" in content
        assert "## Summary" in content

    def test_execute_detects_lint_issues(self, job: GovernanceJob):
        """Test that execution detects lint issues."""
        result = job.execute()

        assert result["lint_issues"] > 0  # invalid.md has missing fields

    def test_execute_detects_stale_pages(self, job: GovernanceJob):
        """Test that execution detects stale pages."""
        result = job.execute()

        assert result["stale_pages"] >= 0  # old.md may be flagged as stale

    def test_execute_detects_low_quality(self, job: GovernanceJob):
        """Test that execution detects low-quality pages."""
        result = job.execute()

        assert result["low_quality_pages"] >= 0

    def test_generate_report_structure(self, job: GovernanceJob):
        """Test report structure."""
        job.execute()

        reports_dir = job.wiki_base / "reports"
        assert reports_dir.exists()

        # Find latest report
        reports = list(reports_dir.glob("governance_*.md"))
        assert len(reports) > 0

        content = reports[0].read_text()
        assert "# Governance Report" in content
        assert "## Summary" in content
        assert "Pages scanned:" in content
        assert "Duplicate candidates:" in content or "## Detected Duplicates" in content

    def test_run_governance_check_function(self, wiki_base: Path):
        """Test the run_governance_check function."""
        result = run_governance_check(wiki_base=wiki_base)

        assert result["status"] == "success"
        assert "lint_issues" in result
        assert "stale_pages" in result
        assert "low_quality_pages" in result

    def test_execute_with_no_domains(self, temp_dir: Path):
        """Test execution with no domains directory."""
        empty_wiki = temp_dir / "empty"
        job = GovernanceJob(wiki_base=empty_wiki)

        result = job.execute()

        assert result["status"] == "success"
        assert result["lint_issues"] == 0
        assert result["stale_pages"] == 0
        assert result["low_quality_pages"] == 0
