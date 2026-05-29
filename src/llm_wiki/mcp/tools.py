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
import datetime
import logging
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from mcp.server.fastmcp.exceptions import ToolError

from llm_wiki.api.errors import ERROR_MAP
from llm_wiki.api.services.archive import (
    archive_page as do_archive_page,
)
from llm_wiki.api.services.archive import (
    unarchive_page as do_unarchive_page,
)
from llm_wiki.api.services.dashboard import get_domain_dashboard
from llm_wiki.api.user_jobs import UserJobStore
from llm_wiki.exceptions import (
    ExportNotReadyError,
    WikiError,
    WikiNotFoundError,
)
from llm_wiki.query.log import QueryLogEntry  # noqa: PLC0414

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
    "UNKNOWN_KNOWLEDGE_CATEGORY": 1008,
    "UNKNOWN_FACT_KEY": 1009,
    "FACT_CONFLICT": 1010,
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


def _create_deep_query_runner_with_config(
    wiki,
    wiki_config=None,
    query_log=None,  # type: ignore[default-value]
) -> Callable:  # type: ignore[return-value]
    """Factory that creates a deep-query runner with wiki/wiki_config/query_log in closure."""

    async def run_deep_query_with_config_fn(query_text: str, pages: list[dict]) -> dict:
        """Run a deep query that blocks up to 30s for LLM synthesis."""
        page_ids = [p["page_id"] for p in pages]
        pages_with_content = await asyncio.to_thread(wiki.get_pages_with_content, page_ids)

        # Pull llm_extraction from feature flags if available
        llm_extraction = False
        if wiki_config and hasattr(wiki_config, "daemon"):
            llm_extraction = wiki_config.daemon.features.llm_extraction

        from llm_wiki.synthesis.engine import run_deep_query  # noqa: PLC0414

        result = await run_deep_query(
            query_text, pages_with_content, llm_extraction=llm_extraction, timeout=30.0
        )

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

    return run_deep_query_with_config_fn


