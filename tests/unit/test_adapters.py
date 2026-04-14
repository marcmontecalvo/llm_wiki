"""Tests for source adapters."""

from pathlib import Path

from llm_wiki.adapters.base import AdapterRegistry, SourceAdapter
from llm_wiki.adapters.markdown import MarkdownAdapter
from llm_wiki.adapters.text import TextAdapter


class TestMarkdownAdapter:
    """Tests for MarkdownAdapter."""

    def test_can_parse_md_file(self):
        """Test can_parse recognizes .md files."""
        assert MarkdownAdapter.can_parse(Path("test.md"))
        assert MarkdownAdapter.can_parse(Path("document.MD"))
        assert MarkdownAdapter.can_parse(Path("README.markdown"))

    def test_can_parse_rejects_other_files(self):
        """Test can_parse rejects non-markdown files."""
        assert not MarkdownAdapter.can_parse(Path("test.txt"))
        assert not MarkdownAdapter.can_parse(Path("document.pdf"))
        assert not MarkdownAdapter.can_parse(Path("file.html"))

    def test_extract_metadata_simple(self, temp_dir: Path):
        """Test extracting metadata from simple markdown."""
        adapter = MarkdownAdapter()
        filepath = temp_dir / "test.md"
        content = "# Hello World\n\nThis is content."

        metadata = adapter.extract_metadata(filepath, content)

        assert metadata["source_type"] == "markdown"
        assert metadata["source_path"] == str(filepath)
        assert metadata["title"] == "Test"  # From filename

    def test_extract_metadata_with_frontmatter(self, temp_dir: Path):
        """Test extracting metadata from markdown with frontmatter."""
        adapter = MarkdownAdapter()
        filepath = temp_dir / "test.md"
        content = """---
title: Custom Title
author: John Doe
tags:
  - test
  - example
---

# Hello World

Content here."""

        metadata = adapter.extract_metadata(filepath, content)

        assert metadata["title"] == "Custom Title"
        assert metadata["author"] == "John Doe"
        assert metadata["tags"] == ["test", "example"]
        assert metadata["source_type"] == "markdown"

    def test_extract_metadata_title_from_filename(self, temp_dir: Path):
        """Test title generation from filename."""
        adapter = MarkdownAdapter()

        # Hyphenated filename
        filepath = temp_dir / "my-test-document.md"
        metadata = adapter.extract_metadata(filepath, "# Content")
        assert metadata["title"] == "My Test Document"

        # Underscored filename
        filepath = temp_dir / "another_test_file.md"
        metadata = adapter.extract_metadata(filepath, "# Content")
        assert metadata["title"] == "Another Test File"

    def test_normalize_to_markdown_no_frontmatter(self, temp_dir: Path):
        """Test normalizing markdown without frontmatter."""
        adapter = MarkdownAdapter()
        filepath = temp_dir / "test.md"
        content = "# Hello\n\nThis is content.\n\n## Section"

        result = adapter.normalize_to_markdown(filepath, content)

        assert result == content.strip()

    def test_normalize_to_markdown_strips_frontmatter(self, temp_dir: Path):
        """Test normalizing markdown strips frontmatter."""
        adapter = MarkdownAdapter()
        filepath = temp_dir / "test.md"
        content = """---
title: Test
---

# Hello

Content here."""

        result = adapter.normalize_to_markdown(filepath, content)

        # Should only have body, no frontmatter
        assert "# Hello" in result
        assert "Content here." in result
        assert "title: Test" not in result
        assert "---" not in result

    def test_process_full_workflow(self, temp_dir: Path):
        """Test complete processing workflow."""
        adapter = MarkdownAdapter()
        filepath = temp_dir / "test-document.md"
        filepath.write_text("""---
author: Test Author
---

# Document Title

This is the content.
""")

        metadata, markdown = adapter.process(filepath)

        # Check metadata
        assert metadata["author"] == "Test Author"
        assert metadata["source_type"] == "markdown"

        # Check markdown
        assert "# Document Title" in markdown
        assert "This is the content." in markdown
        assert "author:" not in markdown  # Frontmatter stripped


