"""Integration tests for llms-full.txt export functionality."""

from pathlib import Path

import pytest

from llm_wiki.export.llmsfull import LLMSFullExporter


class TestLLMSFullExportIntegration:
    """Integration tests for complete llms-full.txt export workflow."""

    @pytest.fixture
    def wiki_structure(self, temp_dir: Path) -> Path:
        """Create a realistic wiki structure with multiple domains and pages."""
        wiki_base = temp_dir / "wiki"
        index_dir = wiki_base / "index"
        index_dir.mkdir(parents=True)

        # Create domains: tech, science, personal
        domains = {
            "tech": [
                {
                    "id": "python",
                    "title": "Python",
                    "kind": "entity",
                    "entity_type": "Programming Language",
                    "confidence": 0.95,
                    "tags": ["programming", "interpreted"],
                },
                {
                    "id": "django",
                    "title": "Django",
                    "kind": "entity",
                    "entity_type": "Web Framework",
                    "confidence": 0.90,
                    "tags": ["web", "framework"],
                    "links": ["python"],
                },
            ],
            "science": [
                {
                    "id": "quantum-mechanics",
                    "title": "Quantum Mechanics",
                    "kind": "concept",
                    "confidence": 0.88,
                    "tags": ["physics", "quantum"],
                },
                {
                    "id": "photon",
                    "title": "Photon",
                    "kind": "entity",
                    "entity_type": "Particle",
                    "confidence": 0.92,
                    "tags": ["physics", "particle"],
                    "links": ["quantum-mechanics"],
                },
            ],
            "personal": [
                {
                    "id": "learning-goals",
                    "title": "Learning Goals",
                    "kind": "page",
                    "confidence": 0.75,
                    "tags": ["personal"],
                },
            ],
        }

        import json

        for domain_name, pages in domains.items():
            pages_dir = wiki_base / "domains" / domain_name / "pages"
            pages_dir.mkdir(parents=True)

            for page in pages:
                page_id = page["id"]
                page_content = f"""---
id: {page_id}
title: {page["title"]}
domain: {domain_name}
kind: {page["kind"]}
confidence: {page["confidence"]}
status: published
created_at: 2024-01-01T00:00:00
updated_at: 2024-02-01T00:00:00
tags: {json.dumps(page.get("tags", []))}
links: {json.dumps(page.get("links", []))}
summary: A comprehensive summary of {page["title"]}
"""
                if page["kind"] == "entity":
                    page_content += f"entity_type: {page['entity_type']}\n"

                page_content += f"""---

## Overview

This is the {page["title"]} page. It contains comprehensive information about {page["title"]}.

## Key Points

- Point 1 about {page["title"]}
- Point 2 about {page["title"]}
- Point 3 about {page["title"]}

## Further Reading

See related pages for more information.
"""

                (pages_dir / f"{page_id}.md").write_text(page_content)

        # Create a backlink index
        # Note: forward_links = links FROM this page TO others
        #       backlinks = links FROM other pages TO this page
        backlinks_data = {
            "python": {"forward_links": [], "backlinks": ["django"], "broken_links": []},
            "django": {"forward_links": ["python"], "backlinks": [], "broken_links": []},
            "quantum-mechanics": {"forward_links": [], "backlinks": ["photon"], "broken_links": []},
            "photon": {
                "forward_links": ["quantum-mechanics"],
                "backlinks": [],
                "broken_links": [],
            },
            "learning-goals": {"forward_links": [], "backlinks": [], "broken_links": []},
        }

        (index_dir / "backlinks.json").write_text(json.dumps(backlinks_data))

        return wiki_base

    def test_export_all_domains_comprehensive(self, wiki_structure: Path):
        """Test exporting all domains produces comprehensive output."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        output = exporter.export_all()

        assert output.exists()
        content = output.read_text()

        # Check domain headers
        assert "# Domain: personal" in content
        assert "# Domain: science" in content
        assert "# Domain: tech" in content

        # Check page headers
        assert "# Python" in content
        assert "# Django" in content
        assert "# Quantum Mechanics" in content

        # Check metadata sections
        assert "<!-- Metadata -->" in content
        assert "- id: python" in content
        assert "- domain: tech" in content
        assert "- entity_type: Programming Language" in content

        # Check summary sections
        assert "<!-- Summary -->" in content
        assert "> A comprehensive summary" in content

        # Check content sections
        assert "<!-- Content -->" in content
        assert "Overview" in content

        # Check links sections
        assert "<!-- Links -->" in content
        assert "[[python]]" in content
        assert "[[django]]" in content

    def test_export_with_quality_filter(self, wiki_structure: Path):
        """Test quality-based filtering works correctly."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        # Export with high quality threshold
        output = exporter.export_all(min_quality=0.90)

        content = output.read_text()

        # Should include pages with confidence >= 0.90
        assert "# Python" in content  # 0.95
        assert "# Django" in content  # 0.90
        assert "# Photon" in content  # 0.92

        # Should exclude pages with confidence < 0.90
        assert "# Learning Goals" not in content  # 0.75
        assert "# Quantum Mechanics" not in content  # 0.88

    def test_export_with_page_limit(self, wiki_structure: Path):
        """Test maximum page limit works correctly."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        # Export with limit of 2 pages
        output = exporter.export_all(max_pages=2)

        content = output.read_text()

        # Count page title headings (lines starting with "# " but not "## ")
        lines = content.split("\n")
        page_headings = [
            line for line in lines if line.startswith("# ") and not line.startswith("## ")
        ]

        # Should have exactly 2 pages (the limit) or fewer
        # Filter out domain headings which start with "# Domain:"
        page_titles = [h for h in page_headings if not h.startswith("# Domain:")]
        assert len(page_titles) <= 2
        assert len(page_titles) > 0

    def test_export_single_domain(self, wiki_structure: Path):
        """Test exporting a single domain."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        output = exporter.export_domain("tech")

        assert output.exists()
        content = output.read_text()

        # Should only contain tech pages
        assert "# Python" in content
        assert "# Django" in content

        # Should not contain other domains
        assert "# Quantum Mechanics" not in content
        assert "# Learning Goals" not in content

    def test_export_domain_with_filters(self, wiki_structure: Path):
        """Test domain export with filtering options."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        # Export tech domain with quality >= 0.91
        output = exporter.export_domain("tech", min_quality=0.91)

        content = output.read_text()

        # Should include Python (0.95)
        assert "# Python" in content

        # Should not include Django (0.90)
        assert "# Django" not in content

    def test_export_stats(self, wiki_structure: Path):
        """Test export statistics are accurate."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        stats = exporter.get_export_stats()

        assert stats["total_pages"] == 5  # 2 + 2 + 1
        assert stats["total_domains"] == 3  # tech, science, personal
        assert (
            stats["pages_with_backlinks"] == 2
        )  # python (from django), quantum-mechanics (from photon)

    def test_export_preserves_page_order(self, wiki_structure: Path):
        """Test that pages are exported in sorted order."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        output = exporter.export_domain("tech")

        content = output.read_text()

        # Find positions of pages
        django_pos = content.find("# Django")
        python_pos = content.find("# Python")

        # Pages should appear in alphabetical order
        assert django_pos < python_pos

    def test_export_all_creates_single_file(self, wiki_structure: Path):
        """Test that export_all creates a single consolidated file."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        output = exporter.export_all()

        assert output.name == "llms-full.txt"
        assert output.parent.name == "exports"

        # File should contain all pages
        content = output.read_text()
        page_count = content.count("# Domain:")
        assert page_count >= 1

    def test_export_format_is_lvm_parseable(self, wiki_structure: Path):
        """Test that exported format is structured for LLM parsing."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        output = exporter.export_domain("tech")

        content = output.read_text()

        # Check structured sections with HTML comments
        assert "<!-- Metadata -->" in content
        assert "<!-- Summary -->" in content
        assert "<!-- Content -->" in content
        assert "<!-- Links -->" in content

        # Check consistent formatting
        assert content.count("<!-- Metadata -->") == 2  # 2 pages in tech
        assert content.count("---") >= 2  # Page separators

    def test_export_handles_missing_optional_fields(self, wiki_structure: Path):
        """Test export handles pages with missing optional fields."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        # Export page without optional fields
        pages_dir = wiki_structure / "domains" / "personal" / "pages"
        minimal_page = pages_dir / "minimal.md"
        minimal_page.write_text("""---
id: minimal
title: Minimal Page
domain: personal
kind: page
---

Just some content.""")

        output = exporter.export_page(minimal_page)

        assert "# Minimal Page" in output
        assert "<!-- Metadata -->" in output
        assert "Just some content" in output

    def test_export_large_file_handling(self, wiki_structure: Path):
        """Test export handles larger wiki structures."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        output = exporter.export_all()

        # Should be a reasonable file size
        file_size = output.stat().st_size
        assert file_size > 1000  # At least 1KB

        # Should not exceed reasonable limits (less than 10MB for test data)
        assert file_size < 10 * 1024 * 1024

    def test_cli_command_integration(self, wiki_structure: Path):
        """Test that CLI integration works."""
        from click.testing import CliRunner

        from llm_wiki.cli import export_llmsfull

        runner = CliRunner()

        # Test export_all via CLI
        result = runner.invoke(
            export_llmsfull,
            ["--wiki-base", str(wiki_structure), "--min-quality", "0.8"],
        )

        assert result.exit_code == 0
        assert "Exporting all domains" in result.output
        assert "File size:" in result.output
        assert ".txt" in result.output

    def test_cli_command_domain_filter(self, wiki_structure: Path):
        """Test CLI command with domain filter."""
        from click.testing import CliRunner

        from llm_wiki.cli import export_llmsfull

        runner = CliRunner()

        # Test export with domain filter
        result = runner.invoke(
            export_llmsfull,
            ["--wiki-base", str(wiki_structure), "--domain", "tech"],
        )

        assert result.exit_code == 0
        assert "Exporting domain 'tech'" in result.output
        assert ".txt" in result.output

    def test_cli_command_with_quality_filter(self, wiki_structure: Path):
        """Test CLI command with quality filter."""
        from click.testing import CliRunner

        from llm_wiki.cli import export_llmsfull

        runner = CliRunner()

        # Test export with strict quality filter
        result = runner.invoke(
            export_llmsfull,
            [
                "--wiki-base",
                str(wiki_structure),
                "--min-quality",
                "0.95",
            ],
        )

        assert result.exit_code == 0
        # Should show reduced export
        assert "Wiki contains" in result.output

    def test_cli_command_since_filter(self, wiki_structure: Path):
        """Test CLI --since flag filters pages by date."""
        from click.testing import CliRunner

        from llm_wiki.cli import export_llmsfull

        runner = CliRunner()

        result = runner.invoke(
            export_llmsfull,
            ["--wiki-base", str(wiki_structure), "--since", "2025-01-01"],
        )

        assert result.exit_code == 0
        assert "Exporting all domains" in result.output

        # All test pages have updated_at 2024-02-01, so nothing should be exported
        output_file = wiki_structure / "exports" / "llms-full.txt"
        assert output_file.exists()
        content = output_file.read_text()
        assert "# Python" not in content

    def test_export_file_is_readable(self, wiki_structure: Path):
        """Test that exported file is valid and readable."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        output = exporter.export_all()

        # Should be readable
        content = output.read_text(encoding="utf-8")
        assert len(content) > 0

        # Should be valid markdown
        assert content.count("#") > 0  # Has headings
        assert content.count("---") > 0  # Has separators
        assert content.count("<!--") > 0  # Has comments

    def test_multiple_exports_same_output(self, wiki_structure: Path):
        """Test that multiple exports to same file overwrite correctly."""
        exporter = LLMSFullExporter(wiki_base=wiki_structure)

        output = wiki_structure / "exports" / "test.txt"

        # First export
        result1 = exporter.export_all(output_file=output, max_pages=2)
        size1 = result1.stat().st_size
        content1 = result1.read_text()

        # Second export with different filters
        result2 = exporter.export_all(output_file=output, max_pages=5)
        size2 = result2.stat().st_size
        content2 = result2.read_text()

        # Should have overwritten
        assert result1 == result2
        # Second export should be larger (more pages)
        assert size2 > size1
        assert content1 != content2
