"""Tests for fulltext search indexer."""

from pathlib import Path

import pytest

from llm_wiki.index.fulltext import FulltextIndex


class TestFulltextIndex:
    """Tests for FulltextIndex."""

    @pytest.fixture
    def index(self, temp_dir: Path) -> FulltextIndex:
        """Create fulltext index in temp directory."""
        index_dir = temp_dir / "index"
        return FulltextIndex(index_dir=index_dir)

    def test_tokenize(self, index: FulltextIndex):
        """Test text tokenization."""
        text = "Python Programming and API Design"

        tokens = index._tokenize(text)

        assert tokens == ["python", "programming", "and", "api", "design"]

    def test_tokenize_filters_short_words(self, index: FulltextIndex):
        """Test that single-character words are filtered."""
        text = "a b c Python is a language"

        tokens = index._tokenize(text)

        # Single chars filtered out
        assert "a" not in tokens
        assert "b" not in tokens
        assert "c" not in tokens
        assert "python" in tokens
        assert "is" in tokens

    def test_tokenize_extracts_alphanumeric(self, index: FulltextIndex):
        """Test that only alphanumeric words are extracted."""
        text = "Python, JavaScript! C++. Go? Rust123"

        tokens = index._tokenize(text)

        assert "python" in tokens
        assert "javascript" in tokens
        assert "go" in tokens
        assert "rust123" in tokens
        # C++ gets broken up
        assert "c" not in tokens  # Too short

    def test_add_document(self, index: FulltextIndex):
        """Test adding a document to index."""
        index.add_document(
            page_id="page1",
            title="Python Programming",
            content="Learn Python programming with examples",
            domain="tech",
        )

        # Check document metadata
        assert "page1" in index.documents
        assert index.documents["page1"]["title"] == "Python Programming"
        assert index.documents["page1"]["domain"] == "tech"

        # Check inverted index
        assert "python" in index.inverted_index
        assert "page1" in index.inverted_index["python"]

        # Title words should be weighted (appear 3x)
        # "python" appears once in title (3x weight) and once in content = 4
        assert index.inverted_index["python"]["page1"] == 4

    def test_add_document_updates_existing(self, index: FulltextIndex):
        """Test updating an existing document."""
        index.add_document("page1", "Title", "Content", "general")
        index.add_document("page1", "New Title", "New content", "tech")

        # Should have updated metadata
        assert index.documents["page1"]["title"] == "New Title"
        assert index.documents["page1"]["domain"] == "tech"

    def test_remove_document(self, index: FulltextIndex):
        """Test removing a document from index."""
        index.add_document("page1", "Python", "Python content", "tech")

        index.remove_document("page1")

        assert "page1" not in index.documents
        # Should be removed from inverted index
        if "python" in index.inverted_index:
            assert "page1" not in index.inverted_index["python"]

    def test_remove_nonexistent_document(self, index: FulltextIndex):
        """Test removing a document that doesn't exist."""
        # Should not raise error
        index.remove_document("nonexistent")

    def test_search_single_word(self, index: FulltextIndex):
        """Test searching for a single word."""
        index.add_document("page1", "Python Tutorial", "Learn Python programming")
        index.add_document("page2", "JavaScript Guide", "Learn JavaScript basics")
        index.add_document("page3", "Python Advanced", "Advanced Python techniques")

        results = index.search("python")

        assert len(results) == 2
        page_ids = [r["page_id"] for r in results]
        assert "page1" in page_ids
        assert "page3" in page_ids

    def test_search_multiple_words(self, index: FulltextIndex):
        """Test searching for multiple words."""
        index.add_document("page1", "Python Tutorial", "Learn Python programming")
        index.add_document("page2", "Python Web", "Python web development")
        index.add_document("page3", "JavaScript Web", "JavaScript web development")

        results = index.search("python web")

        # Should return pages with both words ranked higher
        assert len(results) > 0
        # page2 has both "python" and "web"
        page_ids = [r["page_id"] for r in results]
        assert "page2" in page_ids

    def test_search_with_domain_filter(self, index: FulltextIndex):
        """Test searching with domain filter."""
        index.add_document("page1", "Python", "Python content", "tech")
        index.add_document("page2", "Python", "Python content", "business")

        results = index.search("python", domain="tech")

        assert len(results) == 1
        assert results[0]["page_id"] == "page1"
        assert results[0]["domain"] == "tech"

    def test_search_limit(self, index: FulltextIndex):
        """Test search result limit."""
        # Add many documents
        for i in range(20):
            index.add_document(f"page{i}", "Python", f"Python content {i}", "tech")

        results = index.search("python", limit=5)

        assert len(results) == 5

    def test_search_no_results(self, index: FulltextIndex):
        """Test search with no matching documents."""
        index.add_document("page1", "Python", "Python content")

        results = index.search("nonexistent")

        assert results == []

    def test_search_empty_query(self, index: FulltextIndex):
        """Test search with empty query."""
        index.add_document("page1", "Python", "Content")

        results = index.search("")

        assert results == []

    def test_search_scoring_title_weighted(self, index: FulltextIndex):
        """Test that title words are weighted higher in scoring."""
        # Document with word only in title
        index.add_document("page1", "Python Programming", "Learn to code")
        # Document with word only in content
        index.add_document("page2", "Coding Guide", "Learn Python basics")

        results = index.search("python")

        # page1 should score higher due to title weighting
        assert results[0]["page_id"] == "page1"
        assert results[0]["score"] > results[1]["score"]

    def test_search_returns_metadata(self, index: FulltextIndex):
        """Test that search results include metadata."""
        index.add_document("page1", "Test Page", "Content", "tech")

        results = index.search("test")

        assert len(results) == 1
        result = results[0]
        assert result["page_id"] == "page1"
        assert result["title"] == "Test Page"
        assert result["domain"] == "tech"
        assert "score" in result

    def test_save_and_load(self, index: FulltextIndex, temp_dir: Path):
        """Test saving and loading index."""
        # Add documents
        index.add_document("page1", "Python", "Python content", "tech")
        index.add_document("page2", "JavaScript", "JS content", "tech")

        # Save
        index.save()

        # Create new index and load
        index2 = FulltextIndex(index_dir=temp_dir / "index")
        index2.load()

        # Verify data was loaded
        assert len(index2.documents) == 2
        assert "page1" in index2.documents
        assert "python" in index2.inverted_index

        # Search should work
        results = index2.search("python")
        assert len(results) == 1

    def test_load_nonexistent_index(self, index: FulltextIndex):
        """Test loading when no index exists."""
        # Should not raise error
        index.load()
        assert len(index.documents) == 0

    def test_rebuild_from_pages(self, index: FulltextIndex, temp_dir: Path):
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
title: Python Programming
---

