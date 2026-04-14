"""Example tests to verify pytest setup."""

from pathlib import Path


def test_basic_assertion():
    """Test basic assertion."""
    assert 1 + 1 == 2


def test_temp_dir_fixture(temp_dir: Path):
    """Test temp_dir fixture."""
    assert temp_dir.exists()
    assert temp_dir.is_dir()


def test_sample_markdown_fixture(sample_markdown: str):
    """Test sample_markdown fixture."""
    assert "# Test Page" in sample_markdown
    assert "id: test-page" in sample_markdown


def test_sample_frontmatter_fixture(sample_frontmatter: dict):
    """Test sample_frontmatter fixture."""
    assert sample_frontmatter["id"] == "test-page"
    assert sample_frontmatter["kind"] == "page"
    assert sample_frontmatter["confidence"] == 0.8


def test_wiki_root_fixture(wiki_root: Path):
    """Test wiki_root fixture creates proper structure."""
    assert wiki_root.exists()
    assert (wiki_root / "domains" / "general").exists()
    assert (wiki_root / "shared" / "concepts").exists()
    assert (wiki_root / "inbox" / "new").exists()
