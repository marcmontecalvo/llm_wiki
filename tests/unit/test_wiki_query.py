"""Tests for unified wiki query interface."""

from pathlib import Path

import pytest

from llm_wiki.query.search import WikiQuery


class TestWikiQuery:
    """Tests for WikiQuery."""

    @pytest.fixture
    def wiki_query(self, temp_dir: Path) -> WikiQuery:
        """Create wiki query with temp directory."""
        wiki_base = temp_dir / "wiki"
        return WikiQuery(wiki_base=wiki_base)

    def test_init_creates_indexes(self, wiki_query: WikiQuery):
        """Test that initialization creates both indexes."""
        assert wiki_query.metadata_index is not None
        assert wiki_query.fulltext_index is not None

    def test_add_page(self, wiki_query: WikiQuery):
        """Test adding a page to indexes."""
        metadata = {
            "id": "test",
            "title": "Test Page",
            "domain": "tech",
            "kind": "page",
            "tags": ["test"],
        }

        wiki_query.add_page("test", "Test Page", "Test content", metadata)

        # Should be in both indexes
        assert wiki_query.metadata_index.get_page("test") is not None
        assert "test" in wiki_query.fulltext_index.documents

    def test_remove_page(self, wiki_query: WikiQuery):
        """Test removing a page from indexes."""
        metadata = {"id": "test", "title": "Test", "tags": []}
        wiki_query.add_page("test", "Test", "Content", metadata)

        wiki_query.remove_page("test")

        assert wiki_query.metadata_index.get_page("test") is None
        assert "test" not in wiki_query.fulltext_index.documents

    def test_get_page(self, wiki_query: WikiQuery):
        """Test getting page by ID."""
        metadata = {"id": "test", "title": "Test Page"}
        wiki_query.add_page("test", "Test Page", "Content", metadata)

        result = wiki_query.get_page("test")

        assert result is not None
        assert result["title"] == "Test Page"

    def test_find_by_tag(self, wiki_query: WikiQuery):
        """Test finding pages by tag."""
        wiki_query.add_page("page1", "Page 1", "Content", {"id": "page1", "tags": ["python"]})
        wiki_query.add_page("page2", "Page 2", "Content", {"id": "page2", "tags": ["python"]})
        wiki_query.add_page("page3", "Page 3", "Content", {"id": "page3", "tags": ["javascript"]})

        results = wiki_query.find_by_tag("python")

        assert len(results) == 2

    def test_find_by_kind(self, wiki_query: WikiQuery):
        """Test finding pages by kind."""
        wiki_query.add_page("entity1", "Entity 1", "Content", {"id": "entity1", "kind": "entity"})
        wiki_query.add_page("page1", "Page 1", "Content", {"id": "page1", "kind": "page"})

        results = wiki_query.find_by_kind("entity")

        assert len(results) == 1
        assert results[0]["id"] == "entity1"

    def test_find_by_domain(self, wiki_query: WikiQuery):
        """Test finding pages by domain."""
        wiki_query.add_page("page1", "Page 1", "Content", {"id": "page1", "domain": "tech"})
        wiki_query.add_page("page2", "Page 2", "Content", {"id": "page2", "domain": "business"})

        results = wiki_query.find_by_domain("tech")

        assert len(results) == 1
        assert results[0]["id"] == "page1"

    def test_get_all_tags(self, wiki_query: WikiQuery):
        """Test getting all tags."""
        wiki_query.add_page("page1", "Page 1", "Content", {"id": "page1", "tags": ["python"]})
        wiki_query.add_page("page2", "Page 2", "Content", {"id": "page2", "tags": ["api"]})

        tags = wiki_query.get_all_tags()

        assert "python" in tags
        assert "api" in tags

    def test_search_fulltext_only(self, wiki_query: WikiQuery):
        """Test fulltext search without filters."""
        wiki_query.add_page(
            "page1",
            "Python Programming",
            "Learn Python",
            {"id": "page1", "title": "Python Programming", "domain": "tech"},
        )
        wiki_query.add_page(
            "page2",
            "JavaScript Guide",
            "Learn JS",
            {"id": "page2", "title": "JavaScript Guide", "domain": "tech"},
        )

        results = wiki_query.search(query="python")

        assert len(results) == 1
        assert results[0]["page_id"] == "page1"

    def test_search_with_domain_filter(self, wiki_query: WikiQuery):
        """Test search with domain filter."""
        wiki_query.add_page(
            "page1",
            "Python",
            "Python content",
            {"id": "page1", "title": "Python", "domain": "tech"},
        )
        wiki_query.add_page(
            "page2",
            "Python",
            "Python content",
            {"id": "page2", "title": "Python", "domain": "business"},
        )

        results = wiki_query.search(query="python", domain="tech")

        assert len(results) == 1
        assert results[0]["domain"] == "tech"

    def test_search_with_kind_filter(self, wiki_query: WikiQuery):
        """Test search with kind filter."""
        wiki_query.add_page(
            "page1",
            "Python",
            "Python language",
            {"id": "page1", "title": "Python", "kind": "entity"},
        )
        wiki_query.add_page(
            "page2",
            "Python Guide",
            "Python tutorial",
            {"id": "page2", "title": "Python Guide", "kind": "page"},
        )

        results = wiki_query.search(query="python", kind="entity")

        assert len(results) == 1
        assert results[0]["kind"] == "entity"

    def test_search_with_tag_filter(self, wiki_query: WikiQuery):
        """Test search with tag filter."""
        wiki_query.add_page(
            "page1",
            "Python",
            "Python content",
            {"id": "page1", "title": "Python", "tags": ["programming", "tutorial"]},
        )
        wiki_query.add_page(
            "page2",
            "Python",
            "Python content",
            {"id": "page2", "title": "Python", "tags": ["programming"]},
        )

        results = wiki_query.search(query="python", tags=["programming", "tutorial"])

        # Only page1 has both tags
        assert len(results) == 1
        assert results[0]["page_id"] == "page1"

    def test_search_metadata_only(self, wiki_query: WikiQuery):
        """Test search with metadata filters only (no fulltext query)."""
        wiki_query.add_page(
            "page1", "Page 1", "Content", {"id": "page1", "kind": "entity", "tags": ["python"]}
        )
        wiki_query.add_page(
            "page2", "Page 2", "Content", {"id": "page2", "kind": "page", "tags": ["python"]}
        )

        results = wiki_query.search(kind="entity")

        assert len(results) == 1
        assert results[0]["page_id"] == "page1"

    def test_search_returns_enriched_results(self, wiki_query: WikiQuery):
        """Test that search results include all metadata fields."""
        wiki_query.add_page(
            "page1",
            "Test Page",
            "Content",
            {
                "id": "page1",
                "title": "Test Page",
                "domain": "tech",
                "kind": "entity",
                "tags": ["test"],
            },
        )

        results = wiki_query.search(query="test")

        assert len(results) == 1
        result = results[0]
        assert result["page_id"] == "page1"
        assert result["title"] == "Test Page"
        assert result["domain"] == "tech"
        assert result["kind"] == "entity"
        assert "test" in result["tags"]
        assert "score" in result

    def test_search_limit(self, wiki_query: WikiQuery):
        """Test search result limit."""
        for i in range(10):
            wiki_query.add_page(
                f"page{i}",
                f"Python Page {i}",
                "Python content",
                {"id": f"page{i}", "title": f"Python Page {i}"},
            )

        results = wiki_query.search(query="python", limit=3)

        assert len(results) == 3

    def test_save_and_load_indexes(self, wiki_query: WikiQuery, temp_dir: Path):
        """Test saving and loading indexes."""
        # Add data
        wiki_query.add_page("page1", "Test", "Content", {"id": "page1", "title": "Test"})

        # Save
        wiki_query.save_indexes()

        # Create new query instance
        wiki_query2 = WikiQuery(wiki_base=temp_dir / "wiki")

        # Should have loaded data
        assert wiki_query2.get_page("page1") is not None

    def test_rebuild_indexes(self, wiki_query: WikiQuery, temp_dir: Path):
        """Test rebuilding indexes from wiki pages."""
        # Create wiki structure
        wiki_base = temp_dir / "wiki"
        domain_dir = wiki_base / "domains" / "general" / "pages"
        domain_dir.mkdir(parents=True)

        # Create test page
        page_file = domain_dir / "test.md"
        page_file.write_text(
            """---
id: test
title: Test Page
tags:
  - test
---

Test content
"""
        )

        # Rebuild
        metadata_count, fulltext_count = wiki_query.rebuild_indexes()

        assert metadata_count == 1
        assert fulltext_count == 1

        # Should be searchable
        results = wiki_query.search(query="test")
        assert len(results) == 1

    def test_search_empty_query_with_filters(self, wiki_query: WikiQuery):
        """Test metadata-only search with no fulltext query."""
        wiki_query.add_page(
            "page1",
            "Page 1",
            "Content",
            {"id": "page1", "domain": "tech", "tags": ["python"]},
        )
        wiki_query.add_page(
            "page2",
            "Page 2",
            "Content",
            {"id": "page2", "domain": "business", "tags": ["python"]},
        )

        # Search by domain only, no fulltext query
        results = wiki_query.search(domain="tech")

        assert len(results) == 1
        assert results[0]["domain"] == "tech"

    def test_search_no_results(self, wiki_query: WikiQuery):
        """Test search with no matching results."""
        wiki_query.add_page("page1", "Test", "Content", {"id": "page1", "title": "Test"})

        results = wiki_query.search(query="nonexistent")

        assert results == []
