"""Tests for page enrichment."""

from pathlib import Path

import pytest

from llm_wiki.extraction.enrichment import PageEnricher


class TestPageEnricher:
    """Tests for PageEnricher."""

    @pytest.fixture
    def enricher(self) -> PageEnricher:
        """Create page enricher."""
        return PageEnricher()

    def test_enrich_page_basic(self, enricher: PageEnricher, temp_dir: Path):
        """Test basic page enrichment."""
        # Create test page
        test_file = temp_dir / "test.md"
        test_file.write_text(
            """---
title: Test Page
domain: general
---

# Test Content

This is the content.
"""
        )

        # Extracted metadata
        extracted = {
            "kind": "page",
            "summary": "A test page",
            "tags": ["test", "example"],
        }

        # Enrich
        result = enricher.enrich_page(test_file, extracted)

        # Read result
        content = result.read_text()

        # Should have enriched metadata
        assert "kind: page" in content
        assert "summary: A test page" in content
        assert "tags:" in content
        assert "- test" in content
        assert "status: enriched" in content

        # Body should be preserved
        assert "# Test Content" in content

    def test_enrich_page_with_entities(self, enricher: PageEnricher, temp_dir: Path):
        """Test enrichment with entities."""
        test_file = temp_dir / "test.md"
        test_file.write_text("---\ntitle: Test\n---\nContent")

        extracted = {"kind": "entity"}
        entities = [{"name": "Python", "type": "technology", "description": "Language"}]

        result = enricher.enrich_page(test_file, extracted, entities=entities)
        content = result.read_text()

        # Should have entities in frontmatter
        assert "entities:" in content
        assert "Python" in content

    def test_enrich_page_with_concepts(self, enricher: PageEnricher, temp_dir: Path):
        """Test enrichment with concepts."""
        test_file = temp_dir / "test.md"
        test_file.write_text("---\ntitle: Test\n---\nContent")

        extracted = {"kind": "concept"}
        concepts = [{"name": "Microservices", "description": "Architectural pattern"}]

        result = enricher.enrich_page(test_file, extracted, concepts=concepts)
        content = result.read_text()

        # Should have concepts in frontmatter
        assert "concepts:" in content
        assert "Microservices" in content

    def test_enrich_page_merges_tags(self, enricher: PageEnricher, temp_dir: Path):
        """Test that tags are merged, not replaced."""
        test_file = temp_dir / "test.md"
        test_file.write_text(
            """---
title: Test
tags:
  - existing
  - old
---
Content"""
        )

        extracted = {"tags": ["new", "extracted", "existing"]}

        result = enricher.enrich_page(test_file, extracted)
        content = result.read_text()

        # Should have all unique tags
        assert "- existing" in content
        assert "- old" in content
        assert "- new" in content
        assert "- extracted" in content

    def test_enrich_page_preserves_existing_fields(self, enricher: PageEnricher, temp_dir: Path):
        """Test that existing fields are preserved."""
        test_file = temp_dir / "test.md"
        test_file.write_text(
            """---
title: Original Title
kind: entity
summary: Original summary
author: John Doe
---
Content"""
        )

        extracted = {
            "kind": "concept",  # Should not override
            "summary": "New summary",  # Should not override
            "tags": ["new"],
        }

        result = enricher.enrich_page(test_file, extracted)
        content = result.read_text()

        # Existing fields should be preserved
        assert "title: Original Title" in content
        assert "kind: entity" in content  # Not changed
        assert "summary: Original summary" in content  # Not changed
        assert "author: John Doe" in content

    def test_enrich_page_limits_tags(self, enricher: PageEnricher, temp_dir: Path):
        """Test that tags are limited to 10."""
        test_file = temp_dir / "test.md"
        test_file.write_text("---\ntitle: Test\n---\nContent")

        # More than 10 tags
        extracted = {"tags": [f"tag{i}" for i in range(15)]}

        result = enricher.enrich_page(test_file, extracted)
        content = result.read_text()

        # Count tags
        tag_lines = [line for line in content.split("\n") if line.strip().startswith("- tag")]
        assert len(tag_lines) <= 10
