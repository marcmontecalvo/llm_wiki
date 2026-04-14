"""Tests for export daemon job."""

from pathlib import Path

import pytest

from llm_wiki.daemon.jobs.export import ExportJob, run_export_job


class TestExportJob:
    """Tests for ExportJob."""

    @pytest.fixture
    def wiki_base(self, temp_dir: Path) -> Path:
        """Create wiki with test page."""
        wiki_base = temp_dir / "wiki"
        pages_dir = wiki_base / "domains" / "general" / "pages"
        pages_dir.mkdir(parents=True)

        (pages_dir / "test.md").write_text(
            """---
id: test
title: Test Page
domain: general
---

Test content with [[other-page]] link."""
        )

        return wiki_base

    def test_execute_success(self, wiki_base: Path):
        """Test successful execution."""
        job = ExportJob(wiki_base=wiki_base)

        result = job.execute()

        assert result["status"] == "success"
        assert "llmstxt_path" in result
        assert "json_sidecars" in result
        assert "graph_path" in result
        assert "sitemap_path" in result

    def test_execute_creates_exports(self, wiki_base: Path):
        """Test that execution creates export files."""
        job = ExportJob(wiki_base=wiki_base)

        job.execute()

        exports_dir = wiki_base / "exports"
        assert exports_dir.exists()
        assert (exports_dir / "llms.txt").exists()
        assert (exports_dir / "graph.json").exists()
        assert (exports_dir / "sitemap.xml").exists()

    def test_run_export_job_function(self, wiki_base: Path):
        """Test the run_export_job function."""
        result = run_export_job(wiki_base=wiki_base)

        assert result["status"] == "success"
