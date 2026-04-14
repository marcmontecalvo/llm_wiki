"""
Tests for CLI commands.
"""

import pytest
from click.testing import CliRunner

from llm_wiki.cli import main


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def wiki_setup(tmp_path):
    """Set up a minimal wiki structure for testing."""
    wiki_base = tmp_path / "wiki_system"
    (wiki_base / "domains" / "general" / "pages").mkdir(parents=True)
    (wiki_base / "domains" / "tech" / "pages").mkdir(parents=True)
    (wiki_base / "inbox").mkdir(parents=True)
    (wiki_base / "index").mkdir(parents=True)
    (wiki_base / "exports").mkdir(parents=True)
    (wiki_base / "reports").mkdir(parents=True)
    return wiki_base


def test_cli_help(runner):
    """Test main CLI help."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Federated LLM wiki system" in result.output
    assert "search" in result.output
    assert "ingest" in result.output
    assert "govern" in result.output
    assert "export" in result.output


def test_cli_version(runner):
    """Test version command."""
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower()


def test_search_help(runner):
    """Test search command help."""
    result = runner.invoke(main, ["search", "--help"])
    assert result.exit_code == 0
    assert "Search and query" in result.output


def test_search_query_help(runner):
    """Test search query subcommand help."""
    result = runner.invoke(main, ["search", "query", "--help"])
    assert result.exit_code == 0
    assert "--domain" in result.output
    assert "--kind" in result.output
    assert "--tags" in result.output


def test_search_get_help(runner):
    """Test search get subcommand help."""
    result = runner.invoke(main, ["search", "get", "--help"])
    assert result.exit_code == 0
    assert "Get a specific page" in result.output


def test_ingest_help(runner):
    """Test ingest command help."""
    result = runner.invoke(main, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "Ingest content" in result.output


def test_ingest_text_help(runner):
    """Test ingest text subcommand help."""
    result = runner.invoke(main, ["ingest", "text", "--help"])
    assert result.exit_code == 0
    assert "--title" in result.output
    assert "--domain" in result.output


def test_ingest_text_creates_file(runner, wiki_setup):
    """Test that ingest text creates a file in inbox."""
    result = runner.invoke(
        main,
        [
            "ingest",
            "text",
            "Test content",
            "--title",
            "Test Page",
            "--domain",
            "general",
            "--wiki-base",
            str(wiki_setup),
        ],
    )

    assert result.exit_code == 0
    assert "Page created" in result.output

    # Verify file was created
    inbox_files = list((wiki_setup / "inbox").glob("*.md"))
    assert len(inbox_files) == 1
    assert inbox_files[0].name == "test-page.md"

    # Verify content
    content = inbox_files[0].read_text()
    assert "title: Test Page" in content
    assert "domain: general" in content
    assert "Test content" in content


def test_govern_help(runner):
    """Test govern command help."""
    result = runner.invoke(main, ["govern", "--help"])
    assert result.exit_code == 0
    assert "governance checks" in result.output


def test_govern_check_help(runner):
    """Test govern check subcommand help."""
    result = runner.invoke(main, ["govern", "check", "--help"])
    assert result.exit_code == 0
    assert "Run governance checks" in result.output


def test_govern_rebuild_index_help(runner):
    """Test govern rebuild-index subcommand help."""
    result = runner.invoke(main, ["govern", "rebuild-index", "--help"])
    assert result.exit_code == 0
    assert "Rebuild search indexes" in result.output


def test_export_help(runner):
    """Test export command help."""
    result = runner.invoke(main, ["export", "--help"])
    assert result.exit_code == 0
    assert "Export wiki content" in result.output


def test_export_all_help(runner):
    """Test export all subcommand help."""
    result = runner.invoke(main, ["export", "all", "--help"])
    assert result.exit_code == 0
    assert "Export all formats" in result.output


def test_export_llmstxt_help(runner):
    """Test export llmstxt subcommand help."""
    result = runner.invoke(main, ["export", "llmstxt", "--help"])
    assert result.exit_code == 0
    assert "llms.txt format" in result.output


def test_export_graph_help(runner):
    """Test export graph subcommand help."""
    result = runner.invoke(main, ["export", "graph", "--help"])
    assert result.exit_code == 0
    assert "graph of page relationships" in result.output


def test_init_help(runner):
    """Test init command help."""
    result = runner.invoke(main, ["init", "--help"])
    assert result.exit_code == 0
    assert "Initialize" in result.output


def test_search_query_no_results(runner, wiki_setup):
    """Test search query with no results."""
    result = runner.invoke(
        main,
        [
            "search",
            "query",
            "--domain",
            "tech",
            "--wiki-base",
            str(wiki_setup),
        ],
    )

    assert result.exit_code == 0
    assert "No results found" in result.output


def test_search_get_not_found(runner, wiki_setup):
    """Test search get for non-existent page."""
    result = runner.invoke(
        main,
        [
            "search",
            "get",
            "nonexistent-page",
            "--wiki-base",
            str(wiki_setup),
        ],
    )

    assert result.exit_code == 1
    assert "not found" in result.output


def test_ingest_file_help(runner):
    """Test ingest file subcommand help."""
    result = runner.invoke(main, ["ingest", "file", "--help"])
    assert result.exit_code == 0
    assert "Ingest a file" in result.output


def test_ingest_file_copies_to_inbox(runner, wiki_setup, tmp_path):
    """Test that ingest file copies file to inbox."""
    # Create a test file
    test_file = tmp_path / "test.md"
    test_file.write_text("# Test\n\nTest content")

    result = runner.invoke(
        main,
        [
            "ingest",
            "file",
            str(test_file),
            "--wiki-base",
            str(wiki_setup),
        ],
    )

    assert result.exit_code == 0
    assert "File copied to inbox" in result.output

    # Verify file was copied
    inbox_file = wiki_setup / "inbox" / "test.md"
    assert inbox_file.exists()
    assert "Test content" in inbox_file.read_text()
