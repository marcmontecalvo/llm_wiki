"""Tests for frontmatter parser."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from llm_wiki.models.page import PageFrontmatter
from llm_wiki.utils.frontmatter import (
    FrontmatterError,
    extract_frontmatter_section,
    has_frontmatter,
    parse_and_validate,
    parse_frontmatter,
    read_page_file,
    write_frontmatter,
    write_page_file,
    write_with_validation,
)


class TestParseFrontmatter:
    """Tests for parse_frontmatter function."""

    def test_parse_valid_frontmatter(self):
        """Test parsing valid frontmatter."""
        content = """---
id: test-page
kind: page
title: Test Page
domain: general
updated_at: 2026-04-13T00:00:00Z
---

# Test Page

Content here.
"""
        metadata, body = parse_frontmatter(content)

        assert metadata["id"] == "test-page"
        assert metadata["kind"] == "page"
        assert metadata["title"] == "Test Page"
        assert "# Test Page" in body
        assert "Content here." in body

    def test_parse_empty_frontmatter(self):
        """Test parsing content with empty frontmatter."""
        content = """---
---

Content here.
"""
        metadata, body = parse_frontmatter(content)

        assert metadata == {}
        assert "Content here." in body

    def test_parse_no_frontmatter(self):
        """Test parsing content without frontmatter."""
        content = "# No Frontmatter\n\nJust content."

        metadata, body = parse_frontmatter(content)

        assert metadata == {}
        assert body == content

    def test_parse_invalid_yaml(self):
        """Test parsing invalid YAML raises error."""
        content = """---
invalid: yaml: {]
---
"""
        with pytest.raises(FrontmatterError, match="Failed to parse"):
            parse_frontmatter(content)


class TestParseAndValidate:
    """Tests for parse_and_validate function."""

    def test_parse_and_validate_success(self):
        """Test parsing and validating valid frontmatter."""
        now = datetime.now(UTC)
        content = f"""---
id: test-page
kind: page
title: Test Page
domain: general
updated_at: {now.isoformat()}
---

# Test Page
"""
        frontmatter_obj, body = parse_and_validate(content)

        assert isinstance(frontmatter_obj, PageFrontmatter)
        assert frontmatter_obj.id == "test-page"
        assert frontmatter_obj.kind == "page"
        assert "# Test Page" in body

    def test_parse_no_frontmatter_raises(self):
        """Test parsing content without frontmatter raises error."""
        content = "# No Frontmatter"

        with pytest.raises(FrontmatterError, match="No frontmatter found"):
            parse_and_validate(content)

    def test_parse_missing_kind_raises(self):
        """Test parsing without 'kind' field raises error."""
        content = """---
id: test
title: Test
---
"""
        with pytest.raises(FrontmatterError, match="missing required 'kind'"):
            parse_and_validate(content)

    def test_parse_invalid_schema_raises(self):
        """Test parsing with invalid schema raises error."""
        content = """---
id: ""
kind: page
title: Test
domain: general
updated_at: 2026-04-13T00:00:00Z
---
"""
        with pytest.raises(FrontmatterError, match="Invalid frontmatter"):
            parse_and_validate(content)


class TestWriteFrontmatter:
    """Tests for write_frontmatter function."""

    def test_write_simple_frontmatter(self):
        """Test writing frontmatter to markdown."""
        frontmatter_dict = {
            "id": "test",
            "kind": "page",
            "title": "Test",
        }
        body = "# Test\n\nContent here."

        result = write_frontmatter(frontmatter_dict, body)

        assert result.startswith("---\n")
        assert "id: test" in result
        assert "kind: page" in result
        assert "# Test" in result

    def test_write_preserves_body(self):
        """Test writing preserves body content exactly."""
        frontmatter_dict = {"id": "test"}
        body = "# Header\n\n- Item 1\n- Item 2"

        result = write_frontmatter(frontmatter_dict, body)

        assert "# Header" in result
        assert "- Item 1" in result
        assert "- Item 2" in result


class TestWriteWithValidation:
    """Tests for write_with_validation function."""

    def test_write_validated_frontmatter(self):
        """Test writing validated frontmatter object."""
        now = datetime.now(UTC)
        frontmatter_obj = PageFrontmatter(
            id="test",
            kind="page",
            title="Test",
            domain="general",
            updated_at=now,
        )
        body = "Content"

        result = write_with_validation(frontmatter_obj, body)

        assert "id: test" in result
        assert "kind: page" in result
        assert "Content" in result


class TestReadPageFile:
    """Tests for read_page_file function."""

    def test_read_valid_page_file(self, temp_dir: Path):
        """Test reading valid page file."""
        now = datetime.now(UTC)
        page_file = temp_dir / "test.md"
        page_file.write_text(
            f"""---
