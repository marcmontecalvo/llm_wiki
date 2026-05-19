"""Ingest and index-rebuild endpoints.

Routes:
    - POST /v1/daemon/jobs/index-rebuild
    - POST /v1/ingest
    - GET /v1/ingest/{job_id}
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from starlette.status import HTTP_404_NOT_FOUND, HTTP_422_UNPROCESSABLE_ENTITY

from llm_wiki.api.models import IngestRequest, IngestStatusResponse
from llm_wiki.api.user_jobs import UserJobStore
from llm_wiki.deps import get_user_job_store, get_wiki
from llm_wiki.query.search import WikiQuery

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["ingest"])


@router.post("/daemon/jobs/index-rebuild")
async def index_rebuild(wiki: WikiQuery = Depends(get_wiki)) -> dict:
    """Trigger an asynchronous index rebuild."""
    job_id = str(uuid.uuid4())

    async def _run() -> None:
        try:
            from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob

            job = IndexRebuildJob(wiki=wiki)
            await asyncio.to_thread(job.execute)
        except Exception as exc:
            logger.error("Index rebuild failed: %s", exc)

    asyncio.create_task(_run())
    return {"job_id": job_id, "status": "queued"}


@router.post("/ingest", response_model=IngestStatusResponse)
async def submit_ingest(
    req: IngestRequest,
    wiki: WikiQuery = Depends(get_wiki),
    store: UserJobStore = Depends(get_user_job_store),
) -> IngestStatusResponse:
    """Submit content for ingestion.

    Writes the content to ``inbox/new/`` and persists job status via UserJobStore.
    """
    job_id = str(uuid.uuid4())

    # Determine source path and domain
    source_path = req.source_path or ""
    domain = req.domain or "general"

    if not req.content and not source_path:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "INVALID_REQUEST",
                "message": "Either content or source_path must be provided",
            },
        )

    # Write content to inbox/new/ for daemon's InboxScanJob to pick up
    inbox_path = wiki.wiki_base / "inbox" / "new" / f"api-ingest-{job_id}.md"

    content: str = req.content or ""
    if req.source_path:
        try:
            source = Path(req.source_path)
            if source.exists():
                content = await asyncio.to_thread(source.read_text, encoding="utf-8")
            else:
                content = f"# Ingest from path\n\nSource: {source_path}\n"
        except Exception:
            content = f"# Ingest from path\n\nSource: {source_path}\n"
    elif not content:
        content = f"# Ingest from path\n\nSource: {source_path}\n"

    frontmatter = _build_frontmatter(domain, source_path)
    full_content = frontmatter + content

    await asyncio.to_thread(inbox_path.write_text, full_content, encoding="utf-8")

    status = IngestStatusResponse(
        job_id=job_id,
        status="queued",
        source_path=source_path,
        domain=domain,
        page_ids=[],
        indexed=False,
        message="Ingest job queued.",
    )
    await asyncio.to_thread(store.save, job_id, status)
    return status


@router.get("/ingest/{job_id}", response_model=IngestStatusResponse)
async def get_ingest_status(
    job_id: str,
    store: UserJobStore = Depends(get_user_job_store),
) -> IngestStatusResponse:
    """Poll ingest job status.

    Returns 404 if the job_id is not found.
    """
    status = await asyncio.to_thread(store.get, job_id)
    if status is None:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail={
                "error_code": "WIKI_NOT_FOUND",
                "message": f"Ingest job not found: {job_id}",
            },
        )
    return status


def _build_frontmatter(domain: str, source_path: str = "") -> str:
    """Build YAML frontmatter to attach to new inbox entries."""
    parts: list[str] = [
        "---",
        "kind: page",
        f"domain: {domain}",
    ]
    if source_path:
        parts.append(f"source: {source_path}")
    parts.append("---")
    return "\n".join(parts) + "\n"
