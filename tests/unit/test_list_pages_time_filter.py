"""Tests for Story 1.14: list_pages updated_since time filter.

Covers:
  - WikiQuery.list_pages() service-layer filter (AC 1, 3)
  - GET /v1/pages?updated_since=... REST endpoint (AC 1, 2)
  - list_pages MCP tool updated_since parameter (AC 3)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_wiki.api.routers.pages import router as pages_router
from llm_wiki.deps import get_wiki
from llm_wiki.mcp.tools import register_tools
from llm_wiki.query.search import WikiQuery

# ── Service-layer fixtures ────────────────────────────────────────────────────


@pytest.fixture
def wiki_with_pages(temp_dir: Path) -> WikiQuery:
    """WikiQuery with three pages having different updated_at timestamps."""
    wiki = WikiQuery(wiki_base=temp_dir / "wiki")
    wiki.add_page(
        "old-page",
        "Old Page",
        "content",
        {"id": "old-page", "title": "Old Page", "updated_at": "2025-01-01T00:00:00Z"},
    )
    wiki.add_page(
        "recent-page",
        "Recent Page",
        "content",
        {"id": "recent-page", "title": "Recent Page", "updated_at": "2026-03-01T00:00:00Z"},
    )
    wiki.add_page(
        "no-date-page",
        "No Date Page",
        "content",
        {"id": "no-date-page", "title": "No Date Page"},
    )
    return wiki


# ── Service-layer tests ───────────────────────────────────────────────────────


def test_list_pages_no_filter_returns_all(wiki_with_pages: WikiQuery) -> None:
    pages, _ = wiki_with_pages.list_pages()
    assert len(pages) == 3


def test_list_pages_updated_since_filters_correctly(wiki_with_pages: WikiQuery) -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    pages, _ = wiki_with_pages.list_pages(updated_since=cutoff)
    page_ids = {p.get("id", p.get("page_id")) for p in pages}
    assert "recent-page" in page_ids
    assert "old-page" not in page_ids
    assert "no-date-page" not in page_ids


def test_list_pages_future_cutoff_returns_empty(wiki_with_pages: WikiQuery) -> None:
    future = datetime(2099, 1, 1, tzinfo=UTC)
    pages, _ = wiki_with_pages.list_pages(updated_since=future)
    assert pages == []


def test_list_pages_no_updated_since_none_regression(wiki_with_pages: WikiQuery) -> None:
    """Omitting updated_since returns all pages (backward compat)."""
    pages, _ = wiki_with_pages.list_pages(updated_since=None)
    assert len(pages) == 3


def test_list_pages_pages_without_updated_at_excluded_when_filter_set(
    wiki_with_pages: WikiQuery,
) -> None:
    """Pages lacking updated_at are excluded when a filter is active."""
    cutoff = datetime(2000, 1, 1, tzinfo=UTC)
    pages, _ = wiki_with_pages.list_pages(updated_since=cutoff)
    page_ids = {p.get("id", p.get("page_id")) for p in pages}
    assert "no-date-page" not in page_ids


def test_list_pages_z_and_offset_formats_treated_equal(temp_dir: Path) -> None:
    """'2026-05-01T00:00:00Z' and '2026-05-01T00:00:00+00:00' are identical instants."""
    wiki = WikiQuery(wiki_base=temp_dir / "wiki2")
    wiki.add_page(
        "p1",
        "P1",
        "c",
        {"id": "p1", "updated_at": "2026-06-01T00:00:00Z"},
    )

    cutoff_z = datetime.fromisoformat("2026-05-01T00:00:00Z")
    cutoff_plus = datetime.fromisoformat("2026-05-01T00:00:00+00:00")
    pages_z, _ = wiki.list_pages(updated_since=cutoff_z)
    pages_plus, _ = wiki.list_pages(updated_since=cutoff_plus)
    assert len(pages_z) == len(pages_plus) == 1


# ── REST-endpoint fixtures ────────────────────────────────────────────────────


def _make_test_app(wiki: WikiQuery) -> FastAPI:
    app = FastAPI()
    app.include_router(pages_router)
    app.dependency_overrides[get_wiki] = lambda: wiki
    return app


@pytest.fixture
def test_client(temp_dir: Path) -> TestClient:
    """Test client backed by an empty WikiQuery."""
    wiki = WikiQuery(wiki_base=temp_dir / "wiki_empty")
    return TestClient(_make_test_app(wiki))


@pytest.fixture
def test_client_with_pages(temp_dir: Path) -> TestClient:
    """Test client backed by a WikiQuery with pages at known timestamps."""
    wiki = WikiQuery(wiki_base=temp_dir / "wiki_rest")
    wiki.add_page(
        "old-page",
        "Old Page",
        "content",
        {"id": "old-page", "title": "Old Page", "updated_at": "2025-06-01T00:00:00Z"},
    )
    wiki.add_page(
        "new-page",
        "New Page",
        "content",
        {"id": "new-page", "title": "New Page", "updated_at": "2026-06-01T00:00:00Z"},
    )
    return TestClient(_make_test_app(wiki))


# ── REST-endpoint tests ───────────────────────────────────────────────────────


def test_rest_422_on_invalid_date(test_client: TestClient) -> None:
    response = test_client.get("/v1/pages?updated_since=not-a-date")
    assert response.status_code == 422


def test_rest_200_without_filter(test_client_with_pages: TestClient) -> None:
    response = test_client_with_pages.get("/v1/pages")
    assert response.status_code == 200


def test_rest_filters_pages(test_client_with_pages: TestClient) -> None:
    response = test_client_with_pages.get("/v1/pages?updated_since=2026-01-01T00:00:00Z")
    assert response.status_code == 200
    page_ids = [p["page_id"] for p in response.json()["pages"]]
    assert "new-page" in page_ids
    assert "old-page" not in page_ids


def test_rest_filters_pages_utc_offset_form(test_client_with_pages: TestClient) -> None:
    """+00:00 suffix form is also a valid ISO8601 datetime."""
    response = test_client_with_pages.get("/v1/pages?updated_since=2026-01-01T00:00:00%2B00:00")
    assert response.status_code == 200
    page_ids = [p["page_id"] for p in response.json()["pages"]]
    assert "new-page" in page_ids
    assert "old-page" not in page_ids


def test_rest_future_cutoff_returns_empty(test_client_with_pages: TestClient) -> None:
    response = test_client_with_pages.get("/v1/pages?updated_since=2099-01-01T00:00:00Z")
    assert response.status_code == 200
    assert response.json()["pages"] == []


# ── MCP tool tests ────────────────────────────────────────────────────────────


def _make_mock_server_and_wiki(
    wiki: WikiQuery,
) -> tuple[object, dict[str, object]]:
    """Register MCP tools and return (server, tools_dict)."""
    from mcp.server import FastMCP

    server = FastMCP("test")
    register_tools(server, wiki)
    tools = {t.name: t for t in server._tool_manager._tools.values()}
    return server, tools


@pytest.fixture
def wiki_for_mcp(temp_dir: Path) -> WikiQuery:
    wiki = WikiQuery(wiki_base=temp_dir / "wiki_mcp")
    wiki.add_page(
        "mcp-old",
        "MCP Old",
        "c",
        {"id": "mcp-old", "title": "MCP Old", "updated_at": "2025-01-01T00:00:00Z"},
    )
    wiki.add_page(
        "mcp-new",
        "MCP New",
        "c",
        {"id": "mcp-new", "title": "MCP New", "updated_at": "2026-06-01T00:00:00Z"},
    )
    return wiki


def test_mcp_list_pages_no_filter(wiki_for_mcp: WikiQuery) -> None:
    _, tools = _make_mock_server_and_wiki(wiki_for_mcp)
    result = asyncio.run(tools["list_pages"].fn(domain=None, kind=None, updated_since=None))
    assert len(result["pages"]) == 2


def test_mcp_list_pages_updated_since_filters(wiki_for_mcp: WikiQuery) -> None:
    _, tools = _make_mock_server_and_wiki(wiki_for_mcp)
    result = asyncio.run(tools["list_pages"].fn(updated_since="2026-01-01T00:00:00Z"))
    page_ids = [p["page_id"] for p in result["pages"]]
    assert "mcp-new" in page_ids
    assert "mcp-old" not in page_ids


def test_mcp_list_pages_invalid_updated_since_raises_tool_error(
    wiki_for_mcp: WikiQuery,
) -> None:
    from mcp.server.fastmcp.exceptions import ToolError

    _, tools = _make_mock_server_and_wiki(wiki_for_mcp)
    with pytest.raises(ToolError, match="INVALID_ARGUMENT"):
        asyncio.run(tools["list_pages"].fn(updated_since="not-a-date"))


def test_mcp_list_pages_utc_offset_form(wiki_for_mcp: WikiQuery) -> None:
    """+00:00 offset form is accepted and produces the same result as Z form."""
    _, tools = _make_mock_server_and_wiki(wiki_for_mcp)
    result = asyncio.run(tools["list_pages"].fn(updated_since="2026-01-01T00:00:00+00:00"))
    page_ids = [p["page_id"] for p in result["pages"]]
    assert "mcp-new" in page_ids
    assert "mcp-old" not in page_ids


def test_mcp_list_pages_future_cutoff_returns_empty(wiki_for_mcp: WikiQuery) -> None:
    """Future cutoff returns no pages via MCP tool."""
    _, tools = _make_mock_server_and_wiki(wiki_for_mcp)
    result = asyncio.run(tools["list_pages"].fn(updated_since="2099-01-01T00:00:00Z"))
    assert result["pages"] == []


# ── Gap: boundary, combined filters, pagination, malformed date ──────────────


def test_list_pages_exact_boundary_excluded(temp_dir: Path) -> None:
    """A page with updated_at == updated_since is NOT returned (filter is strictly >)."""
    wiki = WikiQuery(wiki_base=temp_dir / "wiki_boundary")
    cutoff = datetime(2026, 5, 1, tzinfo=UTC)
    wiki.add_page(
        "exact-page",
        "Exact Page",
        "content",
        {"id": "exact-page", "title": "Exact Page", "updated_at": "2026-05-01T00:00:00Z"},
    )
    pages, _ = wiki.list_pages(updated_since=cutoff)
    assert pages == []


def test_list_pages_domain_and_updated_since_combined(temp_dir: Path) -> None:
    """Domain filter uses a different code branch; updated_since must still apply."""
    wiki = WikiQuery(wiki_base=temp_dir / "wiki_domain_combo")
    wiki.add_page(
        "alpha-old",
        "Alpha Old",
        "content",
        {
            "id": "alpha-old",
            "domain": "alpha",
            "title": "Alpha Old",
            "updated_at": "2025-01-01T00:00:00Z",
        },
    )
    wiki.add_page(
        "alpha-new",
        "Alpha New",
        "content",
        {
            "id": "alpha-new",
            "domain": "alpha",
            "title": "Alpha New",
            "updated_at": "2026-06-01T00:00:00Z",
        },
    )
    wiki.add_page(
        "beta-new",
        "Beta New",
        "content",
        {
            "id": "beta-new",
            "domain": "beta",
            "title": "Beta New",
            "updated_at": "2026-06-01T00:00:00Z",
        },
    )
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    pages, _ = wiki.list_pages(domain="alpha", updated_since=cutoff)
    page_ids = {p.get("id", p.get("page_id")) for p in pages}
    assert "alpha-new" in page_ids
    assert "alpha-old" not in page_ids
    assert "beta-new" not in page_ids


def test_list_pages_kind_and_updated_since_combined(temp_dir: Path) -> None:
    """Kind filter combined with updated_since filters both dimensions."""
    wiki = WikiQuery(wiki_base=temp_dir / "wiki_kind_combo")
    wiki.add_page(
        "concept-old",
        "Concept Old",
        "content",
        {
            "id": "concept-old",
            "kind": "concept",
            "title": "Concept Old",
            "updated_at": "2025-01-01T00:00:00Z",
        },
    )
    wiki.add_page(
        "concept-new",
        "Concept New",
        "content",
        {
            "id": "concept-new",
            "kind": "concept",
            "title": "Concept New",
            "updated_at": "2026-06-01T00:00:00Z",
        },
    )
    wiki.add_page(
        "page-new",
        "Page New",
        "content",
        {
            "id": "page-new",
            "kind": "page",
            "title": "Page New",
            "updated_at": "2026-06-01T00:00:00Z",
        },
    )
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    pages, _ = wiki.list_pages(kind="concept", updated_since=cutoff)
    page_ids = {p.get("id", p.get("page_id")) for p in pages}
    assert "concept-new" in page_ids
    assert "concept-old" not in page_ids
    assert "page-new" not in page_ids


def test_list_pages_cursor_paginates_filtered_results(temp_dir: Path) -> None:
    """Cursor pagination operates over the post-filter set, not the full set."""
    wiki = WikiQuery(wiki_base=temp_dir / "wiki_cursor_filter")
    for i in range(3):
        wiki.add_page(
            f"recent-{i}",
            f"Recent {i}",
            "content",
            {"id": f"recent-{i}", "title": f"Recent {i}", "updated_at": "2026-06-01T00:00:00Z"},
        )
    for i in range(2):
        wiki.add_page(
            f"old-{i}",
            f"Old {i}",
            "content",
            {"id": f"old-{i}", "title": f"Old {i}", "updated_at": "2025-01-01T00:00:00Z"},
        )
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    page1, cursor = wiki.list_pages(updated_since=cutoff, limit=2)
    assert len(page1) == 2
    assert cursor is not None
    page2, cursor2 = wiki.list_pages(updated_since=cutoff, limit=2, cursor=cursor)
    assert len(page2) == 1
    assert cursor2 is None
    all_ids = {p.get("id", p.get("page_id")) for p in page1 + page2}
    assert not any("old" in pid for pid in all_ids)


def test_list_pages_malformed_updated_at_excluded(temp_dir: Path) -> None:
    """A page with an unparseable updated_at value is excluded when a filter is active."""
    wiki = WikiQuery(wiki_base=temp_dir / "wiki_malformed")
    wiki.add_page(
        "bad-date",
        "Bad Date",
        "content",
        {"id": "bad-date", "title": "Bad Date", "updated_at": "not-a-valid-date"},
    )
    cutoff = datetime(2000, 1, 1, tzinfo=UTC)
    pages, _ = wiki.list_pages(updated_since=cutoff)
    assert pages == []


def test_list_pages_naive_stored_timestamp_no_typeerror(temp_dir: Path) -> None:
    """Stored updated_at without tz suffix is treated as UTC — no TypeError raised."""
    wiki = WikiQuery(wiki_base=temp_dir / "wiki_naive_stored")
    wiki.add_page(
        "naive-old",
        "Naive Old",
        "content",
        {"id": "naive-old", "title": "Naive Old", "updated_at": "2025-01-01T00:00:00"},
    )
    wiki.add_page(
        "naive-new",
        "Naive New",
        "content",
        {"id": "naive-new", "title": "Naive New", "updated_at": "2026-06-01T00:00:00"},
    )
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    pages, _ = wiki.list_pages(updated_since=cutoff)
    page_ids = {p.get("id", p.get("page_id")) for p in pages}
    assert "naive-new" in page_ids
    assert "naive-old" not in page_ids


def test_list_pages_naive_updated_since_no_typeerror(temp_dir: Path) -> None:
    """Naive updated_since (no tz) is treated as UTC — no TypeError against aware stored timestamps."""
    wiki = WikiQuery(wiki_base=temp_dir / "wiki_naive_since")
    wiki.add_page(
        "aware-old",
        "Aware Old",
        "content",
        {"id": "aware-old", "title": "Aware Old", "updated_at": "2025-01-01T00:00:00Z"},
    )
    wiki.add_page(
        "aware-new",
        "Aware New",
        "content",
        {"id": "aware-new", "title": "Aware New", "updated_at": "2026-06-01T00:00:00Z"},
    )
    cutoff = datetime(2026, 1, 1)  # naive — no tzinfo
    pages, _ = wiki.list_pages(updated_since=cutoff)
    page_ids = {p.get("id", p.get("page_id")) for p in pages}
    assert "aware-new" in page_ids
    assert "aware-old" not in page_ids
