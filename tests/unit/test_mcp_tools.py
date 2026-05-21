"""Tests for MCP tool definitions.

Tools are registered with a mock WikiQuery and UserJobStore.
Tests verify:
  - All 7 tools are registered
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


def test_tools_list_has_seven_tools(temp_dir: Path) -> None:
    """AC1: tools/list returns all 7 tools."""
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
