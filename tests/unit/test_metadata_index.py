"""Tests for metadata indexer."""

from pathlib import Path

import pytest

from llm_wiki.index.metadata import MetadataIndex


class TestMetadataIndex:
    """Tests for MetadataIndex."""

    @pytest.fixture
    def index(self, temp_dir: Path) -> MetadataIndex:
        """Create metadata index in temp directory."""
        index_dir = temp_dir / "index"
        return MetadataIndex(index_dir=index_dir)

    def test_add_page(self, index: MetadataIndex):
        """Test adding a page to index."""
        metadata = {
            "id": "test-page",
            "title": "Test Page",
            "domain": "general",
            "kind": "page",
            "tags": ["test", "example"],
        }

        index.add_page("test-page", metadata)

        assert "test-page" in index.pages
        assert index.pages["test-page"]["title"] == "Test Page"
        assert "test-page" in index.by_tag["test"]
        assert "test-page" in index.by_tag["example"]
        assert "test-page" in index.by_kind["page"]
        assert "test-page" in index.by_domain["general"]

    def test_add_page_normalizes_tags(self, index: MetadataIndex):
        """Test that tags are normalized to lowercase."""
        metadata = {
            "id": "test",
            "title": "Test",
            "tags": ["Python", "API", "Database"],
        }

        index.add_page("test", metadata)

        assert "test" in index.by_tag["python"]
        assert "test" in index.by_tag["api"]
        assert "test" in index.by_tag["database"]

    def test_remove_page(self, index: MetadataIndex):
        """Test removing a page from index."""
        metadata = {
            "id": "test",
            "title": "Test",
            "tags": ["test"],
            "kind": "page",
            "domain": "general",
        }

        index.add_page("test", metadata)
        index.remove_page("test")

        assert "test" not in index.pages
        assert "test" not in index.by_tag.get("test", set())
        assert "test" not in index.by_kind.get("page", set())
        assert "test" not in index.by_domain.get("general", set())

    def test_remove_nonexistent_page(self, index: MetadataIndex):
        """Test removing a page that doesn't exist."""
        # Should not raise error
        index.remove_page("nonexistent")

    def test_find_by_tag(self, index: MetadataIndex):
        """Test finding pages by tag."""
        index.add_page("page1", {"id": "page1", "title": "Page 1", "tags": ["python"]})
        index.add_page("page2", {"id": "page2", "title": "Page 2", "tags": ["python", "api"]})
        index.add_page("page3", {"id": "page3", "title": "Page 3", "tags": ["api"]})

        results = index.find_by_tag("python")

        assert len(results) == 2
        page_ids = [p["id"] for p in results]
        assert "page1" in page_ids
        assert "page2" in page_ids

    def test_find_by_tag_case_insensitive(self, index: MetadataIndex):
        """Test tag search is case insensitive."""
        index.add_page("page1", {"id": "page1", "title": "Page 1", "tags": ["Python"]})

        results = index.find_by_tag("PYTHON")

        assert len(results) == 1
        assert results[0]["id"] == "page1"

    def test_find_by_kind(self, index: MetadataIndex):
        """Test finding pages by kind."""
        index.add_page("entity1", {"id": "entity1", "title": "Entity 1", "kind": "entity"})
        index.add_page("concept1", {"id": "concept1", "title": "Concept 1", "kind": "concept"})
        index.add_page("page1", {"id": "page1", "title": "Page 1", "kind": "page"})

        results = index.find_by_kind("entity")

        assert len(results) == 1
        assert results[0]["id"] == "entity1"

    def test_find_by_domain(self, index: MetadataIndex):
        """Test finding pages by domain."""
        index.add_page("page1", {"id": "page1", "title": "Page 1", "domain": "tech"})
        index.add_page("page2", {"id": "page2", "title": "Page 2", "domain": "tech"})
        index.add_page("page3", {"id": "page3", "title": "Page 3", "domain": "business"})

        results = index.find_by_domain("tech")

        assert len(results) == 2
        page_ids = [p["id"] for p in results]
        assert "page1" in page_ids
        assert "page2" in page_ids

    def test_get_page(self, index: MetadataIndex):
        """Test getting page by ID."""
        metadata = {"id": "test", "title": "Test Page"}
        index.add_page("test", metadata)

        result = index.get_page("test")

        assert result is not None
        assert result["title"] == "Test Page"

    def test_get_nonexistent_page(self, index: MetadataIndex):
        """Test getting page that doesn't exist."""
        result = index.get_page("nonexistent")

        assert result is None

    def test_get_all_tags(self, index: MetadataIndex):
        """Test getting all tags."""
        index.add_page("page1", {"id": "page1", "tags": ["python", "api"]})
        index.add_page("page2", {"id": "page2", "tags": ["docker", "api"]})

        tags = index.get_all_tags()

        assert tags == ["api", "docker", "python"]  # Sorted

    def test_save_and_load(self, index: MetadataIndex, temp_dir: Path):
        """Test saving and loading index."""
        # Add some pages
        index.add_page(
            "page1", {"id": "page1", "title": "Page 1", "tags": ["test"], "kind": "page"}
        )
        index.add_page(
            "page2", {"id": "page2", "title": "Page 2", "tags": ["example"], "kind": "concept"}
        )

        # Save
        index.save()

        # Create new index and load
        index2 = MetadataIndex(index_dir=temp_dir / "index")
        index2.load()

        # Verify data was loaded
        assert len(index2.pages) == 2
        assert "page1" in index2.pages
        assert "page2" in index2.pages
        assert "test" in index2.by_tag
        assert "page" in index2.by_kind

    def test_load_nonexistent_index(self, index: MetadataIndex):
        """Test loading when no index exists."""
        # Should not raise error
        index.load()
        assert len(index.pages) == 0

    def test_rebuild_from_pages(self, index: MetadataIndex, temp_dir: Path):
        """Test rebuilding index from wiki pages."""
        # Create wiki structure
        wiki_base = temp_dir / "wiki"
        domain_dir = wiki_base / "domains" / "general" / "pages"
        domain_dir.mkdir(parents=True)

        # Create test pages
        page1 = domain_dir / "page1.md"
        page1.write_text(
            """---
id: page1
title: Page 1
kind: page
tags:
  - test
  - example
---

Content
"""
        )

        page2 = domain_dir / "page2.md"
        page2.write_text(
            """---
id: page2
title: Page 2
kind: entity
tags:
  - python
---

Content
"""
        )

        # Rebuild
        count = index.rebuild_from_pages(wiki_base)

        assert count == 2
        assert "page1" in index.pages
        assert "page2" in index.pages
        assert "page1" in index.by_tag["test"]
        assert "page2" in index.by_kind["entity"]

    def test_rebuild_from_pages_missing_domains(self, index: MetadataIndex, temp_dir: Path):
        """Test rebuilding when domains directory doesn't exist."""
        wiki_base = temp_dir / "wiki"

        count = index.rebuild_from_pages(wiki_base)

        assert count == 0

    def test_rebuild_from_pages_handles_errors(self, index: MetadataIndex, temp_dir: Path):
        """Test rebuilding handles invalid files gracefully."""
        wiki_base = temp_dir / "wiki"
        domain_dir = wiki_base / "domains" / "general" / "pages"
        domain_dir.mkdir(parents=True)

        # Create invalid page (bad YAML)
        invalid_page = domain_dir / "invalid.md"
        invalid_page.write_text("---\ninvalid: yaml: syntax:\n---\nContent")

        # Should not crash
        count = index.rebuild_from_pages(wiki_base)

        assert count == 0  # Invalid page not indexed
