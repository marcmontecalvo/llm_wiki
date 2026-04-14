"""Tests for index rebuild daemon job."""

from pathlib import Path

import pytest

from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob, run_index_rebuild


class TestIndexRebuildJob:
    """Tests for IndexRebuildJob."""

    @pytest.fixture
    def wiki_base(self, temp_dir: Path) -> Path:
        """Create wiki directory structure."""
        wiki_base = temp_dir / "wiki"
        domain_dir = wiki_base / "domains" / "general" / "pages"
        domain_dir.mkdir(parents=True)
        return wiki_base

    @pytest.fixture
    def job(self, wiki_base: Path) -> IndexRebuildJob:
        """Create index rebuild job."""
        return IndexRebuildJob(wiki_base=wiki_base)

    def test_init(self, job: IndexRebuildJob, wiki_base: Path):
        """Test job initialization."""
        assert job.wiki_base == wiki_base
        assert job.wiki_query is not None

    def test_execute_empty_wiki(self, job: IndexRebuildJob):
        """Test executing rebuild on empty wiki."""
        result = job.execute()

        assert result["status"] == "success"
        assert result["metadata_count"] == 0
        assert result["fulltext_count"] == 0

    def test_execute_with_pages(self, job: IndexRebuildJob, wiki_base: Path):
        """Test executing rebuild with wiki pages."""
        # Create test pages
        pages_dir = wiki_base / "domains" / "general" / "pages"

        page1 = pages_dir / "page1.md"
        page1.write_text(
            """---
id: page1
title: Test Page 1
tags:
  - test
---

Test content
"""
        )

        page2 = pages_dir / "page2.md"
        page2.write_text(
            """---
id: page2
title: Test Page 2
kind: entity
---

Content
"""
        )

        result = job.execute()

        assert result["status"] == "success"
        assert result["metadata_count"] == 2
        assert result["fulltext_count"] == 2

    def test_execute_with_multiple_domains(self, job: IndexRebuildJob, wiki_base: Path):
        """Test executing rebuild with multiple domains."""
        # Create pages in multiple domains
        tech_pages = wiki_base / "domains" / "tech" / "pages"
        tech_pages.mkdir(parents=True)

        business_pages = wiki_base / "domains" / "business" / "pages"
        business_pages.mkdir(parents=True)

        tech_page = tech_pages / "tech.md"
        tech_page.write_text("---\nid: tech\ntitle: Tech Page\n---\nContent")

        business_page = business_pages / "business.md"
        business_page.write_text("---\nid: business\ntitle: Business Page\n---\nContent")

        result = job.execute()

        assert result["status"] == "success"
        assert result["metadata_count"] == 2
        assert result["fulltext_count"] == 2

    def test_execute_handles_errors(self, job: IndexRebuildJob, wiki_base: Path):
        """Test that execute handles errors gracefully."""
        # Create invalid page
        pages_dir = wiki_base / "domains" / "general" / "pages"
        invalid_page = pages_dir / "invalid.md"
        invalid_page.write_text("---\ninvalid: yaml: syntax:\n---\nContent")

        # Should not crash
        result = job.execute()

        assert result["status"] == "success"
        # Invalid page should be skipped
        assert result["metadata_count"] == 0

    def test_execute_rebuilds_indexes(self, job: IndexRebuildJob, wiki_base: Path):
        """Test that execute actually rebuilds the indexes."""
        # Create a page
        pages_dir = wiki_base / "domains" / "general" / "pages"
        page = pages_dir / "test.md"
        page.write_text("---\nid: test\ntitle: Test\n---\nContent")

        # Execute rebuild
        job.execute()

        # Verify indexes were rebuilt
        assert job.wiki_query.get_page("test") is not None
        results = job.wiki_query.search(query="test")
        assert len(results) == 1

    def test_execute_saves_indexes(self, job: IndexRebuildJob, wiki_base: Path):
        """Test that execute saves indexes to disk."""
        # Create a page
        pages_dir = wiki_base / "domains" / "general" / "pages"
        page = pages_dir / "test.md"
        page.write_text("---\nid: test\ntitle: Test\n---\nContent")

        # Execute rebuild
        job.execute()

        # Verify index files were created
        index_dir = wiki_base / "index"
        assert (index_dir / "metadata.json").exists()
        assert (index_dir / "fulltext.json").exists()

    def test_run_index_rebuild_function(self, wiki_base: Path):
        """Test the run_index_rebuild function."""
        # Create a page
        pages_dir = wiki_base / "domains" / "general" / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        page = pages_dir / "test.md"
        page.write_text("---\nid: test\ntitle: Test\n---\nContent")

        # Run via function
        result = run_index_rebuild(wiki_base=wiki_base)

        assert result["status"] == "success"
        assert result["metadata_count"] == 1
        assert result["fulltext_count"] == 1

    def test_execute_with_missing_id(self, job: IndexRebuildJob, wiki_base: Path):
        """Test handling pages without explicit ID."""
        pages_dir = wiki_base / "domains" / "general" / "pages"
        page = pages_dir / "test_page.md"
        page.write_text("---\ntitle: Test Page\n---\nContent")

        result = job.execute()

        assert result["status"] == "success"
        assert result["metadata_count"] == 1

        # Should use filename as ID
        page_data = job.wiki_query.get_page("test_page")
        assert page_data is not None

    def test_execute_incremental_rebuild(self, job: IndexRebuildJob, wiki_base: Path):
        """Test that rebuild replaces old data."""
        pages_dir = wiki_base / "domains" / "general" / "pages"

        # First rebuild with one page
        page1 = pages_dir / "page1.md"
        page1.write_text("---\nid: page1\ntitle: Page 1\n---\nContent")

        result1 = job.execute()
        assert result1["metadata_count"] == 1

        # Add another page and rebuild
        page2 = pages_dir / "page2.md"
        page2.write_text("---\nid: page2\ntitle: Page 2\n---\nContent")

        result2 = job.execute()
        assert result2["metadata_count"] == 2

        # Both pages should be in index
        assert job.wiki_query.get_page("page1") is not None
        assert job.wiki_query.get_page("page2") is not None

    def test_execute_with_no_domains_dir(self, temp_dir: Path):
        """Test execute when domains directory doesn't exist."""
        wiki_base = temp_dir / "empty_wiki"
        job = IndexRebuildJob(wiki_base=wiki_base)

        result = job.execute()

        # Should succeed with zero count
        assert result["status"] == "success"
        assert result["metadata_count"] == 0
        assert result["fulltext_count"] == 0
