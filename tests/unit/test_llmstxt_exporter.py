"""Tests for llms.txt exporter."""

from pathlib import Path

import pytest

from llm_wiki.export.llmstxt import LLMSTxtExporter


class TestLLMSTxtExporter:
    """Tests for LLMSTxtExporter."""

    @pytest.fixture
    def exporter(self, temp_dir: Path) -> LLMSTxtExporter:
        """Create exporter."""
        return LLMSTxtExporter(wiki_base=temp_dir / "wiki")

    @pytest.fixture
    def wiki_with_pages(self, temp_dir: Path) -> Path:
        """Create wiki with test pages."""
        wiki_base = temp_dir / "wiki"
        pages_dir = wiki_base / "domains" / "general" / "pages"
        pages_dir.mkdir(parents=True)

        (pages_dir / "page1.md").write_text(
            """---
id: page1
title: Test Page 1
domain: general
kind: page
tags:
  - test
  - example
summary: A test page
---

# Content

This is test content."""
        )

        (pages_dir / "page2.md").write_text(
            """---
id: page2
title: Test Page 2
domain: general
---

Simple page content."""
        )

        return wiki_base

    def test_export_page(self, exporter: LLMSTxtExporter, wiki_with_pages: Path):
        """Test exporting a single page."""
        page_file = wiki_with_pages / "domains" / "general" / "pages" / "page1.md"

        result = exporter.export_page(page_file)

        assert "# Test Page 1" in result
        assert "<!-- id: page1 -->" in result
        assert "<!-- domain: general -->" in result
        assert "<!-- tags: test, example -->" in result
        assert "> A test page" in result
        assert "This is test content" in result

    def test_export_page_minimal(self, exporter: LLMSTxtExporter, temp_dir: Path):
        """Test exporting page with minimal metadata."""
        pages_dir = temp_dir / "wiki" / "domains" / "test" / "pages"
        pages_dir.mkdir(parents=True)

        test_file = pages_dir / "minimal.md"
        test_file.write_text("---\ntitle: Minimal\n---\nContent")

        result = exporter.export_page(test_file)

        assert "# Minimal" in result
        assert "Content" in result

    def test_export_page_error_handling(self, exporter: LLMSTxtExporter, temp_dir: Path):
        """Test handling export errors."""
        bad_file = temp_dir / "nonexistent.md"

        result = exporter.export_page(bad_file)

        assert result == ""

    def test_export_domain(self, exporter: LLMSTxtExporter, wiki_with_pages: Path):
        """Test exporting a domain."""
        exporter.wiki_base = wiki_with_pages

        output = exporter.export_domain("general")

        assert output.exists()
        content = output.read_text()

        assert "# Test Page 1" in content
        assert "# Test Page 2" in content
        assert "---" in content  # Page separator

    def test_export_domain_missing(self, exporter: LLMSTxtExporter):
        """Test exporting nonexistent domain."""
        output = exporter.export_domain("nonexistent")

        assert not output.exists()  # Not created if no pages

    def test_export_all(self, exporter: LLMSTxtExporter, wiki_with_pages: Path):
        """Test exporting all domains."""
        exporter.wiki_base = wiki_with_pages

        output = exporter.export_all()

        assert output.exists()
        content = output.read_text()

        assert "# Domain: general" in content
        assert "# Test Page 1" in content
        assert "# Test Page 2" in content

    def test_export_all_creates_exports_dir(self, exporter: LLMSTxtExporter, wiki_with_pages: Path):
        """Test that export_all creates exports directory."""
        exporter.wiki_base = wiki_with_pages

        exporter.export_all()

        exports_dir = wiki_with_pages / "exports"
        assert exports_dir.exists()

    def test_export_domain_custom_output(
        self, exporter: LLMSTxtExporter, wiki_with_pages: Path, temp_dir: Path
    ):
        """Test exporting to custom output file."""
        exporter.wiki_base = wiki_with_pages
        custom_output = temp_dir / "custom.txt"

        result = exporter.export_domain("general", output_file=custom_output)

        assert result == custom_output
        assert custom_output.exists()
