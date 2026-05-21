"""Query endpoint — POST /v1/query and GET /v1/query/{job_id}.

Supports three depths:
  - quick / standard: synchronous, returns 200 with results
  - deep: asynchronous, returns 202 with job_id; poll GET /v1/query/{job_id}

Deep query job state lives in ``app.state.deep_jobs`` (in-memory dict,
5-minute TTL, lost on restart).

Query log integration draws from Story 1.12 when available.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from llm_wiki.api.models import QueryRequest, QueryResponse, QueryResultItem
from llm_wiki.deps import get_profile_id, get_wiki
from llm_wiki.query.search import WikiQuery

logger = logging.getLogger(__name__)

router = APIRouter(tags=["query"])


@dataclass
class DeepQueryJob:
    """In-memory deep query job tracker."""

    status: Literal["running", "complete", "failed"]
    created_at: datetime = field(default_factory=datetime.utcnow)
    result: QueryResponse | None = None

    @property
    def is_expired(self) -> bool:
        """Return True if the job has exceeded its 5-minute TTL."""
        return (datetime.utcnow() - self.created_at).total_seconds() > 300


def _page_to_result(page: dict[str, Any]) -> QueryResultItem:
    """Convert a page metadata dict to a QueryResultItem.

    Sprint 1: confidence comes from frontmatter; provenance and
    contradictions are pulled from metadata if present.
    """
    return QueryResultItem(
        page_id=page.get("page_id", page.get("id", "")),
        title=page.get("title", ""),
        confidence=page.get("confidence", 0.0),
        provenance=page.get("sources", []),
        contradictions=page.get("contradictions", []),
    )


async def _log_query(
    request: Request,
    query_text: str,
    depth: str,
    result_count: int,
    confidence_avg: float | None,
    domain: str | None = None,
) -> None:
    """Log a query to the query log (Story 1.12).

    Uses the singleton from request.app.state.query_log — never instantiates
    a new store per request.
    """
    store = getattr(request.app.state, "query_log", None)
    if store is None:
        return
    from llm_wiki.query.log import QueryLogEntry  # noqa: PLC0414

    entry = QueryLogEntry(
        query_text=query_text,
        depth=depth,
        domains=[domain] if domain else [],
        result_count=result_count,
        confidence_avg=confidence_avg,
    )
    await asyncio.to_thread(store.log, entry)


@router.post("/v1/query", response_model=None)
async def query(
    req: QueryRequest,
    request: Request,
    wiki: WikiQuery = Depends(get_wiki),
    profile_id: str | None = Depends(get_profile_id),
) -> QueryResponse | JSONResponse:
    """Dispatch a query — sync (quick/standard) or async (deep)."""
    # quick / standard — synchronous (log only for these, not deep-background)
    if req.depth == "deep":
        return await _handle_deep_query(req, wiki, request, profile_id)

    pages = await asyncio.to_thread(
        wiki.search, req.query, domain=req.domain, scope_to_profile=profile_id
    )
    limit = 10 if req.depth == "quick" else 50
    results = [_page_to_result(p) for p in pages[:limit]]

    # Log query to query log (non-blocking, fire-and-forget)
    if results:
        confidence_avg = sum(r.confidence for r in results) / len(results)
    else:
        confidence_avg = None
    try:
        asyncio.create_task(
            _log_query(
                request,
                req.query,
                req.depth,
                len(results),
                confidence_avg,
                req.domain,  # type: ignore[arg-type]
            )
        )
    except Exception:
        pass

    return QueryResponse(results=results, timed_out=False, partial=False)


async def _handle_deep_query(
    req: QueryRequest,
    wiki: WikiQuery,
    request: Request,
    profile_id: str | None,
) -> JSONResponse:
    """Handle deep (async) query — returns 202 Accepted."""
    from fastapi.responses import JSONResponse

    job_id = str(uuid.uuid4())
    job = DeepQueryJob(status="running")
    request.app.state.deep_jobs[job_id] = job  # type: ignore[attr-defined]

    asyncio.create_task(_run_deep_query(job_id, req.query, wiki, request.app.state, profile_id))

    return JSONResponse(
        status_code=202,
        content=QueryResponse(job_id=job_id, status="queued", results=[]).model_dump(),
    )


async def _run_deep_query(
    job_id: str,
    query: str,
    wiki: WikiQuery,
    state: Any,
    profile_id: str | None,
) -> None:
    """Background task that runs deep synthesis and stores the result."""
    try:
        pages = await asyncio.to_thread(wiki.search, query, scope_to_profile=profile_id)
        # Pull llm_extraction from feature flags if available
        llm_extraction = False
        try:
            cfg = getattr(state, "wiki_config", None)
            if cfg and cfg.daemon.features.llm_extraction:
                llm_extraction = True
        except Exception:
            pass

        # Build the page content payloads for synthesis while collecting
        # page IDs that were used — used after synthesis to build results.
        page_ids = [p["page_id"] for p in pages]
        pages_with_content = await asyncio.to_thread(wiki.get_pages_with_content, page_ids)

        from llm_wiki.synthesis.engine import run_deep_query  # noqa: PLC0414

        result = await run_deep_query(
            query,
            pages_with_content,
            llm_extraction=llm_extraction,
            timeout=30.0,
        )

        r = QueryResponse(
            results=[_page_to_result(p) for p in pages_with_content if not result.timed_out],
            timed_out=result.timed_out,
            partial=result.partial,
            was_heuristic=result.was_heuristic,
            status="timed_out" if result.timed_out else "done",
        )

        job = state.deep_jobs.get(job_id)  # type: ignore[attr-defined]
        if job is not None:
            job.status = "complete"
            job.result = r
    except Exception as e:
        job = state.deep_jobs.get(job_id)  # type: ignore[attr-defined]
        if job is not None:
            job.status = "failed"
        logger.error("Deep query %s failed: %s", job_id, e)


@router.get("/v1/query/{job_id}")
async def get_query_job(
    job_id: str,
    request: Request,
    wiki: WikiQuery = Depends(get_wiki),
) -> JSONResponse:
    """Poll a deep query job — returns 200 with results or 404 if not found."""
    jobs: dict[str, DeepQueryJob] = request.app.state.deep_jobs  # type: ignore[attr-defined]
    job = jobs.get(job_id)

    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error_code": "WIKI_NOT_FOUND", "message": f"Job {job_id} not found"},
        )

    headers = {"X-Job-TTL": "300"}

    if job.status == "running":
        return JSONResponse(
            status_code=200,
            content={"status": "running", "job_id": job_id},
            headers=headers,
        )

    if job.status == "failed":
        return JSONResponse(
            status_code=200,
            content={"status": "failed", "job_id": job_id, "results": []},
            headers=headers,
        )

    # complete
    response = job.result if job.result else QueryResponse(results=[], timed_out=True, partial=True)
    return JSONResponse(
        status_code=200,
        content=response.model_dump(),
        headers=headers,
    )
