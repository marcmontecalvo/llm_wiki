"""Tests for llms-full.txt exporter."""

from pathlib import Path

import pytest

from llm_wiki.export.llmsfull import LLMSFullExporter
from llm_wiki.models.extraction import (
    ClaimExtraction,
    ConceptExtraction,
    EntityExtraction,
    ExtractionResult,
    RelationshipExtraction,
)


class TestLLMSFullExporter:
    """Tests for LLMSFullExporter."""

    @pytest.fixture
    def exporter(self, temp_dir: Path) -> LLMSFullExporter:
        """Create exporter."""
        return LLMSFullExporter(wiki_base=temp_dir / "wiki")

    @pytest.fixture
    def wiki_with_pages(self, temp_dir: Path) -> Path:
        """Create wiki with test pages and extraction data."""
        wiki_base = temp_dir / "wiki"
        pages_dir = wiki_base / "domains" / "general" / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)

        # Create index directory
        index_dir = wiki_base / "index"
        index_dir.mkdir(parents=True, exist_ok=True)

        # Page 1 with extraction data
        (pages_dir / "python.md").write_text(
            """---
id: python
title: Python Programming Language
domain: general
kind: entity
status: published
confidence: 0.95
created_at: 2024-01-01T00:00:00
updated_at: 2024-02-01T00:00:00
entity_type: Programming Language
tags:
  - programming
  - python
  - backend
summary: Python is a high-level, interpreted programming language
sources:
  - https://python.org
links:
  - pip
  - virtualenv
---

## Overview
Python is a high-level, interpreted programming language created by Guido van Rossum.

## Features
- Dynamic typing
- Simple syntax
- Rich standard library
- Great for web development, data science, and automation

## History
Python 1.0 was released in January 2000."""
        )

        # Create extraction data for python
        extraction_data = {
            "entities": [
                {
                    "name": "Python",
                    "entity_type": "Programming Language",
                    "description": "A high-level programming language",
                    "aliases": ["Python 3", "Py"],
                    "confidence": 0.98,
                    "context": "Overview section",
                }
            ],
            "concepts": [
                {
                    "name": "Dynamic Typing",
                    "definition": "Type checking at runtime rather than compile time",
                    "category": "Type System",
                    "related_concepts": ["Static Typing"],
                    "confidence": 0.92,
                    "examples": ["x = 5; x = 'string'"],
                }
            ],
            "claims": [
                {
                    "claim": "Python is a high-level programming language",
                    "subject": "Python",
                    "predicate": "is",
                    "object": "high-level language",
                    "confidence": 0.99,
                    "source_reference": "Overview section",
                }
            ],
            "relationships": [
                {
                    "source_entity": "Python",
                    "relationship_type": "created_by",
                    "target_entity": "Guido van Rossum",
                    "confidence": 0.98,
                    "bidirectional": False,
                }
            ],
            "extraction_metadata": {},
        }

        import json

        (index_dir / "python_extraction.json").write_text(json.dumps(extraction_data))

        # Page 2 without extraction data
        (pages_dir / "django.md").write_text(
            """---
id: django
title: Django Web Framework
domain: general
kind: page
status: published
confidence: 0.85
created_at: 2024-01-15T00:00:00
updated_at: 2024-02-15T00:00:00
tags:
  - web
  - framework
  - django
summary: Django is a web framework for building web applications
links:
  - python
---

Django is a high-level web framework that encourages rapid development."""
        )

        # Create backlink index
        backlinks_data = {
            "python": {
                "forward_links": ["pip", "virtualenv"],
                "backlinks": ["django"],
                "broken_links": [],
            },
            "django": {
                "forward_links": ["python"],
                "backlinks": [],
                "broken_links": [],
            },
        }

        (index_dir / "backlinks.json").write_text(json.dumps(backlinks_data))

        return wiki_base

    def test_export_page_basic(self, exporter: LLMSFullExporter, wiki_with_pages: Path):
        """Test exporting a single page with basic metadata."""
        exporter.wiki_base = wiki_with_pages
        exporter.backlink_index.load()

        page_file = wiki_with_pages / "domains" / "general" / "pages" / "django.md"
        result = exporter.export_page(page_file)

        # Check basic structure
        assert "# Django Web Framework" in result
        assert "<!-- Metadata -->" in result
        assert "- id: django" in result
        assert "- domain: general" in result
        assert "- kind: page" in result
        assert "- confidence: 0.85" in result

        # Check summary
        assert "<!-- Summary -->" in result
        assert "> Django is a web framework" in result

        # Check content
        assert "<!-- Content -->" in result
        assert "high-level web framework" in result

        # Check links
        assert "<!-- Links -->" in result
        assert "[[python]]" in result

    def test_export_page_with_extractions(self, exporter: LLMSFullExporter, wiki_with_pages: Path):
        """Test exporting a page with extraction data."""
        exporter.wiki_base = wiki_with_pages
        exporter.backlink_index.load()

        page_file = wiki_with_pages / "domains" / "general" / "pages" / "python.md"
        result = exporter.export_page(page_file)

        # Check extracted entities
        assert "<!-- Entities -->" in result
        assert "#### Python" in result
        assert "- Type: Programming Language" in result
        assert "- Aliases: Python 3, Py" in result

        # Check extracted concepts
        assert "<!-- Concepts -->" in result
        assert "#### Dynamic Typing" in result
        assert "- Category: Type System" in result

        # Check extracted claims
        assert "<!-- Claims -->" in result
        assert "Python is a high-level programming language" in result
        assert "(99%)" in result

        # Check extracted relationships
        assert "<!-- Relationships -->" in result
        assert "Python --[created_by]--> Guido van Rossum" in result

    def test_export_page_without_extractions(
        self, exporter: LLMSFullExporter, wiki_with_pages: Path
    ):
        """Test exporting a page without extraction data."""
        exporter.wiki_base = wiki_with_pages
        exporter.backlink_index.load()

        page_file = wiki_with_pages / "domains" / "general" / "pages" / "django.md"
        result = exporter.export_page(page_file, include_extractions=True)

        # Should not have extraction sections
        assert "<!-- Entities -->" not in result
        assert "<!-- Concepts -->" not in result
        assert "<!-- Claims -->" not in result
        assert "<!-- Relationships -->" not in result

    def test_export_page_without_links(self, exporter: LLMSFullExporter, wiki_with_pages: Path):
        """Test exporting without including links."""
        exporter.wiki_base = wiki_with_pages
        exporter.backlink_index.load()

        page_file = wiki_with_pages / "domains" / "general" / "pages" / "python.md"
        result = exporter.export_page(page_file, include_links=False)

        # Should not have links section
        assert "<!-- Links -->" not in result

    def test_export_domain(self, exporter: LLMSFullExporter, wiki_with_pages: Path):
        """Test exporting a domain."""
        exporter.wiki_base = wiki_with_pages

        output = exporter.export_domain("general")

        assert output.exists()
        content = output.read_text()

        # Check both pages are included
        assert "# Python Programming Language" in content
        assert "# Django Web Framework" in content
        assert "---" in content  # Page separator

    def test_export_domain_quality_filter(self, exporter: LLMSFullExporter, wiki_with_pages: Path):
        """Test domain export with quality filtering."""
        exporter.wiki_base = wiki_with_pages

        # Only include pages with confidence >= 0.9
        output = exporter.export_domain("general", min_quality=0.9)

        content = output.read_text()

        # Should only include python (0.95)
        assert "# Python Programming Language" in content
        # django has 0.85, should be excluded
        assert "# Django Web Framework" not in content

    def test_export_domain_max_pages(self, exporter: LLMSFullExporter, wiki_with_pages: Path):
        """Test domain export with page limit."""
        exporter.wiki_base = wiki_with_pages

        # Only export 1 page
        output = exporter.export_domain("general", max_pages=1)

        content = output.read_text()

        # Should have only one page export
        separators = content.count("---")
        # Should have at least 1 separator between pages
        assert separators == 1

    def test_export_domain_custom_output(
        self, exporter: LLMSFullExporter, wiki_with_pages: Path, temp_dir: Path
    ):
        """Test exporting to custom output file."""
        exporter.wiki_base = wiki_with_pages
        custom_output = temp_dir / "custom_full.txt"

        result = exporter.export_domain("general", output_file=custom_output)

        assert result == custom_output
        assert custom_output.exists()

    def test_export_all(self, exporter: LLMSFullExporter, wiki_with_pages: Path):
        """Test exporting all domains."""
        exporter.wiki_base = wiki_with_pages

        output = exporter.export_all()

        assert output.exists()
        content = output.read_text()

        # Check domain header
        assert "# Domain: general" in content
        assert "# Python Programming Language" in content
        assert "# Django Web Framework" in content

    def test_export_all_with_filters(self, exporter: LLMSFullExporter, wiki_with_pages: Path):
        """Test export_all with quality and page limits."""
        exporter.wiki_base = wiki_with_pages

        output = exporter.export_all(min_quality=0.9, max_pages=1)

        content = output.read_text()

        # Should only have python (0.95 >= 0.9)
        assert "# Python Programming Language" in content
        assert "# Django Web Framework" not in content

    def test_export_all_creates_exports_dir(
        self, exporter: LLMSFullExporter, wiki_with_pages: Path
    ):
        """Test that export_all creates exports directory."""
        exporter.wiki_base = wiki_with_pages

        exporter.export_all()

        exports_dir = wiki_with_pages / "exports"
        assert exports_dir.exists()

    def test_get_export_stats(self, exporter: LLMSFullExporter, wiki_with_pages: Path):
        """Test getting export statistics."""
        exporter.wiki_base = wiki_with_pages

        stats = exporter.get_export_stats()

        assert stats["total_pages"] == 2
        assert stats["total_domains"] == 1
        assert stats["pages_with_extractions"] == 1
        assert stats["pages_with_backlinks"] == 1  # Only python has backlinks (from django)

    def test_export_page_error_handling(self, exporter: LLMSFullExporter, temp_dir: Path):
        """Test handling export errors."""
        bad_file = temp_dir / "nonexistent.md"

        result = exporter.export_page(bad_file)

        assert result == ""

    def test_format_metadata_section_complete(self, exporter: LLMSFullExporter):
        """Test metadata formatting with complete data."""
        metadata = {
            "id": "test-page",
            "domain": "tech",
            "kind": "entity",
            "status": "published",
            "confidence": 0.95,
            "created_at": "2024-01-01",
            "updated_at": "2024-02-01",
            "entity_type": "Concept",
            "tags": ["test", "example"],
        }

        result = exporter._format_metadata_section(metadata)

        assert "<!-- Metadata -->" in result
        assert "- id: test-page" in result
        assert "- domain: tech" in result
        assert "- confidence: 0.95" in result
        assert "- entity_type: Concept" in result
        assert "- tags: test, example" in result

    def test_format_entities_section(self, exporter: LLMSFullExporter):
        """Test entity section formatting."""
        entity = EntityExtraction(
            name="Python",
            entity_type="Programming Language",
            description="A high-level language",
            aliases=["Py", "Python3"],
            confidence=0.95,
        )

        extraction = ExtractionResult(entities=[entity])

        result = exporter._format_entities_section(extraction)

        assert result is not None
        assert "<!-- Entities -->" in result
        assert "#### Python" in result
        assert "- Type: Programming Language" in result
        assert "- Description: A high-level language" in result
        assert "- Aliases: Py, Python3" in result

    def test_format_concepts_section(self, exporter: LLMSFullExporter):
        """Test concept section formatting."""
        concept = ConceptExtraction(
            name="Type System",
            definition="System for classifying types",
            category="Programming",
            related_concepts=["Static Typing", "Dynamic Typing"],
            examples=["Python", "JavaScript"],
        )

        extraction = ExtractionResult(concepts=[concept])

        result = exporter._format_concepts_section(extraction)

        assert result is not None
        assert "<!-- Concepts -->" in result
        assert "#### Type System" in result
        assert "- Definition: System for classifying types" in result
        assert "- Category: Programming" in result

    def test_format_claims_section(self, exporter: LLMSFullExporter):
        """Test claims section formatting."""
        claim = ClaimExtraction(
            claim="Python is interpreted",
            subject="Python",
            predicate="is",
            object="interpreted",
            confidence=0.95,
            source_reference="Section 1",
            qualifiers=["in most implementations"],
        )

        extraction = ExtractionResult(claims=[claim])

        result = exporter._format_claims_section(extraction)

        assert result is not None
        assert "<!-- Claims -->" in result
        assert "Python is interpreted (95%)" in result
        assert "subject=Python" in result
        assert "qualifiers: in most implementations" in result

    def test_format_relationships_section(self, exporter: LLMSFullExporter):
        """Test relationships section formatting."""
        rel = RelationshipExtraction(
            source_entity="Python",
            relationship_type="created_by",
            target_entity="Guido van Rossum",
            confidence=0.98,
            bidirectional=False,
        )

        extraction = ExtractionResult(relationships=[rel])

        result = exporter._format_relationships_section(extraction)
        assert result is not None
        assert "<!-- Relationships -->" in result
        assert "Python --[created_by]--> Guido van Rossum (98%)" in result

    def test_format_relationships_bidirectional(self, exporter: LLMSFullExporter):
        """Test bidirectional relationship formatting."""
        rel = RelationshipExtraction(
            source_entity="A",
            relationship_type="similar_to",
            target_entity="B",
            confidence=0.8,
            bidirectional=True,
        )

        extraction = ExtractionResult(relationships=[rel])

        result = exporter._format_relationships_section(extraction)
        assert result is not None
        assert "A <--[similar_to]--> B (80%)" in result

    def test_export_page_entity_page(self, exporter: LLMSFullExporter, wiki_with_pages: Path):
        """Test exporting an entity page with entity-specific metadata."""
        exporter.wiki_base = wiki_with_pages
        exporter.backlink_index.load()

        page_file = wiki_with_pages / "domains" / "general" / "pages" / "python.md"
        result = exporter.export_page(page_file)

        # Check metadata section includes entity_type
        assert "- entity_type: Programming Language" in result
        # Aliases are in the Entities section, not Metadata (since not in frontmatter)
        assert "- Aliases: Python 3, Py" in result

    def test_format_summary_section_missing(self, exporter: LLMSFullExporter):
        """Test summary section when not present."""
        metadata = {"id": "test", "domain": "general"}

        result = exporter._format_summary_section(metadata)

        assert result is None

    def test_format_links_section_complete(self, exporter: LLMSFullExporter, wiki_with_pages: Path):
        """Test links section with all link types."""
        exporter.wiki_base = wiki_with_pages
        exporter.backlink_index.load()

        metadata = {"links": ["related-page"]}
        result = exporter._format_links_section("python", metadata)
        assert result is not None
        assert "<!-- Links -->" in result
        assert "Forward links:" in result
        assert "Backlinks:" in result
        assert "[[related-page]]" in result

    def test_export_domain_loads_backlink_index(
        self, exporter: LLMSFullExporter, wiki_with_pages: Path
    ):
        """export_domain should load the backlink index so link data is populated."""
        exporter.wiki_base = wiki_with_pages
        # Intentionally do NOT call backlink_index.load() before export_domain

        output = exporter.export_domain("general")
        content = output.read_text()

        # Django links to python; after backlink index is loaded the link section exists
        assert "<!-- Links -->" in content

    def test_export_domain_since_date_filter(
        self, exporter: LLMSFullExporter, wiki_with_pages: Path
    ):
        """export_domain should exclude pages updated before since_date."""
        exporter.wiki_base = wiki_with_pages

        # Both test pages have updated_at 2024-02-01, so since 2024-03-01 should exclude all
        output = exporter.export_domain("general", since_date="2024-03-01")
        content = output.read_text()

        assert "# Python Programming Language" not in content
        assert "# Django Web Framework" not in content

    def test_export_domain_since_date_includes_newer(
        self, exporter: LLMSFullExporter, wiki_with_pages: Path
    ):
        """export_domain since_date should include pages at or after the cutoff."""
        exporter.wiki_base = wiki_with_pages

        # Both pages updated 2024-02-01, since 2024-01-01 should include both
        output = exporter.export_domain("general", since_date="2024-01-01")
        content = output.read_text()

        assert "# Python Programming Language" in content
        assert "# Django Web Framework" in content

    def test_export_all_since_date_filter(self, exporter: LLMSFullExporter, wiki_with_pages: Path):
        """export_all should respect since_date across all domains."""
        exporter.wiki_base = wiki_with_pages

        output = exporter.export_all(since_date="2025-01-01")
        content = output.read_text()

        assert "# Python Programming Language" not in content
        assert "# Django Web Framework" not in content


