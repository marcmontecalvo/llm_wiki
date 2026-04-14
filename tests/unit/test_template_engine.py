"""Tests for template engine."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from llm_wiki.templates.engine import TemplateEngine, TemplateError, render_page_from_template


class TestTemplateEngine:
    """Tests for TemplateEngine class."""

    def test_init_with_valid_directory(self):
        """Test initializing with valid template directory."""
        engine = TemplateEngine("templates")
        assert engine.template_dir == Path("templates")

    def test_init_with_missing_directory(self, temp_dir: Path):
        """Test initializing with missing directory raises error."""
        nonexistent = temp_dir / "nonexistent"
        with pytest.raises(TemplateError, match="does not exist"):
            TemplateEngine(nonexistent)

    def test_load_template(self):
        """Test loading existing template."""
        engine = TemplateEngine("templates")
        template = engine._load_template("page.md")

        assert "id: PLACEHOLDER" in template
        assert "title: PLACEHOLDER" in template
        assert "# PLACEHOLDER" in template

    def test_load_missing_template(self):
        """Test loading missing template raises error."""
        engine = TemplateEngine("templates")

        with pytest.raises(TemplateError, match="not found"):
            engine._load_template("nonexistent.md")

    def test_substitute_placeholders(self):
        """Test placeholder substitution."""
        engine = TemplateEngine("templates")
        template = """---
id: PLACEHOLDER
title: PLACEHOLDER
domain: PLACEHOLDER
---

# PLACEHOLDER
"""
        data = {
            "id": "test-page",
            "title": "Test Page",
            "domain": "general",
        }

        result = engine._substitute_placeholders(template, data)

        assert "id: test-page" in result
        assert "title: Test Page" in result
        assert "domain: general" in result
        assert "# Test Page" in result
        assert "PLACEHOLDER" not in result

    def test_render_template(self):
        """Test rendering a template."""
        engine = TemplateEngine("templates")

        result = engine.render(
            "page.md",
            id="test",
            title="Test",
            domain="general",
        )

        assert "id: test" in result
        assert "title: Test" in result

    def test_render_page_minimal(self):
        """Test rendering page with minimal data."""
        engine = TemplateEngine("templates")

        result = engine.render_page(
            kind="page",
            id="test-page",
            title="Test Page",
            domain="general",
        )

        # Should have frontmatter
        assert result.startswith("---\n")
        assert "id: test-page" in result
        assert "kind: page" in result
        assert "title: Test Page" in result

    def test_render_page_with_datetime(self):
        """Test rendering page with datetime."""
        engine = TemplateEngine("templates")
        now = datetime.now(UTC)

        result = engine.render_page(
            kind="page",
            id="test",
            title="Test",
            domain="general",
            updated_at=now,
        )

        assert "id: test" in result
        # updated_at should be in ISO format
        assert now.isoformat()[:19] in result  # Check date/time part

    def test_render_page_adds_default_updated_at(self):
        """Test rendering adds updated_at if not provided."""
        engine = TemplateEngine("templates")

        result = engine.render_page(
            kind="page",
            id="test",
            title="Test",
            domain="general",
        )

        # Should have updated_at added automatically
        assert "updated_at:" in result
        assert "2026" in result  # Current year

    def test_render_entity_page(self):
        """Test rendering entity page."""
        engine = TemplateEngine("templates")

        result = engine.render_page(
            kind="entity",
            id="test-entity",
            title="Test Entity",
            domain="general",
            entity_type="organization",
        )

        assert "kind: entity" in result
        assert "entity_type: organization" in result

    def test_render_concept_page(self):
        """Test rendering concept page."""
        engine = TemplateEngine("templates")

        result = engine.render_page(
            kind="concept",
            id="test-concept",
            title="Test Concept",
            domain="general",
        )

        assert "kind: concept" in result

    def test_render_source_page(self):
        """Test rendering source page."""
        engine = TemplateEngine("templates")
        now = datetime.now(UTC)

        result = engine.render_page(
            kind="source",
            id="test-source",
            title="Test Source",
            domain="general",
            source_type="markdown",
            source_path="/path/to/source.md",
            ingested_at=now,
        )

        assert "kind: source" in result
        assert "source_type: markdown" in result
        assert "source_path: /path/to/source.md" in result

    def test_render_page_invalid_kind(self):
        """Test rendering with invalid kind raises error."""
        engine = TemplateEngine("templates")

        with pytest.raises(TemplateError, match="Failed to create frontmatter"):
            engine.render_page(
                kind="invalid",
                id="test",
                title="Test",
                domain="general",
            )

    def test_render_page_missing_required_field(self):
        """Test rendering without required fields raises error."""
        engine = TemplateEngine("templates")

        with pytest.raises(TemplateError, match="Failed to create frontmatter"):
            engine.render_page(
                kind="page",
                id="test",
                # Missing title
                domain="general",
            )


class TestRenderPageFromTemplate:
    """Tests for render_page_from_template convenience function."""

    def test_render_page_from_template(self):
        """Test convenience function renders page."""
        result = render_page_from_template(
            kind="page",
            id="test",
            title="Test",
            domain="general",
        )

        assert "id: test" in result
        assert "kind: page" in result

    def test_render_with_custom_template_dir(self, temp_dir: Path):
        """Test rendering with custom template directory."""
        custom_templates = temp_dir / "custom_templates"
        custom_templates.mkdir()

        # Create a simple template
        (custom_templates / "page.md").write_text(
            """---
id: PLACEHOLDER
kind: PLACEHOLDER
title: PLACEHOLDER
domain: PLACEHOLDER
updated_at: PLACEHOLDER
---

# PLACEHOLDER
"""
        )

        result = render_page_from_template(
            kind="page",
            template_dir=custom_templates,
            id="test",
            title="Test",
            domain="general",
        )

        assert "id: test" in result
