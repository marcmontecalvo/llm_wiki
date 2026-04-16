"""Unit tests for ObsidianVaultAdapter."""

import pytest

from llm_wiki.adapters.obsidian import ObsidianVaultAdapter


@pytest.fixture
def obsidian_adapter():
    """Create an ObsidianVaultAdapter instance."""
    return ObsidianVaultAdapter()


@pytest.fixture
def temp_md_file(tmp_path):
    """Create a temporary markdown file."""
    return tmp_path / "test.md"


class TestCanParse:
    """Tests for can_parse method."""

    def test_can_parse_md_file(self, obsidian_adapter, temp_md_file):
        """Should return True for .md files."""
        temp_md_file.write_text("# Test")
        assert obsidian_adapter.can_parse(temp_md_file) is True

    def test_cannot_parse_other_files(self, obsidian_adapter, tmp_path):
        """Should return False for non-markdown files."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("test")
        assert obsidian_adapter.can_parse(txt_file) is False


class TestExtractMetadata:
    """Tests for extract_metadata method."""

    def test_extract_basic_metadata(self, obsidian_adapter, temp_md_file):
        """Should extract basic metadata from file."""
        content = "# My Test Page\n\nThis is a test."
        temp_md_file.write_text(content)

        metadata = obsidian_adapter.extract_metadata(temp_md_file, content)

        assert metadata["source_type"] == "obsidian"
        assert metadata["page_id"] == "test"
        assert metadata["title"] == "Test"

    def test_extract_wikilinks(self, obsidian_adapter, temp_md_file):
        """Should extract wikilinks from content."""
        content = "# Test\nLinks to [[page-one]] and [[page-two|display]]."
        temp_md_file.write_text(content)

        metadata = obsidian_adapter.extract_metadata(temp_md_file, content)

        assert "wikilinks" in metadata
        assert "page-one" in metadata["wikilinks"]

    def test_extract_embedded(self, obsidian_adapter, temp_md_file):
        """Should extract embedded files from content."""
        content = "# Test\n![[embedded-page]]"
        temp_md_file.write_text(content)

        metadata = obsidian_adapter.extract_metadata(temp_md_file, content)

        assert "embedded" in metadata
        assert "embedded-page" in metadata["embedded"]

    def test_extract_hashtags(self, obsidian_adapter, temp_md_file):
        """Should extract hashtags from content."""
        content = "# Test\nThis has #tag1 and #another in it."
        temp_md_file.write_text(content)

        metadata = obsidian_adapter.extract_metadata(temp_md_file, content)

        assert "tags" in metadata
        assert "tag1" in metadata["tags"]


class TestNormalizeToMarkdown:
    """Tests for normalize_to_markdown method."""

    def test_strip_frontmatter(self, obsidian_adapter, temp_md_file):
        """Should strip frontmatter from content."""
        content = "---\ntitle: Test\n---\n# Body"
        temp_md_file.write_text(content)

        result = obsidian_adapter.normalize_to_markdown(temp_md_file, content)

        assert "---" not in result

    def test_convert_embedded(self, obsidian_adapter, temp_md_file):
        """Should convert embedded files to wikilinks."""
        content = "# Test\n![[embed]]"
        temp_md_file.write_text(content)

        result = obsidian_adapter.normalize_to_markdown(temp_md_file, content)

        assert "[[embed]]" in result
        assert "![[" not in result


class TestProcess:
    """Tests for full process method."""

    def test_process_simple(self, obsidian_adapter, temp_md_file):
        """Should process a simple Obsidian file."""
        content = "# Test Page\nContent with [[link]]."
        temp_md_file.write_text(content)

        metadata, markdown = obsidian_adapter.process(temp_md_file)

        assert metadata["source_type"] == "obsidian"
        assert "link" in markdown