class TestLLMSFullExporterIntegration:
    """Integration tests for LLMSFullExporter."""

    @pytest.fixture
    def full_wiki(self, temp_dir: Path) -> Path:
        """Create a more complete wiki structure."""
        wiki_base = temp_dir / "wiki"

        # Create multiple domains
        for domain_name in ["tech", "science"]:
            pages_dir = wiki_base / "domains" / domain_name / "pages"
            pages_dir.mkdir(parents=True)

            for i in range(3):
                page_id = f"{domain_name}-page-{i}"
                (pages_dir / f"{page_id}.md").write_text(
                    f"""---
id: {page_id}
title: {domain_name.title()} Page {i}
domain: {domain_name}
kind: page
confidence: {0.8 + i * 0.05}
---

Content for page {i} in {domain_name}."""
                )

        return wiki_base

    def test_export_all_full_wiki(self, full_wiki: Path):
        """Test exporting a multi-domain wiki."""
        exporter = LLMSFullExporter(wiki_base=full_wiki)

        output = exporter.export_all()

        assert output.exists()
        content = output.read_text()

        # Check all domains are present
        assert "# Domain: science" in content
        assert "# Domain: tech" in content

        # Check some pages
        assert "Science Page 0" in content
        assert "Tech Page 1" in content

    def test_export_all_with_strict_quality_filter(self, full_wiki: Path):
        """Test export with strict quality filter."""
        exporter = LLMSFullExporter(wiki_base=full_wiki)

        # Only include pages with confidence >= 0.9
        output = exporter.export_all(min_quality=0.9)

        content = output.read_text()

        # Pages with confidence 0.8 and 0.85 should be excluded
        # Only pages with 0.9+ should be included (Page 2 in each domain)
        assert "Page 2" in content
        assert "Page 0" not in content or "Page 0" not in content.split("# Domain")[1]

    def test_export_file_size(self, full_wiki: Path):
        """Test that exported file is created with reasonable size."""
        exporter = LLMSFullExporter(wiki_base=full_wiki)

        output = exporter.export_all()

        assert output.exists()
        file_size = output.stat().st_size
        # Should have some reasonable content (at least 500 bytes)
        assert file_size > 500
