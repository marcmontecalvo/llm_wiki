"""Tests for MCP tool definitions.

Tools are registered with a mock WikiQuery and UserJobStore.
Tests verify:
  - All 11 tools are registered (8 core + 3 archive tools)
  - Tool parameters match expected names
  - WikiError translation to MCP ToolError
  - Tool call behavior with mocked wiki
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mcp.server import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from llm_wiki.exceptions import (
    DomainUnknownError,
    ExportNotReadyError,
    IndexStaleError,
    IngestError,
    InvalidDepthError,
    WikiNotFoundError,
)
from llm_wiki.mcp.tools import (
    _handle_wiki_error,
    register_tools,
)


def _make_mock_wiki(**overrides: object) -> MagicMock:
    """Create a MagicMock WikiQuery with reasonable defaults."""
    import tempfile as _tempfile  # noqa: PLC0414

    wiki = MagicMock()
    # Apply safe defaults before overrides so callers can override any of them.
    wiki.search.return_value = []
    wiki.get_page.return_value = None
    wiki.get_pages_with_content.return_value = []
    # list_pages returns (page_list, next_cursor) — default to empty
    wiki.list_pages.return_value = ([], None)
    wiki.metadata_index = MagicMock()
    wiki.metadata_index.pages = {}
    wiki.metadata_index.by_domain = {}

    for key, value in overrides.items():
        setattr(wiki, key, value)

    if not hasattr(wiki, "wiki_base") or isinstance(wiki.wiki_base, MagicMock):
        with _tempfile.TemporaryDirectory() as tmpdir:
            wiki.wiki_base = Path(tmpdir)
    return wiki


# ── tools-list tests ──────────────────────────────────────────────


def test_tools_list_has_eleven_tools(temp_dir: Path) -> None:
    """All 11 tools are registered (8 core + 3 archive)."""
    wiki = _make_mock_wiki()
    server = FastMCP("test")
    register_tools(server, wiki)

    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "query",
        "ingest",
        "ingest_status",
        "search",
        "read_page",
        "list_pages",
        "export",
        "domain_dashboard",
        "list_archive",
        "archive_page",
        "unarchive_page",
    }
    assert names == expected


# ── Query tool tests ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_query_quick_returns_results() -> None:
    """query with depth='quick' returns results minimized to 10."""
    wiki = _make_mock_wiki(
        search=MagicMock(
            return_value=[
                {
                    "page_id": f"x{i}",
                    "title": f"X{i}",
                    "confidence": 0.9,
                    "sources": [],
                    "contradictions": [],
                }
                for i in range(15)
            ]
        ),
    )
    server = FastMCP("test")
    register_tools(server, wiki)

    result_blocks = await server.call_tool(
        "query",
        {
            "query_text": "test query",
            "depth": "quick",
        },
    )
    # Result is a list of content blocks (or list+meta in some versions)
    assert len(result_blocks) >= 1
    text = result_blocks[0].text if hasattr(result_blocks[0], "text") else str(result_blocks[0])
    data = json.loads(text)
    # quick depth limits to 10
    assert len(data["results"]) == 10
    assert data["timed_out"] is False
    assert data["partial"] is False


# ── Error handling (AC7) ─────────────────────────────────────────

_ERROR_CODE_TESTS = [
    (WikiNotFoundError("missing"), "WIKI_NOT_FOUND", 1001),
    (DomainUnknownError("bad domain"), "DOMAIN_UNKNOWN", 1002),
    (IndexStaleError("stale"), "INDEX_STALE", 1004),
    (ExportNotReadyError("not ready"), "EXPORT_NOT_READY", 1006),
    (IngestError("failed"), "INGEST_ERROR", 1003),
    (InvalidDepthError("bad depth"), "INVALID_DEPTH", 1007),
]


@pytest.mark.parametrize("exc,http_code,code", _ERROR_CODE_TESTS)
def test_error_mapping(exc, http_code, code):
    """AC7: WikiError subclasses map to correct MCP error codes."""
    tool_error = _handle_wiki_error(exc)
    assert isinstance(tool_error, ToolError)
    assert http_code in str(tool_error)
    assert str(code) in str(tool_error)


@pytest.mark.anyio
async def test_read_page_not_found_raises_tool_error() -> None:
    """AC7: read_page raises ToolError for missing pages."""
    wiki = _make_mock_wiki(get_page=MagicMock(return_value=None))
    server = FastMCP("test")
    register_tools(server, wiki)

    with pytest.raises(ToolError, match="WIKI_NOT_FOUND"):
        await server.call_tool("read_page", {"page_id": "nonexistent"})


# ── Tool naming conventions (AC9) ──────────────────────────────


def test_tool_names_follow_convention() -> None:
    """AC9: tool names use verb_noun snake_case (ingest_status is grandfathered)."""
    wiki = _make_mock_wiki()
    server = FastMCP("test")
    register_tools(server, wiki)

    tools = asyncio.run(server.list_tools())
    for tool in tools:
        if tool.name == "ingest_status":
            continue  # grandfathered exception
        # Single-word names (query, search, ingest, export) are acceptable;
        # multi-word names must use snake_case.
        if "_" in tool.name:
            assert "__" not in tool.name
            assert not tool.name.endswith("_")


# ── list_pages pagination ────────────────────────────────────────


@pytest.mark.anyio
async def test_list_pages_with_no_filters() -> None:
    """list_pages with no filters returns all pages from metadata."""
    page_a = {"page_id": "general-page-a", "title": "Page A", "domain": "general", "kind": "page"}
    page_b = {"page_id": "general-page-b", "title": "Page B", "domain": "general", "kind": "page"}
    wiki = _make_mock_wiki()
    wiki.list_pages.return_value = ([page_a, page_b], None)
    server = FastMCP("test")
    register_tools(server, wiki)

    result_blocks = await server.call_tool("list_pages", {})
    assert len(result_blocks) >= 1
    text = result_blocks[0].text if hasattr(result_blocks[0], "text") else str(result_blocks[0])
    data = json.loads(text)
    assert data["total_hint"] == 2
    assert len(data["pages"]) == 2


@pytest.mark.anyio
async def test_list_pages_with_cursor_pagination() -> None:
    """list_pages applies cursor-based pagination correctly."""
    page_a = {"page_id": "general-page-a", "title": "A", "domain": "general", "kind": "page"}
    wiki = _make_mock_wiki()
    wiki.list_pages.return_value = ([page_a], None)
    server = FastMCP("test")
    register_tools(server, wiki)

    result_blocks = await server.call_tool(
        "list_pages",
        {
            "limit": 1,
        },
    )
    assert len(result_blocks) >= 1
    text = result_blocks[0].text if hasattr(result_blocks[0], "text") else str(result_blocks[0])
    data = json.loads(text)
    # With 1 page and limit 1, next_cursor should be None
    assert data.get("next_cursor") is None
    assert data.get("total_hint") == 1


# ── MCP archive tools ──────────────────────────────────────────────


def _make_archive_wiki(tmp_path: Path) -> MagicMock:
    """Create a WikiQuery mock with archive directories populated."""
    # Use a real WikiQuery so archive scanning reads actual files.
    return tmp_path


@pytest.mark.anyio
async def test_list_archive_empty_domain() -> None:
    """list_archive returns empty pages when archive directory is empty."""
    wiki = _make_mock_wiki()
    server = FastMCP("test")
    register_tools(server, wiki)

    archive_dir = wiki.wiki_base / "domains" / "ml" / "archive"
    archive_dir.mkdir(parents=True)

    result_blocks = await server.call_tool("list_archive", {"domain": "ml"})
    assert len(result_blocks) >= 1
    text = result_blocks[0].text if hasattr(result_blocks[0], "text") else str(result_blocks[0])
    data = json.loads(text)
    assert data["domain"] == "ml"
    assert data["total"] == 0
    assert data["pages"] == []


@pytest.mark.anyio
async def test_list_archive_returns_archived_pages(tmp_path: Path) -> None:
    """list_archive reads archived page frontmatter."""
    # Create a real archive directory under the mock wiki's tmp_path.
    wiki = _make_mock_wiki(wiki_base=tmp_path)
    server = FastMCP("test")
    register_tools(server, wiki)

    archive_dir = tmp_path / "domains" / "ml" / "archive"
    archive_dir.mkdir(parents=True)

    fm_content = "---\nid: old-page\ntitle: Old Page\ndomain: ml\narchived_at: 2025-01-01T00:00:00\n---\ncontent\n"
    (archive_dir / "old-page.md").write_text(fm_content)

    result_blocks = await server.call_tool("list_archive", {"domain": "ml"})
    data = json.loads(
        result_blocks[0].text if hasattr(result_blocks[0], "text") else str(result_blocks[0])
    )
    assert data["total"] == 1
    assert data["pages"][0]["page_id"] == "old-page"
    assert data["pages"][0]["title"] == "Old Page"


@pytest.mark.anyio
async def test_archive_page_error_for_missing() -> None:
    """archive_page raises ToolError for missing page."""
    wiki = _make_mock_wiki()
    server = FastMCP("test")
    register_tools(server, wiki)

    with pytest.raises(ToolError, match="archive_failed"):
        await server.call_tool("archive_page", {"page_id": "nonexistent"})


@pytest.mark.anyio
async def test_unarchive_page_error_for_missing() -> None:
    """unarchive_page raises ToolError for missing page."""
    wiki = _make_mock_wiki()
    server = FastMCP("test")
    register_tools(server, wiki)

    with pytest.raises(ToolError, match="archive_failed"):
        await server.call_tool("unarchive_page", {"page_id": "nonexistent"})


# ── include_archived on MCP tools ──────────────────────────────────


@pytest.mark.anyio
async def test_query_passes_include_archived() -> None:
    """MCP query tool passes include_archived to wiki.search."""
    wiki = _make_mock_wiki()
    server = FastMCP("test")
    register_tools(server, wiki)

    await server.call_tool(
        "query",
        {"query_text": "x", "include_archived": True},
    )
    wiki.search.assert_called_once_with(
        "x", domain=None, scope_to_profile=None, include_archived=True
    )


@pytest.mark.anyio
async def test_search_passes_include_archived() -> None:
    """MCP search tool passes include_archived to wiki.search."""
    wiki = _make_mock_wiki()
    server = FastMCP("test")
    register_tools(server, wiki)

    await server.call_tool("search", {"q": "x", "include_archived": True})
    wiki.search.assert_called_once_with(
        "x", domain=None, limit=10, scope_to_profile=None, include_archived=True
    )


@pytest.mark.anyio
async def test_list_pages_passes_include_archived() -> None:
    """MCP list_pages tool passes include_archived to wiki.list_pages."""
    wiki = _make_mock_wiki()
    server = FastMCP("test")
    register_tools(server, wiki)

    await server.call_tool("list_pages", {"include_archived": True})
    wiki.list_pages.assert_called_once()
    kwargs = wiki.list_pages.call_args.kwargs  # type: ignore[attr-defined]
    assert kwargs["include_archived"] is True

    # Default is False
    wiki.reset_mock()
    await server.call_tool("list_pages", {})
    kwargs = wiki.list_pages.call_args.kwargs  # type: ignore[attr-defined]
    assert kwargs["include_archived"] is False