class TestAdapterRegistry:
    """Tests for AdapterRegistry."""

    def test_register_adapter(self):
        """Test registering an adapter."""
        registry = AdapterRegistry()

        registry.register(MarkdownAdapter)

        assert MarkdownAdapter in registry.get_all_adapters()

    def test_get_adapter_for_markdown(self, temp_dir: Path):
        """Test getting adapter for markdown file."""
        registry = AdapterRegistry()
        registry.register(MarkdownAdapter)

        adapter = registry.get_adapter(temp_dir / "test.md")

        assert isinstance(adapter, MarkdownAdapter)

    def test_get_adapter_no_match(self, temp_dir: Path):
        """Test getting adapter when no adapter matches."""
        registry = AdapterRegistry()
        registry.register(MarkdownAdapter)

        adapter = registry.get_adapter(temp_dir / "test.pdf")

        assert adapter is None

    def test_get_all_adapters(self):
        """Test getting all registered adapters."""
        registry = AdapterRegistry()

        registry.register(MarkdownAdapter)

        adapters = registry.get_all_adapters()

        assert len(adapters) == 1
        assert MarkdownAdapter in adapters

    def test_multiple_adapters(self, temp_dir: Path):
        """Test registry with multiple adapters."""

        # Create a dummy adapter for testing
        class TextAdapter(SourceAdapter):
            @classmethod
            def can_parse(cls, filepath: Path) -> bool:
                return filepath.suffix == ".txt"

            def extract_metadata(self, filepath: Path, content: str) -> dict:
                return {}

            def normalize_to_markdown(self, filepath: Path, content: str) -> str:
                return content

        registry = AdapterRegistry()
        registry.register(MarkdownAdapter)
        registry.register(TextAdapter)

        # Should match markdown
        md_adapter = registry.get_adapter(temp_dir / "test.md")
        assert isinstance(md_adapter, MarkdownAdapter)

        # Should match text
        txt_adapter = registry.get_adapter(temp_dir / "test.txt")
        assert isinstance(txt_adapter, TextAdapter)

        # Should have both
        assert len(registry.get_all_adapters()) == 2


class TestTextAdapter:
    """Tests for TextAdapter."""

    def test_can_parse_txt_file(self):
        """Test can_parse recognizes .txt files."""
        assert TextAdapter.can_parse(Path("test.txt"))
        assert TextAdapter.can_parse(Path("document.TXT"))

    def test_can_parse_rejects_other_files(self):
        """Test can_parse rejects non-text files."""
        assert not TextAdapter.can_parse(Path("test.md"))
        assert not TextAdapter.can_parse(Path("document.pdf"))
        assert not TextAdapter.can_parse(Path("file.html"))

    def test_extract_metadata_from_first_line(self, temp_dir: Path):
        """Test extracting title from first line."""
        adapter = TextAdapter()
        filepath = temp_dir / "test.txt"
        content = """My Great Title
This is the body content.
It has multiple lines."""

        metadata = adapter.extract_metadata(filepath, content)

        assert metadata["title"] == "My Great Title"
        assert metadata["source_type"] == "text"
        assert metadata["source_path"] == str(filepath)

    def test_extract_metadata_from_filename(self, temp_dir: Path):
        """Test falling back to filename for title."""
        adapter = TextAdapter()
        filepath = temp_dir / "my-document-name.txt"
        # First line looks like body text (ends with period)
        content = """This is a sentence that looks like body content.
More content here."""

        metadata = adapter.extract_metadata(filepath, content)

        assert metadata["title"] == "My Document Name"

    def test_extract_metadata_empty_file(self, temp_dir: Path):
        """Test extracting metadata from empty file."""
        adapter = TextAdapter()
        filepath = temp_dir / "empty-file.txt"
        content = ""

        metadata = adapter.extract_metadata(filepath, content)

        assert metadata["title"] == "Empty File"
        assert metadata["source_type"] == "text"

    def test_normalize_with_title_first_line(self, temp_dir: Path):
        """Test normalizing text with title in first line."""
        adapter = TextAdapter()
        filepath = temp_dir / "test.txt"
        content = """Document Title
This is the content.
More content here."""

        result = adapter.normalize_to_markdown(filepath, content)

        assert result.startswith("# Document Title")
        assert "This is the content." in result
        assert "More content here." in result

    def test_normalize_without_title_first_line(self, temp_dir: Path):
        """Test normalizing text when first line is not a title."""
        adapter = TextAdapter()
        filepath = temp_dir / "my-test.txt"
        content = """This is the first sentence of content.
And here is more."""

        result = adapter.normalize_to_markdown(filepath, content)

        # Should use filename as title
        assert result.startswith("# My Test")
        # Should include all content
        assert "This is the first sentence of content." in result
        assert "And here is more." in result

    def test_normalize_empty_file(self, temp_dir: Path):
        """Test normalizing empty file."""
        adapter = TextAdapter()
        filepath = temp_dir / "empty.txt"
        content = ""

        result = adapter.normalize_to_markdown(filepath, content)

        # Empty file still gets a title from filename
        assert result.startswith("# Empty")

    def test_process_full_workflow(self, temp_dir: Path):
        """Test complete processing workflow."""
        adapter = TextAdapter()
        filepath = temp_dir / "my-notes.txt"
        filepath.write_text("""My Notes
These are my notes.
They have multiple lines.
And paragraphs.""")

        metadata, markdown = adapter.process(filepath)

        # Check metadata
        assert metadata["title"] == "My Notes"
        assert metadata["source_type"] == "text"

        # Check markdown
        assert markdown.startswith("# My Notes")
        assert "These are my notes." in markdown
        assert "They have multiple lines." in markdown