Learn Python programming with examples.
"""
        )

        page2 = domain_dir / "page2.md"
        page2.write_text(
            """---
id: page2
title: JavaScript Guide
---

Learn JavaScript basics.
"""
        )

        # Rebuild
        count = index.rebuild_from_pages(wiki_base)

        assert count == 2
        assert "page1" in index.documents
        assert "page2" in index.documents

        # Search should work
        results = index.search("python")
        assert len(results) == 1
        assert results[0]["page_id"] == "page1"

    def test_rebuild_from_pages_missing_domains(self, index: FulltextIndex, temp_dir: Path):
        """Test rebuilding when domains directory doesn't exist."""
        wiki_base = temp_dir / "wiki"

        count = index.rebuild_from_pages(wiki_base)

        assert count == 0

    def test_rebuild_from_pages_handles_errors(self, index: FulltextIndex, temp_dir: Path):
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

    def test_rebuild_clears_existing_index(self, index: FulltextIndex, temp_dir: Path):
        """Test that rebuild clears existing index data."""
        # Add some initial data
        index.add_document("old", "Old Doc", "Old content")

        # Create wiki with new data
        wiki_base = temp_dir / "wiki"
        domain_dir = wiki_base / "domains" / "general" / "pages"
        domain_dir.mkdir(parents=True)

        new_page = domain_dir / "new.md"
        new_page.write_text("---\nid: new\ntitle: New Doc\n---\nNew content")

        # Rebuild
        index.rebuild_from_pages(wiki_base)

        # Old document should be gone
        assert "old" not in index.documents
        assert "new" in index.documents