id: test
kind: page
title: Test
domain: general
updated_at: {now.isoformat()}
---

# Test
"""
        )

        frontmatter_obj, body = read_page_file(page_file)

        assert frontmatter_obj.id == "test"
        assert "# Test" in body

    def test_read_nonexistent_file_raises(self, temp_dir: Path):
        """Test reading nonexistent file raises error."""
        nonexistent = temp_dir / "nonexistent.md"

        with pytest.raises(FrontmatterError, match="does not exist"):
            read_page_file(nonexistent)

    def test_read_invalid_frontmatter_raises(self, temp_dir: Path):
        """Test reading file with invalid frontmatter raises error."""
        bad_file = temp_dir / "bad.md"
        bad_file.write_text(
            """---
id: test
---
"""
        )

        with pytest.raises(FrontmatterError, match="missing required 'kind'"):
            read_page_file(bad_file)


class TestWritePageFile:
    """Tests for write_page_file function."""

    def test_write_page_file(self, temp_dir: Path):
        """Test writing page file."""
        now = datetime.now(UTC)
        frontmatter_obj = PageFrontmatter(
            id="test",
            kind="page",
            title="Test",
            domain="general",
            updated_at=now,
        )
        body = "# Test\n\nContent"

        page_file = temp_dir / "test.md"
        write_page_file(page_file, frontmatter_obj, body)

        assert page_file.exists()
        content = page_file.read_text()
        assert "id: test" in content
        assert "# Test" in content

    def test_write_creates_parent_directory(self, temp_dir: Path):
        """Test writing creates parent directories."""
        now = datetime.now(UTC)
        frontmatter_obj = PageFrontmatter(
            id="test",
            kind="page",
            title="Test",
            domain="general",
            updated_at=now,
        )

        nested_file = temp_dir / "subdir" / "test.md"
        write_page_file(nested_file, frontmatter_obj, "Content")

        assert nested_file.exists()
        assert nested_file.parent.exists()

    def test_roundtrip(self, temp_dir: Path):
        """Test writing then reading produces same data."""
        now = datetime.now(UTC)
        original_frontmatter = PageFrontmatter(
            id="test",
            kind="page",
            title="Test Page",
            domain="general",
            status="published",
            confidence=0.95,
            sources=["source1"],
            updated_at=now,
        )
        original_body = "# Test\n\nContent here."

        page_file = temp_dir / "test.md"
        write_page_file(page_file, original_frontmatter, original_body)

        read_frontmatter, read_body = read_page_file(page_file)

        assert read_frontmatter.id == original_frontmatter.id
        assert read_frontmatter.title == original_frontmatter.title
        assert read_frontmatter.status == original_frontmatter.status
        assert read_body.strip() == original_body.strip()


class TestHasFrontmatter:
    """Tests for has_frontmatter function."""

    def test_has_frontmatter_true(self):
        """Test detecting frontmatter."""
        content = """---
id: test
---
Content
"""
        assert has_frontmatter(content)

    def test_has_frontmatter_false(self):
        """Test detecting no frontmatter."""
        content = "# Just Content\n\nNo frontmatter here."
        assert not has_frontmatter(content)

    def test_has_frontmatter_not_at_start(self):
        """Test frontmatter not at start returns False."""
        content = """Some text first

---
id: test
---
"""
        assert not has_frontmatter(content)


class TestExtractFrontmatterSection:
    """Tests for extract_frontmatter_section function."""

    def test_extract_frontmatter_section(self):
        """Test extracting frontmatter section."""
        content = """---
id: test
title: Test
---

Content
"""
        section = extract_frontmatter_section(content)

        assert section is not None
        assert "id: test" in section
        assert "title: Test" in section
        assert "---" not in section  # Delimiters not included
        assert "Content" not in section  # Body not included

    def test_extract_no_frontmatter(self):
        """Test extracting from content without frontmatter."""
        content = "Just content"

        section = extract_frontmatter_section(content)

        assert section is None
