"""
End-to-end integration tests.

Tests complete workflows from ingestion to export.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from llm_wiki.daemon.jobs.export import ExportJob
from llm_wiki.daemon.jobs.governance import GovernanceJob
from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob
from llm_wiki.query.search import WikiQuery


@pytest.fixture
def populated_wiki(tmp_path):
    """Create a wiki with sample content."""
    wiki_base = tmp_path / "wiki_system"

    # Create directory structure
    for domain in ["general", "tech"]:
        (wiki_base / "domains" / domain / "pages").mkdir(parents=True)
        (wiki_base / "domains" / domain / "queue").mkdir(parents=True)

    (wiki_base / "index").mkdir(parents=True)
    (wiki_base / "exports").mkdir(parents=True)
    (wiki_base / "reports").mkdir(parents=True)
    (wiki_base / "inbox").mkdir(parents=True)

    # Create sample pages
    now = datetime.now(UTC).isoformat()

    tech_pages = wiki_base / "domains" / "tech" / "pages"

    (tech_pages / "python.md").write_text(f"""---
id: python
title: Python Programming
domain: tech
kind: entity
tags:
  - python
  - programming
summary: Python is a high-level programming language
created: {now}
updated: {now}
source: https://python.org
---

# Python Programming

Python is a high-level, interpreted programming language.

## Features

- Easy to learn
- Large standard library
- Dynamic typing
""")

    (tech_pages / "docker.md").write_text(f"""---
id: docker
title: Docker
domain: tech
kind: entity
tags:
  - docker
  - containers
summary: Docker is a containerization platform
created: {now}
updated: {now}
---

# Docker

Docker is a platform for developing applications in containers.
""")

    general_pages = wiki_base / "domains" / "general" / "pages"

    (general_pages / "notes.md").write_text(f"""---
id: notes
title: General Notes
domain: general
kind: page
tags:
  - notes
summary: General project notes
created: {now}
updated: {now}
---

# General Notes

Various notes and ideas.
""")

    return wiki_base


def test_index_rebuild_and_search(populated_wiki):
    """Test that indexing and search work end-to-end."""
    # Rebuild indexes
    index_job = IndexRebuildJob(wiki_base=populated_wiki)
    stats = index_job.execute()

    # Verify indexes were built
    assert stats["metadata_pages"] == 3
    assert stats["fulltext_documents"] == 3

    # Test search
    wiki = WikiQuery(wiki_base=populated_wiki)

    # Search by text
    results = wiki.search(query="python")
    assert len(results) > 0
    assert any(r["id"] == "python" for r in results)

    # Search by tag
    python_pages = wiki.find_by_tag("python")
    assert any(p.get("id") == "python" for p in python_pages)

    # Search by domain
    tech_pages = wiki.find_by_domain("tech")
    assert len(tech_pages) == 2

    # Get specific page
    page = wiki.get_page("python")
    assert page is not None
    assert page["title"] == "Python Programming"


def test_governance_workflow(populated_wiki):
    """Test that governance checks work end-to-end."""
    job = GovernanceJob(wiki_base=populated_wiki)
    stats = job.execute()

    # Verify statistics
    assert stats["total_pages"] == 3
    assert "lint_issues" in stats
    assert "stale_pages" in stats
    assert "low_quality_pages" in stats

    # Verify report was created
    report_path = Path(stats["report_path"])
    assert report_path.exists()

    # Verify report content
    content = report_path.read_text()
    assert "# Wiki Governance Report" in content
    assert "## Summary" in content


def test_export_workflow(populated_wiki):
    """Test that all exports work end-to-end."""
    job = ExportJob(wiki_base=populated_wiki)
    stats = job.execute()

    # Verify all exports were created
    assert stats["llmstxt_path"] is not None
    llmstxt_path = Path(stats["llmstxt_path"])
    assert llmstxt_path.exists()

    assert stats["graph_path"] is not None
    graph_path = Path(stats["graph_path"])
    assert graph_path.exists()

    assert stats["sitemap_path"] is not None
    sitemap_path = Path(stats["sitemap_path"])
    assert sitemap_path.exists()

    # Verify llms.txt content
    llmstxt_content = llmstxt_path.read_text()
    assert "# Python Programming" in llmstxt_content
    assert "# Docker" in llmstxt_content

    # Verify sitemap structure
    sitemap_content = sitemap_path.read_text()
    assert "<?xml version=" in sitemap_content
    assert "<urlset" in sitemap_content


def test_complete_workflow(populated_wiki):
    """Test complete workflow: index → search → govern → export."""
    # Step 1: Build indexes
    index_job = IndexRebuildJob(wiki_base=populated_wiki)
    index_stats = index_job.execute()
    assert index_stats["metadata_pages"] == 3

    # Step 2: Query content
    wiki = WikiQuery(wiki_base=populated_wiki)
    results = wiki.search(query="python programming")
    assert len(results) > 0

    # Step 3: Run governance
    gov_job = GovernanceJob(wiki_base=populated_wiki)
    gov_stats = gov_job.execute()
    assert gov_stats["total_pages"] == 3

    # Step 4: Export
    export_job = ExportJob(wiki_base=populated_wiki)
    export_stats = export_job.execute()
    assert Path(export_stats["llmstxt_path"]).exists()

    # Verify all components worked together
    assert index_stats["metadata_pages"] == gov_stats["total_pages"]


def test_empty_wiki_handling(tmp_path):
    """Test that system handles empty wiki gracefully."""
    wiki_base = tmp_path / "wiki_system"

    # Create minimal structure
    (wiki_base / "domains" / "general" / "pages").mkdir(parents=True)
    (wiki_base / "index").mkdir(parents=True)
    (wiki_base / "exports").mkdir(parents=True)
    (wiki_base / "reports").mkdir(parents=True)

    # Test indexing empty wiki
    index_job = IndexRebuildJob(wiki_base=wiki_base)
    stats = index_job.execute()
    assert stats["metadata_pages"] == 0

    # Test governance on empty wiki
    gov_job = GovernanceJob(wiki_base=wiki_base)
    gov_stats = gov_job.execute()
    assert gov_stats["total_pages"] == 0

    # Test export on empty wiki
    export_job = ExportJob(wiki_base=wiki_base)
    export_stats = export_job.execute()
    assert Path(export_stats["llmstxt_path"]).exists()