def register_tools(
    server,
    wiki,
    wiki_config=None,
    query_log=None,
    knowledge_store=None,  # type: ignore[default-value]
) -> None:
    """Register MCP tools with the given server instance.

    Args:
        server: The MCP server (FastMCP) instance.
        wiki: WikiQuery singleton.
        wiki_config: Optional wiki configuration.
        query_log: Optional QueryLogStore singleton for logging queries.
        knowledge_store: Optional WorkspaceFactStore singleton for facts API.
    """
    state_dir = wiki.wiki_base / "state"
    store = UserJobStore(state_dir=state_dir)
    run_deep_query_with_config_fn = _create_deep_query_runner_with_config(
        wiki, wiki_config=wiki_config, query_log=query_log
    )

    @server.tool()
    async def query(
        query_text: str,
        depth: str = "quick",
        domain: str | None = None,
        profile_id: str | None = None,
        include_archived: bool = False,
    ) -> dict:
        """Query the wiki for information.

        Args:
            query_text: The search query.
            depth: One of 'quick', 'standard', or 'deep'.
                   Deep queries block up to 30s for LLM synthesis.
            domain: Optional domain filter.
            profile_id: Optional profile ID for multi-user domain scoping.
            include_archived: Include archived pages in results.
        """
        try:
            pages = await asyncio.to_thread(
                wiki.search,
                query_text,
                domain=domain,
                scope_to_profile=profile_id,
                include_archived=include_archived,
            )
        except WikiError as e:
            raise _handle_wiki_error(e) from e

        if depth == "deep":
            return await run_deep_query_with_config_fn(query_text, pages)  # type: ignore[no-any-return]

        limit = 10 if depth == "quick" else 50
        results = [_page_to_result(p) for p in pages[:limit]]

        # Log query to query log (non-blocking, fire-and-forget)
        if query_log is not None:
            try:
                confidence_avg = (
                    sum(r["confidence"] for r in results) / len(results) if results else None
                )
                entry = QueryLogEntry(
                    query_text=query_text,
                    depth=depth,
                    domains=[domain] if domain else [],
                    result_count=len(results),
                    confidence_avg=confidence_avg,
                )
                asyncio.create_task(asyncio.to_thread(query_log.log, entry))
            except Exception:
                pass

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
        profile_id: str | None = None,
        include_archived: bool = False,
    ) -> dict:
        """Search the wiki with merged full-text + vector results.

        Args:
            q: Search query text.
            domain: Optional domain filter.
            limit: Max results (1-100).
            profile_id: Optional profile ID for multi-user domain scoping.
            include_archived: Include archived pages in results.
        """
        try:
            pages = await asyncio.to_thread(
                wiki.search,
                q,
                domain=domain,
                limit=limit,
                scope_to_profile=profile_id,
                include_archived=include_archived,
            )
            results = [_page_to_search_result(p) for p in pages]
            return {"results": results}
        except WikiError as e:
            raise _handle_wiki_error(e) from e

    @server.tool()
    async def read_page(
        page_id: str,
    ) -> dict:
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
            if not content:
                for domain_dir in (wiki_base / "domains").iterdir():
                    if not domain_dir.is_dir():
                        continue
                    archive_file = domain_dir / "archive" / f"{page_id}.md"
                    if archive_file.exists():
                        content = await asyncio.to_thread(archive_file.read_text, encoding="utf-8")
                        break

            return _page_to_page_response(page, content)
        except WikiError as e:
            raise _handle_wiki_error(e) from e

    @server.tool()
    async def list_pages(
        domain: str | None = None,
        kind: str | None = None,
        updated_since: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
        include_archived: bool = False,
    ) -> dict:
        """List wiki pages with optional filtering and cursor-based pagination.

        Args:
            domain: Filter by domain.
            kind: Filter by page kind.
            updated_since: ISO8601 datetime string — return only pages updated after this time.
            cursor: Pagination cursor (base64-encoded offset).
            limit: Page size (1-200).
            include_archived: Include archived pages in results.
        """
        try:
            parsed_since: datetime.datetime | None = None
            if updated_since is not None:
                try:
                    parsed_since = datetime.datetime.fromisoformat(updated_since)
                except ValueError:
                    raise ToolError(
                        f"INVALID_ARGUMENT(1000): Invalid updated_since format: {updated_since!r}"
                    )

            page_items, next_cursor = await asyncio.to_thread(
                wiki.list_pages,
                domain=domain,
                kind=kind,
                updated_since=parsed_since,
                cursor=cursor,
                limit=limit,
                include_archived=include_archived,
            )

            results = [
                {
                    "page_id": meta.get("page_id", meta.get("id", "")),
                    "title": meta.get("title", ""),
                    "content": "",
                    "frontmatter": meta,
                    "domain": meta.get("domain", "general"),
                    "kind": meta.get("kind", "page"),
                    "confidence": meta.get("confidence", 0.0),
                }
                for meta in page_items
            ]

            return {
                "pages": results,
                "next_cursor": next_cursor,
                "total_hint": len(results),
            }
        except ToolError:
            raise
        except WikiError as e:
            raise _handle_wiki_error(e) from e

    @server.tool()
    async def export(
        fmt: str,
    ) -> dict:
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

    @server.tool()
    async def domain_dashboard(
        domain: str,
    ) -> dict:
        """Get a per-domain health dashboard.

        Returns page count, confidence distribution histogram,
        recent changes, low confidence count, stale count,
        and last governance run status.

        Args:
            domain: Domain identifier (e.g. 'general', 'nlp').
        """
        try:
            wiki_root = wiki.wiki_base
            result = get_domain_dashboard(domain, wiki_root)
            return result.model_dump()
        except WikiError as e:
            raise _handle_wiki_error(e) from e

    @server.tool()
    def list_archive(domain: str) -> dict:
        """List archived pages for a domain.

        Args:
            domain: Domain identifier (e.g. 'general', 'nlp').
        """
        from llm_wiki.utils.frontmatter import parse_frontmatter  # noqa: PLC0415

        wiki_base: Path = wiki.wiki_base
        archive_dir = wiki_base / "domains" / domain / "archive"

        pages: list[dict] = []
        if archive_dir.exists():
            for page_file in sorted(archive_dir.glob("*.md")):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, _ = parse_frontmatter(content)
                    pages.append(
                        {
                            "page_id": metadata.get("id", page_file.stem),
                            "title": metadata.get("title", page_file.stem),
                            "archived_at": metadata.get("archived_at"),
                            "updated_at": metadata.get("updated_at"),
                        }
                    )
                except Exception as e:
                    logger.warning("Failed to parse %s: %s", page_file, e)

        return {"kind": "archive", "pages": pages, "domain": domain, "total": len(pages)}

    @server.tool()
    async def archive_page(page_id: str) -> dict:
        """Archive a page by ID.

        Moves the page from pages/ to archive/ and marks it as archived.
        Idempotent — safe to call if the page is already archived.

        Args:
            page_id: The page identifier.
        """
        try:
            result = await asyncio.to_thread(do_archive_page, page_id, wiki.wiki_base)
            if result.get("status") == "success":
                return result
            raise ToolError(f"archive_failed: {result.get('error', 'unknown')}")
        except WikiError as e:
            raise _handle_wiki_error(e) from e

    @server.tool()
    async def unarchive_page(page_id: str) -> dict:
        """Restore an archived page back to pages/.

        Opposite of archive_page — restores the page and removes
        the archived_at frontmatter field.

        Args:
            page_id: The page identifier.
        """
        try:
            result = await asyncio.to_thread(do_unarchive_page, page_id, wiki.wiki_base)
            if result.get("status") == "success":
                return result
            raise ToolError(f"archive_failed: {result.get('error', 'unknown')}")
        except WikiError as e:
            raise _handle_wiki_error(e) from e

    # ── Knowledge facts tools (Epic HF) ───────────────────────────────────

    if knowledge_store is not None:

        @server.tool()
        async def fact_get(
            workspace_id: str,
            fact_key: str,
        ) -> dict:
            """Retrieve a single structured fact by key.

            Returns the full fact for the given workspace and key, or an
            error if the fact does not exist.

            Args:
                workspace_id: The workspace identifier.
                fact_key: The fact identifier (must be unique within the workspace).
            """
            try:
                fact = await asyncio.to_thread(knowledge_store.get_fact, workspace_id, fact_key)
                if fact is None:
                    raise ToolError(f"Fact not found: {fact_key}")
                return dict(fact.model_dump())
            except ToolError:
                raise
            except WikiError as e:
                raise _handle_wiki_error(e) from e

        @server.tool()
        async def fact_list(
            workspace_id: str,
            category: str | None = None,
            limit: int = 50,
        ) -> dict:
            """List facts for a workspace with optional category filter.

            Returns paginated results with a cursor for next-page navigation.

            Args:
                workspace_id: The workspace identifier.
                category: Optional category filter.
                limit: Max results (1-200).
            """
            try:
                result = await asyncio.to_thread(
                    knowledge_store.list_facts,
                    workspace_id,
                    category=category,
                    limit=limit,
                )
                return dict(result.model_dump())
            except ToolError:
                raise
            except WikiError as e:
                raise _handle_wiki_error(e) from e

        @server.tool()
        async def fact_put(
            workspace_id: str,
            fact_key: str,
            value: str,
            source_type: str = "manual_admin",
            category: str | None = None,
        ) -> dict:
            """Create or update a structured fact.

            Accepts simple key-value pairs and persists them atomically.

            Args:
                workspace_id: The workspace identifier.
                fact_key: The fact identifier (unique within the workspace).
                value: JSON string value for the fact.
                source_type: Source type identifier.
                category: Category identifier (e.g. 'workspace.roster').
                          Auto-derived from fact_key prefix if omitted, but
                          explicit category is preferred.
            """
            try:
                import json as _json  # noqa: PLC0415

                parsed_value = _json.loads(value) if isinstance(value, str) else value
                from datetime import UTC, datetime  # noqa: PLC0415

                from llm_wiki.knowledge.models import (  # noqa: PLC0415
                    KnowledgeFactWriteRequest,
                    KnowledgeSource,
                )

                _category = category or f"workspace.{fact_key.split('.')[0]}"
                req = KnowledgeFactWriteRequest(
                    category=_category,
                    key=fact_key,
                    value=parsed_value,
                    source=KnowledgeSource(
                        type=cast(
                            Any,
                            source_type if source_type else None,
                        ),
                        observed_at=datetime.now(tz=UTC),
                    ),
                )
                result = await asyncio.to_thread(knowledge_store.put_fact, workspace_id, req)
                return dict(result.model_dump())
            except ToolError:
                raise
            except WikiError as e:
                raise _handle_wiki_error(e) from e

        @server.tool()
        async def fact_delete(
            workspace_id: str,
            fact_key: str,
        ) -> dict:
            """Delete (tombstone) a structured fact.

            Sets the fact status to 'deleted' and returns the tombstone.

            Args:
                workspace_id: The workspace identifier.
                fact_key: The fact identifier to delete.
            """
            try:
                result = await asyncio.to_thread(
                    knowledge_store.delete_fact, workspace_id, fact_key
                )
                if result is None:
                    raise ToolError(f"Fact not found: {fact_key}")
                return dict(result.model_dump())
            except ToolError:
                raise
            except WikiError as e:
                raise _handle_wiki_error(e) from e

        @server.tool()
        async def fact_history(
            workspace_id: str,
            fact_key: str,
        ) -> list[dict]:
            """Return the full version history of a fact.

            Each entry is the complete KnowledgeFact state at a version point.

            Args:
                workspace_id: The workspace identifier.
                fact_key: The fact identifier.
            """
            try:
                history = await asyncio.to_thread(
                    knowledge_store.get_history, workspace_id, fact_key
                )
                return [f.model_dump() for f in history]
            except ToolError:
                raise
            except WikiError as e:
                raise _handle_wiki_error(e) from e

        @server.tool()
        async def fact_batch_put(
            workspace_id: str,
            facts: str,
        ) -> list[dict]:
            """Bulk write multiple structured facts.

            Each fact is processed atomically. Returns per-result status.

            Args:
                workspace_id: The workspace identifier.
                facts: JSON string array of {key, value, source_type, category} objects.
                       Each item MUST include 'category' (e.g. 'workspace.roster').
            """
            try:
                import json as _json  # noqa: PLC0415

                items = _json.loads(facts) if isinstance(facts, str) else facts
                from datetime import UTC, datetime  # noqa: PLC0415

                from llm_wiki.knowledge.models import (  # noqa: PLC0415
                    KnowledgeFactWriteRequest,
                    KnowledgeSource,
                )

                requests = []
                for item in items:
                    cat = item.get("category")
                    if cat is None:
                        raise ToolError(
                            "INVALID_REQUEST(1000): 'category' is required for each item in batch"
                        )
                    requests.append(
                        KnowledgeFactWriteRequest(
                            category=cat,
                            key=item["key"],
                            value=item["value"],
                            source=KnowledgeSource(
                                type=item.get("source_type", "manual_admin"),
                                observed_at=datetime.now(tz=UTC),
                            ),
                        )
                    )
                results = await asyncio.to_thread(knowledge_store.batch_put, workspace_id, requests)
                return [r.model_dump() for r in results]
            except ToolError:
                raise
            except WikiError as e:
                raise _handle_wiki_error(e) from e

        # ── Conflict tools (Epic HF.4) ────────────────────────────────────────

        @server.tool()
        async def conflict_list(
            workspace_id: str,
        ) -> dict:
            """List unresolved fact conflicts for a workspace.

            Returns a list of pending conflicts with candidate
            information, workspace, and fact keys.

            Args:
                workspace_id: The workspace identifier.
            """
            try:
                conflicts = await asyncio.to_thread(
                    knowledge_store.review_queue.list_conflicts,
                    workspace_id,
                )
                return {"conflicts": conflicts, "total": len(conflicts)}
            except ToolError:
                raise
            except WikiError as e:
                raise _handle_wiki_error(e) from e

        @server.tool()
        async def conflict_resolve(
            workspace_id: str,
            fact_key: str,
            choice: str,
            candidate_index: int | None = None,
        ) -> dict:
            """Resolve a fact conflict.

            Args:
                workspace_id: The workspace identifier.
                fact_key: The fact key involved in the conflict.
                choice: One of ``canonical``, ``reject``, ``stale``.
                candidate_index: Index of the winning candidate
                    (for ``canonical`` choice).
            """
            if choice not in ("canonical", "reject", "stale"):
                raise ToolError(
                    f"INVALID_ARGUMENT(1000): choice must be one of "
                    f"canonical, reject, stale — got {choice!r}"
                )
            try:
                result = await asyncio.to_thread(
                    knowledge_store.resolve_conflict,
                    workspace_id,
                    fact_key,
                    choice,
                    candidate_index,
                )
                error = result.get("error")
                if error == "conflict_not_found":
                    raise ToolError(
                        f"FACT_CONFLICT(1010): No unresolved conflict found for {fact_key}"
                    )
                if error == "INVALID_CANDIDATE_INDEX":
                    raise ToolError(
                        f"FACT_CONFLICT(1011): candidate_index must be 0..{result['candidate_count'] - 1}"
                    )
                return result  # type: ignore[no-any-return]
            except ToolError:
                raise
            except WikiError as e:
                raise _handle_wiki_error(e) from e

    # ── Category registry tool (Epic HF.3) ────────────────────────────────

    @server.tool()
    def categories_list() -> dict:
        """List the canonical category registry with legacy aliases.

        Returns the same data served by the REST
        GET /v1/workspaces/{workspace_id}/facts/categories endpoint.

        AC: 4
        """
        from llm_wiki.knowledge.categories import (  # noqa: PLC0415
            get_categories_list as _get_categories_list,
        )

        return _get_categories_list()
