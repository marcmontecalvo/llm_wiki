"""
Smoke tests for integration testing.

These tests verify that basic components can be imported and instantiated
without errors, providing a foundation for deeper integration testing.
"""

import pytest

from llm_wiki.daemon.jobs.export import ExportJob
from llm_wiki.daemon.jobs.governance import GovernanceJob
from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob
from llm_wiki.governance.linter import MetadataLinter
from llm_wiki.governance.quality import QualityScorer
from llm_wiki.governance.staleness import StalenessDetector
from llm_wiki.index.fulltext import FulltextIndex
from llm_wiki.index.metadata import MetadataIndex
from llm_wiki.query.search import WikiQuery


@pytest.fixture
def wiki_structure(tmp_path):
    """Create minimal wiki structure."""
    wiki_base = tmp_path / "wiki_system"
    (wiki_base / "domains" / "general" / "pages").mkdir(parents=True)
    (wiki_base / "domains" / "tech" / "pages").mkdir(parents=True)
    (wiki_base / "index").mkdir(parents=True)
    (wiki_base / "exports").mkdir(parents=True)
    (wiki_base / "reports").mkdir(parents=True)
    (wiki_base / "inbox").mkdir(parents=True)
    return wiki_base


def test_can_instantiate_wiki_query(wiki_structure):
    """Test that WikiQuery can be instantiated."""
    wiki = WikiQuery(wiki_base=wiki_structure)
    assert wiki is not None
    assert wiki.wiki_base == wiki_structure


def test_can_instantiate_metadata_index(wiki_structure):
    """Test that MetadataIndex can be instantiated."""
    index_dir = wiki_structure / "index"
    index = MetadataIndex(index_dir=index_dir)
    assert index is not None


def test_can_instantiate_fulltext_index(wiki_structure):
    """Test that FulltextIndex can be instantiated."""
    index_dir = wiki_structure / "index"
    index = FulltextIndex(index_dir=index_dir)
    assert index is not None


def test_can_instantiate_governance_components(wiki_structure):
    """Test that governance components can be instantiated."""
    linter = MetadataLinter()
    staleness = StalenessDetector()
    quality = QualityScorer()

    assert linter is not None
    assert staleness is not None
    assert quality is not None


def test_can_instantiate_jobs(wiki_structure):
    """Test that daemon jobs can be instantiated."""
    index_job = IndexRebuildJob(wiki_base=wiki_structure)
    gov_job = GovernanceJob(wiki_base=wiki_structure)
    export_job = ExportJob(wiki_base=wiki_structure)

    assert index_job is not None
    assert gov_job is not None
    assert export_job is not None


def test_wiki_query_on_empty_wiki(wiki_structure):
    """Test that WikiQuery works on empty wiki."""
    wiki = WikiQuery(wiki_base=wiki_structure)

    # Should not crash on empty wiki
    results = wiki.find_by_domain("general")
    assert results is not None

    results = wiki.find_by_tag("nonexistent")
    assert results is not None

    page = wiki.get_page("nonexistent")
    assert page is None


def test_can_create_and_read_simple_page(wiki_structure):
    """Test creating and reading a simple page."""
    # Create a simple page
    tech_pages = wiki_structure / "domains" / "tech" / "pages"
    page_file = tech_pages / "test.md"

    content = """---
id: test
title: Test Page
domain: tech
---

# Test Page

This is a test.
"""
    page_file.write_text(content)

    # Try to query it
    wiki = WikiQuery(wiki_base=wiki_structure)

    # This might not work without indexing, but shouldn't crash
    _ = wiki.get_page("test")
    # Whether it finds the page or not, it shouldn't raise an exception


def test_metadata_index_basic_operations(wiki_structure):
    """Test basic metadata index operations."""
    index_dir = wiki_structure / "index"
    index = MetadataIndex(index_dir=index_dir)

    # Test empty operations
    pages = index.find_by_domain("tech")
    assert pages is not None  # Should return empty set, not crash

    # Test save/load on empty index
    index.save()
    assert (index_dir / "metadata.json").exists()

    # Reload
    new_index = MetadataIndex(index_dir=index_dir)
    new_index.load()
    assert new_index.pages is not None


def test_fulltext_index_basic_operations(wiki_structure):
    """Test basic fulltext index operations."""
    index_dir = wiki_structure / "index"
    index = FulltextIndex(index_dir=index_dir)

    # Test search on empty index
    results = index.search("test query")
    assert results is not None  # Should return empty list, not crash

    # Test save/load
    index.save()
    assert (index_dir / "fulltext.json").exists()

    # Reload
    new_index = FulltextIndex(index_dir=index_dir)
    new_index.load()
    assert new_index.inverted_index is not None


def test_linter_on_empty_wiki(wiki_structure):
    """Test linter on empty wiki."""
    linter = MetadataLinter()

    # Should handle empty wiki gracefully
    issues = linter.lint_all(wiki_structure)
    assert issues is not None
    assert isinstance(issues, list)


def test_system_components_integration(wiki_structure):
    """Test that major system components can work together."""
    # Create indexes
    metadata_index = MetadataIndex(index_dir=wiki_structure / "index")
    fulltext_index = FulltextIndex(index_dir=wiki_structure / "index")

    # Create query interface
    wiki = WikiQuery(wiki_base=wiki_structure)

    # Create governance components
    linter = MetadataLinter()
    staleness = StalenessDetector()
    quality = QualityScorer()

    # All should be instantiated without errors
    assert all(
        [
            metadata_index,
            fulltext_index,
            wiki,
            linter,
            staleness,
            quality,
        ]
    )
