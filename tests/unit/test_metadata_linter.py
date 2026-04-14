"""Tests for metadata linter."""

from pathlib import Path

import pytest

from llm_wiki.governance.linter import LintIssue, LintSeverity, MetadataLinter
from llm_wiki.index.metadata import MetadataIndex


class TestMetadataLinter:
    """Tests for MetadataLinter."""

    @pytest.fixture
    def linter(self) -> MetadataLinter:
        """Create metadata linter."""
        return MetadataLinter()

    def test_lint_file_valid(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting a valid file."""
        test_file = temp_dir / "valid.md"
        test_file.write_text(
            """---
id: test-page
title: Test Page
domain: general
kind: page
summary: A test page
tags:
  - test
---

Content
"""
        )

        issues = linter.lint_file(test_file)

        # Should have no errors or warnings, maybe info about recommended fields
        errors = [i for i in issues if i.severity == LintSeverity.ERROR]
        assert len(errors) == 0

    def test_lint_file_missing_required_fields(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting file missing required fields."""
        test_file = temp_dir / "missing.md"
        test_file.write_text(
            """---
title: Missing Fields
---

Content
"""
        )

        issues = linter.lint_file(test_file)

        # Should have errors for missing id and domain
        errors = [i for i in issues if i.severity == LintSeverity.ERROR]
        assert len(errors) >= 2

        error_fields = {i.field for i in errors}
        assert "id" in error_fields
        assert "domain" in error_fields

    def test_lint_file_invalid_kind(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting file with invalid kind."""
        test_file = temp_dir / "invalid_kind.md"
        test_file.write_text(
            """---
id: test
title: Test
domain: general
kind: invalid_kind
---

Content
"""
        )

        issues = linter.lint_file(test_file)

        # Should have error for invalid kind
        kind_errors = [i for i in issues if i.severity == LintSeverity.ERROR and i.field == "kind"]
        assert len(kind_errors) == 1
        assert "invalid kind" in kind_errors[0].message.lower()

    def test_lint_file_invalid_tags_type(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting file with invalid tags type."""
        test_file = temp_dir / "invalid_tags.md"
        test_file.write_text(
            """---
id: test
title: Test
domain: general
tags: not-a-list
---

Content
"""
        )

        issues = linter.lint_file(test_file)

        # Should have error(s) for invalid tags type
        tag_errors = [i for i in issues if i.severity == LintSeverity.ERROR and i.field == "tags"]
        assert len(tag_errors) >= 1

    def test_lint_file_too_many_tags(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting file with too many tags."""
        tags = "\n".join(f"  - tag{i}" for i in range(15))
        test_file = temp_dir / "many_tags.md"
        test_file.write_text(
            f"""---
id: test
title: Test
domain: general
tags:
{tags}
---

Content
"""
        )

        issues = linter.lint_file(test_file)

        # Should have warning for too many tags
        tag_warnings = [
            i
            for i in issues
            if i.severity == LintSeverity.WARNING and "too many tags" in i.message.lower()
        ]
        assert len(tag_warnings) == 1

    def test_lint_file_missing_summary(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting file without summary."""
        test_file = temp_dir / "no_summary.md"
        test_file.write_text(
            """---
id: test
title: Test
domain: general
---

Content
"""
        )

        issues = linter.lint_file(test_file)

        # Should have info about missing summary
        summary_info = [
            i for i in issues if i.severity == LintSeverity.INFO and i.field == "summary"
        ]
        assert len(summary_info) == 1

    def test_lint_file_entity_missing_source(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting entity without source citation."""
        test_file = temp_dir / "entity.md"
        test_file.write_text(
            """---
id: python
title: Python
domain: tech
kind: entity
---

Content
"""
        )

        issues = linter.lint_file(test_file)

        # Should have warning for missing source
        source_warnings = [
            i for i in issues if i.severity == LintSeverity.WARNING and i.field == "source"
        ]
        assert len(source_warnings) == 1

    def test_lint_file_invalid_field_types(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting file with invalid field types."""
        test_file = temp_dir / "invalid_types.md"
        test_file.write_text(
            """---
id: test
title: 123
domain: general
entities: not-a-list
---

Content
"""
        )

        issues = linter.lint_file(test_file)

        # Should have errors for invalid types
        type_errors = [i for i in issues if i.severity == LintSeverity.ERROR and "type" in i.rule]
        assert len(type_errors) >= 1

    def test_lint_file_parse_error(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting file with parse error."""
        test_file = temp_dir / "invalid.md"
        test_file.write_text(
            """---
invalid: yaml: syntax:
---

Content
"""
        )

        issues = linter.lint_file(test_file)

        # Should have parse error
        parse_errors = [i for i in issues if i.rule == "parse_error"]
        assert len(parse_errors) == 1

    def test_detect_orphans(self, temp_dir: Path):
        """Test orphan page detection."""
        # Create metadata index
        index = MetadataIndex(index_dir=temp_dir / "index")

        # Add pages
        index.add_page("page1", {"id": "page1", "title": "Page 1", "related_pages": ["page2"]})
        index.add_page("page2", {"id": "page2", "title": "Page 2"})
        index.add_page("page3", {"id": "page3", "title": "Page 3", "related_pages": []})

        linter = MetadataLinter(metadata_index=index)
        orphans = linter.detect_orphans()

        # page1 and page3 are orphans (no incoming links)
        # page2 is linked from page1
        assert "page2" not in orphans
        assert "page1" in orphans
        assert "page3" in orphans

    def test_detect_orphans_no_index(self, linter: MetadataLinter):
        """Test orphan detection without index."""
        with pytest.raises(ValueError, match="metadata_index required"):
            linter.detect_orphans()

    def test_lint_domain(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting all pages in a domain."""
        # Create domain structure
        domain_dir = temp_dir / "general"
        pages_dir = domain_dir / "pages"
        pages_dir.mkdir(parents=True)

        # Create test pages
        page1 = pages_dir / "page1.md"
        page1.write_text("---\nid: page1\ntitle: Page 1\ndomain: general\n---\nContent")

        page2 = pages_dir / "page2.md"
        page2.write_text("---\ntitle: Missing ID\n---\nContent")  # Missing id, domain

        issues = linter.lint_domain(domain_dir)

        # Should have issues from page2
        assert len(issues) > 0
        error_pages = {i.page_id for i in issues if i.severity == LintSeverity.ERROR}
        assert "Missing ID" in error_pages or "page2" in error_pages

    def test_lint_domain_missing_dir(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting domain with missing pages directory."""
        domain_dir = temp_dir / "empty"
        domain_dir.mkdir()

        issues = linter.lint_domain(domain_dir)

        # Should return empty list
        assert issues == []

    def test_lint_all(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting all pages in wiki."""
        # Create wiki structure
        wiki_base = temp_dir / "wiki"
        general_pages = wiki_base / "domains" / "general" / "pages"
        general_pages.mkdir(parents=True)

        tech_pages = wiki_base / "domains" / "tech" / "pages"
        tech_pages.mkdir(parents=True)

        # Create test pages
        (general_pages / "page1.md").write_text(
            "---\nid: page1\ntitle: Page 1\ndomain: general\n---\nContent"
        )
        (tech_pages / "page2.md").write_text("---\ntitle: Missing Fields\n---\nContent")

        issues = linter.lint_all(wiki_base)

        # Should have issues from page2
        assert len(issues) > 0
        error_pages = {i.page_id for i in issues if i.severity == LintSeverity.ERROR}
        assert len(error_pages) > 0

    def test_lint_all_missing_domains(self, linter: MetadataLinter, temp_dir: Path):
        """Test linting wiki with missing domains directory."""
        wiki_base = temp_dir / "empty_wiki"

        issues = linter.lint_all(wiki_base)

        # Should return empty list
        assert issues == []

    def test_lint_issue_dataclass(self):
        """Test LintIssue dataclass."""
        issue = LintIssue(
            page_id="test",
            severity=LintSeverity.ERROR,
            rule="test_rule",
            message="Test message",
            field="test_field",
        )

        assert issue.page_id == "test"
        assert issue.severity == LintSeverity.ERROR
        assert issue.rule == "test_rule"
        assert issue.message == "Test message"
        assert issue.field == "test_field"
