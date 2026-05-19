"""MCP tool definitions.

All 7 tools delegate to the same service methods used by REST routes.
No business logic lives in this module -- it is a thin adaptation layer.

MCP error handling uses the SDK-native ``ToolError`` from
``mcp.server.fastmcp.exceptions``.  Application-level error codes
are positive integers (outside the JSON-RPC 2.0 reserved range) and
are included in the error message alongside the HTTP error-code string.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import logging
import uuid
from collections.abc import Callable
from pathlib import Path

from mcp.server.fastmcp.exceptions import ToolError

from llm_wiki.api.errors import ERROR_MAP
from llm_wiki.api.user_jobs import UserJobStore
from llm_wiki.exceptions import (
    ExportNotReadyError,
    WikiError,
    WikiNotFoundError,
)

logger = logging.getLogger(__name__)

# Application-level error codes -- positive integers, outside the
# JSON-RPC 2.0 reserved range (-32768 to -32000).
_MCP_ERROR_CODES: dict[str, int] = {
    "WIKI_NOT_FOUND": 1001,
    "DOMAIN_UNKNOWN": 1002,
    "INGEST_ERROR": 1003,
    "INDEX_STALE": 1004,
    "DAEMON_NOT_RUNNING": 1005,
    "EXPORT_NOT_READY": 1006,
    "INVALID_DEPTH": 1007,
}


def _handle_wiki_error(exc: WikiError) -> ToolError:
    """Convert a WikiError to an MCP ToolError.

    Uses the SDK-native ``ToolError``; includes the application error
    code (positive integer) and the HTTP error-code string in the
    message.
    """
    _, http_code = ERROR_MAP.get(type(exc), (500, "INTERNAL_ERROR"))
    code = _MCP_ERROR_CODES.get(http_code, 1000)
    return ToolError(f"{http_code}({code}): {exc}")


def _page_to_result(page: dict) -> dict:
    """Convert a page metadata dict to a query result item."""
    return {
        "page_id": page.get("page_id", page.get("id", "")),
        "title": page.get("title", ""),
        "confidence": page.get("confidence", 0.0),
        "provenance": page.get("sources", []),
        "contradictions": page.get("contradictions", []),
    }


def _page_to_search_result(page: dict) -> dict:
    """Convert a page metadata dict to a search result item."""
    return {
        "page_id": page.get("page_id", page.get("id", "")),
        "title": page.get("title", ""),
        "confidence": page.get("confidence", 0.0),
        "score": page.get("score", 0.0),
    }


def _build_frontmatter(domain: str, source_path: str = "") -> str:
    """Build YAML frontmatter for inbox entries (mirrors api/routers/ingest)."""
    parts = ["---", "kind: page", f"domain: {domain}"]
    if source_path:
        parts.append(f"source: {source_path}")
    parts.append("---")
    return "\n".join(parts) + "\n"


def _page_to_page_response(page: dict, content: str = "") -> dict:
    """Convert a page (with optional content) to a PageResponse-like dict."""
    frontmatter = page.get("frontmatter", {})
    if not frontmatter and content:
        try:
            from llm_wiki.utils.frontmatter import parse_frontmatter  # noqa: PLC0414

            parsed_fm, parsed_content = parse_frontmatter(content)
            if parsed_fm:
                frontmatter = parsed_fm
                content = parsed_content
        except Exception:
            pass

    return {
        "page_id": frontmatter.get("id", page.get("page_id", page.get("id", ""))),
        "title": frontmatter.get("title", ""),
        "content": content,
        "frontmatter": frontmatter,
        "domain": frontmatter.get("domain", "general"),
        "kind": frontmatter.get("kind", "page"),
        "confidence": frontmatter.get("confidence", 0.0),
    }


def _create_deep_query_runner(
    wiki,
) -> Callable:  # type: ignore[return-value]
    """Factory that creates a deep-query runner with wiki in closure.

    Returns an async callable that takes (query_text, pages) and returns
    a dict with results/timed_out/partial keys.
    """

    async def run_deep_query_fn(query_text: str, pages: list[dict]) -> dict:
        """Run a deep query that blocks up to 30s for LLM synthesis."""
        page_ids = [p["page_id"] for p in pages]
        pages_with_content = await asyncio.to_thread(wiki.get_pages_with_content, page_ids)

        from llm_wiki.synthesis.engine import run_deep_query  # noqa: PLC0414

        result = await run_deep_query(query_text, pages_with_content, timeout=30.0)

        if result.timed_out:
            return {
                "results": [_page_to_result(p) for p in pages_with_content],
                "timed_out": True,
                "partial": True,
            }

        return {
            "results": [_page_to_result(p) for p in pages_with_content],
            "timed_out": False,
            "partial": False,
        }

    return run_deep_query_fn


def register_tools(server, wiki) -> None:
    """Register MCP tools with the given server instance.

    Args:
        server: The MCP server (FastMCP) instance.
        wiki: WikiQuery singleton.
    """
    state_dir = wiki.wiki_base / "state"
    store = UserJobStore(state_dir=state_dir)
    run_deep_query_fn = _create_deep_query_runner(wiki)

    @server.tool()
    async def query(
        query_text: str,
        depth: str = "quick",
        domain: str | None = None,
        profile_id: str | None = None,
    ) -> dict:
        """Query the wiki for information.

        Args:
            query_text: The search query.
            depth: One of 'quick', 'standard', or 'deep'.
                   Deep queries block up to 30s for LLM synthesis.
            domain: Optional domain filter.
            profile_id: Optional profile ID for multi-user domain scoping.
        """
        try:
            pages = await asyncio.to_thread(
                wiki.search, query_text, domain=domain, scope_to_profile=profile_id
            )
        except WikiError as e:
            raise _handle_wiki_error(e) from e

        if depth == "deep":
            return await run_deep_query_fn(query_text, pages)  # type: ignore[no-any-return]

        limit = 10 if depth == "quick" else 50
        results = [_page_to_result(p) for p in pages[:limit]]
        return {"results": results, "timed_out": False, "partial": False}

    @server.tool()
    async def ingest(
        source_path: str | None = None,
        content: str | None = None,
        domain: str | None = None,
    ) -> dict:
        """Ingest content into the wiki.

        Args:
            source_path: Path to a file to ingest.
            content: Markdown content to ingest.
            domain: Target domain (defaults to 'general').
        """
        try:
            job_id = str(uuid.uuid4())
            effective_domain = domain or "general"

            if not content and not source_path:
                raise ToolError(
                    "INVALID_REQUEST(1000): Either content or source_path must be provided"
                )

            inbox_path = wiki.wiki_base / "inbox" / "new" / f"api-ingest-{job_id}.md"
            item_content: str = content or ""
            if source_path:
                try:
                    source = Path(source_path)
                    if source.exists():
                        item_content = await asyncio.to_thread(source.read_text, encoding="utf-8")
                    else:
                        item_content = f"# Ingest from path\n\nSource: {source_path}\n"
                except Exception:
                    item_content = f"# Ingest from path\n\nSource: {source_path}\n"
            elif not item_content:
                item_content = f"# Ingest from path\n\nSource: {source_path}\n"

            frontmatter_str = _build_frontmatter(effective_domain, source_path or "")
            full_content = frontmatter_str + item_content

            await asyncio.to_thread(inbox_path.write_text, full_content, encoding="utf-8")

            from llm_wiki.api.models import IngestStatusResponse  # noqa: PLC0414

            status = IngestStatusResponse(
                job_id=job_id,
                status="queued",
                source_path=source_path,
                domain=effective_domain,
                page_ids=[],
                indexed=False,
                message="Ingest job queued.",
            )
            await asyncio.to_thread(store.save, job_id, status)
            return status.model_dump()
        except ToolError:
            raise
        except WikiError as e:
            raise _handle_wiki_error(e) from e

    @server.tool()
    async def ingest_status(job_id: str) -> dict:
        """Check the status of an ingest job.

        Args:
            job_id: The ingest job ID returned by the ingest tool.
        """
        try:
            status = await asyncio.to_thread(store.get, job_id)
            if status is None:
                raise WikiNotFoundError(f"Ingest job not found: {job_id}")
            return status.model_dump()
        except WikiError as e:
            raise _handle_wiki_error(e) from e

    @server.tool()
    async def search(
        q: str,
        domain: str | None = None,
        limit: int = 10,
    ) -> dict:
        """Search the wiki with merged full-text + vector results.

        Args:
            q: Search query text.
            domain: Optional domain filter.
            limit: Max results (1-100).
        """
        try:
            pages = await asyncio.to_thread(wiki.search, q, domain=domain, limit=limit)
            results = [_page_to_search_result(p) for p in pages]
            return {"results": results}
        except WikiError as e:
            raise _handle_wiki_error(e) from e

    @server.tool()
    async def read_page(page_id: str) -> dict:
        """Read a single page by ID.

        Args:
            page_id: The page identifier (e.g. 'general-python-typing').
        """
        try:
            page = wiki.get_page(page_id)
            if page is None:
                raise WikiNotFoundError(f"Page not found: {page_id}")
            # Get full content from filesystem
            wiki_base = wiki.wiki_base
            content = ""
            for domain_dir in (wiki_base / "domains").iterdir():
                if not domain_dir.is_dir():
                    continue
                page_file = domain_dir / "pages" / f"{page_id}.md"
                if page_file.exists():
                    content = await asyncio.to_thread(page_file.read_text, encoding="utf-8")
                    break
            if not content:
                shared_file = wiki_base / "shared" / f"{page_id}.md"
                if shared_file.exists():
                    content = await asyncio.to_thread(shared_file.read_text, encoding="utf-8")

            return _page_to_page_response(page, content)
        except WikiError as e:
            raise _handle_wiki_error(e) from e

    @server.tool()
    async def list_pages(
        domain: str | None = None,
        kind: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict:
        """List wiki pages with optional filtering and cursor-based pagination.

        Args:
            domain: Filter by domain.
            kind: Filter by page kind.
            cursor: Pagination cursor (base64-encoded offset).
            limit: Page size (1-200).
        """
        try:
            all_pages: list[dict] = []

            if domain or kind:
                if domain:
                    page_ids = wiki.metadata_index.by_domain.get(domain, set())
                else:
                    page_ids = set(wiki.metadata_index.pages.keys())

                for pid in page_ids:
                    meta = wiki.metadata_index.get_page(pid)
                    if meta is None:
                        continue
                    if kind and meta.get("kind") != kind:
                        continue
                    all_pages.append(meta)
            else:
                all_pages = list(wiki.metadata_index.pages.values())

            offset = 0
            if cursor:
                try:
                    offset = int(base64.b64decode(cursor).decode())
                except Exception:
                    offset = 0

            total = len(all_pages)
            page_items = all_pages[offset : offset + limit]
            next_cursor = (
                base64.b64encode(str(offset + limit).encode()).decode()
                if (offset + limit) < total
                else None
            )

            results = []
            for meta in page_items:
                results.append(
                    {
                        "page_id": meta.get("page_id", meta.get("id", "")),
                        "title": meta.get("title", ""),
                        "content": "",
                        "frontmatter": meta,
                        "domain": meta.get("domain", "general"),
                        "kind": meta.get("kind", "page"),
                        "confidence": meta.get("confidence", 0.0),
                    }
                )

            return {
                "pages": results,
                "next_cursor": next_cursor,
                "total_hint": total,
            }
        except WikiError as e:
            raise _handle_wiki_error(e) from e

    @server.tool()
    async def export(fmt: str) -> dict:
        """Get an exported wiki artifact.

        Supported formats: 'llms-txt', 'llms-full-txt', 'json-ld'.

        Args:
            fmt: Export format name.
        """
        try:
            fmt_map: dict[str, str] = {
                "llms-txt": "llms.txt",
                "llms-full-txt": "llms-full.txt",
                "json-ld": "graph.jsonld",
            }
            filename = fmt_map.get(fmt)
            if not filename:
                raise ExportNotReadyError(f"Unknown export format: {fmt}")

            exports_dir = wiki.wiki_base / "exports"
            path = exports_dir / filename

            if not path.exists():
                raise ExportNotReadyError(
                    f"Export '{fmt}' not yet generated. POST /v1/export to trigger."
                )

            content = await asyncio.to_thread(path.read_text, encoding="utf-8")
            stat = await asyncio.to_thread(path.stat)
            last_modified = datetime.datetime.fromtimestamp(
                stat.st_mtime, tz=datetime.UTC
            ).strftime("%a, %d %b %Y %H:%M:%S GMT")

            media_type = "text/plain"
            if fmt == "json-ld":
                media_type = "application/ld+json"

            return {
                "format": fmt,
                "content": content,
                "media_type": media_type,
                "last_modified": last_modified,
            }
        except WikiError as e:
            raise _handle_wiki_error(e) from e
